#!/bin/bash

# set -x

LOCAL_DIR="./rshell-test"

RSHELL_DIR=rshell
TESTS_DIR=tests

#RSHELL="$(pwd)/${RSHELL_DIR}/main.py --quiet --nocolor"
RSHELL="$(pwd)/r.py --quiet --nocolor"
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
    echo ${content} > ${dirname}/file1
    echo ${content} > ${dirname}/file2
    mkdir ${dirname}/sub
    echo ${content} > ${dirname}/sub/file1
    echo ${content} > ${dirname}/sub/file2
}

report() {
    if [ $1 -eq 0 ]; then
        echo $2 " - PASS"
    else
        echo $2 " - FAIL"
        exit 1
    fi
    echo
}

rsync_test() {
    # rsync tests
    local LOCAL_ROOT="/tmp"
    local REMOTE_ROOT="/sd"
    local TMP_REF="pyboard_ref"
    local TMP_OUT="pyboard_out"
    local TMP_RESULT="pyboard"
    local TREE_CMP="$(pwd)/${TESTS_DIR}/tree_cmp.py"
#    local FLAGS=""
    local FLAGS="--verbose"

    echo
    make_tree ${LOCAL_ROOT}/${TMP_REF} # Unchanging
    make_tree ${LOCAL_ROOT}/${TMP_OUT} # Subject to deletions

    THIS_TEST="rsync test basic"
    echo Testing ${THIS_TEST}
    ${RSHELL} rm -r ${REMOTE_ROOT}/${TMP_RESULT} 2> /dev/null
    ${RSHELL} mkdir ${REMOTE_ROOT}/${TMP_RESULT}
    ${RSHELL} cp -r ${LOCAL_ROOT}/${TMP_OUT}/* ${REMOTE_ROOT}/${TMP_RESULT}

    rm -r ${LOCAL_ROOT}/${TMP_RESULT} 2> /dev/null
    mkdir ${LOCAL_ROOT}/${TMP_RESULT}
    ${RSHELL} cp -r ${REMOTE_ROOT}/${TMP_RESULT}/* ${LOCAL_ROOT}/${TMP_RESULT}
    ${TREE_CMP} ${LOCAL_ROOT}/${TMP_OUT} ${LOCAL_ROOT}/${TMP_RESULT} ${FLAGS}
    report $? "${THIS_TEST}"

    # Sync without -m but one file missing from source
    THIS_TEST="rsync test no delete"
    echo Testing ${THIS_TEST}
    rm ${LOCAL_ROOT}/${TMP_OUT}/sub/file1
    ${RSHELL} rsync ${FLAGS} ${LOCAL_ROOT}/${TMP_OUT} ${REMOTE_ROOT}/${TMP_RESULT}
    ${RSHELL} rsync ${FLAGS} ${REMOTE_ROOT}/${TMP_RESULT} ${LOCAL_ROOT}/${TMP_RESULT}
    ${TREE_CMP} ${LOCAL_ROOT}/${TMP_REF} ${LOCAL_ROOT}/${TMP_RESULT} ${FLAGS}
    report $? "${THIS_TEST}"

    THIS_TEST="rsync test delete file"
    echo Testing ${THIS_TEST}
    ${RSHELL} rsync ${FLAGS} -m ${LOCAL_ROOT}/${TMP_OUT} ${REMOTE_ROOT}/${TMP_RESULT}
    ${RSHELL} rsync ${FLAGS} -m ${REMOTE_ROOT}//${TMP_RESULT} ${LOCAL_ROOT}/${TMP_RESULT}
    ${TREE_CMP} ${LOCAL_ROOT}/${TMP_OUT} ${LOCAL_ROOT}/${TMP_RESULT} ${FLAGS}
    report $? "${THIS_TEST}"

    THIS_TEST="rsync test delete directory"
    echo Testing ${THIS_TEST}
    rm -r ${LOCAL_ROOT}/${TMP_OUT}/sub
    ${RSHELL} rsync ${FLAGS} -m ${LOCAL_ROOT}/${TMP_OUT} ${REMOTE_ROOT}/${TMP_RESULT}
    ${RSHELL} rsync ${FLAGS} -m ${REMOTE_ROOT}/${TMP_RESULT} ${LOCAL_ROOT}/${TMP_RESULT}
    ${TREE_CMP} ${LOCAL_ROOT}/${TMP_OUT} ${LOCAL_ROOT}/${TMP_RESULT} ${FLAGS}
    report $? "${THIS_TEST}"

    echo Removing test data
    ${RSHELL} rm -r ${REMOTE_ROOT}/${TMP_RESULT}
    rm -r ${LOCAL_ROOT}/${TMP_REF} 2> /dev/null
    rm -r ${LOCAL_ROOT}/${TMP_OUT} 2> /dev/null
    rm -r ${LOCAL_ROOT}/${TMP_RESULT} 2> /dev/null
}

test_dir ${LOCAL_DIR}
echo
ROOT_DIRS=$(${RSHELL} ls /pyboard)
for root_dir in ${ROOT_DIRS}; do
    test_dir /${root_dir}rshell-test
done
rsync_test
echo
echo "PASS"
