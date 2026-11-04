#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install verified SenseVoice int8 weights; never upload audio."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
from remote_bridge.config import MODEL_DIR

SIZE = 239233841
SHA256 = 'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51'
TOKEN_BLOB = '2cfc92fc2ff26aaa690b7c01fd96b41109413881'
REPO = 'csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        while data:=source.read(1024*1024):h.update(data)
    return h.hexdigest()

def token_ok(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+bytes([0])+data).hexdigest()==TOKEN_BLOB

def main():
    parser=argparse.ArgumentParser(description='安装约 239 MB 的 SenseVoice 本地模型')
    parser.add_argument('--mirror',action='store_true',help='使用 hf-mirror.com 镜像，仍校验模型内容')
    parser.add_argument('--directory',type=Path,default=MODEL_DIR)
    args=parser.parse_args();dest=args.directory.expanduser();dest.mkdir(parents=True,exist_ok=True)
    existing=dest/'model.int8.onnx'
    if existing.exists() and digest(existing)==SHA256 and (dest/'tokens.txt').exists() and token_ok((dest/'tokens.txt').read_bytes()):
        print('本地模型已存在且校验通过。');return
    host='hf-mirror.com' if args.mirror else 'huggingface.co'
    base='https://'+host+'/'+REPO+'/resolve/main/'
    with tempfile.TemporaryDirectory(prefix='.sensevoice-',dir=dest.parent) as tmp:
        root=Path(tmp);chunk=2*1024*1024;count=(SIZE+chunk-1)//chunk
        def fetch(i):
            start=i*chunk;end=min(SIZE,start+chunk)-1
            for attempt in range(4):
                try:
                    req=urllib.request.Request(base+f'model.int8.onnx?part={i}',headers={'Range':f'bytes={start}-{end}'})
                    with urllib.request.urlopen(req,timeout=90) as response:
                        if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{SIZE}':
                            raise RuntimeError('服务器没有返回所请求的数据分片')
                        data=response.read(end-start+2)
                    if len(data)!=end-start+1:raise RuntimeError('分片长度不正确')
                    (root/str(i)).write_bytes(data);return i
                except Exception:
                    if attempt==3:raise
                    time.sleep(2)
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=[pool.submit(fetch,i) for i in range(count)]
            for done,job in enumerate(as_completed(jobs),1):
                job.result();print(f'模型下载 {done}/{count}',flush=True)
        model=root/'model.int8.onnx'
        with model.open('wb') as out:
            for i in range(count):
                with (root/str(i)).open('rb') as source:shutil.copyfileobj(source,out)
        if digest(model)!=SHA256:raise RuntimeError('模型校验失败，未安装')
        for name in ('tokens.txt','LICENSE'):
            with urllib.request.urlopen(base+name,timeout=45) as response:(root/name).write_bytes(response.read(1024*1024))
        if not token_ok((root/'tokens.txt').read_bytes()):raise RuntimeError('词表校验失败，未安装')
        for name in ('model.int8.onnx','tokens.txt','LICENSE'):os.replace(root/name,dest/name)
    print('安装完成：'+str(dest))

if __name__=='__main__':main()
