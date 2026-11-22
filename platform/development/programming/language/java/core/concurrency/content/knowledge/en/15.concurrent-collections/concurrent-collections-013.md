# ConcurrentHashMap: null policy, computeIfAbsent(), and mapping function constraints

## 1. Context: multiple threads accessing one Map

`ConcurrentHashMap<K,V>` is an implementation of `ConcurrentMap` in `java.util.concurrent`, suitable when multiple threads need to read and update key–value mappings concurrently. Unlike a regular `HashMap`, it designs its operations for concurrent use without requiring the application to lock the entire map around each individual call.

However, **thread-safe does not mean every sequence of caller operations is atomic**. Two questions are especially important:

1. **Why does `ConcurrentHashMap` disallow `null` keys and `null` values?**
2. **What does `computeIfAbsent()` guarantee, and why is the mapping function constrained?**

This is general Java concurrency knowledge on **Java 17+**, not tied to any specific framework.

Initial example:

```java
ConcurrentHashMap<String, String> map = new ConcurrentHashMap<>();
String value = map.computeIfAbsent("language", key -> "Java");
```

This is a **snippet**; it requires importing `java.util.concurrent.ConcurrentHashMap`. If the key does not exist yet, the mapping function is used to compute the value. The map records the non-null value under an atomic contract and returns either the existing or newly created value.

What must not be inferred: that any arbitrary code placed inside the `computeIfAbsent` lambda is safe, that all operations on the returned object are thread-safe, or that initializing the value creates a program-wide transaction.

## 2. Null policy: both keys and values are forbidden

`ConcurrentHashMap` **does not allow `null` as a key and does not allow `null` as a value**. APIs that require a valid key/value typically throw `NullPointerException` if passed null in a forbidden position.

Example:

```java
map.put(null, "value"); // NullPointerException.
map.put("key", null);   // NullPointerException.
map.get(null);          // NullPointerException.
```

This is a snippet (assuming `map` is already declared); it cannot be run sequentially in a normal demo without handling exceptions. `putIfAbsent`, `replace`, `merge`, `computeIfAbsent`, and related APIs also have validation rules for keys, values, and functions according to each method's contract.

### Why does this design make sense in concurrency?

With a regular map that can store null values, a call `get(key) == null` has two interpretations:

- The key is **absent** from the map.
- The key is present in the map, but its value is `null`.

In a concurrent environment, calling `containsKey(key)` **after** `get(key)` to distinguish the two still does not produce an atomic snapshot: another thread can modify the map between the two calls.

`ConcurrentHashMap` eliminates this ambiguity by **never storing a key → null mapping**. Therefore, when `get(key)` returns null for a valid key, at the time of the read there is no valid value mapping for that key. However, **another thread can still add a mapping immediately afterward**: null does not guarantee that the absent state will persist forever.

The null policy is also useful in bulk operations, where a null value commonly represents "no result" for a transform/filter operation under the API contract.

### Complete Java 17+ example: null key/value and null result

Create the file `ConcurrentHashMapNullDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentHashMapNullDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();

        try {
            map.put(null, "x");
        } catch (NullPointerException expected) {
            System.out.println("Null key rejected");
        }

        try {
            map.put("x", null);
        } catch (NullPointerException expected) {
            System.out.println("Null value rejected");
        }

        String calculated = map.computeIfAbsent(
                "missing", key -> null);

        System.out.println("Returned null: "
                + (calculated == null));
        System.out.println("Missing key stored: "
                + map.containsKey("missing"));

        ConcurrentHashMap<String, Optional<String>> negativeCache =
                new ConcurrentHashMap<>();
        negativeCache.computeIfAbsent(
                "absent-item", key -> Optional.empty());

        System.out.println("Negative result stored: "
                + negativeCache.containsKey("absent-item"));
    }
}
```

Compile/run:

```bash
javac ConcurrentHashMapNullDemo.java
java ConcurrentHashMapNullDemo
```

Deterministic output:

```text
Null key rejected
Null value rejected
Returned null: true
Missing key stored: false
Negative result stored: true
```

**A very important distinction:**

- `map.put("x", null)` **throws NPE**: this is a request to write a null value.
- `computeIfAbsent("missing", key -> null)` **does not throw NPE merely because the lambda returns null**. It returns null and **does not record a mapping**.
- If you want to record the state "looked up but not found", you can store a **non-null value** representing an absent result, such as `Optional.empty()`. This is called *negative caching*; you need to define a refresh or expiration policy to avoid caching negative results for too long.

`Optional` is just one way to represent it, not mandatory. In business APIs with multiple cases such as error/not-found/pending, an explicit immutable result type may be more appropriate.

## 3. Why can't `get` + `put` replace `computeIfAbsent`?

Suppose two threads both want to initialize a value when the key does not exist yet.

The **non-atomic** approach:

```java
// Snippet NOT safe to guarantee single initialization.
String old = map.get("setting");
if (old == null) {
    String created = expensiveCreate();
    map.put("setting", created);
}
```

The snippet above assumes `map` and `expensiveCreate()` are already declared; it is not a standalone program.

A possible interleaving:

```text
Thread A                         Thread B
--------                         --------
get("setting") -> null
                                 get("setting") -> null
expensiveCreate() -> "A"
                                 expensiveCreate() -> "B"
put("setting", "A")
                                 put("setting", "B")
```

Even though `ConcurrentHashMap.get` and `put` are individually synchronized according to the contract, **the combination "check absence → create → write" is split into multiple steps**. Two threads can create duplicate values, execute side effects twice, and even overwrite each other's results.

`putIfAbsent(key, value)` guarantees that the **conditional write operation** is atomic, but if you **compute the value before calling it**, two threads can still perform the expensive computation:

```java
// Snippet: two threads can both compute beforehand, even though only one value is written.
String computed = expensiveCreate();
map.putIfAbsent("setting", computed);
```

`computeIfAbsent(key, mappingFunction)` brings the **computation for the absent case** into `ConcurrentHashMap`'s own coordination protocol.

## 4. Contract of `ConcurrentHashMap.computeIfAbsent`

Primary signature:

```java
V computeIfAbsent(
        K key,
        Function<? super K, ? extends V> mappingFunction)
```

This is an abbreviated signature, not a standalone Java file.

### Case by case

| Key state | `computeIfAbsent` behavior | Result |
| --- | --- | --- |
| Key already mapped to a non-null value | Does not run mapping function | Returns existing value |
| Key absent, function returns non-null value | Mapping key → value is established atomically | Returns the established value |
| Key absent, function returns `null` | No mapping is established | Returns `null` |
| Key absent, function throws unchecked exception or `Error` | No mapping is established from that attempt; exception propagates | Caller sees the error |
| Key is `null` | Invalid | `NullPointerException` |
| Mapping function is `null` | Invalid | `NullPointerException` |
| Function attempts to recursively update the map | Contract violation | May be detected and throw `IllegalStateException`; do not rely on detection in all cases |

**Key guarantee in JDK 17:** a `ConcurrentHashMap.computeIfAbsent` invocation is performed **atomically** with respect to the corresponding mapping. By contract, the mapping function is invoked **at most once per invocation** when the key is absent; if the key is already present, it is not invoked.

Do not interpret this as "this function runs only once across the **entire application lifecycle**". If the first attempt returns null, throws an error, or the mapping is later removed, future calls may need to recompute. For each key, only one mapping can be established at a time under the map's protocol; it is not an *exactly-once* guarantee for a side effect outside the map across the whole system.

**Note on concrete classes:** `Map.computeIfAbsent` is a **default method** with guarantees that vary by implementation. Do not generalize the atomicity of `ConcurrentHashMap.computeIfAbsent` to `HashMap` or every other `Map` implementation. When writing code that accepts `Map<K,V>` from outside, you must clearly establish the actual map type / concurrent contract.

## 5. Java 17+: multiple threads initializing the same key

We use a `CountDownLatch` to signal eight threads to start simultaneously, and an `AtomicInteger` to count how many times the mapping function is actually invoked. Each thread retrieves the value for the same key.

Create the file `AtomicMapInitialization.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicMapInitialization {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger creations = new AtomicInteger();
        AtomicInteger received = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[8];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                    String value = map.computeIfAbsent("topic", key -> {
                        creations.incrementAndGet();
                        return "Java";
                    });
                    if ("Java".equals(value)) {
                        received.incrementAndGet();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            workers[i].start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Received: " + received.get());
        System.out.println("Mapping calls: " + creations.get());
        System.out.println("Entries: " + map.size());
        System.out.println("Stored: " + map.get("topic"));
    }
}
```

Run:

```bash
javac AtomicMapInitialization.java
java AtomicMapInitialization
```

Output when there is no external interrupt:

```text
Received: 8
Mapping calls: 1
Entries: 1
Stored: Java
```

**Why does the result not depend on scheduling?**

1. No code removes or replaces the mapping for key `topic`.
2. The function always returns a non-null string, so the mapping is established successfully.
3. When multiple threads contend for the same key, `ConcurrentHashMap` coordinates `computeIfAbsent` so the mapping function is not executed concurrently multiple times for **the mapping being created**. Once the mapping exists, subsequent calls simply return the value.
4. All eight threads receive the value `Java`. `AtomicInteger` ensures that counting invocations and receipts suffers no lost updates.
5. `join()` in main waits for all workers to finish before printing.

**Warning about side effects:** the example uses `creations.incrementAndGet()` to **measure function invocations**. Do not assume that putting a database write or email send inside a mapping function makes it system-wide exactly-once; if the mapping is not established successfully or is removed later, other calls may repeat the side effect.

## 6. Critical constraint: the mapping function must be short, simple, and must not modify the map itself

The Javadoc of `ConcurrentHashMap.computeIfAbsent` explicitly states: **the entire method invocation is performed atomically**, and **some attempted update operations on this map by other threads may be blocked while computation is in progress**. Therefore, the mapping function should be **short and simple**.

In particular, **the mapping function must not modify this map during computation**. This is not merely performance-tuning advice; it is an API contract constraint.

### What NOT to do inside the lambda

- Call `map.put(...)`, `remove(...)`, `compute(...)`, or `computeIfAbsent(...)` on **the same map**, even for a different key.
- Recurse requiring creation of **the same key** currently being computed.
- Call an uncontrolled callback that might modify the same map.
- Wait on a task in an executor where that task needs to update or compute on the same map.
- Perform long I/O, HTTP calls, database waits, long sleeps, or lock a resource that does not guarantee progress.
- Allocate very heavy objects or run long business logic directly inside the mapping mechanism.

**Incorrect** example:

```java
// Snippet FORBIDDEN to execute on the same ConcurrentHashMap.
// map is already declared; this snippet is not meant to be run as a demo.
map.computeIfAbsent("a", key -> {
    map.put("b", "side-effect");
    return "value-a";
});
```

The snippet above violates the contract **not to modify the map itself during computation**. Depending on the keys, table state, implementation, and contention path, it may block, fail, or exhibit unintended behavior. **Do not** design based on "I tested it and it seemed to work".

### Same-key recursion

```java
// DANGEROUS snippet: may throw IllegalStateException.
map.computeIfAbsent("a", key ->
        map.computeIfAbsent("a", nested -> "nested"));
```

The Javadoc specifies that `IllegalStateException` may be thrown if a recursive update is detected that prevents the computation from completing. Do not use this exception for normal control flow; fix the design so initialization does not recursively update the same map.

### Why does a slow function affect other threads?

The map must protect the atomicity of installing the mapping. While the function is computing a value, other updates may have to wait in certain regions/contention cases. This does **not** mean the entire map is locked by a single global monitor for all operations: many reads and updates in independent parts can still make progress. However, there is no guarantee that a slow function only slows down a single key.

**Safe rule:** use the lambda as a **fast, local value-creation step with no side effects on the same map**. If heavy data loading is needed, consider storing a **placeholder object representing the work** and running the actual work **outside the mapping function**, or using an executor/cache designed for asynchronous loading.

## 7. When computeIfAbsent returns null or throws an error: it can be recomputed next time

A null result cannot be placed into `ConcurrentHashMap` because null values are forbidden. Similarly, when the mapping function throws an exception, the attempt does not record a mapping for the key.

Create the file `MappingFailureDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class MappingFailureDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger calls = new AtomicInteger();

        try {
            map.computeIfAbsent("item", key -> {
                calls.incrementAndGet();
                throw new IllegalStateException("cannot initialize");
            });
        } catch (IllegalStateException expected) {
            System.out.println("First computation failed");
        }

        System.out.println("Absent after exception: "
                + !map.containsKey("item"));

        String value = map.computeIfAbsent("item", key -> {
            calls.incrementAndGet();
            return "recovered";
        });

        System.out.println("Recovered: " + value);
        System.out.println("Mapping calls: " + calls.get());

        String missing = map.computeIfAbsent("nil", key -> null);
        System.out.println("Null result: " + (missing == null));
        System.out.println("Nil stored: " + map.containsKey("nil"));
    }
}
```

Compile/run:

```bash
javac MappingFailureDemo.java
java MappingFailureDemo
```

Output:

```text
First computation failed
Absent after exception: true
Recovered: recovered
Mapping calls: 2
Null result: true
Nil stored: false
```

The first time, the function throws an error and the key is not recorded. The next time, the key is still absent so the function runs **again**, this time returning a value. The `nil` case returning null also establishes no mapping.

**This is what breaks the misconception that "computeIfAbsent guarantees computing only once forever"**. It only coordinates computing/writing when needed under the map's contract and **per invocation**. If business logic requires initializing strictly once regardless of process restarts or errors, you must have an idempotency protocol or transaction at the appropriate source of truth.

## 8. Common example: frequency map using `LongAdder`

The `ConcurrentHashMap` Javadoc shows a very useful pattern: a map from keys to counters. With multiple threads, create a `LongAdder` for an absent key and increment that counter.

```java
frequencies.computeIfAbsent(key, k -> new LongAdder())
           .increment();
```

This is a snippet; `frequencies`, `key`, and the `LongAdder` import are not declared here. The neat points are:

- `computeIfAbsent` is only responsible for **installing a shared LongAdder** for the key when absent.
- `LongAdder.increment()` performs multi-thread-safe updates on **the LongAdder object itself**.
- Do not put `increment()` inside the mapping function, because that makes **counting each event** depend on whether the key was absent. If the key is already present, the mapping function **does not run** and the event will not be counted.
- Do not use a plain `Integer` with `get()+1`/`put()`; an immutable `Integer` does not make a read–modify–write pair atomic.

### Java 17+: four workers incrementing a counter together

Create the file `ConcurrentFrequencyDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentFrequencyDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> frequencies =
                new ConcurrentHashMap<>();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    frequencies.computeIfAbsent(
                            "java", key -> new LongAdder())
                            .increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Keys: " + frequencies.size());
        System.out.println("Java count: "
                + frequencies.get("java").sum());
    }
}
```

Run:

```bash
javac ConcurrentFrequencyDemo.java
java ConcurrentFrequencyDemo
```

Output:

```text
Keys: 1
Java count: 4000
```

Every worker increments **the same LongAdder** associated with key `java`. Once main has called `join()` on all four workers, the final total is 4,000. While multiple threads are still updating, `LongAdder.sum()` is **not an absolute atomic snapshot**; it is suitable for statistics/counting under high contention, but should not be used as an exact guard condition for business transactions.

### Pitfall when removing/replacing counters

If one thread calls `frequencies.remove("java")` while another thread has already obtained the old `LongAdder` and continues calling `increment()`, the increment may happen on **an object that has already been removed from the map**. The map guarantees individual mapping set/get operations; it does not automatically "keep a live lock" on the returned object for all subsequent usage.

If every increment must be accounted for accurately across counter resets/rotations, you must design a separate reset protocol. Do not concurrently remove/replace a `LongAdder` in the map and assume all threads have switched to the new counter.

## 9. Atomic mapping does not mean the value is thread-safe

`ConcurrentHashMap<K,V>` protects **the key → value mapping structure**, but does not automatically protect **mutable state inside V**.

Dangerous example:

```java
// Snippet: list is a mutable ArrayList without separate synchronization.
ConcurrentHashMap<String, java.util.ArrayList<String>> map =
        new ConcurrentHashMap<>();

java.util.ArrayList<String> list = map.computeIfAbsent(
        "users", key -> new java.util.ArrayList<>());

// Multiple threads calling list.add(...) concurrently is NOT safe.
list.add("user-1");
```

`computeIfAbsent` can create and publish **a shared List object**, but `ArrayList.add` does not become thread-safe just because the `List` sits inside a `ConcurrentHashMap`.

Options depending on requirements:

- Use an **immutable object** as the value when reads are frequent, and replace the entire value via `compute`/`replace`/CAS-map operations.
- Use an **atomic/concurrent structure** as the value, such as `LongAdder`, `ConcurrentLinkedQueue`, or `CopyOnWriteArrayList`, if its behavior truly fits.
- Use a separate lock or encapsulate state in a class with an explicit synchronization policy.
- If atomicity across **multiple keys at once** is needed, `computeIfAbsent`'s per-key mechanism **does not create a multi-key transaction**.

Even with an immutable value, the pattern of reading a reference and then updating the map must still handle the case where the mapping changed between the two steps if that is a business condition.

## 10. Do not put I/O and expensive computation directly into the mapping function

An initially simple-looking pattern:

```java
// Snippet NOT RECOMMENDED if loadFromRemote() may block for a long time.
Result result = map.computeIfAbsent(
        key, k -> loadFromRemote(k));
```

`Result`, `map`, `key`, and `loadFromRemote` are not declared in this snippet. Problems:

1. The mapping function may run for a long time or block on I/O without a timeout.
2. Some updates from other threads on the map may be blocked during the computation phase.
3. If the I/O needs a callback that updates the same map, deadlock or recursive update issues may occur.
4. When the function returns null, negative results are not cached; subsequent calls repeat the load.
5. When the function throws an error, failures are not cached; subsequent requests can cause a **retry storm**.
6. An external side effect is not rolled back if the mapping later fails.

When a value is expensive to initialize, you can use a **placeholder** representing a computation, install the placeholder quickly into the map, and then perform the actual work outside the mapping function. This approach still requires timeout, cancellation, error, and eviction policies.

### Java 17+: memoization with a quickly installed `FutureTask`

Create the file `ConcurrentMemoDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentMemoDemo {
    private final ConcurrentHashMap<String, FutureTask<String>> cache =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public String load(String key)
            throws InterruptedException, ExecutionException {
        FutureTask<String> task = cache.computeIfAbsent(
                key,
                k -> new FutureTask<>(() -> {
                    loads.incrementAndGet();
                    return k.toUpperCase(Locale.ROOT);
                })
        );

        // Runs outside the mapping function: run() executes
        // the callable only once even if multiple threads call it.
        task.run();

        try {
            return task.get();
        } catch (ExecutionException e) {
            cache.remove(key, task); // Remove the exact failed instance.
            throw e;
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentMemoDemo memo = new ConcurrentMemoDemo();
        ExecutorService executor = Executors.newFixedThreadPool(6);
        try {
            List<Callable<String>> calls = new ArrayList<>();
            for (int i = 0; i < 6; i++) {
                calls.add(() -> memo.load("java"));
            }

            List<Future<String>> results = executor.invokeAll(calls);
            boolean allMatch = true;
            for (Future<String> result : results) {
                allMatch &= "JAVA".equals(result.get());
            }

            System.out.println("All equal: " + allMatch);
            System.out.println("Load calls: " + memo.loads.get());
            System.out.println("Cache entries: " + memo.cache.size());
        } finally {
            executor.shutdown();
        }
    }
}
```

Compile/run:

```bash
javac ConcurrentMemoDemo.java
java ConcurrentMemoDemo
```

Output when there is no external interrupt:

```text
All equal: true
Load calls: 1
Cache entries: 1
```

**Explanation:**

1. `computeIfAbsent` **only creates the `FutureTask`**, a small object representing the computation, and quickly installs it into the map.
2. The actual computation `k.toUpperCase(...)` and the `loads` counter live **inside the `FutureTask`'s `Callable`**, executed by `task.run()` **after `computeIfAbsent` has returned**.
3. If multiple callers request the same key, they receive the same `FutureTask`. `FutureTask.run()` is designed so the inner callable runs **once** for a given task instance; other callers can call `get()` to wait for the result.
4. `FutureTask.get()` publishes the result or throws `ExecutionException`. If the task fails, the code uses `cache.remove(key, task)` to remove the mapping **only if it still points to this exact task**, allowing subsequent calls to retry.
5. There is no need to guess the schedule of the six workers: the task result is `JAVA` and the single `FutureTask` for the key keeps the execution count at 1.

**Limitation of the example:** `task.run()` executes **on one of the caller threads**; it can block that caller if the load is heavy. If you want to run it on a separate executor, you must design a **submit-once** mechanism, rather than blindly calling `executor.submit(task)` from every caller after `computeIfAbsent`, as that would cause redundant submissions. You must also account for timeouts, task cancellation, retries after failure, and bounding the number of cached tasks.

In production systems, a cache library with loaders, expiry, size limits, and metrics observability is usually easier to maintain than a hand-rolled memoization algorithm. Do not turn the `FutureTask` example into an unbounded cache without eviction or error policies.

## 11. Comparing `computeIfAbsent()` with other remapping APIs

This article focuses on **the null policy and mapping function**. Other APIs can be compared simply by mapping state:

| API | When the function is applied | When the function returns null |
| --- | --- | --- |
| `computeIfAbsent(k, fn)` | When key is absent; function receives key | Does not add mapping |
| `computeIfPresent(k, fn)` | When key is present; function receives key and old value | Removes mapping |
| `compute(k, fn)` | Whether key is present or absent; old value may be null | Does not add, or removes mapping |
| `merge(k, v, fn)` | If absent, sets v; if present, calls fn(old, v) | Removes mapping |

These methods have atomic contracts per relevant mapping, but do not protect other side effects; callbacks must not modify the map itself during remapping. Choosing between `compute` and `merge` for common updates was already implemented and verified in the previous API article.

## 12. Per-key atomicity, not a whole-map snapshot

`ConcurrentHashMap` supports high concurrency, but does not promise that checks or updates spanning **multiple keys** form a single transaction:

```java
// Snippet, does NOT create a transaction across two keys.
map.computeIfAbsent("left", key -> "L");
map.computeIfAbsent("right", key -> "R");
```

Another thread can observe `left` already set while `right` is not yet set. If the application invariant is "both mappings change together or neither changes", a different design is needed: an immutable aggregate value under **a single key**, an external lock, or an appropriate transaction mechanism at the data layer.

### Map views and iteration

`ConcurrentHashMap`'s `keySet()`, `values()`, and `entrySet()` provide views that can be used during concurrent updates; their iterators are **weakly consistent**: they do not throw `ConcurrentModificationException` merely because of normal concurrent updates, but they **do not** guarantee a static whole-map snapshot.

Requirements like "iterate over all keys at an exact single point in time" should not rely on `ConcurrentHashMap` iterators while writers are updating. If a business-consistent snapshot is required, you must pause writers via an application protocol, use an immutable snapshot, or choose an appropriate design.

`size()` and `mappingCount()` while the map is being concurrently modified serve as **changing/estimated** state measurements, not a synchronization mechanism for determining the exact number of tasks that can be admitted. `mappingCount()` returns `long` to represent mapping counts exceeding the `int` range, and is likewise considered an estimate under concurrent updates.

## 13. Visibility, publication, and safety of the returned object

`ConcurrentHashMap` provides memory-consistency relationships for mapping access operations: a successful update for a key can be observed by a subsequent read that sees that value with the corresponding synchronization guarantees.

However:

- The map protects **how the reference** to a value is published; it does not prevent another thread from **mutating mutable fields of that object** after the reference is published.
- If a value has multiple related fields, invariants within the object must be preserved through immutable design, locks, or dedicated atomic state.
- Using `final` in an immutable value type/record makes the design easier to reason about, but **a record containing a mutable `List` can still be modified externally** without defensive copying.
- One thread may call `get(k)` and receive the old value, while another thread calls `replace(k, newValue)`. The first thread continuing to use the old value does not mean the map holds a global snapshot.
- With `computeIfAbsent`, the value created by the lambda should be **fully initialized before being returned**; do not let the object leak from a constructor or callback while its state is still incomplete.

### Mutable value vs immutable snapshot

Example of mapping an immutable value:

```java
// Java 17+ snippet: record Position(int x, int y) {} is already declared.
ConcurrentHashMap<String, Position> positions =
        new ConcurrentHashMap<>();
positions.compute("current",
        (key, oldValue) -> new Position(10, 20));
```

This is not a standalone file because `Position` is not declared. Once a mapping exists, readers can retrieve a `Position` object containing two fully constructed final primitives; if a writer wants to change both at once, it can replace **a single value reference** via `compute` or `replace`, rather than mutating two separate mutable fields outside a lock.

**Do not infer** that multi-key updates become atomic merely because each value is a record; the map's atomic boundary remains the individual mapping.

## 14. Common mistakes

1. **"ConcurrentHashMap also allows null like HashMap."** False: both null keys and null values are forbidden.
2. **"`computeIfAbsent(k, f)` returning null means the map stored null."** False: no mapping is established.
3. **"`get(k) == null` guarantees the key will not appear a moment later."** False: another thread can update it immediately.
4. **"`get` followed by `put` is one atomic step because the map is concurrent."** False: this is a two-call check–then–act sequence.
5. **"`putIfAbsent` avoids computing two expensive values upfront."** Not necessarily: if both callers compute the value **before** calling `putIfAbsent`, it is still computed twice.
6. **"The mapping function runs strictly once per key over the entire process lifetime."** False if the mapping is removed, the function returns null, or it throws an error.
7. **"The lambda can freely call `put` for another key on the same map."** False: the mapping function must not modify the map being computed.
8. **"Same-key recursion can be used to initialize dependencies."** False: it may throw `IllegalStateException` or prevent the algorithm from making progress.
9. **"Putting HTTP/DB calls inside `computeIfAbsent` is inherently safe and optimal."** False: slow functions can block other updates, cause contention, and complicate retries/timeouts.
10. **"The returned value is automatically thread-safe."** False: `ArrayList`, `HashMap`, and mutable objects still need protection.
11. **"Putting `LongAdder.increment()` inside the lambda counts every call."** False: the lambda does not run when the key is already present.
12. **"`LongAdder.sum()` is always an atomic snapshot during concurrent updates."** False: not necessarily.
13. **"`computeIfAbsent` can transactionally update multiple keys."** False: atomicity applies only at the boundary of the respective update operation.
14. **"Iterating over `ConcurrentHashMap` is always a fixed snapshot."** False: it is weakly consistent and may reflect concurrent updates.
15. **"`ConcurrentHashMap.size()` is an exact, absolute way to gate admitting new tasks."** False: observed size is not an atomic admission check.
16. **"Using `Optional.empty()` means the cache automatically has a TTL."** False: it is just a sentinel value; expiry/eviction must be designed separately.
17. **"A `FutureTask` in the map guarantees every external side effect is exactly once."** False: `FutureTask` coordinates one task instance within the JVM; failures/restarts/retries require a different protocol.

## 15. Pre-implementation checklist

1. **Define what null means.** If negative caching is needed, use a non-null sentinel value; never call `put(k, null)`.
2. **Choose the right atomic boundary.** Single-key value initialization uses `computeIfAbsent`; counter increments use `merge` or `LongAdder`; multi-key invariants require a different design.
3. **Do not split check–then–act.** Do not write `if (get == null) put(...)` and expect only one thread to initialize.
4. **Keep the mapping function short, simple, and pure with respect to the map.** Do not modify the same map, do not recursively update, and avoid long-blocking I/O, locks, or callbacks.
5. **Distinguish returning null from throwing an exception.** Both leave the key absent if no mapping existed beforehand; subsequent calls may recompute.
6. **Check side effects.** Recomputation after failure/removal can repeat external operations; ensure idempotency when business logic requires it.
7. **Is the value itself thread-safe?** Use atomic/concurrent values or immutable snapshots if multiple threads continue to modify or read it.
8. **Do not remove a counter in active use and assume all updates switch to the new counter.** A reset protocol may be needed.
9. **When work is heavy, consider a placeholder.** Quickly install a `FutureTask`/future and compute outside the mapping function; handle exceptions, timeouts, and eviction.
10. **Do not rely on iterator order when a whole-map snapshot is needed.** Use a dedicated snapshot design.
11. **Monitor contention and actual metrics.** Measure mapping latency, failure/retry rates, key count, memory, and cache hit rate.
12. **Verify target JVM/API.** The examples here run on Java 17+; consult the Javadoc for your exact deployment JDK.
13. **Test concurrency under diverse schedules.** Use latches to coordinate tests rather than using `sleep` as proof of no data races.
14. **Clean up properly over the lifecycle.** Pools and caches must have owners; avoid retaining error entries or stale values indefinitely.

## 16. Official documentation

- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [ConcurrentMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)
- [Map.computeIfAbsent — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [LongAdder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)

**In summary:** `ConcurrentHashMap` forbids null keys and values so concurrent access has an unambiguous absence signal. `computeIfAbsent` establishes a mapping **atomically** when a key is absent, but the function may record no mapping if it returns null or throws an error, and it **must not modify the map itself during computation**. Keep mapping functions fast, use value types with explicit thread-safety protocols, avoid pushing long I/O into the computation, and do not treat single-key atomicity as a transaction across multiple keys or multiple side effects.
