#!/usr/bin/env python

import sys
import subprocess
import shlex
import json
import tempfile
import time

# XXX make sure dcos cli is connected
# XXX does not do any waiting correctly, just does sleeps
# XXX have the first sleep be longer, so the image can pull

def main():
    os_type = sys.argv[1]
    net_type = sys.argv[2]
    test_type = sys.argv[3]
    assert os_type == "core" or os_type == "centos"
    output = {}
    if net_type == "http":
        if test_type == "bridge":
            output[("http", "bridge")] = run_test(http_bridge, os_type, "httpd-bridge.json", "vegeta-bridge.json")
        if test_type == "host":
            output[("http", "host")] = run_test(http_host, os_type, "httpd-host.json", "vegeta-host.json")
        if test_type == "overlay":
            output[("http", "overlay")] = run_test(http_overlay, os_type, "httpd-overlay.json", "vegeta-overlay.json")
        if test_type == "all":
            output[("http", "bridge")] = run_test(http_bridge, os_type, "httpd-bridge.json", "vegeta-bridge.json")
            print(output[("http", "bridge")])
            output[("http", "host")] = run_test(http_host, os_type, "httpd-host.json", "vegeta-host.json")
            print(output[("http", "host")])
            output[("http", "overlay")] = run_test(http_overlay, os_type, "httpd-overlay.json", "vegeta-overlay.json")
            print(output[("http", "overlay")])
            print("\n")
    if net_type == "redis":
        if test_type == "bridge":
            output[("redis", "bridge")] = run_test(redis_bridge, os_type, "redis-bridge.json", "redis-bench-bridge.json")
        if test_type == "host":
            output[("redis", "host")] = run_test(redis_host, os_type, "redis-host.json", "redis-bench-host.json")
        if test_type == "overlay":
            output[("redis", "overlay")] = run_test(redis_overlay, os_type, "redis-overlay.json", "redis-bench-overlay.json")
        if test_type == "all":
            output[("redis", "bridge")] = run_test(redis_bridge, os_type, "redis-bridge.json", "redis-bench-bridge.json")
            print(output[("redis", "bridge")])
            output[("redis", "host")] = run_test(redis_host, os_type, "redis-host.json", "redis-bench-host.json")
            print(output[("redis", "host")])
            output[("redis", "overlay")] = run_test(redis_overlay, os_type, "redis-overlay.json", "redis-bench-overlay.json")
            print(output[("redis", "overlay")])
    if net_type == "all":
        output[("http", "host")] = run_test(http_host, os_type, "httpd-host.json", "vegeta-host.json")
        print(output[("http", "host")])
        output[("http", "bridge")] = run_test(http_bridge, os_type, "httpd-bridge.json", "vegeta-bridge.json")
        print(output[("http", "bridge")])
        output[("http", "overlay")] = run_test(http_overlay, os_type, "httpd-overlay.json", "vegeta-overlay.json")
        print(output[("http", "overlay")])
        output[("redis", "host")] = run_test(redis_host, os_type, "redis-host.json", "redis-bench-host.json")
        print(output[("redis", "host")])
        output[("redis", "bridge")] = run_test(redis_bridge, os_type, "redis-bridge.json", "redis-bench-bridge.json")
        print(output[("redis", "bridge")])
        output[("redis", "overlay")] = run_test(redis_overlay, os_type, "redis-overlay.json", "redis-bench-overlay.json")
        print(output[("redis", "overlay")])
        print("\n")
    if net_type == "debug":
        raw = open("debug_output.log")
        output[("http", "overlay")] = raw.read()
        raw.close()
    print(output)
    parse_output(output, os_type)

# Prints and logs test output
#
# result_dict is dict { ( test_type, net_type ): str }
def parse_output(result_dict, os_type):
    # print the raw output to a single file
    # then just have a http and redis file
    raw_output_file = "raw_output.log"
    http_output_file = "http_output.csv"
    redis_output_file = "redis_output.csv"
    raw_out_fd = open(raw_output_file, 'w+')
    http_fd = None
    redis_fd = None
    for test_type, _ in result_dict.keys():
        if test_type == "http" and http_fd is None:
            http_fd = open(http_output_file, 'w+')
        if test_type == "redis" and redis_fd is None:
            redis_fd = open(redis_output_file, 'w+')

    # map from net_type to data
    parsed_http = {}
    parsed_redis = {}
    for key in result_dict.keys():
        test_type, net_type = key
        str_blob = result_dict[key]
        raw_out_fd.write("{}-{}\n{}\n".format(test_type, net_type, str_blob))
        if test_type == "http":
            parsed_http[net_type] = extract_vegeta(str_blob)
        if test_type == "redis":
            parsed_redis[net_type] = extract_redis(str_blob)

    # if len of parsed_http is not empty, then output it as a csv to a file
    # as well as print it out (with identifiers, like http and overlay)
    # also print it to the raw log
    os_id = None
    if os_type == "core":
        os_id = "CoreOS"
    if os_type == "centos":
        os_id = "Centos7"
    http_header_line = "HTTP benchmark"
    http_num_line = "95th percentile latency (ns)"
    for net_type in parsed_http.keys():
        http_header_line += ",{} ({})".format(os_id, net_type)
        http_num_line += ",{}".format(parsed_http[net_type])
    redis_header_line = "Redis benchmark"
    redis_num_line = "GET req"
    for net_type in parsed_redis.keys():
        redis_header_line += ",{} ({})".format(os_id, net_type)
        redis_num_line += ",{}".format(parsed_redis[net_type])

    if http_fd is not None:
        http_fd.write("{}\n{}".format(http_header_line, http_num_line))
        http_fd.close()
    if redis_fd is not None:
        redis_fd.write("{}\n{}".format(redis_header_line, redis_num_line))
        redis_fd.close()
    raw_out_fd.close()

def extract_vegeta(str_blob):
    print(json.loads(str_blob))
    return str(json.loads(str_blob)["latencies"]["95th"])

def extract_siege(str_blob):
    for raw_line in str_blob.splitlines():
        line = raw_line.strip().split()
        if len(line) >= 2 and line[0] == "Transaction":
            return line[2]

def extract_redis(str_blob):
    for raw_line in str_blob.splitlines():
        line = raw_line.strip().split(",")
        if len(line) >= 2 and line[0] == "\"GET\"":
            return line[1].strip("\"")

def run_test(test_fun, os_type, server_file, client_file):
    tmp_file = tempfile.NamedTemporaryFile(mode="w+")
    output = test_fun(os_type, server_file, client_file, tmp_file)
    tmp_file.close()
    return output

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

if __name__ == "__main__":
    main()
