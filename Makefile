#
# Note: My setup uses the username/password stored in the ~/.pypirc file
#

test:
	./tests/test-rshell.sh

# Creates the source distribution tarball
sdist:
	python3 setup.py sdist

# Creates the distribution tarball and uploads to the pypi test server
upload-test:
	rm -rf dist/*
	python3 setup.py sdist
	twine upload -r testpypi dist/*

# Creates the distribution tarball and uploads to the pypi live server
upload:
	rm -rf dist/*
	python3 setup.py sdist
	twine upload -r pypi dist/*

# Registers this package on the pypi live server
requirements:
	pip install -r requirements.txt
