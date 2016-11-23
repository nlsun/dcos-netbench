#!/usr/bin/env python

# python3

import csv
import json
import os
import sys

MASTER = "Master"
AGENT = "Agent"

def main():
    datadir = sys.argv[1]

    # XXX Should be configurable, as a bandaid have it come through an arg?
    # XXX The proper way would be to have this be in the hook
    maxcpus = {MASTER: 400, AGENT: 200}

    filenames = None
    try:
        (_, _, filenames) = next(os.walk(datadir))
    except StopIteration as e:
        print(e)
        error("'{}' not valid dir".format(datadir))

    suffix = 'ttracker_out'
    testname = os.path.basename(datadir)[:-len(suffix)]

    parse(datadir, filenames, testname, maxcpus)

# XXX Newline delimited for each row
# XXX No trailing newlines
#
# {
#     "hostname": "jenksincicpu-36-master-blahblah",
#     "maxcpu": 400,
#     "role": "master",
#     "testname": "jenkinscicpu-36",
#     "timestamp": 1274879,
#     "procs": [
#         {
#             "cpu": 4.0939,
#             "name": "minuteman"
#         },
#         {
#             "cpu": 5.0939,
#             "name": "navstar"
#         },
#         {
#             "cpu": 6.0939,
#             "name": "spartan"
#         }
#     ]
# }
def parse(datadir, filenames, testname, maxcpus):
    timestamp = "Timestamp"
    dataerror = "error"
    suffix = "_cpu.csv"
    outputfile = "bigquery.json"
    jsonstrs = []

    for fl in filenames:
        if not fl.endswith(suffix):
            continue
        hostjson = {}
        host = fl[:-len(suffix)]
        role = get_role(datadir, host)
        hostjson["hostname"] = host
        hostjson["testname"] = testname
        hostjson["role"] = role
        hostjson["maxcpu"] = maxcpus[role]
        with open(os.path.join(datadir, fl)) as fd:
            reader = csv.DictReader(fd)
            errored = set()
            for row in reader:
                hostprocs = []
                x = int(row[timestamp])
                # If an error was seen in a column, then invalidate
                # the rest of the values from that column
                keys = [k for k in row.keys() if k != timestamp and k not in errored]
                for k in keys:
                    if row[k] == dataerror:
                        errored.add(k)
                        continue
                    y = float(row[k])
                    hostprocs.append({"name": k,
                                      "cpu": y})
                hostjson["procs"] = hostprocs
                hostjson["timestamp"] = int(row[timestamp])
                jsonstrs.append(json.dumps(hostjson))
            if errored:
                print("encountered error with {}".format(errored))

    with open(os.path.join(datadir, outputfile), 'w+') as fd:
        for s in jsonstrs:
            fd.write(s + "\n")

def get_role(datadir, host):
    suffix = "_hook.csv"
    with open(os.path.join(datadir, host+suffix)) as fd:
        reader = csv.reader(fd)
        for row in reader:
            if len(row) != 2:
                continue
            timestamp = row[0]
            value = row[1].split(":")
            if value[0] == "nodetype":
                return value[1]
    return None

if __name__ == "__main__":
    main()
