# Do Not Store Mutable Business State in Shared Context

## 1. The Problem in Java Concurrency

A Java application can process many requests concurrently: each request has a different user, order, amount, permissions, and processing state. **Mutable business state** is data that can change during processing, such as `currentOrder`, `cartItems`, `balance`, `discount`, or `currentUser`. If multiple tasks look at **the same mutable context object**, they can overwrite each other's data, causing an operation for request A to mistakenly use request B's data.

This is a **state ownership boundary** bug: data that belongs to a single request/task is placed where multiple requests read and modify it. This bug occurs with both platform threads and virtual threads; adding `volatile`, `synchronized`, or `ConcurrentHashMap` does not automatically create isolation between requests.

In the **Thread Context** chapter, we need to distinguish between:

- **Execution context**: data accompanying a single execution, typically including request ID, correlation ID, actor/user ID, locale, trace context, or observability information. It should be small, have a clear lifetime, and preferably be immutable.
- **Business state**: data that determines business outcomes, such as cart line items, inventory, money transfer status, or order processing state. It needs its own owner, lifecycle, and update rules.
- **Shared state**: data that multiple tasks genuinely need to share, such as a synchronized cache, system counters, or a persistent data store. If mutable, it must have an update protocol that guarantees business invariants.
- **Thread-local context**: a way to bind a value to the current thread; it does not automatically make the inner object immutable, does not automatically turn the data into a request's property, and does not automatically propagate data to every other thread.

Principle: **context carries identification and observability information; business state lives in parameters, results, entities, or storage managed with appropriate concurrency rules**.

## 2. What Constitutes a Risky "Shared Context"?

The design patterns below easily turn per-request information into global state:

```java
// Wrong example: all tasks share the same user variable.
static String currentUserId;

// Wrong example: a single map used for every request.
static final java.util.Map<String, Object> CONTEXT =
        new java.util.concurrent.ConcurrentHashMap<>();

// Wrong example: a singleton holding the "order being processed".
final class ProcessingContext {
    String currentOrderId;
    long currentAmount;
}
```

The three snippets above only illustrate anti-patterns, **not standalone programs**. `ConcurrentHashMap` can protect the safety of `put/get` operations on the map itself, but it does not prevent A from calling `put("currentUser", "alice")` and then B overwriting it with `"bob"`. When A reads next, the map is completely memory-consistent, yet the value belongs to request B. **A thread-safe container does not mean request-safe business data.**

Another example that looks safe:

```java
static final ThreadLocal<java.util.Map<String, Object>> CTX =
        ThreadLocal.withInitial(java.util.HashMap::new);
```

Each thread gets its own default `HashMap`, but that is only per **thread**, not per request. A platform thread in an executor can run multiple requests sequentially; if you forget to clear/restore state, the next request receives the previous one's data. Conversely, if someone calls `CTX.get()` and passes that map reference to another task, two threads can modify **the exact same map** concurrently. `ThreadLocal` neither copies nor protects the stored object.

## 3. Java 21+ Example: The Same Context Corrupts Two Requests' Data

The standalone program below forces an ordering so the bug appears **deterministically**, without depending on the luck of a race condition. Two virtual threads share a single global map. Request Alice writes `alice` and waits for Bob to write `bob`; when Alice reads back, the data has been overwritten.

Save as `SharedContextPitfall.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedContextPitfall {
    private static final Map<String, String> SHARED =
            new ConcurrentHashMap<>();

    // Immutable metadata snapshot for each request.
    private record RequestContext(String requestId, String userId) {}

    private static String process(RequestContext context) {
        // Do not read "currentUser" from a global variable.
        return context.userId();
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch alicePublished = new CountDownLatch(1);
        CountDownLatch bobPublished = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> aliceWrong = executor.submit(() -> {
                SHARED.put("currentUser", "alice");
                alicePublished.countDown();
                bobPublished.await();
                return SHARED.get("currentUser");
            });

            Future<String> bobWrong = executor.submit(() -> {
                alicePublished.await();
                SHARED.put("currentUser", "bob");
                bobPublished.countDown();
                return SHARED.get("currentUser");
            });

            // These two results reflect the same shared context.
            System.out.println("shared alice=" + aliceWrong.get());
            System.out.println("shared bob=" + bobWrong.get());

            RequestContext alice = new RequestContext("A", "alice");
            RequestContext bob = new RequestContext("B", "bob");

            Future<String> aliceSafe =
                    executor.submit(() -> process(alice));
            Future<String> bobSafe =
                    executor.submit(() -> process(bob));

            System.out.println("isolated A=" + aliceSafe.get());
            System.out.println("isolated B=" + bobSafe.get());
        }
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac SharedContextPitfall.java
java SharedContextPitfall
```

Exact output:

```text
shared alice=bob
shared bob=bob
isolated A=alice
isolated B=bob
```

Explanation:

1. `SHARED` is a proper `ConcurrentHashMap` and every `put/get` operation is valid.
2. Both requests are still wrong from a business perspective because both use **a single process-wide key `"currentUser"`**.
3. `CountDownLatch` forces Alice to wait until Bob has written; therefore the bug reproduces consistently.
4. The correct version creates **two separate `RequestContext` instances**, passed explicitly into the processing function. Running on virtual threads does not change the logic.
5. `Future.get()` waits for the task to complete and ensures errors in the task are reported to the caller. `try-with-resources` closes the executor cleanly according to its lifecycle.

Do not interpret this example as "every shared map is wrong." A cache or index can be shared safely when designed for sharing; the problem is storing **a single request's private value under a single global key** and treating it as the current context for all tasks.

## 4. ThreadLocal: Per-Thread Value Is Not Per-Request State

`ThreadLocal<T>` holds one value slot **per thread**. Two different threads calling `get()` on the same `ThreadLocal` object access two separate slots. However:

- **Platform-thread pools reuse threads**: request A finishes, but the thread does not die; if state is not cleared, request B running on that thread can read leftover values.
- **Offloading work to a new thread**: `ThreadLocal` generally does not automatically propagate to a newly created thread or a task in an executor. Code running on another thread may see `null`/the default value.
- **Mutable objects stored inside**: `ThreadLocal` only isolates each thread's *slot*; if two slots point to an object shared by the code itself, the object still has aliases and races.
- **Virtual threads**: also support `ThreadLocal`, but typically have one virtual thread per task and should not be pooled. Many virtual threads each holding large payloads in thread-locals consume significant memory; do not use thread-locals to cache expensive objects per virtual thread.

### Example: A Subsequent Request Reads the Previous Request's Data by Mistake

Save the file `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.Executors;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        // One platform worker reused across three tasks.
        try (var executor = Executors.newSingleThreadExecutor()) {
            String first = executor.submit(() -> {
                USER.set("alice");
                return USER.get(); // Intentionally omit remove(): demonstrates the bug.
            }).get();

            String leaked = executor.submit(() -> {
                String value = USER.get(); // Sees "alice" from task 1.
                USER.remove();            // Clean up to observe task 3.
                return value;
            }).get();

            String cleared = executor.submit(
                    () -> String.valueOf(USER.get())).get();

            System.out.println("task1=" + first);
            System.out.println("task2=" + leaked);
            System.out.println("task3=" + cleared);
        }
    }
}
```

Run with JDK 21+:

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

```text
task1=alice
task2=alice
task3=null
```

`newSingleThreadExecutor()` guarantees tasks execute sequentially on one worker, so the second request seeing the first request's data is deliberately demonstrated. The example **intentionally contains a bug in task 1**; never omit cleanup like this in production code.

If library compatibility forces you to use a thread-local for short-lived metadata, bound its lifecycle:

```java
// Illustrative snippet inside a handler method:
USER.set(userId);
try {
    processRequest();
} finally {
    USER.remove();
}
```

In this example, `USER`, `userId`, and `processRequest()` must be defined by the application; **this is a snippet, not a standalone runnable program**. When an earlier binding might already exist on the same call stack, replacing an old binding with a new one and then calling `remove()` can wipe out the outer scope's binding; design the context owner and the rule for restoring the previous value explicitly. The best approach is still to use explicit parameters whenever possible.

## 5. InheritableThreadLocal Does Not Turn Mutable Context into an Independent Copy

`InheritableThreadLocal<T>` can pass an **initial value** from a parent thread to a child thread at thread creation time. By default, `childValue(parentValue)` returns **the exact same reference** as the parent. For example:

```java
import java.util.ArrayList;
import java.util.List;

InheritableThreadLocal<List<String>> tags = new InheritableThreadLocal<>();
List<String> sharedTags = new ArrayList<>();
tags.set(sharedTags);

Thread child = Thread.ofVirtual().start(() -> {
    tags.get().add("child");
});
child.join();

System.out.println(sharedTags); // [child]
tags.remove();
```

The above is a **snippet** using statements inside a method; to run standalone, wrap it in a class and `main`. It shows that the parent and child hold the same `ArrayList` reference, so modifications from the child affect the object seen by the parent. The example intentionally uses `join()` to avoid reading an unsynchronized `ArrayList` concurrently. If both threads modify it concurrently, that is also a **data race**.

Do not rely on inheritance to pass mutable business state; use messages, separate snapshot copies, or immutable parameters. When creating threads, some `Thread.Builder` APIs allow `inheritInheritableThreadLocals(false)`; however, that only disables inheritance and **does not solve the data ownership problem**.

## 6. Record, `final`, and Unmodifiable Do Not Automatically Provide Deep Immutability

A convenient way to carry per-request metadata is to create an immutable value object:

```java
record RequestContext(
        String requestId,
        String userId,
        String traceId
) {}
```

`String` is immutable and `record` fields are `final`, so with the components above the context is suitable for shared reading without worrying that a task will mutate the `userId` field after creation. However, **a record is only immutable at the field reference level**; it does not automatically deep-copy inner objects:

```java
record CartContext(java.util.List<String> productIds) {}

var products = new java.util.ArrayList<String>();
products.add("book");
var context = new CartContext(products);
products.add("laptop"); // context.productIds() also sees laptop.
```

If metadata needs to contain a collection, create a **snapshot** with `List.copyOf` / `Map.copyOf` / `Set.copyOf`, and consider deep-copying mutable elements as well:

```java
import java.util.List;
import java.util.Objects;

record SafeContext(String requestId, List<String> roles) {
    SafeContext {
        Objects.requireNonNull(requestId);
        roles = List.copyOf(Objects.requireNonNull(roles));
    }
}
```

This is a declaration snippet that can be placed in an appropriate Java file; it has no standalone `main`. `List.copyOf` creates a list that cannot be modified through the list API and is detached from structural changes to the input list; here the elements are immutable `String`s. With `List<MutableOrder>`, an unmodifiable list **can still contain `MutableOrder` instances that are mutated internally**. Do not store such mutable entities in a context just because you wrapped them in an "immutable" list.

Also, do not confuse `final Map<K,V>` with an immutable map: `final` prevents reassigning the variable/reference, but does not prevent `map.put(...)`.

## 7. Choosing How to Pass Data: Explicit Parameter, ThreadLocal, ScopedValue

| Need | Appropriate Approach | What to Avoid |
| --- | --- | --- |
| Calculate order fee from request data | `OrderInput`/`OrderSnapshot` parameter, explicit return value | Storing mutable `currentOrder` in global/shared context |
| Pass request ID/user ID across many methods | Explicit parameters; `ThreadLocal` or `ScopedValue` can be used for metadata that must be propagated implicitly | Expanding context into a "bag" holding every business entity |
| Invoke a task on another executor | Capture immutable context and pass into `Runnable`/`Callable`/parameters | Assuming `ThreadLocal` automatically follows the task |
| Multiple tasks updating inventory concurrently | Dedicated state owner and appropriate atomic update/transaction protocol | Shared `Map<String,Object>` with unprotected check-then-act operations |
| Share a read cache | Concurrently designed cache, safe keys/values, expiration policy | Cache containing mutable objects that callers mutate directly |
| Logging/correlation within a call stack | Short, immutable IDs with a clear lifecycle | Holding request body/connections/large objects in thread-locals |

### ScopedValue on Java 25+

`ScopedValue<T>` became a stable API in **JDK 25** (introduced in preview since JDK 21). It provides **execution-scoped binding**, well-suited for read-only data passed across many methods, especially when combined with supported structured subtask constructs. Unlike `ThreadLocal.set`, which can mutate the binding from arbitrary code, code inside the scope normally only reads the current binding, and the binding automatically ends when leaving the scope.

```java
// JDK 25+ snippet, not a standalone program.
record RequestMetadata(String requestId, String actorId) {}

private static final ScopedValue<RequestMetadata> CURRENT =
        ScopedValue.newInstance();

static void execute(RequestMetadata metadata) {
    ScopedValue.where(CURRENT, metadata).run(() -> {
        audit(CURRENT.get().requestId());
    });
}
```

`audit(...)` is an application-defined function; this is an illustrative **snippet**. The stable `ScopedValue` code above will not compile directly on JDK 21 without using that version's exact preview API and preview flags.

**Key takeaway:** a `ScopedValue` binding has a controlled lifecycle, yet it still holds **a reference to an object**. If you bind a mutable `HashMap`, `ArrayList`, or `Order`, code with access can still mutate that object. "Scoped" does not mean "deep immutable." Only bind small, immutable metadata that genuinely belongs to the execution flow.

A `ScopedValue` binding also does not automatically propagate to **every** independent executor task. Inheritance in structured subtasks must follow the task scope API/mechanism of the specific JDK you are running. Across ordinary thread/process boundaries or message queues, pass metadata intentionally.

## 8. Where Should Business State Live?

Decide based on **data ownership** and **when updates are needed**, rather than the currently executing thread.

### 8.1. State Needed Only Within a Single Task

Use parameters, local variables, objects scoped to the task's lifetime, and return values. For example:

```java
record OrderInput(String orderId, long subtotal, long discount) {}
record OrderResult(String orderId, long payable) {}

static OrderResult calculate(OrderInput input) {
    if (input.subtotal() < 0 || input.discount() < 0 ||
            input.discount() > input.subtotal()) {
        throw new IllegalArgumentException("invalid amount");
    }
    return new OrderResult(
            input.orderId(),
            input.subtotal() - input.discount());
}
```

This is an illustrative declaration snippet that can live in an appropriate Java class. The variables and result belong to a single `calculate` invocation and cannot be modified by another request via a global `currentAmount` variable. The example uses `long` in a conventional smallest currency unit; this article focuses on concurrency, not multi-currency rules.

### 8.2. State That Multiple Tasks Need to Update Concurrently

Here **genuine shared mutable state exists**. Move the state into an object with clear ownership, a data store/transaction, a mailbox/actor, or a concurrent structure with protected invariants. For example, "only one item left" requires checking and decrementing inventory as **one atomic logical step**: a plain `ConcurrentHashMap.get` followed by `put` is insufficient when multiple tasks purchase concurrently.

`AtomicInteger` is suitable for simple counters; `ConcurrentHashMap.compute(...)` can support single-key updates with appropriate consistency rules, but it does not provide transactions across multiple keys or a database. When business logic spans a database or external system, you need the corresponding consistency mechanism where the data is managed. Do not put a `synchronized` block around a "request context" and assume you have protected an entire distributed transaction.

### 8.3. Shared Read-Only State

You can share immutable configuration, immutable catalogs/lookups, thread-safe formatters (for example `java.time.format.DateTimeFormatter`), or a snapshot after construction is complete. You must publish the object safely and never expose references to mutable components for callers to modify.

In Java, **safe publication** and **true immutability** are complementary: an object that is safely published yet still mutable still requires synchronization for subsequent concurrent modifications.

## 9. How to Identify and Fix Bugs in a Codebase

When you see classes like `RequestContextHolder`, `UserContext`, `ProcessingContext`, or static utilities, inspect carefully:

1. Are there any `static`/singleton fields named `currentUser`, `currentOrder`, `pendingPayment`, `cart`, `amount`, or `transactionState`?
2. Does the context contain a `Map<String,Object>`, `List`, entity, or mutable DTO exposed directly via a getter?
3. Is there a `ThreadLocal.set(...)` without a matching `remove()` in `finally`? Is cleanup scattered across multiple places so the owner is unclear?
4. Does a method accept a context and silently mutate it, causing call order to change the outcome?
5. Does the code spawn a child thread, executor task, `CompletableFuture`, or new virtual thread and expect to see the same thread-local without passing data?
6. Are logs correlated by `requestId` to check whether one handler accessed another request's `userId/orderId` by mistake?
7. Is there a business rule requiring atomic updates whose implementation only locks individual collection operations?

Controlled refactoring workflow:

- **Step 1:** Classify fields: per-request immutable metadata, in-request business data, shared domain state, or resource holder.
- **Step 2:** For per-request business data, move it into parameters or a task-private object with clear mutability permissions and lifecycle; preferably pass immutable snapshots between tasks.
- **Step 3:** For shared domain state, design ownership and atomicity/transactions at the right level; verify invariants under concurrent load.
- **Step 4:** For metadata that truly needs implicit propagation, keep the scope small and enforce cleanup/binding rules; avoid carrying mutable domain objects.
- **Step 5:** Test multiple requests with different actors and data running concurrently, reusing a platform thread pool, with errors/timeouts/cancellations and branches that spawn new threads.

### Testing Matters More Than "Just Running Many Times"

Running 1,000 times may still fail to reproduce a timing bug. Use `CountDownLatch`/`CyclicBarrier` to **force intentional interleaving**, like in the Section 3 example, then assert that each request's result matches its own input. Add exception and cancellation cases to verify cleanup in `finally`. For shared domain state, verify the final invariants: total items sold never exceeds stock, transferred money is never lost or duplicated, and state never transitions illegally.

## 10. Common Misconceptions

**"Using ConcurrentHashMap is enough."** A thread-safe collection keeps container operations intact, but it does not fix two requests accessing the same `currentUser` key or split check-then-act rules.

**"Each thread has its own ThreadLocal, so each request has its own data."** False when a platform thread runs multiple requests sequentially or when code shares a mutable reference. `ThreadLocal` isolates by thread, not by business scope.

**"InheritableThreadLocal automatically copies data for child threads."** By default it can pass the same object reference. Copying a reference is not a deep copy.

**"Record/final makes everything immutable."** Reference fields cannot be reassigned, but inner objects/lists remain mutable unless proper snapshots are created.

**"ScopedValue will protect all state."** ScopedValue bounds the lifetime of the *binding*; it does not make the bound object immutable and does not create transactions for business data.

**"Switching to virtual threads eliminates context mix-ups."** Virtual threads enable a one-thread-per-task model, but they do not fix shared static holders, mutable aliases, or ownership bugs. Also, do not cache large objects in a `ThreadLocal` per virtual thread.

**"Using synchronized on every access is enough."** Synchronization can prevent bytecode-level races, yet still let request A read B's state depending on lock acquisition order; it can also cause contention and reduce throughput. First, design the right scope.

**"Context is convenient, so let's pass the whole entity to avoid adding parameters."** When a mutable entity is attached to an ambient context, functions implicitly depend on it, becoming hard to test, hard to trace mutation paths, and prone to cross-request data leaks. Make dependencies and ownership explicit.

## 11. Design and Operations Checklist

- [ ] Context holds **small, sufficient metadata**: request/correlation ID, actor ID, trace ID; no mutable order/cart/payment.
- [ ] Each request/task has its own input snapshot; processing functions have explicit parameters and results.
- [ ] No singleton/static "current business object" shared across concurrent tasks.
- [ ] No mutable collection/DTO exposed directly through context; deep immutability has been considered.
- [ ] If ThreadLocal is unavoidable, every binding has a clear owner, lifecycle, and `finally/remove` or restore rule.
- [ ] Executor/virtual thread/async boundaries propagate context appropriately, without assuming thread-locals follow tasks automatically.
- [ ] Shared domain state has atomicity/invariants/transactions at the right level.
- [ ] Tests force interleaving and verify no actor, request, or order mix-ups; cleanup on exception is tested.
- [ ] Metrics/logs include request ID to detect anomalies, without logging passwords, tokens, or unnecessary sensitive data.

## Conclusion

**Thread context is a mechanism to help code know what it is currently working on; it is not a shared store for mutable business state.** In Java concurrency, prevent data corruption by identifying the owner of each piece of state, passing request data explicitly or via clearly scoped immutable metadata, and using synchronization/transactions when multiple tasks genuinely need to update shared domain state. `ThreadLocal`, `InheritableThreadLocal`, and `ScopedValue` each have their own use cases; none of them replaces proper ownership design.

## References

1. Oracle, [ThreadLocal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, lifecycle, and `remove()`.
2. Oracle, [InheritableThreadLocal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): inherited values and `childValue`.
3. Oracle, [Virtual Threads — Java SE 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): one thread per task, warnings about caching in thread-locals.
4. Oracle, [ScopedValue — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): scoped bindings and limitations when passing mutable objects.
5. OpenJDK, [JEP 506: Scoped Values](https://openjdk.org/jeps/506): API stabilization in JDK 25.
