#!/usr/bin/env python

# python3

import csv
import matplotlib

# This MUST be called before any other matplotlib imports for this to work
# in a headless (server) environment
matplotlib.use('Agg')

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import datetime
import numpy as np
import sys
import os

def error(msg):
    print("error: {}".format(msg))
    sys.exit(1)

def main():
    datadir = sys.argv[1]

    matplotlib.style.use('ggplot')

    filenames = None
    try:
        (_, _, filenames) = next(os.walk(datadir))
    except StopIteration as e:
        print(e)
        error("'{}' not valid dir".format(datadir))

    (lines, hooks) = parse(datadir, filenames)

    mkplot(lines, hooks)
    plt.savefig(os.path.join(datadir, 'plot.pdf'), bbox_inches='tight')
    mkplot(lines, hooks, genhook=False)
    plt.savefig(os.path.join(datadir, 'plot_nohook.pdf'), bbox_inches='tight')
    mkplot(lines, hooks, master=False)
    plt.savefig(os.path.join(datadir, 'agentplot.pdf'), bbox_inches='tight')
    mkplot(lines, hooks, master=False, genhook=False)
    plt.savefig(os.path.join(datadir, 'agentplot_nohook.pdf'), bbox_inches='tight')
    mkplot(lines, hooks, agent=False)
    plt.savefig(os.path.join(datadir, 'masterplot.pdf'), bbox_inches='tight')
    mkplot(lines, hooks, agent=False, genhook=False)
    plt.savefig(os.path.join(datadir, 'masterplot_nohook.pdf'), bbox_inches='tight')

def mkplot(lines, hooks, genhook=True, master=True, agent=True):
    fig = plt.figure(figsize=(40, 10))

    xmin = int(lines[0].x[0])
    xmax = int(lines[0].x[-1])
    for ln in lines:
        smallx = int(ln.x[0])
        bigx = int(ln.x[-1])
        if smallx < xmin:
            xmin = smallx
        if bigx > xmax:
            xmax = bigx

    subplot_names = []
    for ln in lines:
        if ln.proc not in subplot_names:
            subplot_names.append(ln.proc)
    if genhook:
        num_plots = len(subplot_names) + 1  # Extra one for hook plot
    else:
        num_plots = len(subplot_names)
    subplots = {}
    legended = False
    for name in sorted(subplot_names):
        index = len(subplots) + 1
        subplots[name] = plt.subplot(num_plots, 1, index)
        subplots[name].set_xlim([xmin, xmax])
        if not legended:
            mklegend()
            legended = True

    if genhook:
        hookplot = "hooks"
        subplots[hookplot] = plt.subplot(num_plots, 1, len(subplots)+1)
        subplots[hookplot].set_xlim([xmin, xmax])

    for ln in lines:
        if (not master and ln.master()) or (not agent and ln.agent()):
            continue
        if ln.master():
            subplots[ln.proc].plot(ln.x, ln.y, color=ln.color)
        elif ln.agent():
            subplots[ln.proc].plot(ln.x, ln.y, color=ln.color)
        subplots[ln.proc].set_title(ln.proc)
        if genhook:
            for hk in hooks:
                subplots[ln.proc].axvline(x=int(hk.ts))

    if genhook:
        subplots[hookplot].set_title(hookplot)
        height = [0.1, 0.3, 0.5, 0.7, 0.9]
        for i, hk in enumerate(hooks):
            subplots[hookplot].axvline(x=int(hk.ts))
            shortid = "".join([s[0] for s in hk.id.split("_")])
            subplots[hookplot].annotate(shortid, xy=(hk.ts, height[i%len(height)]))

    plt.tight_layout()

def mklegend():
    ms_line = mlines.Line2D([], [], color=Line.MASTERCOLOR, markersize=15, label='master')
    ag_line = mlines.Line2D([], [], color=Line.AGENTCOLOR, markersize=15, label='agent')
    plt.legend(handles=[ms_line, ag_line], loc='upper left',
               bbox_to_anchor=(0, 1.5), fancybox=True, shadow=True, ncol=5)

def parse(datadir, filenames):
    timestamp = "Timestamp"
    linedict = {}  # {"hostname": {"procname": Line}}
    hooks = []  # List of Hooks

    suffix = "_cpu.csv"
    for fl in filenames:
        if not fl.endswith(suffix):
            continue
        host = fl[:-len(suffix)]
        if host not in linedict:
            linedict[host] = {}
        with open(os.path.join(datadir, fl)) as fd:
            reader = csv.DictReader(fd)
            for row in reader:
                x = row[timestamp]
                keys = row.keys()
                for k in keys:
                    if k == timestamp:
                        continue
                    y = row[k]
                    if k not in linedict[host]:
                        line = Line(host=host, proc=k, x=[x], y=[y])
                        linedict[host][k] = line
                    linedict[host][k].x.append(x)
                    linedict[host][k].y.append(y)

    suffix = "_hook.csv"
    for fl in filenames:
        if not fl.endswith(suffix):
            continue
        host = fl[:-len(suffix)]
        with open(os.path.join(datadir, fl)) as fd:
            reader = csv.reader(fd)
            for row in reader:
                if len(row) != 2:
                    continue
                timestamp = row[0]
                value = row[1].split(":")
                if value[0] == "nodetype":
                    role = {'Master': Line.MASTER,
                            'Agent': Line.AGENT}[value[1]]
                    for proc in linedict[host].keys():
                        linedict[host][proc].set_role(role)
                if value[0] == "testnotify":
                    hookid = value[1]
                    hooks.append(Hook(timestamp, hookid))

    lines = []
    for v1 in linedict.values():
        for v2 in v1.values():
            lines.append(v2)
    return (lines, hooks)


class Line():
    MASTER = 0
    AGENT = 1
    MASTERCOLOR = '#009e73'
    AGENTCOLOR = '#56b4e9'

    def __init__(self, host=None, role=None, proc=None, x=None, y=None):
        self.role = None
        self.color = None

        self.host = host  # Hostname
        self.proc = proc  # Process name
        self.x = x  # List of x axis values
        self.y = y  # List of y axis values

        self.set_role(role)

    def set_role(self, input_role):
        if input_role is None:
            return
        assert input_role in [Line.MASTER, Line.AGENT]

        self.role = input_role
        if self.role == Line.MASTER:
            self.color = Line.MASTERCOLOR
        if self.role == Line.AGENT:
            self.color = Line.AGENTCOLOR

    def master(self):
        return self.role == Line.MASTER

    def agent(self):
        return self.role == Line.AGENT

class Point():
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y

class Hook():
    def __init__(self, timestamp=None, ident=None):
        self.ts = timestamp
        self.id = ident

if __name__ == "__main__":
    main()
