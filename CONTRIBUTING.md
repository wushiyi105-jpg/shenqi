# 参与贡献

合同体检：硬规则扫条款、模型读语义、每条引文回原文核验。

## 本地跑起来

```bash
git clone https://github.com/wushiyi105-jpg/shenqi.git
cd shenqi
cp .env.example .env      # Windows: copy .env.example .env

python -m shenqi add samples/云盘服务合同-坑版.txt samples/云盘服务合同-改后版.txt
python -m shenqi review 1 --rules-only      # 不花钱，只跑规则
python -m shenqi review 1                   # 规则 + 模型
python -m shenqi serve    # http://127.0.0.1:8768
```

## 跑测试

```bash
python -m unittest discover tests -v
```

单测不依赖真 key：所有模型调用在测试里都换成了假客户端，没配 .env 也能全绿。Windows 终端如果中文乱码，先把环境变量 PYTHONIOENCODING 设成 utf-8。

## 提 PR

1. fork 本仓库，从 main 开一个分支，名字说清要干什么，比如 fix-csv-encoding。
2. 改代码，能顺手补一个测试就补。
3. 本地把上面的测试命令跑一遍，全绿再往下走。
4. 提 PR，写三件事：改了什么、为什么改、本地测试结果。
5. 动到模型调用那一层的，贴一段真实运行输出，比任何描述都省事。

不用写得很正式，说清楚就行。
