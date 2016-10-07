all: env test

clean:
	scripts/clean.sh

env:
	scripts/env.sh

test:
	scripts/test.sh
