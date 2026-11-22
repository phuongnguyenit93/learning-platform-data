# ConcurrentMap and Conditional Update Operations

A map stores key-to-value associations. When multiple threads share a map, requirements often go beyond "read a value" or "write a value": register only if absent, change state only if it still matches the previously read state, or remove only a registration that this caller still owns.

`ConcurrentMap<K, V>` extends `Map<K, V>` with concurrency guarantees, including operations that combine **checking a condition and updating** into a single atomic action. It is the tool for expressing decisions over a mapping without allowing a competing operation to interleave between the check and the write. [Java 17: ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

This lesson uses `ConcurrentHashMap` as the concrete implementation so the rules are unambiguous: neither `null` keys nor `null` values are allowed. That makes it possible to interpret return values without confusing `null` with an actually stored value.

Before diving into the API, keep four concepts in mind:

- **Mapping:** the key-value pair currently stored in the map at the moment of evaluation.
- **Update condition:** a requirement that must hold at the exact moment the map executes the operation, not merely during an earlier read.
- **Atomic:** the decision and modification parts of a call are executed as a single action with respect to the target mapping.
- **Expected value:** the old value used as the condition, such as "change from `PENDING` to `RUNNING` only if it is still equal to `PENDING`."

The plan is to understand the gap in compound operations, study the four core APIs, run an example with controlled contention, and then examine the limits of equality checks and atomicity scope.

## 1. A Thread-Safe Map Does Not Make a Sequence of Calls Atomic

Consider a `"slot"` registration entry that is initially unclaimed. The following snippet assumes `claims` is an already-initialized `ConcurrentMap<String, String>`:

~~~java
if (!claims.containsKey("slot")) {
    claims.put("slot", "CLAIMED");
    // Proceed with work assuming this thread just claimed the slot.
}
~~~

Each call to `containsKey` and `put` can be completely thread-safe when invoked concurrently. However, there is a time gap between the two calls. One valid interleaving is:

~~~text
Thread 1: sees slot is absent
Thread 2: sees slot is absent
Thread 1: writes CLAIMED and assumes it won
Thread 2: writes CLAIMED and also assumes it won
~~~

The map still has only one `slot` key. The data structure is not corrupted. What is violated is the rule that **only one party may be recognized as having registered successfully**.

`putIfAbsent` moves the "if absent" condition inside the update operation itself. The caller must rely on the result of that operation to determine whether it won the claim.

The same issue occurs when reading a counter and writing the old value plus one, reading a state and replacing it unconditionally, or checking an owner and removing unconditionally. The thread safety of individual calls does not compose them into a larger transaction.

## 2. Four Operations to Distinguish

The following table assumes a map that rejects `null` values, specifically the `ConcurrentHashMap` used in this lesson. Every condition is evaluated as part of the operation itself, not via a separate prior check.

| Call | When does it modify the mapping? | Return value |
|---|---|---|
| `putIfAbsent(k, candidate)` | When there is no value at `k`. | The previous value; `null` indicates the call inserted into an absent key. |
| `replace(k, replacement)` | When `k` currently has a mapping, regardless of what the old value is. | The replaced value; `null` if there was no mapping to replace. |
| `replace(k, expected, replacement)` | When the current value at `k` equals `expected` according to the operation's equality contract. | `true` if replaced, `false` if the condition did not match. |
| `remove(k, expected)` | When the current value at `k` equals `expected`. | `true` if removed, `false` if not removed. |

The atomicity contract of these operations is specified by `ConcurrentMap`; merely having the same method names on the `Map` interface does not provide concurrency guarantees for arbitrary implementations. [Java 17: ConcurrentMap conditional methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#putIfAbsent(K,V))

### 2.1. putIfAbsent: Insert Only When Absent

The following snippet illustrates usage inside a method:

~~~java
java.util.concurrent.ConcurrentMap<String, String> registrations =
        new java.util.concurrent.ConcurrentHashMap<>();

String previous = registrations.putIfAbsent("id-5", "Lan");
boolean inserted = previous == null;
~~~

With a newly created map, `previous` is `null` and `inserted` is `true`. If another party had already stored `"Minh"` at `id-5`, the call returns `"Minh"` and does not overwrite it with `"Lan"`.

Common misinterpretations:

- The return value is not the new value the caller tried to store.
- The return value is not a `boolean`.
- The existing value might be equal in content to the candidate; that does not prove the caller just won.
- Do not call `containsKey` afterward to infer what just happened; that is an observation at a different point in time.

If you need the value that was actually selected in a non-null map, a common pattern is:

~~~java
String candidate = "Lan";
String existing = registrations.putIfAbsent("id-5", candidate);
String selected = existing == null ? candidate : existing;
~~~

`selected` is the outcome of that call's selection. It is not a promise that no one else can replace or remove the mapping immediately afterward.

### 2.2. Two-Argument replace: Only Requires the Key to Exist

`replace(k, replacement)` differs from `put(k, replacement)` in that it does not create a mapping for an absent key.

~~~java
String old = registrations.replace("id-missing", "Hoa");
// With the data above: old is null and id-missing is not created.
~~~

However, the two-argument form **does not check for a specific old value**. If the requirement is "only accept the change if the registration is still the one I read," this form is not sufficient.

For example, one thread reads `PENDING`, another thread changes it to `CANCELLED`, and then the first thread calls `replace(k, "RUNNING")`. The two-argument form can overwrite even `CANCELLED` because the key still exists. To protect an assumption about the old state, you must use the three-argument form.

### 2.3. Three-Argument replace: Replace Only the Expected Value

~~~java
boolean started = states.replace("job-8", "PENDING", "RUNNING");
~~~

This snippet assumes `states` is a `ConcurrentMap<String, String>` that disallows `null`. `started` is `true` only when the replacement actually took place.

If the key is absent or holds a different value, the result is `false` and the call does not write `RUNNING`. Those two failure cases are not distinguished by the `boolean` return value alone. You can read the map again to decide how to proceed, but that subsequent read is a new observation.

This example expresses a very narrow state transition: `PENDING → RUNNING`. It does not automatically enforce all business rules such as caller permissions, deadlines, job versions, or the state of other keys. If those factors must be decided together, they need to be incorporated into the condition model or handled with a broader coordination mechanism.

### 2.4. Two-Argument remove: Clean Up Only the Matching Mapping

`remove(k)` removes the current mapping by key. `remove(k, expected)` removes it only if the value still matches the condition.

A typical scenario is cleaning up an old registration:

~~~text
Party A registered with session token A-1.
The registration was replaced with session token B-1.
Party A finishes late and performs cleanup.
~~~

If A calls `remove(key)`, it could delete registration B-1. If A calls `remove(key, "A-1")`, the removal fails when the current mapping is B-1.

This is **conditional removal based on the current value**. For the condition to mean "specifically my registration," the value must contain an identifier that cannot be accidentally reused. Using only a generic owner name like `"A"` might fail to distinguish two different registrations by the same party A.

## 3. Interpreting Atomic Results Over Time

You can reason about each conditional call as a decision that takes effect at a single point in time between the call's start and completion. The condition check and the update are not split into two independent decisions that another party can interleave between.

However, the map is not frozen after returning a result:

~~~text
T1: replace(k, OLD, NEW) succeeds
T2: remove(k, NEW) succeeds
T1: executes the next line of code
~~~

T1 succeeded in replacing the value and can still see the key as absent if it reads again on the next line. Those two facts do not contradict each other.

Similarly, `remove(k, expected)` returning `true` does not guarantee that `k` will still be absent on the next `get`; another party may have re-inserted it.

Distinguish two goals:

- **Knowing whether the just-executed call was accepted:** use its return value.
- **Knowing the state observed at a subsequent read:** use that read, keeping in mind that it too can change shortly after.

Do not use a post-update `get` as a substitute for the meaning of the return value. Likewise, do not hold onto an old result and treat it as an indefinite exclusive lock.

## 4. Value Equality Does Not Mean Same Object Identity

The condition for `replace(k, expected, replacement)` and `remove(k, expected)` is defined in terms of value equality, not `==` reference identity. For `String`, two separately constructed objects with the same content still match.

~~~java
String stored = new String("OPEN");
String expected = new String("OPEN");

boolean sameObject = stored == expected; // false
boolean sameValue = stored.equals(expected); // true
~~~

`equals` represents the equality relation defined by the type; it does not automatically mean "same version," "same registration," or "never modified." [Java 17: Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))

Condition design must go hand in hand with value-type design:

- For a simple immutable value, content comparison is usually appropriate.
- For a registration session, a dedicated session token should be included.
- For a state where intermediate modifications must be detected, a version should be included in the equality check.
- For a mutable-in-place object, retaining a reference does not guarantee a snapshot of the value as it was when read.

If `equals` ignores the version or session token, adding that field to the class without including it in equality comparisons will not produce the desired condition.

## 5. Complete Verification Program

Save the file as `ConditionalMapDemo.java`. The program uses APIs and syntax available in Java 17, was compiled with `javac --release 17`, and was run on OpenJDK Zulu 24.0.2. The output below is from that environment; do not extrapolate it as a claim of having run on JVM 17.

The multithreaded sections use `CyclicBarrier` to coordinate the timing of checks and updates. They do not use `Thread.sleep` to hope for the right race condition. `ConcurrentHashMap` protects individual calls, so the broken compound-operation examples do not need to corrupt the map structure to fail.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ConditionalMapDemo {
    record Revision(long number, String state) {}

    @FunctionalInterface
    interface CheckedTask {
        void execute() throws Exception;
    }

    static void together(CheckedTask task) throws Exception {
        AtomicReference<Throwable> problem = new AtomicReference<>();
        Thread[] threads = new Thread[2];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                try {
                    task.execute();
                } catch (Throwable ex) {
                    problem.compareAndSet(null, ex);
                }
            }, "contender-" + i);
            threads[i].setDaemon(true);
        }
        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join(5000);
        }
        for (Thread thread : threads) {
            if (thread.isAlive()) {
                for (Thread other : threads) {
                    other.interrupt();
                }
                throw new AssertionError("Concurrent scenario timed out");
            }
        }
        if (problem.get() != null) {
            throw new AssertionError("Concurrent scenario failed", problem.get());
        }
    }

    static void addOne(ConcurrentMap<String, Integer> counts, String key) {
        for (;;) {
            Integer observed = counts.get(key);
            if (observed == null) {
                if (counts.putIfAbsent(key, 1) == null) {
                    return;
                }
            } else {
                int updated = Math.addExact(observed, 1);
                if (counts.replace(key, observed, updated)) {
                    return;
                }
            }
        }
    }

    static String build(AtomicInteger builds) {
        return "candidate-" + builds.incrementAndGet();
    }

    static String nullResult(Runnable task) {
        try {
            task.run();
            return "completed";
        } catch (NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentMap<String, String> state = new ConcurrentHashMap<>();
        System.out.println("insert-first = "
                + state.putIfAbsent("job", "PENDING"));
        System.out.println("insert-second = "
                + state.putIfAbsent("job", "OTHER"));
        System.out.println("stored = " + state.get("job"));

        System.out.println("replace-missing = "
                + state.replace("missing", "RUNNING"));
        System.out.println("missing-present = " + state.containsKey("missing"));
        System.out.println("replace-present-old = "
                + state.replace("job", "RUNNING"));
        System.out.println("replace-stale = "
                + state.replace("job", "PENDING", "DONE"));
        System.out.println("replace-match = "
                + state.replace("job", "RUNNING", "DONE"));
        System.out.println("after-replace = " + state.get("job"));
        System.out.println("remove-stale = " + state.remove("job", "RUNNING"));
        System.out.println("remove-match = " + state.remove("job", "DONE"));
        System.out.println("remove-again = " + state.remove("job", "DONE"));

        ConcurrentMap<String, String> equality = new ConcurrentHashMap<>();
        String actual = new String("OPEN");
        String equivalent = new String("OPEN");
        equality.put("door", actual);
        System.out.println("same-reference = " + (actual == equivalent));
        System.out.println("replace-equal-value = "
                + equality.replace("door", equivalent, "CLOSED"));

        ConcurrentMap<String, String> claims = new ConcurrentHashMap<>();
        AtomicInteger reportedWinners = new AtomicInteger();
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        together(() -> {
            boolean vacant = !claims.containsKey("slot");
            bothChecked.await(5, TimeUnit.SECONDS);
            if (vacant) {
                claims.put("slot", "CLAIMED");
                reportedWinners.incrementAndGet();
            }
        });
        System.out.println("check-then-put-winners = " + reportedWinners.get());

        claims.clear();
        reportedWinners.set(0);
        CyclicBarrier bothReady = new CyclicBarrier(2);
        together(() -> {
            bothReady.await(5, TimeUnit.SECONDS);
            if (claims.putIfAbsent("slot", "CLAIMED") == null) {
                reportedWinners.incrementAndGet();
            }
        });
        System.out.println("putIfAbsent-winners = " + reportedWinners.get());

        ConcurrentMap<String, Integer> broken = new ConcurrentHashMap<>();
        broken.put("hits", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        together(() -> {
            int previous = broken.get("hits");
            bothRead.await(5, TimeUnit.SECONDS);
            broken.put("hits", previous + 1);
        });
        System.out.println("get-then-put-count = " + broken.get("hits"));

        ConcurrentMap<String, Integer> fixed = new ConcurrentHashMap<>();
        CyclicBarrier startCounting = new CyclicBarrier(2);
        together(() -> {
            startCounting.await(5, TimeUnit.SECONDS);
            for (int i = 0; i < 1000; i++) {
                addOne(fixed, "hits");
            }
        });
        System.out.println("conditional-loop-count = " + fixed.get("hits"));

        ConcurrentMap<String, String> plain = new ConcurrentHashMap<>();
        plain.put("item", "A");
        String oldState = plain.get("item");
        plain.put("item", "B");
        plain.put("item", "A");
        System.out.println("plain-ABA-update = "
                + plain.replace("item", oldState, "C"));

        ConcurrentMap<String, Revision> versions = new ConcurrentHashMap<>();
        versions.put("item", new Revision(1, "READY"));
        Revision observed = versions.get("item");
        versions.put("item", new Revision(2, "BUSY"));
        versions.put("item", new Revision(3, "READY"));
        System.out.println("versioned-stale-update = "
                + versions.replace("item", observed, new Revision(4, "DONE")));
        System.out.println("versioned-current = " + versions.get("item"));

        ConcurrentMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger builds = new AtomicInteger();
        cache.putIfAbsent("key", build(builds));
        cache.putIfAbsent("key", build(builds));
        System.out.println("eager-builds = " + builds.get());
        System.out.println("eager-stored = " + cache.get("key"));

        AtomicInteger lazyBuilds = new AtomicInteger();
        String reused = cache.computeIfAbsent("key", key -> build(lazyBuilds));
        System.out.println("existing-compute-builds = " + lazyBuilds.get());
        System.out.println("existing-compute-value = " + reused);

        System.out.println("null-key = "
                + nullResult(() -> cache.putIfAbsent(null, "x")));
        System.out.println("null-value = "
                + nullResult(() -> cache.putIfAbsent("null-test", null)));
    }
}
~~~

Compile and run commands in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ConditionalMapDemo.java
java ConditionalMapDemo
~~~

Verified stdout:

~~~text
insert-first = null
insert-second = PENDING
stored = PENDING
replace-missing = null
missing-present = false
replace-present-old = PENDING
replace-stale = false
replace-match = true
after-replace = DONE
remove-stale = false
remove-match = true
remove-again = false
same-reference = false
replace-equal-value = true
check-then-put-winners = 2
putIfAbsent-winners = 1
get-then-put-count = 1
conditional-loop-count = 2000
plain-ABA-update = true
versioned-stale-update = false
versioned-current = Revision[number=3, state=READY]
eager-builds = 2
eager-stored = candidate-1
existing-compute-builds = 0
existing-compute-value = candidate-1
null-key = NullPointerException
null-value = NullPointerException
~~~

`together` waits for both threads to finish before the main thread prints the results, and forwards any worker-thread error back to the main thread. The five-second timeouts only bound how long the verification waits; they do not determine which thread wins.

## 6. Analyzing the Results

### 6.1. Return Value Distinguishes Insertion from Retention

The first three lines:

~~~text
insert-first = null
insert-second = PENDING
stored = PENDING
~~~

The first call creates the mapping `job → PENDING`. The second call supplies candidate `OTHER` but receives the existing value `PENDING`. The stored value remains `PENDING`.

There is no need for a pre-checked "already exists" flag. The return value of `putIfAbsent` itself carries the result of the atomic decision.

### 6.2. The Two Forms of replace Protect Different Conditions

~~~text
replace-missing = null
missing-present = false
replace-present-old = PENDING
replace-stale = false
replace-match = true
after-replace = DONE
~~~

The two-argument `replace` on `missing` does not create the key. The two-argument form on `job` replaces `PENDING` with `RUNNING` and returns `PENDING`.

Afterward, the call requiring `PENDING` as the condition fails because the current value is already `RUNNING`. The call requiring `RUNNING` succeeds and changes it to `DONE`.

This section runs sequentially to clearly verify each operation's contract before introducing contention. Multiple threads are not needed to observe the difference between "the key still exists" and "the value still matches the expected one."

### 6.3. Conditional Removal Does Not Remove a Changed State

~~~text
remove-stale = false
remove-match = true
remove-again = false
~~~

The condition `RUNNING` no longer matches `DONE`, so it does not remove the entry. The condition `DONE` matches, so it removes it. The subsequent removal has no mapping to remove and returns `false`.

This is an operation outcome, not an exception to catch for handling contention. A condition no longer holding is an expected result when multiple parties compete.

### 6.4. Conditions Use Value Equality

~~~text
same-reference = false
replace-equal-value = true
~~~

Two `String` objects have different references but the same content `OPEN`. The replacement condition still matches. Therefore, using `new String(...)` to create a "unique token" does not establish a distinct session identity if the token content is identical.

### 6.5. The Map Has Only One Key, Yet Both Sides Can Claim Victory

In the `check-then-put` section, the barrier forces both threads to finish checking that the key is absent before either writes. Both enter the `if` branch and increment the self-reported winner count. The result is `2`.

The `putIfAbsent` section places the barrier before the atomic operation. Both threads still compete, but only the one that receives `null` increments the winner count. Since there is no removal or replacement during this phase, the result is `1`.

If another party removes the key and allows re-creation, multiple `putIfAbsent` calls can succeed in sequence across different lifecycles of the same key. Therefore, "one winner" must be tied to the time window and lifecycle rules defined by the problem.

### 6.6. get-then-put Can Lose an Increment

In the `broken` section, both threads read `0` before the barrier, and then both write `1`. There are two increment requests, yet the result is only `1`.

In `fixed`, `addOne` loops over reading and attempting conditional replacement. If the key is absent, it attempts to insert `1`; if present, it replaces only if the value still equals the one just read. When one side updates first, the other must re-read and recompute.

Two threads each increment `1,000` times, with no key removal and no other writes, so the verified result is `2,000`.

### 6.7. Equality Conditions Do Not Preserve Change History

`plain-ABA-update = true` comes from this sequence:

~~~text
Read A as the expected value
Value is changed to B
Value is changed back to A
Attempt to replace with condition still equal to A
Result: condition matches
~~~

If the requirement is merely "the current value equals A," succeeding obeys the contract. If the requirement is "no one has updated it since I read it," that condition is too weak. The phenomenon where a value returns to A after passing through B is commonly called **ABA**.

The `versions` section adds a version number. The current value is `Revision(3, "READY")`, which differs from the read `Revision(1, "READY")`, so the stale update is rejected.

The record in the example has `long` and `String` components; the record-generated equality compares the corresponding components. Thus, the version number is part of the condition, not just metadata for logging. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

### 6.8. Conditional Insertion Does Not Defer Argument Evaluation

~~~text
eager-builds = 2
eager-stored = candidate-1
~~~

Both `build` calls ran when Java evaluated the arguments before invoking `putIfAbsent`. The second construction can waste work even though its value is not selected.

When `computeIfAbsent` is called on an already-present key in the example, the mapping function does not run:

~~~text
existing-compute-builds = 0
existing-compute-value = candidate-1
~~~

This difference helps guide API selection, but you must not assume that every `ConcurrentMap` implementation invokes the mapping function the exact same number of times under all contention scenarios.

## 7. Conditional Update Loops

`addOne` is an optimistic update pattern: read the state, compute a new candidate, request replacement if the state still matches; if rejected, retry using the newly re-read data.

This pattern is used to illustrate the mechanism, not as a recommendation to write every counter with a verbose loop. For simple computations, an API like `merge` on a concrete class can express it more concisely.

### 7.1. Why Re-read After Failure?

Suppose two threads both read `10` and both compute `11`. One succeeds in replacing it. The other must use `11` to compute `12`.

If the failing thread keeps retrying `replace(key, 10, 11)` without re-reading, it is clinging to a stale assumption. If it calls `put(key, 11)` to "make sure the write goes through," it can overwrite a newer update.

The loop in the program always goes back to `get`. Computation is based on the fresh read, not by reusing the failed attempt's result.

### 7.2. Keep the Computation Repeatable

During a single successful update, the candidate computation block may run multiple times due to failed attempts. Therefore, this block should compute from the input data and produce a new result, avoiding external side effects that cannot be safely repeated.

Do not place sending notifications, deducting money in an external system, or confirming task completion before a conditional replacement and assume they happen only once. The map does not roll back those side effects when the replacement fails.

Even after `replace` returns `true`, performing an external side effect does not form a single combined transaction with the map. If the process stops between the two steps, recovery design is still needed according to real-world requirements.

### 7.3. Absent Keys and Re-creation Must Make Sense

`addOne` treats an absent key as a non-existent counter and tries to create `1`. If another thread removes the key in the meantime, the loop may re-create it.

That suits a counter that is allowed to restart after removal, but it can be wrong if removal means "the task is closed and must not be reopened." In that case, an explicit closed-state model or a protocol that forbids arbitrary re-creation is required.

No single conditional loop fits every possible meaning of removal.

### 7.4. Atomicity Does Not Imply Lock-Free Algorithms

`ConcurrentMap` is an interface contract. From the existence of an atomic `replace`, you cannot conclude that the implementation uses a single CPU instruction, never blocks, or guarantees that a particular thread always wins within bounded time.

Under continuous contention, one party may have to retry many times. When choosing an algorithm for a critical path, evaluate the class contract, contention level, and progress requirements rather than looking only at operation names.

## 8. Designing Values for Reliable Conditions

### 8.1. Prefer Replacing Whole Immutable Values

A favorable model is:

~~~text
Read a value that is not mutated in place
    -> create a new value
    -> conditionally replace based on the old value
~~~

With the `Revision` record in the program, the numeric and string components cannot be mutated through the old object. When a new value is stored, the old read still accurately describes the state the caller observed.

In general, a record does not deep-copy every object held in its components. If a component is a mutable list, immutability must be designed explicitly. The example uses only `long` and `String` to avoid that issue.

### 8.2. An Old Reference to a Mutable Object Is Not an Old Snapshot

Suppose the value is an `Account` object with a mutable `balance` field. The caller gets `observed = map.get(key)`. Later, someone modifies `balance` on the exact object that `observed` points to.

At that point, `observed` no longer specifically represents "the balance at the time I read it." It still points to the object being mutated. A conditional operation reusing that reference might match even though the content has changed.

The solution does not lie in adding another `get`. You need immutable values, versioned data records, or a dedicated locking protocol for the relevant objects and operations.

### 8.3. Versions Only Help When Every Writer Complies

The `Revision` example prevents the stale version `1` case from matching when the string state returns to `READY` at version `3`. However, this guarantee depends on update discipline:

- Each update must increment or generate an appropriate new version marker.
- Every write path must follow that rule, including cleanup tools and recovery paths.
- Removing and re-inserting must not accidentally reuse an identifier that an old request still holds.
- Equality must include the identifier being checked.
- Value-range limits and version-number rollover must be considered if the system lives long enough.

Merely adding a `version` field to a class does not force writers to use it. An unconditional `put` from one party can bypass the optimistic update protocol of all other parties.

### 8.4. Keys Must Also Have Stable Semantics

Keys used in a map must obey the equality and hashing or ordering contract of the map class in use. Mutating components that determine a key's `equals`/`hashCode` while the key is stored in the map can make lookups unreliable. `Map` explicitly warns against mutable keys that affect equality. [Java 17: rules on mutable keys](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Conditional operations cannot rescue a key model whose identity mutates while it is being used as a key.

## 9. Relationship to compute and merge

The four core operations take a candidate already computed by the caller. The methods `computeIfAbsent`, `computeIfPresent`, `compute`, and `merge` additionally accept a computation function so the map can coordinate the update according to the method's contract.

Distinguishing use cases:

| Need | Commonly considered tool |
|---|---|
| Candidate already exists; insert only if absent | `putIfAbsent` |
| Have a specific old value; replace only if it still matches | `replace(k, expected, replacement)` |
| Clean up only the exact registration held | `remove(k, expected)` |
| Compute a value only when absent using a function | `computeIfAbsent` |
| Compute a new value from the current value | `compute`, `computeIfPresent`, or `merge`, depending on absence behavior and result semantics |

An important point is that **the interface contract and a concrete implementation's stronger contract are not always identical**.

In `ConcurrentMap`, the default implementations of some computation methods may retry the process under concurrent updates; the update function may run multiple times. Do not carry the assumption that "the function always runs only once" into an arbitrary implementation. [Java 17: ConcurrentMap.compute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction))

`ConcurrentHashMap` specifies that a `computeIfAbsent` call is performed atomically and the function is invoked once per call that needs to compute when the key is absent; the computation should be short, simple, and must not modify the map during computation. Even that is not a promise of "once in the entire lifetime of the key": the value can be removed, the function can return `null` or throw an exception, and subsequent calls have different conditions. [Java 17: ConcurrentHashMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

`ConcurrentSkipListMap` is another `ConcurrentMap` implementation with ordered keys. Its documentation does not promise that `computeIfAbsent` applies the function atomically only once when absent. Therefore, do not copy `ConcurrentHashMap`-specific assumptions just because both implement `ConcurrentMap`. [Java 17: ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function))

These differences are why you should read the exact method contract on the exact implementation class whenever the function has high cost, side effects, or invocation-count requirements.

## 10. Boundaries to Keep Clear

### 10.1. Null Policy Belongs to the Concrete Implementation

`ConcurrentHashMap` and `ConcurrentSkipListMap` do not allow `null` keys or `null` values. The verification program uses `ConcurrentHashMap` and shows that `putIfAbsent` with a `null` key or `null` value throws `NullPointerException`.

Do not turn that into a claim that every possible `ConcurrentMap` implementation must forbid `null` in the same way. The interface Javadoc includes implementation notes for maps that support `null`; many default methods assume `get` returning `null` means absent and must be overridden when that assumption does not hold. [Java 17: ConcurrentMap.getOrDefault implementation notes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#getOrDefault(java.lang.Object,V))

In general-purpose code, do not use `replace(key, null, value)` as "insert if absent." The API that expresses that intent is `putIfAbsent`, along with the concrete class's null policy.

### 10.2. Publishing a Mapping Does Not Automatically Synchronize Later Mutations

`ConcurrentMap` provides memory-publication guarantees between actions prior to placing an object into the map and actions accessing or removing that object in another thread. This helps safely hand off initialized objects through the map. It does not automatically protect subsequent in-place mutations. [Java 17: ConcurrentMap memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

For example, `ConcurrentMap<String, List<String>>` does not automatically make a stored `ArrayList` safe when multiple threads call `add` on that list. You must choose a value type with an appropriate concurrency contract or replace the whole value via a conditional protocol.

### 10.3. Single-Key Atomicity Is Not a Multi-Key Transaction

Two conditional calls on `account-A` and `account-B` are two separate operations. If the first succeeds and the second fails, the map does not automatically roll back the first.

Rules such as transferring quantities between two warehouses, updating two indexes together, or updating a map alongside an external record require a broader consistency mechanism. That could be a shared lock obeyed by all parties, combining state into a single value, or transactions at the data's authoritative store; the choice depends on the problem.

Adding `synchronized (map)` on one caller's side does not cause ordinary `ConcurrentHashMap` calls from other callers to participate in that monitor. An external locking protocol covers all accesses only when every relevant access coordinates through it.

### 10.4. Conditional Updates Do Not Provide a Whole-Map Snapshot

Conditional operations protect decisions on the target mapping. They do not turn an iteration, `size`, or a sequence of multi-key reads into an atomic whole-map snapshot.

If you need to produce a consistent report of the entire map, define the data point-in-time and snapshot mechanism explicitly. If you only need to monitor shifting state, weaker consistency may be appropriate. Distinguish that requirement from conditionally updating a single key.

### 10.5. Declared Type Does Not Change the Underlying Implementation

`Map` already declares methods such as `putIfAbsent` and `replace`, but its default implementations do not promise synchronization or atomicity for every map. A `HashMap` does not become a concurrent data structure merely by calling these API names. [Java 17: Map.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putIfAbsent(K,V))

Conversely, a variable declared as `Map` that actually refers to a `ConcurrentHashMap` still invokes that object's methods. Declaring `ConcurrentMap` usually helps express the concurrency requirements of the calling code; what determines the actual guarantee is the contract satisfied by the runtime implementation object.

## 11. How to Choose and Verify

Before writing code, describe the operation with a conditional sentence:

- "Insert only if the key is absent."
- "Replace only if the value still equals the one I am using."
- "Remove only if the registration still belongs to this exact session."
- "Recompute from the current value and retry if it was changed."

Then check each question in turn:

1. Does the condition involve only a single mapping or multiple objects?
2. Is `equals` comparison sufficient, or is a session token/version needed?
3. Can the value be mutated in place, causing the expected value to change unexpectedly?
4. Is the return value used immediately to distinguish success from failure?
5. Can the computation block run multiple times without causing incorrect duplicate side effects?
6. Can the key be removed and re-created while an old request is still running?
7. Which concrete implementation class do the `null` policy and computation-function contract belong to?

In tests, assert the direct outcomes: the number of recognized winners, the final count, the new state, and the rejection of stale requests. Do not test merely for "no exception thrown."

The program above uses barriers to force lost-update and double-winner schedules. The ABA and versioning examples use sequential steps to reproduce histories that an old request can encounter. Isolating conditions this way helps explain results deterministically rather than depending on thread scheduling luck.

## 12. Self-Check Exercises

### Exercise 1 — Reading putIfAbsent Correctly

A `ConcurrentHashMap` already contains `id → "Mai"`. What does `putIfAbsent(id, "Lan")` return, what does it store, and did the caller just insert successfully?

**Answer:** It returns `"Mai"`, keeps `"Mai"`, and does not insert. The candidate `"Lan"` is not the selected result.

### Exercise 2 — Two Forms of replace

One thread reads `PENDING`, but before it writes, another thread changes it to `CANCELLED`. Compare `replace(k, "RUNNING")` and `replace(k, "PENDING", "RUNNING")`.

**Answer:** The two-argument form only requires the key to still have a value, so it can overwrite `CANCELLED`. The three-argument form fails if the current value is no longer `PENDING`. Choose the second form when you need to protect an assumption about the old state.

### Exercise 3 — Cleaning Up an Old Registration

A holds session token `A-1`. The map has moved on to session `B-1`. Should A call `remove(k)` or `remove(k, "A-1")`?

**Answer:** Use the form with the expected value, so it does not remove the new mapping `B-1`. If the application reuses session tokens without distinguishing registrations, fix the identifier model first.

### Exercise 4 — Succeeded Yet get Sees Something Different

`replace(k, old, next)` returns `true`, but `get(k)` on the next line returns a third value. Is that enough evidence to conclude the conditional operation is not atomic?

**Answer:** No. Another party could have updated the key after the successful replacement and before the read. The `true` result describes the call that just executed; it does not lock the state for subsequent lines.

### Exercise 5 — Value A Returns

A request holds `A`; the map goes to `B` and then back to `A`. Is `replace(k, A, C)` enough to detect any intermediate updates?

**Answer:** No. It checks whether the current value equals `A`, not the history. If you need to detect intermediate changes, use a versioned value or an appropriate identifier and ensure all write paths obey it.

### Exercise 6 — Expensive Construction Function

Why does `putIfAbsent(k, create())` still call `create` when the key already exists? Can you always replace it with `computeIfAbsent` and claim the function runs only once during the program's lifetime?

**Answer:** Arguments are evaluated before the call. `computeIfAbsent` can avoid computing when a value already exists, but the invocation count and atomicity scope of the function must be read from the concrete implementation class. Even `ConcurrentHashMap`'s strong contract is not a guarantee of computing only once across the key's entire lifetime.

### Exercise 7 — Thread-Safe Map, Mutable List Inside

Multiple threads fetch a list from `ConcurrentMap<String, ArrayList<String>>` and call `add` on it. Is the atomicity of `putIfAbsent` enough to protect those `add` calls?

**Answer:** No. Safely inserting a mapping and mutating the value object are two different things. You need an appropriate value type or a separate update protocol.

### Exercise 8 — Incrementing a Counter and Key Removal

A loop like `addOne` sees a key as absent after a manager removed it to close a task. It tries `putIfAbsent(k, 1)`. Why can this operation obey the map's contract yet violate the requirements?

**Answer:** The map allows creating a mapping when absent, but "removed" may carry the business meaning that it must not be re-created. You need an explicit closed-state model or clear lifecycle rules rather than overloading absence for two different meanings.

A conditional operation is useful when the API's condition expresses the exact condition the program needs to protect. Design keys, values, versions, and return-value handling together; only then do you have a solid basis for scaling from a single atomic update to a correct processing flow.
