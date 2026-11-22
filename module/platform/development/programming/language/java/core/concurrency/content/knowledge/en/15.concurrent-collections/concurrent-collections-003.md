# Atomic Compound Operations of ConcurrentHashMap in Java Concurrency

> **Scope:** General Java SE concurrency under **Concurrent Collections**. This lesson explains why individual `ConcurrentHashMap` operations are thread-safe while a read–decide–write sequence is not automatically atomic; how to use `putIfAbsent`, `remove(key, value)`, `replace`, `computeIfAbsent`, `computeIfPresent`, `compute`, and `merge`; per-key atomicity boundaries; using `LongAdder`; remapping function safety; common pitfalls; and Java 17 testing. Spring-specific topics are covered in another chapter.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish a **thread-safe method** from an **atomic compound operation**: `get` and `put` are each safe when called individually, but `get → compute → put` is not a single atomic operation.
- Identify interleavings that cause **lost updates**, check-then-act races, duplicate initialization, or stale conditional updates, even when using a `ConcurrentHashMap`.
- Choose the right API: `putIfAbsent` for initialize-if-missing; `replace(key, oldValue, newValue)` / `remove(key, value)` for conditional updates; `compute*` / `merge` for transformations based on the current value.
- Understand the difference between **mapping presence/absence** and `null` semantics in `ConcurrentHashMap`, including how returning `null` from a remapping function prevents a mapping from being added or removes an existing one.
- Explain why these compound operations guarantee **atomicity per mapping/key**, yet do not form an atomic transaction across multiple keys, other collections, or side effects outside the JVM.
- Design remapping functions that are **short, simple, free of long I/O, do not recursively update the same map, and do not rely on side effects to count executions**.
- Apply the `computeIfAbsent(key, k -> new LongAdder()).increment()` pattern for concurrent counting, while stating the limitations of `LongAdder.sum()` and the risk of replacing/removing a mapping while other threads still hold the old counter.
- Write deterministic Java 17 tests with controlled ordering to prove lost updates with `get/put` and accurate results with `merge` under multiple threads.
- Interpret `size()`, `mappingCount()`, iterators, bulk operations, and memory effects accurately without treating them as a transactional snapshot.

**Core message:** `ConcurrentHashMap` ensures structural safety of the map and provides **per-key atomic transformations**. It **does not automatically turn any code block with multiple map calls into an atomic transaction**.

## 2. A Thread-Safe Method Is Not a Thread-Safe Workflow

Suppose a map tracks visit counts:

```java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("java", 0);
```

This snippet sits inside a method with `import java.util.concurrent.ConcurrentHashMap`. Both calls execute on the same thread to set up initial data.

Many developers write:

```java
int old = counts.get("java");
counts.put("java", old + 1);
```

This **demonstrates improper synchronization for an increment**. `get()` is thread-safe and `put()` is also thread-safe, but there is a window between them where another thread can run. Both threads can read the same old value and then write the exact same new result.

```text
Initial: count = 0

Thread T1                   Thread T2
-------------------------   -------------------------
get("java") -> 0
                            get("java") -> 0
put("java", 1)
                            put("java", 1)

Final result: 1
Expected increments: 2
```

This is a **lost update** caused by a **non-atomic read–modify–write**, not because `ConcurrentHashMap` is "not thread-safe". Each individual operation still satisfies Java's concurrent collection contract.

A correct fix:

```java
counts.merge("java", 1, Integer::sum);
```

This is a snippet inside a method, assuming `counts` already exists. `merge` computes and updates the existing mapping as **a single per-key atomic compound operation**. If two threads increment the same key concurrently, both updates are applied in a valid atomic order; no lost update occurs from separate `get/put` calls.

### Identify the Invariant Before Choosing a Primitive

- **Only need "register if the key does not exist yet"** → `putIfAbsent`.
- **Update only if the current value still equals the observed value** → `replace(key, expected, update)`.
- **Remove only if the mapping has not changed** → `remove(key, expectedValue)`.
- **Need to compute from the current value** → `compute`, `computeIfPresent`, `merge`.
- **Need to create an object once if the key is absent** → `computeIfAbsent`.
- **Need atomicity across two keys or database + map** → the APIs above are **not enough**; a different synchronization/transaction design is required.

## 3. What Is an Atomic Compound Operation?

A **compound operation** consists of multiple related decisions, such as "read current state, check a condition, compute the next value, update". If implemented as separate calls:

```text
get(key) -> decide -> put(key, next)
```

the state can change between steps. When using the corresponding atomic API, **the decision and the update are coordinated into a single atomic operation on the mapping**.

`ConcurrentHashMap` supports per-key compound updates through `ConcurrentMap` and its concrete overrides. You should not infer from the general `Map` interface or from a map that synchronizes each method individually that **all default implementations of `compute`/`merge`** provide the same level of guarantee; here we are specifically discussing **Java SE 17's `ConcurrentHashMap`**.

Example:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("votes", 0);
map.compute("votes", (key, current) -> current + 1);
```

Snippet inside a method, importing `ConcurrentHashMap`. For the existing key `votes`, `compute` takes the current mapping, computes from that value, and updates it under the operation's atomic guarantee. Multiple threads calling `compute` on the same key will not suffer lost updates like two separate `get`/`put` calls.

### How Far Does Atomicity Reach?

**Included:** a successful `compute/merge/replace/putIfAbsent` call takes effect on **the involved mapping** as an atomic operation per its contract.

**Not automatically included:** a map-wide transaction; atomicity across two different keys; atomicity of inserting an entry into the map and writing to a database; atomicity of fields inside a mutable object stored as a value.

Do not equate "every map operation is concurrency-safe" with "every business invariant using the map is guaranteed".

## 4. Why Use ConcurrentHashMap for Compound Operations?

`HashMap` does not guarantee thread safety when multiple writers modify it concurrently. `ConcurrentHashMap` protects its internal structure and provides conditional atomic updates per mapping. Its iterators are weakly consistent and do not produce a consistent snapshot of the entire map.

Here, the core question is **whether the condition and the update live inside a single atomic operation**. `ConcurrentHashMap` does not create multi-key transactions and does not allow `null` keys or values; the foundational differences from `HashMap` were covered in the chapter introduction.

## 5. Quick Selection Table for Atomic Operations

| API | When does the update happen? | Return value / meaning | Key things to remember |
|---|---|---|---|
| `putIfAbsent(k, v)` | Only when the key has no mapping | Previous value, or `null` if absent | Does not overwrite an existing value |
| `remove(k, expectedValue)` | Only when the current mapping equals `expectedValue` | `boolean` | Compare-and-remove by key/value |
| `replace(k, expectedValue, newValue)` | Only when the current value matches `expectedValue` | `boolean` | Compare-and-replace by equality |
| `replace(k, newValue)` | Only if the key already has a mapping | Previous value or `null` | Does not create a new mapping |
| `computeIfAbsent(k, function)` | Computes and inserts only when absent | Existing/new value, may be `null` if function returns `null` | Atomic lazy initialization |
| `computeIfPresent(k, function)` | Computes only when present | New value or `null` | Function returning `null` → removes mapping |
| `compute(k, function)` | Computes on current, even when absent | New value or `null` | Function receives `null` as current if absent |
| `merge(k, value, function)` | If absent, inserts `value`; if present, combines with current | Resulting value or `null` if mapping is removed | Commonly fits counters/aggregation |
| `replaceAll(function)` | Applies function to mappings | `void` | Does **not** turn the whole map into a transactional snapshot |

This table applies to Java SE 17 `ConcurrentHashMap`. `null` in the remapping APIs is **a specifically defined control signal**; it does not mean CHM stores `null` values in the map.

## 6. putIfAbsent: Initialize If Missing

Usage:

```java
ConcurrentHashMap<String, String> registry = new ConcurrentHashMap<>();
String first = registry.putIfAbsent("job-42", "CREATED");
String again = registry.putIfAbsent("job-42", "DUPLICATE");
System.out.println(first); // null
System.out.println(again); // CREATED
```

Snippet inside a method with `ConcurrentHashMap` imported. The first time, the key does not exist yet, so `CREATED` is associated and `null` is returned. The second time, the key already exists, so the method **does not overwrite** and returns the existing value `CREATED`.

### Why Not Write `containsKey` Followed by `put`?

```java
if (!registry.containsKey("job-42")) {
    registry.put("job-42", "CREATED");
}
```

This is a **non-atomic check-then-act pattern**. Two threads can both observe the key as absent and both write; the later write overwrites the earlier one. If you need "only one writer wins", use `putIfAbsent`.

### Initialization with Side Effects: `putIfAbsent` May Not Be Enough

```java
ExpensiveValue candidate = loadFromNetwork();
ExpensiveValue winner = map.putIfAbsent(key, candidate);
```

Illustrative snippet requiring `ExpensiveValue`, `map`, `key`, and `loadFromNetwork()`. Even though only one insertion wins, **`loadFromNetwork()` already ran before `putIfAbsent`** on every calling thread. Multiple threads can all perform expensive I/O, even though only one object is retained.

`computeIfAbsent` lets you attach the computation to the absent condition atomically per key; however, moving slow I/O into the mapping function can block other updates and does not automatically provide durability or timeouts. Consider a dedicated loading model.

## 7. remove(key, value): Conditional Removal

`remove(key)` deletes the mapping by key. If you previously read a value and **only want to remove it if the mapping has not changed**, use:

```java
boolean removed = registry.remove("job-42", "CREATED");
```

Illustrative snippet where `registry` was defined earlier. It returns `true` only when the current mapping matches the expected value under the map's semantics. If another thread has already transitioned the state to `RUNNING`, a removal expecting `CREATED` returns `false`; you avoid accidentally deleting the new state.

**Mistake to avoid:**

```java
if ("CREATED".equals(registry.get("job-42"))) {
    registry.remove("job-42"); // May remove a new state just written by another thread!
}
```

This is **buggy illustrative code**: another thread can change `CREATED` → `RUNNING` between `get` and `remove`.

Conditional remove is useful for invalidating cached entries, cleaning up a known version, or deleting a marker upon completion—though if the value can revert to an equal previous value, you must also consider **ABA/generation** at the business layer.

## 8. replace(key, old, new): Compare-and-Swap per Mapping

`ConcurrentHashMap.replace(key, expectedValue, newValue)` checks the current value of a key and replaces it only if it matches the expected value.

```java
ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
states.put("order", "NEW");
boolean claimed = states.replace("order", "NEW", "PROCESSING");
boolean stale = states.replace("order", "NEW", "FAILED");
```

Illustrative snippet. `claimed` will be `true`, and `stale` will be `false` assuming no other thread intervened between the two calls.

`replace(key, newValue)` is another overload: it only requires the key to **already exist**, without checking an expected old value; it returns the previous value or `null` if absent.

### Equality Instead of Identity

`replace(key, oldValue, newValue)` and `remove(key, value)` use **value equality (`equals`)** according to map semantics, not reference CAS identity `==` as in `AtomicReference`. If two different object instances are `equals`, conditional `replace` may treat them as matching. This matters when using enums, records, strings, or value objects with field-based equality.

**Watch out:** if the business invariant requires "the exact generation that was read", equality between two value objects at different times may not be enough. You may need an immutable version field in the value, a token/generation ID, or a separate optimistic versioning protocol.

### Does Compare-and-Replace Cover an Entire Workflow?

No. It only protects a single mapping update. If a caller reads multiple keys A and B and then only replaces A, B's value may have changed in the meantime. When a business invariant depends on multiple keys, you must protect or validate the entire dependency set.

## 9. computeIfAbsent: Atomic Lazy Initialization

`computeIfAbsent(key, mappingFunction)` is the standard tool when you want to create a value **if and only if the key is currently absent**.

```java
ConcurrentHashMap<String, List<String>> buckets = new ConcurrentHashMap<>();
List<String> javaBucket = buckets.computeIfAbsent(
        "java", k -> new CopyOnWriteArrayList<>());
```

Snippet inside a method requiring imports `ConcurrentHashMap`, `List`, and `CopyOnWriteArrayList`. When the key `java` is absent, the mapping function creates a new list and the map publishes a reference to it. If the key already has a value, the function does not run.

According to the Java 17 `ConcurrentHashMap` JavaDoc, **the entire method invocation is performed atomically**, and the mapping function is applied **at most once per key / invocation** while computing during that call. Competing updates on the map may have to wait for the computation to finish.

### Four Cases to Distinguish

1. **Key present:** returns the existing value; the mapping function is not invoked.
2. **Key absent, function returns non-null:** inserts the new mapping and returns that value.
3. **Key absent, function returns `null`:** **no mapping is added** and `null` is returned; subsequent calls may retry computing it.
4. **Function throws an unchecked exception/Error:** the exception is propagated to the caller per contract, and no mapping is established by that call; the application must handle the failure.

**Do not store `null` values in `ConcurrentHashMap`.** Putting `null` via `put` is forbidden; `computeIfAbsent` returning `null` means "no mapping created", not storing `null` in the map.

### Should `computeIfAbsent` Be Treated as a Production Cache Loader?

It works well for **lightweight and fast** object initialization, but you should not default to placing network calls or long blocking I/O inside the function:

```java
// Illustrates the risk: slow I/O inside the mapping function.
CacheValue value = cache.computeIfAbsent(key, k -> loadRemote(k));
```

Snippet where `CacheValue`, `cache`, and `loadRemote` are application-defined. Other threads updating affected mappings may be blocked during a long computation. If the remote call times out or throws an error, the key is not cached and many subsequent callers may retry, causing a stampede.

Design alternatives include storing a `CompletableFuture<Value>` as a **placeholder for an in-flight computation**, using a cache with synchronous loading and timeout/eviction policies, or isolating upstream rate limits. Those approaches also need explicit handling for failed futures, retries, and eviction; CHM does not solve the entire caching lifecycle by itself.

## 10. computeIfPresent: Process Only Existing Values

`computeIfPresent(key, remappingFunction)` invokes the function only when a mapping currently exists.

```java
ConcurrentHashMap<String, Integer> attempts = new ConcurrentHashMap<>();
attempts.put("job", 1);
attempts.computeIfPresent("job", (k, current) -> current + 1);
```

Illustrative snippet. After the call, the value for `job` becomes `2`.

If the key is absent, the function does not run and the map creates no new entry. If the function returns `null`, the current mapping is **removed**:

```java
attempts.computeIfPresent("job", (k, current) -> null);
// "job" is absent after the call unless another thread re-adds it.
```

This is valid per the CHM contract: `null` is a way to request removal, not a stored `null` value.

### TTL/Cleanup Scenario

When you want to remove an entry based on a property of the old value without separating check-then-remove:

```java
cache.computeIfPresent(key, (k, entry) ->
        entry.expiredAt(now) ? null : entry);
```

Illustrative snippet requiring `cache`, `key`, `entry` with an `expiredAt` method, and a defined `now`. The decision to remove the current mapping is based on the value snapshot the function receives **inside the compound operation**. However, system time/TTL policy and mutability of `entry` must be well-defined; if a mutable entry is modified outside the map, the function does not automatically lock the object.

## 11. compute: General-Purpose Remapping Including Absent Keys

`compute(key, (k, oldValue) -> newValue)` is invoked whether the key is present or absent. If absent, `oldValue == null`. That is why you must handle `null` when creating an initial value.

```java
ConcurrentHashMap<String, Integer> counters = new ConcurrentHashMap<>();
counters.compute("java", (key, current) ->
        current == null ? 1 : current + 1);
```

Snippet inside a method. Result is `java=1`. Calling it again yields `java=2`; each call decides based on the current mapping at the time of the atomic operation.

**Null return semantics:**

- If an old mapping exists and the function returns `null` → **removes the mapping**.
- If the mapping is absent and the function returns `null` → **does not create a mapping**.
- If the function throws an unchecked exception or `Error`, the error propagates to the caller and the mapping is not updated by that call.

### Do Not Use `compute` for I/O or External Transactions

`compute` can serialize/coordinate updates to the same key in the map, but the function may execute under internal synchronization. You should not run long database transactions, send emails, call external APIs, or wait on another task that needs to update the same map from inside the function.

`compute` does not make effects outside the map atomic with the entry. If the function sends an email and then fails before returning, the map state may remain unchanged while the email was already sent. Design around idempotency, an outbox, or separate transactions if the business logic requires it.

## 12. merge: The Simplest Pattern for Accumulation and Aggregation

`merge(key, value, remappingFunction)` has two branches:

- **Absent:** inserts `value` (must be non-null) directly into the map; **does not invoke `remappingFunction`**.
- **Present:** invokes `remappingFunction.apply(currentValue, value)`; if it returns non-null, stores the result; if it returns `null`, **removes the mapping**.

```java
ConcurrentHashMap<String, Integer> totals = new ConcurrentHashMap<>();
totals.merge("clicks", 1, Integer::sum);
totals.merge("clicks", 1, Integer::sum);
```

Snippet inside a method. Result: `clicks = 2`.

### Why Does `merge` Prevent Lost Updates?

Suppose 4 threads each call `totals.merge("clicks", 1, Integer::sum)` 1,000 times. Updates to the same key execute with atomic compound semantics. Assuming no `int` overflow and all calls complete, the final result is **4,000**.

This differs from the old version:

```java
// Incorrect when multiple threads increment the same key:
totals.put("clicks", totals.get("clicks") + 1);
```

This is **buggy illustrative code**: `get`/`put` can interleave and lose updates.

### Correctness of the Operation

If you use `Integer::sum` with `Integer`, addition can overflow when the sum exceeds the 32-bit range. Atomically applied updates do **not** automatically prevent overflow. If a larger range is needed, use `Long`/`LongAdder` or check bounds per contract.

If `remappingFunction` is non-commutative or non-associative (for example, string concatenation or state-machine transitions), the order of atomic updates across threads can affect which valid outcome is produced. The map guarantees per-key atomicity, **not a business-level ordering** across producers.

### `merge` and `null`

`merge(k, null, f)` is invalid on `ConcurrentHashMap`; `value` must be non-null. However, `f` may return `null` to request removing an existing mapping. When absent, `f` is not called; `value` is inserted directly.

## 13. Standalone Java 17 Example: Comparing Failures and Atomic Operations

This example has five parts, all tested with `javac --release 17`:

1. Force two threads to both read `count=0` before either writes using `get/put`; the lost-update result is **deterministically** `1`, independent of scheduler luck.
2. Run four threads concurrently, each calling `merge` 1,000 times; result is `4000`.
3. Exercise `putIfAbsent`, `replace(key, old, new)`, and `remove(key, value)`.
4. Use `computeIfAbsent` to initialize a shared `LongAdder`, with four threads incrementing 1,000 times each; demonstrate the factory runs once in the given workload.
5. Use `compute`/`computeIfPresent` and a `null`-returning function to remove or avoid adding a mapping.

Create **`ConcurrentMapAtomicDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentMapAtomicDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            ConcurrentHashMap<String, Integer> broken = new ConcurrentHashMap<>();
            broken.put("count", 0);
            CountDownLatch bothRead = new CountDownLatch(2);
            CountDownLatch mayWrite = new CountDownLatch(1);
            List<Future<?>> unsafeTasks = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                unsafeTasks.add(pool.submit(() -> {
                    int old = broken.get("count");
                    bothRead.countDown();
                    mayWrite.await();
                    broken.put("count", old + 1);
                    return null;
                }));
            }
            bothRead.await();
            mayWrite.countDown();
            for (Future<?> future : unsafeTasks) future.get();
            System.out.println("getThenPut=" + broken.get("count"));

            ConcurrentHashMap<String, Integer> totals = new ConcurrentHashMap<>();
            List<Future<?>> safeTasks = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                safeTasks.add(pool.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        totals.merge("count", 1, Integer::sum);
                    }
                    return null;
                }));
            }
            for (Future<?> future : safeTasks) future.get();
            System.out.println("mergeTotal=" + totals.get("count"));

            ConcurrentHashMap<String, String> registry = new ConcurrentHashMap<>();
            System.out.println("firstInsert=" + (registry.putIfAbsent("id", "A") == null));
            System.out.println("secondReturned=" + registry.putIfAbsent("id", "B"));
            System.out.println("compareReplace=" + registry.replace("id", "A", "C"));
            System.out.println("staleReplace=" + registry.replace("id", "A", "D"));
            System.out.println("conditionalRemove=" + registry.remove("id", "C"));

            ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();
            AtomicInteger factoryCalls = new AtomicInteger();
            List<Future<?>> counterTasks = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                counterTasks.add(pool.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        counts.computeIfAbsent("java", k -> {
                            factoryCalls.incrementAndGet();
                            return new LongAdder();
                        }).increment();
                    }
                    return null;
                }));
            }
            for (Future<?> future : counterTasks) future.get();
            System.out.println("factoryCalls=" + factoryCalls.get());
            System.out.println("longAdderSum=" + counts.get("java").sum());

            ConcurrentHashMap<String, Integer> statuses = new ConcurrentHashMap<>();
            statuses.compute("attempts", (k, v) -> v == null ? 1 : v + 1);
            statuses.computeIfPresent("attempts", (k, v) -> v + 1);
            System.out.println("computeAndPresent=" + statuses.get("attempts"));
            statuses.computeIfPresent("attempts", (k, v) -> null);
            System.out.println("removedByNull=" + !statuses.containsKey("attempts"));
            System.out.println("absentOnNull=" +
                    (statuses.computeIfAbsent("missing", k -> null) == null
                            && !statuses.containsKey("missing")));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 ConcurrentMapAtomicDemo.java
java ConcurrentMapAtomicDemo
```

**Verified exact stdout:**

```text
getThenPut=1
mergeTotal=4000
firstInsert=true
secondReturned=A
compareReplace=true
staleReplace=false
conditionalRemove=true
factoryCalls=1
longAdderSum=4000
computeAndPresent=2
removedByNull=true
absentOnNull=true
```

### Analysis of the Controlled-Schedule Lost Update

Two tasks start in a pool of **four workers**. Each task:

1. Reads `broken.get("count")` when the initial value is `0`.
2. Calls `bothRead.countDown()`.
3. Waits on `mayWrite.await()`.
4. After `main` receives both read signals, `main` calls `mayWrite.countDown()`.
5. Both tasks write `old + 1`; since `old` is `0` for both, both write `1`.

Regardless of which task writes first, the final value is always **1**. This is a deterministic test proving that **two thread-safe methods do not compose into an atomic increment**.

### Analysis of 4,000 `merge` Calls

Four tasks, each running a 1,000-iteration loop, call:

```java
totals.merge("count", 1, Integer::sum);
```

That is 4,000 updates in total. Each update executes with atomic semantics on the `count` mapping, so no increments are lost to concurrent interleaving. `Future.get()` in `main` waits for all tasks to complete before reading the result. Since 4,000 is within `int` range, no overflow occurs in this example.

### Analysis of `registry`

- The first `putIfAbsent("id", "A")` returns `null`; the expression prints `firstInsert=true`.
- The next `putIfAbsent("id", "B")` returns the existing value `A` without overwriting; `secondReturned=A`.
- `replace("id", "A", "C")` succeeds and the map holds `C`.
- `replace("id", "A", "D")` fails because expected `A` is stale.
- `remove("id", "C")` removes conditionally and returns `true`.

All `registry` operations in the demo run sequentially on `main` so stdout does not depend on the scheduler. Similar concurrent behavior can be tested with latches if you want to exercise specific contention.

### Analysis of `computeIfAbsent` + `LongAdder`

Four threads call `computeIfAbsent("java", factory).increment()`. Because the key `java` is inserted and **never removed or replaced** during the test, a single `LongAdder` is shared, the factory runs once in the tested scenario, and 4,000 increments accumulate.

**Do not infer from `factoryCalls=1` in the demo that every invocation in an application's lifetime will only call the factory once in total:** if the key is removed, the function returns `null`, or the computation fails, later calls can run the factory again. The guarantee must be read **per key, per operation, and per mapping state**.

### Analysis of `null` Returns

`compute("attempts", ...)` initializes to `1`; `computeIfPresent` increments to `2`. `computeIfPresent` returning `null` **removes the mapping**; `computeIfAbsent("missing", k -> null)` creates no mapping. Both `removedByNull` and `absentOnNull` evaluate to `true`.

## 14. LongAdder and computeIfAbsent: An Efficient Counter Pattern

The `ConcurrentHashMap` JavaDoc shows a frequency-map pattern similar to:

```java
ConcurrentHashMap<String, LongAdder> freq = new ConcurrentHashMap<>();
freq.computeIfAbsent(word, k -> new LongAdder()).increment();
```

Illustrative snippet with `word` defined externally, requiring imports `ConcurrentHashMap` and `java.util.concurrent.atomic.LongAdder`.

### Why Two Layers of Synchronization?

1. **Map:** `computeIfAbsent` ensures creating/retrieving the counter reference for the key is coordinated atomically.
2. **Counter:** `LongAdder.increment()` performs a thread-safe update on the counter object itself per the `LongAdder` API.

`computeIfAbsent` does not guard the entire time a thread is calling `increment()`. Once the function returns, the increment happens **outside** the map's compound operation, but `LongAdder` has its own concurrency semantics.

### Caveat When the Map Entry Is Removed or Replaced

Suppose thread T1 obtains a reference to the old `LongAdder`:

```java
LongAdder oldCounter = freq.computeIfAbsent(word, k -> new LongAdder());
```

Then T2 removes the `word` mapping from the map and creates a new `LongAdder`. T1 still holds `oldCounter` and calls `increment()` on an object **no longer referenced by the map**. There is no data race inside `LongAdder` itself, but **logical counts for the key can be lost** when you read the new current mapping.

Therefore, this pattern works best when the counter's lifecycle is stable and **counters are not removed/replaced while updaters are still using them**. If you need to reset or rotate counters while threads are incrementing, design epoch/generation ownership, snapshot/hand-off, or explicit synchronization.

### Is `LongAdder.sum()` an Atomic Snapshot?

No. `sum()` returns the current total summed across `LongAdder`'s internal cells, and **is not a strictly atomic snapshot** while other threads are concurrently incrementing. It is suitable for high-throughput metrics, not as a transaction/sequence signal requiring an exact linearizable value across concurrent writers.

In the demo, `main` calls `Future.get()` for **all** worker tasks before calling `sum()`, so no concurrent writers remain and `4000` is deterministic.

### When to Use `AtomicLong` Instead of `LongAdder`?

- `AtomicLong` fits counters that need `compareAndSet`, `getAndIncrement`, and an instantaneous read with single-variable atomic semantics.
- `LongAdder` can reduce contention for statistics incremented by many threads concurrently, at the cost that `sum()` is not an atomic snapshot while updates are in flight.
- For small counters or low contention, pick the simplest type and measure rather than assuming `LongAdder` is always faster.

## 15. Do Not Mutate the Map Inside a Remapping Function

The JavaDoc for `ConcurrentHashMap.compute/computeIfAbsent/computeIfPresent/merge` requires computations to be short and simple and states that **they must not attempt to update other mappings of the same map during the computation**. Recursive updates can cause blocking or an `IllegalStateException` when the JVM detects a non-terminating recursive update.

Incorrect example:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.computeIfAbsent("a", k -> {
    map.put("b", 1); // Do not do this inside a mapping function.
    return 2;
});
```

This is **a design to avoid**, with no guarantee that the program will always throw an exception across all interleavings or keys. Because of how the map coordinates updates, modifying another key can inadvertently cause contention or reentrancy issues; do not rely on a single test passing.

More obvious incorrect example:

```java
map.computeIfAbsent("a", k ->
        map.computeIfAbsent("a", x -> 1)); // Recursive update.
```

This is buggy illustrative code. If a recursive update can be detected as non-terminating recursion, `ConcurrentHashMap` may throw `IllegalStateException`; never use that exception as normal control flow.

**Rule of thumb:** the function should be a pure transformation of `key, current`, short-running, non-blocking, free of irreversible side effects, and must not call methods that update the same map. If multiple keys must be updated, extract a different protocol.

## 16. Why Can a Slow Remapping Function Hurt Throughput?

Some CHM compound methods maintain coordination against competing updates while the remapping function is executing.

```java
// Illustrates an anti-pattern: long I/O inside compute.
map.compute(key, (k, old) -> {
    sleepOrCallRemoteService();
    return transform(old);
});
```

Illustrative Java pseudocode; `sleepOrCallRemoteService` and `transform` are application-defined.

A long-running computation can **block other updates**, especially when they contend on the same mapping or affected internal state. Do not claim that "`compute` locks the entire `ConcurrentHashMap` for all keys"—CHM is designed for concurrency across keys; the impact depends on collisions and the implementation.

### What to Do Instead

- Prepare data that can be computed **outside the function** if it does not require the current snapshot.
- If the computation must depend on `current`, keep the work inside `compute` **fast and pure**.
- For long I/O, you typically need a state machine, a `Future` placeholder, a cache-loading framework, or a task queue to decouple long-running transactions from map updates.
- Measure tail latency and contention under realistic traffic, not only average throughput.
- Enforce deadlines/timeouts on external APIs rather than letting a map lock wait indefinitely on the network.

## 17. Can a Mapping Function Be Called More Than Once?

You should not apply a single answer to every map type or every operation.

- For **Java SE 17 `ConcurrentHashMap.computeIfAbsent`**, the function is applied at most once per key for a single invocation per contract. If the key already has a mapping, the function does not run. However, if a previous call returned `null` or failed, a later invocation may call it again.
- For `compute`/`merge` in CHM, an invocation is coordinated atomically for the mapping; do not assume the function acts as an out-of-JVM transaction-manager callback or will be retried according to application business policy.
- For some other `Map` implementations, default methods built on `get`/`put` do not necessarily share the same atomicity; read the API of **the concrete class**.
- For **caller-written retry loops**, the function/task may run multiple times across invocations; do not place non-idempotent side effects inside without control.

A more important question than "how many times is the function called?" is: **does the function have any side effect whose execution during a critical update compromises correctness or throughput?** Even a single invocation can cause trouble if it transfers money, deletes files, or waits on a dependent lock cycle.

## 18. Multi-Key Invariants: What ConcurrentHashMap Does Not Do Automatically

Suppose you want to transfer 10 units from account A to account B, both stored in the same `ConcurrentHashMap`:

```java
balances.compute("A", (k, a) -> a - 10);
balances.compute("B", (k, b) -> b + 10);
```

This **snippet is not transactionally safe**: assuming `balances` has the appropriate entries and non-null balances. Each `compute` on a single key is atomic, **but the pair together is not an atomic operation**. A reader between the two calls can observe the total balance reduced by 10, or a failure between them can leave A debited without B credited.

### Possible Solutions Depending on Requirements

1. **External lock for the entire invariant:** guard both updates and any readers needing a consistent snapshot with the same lock. If multiple locks are used, enforce a consistent lock order to avoid deadlocks.
2. **An immutable aggregate state:** store a single object containing both A and B in an `AtomicReference<ImmutableLedger>`, and CAS-swap the whole object after validation; this ensures updates happen on **a single reference**. Suitable when size and invariants allow.
3. **Storage-layer transactions:** if data needs durability/consistency across JVMs or databases, use an appropriate transaction.
4. **Event sourcing / serial owner:** serialize commands through a single owner that updates the ledger and publishes consistent snapshots; handle failure/recovery explicitly.

There is no magic `ConcurrentHashMap.computeAllKeysAtomically()` in the standard API. Bulk methods do not turn multiple keys into a transaction.

### `replaceAll` Is Not a Global Atomic Snapshot

`replaceAll((k, v) -> ...)` applies a function across mappings, but while other threads are mutating, it does not produce **an atomic all-map transition** like swapping an immutable snapshot. If a business invariant requires all keys to change at the same instant, do not use `replaceAll` as a transaction.

## 19. Iteration, size, mappingCount, and Snapshot Semantics

`ConcurrentHashMap` allows iteration during concurrent updates without throwing `HashMap`-style fail-fast `ConcurrentModificationException`; iterators have **weakly consistent semantics**.

This means:

- An iterator may reflect some concurrent updates depending on observation timing, rather than a transactional snapshot of the entire map.
- `size()` and `mappingCount()` are useful for metrics/monitoring, but if threads are continuously updating, the values can be approximate/transient.
- `mappingCount()` returns a `long`, useful when the mapping count may exceed `size()`'s `int` range.
- A check like `if (map.size() == 0) {...}` does not keep the map "empty" for the next statement; a key may be inserted right after the check.
- Bulk operations `forEach`, `search`, and `reduce` do not acquire a global lock to create a transactionally isolated snapshot.

If you need a stable snapshot, coordinate with **external synchronization / a quiescence protocol**, immutable snapshots, or a versioned-state architecture. `new HashMap<>(concurrentMap)` can create a point-in-time copy in a quiescent phase, but while writers are active, that copy is **not automatically a global point-in-time snapshot**.

## 20. Null, Absent, and Default Values

`ConcurrentHashMap` forbids `null` keys and `null` values:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
// map.put(null, 1);       // NullPointerException
// map.put("a", null);      // NullPointerException
```

Illustrative snippet with two lines intentionally commented out so the program does not crash.

Forbidding `null` gives `get(key) == null` an unambiguous meaning: at the time of the read, no mapping exists, unlike `HashMap` which can store a `null` value.

Still, `get(key) == null` is only a **transient snapshot**, not a reservation on the key. Two threads both reading `null` and then calling `put` can still race. To create if absent, call `putIfAbsent` or `computeIfAbsent`.

### `null` from `compute`/`merge` Is a Control Signal, Not a Data Value

| API | Returning `null` from function | Effect on map |
|---|---|---|
| `computeIfAbsent` | Does not create entry | Key remains absent |
| `computeIfPresent` | Removes existing entry | Key absent after operation, barring later concurrent update |
| `compute` | Removes if present; does not insert if absent | Key absent |
| `merge` | Removes entry when `remappingFunction` for a present key returns `null` | Key absent |

**Do not write code assuming a "`null` value" is stored inside CHM.** If your business domain has both "unknown" and "absent" states, use a dedicated wrapper/enum/record to represent "unknown" as a non-null object.

## 21. ABA and Value Equality with Conditional Replace

A subtle scenario: T1 reads value `A`. T2 changes `A → B → A` (final value **equals** `A`). T1 executes:

```java
boolean updated = map.replace(key, expectedA, next);
```

Illustrative snippet with `map`, `key`, `expectedA`, and `next` defined.

If the current mapping `equals` `expectedA`, `replace` can succeed even though changes occurred in between. This is a form of **ABA at the logical level of optimistic compare/update**. If the business invariant requires "no one modified the mapping since I read it", checking equality of the final value may not be enough.

One way to handle this is attaching a **generation/version** to an immutable value:

```java
record VersionedState(long generation, String status) { }

ConcurrentHashMap<String, VersionedState> states = new ConcurrentHashMap<>();
VersionedState observed = states.get("job");
if (observed != null) {
    VersionedState next = new VersionedState(
            observed.generation() + 1, "RUNNING");
    boolean changed = states.replace("job", observed, next);
}
```

Snippet inside a method using `record` (supported in Java 17). `record` generates equality based on its components, so a different version produces a different expected value. **Condition:** every path that modifies the mapping must follow the generation-increment rule and never reset/reuse generations while stale readers may exist.

Do not add versioning if the invariant truly only cares about current-state equality; it adds complexity without needed correctness.

## 22. Mutable Values: ConcurrentHashMap Does Not Lock Objects Inside

`ConcurrentHashMap<K, V>` is safe for **the `key → reference` structure**. If the value is an `ArrayList`, `HashMap`, mutable POJO, or plain counter, storing its reference in CHM **does not make the value's methods thread-safe**.

```java
ConcurrentHashMap<String, ArrayList<String>> map = new ConcurrentHashMap<>();
map.put("queue", new ArrayList<>());
map.get("queue").add("item"); // Race if multiple threads add to the same ArrayList.
```

This is **unsafe illustrative code**, requiring the corresponding imports. Multiple threads can concurrently mutate the unsynchronized `ArrayList` even though the container is a CHM.

Solutions:

- Use immutable values and swap them with atomic `compute` or `replace`.
- Use an appropriate thread-safe value, such as `LongAdder`, `ConcurrentLinkedQueue`, or a lock-protected object.
- Use ownership transfer so only one thread owns a mutable value at a time.
- Do not hand out a mutable object to callers to mutate freely if state must obey invariants managed by map updates.

### Does `compute` Protect Mutations Inside the Value?

Within a per-key `compute`, the function's logic is coordinated with **atomic mapping updates on the same key**. But if another thread already holds a reference to the mutable value and modifies its fields directly **outside the `compute`/lock protocol**, it can still race. Therefore, either wrap mutable values in a strict protocol or prefer immutable replacement.

## 23. Memory Consistency in ConcurrentHashMap

Java concurrent collections provide memory consistency guarantees: actions in one thread **prior to publishing an object into a concurrent collection** *happen-before* actions in another thread **subsequent to accessing or retrieving that object** from the collection per the relevant contract.

In `ConcurrentHashMap`, a `get(key)` returning a non-null value has the appropriate memory ordering with the corresponding insertion/update of that mapping, enabling safe publication of prepared objects when following the right protocol.

Example:

```java
record Item(int id, String payload) {}
ConcurrentHashMap<String, Item> items = new ConcurrentHashMap<>();
items.put("order-1", new Item(1, "created"));
// Another thread calls get("order-1") and uses the immutable record.
```

Snippet inside a method with `ConcurrentHashMap` imported and a Java 17 `record`. If another thread reads the `Item` properly published via the map, values initialized before publication are observed per the contract.

However:

1. CHM does not give mutable fields of an object *happens-before* guarantees if threads keep mutating them **outside** the map.
2. Reading `get` on two different keys does not create a **consistent snapshot** of a two-key business transaction.
3. Calling `Future.get()` to wait for workers in the demo establishes completion/visibility in `main`; it does **not** fix the `get+put` race that happened earlier among workers.
4. `Thread.sleep()` is not a synchronization mechanism and cannot replace `compute/merge/replace`.
5. An atomic mapping update is a coordination point **on the mapping reference/value**; it does not make database, network, or file-system side effects atomic with the map.

Distinguishing atomicity, visibility, and invariant consistency helps you pick the right tool.

## 24. Rejection and Exceptions from Remapping Functions

Mapping methods can throw exceptions:

- `NullPointerException` when a required non-null key, function, or value is passed as `null`.
- `IllegalStateException` for certain detectable recursive updates per contract.
- A runtime exception or `Error` thrown by the mapping/remapping function. For `compute`/`merge`/`computeIfAbsent`, the mapping is not updated by the failing call per the published semantics.
- Application-specific runtime exceptions intentionally thrown after invariant checks.

Example:

```java
try {
    map.compute("job", (k, old) -> {
        if (old != null && old < 0) {
            throw new IllegalStateException("negative state");
        }
        return old == null ? 1 : old + 1;
    });
} catch (IllegalStateException e) {
    reportFailure(e);
}
```

Illustrative code with `map` of type `ConcurrentHashMap<String, Integer>` and application-defined `reportFailure`. When the function throws, do not assume the update succeeded. However, any side effect the function performed **before throwing** may already have occurred, so avoid irreversible effects inside it.

### Do Not Confuse a Failed Update with a Rejected Executor Task

The exceptions above occur inside the map call. If code calls the map from an `ExecutorService.submit()` task, the exception may be wrapped in a `Future` and observed by the caller via `ExecutionException.getCause()`. That belongs to task error handling and does not change CHM's atomic semantics. Do not confuse a thread pool's `RejectedExecutionException` with a "rejection" from CHM; `ConcurrentHashMap` compound methods do not use an executor's rejection handler.

## 25. Comparison with Collections.synchronizedMap and ConcurrentSkipListMap

### Collections.synchronizedMap

A wrapped map:

```java
Map<String, Integer> synchronizedMap =
        Collections.synchronizedMap(new HashMap<>());
```

Snippet inside a method requiring imports `Map`, `Collections`, and `HashMap`. The wrapper synchronizes individual methods, but **multiple separate calls** still require a caller-side `synchronized` block to form a compound operation.

```java
synchronized (synchronizedMap) {
    int old = synchronizedMap.get("count");
    synchronizedMap.put("count", old + 1);
}
```

This is a correct example of using **the wrapper's own monitor** for both steps. You must ensure **all other accesses related to the same invariant** follow the same locking protocol. Compared to CHM, a single global lock can cause heavier contention across independent keys under concurrent workloads.

### ConcurrentSkipListMap

`ConcurrentSkipListMap` is an ordered concurrent map based on key sort order. It is appropriate when sorted/navigable operations are needed. However, **do not assume every `compute` method on every `ConcurrentMap`** has the exact same implementation atomic semantics as CHM: read the JavaDoc of the concrete class and identify per-key vs. multi-key requirements.

### AtomicReference with an Immutable Whole-State

If a business invariant spans multiple keys and the data set is relatively small or copyable, an `AtomicReference<ImmutableState>` allowing CAS replacement of **the entire state snapshot** may fit better than CHM. Copying cost and contention must be weighed; no single solution is always best.

## 26. Performance and Key Design

Atomic compound operations have coordination costs. There is no universal "benchmark winner".

Factors that matter:

- Whether threads access **the same hot key** or spread across many keys.
- Length of the remapping function.
- `hashCode()` distribution quality and hash collisions.
- Resize frequency, entry count, and memory/GC pressure.
- Object allocation per update, `Integer` boxing, and entry churn.
- CPU-bound vs. I/O-bound workload characteristics.
- Actual contention level and executor concurrency.
- Choosing `LongAdder` vs. immutable value replacement.

### Hot Keys and `LongAdder`

If every thread calls `merge("globalCount", 1, Integer::sum)`, updating **the same mapping** creates contention. For frequency statistics, storing `LongAdder` as the value lets multiple threads increment a counter designed to reduce contention.

Still, `LongAdder.sum()` is not an atomic snapshot while updates are ongoing, and resetting/replacing map entries requires an ownership/epoch protocol. Do not use `LongAdder` for sequence IDs or invariants needing a deterministic CAS value if the API does not fit.

### Keys Must Have Stable `equals`/`hashCode`

If a key is a mutable object and `hashCode()`/`equals()` depend on fields mutated after insertion, lookups may fail to find the entry and logical map behavior breaks, even though the collection is thread-safe. Prefer immutable keys such as `String`, immutable records, or identifiers with stable equality.

### Do Not Benchmark with a Single `System.nanoTime`

When comparing `merge`, `compute`, `AtomicLong`, and `LongAdder`, use realistic workloads and proper benchmarking methodology (such as JMH). A few microseconds of difference in a single run prove nothing. More importantly: only compare options that **all preserve the required invariant**.

## 27. Testing Concurrent Updates Reliably

Concurrency tests should have two layers:

### A. Testing Specific Invariants and Interleavings

1. **`get→put` lost update:** force two threads to both read `0` before writing; the result should demonstrate why the code is broken (as in the demo).
2. **`merge` increments:** four threads × N increments; after all `Future`s complete, the value equals 4N.
3. **`putIfAbsent` contest:** N threads attempt to insert the same key concurrently; verify only one final mapping exists and its value belongs to a valid candidate, without asserting which thread wins.
4. **Conditional `replace` race:** T1 and T2 share the same expected old value; at most one replace to two distinct next values succeeds if nothing reverts the value back to `old` in between.
5. **`computeIfAbsent` single-key initialization:** multiple threads request an absent key concurrently; produce a stable non-null value object and observe factory invocations per contract.
6. **`null` return:** `compute`/`computeIfPresent`/`merge` returning `null` in the right branch removes the mapping; `computeIfAbsent` returning `null` does not insert.
7. **Exception:** mapping function throws; verify no new mapping is created by that call.
8. **Mutable value race:** test the difference between map atomicity and non-thread-safe value operations.
9. **Multi-key transfer:** stress reader/writer threads to show per-key updates do not keep the sum of two accounts invariant at every instant.
10. **Lifecycle:** do not remove/reuse `LongAdder` while threads still hold references if the invariant requires no lost counts.

### B. Stress and Instrumentation

- Use `CountDownLatch`/`CyclicBarrier` for checkpoints instead of guessing with `Thread.sleep()`.
- Use `Future.get(timeout, unit)` so tests have deadlines and surface worker exceptions.
- Verify the exact total after **all** writers finish; reading earlier may observe a valid intermediate value.
- Under high contention, record throughput/latency metrics rather than logging every operation and skewing the workload.
- Test keys with valid hash collisions and key classes with proper `equals`/`hashCode`.
- If you need to assert an algorithm is strictly linearizable, combine event histories or model checking; "a stress test passed once" is not a formal proof.

**Do not try to "fix" a lost update by adding `Thread.sleep` between `get` and `put`.** It only shifts timing or makes the race easier to hit; the fix is the proper compound operation.

## 28. Common Implementation Mistakes

1. **Using `get` then `put` to increment a counter.** Two thread-safe calls do not make an atomic increment; use `merge`/`compute` or an atomic counter.
2. **Using `containsKey` then `put` for lazy initialization.** Check-then-act race; use `putIfAbsent`/`computeIfAbsent`.
3. **Creating an expensive object before `putIfAbsent` and assuming the factory runs once.** Multiple threads can construct duplicate candidates, with only one winner inserted.
4. **Performing long I/O inside `computeIfAbsent`.** The mapping function can block competing updates; consider a dedicated loading protocol.
5. **Mutating the map inside a remapping function.** Recursive or cross-key updates can cause errors or unpredictable blocking.
6. **Assuming `computeIfAbsent` returning `null` stores `null`.** No: no mapping is established.
7. **Assuming `computeIfPresent` calls the function even when absent.** No: only for present mappings.
8. **Assuming `merge` calls the remapping function when absent.** No: when absent, the supplied value is used directly.
9. **Confusing `replace(key, newValue)` with `replace(key, expected, newValue)`.** The first overload does not check the expected value.
10. **Confusing `remove(key)` with `remove(key, expectedValue)`.** Removing by key alone can delete a newer state.
11. **Assuming value equality means the same generation.** `A → B → A` can cause stale compare/updates; use a version if the invariant requires it.
12. **Using `HashMap` across multiple threads without synchronization.** Lacks CHM's thread safety.
13. **Using `Collections.synchronizedMap` without holding the lock across multiple operations.** Compound sequences still race unless the whole sequence is locked.
14. **Using `LongAdder` and removing the key while threads still increment the old counter.** Logical updates can be lost even though `LongAdder` is thread-safe.
15. **Assuming `LongAdder.sum` is an atomic snapshot during concurrent writes.** No; quiescence or another mechanism is needed for an exact point-in-time read.
16. **Assuming `compute` protects mutable fields of the stored object.** Only the mapping is coordinated; direct mutations outside the protocol still race.
17. **Using `replaceAll` as a transaction to change all keys.** There is no global atomic update.
18. **Using `size()`/`isEmpty()` as a guard that stays true.** Concurrency can change it right after the snapshot.
19. **Assuming iterators produce an isolated snapshot.** CHM iterators are weakly consistent.
20. **Using mutable keys whose `hashCode` changes after insertion.** Breaks key lookups.
21. **Putting network/email side effects in a remapping function.** Map operations are not in a transaction with external side effects.
22. **Ignoring exceptions from a mapper.** The mapping is not updated, but external side effects before the exception may already have happened.
23. **Assuming a method labeled atomic makes all business state atomic.** The operation's scope is a single mapping, not the entire workflow.
24. **Checking `size` first and assuming the map stays empty when calling `put`.** Use an atomic admission method instead of check-then-act.
25. **Assuming thread completion order in `merge` has business meaning.** With non-commutative functions, different orders yield different results; design explicit ordering if needed.
26. **Incrementing boxed `Integer` to huge values without considering overflow or allocations.** Counters have their own range and performance constraints.
27. **Using `computeIfAbsent` as a permanent negative/error cache.** If the function throws or returns `null`, no mapping is stored; later callers will retry; add an explicit failure/negative-cache policy if needed.
28. **Using `putIfAbsent` for "execute only once" external effects.** Only mapping insertion is atomic; external effects require idempotency and recovery.
29. **Reading a non-null `get(key)` and assuming it stays unchanged during processing.** The mapping can change; use conditional `replace`/`compute` to validate on commit.
30. **Treating `ConcurrentHashMap` as a distributed lock.** It is an in-process concurrent collection, providing neither cross-process mutual exclusion nor durability.

## 29. Production Code Review Checklist

Before merging code that uses `ConcurrentHashMap`, verify:

- **Invariant:** Is it for an independent key or does it span multiple keys/resources?
- **Read–modify–write:** Are there any `get` followed by `put`/`remove` sequences intended to be atomic?
- **API:** Was the right method chosen among `putIfAbsent` / `replace` / `remove(k, v)` / `compute*` / `merge`?
- **Absent:** Does the function handle a `null` current value properly when the key is absent?
- **Null result:** Could returning `null` unintentionally remove a mapping or fail to create one?
- **Side effects:** Does the mapping/remapping function perform I/O, locking, network calls, writes outside the map, or recursive updates?
- **Duration:** Is the computation in the function short, bounded, and free of severe contention?
- **Equality:** Does the expected value use `equals` appropriately? Is a generation needed to prevent ABA?
- **Value safety:** Are mutable objects in the map protected by a dedicated mechanism?
- **LongAdder lifecycle:** Are counters removed/reset while threads may still hold references?
- **Visibility:** Does state prepared before publication follow proper immutability/ownership protocols?
- **Capacity:** Can the number of keys grow unboundedly and cause memory pressure?
- **Metrics:** Are hot keys, collisions, latency, memory, mapper failures, and throughput monitored?
- **Testing:** Are interleavings tested with latches and results checked after `Future.get`? Are both single-key and multi-key stress tests present?
- **Failure semantics:** If an operation throws after an earlier side effect, how are recovery and idempotency handled?
- **Compatibility:** Are all used APIs available in the target JDK (e.g., Java 17)?

## 30. Self-Check Questions and Answers

**Q1.** `ConcurrentHashMap.get` and `put` are both thread-safe. Why can `put(k, get(k) + 1)` still lose updates?  
**Answer:** Because they are two separate calls. Two threads can both read the same old value and then write the same new value; there is no atomic read–modify–write.

**Q2.** What is the simplest call to increment an `int` counter for a key?  
**Answer:** `map.merge(key, 1, Integer::sum)`, assuming `int` does not overflow and no multi-key transaction is needed.

**Q3.** Two threads both call `putIfAbsent(k, newValue)`. What is guaranteed?  
**Answer:** A mapping is added only on the absent condition; if already present, the later call does not overwrite and returns the current value per contract.

**Q4.** Why can `putIfAbsent(key, loadExpensive())` perform duplicate computation?  
**Answer:** The argument expression `loadExpensive()` runs **before** `putIfAbsent` is invoked on each thread; the method only guards insertion.

**Q5.** If a `computeIfAbsent` function returns `null`, is the key stored with a `null` value?  
**Answer:** No. `ConcurrentHashMap` does not allow `null` values; no mapping is added.

**Q6.** What does it mean when a `computeIfPresent` function returns `null` for an existing key?  
**Answer:** It requests removing that key's mapping as part of the compound update.

**Q7.** Does `merge` call the remapping function when the key is absent?  
**Answer:** No. It inserts the supplied non-null value directly.

**Q8.** Does `replace(k, old, new)` compare `old` by identity or equality?  
**Answer:** By the map's value equality (`equals`), not CAS reference identity.

**Q9.** How does `remove(k, v)` differ from `remove(k)`?  
**Answer:** It removes only if the current mapping matches the expected value, preventing accidental deletion of a state changed by another thread.

**Q10.** Do a `compute` on A and a `compute` on B together form a two-key atomic transaction?  
**Answer:** No. Each compound update is atomic per key, not a combined commit.

**Q11.** Why should a remapping function not recursively update the same map?  
**Answer:** It can violate the contract, causing blocking, non-termination, or `IllegalStateException` when a recursive update is detected.

**Q12.** What problems can arise if a remapping function calls a network API and returns the value?  
**Answer:** It makes competing updates wait a long time, introduces timeouts/partial side effects outside the map's transaction, and complicates retries and consistency.

**Q13.** What are the two sources of thread safety in `computeIfAbsent(k, ignored -> new LongAdder()).increment()`?  
**Answer:** CHM coordinates initialization of the mapping; `LongAdder` protects increments on the counter object.

**Q14.** If another thread removes the key and creates a new `LongAdder`, can a thread holding the old `LongAdder` still increment it?  
**Answer:** Yes. It increments the old object no longer referenced by the map, so logical counts for the key can be lost.

**Q15.** Is `LongAdder.sum()` a perfect atomic snapshot while writers are still incrementing?  
**Answer:** No. It computes a sum that is not an atomic snapshot during concurrent updates.

**Q16.** Does `ConcurrentHashMap.size() == 0` prove the map will remain empty for the next call?  
**Answer:** No. The snapshot/estimate can change immediately; use an atomic operation or another locking protocol.

**Q17.** Do `ConcurrentHashMap` iterators provide a consistent point-in-time snapshot?  
**Answer:** No. They are weakly consistent and may reflect some concurrent changes.

**Q18.** Does `computeIfAbsent` guarantee an external API is called only once forever for a key?  
**Answer:** No. The mapping can be removed, the computation can fail/return `null`, later invocations can retry, and external side effects have no exactly-once guarantee.

**Q19.** Two value objects are equal according to `equals` but belong to different generations. Does `replace(k, old, new)` detect the generation?  
**Answer:** Not if equality excludes the generation. A version field or immutable versioned state is needed if the invariant must distinguish generations.

**Q20.** Why did the demo test use latches for `get/put` but `Future.get` for `merge`?  
**Answer:** Latches force two threads to read the same old value to deterministically prove a lost update; `Future.get` waits for all atomic updates to finish before verifying `4000`.

## 31. Advanced Practice Exercises

### Exercise A — Initializing a Cache Entry

Have 20 threads request the same absent key. Write two versions:

- `putIfAbsent(k, expensiveFactory())` and measure how many times the factory runs.
- `computeIfAbsent(k, k2 -> cheapFactory())` and measure how many times the function runs when the mapping stays stable.

Explain why a factory with external side effects is a different problem from initializing an object in the map. Use `CountDownLatch`/`Future.get(timeout)` to coordinate the test without relying on `sleep`.

### Exercise B — State Transition

Create `record JobState(long generation, String status)`. Multiple threads attempt to transition `NEW → CLAIMED` using `replace(k, expected, next)`. Prove that only one thread can win for the same expected state when nothing transitions the state back to `expected`. Then simulate ABA and add generation handling.

### Exercise C — Word Frequency

Build a frequency map from a set of words where threads split the input and use `computeIfAbsent(word, k -> new LongAdder()).increment()`. Wait for all `Future`s and verify the total word count. Try calling `sum()` while writers are still running and explain why the snapshot is not guaranteed to be linearizable.

### Exercise D — Conditional Cleanup

Use `computeIfPresent` to remove an entry if the record has expired. Test one thread updating a fresh record right as another thread attempts cleanup, ensuring the fresh record is not deleted as a stale `get + remove` check would do.

### Exercise E — Multi-Key Invariant

Simulate transferring points `A → B` while a reader continuously reads the sum `A + B`. Demonstrate that two separate `compute` calls do not provide a two-key atomic snapshot. Redesign using an immutable aggregate state or a shared lock, then test the invariant.

## 32. Official References

- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): specification of atomic `computeIfAbsent`, `computeIfPresent`, `compute`, `merge`, bulk ops, `null` handling, `mappingCount`, weakly consistent views, and `LongAdder` frequency maps.
- [Java SE 17 — ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): semantics of `putIfAbsent`, conditional `remove`/`replace`, and the interface contract.
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): key/value mapping, equality, and default methods.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `increment`/`sum` and snapshot limitations under concurrent updates.
- [Java SE 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic counter and CAS.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination for test interleavings and memory consistency.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`/`shutdown` and lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion, exceptions, and memory effects of `get`.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, data races, and memory ordering.

**Conclusion:** `ConcurrentHashMap` does not make `get → check → put` automatically atomic. Use **the right compound operation for the invariant and per key**: `putIfAbsent` for insert-if-missing, `replace/remove` with an expected value for compare-and-update, `compute*` to remap based on current state, and `merge` to accumulate/aggregate. Remapping functions must be short, free of recursive updates, and free of non-idempotent side effects. If state spans multiple keys, mutable referents, or external systems, design additional synchronization, transactions, or lifecycle management—map thread safety **does not replace** end-to-end workflow correctness.