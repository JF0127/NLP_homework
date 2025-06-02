#! /usr/bin/bash

PORT=$1
if test -z "$PORT" ; then
    echo "请输入端口号"
    exit
fi

PID=$(lsof -i:$PORT | grep uvicorn | awk '{print $2}')
if test -n "$PID"; then
    echo "杀掉已有服务PID=$PID"
    kill -9 $PID
else
    echo "端口未被占用"
fi
