#!/usr/bin/env python

import subprocess
import shlex
import json
import time

# XXX make sure dcos cli is connected
# XXX does not do any waiting correctly, just does sleeps
# XXX have the first sleep be longer, so the image can pull
# XXX add notion of repetitions, how many times to run each command before
#   averaging and outputting that.

def http_bridge(os_type, server_file, client_file, tmp_file):
    def bridge_vegeta():
        deploy_wait()
        time.sleep(5)
        host, port = bridge_hostport(os_type, "_web._httpd._tcp.marathon.mesos")
        return host + ":" + port
    return http_helper(os_type, server_file, client_file, tmp_file, bridge_vegeta)

def http_host(os_type, server_file, client_file, tmp_file):
    def host_vegeta():
        deploy_wait()
        time.sleep(5)
        host = host_host(os_type)
        return host + ":80"
    return http_helper(os_type, server_file, client_file, tmp_file, host_vegeta)

def http_overlay(os_type, server_file, client_file, tmp_file):
    def overlay_vegeta():
        deploy_wait()
        time.sleep(30)
        url = "httpd.marathon.containerip.dcos.thisdcos.directory:80"
        return url
    return http_helper(os_type, server_file, client_file, tmp_file, overlay_vegeta)

def http_helper(os_type, server_file, client_file, tmp_file, get_vegeta):
    deploy_wait()
    subprocess.call(shlex.split("dcos marathon app add " + server_file))
    client_fd = open(client_file, 'r')
    client_json = json.load(client_fd)
    client_json["cmd"] = gen_vegeta(get_vegeta())
    tmp_file.write(json.dumps(client_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    raw_log = vegeta_wait()
    subprocess.call(shlex.split("dcos marathon app remove httpd"))
    subprocess.call(shlex.split("dcos marathon app remove vegeta"))
    return raw_log.decode()

def vegeta_wait():
    finished = ""
    raw_log = None
    while "latencies" not in finished:
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

def redis_bridge(os_type, server_file, client_file, tmp_file):
    def bridge_bench():
        deploy_wait()
        time.sleep(5)
        return bridge_hostport(os_type, "_redis._redis._tcp.marathon.mesos")
    return redis_helper(os_type, server_file, client_file, tmp_file, bridge_bench)

def redis_host(os_type, server_file, client_file, tmp_file):
    def host_bench():
        deploy_wait()
        time.sleep(5)
        host = host_host(os_type)
        return (host, "6379")
    return redis_helper(os_type, server_file, client_file, tmp_file, host_bench)

def redis_overlay(os_type, server_file, client_file, tmp_file):
    def overlay_bench():
        deploy_wait()
        time.sleep(30)
        url = "redis.marathon.containerip.dcos.thisdcos.directory"
        return (url, "6379")
    return redis_helper(os_type, server_file, client_file, tmp_file, overlay_bench)

def bridge_hostport(os_type, addr):
    split_port = []
    while len(split_port) != 8:
        ssh_comm = ("dcos node ssh --leader --master-proxy " +
                    "--option 'ForwardAgent=yes' " +
                    "--option 'LogLevel=QUIET' " +
                    "--option 'StrictHostKeyChecking=no' " +
                    "--option 'UserKnownHostsFile=/dev/null' " +
                    "--user '{}' ".format(os_type) +
                    "'host -t srv {}'".format(addr))
        raw_port = subprocess.check_output(shlex.split(ssh_comm))
        split_port = raw_port.decode().split()
        time.sleep(1)
    port = split_port[6]
    host = split_port[7]
    return (host, port)

def host_host(os_type):
    ssh_comm = ("dcos node ssh --leader --master-proxy " +
                "--option 'ForwardAgent=yes' " +
                "--option 'LogLevel=QUIET' " +
                "--option 'StrictHostKeyChecking=no' " +
                "--option 'UserKnownHostsFile=/dev/null' " +
                "--user '{}' ".format(os_type) +
                "'host slave.mesos'")
    raw_port = subprocess.check_output(shlex.split(ssh_comm))
    split_port = raw_port.decode().split()
    host = split_port[3]
    return host

def redis_helper(os_type, server_file, client_file, tmp_file, get_bench):
    deploy_wait()
    subprocess.call(shlex.split("dcos marathon app add " + server_file))
    client_fd = open(client_file, 'r')
    client_json = json.load(client_fd)
    client_json["cmd"] = gen_redis_bench(get_bench())
    tmp_file.write(json.dumps(client_json))
    tmp_file.flush()
    subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
    finished = ""
    raw_log = None
    while "MSET (10 keys)" not in finished:
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

def gen_vegeta(host):
    return ("echo 'GET http://{}/' | vegeta attack -duration=5s >/dev/null && " +
            "echo 'GET http://{}/' | vegeta attack -duration=1m | " +
            "vegeta report -reporter=json && sleep infinity").format(host, host)

def gen_redis_bench(tup):
    host, port = tup
    return ("sleep 10 && redis-benchmark --csv -h {} -p {} && " +
            "sleep infinity").format(host, port)

def deploy_wait():
    comm = "bash -c 'while dcos marathon deployment list > /dev/null 2>&1; do sleep 1; done'"
    subprocess.call(shlex.split(comm))
