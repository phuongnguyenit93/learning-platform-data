# Outbound Flows: Sending Messages to External Systems

## Learning Objectives

After this lesson, you will be able to:

- Describe the path of a message from a **MessageChannel**, through an **outbound channel adapter**, to an external system.
- Distinguish a one-way outbound adapter from an outbound gateway based on business reply requirements.
- Identify the responsibilities of the channel, handler, converter, payload, headers, and connection in a send operation.
- Build a Java DSL flow that exports CSV to a file using an outbound adapter and verify the result.
- Analyze retries, duplicate sends, acknowledgment timing, transactions, send rate, and connection lifecycle.

## 1. Where Does Outbound Sit in a Messaging Architecture?

After receiving and processing data, an application often needs to send results to another system: exporting CSV files for a partner, publishing events to Kafka, sending messages via JMS/AMQP, calling an HTTP API, uploading files to SFTP, or updating a database. Each target has its own protocol, format, acknowledgment policy, and resource limits. If business logic manages each client directly, changing the target system causes unnecessary modifications across the codebase.

In **Spring Integration**, endpoints exchange **Message** objects through **MessageChannel** instances. An **outbound channel adapter** is an endpoint at the outbound boundary: it receives a message from a channel and performs a write or send operation to an external system. Business processors can produce standardized data without knowing the connection details of files, SFTP, HTTP, JMS, AMQP, Kafka, or databases.

For example, an order-processing service creates a message describing an approved order. The message travels through a channel to an outbound adapter that writes a CSV to a partner exchange directory. If the target switches to Kafka, you can keep the upstream business processing and adjust the data normalization step, the adapter, and the delivery contract of the new target.

~~~mermaid
flowchart LR
    A["Business logic / Transformer<br/>creates message"] --> C["MessageChannel<br/>outboundOrders"]
    C --> O["Outbound channel adapter<br/>Message handler"]
    O --> X["External system<br/>File / SFTP / HTTP / JMS<br/>AMQP / Kafka / Database"]
    O -. "Protocol-level error or acknowledgment" .-> E["Error handling<br/>Retry / Observability"]
~~~

**Outbound is defined from the perspective of the Spring Integration application.** A message may be produced by an inbound adapter, a transformer, a service activator, or a Java service. The endpoint is called an outbound adapter because it **consumes a message to produce an effect on an external system**.

## 2. The Path from MessageChannel to the Target System

A send operation can be broken down into seven stages:

| Stage | Component | Responsibility |
| --- | --- | --- |
| 1. Preparation | Handler, transformer, or application | Creates the properly formatted payload and adds required headers |
| 2. Internal send | Producer | Sends the Message to a MessageChannel |
| 3. Dispatch | MessageChannel | Invokes a subscriber or buffers the message for later retrieval by a consumer |
| 4. Consumption | Outbound endpoint | Receives the message and reads payload and headers |
| 5. Mapping | Adapter/converter | Builds a file, HTTP request, broker record, or write command |
| 6. I/O | Client, session, or connection | Performs the operation against the external system |
| 7. Outcome | Adapter and error handling | Records protocol-level outcome or detects errors |

Three points in time must be distinguished:

1. **The message has been accepted by the channel:** this does not guarantee the external system has received the data.
2. **The adapter has performed the send operation:** the confirmation level depends on the protocol, client, and configuration.
3. **The target system's business processing is complete:** this may happen later or only be known through a separate response flow.

For example, a Kafka producer receiving a broker acknowledgment that a record was stored does not mean the final consumer has processed that record. An HTTP API returning 202 Accepted may only have queued asynchronous work. Succeeding in writing a file does not prove the partner has read it.

## 3. How Do Outbound Adapters and Outbound Gateways Differ?

An **outbound channel adapter** follows a **one-way** model: it receives a message, causes an external side effect, and does not return a business reply message back into the flow. An **outbound gateway** serves **request–reply**: it sends a request, receives a response, and emits that response as a message for the flow to continue processing.

| Requirement | Component to Consider | Example |
| --- | --- | --- |
| Send data when the flow needs no returned body | Outbound channel adapter | Writing a file, publishing a Kafka event, sending a JMS message |
| Must use the response to decide the next step | Outbound gateway | HTTP API returning a transaction ID or customer details |
| Receive data from an external source into a channel | Inbound adapter | Scanning files from a directory |
| External caller invokes the app and waits for a result | Inbound gateway | HTTP POST returning a response based on processing results |

~~~mermaid
flowchart TB
    subgraph A["Adapter: one-way"]
      A1["MessageChannel"] --> A2["Outbound adapter"] --> A3["Target system"]
    end
    subgraph B["Gateway: request-reply"]
      B1["Request channel"] --> B2["Outbound gateway"] --> B3["Target system"]
      B3 --> B2
      B2 --> B4["Reply channel"]
    end
~~~

**One-way does not mean error-free or fully asynchronous.** An adapter can still block while writing a file, wait for a client-level acknowledgment, or throw an exception. The distinction lies in **the business reply contract within the messaging flow**.

When analyzing requirements, ask: *Does the next step need response data from the target system?* If yes, a gateway or an asynchronous reply mechanism with a correlation ID fits better. If you only need to send/write and manage success/failure via the client's mechanism, an outbound adapter is usually sufficient.

## 4. Message Contracts at the Outbound Boundary

A Message consists of a **payload** and **headers**. The adapter must be able to translate this information into an operation understood by the target system.

~~~text
Message
├── payload: String / byte[] / File / DTO / ...
└── headers
    ├── id, timestamp
    ├── correlationId or traceId (if present)
    └── target-adapter metadata (if configured)
                 |
                 v
          Outbound adapter
                 |
                 v
       File / HTTP / JMS / Kafka / SFTP / DB
~~~

Contract examples:

- **File:** file content and filename, duplicate-name handling mode, target directory.
- **HTTP:** URL, method, body, Content-Type, and mapped HTTP headers.
- **JMS/AMQP:** payload converted according to the broker's message contract, destination or routing key, delivery properties.
- **Kafka:** topic, key, value, serializer; broker metadata is not automatically equivalent to internal headers.
- **Database:** data/update statement, record keys, transaction boundaries, and conflict policy.

| Decision | Questions to Answer |
| --- | --- |
| Payload type | Does the adapter support it directly or does it need a transformer/converter? |
| Format | Which schema/version of CSV, JSON, XML, bytes, or records? |
| Target destination | Where are the filename, topic, queue, URL, or table determined? |
| Metadata | Which headers are mapped to the external protocol, and which are internal only? |
| Business identifier | Which event ID/order ID stays stable across retries? |
| Data security | Could credentials or sensitive information leak into logs, URLs, or filenames? |
| Contract evolution | How does the partner handle new versions and format errors? |

Data should be normalized **before** the adapter. For instance, a handler produces an OrderExport object; a transformer converts it to CSV for file export or JSON for Kafka publishing. This keeps business code decoupled from transport formats.

## 5. Java DSL Example: Sending CSV from a MessageChannel to a File

The following example creates a **DirectChannel** named exportChannel. A service sends a message containing CSV content and a filename header. The outbound adapter consumes the message and writes it to the **./data/export** directory.

With Spring Boot, use the Spring Integration dependencies (typically via spring-boot-starter-integration) and **spring-integration-file** compatible with your Spring Boot version. The example illustrates a one-way send path rather than a complete order-export workflow.

### 5.1. Defining the Channel and Adapter

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OutboundFileConfiguration {

    @Bean
    public MessageChannel exportChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow exportFileFlow() {
        return IntegrationFlow.from("exportChannel")
            .handle(Files.outboundAdapter(new File("./data/export"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**Configuration breakdown:**

1. **exportChannel():** the channel receiving messages from the producer.
2. **IntegrationFlow.from("exportChannel"):** connects the flow to the channel; the outbound adapter is the subscriber.
3. **Files.outboundAdapter(...):** creates the endpoint that writes data to the target file.
4. **autoCreateDirectory(true):** allows creating the target directory if it does not exist and the application has write permissions.
5. **fileNameGenerator(...):** retrieves the filename from the FileHeaders.FILENAME header. The producer must supply a valid filename.
6. **fileExistsMode(FileExistsMode.FAIL):** raises an error if the file already exists, preventing accidental overwrites in the example.
7. **handle(...):** executes a one-way side effect. The flow does not continue with a business response from the file adapter.

### 5.2. Service Sending the Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderExportService {

    private final MessageChannel exportChannel;

    public OrderExportService(
            @Qualifier("exportChannel") MessageChannel exportChannel) {
        this.exportChannel = exportChannel;
    }

    public void export(String orderId, long total) {
        // In practice, validate orderId before using it as a filename.
        String csv = "orderId,total\n" + orderId + "," + total + "\n";

        Message<String> message = MessageBuilder.withPayload(csv)
            .setHeader(FileHeaders.FILENAME, "order-" + orderId + ".csv")
            .build();

        boolean accepted = exportChannel.send(message);
        if (!accepted) {
            throw new IllegalStateException("Failed to send message");
        }
    }
}
~~~

When calling the service with order ID **O-1001** and total **150000**, the adapter attempts to write **./data/export/order-O-1001.csv**:

~~~csv
orderId,total
O-1001,150000
~~~

With DirectChannel, the handler typically runs synchronously on the sender's thread. If writing the file throws an exception, the error may propagate back to the caller; the send method does not always just return false. If you replace the channel with an asynchronous or queued channel, the return value of send **is no longer sufficient to infer that the file was written**.

**Scope of this example:** it does not handle CSV escaping when data contains commas or newlines, does not validate filenames against path traversal, lacks retry/reconciliation mechanisms, and has no completion-publication convention. In production, use a CSV encoder, validate filenames, decide on a collision policy, and ensure safe file handoff.

### 5.3. Verification Exercise

1. Start the application containing both classes above.
2. Call OrderExportService's export method with ID **O-1001** and total **150000**, from an integration test or an appropriate entry point.
3. Verify the file appears in **./data/export**, containing the two CSV lines shown in the example.
4. Call it again with the same ID: the **FileExistsMode.FAIL** policy will refuse to overwrite the existing file.
5. Send a different ID to observe the adapter continuing to export a new file.

Do not treat verifying the send call as confirmation that the partner has received the data. For files, inspect the target file; for brokers, consider producer acknowledgments; for business completion, require separate evidence of partner processing.

## 6. Role of MessageChannel in Send Rate and Timing

The adapter consumes messages, but **the channel upstream of it** determines how messages reach the handler:

| Channel Type | Dispatch Behavior | Outbound Consequences |
| --- | --- | --- |
| **DirectChannel** | Subscriber usually runs immediately on the sender thread | Slow I/O can block the producer thread; synchronous errors propagate back easily |
| **ExecutorChannel** | Hands work off to an executor | Producer can proceed sooner; requires managing thread pool, queue, and async errors |
| **QueueChannel** | Buffers messages; consumer pulls actively | Requires a polling consumer; must choose capacity and full-queue behavior |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Can send to multiple targets; must handle per-branch failures and partial success |

### 6.1. Does Outbound Need a Poller?

With DirectChannel or ExecutorChannel, the endpoint is normally triggered when a message arrives. **A poller is not required simply because it is an outbound adapter.** However, if the adapter pulls messages from a **PollableChannel** such as QueueChannel, a polling consumer must actively fetch messages from the queue.

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel<br/>queued messages"]
    T["Consumer poller<br/>governs fetch cadence"] -.-> Q
    Q --> O["Outbound adapter"]
    O --> D["External system"]
~~~

The poller in this diagram coordinates **fetching messages from an internal channel to send**, unlike the poller on an inbound file/SFTP/database adapter which actively queries **an external source to receive**.

QueueChannel uses memory by default. If the application stops unexpectedly, queued messages are not guaranteed to survive. When durability and recovery of pending outbound messages are needed, design an appropriate backing store or use an outbox/durable queue.

### 6.2. Backpressure and Overload

If upstream produces 1,000 messages/second while the target system can only sustain 100 messages/second, a backlog will build up. Switching from DirectChannel to ExecutorChannel does not create extra capacity at the target; it may simply shift the bottleneck into a task queue. You must bound concurrent requests, queue capacity, send rate, timeouts, and apply an appropriate retry policy.

## 7. Sending to Different External Systems

The general role is the same, but acknowledgment points and I/O constraints depend on the technology:

| Target | Common Operation | Considerations |
| --- | --- | --- |
| **File** | Write payload to disk | Filename, name collisions, write permissions, file completion state |
| **SFTP** | Upload file to remote directory | Session, authentication, timeout, reconnect, temporary name and rename |
| **HTTP** | Send request to API | URL, method, headers, status, timeout; use a gateway if the flow needs the response |
| **JMS** | Send message to destination | Converter, transactions, producer config, and broker policy |
| **AMQP** | Publish via exchange/routing key | Publisher confirm/return when needed, routing, and requeue/DLQ on consumer side |
| **Kafka** | Publish topic/key/value record | Serializer, partition ordering, producer acknowledgment, retry, and transactions |
| **Database** | Insert/update data via JDBC | Update statement, unique keys, deadlocks, and transaction boundaries |

**For file/SFTP:** if the partner continuously scans the directory, they might see a file before writing finishes. Typically you need a **write temporary name → finish writing → rename/publish** convention. Whether rename is atomic depends on the filesystem or SFTP server and should be verified in practice.

**For HTTP:** receiving a 2xx status code may only prove the API accepted the request. In particular, HTTP 202 Accepted usually indicates work will be processed later. If you need the response body for a subsequent step, an outbound gateway is better suited than an outbound adapter.

**For JMS/AMQP/Kafka:** producer/broker acknowledgment differs from confirmation that the consumer executed the business logic. When connectivity drops right after sending, the state may be ambiguous; retrying risks creating duplicates. You need idempotency keys on the receiving system and appropriate acknowledgment policies.

**For databases:** the success of an update statement normally belongs to that database's transaction. Do not assume this transaction automatically covers subsequent HTTP/SFTP/Kafka calls.

## 8. Where Do Outbound Errors Occur?

An outbound flow can fail before payload conversion, while connecting, during transmission, or after the target accepts the data before returning an acknowledgment.

~~~mermaid
flowchart TD
    M["Message from channel"] --> V{"Valid message contract?"}
    V -- "No" --> B["Quarantine data or fix contract"]
    V -- "Yes" --> S["Outbound adapter sends"]
    S --> R{"Client outcome"}
    R -- "Success" --> OK["Record progress per policy"]
    R -- "Transient error" --> RET["Bounded retry with backoff"]
    R -- "Unknown state" --> UN["Reconciliation + idempotency"]
    R -- "Unrecoverable error" --> DL["Quarantine / alert"]
    RET --> S
~~~

Typical failures:

- **Contract mismatch:** unsupported payload, JSON serialization failure, blank filename, or invalid topic.
- **Connectivity:** timeout, DNS failure, closed SFTP session, unavailable broker.
- **Target rejection:** HTTP 4xx/5xx, missing write permissions, database constraint violation, or misrouting.
- **Ambiguous state:** the request left the client, but the connection dropped before receiving acknowledgment.
- **Overload:** exhausted connection pool, full executor queue, target system rate limiting.

### 8.1. Retry and Idempotency

Retry can recover from transient errors, yet it risks duplicate side effects if the outcome of the prior send is unknown. For example, an order-creation API call succeeds on the server, but the client times out; retrying without an idempotency key can create two orders.

A safe outbound strategy requires:

1. Separating **retryable errors** from **data/configuration errors that require fixing**.
2. Capping retry attempts and using appropriate backoff to protect the target.
3. Keeping a stable business key, such as **partnerId + orderId** or an event ID, across attempts.
4. Persisting failed messages or incomplete states for follow-up handling.
5. Reconciling with the target when it is unclear whether a previous send succeeded.

**A newly generated Message ID** created when rebuilding a Message is not necessarily a stable business identifier. For resends, rely on the identity defined by the business contract.

### 8.2. Synchronous and Asynchronous Error Paths

With **DirectChannel**, exceptions from the outbound handler can propagate back to the producer. With **ExecutorChannel** or queue consumers, errors can occur after the producer has finished sending to the channel. Depending on configuration, Spring Integration may route an ErrorMessage to **errorChannel**, or the adapter/client may use its own error handler and callbacks.

Do not assume the default errorChannel automatically handles all errors, retries them, or saves unsent messages. Inspect the error mechanisms of the endpoint, channel type, and client in use, then explicitly design retries, dead-lettering/quarantine, or reconciliation.

## 9. Transactions and Delivery Guarantees

When integrating multiple systems, separate these concepts:

| Milestone | What Is Known | What Remains Uncertain |
| --- | --- | --- |
| Channel accepts message | Producer handed the message into the channel's delivery mechanism | Whether the external target received it |
| Client/adapter reports success | Operation reached the acknowledgment level supported and configured by the client | Whether the receiver completed business processing |
| Business acknowledgment from partner | Completed under the agreed business contract | Whether future retries are automatically safe without idempotency |

For example, the system writes an order to a database and then publishes an OrderCreated event to Kafka. If the process crashes **after writing to the database but before sending the event**, the partner never learns about the new order. If Kafka received the event before the application recorded the sent state, a rerun could send a duplicate.

**Transactional outbox** is a common pattern: business changes and an outbox record are saved in the same database transaction; a worker reads the outbox, dispatches the message to the target, and records progress. The target consumer still needs idempotency because replays can happen.

You cannot infer **end-to-end exactly-once** merely from using an outbound adapter. A single database transaction does not automatically span the file system, SFTP, HTTP, and Kafka simultaneously. Where a broker or JDBC provides its own transaction mechanism, state the guarantee scope accurately according to the supported resources.

## 10. Connection Lifecycle and Observability

Outbound adapters use resources such as HTTP clients, sockets, SFTP session factories, JMS/AMQP connection factories, Kafka producers, or JDBC connection pools. These resources require configuration for timeouts, pool sizes, authentication, connection recovery, and clean shutdown when the application stops.

A useful operational checklist:

| Dimension | What to Observe or Configure |
| --- | --- |
| Throughput | Messages requested for send, successful/failed send counts |
| Latency | Send duration, timeouts, queue wait time |
| Backlog | Queue depth, unprocessed outbox rows, producer buffer, failed messages |
| Reliability | Retry counts, duplicate sends, ambiguous states, reconciliation results |
| Connectivity | Live sessions, authentication errors, reconnects, connection pool limits |
| Tracing | Correlation ID, event ID, target system name, appropriate error codes |
| Security | Secure credential storage, no sensitive payloads in logs, path and URL validation |

If message generation rate exceeds sustained send capacity, apply load limits, bounded capacity, backoff, or durable queues. Do not increase concurrency unboundedly hoping the target will speed up.

## 11. Synthesis Scenario: Exporting Orders to File and Kafka

Suppose after recording an order, the application must export a CSV file for a partner and publish a Kafka event for analytics. One design worth considering:

~~~mermaid
flowchart LR
    A["OrderService"] --> DB[("Database")]
    DB --> OUT["Outbox: OrderExportEvent"]
    OUT --> P["Publishing worker"]
    P --> T["Normalize payload + headers"]
    T --> R{"Router"}
    R --> CF["fileExportChannel"]
    R --> CK["kafkaExportChannel"]
    CF --> AF["File outbound adapter"]
    CK --> AK["Kafka outbound adapter"]
    AF --> F["Partner directory"]
    AK --> K["Kafka topic"]
    AF -. "Status / error" .-> ST["Tracking and reconciliation"]
    AK -. "Status / error" .-> ST
~~~

The two branches have separate contracts. The file branch needs safe filenames, CSV formatting, and a publish-only-after-completion convention; the Kafka branch needs a topic, key, serializer, and producer acknowledgment. **The router does not turn two external operations into a single atomic transaction.** If one branch succeeds and the other fails, track state per target so you can resume only the missing branch instead of blindly replaying both.

Business keys such as orderId/eventId should remain stable across both targets. For partners needing business confirmation, design a separate feedback/reconciliation flow to distinguish **sent** from **processed**.

## 12. Common Design Mistakes

**Confusing an outbound adapter with a gateway.** A one-way adapter does not feed a business response back into the flow. If the next step needs a response, choose a gateway or design an asynchronous reply mechanism with a correlation ID.

**Using send success to claim the partner processed the data.** With asynchronous channels, queues, or brokers, a successful send may reflect only an intermediate milestone.

**Passing every DTO directly to every adapter.** Each target has its own formatting, serializer, and header-mapping requirements; place transformers at the proper boundary.

**Retrying infinitely on errors.** This can cause overload, duplicate writes, and mask unrecoverable data errors.

**Assuming QueueChannel is durable by default.** An in-memory queue does not preserve messages across process crashes.

**Sending files without agreeing on a completion marker.** The partner may read an incomplete file if they scan the directory too early.

**Treating multiple send targets as a single outcome.** File and Kafka can succeed or fail independently; track, recover, and reconcile each target separately.

## 13. Self-Check Questions

1. Where does an outbound channel adapter receive messages from, and where does its responsibility end?
2. Why can an outbound adapter still block a thread and throw exceptions even though it is described as **one-way**?
3. When is an outbound HTTP gateway more suitable than an outbound HTTP adapter?
4. What is the difference between an outbound adapter consuming from a DirectChannel versus a QueueChannel? When is a poller needed?
5. A Kafka producer loses connectivity after publishing a record but before receiving an acknowledgment. Why does retrying risk creating duplicates?
6. Why does FileExistsMode.FAIL in the example only prevent overwriting files and not guarantee end-to-end flow idempotency?
7. If exporting an order to both File and Kafka succeeds on only one branch, what state must be persisted for safe recovery?

## Summary

**An outbound flow** moves messages from the internal system through a MessageChannel to an **outbound channel adapter**, where payload and headers are mapped to an operation against an external system. Adapters suit one-way communication; outbound gateways serve request–reply interactions. Reliable delivery requires designing the message contract, channel dispatch behavior, acknowledgment points, retry/idempotency, transactions, and observability together. These principles apply to files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, even though each adapter has its own I/O mechanisms and lifecycle.
