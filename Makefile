.PHONY: help test-python build-go build-rust build-cpp build-java bench-smoke

help:
	@echo "make test-python   # 离线单元测试（mock 服务）"
	@echo "make build-go      # go build"
	@echo "make build-rust    # cargo build --release"
	@echo "make build-cpp     # cmake 构建"
	@echo "make build-java    # mvn compile"
	@echo "make bench-smoke   # 对真实 API 跑冒烟基准（需要 .env）"

test-python:
	cd python && uv run python -m unittest discover -s tests -v

build-go:
	cd go && go build ./...

build-rust:
	cd rust && cargo build --release

build-cpp:
	cd cpp && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j4

build-java:
	cd java && mvn -B -DskipTests compile

bench-smoke:
	cd python && uv run benchmark.py --suite smoke --repeat 1 --warmup 0
