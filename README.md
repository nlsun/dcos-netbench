# Network Benchmark

- Make sure the DC/OS CLI is authenticated
- Python 3

Run with:
```shell
# os: coreos, centos
# test_type: all, http, redis
# network_type: all, host, bridge, overlay
# repetitions: Number of times to run the test (results are averaged)

python3 perf.py <os> <test_type> <network_type> <repetitions>
```

outputs `<timestamp>_raw.log` and `<timestamp>_<test_type>.csv`
