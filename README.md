# Network Benchmark

- Make sure the DC/OS CLI is authenticated
- Python 3

Run with:
```shell
make env
source env/bin/activate
python env/bin/dcos-netbench
```

outputs `<timestamp>_raw.log` and `<timestamp>_<test_type>.csv`
