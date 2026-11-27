# @InboundChannelAdapter for Polling Sources

## 1. Context and Objectives

In the **Integration Flow Creation** chapter, `@InboundChannelAdapter` is a way to declare a **polling-based entry point (inbound endpoint)** using a Spring Integration annotation. When a data source does not proactively push events to the application, the endpoint periodically calls a `MessageSource`, receives a message if data is available, and sends it to a `MessageChannel` for the rest of the integration flow to process.

This lesson belongs to the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing data exchange over files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and controlling message contracts, errors, and connection lifecycles.

After this lesson, learners should be able to:

- Distinguish between `@InboundChannelAdapter`, `MessageSource`, `@Poller`, and `MessageChannel`.
- Create an inbound endpoint using `@Bean` combined with `@InboundChannelAdapter`.
- Understand how each poll invokes `receive()`, including when no data is available.
- Configure `fixedDelay`, `fixedRate`, `cron`, and `maxMessagesPerPoll` according to source and destination characteristics.
- Connect the adapter to a processing flow using the Java DSL, and apply it to file sources or similar polling sources.
- Design error handling, deduplication, start/stop lifecycle, and observability for the endpoint.

**Core point:** `@InboundChannelAdapter` registers an endpoint that pulls data from a source on a schedule. **It does not itself define how to read files, SFTP, or databases**; reading is implemented by the `MessageSource` instance returned by the method.

## 2. How Inbound Polling Works

A polling flow typically consists of four parts with clear responsibilities:

~~~mermaid
flowchart LR
    TIMER["TaskScheduler / Poller"]
    ADAPTER["@InboundChannelAdapter<br/>calls MessageSource.receive()"]
    SOURCE[("Source: file, SFTP,<br/>database, queue...")]
    CH["MessageChannel"]
    FLOW["Filter → Transform → Handle<br/>or outbound adapter"]
    TIMER -->|"Scheduled trigger"| ADAPTER
    ADAPTER <-->|"Reads data"| SOURCE
    ADAPTER -->|"Message<T> if available"| CH
    CH --> FLOW
~~~

| Component | What does it do? | What is it not responsible for? |
| --- | --- | --- |
| `MessageSource<T>` | Defines how to fetch **one message** per `receive()` call; may return `null`. | Does not schedule its own execution. |
| `@InboundChannelAdapter` | Turns a `MessageSource` bean into a polling inbound endpoint; specifies the channel and poller. | Does not directly replace the source's data-reading rules. |
| `@Poller` | Specifies when to poll and the maximum number of messages to receive per poll cycle. | Does not guarantee durable message storage or exactly-once processing. |
| `MessageChannel` | Delivers messages from the adapter to downstream consumers or flows. | Does not automatically create a consumer to receive messages. |
| `IntegrationFlow` / handler | Validates, transforms, routes, writes to destination, returns results, or handles errors. | Does not automatically generate data from a source without an adapter/gateway. |

In the typical sequence:

1. Spring initializes the `MessageSource` bean and the annotated endpoint.
2. The poller fires on schedule; each trigger calls `MessageSource.receive()`.
3. If the result is a `Message<?>`, the endpoint sends it to the configured channel. With `maxMessagesPerPoll > 1`, the endpoint may invoke `receive()` multiple times within the same poll cycle.
4. If `receive()` returns `null`, there is no message at that moment; the current poll cycle ends, while the polling schedule continues.
5. The consumer receives the message via the channel and executes the flow according to the channel's synchronous or asynchronous semantics.

`null` means *no data available right now*, which is distinct from throwing an exception when reading the source or failing to send a message. This is an important contract when writing a custom `MessageSource`.

## 3. Preparing Spring Integration

The examples use Java 17+, Spring Boot, and Spring Integration with Spring Boot dependency management. In Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Key imports used in the code examples:

~~~java
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
~~~

A Spring Boot project using the starter usually auto-configures Spring Integration; the example below explicitly declares `@EnableIntegration` to make the framework's role visible. **Do not also use `@Scheduled` to call `receive()`**, because the endpoint already has its own poller.

In its common form, the configuration method has the following structure:

~~~java
@Bean
@InboundChannelAdapter(
        value = "data.input",
        poller = @Poller(fixedDelay = "5000", maxMessagesPerPoll = "1"))
MessageSource<MyPayload> dataSource() {
    return () -> /* return Message<MyPayload> or null */;
}
~~~

The snippet above is a **signature template**, where `MyPayload` is an application-defined data type; the expression after `return` will be implemented in the runnable example in section 4. The annotation is placed on the **method returning `MessageSource`**, not on a message-handling method.

## 4. Runnable Example: Polling a Task Queue

To observe the flow without installing a message broker or SFTP server, we use an in-memory queue. The queue initially contains three job codes. Each time it is polled, the source pulls at most one message per `receive()` call; the poller can take up to two messages per poll cycle.

Place the following code in `PollingDemoApplication.java`, package `demo.integration`.

~~~java
package demo.integration;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class PollingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PollingDemoApplication.class, args);
    }

    @Bean(name = "jobs.input")
    MessageChannel jobsInputChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            value = "jobs.input",
            poller = @Poller(
                    fixedDelay = "2000",
                    maxMessagesPerPoll = "2"))
    MessageSource<String> jobSource() {
        Queue<String> pending = new ConcurrentLinkedQueue<>(
                List.of("JOB-001", "JOB-002", "JOB-003"));

        return () -> {
            String next = pending.poll();
            if (next == null) {
                return null;
            }

            return MessageBuilder.withPayload(next)
                    .setHeader("source", "memory-queue")
                    .build();
        };
    }

    @Bean
    IntegrationFlow jobProcessingFlow() {
        return IntegrationFlow.from("jobs.input")
                .filter(String.class, job -> job.startsWith("JOB-"))
                .handle(String.class, (job, headers) -> {
                    System.out.println("Processing: " + job
                            + " (source=" + headers.get("source") + ")");
                    return null; // end of one-way flow
                })
                .get();
    }
}
~~~

### 4.1. Explaining Each Connection Point

- `@Bean(name = "jobs.input")` declares a `DirectChannel` with an explicit name. Both the adapter and the flow reference this exact name.
- `@InboundChannelAdapter(value = "jobs.input", ...)` creates an endpoint that sends messages to that channel.
- `jobSource()` is only called by Spring to **create the source bean**. After startup, the poller calls `receive()` on the source (the returned lambda), rather than periodically re-invoking the `jobSource()` factory method.
- `Queue.poll()` retrieves and removes an item from memory; if the queue is empty, it returns `null`.
- `MessageBuilder` builds a `Message<String>` with the job code as payload and a `source` header.
- `IntegrationFlow.from("jobs.input")` attaches a consumer to the channel. `filter` allows only codes prefixed with `JOB-` through; `handle` logs and returns `null` because this is a one-way flow.

### 4.2. What Happens When the Application Runs?

Assuming no processing step is slow and the poll schedule fires normally:

~~~text
Poll cycle 1:
  receive() -> Message("JOB-001") -> jobs.input -> handler
  receive() -> Message("JOB-002") -> jobs.input -> handler

Poll cycle 2:
  receive() -> Message("JOB-003") -> jobs.input -> handler
  receive() -> null                -> end of poll cycle

Subsequent poll cycles:
  receive() -> null                -> no new messages
~~~

`maxMessagesPerPoll = "2"` is the **limit on messages per trigger**, not a batch size packed into a single message. Each message still carries one `String` payload and its headers. Because the source starts with only three jobs, there will be no further output afterward, though the poller continues firing periodically.

**Reliability warning for this demo:** `Queue.poll()` removes the item from the queue before the handler finishes. If the handler throws an exception, the in-memory queue in this example does not put the item back automatically. Do not use this pattern as a reliable queue in production; real systems need proper processing acknowledgements, durable storage, retries, and idempotency.

## 5. Understanding @Poller Parameters

`@Poller` describes the endpoint's polling schedule. Common attributes include:

| Attribute | Meaning | When to Use |
| --- | --- | --- |
| `fixedDelay = "5000"` | A 5-second delay after one execution finishes before the next begins. | Sources that must avoid overly frequent scans; variable processing durations. |
| `fixedRate = "5000"` | Aims to trigger every 5 seconds from the start time; actual timing depends on the scheduler. | When steady frequency is needed and processing time and concurrency are controlled. |
| `cron = "0 */5 * * * *"` | Triggers at second 0, every 5 minutes using Spring cron syntax. | Sources that need scanning on a specific wall-clock schedule. |
| `initialDelay = "1000"` | Delays the first poll by roughly 1 second when used with a compatible trigger. | Giving dependent components time to become ready. |
| `maxMessagesPerPoll = "10"` | Up to ten messages fetched per cycle; if `receive()` returns `null` early, the cycle stops early. | Bounding the amount of work per trigger. |

String time values in the examples use milliseconds under standard configuration. In Spring Integration versions that support explicit time units, you can specify units explicitly to avoid confusion. Verify against your actual framework version before copying settings into another project.

The two configuration snippets below illustrate **mutually exclusive alternatives** (each adapter picks one appropriate schedule):

~~~java
@Poller(fixedDelay = "5000", maxMessagesPerPoll = "10")
~~~

~~~java
@Poller(cron = "0 */5 * * * *", maxMessagesPerPoll = "50")
~~~

Do not mix `fixedDelay`, `fixedRate`, and `cron` on the same poller when you only want a single trigger schedule.

### 5.1. Polling Rate Does Not Equal Processing Throughput

With the `DirectChannel` in the example, sending a message usually executes the consumer on the poller's own thread. If a handler calls a slow API that takes 4 seconds per message, a poll cycle receiving two messages can take at least around 8 seconds, followed by the `fixedDelay` interval before the next cycle. Thus **polling every 2 seconds does not mean two messages are completed every 2 seconds**.

When the target is slow, consider bounding `maxMessagesPerPoll`, external call durations, timeouts, concurrency limits, bounded queues, and load-shedding mechanisms. If you offload processing to an `ExecutorChannel` or a broker, thread boundaries, transactions, and source acknowledgements also change; design a dedicated error path accordingly.

### 5.2. Choosing Messages per Poll

Use a small limit when the target is load-sensitive or business logic has slow side effects. Increase the limit when reading many short records with lightweight processing. Do not set a very large value and expect the scheduler to remain fair across endpoints: one long poll cycle can hold resources for a long time and starve other tasks.

## 6. Real-World Scenario: @InboundChannelAdapter Reading CSV Files

For file sources, Spring Integration provides `FileReadingMessageSource`. Rather than writing a custom directory-checking lambda, configure this message source and attach a polling schedule. Additional dependency required:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

The configuration example below lives in `CsvFilePollingConfiguration.java` in the application:

~~~java
package demo.integration;

import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
class CsvFilePollingConfiguration {

    @Bean(name = "files.input")
    MessageChannel filesInputChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            value = "files.input",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "5"))
    MessageSource<File> csvFileSource() {
        var source = new FileReadingMessageSource();
        source.setDirectory(new File("./inbox"));

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    @Bean
    IntegrationFlow csvFileFlow() {
        return IntegrationFlow.from("files.input")
                .handle(File.class, (file, headers) -> {
                    System.out.println("Detected CSV file: "
                            + file.getAbsolutePath());
                    return null;
                })
                .get();
    }
}
~~~

Create the `./inbox` directory before starting the application; this path is relative to the process's working directory. Each message from the source has a **`File` payload**. The example handler only logs the path and does not open or parse the CSV contents yet.

There are **two distinct filter layers** here:

1. `SimplePatternFileListFilter("*.csv")` is a **file-list** filter deciding which files enter the source.
2. `AcceptOnceFileListFilter` reduces re-emitting the same file while the application is running. This filter relies on in-memory state and does not guarantee deduplication across restarts.
3. `.filter(...)` in `IntegrationFlow` (if added) filters **already emitted messages**, and does not replace source-level file filtering.

When moving to production, add mechanisms to detect completed file writes, handle malformed files, move files to processed/quarantine folders, and persist read state if deduplication across restarts is required.

### 6.1. Why Not Just Use @Scheduled and Send Manually?

You can write `@Scheduled` code to read files and send them to a `MessageChannel`, but when using Spring Integration, `@InboundChannelAdapter` directly expresses the **source → poller → channel** lifecycle. The framework manages the endpoint and lets you configure pollers, channels, advice, metrics, and error handling consistently with other adapters.

A custom `@Scheduled` task may be fine for simple background jobs; however, when building an integration flow, `@InboundChannelAdapter` separates the **data source** from **message processing steps** much more cleanly.

## 7. Placing @InboundChannelAdapter in Integration Architecture

### 7.1. Which Sources Fit Polling?

| Source | Suitable for inbound polling? | Notes |
| --- | --- | --- |
| Files in a directory | Yes. | Use `FileReadingMessageSource`, filters, and a file-state strategy. |
| Remote SFTP directory | Yes. | Requires SFTP adapter/module plus synchronization/file selection, sessions, and reconnect handling. |
| Database | Yes, if querying new rows via a watermark. | Requires queries, checkpoints, transactions, and duplicate prevention. |
| REST API supporting periodic fetch only | Possible, via a custom source/service. | Must enforce rate limits, timeouts, pagination, retries, and result caps. |
| Incoming HTTP requests to the app | Usually no. | Use an HTTP inbound gateway to receive pushed requests. |
| JMS/AMQP/Kafka consumers | Usually prefer listener/message-driven adapters. | Brokers have native delivery/ack semantics; avoid replacing listeners with generic pollers without reason. |

In the `SPRING_INTEGRATION_ADAPTERS` module, the commonality across sources is that once an adapter emits a `Message<?>`, the transform, route, and outbound parts in the Java DSL can be reused. The differences lie in **how data is received, state durability, and processing acknowledgements** for each protocol.

### 7.2. Inbound Adapter vs. Gateway

- **Inbound adapter:** receives data and sends messages inward into the application. There is no expectation of returning a direct response to the origin.
- **Inbound gateway:** receives a request and typically needs to send a response back to the corresponding caller (for example, HTTP).
- **Outbound adapter:** receives messages from a flow to send one-way to a target system.
- **Outbound gateway:** sends a request from a flow to a target system and returns the reply back into the flow.

A file source or database poller is typically an inbound adapter. For an HTTP server API receiving requests and returning JSON, an inbound HTTP gateway is more appropriate.

## 8. Message Contracts and Correctness When Reading Sources

`MessageSource<T>` determines the payload and headers of messages at the integration boundary. Agree on the contract before running the flow:

| Contract Element | Example | Rationale |
| --- | --- | --- |
| Payload type | `File`, `OrderEvent`, or `List<Row>`. | Consumers know the expected type and handling behavior. |
| Source identifier | `sourceSystem = "sftp-a"`. | Error categorization and source traceability. |
| Business identifier | `eventId` or `orderId`. | Idempotency and reconciliation. |
| Timestamps | `eventTime` and ingestion timestamp. | Tracking latency and late-arriving data. |
| Read checkpoint | Offset, monotonic ID, updated timestamp. | Recovery after restarts; preventing skipped or duplicate reads. |
| Malformed input handling | Coded errors, quarantine, alerts. | Preventing invalid data from reaching destination writers. |

If a single source API call returns 100 records and the source creates **one message holding a list of 100 records**, `maxMessagesPerPoll = "10"` still means at most **10 messages**, not 10 records. To make each record a separate message, either change the source to emit one record at a time or add a splitter step, then decide how errors and acknowledgements correlate.

### 8.1. Safe Polling Across Errors and Restarts

Distinguish three milestones:

1. **Read from source:** the file/record/event was fetched or observed.
2. **Delivered to channel:** the message was handed off to the next component.
3. **Business processing succeeded:** data was written to the target, acknowledged, and is reconcilable.

These three events **do not automatically happen inside the same transaction**. For example, an in-memory queue can lose an item if `poll()` succeeds but the handler throws. An API may return the same event again on retry even though the earlier event was already persisted. A partially written file might be read too early.

Depending on the source, implement post-success checkpoints, timely acknowledgements, error holding areas, and idempotency keys at the destination. Exactly-once semantics cannot be guaranteed by `@InboundChannelAdapter` or `maxMessagesPerPoll` alone.

## 9. Error Handling in Polling Flows

With a synchronous `DirectChannel`, handlers typically run on the poller's thread. If a handler throws an exception, sending the message can fail immediately within that poll cycle. In asynchronous poller configurations, the framework may publish an `ErrorMessage` to a configured error channel. Exact error propagation and retry behavior depend on the channel, scheduler, advice, and endpoint configuration.

### 9.1. Classifying Errors

- **No data available:** `receive() == null`, not an error; no immediate retry needed.
- **Source unreachable:** SFTP connection drop, database timeout, file permissions. Record the cause, apply backoff, and alert if prolonged.
- **Malformed message:** payload violates the contract; move to quarantine or emit a reconcilable business error.
- **Destination processing failure:** broker disconnect, API error, database write failure. Consider bounded retries, idempotency, and dead-letter queues.
- **Indeterminate outcome:** the target may have persisted the write, but the response was lost. Avoid blind retries if the operation has non-idempotent side effects.

### 9.2. Placing Retry Policies at the Right Layer

For example, SFTP authentication failures should be retried at the connection/source layer. Reading a CSV file where line 27 violates the schema should be handled at the validation and quarantine layer. Sending an order to a target that timed out requires querying the target or using an idempotency key before writing again.

The poller running again **does not mean** the failed record is automatically retried; if the record was already marked consumed, the next poll cycle may no longer see it. This is why separating source state, message dispatch, and success acknowledgement is critical.

## 10. Endpoint Lifecycle, Threading, and Observability

Spring Integration initializes poller endpoints along with the application context and manages them through the framework's lifecycle mechanism. In multi-instance deployments, all instances may poll the same source simultaneously unless coordination, partitioning, or locking is in place. Explicitly choose a single-consumer, competing-consumers, or partitioned model during design.

In production setups, monitor at least:

- Last poll timestamp, empty-poll count, and interval drift between polls.
- Counts of messages read, sent to channels, succeeded, and failed.
- `receive()` duration, handler duration, and external system timeouts.
- Source rate vs. destination rate, queue depth, retry counts, and quarantined item counts.
- Endpoint start/stop state, connection errors, thread pools, and connection/session pools.

Avoid logging full payloads containing sensitive data. Use IDs or correlation IDs to link adapter logs with handler logs, and log only necessary metadata.

### 10.1. Polling Across Multiple Instances

If two instances scan the same directory or database table without coordination, both can pick up the same record. Filters that keep state only in each instance's memory will **not** prevent duplicates across two processes. Use partitioning, distributed locks, record claiming, or a durable state repository.

When shutting down the application, separately account for **stopping new poll triggers**, **draining in-flight messages**, and **closing sessions/connections**. Asynchronous channels or buffers may still hold pending messages after the scheduler stops.

## 11. Testing Polling Sources and Endpoints

To test `MessageSource` logic, you can call `receive()` directly in a controlled manner without waiting for a scheduler. Below is a JUnit 5 test for the example class in section 4:

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.integration.core.MessageSource;

class JobSourceTest {

    @Test
    void returnsThreeMessagesThenNull() {
        MessageSource<String> source =
                new PollingDemoApplication().jobSource();

        assertEquals("JOB-001", source.receive().getPayload());
        assertEquals("JOB-002", source.receive().getPayload());
        assertEquals("JOB-003", source.receive().getPayload());
        assertNull(source.receive());
    }
}
~~~

This test only verifies the **source contract**: returning three messages and then `null`. It does not prove the `@Poller` schedule or that the flow is registered by Spring, because the bean is instantiated directly outside the context.

To test the entire path, add an integration test that boots the Spring context, attaches a verifying consumer to the output channel or inspects the final outcome, and waits for messages using test synchronization utilities rather than fixed `Thread.sleep()` calls. For file sources, use a temporary directory, place one valid `.csv` file and one invalid file, verify the source only emits the target file, and then test restarts to observe the limits of in-memory filters.

JUnit/Spring Boot test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

In this lesson, you do not need to start a real SFTP server or database to verify `receive()` logic. When testing protocol boundaries, write dedicated tests for reconnects, acknowledgements, network errors, restarts, and duplicates.

## 12. Common Pitfalls

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| No messages appear from adapter. | `receive()` always returns `null`; mismatched channel name; endpoint not started. | Add bounded logging at the source, verify channel names, and check endpoint lifecycle. |
| App polls source continuously and overloads it. | Interval too short or too many messages fetched per cycle. | Adjust trigger interval, poll limits, latency handling, and backpressure. |
| Only one message seen despite many records in payload. | Source packs an entire batch into one `Message<List<?>>`. | Review the source contract; split messages with a splitter if needed. |
| Files are re-read after restart. | Filter only stores state in RAM. | Use a metadata/persistent filter or file-ID idempotency. |
| Files are skipped after a processing error. | Source marked or removed the record before the handler succeeded. | Design checkpoints/acks and retries tied to business outcome. |
| Poller config looks right, yet throughput is slow. | Synchronous `DirectChannel` makes each poll cycle block on handler time. | Measure handler duration, tune concurrency, and consider an appropriate channel. |
| Same record processed by multiple instances. | Multiple pollers scanning the source without coordination. | Use distributed locks, record claiming, partitioning, or a dedicated leader instance. |
| Error path does not behave as expected. | Exception occurs on another thread or filter drops messages silently. | Distinguish source vs. handler errors, thread boundaries, error channels, and timeouts. |

## 13. Hands-On Exercise

**Prompt:** build an application receiving `PaymentRequest` items from a simulated polling source, up to 3 messages per poll, spaced 1 second apart. Each `PaymentRequest` has `id`, `amount`, and `currency`. After reading, the flow must:

1. Reject requests missing an `id` and send them to a defined error-inspection branch.
2. Attach a `sourceSystem` header at the source and log a correlation ID during processing.
3. Route `VND` and `USD` to two separate handlers; each handler must prevent duplicate writes by `id`.
4. Simulate a handler failure on the first attempt, then verify whether your retry policy reprocesses that exact request.
5. Have the source return `null` once empty; verify the app stays alive and polling continues.
6. Replace the simulated source with `FileReadingMessageSource` and explain what must be added to prevent lost or duplicate files across restarts.

**Pass criteria:** clearly state how many messages are pulled per cycle, distinguish each error type, describe when processing is acknowledged, and include tests proving duplicates do not produce repeated side effects.

## 14. Quick Self-Check

1. A method annotated with `@InboundChannelAdapter` returns `MessageSource<T>`; which method does the poller invoke on each scheduled tick?
2. When `receive()` returns `null`, does the framework permanently stop the adapter?
3. How does `maxMessagesPerPoll = "5"` differ from a single message containing a list of 5 records?
4. Why does `fixedDelay = "1000"` not guarantee that one message finishes processing every second?
5. A file was read successfully, but the handler writing to the database failed: where must state be managed to retry safely?
6. When running three application instances, is an `AcceptOnceFileListFilter` on each instance enough to prevent duplicates?

**Answer hints:** the poller calls `MessageSource.receive()`; `null` only indicates no data is currently available; the poll limit counts messages; a synchronous channel ties handler execution time to the poll cycle; checkpoints/acks/idempotency must align across source and destination; local in-memory filters do not coordinate across instances.

## 15. Summary

`@InboundChannelAdapter` brings **polling-based sources** into Spring Integration through a `MessageSource`. The poller controls the schedule and message count; channels connect the source to processing steps in an `IntegrationFlow`; and business handlers own final outcomes and side effects.

When applying this to files, SFTP, databases, or periodic APIs, design three things together: **payload/header contracts**, **schedule and throughput regulation**, and **error handling, read-state tracking, and idempotency**. The annotation syntax is concise, but the reliability of the integration flow depends on making those behaviors explicit from the start.
