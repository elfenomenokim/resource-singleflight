<div align="center">

<img src="https://raw.githubusercontent.com/elfenomenokim/resource-singleflight/main/docs/logo.svg" width="96" height="96" alt="resource-singleflight: 호출자는 여럿, 작업은 하나">

# resource-singleflight

키 하나에 최대 한 개의 작업만 돌리고, 모든 호출자에게 같은 `Future`를 넘기는 파이썬 라이브러리.

[English](README.md) · Python 3.9+

[![license](https://img.shields.io/github/license/elfenomenokim/resource-singleflight)](LICENSE)

[설치](#설치) · [빠른-시작](#빠른-시작) · [왜-필요한가](#왜-필요한가) · [레퍼런스](#레퍼런스)

</div>

같은 키를 요청한 스레드 50개가 작업을 1번만 실행했고 4.6ms가 걸렸습니다. 캐시에 있는 결과를 다시 꺼내는 비용은 3.3µs입니다. 두 값은 `docs/bench/coalesce.json`에 저장되어 있습니다.

새로고침 루프에는 익숙한 문제가 있습니다. 창 열 개가 같은 초에 깨어나 똑같이 비싼 읽기를 각자 시작합니다. 이 코디네이터는 첫 번째만 일하게 하고, 나머지 아홉에게 같은 `Future`를 줘서 기다리게 합니다. 읽기를 교체해야 할 때는 이전 작업이 계속 돌되 결과를 더는 publish하지 못합니다. 그래서 늦게 끝난 답이 새 답을 덮어쓰지 않습니다.

표준 라이브러리만 씁니다. 파일 하나이고, 스스로 띄우는 스레드는 작업용 스레드뿐입니다.

## 설치

```sh
pip install resource-singleflight
```

Python 3.9 이상, 의존성 없음. macOS arm64 · Python 3.12에서 확인했습니다.

## 빠른 시작

```python
from resource_singleflight import ResourceCoordinator

coordinator = ResourceCoordinator(thread_name_prefix="refresh")

def read_expensive() -> str:
    return "value"

first = coordinator.submit("key", read_expensive, cache_ttl=30.0)
second = coordinator.submit("key", read_expensive, cache_ttl=30.0)
print(first is second)      # True: 작업 하나, Future 하나
print(first.result(1))      # 'value'
```

호출자 열 개, 작업 한 번. 작업 함수가 모든 호출자가 요청할 때까지 기다리는 경우입니다. 합치기가 목적인 상황이 바로 이것입니다.

```python
import threading
from resource_singleflight import ResourceCoordinator

coordinator = ResourceCoordinator()
started, release = threading.Event(), threading.Event()
calls = []

def read():
    calls.append(1)
    started.set()
    release.wait(5)
    return "value"

futures = []
target = lambda: futures.append(coordinator.submit("key", read, cache_ttl=30.0))
threads = [threading.Thread(target=target) for _ in range(10)]
for thread in threads:
    thread.start()
started.wait(2)
release.set()
for thread in threads:
    thread.join(5)

print(len(calls))                       # 1
print({f.result(2) for f in futures})   # {'value'}
```

`force` 새로고침은 진행 중인 읽기를 교체합니다. 밀려난 `Future`는 멈춰 있는 대신 교체된 작업의 결과로 풀립니다.

```python
old = coordinator.submit("key", slow_read, cache_ttl=30.0)
new = coordinator.submit("key", fast_read, cache_ttl=30.0, force=True)
print(old.result(1))   # 오래된 값이 아니라 교체된 작업의 결과
```

## 왜 필요한가

요청 합치기는 사전 하나를 잠그는 일처럼 보입니다. 실제로 어려운 것은 가장자리입니다.

- **떨어져 나간 읽기는 publish하면 안 됩니다.** 새로고침이 교체되었으면 그 결과는 더 이상 필요하지 않습니다. 교체할 때 세대(generation)를 올리고, 작업은 자기 세대가 최신일 때만 publish합니다. 늦게 끝난 작업은 아무것도 풀지 못하고 아무것도 캐시하지 않습니다.
- **아무도 멈춰 있으면 안 됩니다.** 기다리는 사람이 있는 `Future`를 취소하면 잘못한 것이 없는 호출자에게 `CancelledError`가 납니다. 대신 이미 나간 `Future`를 교체 작업의 결과로 풀어서, 모든 호출자가 답을 받습니다.
- **진행 중인 작업의 소유권은 남습니다.** 이미 시스템 호출 안에 들어간 파이썬 코드는 멈출 수 없습니다. 코디네이터는 시작한 작업을 끝날 때까지 붙들고, `wait_for_idle()`이 마지막 작업이 끝났는지 알려 줍니다. 종료 절차가 기대 대신 기다릴 수 있습니다.
- **캐시와 publish가 함께 결정됩니다.** 세대 확인과 캐시 쓰기가 같은 잠금 안에서 일어납니다. 교체는 publish 전부 아니면 전부 뒤에만 들어옵니다.

## 레퍼런스

### `ResourceCoordinator(thread_name_prefix="singleflight")`

| 메서드 | 동작 |
| --- | --- |
| `submit(key, function, *, cache_ttl=0.0, force=False)` | `key`의 진행 중인 `Future`에 합류하거나, 캐시 값을 내주거나, 작업 하나를 시작합니다. `force=True`는 현재 세대를 교체합니다. |
| `invalidate(key)` | 캐시 값을 버리고 합류 가능한 flight를 퇴역시킵니다. 돌고 있는 작업의 소유권은 유지합니다. |
| `clear()` | 모든 캐시 값을 버리고 합류 가능한 flight를 모두 취소합니다. 돌고 있는 작업의 소유권은 유지합니다. |
| `wait_for_idle(timeout=None)` | 이 코디네이터가 시작한 모든 작업이 끝날 때까지 기다립니다. 시간 초과면 `False`. |

`key`는 해시 가능한 값이면 무엇이든 됩니다. `function`은 인자를 받지 않고, 필요한 값은 클로저로 잡습니다.

### `env_flag(names, *, default=True)`

환경 변수에서 불리언 스위치를 읽습니다. `names` 중 처음 설정된 것을 봅니다. 설정되지 않았으면 `default`를 씁니다. `0`, `false`, `no`, `off` 밖의 값은 모두 켜짐으로 봅니다. 오타 하나로 조정이 조용히 꺼지지 않게 하려는 것입니다.

## 숫자

2026-11-19, macOS arm64(M5 Pro), Python 3.12.8에서 쟀습니다. 값은 `docs/bench/coalesce.json`에 있습니다.

| 항목 | 결과 |
| --- | --- |
| 스레드 50개가 키 하나를 제출, 작업은 20ms | 작업 1회, 전체 4.6ms |
| 캐시된 결과 제출 | 제출당 3.3µs |

## 한계

- 프로세스 하나입니다. 프로세스 사이 조정은 없습니다. 프로세스 둘은 각자 작업을 돌립니다.
- 겹치는 제출만 합쳐집니다. 작업이 다음 호출자의 제출보다 먼저 끝나면 그 호출자는 직접 시작하거나, `cache_ttl`이 0보다 크면 캐시를 받습니다. 5µs짜리 함수를 스레드 열 개가 제출하면 호출이 여러 번 날 수 있습니다. 결과는 여전히 맞습니다.
- 영속성이 없습니다. 캐시는 메모리 사전이고 키마다 단조 증가 시계 기준 만료 시각을 둡니다.
- 작업을 중간에 멈출 수 없습니다. `force`는 결과를 다른 곳으로 돌릴 뿐 멈추지 않습니다. 종료가 한정되어야 하면 `wait_for_idle()`을 쓰십시오.
- Linux와 Windows에서는 실행해 보지 않았습니다.

## 자주 묻는 질문

**`functools.lru_cache`로는 안 됩니까?** 캐시에는 진행 중 상태가 없습니다. 그래서 차가운 키를 요청한 호출자가 각자 읽기를 시작합니다. 이 타입은 교체까지 책임지는데, 평범한 캐시는 그것을 표현하지 못합니다.

**잠금과 사전 대신 왜 `Future`입니까?** 잠금은 "기다려라"까지만 말합니다. `Future`는 결과, 예외, 취소 상태를 함께 나르고, 호출자가 자기 타임아웃을 고를 수 있습니다.

## 기여

버그 보고와 패치를 환영합니다. 확인할 검사와 동작 변경에 필요한 픽스처는 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다.

## 라이선스

MIT, [LICENSE](LICENSE).
