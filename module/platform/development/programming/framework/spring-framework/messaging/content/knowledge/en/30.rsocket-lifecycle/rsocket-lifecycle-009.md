# Offloading Blocking Tasks Out of the Reactive Pipeline

In Spring Messaging with RSocket, handlers typically return **Mono** or **Flux** to represent results arriving asynchronously. A reactive pipeline can process many requests without tying up a dedicated thread throughout I/O wait time. This benefit is lost if a handler directly calls a blocking API such as synchronous JDBC/JPA, RestTemplate, synchronous file reads, or a legacy SDK.

The right approach is to isolate the blocking portion onto a scheduler designed for blocking tasks, typically **Schedulers.boundedElastic()**, and continue returning a publisher for Spring to manage. This keeps pipeline and I/O threads free from waiting on synchronous calls.

## 1. How Do Blocking Tasks Affect the RSocket Pipeline?

A blocking operation holds the current thread until the operation completes. While that thread is waiting, it cannot process other work. In a reactive system, a small number of threads can serve many connections and signals. If a handler blocks a thread running the pipeline, other requests can be delayed as well.

For example, a handler receives an RSocket request and calls a synchronous JDBC service:

~~~java
@MessageMapping("customers.find")
Mono<Customer> find(CustomerRequest request) {
    Customer customer = jdbcCustomerService.findById(request.customerId());
    return Mono.just(customer);
}
~~~

The **findById** call runs immediately when the handler method is invoked. The publisher is created only after the query has finished. Thus, returning **Mono** at the end of the method does not make the query non-blocking.

Consequences may include:

- The thread handling the request is held for the entire wait on the database or external service.
- Latency increases as concurrent requests grow.
- Thread pools or queues accumulate work, reducing system throughput.
- One slow service can cause cascading impact across many other requests.
- The system loses the scalability benefits offered by the reactive model.

Never assume every RSocket handler always runs on a fixed thread type. The actual thread depends on the transport, configuration, and scheduler placement in the pipeline. The rule to keep is: never perform blocking tasks on threads serving reactive pipelines or I/O.

## 2. Identifying Blocking vs. Non-Blocking Tasks

Operations that are typically blocking:

- JDBC, synchronous JPA/Hibernate, and repositories returning results directly.
- RestTemplate or synchronous HTTP clients.
- File read/write via synchronous APIs such as **Files.readString**.
- Calling legacy SDKs that only expose synchronous methods.
- Waiting via **Thread.sleep**, **Future.get**, or **CountDownLatch.await**.
- Invoking external processes and waiting for results.
- Waiting on locks or synchronous resources for an unbounded time.

APIs typically designed to be non-blocking:

- WebClient with Reactor Netty.
- R2DBC and reactive repositories.
- Reactor Netty or reactive RSocket clients.
- APIs returning **Mono** or **Flux** that do not block threads while awaiting I/O.

Distinguish blocking I/O from CPU computation. Heavy encryption or data processing may consume CPU without waiting on I/O. **boundedElastic** is for blocking tasks; **parallel** is for short, non-blocking CPU-bound work.

If you can replace a blocking library with a suitable non-blocking driver or client, that is usually the better long-term solution. Offloading is a safer integration approach when synchronous APIs cannot yet be replaced.

## 3. Standard Pattern: Mono.fromCallable Combined with subscribeOn

Reactor provides **Mono.fromCallable** to defer invoking a synchronous function until the publisher is subscribed to. Combine it with **subscribeOn(Schedulers.boundedElastic())** to run that call on a scheduler meant for blocking work.

~~~java
Mono<Customer> customerMono = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Crucially, the blocking call sits inside **fromCallable**. It does not run when creating the publisher; it runs upon subscription and is executed by the designated scheduler.

Example in an RSocket controller:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class CustomerRSocketController {

    private final LegacyCustomerService customerService;

    CustomerRSocketController(LegacyCustomerService customerService) {
        this.customerService = customerService;
    }

    @MessageMapping("customers.find")
    Mono<CustomerView> find(CustomerRequest request) {
        return Mono.fromCallable(
                () -> customerService.findById(request.customerId())
            )
            .subscribeOn(Schedulers.boundedElastic())
            .map(CustomerView::from);
    }
}

record CustomerRequest(String customerId) {}

record CustomerView(String id, String displayName) {
    static CustomerView from(Customer customer) {
        return new CustomerView(customer.id(), customer.displayName());
    }
}
~~~

In this example, **customerService.findById** remains a synchronous API. Reactor executes the call on a bounded elastic worker. Once the result is ready, subsequent steps in the pipeline continue and Spring sends the result over RSocket.

Key points to remember:

1. **fromCallable** defers the call and turns exceptions into publisher error signals.
2. **subscribeOn** places subscribing and executing the source onto the chosen scheduler.
3. The handler still returns **Mono**. Do not call subscribe or block manually in the handler.
4. If the synchronous function returns null, **Mono.fromCallable** emits an empty Mono. If null is an invalid state, check and emit an explicit error.
5. Wrap only the blocking portion. Keep the remaining reactive steps non-blocking.

For blocking operations that return no value, you can use **Mono.fromRunnable**:

~~~java
Mono<Void> saveAuditRecord(AuditRecord record) {
    return Mono.fromRunnable(() -> legacyAuditClient.save(record))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

If the operation can throw an exception, that exception becomes an onError signal and can be handled with operators such as **onErrorMap** or **onErrorResume**.

## 4. Why subscribeOn Fits Blocking Sources Better Than publishOn

Both operators deal with schedulers, but they take effect at different positions.

- **subscribeOn(scheduler)** controls the scheduler used to subscribe to the source. For a blocking source like **Mono.fromCallable**, it makes the callable execute on that scheduler.
- **publishOn(scheduler)** switches processing of downstream signals and operators after it to the specified scheduler. It does not retroactively move a blocking call that already ran before publishOn.

The following example is unsafe:

~~~java
Mono<Customer> wrong = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .publishOn(Schedulers.boundedElastic());
~~~

The source callable can run on the initial subscribing thread. **publishOn** sits after the source, so it does not protect the JDBC call.

The proper pattern:

~~~java
Mono<Customer> correct = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

**publishOn** is still useful when you want to switch steps after a specific point. For instance, if you need to run a CPU-bound transformation after receiving a result, you can switch to **Schedulers.parallel()** at the appropriate spot:

~~~java
Mono<Result> result = Mono
    .fromCallable(() -> blockingClient.load(id))
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::computeResult);
~~~

In this pipeline, the blocking call runs on bounded elastic; the computation after publishOn runs on parallel. Do not move the entire pipeline onto a single scheduler just because one step is blocking.

## 5. Avoid Calling Blocking Code Before Creating the Publisher

A common mistake is passing a blocking call as an argument to **Mono.just**:

~~~java
Mono<Customer> wrong = Mono.just(
    jdbcCustomerService.findById(customerId)
);
~~~

Java evaluates arguments before calling **Mono.just**, so the query runs immediately on the current thread. The publisher cannot defer a call that already happened.

Use instead:

~~~java
Mono<Customer> correct = Mono
    .fromCallable(() -> jdbcCustomerService.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Another mistake is calling **block()** inside a handler:

~~~java
@MessageMapping("customers.find")
Mono<Customer> wrong(CustomerRequest request) {
    Customer customer = customerService.findById(request.customerId());
    return Mono.just(customer);
}
~~~

The right way is to return a publisher wrapping the offloaded synchronous call:

~~~java
@MessageMapping("customers.find")
Mono<Customer> find(CustomerRequest request) {
    return Mono.fromCallable(
            () -> customerService.findById(request.customerId())
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

In reactive controllers, avoid operations like **block()**, **blockOptional()**, **toIterable()**, **toStream()**, and manual **subscribe()** to extract results. These can break asynchronicity, cause handlers to finish at the wrong time, or sever error and cancellation propagation.

Spring manages the subscription for the publisher returned by the handler. The handler should describe the work with **Mono** or **Flux**, then return that publisher to the framework.

## 6. Offloading Blocking Tasks in Flux and Multi-Element Streams

If a request must process multiple items using a synchronous API, offload each operation and bound concurrency.

~~~java
Flux<Product> products = Flux.fromIterable(productIds)
    .flatMap(
        id -> Mono.fromCallable(() -> blockingProductClient.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        16
    );
~~~

The argument **16** limits how many inner publishers flatMap subscribes to concurrently in this example. Bounding concurrency prevents firing too many blocking calls at once when the input list is large.

If the blocking API returns an entire collection, you can defer loading the collection and then convert it into a Flux:

~~~java
Flux<Product> products = Mono
    .fromCallable(() -> legacyProductClient.loadAll())
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
~~~

If iterating the iterator itself is blocking, verify where iteration occurs and ensure the entire blocking portion executes on an appropriate scheduler. Not every API returning **Iterable** spends time only when fetching the collection; some iterators perform I/O on every next call.

Backpressure regulates emitting and consuming signals in the pipeline, but does not automatically turn blocking APIs into non-blocking ones. Combine backpressure with concurrency limits, queue limits, and timeouts on the blocking client.

## 7. Choosing the Right Scheduler for the Purpose

| Scheduler | Purpose | Suitable for Blocking I/O? |
|---|---|---|
| **Schedulers.boundedElastic()** | Blocking tasks, I/O waits, or synchronous APIs | Yes; this is the usual default choice |
| **Schedulers.parallel()** | CPU-bound, non-blocking computation | No |
| **Schedulers.single()** | Sequential work on a single worker | Should not be used for blocking tasks |
| **Schedulers.immediate()** | Immediate execution on the current thread | No |
| **Schedulers.fromExecutor(...)** | Using an application-managed executor | Possibly, if the executor is properly designed and bounded |

### Why boundedElastic?

Bounded elastic is designed to isolate blocking work using a bounded pool. It allows workers to be created on demand while still bounding resources and queued tasks. This bounding prevents creating an unbounded number of new threads per request.

Even so, bounded elastic is not an infinite resource:

- If blocking calls take a long time, workers stay occupied longer.
- If task count exceeds capacity, tasks may wait in a queue.
- When the pool or queue saturates, latency climbs and scheduler errors may occur.
- A system with too many blocking calls can still exhaust resources.

Do not create **Schedulers.newBoundedElastic(...)** per request. If you need a dedicated pool to isolate a group of APIs with distinct load profiles, create the scheduler at application level, configure explicit thread and queue limits, and dispose it on application shutdown.

Do not use **Schedulers.parallel()** for JDBC or synchronous HTTP clients. Parallel workers are optimized for CPU-bound work; blocking them can starve other reactive tasks of threads.

## 8. Timeouts, Cancellation, and Resource Limits

You can attach a timeout to the publisher:

~~~java
Mono<Customer> customer = Mono
    .fromCallable(() -> blockingCustomerClient.find(customerId))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
~~~

Timeout bounds how long the subscriber waits for a result. However, do not assume timeout always stops a running blocking call immediately. When the subscriber cancels the subscription, whether the task stops depends on the scheduler and underlying synchronous API. Some libraries keep running until the operation returns or an internal timeout triggers.

Therefore, configure timeouts directly in the blocking client:

- Connection timeout to bound connection establishment time.
- Read/response timeout to bound waiting for data.
- Timeouts for database queries or statements.
- Cancellation or interrupt mechanisms if supported by the library and safe for the application to use.

At the same time, consider:

- Limiting concurrent requests entering the blocking service.
- Limiting how many elements flatMap processes concurrently.
- Bounding queue size if using a custom executor.
- Avoiding infinite retries. Retrying a non-idempotent write can create duplicate data.
- Releasing connections, streams, and resources in finally or an appropriate resource-management mechanism.

Offloading protects reactive threads from waiting directly. It does not make blocking operations faster and does not replace timeouts, bulkheads, or load limits.

## 9. Preserving the RSocket Request Lifecycle

Switching schedulers should not alter the RSocket interaction model:

- Request-Response continues returning **Mono<T>**.
- Request-Stream continues returning **Flux<T>**.
- Fire-and-Forget can use a publisher that completes without returning data.
- Channel must still handle bidirectional streams per the designed contract.

Example of a Request-Response handler:

~~~java
@MessageMapping("inventory.lookup")
Mono<InventoryItem> lookup(InventoryRequest request) {
    return Mono.fromCallable(
            () -> blockingInventoryClient.lookup(request.sku())
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Example of a handler returning a stream:

~~~java
@MessageMapping("inventory.watch")
Flux<InventoryItem> watch(InventoryWatchRequest request) {
    return Flux.fromIterable(request.skus())
        .flatMap(
            sku -> Mono.fromCallable(
                    () -> blockingInventoryClient.lookup(sku)
                )
                .subscribeOn(Schedulers.boundedElastic()),
            8
        );
}
~~~

In the second example, at most eight lookups are subscribed concurrently per subscription to this pipeline. If multiple clients and subscriptions are active together, calculate total load on the blocking service rather than looking only at a single request's limit.

When a client cancels a request or disconnects, the publisher may receive cancellation. An in-progress blocking task may not stop instantaneously. Thus, internal timeouts and library cancellation mechanisms remain necessary.

Do not call **subscribe()** inside a handler to run work on your own and return a different publisher. Doing so detaches the work from the RSocket request lifecycle: errors may not reach the requester, cancellation can no longer control the task, and the framework does not know when work finishes.

## 10. Context, Transactions, and ThreadLocal

When a pipeline switches from one thread to another, do not rely on the assumption that every **ThreadLocal** automatically keeps its value. Values such as request context, tracing, or security context may require an appropriate context-propagation mechanism.

In Spring reactive applications, **Reactor Context** is the right place to store subscription-bound context. If a blocking library only reads ThreadLocal, configure a context-propagation mechanism compatible with your Spring/Reactor version.

Also distinguish imperative and reactive transactions:

- Imperative transactions are typically thread-bound via ThreadLocal.
- Reactive transactions propagate via Reactor Context and require a reactive transaction manager.
- A blocking JDBC call does not become a reactive transaction simply by wrapping it in a Mono.

If calling a transactional imperative service, let transaction boundaries be managed by the appropriate transaction manager and ensure the call executes within that transaction scope. Do not split an imperative transaction across multiple scheduler hops assuming thread-bound state will follow the publisher automatically.

## 11. Observability and Testing

A good offloading implementation should be verified for both behavior and resource usage.

### Runtime Observability

Monitor:

- Latency of RSocket handlers and each blocking call.
- Concurrent request counts and queued task counts.
- Thread names when executing blocking calls.
- Timeouts, cancellations, connection errors, and scheduler errors.
- Pool status of JDBC/HTTP clients and resource utilization.
- Latency changes as load increases.

You can add **doOnNext**, **doOnError**, or tracing to observe the pipeline. Avoid logging entire sensitive payloads.

### Testing

Include tests verifying:

1. The handler returns the publisher immediately and the blocking call happens only upon subscription.
2. The blocking call executes on a bounded elastic worker, not on a non-blocking pipeline thread.
3. Errors from the synchronous API become onError and are handled properly.
4. Timeouts and cancellation behave in line with the blocking library's capabilities.
5. Under multiple concurrent requests, concurrency and pool limits hold.
6. Request-Response and Request-Stream still conform to their interaction models.

**BlockHound** can help detect certain blocking calls on threads marked non-blocking during development or testing. When integrating it, use a version compatible with Reactor and running libraries; allow exceptions intentionally only after understanding the impact.

A simple test showing the call runs on subscribe:

~~~java
AtomicBoolean invoked = new AtomicBoolean(false);

Mono<String> source = Mono.fromCallable(() -> {
    invoked.set(true);
    return "loaded";
}).subscribeOn(Schedulers.boundedElastic());

assertFalse(invoked.get());

String value = source.block();

assertEquals("loaded", value);
assertTrue(invoked.get());
~~~

This example uses **block()** to wait for the result in a test or standalone code. Do not use this synchronous wait inside a reactive handler. In integration tests, you can use **StepVerifier** to assert signals without managing subscriptions manually.

## 12. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Calling JDBC directly then returning Mono.just | Query runs before the publisher is created | Use Mono.fromCallable and subscribeOn |
| Using Mono.just(blockingCall()) | Java evaluates the call immediately | Move the call into fromCallable |
| Placing publishOn after a blocking source | Source may already run on the initial subscribing thread | Use subscribeOn for the source |
| Calling block() inside a handler | Blocks thread and breaks the pipeline | Return Mono or Flux |
| Calling subscribe() inside a handler | Detaches task from request lifecycle | Return the publisher to Spring |
| Using parallel for blocking I/O | Occupies workers meant for CPU-bound work | Use boundedElastic |
| Creating a new scheduler per request | Creates many pools and makes resource control hard | Reuse an application-level scheduler |
| Not setting client timeouts | One call can hold a worker indefinitely | Configure timeouts in the blocking library |
| Retrying non-idempotent write operations | Can execute business logic multiple times | Design idempotency and controlled retries |
| Allowing unbounded concurrency | Can exhaust connection pools or queues | Set concurrency limits and admission control |

## 13. Pre-Production Checklist

- [ ] Accurately identified blocking operations and expected wait times.
- [ ] Checked whether a non-blocking API alternative exists.
- [ ] Blocking calls are deferred via fromCallable or fromRunnable.
- [ ] Blocking sources run via subscribeOn with boundedElastic or an appropriate dedicated scheduler.
- [ ] No calls to block, toIterable, toStream, or manual subscribe inside handlers.
- [ ] Handlers keep returning the right Mono/Flux per the RSocket interaction model.
- [ ] Client-level timeouts and appropriate cancellation handling are in place.
- [ ] Concurrency limits and downstream resource limits are configured.
- [ ] Considered transactions, security context, and ThreadLocal across thread hops.
- [ ] Measured latency, queued tasks, and pool usage under rising load.
- [ ] Tested errors, timeouts, cancellation, and high concurrency.

## 14. References

- [Project Reactor Reference: Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — using subscribeOn, publishOn, and schedulers.
- [Project Reactor API: Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html) — boundedElastic, parallel, and creating schedulers.
- [Project Reactor Reference: Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — subscription behavior and deferring publisher execution.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — requester, responder, and reactive handler models in Spring.
- [BlockHound](https://github.com/reactor/BlockHound) — tool to detect blocking calls on non-blocking threads during development and testing.
