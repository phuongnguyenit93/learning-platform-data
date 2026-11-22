# Stateless Objects and Avoiding Shared State in Java Concurrency

## 1. Why does a stateless design help with thread safety?

A familiar scenario: multiple threads concurrently call a shared object. If each call writes its own temporary data into a field of the object, a later call can overwrite data that an earlier call has not finished using. That is a common form of race condition, even when each individual method looks very simple.

**A stateless design (not retaining mutable state per task)** eliminates many sources of races right from the program's structure: each call receives its inputs, computes using local variables, and returns a result; data being processed is not stored in shared instance or static fields. When there is no shared mutable state, no lock is needed merely to protect intermediate data of independent calls.

After this lesson, you will be able to:

- Distinguish **stateless object**, **immutable object**, **thread-confined state**, and **thread-safe stateful object**.
- Accurately identify where shared mutable state exists, including static fields, collections, objects passed by reference, lambda captures, and external dependencies.
- Recognize the bug of storing per-task data in a field; understand why making individual getters/setters `synchronized` cannot save a sequence of dependent actions.
- Refactor designs to pass data via parameters, use local variables, return values, immutable snapshots, and combine results after tasks complete.
- Know the limits: a stateless Java object can still cause concurrency bugs if it calls a non-thread-safe dependency or operates on stateful external resources.
- Compile/run Java 17+ examples to clearly see both the bug and the fix, along with a code review checklist.

The scope of this lesson is **Java SE/JVM concurrency** only, without depending on any framework.

## 2. Three questions that must be kept separate

The following three concepts are related, but they are **not synonymous**:

| Concept | Characteristics | Example |
|---|---|---|
| **Stateless** | Does not retain mutable data between calls that can affect the result of another call; task data lives in parameters/locals/results. | A string normalization function that only takes an input and creates a new string. |
| **Immutable** | An object's state does not change after proper construction; it may have fixed configuration state. | A record containing `String`, `int`; `BigDecimal`; a policy with final immutable settings. |
| **Thread-safe** | Has a contract to behave correctly when accessed by multiple threads in supported ways. Can be stateless, immutable, or synchronized stateful. | `AtomicInteger` is thread-safe yet **stateful**; a counter with `synchronized` methods is also stateful. |

A **strictly stateless** object does not need to store call-dependent state. However, in practice people also call a *stateless service* one that holds fixed **immutable configuration** (such as a tax rate), because it does not store per-request progress or data. To put it precisely: that service **holds no mutable per-call state**, rather than having no fields at all.

**Thread safety is a property of the entire protocol for using an object**, not just of a class name or annotation. A method can hold no fields and still be unsafe if it mutates a shared `List`, accesses static mutable state, or interacts with a non-thread-safe dependency.

### Distinguishing data scopes

~~~text
                 A single shared instance
             ┌───────────────────────────┐
Thread A ───▶│ method(inputA)            │
             │   localA = ...            │──▶ resultA
             │                           │
Thread B ───▶│ method(inputB)            │
             │   localB = ...            │──▶ resultB
             └───────────────────────────┘
                   NO shared mutable
                    per-call fields

Unlike:
             ┌───────────────────────────┐
Thread A ───▶│ this.currentInput = "A"  │
Thread B ───▶│ this.currentInput = "B"  │
             │ uses this.currentInput    │
             └───────────────────────────┘
               Reading/writing the same field
~~~

Two independent local variables in two executions do not become a shared variable just because two threads call the same instance method. Each call has its own local variables and parameters semantically. However, a **reference value** in a local variable can point to the same mutable object; simply having a local variable name does not guarantee that the referenced object is private.

## 3. Where does shared state come from?

A value becomes a source of risk when the following conditions hold:

1. It can be accessed by multiple threads over overlapping time intervals.
2. At least one thread can **mutate** that same state.
3. There is no ownership or synchronization protocol guaranteeing safety for those concurrent accesses.

Common sources of shared state:

| Where it lives | Example | What to check |
|---|---|---|
| Instance field | `this.lastInput`, `this.buffer` | Is the same instance shared among multiple workers? |
| Static field | `static int requestCount` | Multiple instances still write to the same class-level field. |
| Collection passed into a method | `List`, `Map`, `Set`, array | Do callers hold the same reference and mutate it concurrently? |
| Object inside a collection | `Map<String, MutableValue>` | A thread-safe Map does not automatically make mutable values thread-safe. |
| Dependency held inside a service | client, formatter, accumulator, cache | Does the dependency have mutable state and is it used concurrently? |
| Lambda/closure | A `Runnable` capturing a `List`, `AtomicInteger`, or object | Captured local variables can point to a shared mutable object. |
| File, DB, socket, external process | writing the same file, updating the same record, sending on the same session | Data outside the JVM has its own ordering and invariants. |
| `ThreadLocal` | per-thread data | Not stateless; a worker pool can retain state across multiple tasks. |

In particular, **`final` only locks the field reference**, not the object it points to:

~~~java
final class UnsafeTags {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    void add(String tag) {
        tags.add(tag); // still mutates the shared ArrayList
    }
}
~~~

This is an illustrative class snippet without a standalone `main`. The `final` field cannot be reassigned to another `List`, but the contents of the `ArrayList` remain mutable. If multiple threads call `add` concurrently, `ArrayList` provides no thread-safety guarantees.

## 4. Bug example: storing per-task input in a field

Suppose a formatter serves multiple calls:

~~~java
class StatefulLabelService {
    private String lastLabel;

    void remember(String label) {
        lastLabel = label;
    }

    String render() {
        return "[" + lastLabel + "]";
    }
}
~~~

The caller expects the call sequence `remember("A")` followed by `render()` to return `[A]`. But if another thread manages to call `remember("B")` before `render()`, the result becomes `[B]`. This is a **cross-request interference** bug: one task's data leaks into another task.

A common misconception: "Adding `synchronized` to `remember` and `render` will make it fine." Locking each method individually only gives each method mutual exclusion while it runs; the **pair** `remember` → `render` can still interleave with another task:

~~~text
Thread A                  Thread B
remember("A")
                          remember("B")
render() -> "[B]"
                          render() -> "[B]"
~~~

Even if both `remember()` and `render()` are `synchronized`, the execution schedule above is still valid because the monitor is released between the two calls. To preserve the consistency of the **entire sequence**, you must design a single atomic method or hold one lock across the whole sequence. The simpler solution here is **not storing `lastLabel` in a shared field**.

## 5. Standalone runnable example: staging the bug and the stateless design

The following example uses `CountDownLatch` to create a deterministic execution schedule. Thread A writes `"A"`, thread B overwrites `"B"`, and then both read the same shared field. Next, the program has two threads use **the same `StatelessLabelService`**, but each call keeps its input in a parameter; each caller gets the right result.

Save the file **StatelessServiceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class StatelessServiceDemo {
    static final class StatefulLabelService {
        private String lastLabel;

        void remember(String label) {
            lastLabel = label;
        }

        String render() {
            return "[" + lastLabel + "]";
        }
    }

    static final class StatelessLabelService {
        String format(String label) {
            String normalized = label.trim();
            return "[" + normalized + "]";
        }
    }

    public static void main(String[] args) throws InterruptedException {
        StatefulLabelService bad = new StatefulLabelService();
        CountDownLatch aWritten = new CountDownLatch(1);
        CountDownLatch bWritten = new CountDownLatch(1);
        String[] badResults = new String[2];

        Thread a = new Thread(() -> {
            try {
                bad.remember("A");
                aWritten.countDown();
                bWritten.await();
                badResults[0] = bad.render();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "bad-A");

        Thread b = new Thread(() -> {
            try {
                aWritten.await();
                bad.remember("B");
                bWritten.countDown();
                badResults[1] = bad.render();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "bad-B");

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("stateful A=" + badResults[0]);
        System.out.println("stateful B=" + badResults[1]);

        StatelessLabelService good = new StatelessLabelService();
        String[] goodResults = new String[2];
        Thread c = new Thread(
                () -> goodResults[0] = good.format("A"), "good-A");
        Thread d = new Thread(
                () -> goodResults[1] = good.format("B"), "good-B");

        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("stateless A=" + goodResults[0]);
        System.out.println("stateless B=" + goodResults[1]);
    }
}
~~~

Run with JDK 17+:

~~~bash
javac StatelessServiceDemo.java
java StatelessServiceDemo
~~~

Output when there is no external interruption:

~~~text
stateful A=[B]
stateful B=[B]
stateless A=[A]
stateless B=[B]
~~~

**Why the output is deterministic:**

- `aWritten` forces B to wait until A finishes writing, then B writes `"B"` before A proceeds. `bWritten` forces A to wait until B finishes writing before reading the field, so A sees `"B"`.
- B reads immediately after writing `"B"`; there are no other writes. Therefore, both stateful results are `[B]`.
- The two `good` threads call `format` on **the same instance**, but the method only uses `label` and the local `normalized`, creating a new `String`; there is no shared mutable field to overwrite.
- Each thread writes to its **own slot** in the result array; `main` reads after joining all corresponding threads. `join()` provides a happens-before relationship so `main` observes the completed results.
- The latches are used **to stage the buggy ordering**, not to fix a shared state. The real fix in the `good` part is removing the field that held per-call data.

The example is intentionally simple to demonstrate **correctness/incorrectness of call independence**, not a benchmark. Do not use `Thread.sleep` to manufacture a "guaranteed race," because sleep duration does not guarantee execution order.

## 6. Refactor: turn a method into an input → output transaction

Instead of:

~~~java
class Formatter {
    private String currentUser;

    void setUser(String user) {
        currentUser = user;
    }

    String greeting() {
        return "Hello, " + currentUser;
    }
}
~~~

Redesign as:

~~~java
class Formatter {
    String greeting(String user) {
        String normalized = user.strip();
        return "Hello, " + normalized;
    }
}
~~~

The new method has two properties:

1. The `user` data is passed into **the specific call**, without needing a write to the instance to prepare for a subsequent read.
2. The result is **returned directly** to the caller. There is no `lastResult` or `currentUser` that another task can overwrite.

Here `String` is immutable, and `strip()` returns a corresponding `String` rather than mutating the input. Therefore, callers do not share mutable working state through the method.

**API design note:** A method that processes multiple parameters can accept an immutable input object (`record`) to keep semantics clear. Avoid two-step `setContext(x)` then `execute()` designs on a shared object, as that introduces temporal coupling that easily causes races when multiple threads call it concurrently.

## 7. Stateless service with immutable configuration

In real applications, an object may need fixed configuration: rates, formatting rules, default limits, or an immutable list of policies. Holding immutable config is not the same as storing per-request state.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

final class PriceCalculator {
    private final BigDecimal taxRate;

    PriceCalculator(BigDecimal taxRate) {
        this.taxRate = Objects.requireNonNull(taxRate);
    }

    BigDecimal total(BigDecimal amount) {
        Objects.requireNonNull(amount);
        return amount.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`PriceCalculator` has **immutable configuration state** `taxRate`, but does not record separate state for each calculation. `BigDecimal` is immutable; the calculation produces a new value. If the object is constructed and **safely published** to workers, multiple threads can call `total()` concurrently without needing a lock to protect this calculation itself.

### Standalone example with ExecutorService

Save **StatelessPriceDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StatelessPriceDemo {
    static final class PriceCalculator {
        private final BigDecimal taxRate;

        PriceCalculator(BigDecimal taxRate) {
            this.taxRate = Objects.requireNonNull(taxRate);
        }

        BigDecimal total(BigDecimal amount) {
            Objects.requireNonNull(amount);
            return amount.multiply(BigDecimal.ONE.add(taxRate))
                    .setScale(2, RoundingMode.HALF_UP);
        }
    }

    public static void main(String[] args) throws Exception {
        PriceCalculator calculator =
                new PriceCalculator(new BigDecimal("0.08"));

        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Future<BigDecimal> a = workers.submit(() ->
                    calculator.total(new BigDecimal("100.00")));
            Future<BigDecimal> b = workers.submit(() ->
                    calculator.total(new BigDecimal("50.00")));

            System.out.println("A=" + a.get());
            System.out.println("B=" + b.get());
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Commands:

~~~bash
javac StatelessPriceDemo.java
java StatelessPriceDemo
~~~

Output:

~~~text
A=108.00
B=54.00
~~~

**Why is it safe for both tasks?**

- The calculator is fully initialized **before** being captured into the `Runnable`/`Callable` submitted to the executor. `ExecutorService`'s memory consistency contract guarantees that actions prior to submission happen-before actions of the task; the task sees the state established by the constructor.
- `taxRate` is a `final` reference to an immutable `BigDecimal`. No task updates it.
- Each call to `total` uses its own parameter, creates a new `BigDecimal` result, and writes no instance fields.
- `Future.get()` waits for the task to complete and also establishes a happens-before relationship for the caller to observe the result.
- Printing in the order `a.get()` then `b.get()` does not require task A to finish before B. The two tasks may be scheduled in any order.
- `shutdown()` closes acceptance of new tasks; the example already calls `get()` on both `Future`s before leaving `try`. In a real lifecycle, you also need timeouts/cancellation and handling for failed or non-terminating tasks.

Important point: **a `final` reference is not enough if the configuration object itself is mutable**. For example, `private final ArrayList<String> rules` still allows `rules` to be mutated after the constructor, which can cause races. Copy/freeze to the required depth and use immutable elements when needed.

## 8. Patterns for avoiding mutable shared state

### Pattern A — Move per-task data into parameters

Replace `this.input = x; process()` with `process(x)`; return a value instead of writing `this.lastResult`.

~~~java
String normalize(String input) {
    return input.strip().toLowerCase(java.util.Locale.ROOT);
}
~~~

This illustrative method stores no state and creates a new `String`. `Locale.ROOT` is useful when technical normalization should not depend on the user's locale; actual normalization rules should follow the domain.

### Pattern B — Keep intermediate values in local variables

~~~java
long sumSquares(int[] source) {
    long total = 0;
    for (int n : source) {
        total += (long) n * n;
    }
    return total;
}
~~~

`total` is private to each invocation, so no lock is needed for `total`. **However**, the caller could mutate the `source` array while the method is reading it, creating a data snapshot issue. If a stable result is required, either require that the input is not mutated concurrently or make a copy before computing. Also define an overflow policy for `long` addition when data values are very large.

### Pattern C — Thread confinement or task confinement

A mutable object can be safe if **only one task/thread owns it** and it is not shared before completion. For example, each task creates its own `StringBuilder`:

~~~java
String makeLabel(String first, String second) {
    StringBuilder local = new StringBuilder();
    local.append(first).append(" / ").append(second);
    return local.toString();
}
~~~

`StringBuilder` is not synchronized and is not thread-safe when shared arbitrarily, but **there is no race** if it is used only within a single invocation, does not escape to another thread, and has no shared reference. Having a mutable class does not force you to use `StringBuffer`.

### Pattern D — Immutable input/result snapshots

~~~java
record JobInput(String id, int quantity) {}
record JobResult(String id, long doubledQuantity) {}

JobResult calculate(JobInput input) {
    return new JobResult(
            input.id(),
            (long) input.quantity() * 2
    );
}
~~~

`record` is concise, has `final` components, and is well suited for representing inputs/results. However, a record is **only shallowly immutable** if a component is a mutable object. `record Payload(List<String> items)` does not automatically prevent the caller from mutating the `List` passed in. You can use `List.copyOf(items)` in an appropriate constructor while also ensuring the elements inside the `List` have the required immutability.

### Pattern E — Aggregate results after tasks complete

If each task needs to compute its own value, have it return the value instead of having all tasks write to a service's `total` field. The caller can combine `Future` results after awaiting completion, or use a stream reduction appropriate for the operation.

~~~java
// Snippet inside a method that has List<Future<Long>> futures:
long total = 0;
for (java.util.concurrent.Future<Long> future : futures) {
    total = Math.addExact(total, future.get());
}
~~~

This is a **code snippet**; `futures` is created in calling code and the method must declare/handle the checked exceptions of `get()`. `Math.addExact` helps detect overflow instead of silently wrapping around.

### Pattern F — When shared state is unavoidable, manage it with a clear protocol

Not every problem can eliminate state. Metrics, caches, queues, sessions, inventory, and external resources have real domain state. In those cases:
- `AtomicInteger`/`AtomicLong` for simple atomically updated counters.
- `LongAdder` for metrics with many writers, accepting that `sum()` is not an atomic snapshot while updates are ongoing.
- `ConcurrentHashMap` or an appropriate concurrent collection if multiple threads access a shared structure; do not assume a `containsKey` then `put` sequence is automatically atomic.
- `synchronized`, `ReentrantLock`, a CAS loop, or a single owner thread to maintain multi-step invariants.
- Bounded queues, timeouts, and backpressure when tasks are handed off across threads.

The goal of stateless design is **minimizing unnecessary shared state**, not denying the need for legitimate state.

## 9. Misconceptions to avoid

### "No fields" means thread-safe in every situation

False. Example:

~~~java
void append(java.util.List<String> target, String text) {
    target.add(text);
}
~~~

This method has no instance fields, yet two threads can pass **the same `ArrayList`** into `target`. If elements are added to the `ArrayList` concurrently without proper synchronization, the program is still not thread-safe.

Safety must also consider **ownership and thread safety of passed-in objects**. A stateless service only eliminates one source of internal shared state.

### "Each thread has local variables" means every object it uses is private

False. Two local variables `List<String> mine` can point to the same `List`, because local variables store **references**, not copies of objects. Do not confuse protecting a local reference variable with protecting the object on the heap.

### "`final`" turns a mutable object into an immutable one

False. `final Map<String, String> settings = new HashMap<>()` still allows `settings.put(...)`. To achieve immutable state, build an unmodifiable structure or do not expose mutability externally. `Map.copyOf` creates an unmodifiable map at the map level, but if the values are mutable objects, they can still change.

### "`synchronized` on every getter/setter is enough"

Not necessarily. If the logic requires `setUser(x)` followed by the corresponding `getGreeting()`, locking each method separately still lets another thread interleave in between. Replace it with a single-step stateless method or protect **the entire workflow** under one critical section on the right lock object.

### "A `static` counter has only one copy, so it's safe"

No. Precisely because it is a single shared copy, `static int count; count++` requires even more scrutiny for contention. `static` does not provide atomicity, visibility, or mutual exclusion.

### "Using `ThreadLocal` makes it stateless"

No. `ThreadLocal` **stores state** attached to the current thread. With a thread pool, a long-lived worker can be reused for many tasks and retain values from a previous task. When using `ThreadLocal`, define its scope, initialization, and call `remove()` in a `finally` block when appropriate. `ThreadLocal` is not a substitute for an explicit context-passing API when shared state can be avoided.

### "Using a concurrent collection makes every workflow atomic"

No. Structures like `ConcurrentHashMap` provide thread-safe operations per their API; multiple sequential calls can still interleave. When the invariant is "create if absent," choose an atomic operation like `computeIfAbsent` or `putIfAbsent` as required; the mapping function must obey the contract and avoid unintended side effects.

### "An immutable object makes all related systems consistent"

No. An immutable snapshot protects **what is inside the captured data**, but records outside the JVM, network requests, and the filesystem still have their own concurrency semantics. A service that holds no fields yet calls an external system can still suffer lost updates or races on the external resource.

## 10. Stateless vs thread-safe stateful: choosing the right solution

| Situation | Approach | Why |
|---|---|---|
| Format/validate/compute per input | Stateless method, local variables | No need to store intermediate per-call fields. |
| Read-heavy, rarely changing configuration | Immutable configuration, safe publication | Safely shares fixed configuration. |
| Multi-step work needing context | Immutable request context passed to method/task | Avoids `setContext()` on a shared instance. |
| Each task needs a temporary mutable buffer | Create a private buffer inside the task | Thread confinement, no sharing. |
| Counting total invocations | `AtomicLong`/`LongAdder` | This is real domain state, cannot "fake stateless." |
| Shared cache | Concurrent map and proper update mechanism | Needs capacity, consistency, eviction, and update synchronization policies. |
| Multiple values must be consistent together | Atomic replacement with immutable snapshot or shared lock | Preserves multi-field invariants in a single protocol. |
| Request data pushed into a mutable dependency | Redesign the dependency or protect access | A superficially stateless service can still race at a lower layer. |

An effective decision process:

1. **Does that state really need to live across calls?** If not, turn it into a parameter/local/result.
2. **If it must be shared, can it be immutable after construction?** If yes, publish it safely and do not mutate it.
3. **If it must be mutated, who is the owner and what invariants must hold?** Choose a lock/CAS/concurrent data structure covering all related operations.
4. **How many threads will access the same object?** Measure contention and profile before optimizing.
5. **Do external resources have state?** Design an appropriate protocol outside the JVM as well.

## 11. Publication, the Java Memory Model, and correctness

Removing mutable per-call fields reduces internal races, but **safe object publication** still matters. If an object has immutable configuration, other threads must receive its reference through a publication path guaranteed by the JMM.

Common ways include: initialization via safe static initialization; passing the object to an executor task after initialization completes; appropriate synchronization/volatile reference; or publishing a properly designed immutable object without letting `this` escape during construction.

For example, with `ExecutorService.submit`: actions in the thread before submitting a task happen-before actions inside the task under `ExecutorService`'s memory consistency contract. Thus, an instance with immutable config initialized before submission can be safely used by multiple tasks for reading that configuration.

`final` fields have their own initialization guarantees in the JMM when the constructor completes properly. However, `final` does not protect the contents of a mutable object pointed to by the field, and it does not excuse letting `this` escape before the constructor finishes. When designing for sharing, prefer clear ownership and avoid ambiguous publication.

### Happens-before and reading results

When a task returns data into a `Future`, `Future.get()`'s contract ensures the caller sees the completed actions of the task. Similarly, actions of a thread before terminating happen-before another thread returns from the corresponding `join()`.

**However, `join`/`get` do not fix races that already occurred inside the tasks**: if two tasks both write to `this.lastResult`, waiting for them to finish only lets you see one of the final values. The right approach is not using a shared result field when each task needs its own result.

## 12. A subtle design flaw: mutable helpers

Suppose a service has no counter or user field, yet keeps a `StringBuilder` to "reuse memory":

~~~java
class SharedBuilderFormatter {
    private final StringBuilder builder = new StringBuilder();

    String format(String name) {
        builder.setLength(0);
        builder.append("Hello ");
        builder.append(name);
        return builder.toString();
    }
}
~~~

This is an **object with mutable shared state** and is not thread-safe. Two threads calling `format` concurrently can interleave `setLength`/`append`/`toString`, returning corrupted strings or throwing errors depending on the situation. `final` only ensures the `builder` field cannot be pointed to another `StringBuilder`.

The natural fix:

~~~java
class LocalBuilderFormatter {
    String format(String name) {
        StringBuilder local = new StringBuilder();
        local.append("Hello ").append(name);
        return local.toString();
    }
}
~~~

Each invocation has its own buffer. This is a classic example of **avoiding sharing** rather than applying a lock to a resource that never needed to be shared. The JVM can optimize allocations in many cases, though one should not claim the runtime is guaranteed to eliminate every allocation; benchmark if allocation performance is an actual issue.

If the workload is very heavy and truly requires pooling, pooling must be designed with clear ownership, reset, exception handling, and lifecycle. That is a complex tradeoff, not a default optimization.

## 13. Boundary with external state and side effects

A Java method with no fields can still call a database, filesystem, socket, or remote service to write data. In terms of **the object's internal state**, it may be stateless; in terms of **business effects**, it is not a pure function and can contend with other calls.

Illustrative example:

~~~java
void transfer(AccountRepository repository,
              String from, String to, long amount) {
    // Actual steps must have transaction/atomicity per the data source's
    // contract. Simply having no fields in the method is not enough.
}
~~~

This is an **illustrative signature snippet**; `AccountRepository` and the transfer logic are not defined here. Do not treat it as a runnable program. The point: when multiple workers operate on the same external account, a stateless Java object cannot guarantee balance invariants. A protocol is needed where the data is owned (atomic operations, transactions, versioning, or another design suited to that system).

Within a single JVM, the same principle applies to files, shared caches, concurrent collections, and resource pools. **Avoiding state in a service** does not mean removing all state from the system; it makes where state is owned and protected clearer.

## 14. When should state be kept intentionally?

Some objects should be stateful:

- **Counter/metric:** number of requests or events; use atomics/adders with appropriate observation semantics.
- **Queue/channel:** pending work items, with capacity/backpressure and a producer–consumer contract.
- **Cache:** shared results, bounded capacity, expiration, and per-key consistency.
- **State machine:** state transitioning through stages, maintaining invariants across transitions.
- **Rate limiter:** permit/token state, requiring atomic coordination.

The key is **not cramming state into a pure processing service just to reuse an object**. If state genuinely needs to exist, let it belong to a component with clear responsibility and synchronization policy.

Simple example:

~~~java
import java.util.concurrent.atomic.AtomicLong;

final class RequestMetrics {
    private final AtomicLong handled = new AtomicLong();

    void recordHandled() {
        handled.incrementAndGet();
    }

    long handledSoFar() {
        return handled.get();
    }
}
~~~

`RequestMetrics` is a **stateful, thread-safe counter** for incrementing/reading a single value. It does not become stateless just because it uses `AtomicLong`. If a business operation requires consistency between this metric and other state, an additional appropriate protocol is needed; an atomic update of one counter does not make all external operations atomic.

## 15. Code review checklist for eliminating sharing

When reviewing a class used concurrently, check in order:

1. **Are there mutable instance fields?** Especially `currentUser`, `lastResult`, `StringBuilder`, `ArrayList`, `HashMap`, `SimpleDateFormat`, or internal buffers. For modern Java date/time, prefer immutable APIs like `DateTimeFormatter`.
2. **Are there static mutable fields?** A class with "no instance fields" can still share state via `static`.
3. **Does the method truly use only inputs and locals?** Is per-call data returned rather than placed into a shared field?
4. **Do inputs reference shared mutable objects?** Local parameters do not guarantee the object is private. Establish owner/copy/immutable conventions.
5. **Are called dependencies thread-safe?** A service that mutates no state of its own can still call a mutable helper.
6. **Are there multiple dependent steps?** Sequences like set-then-get, check-then-act, or read-then-write need an operation-level invariant.
7. **Where are task results collected?** Prefer return values/`Future`/reduction; avoid `lastResult` on a shared instance.
8. **Is the object safely published?** Constructor completes, and immutable state is not modified after publication.
9. **Is `ThreadLocal` cleaned up?** If `ThreadLocal` is needed, clearly define the owner, set/remove timing, and risk of retaining data across worker reuse.
10. **Are external resources shared?** Files, connections, caches, and data systems have their own state and contracts.
11. **Was correctness checked before benchmarking?** Adding `synchronized` may make a bug disappear, but a stateless refactor often also eliminates hard-to-understand temporal coupling.
12. **Are the API's concurrency limits clearly documented?** Statelessness does not automatically bound task count, memory, queues, connections, or CPU.

## 16. Self-check exercises

**Question 1.** An object has a `private final BigDecimal rate` field set from the constructor and never changed, and `calculate(x)` only uses locals. Can it be called concurrently by multiple threads?

**Answer:** Yes, provided the calculator is initialized and safely published, `BigDecimal` is immutable, the method does not mutate shared state, and it uses no unsafe dependencies. This is a service that **holds no mutable per-call state** even though it has immutable configuration.

**Question 2.** A method has no fields, but accepts `List<String> input` and calls `input.sort(...)`. Is it automatically thread-safe?

**Answer:** No. If multiple threads pass in the same mutable list, the method can mutate the shared input concurrently. Ownership/copying or appropriate synchronization is required.

**Question 3.** Two methods `synchronized setUser()` and `synchronized getGreeting()` are on the same instance. Caller A calls `set("A")`, caller B calls `set("B")`, then A calls `get()`. Could it return B?

**Answer:** Yes. Each method is atomic with respect to the monitor, but the lock is released between the two methods. The `set`+`get` sequence is not atomic.

**Question 4.** A service has `private final StringBuilder builder`, and each method calls `setLength(0)`, then `append`, then `toString`. Is this stateless?

**Answer:** No. `builder` is a mutable shared field. Move the `StringBuilder` into a local variable inside the method or design appropriate ownership.

**Question 5.** Does using a `ThreadLocal<UserContext>` in a worker pool make a service stateless?

**Answer:** No. It still stores per-thread state, can persist across multiple tasks on the same worker, and requires proper cleanup.

**Question 6.** When two tasks need to sum their results, which approach reduces shared state: both incrementing an unsynchronized `sum` field, or each task returning a value and the caller aggregating after `Future.get()`?

**Answer:** Having each task return a value and the caller aggregate after `get()` is usually simpler and avoids races on the `sum` field. Handle exceptions, cancellation, overflow, and task count according to real requirements.

## 17. Reference documentation

- **Java Language Specification §17 — Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- **ExecutorService:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Future:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **CountDownLatch:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- **AtomicLong:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- **ConcurrentHashMap:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- **ThreadLocal:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html

**Key takeaway:** The simplest solution to many race conditions is **not sharing mutable state when it is not needed**. Keeping task data in parameters/locals/results and maintaining immutable configuration allows a single instance to serve multiple threads more safely, with fewer locks and less need to reason about interleaving. When shared state is genuinely part of the domain, explicitly define its owner, invariants, and synchronization mechanism to protect it.
