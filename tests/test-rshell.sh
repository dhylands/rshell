#!/bin/bash

# set -x

LOCAL_DIR='./rshell-test'
REMOTE_DIR='/flash/rshell-test'

RSHELL_DIR=rshell
TESTS_DIR=tests

RSHELL="$(pwd)/${RSHELL_DIR}/rshell.py --quiet"
MAKE_ALL_BYTES="$(pwd)/${TESTS_DIR}/make_all_bytes.py"

cmp_results() {
    local file1=$1
    local file2=$2
    local msg="$3"

    if cmp ${file1} ${file2}; then
        echo "${msg} - PASS"
        return
    fi
    echo "${msg} - FAIL"
    exit 1
}

test_results() {
    local output=$1
    local expected=$2
    local msg="$3"

    if [ "${output}" == "${expected}" ]; then
        echo "${msg} - PASS"
        return
    fi
    echo "${msg} - FAIL"
    exit 1
}

test_dir() {
    dirname=$1
    echo "Testing ${dirname}"

    ${RSHELL} rm -rf test-out
    test_results $(${RSHELL} filetype test-out) "missing" "rm test-out"

    ${RSHELL} mkdir test-out
    test_results $(${RSHELL} filetype test-out) "dir" "mkdir test-out"

    pushd test-out > /dev/null

    cat > file-ref.txt << EOF
Line1
Line2
EOF
    ${RSHELL} rm -rf ${dirname}
    ${RSHELL} mkdir ${dirname}

    ${RSHELL} "echo Line1 > ${dirname}/file.txt"
    ${RSHELL} "echo Line2 >> ${dirname}/file.txt"
    ${RSHELL} cp ${dirname}/file.txt file-1.txt
    cmp_results file-1.txt file-ref.txt "echo redirection"

    ${RSHELL} "cat ${dirname}/file.txt > file-2.txt"
    cmp_results file-2.txt file-ref.txt "rshell cat redirection"

    ${RSHELL} cat ${dirname}/file.txt > file-3.txt
    cmp_results file-3.txt file-ref.txt "bash cat redirection"

    ${MAKE_ALL_BYTES}
    ${RSHELL} cp all-bytes.dat ${dirname}/all-bytes.dat
    ${RSHELL} cp ${dirname}/all-bytes.dat all-bytes.tst
    cmp_results all-bytes.dat all-bytes.tst "all-bytes.dat"

    popd > /dev/null

    ${RSHELL} rm -rf test-out
}

test_dir ${LOCAL_DIR}
echo
test_dir ${REMOTE_DIR}

echo "PASS"



