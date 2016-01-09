test:
	./tests/test-rshell.sh

# Creates the source distribution tarball
sdist:
	python3 setup.py sdist

# Registers this package on the pypi test server
register-test:
	python3 setup.py register -r pypitest

# Creates the distribution tarball and uploads to the pypi test server
upload-test:
	python3 setup.py sdist upload -r pypitest

# Creates the distribution tarball and uploads to the pypi live server
upload:
	python3 setup.py sdist upload -r pypi

# Registers this package on the pypi live server
register:
	python3 setup.py register -r pypi
