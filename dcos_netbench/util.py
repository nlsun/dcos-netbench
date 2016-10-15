import shlex
import subprocess


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
