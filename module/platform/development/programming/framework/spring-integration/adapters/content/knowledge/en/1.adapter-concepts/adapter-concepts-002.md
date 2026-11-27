# Inbound Flows: Bringing Data into a MessageChannel

## Learning Objectives

After this lesson, you will be able to:

- Trace the path of data from an external system, through an inbound channel adapter, into a Spring Integration Message, and onto a MessageChannel.
- Distinguish between a poller-based inbound adapter and an event-driven inbound adapter, and determine when an inbound gateway is needed.
- Identify the impact of DirectChannel, QueueChannel, and ExecutorChannel on synchronous processing, latency, and load handling.
- Build a flow that reads CSV files into a MessageChannel using Spring Integration Java DSL and verify delivery to a subscriber.
- Design payload/header contracts, error handling, deduplication, and connection lifecycle management on the inbound side.

## 1. Context: From External Sources to the Internal Message Model

An integration system often receives data in many ways: files dropped into a directory, files on SFTP, HTTP requests, messages in JMS/AMQP, Kafka records, or new rows in a database. Each source has its own connection mechanism, delivery cadence, acknowledgment semantics, and data representation. If all business processing directly calls each source's API, switching protocols or adding a new source forces changes across many places.

In **Spring Integration**, an inbound channel adapter is the connection point **from an external system into the application's messaging flow**. It receives or retrieves data from the source, creates a message according to the configured contract, and sends the message to a **MessageChannel**. Components behind the channel can validate, transform, route, store, or forward the data without directly opening connections to the original source.

A Spring Integration message consists of two main parts:

- **Payload:** the data that the next step needs to process, such as a File object, a JSON string, a byte array, or a DTO.
- **Headers:** accompanying metadata, such as an identifier, creation timestamp, correlation key, and adapter-specific metadata.

Key point to remember: **the inbound adapter receives data, the MessageChannel delivers the message, and the handler processes the content**. These three roles can be configured within the same IntegrationFlow, yet they remain distinct responsibilities.

~~~mermaid
flowchart LR
    S["External system<br/>File / SFTP / JMS / Kafka / DB"] --> A["Inbound channel adapter"]
    P["Poller or listener"] -. "Triggers receipt" .-> A
    A --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel"]
    C --> H["Transformer / Filter / Handler"]
    H --> N["Subsequent processing flow"]
~~~

For HTTP sources, depending on the goal, you can use either an inbound channel adapter or an inbound gateway. When the caller needs a business reply from the flow to construct the HTTP response, a gateway is the better choice. The **inbound** direction is always measured from outside **into the Spring Integration application**.

## 2. How Does an Inbound Message Enter a Channel?

The process can be broken down into six stages:

| Stage | Acting Component | What Happens |
| --- | --- | --- |
| 1. Source has data | File system, SFTP server, queue, topic, HTTP client, database | New data or an event is ready for ingestion |
| 2. Trigger receipt | Poller or listener/consumer | A poller runs on a schedule; a listener is woken by an event or the protocol's consumer mechanism |
| 3. Receive data | Inbound adapter, message source, or integration client | Reads a file, receives a broker message, accepts a request, or queries a source |
| 4. Create message | Adapter and configured converters | Determines payload and headers; may convert the data representation |
| 5. Send to channel | Inbound endpoint | Delivers the message through the MessageChannel according to channel semantics |
| 6. Consume message | Subscriber or polling consumer behind the channel | Runs a transformer, filter, service activator, or another flow |

**Boundary 5 is critical.** That a channel has accepted a message does not necessarily mean business processing is complete or the target system has written the data. With a synchronous DirectChannel, sending typically invokes the handler on the same execution thread. With an asynchronous or queued channel, the send step can finish before downstream business logic completes.

### 2.1. Polling Inbound: The Application Actively Queries the Source

Some sources do not proactively push notifications whenever data arrives. In those cases, Spring Integration uses a **MessageSource** combined with a **poller**. On each trigger, the poller invokes the message source's receive mechanism; if data is available, it creates and sends a message to the channel; if not, it waits for the next cycle.

For example, every 5 seconds scan an input directory, pick up at most 5 valid CSV files matching a filter, and send each File object to the channel. Distinguish carefully:

- **fixedDelay:** the pause between runs under the poller's fixed-delay scheduling, not a millisecond-exact delivery SLA.
- **maxMessagesPerPoll:** limits how many messages the poller fetches in a single execution; it is not a global limit on total messages in the application.
- **Source filter:** decides which data items are eligible candidates for receipt, such as by filename or whether they have already been picked up.
- **Downstream consumer:** determines actual processing capacity; speeding up polling without improving downstream throughput can increase overload.

Seeing a new file does not mean the partner system has finished writing it. In production environments, use conventions like writing to a temporary file followed by an atomic rename, completion marker signals, file age filters, or an equivalent mechanism.

### 2.2. Event-Driven Inbound: The Source or Client Emits Events

For sources that support listeners or consumers, the adapter receives events when the protocol's listening mechanism fires. For instance, a JMS listener receives a message from a queue, an AMQP listener receives a delivery from a broker, or a Kafka consumer receives records provided by the broker via the Kafka client's internal poll loop.

**Do not equate "a Kafka consumer has an internal poll" with "a Spring Integration poller for a MessageSource".** Kafka's message-driven adapter manages consumer lifecycles using Kafka infrastructure; developers normally do not configure a Spring Integration Poller for this endpoint.

| Criterion | Polling Inbound | Event-Driven / Message-Driven Inbound |
| --- | --- | --- |
| Trigger mechanism | Spring Integration poller schedule | Protocol listener, container, or consumer |
| Examples | Reading directories, scanning SFTP, querying a database | JMS, AMQP, Kafka, HTTP requests |
| Load tuning | Poll interval, batch size, and maxMessagesPerPoll | Concurrency, prefetch, batching, consumer settings, and acknowledgment mode |
| Main risks | Latency between scans, re-reading data, reading incomplete sources | Message redelivery, connection drops, listener overload, improper ack/offset handling |
| Design concerns | Filtering, pickup ordering, state across restarts | Acknowledgment point, error handling, restart behavior, and load balancing |

Neither option inherently guarantees zero data loss or zero duplicates. Actual guarantees depend on the source, adapter, channel, transactions, and business logic.

## 3. MessageChannel Determines How Messages Reach Processors

An inbound adapter puts a message into a channel, but it does not by itself dictate how everything downstream executes. The **MessageChannel type** determines how messages are dispatched and the degree of coupling between source and consumer.

| MessageChannel | Delivery Behavior | Implications for Inbound |
| --- | --- | --- |
| DirectChannel | Invokes subscriber synchronously on sender thread | A slow handler can block the poller/listener thread; exceptions can propagate back along the same call chain |
| ExecutorChannel | Delegates processing to an executor | Must bound threads, queue capacity, and overload handling; does not preserve ordering by default |
| QueueChannel | Places messages in a queue for a consumer to actively pull | Requires a consumer or poller on the receiving side; persistence depends on backing store, not enabled by default |
| PublishSubscribeChannel | Broadcasts messages to subscribers | Fits multiple branches needing the same event; not a default load-balancing mechanism across workers |

### 3.1. Why Choose the Channel Before Tuning the Poller?

Suppose an inbound adapter can ingest 100 files/second, while the service activator can only process 10 files/second:

- With DirectChannel, each message send waits for processing to finish; ingestion rate is naturally throttled by the synchronous consumer.
- With ExecutorChannel, the inbound side can keep picking up files while workers process them, but the task queue can fill up if arrival rate persistently exceeds processing rate.
- With QueueChannel, messages can be buffered before processing, but you must explicitly decide capacity, retention time, and full-queue policy.

Changing the channel does not magically increase business processing capacity. Determine sustainable throughput, processing latency, allowable backlog, and delivery semantics before increasing concurrency.

### 3.2. Send Success Differs from Business Success

Sending a message to a channel can complete while business processing is still running on another thread. Therefore:

1. **Received from source** does not necessarily mean **sent to channel**.
2. **Sent to channel** does not necessarily mean **successfully written to the database or target system**.
3. **Protocol-level response received** does not necessarily mean **business processing is complete**.

This is why inbound design must address acknowledgment/commit timing, retry mechanisms, and duplicate-processing prevention from the start.

## 4. Java DSL Example: File Inbound Adapter Feeding a DirectChannel

This hands-on example creates a polling source: every 5 seconds it scans **./data/inbox**, selects up to 5 **.csv** files per poll, and sends a message with a **File** payload to a channel named **incomingFiles**. A second flow subscribes to that channel and logs basic metadata to the console.

The example uses Spring Integration Java DSL. With Spring Boot, you need the Spring Integration starter and the **spring-integration-file** module compatible with your Spring Boot/Spring Integration version. No explicit version is needed when using Spring Boot's dependency management.

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class InboundFileConfiguration {

    @Bean
    public MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    // Producer side: file source -> MessageChannel
    @Bean
    public IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                spec -> spec.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))
            .channel("incomingFiles")
            .get();
    }

    // Consumer side: MessageChannel -> processing
    @Bean
    public IntegrationFlow fileConsumerFlow() {
        return IntegrationFlow.from("incomingFiles")
            .handle(File.class, (file, headers) -> {
                System.out.println(
                    "Received CSV: " + file.getName()
                    + ", size: " + file.length() + " bytes");
                return null; // End one-way flow
            })
            .get();
    }
}
~~~

### 4.1. Explaining Each Component

1. **Files.inboundAdapter(...):** configures the file inbound adapter. The message source returns a File object representing the selected file; it does not automatically read or parse CSV content into order objects.
2. **autoCreateDirectory(true):** creates the input directory if it does not exist per adapter configuration; only appropriate when the application has permissions on that location.
3. **patternFilter("*.csv"):** selects files matching the filename pattern. Extension-based filtering does not verify valid CSV syntax and does not prove the file has finished writing.
4. **Pollers.fixedDelay(...):** sets up the schedule for calling the message source; **maxMessagesPerPoll(5)** caps the number of messages fetched per poll cycle.
5. **incomingFiles():** creates a DirectChannel. The adapter does not call the file-handling method directly; it sends messages into this named channel.
6. **IntegrationFlow.from("incomingFiles"):** the consuming flow subscribes to messages on the channel and runs the handler with a File payload.
7. **return null:** the handler produces no reply message; the flow terminates after processing. This example only prints metadata to illustrate handoff; it does not persist orders or move files yet.

If you want to read the CSV content, place a transformer or service activator after the channel to convert the payload from File into a business structure. For large files, read as a stream or record-by-record instead of loading the entire file into memory.

### 4.2. Manual Testing

1. Start the application with the configuration above; verify that **./data/inbox** is created or already exists.
2. Create a small file **orders-001.csv** in the directory, for instance with two lines **orderId,total** and **O-1001,150000**.
3. Watch the console after the poller interval: the filename and size appear when the handler receives the message.
4. Add **readme.txt** as well to confirm the filter does not pick up files outside the pattern.
5. Stop and restart the application to observe file re-pickup behavior. For stable behavior across restarts, design a persistent state filter and a workflow to move or delete files after successful processing.

**Scope of this example:** it only proves the flow File → Message → DirectChannel → handler. Do not treat console output as proof that business data has been durably saved; do not assume files are automatically deleted or moved to an archive folder.

## 5. Message Contracts at the Inbound Boundary

For downstream components to process data from multiple adapters, the team must agree on **payload type**, key **headers**, and conversion rules.

~~~text
Message<File>
├── payload: File("./data/inbox/orders-001.csv")
└── headers
    ├── id, timestamp
    └── additional metadata (if provided by adapter/converter)

        |
        v
Transformer: read CSV, normalize, validate format
        |
        v
Message<OrderBatch> -> Business processing MessageChannel
~~~

Some external sources may carry details such as remote filename, Kafka topic/partition/offset, correlation ID, or JMS/AMQP headers. Specific values depend on the adapter and mapping configuration. **Do not assume all inbound messages share the same set of headers**, or that headers are guaranteed to pass intact to an outbound protocol.

| Question | Example Decision |
| --- | --- |
| What is the inbound data type? | File, byte array, String, Map, DTO, or client record |
| Is the content already decoded? | Did the adapter only receive bytes or did a converter turn JSON into a DTO? |
| Which headers support processing? | Source ID, correlation ID, event type, filename, idempotency key |
| What is the record identifier key? | orderId, eventId, message ID guaranteed stable by the partner |
| How does the contract change when switching sources? | File → Kafka may change payload type, metadata, and ack timing |
| Who is responsible for validation? | Converter/transformer checks syntax; handler or validator checks business rules |

A clean design pattern is normalizing data near the inbound boundary: **source-specific payload → stable domain message**. For example, both File and SFTP pass through a parsing step to produce an **OrderBatch** before entering the order-processing channel. This keeps business handlers loosely coupled to protocol details while preserving key metadata for tracing.

## 6. Common Inbound Sources in Spring Integration

Although they all feed data into a MessageChannel, adapters for different systems have distinct operational conditions:

| Source | Common Inbound Style | Considerations |
| --- | --- | --- |
| Local file | Polling file inbound adapter | Has the file finished writing, accept-once filter, state across restarts |
| SFTP | Polling / remote file synchronization depending on config | Connectivity, login sessions, incomplete remote files, metadata, and idempotency |
| HTTP | Inbound adapter or inbound gateway | Distinguishing one-way receipt from request–reply contracts, status codes, and timeouts |
| JMS | Message-driven inbound adapter | Acknowledgment, transactions, redelivery, listener concurrency |
| AMQP | Message-driven inbound adapter | Ack/nack, prefetch, queue binding, requeue or dead-lettering |
| Kafka | Message-driven inbound adapter | Consumer group, partition/ordering, offset commit, retry, and deserialization |
| Database | JDBC inbound adapter / polling query | Watermark, new rows, transactions, concurrency, and preventing re-reads |

For example, if a partner previously pushed CSVs over SFTP and switches to Kafka, the parsing step may be reusable **if the domain contract stays the same**, but the inbound layer must review converters, metadata, consumption cadence, and record acknowledgment. Kafka has no "file finished writing" concept like SFTP; instead, the system must handle offsets, consumer groups, and record redelivery.

## 7. Error Handling in Inbound Flows

Errors can happen **before message creation**, **while sending to a channel**, or **while a subscriber is processing**. Knowing which boundary failed is essential to choosing a recovery strategy.

~~~mermaid
flowchart TD
    A["External source"] --> B["Inbound adapter"]
    B --> C{"Received/read OK?"}
    C -- "No" --> E1["Log + source-specific retry/reconnect"]
    C -- "Yes" --> D["MessageChannel"]
    D --> F{"Consumer processed OK?"}
    F -- "No" --> E2["Error flow / retry / quarantine failed message"]
    F -- "Yes" --> G["Confirm progress per policy"]
    E1 -. "Re-acquire if appropriate" .-> A
    E2 -. "Controlled recovery" .-> F
~~~

### 7.1. Synchronous vs. Asynchronous Errors

With **DirectChannel**, the handler typically runs on the sender's thread; subscriber exceptions can propagate back to the inbound/poller side and affect the current pickup attempt. With **ExecutorChannel** or queued flows, errors can occur after the send-to-channel step has already returned. Consequently, send success alone cannot determine business success across all configurations.

Depending on the endpoint and configuration, Spring Integration can route errors to **errorChannel** as an **ErrorMessage**. For polling flows, configure and test the poller's error path; for JMS/AMQP/Kafka, coordinate the listener container's error handler, retries, and ack policies accordingly. A default errorChannel does not replace an explicitly designed retry or dead-letter policy.

### 7.2. Retry, Redelivery, and Idempotency

**Retry** helps recover from transient failures, such as an interrupted SFTP connection or an overloaded database. However, if a failure happens after an order is saved but before the source records success, the data may be delivered again.

**Idempotency** prevents reprocessing the same event from causing duplicate business side effects. Common implementation techniques:

- Construct a stable processing key, such as **partnerId + orderId** or a partner-guaranteed unique event ID.
- Persist processing results or seen keys in durable storage matching business requirements.
- Only acknowledge or commit source progress at the point consistent with desired guarantees.
- For files, combine persistent filters, post-processing file moves, and safe rerun capabilities.
- For queues/brokers, understand how ack, nack, requeue, and offset commits behave when a handler fails.

Never claim **end-to-end exactly-once** solely because you use a specific adapter or channel type. The file system, broker, and database may belong to separate transactions. If consistency is needed, consider idempotent consumers, outbox/inbox, supported transactions, or compensating actions.

## 8. Inbound Adapter Lifecycle, Load, and Observability

Inbound adapters are often tied to resources with their own lifecycles: schedulers, sockets, SFTP sessions, JMS listener containers, Kafka consumers, or connection pools. On application startup, endpoints must be registered and begin receiving data; on shutdown, tasks and resources must be closed or drained according to defined policy.

Connection readiness is not the same as processing readiness. For instance, a poller may run on schedule yet fail to read files due to permissions, or a Kafka consumer may stay connected while downstream capacity is exhausted.

| Operational Dimension | What to Monitor or Configure |
| --- | --- |
| Ingestion capability | Messages received, empty poll counts, last pickup time, listener status |
| Latency | Time from event appearance to receipt and completion |
| Backlog | Waiting files, queue depth, Kafka consumer lag, unprocessed rows |
| Errors | Connection errors, data conversion failures, channel sends, business errors, exhausted retries |
| Throughput | Messages/second and downstream processing duration |
| Data safety | Duplicate event counts, redeliveries, quarantined messages, checkpoint durability |

In particular, increasing **maxMessagesPerPoll**, listener counts, or worker counts must be paired with capacity evaluation. If the source feeds data faster than sustained processing capacity, the system must enforce input throttling, backpressure, bounded buffers, or backlog recovery policies.

For security, configure endpoints using proper credentials/secrets; avoid printing sensitive data verbatim in logs. For tracing, prefer correlation IDs, event IDs, and status fields rather than logging entire payloads.

## 9. Design Scenario: Receiving Partner Orders

A retail application receives order data via CSV files. The requirement is that each valid order is created only once, even if the partner resends a file or the application restarts.

Proposed flow:

~~~mermaid
flowchart LR
    F["CSV drop directory"] --> I["File inbound adapter + poller"]
    I --> C1["rawFiles"]
    C1 --> T["Parse CSV"]
    T --> V["Business validation"]
    V --> C2["validOrders"]
    C2 --> K["Check idempotency key"]
    K --> DB[("Database")]
    V -. "Invalid data" .-> ER["Store error details for handling"]
~~~

Here, **rawFiles** carries a File payload, while **validOrders** carries normalized data. The database-writing handler does not need to know whether the file came from disk or SFTP. However, ensuring each order is created once should rely on a business key and database write constraints rather than relying solely on file filter state.

If data later arrives over HTTP or Kafka, you can replace the inbound point and transformation step to keep emitting **validOrders** messages with the same business contract. At that point, you must still separately design when to return the HTTP response or commit the Kafka offset so it accurately reflects the level of completion guaranteed by the system.

## 10. Common Design Mistakes

**Assuming the inbound adapter handles business logic itself.** Adapters primarily bring data into the messaging flow; validation, parsing, and business rules should be clearly placed in downstream endpoints.

**Equating MessageChannel with a durable queue.** DirectChannel delivers synchronously; QueueChannel by default does not guarantee preserving messages across restarts. Choose channels per requirements and configure persistence if needed.

**Using a poller for every source.** HTTP requests, JMS/AMQP listeners, and Kafka message-driven adapters have their own receive mechanisms. Spring Integration pollers fit sources that require scheduled active querying.

**Equating receipt with successful processing.** Ack/commit timing must align with error paths, channels, handlers, and target-system writes.

**Reading a file the moment its name appears.** The file may still be mid-write; agree on a file handoff protocol with the partner.

**Speeding up inbound without checking downstream.** A poller or listener faster than its handler can cause backlogs, full queues, or rising memory usage and latency.

## 11. Self-Check Questions

1. How does an inbound channel adapter differ from a MessageChannel? Describe a message passing through both components.
2. When a File inbound adapter is triggered by a poller and the directory has no matching files, what happens on the next receive cycle?
3. Why can using a DirectChannel cause a slow handler to directly impact message ingestion speed?
4. If a broker redelivers a message after the handler has already saved an order, what mechanism does the system need to avoid creating two orders?
5. If an HTTP API must return the order-processing result within the same request, should you consider an inbound adapter or an inbound gateway? Why?
6. When migrating a file source to Kafka, which parts of the payload, headers, and acknowledgment contract must be re-examined?

## Summary

**An inbound flow** is a controlled pathway from an external system to a **MessageChannel**: a source produces data, an inbound adapter receives it and builds a message, a channel delivers it to a consumer, and downstream endpoints execute business logic. Understanding each boundary helps you pick the right poller or listener, keep payloads/headers consistent, avoid overload, and recover safely when connectivity or processing fails. These principles apply across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, even though acknowledgment and lifecycle mechanisms vary by protocol.
