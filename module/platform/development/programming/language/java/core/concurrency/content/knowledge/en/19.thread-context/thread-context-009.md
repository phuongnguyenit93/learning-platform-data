# Prefer Explicit Parameters When Data Flow Is Simple

## 1. The Problem: Context Data Following a Task

In a concurrent Java program, a task often needs some accompanying data: `requestId`, `tenantId`, username, locale, deadline, or routing information. This data is collectively called **execution context**. When offloading work to another thread, the program must decide how to deliver the context to where it is processed.

There are two common design styles:

- **Explicit parameters:** a method receives whatever data it needs via its parameters; the caller is responsible for providing it.
- **Implicit thread-bound context:** a method calls `ThreadLocal.get()` or reads another context mechanism even though its signature does not indicate what data it depends on.

**Rule of thumb:** when data only flows through a few methods, **prefer explicit parameters**. This keeps dependencies right in the method signature, makes testing straightforward, and does not depend on whether the task runs on a platform thread, an executor worker, or a virtual thread.

An example of a readable design:

~~~java
int calculateFee(int amount, boolean premium) {
    return premium ? 0 : amount / 20;
}
~~~

The caller clearly sees both inputs. Compare that with relying on hidden context:

~~~java
int calculateFee(int amount) {
    boolean premium = PREMIUM_CUSTOMER.get();
    return premium ? 0 : amount / 20;
}
~~~

These are two **illustrative method snippets**, not standalone Java classes. `PREMIUM_CUSTOMER` in the latter snippet is assumed to be a `ThreadLocal<Boolean>`; if no value has been set, `get()` can return `null` and unboxing can throw a `NullPointerException`. Even if the null issue is handled, the contract requiring the caller to set up the thread context beforehand remains hidden.

There is no mandatory rule to eliminate `ThreadLocal` completely. The advice here applies when **data flow is simple**, meaning the values and their path are short enough to be expressed directly.

## 2. Why Explicit Parameters Are Often Better

Consider the processing chain:

~~~text
handleRequest(context, amount)
    -> calculateTotal(amount)
    -> formatResponse(context, total)
~~~

`calculateTotal` only performs arithmetic, while `formatResponse` uses the request ID and tenant ID. Each method receives only the data it needs, rather than silently reading thread state.

Concrete benefits:

1. **Dependencies are visible:** looking at the signature tells you whether a method needs `requestId` or `tenantId`.
2. **Independent testing:** call the method with sample data without setting up or tearing down thread context in test fixtures.
3. **Easy crossing of async boundaries:** a closure captures a value and calls `process(context)` on any thread.
4. **Reduced cross-request data leaks:** a thread pool may reuse workers, but parameters from a previous call do not linger into the next call.
5. **Easier refactoring:** moving a task between regular threads, virtual threads, or an executor does not break implicit context setup preconditions.
6. **Simpler lifecycle control:** the context object lives as long as the reference held by the task; there is no `ThreadLocal` slot to clean up after each run.

There is a trade-off: when the same piece of information must be passed through dozens of layers that do not use it, signatures can become verbose. Only then should you consider designing a context object or a clearly scoped context mechanism. Avoiding adding two parameters to two methods is not enough reason to introduce a thread-local.

## 3. Complete Example with Java 17+: Immutable Context

Use a `record` to represent a context value composed of immutable `String`s. Methods pass the required data along the processing path without reading thread state.

Save to **`ExplicitContextDemo.java`**:

~~~java
import java.util.Objects;

public class ExplicitContextDemo {
    record RequestContext(String requestId, String tenantId) {
        RequestContext {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(tenantId, "tenantId");
        }
    }

    static int calculateTotal(int amount, int shippingFee) {
        return amount + shippingFee;
    }

    static String formatResult(RequestContext context, int total) {
        return context.requestId() + " / "
                + context.tenantId() + " -> " + total;
    }

    static String handleOrder(
            RequestContext context, int amount, int shippingFee) {
        int total = calculateTotal(amount, shippingFee);
        return formatResult(context, total);
    }

    public static void main(String[] args) {
        RequestContext context = new RequestContext("req-42", "tenant-A");
        System.out.println(handleOrder(context, 150, 15));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Exact stdout:

~~~text
req-42 / tenant-A -> 165
~~~

Analysis:

- `handleOrder` and `formatResult` need the context, so their signatures show it.
- `calculateTotal` does not need the context, so it does **not** accept a context parameter just to forward it along.
- `RequestContext` can be safely shared in this example because its `String` fields are immutable. **A record does not guarantee deep immutability**: if you add a mutable `List` or `Map`, create a snapshot or defensive copy.
- No assumptions are needed about which thread is running; the result depends solely on the input data and method logic.
- For values used individually, you can pass `requestId` or `tenantId` directly instead of always wrapping the entire context.

A simple test can call `handleOrder(new RequestContext(...), 150, 15)`, compare the returned string, and finish. It does not matter which thread the test runner uses or whether tests run in parallel.

## 4. `ThreadLocal` Solves a Different Problem and Has Its Own Risks

**ThreadLocal** is an option when a legacy API needs to read the state of the **currently running thread** across many call layers; it does not automatically turn that state into per-request data. In a worker pool, task A might set a context and finish, while task B running on the same worker reads the stale data if there is no cleanup.

~~~java
// Snippet with ThreadLocal<String> CURRENT and method handle():
CURRENT.set(requestId);
try {
    handle();
} finally {
    CURRENT.remove();
}
~~~

The snippet above must be placed at the **task's context-ownership boundary**, and you must also check whether nested scopes need to **restore the previous value**. If logical calls cross into another executor/thread, `ThreadLocal` does not automatically propagate upon submission; you still have to capture and bind it on the worker side or pass explicit parameters.

This article prioritizes **passing immutable variables/records directly** because dependencies are easy to inspect and no implicit cleanup is required. The set/get/remove rules, leak bugs on pooled workers, and propagation wrappers are covered in separate dedicated articles.

## 5. Passing Context to an Executor via Closure

When a method dispatches work to an executor, take a snapshot of the context **at the handoff boundary**, then capture it in a `Runnable` or `Callable`. The task receives the data via parameters:

~~~text
caller: contextA, contextB
    |
    +-- submit(() -> process(contextA))
    |                    |
    |                    +-- any worker
    |
    +-- submit(() -> process(contextB))
                         |
                         +-- any worker
~~~

Save **`ExplicitExecutorDemo.java`** (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExplicitExecutorDemo {
    record RequestContext(String requestId, String tenantId) {}

    static String process(RequestContext context, int amount) {
        return context.requestId()
                + " [" + context.tenantId() + "]: " + amount;
    }

    public static void main(String[] args) throws Exception {
        RequestContext first = new RequestContext("req-A", "tenant-X");
        RequestContext second = new RequestContext("req-B", "tenant-Y");

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> f1 =
                    executor.submit(() -> process(first, 100));
            Future<String> f2 =
                    executor.submit(() -> process(second, 200));

            System.out.println(f1.get());
            System.out.println(f2.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
~~~

Exact stdout:

~~~text
req-A [tenant-X]: 100
req-B [tenant-Y]: 200
~~~

The tasks may finish in any order, but the program calls `f1.get()` and then `f2.get()`, so the order of the two printed lines is deterministic. `Future.get()` also allows the caller to receive task failures via `ExecutionException`.

`first` and `second` are effectively final local variables, so the lambdas are allowed to capture them. Both records contain immutable `String`s. If you replace them with a mutable object and mutate it after `submit`, threads may observe unexpected changes or encounter data races. **Explicit parameters solve data delivery; immutability/synchronization solves shared mutable state.**

## 6. Virtual Threads (Java 21+) Do Not Change the Rule

Virtual threads are scheduled by the JVM onto carrier threads. A virtual thread can be unmounted while waiting on I/O and resumed on a different carrier. Method parameters and task variables follow normal execution flow, so there is no need to tie request context to carrier identity.

Save **`ExplicitVirtualThreadDemo.java`** (JDK 21+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExplicitVirtualThreadDemo {
    record RequestContext(String requestId, String tenantId) {}

    static String process(RequestContext context) {
        return context.requestId()
                + "/" + context.tenantId()
                + ": virtual=" + Thread.currentThread().isVirtual();
    }

    public static void main(String[] args) throws Exception {
        RequestContext a = new RequestContext("req-01", "tenant-A");
        RequestContext b = new RequestContext("req-02", "tenant-B");

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first =
                    executor.submit(() -> process(a));
            Future<String> second =
                    executor.submit(() -> process(b));

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitVirtualThreadDemo.java
java ExplicitVirtualThreadDemo
~~~

Exact stdout:

~~~text
req-01/tenant-A: virtual=true
req-02/tenant-B: virtual=true
~~~

`Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread for each task. `try-with-resources` closes the executor and completes lifecycle management. There is no implicit "thread context" setup; `process(context)` does not care whether it runs on a virtual thread or a platform thread.

If there is only one task and no return value needs to be collected, you can use the direct API:

~~~java
RequestContext context = new RequestContext("req-03", "tenant-A");
Thread worker = Thread.startVirtualThread(() -> process(context));
worker.join();
~~~

This is a **code snippet** inside a method where `RequestContext` and `process` are defined, and `InterruptedException` is handled or declared. `Thread.join()` only waits for completion; it does not return a result or rethrow uncaught exceptions from the worker. When you need structured results and errors, use `Callable`/`Future` as shown above.

**Note:** virtual threads still have their own `ThreadLocal`; they do not "read the carrier's ThreadLocal" in an arbitrary way. The issue with implicit context is that it clings to a specific thread or scope and requires proper propagation/binding rules when a task branches out. Explicit parameters avoid forcing readers to guess those rules.

## 7. Signature Design: Pass Separately or Group into a Context?

### 7.1. Few Data Items, Used in One Method

When a method only needs two values, use two parameters:

~~~java
String formatMessage(String requestId, String localeTag) {
    return "[" + requestId + "] " + localeTag;
}
~~~

There is no need to create a 20-field `RequestContext` for this operation.

### 7.2. A Cohesive Group of Data That Travels Together

When a group of fields together describes a request, you can group them into an immutable object:

~~~java
record RequestContext(
        String requestId,
        String tenantId,
        java.util.Locale locale) {}
~~~

Do not turn the object into a **"bag of services and state"** containing database connections, HTTP responses, loggers, global config, and various mutable objects. Doing so merely replaces one implicit dependency with a broad dependency that is hard to reason about.

### 7.3. Methods That Do Not Use Context

Do not accept a context parameter just for convention if the method does not actually need it. Have the method take `amount` and `taxRate` if it only calculates tax. This keeps signatures meaningful, aids testing, and avoids coupling.

### 7.4. Context Containing Mutable Data

`record RequestContext(List<String> roles) {}` does not provide deep immutability. If multiple tasks look at that same list and one mutates it, a race condition still occurs. Take a snapshot before submitting:

~~~java
List<String> rolesSnapshot = List.copyOf(roles);
executor.submit(() -> checkRoles(rolesSnapshot));
~~~

This is a **code snippet** where `roles`, `executor`, and `checkRoles` are defined. `List.copyOf` creates an unmodifiable list; the elements inside can still be mutable if their types allow it. When you genuinely need shared mutable state, use a clear owner, locks, atomics, or an appropriate concurrent collection—do not assume "passing a param" automatically makes every operation thread-safe.

## 8. When to Consider Implicit Context

Some cross-cutting concerns across many layers can make manual passing inconvenient: tracing/correlation IDs across shared libraries, metadata attached to a scope, or third-party APIs that only read implicit context. In those cases, evaluate:

- Who **sets up** and **closes** the context?
- Is the context scoped to a single call, a task, a request, or the entire thread?
- Does it cross executor/child-thread boundaries, and by what rule must it propagate?
- Can data leak between requests?
- Is the data immutable and safe to share across subtasks?
- If an error or cancellation occurs mid-way, is `finally`/scope closing guaranteed to run?

Java 25 standardizes **`ScopedValue`** (JEP 506) for bounded-scope implicit reading, which fits certain multi-layer problems. It is a different mechanism from `ThreadLocal`: binding has a bounded scope, and propagation to child tasks depends on how tasks are created and managed. On Java 17/21, or when passing through only a few calls, parameter passing remains the simpler choice.

**Security note:** passing `userId` or `tenantId` properly does not perform authorization by itself. Authorization layers must still validate inputs and enforce resource access per request.

## 9. Common Scenarios and Decisions

| Scenario | Prefer | Why |
| --- | --- | --- |
| Fee-calculation method needs `amount` and `premium` | Two parameters | Small, clear dependencies |
| Request log-formatting method only needs `requestId` | Pass `requestId` | No thread context setup/cleanup needed |
| Several methods share `requestId`, `tenantId`, `locale` | Immutable `RequestContext` | Meaningful grouping without overly long signatures |
| Submit two tasks to an executor | Capture context then call `process(context)` | Independent of worker reuse |
| One virtual thread handles one request | Pass/capture context | Independent of carrier, easy to test |
| Framework/library requires multi-layer implicit context | Consider scoped/thread context mechanism | Requires clear scope, cleanup, and propagation |
| Multiple tasks need the same mutable counter | Atomic/lock or dedicated owner | Context propagation does not replace concurrency control |
| Work has a deadline | Pass deadline and design timeout/cancellation | Passing data does not automatically stop a task |

In the second example, a real logger sometimes has its own mechanism to attach a correlation ID automatically; that is a separate infrastructure decision. The table above is for **simple data flow in your own Java application code**.

## 10. Common Mistakes

1. **Hiding method inputs in `ThreadLocal`** even when the caller can pass them directly: increases difficulty in testing, debugging, and code review.
2. **Forgetting `remove()` in an executor**: data from a previous request can appear in another task on the same worker.
3. **Assuming `InheritableThreadLocal` propagates across every executor**: worker pools may have already been created before the request arrived.
4. **Capturing a mutable object and mutating it after `submit`**: the lambda still holds the same reference, not an immutable copy.
5. **Passing context to every method regardless of whether it uses it**: creates coupling and obscures real dependencies.
6. **Stuffing many services and large objects into a "Context"**: turns the object into an unwieldy service locator.
7. **Thinking `Future.get()` brings thread-local state back to the caller**: `get()` only returns the result or reports a task exception.
8. **Confusing thread identity with logical request identity**: a single request can split across multiple tasks/threads.
9. **Assuming explicit parameters eliminate all races**: mutable data still must be protected.
10. **Equating propagation with cancellation**: having a deadline in the context does not automatically interrupt the thread when time expires.

## 11. Review Checklist

- [ ] For a path spanning only a few methods, have you tried passing parameters instead of using `ThreadLocal`?
- [ ] Does each method receive **only the data fields it actually uses**?
- [ ] If several fields always travel together, have you considered a minimal, immutable context object?
- [ ] At `executor.submit`, `Thread.startVirtualThread`, or callbacks, is the context passed into the task explicitly?
- [ ] Are any mutable objects shared between tasks without a synchronization strategy?
- [ ] If `ThreadLocal` is still used, is there `try/finally` cleanup/restore and a test for worker reuse?
- [ ] Is there any false assumption that tasks of a single request run on the same thread?
- [ ] Do outputs, errors, and timeouts have their own propagation/lifecycle instead of relying on hidden state?
- [ ] Is data received from context checked for authorization when used in sensitive operations?

## 12. Official Documentation

- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove`.
- [Java SE 17 — `InheritableThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): value inheritance semantics.
- [Java SE 21 — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `startVirtualThread`, `join`, and `isVirtual`.
- [Java SE 21 — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): the virtual thread concurrency model.
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): bounded-scope context starting in JDK 25.
