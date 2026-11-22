# Distinguishing Per-Operation Safety from Compound-Sequence Safety

## 1. The Problem to Understand Before Choosing a Collection

Suppose a hit counter is stored in a map. Each request reads the current number, adds one, and writes it back. You replace `HashMap` with `ConcurrentHashMap`, yet the final total is still lower than the number of requests processed. This can happen even though every individual `get` and `put` call is executed strictly according to the map's contract.

The key point is that **the operation boundary protected by the collection can be smaller than the unit of work the program needs to protect**. "Increment the counter once" is one unit of work; "read a value" and "write a value" are two separate calls. Another thread can run in between them.

This lesson focuses on identifying and closing that gap in Java Collections. After studying it, you should be able to do four things:

- State the condition that must always hold when multiple threads work together.
- Write an interleaving schedule that breaks an existing sequence of operations.
- Choose a built-in compound method or a shared lock that covers the right unit of work.
- Inspect the read path, the write path, and the element objects—rather than looking only at the collection class name.

The background knowledge required is `Map`, `List`, `Queue`, object references, lambdas, and how to read a `synchronized` block. The programs use syntax and APIs compatible with Java 17 or later. You do not need to know how the JVM implements hash tables or machine code to follow the reasoning.

### 1.1. Related Concepts

| Concept | Question It Answers | Example in This Lesson |
| --- | --- | --- |
| Thread safety | Does the object uphold its contract when multiple threads use it in the specified way? | Two threads concurrently calling `ConcurrentHashMap.put` |
| Atomicity | Is a unit of work observed as a single, uninterrupted step within the promised scope? | Combining "read old count then add one" with `merge` |
| Visibility | Does the reading thread have the required synchronization relationship to see published data? | Reading a result after task completion via `Future.get` |
| Invariant | What must remain true in every state that callers are allowed to observe? | The total number of slots across two compartments always equals 20 |
| Compound action | Which unit of work consists of multiple interdependent steps? | Checking absence then adding, or reading two keys then summing |
| Synchronization protocol | What coordination rules must all parties follow? | Every move and every total read acquires the same lock |

Atomicity always requires a specific scope: a single update, a single key, a single collection, or multiple objects together. Never use the word "atomic" without stating that scope.

A thread-safe collection does not automatically know your program's business rules. It does not know that two keys `left` and `right` must keep a sum of 20, nor does it know that a name may only be registered once if you manually combine `contains` with `add`.

## 2. Why Do Multiple Safe Operations Still Form a Broken Sequence?

### 2.1. Read–Modify–Write Can Lose Updates

The following snippet is **illustrative code that is intentionally broken when multiple threads increment concurrently**, not a standalone program:

```java
int before = counts.get("hits");
counts.put("hits", before + 1);
```

Suppose `counts` is a `ConcurrentHashMap<String, Integer>` that already contains `"hits" -> 0`. Two threads can execute:

| Step | Thread A | Thread B | Value in Map |
| --- | --- | --- | --- |
| 1 | Reads 0 | Has not read yet | 0 |
| 2 | Holds 0 in a local variable | Reads 0 | 0 |
| 3 | Computes 0 + 1, writes 1 | Holds 0 in a local variable | 1 |
| 4 | Done | Computes 0 + 1, writes 1 | 1 |

Two increments completed, yet the result is only 1. The map did not fail a single `put`: both threads explicitly asked it to write 1. The flaw lies in how the program derived two new values from the same old value.

This is a **lost update**. Writing it compactly as `counts.put("hits", counts.get("hits") + 1)` only reduces the line count; it does not merge the two calls into a single atomic operation. The same read–compute–write idea also explains why `x++` does not automatically become atomic. [Oracle: Thread Interference](https://docs.oracle.com/javase/tutorial/essential/concurrency/interfere.html)

### 2.2. Check-Then-Act Relies on a Stale Observation

Another example is **check-then-act**. The illustrative snippet below also intentionally leaves a race window exposed:

```java
if (!registrations.containsKey("seat-7")) {
    registrations.put("seat-7", "Lan");
}
```

Thread A sees the seat is free. Before A writes, Thread B registers that seat for `"Minh"`. Then A writes `"Lan"` and overwrites B's registration. If the rule is "only the first person gets registered," this implementation is wrong.

There are not two `"seat-7"` keys in the map; the map still upholds its rule of at most one mapping per key. **No duplicate keys in the map** and **not overwriting an existing registrant** are two different conditions. A `put` call can always replace the value at an existing key.

A return value from `isEmpty`, `containsKey`, `size`, or `get` is an observation. To use it to decide a subsequent mutation, you must prove that the condition remains protected until the mutation takes place.

### 2.3. A Race Condition Is Not the Same as a Data Race

In this lesson, a **race condition** means correctness depends on how steps from multiple threads interleave. Two threads using nothing but thread-safe APIs on `ConcurrentHashMap` can still produce this kind of bug.

A **data race** under the Java Memory Model has a narrower meaning: two conflicting accesses not ordered by a happens-before relationship. Do not infer "no data race on the map structure" to mean "the registration workflow is definitely correct."

According to the JLS, unlocking a monitor establishes a happens-before relationship with a subsequent lock on that same monitor. This rule serves ordering coordination and data visibility; the program must still place all steps that need protection inside the lock's scope. [JLS 17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

### 2.4. `final` and `volatile` Do Not Automatically Protect Compound Sequences

`final Map<...>` prevents reassigning the reference variable after initialization according to `final` rules; it does not make the map immutable. A `volatile` reference variable helps coordinate publishing or replacing the reference, but it does not turn `get` followed by `put`, or `contains` followed by `add`, into a single operation.

Similarly, a counter declared as `volatile int` still needs an appropriate mechanism if multiple threads increment it with `++`. Visibility of individual accesses does not replace combining the entire read–modify–write sequence. [Oracle: Atomic Access](https://docs.oracle.com/javase/tutorial/essential/concurrency/atomic.html)

Therefore, when analyzing a bug, ask two separate questions: "by what mechanism is the data published/read?" and "by what mechanism are interdependent steps combined?" Answering the first question is not enough to answer the second.

## 3. Experiment: The Same Bug with a Concurrent Map and a Synchronized Map

The following complete program forces two threads to **both read 0 before either thread writes**. `CyclicBarrier` serves as the rendezvous point for the two tasks. It does not use `Thread.sleep` and does not rely on running many times to catch a bug by chance.

The program tests four cases:

1. `ConcurrentHashMap` with separate `get`/`put`.
2. `Collections.synchronizedMap` with separate `get`/`put`.
3. `ConcurrentHashMap.merge` to combine per-key increments.
4. A `synchronized` block wrapping the entire read–modify–write on a synchronized map.

Save as **`AtomicStepDemo.java`**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AtomicStepDemo {
    private static final int REPETITIONS = 2_000;

    public static void main(String[] args) throws Exception {
        Map<String, Integer> concurrent = new ConcurrentHashMap<>();
        Map<String, Integer> wrapped =
                Collections.synchronizedMap(new HashMap<>());

        System.out.println("concurrent split = " + forceLostUpdate(concurrent));
        System.out.println("wrapped split = " + forceLostUpdate(wrapped));

        ConcurrentHashMap<String, Integer> merged = new ConcurrentHashMap<>();
        runTwice(() -> {
            for (int i = 0; i < REPETITIONS; i++) {
                merged.merge("hits", 1, Integer::sum);
            }
        });
        require(merged.get("hits") == 2 * REPETITIONS, "merge lost an update");
        System.out.println("concurrent merge = " + merged.get("hits"));

        Map<String, Integer> guarded =
                Collections.synchronizedMap(new HashMap<>());
        guarded.put("hits", 0);
        runTwice(() -> {
            for (int i = 0; i < REPETITIONS; i++) {
                synchronized (guarded) {
                    int before = guarded.get("hits");
                    guarded.put("hits", before + 1);
                }
            }
        });
        require(guarded.get("hits") == 2 * REPETITIONS, "guard lost an update");
        System.out.println("wrapped whole block = " + guarded.get("hits"));
    }

    private static int forceLostUpdate(Map<String, Integer> map)
            throws Exception {
        map.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(() -> {
                int before = map.get("hits");
                bothRead.await(5, TimeUnit.SECONDS);
                map.put("hits", before + 1);
                return null;
            });
            Future<?> second = pool.submit(() -> {
                int before = map.get("hits");
                bothRead.await(5, TimeUnit.SECONDS);
                map.put("hits", before + 1);
                return null;
            });
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            int result = map.get("hits");
            require(result == 1, "the forced schedule did not occur");
            return result;
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void runTwice(Runnable action) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(action);
            Future<?> second = pool.submit(action);
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all AtomicStepDemo.java
java AtomicStepDemo
```

Stdout when the program completes normally:

```text
concurrent split = 1
wrapped split = 1
concurrent merge = 4000
wrapped whole block = 4000
```

The first two lines are always 1 under the schedule the program forces: each thread holds a local variable `before = 0`, and then both write `1`. The order of the two writes does not change this outcome.

The last two lines are 4,000 because there are two tasks, each incrementing 2,000 times. In the `merge` case, the update is submitted to the map as a single combined operation. In the external-lock case, the second thread cannot interleave between the read and write of the thread holding the monitor.

`Collections.synchronizedMap` does not hold its monitor from the return of `get` until a later `put`. Two separate calls from user code create two separate protection scopes. Only when an outer block wraps the entire sequence is the gap between them covered.

The rendezvous is placed only in the intentionally broken case. **Do not move a barrier inside a block holding the same lock**: the first task could hold the lock and wait for the second task, while the second task is waiting for that very lock. That test design would create a deadlock instead of demonstrating correctness.

By contract, `CyclicBarrier` lets a group of threads wait for each other at a common point. `Future.get` retrieves a task's result or failure; actions of the task happen-before actions following the corresponding `get`. [CyclicBarrier Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html), [Future Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

The timeouts in the code ensure the test fails fast rather than hanging indefinitely if the environment cannot run the tasks. They are not what creates the interleaving schedule. The `finally` block shuts down the thread pool; wait/compile/run exceptions are not swallowed to print a falsely successful result.

## 4. First Fix: Use an Appropriate Compound Operation

### 4.1. Choose an API That Expresses the Exact Condition to Protect

With `ConcurrentMap`, several conditional operations are designed to execute atomically. Do not rebuild them from multiple `get`, `containsKey`, `put`, or `remove` calls:

| Intent | Hand-Rolled Sequence with a Gap | API to Consider |
| --- | --- | --- |
| Register only if the key is absent | `containsKey` then `put` | `putIfAbsent(key, value)` |
| Remove only if the value is still the known one | `get` then compare then `remove(key)` | `remove(key, expectedValue)` |
| Replace only if the value has not changed | `get` then compare then `put` | `replace(key, expectedValue, newValue)` |

The return value tells you the outcome of the conditional operation. The snippet below is **illustrative code**, assuming `registrations` is a shared `ConcurrentHashMap<String, String>`:

```java
String previous = registrations.putIfAbsent("seat-7", "Lan");
if (previous == null) {
    System.out.println("Dang ky thanh cong");
} else {
    System.out.println("Cho da duoc dang ky");
}
```

In this example, `null` indicates there was no previous value, because the map implementation in use does not allow null values. A key can still be removed and re-registered later if the application allows it; the success of this call is not a guarantee that "this seat belongs to Lan forever."

These conditional variants are specified in the `ConcurrentMap` contract. Use the return value of that operation itself to choose the next branch. [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

### 4.2. Update Based on the Current Value with `compute` or `merge`

With `ConcurrentHashMap`, incrementing a per-key counter can be expressed using either of the following two illustrative snippets:

```java
counts.merge("hits", 1, Integer::sum);

counts.compute("hits", (key, oldValue) ->
        oldValue == null ? 1 : oldValue + 1);
```

These are **two alternatives**, not two lines to run for a single hit; running both would increment twice. In this snippet, `counts` is a `ConcurrentHashMap<String, Integer>`.

`merge` uses the value 1 when there is no mapping; when one exists, it combines the old number with 1. `compute` handles both the absent and present cases. `computeIfAbsent` is suited for creating a missing mapping, not for incrementing on every hit.

On `ConcurrentHashMap`, calls to `compute`/`computeIfAbsent`/`merge` carry an atomicity guarantee for updating the mapping in question. Returning `null` from the function may avoid creating or remove the mapping depending on the method. The mapping function should be short and must not modify the map being computed; some other updates may have to wait. [ConcurrentHashMap — compute and merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#compute(K,java.util.function.BiFunction))

This fix still requires every code path that increments the counter to follow a compatible rule. If another path still runs `get` followed by `put` with an old number, it can still overwrite the result of a `merge`. Changing one call site does not automatically fix other call sites.

### 4.3. The Declared Type `Map` Does Not Carry the Guarantees of Every Implementation

You must read the contract of the actual runtime class:

```java
Map<String, Integer> a = new HashMap<>();
Map<String, Integer> b = new ConcurrentHashMap<>();
```

These are **two illustrative declarations**, requiring the corresponding imports. Both can call `merge`, but sharing a method name does not prove the same synchronization guarantees. Many default methods on `Map`, including compute/update methods, do not promise synchronization or atomicity; each implementation class must specify its own behavior. [Map Java 17 — default methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction))

Declaring `b` as `Map` does not strip away `ConcurrentHashMap`'s implementation: Java still dispatches to the overridden method of the actual object. However, if a component's contract only says "accepts any `Map`," callers have no default basis to assume every passed-in object is safe to share across threads.

When designing an API, state clearly whether you require a `ConcurrentMap`, a specific object with known guarantees, or a map accessed only under a private lock. Both the parameter type and the contract documentation should make this requirement clear to callers.

### 4.4. Update Atomicity Does Not Mean Side Effects Run Exactly Once

A mapping function should only build or transform a result locally and return it. Do not infer from "the mapping is updated atomically" to "sending a notification, charging an external account, or calling a remote service happens exactly once."

The default `compute`/`merge` methods on `ConcurrentMap` may retry and invoke the remapping function multiple times under contention. Specifically, `ConcurrentHashMap.computeIfAbsent` invokes the function once per method call if the key is absent, and does not invoke it if the key already has a value; that is still not a guarantee that the function runs only once over the key's entire lifetime. [ConcurrentMap — merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#merge(K,V,java.util.function.BiFunction)), [ConcurrentHashMap — computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

For example, the mapping function might return null, throw an exception, or the mapping might be removed so a later call recreates it. If you perform a side effect before the function fails, rolling back or skipping the map change does not automatically undo that side effect.

Also do not call `compute` on another map while arbitrarily holding locks or waiting on other tasks. Task A holding resource X and waiting for Y while Task B holds Y and waits for X can create a wait cycle. Putting long-running work inside a mapping function also holds the coordinated region longer. Lazy loading of data needs a dedicated task-lifecycle design if application requirements demand it—it cannot be solved merely by switching map method names.

## 5. Second Fix: Hold a Single Lock for the Entire Sequence

### 5.1. With a Synchronized Wrapper, Lock on the Returned Wrapper Object

Suppose a list is created and safely published with:

```java
List<String> names =
        Collections.synchronizedList(new ArrayList<>());
```

To enforce the rule "add if not already present," the illustrative snippet below holds the monitor of `names` itself for both steps:

```java
synchronized (names) {
    if (!names.contains("Lan")) {
        names.add("Lan");
    }
}
```

The condition is that all callers must access the list through that wrapper and follow the same protocol for compound operations. A thread calling `add` directly can still add a duplicate after this block finishes; the lock does not turn a `List` into a `Set` and does not forbid an operation that the program still permits.

Similarly, if the backing list is retained elsewhere and mutated directly, the wrapper cannot force that access path to wait on its monitor.

For synchronized wrappers, the documentation requires all access to the backing structure to go through the returned object. When traversing via iterator, spliterator, or stream, the caller must manually hold the appropriate lock. For views of a synchronized map, lock on the returned map itself, not separately on `keySet` or `entrySet`. [Collections — synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

### 5.2. Locking Small Pieces Separately Still Leaves the Decision Gap Exposed

The following **illustrative snippet with an intentionally wrong lock scope** still has a gap:

```java
int before;
synchronized (counts) {
    before = counts.get("hits");
}

synchronized (counts) {
    counts.put("hits", before + 1);
}
```

Between the two blocks, another thread can update the value. The local variable `before` does not automatically update to match the map. Both the decision and the update must be enclosed in the same lock acquisition.

Locking also requires the **same object identity**, not just the same variable name or equal contents:

- Two distinct `new Object()` instances are two different locks.
- Locking the backing map is not the same as locking the synchronized wrapper.
- Creating a new wrapper around the same map on every call does not produce a shared lock.
- Locking `this` on two different service instances does not provide mutual exclusion between them.

Monitor reentrancy allows a thread that already holds a monitor to call another method that also uses that monitor. It does not turn two different monitors into a single shared lock. [JLS 17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)

### 5.3. An External Lock Around a Concurrent Collection Only Works When All Parties Cooperate

You can establish a convention using `synchronized (guard)` around a `ConcurrentHashMap`. However, other threads that simply call `map.put` without acquiring `guard` will not automatically wait for that external lock.

In particular, `synchronized (concurrentMap)` is not a command telling that class to pause all internal updates. `ConcurrentHashMap` does not provide a whole-table lock that blocks all accesses in this way. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

If you already have a shared lock covering every operation and every access path, a private `HashMap` can satisfy that design. In that case, safety comes from the enclosing class and the locking protocol. You must prevent the map from escaping so callers cannot accidentally create a bypass path.

When multiple objects need separate locks, lock acquisition order must be consistent to avoid wait cycles. For a small problem, a single shared lock is usually easier to reason about; split locks only after clearly defining the invariants and how every access path coordinates.

## 6. Single-Key Atomicity Does Not Protect Invariants Across Multiple Keys

### 6.1. Two `compute` Calls Are Still Two Separate Updates

Suppose two compartments store slot counts `left` and `right`. Initially each compartment has 10 slots; the operation "move one slot from left to right" must preserve the invariant:

```text
left + right = 20
```

You can write two `compute` calls that are safe per key, yet still expose an intermediate state:

```java
slots.compute("left", (key, value) -> value - 1);
slots.compute("right", (key, value) -> value + 1);
```

This snippet is **illustrative code that intentionally fails to protect a multi-key invariant**, with `slots` being a `ConcurrentHashMap<String, Integer>` that already has both keys.

After the first line, the state is `left = 9, right = 10`. After the second line, the state is `left = 9, right = 11`. Both per-key computations are correct, yet a reader between the two lines can observe a total of 19.

Reading the total is also a sequence: `get("left")` followed by `get("right")`. Even when the two updates are placed next to each other with no intentional pause in between, an uncoordinated compound read can still mix observations from two different phases.

What the application needs to protect is **the move and the snapshot of the two related numbers**, not just individual writes. Atomicity on one key does not automatically extend to a second key.

### 6.2. Experiment: Observing an Intermediate State and a Shared-Lock Wrapper

The following program has two halves:

- The first half uses a concurrent map and two latches so the reader is guaranteed to run between the two updates.
- The second half keeps a private map inside `SlotStore`. Both `move` and `snapshot` hold the same `guard`, and `snapshot` returns only a record containing two integers.

Save as **`CollectionInvariantDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CollectionInvariantDemo {
    private static final int CHECKS = 1_000;

    public static void main(String[] args) throws Exception {
        showIntermediateState();
        showGuardedState();
    }

    private static void showIntermediateState() throws Exception {
        ConcurrentHashMap<String, Integer> slots = new ConcurrentHashMap<>();
        slots.put("left", 10);
        slots.put("right", 10);
        CountDownLatch firstWrite = new CountDownLatch(1);
        CountDownLatch readFinished = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> writer = pool.submit(() -> {
                slots.compute("left", (key, value) -> value - 1);
                firstWrite.countDown();
                await(readFinished);
                slots.compute("right", (key, value) -> value + 1);
                return null;
            });
            Future<Integer> reader = pool.submit(() -> {
                await(firstWrite);
                try {
                    return slots.get("left") + slots.get("right");
                } finally {
                    readFinished.countDown();
                }
            });
            int observed = reader.get(10, TimeUnit.SECONDS);
            writer.get(10, TimeUnit.SECONDS);
            require(observed == 19, "intermediate state was not observed");
            System.out.println("separate compute, observed total = " + observed);
            System.out.println("separate compute, final total = "
                    + (slots.get("left") + slots.get("right")));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void showGuardedState() throws Exception {
        SlotStore slots = new SlotStore();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> writer = pool.submit(() -> {
                await(start);
                for (int i = 0; i < CHECKS; i++) {
                    slots.move("left", "right");
                    slots.move("right", "left");
                }
                return null;
            });
            Future<Integer> reader = pool.submit(() -> {
                await(start);
                for (int i = 0; i < CHECKS; i++) {
                    Snapshot snapshot = slots.snapshot();
                    require(snapshot.total() == 20, "broken invariant");
                }
                return CHECKS;
            });
            start.countDown();
            int checks = reader.get(10, TimeUnit.SECONDS);
            writer.get(10, TimeUnit.SECONDS);
            Snapshot last = slots.snapshot();
            require(last.left() == 10 && last.right() == 10, "wrong final state");
            System.out.println("guarded snapshots checked = " + checks);
            System.out.println("guarded final = " + last);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static final class SlotStore {
        private final Object guard = new Object();
        private final Map<String, Integer> values = new HashMap<>();

        private SlotStore() {
            values.put("left", 10);
            values.put("right", 10);
        }

        private void move(String from, String to) {
            if (from.equals(to)) {
                throw new IllegalArgumentException("distinct slots required");
            }
            synchronized (guard) {
                Integer source = values.get(from);
                Integer target = values.get(to);
                if (source == null || target == null || source <= 0) {
                    throw new IllegalStateException("invalid move");
                }
                values.put(from, source - 1);
                values.put(to, target + 1);
            }
        }

        private Snapshot snapshot() {
            synchronized (guard) {
                return new Snapshot(values.get("left"), values.get("right"));
            }
        }
    }

    private record Snapshot(int left, int right) {
        private int total() {
            return left + right;
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
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
javac --release 17 -encoding UTF-8 -Xlint:all CollectionInvariantDemo.java
java CollectionInvariantDemo
```

Stdout on a successful run:

```text
separate compute, observed total = 19
separate compute, final total = 20
guarded snapshots checked = 1000
guarded final = Snapshot[left=10, right=10]
```

In the first half, `firstWrite` opens after decrementing the left compartment. The writer waits on `readFinished`, so it does not increment the right compartment before the reader sums both. The result 19 is produced deterministically by explicit coordination, not by machine speed.

In the second half, the writer moves a slot to the right and back 1,000 times. The reader checks 1,000 snapshots. Each snapshot may see `10/10` or `9/11`, but the total is always 20. The final `10/10` result is read after the writer completes.

The read path also acquires `guard`, so it cannot enter between the two `put` calls of a move. If `snapshot` dropped the lock, this reasoning would break down even though `move` is still `synchronized`.

The `Snapshot` record holds two `int` values; it does not return the internal map or a live `Map.Entry`. After exiting the lock, the reader computes solely on its own snapshot; subsequent writes cannot mutate the two components of this record.

`CountDownLatch` provides a single-use gate and data publication semantics via `countDown`/`await` according to its contract. In the experiment, latches control ordering, while `guard` is the mechanism protecting the wrapper's invariant. [CountDownLatch Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

### 6.3. What Actually Proves the Fix?

The experiment is a runnable demonstration, while the real proof lies in the class structure:

1. `values` is private and never returned.
2. Every post-construction method that reads or modifies state holds the same `guard`.
3. Checking that the source has available slots and both writes occur within the same block.
4. Readers capture both numbers under the same lock and return independent data.
5. Both tasks receive the object only after it has been constructed, via executor task submission.

From this, each move can be treated as a transition between two valid states for all parties following the protocol. A reader only sees the state before or after a move.

In this example, slot names are fixed in advance, counts are small, and arithmetic cannot overflow `int`. If you generalize this into a broader API, you must also define value bounds, overflow checks, rules for adding/removing slots, and error handling before mutating state. Holding a lock does not automatically roll back changes if you mutate half the state and then throw an exception.

### 6.4. Sometimes You Should Change How State Is Represented

If multiple pieces of data must always change together, you can group them into **a single immutable value** and replace that entire value in one appropriately guaranteed operation. For example, store a record holding both counts under a lock, or use an `AtomicReference` pointing to an immutable state.

`AtomicReference` supports atomic updates of a single reference. That can fit well when the business boundary coincides with the entire value the reference points to. [AtomicReference Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)

This is a design option, not advice to cram all program data into one giant object. You must weigh copy size, update frequency, and contention level. If a record still holds an externally mutable list, merely lacking setters on the record does not make the whole object graph immutable.

For the problem in this program, a shared lock and private data are already simple enough to prove. There is no reason to introduce a multi-lock protocol or complex retry algorithms.

## 7. A Thread-Safe Map Does Not Automatically Make Its Value Objects Thread-Safe

### 7.1. `computeIfAbsent` Only Combines Creating or Retrieving the Mapping

The following illustrative snippet is very easy to over-interpret:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
groups.computeIfAbsent("team-a", key -> new ArrayList<>()).add("Lan");
```

This is an **illustrative snippet that has a bug when multiple threads modify the list concurrently**, requiring the corresponding imports. Two consecutive units of work happen here:

1. Create or retrieve the list reference in the map.
2. Call `add` on the returned list.

The `add` call happens on an `ArrayList` after the map method has already returned. Threads that receive that same list do not automatically have a protocol protecting the list's structure. `ArrayList` requires external synchronization when accessed by multiple threads and at least one thread modifies it structurally. [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Draw the object boundaries to see this clearly:

```text
ConcurrentHashMap
    "team-a" -> reference -> shared ArrayList

Protecting the mapping does not automatically protect every change inside the ArrayList.
```

Swapping the outer map does not fix the contract of the inner object. Conversely, wrapping the inner list only protects the operations that the list wrapper guards; another sequence like `size`/`get`/`remove` still needs review.

### 7.2. One Solution: Replace Immutable Values per Key

If the requirement is "add a member and every reader receives an unmodifiable list of a single version," the illustrative snippet below moves building the new version inside `compute`:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();

groups.compute("team-a", (key, oldMembers) -> {
    List<String> next = oldMembers == null
            ? new ArrayList<>()
            : new ArrayList<>(oldMembers);
    next.add("Lan");
    return List.copyOf(next);
});
```

This is a **non-standalone illustrative snippet**. The critical assumptions are that every value already in the map also obeys the unmodifiable policy, members are non-null `String`s, and every addition path uses a compatible protocol.

`next` is a new list used only locally during the computation. `oldMembers` is not mutated, so a thread already holding an older version can continue reading that version under the stated contract. A reader obtaining a list reference gets a snapshot version, not a lock preventing a newer version from replacing it in the map. `List.copyOf` creates an unmodifiable list and rejects null elements. [List.copyOf Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

The cost is copying the list on every change. If elements are mutable objects, copying the list only copies references; you need separate rules for element state.

Another option is for the value itself to have its own synchronization mechanism, such as an appropriate concurrent collection. Even so, when requirements span both the mapping and the value's lifecycle, you still must account for removals or replacements in the map.

### 7.3. `AtomicInteger` Values Also Have Lifecycle Boundaries

For counters, you might use this illustrative snippet:

```java
ConcurrentHashMap<String, AtomicInteger> counters = new ConcurrentHashMap<>();
AtomicInteger counter =
        counters.computeIfAbsent("hits", key -> new AtomicInteger());
counter.incrementAndGet();
```

`AtomicInteger.incrementAndGet` combines the increment on the counter object itself. [AtomicInteger Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html#incrementAndGet())

However, another thread could remove the `"hits"` mapping after the first thread retrieves `counter` and before it increments. In that case, the count still increments properly on the retrieved object, but that object may no longer be the current value in the map.

Therefore, this approach can work if counter mappings are kept stable and requirements allow counting under that lifecycle. If the rule is "every increment must update the exact value currently registered at the key, coordinated with removals/resets," you need to redesign the protocol; merely combining two thread-safe objects does not prove the whole operation.

`LongAdder` or an inner concurrent collection does not eliminate this lifecycle issue either. The first step is defining the semantics of remove, reset, version replacement, and in-flight operations.

## 8. Safe Iteration and Reading a Consistent Snapshot Are Different Requirements

### 8.1. Iterating Over a Synchronized Wrapper Must Hold the Lock for the Entire Traversal

The illustrative snippet below shows how to take a copy of a synchronized map:

```java
Map<String, Integer> shared =
        Collections.synchronizedMap(new HashMap<>());

Map<String, Integer> snapshot;
synchronized (shared) {
    snapshot = new HashMap<>(shared);
}
```

This is an **illustrative snippet**, assuming all accesses to the backing map go through the same wrapper. Copying happens inside the lock block, so mutations through the wrapper on other threads must wait. Afterward, `snapshot` can be iterated outside the lock if the copy is used only by the current thread or published through an appropriate protocol.

To iterate directly over a view, hold the map's lock for **both** creating and using the iterator:

```java
synchronized (shared) {
    for (Map.Entry<String, Integer> entry : shared.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

This snippet only illustrates lock scope; it does not promise `HashMap` iteration order. For views from synchronized sorted/navigable wrappers, follow the locking rules for the root wrapper as documented. Do not switch the lock to the view object just because the loop iterates over that view. [Collections Java 17 — iteration rules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Holding the lock while printing, calling external functions, or doing slow work can lengthen wait times for other threads. When requirements allow, taking the needed snapshot under the lock and processing it outside usually keeps lock hold times easier to control.

A copy of the map is still only independent in its mappings and container structure. In this example, `String` and `Integer` are immutable, so no element can be mutated externally to alter the captured numbers. With other value types, you must consider snapshot depth.

### 8.2. Concurrent Traversal Is Not a Point-in-Time Snapshot by Default

Iterators of many concurrent collections are specified as weakly consistent: they can traverse while the structure is changing without providing whole-collection immutable snapshot semantics. [java.util.concurrent — Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

Thus, creating a new map via `new HashMap<>(concurrentMap)` does not prove the source data was a global point-in-time snapshot. The destination map may remain stable afterward, but stability of the destination and point-in-time consistency of the source read are two different questions.

Also do not use `size() == 0` or `isEmpty()` as a reservation for a subsequent operation. In `ConcurrentHashMap`, aggregate status methods during concurrent updates only reflect transient states; `putAll` and `clear` do not provide a whole-map transaction for concurrent readers. [ConcurrentHashMap Java 17 — aggregate status](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

If the application requires reconciling all data from a single consistent version, define an explicit mechanism: a shared lock for both writes and snapshots, versioned immutable state, or a storage design with appropriate transaction boundaries.

### 8.3. Snapshot Iterators Do Not Combine Separate Calls Either

`CopyOnWriteArrayList` has an iterator that sees the array version as of when the iterator was created. However, `contains("Lan")` followed by `add("Lan")` are still two separate calls; a snapshot iterator does not turn that sequence into a conditional add.

This class provides `addIfAbsent` to express adding if not already present. Nor does a structural snapshot deep-copy the state of element objects. [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#addIfAbsent(E))

Similarly, calling `get(0)` after `isEmpty()` on a list can be two observations from different points in time; per-method safety does not keep an index valid until the next call.

The absence of `ConcurrentModificationException` also does not prove a workflow is correct. Conversely, do not use that exception as a synchronization mechanism or as proof that every race bug will definitely be caught. Each collection's iterator has its own contract; fail-fast behavior is best-effort bug detection, not a protocol for preserving invariants. [HashMap Java 17 — fail-fast iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 9. Queue: Act on the Result of the Dequeue Operation, Not a Stale Observation

### 9.1. `isEmpty` Does Not Reserve an Element for the Caller That Checked It

The illustrative snippet below intentionally exposes a bug when two callers take jobs from a queue:

```java
if (!jobs.isEmpty()) {
    String job = jobs.remove();
}
```

With `ConcurrentLinkedQueue`, Thread A can see that the queue has a job; Thread B takes the last element; then Thread A calls `remove` on an empty queue. `remove` throws `NoSuchElementException` when empty, whereas `poll` returns null. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

A non-blocking dequeue should rely on **the result of `poll` itself**. The illustrative snippet below omits the job-processing logic:

```java
String job = jobs.poll();
if (job != null) {
    System.out.println("Da nhan: " + job);
} else {
    System.out.println("Hien chua co viec");
}
```

Assume `jobs` is a `ConcurrentLinkedQueue<String>`. This queue type forbids null elements, so null unambiguously means the dequeue attempt received no element. Its `size` method also requires traversal and is not suitable as a reservation check under concurrent modification. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)

When two threads both `poll` a single element, one claims the job and the other receives null. That can be a completely valid outcome of a non-blocking work-stealing protocol. No prior `isEmpty` check is needed.

However, null only tells you **that specific dequeue attempt** found no element. It does not prove the producer is finished or that no new jobs will arrive. Shutting down a group of consumer tasks requires a separate termination protocol.

### 9.2. If You Need to Wait, Use a True Blocking Operation

With `BlockingQueue`, choose `take()` when you need to wait until an element is available; choose `poll(timeout, unit)` when there is a wait limit. When inserting, `offer` returns a success/failure result; `put` can wait for space. [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Observing `remainingCapacity() > 0` and then calling `add` does not reserve space for the current thread. Another caller can insert first. Decide based on the result of `offer` or an appropriate `put` waiting protocol.

If an API throws `InterruptedException`, propagate the exception to the responsible layer or restore the interrupt flag when translating the error according to your design. Do not catch and ignore it and proceed as if a job was received.

Also do not hold an external lock while calling `take` indefinitely if the producer must acquire that same lock to enqueue work. That design would hold the lock while waiting for a condition it prevents the other party from creating.

Safely dequeuing an element does not mean processing it outside the queue succeeds exactly once. If a thread takes a job and fails before persisting the result, recovery or completion tracking belongs to the job-processing protocol, not `poll`'s guarantee.

## 10. Experiment: Queue and Copy-on-Write List

The complete program below verifies two "check-then-act" patterns:

- Queue: check that an element exists, let another caller drain it, then call `remove`.
- List: both callers confirm the name is absent, then both call `add`.

The correct cases use `poll` and `addIfAbsent`. Which task wins can vary by schedule; stdout prints only aggregate results that do not depend on the winner's identity.

Save as **`CollectionProtocolDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CollectionProtocolDemo {
    public static void main(String[] args) throws Exception {
        showQueueRace();
        showSinglePoll();
        showListRace();
        showAddIfAbsent();
    }

    private static void showQueueRace() throws Exception {
        ConcurrentLinkedQueue<String> jobs = new ConcurrentLinkedQueue<>();
        jobs.add("job-1");
        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch removed = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> {
                boolean wasNonEmpty = !jobs.isEmpty();
                checked.countDown();
                await(removed);
                if (wasNonEmpty) {
                    try {
                        return jobs.remove();
                    } catch (NoSuchElementException ex) {
                        return "NoSuchElementException";
                    }
                }
                return "unexpected empty observation";
            });
            Future<String> second = pool.submit(() -> {
                await(checked);
                try {
                    return jobs.poll();
                } finally {
                    removed.countDown();
                }
            });
            String removedJob = second.get(10, TimeUnit.SECONDS);
            String firstResult = first.get(10, TimeUnit.SECONDS);
            require("job-1".equals(removedJob), "wrong removed job");
            require("NoSuchElementException".equals(firstResult), "race not shown");
            System.out.println("check then remove = " + firstResult);
        } finally {
            stop(pool);
        }
    }

    private static void showSinglePoll() throws Exception {
        ConcurrentLinkedQueue<String> jobs = new ConcurrentLinkedQueue<>();
        jobs.add("job-1");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> jobs.poll());
            Future<String> second = pool.submit(() -> jobs.poll());
            String a = first.get(10, TimeUnit.SECONDS);
            String b = second.get(10, TimeUnit.SECONDS);
            int claimed = (a == null ? 0 : 1) + (b == null ? 0 : 1);
            int empty = (a == null ? 1 : 0) + (b == null ? 1 : 0);
            require(claimed == 1 && empty == 1, "wrong poll outcome");
            require("job-1".equals(a) || "job-1".equals(b), "wrong job");
            System.out.println("poll: claimed = " + claimed + ", empty = " + empty);
        } finally {
            stop(pool);
        }
    }

    private static void showListRace() throws Exception {
        CopyOnWriteArrayList<String> names = new CopyOnWriteArrayList<>();
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(() -> {
                boolean absent = !names.contains("Lan");
                bothChecked.await(5, TimeUnit.SECONDS);
                if (absent) {
                    names.add("Lan");
                }
                return null;
            });
            Future<?> second = pool.submit(() -> {
                boolean absent = !names.contains("Lan");
                bothChecked.await(5, TimeUnit.SECONDS);
                if (absent) {
                    names.add("Lan");
                }
                return null;
            });
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            require(names.size() == 2, "duplicate schedule not shown");
            System.out.println("contains then add = " + names);
        } finally {
            stop(pool);
        }
    }

    private static void showAddIfAbsent() throws Exception {
        CopyOnWriteArrayList<String> names = new CopyOnWriteArrayList<>();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> first = pool.submit(() -> names.addIfAbsent("Lan"));
            Future<Boolean> second = pool.submit(() -> names.addIfAbsent("Lan"));
            boolean a = first.get(10, TimeUnit.SECONDS);
            boolean b = second.get(10, TimeUnit.SECONDS);
            require(a != b && names.size() == 1, "wrong conditional add");
            System.out.println("addIfAbsent = " + names);
        } finally {
            stop(pool);
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void stop(ExecutorService pool) throws InterruptedException {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("pool did not terminate");
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
javac --release 17 -encoding UTF-8 -Xlint:all CollectionProtocolDemo.java
java CollectionProtocolDemo
```

Stdout on a successful run:

```text
check then remove = NoSuchElementException
poll: claimed = 1, empty = 1
contains then add = [Lan, Lan]
addIfAbsent = [Lan]
```

In the broken queue case, the `checked` latch lets the second caller take the job only after the first caller observes the queue is non-empty. The `removed` latch lets the first caller proceed only after the job has been taken. Thus, the exception directly reflects the gap between the two calls.

The `catch` block here only converts the exception into a string result for observation in the test. It is not a way to fix the dequeue protocol. The fix is deciding based on the result of a single `poll`.

In the broken list case, the barrier ensures both callers observe `absent = true` before adding. Two valid `add` calls produce `[Lan, Lan]`. The list itself is not corrupted; the application's own uniqueness rule is what gets violated.

In the `addIfAbsent` version, the two returned booleans must differ and the list contains exactly one name. This does not promise the name can never be removed and re-added later. If another path still calls `add("Lan")` directly, the uniqueness rule can be broken again.

Looking at both examples side by side reveals the same design flaw in two forms: **reading a condition, releasing coordination, and then acting as if the condition still holds**. Built-in conditional operations are valuable because they place the check and the mutation inside the same protection boundary.

## 11. Process for Analyzing a Sequence of Operations in Production Code

### 11.1. Write the Requirement as a Verifiable Condition

Before choosing `ConcurrentHashMap`, `synchronized`, or `CopyOnWriteArrayList`, write down the specific requirement. For example:

- Each completed increment contributes exactly one unit, assuming no reset/remove operation.
- A registration does not overwrite an existing registration.
- A move never lets a reader observe a total other than 20.
- Each dequeue attempt receives at most one element or an empty result.
- A member list never contains two equal elements under the chosen equality rule.

Not every requirement needs a system-wide snapshot. Conversely, if a requirement needs multiple pieces of data from the same version, per-part safe reads will not suffice.

### 11.2. List Every Step and Interleaving Point

Expand compact one-liners into explicit actions. For `put(key, get(key) + 1)`, split into read, compute, write. For `if (size() < limit) add(x)`, split into measure size, compare, add.

Then try inserting another thread's operation into each gap. If you can construct a valid schedule that breaks the condition, you have a counterexample. You do not need to prove the bug "happens often" before fixing it.

If you cannot find a failing schedule, still read the contract: there may be data publication issues, mutable elements, bypass paths, or mid-sequence exceptions that your initial step breakdown did not account for.

### 11.3. Choose the Smallest Protection Boundary That Satisfies the Requirement

| Scope of Condition | Suitable Mechanisms | What Else to Verify |
| --- | --- | --- |
| Single-key update | Conditional `putIfAbsent`, `replace`, `remove`, or `compute`/`merge` on an appropriate class | Concrete class guarantees, return values, remove/replace rules |
| Sequence on a synchronized wrapper | Lock on the wrapper itself for the whole sequence | No external path mutating the backing map/list |
| Multiple keys or multiple collections | Private wrapper class with a shared lock, or combined state design | All readers and writers follow the same protocol |
| State inside an element | Immutable elements or dedicated synchronization | No escaping reference allowing uncoordinated mutation |
| Claiming an available job | `poll` on an appropriate concurrent queue | Null handling and producer lifecycle |
| Waiting for a job or space | Blocking operations on `BlockingQueue` | Interruption, timeouts, shutdown, and held locks |
| Reading all data from one version | Snapshot under a shared lock or publishing immutable state | Copy depth and all update paths |

This selection is driven by requirements. No single mechanism in the table automatically covers all the other rows.

### 11.4. Encapsulate the Protocol So Callers Struggle to Misuse It

A service exposing only `increase`, `registerIfAbsent`, `move`, and `snapshot` is usually easier to keep correct than returning a live map and expecting every caller to remember the same locking rule.

If an object is widely shared, also audit:

- Where the object is created and published to threads.
- Read, write, remove, reset, and bulk methods.
- Views, iterators, and element references that escape.
- Callbacks that invoke external code or perform side effects.
- Reporting read paths that combine multiple keys to infer a condition.
- Behavior when work is interrupted, times out, or throws an exception.

A private lock limits who must coordinate; returning needed snapshots limits accidental external mutation. If you must expose a collection directly, the API documentation should clearly state the boundaries and caller responsibilities.

### 11.5. Testing Must Go Hand in Hand with Reasoning

The three programs in this lesson force specific failing schedules and then check the results of the fixes. They work well for learning because the buggy behavior does not depend on luck and task errors are propagated back to the main thread.

One run reaching 4,000 does not prove every counter implementation is correct. Even a test running millions of times without failure does not rule out a schedule that simply has not occurred yet. The primary evidence remains API contracts, lock scopes, state encapsulation, and all access paths obeying the same protocol.

Do not use `sleep`, log printing speed, or "my machine only has one core" to argue there is no race. Likewise, do not place test waiting inside a locked region in a way that alters the nature of the protocol being verified.

## 12. Practice and Self-Check

### Exercise 1 — Element Count Limit

A `CopyOnWriteArrayList<String>` is shared. Two threads run the following illustrative snippet, with a limit of 10:

```java
if (names.size() < 10) {
    names.add(candidate);
}
```

**Prompt:** When the list currently has 9 elements and there are two distinct candidates, write a schedule that makes the size 11. Does `addIfAbsent` properly fix the limit rule?

**Check:** Both threads can observe size 9 and then each add an element in turn. `addIfAbsent` only combines checking for an equal element and adding; it does not check the limit of 10. You need a shared mechanism covering both the capacity check and the add, obeyed by all update paths—or switch to a bounded structure/protocol that matches the requirement.

### Exercise 2 — Locking Correctly on Writes but Not on Reads

`move` uses a shared lock to update two keys. `total` runs `map.get("left") + map.get("right")` without acquiring the lock. The map is a `ConcurrentHashMap`.

**Prompt:** What part of the requirement "always read a total of 20" is missing?

**Check:** The reader does not participate in the invariant-protection protocol. It can still observe between the two writes or combine data from two different points in time. You must acquire the same lock for the entire read, return a snapshot created under the lock, or represent both numbers as a combined state with an appropriate replacement mechanism.

### Exercise 3 — Mappings and Inner Objects

A service creates a list with `computeIfAbsent` and returns that `List<String>` to the caller. The service itself uses `compute` for all subsequent modifications.

**Prompt:** What happens if the caller keeps and mutates the returned list?

**Check:** A mutation path can bypass the service's protocol. `compute` on other paths does not lock actions on an escaped list. You need immutable/unmodifiable value design, a copy of appropriate depth, or an API that does not return mutable references. You must also check whether an unmodifiable view still reflects a mutating backing structure.

### Exercise 4 — Atomic Increment with Concurrent Reset

A map stores `AtomicInteger`. Thread A retrieves the counter, Thread B removes the key and creates a new counter, and Thread A increments the old object.

**Prompt:** Is the increment lost on the old object itself? Must it necessarily appear when reading the current counter in the map?

**Check:** The increment on the old object can still be completely accurate and atomic. However, the map may already point to the new object, so readers looking up by key will not see that increment. You must define what reset/remove means for in-flight operations and choose a coordination boundary that covers that meaning.

### Exercise 5 — Temporarily Empty Queue

A task calls `poll()`, receives null, and shuts down the entire consumer system while producers are still running.

**Prompt:** The dequeue call itself is thread-safe, so why can the workflow still be wrong?

**Check:** The safety of a single dequeue does not define the termination condition of the work stream. Null reflects only that current dequeue attempt. The system needs a completion signal, cancellation, or another termination protocol, combined with producers having actually stopped.

## 13. References for Checking Contracts in Practice

The examples and interleaving schedules in this lesson are self-constructed illustrations. When switching collection classes or Java versions, verify the exact contract of the class and method you are using:

- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): synchronized wrappers and locking during iteration.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): conditional operations and default behavior of mapping functions.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomicity scope of per-key updates and limits of whole-map observations.
- [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html), [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): result-based dequeue/enqueue and blocking variants.
- [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterators and `addIfAbsent`.
- [JLS Chapter 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitors, ordering, and the Java Memory Model.
