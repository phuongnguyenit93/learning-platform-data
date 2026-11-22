# Thread-Safety Limits of a Hand-Rolled Cache

## 1. A Single-Threaded Cache Being Correct Does Not Mean It Is Safe When Shared

A hand-rolled cache built with `LinkedHashMap` can be very short: look up by key, load data on a miss, insert into the map, and evict the least recently used entry when exceeding the limit.

In a single thread, those steps appear to follow one another naturally. When two threads share the cache, they can interleave at any gap that the design leaves open.

A bug does not necessarily manifest as an exception. The map structure may still appear usable, yet:

- The same key is loaded multiple times.
- A stale value overwrites freshly updated data.
- The entry limit is exceeded or the wrong entry is evicted.
- Iteration observes an inconsistent state.
- A value object is mutated concurrently even though the map itself is protected.
- A slow loader function blocks all other requests.

The goal of this article is to understand the **scope of guarantees of each synchronization approach**, build a small example with a clear contract, and then identify the requirements that this example does not yet solve.

There is no need to try to break `LinkedHashMap` with uncontrolled data races. We can demonstrate a specific issue using a controlled interleaving schedule and by analyzing the protection boundaries.

## 2. “Thread Safety” Consists of Many Different Questions

| Concern | Question to Answer |
| --- | --- |
| Structural integrity | Are the hash table and ordering links manipulated concurrently in an unsafe way? |
| Visibility | Do reader threads have a synchronization relationship to see the necessary writes? |
| Atomicity | Can a multi-step logical operation be interleaved by another thread? |
| Capacity policy | Are insertion, order updates, and eviction consistent under the same rules? |
| Load coordination | Do concurrent requests for the same key share a single load? |
| Data lifecycle | How are invalidation, load failures, and in-flight loads defined? |
| Value objects | Who is allowed to mutate a value after retrieval, and how? |
| Availability / liveness | Does one slow request block the entire cache? |

A `Map` implementation that is safe on individual methods does not automatically answer this entire table.

When saying a “cache is thread-safe,” state clearly which operations, which invariants, and which usage conditions are guaranteed. Do not use a single blanket label to hide many unmade decisions.

## 3. Access-Order LinkedHashMap Has Reads That Modify Structure

`LinkedHashMap` is not synchronized by itself. The [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) documentation specifies the coordination required when threads share an instance and structural modification occurs.

In access-order mode, a `get` that hits an entry can move it to the end of the linked list. Therefore, multiple threads calling only `get` can concurrently modify the ordering links.

### 3.1. Do Not Lock Only `put` and `remove`

If a design locks `put`/`remove` but leaves `get` unguarded under the assumption that “`get` is read-only,” it does not adequately protect an access-order map.

Even a method that does not itself alter order, such as `containsKey`, must not arbitrarily read a structure being modified by another thread without proper coordination.

You must consider the state actually touched, rather than classifying safety by method name alone.

### 3.2. A Read Lock Does Not Automatically Fit `get`

A read-write lock allows multiple parties to hold the read lock concurrently. That is only valid if operations inside the read region genuinely do not concurrently modify the protected state.

`get` on an access-order map does not satisfy that assumption in all cases. Putting all `get` calls under a read lock and letting them run in parallel does not make the ordering list safe.

If you still want to use a read-write model, you must accurately identify which parts require exclusive protection. Do not add a complex locking layer just to preserve a false read-only assumption.

### 3.3. Fail-Fast Does Not Replace Synchronization

`ConcurrentModificationException` only helps detect certain misuse patterns on a best-effort basis.

Not seeing an exception does not prove there are no data races. Catching the exception and retrying does not fix a structure shared against its rules.

Synchronization must come from the shared-access design, not from hoping an iterator will catch every bug.

### 3.4. `removeEldestEntry` Does Not Add Synchronization

Overriding `removeEldestEntry` only adds an eviction decision on the map’s insertion path. It does not create a lock protecting `get`, `put`, ordering links, or returned views.

A `LinkedHashMap` subclass with a `size() > limit` rule still needs the same multithreaded protocol for every access path. If the call path is wrapped by the proper lock, the hook runs within that protected context; the hook itself does not replace external coordination.

## 4. What Does a Shared Lock Protect?

An easy-to-reason-about approach is to use a single monitor to protect the entire cache state and every operation on that state.

According to the [Java Language Specification, Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html), unlocking a monitor has a happens-before relationship with a subsequent lock on that same monitor.

This provides both mutual exclusion and data visibility between code paths that follow the same rule.

### 4.1. Same State Must Use the Same Lock

Locking on one object in one method and a different object in another method does not create a shared protection boundary.

Creating a new `Object()` on each call and synchronizing on that fresh object also fails to coordinate calls with each other.

A `private final` lock object owned by the cache helps clarify ownership. Every map access path, including `size`, `invalidate`, and taking a snapshot of keys, must obey the same rule.

### 4.2. `final` and `volatile` Do Not Replace Locking for Subsequent Mutations

`final` prevents a field reference from being reassigned and plays a role in safe initialization. It does not make the referenced map object immutable.

Making a map reference `volatile` can help with publishing or swapping the entire reference. However, if multiple threads subsequently mutate the same `LinkedHashMap` instance directly without coordination, `volatile` on the reference does not protect its internal buckets and links.

A design that replaces an entire immutable snapshot is a different model and can be analyzed separately. Do not confuse it with keeping a mutable map and merely adding the `volatile` keyword.

### 4.3. Publishing the Cache to Other Threads Also Needs Proper Handling

Initialize the cache completely before sharing it and do not let `this` escape from the constructor.

The examples use `ExecutorService` to submit tasks after creating the cache. The contract of the coordination utility provides the necessary memory ordering; do not use an arbitrary shared variable and hope another thread sees the fully initialized object.

Proper locking inside methods and proper object publication are complementary parts.

## 5. `Collections.synchronizedMap`: Useful, but Does Not Make Arbitrary Code Blocks Transactional

You can wrap the map:

```java
Map<String, String> cache = Collections.synchronizedMap(
        new LinkedHashMap<>(16, 0.75f, true));
```

This is an illustrative declaration snippet with appropriate imports.

According to [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)), all access to the backing map must go through the returned wrapper to maintain serialized access.

Do not hold onto the backing map and call it directly in one place while using the wrapper in another. Those two paths break the protection contract.

### 5.1. Two Separately Locked Calls Still Have a Gap Between Them

The logic “`get`; if missing, load; `put`” has at least three parts. The wrapper does not automatically extend the monitor of a `get` call across to a `put` call written on another line.

A possible interleaving schedule is:

| Step | Thread T1 | Thread T2 |
| --- | --- | --- |
| 1 | `get(k)`: missing | |
| 2 | | `get(k)`: missing |
| 3 | Load data for `k` | |
| 4 | | Also load data for `k` |
| 5 | `put` result | |
| 6 | | `put` result again |

Each individual `get`/`put` may be properly protected. The problem here is that the **logical sequence of operations is not atomic**, so two loads still occur.

### 5.2. Do Not Equate Every API with a Hand-Written `get`/`put` Sequence

This example does not mean the wrapper’s `computeIfAbsent` is implemented as an unlocked `get`/`put` sequence.

In [Collections.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java), `SynchronizedMap` holds its mutex while calling the backing map’s `computeIfAbsent`. Thus, the mapping function can also run while holding the shared lock.

That is a different operation path, and it still has the trade-off that a slow mapping function holds the lock. You must check the corresponding contract and implementation rather than extrapolating from a `get`/`put` experiment to every `Map` method.

### 5.3. Iteration Requires Protecting the Entire Traversal

When using an `Iterator`, `Spliterator`, or `Stream` on a `synchronizedMap` view, the documentation requires manually synchronizing on the **wrapped map** across the entire traversal.

Locking on `keySet` uses a different monitor; it does not substitute for locking on the map wrapper itself.

You can snapshot the needed data inside a short synchronized block and process the snapshot outside. If snapshotting entries, avoid holding onto live map entries and mistaking them for immutable copies; copying key/value references also does not deep-copy the underlying objects.

Even when properly locked, iterating over `keySet` and calling `get` on an access-order map can still mutate the links within the same thread. The lock prevents other threads from interleaving, not the locked code itself from mutating the order. To read pairs without changing order, iterate over `entrySet` and read the value from each entry.

## 6. Java 17 Example: Synchronized Map Still Loads Twice

The following program intentionally forces two cache misses before allowing either request to proceed with loading. `CountDownLatch` controls this schedule; do not use `sleep` and hope a race appears.

The cache in this example is wrapped with `synchronizedMap`. This demonstrates a load-coordination bug, not a race on an unsynchronized `LinkedHashMap`.

Save as **DuplicateLoadDemo.java**:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DuplicateLoadDemo {
    public static void main(String[] args) throws Exception {
        Map<String, String> cache = Collections.synchronizedMap(
                new LinkedHashMap<>(16, 0.75f, true));
        CountDownLatch bothMissed = new CountDownLatch(2);
        AtomicInteger loads = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<String> request = () -> {
            String value = cache.get("k");
            if (value == null) {
                bothMissed.countDown();
                if (!bothMissed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("second miss did not arrive");
                }
                loads.incrementAndGet();
                value = "value-k";
                cache.put("k", value);
            }
            return value;
        };

        try {
            Future<String> first = pool.submit(request);
            Future<String> second = pool.submit(request);
            boolean sameResult = first.get(10, TimeUnit.SECONDS)
                    .equals(second.get(10, TimeUnit.SECONDS));
            System.out.println("same result: " + sameResult);
            System.out.println("loader calls: " + loads.get());
            System.out.println("cache size: " + cache.size());
            System.out.println("cached value: " + cache.get("k"));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DuplicateLoadDemo.java
java DuplicateLoadDemo
```

Stdout:

```text
same result: true
loader calls: 2
cache size: 1
cached value: value-k
```

Both main programs in this article were compiled with `--release 17` and run on OpenJDK 24.0.2. The compiler flag selects the target API/bytecode level; the runtime JVM is version 24.0.2.

### 6.1. Why Is Size 1 Even Though It Loaded Twice?

Both threads used the same key `"k"`, so only one mapping remains at the end. However, both observed a miss before either called `put`, so both executed the load step.

Returning the same data does not prove that coordination is efficient or correct for a loader with side effects. If loading is an expensive operation, two loads still mean twice the work.

### 6.2. What Is the Latch Proving?

`bothMissed` reaches 0 only when both requests have entered the miss branch. Only then are they allowed to load and `put`. Thus, the duplicate-load outcome is reproduced deterministically.

The `await`/`get` timeouts ensure the program fails clearly if the experiment does not make progress, rather than hanging indefinitely. They are test-harness timeouts, not a cache timeout policy.

Do not copy this barrier into a shared-lock region: if one thread holds the lock and waits for another thread to enter the same lock to count down the latch, you can create a deadlock.

## 7. A Small Cache with a Shared Lock and a Clear Contract

The next example uses a wrapper class that does not expose the backing map or live views to callers.

Illustrative contract:

- Maximum entry count must be positive.
- Neither `null` keys nor `null` values are accepted.
- All operations on the map and access order share a single private monitor.
- Insertion and eviction happen within the same protected region.
- `getOrLoad` holds the lock from the miss check through loading, writing, and eviction.
- The loader function must be short, must not call back into the cache, and must not create external lock-waiting chains.
- Keys have stable identity; `hashCode`/`equals` implementations must not mutate the cache.
- Values should be immutable data or protected by their own contract.

This design is intentionally simple so its protection boundaries can be stated clearly. It is meant for small workloads and loaders suitable for running under a lock; it is not a high-availability I/O-loading cache.

### 7.1. Invariants to Maintain

After any public method completes normally:

1. The map contains at most `maximumSize` entries.
2. Remaining entries follow the access order produced by the serialized operations.
3. No entry has a `null` value.
4. Callers hold no live iterator or view that bypasses the locking rules.

During insertion followed by eviction, `size` may temporarily exceed the limit inside the protected region. Operations that obey the same lock cannot observe that transient state.

An entry-count limit is not a byte-size limit for the entire application. Value objects, waiting requests, and loading resources also consume memory separately.

## 8. Java 17 Example: Locking the Full Operation and LRU Eviction

Save as **LockedLruDemo.java**:

```java
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

public class LockedLruDemo {
    static final class LockedLruCache<K, V> {
        private final Object lock = new Object();
        private final int maximumSize;
        private final LinkedHashMap<K, V> data =
                new LinkedHashMap<>(16, 0.75f, true);

        LockedLruCache(int maximumSize) {
            if (maximumSize <= 0) {
                throw new IllegalArgumentException("maximumSize must be positive");
            }
            this.maximumSize = maximumSize;
        }

        public V get(K key) {
            Objects.requireNonNull(key, "key");
            synchronized (lock) {
                return data.get(key);
            }
        }

        public void put(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            synchronized (lock) {
                data.put(key, value);
                trimToLimit();
            }
        }

        public V getOrLoad(K key, Function<? super K, ? extends V> loader) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(loader, "loader");
            synchronized (lock) {
                V current = data.get(key);
                if (current != null) {
                    return current;
                }
                V loaded = Objects.requireNonNull(loader.apply(key), "loaded value");
                data.put(key, loaded);
                trimToLimit();
                return loaded;
            }
        }

        public void invalidate(K key) {
            Objects.requireNonNull(key, "key");
            synchronized (lock) {
                data.remove(key);
            }
        }

        public int size() {
            synchronized (lock) {
                return data.size();
            }
        }

        public List<K> keysSnapshot() {
            synchronized (lock) {
                return List.copyOf(data.keySet());
            }
        }

        private void trimToLimit() {
            while (data.size() > maximumSize) {
                Iterator<K> iterator = data.keySet().iterator();
                iterator.next();
                iterator.remove();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        LockedLruCache<String, String> cache = new LockedLruCache<>(2);
        AtomicInteger loads = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<String> request = () -> {
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("start signal missing");
            }
            return cache.getOrLoad("k", key -> {
                loads.incrementAndGet();
                return "value-" + key;
            });
        };

        try {
            Future<String> first = pool.submit(request);
            Future<String> second = pool.submit(request);
            start.countDown();
            boolean sameResult = first.get(10, TimeUnit.SECONDS)
                    .equals(second.get(10, TimeUnit.SECONDS));
            System.out.println("same result: " + sameResult);
            System.out.println("loader calls: " + loads.get());

            cache.put("b", "value-b");
            System.out.println("get k: " + cache.get("k"));
            cache.put("c", "value-c");
            System.out.println("keys after eviction: " + cache.keysSnapshot());
            System.out.println("get evicted b: " + cache.get("b"));
            System.out.println("final size: " + cache.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LockedLruDemo.java
java LockedLruDemo
```

Stdout on the stated environment:

```text
same result: true
loader calls: 1
get k: value-k
keys after eviction: [k, c]
get evicted b: null
final size: 2
```

### 8.1. Two Concurrent Requests for the Same Key

Both tasks are released after the `start` signal. Whichever enters the protected region first sees `k` missing, invokes the loader, and stores the value.

The other enters afterward, reads the newly stored value, and does not invoke the loader. Thus `loader calls` is 1 in this scenario.

There is no need to assume the first-submitted task wins. The outcome does not depend on which thread acquires the lock first because both request the same key and value.

### 8.2. Verifying the Eviction Policy

After loading, the cache holds `k`. Putting `b` yields the sequence `k, b`. Calling `get("k")` records recent use of `k`, so the sequence becomes `b, k`.

Putting `c` exceeds the limit of 2. The iterator fetches the first key `b` and removes it via the iterator itself, leaving `k, c`.

`get("b")` returns `null`; final size is 2. This is a specific LRU case, not a prediction of arbitrary ordering across concurrent threads.

### 8.3. Why Not Return `keySet`?

`keysSnapshot` creates `List.copyOf` while holding the lock, so the caller receives a structurally independent list that cannot be modified.

It only snapshots the key references. Key objects still need to be stable; the list does not automatically turn a mutable key into an immutable one.

In the example, both keys and values are `String`, avoiding additional shared-object mutation issues.

### 8.4. How Are Load Failures and `null` Handled?

If the loader throws an exception or returns `null`, the method never reaches the `put` step. The `synchronized` block still unlocks automatically when exiting via an exception.

No failure-marker mapping is retained. A subsequent request can retry loading. This is this example’s policy, not the only valid rule for every cache.

Disallowing `null` keeps a `null` return from `get` unambiguous: the entry is not in the cache. If a problem needs to distinguish “not yet loaded” from “known not to exist,” you can use a dedicated result type and a negative-caching policy; that is an additional requirement.

### 8.5. No Promise of “Load Each Key Only Once Forever”

A mapping can be evicted due to capacity, invalidated, or never stored due to a load failure. Afterward, the same key may need to be loaded again.

The example’s guarantee is that two `getOrLoad` calls do not overlap their check–load–write sequence in the same cache under the stated conditions. It does not turn the loader into an operation that executes only once over the lifetime of the application.

## 9. Important Boundary: The Loader Runs Under the Shared Lock

The design above is easy to reason about for atomicity because everything touching map state lies inside a single mutual-exclusion region.

The trade-off lies at `loader.apply`: it executes while the monitor is still held.

### 9.1. One Slow Key Can Block Other Keys

If loading `k` makes a network call taking several seconds, `get` calls for other keys in the same cache must also wait for the monitor, even though their data is already present.

Requests for the same key share the result in the simple scenario, yet the entire cache is serialized around that work.

This is why the example requires the loader to be short and non-blocking. Do not swap in a slow query and still assume the same availability conclusions hold.

### 9.2. Calling External Code While Holding a Lock Can Create Wait Chains

A loader might acquire another lock or wait on another task. If that other task needs the currently locked cache, the two sides can deadlock waiting on each other.

Java monitors are reentrant: the same thread can re-acquire a monitor it already holds. That does not automatically fix recursive loading of the same key, dependency cycles across other caches, or cross-thread waiting.

Therefore, the example’s contract forbids the loader from calling back into the cache. Do not treat a callback that happens to succeed once as proof that an arbitrary reentrant design is correct.

### 9.3. Concurrent Ordering Is Established by the Protected Region

When multiple threads access different keys concurrently, the actual order depends on the order in which they enter and execute the protected operations.

That is not necessarily the order in which requests arrived externally or the timestamps recorded in another system.

To promise a stronger ordering guarantee, additional rules must be defined. A shared lock establishes a reason-about-able execution schedule; it cannot read the timing intent of every caller.

### 9.4. Keeping Data Correct Does Not Equal Good Latency

A design can be structurally safe yet fail to achieve the required throughput or latency.

Measure lock wait time, load time, cache hit rate, and concurrent request count. Do not benchmark single-threaded `get` and assume a locked version will scale well under load.

The programs in this article verify specific properties; stdout is not a performance benchmark.

## 10. Moving Loading Outside the Lock: Less Blocking, New Protocol Needed

An intuitive improvement:

1. Lock, check the cache.
2. Unlock, load the data.
3. Lock again, check and write the result.
4. Update order and evict if needed.

This can reduce how long the shared lock is held. However, it does not automatically preserve the full semantics of `getOrLoad` from the previous example.

### 10.1. Duplicate Loads Can Still Happen

Two threads can both pass the initial check and both load. Re-checking on write lets you keep the already-present value instead of blindly overwriting, but it cannot undo the duplicate load work already performed.

If the loader has side effects, those effects must be analyzed separately. Having only one result stored in the map does not mean only one load ran.

### 10.2. Stale Data May Be Written After Invalidation

Illustrative schedule:

```text
T1: sees k missing, starts loading old data
T2: invalidates k because source data just changed
T1: finishes loading, puts old result into cache
```

If `invalidate` only deletes an existing entry, T1’s late write can reintroduce stale data.

You must define what `invalidate` guarantees: only deleting currently stored state, or also preventing an earlier in-flight load from publishing later?

If the second requirement is needed, the design may need a version or generation token per key/load. On write, the result is accepted only if it still matches the current generation. That is an added protocol, not something provided by `putIfAbsent` alone.

### 10.3. Which Result Wins When Source Data Changes?

If two loads return two different versions, “last writer wins” does not automatically mean “newest data wins.”

You need a criterion for data version or result acceptance order. The wall-clock completion time of two tasks is not enough to infer the freshness of source data.

### 10.4. Shortening Lock Duration Must Not Split Invariants

Updating the map, access history, and eviction policy still needs coordination.

If you switch to `ConcurrentHashMap` plus a separate queue to record history, you now have two structures to keep consistent. Removing from one structure without handling the corresponding state in the other can leave stale history elements or cause wrong evictions.

An approximate LRU algorithm can accept well-defined discrepancies. However, do not claim exact LRU or a hard bound without a mechanism enforcing them.

## 11. Sharing One Load per Key Is More Than Just Adding a `Future`

You might want each loading key to have a `CompletableFuture` so other requests wait on the same result. This idea is commonly called single-flight load coalescing.

To make it a sound design, more questions must be answered:

| Event | Protocol Question |
| --- | --- |
| No data, no in-flight load | Who gets to register the load? |
| Load already in flight | How do subsequent requests share the result? |
| Load succeeds | When is the value published and the in-flight marker removed? |
| Load fails | Is the failure cached, and when can retries happen? |
| One waiter times out | Does it only stop waiting, or cancel the shared work? |
| Invalidation during load | Is the in-flight result still allowed to be written? |
| Old load finishes after a newer load | How do you avoid deleting or overwriting newer state? |
| Too many keys loading at once | Where are task counts and resources bounded? |

A request that times out does not necessarily have the right to cancel a load that other callers are still waiting on. Canceling a `Future` also does not guarantee all underlying I/O has stopped.

Cleaning up in-flight state must be tied to the specific load instance. An older load finishing must not mistakenly remove the registration of a newer load for the same key.

Bounding stored entries also does not bound the number of `Future`s, tasks, connections, or intermediate data for keys currently loading.

These questions explain why a concurrent loading cache can be far more complex than a `Map` plus a few `synchronized` lines. These are design requirements; this article does not present an incomplete `Future` snippet and call it a production-ready implementation.

## 12. What Does `ConcurrentHashMap` Solve?

`ConcurrentHashMap` provides a shared map structure along with atomic operations per its class contract.

According to [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)), `computeIfAbsent` performs the invocation atomically; the mapping function should be short and simple and must not modify the map during computation.

### 12.1. It Can Replace a Single Check-Then-Write Sequence

For a problem that only needs a concurrent mapping and a computation fitting that contract, atomic APIs avoid manually combining `get` and `put` without coordination.

However, it does not promise the function is called only once forever per key. If no value is stored, an error occurs, or the mapping is removed, subsequent calls may recompute.

Nor should it be interpreted as meaning updates to all other keys are always completely unaffected while a mapping function is running. The documentation notes that some updates may block.

### 12.2. It Does Not Provide LRU Ordering or a Capacity Cap

`ConcurrentHashMap` does not maintain an access-order chain like `LinkedHashMap` and does not evict entries by LRU.

Combining `size()`, `put()`, and a removal on separate lines does not form an atomic capacity-enforcement step. Under concurrent modifications, aggregate observations should not be treated as a map-wide transaction either.

If you add a separate ordering queue or counter, you must analyze the combined protocol. Changing the `Map` implementation name does not complete the cache policy.

### 12.3. When More Cache Capabilities Are Needed

If you need load coalescing, size/weight bounds, expiration, or async APIs with many consumers, evaluate a maintained cache library with an appropriate contract.

For example, Caffeine’s official documentation separately covers [Population](https://github.com/ben-manes/caffeine/wiki/Population) and [Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction). Those features must be chosen and configured to match requirements, rather than assuming every cache shares the same guarantees.

Even when using a library, value objects, loader correctness, and source-data freshness remain part of the application’s contract.

## 13. Returned Values Can Still Be Mutated Unsafely Outside

The cache’s lock protects the cache’s structure and operations. Once `get` returns an object, the caller can retain and use that object after the lock is released.

If the value is an `ArrayList` and two threads both add elements to it, the cache’s monitor does not surround those external `add` calls.

Several design options:

- Use immutable values, fully constructed before insertion.
- Copy data appropriately on insertion or retrieval.
- Use a value type with its own thread-safety guarantees.
- Define ownership so only one party is responsible for mutation.

A shallow copy of a `Map` or `List` structure does not deep-copy its values. An unmodifiable snapshot can still hold references to mutable objects.

Similarly, `invalidate` only removes the mapping from the cache per its contract. It does not revoke references that callers previously obtained.

## 14. Multithreaded Tests Must Prove Specific Properties

### 14.1. Use Coordination Primitives Instead of `sleep` to Guess Schedules

The first example uses `CountDownLatch` to force both threads to observe a miss before loading. That is a concrete schedule permitted by the algorithm, sufficient to refute the claim that “it probably only loads once.”

Refer to the contracts of [CountDownLatch Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) and [ExecutorService Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) when building tests that coordinate waiting and data sharing.

`Thread.sleep` does not guarantee the other thread has reached the intended step, and it can make tests both slow and flaky.

### 14.2. Test Data, Bounds, and Lifecycle Separately

For a shared-lock cache, useful checks include:

- Concurrent operations do not corrupt surviving key–value pairs.
- Every observation through the public API respects the promised entry limit.
- Accessing one key and inserting another evicts the right entry in a controlled sequential scenario.
- Two requests for the same key share the result in a scenario without intervening invalidation/eviction.
- A failing loader does not leave behind a stuck state.
- Retries can make progress according to the chosen policy.
- Snapshots are not live views and do not open a path to mutate the backing map.
- Invalidation during a load is tested according to its documented semantics, if the design loads outside the lock.

Do not assert a single fixed global ordering across threads that are allowed to contend for the lock under multiple schedules.

### 14.3. Running Many Iterations Does Not Replace Reasoning About Protection Boundaries

Multithreaded stress tests can uncover bugs, but observing zero failures across a few thousand iterations does not prove every schedule is correct.

You must read the code to identify every path touching state, protection boundaries, publication points, and assumptions about callbacks.

Two forms of evidence complement each other: a reproducible schedule for a specific bug, and an invariant argument covering every path the class permits.

## 15. Limits to Document in a Hand-Rolled Cache’s Contract

| Requirement | Must State Clearly |
| --- | --- |
| Capacity | Entry count or weight/bytes; where the bound is hard or temporarily exceeded |
| LRU | Exact relative to serialized operations or approximate |
| Nulls | Whether allowed; how misses vs. negative results are distinguished |
| Loading | Runs inside or outside the lock; whether loads are coalesced |
| Errors | Cached, retried immediately, or backed off; who receives exceptions |
| Invalidation | Removes mapping only or also invalidates in-flight loads |
| Values | Immutable, copied, or mutated under a separate mechanism |
| Iteration | Live view, snapshot, or caller must hold a lock |
| Concurrency | Which monitor/rule covers all accesses |
| Resources | Bounds on in-flight work, waiters, and wait timeouts |

A learning-oriented cache does not have to satisfy every advanced requirement. It must accurately state what it satisfies and uphold those invariants in code.

If a real application needs guarantees beyond that scope, change the design or adopt a suitable component before relying on unprovided guarantees.

## 16. Common Pitfalls and Fixes

| Misconception | Fix |
| --- | --- |
| Calling only `get` on an access-order `LinkedHashMap` performs no writes | A `get` hit can modify links; coordinate this path too |
| Wrapping with `synchronizedMap` makes any `get`–load–`put` block atomic | Define logical operation boundaries, not just per-method locks |
| Locking on `keySet` is the same as locking on the wrapper | Synchronize on the monitor required by the documentation |
| Once locked, `keySet` plus `get` is always iterator-safe | The same thread can still alter order; read directly via entries |
| A `volatile` map makes all map contents thread-safe | Distinguish publishing a reference from mutating internal structure |
| Two tasks returning the same data means only one load ran | Count and coordinate loads rather than looking only at final values |
| `computeIfAbsent` means strictly once per key forever | Account for removals, errors, unstored results, and exact guarantee scope |
| In-lock loading is safe, so performance must be good | Account for wait times and blocking other keys |
| Moving loading outside the lock leaves `invalidate` semantics unchanged | Analyze in-flight loads and result publication rights |
| Using `ConcurrentHashMap` automatically provides LRU and bounds | Ordering and capacity policies still require explicit design |
| A thread-safe cache makes mutable values thread-safe | Values need their own contract after being returned |
| Seeing no `ConcurrentModificationException` proves correctness | Fail-fast does not replace protection boundaries and concurrency reasoning |

## 17. Self-Check Exercises with Solutions

### Exercise 1: Two Read-Only Threads

An access-order map already contains several entries. Two threads only call `get`. Can synchronization be omitted because neither calls `put`?

**Solution:** No. A `get` hit can modify the ordering links; those accesses must be coordinated.

### Exercise 2: Two Misses

Individual `get`/`put` calls are protected by `synchronizedMap`. Two threads both load `k` and the final size is 1. Is there a contradiction?

**Solution:** No. Individual methods are protected, but the check–load–write sequence is not atomic. Two loads can still produce a single final key.

### Exercise 3: Locked Iteration

A thread synchronizes on the wrapper, iterates over `keySet`, and calls `get` for each key. Does the lock prevent that loop itself from changing the order?

**Solution:** No. The monitor prevents other lock-obeying threads from interleaving, but the same thread calling `get` still mutates the sequence. If you only need the data, iterate over `entrySet` and read the value from each entry.

### Exercise 4: Slow Loader

A cache has a single shared lock and runs the loader inside the lock. When loading `a` is slow, must a `get` for an already-present `b` wait?

**Solution:** It may have to wait for the same monitor. Structural safety does not automatically provide concurrent availability.

### Exercise 5: Invalidation During Out-of-Lock Loading

`T1` starts loading `k`, `T2` invalidates `k`, and then `T1` stores its result. If the requirement is to prevent stale results from returning after invalidation, is simply calling `remove(k)` enough?

**Solution:** No. A protocol for in-flight loads is needed, such as checking a generation/version before accepting the result.

### Exercise 6: List Values

A cache locks all `get`/`put` calls but returns the same `ArrayList` to multiple threads. Are external `add` calls automatically covered by the cache lock?

**Solution:** No. You must use immutable values, copying, a thread-safe value structure, or an appropriate ownership contract.

### Exercise 7: Entry Limit vs. In-Flight Work

A cache retains at most 100 entries but allows thousands of keys to load concurrently. Are total resources guaranteed to be bounded by 100?

**Solution:** No. Tasks, `Future`s, connections, and intermediate data have a different lifecycle from stored entries.

### Exercise 8: Choosing Test Evidence

A multithreaded test runs once without errors. Is that enough to declare the class correct under all schedules?

**Solution:** No. You need property-based tests and an analysis of all access paths, protection boundaries, and class invariants.

## 18. References

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): access-order, structural modification, and synchronization requirements.
- [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)): access via wrapper and traversal synchronization.
- [Collections.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java): locking paths of `SynchronizedMap` methods.
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitors, happens-before relationships, and data races.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic operations and recomputation limits.
- [Caffeine — Population](https://github.com/ben-manes/caffeine/wiki/Population), [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction): reference for load responsibilities and cache policies.

A hand-rolled cache can be correct within a small, well-defined scope. What makes it safe is that every access path follows the same protocol, and what makes it suitable for an application is that those guarantees match the requirements for loading, data lifecycle, and availability.
