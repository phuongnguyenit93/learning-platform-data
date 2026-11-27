# Reactor Context and How It Differs from ThreadLocal

## 1. Why Does a Reactive Application Need a Context Mechanism?

In backend applications, a request often carries metadata used across multiple processing layers: request ID, trace ID, current user, tenant, locale, or security information. Passing all these values as parameters to every method bloats method signatures and forces intermediate layers to forward data they do not directly use.

In traditional imperative applications, **ThreadLocal** is commonly used to solve this problem. A value is bound to the current thread; methods running on the same thread can read the value without receiving it via parameters.

That model breaks down if applied as-is to reactive programming. A request is not guaranteed to be processed on the same thread from start to finish. Reactor can shift execution across threads via operators such as **publishOn** and **subscribeOn**. Values stored in the initial thread's ThreadLocal do not automatically follow the request when the pipeline switches to another thread.

**Reactor Context** solves this problem by attaching metadata to the subscriber of a reactive pipeline. The Context travels with the subscription process and remains accessible even as the pipeline switches threads. It is Reactor's context mechanism, not another ThreadLocal.

## 2. How Does ThreadLocal Work by Thread?

ThreadLocal gives each thread its own copy of a value for the same ThreadLocal variable. Calling **set()** stores the value in storage associated with the current thread. Calling **get()** reads the value belonging to whichever thread executes that call.

Example:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
}

private void process() {
    String requestId = REQUEST_ID.get();
    System.out.println("Request: " + requestId);
}
~~~

In this imperative example, **handleRequest()** and **process()** run synchronously on the same thread. Thus, **process()** reads the value set by **handleRequest()**.

ThreadLocal is widely used in synchronous APIs such as logging MDC, certain servlet-stack security mechanisms, or code needing to bind data to a thread for the duration of a task.

The critical point is that ThreadLocal is bound to a **thread**, not to an application-level concept like a request, transaction, or logical unit of work. If work moves to another thread, the value on the original thread does not move along with it automatically.

## 3. Why Does ThreadLocal Run Into Problems in a Reactive Pipeline?

### 3.1. A Single Request Can Cross Multiple Threads

Reactor does not promise that a pipeline always runs on one thread. **publishOn** changes the scheduler used to execute operators downstream of where it is placed. **subscribeOn** affects the thread used for subscribing and the upstream source.

~~~text
Request A
    |
    v
Thread-1: start pipeline
    |
    v
publishOn(...)
    |
    v
Thread-7: process downstream section
~~~

If the request ID was stored in Thread-1's ThreadLocal, code running on Thread-7 reads Thread-7's ThreadLocal. Thread-1's value does not automatically appear there.

Illustrative example:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

Mono<String> result =
        Mono.just("start")
            .publishOn(Schedulers.parallel())
            .map(value -> REQUEST_ID.get());
~~~

If ThreadLocal was only set on the thread initiating the request, calling **get()** after **publishOn** can return **null** because the **map** operator runs on a different thread. Exact results depend on the scheduler and how ThreadLocal is set; what is certain is that Reactor does not automatically guarantee ThreadLocal values follow the pipeline.

### 3.2. Thread Pools Reuse Threads

Schedulers commonly use thread pools to reuse threads. Once a thread finishes a task, it can be reused for another task. If code sets a ThreadLocal and fails to clear it in time, stale values can remain on the thread and leak into the next task.

This is especially dangerous for per-request metadata such as user ID or tenant ID. A cleanup bug can cause logs or business logic to read data left over from an earlier task.

In the imperative model, a **try/finally** block usually keeps ThreadLocal lifecycle management fairly clear. In a reactive pipeline, a request may pause, resume on another thread, and complete later; a simple synchronous call scope cannot manage that entire lifecycle.

### 3.3. One Request Does Not Equal One Thread

The reactive model allows many requests to be multiplexed across a relatively small number of threads. One request may be processed by several threads at different points in time, while one thread may sequentially execute slices of many different requests.

Consequently, a thread is no longer an appropriate unit to represent a request's context. A mechanism is needed that binds data to the logical processing flow rather than whichever thread happens to run a given step.

## 4. What Is Reactor Context?

**Reactor Context is an immutable key-value structure attached to the subscriber of a reactive chain.** It lets operators read metadata supplied during subscription, even when execution hops across multiple threads.

Key characteristics:

- Context belongs to the subscriber and subscription, not to a specific thread.
- Context propagates during subscription across the Reactor pipeline.
- Context can be read at multiple points in the pipeline using Reactor APIs.
- Context is immutable: adding, replacing, or deleting a key produces a new Context.
- Each subscription has its own Context, allowing independent requests to carry distinct values.
- Context is primarily intended for orchestration and integration metadata, such as trace IDs, tenant IDs, or security information.

Context can store any object as a value. However, Context immutability does not mean every object inside it is immutable. Storing a mutable object and modifying it across multiple operators can still introduce race conditions. Prefer small, clear, immutable values.

Reactor exposes two common API types:

- **Context** is the type that can be created or updated with operations such as **put**, **putAll**, and **delete**.
- **ContextView** is a read-only view, typically passed when an operator accesses Context.

## 5. How to Write and Read Reactor Context

### 5.1. Writing Data with contextWrite

The **contextWrite** operator updates the Context provided to the upstream portion of the pipeline.

~~~java
Mono<String> greeting =
        Mono.just("hello")
            .map(value -> value.toUpperCase())
            .contextWrite(context -> context.put("userId", "user-42"));
~~~

Here, **contextWrite** produces a Context containing key **userId** with value **user-42**. That Context is supplied to upstream operators during subscription.

Because Context is immutable, calling **put** does not mutate a shared Context in place. It creates a new Context containing the updated entry. The lambda passed to **contextWrite** receives the current Context and returns the Context to use.

| API | Meaning |
|---|---|
| **put(key, value)** | Adds a key or replaces the value of an existing key |
| **putAll(otherContext)** | Combines entries from another Context |
| **delete(key)** | Creates a new Context without that key |
| **hasKey(key)** | Checks whether a key exists |
| **get(key)** | Reads a value; throws an error if the key does not exist |
| **getOrDefault(key, defaultValue)** | Reads a value or returns a default value |
| **getOrEmpty(key)** | Reads a value as an Optional |

### 5.2. Reading Data with deferContextual

To read Context at subscription time, Reactor provides **deferContextual**. The lambda receives a **ContextView** from which required values can be retrieved.

~~~java
Mono<String> greeting =
        Mono.deferContextual(context -> {
            String userId = context.getOrDefault("userId", "anonymous");
            return Mono.just("Hello " + userId);
        })
        .contextWrite(context -> context.put("userId", "user-42"));
~~~

When a subscriber subscribes, **deferContextual** reads the active Context and creates a publisher based on the **userId** value. The output of this example is **Hello user-42**.

Use **get()** when a key is mandatory and missing data should fail immediately. Use **getOrDefault()** when a sensible fallback exists. Avoid silently falling back for security or tenant data when a missing key should be treated as a configuration or flow error.

### 5.3. Example Composing Multiple Reactive Operations

A service can read order details and then write an audit log using a tenant ID retrieved from Context:

~~~java
private static final String TENANT_ID = "tenantId";

public Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order ->
                    Mono.deferContextual(context -> {
                        String tenantId = context.get(TENANT_ID);
                        return auditRepository.recordRead(order.getId(), tenantId)
                                .thenReturn(order);
                    }));
}
~~~

The caller can supply the tenant ID for the entire processing chain:

~~~java
return orderService.findOrder("order-100")
        .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

In this example, **contextWrite** sits downstream of the entire service chain. Because Context propagates backward during subscription, upstream operators—including the work inside **flatMap**—can read **tenantId**.

This passes metadata across multiple layers without adding a tenant parameter to every method. However, Context does not by itself enforce authorization or data isolation. Multi-tenant data queries must still apply tenant filters at the data-access layer and verify permissions appropriately. Never treat a value retrieved from Context as proof of user authentication.

## 6. Direction of Context Propagation in Reactor

This is the easiest detail to misunderstand when first learning Reactor Context.

Data in a pipeline normally flows from upstream to downstream. Context, however, is supplied during **subscription from downstream to upstream**. The final subscriber initiates the subscription; the subscriber's Context propagates backward through the operators.

~~~text
Data flow:
Source  ------------------------------>  Subscriber
        upstream                         downstream

Context on subscribe:
Source  <------------------------------  Subscriber
        upstream                         downstream
~~~

### 6.1. Why Is contextWrite Usually Placed at the End of the Chain?

Consider this example:

~~~java
Mono<String> result =
        Mono.deferContextual(context ->
                    Mono.just(context.get("requestId")))
            .map(requestId -> "Request: " + requestId)
            .contextWrite(context -> context.put("requestId", "req-123"));
~~~

The subscriber subscribes to the final publisher. **contextWrite** runs during subscription and creates the Context visible to upstream operators. Consequently, **deferContextual** can read **requestId**.

You can remember this rule as: **contextWrite affects everything written before it in the operator chain**, meaning the upstream section it wraps during subscription.

### 6.2. contextWrite Is Not a Global Variable

Each **contextWrite** scopes Context only for its corresponding upstream segment. It does not update a global Context, nor does it automatically expose the written value to downstream operators.

The example below places **contextWrite** before **flatMap**:

~~~java
Mono<String> result =
        Mono.just("order-100")
            .contextWrite(context -> context.put("tenantId", "tenant-17"))
            .flatMap(orderId ->
                    Mono.deferContextual(context ->
                            Mono.just(context.getOrDefault("tenantId", "missing"))));
~~~

**contextWrite** sits in the upstream branch of **flatMap**. It provides Context to its own upstream segment. The publisher created inside **flatMap** does not see values written at that position by default. If the goal is for **flatMap** and inner publishers to read the key, place **contextWrite** downstream:

~~~java
Mono<String> result =
        Mono.just("order-100")
            .flatMap(orderId ->
                    Mono.deferContextual(context ->
                            Mono.just(context.get("tenantId"))))
            .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

Understanding where to position **contextWrite** prevents missing-key errors even when **put** appears in the code.

### 6.3. Reading Context in Transformation Operators

Besides **deferContextual**, Reactor provides **transformDeferredContextual** to build a publisher transformation based on the subscriber's Context. This API is handy when packaging Context-aware logic into a reusable operator.

~~~java
Mono<String> result =
        Mono.just("order-100")
            .transformDeferredContextual((source, context) ->
                    source.map(orderId ->
                            orderId + " / tenant=" + context.get("tenantId")))
            .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

The **deferred** name emphasizes that the transformation is applied per subscription once the corresponding Context is available. This differs from reading metadata eagerly at pipeline assembly time.

## 7. Reactor Context Does Not Depend on Threads

A major advantage of Reactor Context is that it travels with the subscriber, so it does not depend on which thread executes an operator.

~~~java
Mono<String> result =
        Mono.just("start")
            .publishOn(Schedulers.parallel())
            .flatMap(value ->
                    Mono.deferContextual(context ->
                            Mono.just(value + " / " + context.get("requestId"))))
            .contextWrite(context -> context.put("requestId", "req-123"));
~~~

Even though **publishOn** switches downstream execution to another scheduler, **deferContextual** still reads **requestId**. Context travels along the subscription chain rather than copying ThreadLocals from one thread to another.

Distinguish these two concepts:

- **Scheduler** determines where and when tasks execute.
- **Reactor Context** supplies metadata attached to the subscriber so operators can access it during execution.

Context does not spawn threads, schedule work, or make blocking operations non-blocking. It simply provides a stable context for a reactive pipeline.

## 8. Comparing Reactor Context and ThreadLocal

| Criterion | Reactor Context | ThreadLocal |
|---|---|---|
| Bound to | Subscriber / subscription | Current thread |
| Scope | One reactive processing stream per subscription | One thread while the value is retained |
| Across thread switches | Context stays with the pipeline | Does not move automatically to a new thread |
| How to read | APIs such as `deferContextual`, `transformDeferredContextual` | `ThreadLocal.get()` |
| How to write | `contextWrite`, creating a new Context | `ThreadLocal.set()` on the current thread |
| Structural nature | Context is immutable; values inside may be mutable | Per-thread storage and mutable |
| Request isolation | Per subscriber, assuming each request has its own subscription | Per thread; thread pools may reuse threads |
| Best suited for | Metadata in reactive pipelines | Imperative code tied to a single thread |
| Common pitfalls | Misplacing `contextWrite`, missing keys, misunderstanding Context scope | Losing values across thread switches, forgetting `remove`, reading leftover values |

The two mechanisms serve different execution models. ThreadLocal remains useful in synchronous code and imperative libraries. Reactor Context is better suited when attaching metadata to a reactive pipeline that may span multiple threads.

## 9. What Kinds of Data Belong in Context?

Context should hold data describing the execution environment or identity of the flow, not become a dumping ground for full business state.

| Metadata Type | Example Key | Purpose |
|---|---|---|
| Correlation / trace ID | `traceId` | Correlate logs and traces across services |
| Request ID | `requestId` | Locate logs belonging to the same request |
| Tenant ID | `tenantId` | Provide tenant information to steps that need it |
| User identity | `userId` | Associate user identity with the pipeline |
| Security context | `SecurityContext` | Carry authentication and authority info in reactive security |
| Locale | `locale` | Select appropriate language or formatting |
| Transaction resources | Managed by Spring | Associate operations within the same reactive transaction |

Do not store large datasets, entity graphs, buffers, or mutable objects updated concurrently by multiple steps. Pass such data via publishers, business method parameters, or proper persistence mechanisms.

Key names should be consistent to avoid collisions across libraries and modules. Declare **static final** constants instead of scattering string literals across many classes. For shared libraries, pick clearly namespaced keys. When reading required keys, handle missing-key cases explicitly.

## 10. Integration with Logging, Security, and Tracing

### 10.1. Logging MDC

Many logging frameworks provide MDC (Mapped Diagnostic Context) to attach request IDs or trace IDs to log entries. Traditional MDC relies on ThreadLocal. Therefore, calling **MDC.put()** at the start of a reactive request does not guarantee the value will exist on every thread executing the pipeline.

There are two approaches:

1. Keep metadata in Reactor Context and populate MDC only inside the callback that actually writes logs.
2. Use the Context Propagation library to bridge Reactor Context with the ThreadLocal used by the logging library.

Example reading a trace ID from Reactor Context and temporarily placing it into MDC while handling a signal:

~~~java
.doOnEach(signal -> {
    if (signal.isOnNext()) {
        String traceId = signal.getContextView()
                .getOrDefault("traceId", "unknown");

        try (MDC.MDCCloseable ignored = MDC.putCloseable("traceId", traceId)) {
            log.info("Processed value: {}", signal.get());
        }
    }
})
~~~

This limits how long MDC is set inside the callback and automatically clears the value once logging completes. In production applications, choose the proper hook or logging integration library so logs emitted at other points also receive the appropriate context.

### 10.2. Spring Security in WebFlux

Spring Security on the traditional servlet stack relies on **SecurityContextHolder**, which binds `SecurityContext` to a thread via ThreadLocal. On the reactive stack, requests can switch threads, so Spring Security WebFlux uses Reactor Context to keep the security context attached to the reactive chain.

The **ReactiveSecurityContextHolder.getContext()** API returns a **Mono<SecurityContext>** to access security details inside a pipeline:

~~~java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(securityContext ->
                        securityContext.getAuthentication().getName());
~~~

When building WebFlux applications, use Spring Security's reactive APIs. Do not assume **SecurityContextHolder.getContext()** always returns the current user on every thread during a reactive request.

### 10.3. Tracing and Observability

Trace IDs and span contexts must propagate across multiple processing steps, potentially spanning WebFlux, Spring Data R2DBC, and HTTP calls to other services. Reactor Context plays a key role in carrying this metadata.

Modern observability libraries typically integrate with Reactor or Micrometer Context Propagation to preserve trace context and restore required state at execution boundaries. When using built-in framework integration, follow your framework version's configuration mechanism rather than creating a standalone ThreadLocal for trace IDs.

## 11. Bridging Reactor Context and ThreadLocal

Some legacy libraries expose only ThreadLocal-based APIs. When bringing those libraries into a reactive application, a bridge between Reactor Context and ThreadLocal may be needed.

The Micrometer ecosystem provides the **Context Propagation** library for this purpose. The general idea is:

- Register a **ThreadLocalAccessor** describing how to read, write, and clear a specific ThreadLocal.
- Use capture to copy existing ThreadLocal values into Reactor Context at subscription time.
- When callbacks run on appropriate threads, restore values from Context into ThreadLocal and clean them up afterward.
- Register only the ThreadLocals that genuinely need integration.

Conceptual example of capturing context:

~~~java
Mono<String> task =
        Mono.deferContextual(context ->
                Mono.just(context.getOrDefault("requestId", "unknown")))
            .contextCapture();
~~~

**contextCapture()** uses Context Propagation to capture registered ThreadLocal values into Reactor Context at subscribe time. Hence, the values to capture must be present on the subscribing thread and their corresponding accessors must be registered.

Reactor also supports automatic context propagation via **Hooks.enableAutomaticContextPropagation()** in supported versions. This mode automatically restores registered ThreadLocals from Reactor Context around operator execution. Enable the hook early, before subscriptions relying on this mechanism are created.

Notes when using a bridge:

- Context Propagation does not automatically propagate every ThreadLocal. Only ThreadLocals with a registered accessor are bridged.
- **contextCapture()** captures values at subscribe time; it does not re-read ThreadLocals at every step in the pipeline.
- Automatic mode alters how ThreadLocals are restored around supported operators. Consult the documentation for your exact Reactor and Micrometer versions.
- When pure reactive APIs are available, prefer keeping data in Reactor Context. ThreadLocal bridges are mainly for compatibility with imperative libraries.
- ThreadLocal restoration must have clear scope and cleanup to prevent data leaks between tasks.

Do not hand-roll a ThreadLocal copy mechanism by grabbing values at request start and setting them on arbitrary threads. Doing so makes thread reuse, nested callbacks, errors, cancellation, and multiple schedulers hard to handle safely. Use library-supported integration mechanisms instead.

## 12. Context and Reactive Transactions

Spring Data R2DBC uses a reactive transaction manager. The transaction context is attached to the reactive execution context so operations within the same pipeline can share the appropriate transaction and connection.

For example, a service updates two records in one transaction:

~~~java
@Transactional
public Mono<Void> updateOrderAndInventory(Order order) {
    return orderRepository.save(order)
            .then(inventoryRepository.decrease(order.getProductId(), order.getQuantity()))
            .then();
}
~~~

The publisher is returned to Spring to manage the transaction. Operations needing to join the transaction must remain in the same reactive chain and execute under the transaction context provided by Spring.

This is another illustration of why reactive context cannot rely purely on ThreadLocal. A transaction can span multiple steps and threads, while the transaction manager must bind the right resources to the subscription. Do not call **subscribe()** manually inside a transactional method because it creates an independent subscription with a separate lifecycle from the Spring-managed publisher.

## 13. Common Mistakes When Using Reactor Context

### 13.1. Placing contextWrite in the Wrong Position

If **contextWrite** sits upstream of the operator trying to read Context, that operator will not see the value. Remember that Context propagates from downstream to upstream on subscribe. Placing **contextWrite** downstream of everything that needs the value is usually the clearest approach.

### 13.2. Reading Context Too Early During Pipeline Assembly

Context cannot be read like a local variable at the moment a publisher is declared. Context is supplied per subscription. Use **deferContextual** or **transformDeferredContextual** when you need to access it.

### 13.3. Assuming Context Propagates Automatically to Any Async Task

Context is managed by Reactor within reactive chains. If you spawn your own thread, submit a callback to an external executor, or start an independent subscription, do not assume Context travels along automatically. Use appropriate Context Propagation APIs or pass data explicitly across that boundary.

### 13.4. Creating Nested Subscriptions with subscribe()

Calling **subscribe()** casually inside an operator typically detaches part of the work from the original pipeline. Error handling, cancellation, Context, and transactions may no longer share the same lifecycle. Return publishers and use operators like **flatMap**, **then**, or **zip** to compose work.

### 13.5. Using Context to Store Mutable State

Context immutability only guarantees the key-value structure itself is not modified in place. A value such as a **HashMap** or mutable object can still be modified across steps. Store simple, immutable metadata and avoid using Context to share concurrently mutated state.

### 13.6. Relying on Context Instead of Security Checks

Context is a transport mechanism, not a trust boundary. For example, a tenant ID in Context can carry tenant info across layers, but queries still need tenant filters and access permissions must still be verified. Never trust a key solely because it exists in Context.

### 13.7. Using Per-Request Data in a Shared Cached Pipeline

Operators like **cache()** can share upstream results across multiple subscribers. If upstream depends on a user ID or tenant ID in Context, sharing results can accidentally leak per-request data across requests. Design cache keys and cache placement around data scope; never cache personalized results as if they were shared data.

## 14. Testing Reactor Context

Context behavior can be tested by supplying Context on a publisher and asserting the output.

~~~java
Mono<String> currentRequestId =
        Mono.deferContextual(context ->
                Mono.just(context.get("requestId")));

StepVerifier.create(
            currentRequestId.contextWrite(
                    context -> context.put("requestId", "req-test-1")))
        .expectNext("req-test-1")
        .verifyComplete();
~~~

Test at least these scenarios:

- Key is present and operators read the expected value.
- Key is absent, ensuring errors or fallbacks behave properly.
- Two independent subscriptions can receive two distinct Contexts.
- Context remains readable after the pipeline switches schedulers.
- Inner publishers inside **flatMap** can read Context when **contextWrite** is positioned properly.
- Operations involving caches or nested subscriptions do not inadvertently share per-request data.

These tests verify pipeline and subscription behavior without depending on a specific thread.

## 15. Choosing Between Reactor Context and ThreadLocal

Use **Reactor Context** when data must travel with a reactive pipeline, potentially across multiple operators, schedulers, or service layers. Typical examples include trace IDs, request IDs, security contexts, tenant metadata, and transaction contexts.

Use **ThreadLocal** when dealing with truly thread-bound imperative code whose value lifecycle is tightly managed. ThreadLocal still has its place in synchronous libraries and can be bridged to Reactor via Context Propagation when needed.

In a reactive application, make Reactor Context the primary source of contextual metadata. If a library requires ThreadLocal, use a supported bridge to translate at the appropriate boundary. This keeps per-request context attached to the subscriber while giving imperative APIs the data in the form they expect.

## 16. Conclusion

Reactor Context and ThreadLocal both enable accessing metadata without passing parameters through every method, but they bind data to different units. ThreadLocal binds values to the running thread. Reactor Context binds metadata to the subscriber and subscription of a reactive pipeline.

When a pipeline switches threads, ThreadLocal does not follow automatically; Reactor Context still propagates during subscription. Using Context properly requires understanding downstream-to-upstream propagation, placing **contextWrite** in the right position, and reading data with **deferContextual** or equivalent APIs.

With Spring Data R2DBC and Spring WebFlux, Reactor Context is a core foundation for propagating transaction, security, and tracing metadata throughout non-blocking flows. ThreadLocal may still appear at integration boundaries with imperative libraries, but conversions should be managed through proper Context Propagation mechanisms.
