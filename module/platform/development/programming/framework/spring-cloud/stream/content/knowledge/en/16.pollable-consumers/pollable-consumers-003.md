# Proactively Calling poll and Handling No-Message States

Spring Cloud Stream supports two common ways to consume messages. With a message-driven consumer, the framework receives a message and invokes the handler function when the message arrives. With a pollable consumer, the application proactively asks the input source to check for and deliver a message by calling PollableMessageSource.poll(). The second approach is useful when the application needs to control the reading pace itself, limit the number of messages per cycle, coordinate with a job schedule, or process only when resources are ready.

A poll call does not necessarily receive a message. The method returns true when a message was retrieved and passed to the handler; it returns false when no message was received in that poll. Returning false is a normal flow state, not a business error or a sign of a broken broker. The application needs to decide whether to wait, retry later, end the current cycle, or record an idle state.

This lesson focuses on the poll API, the meaning of the boolean return value, handling messages in the handler, avoiding busy loops when no data is present, and bounding the number of messages read in a cycle. It also covers error handling, binder-specific acknowledgment, testing, monitoring, and safe shutdown.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of PollableMessageSource in the proactive consumer model.
- Use poll(MessageHandler) and accurately interpret true or false results.
- Distinguish a no-message state from an exception during reading or processing.
- Design a bounded poll cycle to process batches without occupying resources indefinitely.
- Choose an appropriate polling schedule, wait interval, and backoff.
- Process messages in a handler and understand binder-specific acknowledgment/redelivery limits.
- Test scenarios with a message, without a message, and with handler exceptions.
- Monitor empty polls, throughput, backlog, and consumer health in production environments.

## 1. What Is a Pollable Consumer?

A pollable consumer allows the application to decide when to ask the broker to deliver a message. Instead of letting the framework automatically invoke a Consumer<T> whenever a message arrives, the application obtains a PollableMessageSource object and calls poll() on a schedule or control loop it manages.

The primary API resides in the package:

~~~java
org.springframework.cloud.stream.binder.PollableMessageSource
~~~

A single poll receives one Message<?> and passes that message to MessageHandler. The basic API has the signature:

~~~java
boolean poll(MessageHandler handler);
~~~

Another overload allows specifying a target type when payload conversion is needed:

~~~java
boolean poll(
        MessageHandler handler,
        ParameterizedTypeReference<?> type);
~~~

Overload details may vary by Spring Cloud Stream version; check the API of the dependency you are using. The most important semantics of the basic method is the boolean result indicating whether that poll received a message.

### 1.1. When Should You Use a Pollable Consumer?

A pollable consumer is suitable when the application needs to proactively regulate consumption rate, for example:

- Only reading messages when an internal resource still has available capacity.
- Processing at most a fixed number of messages per cycle.
- Combining message reading with a scheduler or a batch processing loop.
- Controlling the wait interval between queue checks.
- Integrating with an existing orchestration component in the application.

If you only need to process messages immediately upon arrival and have no requirement to control the reading pace, a message-driven consumer is usually simpler. Polling adds responsibility for managing schedules, wait intervals, retries, and shutdown to the application.

## 2. Meaning of the poll() Return Value

The return value of poll() has two primary states:

| Result | Meaning | Typical Appropriate Action |
|---|---|---|
| true | A message was received and passed to the handler | Process the result, optionally continue polling if budget remains |
| false | The poll did not receive a message | End the cycle or wait until the next poll |

When there is no message, the handler is not invoked. The application should not fabricate a dummy message or invoke the handler with an empty payload to represent an empty queue. The empty state is already represented by the false return value.

### 2.1. false Does Not Mean an Error

The queue may be empty, a message may not have arrived yet, or an eligible message may not be ready for delivery to the consumer at the moment of polling. With Kafka, a consumer might not receive a new record in the current poll even though the topic exists and other partitions are active. With RabbitMQ, a queue might temporarily have no messages ready for delivery.

Therefore, false only describes the outcome of that specific poll. It does not prove that:

- The broker has stopped.
- The destination does not exist.
- The consumer group is broken.
- No more messages will be emitted by producers in the future.
- The entire system has no messages across any partition or queue.

If you need to diagnose the broker, use health checks, metrics, and binder exceptions. Do not use the count of false results as sole evidence of a connection failure.

### 2.2. Distinguishing false from Exceptions

A poll call can receive no message and return false. This is a normal outcome. Situations such as connection failures, conversion failures, handler failures, or binder errors can be represented by exceptions.

| Situation | Signal | How to Handle |
|---|---|---|
| No message | poll() returns false | Wait or end the cycle |
| Message present and processed successfully | poll() returns true | Update success metrics |
| Handler failed | Exception thrown from the poll/handler execution | Record the error and apply the appropriate binder policy |
| Broker or connection error | Exception from the binder/client | Alert, back off, and recover the connection |
| Payload cannot be converted | Conversion exception | Isolate or handle the failed message per policy |

Do not catch all exceptions and treat them as an empty queue. If a connection error is silently converted into a false status, the application can remain silent while the consumer has actually stopped working.

## 3. Executing a Single Poll

Suppose the application already has an input binding configured as a PollableMessageSource and Spring has injected that object into the consumer:

~~~java
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public class OrderPoller {

    private final PollableMessageSource source;

    public OrderPoller(PollableMessageSource source) {
        this.source = source;
    }

    public boolean pollOnce() {
        return source.poll(message -> process(message));
    }

    private void process(Message<?> message) {
        System.out.println("Received: " + message.getPayload());
    }
}
~~~

The example focuses on the poll operation; how a pollable input binding is declared and injected depends on your application's binding model and Spring Cloud Stream version. When wiring, ensure the injected object is the pollable source for the intended input binding.

pollOnce() returns the boolean so the orchestration layer can decide the next step. Separating the poll operation from the execution schedule makes unit testing easier and allows the same consumer to be invoked from a scheduler, executor, or another coordinator.

### 3.1. Handling the Message Inside the Handler

The handler receives a Spring Message<?>. The payload is the business data; headers may contain content type, correlation ID, event ID, or binder metadata.

~~~java
private void process(Message<?> message) {
    Object payload = message.getPayload();
    Object eventId = message.getHeaders().get("eventId");
    Object correlationId = message.getHeaders().get("correlationId");

    // Validate payload type and data before executing business effects.
    orderService.handle(payload, eventId, correlationId);
}
~~~

In production code, validate payload types and required headers before casting or calling services. Do not log full sensitive payloads. If the handler expects a specific DTO type, you can use the overload with ParameterizedTypeReference when the binder and converter support the corresponding conversion.

## 4. Handling the No-Message State

A poll cycle typically has three steps:

1. Call poll() to check the source.
2. If a message is available, the handler processes the message.
3. If no message is available, end the current cycle or wait according to the chosen schedule.

Example of a poll execution with explicit empty-state handling:

~~~java
public void runOneCycle() {
    try {
        boolean received = source.poll(message -> process(message));

        if (received) {
            metrics.incrementReceived();
        } else {
            metrics.incrementEmptyPoll();
        }
    } catch (Exception ex) {
        metrics.incrementPollFailure();
        log.error("Polling order message failed", ex);
    }
}
~~~

The key point is separating the three states: message present, no message, and error. The empty state can be recorded at debug level or in metrics; you should not trigger error alerts every time the queue is temporarily empty.

### 4.1. Do Not Use a Busy Loop

The following code is unsuitable:

~~~java
while (true) {
    source.poll(this::process);
}
~~~

When the queue is empty, the loop keeps calling poll continuously without resting. This can burn CPU, generate excessive logs/metrics, and make unnecessary broker calls.

Adding a simple wait reduces load:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    boolean received = source.poll(this::process);
    if (!received) {
        Thread.sleep(250);
    }
}
~~~

This is only an illustrative example. Production applications must handle InterruptedException, stop the executor on shutdown, and distinguish poll exceptions from empty states. In Spring applications, a scheduler is usually easier to lifecycle-manage than a self-managed infinite loop.

### 4.2. Choosing a Wait Interval

The wait interval directly affects latency and load:

- A short interval detects new messages faster but generates more poll calls when the queue is empty.
- A long interval reduces poll count but increases the time a message waits before processing.
- A fixed interval is predictable and fits steady traffic.
- Incremental backoff fits when the source is frequently empty or when the broker/dependent service is overloaded.

No single value fits every system. Choose based on latency SLA, message volume, resource limits, and per-poll cost.

## 5. Polling One Message or Processing in Batches?

PollableMessageSource.poll(handler) processes one message per call. The application can call it multiple times in a cycle to pull a batch, but should set a limit.

Example of processing at most 50 messages in one cycle:

~~~java
private static final int MAX_MESSAGES_PER_CYCLE = 50;

public int pollBatch() {
    int processed = 0;

    for (int i = 0; i < MAX_MESSAGES_PER_CYCLE; i++) {
        boolean received = source.poll(this::process);

        if (!received) {
            break;
        }

        processed++;
    }

    return processed;
}
~~~

If poll returns false, the cycle stops immediately because no messages are currently ready. If 50 messages are reached, the cycle also stops even though the source may still have data. The next scheduler run continues the work.

### 5.1. Why Cap the Batch?

If the loop continues until the queue is empty, a large backlog spike can cause the cycle to hold the thread for too long. Other tasks such as health checks, status updates, or periodic jobs can be delayed.

Capping the batch helps:

- Share CPU time across tasks.
- Control how many messages a single run can process.
- Prevent a heavily backlogged source from monopolizing the worker.
- Create shutdown checkpoints between cycles.
- Make processing time and throughput easy to measure per batch.

### 5.2. Batch Count Is Not a Batch Transaction

Calling poll 50 times does not mean the 50 messages share a single transaction. Each poll call may have its own delivery lifecycle depending on the binder. If business logic requires all messages to succeed or roll back together, you need a supported transaction mechanism and must verify the actual transaction boundaries.

Do not collect messages into an in-memory batch and acknowledge them all before persisting business results. If the application crashes mid-batch, progress can be lost or duplicates created depending on acknowledgment order.

## 6. Scheduling Polling with Spring

An easy-to-manage implementation is using @Scheduled to run a bounded cycle:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class ScheduledOrderPoller {

    private final PollableMessageSource source;

    ScheduledOrderPoller(PollableMessageSource source) {
        this.source = source;
    }

    @Scheduled(fixedDelay = 500)
    public void pollAvailableMessages() {
        for (int i = 0; i < 50; i++) {
            boolean received = source.poll(this::process);
            if (!received) {
                return;
            }
        }
    }

    private void process(Message<?> message) {
        // Perform business processing.
    }
}
~~~

The application needs to enable scheduling with @EnableScheduling in Spring configuration:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfiguration {}
~~~

fixedDelay measures the duration from when one execution finishes until the next starts. This prevents a new scheduled run from firing while the previous one is still executing. If you need a cron or time-based schedule, you can use the cron attribute of @Scheduled.

### 6.1. Do Not Let Exceptions Break the Schedule

In the example above, if source.poll() or the handler throws an exception, the scheduled method can terminate abnormally. Catch errors at the cycle boundary, record metrics, and apply appropriate backoff:

~~~java
@Scheduled(fixedDelay = 500)
public void pollAvailableMessages() {
    try {
        pollBatch();
    } catch (Exception ex) {
        log.error("Order polling cycle failed", ex);
        metrics.incrementCycleFailure();
    }
}
~~~

Do not catch exceptions and ignore them completely. Log sufficient context, increment error counters, and alert if failures persist. If the failure is due to invalid data, route the message to a dead-letter or error channel appropriate for the binder.

### 6.2. Backoff on Consecutive Empty Polls

If the source is often empty, a short fixed schedule can generate many unnecessary polls. You can use an incremental delay controller:

~~~java
Duration nextDelay(int emptyPolls) {
    long millis = Math.min(5000L, 250L * (1L << Math.min(emptyPolls, 4)));
    return Duration.ofMillis(millis);
}
~~~

This is an algorithmic idea, not a direct configuration for @Scheduled. To apply runtime-variable delays, use TaskScheduler or a dynamic scheduling mechanism. Set an upper cap and reset the backoff when a message is received.

If messages must be processed near real time, do not set the backoff too high. If the poller reads background batches, larger wait intervals can reduce cost when no data is present.

## 7. Handler Success, Handler Failure, and Acknowledgment

When poll retrieves a message, the handler processes the payload. How the message is acknowledged, retained, or redelivered when the handler throws an exception depends on the binder and acknowledgment/transaction configuration.

Key principles:

- Treat a message as successfully processed only after required business effects complete.
- Do not swallow exceptions if the binder relies on exceptions to apply reject or redelivery policies.
- Define how failed messages are routed to an error channel or dead-letter destination.
- Check the binder's retry configuration, since consumer-side retries and broker-side retries can interact.
- Design consumers to be idempotent because redelivery can cause the same message to be processed again.

### 7.1. Kafka

With the Kafka binder, consumer progress is tracked via partition offsets. How offsets are committed during pollable consumer processing depends on ack mode, transactions, and binder configuration. If offsets are committed before business processing finishes, the application can skip records after a failure. If processing finishes before commit and the app stops, records can be read again.

Therefore, verify the commit behavior of your Kafka binder version and choose an appropriate policy. Do not assume poll() returning true means the offset has been durably committed.

### 7.2. RabbitMQ

With the Rabbit binder, messages are typically acknowledged according to the acknowledgment mode and processing status. If a consumer stops before acking, the broker can redeliver the message. Reject, requeue, and dead-letter behavior depend on container/binder configuration.

Do not assume an empty queue after poll() returns false means the queue is permanently drained. Producers may publish new messages right afterward; unacknowledged or in-flight messages may also be in another state inside the broker.

### 7.3. Idempotency

A pollable consumer should tolerate a message being delivered multiple times. You can use a stable event ID and record processed markers in a database:

~~~java
void processOrder(Message<OrderCreated> message) {
    String eventId = (String) message.getHeaders().get("eventId");

    if (processedEventRepository.exists(eventId)) {
        return;
    }

    transactionTemplate.executeWithoutResult(status -> {
        orderService.apply(message.getPayload());
        processedEventRepository.markProcessed(eventId);
    });
}
~~~

The illustrative code must ensure checking and marking the event ID are atomic within an appropriate transaction; merely calling exists() then markProcessed() without a unique constraint or lock can still suffer race conditions when multiple instances process the same event.

## 8. No Messages and Other Operational States

A consumer can observe several distinct states:

| State | Interpretation | Response |
|---|---|---|
| Empty poll | No message available in this check | Wait per schedule |
| Message received | A message was passed to the handler | Process and record outcome |
| Handler failure | Business processing failed | Apply retry/DLQ and alert |
| Polling exception | Binder or poll operation failed | Back off, recover, and alert |
| Conversion failure | Payload could not be converted to required type | Isolate the failed message |
| Shutdown requested | Application needs to stop | Stop starting new polls, finish or let broker redeliver in-flight work |

Do not collapse all these states into a single boolean at the application layer. The boolean from poll only indicates whether that call received a message; errors and shutdown must be represented separately.

### 8.1. Empty Polls Can Be a Normal Signal

Some systems have bursty traffic: nearly zero messages overnight, surging during business hours. In this case, empty polls are a normal operating state.

Do not fire an alert every time poll() returns false. Instead, track empty poll ratio, time since last received message, and source backlog. Alert only when emptiness violates business expectations, such as a source committed to emitting data within a window producing no new messages.

### 8.2. Empty Poll Is Not Proof of Zero Consumer Lag

In partitioned systems, a single poll receiving no message does not prove all partitions are empty. The consumer might be assigned a subset of partitions while data or backlog sits in other partitions. Use Kafka consumer lag or RabbitMQ queue depth to measure backlog rather than inferring from a single poll.

## 9. Testing Pollable Consumers

Tests should verify both boolean branches and the exception branch.

### 9.1. Unit Testing the Message-Received Outcome

You can mock PollableMessageSource to verify the handler is passed and true is returned:

~~~java
@Test
void reportsMessageReceived() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    OrderPoller poller = new OrderPoller(source);

    when(source.poll(any(MessageHandler.class))).thenReturn(true);

    assertThat(poller.pollOnce()).isTrue();
}
~~~

If you need to verify the handler actually processes a payload, the mock can capture the passed MessageHandler and invoke handleMessage(message) inside the stub's answer.

### 9.2. Unit Testing an Empty Poll

~~~java
@Test
void reportsNoMessageWithoutCallingBusinessHandler() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    OrderPoller poller = new OrderPoller(source);

    when(source.poll(any(MessageHandler.class))).thenReturn(false);

    assertThat(poller.pollOnce()).isFalse();
    verify(source).poll(any(MessageHandler.class));
}
~~~

This test verifies the application recognizes an empty poll and does not treat it as an error. If metrics exist, verify the empty counter increments exactly once.

### 9.3. Unit Testing Exceptions

~~~java
@Test
void propagatesOrRecordsPollingFailure() {
    PollableMessageSource source = mock(PollableMessageSource.class);
    when(source.poll(any(MessageHandler.class)))
            .thenThrow(new IllegalStateException("broker unavailable"));

    OrderPoller poller = new OrderPoller(source);

    assertThatThrownBy(poller::pollOnce)
            .isInstanceOf(IllegalStateException.class);
}
~~~

If the poller class catches exceptions and records metrics instead of rethrowing, the test should verify the error counter and corresponding backoff behavior.

### 9.4. Integration Testing with a Binder

The Test Binder can verify the input binding and that messages are received when data is present. With a real broker, test:

- Polling when the queue/topic has messages.
- Polling when no messages exist.
- Messages are acked after handler success as configured.
- Handler errors trigger retry, reject, or redelivery as expected.
- Consumer stops mid-processing and messages recover according to broker semantics.
- Payloads and headers are converted properly.

For Kafka, check offsets and consumer groups. For RabbitMQ, check acknowledgment, requeue, and dead-lettering. Do not use mock tests to draw conclusions about real broker delivery semantics.

## 10. Observability and Alerting

A pollable consumer needs dedicated metrics for polling activity:

| Metric | Purpose |
|---|---|
| poll.attempts | Total number of poll calls |
| poll.received | Number of polls that received a message |
| poll.empty | Number of polls that received no message |
| poll.failures | Number of poll/handler errors |
| poll.duration | Duration per poll or cycle |
| message.processing.duration | Business processing duration |
| message.processing.failures | Number of messages that failed processing |
| consumer.backlog | Number of queued messages or broker lag |
| consumer.last.success | Timestamp of the most recent successful processing |

Metric names are suggestions for your observability stack; standardize them according to application conventions. Avoid using event IDs or customer IDs as high-cardinality labels.

### 10.1. When Should You Alert?

Alert when:

- Poll exceptions rise continuously.
- No messages arrive for longer than the source's SLA.
- Processing latency spikes abnormally.
- Backlog or consumer lag grows continuously.
- Handler failure rate exceeds threshold.
- The consumer has no successful processing within an expected window.

An isolated empty poll usually does not warrant an alert. Combine it with traffic expectations and backlog to avoid false alarms.

## 11. Shutdown and Resilience

When the application receives a shutdown signal, prevent the schedule from starting new poll cycles. If a message is currently being processed, define how long it is allowed to finish and how the broker handles unacknowledged messages.

Key principles:

- Stop schedulers or executors before closing binder connections.
- Do not start a new batch while the application is shutting down.
- Keep the graceful shutdown timeout long enough for a typical message/batch.
- If the handler has not finished, let the binder/broker apply configured redelivery.
- Ensure consumers are idempotent so redelivered messages are safe.
- Monitor in-flight message counts and redelivery rates after restarts.

If using a manual loop, handle interrupts properly and exit the loop when the thread is interrupted. Do not call Thread.sleep() and ignore InterruptedException, as that makes the application difficult to stop.

## 12. Common Pitfalls

1. **Treating false as a broker error**: an empty poll only means that poll call received no message. Distinguish it from exceptions and use health/metrics to diagnose the broker.
2. **Ignoring the boolean result**: the application does not know when the source is empty and may keep calling poll unnecessarily. Check the return value after every call.
3. **Busy looping on an empty queue**: increases CPU usage and creates unnecessary poll load. Use a scheduler, delay, or backoff.
4. **Polling without limits until the queue is empty**: large backlogs can hold the worker for too long. Cap the message count or time per cycle.
5. **Conflating exceptions with empty polls**: binder errors get hidden and the consumer can silently stop working. Handle the two branches separately.
6. **Swallowing exceptions in the handler**: the binder may think the message succeeded even though business logic failed. Explicitly decide when exceptions should propagate.
7. **Assuming true means the offset is committed**: the poll result only reflects message retrieval. Verify the binder's acknowledgment/commit behavior.
8. **Not designing for idempotency**: redelivery can cause duplicate business effects. Use event IDs and record processing markers.
9. **Polling too aggressively**: wastes resources when no messages exist. Tune intervals to actual SLAs and load.
10. **Alerting on every empty poll**: creates noise and masks real failures. Alert on inactivity duration or backlog instead.
11. **Not stopping the scheduler on shutdown**: new polls can begin while the binder is closing. Manage the consumer lifecycle properly.
12. **Testing only the message-present branch**: empty-state handling bugs often slip through. Test true, false, and exception paths.

## 13. Workflow for Building a Pollable Consumer

When implementing a proactive consumer, follow this sequence:

1. Identify why polling is needed instead of a message-driven consumer.
2. Declare the input binding exposed as a PollableMessageSource.
3. Write a handler for payloads and headers with data validation.
4. Call poll() and handle true, false, and exception outcomes separately.
5. Choose one message at a time or a bounded batch.
6. Configure polling schedule, delay, or backoff based on latency requirements.
7. Define acknowledgment, retry, reject, and DLQ behavior per binder.
8. Design idempotency for messages that may be redelivered.
9. Write unit tests for message present, no message, and exceptions.
10. Run integration tests with a real broker for ack, offsets, redelivery, and recovery.
11. Set up metrics, alerts, and graceful shutdown.

## Conclusion

PollableMessageSource.poll() gives the application control over consumption pace. Returning true indicates the poll received a message and passed it to the handler; returning false indicates no message was retrieved during that check. The empty state is normal and should be handled by ending the cycle, waiting on a schedule, or applying backoff. Exceptions must be tracked separately so binder or handler errors are never masked.

A reliable pollable consumer needs bounded batches, an appropriate execution schedule, binder-aligned acknowledgment policies, idempotency, and testing across all three branches: message present, no message, and error. Monitoring empty polls alongside backlog, processing duration, and last success time helps distinguish a normally idle source from a genuinely failing consumer.

## References

- [Spring Cloud Stream — Pollable Consumer](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
