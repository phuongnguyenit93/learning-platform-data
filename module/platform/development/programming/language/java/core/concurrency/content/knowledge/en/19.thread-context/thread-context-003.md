# InheritableThreadLocal and Inheritance Limits in Java Concurrency

## 1. Why Do We Need to Understand This Mechanism?

`ThreadLocal<T>` binds a separate value to the **current thread**. Two threads share the same `ThreadLocal` variable, yet each thread has its own value mapping. This mechanism is sometimes used to hold a request ID, correlation ID, locale preference, or processing context that multiple methods on the same thread need to access.

A problem arises when a task creates a **child thread**: an ordinary `ThreadLocal` does not automatically pass the creating thread's value to the new thread. `InheritableThreadLocal<T>` provides a mechanism to receive the **initial value** from the creating thread when the new thread is initialized.

The most important point: **inheritance here is an initialization operation at thread-creation time, not a continuous context synchronization stream, not guaranteed per task, and does not automatically handle mutable data.** If misused in a thread pool, the application can read stale context or leak data between requests.

This lesson focuses on the API and behavior of **core Java concurrency**, including platform threads, executors, and virtual threads.

### Objectives

After this lesson, you will be able to:

- Distinguish `ThreadLocal` and `InheritableThreadLocal` using the same example.
- Explain accurately **when**, **from which thread**, and **which value** is passed to a new thread.
- Use `childValue(T parentValue)` to create a copy or transform the initial value.
- Recognize limitations with mutable objects, thread pools, executors, indirectly created threads, and virtual threads.
- Choose parameter passing, task wrapping with cleanup, or disabling inheritance when unnecessary.

## 2. ThreadLocal vs. InheritableThreadLocal

Both classes have `get()`, `set(value)`, and `remove()`, but differ in how data is initialized in a child thread.

| Criterion | `ThreadLocal<T>` | `InheritableThreadLocal<T>` |
|---|---|---|
| Value of current thread | `get()`/`set()` per thread | Same |
| When creating a child thread | Does not inherit parent's value | Receives initial value from parent by default |
| When parent calls `set()` after child creation | Not propagated to child | Does **not update** the child's mapping copy |
| When child calls `set()` | Changes only child's mapping | Changes only child's mapping |
| When value is a mutable object | Each thread holds a separate reference if set separately | By default parent and child can hold the **same object reference** |
| Thread pool reusing workers | Does not follow task context | Also does **not follow task context** |
| Cleanup | `remove()` at end of scope | `remove()` at end of scope |

Do not interpret "thread-local value" as "the object is always copied." The `ThreadLocal → value` mapping is separate per thread; two mappings can still point to **the exact same object**.

### Runnable example: inheritance at thread-creation time

**File `InheritanceTiming.java` (Java 21+):**

```java
public class InheritanceTiming {
    private static final ThreadLocal<String> ORDINARY =
            new ThreadLocal<>();

    private static final InheritableThreadLocal<String> INHERITED =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        ORDINARY.set("ordinary-parent");
        INHERITED.set("A");

        try {
            Thread child = Thread.ofPlatform().unstarted(() -> {
                try {
                    System.out.println("child ordinary=" + ORDINARY.get());
                    System.out.println("child inherited=" + INHERITED.get());
                    INHERITED.set("CHILD");
                } finally {
                    ORDINARY.remove();
                    INHERITED.remove();
                }
            });

            // Child thread has been CREATED; not yet STARTED.
            INHERITED.set("B");
            child.start();
            child.join();

            System.out.println("parent inherited=" + INHERITED.get());
        } finally {
            ORDINARY.remove();
            INHERITED.remove();
        }
    }
}
```

Compile and run:

```bash
javac InheritanceTiming.java
java InheritanceTiming
```

Exact stdout:

```text
child ordinary=null
child inherited=A
parent inherited=B
```

Explanation:

1. Parent calls `set("A")` on `INHERITED`.
2. `Thread.ofPlatform().unstarted(...)` **creates a new thread object**; at that moment, the child thread receives the initial value `"A"`.
3. Parent changes it to `"B"` **after creation but before starting**. This only changes the parent's mapping.
4. Child starts and reads `INHERITED.get() == "A"`; `ORDINARY.get()` is `null` because it has no initial value.
5. Child's `set("CHILD")` does not change the parent's value. After `join()`, the parent still reads `"B"`.

`join()` ensures `main` waits for the child to finish printing, so this stdout order is deterministic. If using `new Thread(runnable)`, the inheritance point is also **thread creation**, not the `start()` call.

## 3. The childValue Mechanism: Copying Mappings and Transforming Values

`InheritableThreadLocal` overrides how initial data is created for a child thread via:

```java
protected T childValue(T parentValue)
```

Per the Java API:

- The runtime retrieves the corresponding value from the inheritable-thread-local map of the **thread creating the child thread**.
- `childValue(parentValue)` is called **in the creating thread**, **before the child thread starts running**.
- The default implementation returns **`parentValue` itself**.
- It can be overridden to create a copy, transform, filter, or prevent part of the data from passing to the child.
- `childValue` is not a hook that runs on every `get()` in the child, nor does it run after each task `submit`.

Therefore, the inheritance operation is a **snapshot of mappings at creation time**. This snapshot does not mean a **deep copy of every object**. The cost of copying the inheritable-entry map grows with the number of entries currently present on the parent thread.

### Example: default mutable reference vs. copy via childValue

**File `MutableInheritance.java` (Java 21+):**

```java
import java.util.ArrayList;
import java.util.List;

public class MutableInheritance {
    private static final InheritableThreadLocal<List<String>> SHARED =
            new InheritableThreadLocal<>();

    private static final InheritableThreadLocal<List<String>> COPIED =
            new InheritableThreadLocal<>() {
                @Override
                protected List<String> childValue(List<String> parentValue) {
                    return parentValue == null
                            ? null
                            : new ArrayList<>(parentValue);
                }
            };

    public static void main(String[] args) throws InterruptedException {
        SHARED.set(new ArrayList<>(List.of("origin")));
        COPIED.set(new ArrayList<>(List.of("origin")));

        try {
            Thread child = Thread.ofPlatform().start(() -> {
                try {
                    SHARED.get().add("child");
                    COPIED.get().add("child");
                } finally {
                    SHARED.remove();
                    COPIED.remove();
                }
            });
            child.join();

            System.out.println("shared parent=" + SHARED.get());
            System.out.println("copied parent=" + COPIED.get());
        } finally {
            SHARED.remove();
            COPIED.remove();
        }
    }
}
```

Run:

```bash
javac MutableInheritance.java
java MutableInheritance
```

Stdout:

```text
shared parent=[origin, child]
copied parent=[origin]
```

`SHARED` uses the default `childValue`: the two threads have independent mappings but hold **the same `ArrayList`**. The child adds an element, so the parent sees it as well. `COPIED` creates a new `ArrayList` for the child, so the child's modification does not alter the parent's list.

**Points to note:**

- `new ArrayList<>(parentValue)` is a **shallow copy**: it copies the container and element references. If the elements themselves are mutable, parent and child can still share the inner objects.
- If multiple threads concurrently modify a shared object without synchronization, data races, lost updates, or corrupted state can occur. `InheritableThreadLocal` **does not provide synchronization**.
- When the context is an immutable value (for example `String`, a record with immutable fields, an identifier), sharing the same object is usually simpler and less risky.
- Validation or data-packaging logic can be placed in `childValue`, but you should not perform slow I/O, complex side effects, or operations assuming the child has already started: the method runs in **the thread creating the child**.

## 4. The Biggest Limitation: Thread Pools Do Not Create a New Thread per Task

A request/task may be passed to `submit()` from a thread holding context, but **the task does not automatically become a "child thread" of the submitting thread**. An executor runs tasks on workers it manages. With a fixed pool, a worker is typically created once and then runs many tasks.

This leads to two bugs:

1. **Stale context:** the worker inherits context when it is created; subsequent submissions change the caller's context, but the worker still retains the old value.
2. **Context leakage:** a task changes the value on the worker without cleaning up; the next task on the same worker can see the previous task's value.

### Empirical example with a single fixed worker

**File `PoolInheritanceTrap.java` (Java 21+):**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PoolInheritanceTrap {
    private static final InheritableThreadLocal<String> CONTEXT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool = Executors.newSingleThreadExecutor()) {
            CONTEXT.set("request-A");
            System.out.println("first=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());

            CONTEXT.set("request-B");
            System.out.println("second=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());

            pool.submit(() -> {
                CONTEXT.set("worker-overwrite");
            }).get();

            System.out.println("third=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());
        } finally {
            CONTEXT.remove();
        }
    }
}
```

Run:

```bash
javac PoolInheritanceTrap.java
java PoolInheritanceTrap
```

Stdout:

```text
first=request-A
second=request-A
third=worker-overwrite
```

Because `newSingleThreadExecutor()` creates the worker when the first task is executed, the worker inherits `"request-A"` at creation time. The caller changes it to `"request-B"`, but the worker **is not recreated**. The third task changes the context inside the worker to `"worker-overwrite"`; the next task reads back that exact leftover value in the worker.

The example uses a single worker and awaits each `Future.get()` so the result is deterministic. With a multi-worker pool, each worker may be created at a different time; therefore the same flawed logic can produce **hard-to-reproduce** bugs that depend on timing and scheduling.

**Important rule:** Do not assume `InheritableThreadLocal` will automatically propagate per-request context across `ExecutorService.submit()`, `execute()`, `CompletableFuture.supplyAsync()`, or asynchronous callbacks. The value depends on **which thread actually creates the executing thread** and the worker's lifecycle, not the request's call hierarchy.

## 5. Passing Context Deterministically to an Executor

The clearest approach is to **pass context as a parameter**. An immutable `record` representing request context makes the dependency explicit in the API:

```java
record RequestContext(String traceId) {}

static String process(RequestContext context, String payload) {
    return context.traceId() + ":" + payload;
}
```

This is an illustrative snippet placed inside a class; `process` receives the context directly, so it does not depend on the executing thread.

If you must interact with an existing API that reads a `ThreadLocal`, you can **capture context at submit time** and then **bind and clean it up in the executing thread**. This is an explicit choice by the application, not magic from `InheritableThreadLocal`.

### Complete example: capture, restore, and cleanup

**File `ExplicitContext.java` (Java 21+):**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExplicitContext {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    private static <T> Callable<T> withTrace(
            String traceId, Callable<T> action) {
        return () -> {
            String previous = TRACE_ID.get();
            TRACE_ID.set(traceId);
            try {
                return action.call();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool = Executors.newSingleThreadExecutor()) {
            System.out.println(pool.submit(
                    withTrace("R-1", () -> "task1=" + TRACE_ID.get())).get());

            System.out.println(pool.submit(
                    withTrace("R-2", () -> "task2=" + TRACE_ID.get())).get());

            System.out.println("after=" +
                    pool.submit(() -> { return TRACE_ID.get(); }).get());
        }
    }
}
```

Run:

```bash
javac ExplicitContext.java
java ExplicitContext
```

Stdout:

```text
task1=R-1
task2=R-2
after=null
```

`withTrace` is a task wrapper: before execution it binds the value for the task; in `finally` it restores the worker's state. In this example, the convention is that `null` means no value is present. If the application allows **`null` to carry a distinct meaning**, the context design and restoration rules must represent that state explicitly rather than inferring it solely from `get() == null`.

When you need to pass **multiple attributes**, bundle them into an immutable context object instead of maintaining many separate `ThreadLocal`s that are hard to snapshot and restore. If there are isolation or data-access requirements, you must determine precisely which tasks are allowed to receive the context.

### Do not overlook error cases

The wrapper pattern must use `finally` because `action.call()` can throw an exception. With `Callable<T>`, the exception is still propagated to `Future.get()` via `ExecutionException`; cleanup still runs. When copying mutable context, create an appropriate copy **before** the task uses it to avoid sharing objects across tasks.

If a thread pool processes jobs from multiple users, identity data, tokens, or authorization details should not be inherited automatically into unrelated jobs. Context passed across task boundaries must be **explicitly selected**.

## 6. Virtual Threads: Inheritance Still Exists, but Use Restraint

Virtual threads became a standard feature in Java 21. They also support `ThreadLocal` and `InheritableThreadLocal`. With `Thread.Builder`, the default is to **inherit inheritable-thread-local values** from **the thread creating the virtual thread**; this can be disabled with `inheritInheritableThreadLocals(false)`.

**File `VirtualInheritance.java` (Java 21+):**

```java
public class VirtualInheritance {
    private static final InheritableThreadLocal<String> REQUEST =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        REQUEST.set("parent-context");

        try {
            Thread inherited = Thread.ofVirtual().start(() -> {
                try {
                    System.out.println("default=" + REQUEST.get());
                } finally {
                    REQUEST.remove();
                }
            });
            inherited.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() -> {
                        try {
                            System.out.println("isolated=" + REQUEST.get());
                        } finally {
                            REQUEST.remove();
                        }
                    });
            isolated.join();
        } finally {
            REQUEST.remove();
        }
    }
}
```

Run:

```bash
javac VirtualInheritance.java
java VirtualInheritance
```

Stdout:

```text
default=parent-context
isolated=null
```

The two `join()` calls make the output order deterministic. `isolated` does not inherit data because the builder disabled the mechanism.

### Why be careful with virtual threads?

Virtual threads can be very numerous (tens of thousands or more, depending on workload), while each virtual thread can still hold thread-local entries and the objects they reference. If the context is large, each child copies a map with many entries, or `childValue` creates large mutable copies, **memory and thread-creation overhead will increase significantly**.

Do not use `ThreadLocal` as a large "per-thread" resource cache when the number of virtual threads can be very large. If context propagation is not needed at thread creation, disable inheritance intentionally. If needed, pass small, immutable context with a bounded lifetime.

One more note: a new thread inherits from **the thread that actually creates it**, not by default from the "original request" as a developer might assume. If another thread is responsible for creating the virtual thread, the inheritance source is that creating thread.

## 7. Lifecycle Limits and Inheritance Boundaries

### 7.1. Not a live parent–child relationship

The terms "parent/child thread" refer only to **the relationship at creation time**. They do not mean the child automatically reads new updates from the parent, there is no bidirectional value synchronization, and there is no guarantee the child terminates when the parent terminates.

Example with immutable `String`:

```text
T0: parent.set("A")
T1: create child    → child receives initial value "A"
T2: parent.set("B") → parent="B", child="A"
T3: child.set("C")  → parent="B", child="C"
T4: parent.remove() → does not automatically remove in child
```

If the value is **the same mutable reference**, changes to the shared object may be observed by the other thread according to Java memory synchronization rules; never treat that as a proper context-passing mechanism.

### 7.2. Multi-generation inheritance

When thread A creates B, B receives the initial values left by A (via `childValue`). If B later creates C, C inherits from **B at the time B creates C**, not tracing back to A. Each step can apply its own `childValue`. Even a thread not created inside business logic can carry context if it is created by a thread that has inheritable values.

### 7.3. remove() does not revoke inherited values in the child

`remove()` only removes the mapping on the **current thread**. When the parent calls `remove()` after creating the child, the inherited value in the child does not automatically disappear. When the child is long-lived, the data can continue to be retained; if it references a large object, that object cannot be garbage-collected merely because the parent called `remove()`.

Applications must control task lifecycles and clean up at **every place that actually binds or holds context**, especially with reused workers.

### 7.4. initialValue and childValue are different

- `initialValue()` (inherited from `ThreadLocal`) supplies the initial value when `get()` on the current thread has no entry yet.
- `childValue(parentValue)` supplies the **inherited initial value** when a child thread is created if the creating thread currently has a corresponding entry.

If a thread did not receive an inherited entry, its first `get()` may invoke `initialValue()`. Therefore, when testing inheritance on/off, account for `initialValue` overrides or `withInitial`: do not assume `get() == null` is the only way to detect "not inherited."

## 8. When to Use, When to Avoid?

**May be appropriate** when you genuinely spawn a small number of child threads with a clear task relationship, need to pass **immutable initial values**, do not rely on hard-to-control worker reuse, and actively manage the lifecycle.

**Avoid using by default** when:

- Running on a fixed/cached thread pool or callback chains without controlling which thread executes.
- Context contains complex mutable objects, large buffers, connections, transactions, closeable resources, or references to large object graphs.
- The system handles many independent requests and risks context leakage or identity confusion across tasks.
- Creating a very large number of virtual threads where inheritance is not truly needed.
- Wanting to "automatically" guarantee every async function receives the caller's data: this API makes no such contract.

Pragmatic order of preference:

1. **Pass context as a parameter** or place it in an object representing the request/job whenever possible.
2. If you must use an executor with a thread-local-dependent API, **capture on submit + bind on run + restore in finally**.
3. Use `InheritableThreadLocal` when **child thread initialization** itself is the desired boundary and the data is controlled.
4. On Java 25+, consider **`ScopedValue`** for primarily read-only context scoped to a call stack; note that its semantics and version requirements differ from `InheritableThreadLocal`.

`ScopedValue` is a standard API in Java 25 (JEP 506), providing scoped bindings for one-way data sharing down the call stack. It is not a way to "enable inheritance for arbitrary threads" and should not be confused with `InheritableThreadLocal`. If a program must remain Java 21-compatible, this Java 25 API cannot be used without changing the runtime/source baseline.

## 9. Common Misconceptions

| Misconception | Reality |
|---|---|
| "The child reads the parent's value at `start()` time." | It reads **the initial copy taken when the child was created**. |
| "`InheritableThreadLocal` keeps parent and child context in sync." | There is no continuous or bidirectional value synchronization. |
| "The child calling `set()` updates the parent." | No; each thread has its own mapping. |
| "Two threads always hold two independent objects." | By default `childValue` returns the same reference; mutable objects can be shared. |
| "Submitting a new request to an executor updates the worker." | No; the worker reuses old context unless explicitly bound and cleaned up. |
| "Calling `remove()` in the parent clears the child too." | It clears only the calling thread. |
| "Virtual threads do not support ThreadLocal." | They do; however, memory cost and lifecycle must be considered. |
| "Disabling inheritance requires an external non-JDK API." | Java 21 `Thread.Builder.inheritInheritableThreadLocals(false)` supports it directly. |
| "Having context removes the need to pass authorization info." | Implicit context is easily mis-inherited; access rights must be verified at the proper business boundary. |

## 10. Checklist for Concurrency Code Reviews

- [ ] Clearly identify the thread **creating** the new thread, not just the thread **submitting the task**.
- [ ] If using an executor, determine when workers are created and whether they are reused.
- [ ] Distinguish plain `ThreadLocal` from `InheritableThreadLocal`; do not assume identical behavior.
- [ ] Inherit only truly necessary data; prefer immutable values or `childValue` copying to the required depth.
- [ ] Every bind has a clear scope and `finally` cleanup at the point of use.
- [ ] Do not store passwords, tokens, large request objects, or long-lived connections in implicit context.
- [ ] Test multiple consecutive tasks on **the same worker** to catch stale context and leakage.
- [ ] With virtual threads, consider `inheritInheritableThreadLocals(false)` when inheritance is not needed.
- [ ] Verify the JDK version if using `Thread.ofVirtual()` (Java 21+) or `ScopedValue` (Java 25+).

## 11. Self-Practice

**Question 1.** The parent calls `set("A")`, creates a child using `unstarted(...)`, then calls `set("B")`, and only then calls `start()`. When using `InheritableThreadLocal<String>`, what does the child receive? Why?

**Question 2.** A `newSingleThreadExecutor()` processes a task for user A and then a task for user B. If the worker inherited user A at creation time, why might task B see user A even though the caller changed the context?

**Question 3.** Why might returning `new ArrayList<>(parentValue)` from `childValue(parentValue)` still be insufficient when the list contains mutable objects?

**Question 4.** Does calling `remove()` in the parent guarantee that the inherited data no longer exists in a running child?

**Question 5.** When needing to pass a correlation ID through an executor that reuses workers, which approach has a more controllable lifecycle: relying on inheritance at worker creation time, or capture–bind–finally–restore per task?

**Answer hints:** (1) `"A"`, because inheritance happens at **creation** time; (2) the worker is reused and does not update automatically per task; (3) a shallow copy still shares the elements; (4) no; (5) capture–bind–restore per task or parameter passing.

## Official Java Documentation

- [InheritableThreadLocal (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheritance semantics and `childValue`.
- [Thread.Builder (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): thread creation, inheritance timing, and `inheritInheritableThreadLocals(boolean)`.
- [Executors (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): executors and worker management.
- [JEP 444 – Virtual Threads](https://openjdk.org/jeps/444): virtual threads and notes on thread-local data.
- [JEP 506 – Scoped Values](https://openjdk.org/jeps/506): scoped context API finalized in Java 25.

> **Core principle:** `InheritableThreadLocal` only transfers **an initial value when a child thread is created**. When code crosses executors, thread pools, or mutable contexts, you must manage data propagation and cleanup according to the **task lifecycle**.