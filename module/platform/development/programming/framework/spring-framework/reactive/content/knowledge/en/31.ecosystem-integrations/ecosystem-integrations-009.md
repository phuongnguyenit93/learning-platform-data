# Limiting Splitting Reactive Chains with `subscribe()` or Switching to Imperative APIs

> **Module:** Spring Framework – reactive  
> **Parent topic:** Ecosystem integrations  
> **Focus:** recognizing the reactive ↔ imperative boundary, why calling `subscribe()` inside services/controllers usually breaks the processing chain, when `block()`/`toFuture()`/`toIterable()` are permitted, how to integrate blocking and legacy callback APIs, and how to preserve errors, cancellation, backpressure, transactions, and Reactor Context. Examples use Java 17+, Spring Boot 4.0.9, and Spring WebFlux.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain “assembly” and “subscription” in Reactor, and the difference between cold and hot Publishers.
2. Identify who should own the subscription at each boundary: WebFlux, WebClient, messaging frameworks, tests, or an actual imperative entry point.
3. Spot the anti-pattern `service.doWork().subscribe(); return ...` where errors fail to reach the caller, cancellation is lost, and HTTP success may be returned prematurely.
4. Replace nested `subscribe()` with `map`, `flatMap`, `then`, `zip`, `when`, `onErrorResume`, and appropriate composition operators.
5. Explain why `Mono.just(blockingCall())` and `publishOn` after that call do not solve blocking.
6. Isolate JDBC, JPA, filesystem, or synchronous SDKs using `Mono.fromCallable` + `Schedulers.boundedElastic()` with bounded concurrency.
7. Convert between `Mono` and `CompletableFuture` with awareness of eager/lazy execution and cancellation.
8. Restrict `block`, `blockOptional`, `blockFirst`, `blockLast`, `toIterable`, and `toStream` to controlled synchronous boundaries.
9. Distinguish observational side effects from mandatory business operations that must finish before the response.
10. Keep Reactor Context, reactive transactions, security identity, and cleanup within the same subscription.
11. Write proper WebFlux endpoints and tests proving lazy execution, completion order, errors, and cancellation.
12. Decide when to stop using WebFlux and keep the entire application on a consistent imperative model.

**Short rule:** in reactive business code, **return or compose `Publisher`; do not manually call `subscribe()` just to “make it run”**. Only switch to imperative at an explicit boundary when the caller truly requires a synchronous value; never block the Netty event-loop.

## 2. Distinguishing work description from work execution

A Reactor pipeline is typically **assembled** first, then **triggered** by a `Subscriber`. For cold Publishers like most WebClient requests or `Mono.defer` sources, subscribing starts the work per subscriber.

~~~java
Mono<String> description = Mono.fromSupplier(() -> {
    System.out.println("source started");
    return "done";
});

// Not subscribed yet: the source has not run.
description.map(String::toUpperCase);

// The test or framework will eventually subscribe.
~~~

`map()` creates a new Publisher; if its return value is unused, the newly created operator is not part of the final chain. To retain the transformation:

~~~java
Mono<String> transformed = description.map(String::toUpperCase);
~~~

`Mono.just(value)` is different: **Java evaluates `value` immediately at assembly time**. If the argument makes a synchronous DB or HTTP call, the operation already ran before any subscription:

~~~java
Mono<String> wrong = Mono.just(legacyClient.readSync());
~~~

For sources with side effects or blocking work that must be deferred:

~~~java
Mono<String> deferred = Mono.fromCallable(legacyClient::readSync);
~~~

Calling `fromCallable` does not switch threads on its own. To offload a blocking source, add the appropriate scheduler as shown in section 7.

### 2.1. Cold and hot Publishers

| Property | Cold Publisher | Hot Publisher |
| --- | --- | --- |
| Starts emitting data | Usually per subscription | Can emit even with no subscriber |
| Multiple subscriptions | May re-execute the operation | May receive events from the point of joining |
| Examples | `Mono.defer`, `Mono.fromCallable`, many WebClient calls | Real-time events from `Sinks.Many` |
| Risks | Duplicate POST or database write on double subscription | Dropped events, overflow, or late subscribers |
| Related techniques | Idempotency, intentional `cache`, `share` | Bounded buffer/replay/broadcast with clear policies |

The saying “nothing runs before subscribe” has exceptions: `Mono.just` computes its value at assembly, hot sources may already be emitting, and a pre-created `CompletableFuture` may already be running. Always inspect the nature of the source rather than applying rules mechanically.

### 2.2. One chain, one lifecycle

~~~text
HTTP request
    |
    v
Spring WebFlux subscribes
    |
    v
Controller returns Mono/Flux
    |
    v
Service operators
    |
    v
Repository / WebClient / callback adapter
    |
    +---- onNext / onComplete --> HTTP response
    +---- onError -----------> HTTP error handling
    +---- cancel ------------> cleanup upstream
~~~

When you avoid splitting subscriptions, a request has one primary path for propagating error, cancellation, and demand signals. This is the foundation for transactions and tracing to flow end-to-end.

## 3. Who owns the subscription?

`subscribe()` is neither syntax for `await` nor a way to force a task to finish. It creates a subscription and returns a `Disposable` for the caller to manage.

| Boundary | Typical subscription owner | What should the app return? |
| --- | --- | --- |
| Spring WebFlux controller | WebFlux runtime | `Mono<T>` / `Flux<T>` / `Mono<Void>` |
| Spring WebFlux `WebFilter` | WebFlux runtime | `Mono<Void>` of the entire filter chain |
| WebClient call in a service | Outer caller/framework subscribes when needed | `Mono` / `Flux`, without calling `.subscribe()` |
| Reactive repository/transaction | Outer reactive chain | Composed Publisher |
| `StepVerifier` in tests | `StepVerifier` | Publisher to verify |
| Command-line `main`, imperative UI listener, managed lifecycle task | Boundary code | May `subscribe` and hold the `Disposable` |
| Synchronous function forced to return `T` | Imperative caller | May `block(timeout)` off the event-loop per policy |

Seeing `subscribe()` is not automatically wrong. What is wrong is an **unowned subscribe** in the middle of a chain whose subscription already belongs to a framework or caller.

### 3.1. Anti-pattern in a controller

~~~java
@PostMapping("/orders/{id}/audit")
Mono<String> wrong(@PathVariable String id) {
    auditService.audit(id).subscribe();
    return Mono.just("AUDIT_OK");
}
~~~

Flaws in this example:
- HTTP may return `AUDIT_OK` before the audit finishes writing.
- Audit errors do not propagate into the HTTP response as an error signal.
- Client disconnect does not necessarily cancel the running audit task.
- The request's tracing/security/transaction Context may not enter the detached subscription.
- Retrying the request can cause duplicate audit executions.
- Nobody holds the `Disposable` to cancel or clean up.

How to fix:

~~~java
@PostMapping("/orders/{id}/audit")
Mono<String> correct(@PathVariable String id) {
    return auditService.audit(id).thenReturn("AUDIT_OK");
}
~~~

Here HTTP only succeeds once `auditService.audit` has completed. If the audit fails, the outer chain fails and WebFlux can handle it properly via exception mapping.

### 3.2. Anti-pattern in a service

~~~java
public Mono<Order> submit(Order order) {
    repository.save(order).subscribe();
    return Mono.just(order);
}
~~~

Two independent issues: the `save` operation runs in a detached subscription, and the caller receives `order` before persistence confirms. Replace with:

~~~java
public Mono<Order> submit(Order order) {
    return repository.save(order);
}
~~~

If another system must also be updated:

~~~java
public Mono<Order> submit(Order order) {
    return repository.save(order)
        .flatMap(saved ->
            auditClient.record(saved).thenReturn(saved));
}
~~~

This chain awaits both save and audit. However, the two operations do not automatically form a distributed transaction; if you need event publishing tied to the DB commit, consider the outbox pattern.

## 4. Using operators instead of nested `subscribe`

### 4.1. `map` for fast, synchronous transformations

~~~java
Mono<OrderView> view = repository.findById(id)
    .map(order -> new OrderView(order.id(), order.status()));
~~~

`map` is for transforming a single value, not calling another Publisher. Avoid placing blocking JDBC, synchronous HTTP, or heavy CPU work inside `map` running on the event-loop.

### 4.2. `flatMap` for operations returning Mono

Wrong:

~~~java
Mono<Mono<Receipt>> nested = repository.save(order)
    .map(saved -> auditClient.record(saved).thenReturn(
        new Receipt(saved.id(), "AUDITED")));
~~~

Right:

~~~java
Mono<Receipt> receipt = repository.save(order)
    .flatMap(saved ->
        auditClient.record(saved)
            .thenReturn(new Receipt(saved.id(), "AUDITED")));
~~~

`flatMap` connects the inner Publisher's signals to the outer chain, preserving errors and cancellation. `Mono<Mono<T>>` is usually a sign you need `flatMap`, not `.subscribe()` inside `map`.

### 4.3. `then`, `thenReturn`, `thenMany`

| Operator | Use when | Result |
| --- | --- | --- |
| `then()` | Only care about upstream completion | `Mono<Void>` |
| `thenReturn(value)` | After upstream completes, emit a constant value | `Mono<V>` |
| `then(otherMono)` | Run a sequential next step | Result of `otherMono` |
| `thenMany(otherFlux)` | After upstream, start another stream | `Flux<T>` |

Example:

~~~java
public Mono<Void> deleteThenNotify(String id) {
    return repository.deleteById(id)
        .then(notificationClient.deleted(id));
}
~~~

`notificationClient.deleted(id)` is executed via `then`'s subscription once the delete finishes; if delete errors, the notification does not run. If notification fails after delete has already committed, you need a business recovery policy rather than assuming full-system rollback.

### 4.4. Parallel and sequential

When two operations are independent:

~~~java
Mono<Tuple2<Customer, Cart>> combined =
    Mono.zip(customerClient.find(customerId),
             cartClient.load(customerId));
~~~

When you only need both to complete:

~~~java
Mono<Void> finished = Mono.when(
    cache.invalidate(id),
    searchIndex.remove(id));
~~~

`Mono.when` executes the sources within the same outer subscription; when one source errors, the combinator emits the error and can cancel the remaining sources.

If step B depends on step A, use `flatMap` or `then`, not `zip` just to force two operations to run concurrently.

**Note on `Mono<Void>`:** `zip` requires each source to emit a value. A source completing empty can prevent `zip` from invoking the combinator. For `Mono<Void>` tasks, use `then`, `when`, or explicitly convert completion into a value.

### 4.5. Do not turn `doOnNext` into a business transaction

`doOnNext`, `doOnError`, `doOnSuccess`, and `doFinally` suit metrics, logging, and lifecycle observation:

~~~java
return repository.findById(id)
    .doOnNext(item -> metrics.recordFound())
    .doOnError(error -> metrics.recordFailure());
~~~

If recording an audit must succeed, never call `.subscribe()` or launch an async task inside `doOnNext`:

~~~java
// Wrong if audit must finish before the response.
return repository.findById(id)
    .doOnNext(item -> auditClient.record(item).subscribe());
~~~

Use `flatMap`/`then`. Do not treat `doOnError` as catch/recovery: this operator only observes errors; to transform errors or fall back, use `onErrorMap`, `onErrorResume`, or `onErrorReturn` per policy.

## 5. Errors get “lost” when subscribing manually

~~~java
Mono<Void> audit = auditClient.record(order);

audit.subscribe();
return Mono.just("OK");
~~~

The inner subscription has its own error channel. Errors do not propagate to the outer `Mono.just("OK")`, so the caller cannot tell the operation failed. Calling `subscribe()` without an error consumer can also lead to improperly observed errors.

Right:

~~~java
return auditClient.record(order)
    .thenReturn("OK")
    .onErrorMap(error ->
        new AuditUnavailableException("Audit failed", error));
~~~

`AuditUnavailableException` is an application-defined exception type in this fragment. When returning HTTP responses, map exceptions to safe status/error DTOs via `@ControllerAdvice`/`ErrorWebExceptionHandler`; never return raw stack traces or credentials.

### 5.1. Error recovery must be meaningful

~~~java
return catalogClient.get(id)
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        notFound -> Mono.empty());
~~~

Treating 404 as absent may fit business rules; however, do not write:

~~~java
return catalogClient.get(id)
    .onErrorResume(error -> Mono.empty());
~~~

if that masks 401, 503, timeouts, or data-parsing failures.

### 5.2. Timeout across the whole operation

~~~java
return auditClient.record(order)
    .timeout(Duration.ofSeconds(2))
    .thenReturn("AUDIT_OK");
~~~

On timeout, the outer chain emits an error and sends cancellation upstream. Whether upstream actually stops I/O/SDK work depends on the driver/adapter. For a JDBC blocking call that has already started, Reactor cancellation does not guarantee the driver immediately cancels the query.

## 6. When is calling `subscribe()` manually valid?

An entry point that neither receives nor returns a Publisher may have to start work proactively, such as:
- Desktop UI actions, command-line jobs.
- A purely imperative callback library.
- Managed startup/shutdown lifecycles.
- Integration with a framework whose callback API does not accept a Publisher.

In those cases, **the boundary code is the owner** and must handle errors, cancellation, shutdown, concurrency, and idempotency.

### 6.1. Hold the Disposable and an error handler

~~~java
Disposable running = taskService.execute(command)
    .subscribe(
        ignored -> { },
        error -> log.warn("Task failed", error),
        () -> log.info("Task completed")
    );

// When the user cancels or the component closes:
running.dispose();
~~~

This is an illustrative fragment: `taskService`, `command`, and `log` must be supplied by the application. `Disposable.dispose()` sends a cancel signal; it does not guarantee an external blocking operation halts instantaneously.

**Do not discard the `Disposable` if the task has a cancellable lifecycle.** You can use `Disposables.composite()` to manage multiple subscriptions tied to a screen or component, disposing the entire group when the component closes.

### 6.2. Do not call `block()` to wait inside a WebFlux event handler

A callback may be invoked from an event-loop or dedicated thread. Unless you know the caller thread, never call `block()` merely because a callback API returns `void`. Look for an async extension point in the framework or offload the task to a managed worker.

If fire-and-forget is unavoidable, you must have:
- An error consumer.
- `Disposable` management.
- Quota/concurrency limits.
- A shutdown/cancellation path.
- Logging/metrics per job ID.
- Idempotency/retry budgets.
- A durable queue mechanism if tasks must never be lost.

`subscribe()` is not a message queue; if the JVM crashes, in-memory tasks can vanish.

## 7. Wrapping blocking APIs with boundedElastic: a bridge, not magic

### 7.1. Wrong: eager blocking

~~~java
public Mono<Customer> load(String id) {
    return Mono.just(legacyJpa.findById(id));
}
~~~

Java calls `findById` before creating the `Mono`, potentially on the Netty event-loop.

### 7.2. Right: lazy source and offload

~~~java
public Mono<Customer> load(String id) {
    return Mono.fromCallable(() -> legacyJpa.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` defers the operation until subscribe time, and `subscribeOn(boundedElastic())` puts the blocking source onto the scheduler dedicated to I/O waiting. If the callable returns `null`, the Mono completes empty; use `switchIfEmpty` when 404 is needed.

When the synchronous result returns `void`:

~~~java
public Mono<Void> writeLegacy(Order order) {
    return Mono.fromRunnable(() -> legacyWriter.write(order))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
~~~

**Note:** this is still blocking code. It holds a worker thread and a JDBC connection while waiting. `boundedElastic` caps threads/task queues to prevent unbounded resource growth; you should also cap concurrency and pool sizes for each dependency.

### 7.3. Why doesn't `publishOn` after `Mono.just` rescue it?

~~~java
// Wrong: readSync() already ran before publishOn takes effect.
Mono<String> wrong = Mono.just(legacyClient.readSync())
    .publishOn(Schedulers.boundedElastic());

// Right: deferred source and subscribeOn.
Mono<String> correct =
    Mono.fromCallable(legacyClient::readSync)
        .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` affects subscription/emission on the source side; `publishOn` switches context for operators downstream of where it is placed. Do not use `publishOn` to patch an eager blocking call.

### 7.4. Preserving JDBC/JPA transaction correctness

Standard JPA/JDBC `@Transactional` uses thread-bound resources. Do not start a transaction on a Netty thread and offload individual JDBC rows to other threads.

A clean boundary:

~~~java
@Service
class LegacyBillingService {

    @Transactional
    public Receipt chargeSync(Command command) {
        // All JDBC/JPA operations stay inside one synchronous
        // call wrapped by the Spring transaction proxy.
        return legacyRepository.charge(command);
    }
}
~~~

Outer wrapper:

~~~java
Mono<Receipt> charge(Command command) {
    return Mono.fromCallable(
            () -> legacyBillingService.chargeSync(command))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is an illustrative fragment requiring `legacyRepository`, `Receipt`, `Command`, and the corresponding JPA/JDBC beans. The transaction must open and commit within the same blocking call on the worker thread; do not pass a lazy JPA entity outside and access it after the transaction has closed.

### 7.5. Bounding concurrency

~~~java
Flux<Receipt> chargeBatch(Flux<Command> commands) {
    return commands.flatMap(
        cmd -> Mono.fromCallable(
                () -> legacyBillingService.chargeSync(cmd))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

`flatMap(..., 8)` caps concurrent inner subscriptions **within each batch**. Under many HTTP requests, total concurrency can still be high. Add a bulkhead or semaphore at the dependency level, along with Hikari pool sizing, timeouts, and request limits.

## 8. Crossing from reactive to imperative APIs

Some boundaries demand an immediate `T`, such as a CLI `main` or an SDK accepting only synchronous values. Choose explicitly and know what will block.

### 8.1. `block(Duration)` at an imperative boundary

~~~java
public static void main(String[] args) {
    Mono<String> result = Mono.just("READY");
    String value = result.block(Duration.ofSeconds(2));
    System.out.println(value);
}
~~~

Output:

~~~text
READY
~~~

On Java 17+ with Reactor dependencies, this simple example prints `READY`. `block(Duration)` waits for a signal or timeout; each call can create a new subscription. Never use `block` inside a WebFlux controller, `WebFilter`, or operators running on Reactor non-blocking threads.

Reactor can throw `IllegalStateException` if `block()`/`blockFirst()`/`blockLast()` runs on a scheduler marked non-blocking (such as event-loop/parallel schedulers). Even where allowed, blocking still occupies a thread and affects capacity.

### 8.2. `blockOptional`, `blockFirst`, `blockLast`

| API | Return type | Risks |
| --- | --- | --- |
| `Mono.block(timeout)` | `T` or null when empty | Blocks caller, may create a new subscription |
| `Mono.blockOptional(timeout)` | `Optional<T>` | Still blocks caller |
| `Flux.blockFirst(timeout)` | First element, cancels the rest | May drop elements on hot sources |
| `Flux.blockLast(timeout)` | Last element after onComplete | Infinite if stream never completes |
| `Flux.toIterable()` | Blocking/pull-based Iterable | May block forever and hold resources |
| `Flux.toStream()` | Synchronous Java Stream | Requires `close()`; mind cancellation/resources |
| `Mono.toFuture()` | `CompletableFuture<T>` | Triggers subscription; subsequent `get/join` blocks if incomplete |

For bounded data needing `List<T>` at a synchronous boundary, you can use:

~~~java
List<String> values = Flux.just("A", "B", "C")
    .collectList()
    .block(Duration.ofSeconds(2));
~~~

`collectList()` holds all elements in memory. Only do this when the count is bounded; never turn an infinite stream into a list or iterate a large `Flux` via `toIterable()` on the event-loop.

### 8.3. Is `toFuture()` non-blocking?

~~~java
CompletableFuture<String> future =
    webClient.get()
        .uri("/status")
        .retrieve()
        .bodyToMono(String.class)
        .toFuture();
~~~

`toFuture()` bridges from `Mono` to `CompletableFuture` and initiates subscription. If the caller chains `thenApply`/`whenComplete`, execution can stay async. If the caller calls `future.get()` or `future.join()`, the caller blocks the thread again.

In code that should return a Publisher, do not call `toFuture()` and immediately wrap with `Mono.fromFuture(...)` just to get back to `Mono`; that adds an unnecessary boundary and alters subscribe/cancel timing.

### 8.4. Never block inside `map`/`flatMap`

~~~java
// Wrong: blocks the thread running the operator.
return orderRepository.findById(id)
    .map(order -> pricingClient.price(order).block());
~~~

Replace with composition:

~~~java
return orderRepository.findById(id)
    .flatMap(order ->
        pricingClient.price(order)
            .map(price -> new PricedOrder(order, price)));
~~~

`PricedOrder` is an illustrative DTO fragment. `flatMap` preserves the reactive chain and avoids blocking a thread just to unwrap another Mono.

## 9. Integrating CompletableFuture and CompletionStage

### 9.1. A pre-created Future is often already running

~~~java
CompletableFuture<User> eager = legacyAsyncApi.fetchUser(id);
Mono<User> mono = Mono.fromFuture(eager);
~~~

`fetchUser(id)` may have already started I/O at assembly time. `Mono.fromFuture` only attaches to the existing Future's outcome; it does not make the operation lazy.

### 9.2. Creating the Future on subscription

~~~java
Mono<User> lazy = Mono.fromFuture(
    () -> legacyAsyncApi.fetchUser(id));
~~~

The Supplier is only invoked upon subscription. For a `CompletionStage` that is not a `CompletableFuture`, there is `Mono.fromCompletionStage(() -> api.fetch(id))`.

Per the Reactor API, when `Mono.fromFuture` is cancelled, it attempts to cancel the `CompletableFuture` by default; a `suppressCancel` overload exists if you do not want to propagate cancellation. However, Future cancellation does not guarantee the underlying HTTP request, database query, or task truly halts. Verify whether the SDK implements cancellation/interruption.

### 9.3. `toFuture` at a sync-async boundary

When a Java API requires returning `CompletableFuture`:

~~~java
public CompletableFuture<Receipt> submitAsFuture(Command command) {
    return reactiveService.submit(command).toFuture();
}
~~~

Choose this boundary **deliberately**, rather than scattering `toFuture()` across service methods. When the Future consumer no longer needs the result, have a cancellation policy. For operations with non-idempotent side effects, cancelling the wait does not necessarily undo an already-committed side effect.

## 10. Integrating one-shot callback APIs

Many legacy libraries look like:

~~~java
legacyApi.request(
    value -> handleSuccess(value),
    error -> handleError(error)
);
~~~

To return a `Mono` instead of subscribing manually, use `Mono.create`:

~~~java
Mono<String> lookup(CallbackApi api, String key) {
    return Mono.create(sink -> {
        Registration registration = api.lookup(
            key,
            sink::success,
            sink::error
        );
        sink.onDispose(registration::close);
    });
}
~~~

This is an **illustrative adapter fragment**, requiring `CallbackApi.lookup(key, success, error)` returning a `Registration` with `close()`. Ensure the following:

1. Invoke the success/error callback at most once.
2. Clean up the registration on completion, error, and cancellation.
3. The adapter must not block the thread registering the callback.
4. If the callback API fires multiple progress notifications, use `Flux.create`/`Sinks.Many` with an appropriate buffer/demand policy instead of `Mono.create`.
5. Never swallow callback errors or write unsynchronized to shared mutable state.
6. If registration can be returned after a synchronous callback fires, make cleanup genuinely thread-safe/race-safe.

`Mono.create` is a callback bridge; it **does not automatically turn** a blocking underlying SDK into non-blocking. If `api.lookup` performs blocking work right before returning Registration, offload registration appropriately or fix the SDK wrapper.

## 11. Push events and Reactive Streams demand

A callback can emit events faster than the consumer. Reactive Streams has `request(n)` so downstream throttles upstream; callback APIs may lack any corresponding slowdown mechanism.

When using `Flux.create` or `Sinks.Many`:
- Decide whether events are broadcast, replayed, or single-subscriber.
- Bound buffers and handle overflow; never buffer unboundedly.
- On cancel, unregister the listener and release buffers.
- If data must never be lost, prefer durable queues or protocol-level flow control.
- Do not assume an external emitter honors backpressure merely because it was wrapped in a `Flux`.

Example fragment:

~~~java
Flux<PriceEvent> prices(ListenerApi api) {
    return Flux.create(sink -> {
        Registration reg = api.register(
            event -> sink.next(event),
            sink::error,
            sink::complete
        );
        sink.onDispose(reg::close);
    });
}
~~~

`PriceEvent`, `ListenerApi`, and `Registration` are integration types you must implement. Overflow and lifecycle policies must be selected according to real source characteristics before production use.

## 12. Reactive transactions and Reactor Context

A reactive transaction is not identified solely by a Java thread. `ReactiveTransactionManager` and `TransactionalOperator` use the Reactor subscriber `Context` to hold transaction-bound resources as operators switch threads.

~~~java
Mono<Receipt> process(Command command) {
    return repository.reserve(command.productId())
        .then(repository.save(command.toEntity()))
        .map(this::toReceipt)
        .as(transactionalOperator::transactional);
}
~~~

This is a conceptual fragment, assuming the repository uses a reactive driver and `transactionalOperator` was built from the right `ReactiveTransactionManager`. Both DB operations must stay within the same outer chain/subscriber Context.

Wrong:

~~~java
Mono<Receipt> processWrong(Command command) {
    repository.reserve(command.productId()).subscribe();
    return repository.save(command.toEntity())
        .map(this::toReceipt);
}
~~~

The `reserve` call has left the save operation's subscription/transaction. It may keep running after the request fails, commit outside the boundary, or lose tracing/security information.

### 12.1. Context is not ThreadLocal

`ThreadLocal` can change whenever `publishOn`, `subscribeOn`, or an async callback switches threads. Pass important metadata in the Reactor Context or a matching context-propagation integration.

~~~java
Mono<String> currentTrace() {
    return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("traceId", "unknown")));
}

Mono<String> workflow = currentTrace()
    .contextWrite(context ->
        context.put("traceId", "trace-123"));
~~~

This is a self-contained fragment about Reactor Context. Context values attach to the subscription rather than being read from a global variable or thread name.

Do not log JWTs, secrets, or raw user data into logs/metric tags merely because they are in the Context. With reactive Spring Security, use the `ReactiveSecurityContextHolder` API instead of rolling your own ThreadLocal security context.

### 12.2. `@Transactional` and subscription

With a reactive method proxied by `@Transactional` and paired with the right reactive transaction manager, the transaction runs at subscription time. Calling `subscribe` manually inside the method takes that operation outside the caller's implicit transaction.

JDBC/JPA `PlatformTransactionManager` uses thread-bound resources; it does not automatically join an R2DBC transaction. If integrating blocking JPA, keep the entire JPA transaction inside one synchronous call and offload the boundary as in section 7. Do not expect a single `@Transactional` spanning both JPA and R2DBC to create an atomic distributed transaction.

## 13. Cancellation and resource cleanup

When an HTTP client disconnects, WebFlux can cancel the Publisher serving the response. If code maintains a secondary subscription, cancellation from the request does not automatically cancel that subscription.

Natural pipeline:

~~~java
return webClient.get()
    .uri("/large-report")
    .retrieve()
    .bodyToFlux(ReportPart.class)
    .doOnCancel(() -> metrics.recordCancelled())
    .doFinally(signal -> metrics.recordFinished(signal));
~~~

`doFinally` receives a `SignalType` distinguishing `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. Do not use `doFinally` to manually `subscribe()` a cleanup task and assume the caller will wait for it.

### 13.1. `using` and `usingWhen`

When managing resources yourself:
- `using` suits resources with synchronous cleanup.
- `usingWhen` suits async acquire/cleanup, such as connections or temporary resources opened/closed via Publisher.
- Cleanup must cover complete, error, and cancellation branches when resource semantics require them.

Conceptual example:

~~~java
Mono<Result> operation = Mono.usingWhen(
    asyncResourceFactory.open(),
    resource -> resource.run(),
    resource -> resource.close()
);
~~~

`asyncResourceFactory`, `Result`, and `resource` are illustrative types. For resources with distinct rollback/cleanup on error or cancel, use the `usingWhen` overload accepting `asyncComplete`, `asyncError`, and `asyncCancel` callbacks. Never close the resource before the Publisher finishes processing.

### 13.2. Do not confuse cancel with business rollback

Cancellation signals “downstream no longer needs the data”. It cannot undo an already-committed database write or a charge executed by a payment gateway. For operations with mandatory side effects, use idempotency keys, durable outboxes/jobs, and explicit business states; do not rely on cancellation as a general-purpose transaction rollback.

## 14. Subscribing twice can execute an operation twice

~~~java
Mono<Receipt> operation = paymentClient.charge(command);

operation.subscribe();
operation.subscribe();
~~~

With a cold Publisher making an HTTP call, two subscriptions can send **two payment requests**. In a real application, that is a severe bug. Use idempotency keys and subscribe only at the managed boundary.

Also watch out for:

~~~java
Mono<Receipt> operation = paymentClient.charge(command);

Receipt a = operation.block(Duration.ofSeconds(5));
Receipt b = operation.block(Duration.ofSeconds(5));
~~~

Two `block` calls can create two subscriptions and re-run side effects.

### 14.1. `cache()`/`share()` are not default cure-alls

`cache()` can memoize results for subsequent subscribers, but it alters semantics and lifecycle. For user/tenant-scoped data, sharing a cache across the wrong scope can leak data or return stale values. For payments or write operations, business-layer idempotency is still required even when caching is used.

Be careful with cache TTL, memory limits, error caching, and stale data. Never slap on `cache()` merely to hide a nested-subscription bug.

## 15. Restricting `block()` in WebFlux

### 15.1. Why is the event-loop sensitive?

The Netty event-loop typically serves many sockets with a small number of threads. If you call JDBC, `Thread.sleep`, `Future.get`, or `Mono.block` on that thread, many other requests must wait.

~~~text
WebFlux event loop
   |
   +-- handle Request A
   |       |
   |       +-- block 2 seconds  <-- occupies thread
   |
   +-- Request B, C, D on same thread must wait
~~~

R2DBC or reactive WebClient does not hold a thread waiting for I/O in the JDBC model. However, heavy CPU-bound work can also occupy the event-loop; you may need a dedicated scheduler, load shedding, or a bounded executor.

### 15.2. Acceptable boundaries

`block(timeout)` can be reasonable in:
- `main` of a short-lived command-line tool.
- A migration command or synchronous batch step with a timeout.
- Unit tests outside the event-loop (though `StepVerifier` is usually better).
- Temporary adapters for libraries accepting only synchronous values, with a clear capacity budget.

`block()` inside a WebFlux controller/service/filter handling requests is inappropriate. If most of the system is imperative, **Spring MVC + JDBC/JPA** is usually simpler than forcing every call into `Mono` only to block again.

### 15.3. Virtual threads do not turn blocking into reactive

Virtual threads (on supported JDKs) can reduce the cost of parked threads, but they do not make the JDBC API non-blocking, nor do they change transaction models or database capacity. The Java 17 demo does not rely on virtual threads. Choose a consistent architecture rather than treating `subscribe()`/`block()` as unconditional optimizations.

## 16. Complete example: WebFlux calling a legacy blocking system and a reactive API

This illustrative project runs without requiring a database or external API:
- `LegacyOrderGateway` simulates a synchronous API with `Thread.sleep` to show a blocking boundary.
- `ReactiveAuditGateway` simulates a non-blocking async operation with `Mono.delay`.
- `OrderBoundaryService` chains both operations without calling `.subscribe()` and without blocking the event-loop.
- The controller returns Mono so WebFlux manages the subscription.
- `StepVerifier` tests and HTTP integration tests verify ordering, lazy execution, 404, and errors.

**The legacy gateway in the demo is an intentional simulation**, not a real JDBC driver. When replacing it with JDBC/JPA, configure DataSource/pool/transactions in the legacy module, keep the `fromCallable + boundedElastic` pattern, and do not remove concurrency limits.

### 16.1. Directory structure

~~~text
reactive-boundary-demo/
├── pom.xml
├── src/main/java/com/example/boundary/
│   ├── BoundaryApplication.java
│   ├── OrderView.java
│   ├── AuditReceipt.java
│   ├── LegacyOrderGateway.java
│   ├── ReactiveAuditGateway.java
│   ├── OrderBoundaryService.java
│   └── OrderBoundaryController.java
└── src/test/java/com/example/boundary/
    ├── OrderBoundaryServiceTest.java
    └── OrderBoundaryHttpTest.java
~~~

### 16.2. pom.xml

Spring Boot 4.0.9 and Java 17+. In Boot 4, the WebFlux runtime starter and the WebFlux test starter are separate artifacts.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The parent manages Spring/Reactor versions. There is no need to declare a separate version for `reactor-test` when using Spring Boot's dependency management.

### 16.3. BoundaryApplication.java

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

### 16.4. OrderView.java and AuditReceipt.java

`OrderView.java`:

~~~java
package com.example.boundary;

public record OrderView(String id, String status) {}
~~~

`AuditReceipt.java`:

~~~java
package com.example.boundary;

public record AuditReceipt(String id, String outcome) {}
~~~

They are immutable DTOs, separate from the components performing I/O.

### 16.5. LegacyOrderGateway.java

~~~java
package com.example.boundary;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class LegacyOrderGateway {

    private final AtomicInteger invocations = new AtomicInteger();

    public OrderView find(String id) {
        invocations.incrementAndGet();

        try {
            // Simulates a synchronous JDBC/JPA or SDK call.
            Thread.sleep(40);
        }
        catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "legacy operation interrupted", error);
        }

        if ("missing".equals(id)) {
            return null;
        }

        return new OrderView(id, "READY");
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

`Thread.sleep` exists only in the simulated gateway to represent a blocking source. Never use `Thread.sleep` in a real controller or reactive operator. When replacing the gateway with JPA, all synchronous operations and transactions must reside inside the gateway/transaction service method and be offloaded through the service wrapper.

### 16.6. ReactiveAuditGateway.java

~~~java
package com.example.boundary;

import java.time.Duration;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class ReactiveAuditGateway {

    public Mono<Void> record(OrderView order) {
        return Mono.delay(Duration.ofMillis(40))
            .flatMap(ignored -> {
                if ("fail".equals(order.id())) {
                    return Mono.<Void>error(
                        new IllegalStateException(
                            "simulated audit failure"));
                }
                return Mono.<Void>empty();
            });
    }
}
~~~

`Mono.delay` simulates I/O completion without `Thread.sleep`. The `"fail"` path emits an error signal; the outer chain must propagate the error to the HTTP response rather than returning fake success. In a real application, replace the method with a reactive WebClient/R2DBC call.

### 16.7. OrderBoundaryService.java

~~~java
package com.example.boundary;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class OrderBoundaryService {

    private final LegacyOrderGateway legacyOrderGateway;
    private final ReactiveAuditGateway reactiveAuditGateway;

    public OrderBoundaryService(
            LegacyOrderGateway legacyOrderGateway,
            ReactiveAuditGateway reactiveAuditGateway) {
        this.legacyOrderGateway = legacyOrderGateway;
        this.reactiveAuditGateway = reactiveAuditGateway;
    }

    public Mono<OrderView> find(String id) {
        return Mono.fromCallable(() ->
                legacyOrderGateway.find(id))
            .subscribeOn(Schedulers.boundedElastic())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "order not found")));
    }

    public Mono<AuditReceipt> audit(String id) {
        return find(id)
            .flatMap(order ->
                reactiveAuditGateway.record(order)
                    .thenReturn(
                        new AuditReceipt(order.id(), "AUDITED")));
    }
}
~~~

This is the core part:
- `fromCallable` makes the source lazy; until there is a subscriber, `LegacyOrderGateway.find` does not run.
- `subscribeOn(boundedElastic())` offloads the blocking source off the Netty event-loop.
- `switchIfEmpty` produces a 404 error if the gateway returns null.
- `flatMap` chains the audit into the same subscription.
- `thenReturn` only returns the receipt once the audit completes normally.
- If the audit emits an error, HTTP never receives `AUDITED`; there is no nested `subscribe()`.

### 16.8. OrderBoundaryController.java

~~~java
package com.example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderBoundaryController {

    private final OrderBoundaryService service;

    public OrderBoundaryController(OrderBoundaryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<OrderView> get(@PathVariable String id) {
        return service.find(id);
    }

    @PostMapping("/{id}/audit")
    public Mono<AuditReceipt> audit(@PathVariable String id) {
        return service.audit(id);
    }
}
~~~

There is no `.subscribe()`, `.block()`, or `.toFuture()` in the controller. Spring WebFlux owns the subscription and awaits publisher completion to build the response.

### 16.9. OrderBoundaryServiceTest.java

~~~java
package com.example.boundary;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderBoundaryServiceTest {

    @Test
    void blockingGatewayIsLazyUntilSubscription() {
        LegacyOrderGateway legacy = new LegacyOrderGateway();
        ReactiveAuditGateway audit = new ReactiveAuditGateway();
        OrderBoundaryService service =
            new OrderBoundaryService(legacy, audit);

        Mono<OrderView> pipeline = service.find("42");

        assertEquals(0, legacy.invocationCount());

        StepVerifier.create(pipeline)
            .expectNext(new OrderView("42", "READY"))
            .verifyComplete();

        assertEquals(1, legacy.invocationCount());
    }

    @Test
    void auditCompletesBeforeReceiptIsEmitted() {
        OrderBoundaryService service =
            new OrderBoundaryService(
                new LegacyOrderGateway(),
                new ReactiveAuditGateway());

        StepVerifier.create(service.audit("42"))
            .expectNext(new AuditReceipt("42", "AUDITED"))
            .verifyComplete();
    }

    @Test
    void innerAuditFailureReachesOuterSubscriber() {
        OrderBoundaryService service =
            new OrderBoundaryService(
                new LegacyOrderGateway(),
                new ReactiveAuditGateway());

        StepVerifier.create(service.audit("fail"))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && error.getMessage().contains(
                        "simulated audit failure"))
            .verify();
    }

    @Test
    void cancellationPropagatesIntoSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<Long> source = Flux.interval(
                Duration.ofMillis(10))
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(source)
            .expectNext(0L)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void operatorDoesNotRunUntilSubscribed() {
        AtomicBoolean called = new AtomicBoolean();

        Mono<String> pipeline = Mono.fromSupplier(() -> {
            called.set(true);
            return "ok";
        });

        assertEquals(false, called.get());

        StepVerifier.create(pipeline)
            .expectNext("ok")
            .verifyComplete();

        assertTrue(called.get());
    }
}
~~~

The tests verify lazy sources, audit completion, error propagation, and cancellation. They use StepVerifier as the subscriber, rather than calling `.subscribe()` and sleeping for results. The cancellation test measures Reactor signals; it does not assert that every JDBC/SDK call can be cancelled instantaneously.

### 16.10. OrderBoundaryHttpTest.java

~~~java
package com.example.boundary;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderBoundaryHttpTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void getUsesLegacyBoundaryWithoutBlockingWebFlux() {
        http().get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void auditWaitsForReactiveSideEffect() {
        http().post()
            .uri("/api/orders/42/audit")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.outcome").isEqualTo("AUDITED");
    }

    @Test
    void missingOrderReturns404() {
        http().get()
            .uri("/api/orders/missing")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void auditFailureDoesNotReturnSuccess() {
        http().post()
            .uri("/api/orders/fail/audit")
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
~~~

The HTTP tests prove endpoints, statuses, and JSON contracts work when WebFlux manages the subscription. A single timing check does not prove the server is completely non-blocking; doing that requires a profiler, BlockHound in an appropriate test environment, connection pool metrics, and load tests.

### 16.11. Running the project

Requires Java 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

In Windows CMD, try:

~~~bat
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42/audit
curl -i http://localhost:8080/api/orders/missing
curl -i -X POST http://localhost:8080/api/orders/fail/audit
~~~

Expected results:

| Request | Status | Body or meaning |
| --- | --- | --- |
| GET `/api/orders/42` | 200 | `{"id":"42","status":"READY"}` |
| POST `/api/orders/42/audit` | 200 | `{"id":"42","outcome":"AUDITED"}` only after audit completes |
| GET `/api/orders/missing` | 404 | Error response produced by WebFlux |
| POST `/api/orders/fail/audit` | 5xx | Audit error is not masked by a success response |

For the audit path, total response time includes the legacy blocking call (offloaded) plus the reactive audit duration; waiting for both steps to finish **matches the contract**. The delay numbers are for simulation only.

## 17. Auditing by architecture rather than just “counting subscribes”

Do not ban `subscribe()` across the entire codebase. What matters is location and ownership. Review process:

1. Find all `subscribe(` calls and determine whether a caller/framework already owns a subscription.
2. If inside a controller/service/filter, replace with operator composition.
3. If at an imperative entry point, ensure an error consumer, Disposable owner, cancel/shutdown, and metrics exist.
4. Search for `block(`, `blockFirst`, `blockLast`, `toIterable`, `toStream`, `toFuture`, `Future.get`, `join`, `Thread.sleep`.
5. Check whether they run on the Netty event-loop or a non-blocking scheduler.
6. For blocking I/O, build a lazy source and offload at the right boundary; do not just change the return type to Mono.
7. For future/callback sources, verify lazy execution and SDK cancellation.
8. For databases, check transaction managers/thread-bound vs. Reactor Context.
9. For outbound HTTP, verify response bodies are consumed/released.
10. Verify inner operation errors reach the caller rather than getting lost in a nested subscription.
11. Check whether side effects requiring completion use `flatMap/then`.
12. Check subscription counts on operations with side effects; add idempotency where needed.

### 17.1. Alerting signals

- HTTP request returns 2xx while the audit/payment/DB write still fails later.
- `ErrorCallbackNotImplemented` or “dropped” errors not tied to a request ID.
- CPU/event-loop latency rises when synchronous JDBC/SDKs are added.
- Active task counts rise even after clients have disconnected.
- Both `boundedElastic` thread pool and Hikari pending queues grow simultaneously.
- Duplicate outbound POSTs during retries or multiple subscriptions.
- Reactive transaction rolls back while a side effect in a detached subscription still commits.

## 18. Common mistakes and how to fix them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| `.subscribe()` in a controller | Framework does not wait for task; errors/cancel detached | Return Publisher |
| `.subscribe()` inside `map` | Creates a nested subscription | `flatMap`/`then` |
| `.subscribe()` inside `doOnNext` to write audit | Does not bind business completion | `flatMap` and `thenReturn` |
| `Mono.just(blockingCall())` | Blocking runs eagerly | `fromCallable` + `subscribeOn(boundedElastic)` |
| `publishOn` after an eager call | Switches threads too late | Create a lazy source first |
| `block()` on the Netty event-loop | Stalls other requests or gets rejected | Compose reactive chain |
| `Flux.blockLast()` on an infinite source | Never completes | Bound the stream and add timeout |
| `toIterable()` on unbounded data | Blocking and memory pressure | Keep Flux or paginate |
| `Mono.toFuture().get()` in a handler | Round-trip blocking | Use Mono directly |
| `Mono.fromFuture(alreadyRunningFuture)` assuming lazy | Future may already be running | Supplier overload |
| Callback never unregistered | Leaks listener/resources on cancel | `sink.onDispose` |
| One cold source with multiple subscribers | Side effect runs again | Single owner and idempotency |
| `onErrorResume(error -> Mono.empty())` for all errors | Masks 401/503/timeouts | Fall back per error type |
| `zip` with `Mono<Void>` | Combinator never runs due to empty source | `then` or `when` |
| `collectList()` on an infinite stream | Unbounded memory | Backpressure + LIMIT/stream |
| Using `boundedElastic` with unbounded demand | Scheduler and DB pool saturation | Bulkhead, concurrency, timeout |
| Manual subscribe inside reactive transaction | Loses associated Context/transaction | Compose one chain |
| Assuming cancellation rolls back payment | External write may already have committed | Idempotency/outbox/job state |
| `doOnError` instead of error recovery | Error still propagates | `onErrorMap`/`onErrorResume` |
| Not closing `toStream()` | Can leak resources | `try-with-resources` if used |
| Fire-and-forget for mandatory tasks | Tasks lost on process crash | Durable queue/outbox |

## 19. Strategy for migrating imperative code to reactive

You do not need to migrate the entire system at once. Follow these steps:

1. **Identify the entry point:** WebFlux controller, imperative listener, scheduled job, CLI, or callback.
2. **Pick a consistent direction:** inbound/reactive services return Mono/Flux; imperative boundaries may block or subscribe with ownership.
3. **Quarantine blocking APIs:** JDBC/JPA, RestTemplate, filesystem, sync SDKs, `Future.get`.
4. **Temporarily offload:** wrap with lazy sources and bounded schedulers; log latency and cap concurrency.
5. **Replace with native reactive APIs where worthwhile:** WebClient, R2DBC, reactive drivers.
6. **Convert sequencing to operators:** `flatMap`, `then`, `when` instead of nested subscribes.
7. **Clarify transactions:** do not split operations out of a transaction.
8. **Unify error contracts:** map root causes accurately; do not mask timeouts/cancellations.
9. **Test correctness before throughput:** completion, errors, cancellation, single subscription.
10. **Real benchmarks:** CPU, memory, request p95/p99, worker/event-loop latency, DB pool, and target SLOs.

If most of the workload remains blocking I/O and complex JPA ORMs, consider keeping Spring MVC + JPA instead of forcing imperative code into WebFlux and calling `block()` everywhere.

## 20. Hands-on exercises

**Exercise 1 – Lazy vs eager.** Using `AtomicInteger`, compare `Mono.just(counter.incrementAndGet())` with `Mono.fromSupplier(counter::incrementAndGet)` before/after subscription.

**Exercise 2 – Fix nested subscribe.** Make `save` succeed while `audit` fails. Prove the old code returns 200; switch to `flatMap/thenReturn` so the error reaches the outer subscriber.

**Exercise 3 – Offload legacy.** Call a synchronous SDK simulated with `Thread.sleep`. Wrap in `fromCallable` and `boundedElastic`, measuring event-loop responsiveness.

**Exercise 4 – Timeout.** Add `timeout` to audit. Observe error/cancel signals and distinguish them from real business rollback.

**Exercise 5 – CompletableFuture.** Write an async API counting how many times it starts. Compare `Mono.fromFuture(api.fetch())` and `Mono.fromFuture(() -> api.fetch())`.

**Exercise 6 – CLI boundary.** In `main`, use `block(Duration)` to fetch one value with a timeout; keep WebFlux controllers non-blocking.

**Exercise 7 – Repeated subscription.** A `Mono.defer` with a counter: subscribe twice and confirm the side effect runs twice. Design idempotency.

**Exercise 8 – Callback adapter.** Use `Mono.create`, fire success/error callbacks, and test unregistering on cancellation.

**Exercise 9 – Transaction Context.** Create two R2DBC operations inside `TransactionalOperator`, then deliberately try a nested subscribe and inspect the difference in rollback behavior.

**Exercise 10 – Concurrency.** Use `Flux.range` and `flatMap(..., 8)` calling the legacy adapter and observe worker/pool usage; compare with unbounded `flatMap` concurrency.

**Exercise 11 – Security Context.** Read a trace ID with `Mono.deferContextual`, switch schedulers, and verify Context still flows through the outer chain; compare with a detached subscription.

**Exercise 12 – HTTP.** Run the section 16 demo, verify 200/404/5xx, and observe that the audit response is only emitted once the operation finishes.

## 21. Production checklist

- [ ] WebFlux controllers/filters never call `.subscribe()` or `.block()` for business work.
- [ ] Every task has a clear subscription owner.
- [ ] Mandatory side effects are composed into the outer chain.
- [ ] Inner operation errors reach the caller or are mapped per policy.
- [ ] Manual subscriptions at boundaries have an error handler, Disposable, and shutdown/cancel handling.
- [ ] Never use `Mono.just(blockingCall())`.
- [ ] Blocking I/O is wrapped in a lazy source and a bounded scheduler.
- [ ] Concurrency/bulkheads, DB pools, and timeouts are bounded.
- [ ] No unnecessary repeated Mono ↔ Future conversions.
- [ ] `Future.get/join`, `toIterable`, and `toStream` never run on the event-loop.
- [ ] Cold publishers with side effects are protected by idempotency.
- [ ] Transaction and security Contexts are not broken by nested subscriptions.
- [ ] Reactive resource cleanup handles completion, errors, and cancellation.
- [ ] Callback adapters unregister when no subscriber remains.
- [ ] Infinite streams are never buffered.
- [ ] Tests verify lazy execution, completion, errors, cancellation, and repeated subscription.
- [ ] Observability covers abandoned tasks, errors, queues, and blocking calls.
- [ ] No PII, tokens, or sensitive stack traces are logged or sent to clients.
- [ ] Durable execution strategies exist for mandatory tasks that must not be lost.
- [ ] WebFlux or MVC architecture is chosen based on real workload and dependencies.

## 22. Official references

1. Reactor Reference – Introduction, assembly, subscribe, backpressure, hot/cold: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
2. Reactor Reference – Subscribe patterns, Disposable, and cancel: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
3. Reactor Reference – Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
4. Reactor Reference – Wrapping Blocking Calls: https://projectreactor.io/docs/core/release/reference/faq.html
5. Reactor Javadoc – `Mono.fromCallable`, `fromFuture`, `toFuture`, `usingWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
6. Spring Framework – WebFlux annotated controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
7. Spring Framework – Reactive WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
8. Spring Framework – Reactive transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
9. Spring Framework – Declarative transaction semantics: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
10. Spring Boot 4.0 – WebFlux and test starter coordinates: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Final self-check:** Why has `Mono.just(jpa.find(...))` already blocked before `subscribeOn`? When `audit().subscribe()` in a controller fails, who receives the error and might HTTP 200 have already been sent? When should `flatMap` be used instead of `map`? Why can `block()` create a new subscription? When does `Mono.fromFuture(() -> ...)` differ from `Mono.fromFuture(future)`? If a client disconnects, which subscription is cancelled? If your answers distinguish ownership, execution, error, cancellation, and transaction boundaries, you have mastered the limits of splitting reactive chains with `subscribe()` or falling back to imperative APIs.
