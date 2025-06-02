#! /usr/bin/bash

PORT=$1
if test -z "$PORT" ; then
    echo "请输入端口号"
    exit
else
    echo "###### PORT=$PORT ######" >> server.log
fi

chmod +x ./stop.sh
./stop.sh "$PORT"

source /home/ai/miniconda3/bin/activate /home/ai/miniconda3/envs/nlidb
if [ $? -ne 0 ]; then
    echo "无法激活 conda 环境 nlidb"
    exit
fi

export PYTHONPATH=.

nohup /home/ai/miniconda3/envs/nlidb/bin/uvicorn \
    dbsql.server.main:app \
    --host 0.0.0.0 \
    --port $PORT \
    2>&1 >> server.log &
if [ $? -ne 0 ]; then
    echo "无法启动 uvicorn"
    exit 1
fi
echo "服务启动结束"
