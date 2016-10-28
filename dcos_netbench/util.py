import os
import shlex
import subprocess

ttracker = "ttracker"  # path to ttracker executable
ttracker_url = "https://github.com/nlsun/ttracker/releases/download/v0.1.0/ttracker_linux_amd64"

def reset_file(file_fd):
    file_fd.seek(0)
    file_fd.truncate()
    file_fd.flush()


def init_swarm(config):
    """
    The purpose of this is to set up docker swarm on a cluster that already
    has docker1.12 installed
    """

    user = config.user
    master = config.ms
    agent1 = config.ag1
    agent2 = config.ag2
    network_name = config.dnet

    comm = ("ssh -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "'curl -fsSL http://169.254.169.254/latest/meta-data/local-ipv4'")
    private_master = subprocess.check_output(shlex.split(comm)).decode()

    advertise_addr = "{}:{}".format(private_master, 2377)

    comm = ("ssh -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "'sudo docker swarm init --advertise-addr {}'".format(advertise_addr))
    subprocess.call(shlex.split(comm))

    comm = ("ssh -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "'sudo docker swarm join-token worker -q'")
    token = subprocess.check_output(shlex.split(comm)).decode().strip()

    for ag in (agent1, agent2):
        agent_swarm(user, master, ag, token, advertise_addr)

    comm = ("ssh -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "'sudo docker network create " +
            "--driver overlay --subnet 10.0.9.0/24 {}'".format(network_name))
    subprocess.call(shlex.split(comm))


def agent_swarm(user, master, agent, token, advertise_addr):
    comm = ("ssh -A -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "ssh -o 'StrictHostKeyChecking=no' {} ".format(agent) +
            "'sudo docker swarm join --token {} {}'".format(token, advertise_addr))
    print(comm)
    return subprocess.call(shlex.split(comm))

def allnodes(master, user):
    """
    Return a list of node addresses
    """
    comm = ('ssh -o "StrictHostKeyChecking=no" {}@{} '.format(user, master) +
            '"host master.mesos && host slave.mesos"')
    nodes = []
    for ln in subprocess.check_output(shlex.split(comm)).decode().splitlines():
        nodes.append(ln.strip().split()[3])
    return nodes


def init_ttracker(config):
    user = config.user
    master = config.ms
    for nd in allnodes(master, user):
        """
        - All quotes require 1 slash to be escaped from python
          and then another 2 slashes to produce a slash to escape in the shell.
        - All dollar signs need to be escaped in the shell so they don't
          evaluate immediately
        """
        comm = ("""ssh -A -o StrictHostKeyChecking=no {}@{} """.format(user, master) +
                """'ssh -o StrictHostKeyChecking=no {} """.format(nd) +
                """ "curl -L -o {} {} && """.format(ttracker, ttracker_url) +
                """  chmod 755 {} && """.format(ttracker) +
                """  export BENCHSPEC='' && """ +
                """  for pid in \$(pgrep beam.smp); do """ +
                """    export BENCHSPEC=\\\"\${BENCHSPEC};\$(basename \$(sudo readlink -f /proc/\${pid}/cwd)),\${pid}\\\" ; """ +
                """  done && """ +
                # Remove first character, which is an extra semicolon
                """  export BENCHSPEC=\\\"\$(printf \\\"\$BENCHSPEC\\\" | cut -c 2-)\\\" && """ +
                """  echo \\\"\$BENCHSPEC\\\" && echo \$(hostname) && """ +
                """  sudo systemd-run --unit ttracker ./ttracker -spec \\\"\$BENCHSPEC\\\" -prefix \\\"\$HOME/\$(hostname)\\\" """ +
                """ " """ +
                """' """)
        print(comm)
        subprocess.call(shlex.split(comm))


def clean_ttracker(config):
    user = config.user
    master = config.ms
    for nd in allnodes(master, user):
        comm = ("""ssh -A -o StrictHostKeyChecking=no {}@{} """.format(user, master) +
                """'ssh -o StrictHostKeyChecking=no {} """.format(nd) +
                """ "sudo systemctl stop ttracker" """ +
                """' """)
        subprocess.call(shlex.split(comm))


def fetch_ttracker(config):
    """
    Creates a directory with the same prefix as used elsewhere and sticks
    all of the files output by ttracker into there
    """
    user = config.user
    master = config.ms
    newfile_marker = "DCOS_NETBENCH_NEWFILE"
    logfile_buffer = None
    logfile_name = None
    incoming_filename = False
    outdir = "{}ttracker_out".format(config.prefix)
    try:
        os.mkdir(outdir)
    except OSError as e:
        print("OSError: {}".format(e))
    for nd in allnodes(master, user):
        """
        The format of the output is:

        DCOS_NETBENCH_NEWFILE
        <filename1>
        <file1 content>
        DCOS_NETBENCH_NEWFILE
        <filename2>
        <file2 content>
        ...

        """
        comm = ("""ssh -A -o StrictHostKeyChecking=no {}@{} """.format(user, master) +
                """'ssh -o StrictHostKeyChecking=no {} """.format(nd) +
                """ "for fl in \$(hostname)*; do """ +
                """    echo \\\"{}\\\" && """.format(newfile_marker) +
                """    echo \${fl} && """ +
                """    cat \${fl} && """ +
                """    echo \\\"\\\" ; """ +
                """  done """ +
                """ " """ +
                """' """)
        print(comm)
        output = subprocess.check_output(shlex.split(comm))
        for line in output.decode().splitlines():
            if line == newfile_marker:
                if not (logfile_name is None and logfile_buffer is None):
                    flush_to_file(logfile_name, logfile_buffer)
                logfile_buffer = ""
                logfile_name = ""
                incoming_filename = True
                continue
            if incoming_filename == True:
                logfile_name = os.path.join(outdir, line)
                incoming_filename = False
                continue
            logfile_buffer += line + os.linesep
        if not (logfile_name is None and logfile_buffer is None):
            flush_to_file(logfile_name, logfile_buffer)


def flush_to_file(filename, filecontent):
    fd = open(filename, 'w+')
    fd.truncate()
    fd.write(filecontent)
    fd.flush()
    fd.close()
