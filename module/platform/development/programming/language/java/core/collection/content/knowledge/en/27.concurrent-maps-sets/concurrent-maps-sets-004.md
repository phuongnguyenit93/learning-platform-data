# Limits of Computing Functions: Recursive Updates and Long-Running Tasks

## 1. Understand the Role of the Callback Before Putting Work into a Map

In concurrent maps and sets, a common requirement is: multiple threads encounter a key that has no data yet, or want to modify an existing value at the same time. If you write a manual "read -> check -> write" sequence, two threads might both make decisions based on a stale state. Methods such as `computeIfAbsent`, `computeIfPresent`, `compute`, and `merge` let you describe the computation to perform right at the update point.

The function passed to such a method is called a callback. With `computeIfAbsent`, it typically creates a value for a missing key. With `compute`, it receives the key and the old value, then decides the new value. From the outside, the call looks very concise:

```java
// Illustrative code inside a method; not a standalone program.
counts.compute("java", (key, oldCount) ->
        oldCount == null ? 1 : oldCount + 1);
```

This callback only computes an integer and returns it. The map takes care of publishing the result. That division of responsibility helps the reader clearly see which part belongs to the computation and which part belongs to the update mechanism.

Difficulties arise when you replace addition with work that has dependency cycles or unbounded duration: fetching from a server, reading a database, waiting for another task, or calling a utility method that loops back to modify the same map. A single-line lambda can still hide an entire long-running workflow.

This lesson focuses on `ConcurrentHashMap` on Java 17 and later. You need to distinguish three layers:

- **Update operation:** changing the mapping between a key and a value.
- **Application work:** loading data, checking conditions, business calculations.
- **Waiting relationships:** which thread needs the result of which thread, and which resources are held while waiting.

Thread safety when multiple threads access a map does not automatically design the other two layers for you. After this lesson, you should be able to explain why callbacks should be short, recognize recursive updates even when they pass through multiple methods, and choose how to move slow tasks outside the update operation while understanding the cost of duplicate loading or sharing results.

The programs below are independent of each other. Save each program under the exact filename noted in its section, use JDK 17 or newer, and run from the directory containing the file. The `--release 17` flag keeps the code within Java 17 APIs and syntax. Output is printed only from the main thread after the necessary coordination points, avoiding reasoning from arbitrary print ordering between threads.

## 2. Read the Scope of Guarantees Accurately

With `ConcurrentHashMap`, the computation call is atomic with respect to the associated update. The callback of `computeIfAbsent` runs when a value needs to be created; the callback of `computeIfPresent` runs when the key has a value; `compute` evaluates for both present and absent keys. The callback must be short, simple, and must not modify the map being computed. Some other updates may have to wait. Detected recursive updates can result in `IllegalStateException`. See the [ConcurrentHashMap contract in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)).

"Atomicity" must be placed alongside the exact object being modified. Suppose a callback sends an email and then returns a value: installing the value into the map and the email having been sent are two separate events. If the callback throws an exception after sending the email, the application must handle the consequences of that email itself. There is no basis for treating the entire function as a database transaction.

Similarly, a single call does not turn a sequence of calls into a single atomic action. If business logic must transfer a quantity from key A to key B, two separate `compute` operations do not express a shared transaction boundary. You need a coordination design at the business level; stuffing the update for B into A's callback will create further problems.

### Four Function Forms to Recognize

| Method | Data the callback receives | Decision the callback expresses |
|---|---|---|
| `computeIfAbsent(k, f)` | The missing key | Create a value to use for that key |
| `computeIfPresent(k, f)` | The key and current value | Modify or remove the existing mapping |
| `compute(k, f)` | The key and old value, possibly absent | Decide the next mapping |
| `merge(k, value, f)` | The old value and input value when merging is needed | Combine two values into the next result |

This table helps you read code; it is not an invitation to put more update operations inside the callback. "Decide the next mapping" means **returning a result to the calling method**, rather than calling `put`, `remove`, or `compute` yourself to interfere with the same map while that method is still running.

You must also check the actual implementation class. A variable of type `ConcurrentMap` can point to different classes. Default implementations on that interface may retry, causing the remapping function to be invoked multiple times under contention. Do not generalize the properties of `ConcurrentHashMap` to every implementation class. See the [Implementation Requirements section of ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction)).

From this follows an easy-to-apply design principle: a callback should primarily transform input data into a result. The fewer external side effects it has, the easier the code is to reason about when swapping implementation classes, adding retry mechanisms, or handling errors.

## 3. Null Values, Exceptions, and Execution Counts

In `Map` computation operations, a `null` result is used to decide not to create or to remove a mapping, depending on the method. A callback throwing an exception does not mean the application receives a default value. You need to read both the return branch and the error branch accurately. See the [Map compute contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#compute(K,java.util.function.BiFunction)).

### Program: Outcome of a Callback and Side Effects That Occurred

File `ComputeOutcomesDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class ComputeOutcomesDemo {
    public static void main(String[] args) {
        var values = new ConcurrentHashMap<String, Integer>();
        var attempts = new AtomicInteger();

        values.put("ready", 10);
        int ready = values.computeIfAbsent("ready", key -> {
            attempts.incrementAndGet();
            return 99;
        });
        System.out.println("ready=" + ready + ", attempts=" + attempts.get());

        values.computeIfAbsent("missing", key -> {
            attempts.incrementAndGet();
            return null;
        });
        values.computeIfAbsent("missing", key -> {
            attempts.incrementAndGet();
            return null;
        });
        System.out.println("missingPresent=" + values.containsKey("missing"));
        System.out.println("attemptsAfterNull=" + attempts.get());

        try {
            values.compute("ready", (key, oldValue) -> {
                attempts.incrementAndGet();
                throw new IllegalArgumentException("invalid input");
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
        System.out.println("readyAfterFailure=" + values.get("ready"));
        System.out.println("attemptsAfterFailure=" + attempts.get());

        int updated = values.compute("ready", (key, oldValue) -> oldValue + 5);
        System.out.println("updated=" + updated);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComputeOutcomesDemo.java
java ComputeOutcomesDemo
```

Stdout:

```text
ready=10, attempts=0
missingPresent=false
attemptsAfterNull=2
failure=IllegalArgumentException
readyAfterFailure=10
attemptsAfterFailure=3
updated=15
```

There are four observations in this program:

1. Key `ready` already exists. The value-creating lambda does not run on the first call, so `attempts` remains 0.
2. Both calls for `missing` return `null`. No result is retained for the next call, so the counter increments twice.
3. The callback for `ready` increments the counter and then throws an exception. The mapping still points to 10, while the counter is now 3.
4. The final addition has no side effects; it returns 15 to update the mapping.

The counter is an observation instrument for the experiment. In business code, replacing the counter with a financial debit or an outbound request makes the same sequence far more serious. A failed computation does not automatically roll back an action that already completed before the failure.

### "Once" Must Be Tied to a Specific Scope

You need to separate these questions:

- Did the callback run during the **current call**?
- Might other calls need to recompute after `null`, an exception, or key removal?
- How many candidates were created before a value was retained?
- What external side effects occurred during those computations?

The example above intentionally makes two separate calls for `missing`; there is no contradiction when the data-producing function runs twice. If a service returns `null` to mean "not found," repeating the request may be either the desired policy or a cache design bug. If you want to cache the "not found" result as well, represent it with an explicit value and decide how long to retain that result.

Do not interpret the word "atomic" as a guarantee that data is loaded strictly once over the lifetime of the program. Key lifecycle, eviction policy, and error-handling policy are still decided by the application.

## 4. Recursive Updates: The Computing Function Loops Back to What Is Being Computed

Recursion in this context is not just a Java method calling itself. What you need to look for is **a call path that loops back to update the map before the earlier callback has finished**.

### 4.1. Same Key, Same Map

Consider the dependency chain:

```text
Need to create value for A
    -> callback for A runs
        -> requests creating value for A again
            -> the first value for A cannot be returned yet
```

The inner call needs to complete the very work that the outer call is currently performing. Adding `synchronized` around the lambda will not make the missing value appear. The problem lies in the dependency relationship.

The following program intentionally violates the constraint to observe the error, not as a caching pattern. It uses a fresh map, one key, and one thread; you do not need to run a race between threads to see the issue.

File `RecursiveUpdateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;

public class RecursiveUpdateDemo {
    public static void main(String[] args) {
        var values = new ConcurrentHashMap<String, Integer>();
        try {
            values.computeIfAbsent("A", key ->
                    values.computeIfAbsent("A", nestedKey -> 42));
            System.out.println("unexpected success");
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
        System.out.println("containsA=" + values.containsKey("A"));
        System.out.println("size=" + values.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RecursiveUpdateDemo.java
java RecursiveUpdateDemo
```

Stdout:

```text
failure=IllegalStateException
containsA=false
size=0
```

On the JDK 17 used to verify this lesson, the call is detected and throws `IllegalStateException`; no mapping for A is created. Do not rely on the specific error message text, because the message content is not something to use for business decisions.

**Do not treat the presence or absence of an exception as a validity test for your design.** This program demonstrates one case that is detected. It does not prove that every recursive call path, every locking scheme, and every JVM version is diagnosed in the same way.

### 4.2. Different Keys Still Require Checking the Call Path

A common "fix" is to change the inner call to B:

```java
// INCORRECT illustrative code; do not run as a solution.
cache.computeIfAbsent("A", key ->
        cache.computeIfAbsent("B", otherKey -> "value"));
```

Using a different key name does not eliminate modifying the same map inside the callback. Current test data might happen to pass, and then changing the hash distribution or adding a data-loading branch will expose the problem. Remove the nested update path instead of looking for a pair of keys that makes the code happen to run.

If A needs information from B to be constructed, resolve it at the computation layer: compute the dependencies outside the callback, pass in a ready result, or organize a workflow that manages dependency relationships. Only once the results are ready does the step of publishing into the map take place.

### 4.3. Helper Methods Can Hide a Call Cycle

Consider this illustrative snippet, which is not a standalone program:

```java
// INCORRECT illustrative code: you must read the entire call path of load().
Value value = cache.computeIfAbsent(key, this::load);

// If load() or a function it calls modifies cache again,
// the constraint is still violated even though the lambda does not contain the name cache.
```

When reviewing `load`, do not look only for a direct call. Object constructors, dependency resolvers, user-supplied extension code, or event-logging functions can all call back into the service using the map.

A practical question is: "Before the callback returns, can any code on the call path request creating or modifying an entry in the same data store?" If you cannot determine that, you need to narrow the callback's responsibilities.

### 4.4. Two Different Maps Can Also Create a Wait Cycle

The restriction against modifying the same map is not a tool that detects every deadlock in an application. Imagine:

```text
Thread 1: computing an entry in map M -> needs work in map N
Thread 2: computing an entry in map N -> needs work in map M
```

Even though each function only sees a call "to another map," together they can form a dependency cycle. You must examine resource acquisition order, wait paths, and data dependencies across the entire workflow.

Therefore, a practical rule is to separate local transformations from workflow orchestration. The more services, keys, and data sources a callback has to know about, the harder it is to prove that it will terminate.

## 5. Long-Running Tasks: Computing the Right Result Is Not Enough for Progress

A non-recursive callback can still cause trouble if it holds the update work for too long. For example:

- Waiting for an HTTP connection or response.
- Reading files, querying a database, waiting on an external lock.
- CPU-intensive computation on large data.
- Calling `get()` or `join()` on an incomplete task.
- Running a retry loop without a clear termination bound.

"Short" does not have a universal millisecond number for every system. Consider whether the work blocks on external resources, whether its volume is bounded, and how many requests might have to wait for it.

In the OpenJDK 17 implementation, entries are organized into hash bins and some updates coordinate via bin-level locks. A long-running computation can delay updates to other entries in the same bin; you should not assume each key has a completely isolated waiting mechanism. This is an explanation of the implementation, not a locking interface for applications to rely on. See the [OpenJDK 17 ConcurrentHashMap design notes](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java).

### 5.1. Observing While a Value Is Not Yet Published

The next experiment intentionally holds the callback at a wait gate to observe the state. This is a learning instrument, not a pattern to put into a real callback. It does not use `Thread.sleep` to guess how far a thread has progressed.

File `WaitingComputeDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class WaitingComputeDemo {
    public static void main(String[] args) throws Exception {
        var values = new ConcurrentHashMap<String, String>();
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);

        try {
            var first = pool.submit(() ->
                    values.computeIfAbsent("A", key -> {
                        entered.countDown();
                        try {
                            if (!release.await(10, TimeUnit.SECONDS)) {
                                throw new IllegalStateException("release timeout");
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                        return "first";
                    }));

            if (!entered.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("entry timeout");
            }
            System.out.println("getWhileComputing=" + values.get("A"));

            var second = pool.submit(() -> values.put("A", "second"));
            release.countDown();

            System.out.println("firstResult=" + first.get(10, TimeUnit.SECONDS));
            System.out.println("secondPrevious=" + second.get(10, TimeUnit.SECONDS));
            System.out.println("finalValue=" + values.get("A"));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WaitingComputeDemo.java
java WaitingComputeDemo
```

Stdout:

```text
getWhileComputing=null
firstResult=first
secondPrevious=first
finalValue=second
```

The `entered` gate signals that the first callback has started. The `release` gate is held until after the main thread calls `get("A")`. At that moment, the `"first"` result has not yet been returned by the callback, so the read does not see a mapping for A.

After opening the gate, the first call returns `"first"`; the subsequent `put` receives the previous value `"first"`, and then the map holds `"second"`.

The limits of this observation should be stated clearly:

- The program does not print timings and does not measure average or maximum latency.
- Having `submit`ted the second task does not prove it was immediately executed by the CPU.
- The 10-second timeout is used to detect an experiment failing to make progress in the runtime environment; it is not an API timeout.
- The publication order of data is controlled by the wait gates and fetching results, not by machine speed.
- One successful run does not test all possible execution schedules of another program.

A read returning `null` is also not an application signal you can use to assert "nobody is computing A." It is simply the value of that read. If business logic needs to distinguish missing data from in-progress loading, the data model must represent the loading state.

### 5.2. External Waiting Can Bring Everything to a Halt

Consider this design scenario, not runnable code:

```text
Callback A waits for the result of task T
T needs to update A before completing
Callback A only finishes after T completes
```

Offloading T to an `ExecutorService` does not automatically break the dependency cycle. If the callback calls `future.get()` right after submitting T, the waiting relationship still exists.

There is another form at the executor level: all threads in a pool are waiting for new tasks queued to that same pool. When no free threads remain to execute the new tasks, work cannot make progress. A concurrent map does not solve thread allocation or this dependency ordering.

Before using a blocking wait call, determine who can complete the awaited work and whether that party needs resources held by the waiter.

## 6. First Approach: Compute Outside, Publish with `putIfAbsent`

When duplicate data creation is acceptable, a simple approach is:

```text
Create candidate outside callback
    -> attempt to publish with putIfAbsent
        -> if a prior value exists, use the prior value
        -> if none exists, use the candidate just published
```

This is a design choice derived from separating "creating a candidate" and "selecting the stored value." The goal is to keep the update step short and clear, at the cost of potentially creating candidates multiple times.

File `OutsideCandidateDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class OutsideCandidateDemo {
    record Data(String text) {}

    public static void main(String[] args) throws Exception {
        var values = new ConcurrentHashMap<String, Data>();
        var candidates = new AtomicInteger();
        var bothCreated = new CyclicBarrier(2);
        var pool = Executors.newFixedThreadPool(2);

        try {
            java.util.concurrent.Callable<Data> request = () -> {
                Data candidate = new Data("loaded");
                candidates.incrementAndGet();
                bothCreated.await(10, TimeUnit.SECONDS);
                Data existing = values.putIfAbsent("A", candidate);
                return existing == null ? candidate : existing;
            };

            var first = pool.submit(request);
            var second = pool.submit(request);
            Data left = first.get(10, TimeUnit.SECONDS);
            Data right = second.get(10, TimeUnit.SECONDS);

            System.out.println("candidates=" + candidates.get());
            System.out.println("samePublishedObject=" + (left == right));
            System.out.println("storedText=" + values.get("A").text());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OutsideCandidateDemo.java
java OutsideCandidateDemo
```

Stdout:

```text
candidates=2
samePublishedObject=true
storedText=loaded
```

`CyclicBarrier` forces both tasks to finish creating their candidates before proceeding together to the publication step. Thus the candidate count is always 2 in this experiment. Two independent `Data` objects have the same content `"loaded"`.

Both sides return the object that was selected for the map. The expression `left == right` checks reference identity, not just content equality. The output clearly illustrates: **two candidate creations, yet one shared object**.

### 6.1. What You Must Accept When Using This Approach

If the work outside the map only reads a data source, duplicate loading may be an acceptable cost. If it is an action that must not be repeated, such as allocating a limited external resource, you need a different design or a guarantee mechanism in the system that owns that action.

If a candidate holds closeable resources, the losing side must release its own candidate according to the resource contract. Do not close the winning object that is being used by the map and other callers.

The experiment uses a previously absent key and no interleaved removals. In a real cache, "winning the object selection" does not mean it will stay in the map forever. Another thread can remove or replace the data after publication. If this affects business logic, you must specify the lifecycle and invalidation strategy.

### 6.2. Why Not Use `put` So the Last One Wins?

If all callers `put` their own candidate, a later one can overwrite the value the earlier one just published. When callers need to use the same result for the current creation round, that is a different policy.

The approach above intentionally selects the first publisher and returns that same object to competing callers. It does not solve "which data is newest" if each candidate represents a different version. For versioned data, the selection step must inspect versions or follow a clearly defined business rule.

## 7. Second Approach: Publish a Task, Then Perform the Work Outside the Map

If duplicate loading must be avoided within the same load round, you can have the map hold **an object representing the result being computed**, instead of only holding the final result.

```text
Map: key -> FutureTask

1. Find or publish a FutureTask that has not run yet.
2. Exit the map update operation.
3. Call run() on the selected task.
4. Retrieve the result from that same task.
```

`FutureTask` wraps a `Callable`, holds the result or error state, and provides `get()` to wait for the result. It performs the computation once for the normal lifecycle of the object; constructing a `FutureTask` does not automatically start the work. See [FutureTask in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).

The pattern below is a minimal illustrative cache that holds only strings. The loader function is the same for all keys to focus on the coordination mechanism; a real application needs to pass the key to an appropriate loader.

File `SharedTaskDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedTaskDemo {
    static final class Memo {
        private final ConcurrentHashMap<String, FutureTask<String>> tasks =
                new ConcurrentHashMap<>();
        private final Callable<String> loader;

        Memo(Callable<String> loader) {
            this.loader = loader;
        }

        String get(String key) throws InterruptedException, ExecutionException {
            FutureTask<String> task = tasks.get(key);
            if (task == null) {
                FutureTask<String> candidate = new FutureTask<>(loader);
                FutureTask<String> existing = tasks.putIfAbsent(key, candidate);
                task = existing == null ? candidate : existing;
            }

            // Run outside every map callback; concurrent run calls are safe.
            task.run();
            try {
                return task.get();
            } catch (ExecutionException | CancellationException ex) {
                tasks.remove(key, task);
                throw ex;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        var calls = new AtomicInteger();
        var memo = new Memo(() -> {
            calls.incrementAndGet();
            return new String("data");
        });
        var start = new CyclicBarrier(2);
        var pool = Executors.newFixedThreadPool(2);

        try {
            Callable<String> request = () -> {
                start.await(10, TimeUnit.SECONDS);
                return memo.get("A");
            };
            var first = pool.submit(request);
            var second = pool.submit(request);
            String left = first.get(10, TimeUnit.SECONDS);
            String right = second.get(10, TimeUnit.SECONDS);

            System.out.println("loaderCalls=" + calls.get());
            System.out.println("sameResultObject=" + (left == right));
            System.out.println("cachedAgain=" + memo.get("A"));
            System.out.println("loaderCallsAfterHit=" + calls.get());

            var retryCalls = new AtomicInteger();
            var retryMemo = new Memo(() -> {
                if (retryCalls.incrementAndGet() == 1) {
                    throw new IllegalStateException("temporary failure");
                }
                return "recovered";
            });
            try {
                retryMemo.get("B");
            } catch (ExecutionException ex) {
                System.out.println("firstFailure=" +
                        ex.getCause().getClass().getSimpleName());
            }
            System.out.println("retryResult=" + retryMemo.get("B"));
            System.out.println("retryCalls=" + retryCalls.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SharedTaskDemo.java
java SharedTaskDemo
```

Stdout:

```text
loaderCalls=1
sameResultObject=true
cachedAgain=data
loaderCallsAfterHit=1
firstFailure=IllegalStateException
retryResult=recovered
retryCalls=2
```

### 7.1. Tracking Who Does the Work at Each Step

`tasks.get(key)` looks up the currently held task. If none is found, the caller creates a candidate `FutureTask` and uses `putIfAbsent` to select one task.

The candidate here is only an object wrapping the work. Creating it does not run `loader`. Losing candidates do not trigger corresponding data loads. That is the difference from performing the full load operation before `putIfAbsent` in the previous section.

After the selection step, every caller uses the `task` variable pointing to the winning task. They can all call `run()`; the work of that `FutureTask` object is still executed only once. Subsequent calls continue to retrieve the same result.

**`run()` here runs synchronously on a calling thread.** Writing it this way allows another caller to start the published task if the publisher has not yet called `run`. It does not spawn a new thread and is not an asynchronous API for users of `Memo`.

You need to distinguish two aspects of long-running work:

- The thread calling `Memo.get` may still be busy or waiting during a slow load.
- That thread performs the long part after exiting the map update operation.

This pattern addresses the scope of work held inside the update operation; requirements for freeing calling threads, limiting concurrent loads, and supporting cancellation must be designed separately.

### 7.2. Reading Failure Results and Retry Policies

In the retry portion, the first load throws `IllegalStateException`. The caller of `get()` receives an `ExecutionException` wrapping that cause. The program prints the cause class name, removes that exact failed task, and then the next call creates another task and receives `"recovered"`.

When retrieving a result successfully via `Future.get()`, actions in the computation have a happens-before relationship with actions after `get()` on the receiving thread. `get()` also distinguishes computation errors, interruption, and cancellation. See the [Future contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html#get()).

Thus, in this model there are two separate points in time: publishing the task object into the map and completing the result that the task represents. Seeing the task does not mean the result is ready.

Removing a failed task is **this example's policy**, not a requirement for every cache. Some systems want to retain an error for a period to avoid overloading a failing source. Some systems allow retries with exponential backoff. Whichever you choose, you must specify when one load round ends and the next is allowed to begin.

### 7.3. Why Must You Use `remove(key, task)`?

Let us call the old failed task F1 and the new task F2:

```text
Caller A receives F1's failure and removes F1
Caller B creates and publishes F2 for the same key
Caller C also just received F1's failure and needs to clean up
```

If C calls `remove(key)`, it might accidentally remove F2. The statement `remove(key, task)` only cleans up the mapping if it still points to the task being handled. With the `FutureTask` objects in the example, this is an identity check for the expected object.

This reasoning also applies to many stateful work items: cleaning up an old session must carry an identifier for that session. Do not remove unconditionally just because the key has the same name.

### 7.4. Limitations Left Explicit in the Pattern

The pattern has no expiration time, maximum capacity, or automatic eviction of successful results. If the number of keys grows indefinitely, the number of retained tasks grows accordingly. To use it in a long-lived application, you must choose a lifecycle policy.

The pattern does not expose a task cancellation method. An interrupted waiter does not automatically remove the shared task, because others may still need it. If you add cancellation, you must decide who has the authority to cancel shared work and when it can be removed from the map.

If `loader` returns `null`, that result lives inside the `FutureTask`; the map value is still a task object. This is a different situation from a `computeIfAbsent` callback returning `null`. You must decide separately whether to retain empty load results.

Finally, the pattern assumes loader functions do not call back to wait on the very work they are performing. If loading A calls `memo.get("A")`, it can end up waiting on task A itself. If A waits for B and B waits for A, a wait cycle still exists even though no map callback wraps the loading work.

Publishing a `FutureTask` helps represent the loading state; it does not automatically prove the dependency graph is acyclic.

## 8. Why Just Adding `CompletableFuture` Is Not Enough

A seemingly quick approach is to return a `CompletableFuture` from the callback. You must examine how it is created, its execution schedule, and where completion handlers are placed.

The following example only illustrates an idea to analyze; it is not a standalone program:

```java
// Illustrative code whose execution path needs careful examination.
CompletableFuture<Value> future = cache.computeIfAbsent(key, k ->
        CompletableFuture.supplyAsync(() -> load(k), executor));
```

There are three distinct events in that short snippet: the callback runs, the task is submitted to the executor, and the actual loading task runs. Do not lump them together into a single milestone of "finished loading."

In particular, completion stages without the `Async` suffix can run directly on the completing thread or the thread joining completion. `CompletableFuture` also does not directly control the underlying work producing the result to guarantee that cancellation stops I/O. See [CompletableFuture execution and cancellation policies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

Based on these policies, you need to check specific call paths:

- Can the supplied executor run the command directly on the calling thread?
- Does the rejection policy when capacity is full run the work on the submitter?
- Can the task complete before the callback creating it returns?
- Does error-cleanup code call `cache.remove` back inside the still-active callback?
- Does anything call `join()` inside the callback, turning the offloaded work into a blocking point?

An easier-to-reason-about design is to publish a work-representing object first, finish the map operation, and then start execution and attach lifecycle handling outside that region. That is the design direction; the details must also handle executor task rejection, task failures, and concurrent cleanup by callers.

If task submission fails while an incomplete future remains waiting in the map, later callers will receive an object that nobody can complete. You must complete it with an error state or clean up the exact object according to your chosen policy.

Similarly, one waiter timing out does not mean the data source has stopped. Do not unconditionally remove shared work just because one request can no longer wait; a new load round could start while the old one is still running.

## 9. How to Diagnose Bugs in Existing Code

When you see a thread stalling in `compute` or `computeIfAbsent`, examine both the callback's call path and where it is waiting. Just looking at the map's name or the fact that the class has "Concurrent" in its name is not enough to determine the cause.

### 9.1. Symptoms and Investigation Directions

| Symptom | What to check | Grounded change direction |
|---|---|---|
| `IllegalStateException` when creating a value | Does the callback loop back to modify the same map directly or via another method? | Separate data construction from publication |
| Multiple updates stall together while loading one item | Does the callback do I/O, heavy computation, or wait on another task? | Move the long part outside the update operation |
| Data is loaded multiple times | Are there `null`s, errors, key removals, or multiple candidates computed outside? | Define lifecycle and choose an appropriate coordination approach |
| Waiting on a future that never completes | Who actually starts and who completes the task? Is there a dependency cycle? | Fix waiting relationships and also handle task submission failures |
| New task disappears after an old failure | Is cleanup using `remove(key)`? | Clean up conditionally matching the exact task object |
| Mapping stays unchanged, but inner data changed | Did the callback mutate the old object directly before throwing? | Create a new result or use a separate state-management mechanism |

The last column gives directions for design inspection, not a one-size-fits-all recipe. For example, creating a new result can be expensive if the value is a large dataset; in that case, design appropriate data structures and synchronization boundaries rather than copying mechanically.

### 9.2. Distinguish the Mapping from the Mapped Object

Consider this intentionally problematic snippet, not a standalone program:

```java
// INCORRECT illustrative code: oldList is an object that may be shared.
cache.compute(key, (k, oldList) -> {
    oldList.add("new");
    throw new IllegalStateException("failed");
});
```

If the map already pointed to `oldList`, the fact that the mapping was not replaced does not make the added element disappear. The referenced object has been mutated. Nor can you infer from this that other threads are allowed to freely read or mutate a shared `ArrayList` just because it resides in a concurrent map.

In a design using immutable values, the callback can build a new value from the old value and return it after validation completes. Understand the copying cost and depth of immutability; an outer wrapper does not automatically make nested data immutable.

### 9.3. Observability Data Should Separate Wait Time from Work Time

When analyzing a real system, distinguish:

- Time spent finding or publishing the entry in the map.
- Time spent waiting on an existing load round.
- Time spent loading at the data source.
- Number of discarded candidates, retries, and waiting tasks.
- Errors caused by data, transient source unavailability, and failure to obtain an execution thread.

Do not add a slow, blocking logging operation inside the callback just to measure the callback. You can capture timings at an outer boundary, keep measurement data local, and handle logging in a design that does not worsen the bottleneck you are investigating.

For deadlocks, thread dumps and wait graphs are more useful than a single total-duration metric. For slowdowns under high load, you need key distribution, concurrent load counts, and queue depths. The small experiments in this lesson help you understand the mechanisms; they do not replace application-specific measurements.

## 10. Practice and Design Self-Check

### Exercise 1: Identifying Hidden Recursive Updates

A method `getProduct(id)` calls `computeIfAbsent`. The callback calls `buildProduct(id)`; that builder calls `getProduct(parentId)` to fetch the parent product.

Answer the following:

1. Is `parentId` being different from `id` enough to prove safety?
2. If the parent relationship forms a cycle A -> B -> A, which side can complete first?
3. If there is no data cycle, has modifying the same map inside the callback been eliminated?

Explanation guide: a different key does not permit nested updates in the same map. Dependency cycles must be detected at the model or loading-workflow layer. You can build dependencies outside the callback and then publish the result, or use a loading mechanism that explicitly manages the dependency graph.

### Exercise 2: Deciding Whether Duplicate Candidate Creation Is Acceptable

A configuration read operation takes a long time but has no side effects on the source. Two callers loading in duplicate and keeping only one result is acceptable. Choose the approach of computing outside the map followed by `putIfAbsent`, and state the duplicated resource cost.

Next, replace the read operation with allocating a unique ID from an external system. Explain why "the map keeps only one value" does not reclaim the ID allocated for the losing candidate. If the action must avoid duplication across multiple processes or machines, coordination within a single map object in one JVM is insufficient; the guarantee must exist at the boundary of the system that owns the action.

### Exercise 3: Failure Cleanup Policy and Cancellation Authority

With the `SharedTaskDemo` pattern, suppose two callers are waiting on F1. One receives a failure and removes F1; then another caller publishes F2.

- If the remaining caller of F1 cleans up using `remove(key)`, what can happen?
- Why does `remove(key, F1)` preserve F2?
- If one user stops waiting while F1 is still incomplete, should the work be canceled for everyone?

Explanation guide: cleanup must be tied to the exact work instance. Cancellation authority must be defined; one caller no longer needing the result does not automatically mean others do not need it either.

### Exercise 4: Removing a Blocking Wait Call from a Callback

Given this illustrative flow:

```text
computeIfAbsent
    -> submit task to executor pool
    -> call get to wait
    -> return data
```

Redraw it into two steps: publishing a work-representing object, then executing or waiting outside the map operation. Next, add a branch for the executor rejecting the task. Each branch must indicate who is responsible for bringing the waiting object to a completed state or removing it conditionally.

Do not just delete the `get` line and consider the problem solved. The map's value type, how results are retrieved, and the error policy must all be consistent with the in-progress loading state.

### Questions to Answer Before Keeping a Callback

1. Does the callback only compute the result for the mapping currently being processed?
2. Do all methods it calls avoid looping back to modify the same map?
3. Is the workload clearly bounded and free of waiting on I/O or other tasks?
4. If it returns `null` or throws an error, what will the next call do?
5. Was any external side effect or shared object mutated before an error occurred?
6. When moving the long part outside, is duplicate creation acceptable, or is a shared task required?
7. If sharing a task, who starts it, who completes it, who has authority to cancel it, and who is allowed to clean it up?
8. Is there any dependency path that could cause work to wait on itself or wait in a cycle?

A good design should be able to explain both **the selected value** and **how the work progresses to a result**. Keeping callbacks local, short, and clearly scoped makes both parts easier to verify in code and in operations.
