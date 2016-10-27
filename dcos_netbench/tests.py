#!/usr/bin/env python

import json
import shlex
import subprocess
import time

from dcos_netbench import util


def http_dockeroverlay(config):
    docker_wait(config.ms, config.user)
    hostname1 = get_hostname(config.ms, config.user, config.ag1)
    hostname2 = get_hostname(config.ms, config.user, config.ag2)
    docker_create(config.ms, config.user, config.dnet, "httpd", hostname1,
                  "nlsun/httpd")
    docker_wait(config.ms, config.user)
    docker_create(config.ms, config.user, config.dnet, "vegeta", hostname2,
                  "nlsun/vegeta", gen_vegeta("httpd"))
    docker_wait(config.ms, config.user)
    raw_log = docker_http_wait_output(config.ms, config.user, config.ag2, "vegeta")
    docker_rm(config.ms, config.user, "httpd")
    docker_rm(config.ms, config.user, "vegeta")
    return raw_log.decode()


def redis_dockeroverlay(config):
    docker_wait(config.ms, config.user)
    hostname1 = get_hostname(config.ms, config.user, config.ag1)
    hostname2 = get_hostname(config.ms, config.user, config.ag2)
    docker_create(config.ms, config.user, config.dnet, "redis", hostname1,
                  "redis")
    docker_wait(config.ms, config.user)
    docker_create(config.ms, config.user, config.dnet, "redis-bench", hostname2,
                  "redis", gen_redis_bench(("redis", "6379")))
    docker_wait(config.ms, config.user)
    raw_log = docker_redis_wait_output(config.ms, config.user, config.ag2, "redis-bench")
    docker_rm(config.ms, config.user, "redis")
    docker_rm(config.ms, config.user, "redis-bench")
    return raw_log.decode()


def docker_check_output(master, user, host, name):
    comm = """\
           ssh -A -o 'StrictHostKeyChecking=no' {}@{} \
           'sudo docker inspect --format "{{{{.Status.ContainerStatus.ContainerID}}}}" \
           $(sudo docker service ps {} | tail -n +2 | head -n1 | cut -d" " -f1)' \
           """.format(user, master, name)
    res = subprocess.check_output(shlex.split(comm))
    container_id = res.decode()

    comm = """\
           ssh -A -o 'StrictHostKeyChecking=no' {}@{} \
           ssh {} "sudo docker logs {}" \
           """.format(user, master, host, container_id)
    return subprocess.check_output(shlex.split(comm))


def docker_http_wait_output(master, user, host, name):
    finished = ""
    raw_log = None
    while vegeta_check(finished):
        raw_log = docker_check_output(master, user, host, name)
        finished = raw_log.decode()
        time.sleep(1)
    return raw_log


def docker_redis_wait_output(master, user, host, name):
    finished = ""
    raw_log = None
    while redis_check(finished):
        raw_log = docker_check_output(master, user, host, name)
        finished = raw_log.decode()
        time.sleep(1)
    return raw_log


def docker_create(master, user, network_name, name, hostname, image, command=None):
    if command is None:
        parsed_command = ""
    else:
        parsed_command = 'bash -c "{}"'.format(command)
    comm = """\
           ssh -A -o 'StrictHostKeyChecking=no' {}@{} \
           'sudo docker service create --network {} --replicas 1 --name {} \
           --constraint "node.hostname == {}" {} {}' \
           """.format(user, master, network_name, name, hostname, image, parsed_command)
    return subprocess.call(shlex.split(comm))


def docker_rm(master, user, name):
    comm = """\
           ssh -A -o 'StrictHostKeyChecking=no' {}@{} \
           'sudo docker service rm {}' \
           """.format(user, master, name)
    return subprocess.call(shlex.split(comm))


def get_hostname(master, user, address):
    comm = ("ssh -A -o 'StrictHostKeyChecking=no' {}@{} ".format(user, master) +
            "ssh -o 'StrictHostKeyChecking=no' {} ".format(address) +
            "'hostname'")
    return subprocess.check_output(shlex.split(comm)).decode()


def http_bridge(config):
    def bridge_vegeta(unused):
        deploy_wait()
        return srv_hostport("_web._httpd._tcp.marathon.mesos")
    return http_helper(config.sfile, config.cfile, config.tmpfd,
                       bridge_vegeta, config.ms, config.ag1, config.ag2)


def http_host(config):
    def host_vegeta(host):
        deploy_wait()
        return host + ":80"
    return http_helper(config.sfile, config.cfile, config.tmpfd,
                       host_vegeta, config.ms, config.ag1, config.ag2)


def http_overlay(config):
    def overlay_vegeta(unused):
        deploy_wait()
        return "httpd.marathon.containerip.dcos.thisdcos.directory:80"
    return http_helper(config.sfile, config.cfile, config.tmpfd,
                       overlay_vegeta, config.ms, config.ag1, config.ag2)


def http_helper(server_file, client_file, tmp_file, get_vegeta,
                master, agent1, agent2):
    deploy_wait()
    server_fd = open(server_file, 'r')
    server_json = json.load(server_fd)
    server_json["constraints"] = [["hostname", "LIKE", agent1]]
    util.reset_file(tmp_file)
    tmp_file.write(json.dumps(server_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    client_fd = open(client_file, 'r')
    client_json = json.load(client_fd)
    client_json["cmd"] = gen_vegeta(get_vegeta(agent1))
    client_json["constraints"] = [["hostname", "LIKE", agent2]]
    util.reset_file(tmp_file)
    tmp_file.write(json.dumps(client_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    raw_log = vegeta_wait()
    subprocess.call(shlex.split("dcos marathon app remove httpd"))
    subprocess.call(shlex.split("dcos marathon app remove vegeta"))
    return raw_log.decode()


def vegeta_check(output):
    return "latencies" not in output


def vegeta_wait():
    finished = ""
    raw_log = None
    while vegeta_check(finished):
        raw_log = subprocess.check_output(shlex.split("bash -c \"dcos task log vegeta --lines=1; exit 0\""))
        finished = raw_log.decode()
        time.sleep(1)
    return raw_log


def siege_wait():
    finished = ""
    raw_log = None
    while "Transaction rate:" not in finished:
        raw_log = subprocess.check_output(shlex.split("bash -c \"dcos task log vegeta --lines=13; exit 0\""))
        finished = raw_log.decode()
        time.sleep(1)
    return raw_log


def redis_bridge(config):
    def bridge_bench(unused):
        deploy_wait()
        srv = "_redis._redis._tcp.marathon.mesos"
        return (srv_host(srv), srv_port(srv))
    return redis_helper(config.sfile, config.cfile, config.tmpfd,
                        bridge_bench, config.ms, config.ag1, config.ag2)


def redis_host(config):
    def host_bench(host):
        deploy_wait()
        # time.sleep(5)
        return (host, "6379")
    return redis_helper(config.sfile, config.cfile, config.tmpfd,
                        host_bench, config.ms, config.ag1, config.ag2)


def redis_overlay(config):
    def overlay_bench(unused):
        deploy_wait()
        url = "redis.marathon.containerip.dcos.thisdcos.directory"
        return (url, "6379")
    return redis_helper(config.sfile, config.cfile, config.tmpfd,
                        overlay_bench, config.ms, config.ag1, config.ag2)


def srv_hostport(srv):
    return "{}:{}".format(srv_host(srv), srv_port(srv))


def srv_host(srv):
    return "$(host -t srv {} | cut -f8 -d' ')".format(srv)


def srv_port(srv):
    return "$(host -t srv {} | cut -f7 -d' ')".format(srv)


def redis_check(output):
    return "MSET (10 keys)" not in output


def redis_helper(server_file, client_file, tmp_file, get_bench,
                 master, agent1, agent2):
    deploy_wait()
    server_fd = open(server_file, 'r')
    server_json = json.load(server_fd)
    server_json["constraints"] = [["hostname", "LIKE", agent1]]
    util.reset_file(tmp_file)
    tmp_file.write(json.dumps(server_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    client_fd = open(client_file, 'r')
    client_json = json.load(client_fd)
    client_json["cmd"] = gen_redis_bench(get_bench(agent1))
    client_json["constraints"] = [["hostname", "LIKE", agent2]]
    util.reset_file(tmp_file)
    tmp_file.write(json.dumps(client_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    finished = ""
    raw_log = None
    while redis_check(finished):
        raw_log = subprocess.check_output(shlex.split("bash -c \"dcos task log redis-bench --lines=17; exit 0\""))
        finished = raw_log.decode()
        time.sleep(1)
    subprocess.call(shlex.split("dcos marathon app remove redis"))
    subprocess.call(shlex.split("dcos marathon app remove redis-bench"))
    return raw_log.decode()


def gen_siege(host):
    return ("bash -c \"siege -b --time=5s {} > /dev/null && " +
            "(siege -b -c 1 -t 1m {} 3>&2 2>&1 1>&3) 2>/dev/null && " +
            "sleep infinity\"").format(host, host)


def gen_vegeta(get_host):
    return ('export NETBENCH_HOST="{}" && '.format(get_host) +
            'curl --fail $NETBENCH_HOST && ' +
            'echo "GET http://$NETBENCH_HOST/" | vegeta attack -duration=5s >/dev/null && ' +
            'echo "GET http://$NETBENCH_HOST/" | vegeta attack -duration=1m | ' +
            'vegeta report -reporter=json && sleep infinity')


def gen_redis_bench(tup):
    get_host, get_port = tup
    return ('export REDISBENCH_HOST="{}" && '.format(get_host) +
            'export REDISBENCH_PORT="{}" && '.format(get_port) +
            'netcat -z "$REDISBENCH_HOST" "$REDISBENCH_PORT" && ' +
            'sleep 10 && ' +
            'redis-benchmark --csv -h "$REDISBENCH_HOST" -p "$REDISBENCH_PORT" && ' +
            'sleep infinity')


def deploy_wait():
    comm = "bash -c 'while dcos marathon deployment list > /dev/null 2>&1; do sleep 1; done'"
    subprocess.call(shlex.split(comm))


def docker_check(master, user):
    comm = "ssh {}@{} 'sudo docker service ls'".format(user, master)
    res = subprocess.check_output(shlex.split(comm))
    parsed = [line.split()[2] for line in res.decode().splitlines()[1:]]
    for stat in parsed:
        top, bot = stat.split("/")
        if top != bot:
            return False
    return True


def docker_wait(master, user):
    while not docker_check(master, user):
        time.sleep(1)
