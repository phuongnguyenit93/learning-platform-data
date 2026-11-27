# Endpoint Advice Chain in Spring Integration

In Spring Integration, an **endpoint** connects a message channel to its processing logic: receiving a message, invoking a handler, and then forwarding the result or error to the next step. Beyond business logic, we often need retries, timing measurements, duplicate checks, transactions, or alerting. Putting all of these mechanisms inside the handler forces every use case to handle message runtime details itself and makes it hard to maintain consistent behavior.

An **advice chain** is a sequence of components wrapping an invocation to add behavior before, after, or when the call throws an exception. This lesson belongs to the **Advice chain** chapter of **SPRING_INTEGRATION_RUNTIME**, where Spring Integration orchestrates message flows across channels, consumer endpoints, pollers, and executors, while managing lifecycle, transactions, retries, message stores, error flows, and correlation. The goal is to know where advice is attached, which section of processing it wraps, and the consequences of advice ordering.

> **Key point:** Advice attached to a *handler invocation* and advice attached to a *poller task* have different scopes. Both are often called "endpoint advice," but they are not interchangeable.

## 1. How does an advice chain work?

Imagine a handler whose job is `process(OrderCommand)`, wrapped by two advice instances A and B:

~~~text
MessageChannel
    │
    ▼
Consumer endpoint
    │
    ▼
Advice A: before invocation
    │
    ▼
Advice B: before invocation
    │
    ▼
Handler: process message
    │
    ▼
Advice B: handle result / exception
    │
    ▼
Advice A: handle result / exception
    │
    ▼
Reply or forward to next flow
~~~

This is an **around invocation** pattern: the call enters the chain in the configured order and exits in the reverse order, provided each advice proceeds to the callback. If an advice does not proceed, returns an alternative result, or throws an exception, the handler or inner advice may not execute.

For example, when a timing advice wraps outside a retry advice:

~~~mermaid
sequenceDiagram
    participant C as Consumer endpoint
    participant T as Timing advice
    participant R as Retry advice
    participant H as Business handler
    C->>T: invoke(message)
    T->>R: proceed()
    R->>H: attempt 1
    H--xR: transient exception
    R->>H: attempt 2
    H-->>R: success
    R-->>T: success
    T-->>C: result
    Note over T,R: Outer timing measures both wait time and retry attempts
~~~

If you reverse the order so that timing sits **inside** retry, the number of measurements can equal the number of attempts, with each measurement wrapping only a single handler invocation. Therefore, advice ordering is part of observable business behavior, not merely a matter of configuration style.

## 2. Types of advice to distinguish

| Mechanism | Scope | When to use? |
|---|---|---|
| **Request handler advice** (e.g., <code>RequestHandlerRetryAdvice</code>) | Wraps request processing of a message handler that supports the corresponding advice mechanism | Retries, evaluating results/errors, controlling handler execution |
| **Poller advice** | Wraps the polling task, which may include receiving a message and then processing it | Transactions at the receive/process boundary, poll schedule throttling, polling task management |
| **AOP advice on a Spring service** | Wraps a bean method invocation through a Spring proxy | Business transactions, security, metrics, or shared application service logic |
| **Channel interceptor** | Intercepts before/after send/receive operations on a channel | Traffic observation, adding/inspecting headers, and channel policies |
| **Error handler/error flow** | Receives exceptions or <code>ErrorMessage</code> from runtime boundaries with error-reporting support | Logging, alerting, quarantine, recovery, and asynchronous error handling |

Three points to remember:

1. Spring AOP `Advice` is a general concept, but **the ability to attach advice depends on the endpoint type and the API the handler supports**. Not all endpoints use the same interception point.
2. Spring Integration's `AbstractRequestHandlerAdvice` targets request handling at suitable message handlers. A custom advice that needs to wrap the entire `handleMessage()` call may have to use the `HandleMessageAdvice` mechanism or an interceptor configuration supported by the endpoint, rather than assuming every request handler advice covers every step.
3. Advice does not automatically move between sender and worker threads. Where the advice is placed determines which thread executes it, which exceptions it sees, and which transaction it can participate in.

### How does an "endpoint" differ from a "handler"?

A consumer endpoint, such as `EventDrivenConsumer` or `PollingConsumer`, is responsible for subscribing to a channel or actively polling. The message handler behind it performs the actual message processing. In Java DSL, the operation:

~~~java
.handle(orderService, "process", e -> e.advice(retryAdvice))
~~~

attaches advice via the endpoint/handler configuration that the DSL supports for handler invocation. You should not infer that this advice automatically wraps receiving the message from a queue, the polling scheduler, upstream transformations, or broker ACK operations.

## 3. Practical example: retry advice around a Service Activator

Suppose a system receives order commands; a transient database error should be retried with a limit, while invalid business data should not be retried. The service accepts a plain Java command without depending on Spring Integration APIs.

**Step 1 — build the use case:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

public interface OrderStore {
    // Requires appropriate constraints/transactions to avoid duplicate writes by orderId.
    void saveIdempotently(OrderCommand order);
}

@Service
public class OrderService {
    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    @Transactional
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }
        store.saveIdempotently(command);
    }
}
~~~

`OrderStore` is an illustrative storage port; the application must provide a real implementation. `@Transactional` takes effect when `OrderService` is called through a Spring proxy and an appropriate transaction manager is configured.

**Step 2 — configure `RequestHandlerRetryAdvice` and an endpoint using Java DSL:**

~~~java
@Configuration
@EnableIntegration
public class OrderIntegrationConfig {

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    RequestHandlerRetryAdvice orderRetryAdvice() {
        RetryTemplate template = new RetryTemplate();

        // Maximum 3 attempts, including the initial call.
        template.setRetryPolicy(new SimpleRetryPolicy(3));

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(250);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow orderFlow(
            OrderService service,
            @Qualifier("orderRetryAdvice")
            RequestHandlerRetryAdvice retryAdvice) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process", e -> e.advice(retryAdvice))
            .get();
    }
}
~~~

Key types: `org.springframework.integration.dsl.IntegrationFlow`, `org.springframework.integration.handler.advice.RequestHandlerRetryAdvice`, `org.springframework.integration.channel.DirectChannel`, `org.springframework.integration.config.EnableIntegration`, `org.springframework.messaging.MessageChannel`; `org.springframework.retry.support.RetryTemplate`, `org.springframework.retry.policy.SimpleRetryPolicy`, `org.springframework.retry.backoff.FixedBackOffPolicy`. A Spring Retry dependency compatible with the application version is required.

**Step 3 — send a message to the endpoint:**

~~~java
OrderCommand command = new OrderCommand("O-104", 2);
Message<OrderCommand> request = MessageBuilder.withPayload(command)
    .setHeader("correlationId", "trace-O-104")
    .build();

ordersInput.send(request);
~~~

Here `ordersInput` is the `orders.input` bean. `MessageBuilder` belongs to `org.springframework.integration.support`. With `DirectChannel`, the consumer executes on the thread of the `send()` call; when the handler fails and the advice retries, that same thread must wait for all attempts.

**Note on the example code:** `SimpleRetryPolicy(3)` above is a basic setup to clearly demonstrate the retry mechanism, **not a production policy**: it can retry exceptions that should not be retried, such as `IllegalArgumentException`. In a real system, you need to classify transient/permanent errors and bound backoff, processing time, and overload risk according to your latency budget.

### Call flow in the example

~~~mermaid
flowchart LR
    IN["orders.input<br/>DirectChannel"] --> EP["Service activator endpoint"]
    EP --> RA["RequestHandlerRetryAdvice"]
    RA --> SV["OrderService.process"]
    SV --> DB["OrderStore"]
    SV -. "exception" .-> RA
    RA -. "retry if policy allows" .-> SV
    RA -. "exhausted: propagate/recover" .-> EX["Caller or error flow depending on runtime"]
~~~

The retry advice wraps the invocation of `process()`. It does not guarantee that processing before the endpoint (such as a JSON-parsing transformer) will be re-executed. If conversion fails in an upstream transformer, advice placed on `process()` may never be invoked at all.

## 4. Ordering multiple advice and side effects

Suppose two advice instances `metricsAdvice` and `retryAdvice` are both supported by the endpoint:

~~~java
.handle(service, "process",
    e -> e.advice(metricsAdvice, retryAdvice))
~~~

In a chain executing in declaration order, the first advice wraps outside the subsequent advice:

~~~text
metricsAdvice.enter
  retryAdvice.enter
    process attempt #1 -> failure
    process attempt #2 -> success
  retryAdvice.exit
metricsAdvice.exit
~~~

Metrics outside retry count **one** processed message, and the measured duration includes backoff and all attempts. Reversing the order of the two advice changes what is observed (each attempt versus the entire logical request). If an advice can short-circuit, inner invocations might not happen at all.

The same applies to idempotent receivers, circuit breakers, or recovery advice:

- **Idempotency check before retry:** blocks an already-succeeded message up front; however, the "in-progress" state and when the key is recorded must be designed carefully.
- **Retry inside idempotency:** a single logical request may try multiple times; you must ensure retries do not write duplicate data or emit duplicate events.
- **Recovery before or after observation advice:** determines whether the final failure is seen as an exception or converted into a recovered result.

There is no "best order" independent of your goal. When choosing, sketch the **before / proceed / after / catch** flow for each advice and explicitly specify which cases count as success.

## 5. Poller advice vs. handler advice

With a `SubscribableChannel` (such as `DirectChannel`), the consumer receives messages when the sender sends them. With a `PollableChannel` (such as `QueueChannel`), the polling consumer actively calls `receive()` on a schedule.

~~~mermaid
flowchart TD
    Q["QueueChannel / polling source"]
    POL["Poller task"]
    RX["receive()"]
    H["Handler"]
    ADV1["Poller advice<br/>wraps polling task"]
    ADV2["Handler advice<br/>wraps invocation"]
    Q --> RX
    ADV1 --> POL
    POL --> RX
    RX --> ADV2
    ADV2 --> H
~~~

**Poller advice** is typically used when you need to wrap the receive-and-process cycle, for example when you want a poller-managed transaction to cover both `receive()` and message processing. **Handler advice** wraps the configured handler, such as retrying a query or service call. A handler advice cannot roll back a message receive operation that already committed in an independent transaction.

Annotation example for a polling consumer (assuming beans `orders.queue` and `pollerTxAdvice` are already defined):

~~~java
@ServiceActivator(
    inputChannel = "orders.queue",
    poller = @Poller(
        fixedDelay = "1000",
        adviceChain = "pollerTxAdvice"
    )
)
public void consume(OrderCommand command) {
    orderService.process(command);
}
~~~

`@Poller` belongs to `org.springframework.integration.annotation`. `pollerTxAdvice` can be a transaction advice created with Spring Transaction and a suitable transaction manager. The example illustrates the advice **attachment point** and does not declare the full set of beans, store, or transaction manager.

| Question | Handler advice | Poller advice |
|---|---|---|
| Wraps handler invocation? | Yes, at the configured interceptor point | Can cover it when the handler runs inside the poll task |
| Wraps <code>receive()</code>? | Usually no | Possible, depending on the advice/transaction configuration |
| Suitable for <code>DirectChannel</code>? | Yes, for supported handlers | No polling task to intercept |
| Suitable when pulling messages from a queue? | Handler-specific retry logic | Controls behavior across the full receive/process cycle |
| Affects ACK/redelivery? | Indirectly if an exception propagates | Depends on the source's transaction, message store, and adapter |

Note: Handler-level retry logic re-executes processing on the **same received message**, whereas broker or message store redelivery is a different mechanism: the source delivers the message back to the consumer. You should not treat these two mechanisms as equivalent.

## 6. Transactions and retries: getting the order right

Suppose you have a retry advice and a transaction advice. Two configurations look similar but have different consequences:

### A. Retry wrapping outside a service transaction

~~~text
RetryAdvice
  ├─ attempt 1
  │    └─ @Transactional OrderService -> rollback on error
  ├─ attempt 2
  │    └─ @Transactional OrderService -> rollback on error
  └─ attempt 3
       └─ @Transactional OrderService -> commit on success
~~~

This model is usually appropriate when you want **each attempt to have a fresh transaction**, provided there is no outer transaction already wrapping the entire chain and the service call goes through a Spring proxy. `@Transactional` defaults to `REQUIRED` propagation, so if the caller already has an active transaction, it may join that transaction instead of creating a new one.

### B. Transaction wrapping outside retry

~~~text
PollerTransactionAdvice
  └─ RetryAdvice
       ├─ attempt 1 -> failure
       ├─ attempt 2 -> failure
       └─ attempt 3 -> success
  └─ commit / rollback for the entire poll task
~~~

All attempts may run inside the same transaction. An exception on the first attempt can cause the transaction to be marked rollback-only; even if a later attempt succeeds, the final commit can still fail. With databases, JPA persistence contexts, locks, and transaction timeouts, retrying inside the same transaction can produce confusing secondary errors.

**How to decide:** Determine what the transaction needs to cover: only the service's data changes, or also pulling the message from a transactional channel/source. If you need to retry an entire transaction, use an advice structure and propagation that ensures **each attempt genuinely gets a new transaction**. If you need message consumption and database updates to be atomic, examine the transactional semantics of the message source/broker and transaction manager; advice does not create a distributed transaction on its own.

### Note on idempotency and side effects

Retries can execute a service multiple times. An attempt that fails **after** sending an email, calling a payment API, or emitting an event can leave external side effects even if the database rolls back. Use a business idempotency key, unique constraint, inbox/outbox pattern, or appropriate compensating mechanism. `MessageHeaders.ID` and correlation IDs are not automatically stable idempotency keys.

## 7. Exceptions, recovery, and error channels

An advice can **observe**, **retry**, **transform**, or **swallow** an exception. Document the policy explicitly so operators are not misled:

| Outcome after chain | What the outer handler/endpoint sees | Runtime impact |
|---|---|---|
| Handler succeeds immediately | Normal result | Flow continues |
| Handler fails then retry succeeds | Success result after multiple attempts | Metrics/logs should record that retries occurred |
| Retries exhausted, advice rethrows exception | Exception propagates to caller/consumer boundary | Synchronous flows may report the error directly; async/poller flows handle it via the error handler |
| Recovery callback returns a result/fallback | Endpoint may see a recovered result | Does not automatically trigger rollback/redelivery; distinguish "recovered" from "business processed" |
| Advice swallows exception and returns <code>null</code> / success status | Outer layer may not know about the failure | May result in ACK/removing the message without desired recovery |

`RequestHandlerRetryAdvice` can be configured with a recovery callback; with an appropriate strategy, the application can use `ErrorMessageSendingRecoverer` to send the error once retries are exhausted. However, if the exception also continues to propagate to the scheduler error handler or adapter recovery, **two error-reporting paths** may occur for a single message. You must clearly designate which component is responsible for publishing the final error.

At runtime:

- With `DirectChannel`, an unhandled exception in the handler normally propagates back to the sender along the call stack; Spring Messaging may wrap it in a `MessagingException`.
- With `ExecutorChannel` or an executor-backed subscriber, processing runs on another thread; check the actual error-handling mechanism of the channel/dispatcher and configured error channel.
- With a poller, exceptions in the task can be converted into an `ErrorMessage` by the task scheduler/error handler. `MessagePublishingErrorHandler` is a common component in this mechanism.
- With a broker inbound adapter, ACK, requeue, dead-lettering, and deserialization errors may be decided by the listener/container; handler advice in Spring Integration does not automatically cover steps prior to message creation.

Error channels, retry advice, and dead-letter queues are **distinct** components. Sending an `ErrorMessage` does not mean the source message will automatically be retried or durably persisted.

## 8. Threading, pollers, and performance

Advice executes at the boundary where it is attached:

| Topology | Thread running handler advice | Operational risk |
|---|---|---|
| Sender → <code>DirectChannel</code> → handler | Sender thread | Retries/backoff lengthen <code>send()</code> duration and can cause gateway timeouts |
| Sender → <code>ExecutorChannel</code> → handler | Usually a worker thread | Retries hold workers longer; thread pools/queues can saturate |
| <code>QueueChannel</code> → poller → handler | Poller/scheduler thread or configured thread | Retries stretch a poll cycle, lowering consumption rate and increasing queue depth |
| External adapter → integration channel | Depends on adapter and channel dispatch threads | Can hold listener threads, affecting ACK and throughput |

**Synchronous backoff** in retries typically blocks the thread while waiting. If there are 20 workers and each message retries multiple times with long delays, throughput drops even if the actual service logic takes only a few milliseconds. Calculate your time budget:

~~~text
Total time ≈ Σ execution time per attempt
           + Σ backoff intervals
           + endpoint/channel overhead
~~~

Illustrative example: three attempts, each taking around 100 ms with two 250 ms waits, total around 800 ms (excluding overhead). This is only an illustrative calculation, not a latency guarantee. With a request–reply gateway, check timeouts on the gateway, output channel, thread pool, and upstream client to avoid the caller timing out while the worker continues executing side effects.

Choosing a retry policy by exception type reduces wasted retries and preserves resources for messages that have a chance to recover. Useful metrics include: retry/attempt count, duration around the handler, wait time, exhausted failures, queue depth, active thread count, rejected tasks, timeout rate, and endpoint `isRunning` status.

## 9. How does flow lifecycle affect advice?

Spring Integration can manage endpoints via `SmartLifecycle` and dynamically registered flows via `IntegrationFlowContext`. The advice chain is attached when the endpoint/handler is constructed and initialized; starting/stopping an endpoint does not mean the advice automatically cleans up tasks currently retrying.

- **Start:** the endpoint can receive/poll messages and advice is applied to invocations within its configured scope.
- **Stop:** stops new receives/polls depending on the endpoint, but work already handed to an executor or currently in backoff may keep running; graceful shutdown and tracking of in-flight work are required.
- **Changing chain configuration:** usually requires changing the bean/endpoint configuration or re-registering the flow appropriately. Do not assume mutating an arbitrary advice list at runtime is safe.
- **Application restart:** in-memory state of retry counters or duplicate detectors can be lost; if you need to preserve processing history, use an appropriate persistent store.

An advice chain is not a "flow-wide orchestrator." An advice placed on handler A will not automatically apply to downstream handler B unless it is also attached to B or sits at a broader scope by design.

## 10. Testing advice chains

You should test **observable behavior** rather than merely checking that beans exist.

| Scenario | Expected outcome |
|---|---|
| Handler succeeds on first try | Single service call, no backoff |
| Transient error on first two tries, third succeeds | Three invocations; final side effect happens exactly once per contract |
| Permanent error | Policy does not retry or stops at the exact limit; caller/error flow receives the error |
| Two advice attached together | Correct enter/exit order; metrics outside retry measure total, metrics inside retry measure each attempt |
| Retry ends with recovery | Appropriate result and error message; never both ACKs success and loses data |
| Poller with transaction advice | Transaction boundaries of <code>receive</code>/<code>handle</code> match design and rollback can re-deliver the message if the source supports it |
| Handler runs on executor | Error routing observed on worker thread; caller does not rely on exceptions from <code>send()</code> |
| Stop endpoint during retry | Reasonable handling for in-flight work and incomplete data |

**Conceptual unit test example**: a fake `OrderStore` throws a transient error twice and then succeeds; send a message through `orders.input` in a Spring context; verify the store was called three times, the message produced the expected outcome, and no duplicate records exist. Test the invalid-quantity case separately to verify the retry policy does not repeat a guaranteed failure. Use a spy/mock or counter at the store boundary, and avoid testing by sleeping a fixed duration and inferring the error was handled.

For transaction tests, use a database/test store with real semantics rather than just mocking `@Transactional`. For asynchronous flows, wait on a condition with a timeout (latch/queue or polling assertion utility) rather than asserting immediately after calling `send()`.

## 11. Common pitfalls and how to fix them

| Symptom | Common cause | How to fix |
|---|---|---|
| Handler is not retried | Advice attached to a different endpoint or error occurs before the target handler | Identify which endpoint actually throws the error; attach advice at the right spot |
| Same message processed twice | Retry/redelivery, non-idempotent side effects | Unique keys, inbox/outbox, control recovery and transactions |
| Transaction rolls back even when final retry succeeds | Retry executes inside a transaction already marked rollback-only | Redesign retry/transaction order and propagation |
| Caller does not see exception | Handler runs on an executor or advice recovered/swallowed the error | Inspect thread boundaries and the <code>ErrorMessage</code> path |
| Queue grows when database slows down | Retries hold worker/poller threads too long | Bound attempts/backoff, protect pools, consider scheduled retry mechanisms |
| Metrics count one message as multiple requests | Metrics advice sits inside retry | Place metrics according to the unit measured: logical message vs. attempt |
| Cannot roll back message pulled from queue | Queue/message store is non-transactional or receive already committed | Review source transaction support and redelivery mechanism |
| Flow stopped but processing logs still appear | Task already started/dispatched before stop | Monitor in-flight tasks and shutdown behavior |
| Error channel does not receive errors | Error handled inside advice, or synchronous flow throws to caller | Clarify error/recovery ownership and test each path |

## 12. Production readiness checklist

1. Identify whether advice is attached at the **handler**, **poller**, or **Spring service proxy**; describe the exact invocation segment it wraps.
2. Specify the enter/exit order of every advice; define when an advice retries, returns, short-circuits, recovers, or rethrows an exception.
3. Classify transient vs. permanent errors, bound retries and backoff; align the time budget with gateway, poller, and executor timeouts.
4. Define transaction boundaries for each attempt and receive/ACK operation; test against a real data source/message store.
5. Ensure side effects have an idempotency key or deduplication mechanism, especially under broker redelivery and retries.
6. Observe correlation, endpoint/thread, attempt count, latency, error count, and queue depth; do not log sensitive data.
7. Establish clear ownership for recovery/error channel/DLQ; test both when advice swallows errors and when error publishing fails.
8. Verify start/stop lifecycle, executor shutdown, and behavior when the system restarts mid-retry.

**Conclusion:** Advice chains let you add runtime policies around consumer endpoints without forcing business services to depend on message flow details. To use them correctly, you must clearly understand **where advice is attached**, **the order wrapping the invocation**, **transaction and thread boundaries**, and **retry/recovery policies**. These decisions govern where errors go, whether a message can be reprocessed, and how the system maintains throughput.

## References

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
- [Spring Integration Javadoc](https://docs.spring.io/spring-integration/api/)
- [Spring Retry Reference](https://docs.spring.io/spring-retry/reference/)
