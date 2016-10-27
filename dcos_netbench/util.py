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
    # for each master+agent:
    #   download ttracker, rename executable to ttracker
    #   get the pid of the processes that you need
    #   run and disown ttracker to detach
    user = config.user
    master = config.ms
    for nd in allnodes(master, user):
        # - All quotes require 1 slash to be escaped from python
        #   and then another 2 slashes to produce a slash to escape in the shell.
        # - All dollar signs need to be escaped in the shell so they don't
        #   evaluate immediately
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
    # for each master+agent:
    #   kill all instances of ttracker
    user = config.user
    master = config.ms
    for nd in allnodes(master, user):
        comm = ("""ssh -A -o StrictHostKeyChecking=no {}@{} """.format(user, master) +
                """'ssh -o StrictHostKeyChecking=no {} """.format(nd) +
                """ "sudo systemctl stop ttracker" """ +
                """' """)
        subprocess.call(shlex.split(comm))

def fetch_ttracker(config):
    # Fetch all relevant ttracker output
    pass
