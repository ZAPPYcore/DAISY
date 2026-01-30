# Standard Library Guide

This document focuses on the core `Result`/`Option` helpers and their usage.

## Option

```daisy
import option

fn main() -> int:
  set value = option.some<int>(3)
  set mapped = option.map<int, int>(value, 30)
  print option.unwrap_or<int>(mapped, 0)

  set nested = option.some<Option<int>>(option.some<int>(5))
  set flat = option.flatten<int>(nested)
  print option.expect<int>(flat, "missing value")
  return 0
```

## Result

```daisy
import result

fn main() -> int:
  set value = result.ok<int, int>(7)
  set mapped = result.map<int, int, int>(value, 70)
  print result.unwrap_or<int, int>(mapped, 0)

  set nested = result.ok<Result<int, int>, int>(result.ok<int, int>(9))
  set flat = result.flatten<int, int>(nested)
  print result.expect<int, int>(flat, "bad result")
  return 0
```

## Strings

```daisy
import stdlib_strings
import stdlib_strings_ext

fn main() -> int:
  set s = stdlib_strings.concat("hi", "!")
  print s
  set t = stdlib_strings_ext.trim("  ok ")
  print t
  set _ = stdlib_strings.str_release(s)
  set _ = stdlib_strings.str_release(t)
  return 0
```

```daisy
import stdlib_strings_ext

fn main() -> int:
  print stdlib_strings_ext.count_char("banana", 97)
  print stdlib_strings_ext.last_index_of_char("banana", 97)
  print stdlib_strings_ext.repeat("ab", 3)
  print stdlib_strings_ext.escape_json("\"x\"")
  print stdlib_strings_ext.from_int(42)
  print stdlib_strings_ext.ends_with("hello", "lo")
  print stdlib_strings_ext.strip_prefix("hello", "he")
  print stdlib_strings_ext.strip_suffix("hello", "lo")
  return 0
```

## Collections

```daisy
import stdlib_collections

fn main() -> int:
  set v = stdlib_collections.new_vec()
  set _ = stdlib_collections.push(v, 1)
  set _ = stdlib_collections.push(v, 2)
  print stdlib_collections.len(v)
  print stdlib_collections.get(v, 1)
  print stdlib_collections.sum(v)
  print stdlib_collections.max_or(v, -1)
  print stdlib_collections.contains(v, 2)
  set _ = stdlib_collections.release(v)
  return 0
```

## Concurrency

```daisy
import stdlib_concurrency

fn worker(ch: channel) -> int:
  set _ = stdlib_concurrency.send_many(ch, 3, 10)
  return 0

fn main() -> int:
  set ch = stdlib_concurrency.new_channel()
  set _ = spawn(worker, ch)
  print stdlib_concurrency.recv_sum(ch, 3)
  set _ = stdlib_concurrency.close(ch)
  return 0
```

## Logging

```daisy
import stdlib_log

fn main() -> int:
  stdlib_log.set_level(1)
  stdlib_log.info_kv("service", "startup")
  stdlib_log.warn_kv("cache", "cold")
  stdlib_log.error_kv("db", "down")
  return 0
```



