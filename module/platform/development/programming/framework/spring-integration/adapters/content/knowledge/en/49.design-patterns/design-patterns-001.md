# Polling Consumer Pattern in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Topic:** Polling consumer pattern  
> **Module scope:** Connecting external systems with **Spring Integration** using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; illustrated with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. The focus is on **how to proactively pull data on a schedule**, message contracts, error handling, load throttling, and connection lifecycle.

## 1. Lesson Objectives

After this lesson, learners can:

1. Explain what a **Polling Consumer** is and when to use polling instead of an event-push mechanism (*message-driven/push*).
2. Accurately distinguish between a **`PollingConsumer` reading from a `PollableChannel`** and a **`SourcePollingChannelAdapter` reading from a `MessageSource`** in Spring Integration.
3. Configure a poller using Java DSL or annotations, understanding the effects of `fixedDelay`, `fixedRate`, cron, `maxMessagesPerPoll`, and receive timeout.
4. Design file/SFTP/JDBC reading flows and define the responsibilities of the inbound adapter, `MessageChannel`, handler, and outbound adapter.
5. Manage duplicate data, partially written messages, retries, transactions, acknowledgments, transient errors, and backpressure.
6. Choose a multi-instance deployment strategy without assuming “each record is polled exactly once.”
7. Read metrics, write tests, and explain the limitations of a polling design before taking it to production.

**Guiding question:** *When a data source does not proactively push messages to the application, how do we fetch the right data at the right time, without unintended duplicates, without missing records, and without overloading the system?*

## 2. What is a Polling Consumer?

**Polling Consumer** is an integration pattern in which the receiver **proactively checks** a source or queue according to a schedule or trigger signal, and then receives up to one or more available messages. It contrasts with an **Event-Driven Consumer**, where the source, broker, or runtime proactively notifies/pushes data when it becomes available.

For example, a partner system only uploads CSV files to an SFTP directory every few minutes. The partner does not provide webhooks; the application needs to periodically list the directory and download new files:

~~~text
09:00:00  Poll SFTP: no file yet
09:00:05  Poll SFTP: no file yet
09:00:10  Poll SFTP: found orders-001.csv
09:00:10  Adapter creates Message<File> / file content
09:00:10  Channel delivers to handler for validation and processing
09:00:15  Next poll: do not reprocess old file if filter/metadata is working
~~~

Polling does not necessarily mean “busy-waiting continuously.” With a fixed schedule, the scheduler only triggers at set intervals or after a delay. Each poll cycle must decide **whether data is available**, **how much at most to fetch**, **what to do on error**, and **when the next cycle is allowed to run**.

### 2.1. When should you choose polling?

| Context | Usually suitable choice | Why |
| --- | --- | --- |
| Local file directory where files are dropped periodically | File inbound adapter + poller or supported watch mechanism | The file system does not provide a standard message queue with ack |
| Partner SFTP that only allows listing/downloading files | SFTP inbound/streaming adapter + poller | The receiver must actively connect and look for files |
| Database table containing records awaiting processing | JDBC/message source polling with a claim mechanism | No broker exists; state resides in the DB |
| HTTP API with only `GET /changes` | HTTP polling with cursor/ETag/rate limit | No webhook, SSE, or stream |
| JMS/AMQP broker supporting listeners | Usually consider a message-driven adapter | The broker has receive/ack mechanisms; polling is not always optimal |
| Kafka topic with consumer group | Usually use a Kafka listener/message-driven adapter | The Kafka client still uses `poll()` internally, but Spring Integration has a dedicated listener abstraction |
| An internal `QueueChannel` that needs scheduled consumption | `PollingConsumer` | The channel supports `receive()`; the handler is triggered by a poller |

**Do not infer:** that because the Kafka client has a `poll()` method, every Kafka flow in Spring Integration is a `PollingConsumer` endpoint. You must distinguish the internal polling mechanism of a client/broker from the **Spring Integration endpoint type** configured by the application.

### 2.2. Strengths and costs

**Pros:**

- Controls reading cadence, number of messages per cycle, and operational windows.
- Can integrate systems that only support active reading and have no push mechanism.
- Provides a place to organize timeouts, retries, transactions, and throttling when the target is slow.
- Can adjust consumption rate without modifying the source system.

**Trade-offs:**

- Introduces data detection latency, usually dependent on the interval between polls.
- Polling too frequently when empty causes unnecessary I/O, connections, and load.
- A long poll cycle or slow processing can cause backlog, schedule drift, or overlap if concurrency is not configured appropriately.
- Does not inherently guarantee *end-to-end exactly-once*; handling duplicates/loss requires source design, acknowledgments, transactions, and idempotency.
- Multiple concurrent instances can see the same data if there is no shared lock/claim/metadata.

## 3. Position of Polling Consumer in Enterprise Integration Patterns

~~~mermaid
flowchart LR
    A["External source: File / SFTP / DB / HTTP"] -->|Provides data when queried| SRC["MessageSource"]
    TR["Scheduler + Trigger + Poller"] --> SPA["SourcePollingChannelAdapter"]
    SRC --> SPA
    SPA --> CH["MessageChannel"]
    CH --> HANDLER["Filter / Transformer / Service Activator"]
    HANDLER --> OUT["Outbound Adapter / Gateway"]
    OUT --> DEST["Target system"]
~~~

At a conceptual level, the consumer has a trigger schedule and a receive operation. However, **Spring Integration uses two distinct types of polling endpoints worth separating**.

### 3.1. Two different cases in Spring Integration

| Case | Source being polled | Spring Integration Endpoint | Example |
| --- | --- | --- | --- |
| **Poll external data** | `MessageSource.receive()` | **`SourcePollingChannelAdapter`** | Reading files, querying DB records, fetching data from a remote source |
| **Poll messages already in a channel** | `PollableChannel.receive(timeout)` | **`PollingConsumer`** | `QueueChannel` → scheduled service activator |

Both endpoints share the **poller/trigger** mechanism; they address two different points of receiving data. Calling every polling inbound adapter a `PollingConsumer` class makes reading logs, configurations, and troubleshooting error-prone.

~~~mermaid
flowchart TB
    subgraph ExternalSource["Branch A: poll external source"]
        FS["File / SFTP / JDBC MessageSource"] --> SPA["SourcePollingChannelAdapter"]
        SPA --> DC["DirectChannel / QueueChannel"]
    end
    subgraph ChannelConsume["Branch B: poll channel"]
        PRODUCER["Producer / Upstream flow"] --> Q["QueueChannel (PollableChannel)"]
        Q --> PC["PollingConsumer"]
        PC --> H["MessageHandler"]
    end
    SCHED["TaskScheduler + Poller"] -.-> SPA
    SCHED -.-> PC
    DC --> DOWN["Downstream processing flow"]
~~~

### 3.2. `PollableChannel` and `SubscribableChannel`

| Channel type | Consumption style | Spring Integration examples | Notes |
| --- | --- | --- | --- |
| **`PollableChannel`** | Consumer calls `receive()` to pull a message | `QueueChannel`, `PriorityChannel` | Messages can wait in the channel; requires a poller on the consuming endpoint |
| **`SubscribableChannel`** | Handler is subscribed to receive messages when sent to the channel | `DirectChannel`, `PublishSubscribeChannel` | Do not use `PollingConsumer` to call `receive()` on a `DirectChannel` |
| **Channel with async dispatch** | Subscribers are dispatched via an executor | `ExecutorChannel` | Asynchronous dispatch does not make a channel pollable |

`QueueChannel` buffers messages and supports pull-based reception. `DirectChannel` typically dispatches messages directly to the handler on the sender's thread. Using `QueueChannel` as a buffer helps decouple producer and consumer speeds, but you must **bound its capacity** and understand what happens when it is full; the channel itself is not a durable queue by default if the process dies.

### 3.3. How adapters, gateways, and handlers differ

An **inbound channel adapter** brings data from an external system into a Spring `Message` and sends it to a channel. An **outbound channel adapter** receives a message in a flow and performs an external side effect; normally no reply is expected. A **gateway** models request/reply communication and can wait for a result. A **service activator** invokes business logic when receiving a message. A **poller** is the mechanism that triggers a reading endpoint, not a new channel or transport protocol.

## 4. Poller Configuration Components

A poll cycle consists of: **trigger → fetch up to N messages → dispatch/process → record result or error → wait for the next cycle**. A poller can be configured with Java DSL, annotations, XML, or beans depending on project conventions.

| Parameter/concept | Effect | What to check |
| --- | --- | --- |
| **fixedDelay** | Sets the wait interval between triggers after the previous execution finishes according to the scheduler | Avoids tight spinning when the source is empty; adds latency when data arrives |
| **fixedRate** | Schedules at relatively even time intervals | If work takes longer than the period, understand scheduler/executor behavior and overlap risk |
| **cron** | Polls on a calendar window, e.g., business hours or nightly batches | Timezone, DST if applicable, missed executions during downtime |
| **maxMessagesPerPoll** | Limits the number of messages received/processed in one poll cycle | Batch size, load level, time holding the scheduler |
| **receiveTimeout** | Wait duration when polling from a `PollableChannel` that supports waiting | Do not confuse with SFTP/HTTP network timeouts or handler processing timeouts |
| **TaskScheduler** | Triggers tasks according to the trigger | Pool size, concurrency, shutdown, error handling |
| **TaskExecutor** | Can decouple trigger scheduling from task execution depending on configuration | Threading, message ordering, transactions, and thread-bound context |
| **Transaction advice** | Wraps appropriate operations in a transaction if the source/handler supports it | Transaction boundaries do not automatically span multiple external systems |
| **Advice/error handling** | Retries, observability, error handling at the poll/handler level | Distinguish transient errors from data errors; avoid infinite retries |

### 4.1. Fixed delay and fixed rate

Suppose processing one poll cycle takes 4 seconds:

~~~text
fixedDelay = 5 seconds
  Poll 1 starts t=0, finishes t=4
  Poll 2 can start around t=9 (after waiting 5 seconds)

fixedRate = 5 seconds
  Expected marks t=0, t=5, t=10...
  Actual execution depends on the scheduler and run duration;
  never assume every run always starts right on the mark or always runs in parallel.
~~~

For file downloads or slow API calls, `fixedDelay` generally provides more predictable load. `fixedRate` is useful when a steady cadence is needed, though you must evaluate long-running work and executor settings. Do not treat cron as a guarantee against duplicate or missed messages.

### 4.2. `maxMessagesPerPoll` is not the message size

If a poller sets `maxMessagesPerPoll(10)`, it can fetch up to 10 messages in one trigger, but that does not mean:

- Every cycle will have all 10 messages.
- Each message is a single business record (one file can contain thousands of records).
- The source supports fetching 10 records in a single network query.
- Having 10 messages means 10 handlers will run in parallel.

The **actual batch unit** depends on the adapter: a file, a DB row, an HTTP page, a message in a channel, or a record/event. If the source is empty, `receive()` can return `null` and the poll cycle ends.

### 4.3. `receiveTimeout` is different from connection timeout

With `QueueChannel`, `receive(timeout)` can wait until a message arrives or the timeout expires. However, when polling files/SFTP/HTTP, the adapter also has separate **connection**, **socket read**, **session**, and **response** timeouts. Adjusting the consumer's `receiveTimeout` will not automatically fix an SFTP connect timeout.

### 4.4. Preliminary capacity planning

Let `R` be the number of messages received per cycle, `P` be the average number of completed poll cycles per second, and `T` be the actual processing throughput. Under load:

~~~text
T <= R × P
T <= processing capacity of handler and target system
~~~

This is an **illustrative theoretical bound**, before accounting for empty polls, timeouts, errors, locks, parallelism, or broker constraints. If the source produces 200 messages/second while the flow only processes 100 messages/second, the backlog grows even if increasing poll frequency makes the flow look busier. You must measure end-to-end and address the bottleneck.

## 5. Message Contract and Data Path

Spring Integration transfers data via `org.springframework.messaging.Message<T>`, consisting of a **payload** and **headers**. The payload can be a `File`, `String`, `byte[]`, DTO, database record, or adapter object; headers carry metadata such as ID, timestamp, file info, correlation, or trace.

### 5.1. Message contract checklist

- [ ] Clearly define payload types before/after transformation, encoding, schema, and required fields.
- [ ] Determine how trustworthy adapter headers are; external data must never be used as internal authorization without verification.
- [ ] Have a stable **business key/idempotency key** independent of the runtime-generated message ID.
- [ ] Know whether a message represents one file, one data row, or an entire batch; preserve correlation IDs when splitting/aggregating.
- [ ] Have a way to classify data conversion errors, source errors, and target system errors.
- [ ] Separate metadata needed for auditing from credentials such as access tokens or passwords.
- [ ] Define a contract for the success state: received, parsed, written to DB, or sent to the target?

### 5.2. Example file processing steps

~~~mermaid
sequenceDiagram
    participant S as Scheduler/Poller
    participant F as File MessageSource
    participant A as Inbound Adapter
    participant C as MessageChannel
    participant H as Handler
    participant DB as Database
    S->>A: Trigger poll cycle
    A->>F: receive()
    F-->>A: New file or null
    A->>C: send(Message<File>)
    C->>H: Deliver message
    H->>H: Validate, parse, idempotency
    H->>DB: Save results
    DB-->>H: Appropriate Commit/ACK
    H-->>A: Complete or throw error
~~~

Depending on the channel, handler invocation can be synchronous or asynchronous. Therefore, **“send succeeded” does not always mean “business logic committed.”** Choose the appropriate completion checkpoint, especially before moving/deleting source files or acknowledging messages to a broker.

## 6. Spring Integration Java DSL Example: File Polling

The following example demonstrates an **inbound channel adapter** reading CSV files in a directory and passing messages to a handler. This is the **poll MessageSource** branch, meaning the runtime uses `SourcePollingChannelAdapter`. The code reflects Spring Integration 6.x style; when applying it, verify the exact API for your Spring Boot/Spring Integration version.

### 6.1. Simple configuration

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class FilePollingFlow {

    @Bean
    public IntegrationFlow readCsvFiles() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("./lab/in"))
                         .autoCreateDirectory(true)
                         .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(3))
                               .maxMessagesPerPoll(5)
                    )
                )
                .handle((MessageHandler) message -> {
                    File file = (File) message.getPayload();
                    System.out.println("Found file: " + file.getName());
                    // In real projects: validate, parse, idempotency,
                    // persist results, and manage file state.
                })
                .get();
    }
}
~~~

Meaning:

1. `Files.inboundAdapter(...)` describes the file source to read; it does not turn into a custom application-written scheduler on its own.
2. `endpoint.poller(...)` creates a poll schedule for the **source polling endpoint**.
3. `fixedDelay(Duration.ofSeconds(3))` schedules the wait between trigger cycles.
4. `maxMessagesPerPoll(5)` limits the number of message receives in a single poll cycle.
5. The handler in this example only prints the filename; **printing to the console does not mean the file has been durably processed**.

**Important note on file filters:** whether an already-read file is picked up again depends on the file inbound source/filter configuration and metadata persistence capabilities. When you need to avoid reprocessing across restarts, use a **persistent accept-once filter** and/or business-level idempotency; do not assume an in-memory filter protects across application crashes.

### 6.2. Why do we need a file-completion convention?

An inbound adapter may see a file **as soon as an external writer starts writing it**. If an incomplete file is read, CSV parsing may fail or produce partial data.

Suggested file delivery convention:

~~~text
Partner writes temporarily:
  orders-2026-11-23.csv.uploading

When complete:
  atomic rename (if on the same filesystem and supported)
  orders-2026-11-23.csv

Poller only selects *.csv
  → receives completed published files
~~~

Not every remote filesystem or SFTP server guarantees atomic renames in the way you expect. You can combine staging directories, manifest/marker files, stable-size checks, or last-modified age. You need a clear **producer/consumer contract**, not just `patternFilter("*.csv")`.

### 6.3. Handling successfully received files

A common strategy:

~~~mermaid
flowchart TD
    POLL["Poll selects new file"] --> READY{"File complete and unprocessed?"}
    READY -->|No| SKIP["Skip until next cycle"]
    READY -->|Yes| CLAIM["Claim/mark in-progress if supported"]
    CLAIM --> PARSE["Read + validate + parse"]
    PARSE --> SAVE["Write business data with idempotency"]
    SAVE --> SUCCESS{"Commit succeeded?"}
    SUCCESS -->|Yes| ARCH["Move/mark processed, save audit"]
    SUCCESS -->|No| RETRY["Retain safely for retry or quarantine"]
~~~

**Do not delete or move the file immediately upon receiving the message** if downstream business logic has not yet committed. For multi-step asynchronous flows, a persistent state or separate ack/mark point is required; merely handling the filename is insufficient to prove the file was successfully imported.

### 6.4. Organizing the flow when the handler is slow

Start with a simple **source → channel → handler** flow to measure. If processing is too slow, you can place a bounded `QueueChannel` between producer and consumer and configure **another polling consumer** to drain it. This creates **two polling layers**:

- **Poller A** pulls data from the file `MessageSource` and sends it to the queue.
- **Poller B** calls `receive()` from the `QueueChannel` to invoke the handler.

This design decouples file detection cadence from processing cadence, but does not automatically add durability. You must control queue capacity and full-channel behavior to avoid the producer continuously polling files and growing memory.

## 7. Spring Integration Example: PollingConsumer Reading from QueueChannel

Here, messages are **already inside the application**, in a `QueueChannel`. We use a service handler endpoint with a poller. This is the case corresponding to the **`PollingConsumer`** class in Spring Integration terminology.

### 7.1. Java DSL

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class QueuePollingFlow {

    @Bean
    public QueueChannel auditWorkQueue() {
        // Bounded capacity instead of an unbounded in-memory queue.
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow drainAuditQueue(QueueChannel auditWorkQueue) {
        return IntegrationFlow.from(
                    auditWorkQueue,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(500))
                               .maxMessagesPerPoll(10)
                    )
                )
                .handle((MessageHandler) message -> {
                    System.out.println("Consume: " + message.getPayload());
                    // Process here; an in-memory queue does not replace
                    // a durable broker or business transactions.
                })
                .get();
    }
}
~~~

**Sending messages:** another producer flow can obtain the `auditWorkQueue` bean as a `MessageChannel` and call `send(message)`. The consumer receives on the poller's cadence. If no message is available, `receive()` returns null or waits until timeout, and the handler is not necessarily invoked.

### 7.2. Java annotation: attaching a poller to the consumer

Another style is declaring a `QueueChannel` and a service activator method:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class AnnotatedQueueConsumer {

    @Bean
    public QueueChannel workQueue() {
        return new QueueChannel(50);
    }

    @ServiceActivator(
        inputChannel = "workQueue",
        poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "5")
    )
    public void process(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Here, the `@Poller` annotation belongs to the **queue-consuming service activator**, not a directory-scanning schedule. When choosing a configuration style, ensure `inputChannel` is an appropriate pollable channel; `DirectChannel` does not support `receive()`.

### 7.3. Comparing the two examples to avoid confusion

| Question | File inbound flow | Queue consumer flow |
| --- | --- | --- |
| Reception source | External file directory | Messages already sent to QueueChannel |
| Receive operation | `MessageSource.receive()` | `PollableChannel.receive(timeout)` |
| Typical endpoint | `SourcePollingChannelAdapter` | `PollingConsumer` |
| When no data is available | File source finds no eligible files | Queue is empty |
| Durability | Determined by filter/metadata/file store | In-memory QueueChannel is not durable by default |
| Common failures | Partially written files, duplicates after restart | Full queue, slow handler, message loss on crash |
| How to inspect | Which files were picked, parsed/committed | Queue depth, dequeue rate, handler result |

## 8. Applying Polling Across Adapters and Protocols

It is the same pattern, yet the **data unit, acknowledgment, timeouts, and deduplication mechanisms** vary by external system.

### 8.1. File and SFTP

**File:** reads eligible files in a directory. You must control patterns, staging directories, partially written files, ordering, file size, memory, archiving, and processed metadata. Large files do not need to be read entirely into RAM; you can pass a `File` or stream and process in chunks.

**SFTP:** opens a remote session, lists files, downloads/copies, or streams. Consider:

- Remote and local directories; which files were received, and which were processed?
- Session factory, connection limits, timeouts, server host key verification, secret management.
- **Persistent/shared** remote file filters and metadata stores when running multiple instances.
- Files being uploaded, rename/marker conventions, reconnect, resume, or retry on dropped connections.
- Avoid deleting remote files early before downstream processing is confirmed.
- Observe backlog file count, file age, and download duration.

Spring Integration SFTP offers inbound adapters that download locally or **inbound streaming adapters** that read streams. Choose based on file size, retry approach, and storage requirements. Do not assume “streaming finished” means business data has committed; stream/session resources must be closed properly.

### 8.2. JDBC and database polling

A typical problem is an `integration_outbox` or `pending_task` table holding rows to forward:

~~~sql
-- Illustrative SQL query, not a complete JDBC adapter configuration.
SELECT id, business_key, payload
FROM integration_outbox
WHERE status = 'READY'
ORDER BY created_at, id;
~~~

If two instances query READY rows simultaneously, **both can pick up the same records**. You need a **claim/lease/row lock or conditional status update** within a transaction; syntax like `FOR UPDATE SKIP LOCKED` should only be used when the DB supports it and transactions are configured appropriately. A plain `SELECT` is not an exactly-once queue.

State pattern:

~~~text
READY
  → CLAIMED (owner, leaseUntil, attempt)
  → PROCESSED when the sink confirms the result
  → RETRYABLE/FAILED on error
  → back to READY when the lease expires and is validly recovered
~~~

If the DB is the **source of business transactions**, consider a **transactional outbox** to avoid committing business data without emitting an event, then use a poller to read the outbox and publish messages. However, publishing to a broker or HTTP target still requires idempotency and handling the failure gap between “send succeeded” and “mark processed.”

### 8.3. HTTP polling

When a partner only provides a changes-reading API:

~~~http
GET /api/changes?cursor=cursor-017&limit=100 HTTP/1.1
Authorization: Bearer <REDACTED>
If-None-Match: "<known-etag>"
~~~

This is an illustrative request; ETag, cursor, and endpoint depend on the actual API. The design needs to:

1. Persist the cursor/ETag or watermark in durable storage.
2. Distinguish **no data** from timeouts, 429, and 5xx responses.
3. Respect rate limits and `Retry-After` if provided by the API.
4. Do not advance the cursor before the page's data has been processed according to defined criteria.
5. Handle pagination, amended records, clock skew, and overlapping data windows.
6. Ensure credentials are not leaked in request logs/headers.

With HTTP, polling is often a **scheduled flow invoking an outbound gateway** or a custom message source, depending on interaction direction; not every HTTP outbound gateway should be called an inbound polling adapter.

### 8.4. JMS and AMQP

JMS/AMQP provide broker models with consumer listeners, acknowledgments, redelivery, dead-lettering, prefetch, and product-specific transactions. Usually you should consider a **message-driven inbound adapter/listener container** rather than adding a separate polling schedule if the broker already supports a suitable receive mechanism.

If polling is genuinely used (e.g., via a `MessageSource` or consuming a `PollableChannel`), you must know:

- Who holds the message before the consumer receives it, and when does the broker consider it acknowledged?
- If the handler throws an exception, does the broker redeliver or is the message lost?
- Does the broker transaction span DB writes or target HTTP calls?
- How do prefetch, batching, locks, and concurrency affect ordering/duplicates?
- Where do poison messages go after a bounded number of retries?

Do not attribute broker delivery guarantees to an in-memory `QueueChannel`. When durable queuing and redelivery are needed, choose a storage/ack mechanism with those properties.

### 8.5. Kafka

The Kafka consumer client uses a `poll()` loop to fetch records, but Spring Integration typically integrates Kafka via a **listener/message-driven inbound channel adapter** managed by a Kafka listener container; such a flow is **not identical** to a Spring Integration `PollingConsumer` endpoint reading a `QueueChannel`.

When using Kafka, the core questions are:

- When are offsets committed relative to successful business processing?
- How do consumer groups, partition assignment, and rebalancing affect ordering and retries?
- Can a failing record be re-read repeatedly? Are dead-letter/retry topics defined?
- Does concurrency match the partition count and per-key ordering requirements?
- If proactively polling via a supported `MessageSource`, how does that source manage offsets/acks?

**Conclusion:** choose the adapter/consumption style based on **protocol semantics** first; then pick poll cadence, channels, and throttling. Do not force the file polling model onto Kafka or JMS just to make configurations look uniform.

### 8.6. Quick selection table

| Source | Can be proactively polled? | Must be designed before running |
| --- | --- | --- |
| Local file | Yes | Filter, file completion, received metadata, archive/retry |
| SFTP | Yes | Session, remote/local filter, download/stream, reconnect |
| Database | Yes | Claim/lock, transaction, lease, idempotency |
| HTTP changes API | Yes | Cursor/ETag, rate limit, pagination, watermark |
| JMS | Possible, but listeners are typical | Ack, transaction, redelivery, ordering |
| AMQP | Possible, but listeners are typical | Ack/nack, prefetch, DLQ, concurrency |
| Kafka | Client polls internally; SI usually uses a listener | Offset, group, partition, rebalance, retry |
| Internal QueueChannel | Yes | Capacity, receiveTimeout, poller, durability |

## 9. Delivery Semantics: Polling Does Not Guarantee Exactly-Once

One of the biggest design mistakes is equating **“each source item is polled once”** with **“each business action is processed once.”** Real-world systems have multiple failure windows:

~~~text
T1. Poller receives record from source.
T2. Handler begins processing.
T3. Handler writes result to target database and commits.
T4. Process crashes before marking the source as processed.
T5. On restart, the poller may pick up the record from T1 again.
~~~

If the handler is **not idempotent**, step T5 can generate duplicate invoices, send duplicate emails, or write data twice. Conversely, marking the source “processed” **before T3** risks losing data if the process crashes.

### 9.1. Comparing three delivery approaches

| Target model | Meaning | Typical achievement | Limitation |
| --- | --- | --- | --- |
| **At-most-once** | Never reprocess after one receive; data may be lost on error | Drop/early ack, no redelivery | Unsuitable for business logic that cannot tolerate data loss |
| **At-least-once** | Keep trying until success; duplicates may occur | Retry/redelivery, mark after processing | Handler must tolerate duplicates |
| **Effectively-once** | Observable business side effects happen only once even if messages are redelivered | Business idempotency key, unique constraints, transactions, and reconciliation | Does not mean the entire network/system only transfers the message once |

Some platforms offer strong processing guarantees within a specific transaction/stream boundary, but these **do not automatically extend** across files, SFTP, HTTP, and multiple independent databases. For multi-system polling consumers, **at-least-once + idempotent business operations** is usually a more realistic starting point than a blanket exactly-once promise.

### 9.2. Multi-layer idempotency

1. **Source filter:** prevents re-selecting already-seen files/records; must be persisted durably to survive restarts.
2. **Message idempotent filter:** uses a stable message/business key rather than relying solely on `MessageHeaders.ID`.
3. **Business idempotency:** persists a unique key when producing results so duplicates do not repeat side effects.
4. **Downstream API:** sends an `Idempotency-Key` or uses the API contract's dedupe mechanism if available.
5. **Reconciliation:** reconciles final state when an ACK is lost even though the operation may have succeeded.

For example, if a file is renamed or re-uploaded under a different name, **file path** may not be the best business key. You might need `partnerId + documentId + version` or a content checksum depending on the data contract. Content checksums also require care: two distinct documents with identical content may still need independent processing.

### 9.3. Dedupe table in the DB

Example structure for storing business keys:

~~~sql
CREATE TABLE processed_event (
    source_name VARCHAR(100) NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source_name, business_key)
);
~~~

One strategy is inserting the `processed_event` row **in the same transaction** as the business state change in the target DB. If a unique key conflict occurs, treat it as a known duplicate or check business state before skipping. Never write a “success” dedupe marker before an irreversible side effect finishes, as doing so can cause data loss.

**Warning:** If the handler calls an HTTP API that does not participate in the DB transaction, inserting dedupe + committing the DB still does not form a cross-network transaction. You need an outbox, target API idempotency, or reconciliation as required.

## 10. Transactions, Acknowledgments, and Poller Error Handling

### 10.1. Where are the transaction boundaries?

~~~mermaid
flowchart LR
    POLL["Poll source"] --> CHANNEL["MessageChannel"]
    CHANNEL --> PROCESS["Handler: process"]
    PROCESS --> DB["DB commit"]
    PROCESS --> API["Target HTTP / SFTP / Broker"]
    DB --> MARK["Mark source processed"]
    API --> MARK
    NOTE["Only components sharing the same transaction can be atomic together"] -.-> DB
    NOTE -.-> API
~~~

In Spring Integration, a **transaction advice** can be configured on an eligible polling endpoint. However, you must know:

- Which thread and scope does the transaction apply to?
- Does the `MessageSource` or `PollableChannel` support transactions/rollback?
- Does the handler execute synchronously on the same thread, or via an `ExecutorChannel`/separate executor?
- Do the broker/DB share the same transaction manager or a supported coordination mechanism?
- When the handler fails, can the source return the message, leave it for retry, or only log?

Do not assume putting `@Transactional` on a method makes files, SFTP, Kafka, DB, and HTTP roll back together. A file rename or an already-sent HTTP request cannot be rolled back by a standard JDBC transaction.

### 10.2. Classifying errors to choose a policy

| Error | Example | Typical appropriate handling |
| --- | --- | --- |
| **Transient source error** | SFTP disconnect, HTTP 503, DB timeout | Retry with backoff, reconnect, and alert on threshold |
| **Rate limit** | HTTP 429, API throttling | Respect Retry-After, slow down poll cadence |
| **Invalid data** | CSV missing required column, malformed JSON schema | Quarantine/reject with evidence; do not retry infinitely |
| **Valid data rejected by business rules** | Order with invalid customer | Record business status, route according to business rules |
| **Transient target error** | Target DB offline, broker outage | Do not mark source processed early; idempotent retry |
| **Configuration bug** | Wrong credentials, SFTP host key mismatch, wrong DB role | Stop fast retry loops, alert owner, fix configuration |
| **Poison message** | A message repeatedly throwing exceptions | Cap retries, move to a separate queue/quarantine, and monitor |

### 10.3. Error channel and errors inside a poll

Spring Integration provides `ErrorMessage`, error channels, advice, and error handlers. However, **the exception path depends on the endpoint, channel, scheduler, and flow execution model**:

- Synchronous handler errors can propagate back to the polling endpoint when running on the same call thread.
- Asynchronous handler errors may be routed through a separate error handling path, outside the original poll transaction.
- Errors occurring during source `receive()` need separate logging, alerting, and handling from parsing errors in the handler.
- An error handler that only **logs and swallows exceptions** can alter how the source decides to retry; you must understand adapter semantics.

When building an error flow, record **the original message or business key, source, attempt, exception class, trace ID, and owner** as needed; avoid dumping raw credentials or sensitive payloads verbatim into logs.

### 10.4. Retry with backoff instead of aggressive polling

Suppose SFTP goes down for 10 minutes. If every failed poll retries immediately, the application both increases load and floods logs.

An illustrative policy:

~~~text
First attempt: try on normal schedule.
Failure 1:     short delay, with jitter if multiple instances.
Failure 2:     increase wait duration.
Failure N:     threshold reached → alert, circuit breaker, or pause.
Recovery:      verify connection, re-read metadata, resume safely.
~~~

Do not apply the same retry policy to schema errors and network errors. Malformed data files usually belong in **quarantine**, whereas transient disconnections can be retried once the endpoint recovers. Retry counts and wait durations should be driven by operational targets, not arbitrary numbers.

### 10.5. Where should poison messages go?

~~~mermaid
flowchart TD
    M["Receive message"] --> V{"Data valid?"}
    V -->|No| Q["Quarantine + reason + owner"]
    V -->|Yes| P["Process"]
    P --> R{"Success?"}
    R -->|Yes| A["Ack/mark processed per contract"]
    R -->|Transient error| RETRY["Bounded retry + backoff"]
    RETRY --> P
    R -->|Unrecoverable automatically| DLQ["Error store / DLQ / manual review"]
~~~

A **DLQ** is a pattern that requires **a storage location, an owner, replay capability, and data protection**—not a `log.error(...)` followed by ignoring the message. For file/SFTP, you can use a quarantine directory with metadata; for JMS/AMQP/Kafka, you can use a broker/adapter dead-letter destination.

## 11. Backpressure, Batch Size, and Load Throttling

A polling consumer creates a **work supply cadence** for the handler. Good configuration must balance **latency**, **throughput**, and **source/target load**.

### 11.1. Three variables to measure

| Variable | Meaning | How to observe |
| --- | --- | --- |
| **Arrival rate** | How much new data appears at the source per second/minute | Broker lag, READY records, new file count, HTTP change count |
| **Service rate** | How much business work the handler completes per second/minute | Processed successes/second and processing duration |
| **Backlog** | Data that has arrived but not yet succeeded | Queue depth, file age, pending rows, consumer lag |

For example, the source creates **120 files/minute**, while the handler finishes **80 files/minute**. The backlog grows by about **40 files/minute** under steady conditions without additional parallelism. Merely decreasing `fixedDelay` will not solve this if the handler or DB is the bottleneck.

### 11.2. Increasing throughput cautiously in order

1. Measure per-step latency: poll source, message dispatch, parse, validate, target write.
2. Adjust `maxMessagesPerPoll` if the scheduler frequently finishes early while the source still has data.
3. Reduce empty polling I/O: increase delay, use adaptive backoff, or switch to event-driven if supported by the source.
4. Reduce connection overhead with proper pooling, while avoiding keeping stale broken sessions around too long.
5. Optimize handler/DB, batch operations, or asynchronous processing where transaction boundaries permit.
6. Increase concurrency or instance count only after establishing **claim/lock, idempotency, and ordering**.
7. Monitor the effects: backlog, memory, connection count, latency, and retry rate.

### 11.3. Unbounded `QueueChannel` can cause OOM

If the producer reads files quickly and pushes every message into an in-memory queue while the consumer is slow, heap usage grows. You should:

- Set an intentional **capacity**.
- Define behavior when `send()` fails or blocks.
- Throttle the source, pause the endpoint, or use a durable queue when necessary.
- Measure queue depth and wait times; avoid measuring only received message counts.
- Understand that `QueueChannel` can lose unprocessed data on JVM shutdown without a suitable persistent store.

### 11.4. Concurrency is not “fetching many messages per poll”

`maxMessagesPerPoll(20)` **does not mean** 20 threads process in parallel. Threading depends on the scheduler, executor, channel, handler, and adapter. A `DirectChannel` typically invokes the handler on the sending thread; an `ExecutorChannel` can dispatch via an executor; `QueueChannel` buffers messages for the consumer to pull.

If ordering per order or customer is required, you need **key-based partitioning, serial processing, or version checks**. Enabling multiple threads can improve throughput but cause completion order to diverge from source order.

## 12. Multi-Instance Execution and Duplicate Handling in Distributed Systems

A single-instance poller can already produce duplicates on restart. When deploying **two or more replicas**, the issue becomes more pronounced: both applications may see the same SFTP file or unprocessed database row simultaneously.

### 12.1. Three common deployment models

| Model | How it works | Pros | Safety conditions |
| --- | --- | --- | --- |
| **Single active poller** | Only one instance polls; others act as standby | Simple, easier ordering | Reliable leader election/failover, dead leader detection |
| **Multi-poller with shared claim** | Multiple instances poll; each item is conditionally claimed | Higher throughput | Shared lock/lease/metadata, expired lease recovery, and retry |
| **Partitioned polling** | Each instance owns a data subset by key/range | Easy to enforce ordering within a partition | Assignment coordination, rebalancing, and ownership transfer |

There is no “one-size-fits-all” model. An SFTP directory receiving a few files per day may not need multiple pollers; a large outbox table may require multiple workers, conditional claims, and backlog monitoring.

### 12.2. Why an in-memory accept-once filter is not enough

~~~text
Replica A                         Replica B
  list SFTP: report-01.csv          list SFTP: report-01.csv
  in-memory filter: unseen         in-memory filter: unseen
  download file                     download same file
  process                           duplicate processing
~~~

Two JVMs have **independent memory**. You cannot rely on a local filename set to synchronize a cluster. Depending on the adapter, consider a **persistent/shared metadata store** and an appropriate lock/claim mechanism; for instance, the Spring Integration ecosystem provides metadata store and lock registry options per source.

Even with shared metadata, you must consider when state is saved. If marked “received” before processing and the process dies, data may be missed; if marked late, it may be picked up again. Business-level idempotency remains essential.

### 12.3. Leases and reclaiming after worker crashes

In database polling, a row can carry `ownerId`, `claimedAt`, `leaseUntil`, and `attempt`. A worker claims via a **conditional update** inside a transaction; if the worker dies, the lease expires so another worker can reprocess it.

~~~text
READY --claim atomically--> IN_PROGRESS(owner=A, leaseUntil=t1)
IN_PROGRESS --completed--> PROCESSED
IN_PROGRESS --lease expired--> READY/RETRY
~~~

You must address the case where worker A **is still running after its lease expired** while worker B reclaims the item. This may require heartbeats/lease renewal, fencing tokens, or version checks at commit time. Leases are only one part of a deduplication and side-effect preservation strategy.

### 12.4. Ordering and data history

A poller picking files by name or timestamp does not guarantee **business order**. When two files `order-2.csv` and `order-1.csv` arrive out of order, applying updates blindly can let stale state overwrite newer state.

Design for:

- Business sequence/version if provided by the source.
- Key-based or partition-based processing rules.
- Stale event checks before mutating state.
- Procedures for handling missing or re-delivered versions.

Do not rely solely on `File.lastModified()` as a business event ordering guarantee, especially across systems with clock skew or copied files.

## 13. Endpoint, Connection, and Scheduler Lifecycle

Polling is a **lifecycle-managed task**. When the application starts, it must know whether to poll immediately; on shutdown, it must stop accepting new work and handle in-flight messages according to policy.

### 13.1. Startup

- [ ] Verify file/SFTP/DB/API sources are ready; if not, define retry/backoff and health behavior.
- [ ] Initialize the metadata store, mappings, and idempotency keys before the first poll cycle.
- [ ] Do not open multiple pollers on the same partition without shared coordination.
- [ ] Separate configurations for dev/test/prod; never accidentally point lab environments to production directories or credentials.
- [ ] Check whether endpoints have appropriate auto-startup settings and know how to pause them per runbook.

### 13.2. Shutdown and rolling deployments

- [ ] Prevent new poll cycles before or during service shutdown according to lifecycle hooks.
- [ ] Ensure in-flight handlers have a chance to finish/roll back within the shutdown grace period.
- [ ] Do not mark data processed while the business transaction has not committed.
- [ ] If messages remain in an in-memory `QueueChannel`, have you accounted for avoiding loss on process stop?
- [ ] Shared locks/leases are released or have a TTL so new instances can recover.
- [ ] Avoid running multiple app versions applying incompatible event schemas simultaneously without a compatibility plan.

In Spring Integration, endpoints typically participate in the Spring application context lifecycle and can be paused/started based on configuration capabilities. Bean names, control bus, or runtime management mechanisms must be verified for the target version; never assume stopping an endpoint immediately aborts all running handlers safely.

### 13.3. Connections and resources

| Source | Resources to manage | Failure symptoms |
| --- | --- | --- |
| Local file | File handles, disk IO, archive directory | Locked files, full disk, partial files |
| SFTP | Session, TCP connection, pool, remote server key | Timeouts, stale sessions, server rejections |
| JDBC | Connection pool, transaction, cursor, locks | Connection leaks, deadlocks, pool exhaustion |
| HTTP | HTTP client pool, TLS, rate limits | 429, resets, timeouts, desynchronized cursor |
| JMS/AMQP | Connection, consumer channel/session, ack | Disconnects, redeliveries, stopped consumer |
| Kafka | Consumer group, offset, partition assignment | Rebalancing, rising lag, unprocessed records |

Do not handle connection failures with an unbounded session-creation loop. Configure timeouts, connection validation, retry/backoff, and per-source metrics.

## 14. Observability: Knowing Whether the Poller is Making Progress

“The application is running” does not prove the poller is actually fetching and processing the right data. You must monitor both **polling activity** and **business progress**.

### 14.1. Key metrics

| Metric | Interpretation | When to alert? |
| --- | --- | --- |
| **poll attempts** | Number of scheduler poll triggers | Drops to 0 unexpectedly while source still has data |
| **empty poll ratio** | Ratio of poll cycles yielding no messages | Too high may mean over-polling; though normal when idle |
| **poll duration** | Time for a receive and processing cycle within the measured scope | Sustained growth causing schedule drift |
| **messages received** | Messages pulled from source/channel | Distinct from processed successes |
| **processed successes** | Valid business tasks completed | Fails to rise despite increasing incoming work |
| **processing failures** | Errors by source/handler/target | Sudden spike or repeated failures on the same business key |
| **retry attempts** | Retry counts and causes | Error loop without progress |
| **backlog depth/age** | Quantity and age of unprocessed data | Exceeds SLA-dependent thresholds |
| **duplicate detected** | Messages with previously seen business keys | Spikes after restarts/rebalances/timeouts |
| **last successful commit** | Timestamp of most recent successful business persistence | Too stale while the source generates data |
| **connection errors** | Unreachable SFTP/HTTP/DB/broker | Categorized by source, environment, and error code |

Define metrics by **source, flow, endpoint, target, and environment**; avoid embedding payloads or sensitive PII into metric labels, which causes extreme cardinality and data leaks.

### 14.2. Logging and tracing

Suggested log entry:

~~~json
{
  "flow": "sftp-orders-inbound",
  "pollId": "poll-2026-11-23-00031",
  "source": "partner-A",
  "businessKey": "ORDERS-000387",
  "messageType": "ORDER_FILE",
  "attempt": 2,
  "stage": "VALIDATE_AND_STORE",
  "result": "RETRYABLE_ERROR",
  "durationMs": 142,
  "traceId": "trace-lab-531",
  "target": "order-db"
}
~~~

This JSON sample is illustrative only; it is not Spring Integration's default format. When sources contain PII, never log raw file contents, passwords, tokens, or private keys. Use safe reference keys and log access controls.

### 14.3. Three alerts more useful than “process alive”

1. **No progress:** the source has pending work, yet `lastSuccessfulCommit` does not advance.
2. **Backlog age:** the oldest unprocessed file/record exceeds the business-tolerable age limit.
3. **Repeated failure:** the same connection error or business key exceeds a retry threshold.

An empty poll when the source genuinely has no data is normal. Alerts should combine source signals and data-generation schedules, avoiding false alarms whenever polling returns `null`.

### 14.4. Diagnosing from symptoms

| Symptom | Primary hypothesis | Evidence to look for |
| --- | --- | --- |
| No messages despite files at source | Overly strict filter, endpoint not started, wrong directory | Endpoint state, folder listing, filter logs |
| Very frequent polls with no progress | Incomplete files, parse errors, empty polls, retry loops | Poll duration, rejects, staging area |
| Errors only appear after restart | In-memory-only filter, non-persistent metadata, unreleased locks | Duplicate keys, metadata store, startup sequence |
| Increasing poll rate makes it slower | Target DB/HTTP bottleneck, full connection pool, contention | Sink latency, queue depth, pool metrics |
| Two replicas process the same file | Missing shared claim/metadata or fencing | Instance IDs, lock logs, dedupe violations |
| One message stalls the entire flow | Poison data, infinite retries, missing quarantine | Business key, error flow, attempt count |
| Message dequeued but data missing | Premature ack/mark, async handler, transaction failure | Handler completion, DB commit, channel semantics |

## 15. Designing Tests for Polling Consumers

Because polling is affected by **time, schedulers, and I/O**, tests should separate **processing logic** from **real-time poll schedule mechanics**.

### 15.1. Three testing layers

1. **Unit tests:** test parsers, idempotency keys, state transitions, and retry classification with plain data without running a scheduler.
2. **In-JVM integration tests:** create mock `MessageSource`/channels or temporary directories, start the Spring context, await message delivery, and verify the handler.
3. **End-to-end/contract tests:** connect to mocked or authorized SFTP/DB/brokers to test mapping, transactions, retries, acks/offsets, and target readbacks.

Instead of an arbitrary `Thread.sleep(5000)` hoping a poll has fired, use **eventual assertions with timeouts** in tests, keeping wait times bounded and capturing logs on failure. Test schedules should be tuned fast enough for test environments without changing protocol semantics.

### 15.2. Core test matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| **PC-01** | Empty file directory, poll triggered | Handler not invoked, no spurious exceptions |
| **PC-02** | Add one complete CSV file | Emits exactly one message on a valid receive |
| **PC-03** | Add a `*.tmp` file not matching filter | Not processed before publication |
| **PC-04** | File actively being written, extension not renamed yet | Incomplete file is not processed |
| **PC-05** | 12 files present, `maxMessagesPerPoll=5` | One cycle receives at most 5 messages; subsequent cycles continue |
| **PC-06** | Source returns `null` | No empty message created or handler called with null payload |
| **PC-07** | Two poll cycles see the same file | Contract filter/idempotency prevents duplicate business side effects |
| **PC-08** | App restart after a file is processed | Persistent metadata/idempotency prevents repeated side effects |
| **PC-09** | Handler fails before commit | Source/message retained for retry or quarantined per policy |
| **PC-10** | Handler commits successfully but ACK is lost | Retry causes no duplicate side effect |
| **PC-11** | Malformed CSV schema | Routed to quarantine, no infinite retry |
| **PC-12** | Transient SFTP or HTTP timeout | Retry/backoff, threshold alert, no busy loop |
| **PC-13** | HTTP returns 429 with Retry-After | Slows cadence according to API contract |
| **PC-14** | QueueChannel full | Producer handled per send timeout/backpressure policy |
| **PC-15** | Handler slower than poll interval | Does not cause uncontrolled backlog/OOM |
| **PC-16** | Two instances see the same file/DB row | Shared claim/lock and idempotency prevent duplicate effects |
| **PC-17** | A worker crashes after claiming | Lease/recovery allows safe reprocessing |
| **PC-18** | Out-of-order events arrive | Versioning/business rules prevent stale state overwrites |
| **PC-19** | Stop endpoint with active backlog | Stops taking new work violating policy; drains or recovers in-flight work |
| **PC-20** | Handler completes but source metadata not yet updated | Reconciliation detects it; retry causes no duplicates |
| **PC-21** | Database has no READY records | Poll completes normally without excessive full-table scans |
| **PC-22** | SFTP connection drops and recovers | Safe reconnect without reusing broken stale sessions |
| **PC-23** | Transform fails before outbound call | Error flow logs accurate source and business key |
| **PC-24** | Kafka/JMS message-driven endpoint (if used) | Consumer listener is not confused with QueueChannel's PollingConsumer |

### 15.3. One test many people miss

**Scenario:** the poller reads a file, the parser creates an order in the target DB, and the process crashes **before marking the file as processed**.

**Wrong:** testing only that the first run creates one record; failing to test restart.

**Right:** restart, let the poller see the file again, and verify **only one order exists** thanks to a unique business key/transaction, while source metadata/state is safely recovered or handled.

### 15.4. Testing `QueueChannel` vs. testing `MessageSource`

For `QueueChannel`, tests must verify that when a message is present the consumer receives it via `receive()`, and when empty no processing occurs. Check capacity, blocking timeouts, and shutdown.

For `MessageSource`, tests must verify that **the external source is scanned/read properly**: file patterns, SFTP paths, DB claims, or HTTP cursors. Do not use internal queue tests as proof that an SFTP adapter safely handles duplicates and reconnects.

## 16. Capstone Lab: From CSV Files into a Database

**Goal:** use polling to import mock order files into a simulated data store or test database, with deduplication, error file classification, and backlog observability. No real broker or SFTP account is needed to begin.

### 16.1. Context

Partner DemoPartner drops CSV files following this template:

~~~csv
document_id,order_id,customer_id,amount
FILE-LAB-001,ORD-LAB-001,CUST-LAB-01,125000
FILE-LAB-001,ORD-LAB-002,CUST-LAB-02,82000
~~~

Assumptions:

- Each file has a stable `document_id` assigned by the producer.
- Each order has an `order_id` serving as a unique business key within the partner scope.
- The producer only renames the file to `*.csv` after writing completes.
- The consumer validates the schema and never blindly trusts amounts or filenames.
- Results are written to a test DB with an appropriate unique key.

### 16.2. Suggested directory structure in a personal lab environment

~~~text
lab/
  in/             # Producer publishes completed files
  processing/     # Claimed files (if implemented)
  archive/        # Processed and verified files
  quarantine/     # Malformed files or files needing review
  evidence/       # Test reports/logs without secrets
~~~

This structure is **a suggestion for practitioners**, not a requirement to create directories in the lesson repository.

### 16.3. Implementation steps

**Step 1 — Initialize the source.** Use an adapter that periodically reads files, filtering by `*.csv`; configure fixed delay and a bounded `maxMessagesPerPoll`.

**Step 2 — Publish files.** Producer writes `*.uploading`, verifies completion, then renames to `*.csv`. Prevent the consumer from reading partially written files.

**Step 3 — Create the message contract.** Each message carries the file path/stream plus metadata `partnerId`, `documentId`, `traceId`; a transformer parses it into a validated DTO. `documentId` inside the payload must be verified per contract rather than trusting the filename as a unique key.

**Step 4 — Persist business data.** Process each row into the DB using the business key. For valid duplicates, do not insert duplicate rows; for data errors, record status/quarantine.

**Step 5 — Mark completion.** Only move files to archive or mark processed after commit conditions are met. If a file has multiple records and fails mid-way, choose an **all-or-nothing**, partial recovery, or line-level quarantine policy; document the choice clearly.

**Step 6 — Inject faults.** Make the DB temporarily return a timeout after partial processing; restart the app and verify no duplicate results occur.

**Step 7 — Increase load.** Add 100 mock files, measure poll counts, processing time, and backlog age; adjust delay/batch sizes with verification.

**Step 8 — Simulate two instances.** If adding a replica, implement shared metadata/claim or partitioning. Let both see the same file and verify the side effect occurs only once per business key.

**Step 9 — Handover.** Write runbooks for “SFTP unavailable,” “CSV malformed,” “DB timeout,” “duplicate after restart,” and “backlog age exceeded.”

### 16.4. Lab diagram

~~~mermaid
flowchart LR
    P["Producer\n*.uploading → *.csv"] --> IN["File inbound adapter\nSource poller"]
    IN --> CH["MessageChannel"]
    CH --> VAL["Validate + Transform"]
    VAL --> IDEMP["Idempotent check"]
    IDEMP --> DB["Test database"]
    DB --> DONE["Archive + Evidence"]
    VAL -->|Invalid schema| BAD["Quarantine"]
    DB -->|Transient error| RETRY["Controlled retry"]
    RETRY --> DB
~~~

### 16.5. Acceptance criteria

- [ ] Only complete files matching the pattern are processed.
- [ ] Empty polls produce no unnecessary errors.
- [ ] Valid files are transformed to schema and data-checked.
- [ ] Invalid data does not trigger infinite retries; quarantine and an owner exist.
- [ ] Repeated arrivals of the same business key produce no unintended duplicate side effects.
- [ ] Mid-processing crashes can recover or retry per policy.
- [ ] Sources are never marked processed before commit conditions are satisfied.
- [ ] Backlog and processing times are measurable and have alert thresholds.
- [ ] Increasing the poll rate does not bottleneck the app or lose control of memory.
- [ ] Limitations are documented: persistent metadata, multi-instance behavior, sessions, and transactions.

### 16.6. Advanced exercises

1. Swap the local file source for an **SFTP test server**, checking host keys and remote file filters.
2. Swap the source for a **JDBC outbox**, testing two workers claiming the same record and crash/reclaim behavior.
3. Swap to an HTTP changes API with a cursor; inject a failure right after processing a page but before saving the cursor.
4. Decouple a slow handler using a `QueueChannel` and measure queue depth; compare with `DirectChannel`.
5. Add separate source error flows and business error flows; categorize retries by root cause.
6. Compare against a **JMS/AMQP/Kafka listener** flow, explaining how ordering/ack/delivery differ from file polling.

## 17. Anti-Patterns and Common Design Mistakes

| Anti-pattern | Why it is dangerous | How to improve |
| --- | --- | --- |
| **Polling every few milliseconds without reason** | Empty polls waste I/O and flood logs | Measure required latency; choose delay/adaptive backoff |
| **Setting an excessively large maxMessagesPerPoll** | One cycle ties up the scheduler, spikes memory and target load | Bound batches; measure duration and throughput |
| **Using DirectChannel then trying to call receive()** | DirectChannel is subscribable, not pollable | Use QueueChannel when the consumer needs to pull messages |
| **Confusing PollingConsumer with SourcePollingChannelAdapter** | Configuration, metrics, and errors end up in the wrong place | Clearly distinguish polling a source vs. polling a channel |
| **Using an unbounded QueueChannel to go faster** | Faster producers than consumers bloat heap | Bound queues, apply backpressure, or use a durable broker |
| **Trusting an in-memory filter as exactly-once** | Restarts or multiple instances cause duplicates | Persistent/shared metadata + business idempotency |
| **Marking a file processed before DB commit** | Crashes cause data loss | Tie marking to commit state and appropriate recovery |
| **Marking source late without deduplication** | Retries produce duplicate side effects | Stable business keys, unique constraints, idempotent sinks |
| **Increasing concurrency without claiming** | Multiple workers grab the same row/file | Locks/leases/partitioning and reconciliation |
| **Retrying malformed CSVs forever** | Poison messages stall flows and waste resources | Quarantine + reason + governed replay |
| **Hiding errors with catch-log-and-continue** | Source may think the message succeeded | Classify errors, manage acks/transactions properly |
| **Relying entirely on lastModified** | File copies/clock skew break ordering/freshness | Business IDs, manifests/markers, stable contracts |
| **Deleting files immediately after polling** | Downstream handlers may fail | Archive/delete only after completion criteria are met |
| **Mixing tokens into Message headers/logs** | Credential leaks | Secret managers, redaction, never log raw tokens |
| **Treating poll success as business success** | Source was read, but target has not committed | Measure receive, process, commit, and readback separately |
| **Failing to separate source errors and handler errors** | Retries/alerts misfire | Error flows with classification and ownership |

### 17.1. When NOT to use Polling Consumer

Do not pick polling just because it is easy to visualize if the source system provides a reliable **listener/webhook/stream** with matching semantics. For instance, a JMS listener or Kafka consumer container usually handles broker-native message reception well, whereas building a custom timer to repeatedly query an API/broker can increase latency and operational burden.

Conversely, **webhooks** are not automatically better than polling: you must handle source authentication, producer retries, downtime, duplicates, and ordering. Choose the pattern based on **integration contracts and operational capability**, not technology preference.

## 18. Production Readiness Decision Checklist for Polling

### 18.1. Pattern selection checklist

- [ ] The source **lacks or is unsuitable for** push/listener mechanisms for our needs, giving polling a clear rationale.
- [ ] Polling an **external MessageSource** is clearly distinguished from polling a **PollableChannel** in Spring Integration.
- [ ] Expected throughput, acceptable latency, and source limits are defined.
- [ ] Contracts exist for message unit, schema, encoding, stable business key, and how data completion is signaled.
- [ ] The poller has intentional fixed delay/rate/cron settings and timezone if needed.
- [ ] `maxMessagesPerPoll`, receive timeout, and network timeouts are understood and tested separately.
- [ ] Decisions are clear on when to use DirectChannel, QueueChannel, ExecutorChannel, or a durable broker.

### 18.2. Correctness and safety checklist

- [ ] Duplicate prevention exists across retries/restarts and, if applicable, multiple instances.
- [ ] Transaction boundaries, ack/mark processed points, and non-rollbackable downstream effects are documented.
- [ ] Source data is not deleted or archived before defined completion criteria are satisfied.
- [ ] Poison message handling, quarantine/DLQ, and governed replay exist.
- [ ] Concurrency and ordering have contracts; stale versions cannot overwrite newer state.
- [ ] Metadata stores, locks/leases, or claim mechanisms match the source and topology.
- [ ] Connection credentials are protected and never logged or placed into unnecessary payloads.
- [ ] App has least-privilege access to files/DB/brokers; no overly broad admin credentials.

### 18.3. Operations and recovery checklist

- [ ] Metrics exist for poll attempts, empty polls, processing successes, retries, backlog age, and last successful commit.
- [ ] A **no progress** alert exists for when the source has pending work but the consumer makes no headway.
- [ ] Runbooks exist for source unavailable, malformed data, target timeout, and post-crash retry.
- [ ] Startup, graceful shutdown, and rolling deployments are tested.
- [ ] If running multiple replicas, duplicates/lease expiration/failover have been simulated.
- [ ] Evidence of negative testing and fault injection exists in authorized environments.
- [ ] On-call engineers can distinguish source poll errors from parser, handler, or outbound adapter errors.

### 18.4. Short decision tree

~~~mermaid
flowchart TD
    START{"Does the source have a suitable push/listener?"}
    START -->|Yes| PUSH["Evaluate event-driven\nAck, retry, ordering"]
    START -->|No / unsuitable| POLL{"Where does the data reside?"}
    POLL -->|File/SFTP/DB/HTTP| SOURCE["Source polling endpoint\nMessageSource + Poller"]
    POLL -->|Internal QueueChannel| CHANNEL["PollingConsumer\nPollableChannel + Poller"]
    SOURCE --> CONTRACT["Data contract + ready/claim"]
    CHANNEL --> CONTRACT
    PUSH --> CONTRACT
    CONTRACT --> SAFE["Idempotency + transaction/ack + error flow"]
    SAFE --> OPS["Backpressure + observability + recovery"]
    OPS --> PROD["Re-verify before production"]
~~~

If you cannot answer **“at what exact moment is data considered successfully received?”**, do not optimize `fixedDelay` or increase concurrency yet. Clarify success semantics and recoverability first.

## 19. Self-Check Questions and Summary

### 19.1. Self-check

1. In what action that determines message reception timing does a **Polling Consumer** differ from an **Event-Driven Consumer**?
2. Which Spring Integration polling endpoint type does an inbound file adapter using a `MessageSource` create?
3. Why does a service activator receiving from a `QueueChannel` need a poller, whereas a handler receiving from a `DirectChannel` usually does not?
4. Does `maxMessagesPerPoll(10)` mean 10 parallel threads or that 10 files are always processed successfully?
5. If `receiveTimeout` is increased, does that automatically fix TCP timeouts in SFTP?
6. Why is an in-memory file accept-once filter insufficient to prevent duplicates after a restart?
7. When a DB write succeeds and the process crashes before marking the file processed, what controls are needed?
8. When two replicas poll an outbox table simultaneously, why is `SELECT status='READY'` insufficient?
9. Does a Kafka client using `poll()` automatically equate to a Spring Integration `PollingConsumer`?
10. Which metrics help detect a poller that is still alive while data at the source piles up?

**Reference answers:** (1) scheduled pull vs. notification/push; (2) `SourcePollingChannelAdapter`; (3) `QueueChannel` is a `PollableChannel`, `DirectChannel` is a `SubscribableChannel`; (4) no; (5) no; (6) metadata is not durable/shared; (7) idempotency and safe recovery; (8) requires claim/lock/transaction; (9) no; (10) backlog age alongside last successful commit.

### 19.2. Key takeaways

The **Polling Consumer Pattern** enables an application to proactively pull messages from sources or channels that do not push data. In **Spring Integration**, there are two central forms:

- **`SourcePollingChannelAdapter`** polls a **`MessageSource`**: suited for files, SFTP, JDBC, or external sources readable on a schedule.
- **`PollingConsumer`** polls a **`PollableChannel`** such as **`QueueChannel`** and invokes a handler.

A poller coordinates **when to try receiving** and **how much to try receiving**, and does not by itself determine **when business work is truly complete**. When wiring inbound/outbound adapters, gateways, and `MessageChannel` across files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, always define the **message contract, ack/transaction, data ownership, retries, idempotency, backpressure, connection lifecycle, and auditing** according to each system's semantics.

**Final rule:** *Don't just verify that the poller received the message; prove the message was processed accurately, created no unintended duplicate side effects, and can recover if any step fails.*
