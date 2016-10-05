#!/usr/bin/env python

import sys
import subprocess
import shlex
import json
import tempfile
import time
import tests
import datetime

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
            parsed_prefix = self.default_prefix
        self.dump(self.parsed_results, self.os_type, parsed_prefix)

    def dump(self, parsed_results, os_type, prefix):
        """
        parsed_results: dict {test_type: {net_type: (title, {data_type: value})}}
        """
        fds = {}
        for test_type in parsed_results.keys():
            if test_type not in fds:
                fname = "{}{}.csv".format(prefix, test_type)
                fds[test_type] = open(fname, "w+")

        os_id = self.get_os_id(os_type)
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

if __name__ == "__main__":
    main()
