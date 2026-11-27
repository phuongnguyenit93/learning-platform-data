# MessagePublishingErrorHandler in Spring Integration

An integration flow typically spans multiple execution boundaries: a sender pushes a message into a channel, an endpoint receives the message, a handler invokes business logic, a poller pulls messages from a queue, and an executor shifts work to another thread. When the handler runs **on a different thread from the sender**, an exception cannot automatically return to the original send call via normal exception propagation. Spring Integration addresses part of this problem by publishing errors as messages.

**<code>MessagePublishingErrorHandler</code>** is the centerpiece of that mechanism: it receives a <code>Throwable</code> from task-execution infrastructure and publishes an <code>ErrorMessage</code> to the appropriate error channel. This lesson belongs to the **Error runtime** chapter of **SPRING_INTEGRATION_RUNTIME**, focusing on how this component interacts with channels, consumers, pollers, executors, transactions, retries, message stores, correlation, and runtime observability.

> <code>MessagePublishingErrorHandler</code> is **not** a retry engine, does not automatically move messages to a dead-letter queue, and does not guarantee that every exception in the application turns into an <code>ErrorMessage</code>. A runtime component must actually invoke it or use it as an <code>ErrorHandler</code>.

## 1. Purpose and Position in the Runtime

The class <code>org.springframework.integration.channel.MessagePublishingErrorHandler</code> extends <code>org.springframework.integration.core.ErrorMessagePublisher</code> and implements <code>org.springframework.util.ErrorHandler</code>. Its key API members include:

| API Member | Role |
|---|---|
| <code>handleError(Throwable ex)</code> | Entry point receiving exceptions from a task/poller/channel, then publishing an <code>ErrorMessage</code> |
| <code>setDefaultErrorChannel(MessageChannel)</code> | Specifies the fallback channel as an object |
| <code>setDefaultErrorChannelName(String)</code> | Specifies the fallback channel by bean name |
| <code>getDefaultErrorChannel()</code> | Reads the configured default channel |
| <code>setErrorMessageStrategy(...)</code> | Customizes how <code>ErrorMessage</code> is constructed via the inherited API |
| <code>setSendTimeout(...)</code> | Bounds the time spent sending the error when the target channel may block, via the inherited API |

Component roles should be kept distinct:

- **Business handler** processes the payload and may throw an exception.
- **Consumer endpoint** invokes the handler on the current thread or a runtime-selected thread.
- **<code>ErrorHandler</code>** receives the exception at a boundary that has an error-catching mechanism.
- **<code>MessagePublishingErrorHandler</code>** constructs and publishes the <code>ErrorMessage</code>.
- **Error channel** delivers the error to one or more consumers for logging, alerting, recovery decisions, or storing error records.

~~~mermaid
flowchart LR
    A["Sender"] --> B["Channel / Queue"]
    B --> C["Worker / Poller"]
    C --> D["Consumer endpoint"]
    D --> E["Business handler"]
    E -. "Throwable" .-> F["MessagePublishingErrorHandler"]
    F --> G{"Valid errorChannel<br/>header?"}
    G -->|"Yes"| H["Per-message error channel"]
    G -->|"No"| I["Default / global errorChannel"]
    H --> J["Error consumer"]
    I --> J
    J --> K["Log / alert / quarantine / recovery"]
~~~

The diagram depicts the path when **the task executor or poller has an error-catching mechanism and uses <code>MessagePublishingErrorHandler</code>**. A synchronous call over a <code>DirectChannel</code> typically throws the exception back to the sender without following this path.

## 2. From Exception to ErrorMessage

The processing path can be viewed in steps:

1. A message is handed off to an asynchronous task or a polling consumer.
2. During processing, an endpoint, transformer, or handler throws an exception.
3. The infrastructure managing the task catches the exception and invokes <code>handleError(Throwable)</code>.
4. <code>MessagePublishingErrorHandler</code> creates an <code>ErrorMessage</code> whose payload is the <code>Throwable</code> or an infrastructure-wrapped exception.
5. The error message is sent to the failing message's error channel if a valid header is obtained; otherwise, it uses the configured fallback/global channel.
6. A consumer on the error channel processes the error according to application policy.

### Key data structure

<code>ErrorMessage</code> is a <code>Message&lt;Throwable&gt;</code>, not a <code>Message&lt;String&gt;</code> holding an error text. It may contain:

- <code>error.getPayload()</code>: the exception used for investigation or classification.
- <code>error.getOriginalMessage()</code>: the original message, **which may be null** if no corresponding context is available.
- <code>((MessagingException) cause).getFailedMessage()</code>: the message at the point of failure, if the payload is a <code>MessagingException</code> and this reference is attached.
- Headers of the <code>ErrorMessage</code> itself: do not assume they are identical to the input message's headers.

<code>originalMessage</code> and <code>failedMessage</code> serve different purposes. After a transformer, the failed message may hold the transformed payload, whereas the original message is the data entered earlier into the flow. Not every exception includes both. If a failure occurs before an inbound adapter constructs a Spring <code>Message</code>, the framework may only have the exception or adapter metadata.

~~~java
@ServiceActivator(inputChannel = "orders.errors")
public void observe(ErrorMessage error) {
    Throwable failure = error.getPayload();

    Message<?> failed = failure instanceof MessagingException messagingEx
        ? messagingEx.getFailedMessage()
        : null;

    Message<?> original = error.getOriginalMessage();
    Message<?> context = original != null ? original : failed;

    String correlationId = context != null
        ? (String) context.getHeaders().get("correlationId")
        : null;

    log.error("Order flow failed; correlationId={}", correlationId, failure);
    // Classify error, record metrics, or route records needing investigation to an appropriate store.
}
~~~

The snippet uses <code>org.springframework.messaging.support.ErrorMessage</code>, <code>org.springframework.messaging.MessagingException</code>, and <code>org.springframework.messaging.Message</code>. When reading a correlation ID in practice, align on the header's data type in your contract: the example above assumes the header is a <code>String</code>.

## 3. Rules for Selecting the Error Channel

The error-routing precedence matters more than class names:

| Condition | Where <code>ErrorMessage</code> Is Sent |
|---|---|
| Failing message has <code>MessageHeaders.ERROR_CHANNEL</code> pointing to a valid channel and handler has message context | Channel specified in the header |
| No matching header and <code>MessagePublishingErrorHandler</code> has a configured default channel | Configured default channel |
| No dedicated routing and the application uses Spring Integration's default error infrastructure | Global bean named <code>errorChannel</code> |
| Target channel does not exist, is blocked, or refuses the message | **Error publishing itself can fail**; inspect logs/configuration of the error publisher and caller |

The standard header is <code>MessageHeaders.ERROR_CHANNEL</code>; its value is typically a <code>MessageChannel</code> or a channel name resolvable by a channel resolver. The header takes precedence over the fallback channel, so changing the default channel has no effect on a message already carrying an <code>errorChannel</code> header pointing elsewhere.

The default global <code>errorChannel</code> is a <code>PublishSubscribeChannel</code>. Spring Integration provides a subscriber that logs at ERROR level; since version 5.4.3, the default channel requires subscribers to avoid silently dropping errors when no receiver is attached. If the application defines its own <code>errorChannel</code> bean, the application itself must design appropriate subscribers, capacity, and error behavior.

**Note:** A successful send to the error channel only proves *the error was published*. It does not prove the business message was retried, rolled back, or durably stored.

## 4. When Is MessagePublishingErrorHandler Used?

### 4.1. Pollers and task schedulers

A polling consumer pulls messages from a <code>PollableChannel</code> or a polling source. The processing call runs inside a scheduler-triggered task. Spring Integration integrates <code>MessagePublishingErrorHandler</code> with the default <code>taskScheduler</code> to publish errors from poller tasks to the error channel.

If the application replaces the scheduler with a custom <code>taskScheduler</code> bean, ensure an appropriate error-handling mechanism remains attached to the scheduler to retain this reporting behavior. The framework provides the <code>integrationMessagePublishingErrorHandler</code> bean for reuse in that scenario.

### 4.2. PublishSubscribeChannel with an executor

When a <code>PublishSubscribeChannel</code> uses an executor, subscribers can run on different threads; the channel supports an <code>ErrorHandler</code> and defaults to <code>MessagePublishingErrorHandler</code>. If the channel **has no executor**, subscriber exceptions are thrown directly along the synchronous send call, and any error handler configured on the channel is not applied.

### 4.3. ExecutorChannel and other asynchronous boundaries

<code>ExecutorChannel</code> also delegates processing through an executor, so consumer exceptions generally cannot propagate back to the sender's thread. However, **do not assume every <code>ExecutorChannel</code>, adapter, or standalone <code>TaskExecutor</code> invokes the exact same <code>MessagePublishingErrorHandler</code> instance**. Verify the actual dispatcher/error-handling setup of the component in use.

Some adapters (HTTP, AMQP, Kafka, JMS, etc.) have their own error handlers, retries, acknowledgments, and dead-letter policies. A deserialization error occurring *before a Spring Message is created* may stay entirely inside the listener/container and never enter the integration error channel unless the adapter wires that mechanism.

| Context | What does the sender typically see? | What to verify |
|---|---|---|
| Synchronous <code>DirectChannel</code> | Exception raised on the same call stack | Handle at caller/gateway or appropriate endpoint advice |
| <code>PublishSubscribeChannel</code> with executor | <code>send()</code> may complete before subscriber fails | Channel's error handler and <code>errorChannel</code> header |
| Poller receiving from <code>QueueChannel</code> | Sender does not directly see downstream processing failures | Scheduler error handler, poller transaction, and recovery |
| <code>ExecutorChannel</code> | Handoff and execution may happen on different threads | Dispatcher, error path, rejected tasks, and timeouts |
| Broker inbound listener | Depends on adapter and ACK mode | Listener error handler, retry/backoff, requeue/DLQ |

Even with an executor, never assume <code>send()</code> **always** returns immediately: task rejection, queue bounds, or caller-runs policies can change runtime behavior.

## 5. Java Example: Catching Errors from an Asynchronous PublishSubscribeChannel

This example uses Spring Integration Java/annotation configuration, Java 17+, and a service activator that always throws an exception when an order has an invalid quantity. All beans/methods below live inside a Spring application with the Spring Integration dependency.

**Step 1 — declare the channels, executor, and MessagePublishingErrorHandler itself:**

~~~java
@Configuration
@EnableIntegration
public class OrderErrorConfig {

    @Bean
    public ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-worker-");
        return executor;
    }

    @Bean(name = "orders.errors")
    public MessageChannel ordersErrors() {
        return new DirectChannel();
    }

    @Bean
    public MessagePublishingErrorHandler ordersPublishingErrorHandler(
            @Qualifier("orders.errors") MessageChannel fallbackErrors) {
        MessagePublishingErrorHandler handler = new MessagePublishingErrorHandler();
        handler.setDefaultErrorChannel(fallbackErrors);
        return handler;
    }

    @Bean(name = "orders.input")
    public MessageChannel ordersInput(
            ThreadPoolTaskExecutor orderExecutor,
            @Qualifier("ordersPublishingErrorHandler")
            MessagePublishingErrorHandler errorHandler) {
        PublishSubscribeChannel channel = new PublishSubscribeChannel(orderExecutor);
        channel.setErrorHandler(errorHandler);
        return channel;
    }
}
~~~

Key imports: <code>org.springframework.integration.channel.MessagePublishingErrorHandler</code>, <code>PublishSubscribeChannel</code>, <code>DirectChannel</code>; <code>org.springframework.integration.config.EnableIntegration</code>; <code>org.springframework.messaging.MessageChannel</code>; <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code>; <code>org.springframework.beans.factory.annotation.Qualifier</code>.

In this example, <code>orders.errors</code> is the default error channel for the configured publisher. An application can rely directly on <code>PublishSubscribeChannel</code>'s default <code>MessagePublishingErrorHandler</code> behavior if there is no need to specify a custom default.

**Step 2 — business consumer and error consumer:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Component
public class OrderConsumers {

    @ServiceActivator(inputChannel = "orders.input")
    public void process(OrderCommand order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException(
                "quantity must be greater than 0 for " + order.orderId()
            );
        }
        // Call business service when valid.
    }

    @ServiceActivator(inputChannel = "orders.errors")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        log.error("orders.errors received", failure);
        // Classify the error and decide on alerting, recovery, or quarantine.
    }
}
~~~

<code>@ServiceActivator</code> belongs to <code>org.springframework.integration.annotation</code>, and <code>@Component</code> belongs to Spring Context. The example assumes the application has a <code>log</code> logger (such as SLF4J) and enables Spring component scanning for <code>OrderConsumers</code>.

**Step 3 — send a message with a dedicated error channel:**

~~~java
Message<OrderCommand> request = MessageBuilder
    .withPayload(new OrderCommand("O-42", 0))
    .setHeader(MessageHeaders.ERROR_CHANNEL, ordersErrors)
    .setHeader("correlationId", "req-42")
    .build();

ordersInput.send(request);
~~~

Here <code>ordersInput</code> and <code>ordersErrors</code> are the beans <code>orders.input</code> and <code>orders.errors</code> respectively; <code>MessageBuilder</code> belongs to <code>org.springframework.integration.support</code>, and <code>MessageHeaders</code> belongs to <code>org.springframework.messaging</code>. The example attaches the **channel object** to the header to avoid relying on string-based channel name resolution.

Expected sequence:

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant P as PubSubChannel + Executor
    participant H as OrderConsumers.process()
    participant E as MessagePublishingErrorHandler
    participant C as orders.errors
    participant O as OrderConsumers.onError()
    S->>P: send(Message<OrderCommand>)
    P-->>S: task submitted/scheduled
    P->>H: dispatch on worker thread
    H--xP: IllegalArgumentException
    P->>E: handleError(Throwable)
    E->>C: ErrorMessage
    C->>O: handle(ErrorMessage)
    Note over S,O: Sender does not receive consumer exception via old call stack
~~~

<code>orders.errors</code> uses a <code>DirectChannel</code>, so the error consumer is invoked synchronously **on the thread publishing the error**. If <code>onError()</code> performs heavy work, the business worker can be blocked for a long time; under high load, design an error-processing pipeline with appropriate backpressure, durability, and resource limits.

### What changes if you remove the executor?

If you construct <code>new PublishSubscribeChannel()</code> without an executor, the call to <code>process()</code> runs directly on the sending thread. Exceptions usually propagate from <code>ordersInput.send(request)</code> back to the caller; calling <code>setErrorHandler(...)</code> on the channel will not turn that into asynchronous error handling.

## 6. Direct Practice: Header Takes Precedence over Default Channel

You can verify routing precedence without bootstrapping a full application context using a small example with two <code>QueueChannel</code> instances. The channels are passed directly as objects.

~~~java
QueueChannel perMessageErrors = new QueueChannel();
QueueChannel fallbackErrors = new QueueChannel();

MessagePublishingErrorHandler handler = new MessagePublishingErrorHandler();
handler.setDefaultErrorChannel(fallbackErrors);

Message<String> failedRequest = MessageBuilder.withPayload("invalid")
    .setHeader(MessageHeaders.ERROR_CHANNEL, perMessageErrors)
    .build();

handler.handleError(new MessageHandlingException(failedRequest, "bad payload"));

Message<?> published = perMessageErrors.receive(1000);
assertInstanceOf(ErrorMessage.class, published);
assertNull(fallbackErrors.receive(0));
~~~

<code>QueueChannel</code> belongs to <code>org.springframework.integration.channel</code>; <code>MessageHandlingException</code> belongs to <code>org.springframework.messaging</code>; the last two assertions are from JUnit 5. A standalone test like this demonstrates **the publishing mechanism**, and does not replace an integration test confirming the runtime actually invokes the error handler.

If you omit <code>ERROR_CHANNEL</code> from <code>failedRequest</code>, the error publisher uses the fallback channel when no priority channel is specified. In multi-flow environments, a common pitfall is a message having an <code>errorChannel</code> header previously attached by a gateway or adapter, causing the handler to publish errors somewhere other than the default channel operators are watching.

## 7. Custom TaskScheduler and Pollers

When declaring a custom <code>taskScheduler</code> to control thread count or thread naming, attach a compatible error handler. This is a **replacement configuration** for the default scheduler and must be evaluated within your existing Spring Integration setup.

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler integrationTaskScheduler(
        @Qualifier("integrationMessagePublishingErrorHandler")
        ErrorHandler integrationErrors) {

    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(8);
    scheduler.setThreadNamePrefix("integration-poller-");
    scheduler.setErrorHandler(integrationErrors);
    return scheduler;
}
~~~

<code>ThreadPoolTaskScheduler</code> belongs to <code>org.springframework.scheduling.concurrent</code>; <code>ErrorHandler</code> belongs to <code>org.springframework.util</code>. The <code>integrationMessagePublishingErrorHandler</code> bean is the error handler provided by Spring Integration in standard configurations. Before replacing the scheduler, check how the application initializes and manages <code>taskScheduler</code> to avoid duplicate bean conflicts.

A poller can be configured via annotation:

~~~java
@ServiceActivator(inputChannel = "orders.queue",
                  poller = @Poller(fixedDelay = "1000"))
public void consume(OrderCommand order) {
    orderService.process(order);
}
~~~

This example assumes <code>orders.queue</code> is a declared <code>PollableChannel</code> and <code>orderService</code> is injected into the component. <code>@Poller</code> is a Spring Integration annotation. If the consumer throws an error inside the poller task and no upstream advice recovers/swallows it, the scheduler's error handler can publish an <code>ErrorMessage</code>.

**Transaction boundary:** If the poller opens a transaction around receive/handle, an exception can mark the transaction for rollback before the error is reported via the scheduler. However, <code>MessagePublishingErrorHandler</code> itself does not decide rollback, broker message acknowledgment, or redelivery after failure. Those behaviors are governed by the transaction manager, adapter, message store, and ACK/redelivery policy.

## 8. Distinguishing Error Handling, Retry, and Recovery

Three mechanisms are frequently conflated:

| Mechanism | What does it do? | What does it NOT do automatically? |
|---|---|---|
| <code>MessagePublishingErrorHandler</code> | Publishes errors as <code>ErrorMessage</code> | Does not retry handlers, roll back, or persist payloads |
| <code>RequestHandlerRetryAdvice</code> | Retries a handler invocation per a retry policy | Does not automatically cover failures occurring before the advised endpoint |
| <code>ErrorMessageSendingRecoverer</code> | Used as a recovery callback to publish errors after retries fail | Does not determine the retry policy or guarantee source redelivery |

For example, when a downstream service fails because the database is temporarily unreachable:

1. Retry advice around the handler performs bounded retries with backoff.
2. If it succeeds, the flow continues normally.
3. If attempts are exhausted, a recovery callback can publish an <code>ErrorMessage</code> or let the exception propagate to a runtime boundary.
4. If the final exception reaches a scheduled task with <code>MessagePublishingErrorHandler</code>, the scheduler may publish an additional error message. **Avoid creating two uncontrolled publishing paths**, as this can trigger alerts or store quarantine records twice.

For permanent errors like malformed JSON or invalid business data, infinite retries only fill queues and exhaust threads. Route such messages to an inspection/quarantine path under clear criteria while preserving enough data for remediation.

## 9. What Happens If Publishing ErrorMessage Also Fails?

This is a real-world scenario to design for upfront, especially when the error flow itself has endpoints, executors, or message stores.

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Error consumer never runs | Message has an <code>errorChannel</code> header pointing elsewhere; no subscribers; endpoint not started | Capture headers on failure and verify channel subscriptions/lifecycle |
| Exception appears in logs but no <code>ErrorMessage</code> | Synchronous flow; task uses a different error handler; error occurred before a Spring Message existed | Identify the thread boundary and the error handler actually wired |
| Error-processing worker is blocked | Error consumer does heavy work on <code>DirectChannel</code>, queue is full, or error send blocks | Offload error processing, bound timeouts, and add backpressure |
| Error flow keeps throwing exceptions | Error consumer triggers secondary errors | Minimize dependencies in error consumers; keep reliable fallback logging/alerting |
| Error logged, yet source message is lost | Message was ACKed/removed, error channel is in-memory, or system restarted | Design durable DLQ/quarantine and explicit ACK rules |
| Multiple notifications for one error | Both retry recoverer and scheduler publish, or multiple subscribers cause duplicate side effects | Standardize recovery ownership and idempotency in error handling |

An <code>ErrorMessage</code> on the default <code>PublishSubscribeChannel</code> is only an in-memory message when published and delivered to subscribers; by itself it is **not a persisted record**. If post-restart investigation and replay are required, the system must proactively persist appropriate data to storage, a broker DLQ, or a durable message store.

In Spring Integration, the default channel can be configured with <code>requireSubscribers</code> so messages are not dropped silently when subscribers are missing. This is a useful safeguard, but it does not replace checking error consumer health, tracking publish failure metrics, and persisting raw failed records.

## 10. Correlation, Tracing, and Performance Observability

As messages flow across transformers, splitters, aggregators, and multiple executors, a single failure may span multiple message IDs. Standardize observability metadata:

- **Business/flow correlation ID:** a stable value placed in a header with a clear contract; used to link events across threads.
- **Current message ID:** identifies an individual message, not automatically equivalent to an idempotency key; may change when new messages are created.
- **Failed/original message:** identifies which payload and endpoint actually failed; check for null and enforce access controls.
- **Component/endpoint name, thread, timestamp:** helps distinguish pollers, executors, and subscribers; Spring Messaging stack traces can reveal source component details.
- **Metrics:** error count by exception class/endpoint, error publishing failures, queue depth, active threads, executor rejections, retry counts, and error consumer latency.

Do not log full sensitive payloads to the error channel or centralized logs. Record only necessary identifiers and a masked version; if original payloads must be retained for replay, enforce appropriate access controls and retention periods.

### Diagnosing when no ErrorMessage appears

Proceed step by step:

1. Determine which endpoint the message actually reached using logs/metrics at adapters and channels.
2. Check whether the exception occurred **on the same thread as the sender** or inside an executor/poller task.
3. Verify which task/channel owns the <code>ErrorHandler</code>; do not merely look for a <code>MessagePublishingErrorHandler</code> bean in the context and assume it is used.
4. If published, inspect <code>MessageHeaders.ERROR_CHANNEL</code> on the failed message, the default bean/channel, subscribers, and the start/stop state of the error endpoint.
5. If the target channel has a queue or message store, check capacity, receive capability, durability, and timeouts.
6. If the exception originated from an inbound adapter, inspect deserialization, ACK/nack, container retries, and that adapter's DLQ.
7. If retry/recovery is configured, check whether the exception propagated out or was caught and considered handled by advice/handlers.

## 11. Testing This Mechanism

At minimum, cover the following cases:

| Scenario | What to Verify |
|---|---|
| Error in subscriber on an executor-backed channel | An <code>ErrorMessage</code> is delivered to the expected error consumer |
| Error on a synchronous channel without an executor | Caller receives the exception; do not assume the error channel receives it |
| Message with <code>ERROR_CHANNEL</code> header | Header takes precedence over the default error channel |
| Message without the header | Error is sent to the configured fallback/global channel |
| Error consumer stopped or channel has no subscribers | Failure signal or appropriate fallback occurs; errors are not silently lost |
| Poller throws an exception | Scheduler error handler and transaction/recovery work as designed |
| Error after retries are exhausted | No duplicate side effects or unintended multiple quarantine records |

For asynchronous tests, use <code>CountDownLatch</code>, <code>BlockingQueue</code>, or bounded await utilities to wait for the error consumer rather than calling <code>send()</code> and asserting immediately. A synchronous unit test calling <code>MessagePublishingErrorHandler.handleError(...)</code> directly proves the publishing API; it does **not** prove the framework configured and invoked the error handler on a worker thread.

## 12. Pre-Production Checklist

- Pinpoint the exact thread boundary and error origin: sender, executor, poller, or adapter.
- Configure the error handler on the right runtime component; understand the precedence of the <code>errorChannel</code> header, default channel, and global channel.
- Ensure a working error consumer is active; distinguish error reporting from retry, rollback, ACK, and redelivery.
- Explicitly define transient vs. permanent errors, retry counts, backoff, quarantine, and poison-message handling.
- Preserve correlation IDs, endpoint names, and failed/original message details when available while preventing sensitive payload leaks.
- Control thread pools, capacities, timeouts, and reliability of the error flow itself; monitor/alert on secondary errors.
- Test endpoint start/stop, timeouts, broker redelivery, and failures within the error channel itself.

**Conclusion:** <code>MessagePublishingErrorHandler</code> bridges **exceptions in runtime tasks** and **error messages in message flows**. Once you understand who invokes <code>handleError()</code>, how error channels are selected, and which component owns transactions and retries, you can diagnose failures accurately by thread and endpoint, avoiding lost messages or confusing "error published" with "successfully recovered."

## References

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Configuring the Task Scheduler](https://docs.spring.io/spring-integration/reference/configuration/namespace-taskscheduler.html)
- [Spring Integration Javadoc — MessagePublishingErrorHandler](https://www.springframework.org/spring-integration/docs/6.5.x/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html)
