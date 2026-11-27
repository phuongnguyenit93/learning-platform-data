# Isolating Unavoidable Blocking Tasks and Re-evaluating Transaction Boundaries

## 1. Why must blocking tasks be isolated in a reactive application?

Spring Data Relational R2DBC provides reactive database access APIs. Operations typically return `Mono` or `Flux` and do not require application threads to wait synchronously until the database returns a result.

However, a real-world application may still have to call legacy libraries or services that only provide blocking APIs, for example:

- Legacy JDBC libraries.
- Payment SDKs that only offer synchronous methods.
- Synchronous file reading or filesystem APIs.
- Legacy HTTP clients performing blocking I/O.
- Document processing libraries with long-running synchronous calls.
- An internal API that does not yet have a reactive version.

If a blocking method is called directly on a reactive processing thread, that thread must wait until the work finishes. In a Spring WebFlux application, this can occupy event-loop threads that are designed to handle many requests via non-blocking operations.

The solution is to isolate the blocking task onto an appropriate scheduler, typically `Schedulers.boundedElastic()`, and then compose the result back into the reactive pipeline.

Isolating blocking calls only solves the thread-utilization problem. It does not by itself answer another critical question: should the blocking task run inside or outside an R2DBC transaction? If a transaction is already open and holding a connection while waiting on a blocking call, both the connection and potentially database locks will be held longer than necessary.

This article focuses on two interrelated decisions:

1. Moving unavoidable blocking tasks off the event loop.
2. Redesigning transaction boundaries so that R2DBC transactions surround only the database operations that genuinely require atomicity.

## 2. Distinguishing blocking and non-blocking

### 2.1. What is blocking?

A blocking call holds the current thread until a result arrives or a timeout expires.

Example:

~~~java
String response = legacyClient.fetchCustomer(customerId);
~~~

If `fetchCustomer` makes a synchronous network call taking 2 seconds, the calling thread must wait during that time. The thread cannot continue processing other work while waiting.

Similarly:

~~~java
Customer customer = jdbcTemplate.queryForObject(
    "SELECT id, full_name FROM customers WHERE id = ?",
    customerRowMapper,
    customerId
);
~~~

JDBC is a blocking API. When running the query, the calling thread must wait for the database to return the result.

### 2.2. What is non-blocking?

With reactive APIs, operations are represented by publishers. The calling thread does not sit waiting synchronously for the result:

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId);
~~~

This code builds a publisher. When the publisher is subscribed to, the R2DBC driver performs I/O via non-blocking APIs and emits signals when a result, error, or completion arrives.

Remember:

- `Mono` and `Flux` are types representing a processing stream, not proof that every line inside is non-blocking.
- Calling a blocking function inside `map`, `flatMap`, or `doOnNext` still blocks the thread executing that callback.
- Returning `Mono` from a method does not automatically make code run prior to creating the `Mono` non-blocking.

Incorrect example:

~~~java
public Mono<CustomerView> getCustomer(Long id) {
    Customer customer = legacyClient.fetchCustomer(id); // Blocking immediately when called

    return Mono.just(toView(customer));
}
~~~

The blocking call happens before the publisher is returned. No scheduler automatically moves it to another thread.

## 3. Isolating blocking calls with Mono.fromCallable

### 3.1. Basic pattern

For a blocking method returning a value, use `Mono.fromCallable()` and `subscribeOn(Schedulers.boundedElastic())`:

~~~java
public Mono<CustomerProfile> loadProfile(Long customerId) {
    return Mono.fromCallable(
            () -> legacyClient.fetchCustomerProfile(customerId)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Meaning:

- `Mono.fromCallable()` delays calling the function until subscription.
- `subscribeOn(...)` instructs the subscription and the `Callable` source to execute on the specified scheduler.
- `Schedulers.boundedElastic()` provides workers suited for blocking tasks, with bounded resources rather than creating threads without limit.

When the publisher is subscribed to, `fetchCustomerProfile` runs on a bounded elastic worker. The event loop does not directly wait on that call.

### 3.2. Do not invoke the blocking call before creating the Callable

Do not write:

~~~java
String result = legacyClient.fetchData();

return Mono.fromCallable(() -> result)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Blocking already occurred on the first line. `fromCallable` merely wraps an already computed variable, so it does not move the call to another scheduler.

Place the blocking call itself inside the `Callable`:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 3.3. Use Mono.fromRunnable for methods returning void

If a blocking method only performs an action and returns no value, use `Mono.fromRunnable()`:

~~~java
public Mono<Void> writeArchive(Long orderId) {
    return Mono.fromRunnable(
            () -> legacyArchiveClient.archive(orderId)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

The publisher completes when the blocking method finishes. If the method throws an exception, the publisher emits an error signal.

### 3.4. Handling null results

`Mono.fromCallable()` does not emit a `null` element. If the `Callable` returns `null`, the `Mono` completes empty.

Example:

~~~java
return Mono.fromCallable(
        () -> legacyClient.findOptionalCustomer(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(customerId)
    ));
~~~

Clarify whether `null` means data not found, result not yet available, or a legacy library error. Do not let turning `null` into an empty `Mono` lose business meaning.

## 4. Why use boundedElastic?

### 4.1. Keep blocking off the event loop

WebFlux event-loop threads are designed to process fast callbacks and coordinate non-blocking I/O. If multiple requests call a blocking SDK directly on those threads, the event loop can become saturated. Other requests must wait even when their database or network calls are ready.

Offloading blocking calls to `boundedElastic` separates threads waiting on synchronous I/O from threads handling reactive execution.

### 4.2. boundedElastic has resource limits

`Schedulers.boundedElastic()` is designed for blocking tasks with wait times. The scheduler manages worker counts and queues within Reactor's bounds rather than spawning unbounded threads.

However, `boundedElastic` is not an infinite resource:

- If blocking calls take a long time, workers stay occupied longer.
- If task volume exceeds processing capacity, tasks may wait in the queue.
- If a legacy library hangs or lacks a timeout, workers can be held indefinitely.
- Pushing huge amounts of work onto the scheduler can increase latency and memory pressure.

Configure timeouts on the blocking client itself, limit concurrency when processing multiple items, and monitor scheduler health.

### 4.3. Do not use parallel for blocking I/O

`Schedulers.parallel()` targets short, non-blocking computational tasks. Do not move JDBC, synchronous file I/O, or blocking HTTP clients onto `parallel`.

Suitable pattern:

~~~java
Mono.fromCallable(() -> jdbcTemplate.queryForObject(
        "SELECT full_name FROM customers WHERE id = ?",
        String.class,
        customerId
    ))
    .subscribeOn(Schedulers.boundedElastic());
~~~

If the task is purely CPU-bound and does not block on I/O, `Schedulers.parallel()` can be considered. Classify the workload accurately before picking a scheduler.

### 4.4. You can create a dedicated scheduler for a blocking library

If the system has a specific group of blocking calls requiring independent bounds, you can create a dedicated bounded elastic scheduler:

~~~java
@Configuration
public class LegacyClientSchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    public Scheduler legacyClientScheduler() {
        return Schedulers.newBoundedElastic(
            12,
            500,
            "legacy-client"
        );
    }
}
~~~

Then inject the scheduler:

~~~java
@Service
public class LegacyProfileService {

    private final LegacyClient legacyClient;
    private final Scheduler legacyClientScheduler;

    public LegacyProfileService(
            LegacyClient legacyClient,
            Scheduler legacyClientScheduler) {
        this.legacyClient = legacyClient;
        this.legacyClientScheduler = legacyClientScheduler;
    }

    public Mono<CustomerProfile> load(Long customerId) {
        return Mono.fromCallable(
                () -> legacyClient.fetchCustomerProfile(customerId)
            )
            .subscribeOn(legacyClientScheduler);
    }
}
~~~

The thread cap and queue cap values are examples only. Choose them based on processing time, concurrency, external service limits, and deployment resources. Dedicated schedulers should also be disposed when the application stops.

Do not create a new scheduler per request. Schedulers are shared infrastructure resources scoped to the application lifecycle or a workload group.

## 5. Placing subscribeOn in the right position

### 5.1. subscribeOn and publishOn differ

The two operators serve different roles:

- `subscribeOn` affects where subscription enters the source publisher and is typically used to move blocking calls wrapped in `fromCallable`.
- `publishOn` switches downstream signal processing to another scheduler from the operator's position onward.

Example:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::toView);
~~~

The `Callable` runs on `boundedElastic`. The subsequent `map` receives signals from that source and typically runs on the signal-emitting worker unless another scheduler operator switches execution.

### 5.2. publishOn placed after a call cannot fix blocking that already happened

Avoid writing:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .publishOn(Schedulers.boundedElastic());
~~~

With this approach, `publishOn` placed after the source does not guarantee the `Callable` executes on `boundedElastic`. `publishOn` controls downstream signal emission; it is not the way to move subscription of a blocking source.

Place `subscribeOn` on the source publisher:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 5.3. Isolate only the blocking part

You do not need to move the entire R2DBC pipeline onto `boundedElastic`. Wrap just the blocking call:

~~~java
public Mono<CustomerView> getCustomer(Long id) {
    return Mono.fromCallable(() -> legacyClient.fetchName(id))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(name ->
            customerRepository.findById(id)
                .map(customer -> new CustomerView(
                    customer.getId(),
                    name,
                    customer.getEmail()
                ))
        );
}
~~~

The legacy call runs on `boundedElastic`. The repository query continues using R2DBC reactively.

Do not add `subscribeOn(boundedElastic())` to every repository method just because another part of the flow is blocking. That obscures scheduler usage and does not turn a blocking driver into R2DBC.

## 6. Combining blocking calls with reactive repositories

A flow may need to fetch data from a blocking SDK before reading or writing the database:

~~~java
public Mono<CustomerView> loadCustomerView(Long customerId) {
    return Mono.fromCallable(
            () -> legacyClient.fetchExternalLabel(customerId)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(label ->
            customerRepository.findById(customerId)
                .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)
                ))
                .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getFullName(),
                    label
                ))
        );
}
~~~

This flow has the steps:

1. Subscriber triggers the `Callable`.
2. `Callable` runs on `boundedElastic`.
3. Once `label` arrives, `flatMap` subscribes to the repository read publisher.
4. The repository executes the R2DBC query.
5. The result is mapped to `CustomerView`.

If the blocking SDK does not need data from a database transaction, this is a relatively straightforward structure. There is no need to open an R2DBC transaction before calling the SDK.

### 6.1. When processing multiple elements

If a blocking API must be called per element, you can use `flatMap` with a concurrency limit:

~~~java
public Flux<CustomerView> loadViews(Flux<Long> customerIds) {
    return customerIds.flatMap(
        id -> Mono.fromCallable(
                () -> legacyClient.fetchExternalLabel(id)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(label ->
                customerRepository.findById(id)
                    .map(customer -> new CustomerView(
                        customer.getId(),
                        customer.getFullName(),
                        label
                    ))
            ),
        8
    );
}
~~~

The parameter `8` caps how many inner publishers `flatMap` subscribes to concurrently. This is an illustrative concurrency cap; actual values must reflect SDK limits, scheduler capacity, database pool size, and external service capacity.

If output order must match input order, consider `flatMapSequential` or `concatMap`. `concatMap` processes sequentially, lowering concurrency while potentially increasing total duration.

Do not raise concurrency just to use up workers. A blocking SDK has its own connection limits; sending too many requests can overload the external service.

## 7. Separating R2DBC transactions from blocking calls

### 7.1. The problem with blocking calls inside a transaction

Consider this example:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            Mono.fromCallable(() ->
                blockingPaymentClient.authorize(orderId)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(payment -> {
                order.setStatus("PAID");
                return orderRepository.save(order);
            })
        );
}
~~~

Even though the blocking call was moved to `boundedElastic`, the reactive transaction may still remain open for the entire publisher. The R2DBC connection bound to the Reactor Context by the transaction manager can remain held while the payment client waits for a response.

This causes several consequences:

- The connection pool stays occupied while no SQL is running.
- Transactions stay open longer than necessary.
- Database locks may be held longer.
- Transaction timeouts become more likely.
- When the payment service is slow, other requests can starve for connections.
- A database transaction cannot automatically roll back a payment already accepted by an external system.

Moving a blocking call to `boundedElastic` only frees the event loop. It does not automatically release the connection or end the transaction wrapping the publisher.

### 7.2. Do not open a transaction before an external call when unnecessary

If the external check does not need to occur inside the database transaction, execute it first. Once the result is available, open the transaction only for the database operations requiring atomicity:

~~~java
public Mono<Order> confirmOrder(Long orderId) {
    return Mono.fromCallable(
            () -> blockingPaymentClient.authorize(orderId)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(paymentResult ->
            transactionalOperator.transactional(
                orderRepository.findById(orderId)
                    .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(orderId)
                    ))
                    .flatMap(order -> {
                        order.setStatus("PAID");
                        order.setPaymentReference(
                            paymentResult.reference()
                        );
                        return orderRepository.save(order);
                    })
            )
        );
}
~~~

In this example, the blocking call finishes before `TransactionalOperator` opens a transaction. The transaction surrounds only reading and updating the order.

This structure fits when the payment result can be verified independently before the database write. In practice, also handle cases where order state changed while calling payment, duplicate requests arrive, or the payment result cannot be applied. Use idempotency keys and check business state before writing.

### 7.3. When database data is needed before a blocking call

You may need to read some data to build a request for an external system. It is not necessary to keep a transaction open while waiting for that system.

A possible structure is:

1. Read the necessary data in a query or short transaction.
2. End the transaction.
3. Call the blocking system on `boundedElastic`.
4. Open a new transaction, re-read the current data, and check conditions.
5. Write the result if the state is still valid.

Example:

~~~java
public Mono<Order> processOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .map(this::toPaymentCommand)
        .flatMap(command ->
            Mono.fromCallable(
                    () -> blockingPaymentClient.authorize(command)
                )
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(paymentResult ->
                    transactionalOperator.transactional(
                        orderRepository.findById(orderId)
                            .switchIfEmpty(Mono.error(
                                new OrderNotFoundException(orderId)
                            ))
                            .flatMap(current -> {
                                if (!current.canApply(paymentResult)) {
                                    return Mono.error(
                                        new OrderStateConflictException(orderId)
                                    );
                                }

                                current.markPaid(paymentResult.reference());
                                return orderRepository.save(current);
                            })
                    )
                )
        );
}
~~~

This example highlights reloading state inside the write transaction. If the entity has `@Version`, optimistic locking also helps detect concurrent changes that occurred between the last read and the save.

If calling the external system must happen at most once, do not rely solely on calling the blocking client before the transaction. Design idempotency and handle uncertain outcomes on timeouts.

## 8. Transaction boundaries must follow data atomicity

### 8.1. A transaction only protects resources participating in that transaction

An R2DBC reactive transaction protects database operations participating in the same transaction manager and connection. It does not automatically cover:

- An HTTP call to another service.
- Sending an email.
- Writing a file.
- Calling a payment SDK.
- A JDBC statement using a separate connection.
- A message sent to a broker not participating in that transaction.

If one of those external operations succeeds and then the R2DBC operation fails, a database rollback cannot undo external side effects automatically.

### 8.2. Blocking JDBC does not automatically join an R2DBC transaction

An application may use both R2DBC and JDBC, yet the two APIs normally use different connections and transaction managers.

Example:

~~~java
@Transactional
public Mono<Void> updateBothStores(Long id) {
    return orderRepository.findById(id)
        .flatMap(order -> {
            jdbcTemplate.update(
                "INSERT INTO legacy_audit(order_id) VALUES (?)",
                id
            );

            order.setStatus("UPDATED");
            return orderRepository.save(order);
        })
        .then();
}
~~~

This example has problems:

- `jdbcTemplate.update(...)` is blocking and runs on the current thread.
- JDBC uses JDBC's transaction/connection if configured, not the R2DBC connection automatically.
- Reactive `@Transactional` is typically driven by the R2DBC reactive transaction manager if the method uses that transaction manager.
- Rolling back R2DBC does not automatically roll back an independently committed JDBC statement.
- The JDBC call can also block reactive threads.

If legacy JDBC must be used, isolate it on `boundedElastic` and design cross-store consistency explicitly. Never assume two independent transaction managers form a single atomic transaction.

### 8.3. Short transactions reduce connection hold time

Transactions should surround the database operations that must commit/roll back together. Avoid placing the following steps inside the middle of a transaction if they can wait for long periods:

- Blocking HTTP or SDK calls.
- Waiting for user confirmation.
- Waiting on message brokers not participating in the transaction.
- Reading/writing large files.
- Long computations that do not need to hold database state.
- Retrying an external service with unpredictable wait times.

Short transactions reduce connection hold times, lock hold times, and pool exhaustion risks.

## 9. When to use outbox or saga?

If business logic must coordinate the database with external side effects, simply moving the blocking call outside the transaction may not suffice. You need a consistency workflow.

### 9.1. Transactional outbox

For instance, when confirming an order, the application needs to update order status and record a request to send a notification or call a downstream external system.

Instead of calling the external service inside the transaction, the application writes an outbox record in the same transaction as the business data:

~~~java
public Mono<Order> markReadyForPayment(Long orderId) {
    return transactionalOperator.transactional(
        orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
            .flatMap(order -> {
                order.markPaymentPending();

                return orderRepository.save(order)
                    .flatMap(saved ->
                        outboxRepository.save(
                            OutboxEvent.paymentRequested(
                                saved.getId(),
                                saved.getVersion()
                            )
                        ).thenReturn(saved)
                    );
            })
    );
}
~~~

After the transaction commits, a separate worker reads the outbox and calls the external system. The worker can use a reactive client or wrap a blocking client with `boundedElastic`.

Benefits:

- Order and outbox event are written in the same transaction.
- If the transaction rolls back, the event is not recorded.
- If the application stops after commit, the event remains in the database for the worker to process.
- The worker can retry by policy and use an idempotency key to prevent duplicate side effects.

An outbox does not make the external system join the R2DBC transaction. It creates a durable record for asynchronous processing and failure recovery.

### 9.2. Saga and compensating actions

For multi-step business workflows spanning multiple systems, a saga can be used. Each step completes independently and has a compensating action if a later step fails.

Example:

1. Create an order in `PENDING` state.
2. Send an inventory reservation request.
3. Request payment.
4. Update the order to `CONFIRMED`.
5. If payment fails, release inventory and transition the order to an appropriate state.

Compensating steps are not ACID database rollbacks. They are separate business operations that can themselves fail and need retries/observability.

### 9.3. Choosing the right approach

| Scenario | Approach to consider |
|---|---|
| Blocking call only reads external data, does not need same transaction | Call before or after the transaction, wrapped with `boundedElastic` |
| Updating multiple tables in the same database | Short reactive transaction |
| Writing to database then needing to send a message/email | Transactional outbox |
| Coordinating multiple systems with multiple steps and compensating actions | Saga |
| Legacy JDBC and R2DBC both writing data | Explicit synchronization design; do not assume one shared transaction |
| Calling a payment gateway that can time out and retry | Idempotency key, intermediate states, and reconciliation workflow |

## 10. Setting timeouts and handling cancellation for blocking calls

### 10.1. Publisher-level timeout

You can place a timeout at the reactive level:

~~~java
Mono<PaymentResult> payment =
    Mono.fromCallable(() -> blockingPaymentClient.authorize(command))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(5));
~~~

The timeout delivers an error to the subscriber if no signal arrives within the allowed duration. However, cancelling the subscription does not guarantee a blocking library stops immediately. Many blocking methods do not check interrupts or support cancellation.

Therefore, configure timeouts inside the client itself:

- Connect timeout.
- Read/response timeout.
- Request timeout.
- Timeout waiting for a connection from the SDK's own pool.

Reactor's timeout is an extra protective layer on the pipeline. It does not replace timeouts inside the blocking library.

### 10.2. Cancellation cannot always stop a blocking task

If a blocking HTTP client is waiting on a socket and the subscriber cancels, the thread may keep waiting until the client times out or the call finishes. This can tie up a `boundedElastic` worker even after downstream discarded the result.

Choose libraries with explicit timeouts and cancellation support where possible. Do not start unbounded blocking tasks expecting Reactor to halt them all when a request cancels.

### 10.3. Do not retry every timeout error

A timeout can occur after the external system already executed the operation while the response was lost in transit. For example, a payment gateway may have accepted the transaction even though the application never received the response. Resending a new payment request could create a duplicate charge.

Use business-managed idempotency keys, transaction status queries, or reconciliation workflows before retrying an irreversible side effect.

## 11. Limiting concurrency for blocking tasks

`Schedulers.boundedElastic()` has internal resource limits, but the pipeline should also cap how many tasks the application dispatches.

Example:

~~~java
return customerIds.flatMap(
    id -> Mono.fromCallable(() -> legacyClient.fetchProfile(id))
        .subscribeOn(Schedulers.boundedElastic()),
    10
);
~~~

The concurrency parameter limits how many inner publishers `flatMap` subscribes to at once. This stops the application from firing thousands of blocking calls simultaneously.

Consider together:

- Number of scheduler workers.
- Number of connections the blocking SDK can open.
- Rate limits of the external service.
- Number of connections in the R2DBC pool.
- Average and tail duration of the blocking call.
- Number of concurrent requests in the application.

Do not mechanically match worker count to the R2DBC pool connection count. The two resource pools serve different kinds of I/O and have different lifecycles.

If a flow needs to invoke a blocking call per element and results can be processed independently, `flatMap` with bounded concurrency usually fits. If ordering is mandatory or the library is not thread-safe, use `concatMap` or concurrency of 1.

## 12. Reactor Context and transaction context when switching schedulers

### 12.1. Reactive transactions do not rely on a fixed thread

Spring manages reactive transactions using the Reactor Context. Thus, the transaction context can follow the reactive pipeline across operators and proper Reactor scheduler switches.

Do not assume switching from the event loop to `boundedElastic` automatically drops the transaction. As long as publishers remain chained in the same pipeline, Reactor Context propagates with the subscription.

However, if code spawns raw threads, calls `subscribe` manually, or bridges to a callback API without Reactor Context integration, reactive context may fail to propagate as intended.

### 12.2. Do not create independent subscriptions

Incorrect example:

~~~java
@Transactional
public Mono<Void> updateOrder(Long orderId) {
    orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .subscribe();

    return Mono.empty();
}
~~~

A manually invoked subscription detaches from the publisher Spring manages for the method. The transaction can finish before the save operation completes.

Return the publisher instead:

~~~java
@Transactional
public Mono<Void> updateOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .then();
}
~~~

If a blocking call is needed, compose its publisher into the chain with `flatMap` instead of subscribing manually.

### 12.3. ThreadLocal in legacy libraries is a separate issue

Some blocking libraries use `ThreadLocal` to store request metadata, security principals, MDC, or transaction context. Reactor Context is not equivalent to `ThreadLocal`.

When a call moves onto `boundedElastic`, `ThreadLocal` values from the original thread do not automatically appear on the new worker. If the library requires those values, pass them explicitly as parameters or use context propagation mechanisms supported by your framework and version.

Do not rely on two steps happening to run on the same thread. A reactive pipeline never promises to stay on a single thread from start to finish.

## 13. Patterns to avoid

### 13.1. Calling blocking code directly inside map

Unsuitable:

~~~java
return customerRepository.findById(id)
    .map(customer -> legacyClient.fetchLabel(customer.getId()));
~~~

`map` may run on the thread emitting signals from R2DBC. The blocking call will occupy that thread.

Isolated approach:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        Mono.fromCallable(
                () -> legacyClient.fetchLabel(customer.getId())
            )
            .subscribeOn(Schedulers.boundedElastic())
            .map(label -> toView(customer, label))
    );
~~~

### 13.2. Using Mono.just with a blocking call

Unsuitable:

~~~java
return Mono.just(legacyClient.fetchData());
~~~

Java evaluates the argument to `Mono.just` immediately. The blocking call happens when the method is invoked, before subscription.

Correct approach:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 13.3. Using block to call reactive code

Unsuitable:

~~~java
return Mono.fromCallable(() ->
    customerRepository.findById(id).block()
).subscribeOn(Schedulers.boundedElastic());
~~~

This turns an R2DBC query into a blocking operation, creates nested subscriptions, and sacrifices the benefits of reactive composition. Never wrap a reactive publisher inside a `Callable` just to call `block`.

Compose publishers directly:

~~~java
return customerRepository.findById(id)
    .flatMap(customer -> processCustomer(customer));
~~~

### 13.4. Using publishOn after a blocking call

Unsuitable:

~~~java
return Mono.just(legacyClient.fetchData())
    .publishOn(Schedulers.boundedElastic());
~~~

The blocking call already executed before `Mono.just` was created. `publishOn` cannot move work that already happened.

Correct approach:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 13.5. Holding a transaction while calling an external service

Avoid doing this by default:

~~~java
@Transactional
public Mono<Order> pay(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            Mono.fromCallable(() -> blockingPaymentClient.pay(order))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(result -> orderRepository.save(
                    order.withPaymentResult(result)
                ))
        );
}
~~~

Even with the blocking thread isolated, the R2DBC transaction may still hold a connection while payment waits for a response. If the payment gateway takes 10 seconds, the transaction can remain open just as long.

Re-evaluate the business flow, separate out short write transactions, and use intermediate states, an outbox, or a saga when external side effects must be coordinated outside the database.

## 14. Testing and observability

### 14.1. Checking for blocking on non-blocking-only threads

BlockHound can help detect certain blocking calls running on threads marked non-blocking during tests. It is a helpful tool when building Reactor/WebFlux applications.

A test can verify the flow returns the right result:

~~~java
StepVerifier.create(service.loadProfile(42L))
    .expectNextMatches(profile ->
        profile.customerId().equals(42L)
    )
    .verifyComplete();
~~~

This test verifies reactive output. To prove the blocking call does not execute on the event loop, use dedicated tests or instrumentation; do not rely solely on `StepVerifier` completing.

### 14.2. Monitoring the scheduler

When using `boundedElastic`, observe:

- Number of running tasks.
- Number of queued tasks.
- Wait time before starting.
- Execution time of blocking calls.
- Timeout and error rates.
- Number of long-occupied workers.

If the scheduler frequently hits limits, investigate wait times, client timeouts, concurrency, and external service resilience before increasing thread caps.

### 14.3. Monitoring transactions and the connection pool

For R2DBC, monitor:

- Transaction duration.
- Allocated connections.
- Idle connections.
- Requests waiting for connections.
- Query duration.
- Lock waits and transaction timeouts if provided by the database.

If transaction duration scales proportionally with the response time of a blocking SDK, the transaction likely spans the external call. Review transaction boundaries instead of merely expanding pool size.

### 14.4. Testing errors on cancellation or timeout

Test:

- Blocking client returns normally.
- Blocking client throws an exception.
- Blocking client times out.
- Downstream request cancels before the blocking call finishes.
- Database errors after the blocking call succeeds.
- Retries do not duplicate side effects.

A reactive-layer timeout does not guarantee the blocking task halted. Verify the library's actual behavior and internal timeout configuration.

## 15. Process for re-evaluating transaction boundaries

When a reactive flow contains a blocking task, answer these questions in order:

1. Is the call truly blocking, or is there already a reactive/asynchronous API alternative?
2. Can the legacy library be removed or replaced with a non-blocking client?
3. If irreplaceable, is the call wrapped in `Mono.fromCallable` or `Mono.fromRunnable`?
4. Is `subscribeOn(Schedulers.boundedElastic())` placed on the exact source publisher?
5. Are concurrency limits and client-side timeouts configured on the blocking call?
6. Does the blocking call depend on prior database data?
7. Is a transaction left open while waiting for the external call?
8. Which database operations truly need to commit or roll back together?
9. Can the read transaction finish first, followed by the blocking call, and then a short write transaction?
10. If the external system produces side effects, are idempotency keys, an outbox, or a saga needed?
11. If legacy JDBC is involved, does it use a separate transaction manager and connection?
12. Are errors, timeouts, and cancellations guaranteed not to leak connections or duplicate side effects?
13. Are scheduler, pool, and transaction durations monitored to validate the design?

A transaction should begin close to the atomic database operations and end immediately once they finish. Do not keep a transaction open merely to span the entire request lifecycle when multiple steps do not belong to the same database transaction.

## 16. Self-check exercises

### Exercise 1: Isolating a blocking call

A legacy SDK has a method `fetchDocument(Long id)` returning `Document` via synchronous HTTP. Write the appropriate publisher.

Hint:

~~~java
Mono<Document> document =
    Mono.fromCallable(() -> legacySdk.fetchDocument(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

### Exercise 2: Void-returning method

A library writes a file using `void exportReport()`. Wrap it in a publisher.

Hint:

~~~java
Mono<Void> export =
    Mono.fromRunnable(() -> legacyExporter.exportReport())
        .subscribeOn(Schedulers.boundedElastic());
~~~

### Exercise 3: Distinguishing subscribeOn and publishOn

Why is `Mono.fromCallable(blockingCall).publishOn(boundedElastic())` not the right pattern to ensure the `Callable` runs on `boundedElastic`?

Hint: `publishOn` controls downstream signal processing from that point onward; `subscribeOn` places source subscription onto the scheduler. Use `subscribeOn` on the `Callable` publisher.

### Exercise 4: Evaluating transactions

A `@Transactional` method reads an order, calls a blocking payment gateway for 8 seconds, and then updates the order. Does adding `subscribeOn(boundedElastic)` solve everything?

Hint: No. The event loop is freed, but the transaction may still hold a connection for 8 seconds. Consider calling the gateway outside the transaction, then opening a short transaction to update state and check the version.

### Exercise 5: JDBC and R2DBC

A reactive service with `@Transactional` uses an R2DBC repository and `JdbcTemplate`. Can you assume both operations roll back together?

Hint: No. JDBC and R2DBC normally use separate connections and transaction managers. Design coordination explicitly; do not assume a shared transaction.

### Exercise 6: Blocking call timeouts

The publisher times out after 3 seconds, yet the blocking SDK keeps waiting on the socket for 30 seconds. Why can a `boundedElastic` worker remain occupied?

Hint: Cancellation does not guarantee interrupting a blocking call. Configure timeouts on the SDK/client itself and verify cancellation behavior.

### Exercise 7: Using an outbox

An order update must publish a message after commit. Why is an outbox helpful?

Hint: Write the order and outbox event in the same transaction. A worker sends the message after commit and can retry with an idempotency key if the broker or worker fails.

## 17. Takeaways

- R2DBC and Reactor do not make a blocking library non-blocking.
- Use `Mono.fromCallable()` for blocking calls returning a result and `Mono.fromRunnable()` for actions returning nothing.
- Place `subscribeOn(Schedulers.boundedElastic())` on the source publisher to isolate blocking calls.
- Do not use `Mono.just(blockingCall())`, do not call blocking code directly in `map`, and do not use `block()` to nest reactive publishers.
- `boundedElastic` has worker and queue limits; client-side timeouts and concurrency limits are required.
- Isolate only the blocking section. R2DBC repository operations should still be composed reactively as usual.
- Switching schedulers does not automatically release connections or end an active transaction.
- Do not hold an R2DBC transaction while waiting on external blocking I/O unless business rules strictly require it.
- Blocking JDBC usually uses a separate transaction manager and connection; it does not automatically join an R2DBC transaction.
- Transactions should surround only the database operations requiring atomicity.
- When coordinating the database with external side effects, consider idempotency, transactional outbox, or saga.
- Reactor Context can flow across schedulers in a pipeline; manual subscriptions or custom threads/executors can lose context.
- Reactive timeouts do not guarantee blocking tasks stop immediately; configure library timeouts as well.
- Monitor transaction duration, connection pools, and `boundedElastic` to spot resources held too long.

When encountering an irreplaceable blocking task, isolate that exact call onto `boundedElastic` and re-evaluate any transaction surrounding it. Keep R2DBC transactions short and limited to database operations that must commit or roll back together. For side effects outside the database, use appropriate coordination mechanisms instead of expecting a single R2DBC transaction to govern every system.
