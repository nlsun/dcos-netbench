#!/usr/bin/env python

import sys
import subprocess
import shlex
import json
import tempfile
import time
import tests
import datetime

# XXX make sure dcos cli is connected
# XXX does not do any waiting correctly, just does sleeps
# XXX have the first sleep be longer, so the image can pull
# XXX add notion of repetitions, how many times to run each command before
#   averaging and outputting that.

class Tester:
    def __init__(self, os_type, test_type, net_type):
        self.all_test = ["http", "redis"]
        self.all_net = ["bridge", "overlay", "host"]
        self.results = {}
        self.parsed_results = {}
        self.os_type = os_type

        timestamp = int(datetime.datetime.utcnow().timestamp())
        self.default_prefix = "{}_".format(timestamp)
        if os_type == "coreos":
            self.user = "core"
        else:
            self.user = os_type
        if test_type == "all":
            self.test_type = list(self.all_test)
        else:
            self.test_type = [test_type]
        if net_type == "all":
            self.net_type = list(self.all_net)
        else:
            self.net_type = [net_type]

    def get_os_id(self, os_type):
        return {"coreos": "CoreOS",
                "centos": "Centos7"}[os_type]

    def files(self, test_type, net_type):
        if test_type == "http":
            server_name = "httpd"
            client_name = "vegeta"
        if test_type == "redis":
            server_name = "redis"
            client_name = "redis-bench"
        server_file = "{}-{}.json".format(server_name, net_type)
        client_file = "{}-{}.json".format(client_name, net_type)
        return (server_file, client_file)

    def run(self, reps=1, progress=True, prefix=None):
        """
        reps: How many repetitions to run for each test
        """
        if prefix is None:
            prefix = self.default_prefix
        raw_output_file = prefix + "raw.log"
        raw_out_fd = open(raw_output_file, 'w+')

        for tt in self.test_type:
            for nt in self.net_type:
                fun_str = "{}_{}".format(tt, nt)
                fun = getattr(tests, fun_str)
                server_file, client_file = self.files(tt, nt)
                output = []
                for i in range(reps):
                    res = self.run_test(fun, self.user, server_file, client_file)
                    summary = "{}\n{}".format(fun_str, res)
                    if progress:
                        print(summary)
                    raw_out_fd.write("{}\n".format(summary))
                    raw_out_fd.flush()
                    output.append(res)
                self.results[(tt, nt)] = output
        raw_out_fd.close()

    def parse_results(self):
        self.parse(self.results, self.os_type)

    # Prints and logs test output
    #
    # results is dict { ( test_type, net_type ): [str_iter1, str_iter2, ...] }
    def parse(self, results, os_type):
        parsed = {}
        for key in results.keys():
            test_type, net_type = key
            str_blobs = results[key]
            extracted = self.extract_and_average(test_type, str_blobs)
            if test_type not in parsed:
                parsed[test_type] = {}
            parsed[test_type][net_type] = extracted
        self.parsed_results = parsed
        return self.parsed_results

    def extract_and_average(self, test_type, data):
        """
        data: List of values to be averaged

        Returns the same as Extractor.extract()
        """
        ext = Extractor()
        title = None
        length = len(data)
        extract_type = None
        result = {}
        if test_type == "http":
            extract_type = "vegeta"
        if test_type == "redis":
            extract_type = "redis"
        for str_blob in data:
            title, single_results = ext.extract(str_blob, extract_type)
            for data_type in single_results.keys():
                if data_type not in result:
                    result[data_type] = 0
                result[data_type] += float(single_results[data_type])
        for data_type in result.keys():
            result[data_type] = str(result[data_type]/length)
        return (title, result)

    def dump_results(self, prefix=None):
        if prefix is None:
            parsed_prefix = self.default_prefix
        self.dump(self.parsed_results, self.os_type, parsed_prefix)

    # parsed_results is dict {test_type: {net_type: (title, {data_type: value})}}
    def dump(self, parsed_results, os_type, prefix):
        fds = {}
        for test_type in parsed_results.keys():
            if test_type not in fds:
                fname = "{}{}.csv".format(prefix, test_type)
                fds[test_type] = open(fname, "w+")

        os_id = self.get_os_id(os_type)
        # sort by test type, then sort by net_type
        # make a new file per test_type
        for test_type in sorted(parsed_results.keys()):
            nets = parsed_results[test_type]
            header = None
            body = {}
            for net_type in sorted(nets.keys()):
                title, results = nets[net_type]
                if header is None:
                    header = title
                header += ",{} ({})".format(os_id, net_type)
                for data_type in sorted(results.keys()):
                    if data_type not in body:
                        body[data_type] = data_type
                    body[data_type] += ",{}".format(results[data_type])
            bodystr = ""
            for line in sorted(body.keys()):
                bodystr += "{}\n".format(body[line])
            fds[test_type].write("{}\n{}".format(header, bodystr))

        for key in fds.keys():
            fds[key].close()

    def run_test(self, test_fun, os_type, server_file, client_file):
        tmp_file = tempfile.NamedTemporaryFile(mode="w+")
        output = test_fun(os_type, server_file, client_file, tmp_file)
        tmp_file.close()
        return output

class Extractor:
    def __init__(self, input_val=None, input_type=None):
        self.result = None
        self.title = None
        self.extract(input_val, input_type)

    def extract(self, input_val, input_type):
        if input_val is None or input_type is None:
            return None
        fun = {"vegeta": self.extract_vegeta,
               "siege": self.extract_siege,
               "redis": self.extract_redis}[input_type]
        output = fun(input_val)
        self.title, self.result = output
        return output

    # XXX these extractions function sshould be changed to return tuple with
    # first item title and second item a dict with key being the field, and the value
    # There should also be a special field which 
    def extract_vegeta(self, str_blob):
        title = "HTTP benchmark"
        results = {}
        lat95 = str(json.loads(str_blob)["latencies"]["95th"])
        results["95th percentile latency (ns)"] = lat95
        return (title, results)

    def extract_siege(str_blob):
        title = "HTTP benchmark"
        results = {}
        for raw_line in str_blob.splitlines():
            line = raw_line.strip().split()
            if len(line) >= 2 and line[0] == "Transaction":
                results["trans/sec"] = line[2]
        return (title, results)

    def extract_redis(str_blob):
        title = "Redis benchmark"
        results = {}
        for raw_line in str_blob.splitlines():
            line = raw_line.strip().split(",")
            if len(line) >= 2 and line[0] == "\"GET\"":
                results["Get req"] = line[1].strip("\"")
        return (title, results)

def main():
    os_type = sys.argv[1]
    test_type = sys.argv[2]
    net_type = sys.argv[3]
    repetitions = int(sys.argv[4])
    assert os_type == "coreos" or os_type == "centos"
    tester = Tester(os_type, test_type, net_type)
    tester.run(repetitions)
    tester.parse_results()
    tester.dump_results()

class Tests:
    def http_bridge(os_type, server_file, client_file, tmp_file):
        def bridge_vegeta():
            self.deploy_wait()
            time.sleep(5)
            host, port = self.bridge_hostport(os_type, "_web._httpd._tcp.marathon.mesos")
            return host + ":" + port
        return self.http_helper(os_type, server_file, client_file, tmp_file, bridge_vegeta)

    def http_host(os_type, server_file, client_file, tmp_file):
        def host_vegeta():
            self.deploy_wait()
            time.sleep(5)
            host = self.host_host(os_type)
            return host + ":80"
        return self.http_helper(os_type, server_file, client_file, tmp_file, host_vegeta)

    def http_overlay(os_type, server_file, client_file, tmp_file):
        def overlay_vegeta():
            self.deploy_wait()
            time.sleep(30)
            url = "httpd.marathon.containerip.dcos.thisdcos.directory:80"
            return url
        return self.http_helper(os_type, server_file, client_file, tmp_file, overlay_vegeta)

    def http_helper(os_type, server_file, client_file, tmp_file, get_vegeta):
        self.deploy_wait()
        subprocess.call(shlex.split("dcos marathon app add " + server_file))
        client_fd = open(client_file, 'r')
        client_json = json.load(client_fd)
        client_json["cmd"] = self.gen_vegeta(get_vegeta())
        tmp_file.write(json.dumps(client_json))
        tmp_file.flush()
        subprocess.call(shlex.split("dcos marathon app add " + tmp_file.name))
        raw_log = self.vegeta_wait()
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
            self.deploy_wait()
            time.sleep(5)
            return self.bridge_hostport(os_type, "_redis._redis._tcp.marathon.mesos")
        return self.redis_helper(os_type, server_file, client_file, tmp_file, bridge_bench)

    def redis_host(os_type, server_file, client_file, tmp_file):
        def host_bench():
            self.deploy_wait()
            time.sleep(5)
            host = self.host_host(os_type)
            return (host, "6379")
        return self.redis_helper(os_type, server_file, client_file, tmp_file, host_bench)

    def redis_overlay(os_type, server_file, client_file, tmp_file):
        def overlay_bench():
            self.deploy_wait()
            time.sleep(30)
            url = "redis.marathon.containerip.dcos.thisdcos.directory"
            return (url, "6379")
        return self.redis_helper(os_type, server_file, client_file, tmp_file, overlay_bench)

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
        self.deploy_wait()
        subprocess.call(shlex.split("dcos marathon app add " + server_file))
        client_fd = open(client_file, 'r')
        client_json = json.load(client_fd)
        client_json["cmd"] = self.gen_redis_bench(get_bench())
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
