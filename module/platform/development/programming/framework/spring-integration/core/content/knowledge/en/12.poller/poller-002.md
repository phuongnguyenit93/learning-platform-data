# fixed-delay

## 1. What Problem Does fixed-delay Solve?

In Spring Integration, a poller proactively checks a data source or a `PollableChannel` on a schedule. The `fixed-delay` configuration sets a pause interval after a poll execution finishes before allowing the next poll to start.

For example, an application checks an internal queue, pulls orders, and sends them into a processing flow. If one check takes 300 ms and `fixed-delay` is 2 seconds, the next poll starts approximately 2.3 seconds after the start of the previous poll, provided the scheduler is not delayed.

This scheduling approach is suitable when you need:

- A rest interval between two accesses to a data source.
- The schedule to adapt to the variable processing duration of each poll.
- To avoid a synchronous poll task running back-to-back to catch up after a slow run.
- To configure the flow with the Java DSL or annotated endpoints while keeping the data-fetching cadence easy to explain.

`fixed-delay` is a scheduling property of the poller. It is not a delay applied to individual `Message` instances, not a business processing deadline, and not a substitute for external service rate limiting.

## 2. Where Does the Poller Sit in a Message Flow?

There are two common places where pollers are used in Spring Integration Core.

### 2.1. Inbound Channel Adapter Fetching Data from a Source

A `MessageSource` supplies data when `receive()` is called. The poller schedules calls to the source; when the source returns a message, the adapter sends it to the output channel.

```text
Scheduler
    |
    v
Poller -> MessageSource.receive()
                   |
                   v
                Message -> MessageChannel -> transformer/filter/router/handler
```

In the Java DSL, `IntegrationFlow.fromSupplier(...)` is a convenient way to create a polling source. A non-`null` value returned by the supplier is converted into a message; `null` indicates no data on that invocation.

### 2.2. Endpoint Receiving Messages from a PollableChannel

`QueueChannel` holds messages in a queue and lets the receiver pull them proactively. A polling consumer needs a poller to call `receive()` on the channel and then pass the message to the handler.

```text
Producer -> QueueChannel
                ^
                | receive()
          Poller + polling consumer -> handler
```

Conversely, an endpoint receiving from a `DirectChannel` is invoked in a push model when the producer sends a message. Do not attach a poller to that endpoint to slow down message reception. If you want to switch from a push mechanism to a scheduled pull mechanism, you can place a `QueueChannel` at the appropriate boundary.

## 3. Exact Timing Semantics

Let:

- `D`: the `fixed-delay` value.
- `S(n)`: the start time of the `n`-th poll task.
- `E(n)`: the end time of the `n`-th poll task.
- `T(n) = E(n) - S(n)`: the execution duration of that task.

With a poller running synchronously on a scheduler thread, the schedule takes the form:

```text
S(n + 1) ≈ E(n) + D
S(n + 1) - S(n) ≈ T(n) + D
```

The approximation sign reflects the impact of the scheduler, system load, and clock precision. `fixed-delay` does not guarantee hard real-time timing.

Example with `D = 2 seconds`:

```text
Time:      0s       1s       2s       3s       4s       5s       6s
           |--------|--------|--------|--------|--------|--------|
Poll 1:    [0.0 -> 0.4]
Pause:                 [0.4 ----------> 2.4]
Poll 2:                                  [2.4 ------> 3.6]
Pause:                                                  [3.6 -> 5.6]
Poll 3:                                                                  [5.6 ...]
```

The key timestamps to note are `0.0`, `0.4`, `2.4`, `3.6`, and `5.6` seconds; the diagram illustrates the sequence only and is not drawn strictly to scale.

### 3.1. One Poll Is Not Necessarily One Message

A single task execution can call the source or channel multiple times, depending on `maxMessagesPerPoll`. Therefore, execution time may include:

1. Waiting to receive a message.
2. Creating and sending the message into the flow.
3. Downstream processing if those steps run synchronously.
4. Repeating to fetch subsequent messages in the same poll.
5. Completing steps wrapping the poll, such as configured advice or transactions.

If `maxMessagesPerPoll = 10`, the `fixed-delay` pause sits between polls, not automatically between each pair of messages within that group of ten messages.

### 3.2. What "Finished" Covers Depends on Asynchronous Boundaries

With a `DirectChannel`, downstream handlers typically run immediately on the sending thread. That handler's processing time is included in the poll task's execution time.

If the flow sends to another `QueueChannel` or hands off to a downstream executor, the send can complete before the business work finishes. In that case, `fixed-delay` does not wait for all asynchronous downstream work to finish.

This is why you must clearly identify whether you are measuring the duration of the source, the poll task, or the entire business process.

## 4. Java DSL Example: Fetching at Most One Order per Poll

The example below uses the Java DSL in the Spring Integration 6.x API style, with `Pollers.fixedDelay(Duration)`. The project needs `spring-integration-core` and is initialized via a Spring context. Spring Boot can manage dependency versions for Boot-based projects.

```java
import java.time.Duration;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class FixedDelayOrderFlowConfig {

    @Bean
    public Queue<String> pendingOrders() {
        return new ConcurrentLinkedQueue<>(
                List.of("ORDER-101", "ORDER-102", "ORDER-103"));
    }

    @Bean
    public IntegrationFlow orderPollingFlow(Queue<String> pendingOrders) {
        return IntegrationFlow
                .fromSupplier(
                        pendingOrders::poll,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)))
                .<String, String>transform(String::toUpperCase)
                .handle(message ->
                        System.out.println("Received: " + message.getPayload()))
                .get();
    }
}
```

Explanation:

- `pendingOrders::poll` returns and removes one element from the queue; when the queue is empty, it returns `null` immediately.
- The poller uses a two-second pause after each execution.
- `maxMessagesPerPoll(1)` limits each poll to one message.
- The transformer illustrates an endpoint in the flow. With the already-uppercase data here, the payload keeps the same value.
- The handler ends the flow by printing the payload.

Do not assume the first message always waits exactly two seconds after application startup. The pause between polls and the initial delay are two separate settings. If you want to delay the first poll, configure `initialDelay` explicitly.

```java
Pollers.fixedDelay(Duration.ofSeconds(2))
        .initialDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1);
```

The first poll is scheduled with an initial delay of about five seconds; subsequent polls apply the two-second pause according to the poll task semantics.

The example uses an in-memory queue for illustration only. An item is removed as soon as the supplier pulls it, so a downstream error does not automatically return the item to the queue. For real orders, design data durability, transactions, or an appropriate acknowledgment mechanism.

## 5. Polling Consumer Example on QueueChannel

When a producer actively sends messages into a queue, place the poller on the endpoint consuming the queue:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class QueuedOrderFlowConfig {

    @Bean
    public QueueChannel queuedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow queuedOrderFlow(QueueChannel queuedOrders) {
        return IntegrationFlow
                .from(queuedOrders)
                .handle(
                        message -> processOrder(message),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(1))
                                        .maxMessagesPerPoll(5)
                                        .receiveTimeout(0)))
                .get();
    }

    private void processOrder(Message<?> message) {
        System.out.println("Processing: " + message.getPayload());
    }

    public static boolean enqueue(QueueChannel channel, String orderId) {
        return channel.send(
                MessageBuilder.withPayload(orderId).build(),
                500);
    }
}
```

Here:

- `QueueChannel(100)` has a maximum capacity of 100 messages.
- Producers can call `enqueue(...)` from another component after obtaining the channel bean from Spring.
- Each consumer poll fetches up to five messages, stopping early if the channel has no messages.
- `receiveTimeout(0)` makes each receive an immediate check without waiting for a message to appear.
- After the processing poll completes, the poller pauses for about one second.

When many messages are present, five messages can be processed consecutively in the same poll. This is not a "one second between each message" configuration.

The return value of `send(..., 500)` must be handled by the producer: `false` means it could not be sent within that timeout. Limiting queue capacity creates backpressure at the send point, but the application must still decide whether to wait, reject, or persist the work.

## 6. Using Annotations When Appropriate

If the application declares endpoints with annotations, you can configure the poller directly on a service activator receiving from a pollable channel.

```java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class OrderHandler {

    @ServiceActivator(
            inputChannel = "ordersForAnnotatedHandler",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "1"))
    public void handle(String orderId) {
        System.out.println("Order: " + orderId);
    }
}
```

Declare the corresponding channel in Spring configuration:

```java
@Bean
public QueueChannel ordersForAnnotatedHandler() {
    return new QueueChannel(100);
}
```

In the annotation example, the numeric value `"1000"` of `fixedDelay` is interpreted in milliseconds by default. The string type also allows externalizing the value via placeholders, such as `fixedDelay = "${orders.poll-delay-ms:1000}"`.

This is an alternative configuration approach to the equivalent DSL consumer. If you attach multiple consumers to the same `QueueChannel`, they compete for messages; each message pulled from the queue is delivered to one consumer, not broadcast to all consumers.

## 7. Distinguishing fixed-delay, fixed-rate, and cron

| Scheduling mode | Reference point used for the schedule | Suitable when |
|---|---|---|
| `fixed-delay` | End time of the previous task | You want a pause after each poll |
| `fixed-rate` | Period based on planned start times | You want to maintain a periodic execution cadence |
| `cron` | Time-based schedule expression | You want to run at specific hours, days, or business schedules |

Suppose a task takes 700 ms and the configured interval is 1,000 ms:

- With `fixed-delay`, two consecutive starts are approximately 1,700 ms apart.
- With `fixed-rate`, the target schedule has marks 1,000 ms apart; actual execution timing still depends on the scheduler and task duration.

Do not conclude that `fixed-rate` always produces parallel execution. Concurrency still depends on the scheduling mechanism and executor. Nor conclude that `fixed-delay` always prevents all concurrent processing: asynchronous boundaries can allow the scheduled task to finish before the business work does.

## 8. Parameters That Change Actual Behavior

### 8.1. maxMessagesPerPoll

This parameter limits the number of messages processed in a single poll task execution.

```java
Pollers.fixedDelay(Duration.ofMillis(500))
        .maxMessagesPerPoll(20);
```

If each message takes 50 ms to process synchronously, a full poll of 20 messages takes approximately one second, excluding other overhead. The next poll starts after a 500 ms pause, which is about 1.5 seconds after the previous poll started.

Under conditions where enough data is always available and processing time is relatively stable, you can estimate:

```text
Throughput ≈ N / (N × t + D)
```

Where `N` is the number of messages actually processed per poll, `t` is the average time per message, and `D` is the pause interval; all times use the same unit. This is only a model for a synchronously processing poller, excluding receive wait times, errors, transactions, or resource contention.

Important notes:

- A negative value indicates no message count limit per poll; the poll can continue until the source returns `null`.
- If the source always returns data and the message count is unlimited, the task can run for a very long time without ever reaching the `fixed-delay` pause.
- Do not use `0` to express "unlimited"; that value prevents the poll from processing messages.
- Defaults can differ by endpoint type. Set an explicit limit when batching multiple messages in one poll affects the design.

### 8.2. receiveTimeout

For a polling consumer receiving from a `PollableChannel`, `receiveTimeout` is how long a single receive call can wait for a message.

Suppose:

```text
fixed-delay = 1,000 ms
receiveTimeout = 3,000 ms
maxMessagesPerPoll = 1
```

When the channel is empty, a receive call may wait about three seconds and then return with no message. Only after the task finishes is the one-second pause applied. Two poll start times when idle can therefore be about four seconds apart.

If a message arrives while `receive()` is waiting, it can be picked up immediately during that wait; it does not necessarily have to wait for a new poll schedule.

Do not treat `receiveTimeout` as the overall handler timeout. Nor does it set a timeout for a supplier calling an HTTP API or querying a database. Those operations require their own timeouts on the corresponding client or adapter.

### 8.3. initialDelay

`initialDelay` controls the wait time before the first poll. `fixed-delay` controls the pause between polls. The two parameters serve two different purposes.

Delaying the first poll can be useful when the application needs to wait briefly before starting to fetch data. However, it is not a mechanism to confirm that a dependent system is ready; if readiness is a hard requirement, check that condition explicitly.

### 8.4. Scheduler and Executor

The scheduler decides when the task is triggered. When the poller runs synchronously, calling the source and synchronous downstream processing occupy that task's execution thread. Multiple endpoints sharing a scheduler can affect one another if work runs long and scheduling resources are insufficient.

If you configure a `taskExecutor` on the poller, work can be handed off to the executor:

```java
Pollers.fixedDelay(Duration.ofSeconds(1))
        .maxMessagesPerPoll(1)
        .taskExecutor(pollingExecutor);
```

Here, `pollingExecutor` is a `TaskExecutor` provided by the application, such as a `ThreadPoolTaskExecutor` bean with bounded thread count and queue capacity.

In this configuration, the task run by the scheduler can finish right after handing work to the executor. The pause is measured from the completion of that scheduled task, so the next handoff can occur while previous work is still processing. If the executor allows it, tasks can overlap.

You must evaluate simultaneously:

- Whether the data source and handler are thread-safe under concurrent access.
- Whether message ordering must be preserved.
- The thread count, queue capacity, and rejection policy of the executor.
- Whether producer throughput exceeds sustained consumption capacity.

Increasing scheduler or executor threads does not automatically guarantee ordering, transactions, or exactly-once processing.

## 9. Choosing fixed-delay Based on Business Requirements

### 9.1. Low-Volume Source Tolerating a Few Seconds of Latency

Start with a relatively long pause interval and a small per-poll limit. The goal is to reduce empty checks.

For example: `fixed-delay = 5 seconds`, `maxMessagesPerPoll = 1` for a source that returns results quickly. If lower latency is required, reduce the delay after measuring the cost of accessing the source.

### 9.2. Draining a Backlogged Queue

You can increase `maxMessagesPerPoll` to fetch more messages per poll. In return, a poll holds resources longer, and the impact of errors or transactions can be larger depending on configuration.

For example: a 200 ms delay with up to 50 messages/poll is only suitable when the source and downstream can handle that load. If the source cannot be queried in batches, multiple `receive()` calls can still generate multiple separate source accesses.

### 9.3. External Service with Request Rate Limits

Do not use the reasoning "a one-second delay equals at most one request per second" if:

- One poll processes multiple messages.
- One message triggers multiple requests.
- Retries occur.
- Multiple pollers or multiple application instances exist.
- Asynchronous processing or queued work exists in an executor.

If a shared request limit across instances is needed, you must design a throttling mechanism at the corresponding scope. Each endpoint's `fixed-delay` is only one part of load configuration.

## 10. Errors, Retries, and Transactions

### 10.1. fixed-delay Is Not a Retry Policy

When a handler throws an exception, the endpoint/poller error-handling mechanism decides how the error is forwarded or logged. Polling flows typically use an `ErrorHandler` mechanism and can route errors to an error channel as configured.

The pause interval does not automatically guarantee that a failed message will be picked up again. With an in-memory `QueueChannel`, a message already pulled is not restored by default when the handler fails.

If retries are needed, configure appropriate retry/advice and define attempt limits. When retries run synchronously inside the poll task, the retry time and its backoff waits increase the task duration; the `fixed-delay` pause is applied after the task completes.

### 10.2. Transactions Require Participating Resources

Configuring transactions on a poller can create a transaction boundary around the polling work. Rollback effectiveness depends on the resources, transaction manager, and how components participate in the transaction.

Do not assume that every operation invoked from a poller can be rolled back. For example, an HTTP request already accepted by an external system is not automatically undone simply because a local transaction fails.

For order processing, define separately:

1. When data is considered successfully fetched from the source.
2. When business side effects are recorded.
3. When a message is acknowledged or eligible for replay.
4. How the handler recognizes an already-processed order to limit duplicate side effects.

`fixed-delay` solves the triggering cadence; reliability guarantees require additional design.

## 11. Observing and Testing Behavior

### 11.1. Observing the Right Milestones

To verify the configuration, record at least the start and end times of each poll, the number of messages fetched, processing duration, and thread name. Logs written only when the handler receives a message are not enough to deduce the duration of a poll with multiple messages or multiple empty receives.

Useful metrics include:

| Metric | Helps answer |
|---|---|
| Execution duration per poll | Is the source or downstream prolonging the poll? |
| Number of empty polls | Is the source being checked too frequently? |
| Messages per poll | Is the configured limit being fully utilized? |
| Queue length and message age | Is consumption keeping up with inbound rate? |
| Error count and retry count | Are errors reducing throughput or increasing load? |
| Queued tasks in executor | Is asynchronous work accumulating? |

### 11.2. Test Scenarios to Include

| Scenario | Expected behavior to verify |
|---|---|
| A source returns three messages, limit one message/poll | Each poll fetches at most one message |
| Empty channel and `receiveTimeout = 0` | The check returns quickly and does not invoke the handler |
| Empty channel with a positive receive timeout | Receive wait time is counted in the synchronous poll task |
| Slow synchronous handler | The next poll starts after the previous poll ends plus the pause interval |
| Multi-message-per-poll limit | Messages can be processed consecutively within one poll |
| Handler throws an error | The error-receiving mechanism works and message disposition matches design |
| Dedicated executor | Check for possible overlap and processing order |

For integration tests with real timing, use timeout-aware wait utilities, latches, or appropriate synchronization. Avoid asserting that a run hits an exact millisecond mark, because CI environments can be busy.

If measuring the pause interval, compare the **start time of the next poll** with the **end time of the previous poll**. Comparing only two start times mixes processing time with `fixed-delay`. Use a monotonic clock such as `System.nanoTime()` to measure intervals.

Business logic tests for transformers, filters, routers, or handlers can be run separately with deterministic input messages. Only use scheduler-based tests for behavior that genuinely depends on scheduling to keep the test suite fast and easy to diagnose.

## 12. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "A two-second delay means one message every two seconds" | The pause sits between polls; one poll may have multiple messages or none |
| "Handler takes three seconds, delay is one second, so it still polls every second" | With synchronous processing and one message/poll, two starts are about four seconds apart |
| "Setting a delay guarantees no concurrent processing" | Executors, asynchronous boundaries, and multiple instances can introduce concurrent processing |
| "Delay is a processing timeout" | Delay only determines the pause interval; it does not cancel a slow handler |
| "Reducing delay always increases throughput" | The source or downstream may be the bottleneck; lowering delay may only increase empty checks |
| "A poll with a negative limit will always finish quickly" | A source that always has data can keep the poll running for a long time |
| "An error automatically puts the message back into QueueChannel" | Recovery depends on source type, transactions, and error-handling mechanisms |

## 13. Practice Exercise

Design a flow with a `QueueChannel`, a transformer that normalizes order codes, and a handler that records results into a thread-safe list.

1. Configure the poller with a 500 ms pause, at most two messages per poll, and no waiting when the channel is empty.
2. Send five messages into the channel before starting observation.
3. Record the polls that had data. With a single consumer and no errors, at least three non-empty polls are needed to process all five messages.
4. Make each synchronous processing step take around 200 ms. Predict that a full poll of two messages takes about 400 ms and two consecutive start times are about 900 ms apart, excluding other overhead.
5. Lower the limit to one message/poll and compare the latency of the last message.
6. Add an asynchronous boundary and observe why the completion time of the poll task no longer means all business processing has finished.

After the exercise, you should be able to explain three distinct factors: the pause interval between polls, the amount of work per poll, and the scope of synchronous processing. These three factors determine how `fixed-delay` affects the latency, throughput, and load of a Spring Integration flow.