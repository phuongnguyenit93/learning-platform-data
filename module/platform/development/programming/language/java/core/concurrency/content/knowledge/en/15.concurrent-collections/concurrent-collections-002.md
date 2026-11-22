# ConcurrentHashMap: `putIfAbsent()`, `compute()`, and `merge()` in Java

## 1. The Problem: A Map Updated by Multiple Threads

In Java concurrency, `Map<K,V>` is commonly used to store per-key configuration, access counts, session state, caches, or aggregations. When multiple threads access it concurrently, two requirements must be distinguished:

1. **Structural safety of the Map:** operations do not corrupt the internal data structure when multiple threads read/write concurrently.
2. **An atomic business state change:** a "check → compute → update" sequence must not be interleaved by another thread, causing lost updates or violating invariants.

A plain `HashMap` is **not thread-safe** when modified concurrently by multiple threads. Simply switching to `ConcurrentHashMap` gives the Map's own operations appropriate concurrency mechanisms; however, it does **not** mean that **every application-level sequence of calls** on the Map becomes a transaction.

Counter-example:

```java
Integer old = counts.get("java");
counts.put("java", old == null ? 1 : old + 1);
```

This is an illustrative snippet where `counts` is shared across multiple threads. Two workers can both read `5`, both compute `6`, and both write `6`. As a result, one increment is lost (**lost update**) even when `counts` is a `ConcurrentHashMap`.

The solution is to use **per-key atomic** operations, such as:

- `putIfAbsent(key, value)`: inserts only when the key has no existing mapping.
- `compute(key, remappingFunction)`: recomputes and updates/removes the value based on the **current value** for the key.
- `merge(key, value, remappingFunction)`: inserts an initial value if the key is absent; if already present, combines it with the existing value.

This lesson belongs to the **Concurrent Collections** section in general Java concurrency and requires no framework.

## 2. Why `get()` Followed by `put()` Is Not Enough

Suppose initially `counts["A"] == 10`:

```text
Thread 1                         Thread 2
--------                         --------
get("A") -> 10
                                 get("A") -> 10
compute 11
                                 compute 11
put("A", 11)
                                 put("A", 11)

Result: 11, even though there were two increment requests.
```

`ConcurrentHashMap.get` and `put` individually are designed for concurrent access, but **the gap between them is not locked as a business transaction**.

The same issue appears when writing:

```java
if (!map.containsKey(key)) {
    map.put(key, candidate);
}
```

Two threads may both observe the key as absent and then sequentially `put` two different candidates. The later writer overwrites the earlier one; both callers may think they were the initializer.

Do not try to patch this with a separate `boolean initialized` or `volatile` flag if you still lack an atomic operation combining the check and the update. With `ConcurrentHashMap`, use the API that matches the **business semantics**.

## 3. The Three APIs Side by Side

| API | When key is absent | When key already has a value | Return value | To remove |
| --- | --- | --- | --- | --- |
| `putIfAbsent(k, v)` | Associates new `v` | Keeps existing value | Previous value if present; `null` if inserted | This API does not remove |
| `compute(k, f)` | Calls `f(k, null)` | Calls `f(k, oldValue)` | New value or `null` | `f` returns `null` |
| `merge(k, v, f)` | Associates `v` **without calling `f`** | Calls `f(oldValue, v)` | Merged value or `null` | `f` returns `null` |

The three APIs have different contracts. Choose based on business semantics, not just because they all sound like "updating a Map."

**Mandatory rule:** `ConcurrentHashMap` **does not allow `null` keys or `null` values**. Calling `putIfAbsent(null, ...)`, `putIfAbsent(key, null)`, or `merge(key, null, ...)` is invalid. In `compute`, `null` is used as a **signal for absence / removing a mapping**, not as a `null` value stored in the Map.

In this lesson, all examples use JDK 17 or later and the `ConcurrentHashMap` type directly to rely on the strong contract of this implementation. Do not assume that every other `ConcurrentMap` implementation executes callbacks in the exact same way.

## 4. `putIfAbsent()`: Only One Caller Installs When the Key Does Not Exist

Signature:

```java
V putIfAbsent(K key, V value);
```

Semantics:

- If the key has no mapping, associates `value` and returns `null`.
- If the key already has a mapping, **does not replace it**, and returns the existing value.
- The entire "check key absence + write value" operation executes **atomically** for that key.
- Because `ConcurrentHashMap` forbids `null` values, a `null` return value indicates **there was no previous value** and this call installed the mapping it supplied.

Use cases: registering a unique ID, setting a default configuration, initializing a reusable object, or electing a winner in an initialization race.

### Example 1: Observing the Return Value

Create `PutIfAbsentBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class PutIfAbsentBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> services =
                new ConcurrentHashMap<>();

        String first = services.putIfAbsent("search", "node-A");
        String second = services.putIfAbsent("search", "node-B");

        System.out.println("first previous=" + first);
        System.out.println("second previous=" + second);
        System.out.println("current=" + services.get("search"));
        System.out.println("size=" + services.size());
    }
}
```

Run:

```bash
javac PutIfAbsentBasicsDemo.java
java PutIfAbsentBasicsDemo
```

Output:

```text
first previous=null
second previous=node-A
current=node-A
size=1
```

Explanation:

- On the first call, the key `"search"` is absent, so `"node-A"` is stored and `null` is returned.
- On the second call, the key already exists, so `"node-B"` is **not** installed; `"node-A"` is returned.
- The Map has exactly one key.

### When Is `putIfAbsent` Not Enough?

If the goal is to **add 1 to an existing value**, `putIfAbsent(key, 1)` only takes effect on the first call. Subsequent calls leave the value unchanged—**it does not increment**.

If you want "initialize if absent, otherwise use the existing object," `putIfAbsent` fits; if creating the candidate is expensive, consider `computeIfAbsent` to avoid constructing a new candidate on every call when the key already exists.

Note: `putIfAbsent` takes an **already-computed value**, meaning two threads may **both pay the cost of creating a candidate** before one thread wins. The API only guarantees that one mapping is installed, not that only one external constructor/call was ever executed.

## 5. `putIfAbsent` When Two Threads Race for the Same Key

Suppose two workers both try to install the key `"leader"`. You cannot predict **which thread name wins** because the scheduler decides the ordering. However, you can reliably verify that **only one call** reports success.

Create `PutIfAbsentRaceDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class PutIfAbsentRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> map =
                new ConcurrentHashMap<>();
        AtomicInteger installed = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                if (map.putIfAbsent("leader", "ready") == null) {
                    installed.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(job, "candidate-A");
        Thread b = new Thread(job, "candidate-B");

        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("installed=" + installed.get());
        System.out.println("value=" + map.get("leader"));
        System.out.println("size=" + map.size());
    }
}
```

```bash
javac PutIfAbsentRaceDemo.java
java PutIfAbsentRaceDemo
```

Output when workers are not unexpectedly interrupted:

```text
installed=1
value=ready
size=1
```

Even though both threads may attempt at the same time, for the key `leader`, only one installation from absent to `"ready"` succeeds. There is no need to predict who wins because both candidates install the same value, keeping the output deterministic.

**Do not equate "one caller installed the mapping" with "a business action ran only once."** If two threads call an external API, create a file, send an email, or write to a database **before** calling `putIfAbsent`, the side effect may have already happened twice. Execute side effects based on the win/loss result or an appropriate idempotency protocol.

## 6. `compute()`: Reading the Current Value and Deciding the New Mapping

Signature:

```java
V compute(
        K key,
        BiFunction<? super K, ? super V, ? extends V> remappingFunction);
```

The callback receives:

1. The `key` being updated.
2. The current `oldValue`; in `ConcurrentHashMap`, `oldValue == null` indicates **the key is absent**.

The callback returns:

- A `newValue != null`: installs or replaces the mapping.
- `null`: keeps no mapping for the key (if present, **removes** it; if absent, it remains absent).

With `ConcurrentHashMap.compute`, the entire operation for **a single key** is performed atomically per the contract; the callback is invoked once per call to this method. Other updates in the Map may be blocked while the callback is running, so the callback must be **short and simple**.

### Example 2: Installing, Updating, and Removing with `compute`

Create `ComputeBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ComputeBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        Integer first = map.compute("quota",
                (key, oldValue) ->
                        oldValue == null ? 10 : oldValue + 10);

        Integer second = map.compute("quota",
                (key, oldValue) ->
                        oldValue == null ? 10 : oldValue + 10);

        Integer removed = map.compute("quota",
                (key, oldValue) -> null);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("removed=" + removed);
        System.out.println("contains=" + map.containsKey("quota"));
        System.out.println("size=" + map.size());
    }
}
```

```bash
javac ComputeBasicsDemo.java
java ComputeBasicsDemo
```

Output:

```text
first=10
second=20
removed=null
contains=false
size=0
```

Sequence:

- On the first call, `oldValue == null`, so the callback returns `10`.
- On the second call, `oldValue == 10`, so the callback returns `20`.
- On the final call, the callback returns `null`, removing the mapping.
- The Map does not store `"quota" -> null`; it **no longer contains the key**.

**Distinction:** `compute(k, (key, old) -> null)` is a conditional removal driven by a callback; if no computation is needed, `remove(k)` is usually clearer.

## 7. Why Does `compute` Solve Lost Updates?

Suppose two threads both execute:

```java
counts.compute("java",
        (key, old) -> old == null ? 1 : old + 1);
```

Each call is an atomic update **for key `"java"`**. One call applies `10 -> 11`; the other call then applies `11 -> 12`, rather than both writing `11` based on a stale snapshot as with `get`/`put`.

### Example 3: 20,000 Concurrent Updates

Create `ComputeCounterDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ComputeCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                for (int i = 0; i < 10_000; i++) {
                    counts.compute("java", (key, old) ->
                            old == null ? 1 : old + 1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(job);
        Thread second = new Thread(job);
        first.start();
        second.start();
        start.countDown();

        first.join();
        second.join();

        System.out.println("java=" + counts.get("java"));
        System.out.println("size=" + counts.size());
    }
}
```

```bash
javac ComputeCounterDemo.java
java ComputeCounterDemo
```

Output when there are no unexpected interrupts:

```text
java=20000
size=1
```

Each of the two workers performs 10,000 increments. No external lock or global counter variable is used. `compute` protects the read–modify–write operation for the target key.

**Limitation:** `int` addition can overflow; if business logic requires the count not to exceed a limit, check it inside the callback or use an appropriate numeric type. Also, the Map does not automatically protect a mutable object stored as a value if other code paths modify fields inside that object.

## 8. `merge()`: Initialize or Combine Values in a Single Call

Signature:

```java
V merge(
        K key,
        V value,
        BiFunction<? super V, ? super V, ? extends V> remappingFunction);
```

Unlike `compute`, the callback of `merge` **does not receive the key**. Its two parameters are:

1. **The old value** currently stored in the Map.
2. **The incoming `value`** passed to the `merge` call.

When the key is **absent**, `merge` immediately sets the incoming `value` **without calling the callback**. When the key already has a value, the remapping function computes the new value. If the callback returns `null`, the mapping is removed.

Typical use cases: counters, word frequency, total revenue per product ID, accumulating statistics, combining two immutable result sets.

### Example 4: `merge` to Increment and Remove

Create `MergeBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class MergeBasicsDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();

        int first = map.merge("hits", 1, Integer::sum);
        int second = map.merge("hits", 4, Integer::sum);
        int third = map.merge("hits", 5, Integer::sum);

        Integer removed = map.merge(
                "hits", 2, (oldValue, incoming) -> null);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("third=" + third);
        System.out.println("removed=" + removed);
        System.out.println("contains=" + map.containsKey("hits"));

        Integer again = map.merge("hits", 7, Integer::sum);
        System.out.println("again=" + again);
    }
}
```

```bash
javac MergeBasicsDemo.java
java MergeBasicsDemo
```

Output:

```text
first=1
second=5
third=10
removed=null
contains=false
again=7
```

Why didn't the callback run on the first call? Because key `hits` did not exist yet, `merge("hits", 1, ...)` installed `1` directly. Afterward, `Integer::sum` combined the old value with the incoming value.

On the removal call, the callback received `(10, 2)` and intentionally returned `null`, so the key was removed. Then `merge("hits", 7, ...)` saw the key was absent and installed `7` again.

**Do not treat `merge` returning `null` as the Map storing a null value.** `ConcurrentHashMap` has no null values; returning `null` here signals that the mapping was removed.

## 9. Scenario Table for the Same Key

Suppose we start from an empty Map and then operate on a key `k`:

| Operation | If key was previously absent | If previously `k -> 4` |
| --- | --- | --- |
| `putIfAbsent(k, 7)` | Writes `7`, returns `null` | Keeps `4`, returns `4` |
| `compute(k, (key,v) -> v==null ? 1 : v+1)` | Writes `1`, returns `1` | Writes `5`, returns `5` |
| `merge(k, 3, Integer::sum)` | Writes `3`, returns `3` | Writes `7`, returns `7` |
| `compute(k, (key,v) -> null)` | Remains absent, returns `null` | Removes mapping, returns `null` |
| `merge(k, 3, (a,b) -> null)` | Writes `3`, **does not call callback** | Removes mapping, returns `null` |

The last row is a common trap: if you intend to use `merge` to "remove a key," a callback returning `null` **only runs when the key already has a value**. If the key is absent, `merge` will insert the incoming value. When you only want to remove a key, use `remove` or `compute` with the appropriate condition.

## 10. Using `merge` to Count Word Frequencies Across Multiple Threads

Suppose multiple tasks are reading independent text segments and need to count how many times each word appears. With `ConcurrentHashMap<String,Integer>`:

```java
frequency.merge(word, 1, Integer::sum);
```

this combines "if absent set to 1, if present increment by 1" into a single per-key atomic operation.

### Example 5: Parallel Word Frequency with Deterministic Output

Create `MergeWordFrequencyDemo.java`:

```java
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class MergeWordFrequencyDemo {
    public static void main(String[] args) throws InterruptedException {
        String[] words = {
                "java", "map", "java", "atomic",
                "map", "java", "thread", "atomic"
        };
        ConcurrentHashMap<String, Integer> frequency =
                new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);

        Runnable even = () -> {
            try {
                start.await();
                for (int i = 0; i < words.length; i += 2) {
                    frequency.merge(words[i], 1, Integer::sum);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Runnable odd = () -> {
            try {
                start.await();
                for (int i = 1; i < words.length; i += 2) {
                    frequency.merge(words[i], 1, Integer::sum);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(even);
        Thread second = new Thread(odd);
        first.start();
        second.start();
        start.countDown();
        first.join();
        second.join();

        System.out.println("frequencies="
                + new TreeMap<>(frequency));
    }
}
```

```bash
javac MergeWordFrequencyDemo.java
java MergeWordFrequencyDemo
```

Output when there are no unexpected interrupts:

```text
frequencies={atomic=2, java=3, map=2, thread=1}
```

`ConcurrentHashMap` **does not guarantee iteration order**. `new TreeMap<>(frequency)` is only used after **both workers have `join()`ed**, so the snapshot is complete and `TreeMap` sorts the `String` keys in natural order before printing.

If you repeatedly construct `new TreeMap<>(frequency)` while producers are still updating, you cannot assume it is an atomic point-in-time snapshot of all keys.

### Why Not Use a `HashMap` with `synchronized`?

You can certainly wrap every operation in a shared lock such as `synchronized(lock)` to ensure correctness. `ConcurrentHashMap` is a convenient choice when you want multiple threads to operate on different keys without locking the entire Map with an application-level monitor. Performance depends on workload, hot keys, and contention; **do not claim that `ConcurrentHashMap` is always faster than every locking approach**.

## 11. `compute()` vs. `merge()`: When Should You Choose Which?

Choose `compute` when the update:

- Needs to know the **key** inside the callback.
- Needs to read the old value and apply **complex conditions**.
- Needs to allow a `null` result to remove the key.
- Wants to rebuild an immutable value from the old value.
- Needs to handle absent and present cases with **two different logic branches**.

Example of decrementing stock and removing the mapping when quantity reaches 0:

```java
stock.compute("pencil", (key, current) -> {
    if (current == null || current <= 0) {
        throw new IllegalStateException("out of stock");
    }
    return current == 1 ? null : current - 1;
});
```

This is an illustrative snippet. It treats an absent key as out of stock and removes the mapping when the count runs out. That is just one representation; some domains need to keep a `0`-quantity mapping for reporting, in which case `0` should be returned instead of `null`.

Choose `merge` when the natural logic is **taking an incoming value and combining it with the existing value**:

```java
totals.merge(productId, amount, Long::sum);
```

This is an illustrative snippet where `totals` is `ConcurrentHashMap<String,Long>`, `productId` is `String`, and `amount` is a non-null `Long`. If the key is not present, `amount` is stored. If it is present, it is added to the old total.

Choose `putIfAbsent` when you do not want to modify an existing value:

```java
RegistryEntry previous = entries.putIfAbsent(id, candidate);
```

This is an illustrative snippet with properly constructed `entries` and `candidate`. If you need to check which object won, check `previous == null`; otherwise, you can reuse `previous`.

## 12. Callbacks for `compute`/`merge` Must Be Short and Free of External Side Effects

With `ConcurrentHashMap`, `compute` and `merge` calls execute a complete per-key atomic update; the API documentation specifies that the callback is invoked once per **method invocation**. However, while the callback runs, **other update operations may be blocked**; a slow callback increases contention and liveness risk.

Avoid:

```java
map.compute(key, (k, old) -> {
    callRemotePaymentService();
    Thread.sleep(5000);
    return expensiveRebuild(old);
});
```

This is **counter-example pseudocode**, not standalone runnable code: `Thread.sleep` requires handling `InterruptedException`, and the helpers are application-defined. The key point is **do not put blocking I/O, long waits, or external side effects inside a callback**.

Problems this causes:

- Other threads updating related mappings may have to wait.
- If the callback throws an unchecked exception, the mapping computation may not commit; **side effects already performed outside the Map are not rolled back**.
- If the callback calls an external API and that call modifies the Map or waits on a task that also needs the Map, it can easily create a wait cycle / deadlock.
- If application code retries the `compute` call after an error, external side effects may run again; **"callback once per invocation" does not mean side effect once over the business lifecycle**.

A better approach is to prepare input data outside the callback (if safe), have the callback only compute the new state and commit atomically in the Map, and coordinate external side effects separately with idempotency/transactions if needed.

**Do not claim two systems become a transaction:** updating an in-memory `ConcurrentHashMap` and sending an email or writing to a database do not automatically commit atomically together just because a `compute` call succeeded.

## 13. Do Not Update the Same Map from Inside Its Callback

The `ConcurrentHashMap` Javadoc warns that **the remapping function should not attempt to update other mappings of the same Map** while executing. Some recursive updates may be detected and throw `IllegalStateException`; others may cause blocking or unintended wait cycles.

Example to avoid:

```java
map.compute("a", (key, old) -> {
    map.put("b", "new value"); // Do not update the same map inside the callback.
    return "done";
});
```

This is a counter-example. **Do not rely on code that happens to appear to work on a particular set of keys/buckets**: bucket details, hash collisions, JDK version, and internal update mechanics are not a contract you may exploit.

If you need to update **two keys as one transaction**, do not force it with nested `compute` calls on the same Map. Use an enclosing business lock, an immutable aggregate stored under **one key**, or an appropriate synchronization/transaction structure.

In particular, avoid waiting on `Future.get()` inside a callback if the task you are waiting for must update a key in that same Map. That is a sure way to create a hard-to-analyze **thread-starvation / blocking dependency**.

## 14. Returning `null`, Throwing Exceptions, and Uncommitted Updates

For `compute`:

- **Returns a non-null value:** the new mapping is installed.
- **Returns `null`:** the mapping is removed or remains absent.
- **Callback throws an exception:** the call propagates the exception to the caller; the mapping at that key **is not modified by that failed computation** per the contract.
- **Map holds mutable values:** replacing a mapping does not make subsequent mutations inside that object safe.

For `merge`:

- If the key is absent, inserts the input `value` without calling the callback.
- If the key is present, calls the callback with `oldValue` and `incomingValue`.
- If the callback returns `null`, removes the mapping.
- If the callback throws an exception, the mapping at that key is not updated by that failed merge.

### Example 6: Exceptions Do Not Commit a New Value

Create `ComputeFailureDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class ComputeFailureDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("balance", 100);

        try {
            map.compute("balance", (key, old) -> {
                if (old < 200) {
                    throw new IllegalStateException("insufficient");
                }
                return old - 200;
            });
        } catch (IllegalStateException e) {
            System.out.println("error=" + e.getMessage());
        }

        System.out.println("balance=" + map.get("balance"));
    }
}
```

```bash
javac ComputeFailureDemo.java
java ComputeFailureDemo
```

Output:

```text
error=insufficient
balance=100
```

The callback throws, so the `compute` call does not write a new value for `balance`. If the callback had called a service outside the JVM **before** throwing, that service might already have changed; the Map does not roll back external services. The example code only performs internal validation and computation, so no such side effect occurs.

## 15. Atomicity Is Per-Key Only, Not Map-Wide

This is an important limitation of all three APIs. Suppose a Map stores two balances:

```text
left = 100
right = 0
Invariant: left + right = 100
```

If you transfer 10 units using two operations:

```java
accounts.compute("left", (k, v) -> v - 10);
accounts.compute("right", (k, v) -> v + 10);
```

then **each key is updated atomically on its own**, but a reader can read between the two calls and observe `left + right == 90`.

There is no way to call `compute` **on two independent keys** and magically turn them into a single transaction. If an invariant spans multiple keys, you must protect the entire operation with a shared mechanism or design an immutable aggregate under **a single key**.

### Example 7: Deterministically Observing an Intermediate State

Create `MultiKeyInvariantDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class MultiKeyInvariantDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> accounts =
                new ConcurrentHashMap<>();
        accounts.put("left", 100);
        accounts.put("right", 0);

        CountDownLatch leftUpdated = new CountDownLatch(1);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            accounts.compute("left", (k, v) -> v - 10);
            leftUpdated.countDown();
            try {
                proceed.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            accounts.compute("right", (k, v) -> v + 10);
        });

        writer.start();
        leftUpdated.await();

        int during = accounts.get("left")
                + accounts.get("right");
        System.out.println("during=" + during);

        proceed.countDown();
        writer.join();

        int after = accounts.get("left")
                + accounts.get("right");
        System.out.println("after=" + after);
    }
}
```

```bash
javac MultiKeyInvariantDemo.java
java MultiKeyInvariantDemo
```

Output without unexpected interrupts:

```text
during=90
after=100
```

`leftUpdated.await()` ensures the decrement on `left` has committed. `proceed` holds the writer before it updates `right`. Main observes the intermediate sum `90`. After main opens the latch, the writer increments `right` and the sum returns to `100`.

**There is no data race in the container in the sense of corrupting Map operations**; the issue is **two-step business logic lacking cross-key atomicity**.

To fix this, you can represent both balances in an immutable record `Balances(left, right)` and use `compute("accounts", ...)` to replace **the entire record** under one key; or use a shared lock for both reading and writing the aggregate. With a database, you need a storage-layer transaction, not just an in-JVM lock.

## 16. Immutable Values Give Readers a Consistent Snapshot

A good pattern: store **immutable values** instead of multi-field mutable objects. Each `compute` creates a new object from the old state and atomically replaces the single reference under the same key.

Example `Profile`:

```java
record Profile(int version, String city) {}
```

A record has final components; in this example it only contains `int` and `String`, so it is reasonable to treat it as immutable. If a record contains a mutable `List`, it is **not automatically deeply immutable**.

### Example 8: Atomically Incrementing a Version in a Record

Create `ComputeImmutableStateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ComputeImmutableStateDemo {
    record Profile(int version, String city) {}

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Profile> profiles =
                new ConcurrentHashMap<>();
        profiles.put("u1", new Profile(0, "Ha Noi"));

        CountDownLatch start = new CountDownLatch(1);

        Runnable job = () -> {
            try {
                start.await();
                for (int i = 0; i < 500; i++) {
                    profiles.compute("u1", (key, old) ->
                            new Profile(
                                    old.version() + 1,
                                    old.city()));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(job);
        Thread b = new Thread(job);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        Profile snapshot = profiles.get("u1");
        System.out.println("version=" + snapshot.version());
        System.out.println("city=" + snapshot.city());
    }
}
```

```bash
javac ComputeImmutableStateDemo.java
java ComputeImmutableStateDemo
```

Output without unexpected interrupts:

```text
version=1000
city=Ha Noi
```

Each worker updates the version 500 times, and `compute` on the same key `u1` guarantees no lost updates. Each update creates a new `Profile` without mutating the old one. The reader fetches one `Profile snapshot = profiles.get("u1")` and reads both `version` and `city` from **the same object**.

If the reader called `profiles.get("u1").version()` and then `profiles.get("u1").city()` in two separate lookups, the results could come from two different versions while writers are active. **Grab a local snapshot reference when you need multiple fields consistent at the same version.**

## 17. Mutable Values: A Safe Map Does Not Mean Safe Values

Consider:

```java
ConcurrentHashMap<String, ArrayList<String>> lists =
        new ConcurrentHashMap<>();
lists.put("events", new ArrayList<>());

lists.get("events").add("A");
```

This is an illustrative snippet requiring imports for `java.util.ArrayList` and `ConcurrentHashMap`. If multiple threads retrieve that `ArrayList` and call `add`, the thread-safe Map container **does not protect mutations inside the `ArrayList`**.

Options:

- Use an **immutable copy-on-write value** and `compute(key, ...)` to swap the reference atomically.
- Use an appropriate concurrent collection as the value if the problem truly requires concurrent in-place mutation.
- Use a lock associated with the object/aggregate under a shared protocol.
- Assign a single owner to mutate the data and publish only immutable snapshots to readers.

Per-key immutable example:

```java
events.compute("topic", (key, old) -> {
    List<String> next = new ArrayList<>(
            old == null ? List.of() : old);
    next.add("new event");
    return List.copyOf(next);
});
```

This is an illustrative snippet requiring `events` to be declared as `ConcurrentHashMap<String,List<String>>` and imports for `List` and `ArrayList`. `List.copyOf` creates a list that cannot be structurally modified through standard APIs, but **does not deep-copy mutable elements**. In this example the elements are immutable `String`s, so this approach is appropriate.

**Note:** on each update, copying the entire old list costs `O(n)` in the size of the list. If the event volume is large or updates are very frequent, copy-on-write immutability for a single key may be inefficient; choose a different structure or ownership model.

## 18. `computeIfAbsent`: Close to `putIfAbsent`, but with a Callback

Although the focus of this lesson is `putIfAbsent`, `compute`, and `merge`, `computeIfAbsent` often appears right alongside them:

```java
map.computeIfAbsent(key, k -> createValue(k));
```

It computes the mapping for the key **only when the key is absent**, and installs the value if the mapping function returns **non-null**. If it returns `null`, no mapping is installed. With `ConcurrentHashMap`, the entire invocation is atomic per key and the mapping function is called once during the invocation when computation is needed; the callback must be short and must not recursively modify the same Map.

Comparison:

| Intent | Suggested API |
| --- | --- |
| Candidate already exists; install only if absent | `putIfAbsent(k, candidate)` |
| Construct candidate **only when absent** | `computeIfAbsent(k, factory)` |
| Always recompute from current state; may remove | `compute(k, remap)` |
| Have an incoming value to combine with existing value | `merge(k, incoming, combine)` |

### `LongAdder` Example for a Frequency Map

`LongAdder` is often useful when **many threads continuously increment a hot counter**, because internally it can spread contention better than a single atomic counter.

```java
ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent(
        "java", key -> new LongAdder()).increment();

long total = counts.get("java").sum();
```

This is an illustrative snippet requiring imports for `java.util.concurrent.ConcurrentHashMap` and `java.util.concurrent.atomic.LongAdder`. `computeIfAbsent` installs a `LongAdder` if absent; the caller then increments that counter.

**Consistency distinction:**

- `LongAdder.increment()` supports concurrent updates.
- `LongAdder.sum()` while other threads are still incrementing **is not an atomic snapshot of all updates**, so it suits statistics/monitoring when an approximate point-in-time read is acceptable.
- If a business decision requires **an exact value at a linearization point**, consider another primitive and an appropriate protocol.

`computeIfAbsent` only solves **initializing the adder**; it does not turn reading `sum()` and multi-step conditional logic into a transaction.

## 19. Atomicity and Memory Ordering Under the Java Memory Model

`ConcurrentHashMap` provides concurrency guarantees so threads can safely access the same Map and observe published mappings. A successful update operation has appropriate happens-before relationships with subsequent accesses that retrieve the value from that mapping, per the concurrent collection contract.

A practical consequence: a worker can construct a **fully initialized object**, put it into a `ConcurrentHashMap`, and another worker retrieving that object via `get(key)` after the mapping is published has memory guarantees to observe the writes made prior to publication.

However, do not over-extrapolate:

- **Safe publication does not make a mutable value immutable.**
- A reader obtaining a reference while an external writer mutates unsynchronized fields can still cause a data race.
- A sequence of `get(A)` and `get(B)` does not create an atomic snapshot of two keys.
- Iterating over `entrySet()` while the Map is changing does not create a transactional snapshot of the whole Map.
- Only when using the same Map with a valid update protocol can per-key atomic APIs be used to prove correctness of the corresponding business updates.

When strict consistency is required, explicitly define the **unit of atomicity**: a single mapping, a value aggregate, or a group of multiple mappings requiring a lock/protocol.

## 20. Iterating Over `ConcurrentHashMap`: Weakly Consistent, Not an Immutable Snapshot

`ConcurrentHashMap` supports iterators and traversal operations while the Map is being updated. Its iterators are **weakly consistent**: they do not throw `ConcurrentModificationException` merely because other threads are modifying the Map, and they may reflect some concurrent modifications.

What is **not** guaranteed: that a traversal shows the exact set of all keys/values at a single point in time, in a stable order.

Example:

```java
for (var entry : map.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

This is an illustrative snippet where `map` is a `ConcurrentHashMap`. If the Map is changing, output can vary across runs; you cannot use the output of a traversal as proof of a Map-wide invariant.

APIs like `size()`, `mappingCount()`, and `containsValue()` must also be understood under concurrent updates. When the Map is under heavy writes, whole-Map statistics/aggregations are usually better suited for **monitoring** than for business decisions requiring a consistent snapshot.

If you need an exact report after a batch, wait for all producers to finish (e.g., `Thread.join()`, `Future.get()`) and then create a copy for presentation. If writers keep running, you need locking, a versioning/snapshot protocol, or an appropriate data-isolation strategy to ensure consistency.

## 21. Keys Must Have Stable `equals`/`hashCode`

`ConcurrentHashMap` is a hash-based map. It requires consistent `hashCode()` and `equals()` behavior from keys throughout the time the key is in use. If a key object's fields participating in hashing/equality are mutated after insertion into the Map, `get()`/`remove()` may fail to locate the mapping as expected.

Incorrect example:

```java
final class MutableKey {
    int id;

    MutableKey(int id) {
        this.id = id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other
                && other.id == id;
    }
}
```

This is an illustrative class. If you use `new MutableKey(1)` as a key and then change `id` to `2` after `put`, the key's hash and equality change. A thread-safe `ConcurrentHashMap` **cannot automatically recover a mutable key whose logical identity has changed**.

Prefer:

```java
record Key(int id) {}
```

With `record Key(int id)`, the primitive `int` component is final, making it convenient as a stable key. For records containing arrays or mutable objects, you must still consider deep immutability and the components' `equals`/`hashCode`.

Additionally, `compute` or `merge` callbacks should not rely on a key whose `hashCode` changes during processing.

## 22. Scalability and Hot Keys

`ConcurrentHashMap` allows operations on different keys to make progress concurrently. However, **all threads updating the same key** still contend on that single atomic unit.

For example, if 100 threads all call:

```java
counts.merge("global", 1, Integer::sum);
```

then the key `global` is a hot spot. There is no magic that distributes updates to a single key across multiple cores while keeping a single `Integer` with one atomic update order.

Optimization approaches, depending on the problem:

1. **Key sharding:** give each data partition its own key if business logic allows, reducing contention.
2. **`LongAdder`:** suitable for high-frequency increments where reading the total does not require a linearizable snapshot under concurrent updates.
3. **Batching:** each worker accumulates local counts, then merges once per batch instead of once per item.
4. **Immutable aggregates:** enable reading a consistent snapshot for a single key when the value has multiple fields.
5. **Change the algorithm:** if the workload is tiny or single-threaded, a concurrent Map adds unnecessary overhead.

Do not benchmark with a single `System.nanoTime()` call over a small array and conclude that library A is "always faster." On the JVM, you need warm-up, identical datasets, multiple runs, and a tool like JMH for microbenchmarking.

## 23. Handling Contention, Internal Locking, and Long Callbacks

Some read operations in `ConcurrentHashMap` are designed to be very efficient under many threads; complex updates like `compute`/`merge` may need to coordinate writers in the affected region. Do not write business logic assuming "`ConcurrentHashMap` is completely lock-free in every method."

Each `compute`/`merge` may need to block competing updates while the callback executes. Therefore:

- Callbacks should only perform fast computations, never remote API calls.
- Do not hold another business lock and wait on a callback for a different key in a circular dependency.
- Do not create a dependency where "callback A waits on task B, and task B needs callback A."
- Do not modify other mappings of the same Map inside a callback.
- Do not design a callback with side effects expecting an exception in the callback to roll back external systems.

If you need to maintain an invariant across multiple keys, choose an explicit strategy: an external lock covering the whole aggregate, an immutable value under one key, an actor/single-owner model, or storage-layer transactions. Using per-key callbacks simply because "the Map is concurrent" is not enough to prove a workflow is safe.

## 24. Common Mistakes and How to Fix Them

### 24.1. `get()` Then `put()` to Increment a Counter

**Wrong:** two threads read the same old value and both write the same new result. **Fix:** use `merge(k, 1, Integer::sum)` or `compute(k, (key, old) -> old == null ? 1 : old + 1)`.

### 24.2. `containsKey()` Then `put()` to Initialize

**Wrong:** non-atomic check-then-act. **Fix:** use `putIfAbsent(k, candidate)` or `computeIfAbsent(k, factory)`.

### 24.3. Using `putIfAbsent` to Accumulate

**Wrong:** the first call may install `1`, but subsequent calls will not increment. **Fix:** use `merge` or `compute` depending on the logic.

### 24.4. Forgetting to Check for `null` in a `compute` Callback

When the key is absent, `oldValue == null`. Writing `oldValue + 1` will throw a `NullPointerException` due to unboxing. **Fix:** handle the absent branch explicitly.

### 24.5. Passing `null` to Store in `ConcurrentHashMap`

`ConcurrentHashMap` does not allow `null` keys or values. **Fix:** choose a non-null sentinel/value type, or use `remove` if you want to represent the absence of a mapping.

### 24.6. Confusing `merge` with `compute` When the Key Is Absent

`merge` does not call the callback when the key is absent; it installs the input value directly. **Fix:** if you need a callback to handle both absent and present cases, use `compute`.

### 24.7. Returning `null` from a Callback Expecting the Map to Store `null`

Returning `null` removes or omits the mapping. **Fix:** use an object representing an "empty" state if business logic requires keeping the key.

### 24.8. Performing I/O or Long Waits Inside a Callback

Long callbacks can block competing updates and create lock contention. **Fix:** move I/O to a separate protocol boundary and keep callbacks short.

### 24.9. Updating the Map from Inside Its Own Callback

Nested updates may be forbidden or cause liveness bugs. **Fix:** do not modify other mappings inside the remapping function; handle multi-key updates with a different design.

### 24.10. Assuming Updating Two Keys Is a Transaction

Two `compute` calls are two separate atomic steps. **Fix:** combine them into an immutable aggregate under one key or synchronize the entire operation.

### 24.11. Using a Mutable `ArrayList` as a Value Without Synchronization

A thread-safe Map does not make `ArrayList.add` thread-safe. **Fix:** use an appropriate concurrent collection or a copy-on-write immutable value via `compute`.

### 24.12. Treating an Iterator as a Consistent Snapshot

Iterating over a Map being written to is weakly consistent. **Fix:** use quiescence or a snapshot protocol if exact figures are needed.

### 24.13. Using Mutable Keys

Changing hash/equality breaks lookups. **Fix:** use immutable keys with stable `equals`/`hashCode`.

### 24.14. Ignoring Overflow

`Integer::sum` can overflow if counts exceed the `int` range. **Fix:** use `long` or check with `Math.addExact` according to domain requirements, and have a strategy for exceeding thresholds.

### 24.15. Assuming `LongAdder.sum()` Is an Atomic Snapshot During Writes

`LongAdder` optimizes throughput in some workloads, but a concurrent read of the sum is not a linearizable snapshot. **Fix:** choose an atomic counter or a quiescence protocol if business decisions require an exact point-in-time value.

### 24.16. Ignoring Callback Exceptions

If a callback throws, the mapping does not commit that update. Callers must distinguish input errors, arithmetic errors, and runtime errors and handle them in a controlled way; do not report "success" as if the change happened.

## 25. Practice Exercises

**Exercise 1: Per-key counting.** Use `ConcurrentHashMap<String,Integer>` to count word frequencies from four producers. Implement both `compute` and `merge` approaches, wait for workers using `join()`/`Future.get()`, and compare the results.

**Exercise 2: Single-winner initialization.** Have two threads both call `putIfAbsent("leader", candidate)`, recording which caller receives `null`. Do not hardcode the winner; assert that the mapping is installed exactly once.

**Exercise 3: Decrement to zero.** Use `compute` for an inventory key. When `current == 1`, return `null` to remove; when `current > 1`, subtract 1; when the key is absent, report out-of-stock. Test negative numbers, retry policies, and exceptions.

**Exercise 4: Immutable values.** Replace a single `String` with a record `Config(version, url)` and update version/url in **one `compute`**. Readers call `get()` once and use the snapshot.

**Exercise 5: Multi-key invariant.** Simulate transferring 10 units from key A to B using two `compute` calls. Use a latch so a reader reads between the two steps, demonstrating that the sum can be skewed; then fix it using an immutable aggregate or a shared lock.

**Exercise 6: Dangerous callback.** Try placing a long wait inside a callback and observe the throughput drop (in a test environment). Never do this in production. Rewrite it so the callback only computes state.

**Exercise 7: Verifying result maps.** Use a `TreeMap` after all producers have stopped to get a deterministically sorted key output. Try iterating before waiting for producers and explain why the results can differ.

**Exercise 8: Throughput.** Compare `merge(k, 1, Integer::sum)`, `computeIfAbsent(k, () -> LongAdder).increment()` (fixing the lambda to take the key parameter), and local batching. Benchmark with the same key count and contention; do not rely on a single small run.

## 26. Self-Check Questions

**1. Why doesn't `ConcurrentHashMap` make `get` followed by `put` an atomic increment?**

Because there is a gap between the two calls where another thread can update the key. Individually thread-safe APIs do not combine two separate calls into a transaction.

**2. What does `putIfAbsent(k, v)` returning `null` mean?**

Since `ConcurrentHashMap` does not allow `null` values, it means there was no previous mapping and this call installed `v`.

**3. Can two threads calling `putIfAbsent` on the same absent key both get `null`?**

No, unless the key is removed in between or another update makes it absent again. In a one-time installation race like the example, only one caller wins.

**4. What does `compute(k, (key, old) -> null)` do?**

Removes the mapping if present, or keeps the key absent; the Map does not store `null` values.

**5. Does `merge("hits", 3, Integer::sum)` call `Integer::sum` when the key is absent?**

No. It installs `3` directly.

**6. Does `merge(k, 3, (old, incoming) -> null)` remove the key when it is absent?**

No. It inserts `3`. The callback only runs if the key already has a value.

**7. Should you call a payment API from a `compute` callback?**

No. The callback may block related updates, and external side effects outside the Map are not rolled back if the update fails or business logic retries.

**8. Does a `ConcurrentHashMap<String, ArrayList<String>>` protect concurrent `get(k).add(...)` calls?**

No. The Map's thread safety does not propagate to mutable fields or methods of its values.

**9. Do two `compute` calls updating two keys preserve an invariant across both?**

No. You need a shared atomicity mechanism or to combine the state under a single key.

**10. Why is an immutable record under one key easier to read consistently than multiple separate keys?**

A reader obtains a single snapshot reference containing fields from the same version published atomically by one mapping update.

**11. Can `entrySet()` while the Map is being written to be treated as an exact point-in-time snapshot?**

No. The iterator is weakly consistent; it may reflect some concurrent changes and does not promise a linearizable whole-Map snapshot.

**12. How do `computeIfAbsent` and `putIfAbsent` differ regarding candidate creation?**

`putIfAbsent` takes an already-constructed value. `computeIfAbsent` invokes the mapping function when the key is absent to construct the value; the callback must be kept short and free of uncontrolled side effects.

**13. Is `LongAdder.sum()` under contention a strictly atomic snapshot value?**

No. It is useful for cumulative statistics, but it is not a linearizable concurrent snapshot.

**14. If a `compute` callback throws `IllegalStateException`, is the mapping updated from that failed computation?**

No; the operation fails and the mapping for that key is not updated by that call. External side effects that occurred before the exception are not automatically rolled back.

**15. Why are mutable keys dangerous even when using `ConcurrentHashMap`?**

Because `equals`/`hashCode` can change after insertion; the Map may not be able to locate the mapping again as expected.

**16. Is `ConcurrentHashMap` always faster than a `synchronized` lock?**

No. The outcome depends on workload, hot keys, contention, callback length, memory/cache effects, and actual overhead.

## 27. Summary

**`putIfAbsent`**, **`compute`**, and **`merge`** are three foundational operations for performing **per-key atomic** updates on `ConcurrentHashMap`:

1. **`putIfAbsent(k, v)`:** installs a value only when the key is absent, without overwriting an existing value; suitable for registration/initialization.
2. **`compute(k, f)`:** recomputes state from the current value and can remove via `null`; suitable for validation, state transitions, and immutable snapshots.
3. **`merge(k, v, f)`:** installs `v` if the key is absent; if present, combines it with the old value; suitable for counters and aggregations.

They fix **check-then-act** and **read-modify-write** race conditions within the scope of **a single mapping**, but they do not turn multi-key sequences into transactions, do not automatically protect mutable objects stored as values, and do not make off-JVM side effects atomic with the Map.

To use them safely: keep keys and values non-null, use keys with stable hash/equality, keep callbacks short and never update the same Map from inside them, understand `null`/exception semantics, choose appropriate primitives for hot keys, and wait for workers to finish before generating whole-Map reports that require accuracy. **A thread-safe collection is a tool; correctness still depends on your data protocol and application invariants.**
