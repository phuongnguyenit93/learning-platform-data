# max-messages-per-poll

## 1. Limiting Work Within a Single Poll

In the **Poller** chapter of the **SPRING_INTEGRATION_CORE** module, `max-messages-per-poll` helps control the amount of work a polling endpoint performs each time it is triggered. This property connects directly to three core components of Spring Integration:

- `MessageSource` provides messages for an inbound channel adapter using a polling mechanism.
- `PollableChannel`, such as `QueueChannel`, holds messages for a polling consumer to actively receive.
- The endpoint performs the receive operation and hands the message into the processing flow, where a transformer, filter, router, or service activator continues the work.

The property name in XML is `max-messages-per-poll`; in the Java DSL it is `maxMessagesPerPoll(...)`.

Suppose a `QueueChannel` currently holds 20 messages. The poller runs with `fixedDelay = 1,000 ms` and `maxMessagesPerPoll = 5`. When there are no errors, no competing consumers, and nothing blocking receives, a single poll fetches and dispatches up to 5 messages to the endpoint for processing. If the queue only has 2 messages left, that poll stops after processing them and encountering a receive with no data.

**This is an upper bound for a single poll, not a mandatory number of messages to process and not a queue size limit.**

## 2. One Trigger Firing Can Receive Multiple Messages

You must distinguish the poller's trigger schedule from the message-receiving loop inside each firing:

```text
Trigger fires one poll
    |
    +-- Receive message 1 -> process/forward
    +-- Receive message 2 -> process/forward
    +-- ...
    +-- Stop when limit is reached or no message is received
```

You can picture it with the following pseudocode. This is not the framework's source code:

```java
void runOnePollingTask() {
    long processed = 0;

    while (endpointIsRunning()
            && (maxMessagesPerPoll < 0 || processed < maxMessagesPerPoll)) {
        Message<?> message = receiveOneMessage();

        if (message == null) {
            break;
        }

        processOrForward(message);
        processed++;
    }
}
```

The pseudocode illustrates the success path. Advice, transactions, errors, lifecycle state, and executor configuration can affect actual execution. If a receive or processing step throws an exception outward, do not assume the remaining messages in that poll are guaranteed to continue being processed.

In a synchronous flow over `DirectChannel`, downstream processing time typically falls within the poll's duration. If the message is handed off through an `ExecutorChannel` or another asynchronous boundary, the poller may finish its handoff before downstream business work finishes.

## 3. Meaning of the Values

| Value | Behavior in each poll | What to note |
|---|---|---|
| Positive number, e.g. `1`, `5`, `20` | Performs at most that many successful receives and processing cycles, stopping early when no message is available | Suitable when work per poll must be bounded |
| `0` | Does not perform message receiving during the poll | Not equivalent to stopping the endpoint's lifecycle |
| Negative number, typically `-1` | No count-based message limit; continues until a receive has no data or the poll is interrupted by another condition | Can run for a very long time if the source continuously produces data |

### 3.1. Value `1`

Each poll processes at most one message. This configuration is easy to observe and creates frequent boundaries between polls, though when many messages back up, queue draining capacity can be low if the pause interval is large.

### 3.2. Positive Values Greater Than `1`

One poll can receive multiple messages consecutively without waiting for the next trigger between individual messages. However, if the first receive returns `null`, that poll ends immediately; the poller does not try to call receive the full configured number of times.

Nor does a value of `10` tell the poller to wait until the queue accumulates 10 messages before starting.

### 3.3. Value `0`

`0` skips message receiving. The endpoint's schedule may remain active while each poll fetches no data. When you need to stop an endpoint operationally, use the appropriate lifecycle mechanism and clearly distinguish that intent from setting a limit of `0`.

### 3.4. Negative Values

`-1` does not mean processing negative one messages. It indicates no count limit inside the polling loop.

In particular, a source that always returns a new message can prevent a poll from finishing in the normal way. In that case, the `fixedDelay` pause never gets a chance to start because the current poll has not finished.

## 4. Distinguishing the Two Endpoint Types and Default Values

Do not infer from the word "poller" that all endpoints share the same default value.

| Case | Typical endpoint | Receive operation | Default when not overridden |
|---|---|---|---|
| Inbound channel adapter reading a source | `SourcePollingChannelAdapter` | `MessageSource.receive()` | `1` |
| Consumer reading a pollable channel | `PollingConsumer` | `PollableChannel.receive(...)` | `-1` |

The inbound adapter uses a default of `1` because many `MessageSource` implementations can generate data on every call. For example, a supplier generating a new timestamp will not return `null` on its own to signal end of data. If this source ran unbounded within one poll, it could emit continuously in that single poll.

A polling consumer on a `QueueChannel` can drain multiple messages in one poll. With a negative value, a poll normally ends when the queue has no data left and the receive operation gets no message within the wait timeout.

The values in the table are defaults by endpoint type; a shared poller or explicit configuration can alter the final behavior. In learning examples and configurations requiring load control, set the value explicitly rather than relying on defaults.

`DirectChannel` delivers messages directly to subscribers, so consumers on this channel do not need a poller to receive. The attribute being studied belongs to polling endpoints, not as a general limit option for every `MessageChannel`.

## 5. Java DSL: Fetching at Most Three Messages from QueueChannel

The example below creates a standalone configuration to observe how a polling consumer reads a `QueueChannel`. Each message is converted to uppercase and sent to the result queue.

Assume the application already has compatible Spring Context and Spring Integration Core dependencies. If using Spring Boot, place the configuration in an application with Spring Integration infrastructure enabled; there is no need to manually create an extra context as in the demo runner below.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class BoundedPollerConfig {

    @Bean
    public QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel resultQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow boundedFlow() {
        return IntegrationFlow.from(workQueue())
                .bridge(endpoint -> endpoint
                        .id("boundedBridge")
                        .autoStartup(false)
                        .poller(
                        Pollers.fixedDelay(1000)
                                .maxMessagesPerPoll(3)
                                .receiveTimeout(0)))
                .<String, String>transform(
                        value -> value.toUpperCase(Locale.ROOT))
                .channel(resultQueue())
                .get();
    }
}
```

In this example:

- `workQueue()` is a `PollableChannel`, so the bridge endpoint receiving input requires a poller.
- `autoStartup(false)` keeps the endpoint stopped so the demo program can preload data first; the program then calls `start()` explicitly. When deploying a normal auto-starting flow, you can omit this option.
- `fixedDelay(1000)` configures a 1,000 ms pause measured from when the previous poll completes in the synchronous execution illustrated here.
- `maxMessagesPerPoll(3)` limits one poll to receiving at most three messages.
- `receiveTimeout(0)` makes queue receives return immediately if the queue is empty.
- The transformer and sending to `resultQueue()` run synchronously in this flow.
- The queue capacity of `100` is an independent configuration from the poller's limit of `3`.

Do not place the poller on the downstream transformer just because you want "group processing." In the configuration above, the bridge is the endpoint receiving from the queue; placing the poller there is what controls draining the queue.

### 5.1. Running with Preloaded Data

The bridge endpoint above has `autoStartup(false)`, so the context can initialize completely while the poller has not yet received data. The program loads seven messages, then starts that specific endpoint via the `Lifecycle` interface.

```java
import java.util.List;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BoundedPollerDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                BoundedPollerConfig.class)) {
            QueueChannel input = context.getBean("workQueue", QueueChannel.class);
            QueueChannel output = context.getBean("resultQueue", QueueChannel.class);

            for (String value : List.of("a", "b", "c", "d", "e", "f", "g")) {
                boolean sent = input.send(
                        MessageBuilder.withPayload(value).build(), 0);
                if (!sent) {
                    throw new IllegalStateException("Failed to load sample data");
                }
            }

            context.getBean("boundedBridge", Lifecycle.class).start();

            for (int i = 0; i < 7; i++) {
                Message<?> message = output.receive(5000);
                if (message == null) {
                    throw new IllegalStateException("Timed out waiting for result");
                }
                System.out.println(message.getPayload());
            }
        }
    }
}
```

The seven results will be `A` through `G`. Under the example's conditions, the work limits of the non-empty polls are `3 + 3 + 1` respectively. Actual print times also depend on the scheduler and system load; do not treat absolute timestamps as a poller contract.

## 6. Java DSL: Limiting a MessageSource Poller

The configuration snippet below separately illustrates an inbound channel adapter. Assume `externalBuffer` and `sourceOutput` are beans used for this flow, independent of the previous example.

```java
@Bean
public java.util.concurrent.BlockingQueue<String> externalBuffer() {
    return new java.util.concurrent.LinkedBlockingQueue<>();
}

@Bean
public org.springframework.integration.core.MessageSource<String> bufferedSource(
        java.util.concurrent.BlockingQueue<String> externalBuffer) {

    return () -> {
        String value = externalBuffer.poll();
        if (value == null) {
            return null;
        }
        return org.springframework.messaging.support.MessageBuilder
                .withPayload(value)
                .build();
    };
}

@Bean
public QueueChannel sourceOutput() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow sourceFlow(
        org.springframework.integration.core.MessageSource<String> bufferedSource) {

    return IntegrationFlow.from(bufferedSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(5)))
            .channel(sourceOutput())
            .get();
}
```

Each poll calls the source up to five times to fetch up to five messages. If `externalBuffer.poll()` returns `null`, `MessageSource` also returns `null`, signaling the adapter to end the poll early.

Because the source uses `BlockingQueue.poll()` without a timeout argument, the fetch operation is non-blocking. The `receiveTimeout` of a poller reading a `PollableChannel` is not a way to control the internal timeout of an arbitrary source; wait times for reading files, HTTP, JDBC, or buffers depend on the implementation and configuration of the corresponding source.

If you modify `bufferedSource` into a source that always generates new data, keep a positive limit so each poll has a clear stopping point.

## 7. Do Not Confuse with Business Batches and Payload Element Counts

`maxMessagesPerPoll` counts messages received by the polling endpoint; it does not count elements inside payloads.

| Received data | With `maxMessagesPerPoll(3)` |
|---|---|
| Each message contains one order code | Receives at most three messages, corresponding to at most three codes |
| Each message contains a `List<Order>` with 100 orders | Receives at most three messages; payloads may contain 300 orders total |
| One message is split by a splitter into 20 messages | One receive at the poller can lead to 20 downstream messages |
| Multiple messages are grouped by an aggregator | Output message count is determined by the release strategy |

This property does not build a `List` from multiple messages, does not set a release strategy for an aggregator, and does not create group commit boundaries. If the business requirement is "write to the database in batches of 50 orders," design the grouping, persistence, and transactions accordingly.

Similarly, if a JDBC adapter reads multiple rows in a single query and packages them into one message, the poller's message limit and the query's row limit are two separate configurations.

## 8. Relationship with Schedule, Timeout, and Throughput

### 8.1. Fixed Delay Is Not Time Between Individual Messages

Suppose each message takes 40 ms of synchronous processing, `maxMessagesPerPoll = 5`, and `fixedDelay = 1,000 ms`:

```text
Poll 1: [m1 40ms][m2 40ms][m3 40ms][m4 40ms][m5 40ms]
        <--------------- approx. 200ms --------------->
                                                        pause 1000ms
                                                                    Poll 2...
```

Ignoring overhead and other waits, throughput is approximately:

```text
Throughput ≈ M / (M × T + D)

M: actual number of messages processed per poll
T: average processing time per message, in seconds
D: fixed delay, in seconds
```

With `M = 5`, `T = 0.04`, and `D = 1`, the result is around `4.17 messages/second` when the source always has enough data. Simply configuring five messages with a one-second delay does not guarantee five messages/second.

The formula only fits a simple synchronous model. Executors, parallel processing, channel send waits, advice, and system load can alter the model.

### 8.2. Receive Timeout Affects Poll Duration

For a poller reading `QueueChannel`, if two messages have been fetched but the limit is ten, the next receive call may wait up to `receiveTimeout`. The poll only finishes after that receive finds no data and returns `null`.

Thus, a poll's duration can include wait time when the queue is empty. Setting a long timeout combined with fixed delay can increase the time before the next poll.

If ten messages have already been received, the loop stops at the limit; an eleventh receive is not needed merely to determine whether the queue still has data.

### 8.3. Fixed Rate and Task Executor

Switching to `fixedRate` does not turn this limit into a per-second message quota. The trigger determines the schedule; the limit determines the maximum work within each polling task.

When a `taskExecutor` is present, distinguish when the scheduler submits the task from when the task actually runs and finishes. Pools, executor queues, and task rejection policies can cause multiple polls to wait or gain opportunities to run concurrently. Do not infer concurrency levels solely from `maxMessagesPerPoll`.

Nor does a limit of `10` create ten threads. A normal poll loops through receives sequentially; concurrent processing capability depends on execution configuration and downstream channels.

## 9. Errors, Transactions, and Reprocessing

If the second message causes an error when the limit is five, do not deduce that all five messages belong to one retry unit or are rolled back together.

Identify separately:

1. Whether the error occurs when reading the source, invoking the handler, or handing off to another channel.
2. What advice or transactions the poller and handler have.
3. Whether the source or channel participates in transactions and supports message recovery.
4. Whether the flow has an asynchronous boundary.
5. Which error channel receives the error and whether any reprocessing mechanism exists.

In particular, the in-memory `QueueChannel` in the example does not automatically restore the just-pulled message if the transformer throws an exception. Setting `maxMessagesPerPoll(3)` does not create an exactly-once processing guarantee or a replay guarantee.

For a poller with transaction advice, inspect the actual advice scope and participating resources. Do not rely on the limit value alone to claim a transaction spans each message or the entire poll. If downstream switches to another thread, the transaction bound to the current thread does not automatically follow the message to that thread.

## 10. Choosing a Value Based on Workload Characteristics

One way to start is to set a small positive limit, measure backlog and poll duration, and then adjust based on actual load.

| Symptom | What to examine |
|---|---|
| Queue grows steadily while handler still has capacity | Increase the limit or decrease the pause interval after measuring |
| A single poll runs very long | Lower the limit; check downstream latency and timeouts |
| Source continuously generates messages | Use a positive limit so polls can finish |
| External system gets flooded with requests | Reduce receives per poll and also check concurrency, retries, and rate limiting |
| Payload sizes vary widely | Track item/byte counts and processing time, not just message count |
| Scheduler is held long, delaying other endpoints | Check scheduler pool and thread occupancy time; consider an appropriate executor |

For example, a synchronous flow calls an external API taking about 200 ms per message. If you want message processing in one poll to stay around one second, you can start by trying a limit of five. This is a starting point for measurement, not a real-time guarantee because API latency can fluctuate.

If the API allows at most 100 requests per minute, limiting messages per poll does not automatically enforce that quota. Multiple instances, retries, splitters, or parallel processing can all increase actual request count. When a time-window quota is needed, a corresponding throttling mechanism must be in place.

## 11. Behavior Verification Scenarios

The following scenarios are for practicing observation or writing dedicated tests for your application configuration; this lesson does not claim to have run them in a repository.

| Scenario | Result to verify |
|---|---|
| Preload 7 messages, limit 3 | Non-empty polls process per the `3 + 3 + 1` limit if no other factors intervene |
| Preload 2 messages, limit 10, timeout 0 | Two messages are forwarded; the next receive has no data and ends the poll |
| Empty queue, timeout 0 | The poll produces no output message and finishes quickly |
| Limit 0 | The queue is not drained by the poller |
| Finite source, limit -1 | One poll can drain all available data until the source returns `null` |
| One message containing a list of 100 items, limit 1 | The poller receives one message; the payload still holds 100 items |
| Handler throws an exception | Verify the error path and recovery behavior per actual configuration |

To verify per-poll boundaries, attach observation at the source or endpoint and control the trigger in tests. Simply counting total messages after a few seconds does not prove each poll obeyed the limit. Avoid tests relying solely on `Thread.sleep()` and expecting an exact count at a short timestamp because the scheduler can be delayed.

For the Java DSL example, you can check output payloads and result count using `QueueChannel.receive(timeout)` with a bounded wait. That check verifies the flow transferred all data; to specifically verify the `3 + 3 + 1` cadence, additionally observe individual poll boundaries.

## 12. Key Takeaways

`max-messages-per-poll` caps the number of messages a polling endpoint receives and processes/forwards in each poll. A positive limit creates a count-based stopping point; `0` skips receiving; a negative value continues until the source or channel provides no message or another termination condition occurs.

When designing a Spring Integration flow, identify whether the endpoint reads a `MessageSource` or a `PollableChannel`, where synchronous/asynchronous boundaries sit, wait timeouts, and payload characteristics. Only by combining those factors can you explain the actual impact of the limit on latency, throughput, and downstream load.