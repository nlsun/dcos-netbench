#!/usr/bin/env python

import datetime
import json
import os
import shlex
import subprocess
import tempfile

from dcos_netbench import tests, util

import click


@click.group()
def main():
    pass


@main.command()
@click.argument('master', nargs=1)  # Master public IP address
@click.argument('os_type', nargs=1)
@click.option('--test', '-t', default="all", help="Type of test to run as CSV")
@click.option('--net', '-n', default="all", help="Type to network to test as CSV")
@click.option('--reps', '-r', type=click.INT, default=1,
              help="Number of times to run each test (results are averaged)")
@click.option('--prefix', '-p', help="Set prefix for output files, defaults to timestamp")
@click.option('--ttracker/--no-ttracker', default=False)
def run(master, os_type, test, net, reps, prefix, ttracker):
    valid_os = ["coreos", "centos"]
    if os_type not in valid_os:
        print("'os_type' must be one of {}".format(valid_os))
        exit(1)
    test_type = set(test.split(","))
    net_type = set(net.split(","))

    print('Running benchmarks')
    print([master, os_type, test_type, net_type, reps, prefix, ttracker])
    config = Config(os_type, master, test_type, net_type, prefix, ttracker)
    tester = Tester(config)
    tester.run(reps)
    tester.parse_results()
    tester.dump_results()
    if ttracker:
        util.fetch_ttracker(config)


@main.command()
@click.argument('master', nargs=1)  # Master public IP address
@click.argument('os_type', nargs=1)
@click.option('--swarm/--no-swarm', default=False)
@click.option('--ttracker/--no-ttracker', default=False)
def init(master, os_type, swarm, ttracker):
    print([master, os_type, swarm, ttracker])
    config = Config(os_type, master)
    if swarm:
        print('Initializing Docker Swarm')
        util.init_swarm(config)
    if ttracker:
        print('Initializing ttracker')
        util.init_ttracker(config)


@main.command()
@click.argument('master', nargs=1)  # Master public IP address
@click.argument('os_type', nargs=1)
@click.option('--ttracker/--no-ttracker', default=False)
def clean(master, os_type, ttracker):
    print([master, os_type, ttracker])
    config = Config(os_type, master)
    if ttracker:
        print('Cleaning ttracker')
        util.clean_ttracker(config)


@main.command()
@click.argument('master', nargs=1)  # Master public IP address
@click.argument('os_type', nargs=1)
@click.option('--prefix', '-p', help="Set prefix for output files, defaults to timestamp")
@click.option('--ttracker/--no-ttracker', default=False)
def fetch(master, os_type, prefix, ttracker):
    print([master, os_type, prefix, ttracker])
    config = Config(os_type, master, prefix=prefix)
    if ttracker:
        print('Fetching ttracker output')
        util.fetch_ttracker(config)


class Config:
    """
    This class should be treated as read-only except through public functions
    """

    def __init__(self, os_type, master_address, test_types=None, net_types=None, prefix=None, ttracker=False):
        self.dnet = "my-net"  # Name of Docker overlay network
        self.all_test = set(["http", "redis"])
        self.all_net = set(["bridge", "overlay", "dockeroverlay", "host"])

        self.os = os_type
        self.ms = master_address  # public address
        self.ttracker = ttracker

        self.user = self.get_user(self.os)
        self.ag1, self.ag2 = self.get_agents(master_address, self.user)  # private address
        self.os_id = self.get_os_id(self.os)
        self.tmpfd = tempfile.NamedTemporaryFile(mode="w+")
        self.json_path = self.get_json_path()  # where to find the json files
        if test_types is not None:
            self.ttypes = self.get_test_type(test_types)
        if net_types is not None:
            self.ntypes = self.get_net_type(net_types)
        if prefix is None:
            self.prefix = self.get_prefix()
        else:
            self.prefix = prefix

        self.sfile = None
        self.cfile = None

    def set_app(self, test_type, net_type):
        self.sfile, self.cfile = self.get_files(self.json_path, test_type, net_type)

    # Private Functions

    def get_json_path(self):
        return os.path.join(os.path.dirname(__file__), "json")

    def get_files(self, json_path, test_type, net_type):
        if test_type == "http":
            server_name = "httpd"
            client_name = "vegeta"
        if test_type == "redis":
            server_name = "redis"
            client_name = "redis-bench"
        server_file = "{}-{}.json".format(server_name, net_type)
        client_file = "{}-{}.json".format(client_name, net_type)
        server_path = os.path.join(json_path, server_file)
        client_path = os.path.join(json_path, client_file)
        return (server_path, client_path)

    def get_prefix(self):
        timestamp = int(datetime.datetime.utcnow().timestamp())
        return "{}_".format(timestamp)

    def get_test_type(self, test_type):
        if "all" in test_type:
            return (test_type - set(["all"])) | self.all_test
        return test_type

    def get_net_type(self, net_type):
        if "all" in net_type:
            return (net_type - set(["all"])) | self.all_net
        return net_type

    def get_os_id(self, os_type):
        return {"coreos": "CoreOS",
                "centos": "Centos7"}[os_type]

    def get_user(self, os_type):
        if os_type == "coreos":
            return "core"
        return os_type

    def get_agents(self, master, user):
        comm = "ssh -o 'StrictHostKeyChecking=no' {}@{} 'host slave.mesos'".format(user, master)
        res = subprocess.check_output(shlex.split(comm))
        parsed = [line.split()[3] for line in res.decode().splitlines()]
        assert len(parsed) >= 2
        return parsed[:2]


class Tester:
    def __init__(self, config):
        self.config = config
        self.results = {}
        self.parsed_results = {}

    def run(self, reps=1, progress=True, prefix=None):
        """
        reps: How many repetitions to run for each test
        """
        if prefix is None:
            prefix = self.config.prefix
        raw_output_file = prefix + "raw.log"
        raw_out_fd = open(raw_output_file, 'w+')

        for tt in self.config.ttypes:
            for nt in self.config.ntypes:
                fun_str = "{}_{}".format(tt, nt)
                fun = getattr(tests, fun_str)
                self.config.set_app(tt, nt)
                output = []
                for i in range(reps):
                    res = self.run_test(fun, self.config)
                    summary = "{}\n{}".format(fun_str, res)
                    if progress:
                        print(summary)
                    raw_out_fd.write("{}\n".format(summary))
                    raw_out_fd.flush()
                    output.append(res)
                self.results[(tt, nt)] = output
        raw_out_fd.close()

    def parse_results(self):
        self.parse(self.results, self.config.os)

    def parse(self, results, os_type):
        """
        Returns: dict { ( test_type, net_type ): [str_iter1, str_iter2, ...] }
        """
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
            parsed_prefix = self.config.prefix
        self.dump(self.parsed_results, self.config.os, parsed_prefix)

    def dump(self, parsed_results, os_type, prefix):
        """
        parsed_results: dict {test_type: {net_type: (title, {data_type: value})}}
        """
        fds = {}
        for test_type in parsed_results.keys():
            if test_type not in fds:
                fname = "{}{}.csv".format(prefix, test_type)
                fds[test_type] = open(fname, "w+")

        os_id = self.config.os_id
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

    def run_test(self, test_fun, config):
        util.reset_file(config.tmpfd)
        return test_fun(config)


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

    def extract_vegeta(self, str_blob):
        title = "HTTP benchmark"
        results = {}
        lat95 = str(json.loads(str_blob)["latencies"]["95th"])
        results["95th percentile latency (ns)"] = lat95
        return (title, results)

    def extract_siege(self, str_blob):
        title = "HTTP benchmark"
        results = {}
        for raw_line in str_blob.splitlines():
            line = raw_line.strip().split()
            if len(line) >= 2 and line[0] == "Transaction":
                results["trans/sec"] = line[2]
        return (title, results)

    def extract_redis(self, str_blob):
        title = "Redis benchmark"
        results = {}
        for raw_line in str_blob.splitlines():
            line = raw_line.strip().split(",")
            if len(line) >= 2 and line[0] == "\"GET\"":
                results["GET req"] = line[1].strip("\"")
        return (title, results)


if __name__ == "__main__":
    main()
