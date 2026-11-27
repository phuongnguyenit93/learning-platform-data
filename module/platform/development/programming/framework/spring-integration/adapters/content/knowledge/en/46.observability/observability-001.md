# Message History Across Endpoints in Spring Integration

## 1. The Problem: Which Endpoints Has a Message Passed Through?

In Spring Integration, a processing flow typically starts from an **inbound adapter/gateway**, passes through one or more **MessageChannel**s, **filter**s, **router**s, **transformer**s, **splitter**s, **aggregator**s, **service activator**s, and ends at an **outbound adapter/gateway**. When a flow has multiple branches and asynchronous processing, the question “Where did this message go before failing?” is not easy to answer from a single stack trace line.

**Message history** is diagnostic information accumulated by Spring Integration in a **message header** to reflect the integration components a message has passed through **when history collection is enabled and headers are preserved**. It helps to:

- Distinguish which router branch a message took, which endpoints processed it, and which endpoints never saw it.
- Investigate why a filter, transformer, handler, or gateway produced an unexpected result.
- Cross-check inputs/outputs across file, SFTP, HTTP, JMS, AMQP, Kafka, and database adapters.
- Work alongside **correlation ID**, metrics, logs, and tracing to diagnose cross-channel failures.
- Build tests that verify a message's path according to the integration contract.

This lesson belongs to the **Observability** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The learning scope covers connecting external systems using inbound/outbound adapters, gateways, pollers, and MessageChannels; practicing flows across file, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and tracking **message contracts, errors, and connection lifecycles**. Therefore, the focus is not general logging, but **understanding and operating MessageHistory at each endpoint boundary**.

> **Important limitation:** Message history is diagnostic metadata within a Spring Integration processing path. It is **not automatically** a distributed trace across processes/brokers, does not record per-hop execution duration, is not guaranteed to survive serialization across external protocols, and is **not** an immutable audit log.

### Learning Outcomes

After this lesson, you can:

1. Explain the differences between **history, message ID, correlation ID, log, metric, and trace**.
2. Enable/disable and read `MessageHistory` using appropriate Spring Integration configuration.
3. Trace a message's path across endpoints, channels, routers, splitters/aggregators, pollers, and gateways.
4. Identify places where history **does not appear or gets lost** due to mapping/serialization/new message creation.
5. Write tests and dashboards to support diagnostics without exposing sensitive data or growing headers unboundedly.

## 2. Recap of the Message, Header, Channel, and Endpoint Model

A message in Spring Messaging can be understood as:

~~~text
Message<T>
├── payload: T
└── headers: MessageHeaders
    ├── id
    ├── timestamp
    ├── correlationId / sequenceNumber / sequenceSize (if present)
    ├── application headers (if present)
    └── history (when MessageHistory is enabled and propagated)
~~~

**Payload** is the business data: file content, DTO, byte[], Kafka record, command/request, or processing result. **Headers** carry metadata that supports routing and processing. **MessageChannel** is the transport path for messages; an **endpoint** connects an adapter, handler, or message source to a channel. For example:

| Component | Role | Example |
|---|---|---|
| **Inbound channel adapter** | Receives/polls data from outside, brings it as a message into the flow | File inbound, SFTP inbound, JMS listener |
| **Inbound gateway** | Receives a request and provides a reply path | HTTP inbound gateway |
| **MessageChannel** | Transports messages between endpoints | DirectChannel, QueueChannel, ExecutorChannel |
| **Filter** | Accepts or discards a message based on a condition | Reject wrong file extension, invalid message |
| **Router** | Selects a processing channel/branch | Route by order type |
| **Transformer** | Converts payload/representation | File → DTO, JSON → domain object |
| **Service activator** | Executes business processing | Persist order to database |
| **Splitter / Aggregator** | Splits one message into many / groups them back | Batch items, fan-out/fan-in |
| **Outbound adapter** | Sends externally, usually one-way | Write file/SFTP, publish to Kafka |
| **Outbound gateway** | Request/reply with an external system | HTTP call, database request/reply |
| **Poller** | Triggers a source or consumer periodically | Read directory, DB table, QueueChannel |

**Key takeaway:** history describes **the instrumented components that were actually traversed**, not a static diagram of all configured nodes. If a router chooses branch A, that message's history does not prove whether branch B was called.

## 3. What Is MessageHistory?

Spring Integration provides a **message history** mechanism and the `org.springframework.integration.history.MessageHistory` API. When enabled, component information is accumulated in the header whose name is defined by `MessageHistory.HEADER_NAME` (typically `history`).

A history entry typically contains information equivalent to:

- **`name`:** the name/ID of the recorded integration component.
- **`type`:** the type of the recorded integration component.

You can read history via `MessageHistory.read(message)` and iterate over entries in stored order. Depending on the **version, endpoint type, and configuration**, the exact list of components may vary. Therefore, verify with a test against your active Spring Integration version rather than hardcoding the history shape into business contracts.

### 3.1. Message History Is Not a Message Log

| Question | Can Message History Answer It? | Additional Tools Needed |
|---|---|---|
| Which components did the message pass through? | Yes, within the scope where history is recorded and retained | Logs to inspect execution records |
| Did a filter discard the message? | Can be inferred from path and checkpoints; does not always include reject reason | Discard counter, filter decision logs |
| How long did a handler run? | Not its core purpose | Micrometer timers, observation spans |
| Why did HTTP return 500? | Only provides context leading up to the endpoint | HTTP logs, exception, trace |
| Was a Kafka record redelivered? | Not enough; each processing attempt may carry different history | Offset/partition, consumer logs, delivery metrics |
| Which services did the message visit? | Not guaranteed across processes | Distributed tracing, intentional propagation |
| Is it permanent audit evidence? | No | Securely stored audit events, retention |
| Which endpoint is bottlenecked? | Lacks throughput or queue depth data | Channel/handler metrics, queue depth, tracing |

### 3.2. Diagram of a Flow with History

~~~mermaid
flowchart LR
    EXT[File / SFTP / Broker] --> IN[Inbound Adapter]
    IN --> C1[rawChannel]
    C1 --> F[Validate Filter]
    F --> C2[validChannel]
    C2 --> T[Normalize Transformer]
    T --> R[Type Router]
    R -->|A| H1[Handler A]
    R -->|B| H2[Handler B]
    H1 --> OUT[Outbound Adapter]
    H2 --> OUT
    IN -. history .-> MH[History Header]
    F -. history .-> MH
    T -. history .-> MH
    R -. history .-> MH
    H1 -. history .-> MH
    H2 -. history .-> MH
~~~

Dotted lines only mean **metadata may be recorded as the message passes through**. They do not mean a header is sent to a centralized node named “History Header”, nor do they guarantee every node in the diagram always appears in the list.

## 4. Enabling Message History with Java Configuration

In Spring Integration versions that support annotations, history collection can be enabled using `@EnableMessageHistory` on an application configuration class.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;

@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationHistoryConfiguration {
    // Additional configuration beans if needed by the application.
}
~~~

When integrating with Spring Boot, basic enablement may already be auto-configured by Boot; enabling `@EnableMessageHistory` should not be confused with enabling all metrics/tracing. Check your actual dependencies, version, and application configuration.

### 4.1. Enabling via XML in Legacy Systems

With the Spring Integration XML namespace, the equivalent configuration can use:

~~~xml
<int:message-history/>
~~~

Here the `int` prefix is the Spring Integration namespace declared in the XML file. This example illustrates the **enablement element**, not a complete XML configuration file. Do not use both approaches arbitrarily if the application has overlapping configuration contexts.

### 4.2. Which Environments Should Enable It?

- **Local/test:** useful when studying a flow, comparing filter/router paths, and testing branches.
- **Staging:** convenient for verifying behavior after changing topology, adapters, and channels.
- **Production:** evaluate message rate, header size, cross-service traffic, PII, and overhead before enabling broadly.

Message history typically grows metadata with the number of traversed components. For long flows, large splitter fan-outs, or repeated retries, headers can become significantly large. It should not become an “always on for every message” option without measuring overhead.

## 5. Reading MessageHistory Safely

To inspect at a point in the flow, use the read API instead of accessing the header name string directly.

~~~java
import java.util.Properties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

public final class HistoryInspector {
    private static final Logger log =
            LoggerFactory.getLogger(HistoryInspector.class);

    private HistoryInspector() {}

    public static void inspect(Message<?> message) {
        MessageHistory history = MessageHistory.read(message);
        if (history == null || history.isEmpty()) {
            log.debug("No Spring Integration message history available");
            return;
        }

        for (Properties component : history) {
            String name = component.getProperty("name", "unknown");
            String type = component.getProperty("type", "unknown");
            log.debug("SI history component: name={}, type={}", name, type);
        }
    }
}
~~~

**Compatibility note:** The API and record shape may change across library generations; when upgrading versions, check the `MessageHistory.read(...)` signature and entry contents in the version in use. The example reads only component metadata and **does not print the payload** or headers containing credentials.

### 5.1. Why Check for Null/Empty?

Common cases include:

1. History is not enabled in the corresponding context.
2. The message is read before passing through any tracked endpoint.
3. A new message was created manually without preserving headers.
4. The header was stripped by a filter/header mapper at a protocol boundary.
5. The message arrived from a broker or another service where history was not propagated.
6. The adapter/endpoint or framework version does not contribute a history entry as the developer expected.

Therefore, business logic **should not require history to exist** in order to approve a payment, delete data, or grant permissions. It is observational data, not a trusted domain input.

## 6. Demo: A Flow with a Transformer and a History Inspection Point

Minimal Java DSL example: accept a filename, normalize it, and route it to an observation channel. Use `@EnableMessageHistory` as shown in section 4.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class SimpleHistoryFlow {
    @Bean
    IntegrationFlow filenameFlow() {
        return IntegrationFlow.from("incomingFilename")
                .transform(String.class, String::trim,
                        endpoint -> endpoint.id("normalizeFilename"))
                .channel("historySink")
                .get();
    }

    @Bean
    @ServiceActivator(inputChannel = "historySink")
    MessageHandler historyConsumer() {
        return HistoryInspector::inspect;
    }
}
~~~

**Demonstrated behavior:** a message enters `incomingFilename`, is processed by the `normalizeFilename` transformer, and arrives at the consumer on `historySink`. The history read at the consumer indicates the framework components recorded for that message. **Do not rely on the exact entry count or detailed ordering** of a code snippet without running it on your active library version.

### 6.1. Assign Purposeful Endpoint IDs

Giving endpoints clear, stable names such as `normalizeFilename`, `validateOrder`, `routeBySource`, or `sendToBilling` makes history analysis much easier than auto-generated IDs. Name them by **logical role** rather than hostnames, passwords, usernames, or continuously changing runtime values.

### 6.2. History Emerges Within the Flow

A message constructed outside Spring Integration and sent into a channel may initially have no history. After passing through recorded integration components, new entries are appended. Reading a message **before** or **after** an endpoint can yield different results; choose fixed checkpoints for comparison.

## 7. Tracking Filters, Routers, and Transformers

### 7.1. Filter: When a Message Is Discarded

Suppose we have a file flow:

~~~text
fileInbound -> validateFormat -> normalize -> outboundKafka
                     |
                     +-- discardChannel -> rejectAudit
~~~

If a file is invalid and discarded by the filter, the message **never reaches the transformer or outbound Kafka**. History only reflects the branch actually traversed and still readable. To know **why it was rejected**, have a discard channel/counter/controlled log with a business error code:

~~~text
event = FILE_REJECTED
reason_code = UNSUPPORTED_EXTENSION
source_adapter = fileInbound
endpoint = validateFormat
message_ref = order-batch-2026-11
~~~

Do not expect `history` itself to contain predicate results, rejected payloads, exceptions, or processing timestamps.

### 7.2. Router: One Message Chooses One or Multiple Branches

A router can direct messages to `priorityChannel` or `standardChannel`; some router types can be configured to send to multiple destinations. The history of **each message on each branch** reflects that branch's path only when headers are preserved.

**Common mistake:** seeing the router name in history and concluding “all branches processed it.” To know which branch was chosen, emit a routing decision event/tag with branch count and outcome code; avoid creating tags with unbounded cardinality.

### 7.3. Transformer: When the Payload Changes Shape

A transformer may return a new payload or build a new `Message<?>`. The framework normally handles/propagates appropriate headers depending on transformer type; however, **custom code that builds a message manually** can accidentally drop history, correlation, or reply channel headers.

~~~java
// When explicitly creating a new Message and wanting to preserve appropriate headers
Message<String> normalized =
        MessageBuilder.withPayload(normalizedText)
                .copyHeaders(incomingMessage.getHeaders())
                .build();
~~~

The snippet above requires importing `org.springframework.integration.support.MessageBuilder` or a builder appropriate for your version. This is an example **within the same application**. When crossing HTTP/JMS/AMQP/Kafka, do not blindly copy all headers, because some headers are runtime objects, contain internal information, or cannot be serialized.

## 8. MessageChannel: Direct, Queue, Executor, and Publish-Subscribe

### 8.1. DirectChannel

With `DirectChannel`, downstream handlers typically run synchronously on the calling thread, following the channel's dispatch model. The history header can continue through the flow if not replaced. Do not infer **per-endpoint duration** just because the history list is ordered.

### 8.2. QueueChannel

`QueueChannel` holds messages for a consumer/poller to retrieve later. Wait time in the queue must be measured using queue depth, enqueue/dequeue timestamps, or corresponding metrics; **history does not record wait duration by default**. If a message is reconstructed before being placed into the queue, headers can be lost.

### 8.3. ExecutorChannel

`ExecutorChannel` dispatches through an executor, creating a thread boundary. Message headers may remain on the message, but **MDC and tracing context are thread-local or context-specific**, so they are not automatically guaranteed to transfer to the new thread. Appropriate instrumentation/context propagation is required for your version, Spring Boot/Micrometer, and executor.

### 8.4. PublishSubscribeChannel

A message broadcast to multiple subscribers creates distinct processing paths. When multiple subscribers handle it concurrently, pay attention to **ordering, async dispatch, and message/header immutability**, and do not assume a single history list fully represents all branches in a global order.

| Channel | Key Diagnostic Question | Data Beyond History |
|---|---|---|
| DirectChannel | Which handler receives the message immediately on the call path? | Exception, handler timer |
| QueueChannel | Is the message waiting or is the consumer not polling? | Queue depth, poll count, oldest age |
| ExecutorChannel | Are tasks being scheduled/executed? | Executor queue, active threads, trace propagation |
| PublishSubscribeChannel | Which subscriber succeeded/failed? | Subscriber counters, per-branch logs, error policy |

## 9. Splitter, Aggregator, and Resequencer

This endpoint group often causes learners to draw wrong conclusions about history because **one message can become many messages**, or many messages are grouped into one.

### 9.1. Splitter

Suppose a payload is a list of 100 records. The splitter creates child messages, typically attaching correlation/sequence metadata as configured. Each child message can carry appropriate headers from the parent message and continue accumulating history along its own processing path.

~~~mermaid
flowchart TD
    B[Batch Message] --> S[Splitter]
    S --> M1[Item 1 - separate headers]
    S --> M2[Item 2 - separate headers]
    S --> MN[Item N - separate headers]
    M1 --> V[Validate]
    M2 --> V
    MN --> V
    V --> AGG[Aggregator]
    AGG --> RES[Grouped Result]
~~~

Do not interpret the history of item 7 as proof that the remaining 99 items ran. Summarizing outcomes requires **correlation ID, sequence/aggregation metadata, item status, and metrics**.

### 9.2. Aggregator

An aggregator can produce a result message from a group of input messages. The final history depends on how the framework/policy selects the base message, merges headers, and creates output. **Do not assume the aggregator merges the full history of every input**.

If you need to audit “which endpoints each item passed through,” store **a separate event per item**, or an item result table with correlation ID, rather than expecting the result header to hold every journey.

### 9.3. Resequencer and Retry

Reordering or reprocessing messages causes the **business event order** to differ from execution/arrival order. History is a trace of the local path, not proof of exactly-once processing, broker FIFO, or causality across all threads.

## 10. Pollers and Inbound Adapters: Where Does History Start?

With a **polling inbound adapter**, the poller triggers source reads on a schedule (file directory, remote SFTP, database, or other source), and the adapter creates a message if data exists.

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant SRC as File / SFTP / DB
    participant A as Inbound Adapter
    participant C as MessageChannel
    participant H as Handler
    P->>A: Trigger poll
    A->>SRC: Read/scan source
    alt Data available
        SRC-->>A: File / record
        A->>C: Message with payload + headers
        C->>H: Dispatch
        H->>H: Read MessageHistory
    else No data
        SRC-->>A: Empty
        Note over A,H: No Message to inspect history
    end
~~~

### 10.1. “No Messages” Does Not Mean the Poller Is Not Running

If there are no source records, the poller may run properly while **emitting zero messages**; naturally, there is no history to read. Conversely, a poller may have stopped due to scheduler/executor errors, also leaving no history. Distinguish the two situations using:

- Poll tick count and last poll timestamp.
- Empty/non-empty poll counts, number of emitted records.
- Connection, authentication, timeout, and remote listing/read errors.
- Scheduler state, executor saturation, and locks.
- Age of the oldest unprocessed record/file.

### 10.2. Resource/Connection Lifecycle

File and SFTP have different failure modes: file not found, partially written file, permission denied, remote session timeout, filename collisions, or connection locks. History is only meaningful for messages that actually enter the flow; to understand **why an inbound adapter has not created a message**, monitor the source lifecycle, session factory, poller, remote directory, and filters.

## 11. Comparison Table by Adapter/Gateway Type

| Adapter/Gateway | Where History Helps | What It Does Not Prove by Itself | Additional Data Needed |
|---|---|---|---|
| **File inbound/outbound** | Path from polled file to transformer and output handler | Whether the file was completely/durably written | Redacted file path, size, checksum, write result |
| **SFTP inbound/outbound** | Journey after the remote file becomes a message | Whether the SFTP connection stayed up or upload committed | Remote session, transfer status, retry, remote file identity |
| **HTTP inbound gateway** | Endpoints handling the request inside Spring Integration | Whether the client received the response or network stayed intact | HTTP status, request ID, server/client logs |
| **HTTP outbound gateway** | Path to the HTTP-calling handler and in-app response processing | Whether the remote service committed the transaction on timeout | HTTP status/latency, idempotency key, trace/span |
| **JMS inbound/outbound** | Flow inside each app consuming/producing JMS messages | Broker ack, transaction commit, redelivery count | Message ID, correlation, consumer stats, DLQ |
| **AMQP/RabbitMQ** | Flow around the adapter's producer/consumer | Publish confirm, consumer ack, retry or DLQ outcome | Broker delivery tag, routing key, confirm/ack metrics |
| **Kafka inbound/outbound** | Internal handlers processing records to/from Kafka | Offset commit, transactional boundary, or exactly-once | Topic/partition/offset, consumer group, lag, producer outcome |
| **JDBC/DB adapters** | Processing path of polled or queried records/events | Whether the DB transaction committed without a transaction trace | Query/update result, transaction, lock, poll watermark |

### 11.1. End of Internal History

When an **outbound adapter** sends a message to Kafka/JMS/AMQP/HTTP, history lives inside the internal message. The consuming service may construct a **new message** from the payload and mapped/serialized protocol headers. Therefore, **never assume** process A's history header will automatically become valid history in process B.

### 11.2. Start of Consumer-Side History

An inbound adapter in process B can create a new Spring Message and begin accumulating history **locally in B**. To link A and B, propagate **correlation/trace context** according to an approved integration contract, rather than forwarding all internal headers verbatim.

## 12. Header Propagation and the Risk of Losing History

### 12.1. Boundaries to Watch

1. **Transformer/custom handler** creates a new `Message<?>`.
2. **HeaderFilter** removes or renames headers.
3. **Gateway** turns payload/headers into request parameters and then builds a reply message.
4. **Protocol adapter** maps only a supported subset of headers or selects via a header mapper.
5. **Serializer/converter** converts the message to JSON, Avro, byte[], or a native broker record.
6. **Aggregator/splitter** creates child/result messages with custom header policies.
7. **Error flow** emits an `ErrorMessage` and may include the original message for investigation.
8. **Process boundary** when another service receives the message and creates a new Spring Message.

### 12.2. When Creating a New Message

~~~java
// Easy to lose correlation/history when creating a message from payload:
Message<String> withoutOriginalHeaders =
        MessageBuilder.withPayload(normalized).build();

// Preserve internal headers when explicitly creating a new message in the same flow:
Message<String> withOriginalHeaders =
        MessageBuilder.withPayload(normalized)
                .copyHeaders(source.getHeaders())
                .build();
~~~

This example highlights **the difference in header handling**. Do not blindly copy all headers to external systems. `replyChannel`, `errorChannel`, or headers holding Java objects may not be serializable, and `history` can expose internal topology. When crossing an external adapter, use a **well-defined allowlist and mapping**.

### 12.3. History Headers Can Grow Large

If retries or routing loops append to history, large headers can:

- Increase byte usage in heap, queues, or payload mappings.
- Exceed HTTP/broker header limits or be rejected by converters.
- Inflate log volume and telemetry costs if printed in full.
- Leak endpoint names, system names, and topology details to partners.

Keep history only within the diagnostic scope needed; at network boundaries, usually propagate **correlation IDs and trace context**, not the entire internal history.

## 13. Message ID, Correlation ID, and Business ID

Different IDs solve different problems:

| ID | Meaning | Can It Link the Entire Flow? |
|---|---|---|
| **MessageHeaders.ID** | Identifier of a single Spring Message instance | Unlikely; creating a new message can produce a new ID |
| **Business ID** | Domain order, contract, or batch identifier | Meaningful across systems if designed stably; does not replace idempotency |
| **Correlation ID** | Groups request/reply, splitter/aggregator, or logical transaction | Yes, when consistently propagated per contract |
| **Trace ID / Span ID** | Execution relationship across instrumented operations | Yes, if tracing context is propagated properly |
| **Broker message/record identity** | JMSMessageID, Kafka topic-partition-offset… | Tied to transport and delivery, not business identity |
| **Message history** | Component path list within Spring Integration | Not an ID and insufficient as a correlation key |

### 13.1. Designing IDs Across Adapters

Suppose an order flows from HTTP → Spring Integration → Kafka → service B → JDBC:

~~~text
businessOrderId = ORD-1042
correlationId   = integration-request-79
traceId         = tracing-context-id
messageId(A)    = Local Spring Message UUID in A
kafkaIdentity   = topic / partition / offset
messageId(B)    = Local Spring Message UUID in B
history(A)      = Components traversed in A
history(B)      = Components traversed in B
~~~

When debugging, use the appropriate correlation/trace/business ID to find **the two separate history segments**. Do not treat a Message ID from A as the sole key for messages B, C, and D without an explicit contract.

### 13.2. Redelivery and Idempotency

A Kafka/JMS/AMQP message can be redelivered. Multiple processing attempts may share the **same business ID** while having different traces/spans/Message instances. History does not tell you whether a record was committed to the database; adapter design requires an **idempotent receiver, proper transaction/ack handling, deduplication key, and retry policy**.

## 14. Request/Reply via Gateways and Two-Way History

### 14.1. Inbound Gateway

An HTTP inbound gateway typically creates a request message, passes it through a business flow, and returns a reply to the HTTP caller. The history of the **request** does not automatically show whether the caller received the reply; response status/latency and network telemetry are also needed.

### 14.2. Outbound Gateway

An outbound gateway sends a request to an external system and may receive a reply or exception. On timeout, history reaching the gateway only proves the flow reached the call site, **not that the remote system failed to process it**. Retries can create duplicate transactions without an idempotency key.

### 14.3. Header Differences Between Request and Reply

The reply message may be newly created by the framework, with headers copied/mapped by contract or certain fields dropped. Therefore, inspect **both the message before the gateway and the reply after the gateway** rather than expecting a single history to capture all external activity.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant G as Inbound Gateway A
    participant Flow as Flow A
    participant B as Service B
    Client->>G: Request + correlation
    G->>Flow: Spring Message request
    Flow->>B: Outbound HTTP request
    Note over G,Flow: History A accumulates at internal endpoints
    B-->>Flow: HTTP response
    Flow-->>G: Reply Message
    G-->>Client: HTTP response
    Note over Flow,B: HTTP logs / trace needed to see the call and processing in B
~~~

## 15. Investigating Failures with ErrorMessage and Original Message

An endpoint may throw an exception; depending on dispatch configuration, gateway, error channel, error handling, and transactions, the failure may be wrapped into an `ErrorMessage`. When the original message is present, its history can reveal the path **before the error**.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.integration.history.MessageHistory;

public void inspectError(Message<?> inbound) {
    if (inbound instanceof ErrorMessage error) {
        Message<?> original = error.getOriginalMessage();
        if (original != null) {
            MessageHistory history = MessageHistory.read(original);
            // Log component IDs safely without dumping the entire payload/headers.
        }
        Throwable failure = error.getPayload();
        // Log exception type, error code, and correlation ID according to policy.
    }
}
~~~

**Note:** not every failure produces an ErrorMessage, and `originalMessage` may be absent. An error occurring before a Spring Message exists (e.g., failing to open an SFTP connection, or an HTTP request blocked before the gateway) will have no history for a message that was never created.

### 15.1. Failure Triage Checklist

1. Identify the **exception location**: poller/source, adapter, channel dispatch, transformer, handler, outbound request, broker acknowledgment.
2. Capture exception type, error code, and correlation ID; avoid printing credentials in exception messages.
3. Read the history of the **original message when available**; compare the last endpoint with the flow configuration.
4. Check the error flow's action: discard, retry, dead-letter, rollback, or error reply.
5. Verify **whether side effects already occurred** (file move, HTTP call, DB update, Kafka publish).
6. If retrying, check idempotency key, version, transaction, ack, and backoff configuration.
7. Record status **UNKNOWN/RETRYABLE/FAILED/VERIFIED** per policy; never mark as “not processed” solely because of a timeout.

### 15.2. History Does Not Replace the Exception Stack

History tells you the **path**, whereas stack traces and error classification explain **what failed**. Both must be combined, because the last endpoint in history is not necessarily where the code threw the exception; it could be a downstream call or an asynchronous failure.

## 16. Message History vs. Micrometer Metrics and Tracing

These are three **complementary** layers of observability, not replacements for one another.

| Signal | Represents | Used For |
|---|---|---|
| **Message history** | Component metadata inside a Spring Message | Debugging local path through endpoints |
| **Structured logs** | Events with timestamp, severity, code, correlation | Finding specific actions, analyzing errors |
| **Metrics** | Aggregated counters/timers/gauges | Error rate, throughput, queue depth, latency/SLO |
| **Distributed tracing** | Spans and trace context of operations | Analyzing call paths, cross-service latency |
| **Audit events** | Changes/accesses recorded with retention rules | Accountability, business reconciliation, and compliance |

### 16.1. Spring Integration Management and Micrometer

Spring Integration can instrument integration components; depending on version and configuration, **Micrometer metrics/Observations** can capture channel/handler activity and export it to observability backends such as Prometheus or a tracing backend. **Do not assume that merely adding the message history annotation automatically exports full metrics/traces**.

When deploying, verify:

- Dependencies/instrumentation supported by your current Spring Boot/Spring Integration version.
- Proper configuration of registries/observations and exporters.
- Which channels/handlers/adapters actually emit metrics; do not assume every adapter emits an equivalent counter by default.
- Sampling and tracing propagation across HTTP/brokers/executors.
- Tag cardinality and access controls on telemetry data.

### 16.2. Useful Metrics Along the Path

| Issue | Signals to Monitor |
|---|---|
| Poller runs but receives no files | Poll success/empty/error, file age, remote listing count |
| Filter discards many messages | Accepted/rejected counts by bounded type/source |
| QueueChannel backed up | Queue depth, oldest message age, consumer throughput |
| ExecutorChannel overloaded | Executor active threads, queue size, rejections |
| Outbound HTTP timeouts | Request count, latency distribution, status/error rate |
| Kafka consumer falling behind | Consumer lag, offset processing, rebalance, DLQ count |
| JMS/AMQP redeliveries | Redelivery count, ack/nack/requeue, and DLQ metrics |
| SFTP frequent disconnects | Session open failures, transfer retries, remote latency |
| Duplicate JDBC polls | Poll watermark, rows selected/processed, transaction failures |

History only helps ask “which handler did it reach?”; metrics/tracing help answer “how long did it take?” and “at what rate is it failing?”.

## 17. Designing Safe Logging with History

### 17.1. Structured Logging Instead of Printing the Entire Message

An easy-to-analyze log should look like:

~~~json
{
  "event": "INTEGRATION_MESSAGE_CHECKPOINT",
  "flow": "sftp-orders-to-kafka",
  "endpoint": "normalizeOrder",
  "correlation_ref": "corr-2048",
  "business_ref": "order-batch-71",
  "message_ref": "local-message-id",
  "history_component_count": 4,
  "history_last_component": "normalizeOrder",
  "outcome": "PROCESSED"
}
~~~

This is an **illustrative application-generated log structure**, not automatic output or default Spring Integration field names. Prefer **non-sensitive reference IDs** and only necessary fields; do not log order payloads, URLs containing tokens, or all MessageHeaders.

### 17.2. Data That Should Never Appear in Logs/Exported History

- Passwords, API keys, OAuth tokens, private keys, Authorization headers, cookies.
- PII in payloads, HTTP bodies, or sensitive filenames.
- Full remote paths containing secret usernames/tenants or network topology.
- Raw SAML assertion/JWT contents, sensitive secret manager paths.
- Database queries containing personal data, customer data, or payment information.

### 17.3. Correlation in Logs and MDC

MDC can attach `correlationId`/`traceId` to logs on a single thread, but across `ExecutorChannel`, reactive bridges, or polling tasks, MDC is **not automatically synchronized across all threads**. Use supported and tested context propagation. Message headers are metadata inside the message; MDC is thread/logging context: they are two distinct mechanisms.

## 18. Purposeful Testing of MessageHistory

### 18.1. Test Objectives

A good test should verify:

1. When a message traverses the flow successfully, history is readable at the designated checkpoint.
2. Explicitly assigned endpoint names can be found when that endpoint supports history recording in the tested version.
3. A branch rejected by a filter **does not reach** unintended outbound handlers.
4. A router selects the right destination; do not infer all branches executed.
5. When a custom transformer creates a new message, headers are intentionally preserved or stripped.
6. Across asynchronous boundaries, correlation headers remain accurate and log context propagates if designed to do so.
7. On failure, the original message or pre-failure checkpoint retains enough metadata for investigation.
8. Across brokers/HTTP, only **allowlisted** headers and trace context are sent per contract.

### 18.2. Testing Approach in a Small Environment

~~~text
Given: @EnableMessageHistory and a flow with endpoint id "normalizeFilename"
When : Send message "  invoice.csv  " to the input channel
Then : Consumer receives payload "invoice.csv"
And  : MessageHistory.read(message) is present at the final checkpoint
And  : Evidence of traversing normalizeFilename matches the active version
And  : No credentials or sensitive payloads are logged
~~~

This is a **test specification**, not executed JUnit code. To avoid brittle assertions, focus on explicitly named endpoints and business behavior rather than hardcoding every framework-generated history entry.

### 18.3. Matrix of Branches to Verify

| Case | Input | Expected Outcome | Observation |
|---|---|---|---|
| Happy path | Valid payload | Reaches outbound adapter | History checkpoint and success metric |
| Filter reject | Invalid schema/format | Not sent downstream | Discard counter + reason |
| Router branch A | Type A | Handler A only | Path/branch log |
| Router branch B | Type B | Handler B only | Path/branch log |
| Handler throws | Processing error | Error flow per config | ErrorMessage/original + exception |
| Gateway timeout | Remote does not reply | Timeout/retry per policy | History up to gateway + outbound latency |
| Async | Concurrent messages | No correlation mixing | Trace/MDC propagation + per-message history |
| Split/aggregate | Multi-item batch | Correct grouping | Per-item correlation, do not infer from result history |
| Broker redelivery | Same record redelivered | Proper idempotency | Offset/delivery attempts and audit |

## 19. Diagnostic Procedure When History Is Empty or Missing Endpoints

### SOP-HIST-01

**Symptom:** a message reaches a service activator without `history`, with a truncated list, or without an expected endpoint.

1. **Verify configuration:** was the message history annotation or XML actually loaded in the right ApplicationContext?
2. **Identify the checkpoint:** is the message read before or after the endpoint, and has any handler actually received the message?
3. **Check the flow path:** did the filter/router actually choose the branch being observed?
4. **Audit custom Message creation:** was `MessageBuilder.withPayload(...)` used without copying headers?
5. **Audit header mappers/filters:** did an HTTP/JMS/AMQP/Kafka adapter or converter strip the header?
6. **Check process boundaries:** messages arriving from a broker are newly constructed; was the producer's local history forwarded or intentionally stripped?
7. **Check endpoint IDs:** did auto-generated names differ from expectations after build/refactor?
8. **Check async/races:** were worker logs mismatched by correlation, or are you inspecting a different message?
9. **Verify version/capability:** does the endpoint/adapter actually add history in that version?
10. **Retry on a minimal flow** with history enabled, explicit endpoint IDs, and a consumer calling `MessageHistory.read`.

**Do not apply a quick fix by manually stuffing a `history` header with arbitrary strings**, as that can break framework formatting and create uncontrolled business dependencies.

### 19.1. When History Is Long but the Failure Is Unclear

History does not contain the root-cause exception. Turn to error flows, stack traces, business error codes, broker offsets, HTTP status/latency, or database transaction logs. Do not read a long path and blame the “last endpoint” without verification.

## 20. Performance, Header Size, and Availability

### 20.1. Potential Operational Costs

- **CPU/GC:** adding metadata on every hop in high-throughput flows.
- **Memory:** history grows longer as a message visits more endpoints; fan-out creates multiple message copies with headers.
- **Serialization:** large headers and Java-specific types are unsuitable for network transport.
- **Logging:** printing full history on every message produces huge log volume and high storage costs.
- **Policy risk:** topology and internal identifiers can leak externally through uncontrolled mapping.

There is no single fixed overhead figure; measure it in real workloads or representative load tests.

### 20.2. Keeping Costs Under Control

1. Enable history purposefully for environments/traffic needing investigation; evaluate before broad production rollout.
2. Use short, stable endpoint IDs; never embed payloads or personal identifiers in component names.
3. Avoid dumping full `Message<?>` or complete history on hot paths.
4. At outbound gateways/adapters, propagate only allowlisted headers.
5. Store sampled metrics/traces and business audits in dedicated systems rather than replacing them with ever-growing history headers.
6. Monitor memory, queue depth, broker header limits, latency, and error rates before/after enabling.
7. For retries/DLQs, enforce policies on retention, max attempts, and correlation without keeping unnecessary data forever.
8. When history is disabled in production, maintain alternative diagnostics via correlation ID + structured logs + metrics/tracing.

## 21. Security and Trustworthiness of History

### 21.1. History Headers Are Diagnostic Data, Not Authority

Never use endpoint names in history to **authenticate users, accept messages, approve payments, or grant access**. A message arriving from another system may carry headers controlled by the sender; if you trust that header as audit proof, an external partner or actor could spoof “already passed validatePayment.”

**Business decisions must rely on verified data, policies, authz, and persisted state**, not unauthenticated path headers.

### 21.2. Do Not Expose Full Internal Topology

History can reveal handler names, environments, systems, processing branches, or libraries. Before sending HTTP responses/broker records or logging to external systems, explicitly define which headers may be exported. Do not copy `history` merely for “easier debugging” without contractual requirements and proper safeguards.

### 21.3. Privacy by Design

- Set retention policies for logs/traces.
- Restrict access to telemetry and evidence.
- Hash or use opaque references for sensitive business IDs when needed.
- Never store raw tokens/credentials; check whether exception serializers accidentally log bodies/payloads.
- Distinguish support logs from audit evidence that must be stored and protected independently.

## 22. Comprehensive Practice Scenarios

### Scenario A — File Inbound Succeeds but Kafka Has Not Received the Record

Flow `fileInbound → validate → transform → kafkaOutbound`. The message reaches transform, yet the downstream consumer has not seen the event.

**Investigation:** read history at a checkpoint after transform to verify whether it reached the outbound handler. Check Kafka producer callbacks, broker ack, partition/topic, serialization, retries, and DLQ. History reaching `kafkaOutbound` **does not prove the broker received and committed it**. Use producer metrics/logs with correlation and business IDs.

### Scenario B — SFTP Poller Is Silent

The dashboard shows no message history for 20 minutes while the remote directory has new files.

**Investigation:** do not conclude history is broken. Check poller schedule, session factory, remote listing, authentication, file filters, read permissions, and message-creation errors. If the adapter has not emitted a message, there is no history. Monitor poll success/error counts and file age.

### Scenario C — Router Sends Data to the Wrong Branch

A priority order goes to `normalHandler` instead of `priorityHandler`. History shows the router and normal handler.

**Investigation:** history helps confirm the **actual path**. Inspect routing keys/headers and mapping rules using safe logs, and check whether a transformer modified the attribute; do not fix handler B if the root cause is the router expression.

### Scenario D — HTTP Outbound Times Out and Causes Duplicate Transactions

An outbound gateway calls a payment service; the request times out. A retry produces two transactions.

**Investigation:** history only shows the flow reached the gateway, not whether the remote side committed. Cross-check traceId, idempotency key, remote audit, response/timeout, and DB transactions. Design idempotent retries and reconciliation by business ID.

### Scenario E — JMS Redelivery Cannot Be Linked Across Attempts via History

A JMS consumer processes a message, rolls back, and the broker redelivers. History on the second attempt differs from the first.

**Investigation:** this may be a new Java message produced from the same broker delivery logic. Use JMS headers, correlation, redelivery count, transactions, and DLQ; do not rely on history lists to infer exactly-once delivery.

### Scenario F — Splitter Processes 100 Items, Aggregator Misses One

Result history at the aggregator does not show which item failed.

**Investigation:** track correlation/sequence item IDs, per-item success/failure, completion strategy, timeouts, and discard/error channels. Do not expect a single final history to contain all 100 item paths.

### Scenario G — ExecutorChannel Loses MDC While History Remains

Downstream logs lose the correlation ID, while `MessageHistory.read` still reads the component path.

**Investigation:** headers inside the message are transferred, whereas MDC is thread-local. Check executor context propagation and logging instrumentation; do not build a history-reading workaround as a replacement for tracing.

### Scenario H — Creating a New Message Drops History

A custom transformer builds `MessageBuilder.withPayload(newPayload).build()`; the service activator sees no history even though upstream enabled it.

**Investigation:** fix the header propagation policy within the same-process flow using appropriate header copying and add tests. Across network boundaries, do not copy all headers—select approved public/correlation headers only.

### Scenario I — Kafka Consumer Lacks Upstream Service Trace

Service A publishes to Kafka, service B processes it. B's history starts at B's inbound adapter and does not include A's transformer.

**Investigation:** this is not necessarily a bug. Propagate trace context/opaque correlation IDs via a header mapper, and open traces/logs from both services to link the path. History A and history B are **two local segments**; do not demand copying raw `history` across the broker.

### Scenario J — History Header Leaks in an HTTP Response

A gateway configured to copy all headers causes external clients to receive internal endpoint name strings.

**Resolution:** tighten allowlist/response header mapping so internal topology or runtime headers are never exported externally; audit logs/docs containing leaked info, and add contract and security tests.

## 23. Implementation and Operations Checklist

| Phase | Acceptance Question |
|---|---|
| **Enablement** | Is `@EnableMessageHistory` or XML loaded in the right context? |
| **Endpoint naming** | Do critical endpoints have stable, understandable IDs? |
| **Checkpoint** | Are `MessageHistory.read` checkpoints placed appropriately before/after endpoints? |
| **Flow coverage** | Are happy path, filter reject, router branches, and error flows tested? |
| **Async** | Do queue/executor/pub-sub channels have proper correlation, metrics, and trace propagation? |
| **Poller** | Can empty polls, poll failures, and message processing failures be distinguished? |
| **Gateway** | Are request/reply and remote outcomes verified separately from history? |
| **Broker** | Are offset/ack/redelivery/DLQ/idempotency in place without relying on history to confirm commit? |
| **Header mapping** | Is there an allowlist when sending over HTTP/JMS/AMQP/Kafka to prevent leaking internal history? |
| **Exception** | Are error logs and original messages captured when provided by the framework? |
| **Performance** | Have header size, heap/GC, latency, and log volume been evaluated? |
| **Security** | Are sensitive tokens/payloads excluded from logs, and is history never used as authorization/audit proof? |
| **Operations** | Are correlation IDs, metrics, tracing, and runbooks ready when history is turned off? |

## 24. Conclusion

**Message history across endpoints** is a useful diagnostic tool in Spring Integration: when enabled, accumulated metadata helps operators see which recorded components a message passed through, especially in flows with filters, routers, transformers, splitters/aggregators, and various adapter types. Stable endpoint names, well-placed checkpoints, and testing real branches are key to making history valuable.

However, history **does not replace** metrics for throughput/latency, distributed tracing across services, error logs, broker idempotency/transaction mechanisms, or business audits. Boundaries involving new message creation, gateways, serialization, and asynchronous processing can alter or drop headers. In the **Spring Integration Adapters** module, a sustainable approach combines **local MessageHistory + cross-system correlation/trace context + logs/metrics/destination outcome verification**, while protecting data, bounding headers, and explicitly handling each adapter's connection lifecycle, retries, and errors.
