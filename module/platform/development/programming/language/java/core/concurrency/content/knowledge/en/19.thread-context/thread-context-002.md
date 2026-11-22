# Initializing Values with ThreadLocal.withInitial() in Java

## 1. What Problem Does ThreadLocal.withInitial() Solve?

`ThreadLocal<T>` is a mechanism for storing **values bound to each thread**. Each thread accesses the same `ThreadLocal` object but sees its own value. It is useful when an operation runs primarily on a single thread and needs local state such as a temporary buffer, a counter, or context for a task. Values are not automatically propagated to other threads, and `ThreadLocal` does not replace synchronization mechanisms when data is actually shared.

When you only create:

~~~java
ThreadLocal<StringBuilder> buffer = new ThreadLocal<>();
~~~

the first `buffer.get()` call on each thread returns `null`, unless the thread has already called `set()`. If each thread needs its own `StringBuilder` on first use, you can write:

~~~java
ThreadLocal<StringBuilder> buffer =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Now, **each thread will receive a new `StringBuilder` when that thread calls `get()` for the first time**, and will continue retrieving the same object on subsequent `get()` calls until it is replaced with `set()` or cleared with `remove()`.

`withInitial()` has two benefits: it explicitly defines the initial value and avoids repeating "if `get() == null`, create a new one" logic. However, the initial value **is not created immediately when `withInitial()` is called**.

### Lesson Objectives

- Understand the lazy and per-thread nature of the initializer.
- Distinguish between `get()`, `set()`, `remove()`, and `set(null)`.
- Properly initialize a separate mutable object for each thread.
- Use it in an `ExecutorService`/thread pool without retaining state from a previous task.
- Know the limitations of `ThreadLocal` when work switches threads, runs asynchronously, or has a long lifecycle.

This article uses only standard Java concurrency, independent of any framework.

## 2. API, Types, and When the Supplier Is Called

In the JDK, the static method has the form:

~~~java
public static <S> ThreadLocal<S> withInitial(
    java.util.function.Supplier<? extends S> supplier)
~~~

`Supplier<? extends S>` is a function that takes no arguments and returns a value compatible with `S`. You can use a lambda or a method reference:

~~~java
ThreadLocal<Integer> sequence = ThreadLocal.withInitial(() -> 0);
ThreadLocal<StringBuilder> builder = ThreadLocal.withInitial(StringBuilder::new);
ThreadLocal<java.util.ArrayList<String>> items =
    ThreadLocal.withInitial(java.util.ArrayList::new);
~~~

These examples **declare three `ThreadLocal` instances** without forcing the current thread to create any values yet. Calling `get()` on a thread that has no value yet triggers the corresponding supplier. If you pass `withInitial(null)`, the `ThreadLocal` creation call is rejected with a `NullPointerException` because the supplier is not allowed to be `null`; this is different from a valid supplier that returns `null`.

For a specific `ThreadLocal` object, the state of **each thread** behaves as follows:

| Action in thread | Observed value | Does the supplier run? |
| --- | --- | --- |
| Newly created `ThreadLocal.withInitial(factory)` | Thread has no value yet | Not yet |
| First `get()`, never called `set()` | Value created by `factory.get()` | Yes, in the thread calling `get()` |
| Subsequent `get()` | The same stored value | No |
| `set(custom)` before first `get()` | Returns `custom` on `get()` | No |
| `set(custom)` after `get()` | Replaces current value with `custom` | No |
| `set(null)` | `get()` returns stored `null` | Does not re-initialize |
| `remove()` then `get()` | Value is created again | Yes, on that subsequent `get()` |

Two common misconceptions:

1. **Values are per-thread, not per-method-call.** If two requests run sequentially on the same thread in a pool, both can see *the same stale value* if it is not cleaned up.
2. **The supplier can run multiple times on the same thread.** Each time `remove()` clears the mapping, the next `get()` can invoke the supplier again. Therefore, do not treat the supplier as an initializer that "runs only once in the entire application."

When the supplier returns `null`, `null` is still a recorded value for the thread. Subsequent `get()` calls will not automatically call the supplier again just because they receive `null`.

## 3. Runnable Java 17 Example: Lazy Initialization, set, and remove

This example creates an event list for each thread. A `newSingleThreadExecutor()` allows running two tasks **on the same worker thread**, demonstrating why `remove()` is needed at the end of each task. `AtomicInteger` is used only to count how many times the supplier is run and is safe if the demo is extended to multiple threads.

Create the file `ThreadLocalWithInitialDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadLocalWithInitialDemo {
    private static final AtomicInteger creations = new AtomicInteger();

    private static final ThreadLocal<List<String>> events =
        ThreadLocal.withInitial(() -> {
            creations.incrementAndGet();
            return new ArrayList<>();
        });

    private static String handle(String requestId) {
        List<String> localEvents = events.get();

        try {
            localEvents.add(requestId);
            return String.join(", ", localEvents);
        } finally {
            // Clear task state from the reused thread.
            events.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Trước get: " + creations.get());

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> first =
                executor.submit(() -> handle("A"));
            System.out.println("Lượt 1: " + first.get());

            Future<String> second =
                executor.submit(() -> handle("B"));
            System.out.println("Lượt 2: " + second.get());
        } finally {
            executor.shutdown();
        }

        System.out.println("Số lần tạo: " + creations.get());

        AtomicInteger initCalls = new AtomicInteger();
        ThreadLocal<String> label = ThreadLocal.withInitial(() -> {
            initCalls.incrementAndGet();
            return "initial";
        });

        label.set("manual"); // set before get: supplier not called yet.
        System.out.println("set trước get: " +
            label.get() + ", init=" + initCalls.get());

        label.remove(); // next get will call the supplier.
        System.out.println("sau remove: " +
            label.get() + ", init=" + initCalls.get());

        label.set(null); // null is the currently stored value.
        System.out.println("set(null): " +
            (label.get() == null) + ", init=" + initCalls.get());

        label.remove();
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac -encoding UTF-8 ThreadLocalWithInitialDemo.java
java ThreadLocalWithInitialDemo
~~~

Stdout:

~~~text
Trước get: 0
Lượt 1: A
Lượt 2: B
Số lần tạo: 2
set trước get: manual, init=0
sau remove: initial, init=1
set(null): true, init=1
~~~

**Why is the output deterministic?**

- Creating `events` does not invoke the supplier, so the first line prints `0`.
- `newSingleThreadExecutor` runs both tasks on a single worker, and `first.get()` completes before the second task is submitted. Each task calls `get()` when the mapping has just been cleared by `remove()` in the previous task; the supplier runs twice.
- Task B's list does not retain element A because the `finally` block cleared the mapping. If `events.remove()` is omitted, the second line will become `Lượt 2: A, B` and the total creation count will only be `1`.
- `label.set("manual")` creates a mapping before `label.get()`, so `label`'s supplier has not run. `remove()` forces the next `get()` to re-initialize.
- `label.set(null)` stores `null`; `get()` does not initialize again. The final `label.remove()` clears the main thread's mapping.

In this example, the `ArrayList` object is used in exactly one worker thread at a time. `ArrayList` does not automatically become thread-safe by being placed in a `ThreadLocal`; the safety condition is that the reference to that list is not passed to another thread for concurrent modification.

## 4. A Proper Supplier: Creating a Separate Object Instead of Returning a Shared One

The pattern for initializing a mutable value should **create a new instance inside the supplier**:

~~~java
ThreadLocal<StringBuilder> correct =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Incorrect for the goal of data isolation:

~~~java
StringBuilder shared = new StringBuilder();
ThreadLocal<StringBuilder> incorrect =
    ThreadLocal.withInitial(() -> shared);
~~~

In the incorrect snippet, each thread has its own *mapping*, but every mapping holds **the same `shared` reference**. Multiple threads modifying `shared` concurrently will cause data contention. `ThreadLocal` does not copy objects for you.

Types of values you can use:

- **Immutable:** For example, identifiers or unchanging configuration; the initializer may return the same object if sharing is intentional.
- **Per-thread mutable:** For example, `StringBuilder`, `ArrayList`, parsers, or stateful processors; the supplier must create an appropriate instance and not let the reference escape the thread.
- **Expensive objects:** Only use `ThreadLocal` if the benefit of reuse outweighs the cost of keeping one copy per thread, and a resource cleanup policy is in place.

Note that **the supplier is a function object that can be called concurrently by multiple threads**. A lambda that captures external mutable state—for example, incrementing an `int` in a shared object without synchronization—still has a data race. In the runnable example, `AtomicInteger` protects the creation count; it is not a mechanism of `ThreadLocal`.

Avoid creating a new `ThreadLocal` every time you need to access state:

~~~java
// Misuse: each call creates a different ThreadLocal key.
static StringBuilder newUnrelatedBuffer() {
    return ThreadLocal.withInitial(StringBuilder::new).get();
}
~~~

If the intent is to access state with a thread-level lifecycle, use **the same `ThreadLocal` key** held in a field (typically `private static final` or an instance field with a clear lifecycle). Unrelated components should not share a key just because they have the same value type.

## 5. withInitial() vs. Overriding initialValue(): How Are They Equivalent?

Before Java 8, a common approach was an anonymous subclass:

~~~java
ThreadLocal<StringBuilder> oldStyle = new ThreadLocal<>() {
    @Override
    protected StringBuilder initialValue() {
        return new StringBuilder();
    }
};
~~~

With Java 8+, the equivalent approach is more concise:

~~~java
ThreadLocal<StringBuilder> modern =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Both share the same idea: when `get()` encounters a thread with no mapping yet, it runs the initialization logic and stores the value for reuse in that thread. `withInitial` does not create threads or schedule tasks, nor does it change `set`/`remove` semantics.

Use `withInitial` when the factory can be clearly expressed as a `Supplier`. Overriding `initialValue()` is still valid when you need a subclass or custom logic, but there is no need to create a subclass just to return a value.

If the factory throws a `RuntimeException` during the first `get()`, the exception surfaces at **that `get()` call**; the value for the thread is not successfully set. Subsequent `get()` calls may retry the factory. `Supplier.get()` does not declare checked exceptions; if initialization involves a checked exception, you must handle or wrap it explicitly—you cannot simply throw a checked exception from a `Supplier` lambda.

## 6. Thread Pools: Initialization Is Per-Thread, Not Per-Request

Imagine an `ExecutorService` with 4 workers, while the application processes 10,000 requests. If you use:

~~~java
private static final ThreadLocal<String> CURRENT_REQUEST =
    ThreadLocal.withInitial(() -> "unassigned");
~~~

then each worker may initialize the value `"unassigned"` on its first `get()`, and then be assigned an actual request via `set()`. When a worker finishes a request, **the thread does not disappear**; it stays alive to pick up the next request. Therefore, having a default supplier **does not guarantee** that state is reset at request boundaries.

A standard Java task-handling pattern:

~~~java
static String processOne(String requestId) {
    CURRENT_REQUEST.set(requestId);
    try {
        return "Handling " + CURRENT_REQUEST.get();
    } finally {
        CURRENT_REQUEST.remove();
    }
}
~~~

This snippet is an illustration placed in the same class as the `CURRENT_REQUEST` field above. Use `finally` to clean up even when the work throws an exception or returns early. Do not place `remove()` only in the success branch.

In cases where a caller **already has an active outer context** and wants to temporarily override the value for a nested call, calling `remove()` right after the inner call can wipe out the outer context. You can save and restore the previous value:

~~~java
// Illustrates a nested scope inside an outer scope that already has CURRENT_REQUEST.
String previous = CURRENT_REQUEST.get();
CURRENT_REQUEST.set("nested-request");
try {
    // Invoke nested work here.
} finally {
    CURRENT_REQUEST.set(previous);
}
~~~

This approach proactively calls `get()` and may therefore create the default value if the thread previously had no mapping. If you need to distinguish accurately between "no mapping ever existed" and "null was stored," you must design a dedicated scope/ownership mechanism; `ThreadLocal`'s public API has no method to check whether a mapping exists without initializing it. At **the outermost task boundary**, the owner must still explicitly decide when to call `remove()`.

## 7. ThreadLocal Does Not Automatically Propagate Across Asynchronous Tasks

A core takeaway: `ThreadLocal` follows the **currently executing thread**, not a request object or a logical call chain.

~~~java
// Illustration: inside a class with the CURRENT_REQUEST field.
// executor is an ExecutorService that has been created and lifecycle-managed.
CURRENT_REQUEST.set("req-42");

java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> CURRENT_REQUEST.get(), executor);
~~~

You cannot expect `result` to receive `"req-42"`. The asynchronous task runs on a thread of `executor`, where the `CURRENT_REQUEST` mapping may not exist yet or may hold stale state from improperly managed prior code. A context policy must be defined when handing off tasks.

For small data, the clearest approach is **passing parameters**:

~~~java
String requestId = CURRENT_REQUEST.get();
java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> "Handling " + requestId, executor);
~~~

If a downstream library requires reading from `ThreadLocal`, you can capture the value on the calling thread, then `set/remove` it inside the worker itself:

~~~java
String requestId = CURRENT_REQUEST.get();
java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(() -> {
        CURRENT_REQUEST.set(requestId);
        try {
            return "Handling " + CURRENT_REQUEST.get();
        } finally {
            CURRENT_REQUEST.remove();
        }
    }, executor);
~~~

The three snippets above are **standalone illustrations of context flow**, assuming `executor` and `CURRENT_REQUEST` are already declared and the caller is responsible for shutting down the executor and cleaning up context on the calling thread. Do not use `ThreadLocal` as a hidden mechanism to pass data between threads.

`InheritableThreadLocal` is a different API intended for certain cases where a child thread inherits values at thread creation time; it does not make context propagation across thread pools automatic or reliable. Nor should you assume that `CompletableFuture` continuations will always run on the same thread as the preceding stage: different stages can run on different threads depending on how completion occurs and which executor is used.

## 8. Lifecycle, Memory, and Performance

`ThreadLocal` uses a structure that stores values associated with each thread. You can visualize it as:

~~~text
Thread A -> ThreadLocal key -> value A
Thread B -> ThreadLocal key -> value B
Thread C -> ThreadLocal key -> value C
~~~

This diagram represents the observed logical model; the implementation detail is that each `Thread` has a storage area mapping `ThreadLocal` keys. A `ThreadLocal` declared as `static final` keeps the key alive for a long time; if pool threads are also long-lived, large values can be retained longer than intended. For keys that no longer have strong references, the fact that keys are managed via weak references in `ThreadLocalMap` does not guarantee immediate value reclamation: values may persist until the map cleans up stale entries or the thread terminates. Do not rely on GC instead of calling `remove()` at the right time.

Practical rules:

- Do not hold large object graphs, request bodies, sessions, or closeable resources in `ThreadLocal` longer than required.
- `remove()` deletes the mapping; **it does not automatically call `close()`** on the value. If the value owns a file, socket, or closeable resource, close it in `finally` according to its lifecycle before removing the mapping.
- `withInitial(StringBuilder::new)` can help reuse buffers on workers, but old content remains unless you call `setLength(0)` or `remove()`. Keeping overly large buffers can cause long-term memory retention.
- Requiring a separate value per thread can increase memory overhead with thread count. Do not use `ThreadLocal` for every object just to avoid passing parameters.
- When using virtual threads on Java 21+, `ThreadLocal` still works, but the "keep a cache per thread" pattern is usually unsuitable for very large numbers of virtual threads. Consider designing around explicit data passing and task lifecycles rather than defaulting to per-thread state.

For immutable or cheap, thread-safe values, passing them directly as parameters is usually simpler. `ThreadLocal.withInitial` is valuable when binding state to the *current thread* is an intentional design decision.

## 9. Common Mistakes and How to Verify

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `get()` returns `null` despite using `withInitial` | The supplier actually returns `null` or `set(null)` was called | Define the contract: is `null` a valid value; do not treat `null` as always meaning "uninitialized" |
| Two requests see the same data | Pool reuses threads; mapping is not cleared between requests | `set` at task start, `remove` in `finally` |
| Two threads modify the same object | Supplier returns a shared mutable reference | Create a new instance inside the supplier |
| Supplier does not run on first `get()` as expected | Thread already called `set()` before `get()` | Check the `set/get/remove` sequence |
| Supplier runs again | Thread called `remove()` or the previous `get()` failed during initialization | Understand that initialization happens based on the current mapping |
| Context disappears after `supplyAsync` | Work moved to a different thread | Pass parameters or capture/set/cleanup in the worker |
| Memory grows in a long-lived pool | Large values live alongside workers or stale entries are not yet cleaned up | Limit value size, design lifecycle, call `remove()` |
| Data is lost when nesting scopes | Inner scope calls `remove()`, wiping outer scope state | Save/restore outer state or design scoped ownership |

Self-verify by modifying the example in Section 3:

1. Remove `events.remove()`, and observe that run 2 sees both `A` and `B`. This directly demonstrates **state leak** between two tasks on one worker.
2. Restore `remove()`, try calling `events.get()` twice in the same task and compare with `==`: both refer to the same list before `remove()`.
3. Change the supplier to `() -> null`: consecutive `get()` calls all return `null`, yet the mapping does not re-initialize.
4. Create two separate threads, each calling `events.get()`. The threads receive different lists if the supplier creates `new ArrayList<>()` and does not share the reference externally.
5. Have the task throw an exception inside the `try` block of `handle()`; `finally` still runs and clears the value. In a real environment, you should also check cancellation/interruption branches according to the task's contract.

## 10. When to Use It and Key Takeaways

Choose `ThreadLocal.withInitial(factory)` when a value **needs to belong to each thread**, has a clear initialization strategy, and has a well-defined cleanup lifecycle. `withInitial` runs **lazily** on the first `get()` without a mapping; `set()` overwrites, `set(null)` is a valid value, and `remove()` deletes the mapping so the next `get()` initializes it again.

The most important thing in Java concurrency is recognizing two different boundaries: **the thread** and **the logical task**. In a thread pool, many tasks share the same thread; with asynchronous APIs, a single task can span multiple threads. Therefore, use `try/finally` and `remove()` when owning task-level context, pass data explicitly when crossing threads, and do not assume the supplier creates fresh data for each request.