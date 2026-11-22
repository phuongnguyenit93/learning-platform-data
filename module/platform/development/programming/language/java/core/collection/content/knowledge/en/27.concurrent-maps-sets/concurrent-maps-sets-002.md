# ConcurrentHashMap: Concurrent Access and Null-Disallowing Policy

## 1. What Problem Does ConcurrentHashMap Solve?

An application may have multiple threads simultaneously registering sessions, storing state, or updating access counts. If they all share a single map, the container structure must coordinate reads and modifications. Using a shared `HashMap` variable without a synchronization protocol is not enough.

`ConcurrentHashMap<K, V>` is a hash-table-based map designed for **concurrent access**. It provides thread-safe operations and conditional updates suitable for contexts where multiple parties use it at the same time.

There are two guarantees to learn together:

- The map's operations have a synchronization policy and atomicity scope defined by the documentation.
- The map **does not allow null keys or null values**. Therefore, a `null` result from `get` has a clear meaning: that read did not find a mapping for the key.

This helps in algorithm design, but it does not automatically turn every workflow into a transaction. Nor does it make value objects immutable or decide on its own what "no data" means in business logic.

This lesson focuses on reading those guarantees accurately, applying the basic operations, and modeling absent-data states. The examples are compatible with Java 17 and later.

### 1.1. Terms to Distinguish

| Concept | Meaning in This Lesson |
| --- | --- |
| Mapping | The association between one key and one value currently stored by the map |
| Thread safety | An object upholding its contract when used by multiple threads in the documented way |
| Atomicity | An operation having a protected scope that cannot be split into steps where another party interleaves in a way that breaks the operation's condition |
| Happens-before relationship | A memory-model rule that determines ordering and data visibility between threads |
| Absent key | No mapping is observed by that operation |
| Null value | A reference not pointing to an object; not a value allowed to be stored in `ConcurrentHashMap` |
| Business-level not-found value | An application state that must be represented explicitly, such as having looked up a user and finding none |

A map can be safe at the single-mapping level while a workflow spanning multiple mappings is still broken. Likewise, a map can disallow storing null while a valid method on it still returns null to report a result.

## 2. The Concurrency Model of ConcurrentHashMap

### 2.1. Different from Placing One Lock Around Every Operation

`ConcurrentHashMap` supports concurrent reads and high concurrency for updates. Retrieval operations such as `get` do not lock the entire table; they may overlap with updates. The class does not provide a whole-table locking mechanism to block all access. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Therefore, you should not think of it simply as a `HashMap` with `synchronized` around every method. Readers do not need to lock the map themselves just to perform a `get` according to the class contract.

This also does not mean every update always runs completely independently or never has to wait. Operations contending on the same data and computation functions may need to coordinate. Throughput also depends on the number of keys, hash distribution, read/write ratio, and the work done inside each operation.

**Do not call the entire class "completely lock-free."** That is a stronger claim than necessary to use the API and does not accurately describe all update paths.

In Java 17, do not treat a "fixed 16-segment" model as an API contract. The `concurrencyLevel` constructor parameter is a sizing hint, not the maximum number of threads allowed to use the map. Separate public guarantees from implementation details that may change.

### 2.2. Atomicity Scope Is Usually One Operation or One Key

A single safe `put` does not automatically combine two separate calls from user code. The following snippet is **illustrative code with a bug when multiple threads increment concurrently**, assuming `counts` already holds an integer at key `"requests"`:

```java
int previous = counts.get("requests");
counts.put("requests", previous + 1);
```

Two threads may both read 10 and then both write 11. Neither `put` writes a "half-updated value," but one increment is lost because both new values were computed from the same old number.

For a small counter in this lesson, one increment can be expressed as:

```java
counts.merge("requests", 1, Integer::sum);
```

This is an illustrative snippet, assuming `counts` is a `ConcurrentHashMap<String, Integer>`. When the key is absent, 1 is inserted; when it is already present, the merge function computes the new number. Do not use both the broken snippet and the fixed snippet for the same increment.

Similarly, "register if not already present" should use `putIfAbsent` instead of `containsKey` followed by `put`. `ConcurrentMap` specifies that conditional operations such as `putIfAbsent`, `remove(key, expected)`, and `replace(key, expected, replacement)` perform the check and modification as one atomic operation. [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

### 2.3. Using the Return Value of the Conditional Operation Itself

Non-standalone illustrative example:

```java
String previous = owners.putIfAbsent("slot", "north");
boolean registered = previous == null;
```

With `owners` as a `ConcurrentHashMap<String, String>`:

- `previous == null`: this call inserted the value because there was no prior mapping.
- `previous != null`: someone was already registered; that value is returned and is not replaced by this call.

This return value is more reliable for deciding the success/failure branch than checking beforehand with `containsKey`. Another thread can still remove or replace the registration **after** the operation completes; succeeding does not grant permanent ownership.

With `remove(key, expectedValue)` and `replace(key, expectedValue, newValue)`, "the value still matches" is checked by equality rules and does not inherently carry a version-number meaning. If the application needs to distinguish two generations of data that have the same content, represent the version in the data or protocol.

### 2.4. The Declared Type Does Not Change the Actual Object

You can write:

```java
ConcurrentMap<String, Integer> counts = new ConcurrentHashMap<>();
```

This is an illustrative declaration, requiring the corresponding imports. It expresses the requirement to use a map with concurrent guarantees. If the variable is declared as `Map` while the object is still a `ConcurrentHashMap`, Java still invokes the overridden methods of the actual object.

However, an API that accepts an arbitrary `Map` cannot assume every object passed in is safe to share. The `Map` type itself does not provide synchronization guarantees for all implementations, nor do its default methods automatically carry the same atomicity policy. [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 3. Program: Registering and Accumulating from Two Tasks

### 3.1. Rules of the Example

Two tasks, `north` and `south`, both attempt to register the key `"slot"`. The policy is that only one party may register it when the key is absent.

Afterward, each task records 1,000 requests. Every group of four requests has one check, so each task contributes 250 to the `"checks"` counter.

The program does not require a specific party to win the registration because that depends on scheduling. It verifies that **exactly one party wins** and the final counters lose no updates.

Save as **`ConcurrentRegistrationDemo.java`**:

```java
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentRegistrationDemo {
    private static final int REQUESTS = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, String> owners = new ConcurrentHashMap<>();
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> north = pool.submit(() ->
                    registerAndCount(owners, counts, start, "north"));
            Future<Boolean> south = pool.submit(() ->
                    registerAndCount(owners, counts, start, "south"));
            start.countDown();

            boolean a = north.get(10, TimeUnit.SECONDS);
            boolean b = south.get(10, TimeUnit.SECONDS);
            int successful = (a ? 1 : 0) + (b ? 1 : 0);
            require(successful == 1, "exactly one registration must win");
            require(counts.get("requests") == 2 * REQUESTS, "request count");
            require(counts.get("checks") == 2 * (REQUESTS / 4), "check count");

            String owner = owners.get("slot");
            require("north".equals(owner) || "south".equals(owner), "owner");
            require(!owners.replace("slot", "unknown", "approved"),
                    "wrong expected owner must fail");
            boolean replaced = owners.replace("slot", owner, "approved");
            boolean removed = owners.remove("slot", "approved");
            require(replaced && removed && owners.isEmpty(), "conditional update");

            System.out.println("successful registrations = " + successful);
            System.out.println("counts = " + new TreeMap<>(counts));
            System.out.println("conditional replace = " + replaced);
            System.out.println("conditional remove = " + removed);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static boolean registerAndCount(
            ConcurrentHashMap<String, String> owners,
            ConcurrentHashMap<String, Integer> counts,
            CountDownLatch start,
            String candidate) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        boolean won = owners.putIfAbsent("slot", candidate) == null;
        for (int i = 0; i < REQUESTS; i++) {
            counts.merge("requests", 1, Integer::sum);
            if (i % 4 == 0) {
                counts.merge("checks", 1, Integer::sum);
            }
        }
        return won;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentRegistrationDemo.java
java ConcurrentRegistrationDemo
```

Stdout on a successful run:

```text
successful registrations = 1
counts = {checks=500, requests=2000}
conditional replace = true
conditional remove = true
```

### 3.2. Why Can These Results Be Verified Deterministically?

`putIfAbsent` returns null for exactly one registration when the key is initially absent and no party removes it during the registration phase. Both tasks read the return value of their own call.

`merge` keeps the per-key update inside the merge operation. Each task contributes all 1,000 increments to `requests` and 250 increments to `checks`. The numbers are small, so `int` overflow does not occur.

The main thread reads and prints the results only after receiving the outcomes of both tasks. `TreeMap` is used to present keys in order, keeping stdout deterministic. There is no claim that `ConcurrentHashMap`'s iteration order matches the printed order.

The `replace`/`remove` calls at the end of the program run after the two-task phase, demonstrating the expected-value condition: a wrong expected value is not replaced, while the matching value is replaced and then removed.

The program does not measure performance and does not prove that "two keys are always updated simultaneously." It verifies the logical conditions required for the example. The timeout is only to fail if the run cannot complete; `finally` shuts down the thread pool rather than leaving the process hanging.

## 4. Why Understand the Null-Disallowing Policy?

### 4.1. Storage Contract and the Meaning of `get`

`HashMap` allows null keys and null values. Therefore, in a `HashMap`, `get(key) == null` can mean either that the key is absent or that the key is present with a null value. `containsKey` distinguishes the two states if the data is accessed in a stable or properly coordinated context. [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html#get(java.lang.Object))

`ConcurrentHashMap` does not store either kind of null. For a valid key, a null from `get` is not a null value sitting in the map.

In a concurrent environment, combining `get` with `containsKey` yourself to infer a single state also leaves a gap between the two calls. Another party could add or remove the mapping in between. Disallowing stored nulls gives `get` an absence signal that is unambiguous with respect to a null value.

This explains the purpose of the **value policy**. It does not prove that every theoretically thread-safe data structure must forbid null keys. Both null keys and null values are forbidden here because that is the specific contract of `ConcurrentHashMap`.

### 4.2. Absent on This Read Does Not Mean Absent Forever

Consider the illustrative snippet:

```java
Integer value = counts.get("job");
if (value == null) {
    System.out.println("Lan doc nay khong tim thay anh xa");
}
```

Another thread may insert `"job"` right after the read. Conversely, if `value` is non-null, another thread may remove the mapping before you finish processing it.

Thus, `get` provides the result of a single lookup; it does not reserve the key or lock the key's lifecycle. If the next step depends on the mapping remaining intact, you need a conditional operation or a broader protocol.

It is also important to distinguish a returned null from passing a null key:

```java
counts.get("missing"); // May return null.
counts.get(null);      // Throws NullPointerException.
```

This is an illustrative snippet, assuming `counts` is a `ConcurrentHashMap` and the key `"missing"` does not exist yet. The two lines test two different things: a missing mapping and an invalid key argument.

### 4.3. "No Stored Nulls" Does Not Mean "Every Null Is an Error"

| Case | Meaning in `ConcurrentHashMap` |
| --- | --- |
| `put(null, value)` | Null key is invalid |
| `put(key, null)` | Null stored value is invalid |
| `get(null)` | Null lookup key is invalid |
| `get(nonNullKey)` returns null | The read did not find a mapping |
| `getOrDefault(key, null)` when key is absent | Returns the default value null without storing it |
| `computeIfAbsent` function returns null | Does not create a mapping |
| `compute` function returns null | Removes the existing mapping or keeps it absent |
| `merge` remapping function returns null | Removes the mapping being merged |

The common thread to recognize: **null as stored data** and **null as a control signal or return result** do not play the same role.

In particular, the value argument passed directly to `merge(key, value, function)` must be non-null. That is not the same case as `function` returning null to request removal.

Read the `Throws`, `Returns`, and computation-function contract of each overload. Do not replace reading the contract with an overly broad rule of thumb like "passing or receiving null is always wrong." [ConcurrentHashMap — getOrDefault and compute methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#getOrDefault(java.lang.Object,V))

## 5. Program Testing Null Policy and Modeling Absent Results

### 5.1. Distinguishing Null Data from Do-Not-Create / Remove Signals

The program below runs on a single thread to verify the API policy explicitly. It does not use exceptions as routine input handling; intentionally invalid calls are placed inside a helper check to observe the exception type.

Save as **`ConcurrentNullPolicyDemo.java`**:

```java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentNullPolicyDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();

        System.out.println("get missing = " + map.get("missing"));
        System.out.println("getOrDefault missing, null = "
                + map.getOrDefault("missing", null));

        expectNullPointer("put(null, 1)", () -> map.put(null, 1));
        expectNullPointer("put(k, null)", () -> map.put("k", null));
        expectNullPointer("get(null)", () -> map.get(null));
        expectNullPointer("containsValue(null)", () -> map.containsValue(null));
        expectNullPointer("merge(k, null, sum)",
                () -> map.merge("k", null, Integer::sum));
        System.out.println("remove(missing, null) = " + map.remove("missing", null));

        int[] attempts = {0};
        Integer first = map.computeIfAbsent("absent", key -> {
            attempts[0]++;
            return null;
        });
        Integer second = map.computeIfAbsent("absent", key -> {
            attempts[0]++;
            return null;
        });
        require(first == null && second == null, "no value must be created");
        require(!map.containsKey("absent"), "null must not be stored");
        System.out.println("null-producing attempts = " + attempts[0]);
        System.out.println("absent stored = " + map.containsKey("absent"));

        map.put("count", 3);
        Integer computed = map.compute("count", (key, value) -> null);
        require(computed == null && !map.containsKey("count"), "compute removal");
        System.out.println("after compute-null, present = "
                + map.containsKey("count"));

        map.put("count", 3);
        Integer merged = map.merge("count", 1, (oldValue, added) -> null);
        require(merged == null && !map.containsKey("count"), "merge removal");
        System.out.println("after merge-null, present = "
                + map.containsKey("count"));

        Integer fresh = map.merge("fresh", 5, (oldValue, added) -> {
            throw new AssertionError("absent key must use the supplied value");
        });
        require(fresh == 5, "fresh merge");
        System.out.println("merge into absent key = " + fresh);

        ConcurrentHashMap<String, Optional<String>> cache = new ConcurrentHashMap<>();
        cache.put("known-missing", Optional.empty());
        cache.put("known-present", Optional.of("Lan"));
        System.out.println("unloaded cache entry = " + cache.get("unloaded"));
        System.out.println("known missing = " + cache.get("known-missing").isEmpty());
        System.out.println("known present = "
                + cache.get("known-present").orElseThrow());
    }

    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected NullPointerException: " + label);
        } catch (NullPointerException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentNullPolicyDemo.java
java ConcurrentNullPolicyDemo
```

Stdout on a successful run:

```text
get missing = null
getOrDefault missing, null = null
put(null, 1) -> NullPointerException
put(k, null) -> NullPointerException
get(null) -> NullPointerException
containsValue(null) -> NullPointerException
merge(k, null, sum) -> NullPointerException
remove(missing, null) = false
null-producing attempts = 2
absent stored = false
after compute-null, present = false
after merge-null, present = false
merge into absent key = 5
unloaded cache entry = null
known missing = true
known present = Lan
```

The first lines show that a map that does not store null can still return null when looking up an absent key. Calls to `put`/`get` with invalid keys and null stored values are tested separately.

`remove("missing", null)` returns false per this conditional overload's contract: there is no mapping holding a null value to remove. That case does not allow inserting a null value into the map. A null key argument remains invalid. [ConcurrentHashMap — remove(key, value)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#remove(java.lang.Object,java.lang.Object))

Two `computeIfAbsent` calls whose function returns null produce two computations, because no result was stored after the first call. The `attempts` array is only a local counter for a single-threaded example; do not use array-element increments like this as a shared counter across multiple threads.

The two `after ... present = false` lines show that null from a computation function is interpreted as removal, not as storing a null mapping. Calling `merge` on an absent key uses the supplied value 5 directly; the remapping function is not invoked on that branch.

### 5.2. `computeIfAbsent` Does Not Memoize a Not-Found Result If It Returns Null

Suppose a cache needs to store lookup results. If the computation function returns null when no data exists, the key remains absent; subsequent calls may have to look it up again.

Specifically on `ConcurrentHashMap`, `computeIfAbsent` executes the entire invocation atomically and only invokes the function when it needs to compute a value for an absent key per its contract. However, that is not a guarantee of "called only once in the key's lifetime": returning null, throwing an exception, or removing the mapping can cause a later call to recompute. [ConcurrentHashMap — computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

Distinguishing "no result in the cache yet" from "already looked up, known not to exist" is an application data decision. Using null for both in a null-disallowing map cannot preserve that distinction.

### 5.3. An Explicit Option: `Optional<V>`

In the program above, the cache's value type is `Optional<String>`, and the `Optional` object itself is always non-null when stored:

| Result of `cache.get(key)` | Meaning Defined by the Example |
| --- | --- |
| null | No result record in the cache yet |
| `Optional.empty()` | Recorded as not found |
| `Optional.of("Lan")` | Result `"Lan"` is present |

`Optional` is an object representing the presence or absence of a non-null value. An `Optional.empty()` is a valid object, not a forbidden null map value. [Optional Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)

A non-standalone illustrative handling snippet can use a single local read result:

```java
Optional<String> result = cache.get("user-7");
if (result == null) {
    System.out.println("Chua co ket qua trong cache");
} else if (result.isEmpty()) {
    System.out.println("Da tra cuu va khong tim thay");
} else {
    System.out.println("Tim thay: " + result.orElseThrow());
}
```

Reading once into `result` avoids combining multiple `get` calls and assuming they observe the same state. Even so, the result can still become stale immediately afterward if other parties update the cache.

`Optional` is only one option when you need three states as in the table. If the application also has loading, error, expired, refreshing, or data-version states, a dedicated result type with named states and associated data may be clearer.

Do not arbitrarily use an empty string, a negative number, or a special sentinel object that callers might mistake for real data. If you choose a sentinel object, design its type and handling rules so it cannot leak as a business value.

A "not found" result may also need to expire or be evicted when the source changes. Storing `Optional.empty()` only solves state representation; it does not provide a refresh policy or memory bound on its own.

### 5.4. Keep Computation Functions Short and Manage Side Effects Carefully

Functions passed to `compute`/`computeIfAbsent`/`merge` should only compute the needed result and return. Do not modify the same map being computed, and do not arbitrarily nest operations that could wait on each other. Some other updaters may have to wait while the computation runs.

Mapping atomicity does not cause an external service call, a write to another system, or a sent notification to roll back if the function fails. If business logic needs to coordinate the map with such side effects, a separate protocol is required.

Likewise, do not transfer a specific class's invocation-count guarantee to every `ConcurrentMap`. Some default methods may retry under contention, so the computation function may be called multiple times. [ConcurrentMap — compute and merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction))

## 6. Access Without External Locks Still Has Data-Visibility Rules

### 6.1. Publishing Objects Through the Map

One thread often creates an object, populates its fields, and puts it into the map. Another thread retrieves the object through the map and reads the initialized data.

`ConcurrentMap` specifies that actions prior to placing an object into the map happen-before actions subsequent to another thread accessing or removing that object according to the contract. With `ConcurrentHashMap`, a non-null retrieval has a relationship with the corresponding mapping update. This explains why `get` does not need a user-added external monitor to read a properly published object. [ConcurrentMap — Memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

A happens-before relationship is a memory-model rule, not a promise about how many milliseconds it takes for a thread to get CPU time. Nor does it mean every `get` is guaranteed to find the object if the writer has not inserted it yet.

The map reference itself must be shared via a proper initialization/publication mechanism. In the examples, the map is created before submitting tasks to the executor, not leaked while still under construction.

### 6.2. Program for Publishing and Sharing References

Save as **`PublishedMappingDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PublishedMappingDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Payload> map = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> producer = pool.submit(() -> {
                await(start);
                Payload payload = new Payload("Lan", 42);
                map.put("task", payload);
                return null;
            });

            Future<Payload> consumer = pool.submit(() -> {
                await(start);
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                Payload payload;
                while ((payload = map.get("task")) == null) {
                    if (Thread.currentThread().isInterrupted()) {
                        throw new InterruptedException("consumer interrupted");
                    }
                    if (System.nanoTime() - deadline >= 0) {
                        throw new IllegalStateException("publication timed out");
                    }
                    Thread.onSpinWait();
                }
                require("Lan".equals(payload.owner) && payload.amount == 42,
                        "state initialized before publication");
                return payload;
            });

            start.countDown();
            Payload received = consumer.get(10, TimeUnit.SECONDS);
            producer.get(10, TimeUnit.SECONDS);
            require(map.get("task") == received, "stored reference identity");

            System.out.println("published = " + received);
            System.out.println("same stored object = " + (map.get("task") == received));
            received.amount = 43;
            System.out.println("field after local change = " + map.get("task").amount);

            map.put("task", new Payload("Minh", 7));
            received.amount = 99;
            System.out.println("old reference after replacement = " + received.amount);
            System.out.println("current value after replacement = " + map.get("task"));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Payload {
        private String owner;
        private int amount;

        private Payload(String owner, int amount) {
            this.owner = owner;
            this.amount = amount;
        }

        @Override
        public String toString() {
            return owner + ":" + amount;
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all PublishedMappingDemo.java
java PublishedMappingDemo
```

Stdout on a successful run:

```text
published = Lan:42
same stored object = true
field after local change = 43
old reference after replacement = 99
current value after replacement = Minh:7
```

Both fields of `Payload` are intentionally non-final. The producer task populates `owner` and `amount` before `put`. The consumer task repeatedly calls `get` until it obtains the reference and then checks the data inside that task.

The `start` gate only coordinates when the two tasks begin. Object creation and field writes happen after the producer passes the gate; there is no separate "writes finished" latch for the consumer to rely on afterward. The publication path being demonstrated is the mapping in the map.

The bounded spin-wait loop is only for this small experiment. In an application that needs to wait for work or a result, use a waiting mechanism suited to the requirement, such as `Future` or an appropriate queue, rather than copying this spin loop into normal code paths.

Running the program illustrates usage. The visibility guarantee comes from the API's synchronization contract and the memory model, not from a particular run happening to print 42.

### 6.3. Safe Publication Does Not Make Values Immutable

After both tasks complete, the main thread holds the `received` reference. The line `same stored object = true` proves the map returns the exact stored object, not a deep copy.

Changing `received.amount` to 43 causes the object currently pointed to by the map to also have 43. This part runs sequentially on the main thread to illustrate reference identity.

Next, the map is updated to point to a new `Payload`. The main thread mutates the old object to 99, while the current value in the map remains `Minh:7`. Replacing a mapping does not invalidate old references that have already escaped.

If multiple threads later mutate `Payload.amount`, they still need their own mechanism to protect the field and related invariants. The map protects the mapping; it does not automatically wrap every method or field of the value object under a key.

A common mistake is creating a `ConcurrentHashMap<String, List<String>>`, using `computeIfAbsent` to obtain an `ArrayList`, and then letting multiple threads call `add` on that list. Getting or creating the mapping does not turn the `ArrayList` inside into a concurrent collection.

Design options include immutable values with whole-version replacement, values with their own synchronization, or a wrapper class holding the entire state under one protocol. The choice depends on how adding, removing, and replacing mappings must coordinate with modifying elements.

## 7. Boundaries to Respect When Reading the Contract

### 7.1. One Safe Key Is Not Multiple Keys in One Transaction

Suppose you must decrement a count at key A and increment a count at key B. Two `compute` calls may each be safe per key, yet a reader between the two calls can still observe the new state of A alongside the old state of B.

To maintain an invariant spanning multiple keys, you need a protocol covering the full scope: the same lock for every related read/write path, or grouping the state into an immutable value replaced with appropriate versioning.

Arbitrarily writing `synchronized (map)` around a block does not make other threads calling `map.put` acquire that monitor. External locking only coordinates parties that participate in the same protocol. If this kind of locking is needed, encapsulate the map so no code path bypasses it.

### 7.2. Counts and Iteration Are Not Global Snapshots by Default

While threads are updating, `size`, `isEmpty`, and `containsValue` reflect transient state. They can be useful for monitoring, but should not be used as a reservation for a subsequent action.

Iterators on `ConcurrentHashMap` views are weakly consistent: they can traverse concurrently with updates, do not throw `ConcurrentModificationException` to signal modification like standard iterators, and do not freeze the entire map at a single point in time.

Bulk operations such as `putAll` and `clear` also do not provide a whole-map transition where every concurrent reader sees only completely before or completely after. [ConcurrentHashMap — bulk operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Therefore, `new HashMap<>(liveConcurrentMap)` can produce a structurally independent copy after copying, but it does not by itself prove all entries were captured at the same version. Sorting the copy only changes display order; it does not change the consistency level of how the data was read.

If you know no writers remain during the read phase—such as after awaiting task completion in the first program—checking final counts and state has a different basis. State that condition explicitly rather than applying the conclusion to an ongoing update phase.

### 7.3. Disallowing Null Is Not a Deep Check of the Entire Object

The following illustrative snippet can be placed inside `main`, with `ConcurrentHashMap` imported:

```java
record Profile(String nickname) {}

ConcurrentHashMap<String, Profile> profiles = new ConcurrentHashMap<>();
profiles.put("user-7", new Profile(null));

System.out.println(profiles.get("user-7").nickname() == null); // true
```

The key `"user-7"` is non-null. The value is a non-null `Profile` object. The `nickname` field inside it can still be null if the `Profile` type itself allows it.

Hence, the map's rule does not replace business-data validation. If a nickname is required, the data type or input boundary must enforce that requirement.

Similarly, the map does not automatically validate every component inside a key object. A key must have correct, stable `equals`/`hashCode` while used as a key. Mutating fields that affect equality or hashing can still cause lookups to fail per the map's contract; concurrency does not remove that foundational rule. [Map Java 17 — requirements for mutable keys](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 7.4. A Returned Default Value Is Not a Stored Value

Illustrative snippet:

```java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
int missingCount = counts.getOrDefault("unknown", 0);
boolean stored = counts.containsKey("unknown");
```

With no other party updating, `missingCount` is 0 while `stored` remains false. `getOrDefault` only returns a fallback result for that read; it does not create a counter at that key.

Nor should you use `getOrDefault(key, 0)` followed by `put(key, old + 1)` as a substitute for `merge`. Even though it avoids a null unboxing error, the two calls still have a gap that loses updates.

These issues are independent: code can handle null correctly while synchronizing incorrectly, or choose the right synchronization operation while modeling absent-data state incorrectly.

## 8. Applying and Migrating from HashMap to ConcurrentHashMap

### 8.1. Choosing by Ownership and Access Pattern

| Context | Potentially Suitable Approach | What Must Stay Clear |
| --- | --- | --- |
| Map owned by only one thread | `HashMap` or a regular structure is appropriate | Do not share outside that ownership |
| Multiple threads reading/writing per-key mappings, accepting the no-null policy | `ConcurrentHashMap` | Use proper merge/compute operations; manage element state |
| Need one shared lock for an entire sequence of map operations | Wrapper class with a private lock or a synchronized map under a protocol | Every read/write path must follow the same protocol |
| Need key ordering | Choose a structure with an ordering contract | `ConcurrentHashMap` has no guaranteed key order |
| Need a record of "looked up and not found" | Explicit value such as `Optional.empty()` or a result type | Expiration, eviction, and refresh policies belong to the application |
| Need consistency across multiple objects or the whole dataset | Appropriate versioning, locking, or transaction protocol | A single concurrent collection does not provide all of this by itself |

A `Collections.synchronizedMap(new HashMap<>())` is a useful counterexample to the false rule "thread-safe maps always forbid null": the backing `HashMap` in that example still supports null keys and null values. The wrapper provides synchronization, not `ConcurrentHashMap`'s contract.

However, that does not mean simply switching to a synchronized map handles every sequence of operations. The documentation requires accessing the backing structure through the wrapper and holding the appropriate lock when iterating over views. [Collections — synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

### 8.2. Auditing Null Meanings Before Changing the Type

Changing `new HashMap<>()` to `new ConcurrentHashMap<>()` can expose old assumptions. Identify what each null case currently means:

- Key not found: no null mapping is needed.
- Data not loaded yet: can be represented by the absent state, if appropriate.
- Loaded with no result: requires an explicit value if it must be memoized.
- Invalid input data: report an error at the input boundary per the application contract.
- Removal request: call `remove` or return null according to the semantics of the computation method.
- Data-source error: do not conflate with "no result" if the two states require different handling.

Do not catch `NullPointerException` and silently ignore it as if the write succeeded. Nor should you convert null into an empty string if an empty string is valid data that the application must distinguish.

When migrating data in bulk from an old map, validate/normalize the null policy before inserting into the new map. A failed insertion should not be assumed to have rolled back the entire state. If the requirement is all-or-nothing import, design the validation and publication scope accordingly.

### 8.3. Auditing Operation Sequences After Changing the Container

After handling null data, look for patterns such as:

- `containsKey` followed by `put`.
- `get` followed by `put` of a value computed from the old number.
- `get` followed by comparison followed by `remove`.
- `size` followed by deciding whether insertion is allowed.
- Retrieving a value object and mutating its internal fields or list.

For each pattern, write down the invariant that must hold. Choose `putIfAbsent`, `merge`, `compute`, conditional remove/replace, or a broader protocol matching that exact condition.

If multiple keys are used to represent shared state, do not inspect only individual API call lines. Also consider report readers, delete/reset paths, expiration timing, and value references that have escaped.

Initial sizing parameters are likewise not element-count limits or thread-count limits. They do not replace bounding cache size; `ConcurrentHashMap` does not have built-in TTL or cache-eviction policies.

## 9. Self-Check Exercises

### Exercise 1 — Does Null on Read Mean the Map Stores Null?

A `ConcurrentHashMap<String, Integer>` returns null for `get("x")`.

**Question:** Can you conclude the map contains `"x" -> null`? Can you conclude another thread cannot insert `"x"` immediately afterward?

**Answer:** There are no null mappings in this map type. Null indicates that the read found no mapping. It does not keep the key absent for future actions; another thread can insert it immediately after the read.

### Exercise 2 — Returning Null in a Computation Function

A call to `computeIfAbsent("user-7", function)` returns null because `function` did not find the user. The next call still runs a lookup.

**Question:** Why was the first result not memoized? If you want to keep a not-found result, how can you represent it?

**Answer:** A function returning null does not create a mapping. You can use a non-null value representing "looked up and absent," such as `Optional.empty()` or a dedicated result type, along with appropriate expiration/refresh rules.

### Exercise 3 — Default Values and Counters

A developer changes:

```java
Integer oldValue = counts.get("requests");
counts.put("requests", oldValue + 1);
```

to:

```java
int oldValue = counts.getOrDefault("requests", 0);
counts.put("requests", oldValue + 1);
```

Both snippets are illustrative code, not standalone programs.

**Question:** What did the second version solve, and what is still missing?

**Answer:** It provides a default value to avoid null unboxing when the key is absent. It still does not combine read–modify–write into an atomic operation, so updates can still be lost. For the counting requirement in this lesson, using `merge` on `ConcurrentHashMap` is more appropriate.

### Exercise 4 — Null Inside an Object

A map stores `new Profile(null)` at a non-null key, and the `Profile` constructor does not forbid a null field.

**Question:** Does this violate the map's null-disallowing policy? Is it guaranteed to be valid in business logic?

**Answer:** The value reference is a non-null object, so it does not violate that storage rule itself. Field validity belongs to the data type and application contract; the map does not perform deep validation.

### Exercise 5 — Object Published and Then Mutated

Thread A creates `Payload`, puts it into the map, and later writes to its regular fields. Thread B calls `get` and reads those fields.

**Question:** Can you rely on the initial publication guarantee as proof that all subsequent field mutations are properly coordinated?

**Answer:** No. Publishing initialized data before placing it into the map and synchronizing future mutations are two different requirements. You need immutability or an element-protection mechanism sufficient for those later writes and reads.

### Exercise 6 — Do Two Safe Updates Form One State Transition?

An application uses two `compute` calls: one decrements slot A's count, and one increments slot B's count. A reader sums both keys using two `get` calls.

**Question:** Why can the reader still observe an intermediate sum?

**Answer:** Separate atomicity boundaries do not automatically join into a multi-key transaction. Both the transfer and the read must be coordinated under the invariant the application requires.

## 10. Contract Reference Documentation

The programs in this lesson illustrate API usage; when changing Java versions or implementation classes, check the documentation of the actual object:

- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent access, null policy, computation functions, and bulk-operation limits.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): conditional operations and data-publication relationships.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mapping contract, keys, and default methods.
- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): comparison of null semantics and external synchronization requirements.
- [Optional Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): representing the presence or absence of a non-null value.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): synchronized wrapper mechanism.
