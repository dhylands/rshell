#!/bin/bash

# set -x

LOCAL_DIR="./rshell-test"

RSHELL_DIR=rshell
TESTS_DIR=tests

TMP_REF="/tmp/pyboard_ref"
TMP_OUT="/tmp/pyboard_out"
TMP_IN="/tmp/pyboard_in"
TREE_CMP="$(pwd)/${TESTS_DIR}/tree_cmp.py"
DEST_DIR="/flash/pbtest"


RSHELL="$(pwd)/${RSHELL_DIR}/main.py --quiet --nocolor"
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

make_tree() {
    dirname=$1
    content="Pyboard test"
    rm -r ${dirname} 2> /dev/null
    mkdir ${dirname}
    cd ${dirname}
    echo ${content} > file1
    echo ${content} > file2
    if [ $2 -ne 2 ]; then
        mkdir sub
        cd sub
        echo ${content} > file1
        if [ $2 -eq 1 ]; then
            echo ${content} > file2
        fi
    fi
}
test_dir ${LOCAL_DIR}
echo
ROOT_DIRS=$(${RSHELL} ls /pyboard)
for root_dir in ${ROOT_DIRS}; do
    test_dir /${root_dir}rshell-test
done

# sync tests
echo
rm -r ${TMP_IN} 2> /dev/null
make_tree ${TMP_REF} 1 # Full set of files

THIS_TEST="sync test basic"
echo Testing ${THIS_TEST}
${RSHELL} sync ${TMP_REF} ${DEST_DIR}
${RSHELL} sync ${DEST_DIR} ${TMP_IN}
${TREE_CMP} ${TMP_REF} ${TMP_IN} verbose
if [ $? -eq 0 ]; then
    echo PASS ${THIS_TEST}
else
    echo FAIL ${THIS_TEST}
    exit 1
fi

echo

# Sync without -m but one file missing from source
THIS_TEST="sync test no delete"
echo Testing ${THIS_TEST}
make_tree ${TMP_OUT} 0 # Missing file
${RSHELL} sync ${TMP_OUT} ${DEST_DIR}
${RSHELL} sync ${DEST_DIR} ${TMP_IN}
${TREE_CMP} ${TMP_REF} ${TMP_IN} verbose
if [ $? -eq 0 ]; then
    echo PASS ${THIS_TEST}
else
    echo FAIL ${THIS_TEST}
    exit 1
fi

echo

THIS_TEST="sync test delete file"
echo Testing ${THIS_TEST}
${RSHELL} sync ${TMP_OUT} ${DEST_DIR} -m
${RSHELL} sync ${DEST_DIR} ${TMP_IN} -m
${TREE_CMP} ${TMP_OUT} ${TMP_IN} verbose
if [ $? -eq 0 ]; then
    echo PASS ${THIS_TEST}
else
    echo FAIL ${THIS_TEST}
    exit 1
fi

echo

THIS_TEST="sync test delete directory"
echo Testing ${THIS_TEST}
make_tree ${TMP_OUT} 2 # Missing dir
${RSHELL} sync ${TMP_OUT} ${DEST_DIR} -m
${RSHELL} sync ${DEST_DIR} ${TMP_IN} -m
${TREE_CMP} ${TMP_OUT} ${TMP_IN} verbose
if [ $? -eq 0 ]; then
    echo PASS ${THIS_TEST}
else
    echo FAIL ${THIS_TEST}
    exit 1
fi

# Tidy up
echo Removing test data
${RSHELL} rm -r ${DEST_DIR}
rm -r ${TMP_OUT} 2> /dev/null
rm -r ${TMP_IN} 2> /dev/null
rm -r ${TMP_REF} 2> /dev/null
echo
echo "PASS"
