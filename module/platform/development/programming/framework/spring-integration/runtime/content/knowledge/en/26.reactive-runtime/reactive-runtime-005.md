# Schedulers in Reactive Pipelines

In an integration flow, the same message may be processed by an inbound adapter, channel, transformer, service activator, and then a downstream consumer. With synchronous flows, we usually follow a single Java call stack. With a **reactive pipeline** using Project Reactor, creating `Flux`/`Mono`, calling `subscribe()`, and processing signals can occur at different times or on different threads. Therefore, when debugging issues like "handler did not run," "flow is stalled," or "transaction committed yet downstream hasn't finished," you must identify **which Scheduler is coordinating which piece of work**.

This lesson belongs to the **Reactive runtime** chapter of the **SPRING_INTEGRATION_RUNTIME** module. The goal is to use Reactor `Scheduler` and the `subscribeOn()` and `publishOn()` operators properly in Spring Integration; distinguish them from a poller's `TaskScheduler` and a channel's `TaskExecutor`; and address backpressure, blocking I/O, transactions, retries, error handling, correlation, lifecycle, and performance observability.

> **Principle:** Reactive does not mean "automatically multi-threaded." A `Flux` or `Mono` can run directly on the subscriber's thread; execution location changes only when the source, an operator, or a runtime boundary uses a Scheduler or async API.

## 1. Three Questions to Keep Separate

When looking at a pipeline, answer three questions:

1. **Who triggers execution?** `subscribe()` from a subscriber, an inbound protocol, a reactive consumer, or the framework when an endpoint starts.
2. **Where does the processing stage run?** Caller thread, a Reactor `Scheduler` worker, a Spring Integration `TaskExecutor`, or a thread managed by an asynchronous client.
3. **When is it allowed to emit next?** According to Reactive Streams `request(n)`, capacity/buffers, or the delivery policy of the adapter/channel.

~~~mermaid
flowchart LR
    P["Publisher<br/>Flux / Mono"] --> S["subscribe + request(n)"]
    S --> O1["Upstream operators"]
    O1 --> SCH["publishOn(Scheduler)"]
    SCH --> O2["Downstream operators"]
    O2 --> R["Reactive subscriber / endpoint"]
    R -. "request(n)" .-> P
    S -. "subscribeOn may switch subscription thread" .-> O1
~~~

This diagram only illustrates signal and demand flow: `request(n)` propagates through operators via Reactor's mechanisms, not as a simple direct call from the final consumer to the source as the shorthand arrow suggests.

### Reactor Scheduler vs. Spring TaskScheduler and TaskExecutor

| Component | What is it for? | Examples |
|---|---|---|
| <code>reactor.core.scheduler.Scheduler</code> | Schedules Reactor tasks, dispatches signals via <code>publishOn</code>/<code>subscribeOn</code>, provides clocks for certain operators | <code>Schedulers.parallel()</code>, <code>Schedulers.boundedElastic()</code> |
| <code>org.springframework.scheduling.TaskScheduler</code> | Schedules tasks by time/trigger in Spring | Pollers, scheduled tasks, <code>ThreadPoolTaskScheduler</code> |
| <code>org.springframework.core.task.TaskExecutor</code> | Executes <code>Runnable</code> via an executor mechanism | <code>ExecutorChannel</code>, <code>ThreadPoolTaskExecutor</code> |
| <code>FluxMessageChannel</code> | Channel participating in Reactive Streams and providing <code>Publisher&lt;Message&lt;?&gt;&gt;</code> | Delivers messages to <code>ReactiveStreamsConsumer</code> by demand |

They can be wired together, yet they are **not the same API**. For example, `Schedulers.fromExecutorService(...)` wraps an `ExecutorService` as a Reactor Scheduler, but it does not turn a `TaskScheduler` into a `FluxMessageChannel` or automatically propagate transactions across threads.

## 2. Reactor Does Not Spawn Threads When Building Mono/Flux

Consider the example:

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .map(n -> {
        log.info("map n={}, thread={}", n, Thread.currentThread().getName());
        return n * 10;
    });

// Only here does it subscribe and begin processing.
pipeline.subscribe(result -> log.info("result={}", result));
~~~

Without a scheduling operator, callbacks and `map()` typically run on **the thread calling `subscribe()`**. Declaring the `pipeline` variable neither executes the multiplication nor invokes the source. With a *cold* publisher, each subscription can re-trigger work from the source; with a *hot* source, creation/subscription has different semantics and can emit signals independently of a specific subscriber.

Some operators such as `delayElements()` and `interval()` have their own scheduling mechanisms and sometimes use a default scheduler. Thus, never guess the thread merely from seeing `Flux`: inspect the actual **source**, **operators**, and **thread boundaries**.

## 3. publishOn() and subscribeOn(): Both Switch Threads, Different Scopes

### 3.1. publishOn() Shifts Downstream Signal Processing

`publishOn(scheduler)` switches signals after the operator placement to a worker from the chosen Scheduler. Subsequent downstream operators generally run on that worker until encountering another `publishOn()` or an operator/source that manages its own scheduling.

~~~java
Scheduler downstream = Schedulers.newSingle("order-downstream");

try {
    Flux.just("A", "B")
        .map(s -> {
            log.info("before publishOn: {}", Thread.currentThread().getName());
            return s;
        })
        .publishOn(downstream)
        .map(s -> {
            log.info("after publishOn: {}", Thread.currentThread().getName());
            return s.toLowerCase(Locale.ROOT);
        })
        .blockLast(); // Use only in demos/test boundaries outside reactive workers.
} finally {
    downstream.dispose();
}
~~~

`publishOn()` does not turn each element into an independent parallel task. It normally preserves `onNext` signal order within a subscription on the chosen worker. Nor does the Scheduler name `parallel` mean a single `Flux` with `publishOn(Schedulers.parallel())` automatically fans every element out across multiple cores.

### 3.2. subscribeOn() Switches Subscription Context and Source Work

`subscribeOn(scheduler)` affects the subscribe/request flow toward the source, typically suited for moving a synchronous or blocking source onto another worker:

~~~java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyJdbcRepository.loadCustomer("C-42"))
    .subscribeOn(Schedulers.boundedElastic());

// When a subscriber joins, the callable executes on boundedElastic.
// No JDBC executes when declaring the customer variable.
~~~

Place `subscribeOn()` close to the source being isolated so readers see the boundary clearly. In a chain with multiple `subscribeOn()` calls, stacking them does not give a source multiple independent subscriptions; it usually only introduces unnecessary thread switches. A downstream `publishOn()` can still switch context again.

### 3.3. Example Combining Both Operators

~~~java
Flux<String> flow = Flux.range(1, 3)
    .map(i -> {
        trace("source-map", i);
        return "order-" + i;
    })
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(orderId -> {
        trace("validate", orderId);
        return orderId;
    });
~~~

The `source-map` stage generally runs on a bounded-elastic worker; the `validate` stage after `publishOn` runs on a parallel worker. `trace` is an illustrative application logging helper, not a Spring Integration API.

| Scope | <code>subscribeOn()</code> | <code>publishOn()</code> |
|---|---|---|
| Goal | Shifts subscription/source work to another scheduler | Shifts downstream signals from the operator's position |
| Placement | Usually near the source for clarity | Placed right before the stage needing a context switch |
| Impact on preceding operators | Can affect subscribing/emitting from the source | Does not change the thread of upstream operators that already emitted |
| Multiple times in one chain | Usually adds no benefit; may incur extra thread hops | Each occurrence creates a new boundary |
| Use for blocking legacy sources | Commonly used with <code>Mono.fromCallable(...)</code> + <code>boundedElastic</code> | Can isolate downstream blocking callbacks; ensure upstream doesn't block event-loops |
| Guarantees per-element parallelism? | No | No |

## 4. Choosing a Scheduler Based on Workload Characteristics

Project Reactor provides several Scheduler types; the wrong choice can stall an event loop, hold threads too long, or render backpressure ineffective.

| Scheduler | Suitable for | Should NOT be used for |
|---|---|---|
| <code>Schedulers.immediate()</code> | Running immediately on the current thread without context switch | Isolating blocking I/O |
| <code>Schedulers.single()</code> | Work requiring one sequential, short-lived execution thread | Calling JDBC, slow file I/O, or long blocking HTTP |
| <code>Schedulers.parallel()</code> | Short CPU-bound, non-blocking tasks; worker count typically CPU-based | Calling <code>block()</code> or blocking JDBC |
| <code>Schedulers.boundedElastic()</code> | Wrapping unavoidable blocking I/O and synchronous legacy libraries | Turning a workload "truly non-blocking" or handling unbounded load |
| <code>Schedulers.newBoundedElastic(...)</code> | Creating an isolated bounded pool for a specific integration workload | Creating per message without lifecycle management |
| <code>Schedulers.fromExecutorService(...)</code> | Integrating an already-managed <code>ExecutorService</code> | Assuming every Reactive Streams semantic is preserved automatically |

**`boundedElastic()` is a bounded pool**, including limits on threads and queued tasks. It helps isolate blocking stages from non-blocking threads, yet when the pool fills up, latency rises and task rejections can occur. Starting in Reactor 3.6, it can use Java 21 virtual threads if the runtime and corresponding system properties are enabled; do not assume that in a Java 17 application.

Calling `Mono.block()` or `Flux.blockLast()` on threads belonging to `parallel` or `single` throws `IllegalStateException` by default because those workers are marked non-blocking. Even if `Thread.sleep()` runs on some threads, it still degrades throughput and defeats reactive design goals.

### Quick Selection Rules

- Source is R2DBC, WebClient, or a true reactive driver: **preserve non-blocking APIs**, switching schedulers only when a specific observation/coordination boundary is needed.
- Source is `JdbcTemplate` or a synchronous REST client: use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with bounded concurrency and timeouts.
- Very brief computation: can stay right on the signaling thread; do not add `publishOn` just to "see a different thread."
- CPU-heavy work genuinely needing parallelism: partition bounded work using `flatMap` or Reactor `parallel().runOn(...).sequential()`, evaluating ordering and performance before choosing.

## 5. How Do Reactive Endpoints in Spring Integration Switch Schedulers?

Spring Integration has two related pieces:

1. `FluxMessageChannel` is a `MessageChannel` that simultaneously participates as `Publisher<Message<?>>` and `ReactiveStreamsSubscribableChannel`. Reactive Streams consumers can request messages by demand.
2. `ReactiveStreamsConsumer` is Spring Integration's reactive consumer endpoint, wiring handlers into the subscriber/operator chain.

Since Spring Integration 5.5, `ConsumerEndpointSpec.reactive(...)` lets you turn an endpoint into a reactive consumer **even when the input channel is not a `FluxMessageChannel`**. The callback receives `Flux<Message<?>>` to add operators such as `publishOn`, logging, metrics, or other logic.

### Java DSL Example: Transformer Running on the Parallel Scheduler

Example using Java 17+, Spring Integration 6.x, and Reactor:

~~~java
@Configuration
@EnableIntegration
public class ReactiveNumberFlowConfig {

    @Bean(name = "numbers.input")
    MessageChannel numbersInput() {
        return new DirectChannel();
    }

    @Bean(name = "numbers.output")
    PollableChannel numbersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow numbersFlow() {
        return IntegrationFlow
            .from("numbers.input")
            .transformWith(t -> t
                .<String, Integer>transformer(Integer::parseInt)
                .reactive(flux -> flux.publishOn(Schedulers.parallel())))
            .channel("numbers.output")
            .get();
    }
}
~~~

Key types: `org.springframework.integration.dsl.IntegrationFlow`, `org.springframework.integration.channel.DirectChannel`, `org.springframework.integration.channel.QueueChannel`, `org.springframework.messaging.MessageChannel`, `org.springframework.messaging.PollableChannel`, `org.springframework.integration.config.EnableIntegration`, and `reactor.core.scheduler.Schedulers`.

This shows how to place `publishOn()` **within Spring Integration's reactive endpoint configuration**. Input can be a `DirectChannel`, while the endpoint consumes messages via `ReactiveStreamsConsumer`; processing beyond the boundary runs once the subscription is established and demand permits. Hence, a successful `send()` at ingress is not proof that the transformer and downstream have finished.

Sending a message to observe:

~~~java
Message<String> request = MessageBuilder.withPayload("42").build();
numbersInput.send(request);

// Because of the reactive boundary, the result is awaited on the output channel.
Message<?> result = numbersOutput.receive(5_000);
if (result == null) {
    throw new IllegalStateException("No result within timeout");
}
Integer value = (Integer) result.getPayload(); // 42
~~~

`MessageBuilder` is in `org.springframework.integration.support`. Never call blocking `receive()` inside a non-blocking Reactor worker; waiting as shown above is only appropriate in tests or managed application boundaries.

### What Must NOT Be Inferred from This Example?

- A `DirectChannel` before the endpoint does not make everything after the reactive endpoint a single end-to-end synchronous transaction.
- `Schedulers.parallel()` does not guarantee every message runs on **a different thread**. Dispatching, ordering, and demand depend on the subscription/operators.
- The output `QueueChannel` has polling semantics; it does not turn into a reactive channel.
- `publishOn` does not perform retries, does not convert exceptions into an arbitrary `ErrorMessage` by default, and does not durably persist messages across restarts.

## 6. FluxMessageChannel and Reactive Consumer Backpressure

When you want an entire flow segment to participate in Reactive Streams, you can place `FluxMessageChannel` between compatible endpoints:

~~~java
@Configuration
@EnableIntegration
public class ReactiveOrderChannels {
    @Bean(name = "orders.flux")
    FluxMessageChannel ordersFluxChannel() {
        return new FluxMessageChannel();
    }
}
~~~

`FluxMessageChannel` resides in `org.springframework.integration.channel`. It is neither a `PollableChannel` nor a traditional `SubscribableChannel`; subscribers must follow Reactive Streams. Spring Integration uses `ReactiveStreamsConsumer` as the bridge to message handlers when the input is compatible.

~~~mermaid
flowchart LR
    IN["Reactive source Publisher"] --> FC["FluxMessageChannel"]
    FC --> RC["ReactiveStreamsConsumer"]
    RC --> H["ReactiveMessageHandler"]
    H --> OUT["Mono completion / downstream"]
    RC -. "request(n)" .-> FC
~~~

**Backpressure** means downstream can signal how many elements it is ready to receive. However, an end-to-end guarantee exists only if **every segment involved honors demand**. A callback-based inbound adapter without pause support, an imperative `send()`, a bridge into an imperative channel, or a large buffering operator can consume memory before downstream keeps up.

Example `publishOn(scheduler, 32)` uses the `prefetch` parameter to tune how many elements are staged at the boundary:

~~~java
Flux<Message<?>> tuned = sourceFlux
    .publishOn(Schedulers.parallel(), 32);
~~~

`sourceFlux` is a `Flux<Message<?>>` supplied by upstream. Lowering prefetch can reduce buffering when consumers are slow, though it may add scheduling overhead and cannot fix a source that ignores backpressure. Measure real memory, throughput, and latency instead of tuning to a single magic number.

### Distinguishing Concurrency from Backpressure

| Parameter / technique | Problem it solves | What it does NOT guarantee |
|---|---|---|
| <code>request(n)</code> | Subscriber demand | Every imperative adapter honors demand |
| <code>publishOn(..., prefetch)</code> | Buffering/prefetch at a boundary | Downstream work won't block or lose data |
| <code>flatMap(..., concurrency)</code> | Caps active inner publishers | Output preserves source order |
| <code>concatMap(...)</code> | Serializes inner publishers and preserves order per operator semantics | Max throughput under long I/O loads |
| <code>onBackpressureBuffer(...)</code> | Buffers per policy when upstream emits fast | Unbounded memory or persistence after a crash |

For messages sharing a `correlationId` or business key, excessive concurrency can cause two handlers to update the same group simultaneously. A Reactive Scheduler does not replace `LockRegistry`, transactions, or idempotency.

## 7. Isolating Blocking Code Without Starving Reactive Workers

A common mistake is calling a synchronous JDBC repository or HTTP client directly inside `map()` running on `Schedulers.parallel()`:

~~~java
// AVOID when running on an event-loop / parallel worker:
Flux<Order> unsafe = ordersFlux
    .publishOn(Schedulers.parallel())
    .map(order -> legacyJdbcRepository.save(order));
~~~

`map` waits until JDBC returns; the worker is held for the entire I/O duration. Under high load, scheduler queues or channel backlogs grow.

### Approach 1 — Isolate Each Blocking Source Call

~~~java
Mono<SaveResult> saveBlocking(Order order) {
    return Mono.fromCallable(() -> legacyJdbcRepository.save(order))
        .subscribeOn(Schedulers.boundedElastic());
}

Flux<SaveResult> results = ordersFlux
    .flatMap(this::saveBlocking, 8); // At most 8 active inner publishers.
~~~

This uses `flatMap` to bound concurrency and `subscribeOn` to move JDBC calls to bounded-elastic workers. It **does not make JDBC non-blocking** and does not preserve input order like `concatMap`. The repository is illustrative; `saveBlocking` belongs to the class hosting this processing logic.

### Approach 2 — ReactiveMessageHandler in Spring Integration

Since Spring Integration 6.1, the Java DSL provides `handleReactive(...)` for handlers returning `Mono<Void>`. Example terminal handler running an isolated JDBC operation:

~~~java
@Bean
IntegrationFlow blockingStorageFlow(LegacyOrderService legacyService) {
    return IntegrationFlow.from("orders.flux")
        .handleReactive(message -> Mono
            .fromRunnable(() -> legacyService.store(
                (OrderCommand) message.getPayload()))
            .subscribeOn(Schedulers.boundedElastic())
            .then())
        .get();
}
~~~

`LegacyOrderService` and `OrderCommand` are application-defined types. This is a **terminal** consumer (produces no reply), shown as a standalone example alongside the `orders.flux` channel bean; an actual producer sending `OrderCommand` into the channel is required.

If `legacyService.store(...)` uses `@Transactional` JDBC, it must pass through a Spring proxy and open its transaction **inside the thread executing that call**. An upstream thread's JDBC transaction is not automatically carried across `subscribeOn`.

**Never manually call `subscribe()` inside a handler method to "fire-and-forget" and return success.** That severs the link between publisher completion/error and the endpoint's backpressure/recovery mechanisms. Return `Mono` for framework composition whenever the API supports it.

## 8. A Poller's Scheduler Is Not a Reactor Scheduler by Default

In a standard polling consumer:

~~~text
TaskScheduler
  → runs poller on trigger
  → MessageSource.receive() or QueueChannel.receive()
  → Consumer endpoint
  → handler
~~~

This schedule is triggered by **Spring's `TaskScheduler`**. Do not configure `Schedulers.parallel()` expecting a polling consumer to switch scheduler threads or automatically understand Reactive Streams demand.

Spring Integration has other variants:

- When `SourcePollingChannelAdapter` pushes into a `ReactiveStreamsSubscribableChannel`, the framework can build a reactive pipeline calculating trigger schedules with `Mono.delay()`, polling based on downstream demand rather than scheduling a traditional task-scheduler loop.
- `ReactiveMessageSourceProducer` can wrap `MessageSource.receive()` into a reactive source, using `Schedulers.boundedElastic()` to isolate potential blocking in the source and repeating when the source has no data yet.
- A flow may have *both* a polling boundary *and* a reactive boundary at a later step; inspect both schedulers/thread sources separately.

Therefore, to diagnose "poller not running," check endpoint `isRunning`, triggers, task schedulers, `maxMessagesPerPoll`, output channel subscribers/demand, and source receive capability. Adding `publishOn` downstream will not start an unstarted poller.

## 9. Reactive Transactions Follow Reactor Context, Not ThreadLocal JDBC

In imperative transactions, Spring typically binds transaction state to the thread. `publishOn()`, `subscribeOn()`, and async boundaries can switch execution threads, so never assume a sender's JDBC `@Transactional` survives onto a reactive worker.

Reactive transactions use a `ReactiveTransactionManager` (such as `R2dbcTransactionManager`), binding state to the **subscription's Reactor Context** rather than solely to ThreadLocal. For **genuinely reactive** data operations using the same manager, operators can remain in the transaction even when schedulers switch threads.

Conceptual example using `TransactionalOperator`:

~~~java
@Service
public class ReactiveOrderService {
    private final ReactiveOrderRepository orders;
    private final ReactiveAuditRepository audits;
    private final TransactionalOperator tx;

    public ReactiveOrderService(
            ReactiveOrderRepository orders,
            ReactiveAuditRepository audits,
            ReactiveTransactionManager manager) {
        this.orders = orders;
        this.audits = audits;
        this.tx = TransactionalOperator.create(manager);
    }

    public Mono<Void> saveAndAudit(OrderCommand command) {
        return orders.save(command)
            .flatMap(saved -> audits.record(saved))
            .then()
            .as(tx::transactional);
    }
}
~~~

`ReactiveOrderRepository`/`ReactiveAuditRepository` are illustrative interfaces with methods returning reactive publishers. `TransactionalOperator` is in `org.springframework.transaction.reactive`, and `ReactiveTransactionManager` is in `org.springframework.transaction`. The example assumes both repositories work with the same reactive transaction manager.

Conditions required to claim the transaction protects both save and audit:

1. Both operations share the same reactive transaction manager and transaction-capable resources.
2. The publisher is **subscribed**, with no detached manual `subscribe()` in the middle.
3. Downstream exceptions remain in the pipeline and lead to terminal `onError`, rather than being accidentally converted to success.
4. No blocking JDBC is dropped into the middle expecting the reactive transaction manager to manage it.

`Reactor Context` differs from `MessageHeaders`: correlation IDs travel in headers per the messaging contract; subscription/transaction metadata lives in the reactive context. ThreadLocal logging MDC does not automatically follow every `publishOn` or library: proper context propagation mechanisms are required rather than relying on thread names.

## 10. Error Handling and Retries Along Reactive Signals

In a Reactor pipeline, an unhandled exception typically becomes a **terminal `onError` signal ending the subscription**. When a step fails, never assume every exception automatically appears on Spring Integration's global `errorChannel`: that depends on endpoint type, how the publisher is subscribed, adapters, and `ErrorMessage` publishing configuration.

~~~java
Mono<SaveResult> operation = Mono.defer(() -> reactiveClient.save(order))
    .doOnError(ex -> log.warn("Save failed", ex))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientFailure))
    .timeout(Duration.ofSeconds(5));
~~~

`reactiveClient`, `order`, and `isTransientFailure` are illustrative components. `Retry` is in `reactor.util.retry`. Three **additional** retries follow the first attempt if the policy allows; `timeout` is the reactive deadline of the enclosed segment, not a guarantee that any underlying blocking task is canceled.

### Operators with Very Different Impacts

| Operator | Behavior | Risk if misused |
|---|---|---|
| <code>doOnError(...)</code> | Observes the error without swallowing it | Mistaking it for recovery |
| <code>onErrorResume(...)</code> | Replaces the error branch with a fallback publisher | Turning failure into a success signal, misleading upstream/ACK |
| <code>onErrorMap(...)</code> | Transforms the exception into another type | Losing root cause or message context if wrapped poorly |
| <code>retryWhen(...)</code> | Resubscribes to the enclosed upstream | Re-executing side effects if idempotency is missing |
| <code>timeout(...)</code> | Emits an error if no progress occurs in time | Already-started blocking/remote work may still finish after timeout |
| <code>doFinally(...)</code> | Observes completion, error, or cancellation | Does not send to DLQ or complete external transactions on its own |

**Specifically:** placing `retry()` outside a multi-message publisher can resubscribe **the entire source**, not just the last failed message. With hot sources, brokers, or side effects, understand source semantics and scope retries per message where appropriate.

A `ReactiveMessageHandler` returning `Mono<Void>` gives the framework visibility into completion/error. Conversely:

~~~java
// AVOID: subsequent errors are detached from the current invocation.
public void unsafe(Message<?> message) {
    reactiveClient.send(message).subscribe();
}
~~~

This snippet is not a complete handler; it illustrates the manual-subscribe anti-pattern. When recovery is required, identify the owner: Reactor operator, Spring Integration reactive endpoint, broker inbound adapter, or a dedicated error flow. Only ACK when results satisfy the processing contract, not merely because a subscription *started*.

## 11. Backpressure, Concurrency, and Message Ordering

A `Flux<Message<?>>` can process multiple messages concurrently when using `flatMap` with inner publishers that do not complete immediately:

~~~java
Flux<Receipt> receipts = incomingMessages
    .flatMap(message -> reactiveOrderService.process(
        (OrderCommand) message.getPayload()), 16);
~~~

Here `incomingMessages` is a `Flux<Message<?>>`, and `process()` returns `Mono<Receipt>`. The limit `16` is the maximum concurrency of active inner publishers, not "16 fixed threads." Results may finish **out of input order**.

For business logic requiring ordering per account/order key, you can:

- use `concatMap()` for a serialized stream, trading off throughput;
- route/partition by key and serialize processing within each partition;
- apply appropriate locking/idempotency for group correlation, without treating locks as an arrival-order guarantee.

Do not set `parallel()` or `flatMap` concurrency higher than DB/broker capacity. A well-backpressured publisher can still open too many I/O requests if inner concurrency is unbounded.

## 12. Lifecycle and Managing Schedulers in Applications

Factories like `Schedulers.parallel()` and `Schedulers.boundedElastic()` generally return shared schedulers. Meanwhile, `Schedulers.newSingle(...)`, `newParallel(...)`, and `newBoundedElastic(...)` create dedicated instances that should be disposed when the application stops using them.

Example provisioning a dedicated Scheduler for legacy I/O with Spring managing its lifecycle:

~~~java
@Configuration
public class ReactorSchedulerConfig {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        // Max 8 workers; allows up to 200 queued tasks per backing thread.
        return Schedulers.newBoundedElastic(8, 200, "legacy-io");
    }
}
~~~

This bean can be injected into `Mono.fromCallable(...).subscribeOn(legacyIoScheduler)`. Never create a new Scheduler **per message**, as that leaks threads/queues and complicates shutdown. Never dispose shared `Schedulers.parallel()` or `Schedulers.boundedElastic()` just because one flow stops; other flows may still be using them.

Spring Integration endpoints/flows have their own start/stop lifecycles. Stopping an endpoint can cancel framework-managed subscriptions, yet **does not mean every task already handed to a Scheduler or every in-flight HTTP request halts instantaneously**. With dynamically registered `IntegrationFlow`s or `toReactivePublisher(autoStartOnSubscribe)`, verify clearly who owns the subscription and who stops the flow upon cancellation/termination.

## 13. Observing Threading and Diagnosing Performance

To trace where a message is executing, log at minimum: correlation ID, endpoint/channel name, thread name, upstream request ID, retry count, latency, subscribe/cancel/error outcomes, and queue depth when available. Never log full sensitive payloads.

~~~java
Flux<Message<?>> observed = inputFlux
    .doOnSubscribe(s -> log.debug("reactive subscribed"))
    .doOnNext(message -> log.debug(
        "messageId={}, correlationId={}, thread={}",
        message.getHeaders().getId(),
        message.getHeaders().get("correlationId"),
        Thread.currentThread().getName()))
    .doOnError(ex -> log.error("reactive failure", ex))
    .doFinally(signal -> log.debug("terminated={}", signal));
~~~

This is an illustrative instrumentation snippet, not a replacement for Micrometer/Observation. An error or cancellation is a subscription terminal signal; metrics counting only `onNext` may miss failures when converters/sources fail before emitting a message.

| Symptom | Possible cause | What to check |
|---|---|---|
| `send()` returns yet no output appears | Reactive endpoint hasn't finished, no demand, or downstream failed | Subscriptions, output channel, consumer lifecycle, `onError` |
| CPU spikes while throughput stays low | Excessive thread switches, poor `flatMap` concurrency | Profiling, scheduler queues, number of `publishOn`s, CPU |
| `parallel` workers held too long | Blocking JDBC/HTTP, `Thread.sleep`, `block()` | Thread dumps, BlockHound if configured, handler logs |
| `boundedElastic` overloaded | Too many blocking calls, growing task queue | Wait times, thread cap, timeouts, downstream capacity |
| Lost transaction after `publishOn` | Relying on upstream thread-bound JDBC transaction | Transaction manager, thread boundaries, reactive tx scope |
| Messages reprocessed | `retryWhen`, resubscription, broker redelivery | Retry placement, message IDs, idempotency keys, and ACK |
| Correlation missing in logs | MDC/ThreadLocal not propagated | Reactor Context, context-propagation, correlation headers |
| Test hangs indefinitely | Missing subscribe, zero demand, disposed scheduler, or blocking call | StepVerifier, scheduler ownership, endpoint startup |

### Quick Inspection Checklist

1. Verify the publisher has a **subscriber** and the endpoint is running; without a subscription, a cold pipeline does no work.
2. Map boundaries of `publishOn`, `subscribeOn`, executors/channels, and any self-scheduling operators.
3. Classify blocking vs. non-blocking stages; hunt for `block()`, `Thread.sleep()`, JDBC, and sync clients.
4. Inspect demand/backpressure, `flatMap` concurrency, queue depths, and scheduler wait times.
5. Check `onError` paths, recovery, retries, timeouts, and ACK/redelivery decisions.
6. Confirm whether transactions are thread-bound JDBC or Reactor Context; check correlation across thread hops.
7. Verify start/stop lifecycles, cancellation, and ownership of custom Schedulers.

## 14. Testing Schedulers and Reactive Pipelines

### 14.1. Verifying publishOn() Actually Switches Threads

~~~java
@Test
void publishOnRunsDownstreamOnDedicatedWorker() {
    Scheduler worker = Schedulers.newSingle("downstream-test");
    try {
        Mono<String> publisher = Mono.just("42")
            .publishOn(worker)
            .map(value -> Thread.currentThread().getName());

        StepVerifier.create(publisher)
            .expectNextMatches(name -> name.startsWith("downstream-test"))
            .verifyComplete();
    } finally {
        worker.dispose();
    }
}
~~~

`StepVerifier` belongs to `reactor.test`. This test only verifies the **execution context** of an operator; it does not prove correctness of transactions or backpressure across an entire Spring Integration flow.

### 14.2. Testing Time-Based Operators with Virtual Time

~~~java
@Test
void timeBasedFlowUsesVirtualTime() {
    StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
}
~~~

`withVirtualTime()` swaps the clock of compatible time-based operators so tests do not wait a real hour. The publisher must be **created inside the supplier**, after the virtual scheduler is installed; a pre-injected custom Scheduler may not be replaced by virtual time. Virtual time does not virtualize blocking JDBC/HTTP or replace transaction/restart integration tests.

### 14.3. Testing Spring Integration Endpoints with Real Timeouts

For Section 5's `numbersFlow`:

~~~java
@Test
void reactiveTransformerPublishesParsedNumber() {
    numbersInput.send(MessageBuilder.withPayload("21").build());

    Message<?> result = numbersOutput.receive(5_000);
    assertNotNull(result);
    assertEquals(21, result.getPayload());
}
~~~

`numbersInput` and `numbersOutput` are injected from their respective beans. Also test: malformed JSON/numbers triggering `onError`, demand with no subscriber, stopping the endpoint mid-processing, scheduler saturation, timeouts/cancellation, and duplicate-inducing retries. Never call `receive()` inside a non-blocking Reactor worker.

## 15. Checklist Before Taking Schedulers to Production

- [ ] Identify clearly which source creates the subscription and which endpoint receives `request(n)`.
- [ ] Distinguish Reactor `Scheduler` from poller `TaskScheduler` and channel `TaskExecutor`.
- [ ] Use `publishOn`/`subscribeOn` only at intentional boundaries; know which operators run before/after.
- [ ] Never block `parallel`, `single`, or event loops; isolate legacy blocking calls on bounded `boundedElastic`.
- [ ] Control `flatMap` concurrency, prefetch, buffering, throughput, ordering, and whether sources truly support backpressure.
- [ ] Keep reactive transactions in subscription/Reactor Context; never rely on JDBC ThreadLocal across schedulers.
- [ ] Define `onError`, retry/resubscribe, timeout/cancel, error channel, and ACK/redelivery behavior explicitly.
- [ ] Enforce correlation/idempotency when messages sharing a key execute concurrently or retry.
- [ ] Manage `dispose()` for custom Schedulers, flow lifecycles, and in-flight tasks on shutdown.
- [ ] Test with StepVerifier, virtual time, endpoint integration, load, and failure injection; monitor p95/p99 latency alongside queue/scheduler saturation.

**Conclusion:** Schedulers govern **when and on which thread** reactive steps run, but they do not automatically solve transactions, retries, backpressure, or message durability. In Spring Integration, examine Reactor `publishOn`/`subscribeOn`, `FluxMessageChannel`/`ReactiveStreamsConsumer`, and traditional poller/executor boundaries together. Placing schedulers intentionally, avoiding blocking on unsuitable workers, and keeping completion/errors inside the reactive composition makes message flows easier to diagnose and operate.

## References

- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html)
- [Spring Integration Reference — Reactive Endpoint in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-reactive.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Project Reactor Reference — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor Reference — Testing (StepVerifier and Virtual Time)](https://projectreactor.io/docs/core/release/reference/testing.html)
