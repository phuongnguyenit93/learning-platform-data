# putIfAbsent, compute, merge, and Per-Key Atomicity

A shared counter needs to be incremented from its current value. A cache needs to compute data when it is absent. A state entry needs to be recomputed or removed depending on a check result. All of these problems share a common trait: the write decision depends on the currently stored state.

If you read the state with one call and write with another, another thread can change the data in between. **Per-key atomicity** combines the decision and the update of a single mapping into an operation with a clear contract. It does not turn all work around the map into a single transaction.

This lesson uses Java 17's `ConcurrentHashMap` as the primary subject when discussing atomic `compute` and `merge` calls. At the same time, it distinguishes it from `Map` in general and from other `ConcurrentMap` implementations, because guarantees around the mapping function can differ.

Concepts to recognize:

- **Candidate:** a value already computed by the caller that it wants to insert into the map.
- **Mapping computation function:** a function passed to the map to compute a value from the key or from the current value.
- **Incoming value to merge:** new data passed to `merge`, which is stored directly when the key is absent or combined with the old value when present.
- **Atomicity of a mapping:** the condition and update on a key are coordinated according to the method's contract.
- **External side effects:** sending notifications, mutating other objects, writing files, or calling external systems; they are not automatically part of the map's transaction.
- **Mapping lifecycle:** the process of creating, updating, removing, and possibly recreating the same key.

Start from the meaning of the data to be updated, then choose the API. Using a thread-safe structure is only the foundation; how calls are composed still determines the outcome.

## 1. The Gap Between Read and Write

Suppose `totals` is a `ConcurrentHashMap<String, Integer>` and the key `"visits"` currently has the value `10`:

~~~java
int old = totals.get("visits");
totals.put("visits", old + 1);
~~~

This is an illustrative snippet inside a method, not a standalone program. One valid execution schedule could be:

~~~text
Thread A reads 10
Thread B reads 10
Thread A writes 11
Thread B writes 11
~~~

There are two increment requests, yet the final number is `11`. Neither map corruption nor an exception is needed for a wrong count to happen. Each individual call executed correctly, but the read-then-write sequence as a whole was not an atomic operation.

With `ConcurrentHashMap`, a single increment can be expressed as:

~~~java
totals.compute("visits", (key, old) -> old == null ? 1 : old + 1);
~~~

Or:

~~~java
totals.merge("visits", 1, Integer::sum);
~~~

Both approaches can express a counter starting at `1` when the key is absent. However, they do not have the same input shape or function-invocation semantics; you must understand the branches before using them for more complex problems.

## 2. API Selection Map

The table below applies to `ConcurrentHashMap`, which does not store `null` values.

| API | When key is absent | When key is present | Return value |
|---|---|---|---|
| `putIfAbsent(k, candidate)` | Inserts the candidate. | Keeps the existing value. | The previous value, or `null` if just inserted. |
| `computeIfAbsent(k, loader)` | Calls the function with the key; stores if result is non-`null`. | Does not call the function; uses existing value. | Existing or computed value, or `null` if no mapping was created. |
| `computeIfPresent(k, updater)` | Does not call the function. | Calls the function with key and old value; a `null` result means removal. | Updated value, or `null` if no mapping remains. |
| `compute(k, updater)` | Calls the function with old value `null`. | Calls the function with the old value. | Computed value, or `null` if absent/removed. |
| `merge(k, incoming, combiner)` | Stores `incoming`; does not call the combiner. | Calls the combiner with old value and `incoming`; a `null` result means removal. | Stored value, or `null` if removed. |

`ConcurrentHashMap` specifies that these compute/update calls are performed atomically according to the method contract. Always check the specific rules for the computation function and absent/present conditions on the exact implementation. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

The table does not state that a returned value will remain unchanged forever. After the call completes, another caller may continue updating or removing the key.

## 3. putIfAbsent: Candidate Already Available, Insert Only When Absent

Illustrative pattern:

~~~java
String old = cache.putIfAbsent("profile-3", candidate);
String chosen = old == null ? candidate : old;
~~~

This snippet assumes `cache` is a `ConcurrentHashMap<String, String>` and `candidate` is a non-`null` string already available. If the key is absent, `old` is `null` and the candidate is chosen. If the key is present, `old` is the value retained at that decision point.

The key point is that checking for absence and inserting are not split apart like writing `containsKey` followed by `put`. The `ConcurrentMap.putIfAbsent` contract specifies that this conditional action is performed atomically. [Java 17: ConcurrentMap.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#putIfAbsent(K,V))

### 3.1. Arguments Are Evaluated Before the Method Runs

~~~java
cache.putIfAbsent("profile-3", loadProfile());
~~~

The illustrative snippet above assumes a `loadProfile` method returning a suitable string. Java still has to call it to obtain the argument before invoking `putIfAbsent`, even if the map already contains a value.

Therefore, two threads can both build two expensive candidates, and then only one candidate is inserted. The atomicity of insertion does not prevent duplicated preparation work.

This can be a suitable choice if the candidate is cheap, already available, or intentionally constructed outside the map's computation scope. If creation should happen only when absent, consider `computeIfAbsent` and the contract of the specific map class.

### 3.2. Successful Insertion Does Not Extend Ownership

`putIfAbsent` returning `null` confirms that the insertion succeeded on a map that does not store `null`. It does not guarantee that another party cannot remove and recreate the key before the caller performs its next step.

If a mapping is used to record work ownership, you must also define session IDs, expiration, cleanup conditions, and whether stale requests may affect a new session. An atomic insertion is only one component of that protocol.

## 4. computeIfAbsent: Compute When Absent

Illustrative example with a configuration map:

~~~java
String value = settings.computeIfAbsent("region", key -> "local");
~~~

Assume `settings` is a `ConcurrentHashMap<String, String>`. If a value already exists, it is returned. If absent, the function is used to compute the value.

For `ConcurrentHashMap`, the Java 17 Javadoc specifies that the function is invoked once during the call that needs to compute when the key is absent, and is not invoked when already present. Some updates may have to wait while computation is in progress, so the function should be short, simple, and must not modify the map itself during computation. [Java 17: ConcurrentHashMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

### 4.1. Returning null Does Not Cache Absence

If the function returns `null`, no new mapping is created. Subsequent calls can still invoke the function again.

This differs from "remembering that it was not found." If an application wants to remember failed lookup results as well, it can use a value type that explicitly represents that state, such as a result object or a non-`null` `Optional`. In that case, you also need to design expiration and refresh conditions according to the data's semantics.

### 4.2. Once Per Call Does Not Mean Once in the Key's Lifetime

The function can be called again in a later usage because:

- The previous call returned `null`, so no mapping was created.
- The previous call threw an exception, so no value was set.
- The value was removed.
- The application used a different map or key.

For example, if two threads call it concurrently on an absent key, the function succeeds, and nobody removes or replaces the mapping during that period, you can verify that the loader runs once and both receive the value. When those lifecycle conditions change, the "once" conclusion no longer holds.

## 5. compute: Recompute from Current State

`compute` takes a two-argument function: the key and the old value. On `ConcurrentHashMap`, an old value of `null` indicates that the key is absent.

Example:

~~~java
Integer remaining = stock.compute("book", (key, old) -> {
    if (old == null) {
        return null;
    }
    return old > 0 ? old - 1 : old;
});
~~~

This snippet assumes `stock` is a `ConcurrentHashMap<String, Integer>`. It does not create missing items, decrements by one when the count is positive, and keeps `0` when out of stock.

**Do not read `remaining` and conclude for certain that you just claimed one unit.** A result of `0` could come from decrementing `1` to `0` or from keeping an existing `0`. If the caller needs to know whether the operation was accepted or rejected, the result model must express that through an appropriate protocol; the final stock count alone is not enough to distinguish them.

### 5.1. A null Result Means Removal

For an existing key, returning `null` from `compute` removes the mapping. For an absent key, returning `null` keeps it absent. The map does not store a "new null value."

Therefore, do not use `return null` as a way of saying "I do not want to change anything" if you want to keep the existing mapping. To keep it unchanged, return the old value.

### 5.2. Keeping the Same Value Is Still a Meaningful Branch

A function can return the old value when conditions do not permit a change. However, as in the stock example, the return value alone may not reveal which branch was taken. Determine what the caller needs to know before designing the function.

Do not secretly use an external list or unsafe shared variable just to pass an extra decision result out of the computation function. If the model requires both the state and the decision outcome, use a design with a clear contract and verify how that outcome is published.

### 5.3. computeIfPresent Narrows the Invocation Condition

`computeIfPresent` calls the function only when the key currently has a value. On a map that does not store `null`, an absent key causes the function not to run and the result to be `null`. Returning `null` when present removes the mapping.

It is useful when the update applies only to an already-existing entry. If you need to handle the absent branch to create a new entry or detect a condition, `compute` is a better fit.

## 6. merge: New Data Needs to Be Combined Under the Same Key

`merge` cleanly separates the new incoming data from the combining function:

~~~java
totals.merge("visits", 1, Integer::sum);
~~~

If the key is absent, the number `1` is stored directly. If already present, the function receives the old number then the new incoming number and computes the sum. On `ConcurrentHashMap`, the entire call is performed atomically. [Java 17: ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction))

### 6.1. The Combiner Does Not Receive the Key

The function signature for `merge` is:

~~~text
(oldValue, incomingValue) -> combinedValue
~~~

The function signature for `compute` is:

~~~text
(key, oldValue) -> newValue
~~~

Confusing these two signatures can produce a function that still compiles if the types happen to match, yet computes on the wrong data. Clear parameter naming helps avoid this mistake.

### 6.2. An Absent Key Does Not Invoke the Combiner

If you expect normalization or validation to always happen inside the combiner, the absent branch will bypass it. `incoming` is chosen directly in that branch.

For example, `merge(k, text, combiner)` will not automatically run `combiner` to trim whitespace for the first value. Normalize the data beforehand or choose an operation that handles both branches as required.

### 6.3. Input null and Result null Have Different Meanings

`merge` requires `incoming` to be non-`null`. Passing `null` as the incoming data is not a removal request.

Conversely, a combiner returning `null` means removing the existing mapping. A subsequent `merge` on the removed key will go back to the branch that stores the new incoming data directly.

Do not use a single blanket statement like "merge accepts null" for both positions. Always specify whether you mean the input parameter or the function's return value.

### 6.4. Atomicity Does Not Choose Business Ordering

If multiple threads merge strings, each merge can be atomic, yet the final string order depends on the order of updates. A concatenation function `old + incoming` does not automatically sort data by event timestamp or external sequence number.

With small-integer addition in the example, increments yield the same sum regardless of which thread goes first. With subtraction, "latest version" selection, floating-point numbers, or ordered strings, you must check whether the merge operation is valid under all possible update orders.

## 7. Standalone Runnable Program

The `PerKeyUpdateDemo.java` file below uses APIs available in Java 17. The example was compiled with `javac --release 17` and run on OpenJDK Zulu 24.0.2; do not treat this as proof that it was run on JVM 17.

The example uses a map that does not allow `null`. The multithreaded sections use barriers to control critical timing, keep data scopes clear, and wait for threads to finish before printing.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class PerKeyUpdateDemo {
    @FunctionalInterface
    interface Operation {
        void perform() throws Exception;
    }

    static void twoThreads(Operation operation) throws Exception {
        AtomicReference<Throwable> error = new AtomicReference<>();
        Runnable wrapped = () -> {
            try {
                operation.perform();
            } catch (Throwable failure) {
                error.compareAndSet(null, failure);
            }
        };
        Thread alpha = new Thread(wrapped, "alpha");
        Thread beta = new Thread(wrapped, "beta");
        alpha.setDaemon(true);
        beta.setDaemon(true);
        alpha.start();
        beta.start();
        alpha.join(5000);
        beta.join(5000);
        if (alpha.isAlive() || beta.isAlive()) {
            alpha.interrupt();
            beta.interrupt();
            throw new AssertionError("Threads did not terminate");
        }
        if (error.get() != null) {
            throw new AssertionError("Unexpected thread failure", error.get());
        }
    }

    static String exceptionName(Runnable operation) {
        try {
            operation.run();
            return "none";
        } catch (RuntimeException failure) {
            return failure.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        System.out.println("put-first-old = " + counts.putIfAbsent("p", 2));
        System.out.println("put-again-old = " + counts.putIfAbsent("p", 9));
        System.out.println("put-current = " + counts.get("p"));

        System.out.println("compute-create = "
                + counts.compute("c", (key, old) -> old == null ? 5 : old + 5));
        System.out.println("compute-update = "
                + counts.compute("c", (key, old) -> old + 2));
        System.out.println("compute-delete = "
                + counts.compute("c", (key, old) -> null));
        System.out.println("compute-present-after-delete = "
                + counts.containsKey("c"));

        AtomicInteger absentCalls = new AtomicInteger();
        System.out.println("absent-load = " + counts.computeIfAbsent("a", key -> {
            absentCalls.incrementAndGet();
            return 3;
        }));
        System.out.println("absent-reuse = " + counts.computeIfAbsent("a", key -> {
            absentCalls.incrementAndGet();
            return 99;
        }));
        System.out.println("absent-load-calls = " + absentCalls.get());

        AtomicInteger nullCalls = new AtomicInteger();
        for (int attempt = 0; attempt < 2; attempt++) {
            counts.computeIfAbsent("not-cached", key -> {
                nullCalls.incrementAndGet();
                return null;
            });
        }
        System.out.println("null-load-calls = " + nullCalls.get());
        System.out.println("null-load-cached = " + counts.containsKey("not-cached"));

        AtomicInteger presentCalls = new AtomicInteger();
        System.out.println("present-missing = "
                + counts.computeIfPresent("missing", (key, old) -> {
                    presentCalls.incrementAndGet();
                    return old + 1;
                }));
        System.out.println("present-missing-calls = " + presentCalls.get());
        System.out.println("present-update = "
                + counts.computeIfPresent("p", (key, old) -> old + 8));

        AtomicInteger mergeCalls = new AtomicInteger();
        System.out.println("merge-seed = " + counts.merge("m", 4, (old, incoming) -> {
            mergeCalls.incrementAndGet();
            return old + incoming;
        }));
        System.out.println("merge-calls-after-seed = " + mergeCalls.get());
        System.out.println("merge-combine = " + counts.merge("m", 3, (old, incoming) -> {
            mergeCalls.incrementAndGet();
            return old + incoming;
        }));
        System.out.println("merge-delete = "
                + counts.merge("m", 1, (old, incoming) -> null));
        System.out.println("merge-reseed = " + counts.merge("m", 6, Integer::sum));

        ConcurrentHashMap<String, String> words = new ConcurrentHashMap<>();
        words.put("line", "A");
        System.out.println("merge-argument-order = "
                + words.merge("line", "B", (old, incoming) -> old + ">" + incoming));

        counts.put("failure", 8);
        System.out.println("compute-error = " + exceptionName(() ->
                counts.compute("failure", (key, old) -> {
                    throw new IllegalArgumentException("Cannot compute");
                })));
        System.out.println("value-after-error = " + counts.get("failure"));
        System.out.println("merge-null-seed = " + exceptionName(() ->
                counts.merge("failure", null, Integer::sum)));

        ConcurrentHashMap<String, List<String>> boxes = new ConcurrentHashMap<>();
        List<String> original = new ArrayList<>(List.of("start"));
        boxes.put("box", original);
        System.out.println("mutable-error = " + exceptionName(() ->
                boxes.compute("box", (key, old) -> {
                    old.add("touched");
                    throw new IllegalStateException("After object mutation");
                })));
        System.out.println("same-mapped-object = " + (boxes.get("box") == original));
        System.out.println("mutable-value-after-error = " + boxes.get("box"));

        ConcurrentHashMap<String, Integer> broken = new ConcurrentHashMap<>();
        broken.put("n", 10);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        twoThreads(() -> {
            int observed = broken.get("n");
            bothRead.await(5, TimeUnit.SECONDS);
            broken.put("n", observed + 1);
        });
        System.out.println("separate-read-write = " + broken.get("n"));

        ConcurrentHashMap<String, Integer> merged = new ConcurrentHashMap<>();
        CyclicBarrier mergeStart = new CyclicBarrier(2);
        twoThreads(() -> {
            mergeStart.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                merged.merge("n", 1, Integer::sum);
            }
        });
        System.out.println("concurrent-merge = " + merged.get("n"));

        ConcurrentHashMap<String, Integer> computed = new ConcurrentHashMap<>();
        CyclicBarrier computeStart = new CyclicBarrier(2);
        twoThreads(() -> {
            computeStart.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                computed.compute("n", (key, old) -> old == null ? 1 : old + 1);
            }
        });
        System.out.println("concurrent-compute = " + computed.get("n"));

        ConcurrentHashMap<String, String> offered = new ConcurrentHashMap<>();
        AtomicInteger constructed = new AtomicInteger();
        AtomicInteger insertions = new AtomicInteger();
        CyclicBarrier offersReady = new CyclicBarrier(2);
        twoThreads(() -> {
            String candidate = "offer-" + constructed.incrementAndGet();
            offersReady.await(5, TimeUnit.SECONDS);
            if (offered.putIfAbsent("one", candidate) == null) {
                insertions.incrementAndGet();
            }
        });
        System.out.println("putIfAbsent-constructed = " + constructed.get());
        System.out.println("putIfAbsent-insertions = " + insertions.get());

        ConcurrentHashMap<String, String> loaded = new ConcurrentHashMap<>();
        AtomicInteger loaderCalls = new AtomicInteger();
        AtomicInteger validResults = new AtomicInteger();
        CyclicBarrier loadsReady = new CyclicBarrier(2);
        twoThreads(() -> {
            loadsReady.await(5, TimeUnit.SECONDS);
            String value = loaded.computeIfAbsent("one", key -> {
                loaderCalls.incrementAndGet();
                return "ready";
            });
            if ("ready".equals(value)) {
                validResults.incrementAndGet();
            }
        });
        System.out.println("computeIfAbsent-loader-calls = " + loaderCalls.get());
        System.out.println("computeIfAbsent-valid-results = " + validResults.get());
    }
}
~~~

Commands to run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 PerKeyUpdateDemo.java
java PerKeyUpdateDemo
~~~

Verified stdout:

~~~text
put-first-old = null
put-again-old = 2
put-current = 2
compute-create = 5
compute-update = 7
compute-delete = null
compute-present-after-delete = false
absent-load = 3
absent-reuse = 3
absent-load-calls = 1
null-load-calls = 2
null-load-cached = false
present-missing = null
present-missing-calls = 0
present-update = 10
merge-seed = 4
merge-calls-after-seed = 0
merge-combine = 7
merge-delete = null
merge-reseed = 6
merge-argument-order = A>B
compute-error = IllegalArgumentException
value-after-error = 8
merge-null-seed = NullPointerException
mutable-error = IllegalStateException
same-mapped-object = true
mutable-value-after-error = [start, touched]
separate-read-write = 11
concurrent-merge = 2000
concurrent-compute = 2000
putIfAbsent-constructed = 2
putIfAbsent-insertions = 1
computeIfAbsent-loader-calls = 1
computeIfAbsent-valid-results = 2
~~~

The two threads in each scenario use data dedicated to that scenario. Errors on worker threads are propagated back to the main thread; the timeout ensures the check fails if stuck, rather than deciding which thread wins.

## 8. Reading the Output by Group

### 8.1. putIfAbsent Returns the Previous Value

~~~text
put-first-old = null
put-again-old = 2
put-current = 2
~~~

The first call inserts `2`. The next call offers candidate `9` but receives the existing `2`; the stored value remains `2`.

That is the difference between `putIfAbsent`'s return value and the return values of computation methods that return the post-update value. Do not write a shared helper and assume every return value is the new value.

### 8.2. compute Creates, Updates, and Deletes

~~~text
compute-create = 5
compute-update = 7
compute-delete = null
compute-present-after-delete = false
~~~

The absent branch creates `5`, the next call uses `5` to compute `7`, and returning `null` removes the key. The final check with `containsKey` in this sequential scenario confirms the key is absent.

In a system where writers continue running, a later read is just a new observation. The key does not need to stay absent forever for the earlier removal to have satisfied its contract.

### 8.3. The Loader Runs Only When Needed, and null Is Not Cached

~~~text
absent-load = 3
absent-reuse = 3
absent-load-calls = 1
null-load-calls = 2
null-load-cached = false
~~~

The existing value `3` prevents the subsequent call from running the function that produces `99`. Meanwhile, the function that always returns `null` is called on both attempts because no mapping was created.

If the loader calls an expensive service, not caching absent results can have a significant impact on cost and traffic. This behavior must be chosen deliberately.

### 8.4. computeIfPresent Does Not Handle Absent Keys

~~~text
present-missing = null
present-missing-calls = 0
present-update = 10
~~~

On `missing`, the function does not run. On `p`, which already holds `2`, the function adds `8` to produce `10`.

If a requirement states that an action must occur even when the key is absent, placing it only inside `computeIfPresent` will miss that branch.

### 8.5. merge Distinguishes Initial Insertion from Combining

~~~text
merge-seed = 4
merge-calls-after-seed = 0
merge-combine = 7
merge-delete = null
merge-reseed = 6
~~~

The initial value `4` is stored without calling the combiner. The new value `3` is added to `4` to produce `7`. Returning `null` removes the key; next time, `6` becomes the initial value of a new mapping.

The line `merge-argument-order = A>B` confirms that the function receives the stored value `A` first and the incoming value `B` second. Because this is a sequential example, the character order is completely predictable.

### 8.6. Exceptions Are Not Transactions Across All Objects

~~~text
compute-error = IllegalArgumentException
value-after-error = 8
merge-null-seed = NullPointerException
~~~

The computation function on the integer throws an exception before returning a new value; the mapping still holds `8`. A `null` incoming value in `merge` is rejected.

The next group shows a different outcome regarding object contents:

~~~text
mutable-error = IllegalStateException
same-mapped-object = true
mutable-value-after-error = [start, touched]
~~~

The map still points to the same list. However, the function mutated that very list before throwing, so the element `touched` does not vanish on its own.

This section intentionally runs on a single thread to illustrate rollback limits; it is not a safe pattern for multiple threads mutating an `ArrayList`. "The mapping remains unchanged when the function throws" does not mean "every object touched by the function is restored."

### 8.7. Two Thousand Updates Without Lost Updates from Split Read-Write

~~~text
separate-read-write = 11
concurrent-merge = 2000
concurrent-compute = 2000
~~~

In the first scenario, both threads read `10` and both write `11`. In the next two scenarios, each thread performs `1,000` atomic updates on the same key, with no intervening removals or other writes, so the total is `2,000`.

The example uses a small number range so `int` overflow does not occur. In real applications, addition must still account for numeric bounds or use appropriate types/checks. Atomicity does not eliminate arithmetic errors.

### 8.8. Insertion Atomicity and Candidate Construction Are Two Separate Scopes

~~~text
putIfAbsent-constructed = 2
putIfAbsent-insertions = 1
computeIfAbsent-loader-calls = 1
computeIfAbsent-valid-results = 2
~~~

In the `putIfAbsent` section, two threads are forced to finish building their candidates before contending on insertion, resulting in two constructions and one accepted insertion.

In the `computeIfAbsent` section on `ConcurrentHashMap`, there are no removals or errors during that phase. The loader runs once, and both calls receive `ready`. The program does not depend on which thread runs the loader first.

## 9. Exact Scope of Atomicity

### 9.1. Updating a Single Key's Mapping

For a `compute`/`merge` call on `ConcurrentHashMap`, there is no external read followed by an unconditional overwrite like the buggy pattern at the start of the lesson. Competing updates are coordinated according to the method contract.

This does not promise that every data key has a completely independent lock at the implementation level. Internal structure, hash collisions, and map maintenance work can affect contention and performance. Do not infer from "per-key" that different keys always run in parallel without affecting each other.

### 9.2. Reads Can Continue During Computation

Retrieval operations on `ConcurrentHashMap` generally do not lock in the same way as updates and can overlap with updates. Therefore, do not treat a running `compute` function as a sealed room where no one can read values.

With immutable values, readers observe either the old value or the value published under the contract, rather than accessing an instance being mutated in place. With mutable objects, having the computation function mutate fields of the old object introduces a synchronization problem that the map does not solve for you.

That is why you should prefer **creating a new value and returning it** when updating state through a map.

### 9.3. Does Not Extend to Operations on the Returned Object

The following pattern should be read as two separate steps:

~~~java
groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(member);
~~~

This is an illustrative snippet intentionally written to analyze boundaries, assuming `groups` holds lists and the other variables exist. Finding or creating the list can be coordinated by the map. The `add` step happens **after the map call returns**, and is not automatically inside `computeIfAbsent`'s atomic scope.

If multiple threads obtain the same `ArrayList` and call `add` concurrently, the list itself needs its own synchronization mechanism. Furthermore, the list could already have been removed from the map before `add` runs; the update then affects an object still held by reference that is no longer the current mapping.

Choosing a concurrent list can solve access inside the list, but it does not automatically solve the semantics of updating an entry after it has been removed from the map. That is a lifecycle issue.

### 9.4. Does Not Span Multiple Keys

~~~java
balances.compute("A", (key, old) -> old - amount);
balances.compute("B", (key, old) -> old + amount);
~~~

This is an illustrative snippet lacking a transaction protocol, not a complete money-transfer solution. It assumes both values already exist and `amount` is valid solely to show the boundary: there are two calls, so a reader can observe the state between the two calls, or one call can fail after the other.

A broader mechanism is required if a rule must simultaneously preserve the sum or an invariant across both A and B: a shared lock obeyed by all parties, a single combined value holding both states, or a transaction where the data is owned. Do not try to turn single-key guarantees into multi-key guarantees by placing two calls next to each other.

### 9.5. Does Not Cover External Systems

Saving `DONE` in the map and sending a notification are two separate effects. A process can stop between them. Atomic map computation functions do not create transactions with files, databases, or remote servers.

Keep computation functions focused on producing the mapping value. If a requirement involves external side effects, you must define ordering, idempotency, and recovery according to that requirement.

## 10. Designing Computation Functions

### 10.1. Short, Clear, and Without Nested Updates to the Same Map

Avoid performing long I/O, waiting for user input, calling slow services, or waiting on another task that needs to update the map inside a computation function. Some updates may be blocked while computation is running; waiting on a reverse dependency can deadlock the protocol.

Do not make nested `put`, `compute`, or `merge` calls to modify the same map from inside a computation function. On `ConcurrentHashMap`, the computation function contract forbids modifying the map during computation; some recursive updates that cannot complete may be detected with an `IllegalStateException`. Do not rely on catching exceptions to make an invalid nested design valid.

If computation must happen outside because the work is expensive, you may need to accept multiple candidates and use conditional operations to pick one, or design a separate task-management mechanism. That is a trade-off to state explicitly; there is no automatic way to eliminate all duplicate computation while allowing all work to run non-blocking.

### 10.2. Avoid Mutating the Old Value Directly

The following illustrative example uses fully qualified types and creates a new copy inside the computation function:

~~~java
java.util.concurrent.ConcurrentHashMap<String, java.util.List<String>> groups =
        new java.util.concurrent.ConcurrentHashMap<>();

groups.compute("team", (key, old) -> {
    java.util.List<String> next =
            old == null ? new java.util.ArrayList<>()
                        : new java.util.ArrayList<>(old);
    next.add("Linh");
    return java.util.List.copyOf(next);
});
~~~

The published list in this model is not modified afterward; each update creates and publishes a new list. The elements are strings, so there is no need to handle inner element mutability in this example. `List.copyOf` does not accept `null` elements.

This approach has a copying cost. It is useful when you need clear snapshot semantics and the update volume is appropriate, not as advice to copy every collection under every workload.

### 10.3. Do Not Turn Computation Functions into Places with Non-Idempotent Side Effects

Even when using `ConcurrentHashMap` with strong guarantees for a single `compute` call, multiple separate calls can still execute the same business intent. Caller-level retries, network errors, or removing and recreating a key can repeat that intent.

A function that only computes a new value is usually much easier to test than one that updates the map, sends an email, and mutates an external list all at once. If those effects are needed, design them as separate components with their own contracts.

## 11. Map, ConcurrentMap, and Implementation Classes

### 11.1. Having the Same API Name Does Not Mean Having the Same Guarantees

The `compute`/`merge` methods also exist on `Map`. `Map`'s default implementations do not promise synchronization or atomicity properties for all maps. Calling those method names on `HashMap` does not automatically make it thread-safe. [Java 17: Map.compute and Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#compute(K,java.util.function.BiFunction))

The declared type is part of describing requirements, while actual behavior is determined by the runtime object and its implementation class contract. A `Map`-typed variable pointing to a `ConcurrentHashMap` still invokes that object's methods.

### 11.2. ConcurrentMap May Coordinate via Retries

Some default methods on `ConcurrentMap` coordinate computation using conditional operations such as `putIfAbsent`, `replace`, and `remove`. Under contention, those steps and the computation function may run multiple times. Therefore, do not attribute `ConcurrentHashMap`'s computation-function guarantees to every `ConcurrentMap` implementation. [Java 17: ConcurrentMap.compute and merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#merge(K,V,java.util.function.BiFunction))

These are two distinct kinds of guarantees to separate:

- The mapping update result is accepted via conditional operations.
- The entire execution of the computation function is coordinated as a single atomic computation, and how many times the function can run.

A function with no side effects that computes its result solely from its inputs is much easier to use correctly under retries.

### 11.3. Another Example: ConcurrentSkipListMap

`ConcurrentSkipListMap` provides a concurrent map with key ordering. Its contract explicitly states that `computeIfAbsent` is not guaranteed to be applied only once atomically when absent; other computation methods carry corresponding notes. [Java 17: ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function))

Therefore, a test counting loader invocations on `ConcurrentHashMap` is not proof that the count stays the same after switching to another concurrent map.

### 11.4. Null Policy Must Also Be Read per Class

The examples in this lesson use `ConcurrentHashMap`, where `null` means absent in the stated positions. `ConcurrentMap` in general includes notes for implementations that support `null` values; default methods that assume "`get` returning `null` means absent" must be overridden when that assumption does not hold.

When switching map classes, do not just check that the method names still compile; check the null policy, function invocation conditions, retry behavior, and atomicity guarantees.

## 12. Relation to LongAdder Counters

A common statistics pattern is using a `ConcurrentHashMap` holding `LongAdder` instances, finding or creating the adder before incrementing. `LongAdder` is designed to support high-contention counter updates; `sum` is not an atomic snapshot while updates are still in progress. [Java 17: LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)

This pattern has two layers of contracts:

1. The map coordinates finding or creating the adder object.
2. The adder coordinates increments on that object itself.

This differs from `merge` replacing `Integer` values in a mapping. If the application allows removing and replacing adders, a thread that obtained an old reference might increment an adder that is no longer in the map. Accurate counting across lifecycles requires designing corresponding removal/replacement rules.

Do not choose between the two models based solely on line count. Consider contention levels, sum-reading requirements, key lifecycles, and value creation/replacement costs.

## 13. Verifying Conditions Instead of Only Checking for No Errors

A good test states its requirements clearly:

- For counters without removals, after all increments complete, the total equals the number of requested updates.
- For loader functions, invocation counts are verified under specific conditions regarding map type, errors, removals, and `null` results.
- For non-commutative combiners, the required ordering is modeled rather than guessed from thread scheduling.
- For functions that throw exceptions, distinguish whether the mapping was replaced and whether the old object was mutated beforehand.
- For multiple keys, verify multi-key invariants directly instead of assuming individual calls are sufficient.

The barriers in the program force the lost-update schedule, and the counters are printed after threads finish. Do not rely on a natural run happening to hit or miss contention by chance.

Do not place a barrier waiting for two threads to enter **inside** two `compute` functions on the same key to test atomicity: one call may block the other from entering, causing the test itself to deadlock. Controlling the start point from outside, as in the program above, avoids that false assumption.

## 14. Self-Check Exercises

### Exercise 1 — Both Create When Absent

Why can two threads calling `putIfAbsent(k, expensiveLoad())` both load data, even though only one value is inserted?

**Answer:** The argument is evaluated before the call. Atomicity protects checking/inserting the mapping, not constructing the candidate outside.

### Exercise 2 — null Is Not a Cached Value

A `computeIfAbsent` function always returns `null`. After ten sequential calls, can you assert that the function only ran the first time because the key was already checked?

**Answer:** No. No mapping was created, so each subsequent call can invoke the function again. If you need to remember a not-found result, use an explicit value model.

### Exercise 3 — Keep or Remove

A key already has data. Inside `compute`, the author returns `null` when they do not want to change the data. What does the code actually do on `ConcurrentHashMap`?

**Answer:** It removes the mapping. To keep the old value, return the old value; to represent a rejected update to the caller, design appropriate result information.

### Exercise 4 — merge Function Did Not Run

`merge(k, rawText, normalizer)` is used with the expectation that `normalizer` always normalizes data. Why might the first value remain unnormalized?

**Answer:** When the key is absent, `rawText` is stored directly and the combiner does not run. Normalize before passing it in or choose an operation that handles the absent branch as well.

### Exercise 5 — null in Two Positions

Compare `merge(k, null, combiner)` with a `combiner` returning `null` when the key is present.

**Answer:** The incoming data argument to `merge` must be non-`null`. A `null` result from the combiner, on the other hand, is a request to remove the existing mapping.

### Exercise 6 — Function Throws After Mutating a List

A `compute` function adds an element to the old list and then throws an exception. The map still points to that list. Can you expect the added element to be rolled back automatically?

**Answer:** No. The mapping not being replaced does not mean an already-mutated object is restored. Avoid in-place mutation when clear update semantics are needed; create a new value or use an appropriate protocol.

### Exercise 7 — Two Adjacent Keys

Two `compute` calls update two keys A and B. If both methods are per-key atomic, is it guaranteed that a reader cannot observe the state between the two updates?

**Answer:** No. They are two separate operations. A shared invariant between A and B requires a broader mechanism or a combined-state model.

### Exercise 8 — Switching Map Types

A test on `ConcurrentHashMap` shows two threads fetching data concurrently while the `computeIfAbsent` function runs only once. Can that count be used as a general contract for all `ConcurrentMap` implementations?

**Answer:** No. You must check the specific class contract; implementations that use retries or have different computation-function rules do not automatically carry that guarantee.

Choosing `putIfAbsent`, `compute`, or `merge` starts from the absent/present condition and the meaning of the new data. Then determine the exact scope of atomicity: which mapping is protected, what the computation function may do, and what work still requires its own protocol.
