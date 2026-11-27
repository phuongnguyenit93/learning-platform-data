# Criteria for Choosing an Adapter for an Integration Flow

## Learning Objectives

After this lesson, you will be able to:

- Formulate input/output requirements to choose an **inbound adapter**, **outbound adapter**, **gateway**, or other endpoint in Spring Integration.
- Evaluate **polling** versus **message-driven** mechanisms, data cadence, latency, load capacity, and connected-system constraints.
- Compare common choices for **files, SFTP, HTTP, JMS, AMQP, Kafka, and databases**.
- Define **payload/header** contracts, acknowledgment behavior, retries, idempotency, transactions, security, and operability before writing code.
- Analyze real-world integration scenarios, pick appropriate MessageChannels, and sketch Java DSL flows.
- Avoid decisions made solely by technology name while overlooking delivery semantics and connection lifecycles.

## 1. Choosing an Adapter Means Choosing a Communication Contract

In Spring Integration, a **channel adapter** connects an external system to the internal message flow. An **inbound channel adapter** brings data from an external source into a MessageChannel; an **outbound channel adapter** consumes messages from a channel and sends or writes data externally. A **gateway** fits when you must exchange **request–reply** messages so the caller receives a business result.

Never start design by asking "Should we use Kafka or JMS?" before knowing which direction data flows, who initiates the interaction, when replies are needed, and whether duplicate or lost messages are tolerable. A sound integration flow diagram must depict both the **data path** and the **completion contract** of every step.

For example, an order management system has three requirements:

1. A partner drops CSV files onto SFTP every hour; the application checks and pulls them. This is a **polling inbound** flow.
2. After saving an order, the application emits an OrderCreated event to Kafka. This is a **one-way outbound** flow.
3. During online checkout, the application calls a shipping-fee API and must receive the fee amount before confirming. This is an **outbound request–reply** flow, typically using a gateway.

The same service can use all three endpoint types. They fulfill **different contracts**, not three equivalent ways of writing the same communication.

~~~mermaid
flowchart TD
    R["Integration requirement"] --> D{"Which direction does data flow?"}
    D -->|"External → application"| IN{"External caller needs business reply?"}
    D -->|"Application → external"| OUT{"Flow needs business reply?"}
    IN -->|"No"| IA["Inbound channel adapter"]
    IN -->|"Yes"| IG["Inbound gateway"]
    OUT -->|"No"| OA["Outbound channel adapter"]
    OUT -->|"Yes"| OG["Outbound gateway"]
    IA --> V["Next: evaluate protocol, poller/listener,<br/>payload, delivery guarantees, and ops"]
    IG --> V
    OA --> V
    OG --> V
~~~

**Inbound/outbound direction is defined from the Spring Integration application's perspective.** An outbound adapter may wait on I/O or receive a broker acknowledgment, yet a protocol acknowledgment **does not automatically turn** a one-way operation into a business reply in the flow.

## 2. Decision Framework Before Choosing an Endpoint

You can use these ten questions during an integration flow design session:

| Criterion Group | Question to Resolve | Impact on Selection |
| --- | --- | --- |
| **Direction** | Who initiates: external system or application? | Inbound or outbound |
| **Interaction pattern** | Must a result be returned for the caller to continue? | Channel adapter or gateway |
| **Ingestion style** | Must the source be queried on a schedule or does it push events? | Polling adapter, listener/consumer, HTTP endpoint |
| **Latency/SLA** | Can data be delayed minutes or must responses arrive in seconds? | Poll interval, gateway timeout, listener concurrency |
| **Throughput** | Messages/second, payload size, peak load, and backlog? | Batching, prefetch, capacity, streaming, backpressure |
| **Message contract** | Is payload File, String, bytes, DTO, or record? Which headers stay? | Converter, transformer, header mapper, serializer |
| **Delivery guarantees** | Are redelivery, resends, duplicates, out-of-order, or loss allowed? | ACK/offset, idempotency, transactions, state store |
| **Error handling** | How are timeouts, invalid data, and target failures handled? | Error flow, retry/backoff, dead-letter, reconciliation |
| **Security** | Auth, authorization, encryption, sensitive data, trust boundaries? | TLS/SSH, secret management, header allowlist |
| **Lifecycle/observability** | When to start/stop? Where to track errors and progress? | SmartLifecycle, schedulers, listener containers, metrics |

These ten criteria must be analyzed **together**. For example, a source that fits polling at the protocol level may still miss a 200 ms maximum latency SLA. A broker may satisfy throughput yet fail to solve the need for a **synchronous HTTP response** to an end user.

## 3. Criterion 1: Data Direction and Initiator

Identify which system **actively** starts each exchange:

| Scenario | Message Direction in App | Appropriate Endpoint |
| --- | --- | --- |
| App scans directory for partner files | Outside → inside | File inbound adapter |
| App reads new data over SFTP | Outside → inside | SFTP inbound adapter |
| Broker delivers messages from JMS queue to app | Outside → inside | JMS inbound adapter |
| App publishes events to Kafka | Inside → outside | Kafka outbound adapter |
| App writes report files to SFTP server | Inside → outside | SFTP outbound adapter |
| App calls pricing REST API and uses returned value | Inside → outside → inside | HTTP outbound gateway |
| HTTP client calls app and needs flow response | Outside → inside → outside | HTTP inbound gateway |

Another frequently overlooked direction: **Java code calling into a flow**. If a Java service wants to invoke a flow through an interface and receive a result, use **@MessagingGateway**. A messaging gateway connects a method interface to a messaging flow; it does not necessarily mean sending a request to an external system.

## 4. Criterion 2: One-Way or Request–Reply

The difference is not just whether a technical response exists. Ask: **"Does the caller need business response data to complete its current decision?"**

~~~mermaid
flowchart LR
    subgraph ONE["One-way"]
        A1["MessageChannel"] --> A2["Outbound adapter"]
        A2 --> A3["File / Broker / DB"]
    end
    subgraph TWO["Request–reply"]
        G1["Request channel"] --> G2["Outbound gateway"]
        G2 --> G3["External API / service"]
        G3 -->|"Business response"| G2
        G2 --> G4["Reply channel"]
    end
~~~

**One-way example:** publishing OrderCreated to Kafka so other systems update state when ready. The producer may receive a broker-level acknowledgment, while consumers might not have processed it yet.

**Request–reply example:** needing a shipping fee from a partner API before confirming an order. The flow needs the HTTP response body; an outbound HTTP gateway fits better than a one-way outbound adapter.

**Long-running processing example:** an API kicks off a calculation taking several minutes. Holding a synchronous gateway connection open for that entire duration may be unsuitable. Design HTTP 202 Accepted with a job ID, followed by status queries or completion callbacks/events. In that case, clearly specify the status contract and correlation ID.

## 5. Criterion 3: Polling or Message-Driven Sources

This criterion primarily concerns **inbound endpoints**, and also applies to consumers pulling messages from a PollableChannel on the outbound side.

| Mechanism | Characteristics | Common Sources |
| --- | --- | --- |
| **Polling inbound** | App actively invokes MessageSource on a schedule | File, SFTP, JDBC query |
| **Message-driven inbound** | Listener/consumer receives data via client/protocol mechanism | JMS, AMQP, Kafka |
| **Request-driven** | External system sends requests to a listening endpoint | HTTP inbound gateway/adapter |
| **Internal polling consumer** | Endpoint actively pulls messages from a PollableChannel | QueueChannel → outbound adapter |

With polling, configure **fixed delay/rate**, **maxMessagesPerPoll**, empty poll handling, timeouts, and seen-state tracking. Polling too fast raises network, CPU, or database load; polling too slow increases latency.

With message-driven ingestion, review **consumer concurrency**, **prefetch/batching**, **ACK or offset commits**, redelivery potential, and rebalance/recovery behavior. A Kafka consumer runs its client's internal poll loop, which is **not equivalent** to configuring a Spring Integration Poller on every Kafka inbound adapter.

### 5.1. When Replacing a File/SFTP Source with Kafka

It is never just swapping one adapter class. File/SFTP asks "has the file finished writing?" and "which files were picked up?"; Kafka has topics/partitions, keys, offsets, consumer groups, and commit semantics. Re-examine:

- **Payload:** File or InputStream becomes bytes, String, or record depending on deserializer.
- **Metadata:** filename/path becomes topic, partition, offset, key.
- **Progress:** file filters become offsets/ACKs and protocol checkpoints.
- **Ordering:** can rely on per-key ordering within one partition, not automatically across an entire topic.
- **Recovery:** align commit boundaries with business persistence steps.

Business handlers after the transformer can be reused if a stable domain contract is agreed upon.

## 6. Criterion 4: Latency, Load, and MessageChannel Model

Adapter selection governs how data enters and leaves, whereas **MessageChannel** governs how data moves between endpoints.

| Channel | Core Semantics | When to Be Careful |
| --- | --- | --- |
| **DirectChannel** | Invokes subscriber synchronously on sender thread | Slow I/O handlers can block poller/listener/caller |
| **ExecutorChannel** | Offloads processing to an executor | Must bound pool, queue, async errors, and ordering |
| **QueueChannel** | Buffers messages for a polling consumer | Requires capacity, poller, and restart durability |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Must handle errors or partial success across branches |

For example, suppose incoming load hits **500 messages/second** while downstream handles only **50 messages/second**. Switching to ExecutorChannel avoids blocking the producer immediately, yet the backlog keeps growing as long as the mismatch persists. The solution must include **ingress/egress rate limits, capacity bounds, appropriate concurrency, overload policies**, or scaling downstream capacity.

Also assess **payload size**. Receiving 100,000 tiny files is very different from receiving 10 multi-GB files. For large files, path-based or streaming models fit better than loading whole payloads into an in-memory String/byte array.

**Default QueueChannel is not a disk-persisted durable queue.** If queued messages must never be lost on process crash, provide a persistent MessageStore, an external broker, or an outbox pattern. Picking a good adapter does not solve channel persistence requirements.

## 7. Criterion 5: Delivery Guarantees and Reprocessing Capability

This is often the decisive criterion for financial data, orders, or critical events. Agree on what "success" means:

~~~text
Source emitted data
        ↓
Adapter received
        ↓
MessageChannel accepted
        ↓
Handler processed business logic
        ↓
Adapter sent outbound
        ↓
Target acknowledged per protocol
        ↓
Target completed business processing (if feedback/reconciliation exists)
~~~

These milestones do not necessarily belong to a single transaction. **JMS/AMQP ACK, Kafka offset commit, file picked by poller, HTTP 2xx, or Kafka producer acknowledgment** each have specific scopes. Never treat an intermediate signal as proof that the entire business workflow completed.

| Requirement | What Must Be Designed |
| --- | --- |
| Tolerate at-least-once redelivery | Idempotent handler, duplicate handling, reasonable retries |
| No message loss on restart | Durable source, checkpoint/offset/state store, or outbox |
| Preserve ordering for the same order | Appropriate partition/queue/channel keys and concurrency |
| Never create two business records | Unique constraints and stable idempotency keys on processing side |
| Multiple targets must be updated | Per-target status, outbox, retry/reconciliation, or compensation |
| Transaction required | Identify exact resources covered by the transaction |

**No outbound adapter guarantees end-to-end exactly-once by itself** across arbitrary combinations of HTTP, SFTP, files, brokers, and databases. If business rules forbid duplicate side effects, enforce **business keys** (such as partnerId + orderId or eventId), paired with progress persistence and recovery procedures.

### 7.1. "Unclear Whether Send Succeeded" Is a Real State

Suppose an outbound HTTP adapter/gateway sends an order-creation request. The server writes the data, yet the connection drops before returning the response. The client sees a timeout. Retrying immediately without a deduplication key can create a second order.

With Kafka/JMS/AMQP, losing connectivity right around acknowledgment poses the same problem. Therefore define an **ambiguous outcome state** and **reconciliation strategy**, rather than having only success and failure labels.

## 8. Criterion 6: Payload, Headers, and Schema Contracts

A Spring Integration Message has a **payload** and **headers**. The chosen adapter must support the payload type or pair with appropriate converters/transformers before and after it.

| Source/Target | Common Payload | Metadata to Consider |
| --- | --- | --- |
| **File** | File, String, bytes depending on direction and config | Filename, path, encoding, file completion state |
| **SFTP** | Local File, remote file, InputStream depending on adapter | Remote path, filename, session, write timestamp |
| **HTTP** | Body String/bytes/DTO | URL, method, status, Content-Type, correlation |
| **JMS** | TextMessage/BytesMessage after converter | Message ID, correlation ID, destination, properties |
| **AMQP** | Body bytes/DTO after converter | Exchange, routing key, delivery tag, content type |
| **Kafka** | Value/record after deserializer | Topic, partition, offset, key, timestamp |
| **Database/JDBC** | Row values, map, or object per config | Columns, keys, watermark, transactions |

Do not assume two adapters emit identical payloads/headers simply because they carry the same business entity. For instance, File inbound typically emits a **File**, whereas a Kafka inbound adapter may emit a **JSON String** depending on its deserializer. Place a transformer right behind the inbound boundary to normalize both sources into an **OrderEvent** before entering the business flow.

### 8.1. Header Mappers and Cross-Boundary Data

**replyChannel**, **errorChannel**, and headers holding internal infrastructure objects should not be serialized directly to external systems. Header mappers for JMS/AMQP/HTTP/Kafka have distinct scopes and rules.

Define clearly:

- Which fields serve as stable **eventId** and **schemaVersion**.
- Which fields serve correlation/tracing and which serve as idempotency keys.
- Charset, Content-Type, serializer, schema, and version compatibility.
- Which headers are **allowed** outbound; which sensitive data must be stripped.
- How invalid JSON/CSV, missing required fields, or schema changes are handled.

For CSV files, parsers must handle commas, quotes, and newlines properly; splitting strings by commas fits only toy examples. For large data, bound payload sizes and process via streaming/batching where needed.

## 9. Criterion 7: Errors, Timeouts, and Retries

Never select an adapter solely because it works on the happy path. Check these failure modes:

1. **Source/target unreachable:** DNS, network loss, expired SFTP session, broker disconnect, exhausted DB pool.
2. **Contract violation:** malformed JSON/CSV, wrong payload type, missing header, incompatible serializer.
3. **Source/target overload:** deep queues, rate limits, timeouts, exceeded connection limits.
4. **Business failure:** database constraint violation, insufficient stock, duplicate business key.
5. **Ambiguous outcome:** request went out, but ACK/reply was lost.

~~~mermaid
flowchart TD
    A["Receive or send message"] --> V{"Which failure type?"}
    V -->|"Bad data/schema"| BAD["Quarantine message, fix data or contract"]
    V -->|"Transient: network/overload"| RET["Bounded retry + backoff"]
    V -->|"Target state unknown"| REC["Reconciliation + idempotency"]
    V -->|"Permanent error/permissions"| FIX["Alert, fix config/permissions"]
    RET --> A
~~~

**Retry** means trying again; **idempotency** means ensuring a redelivery or resend causes no duplicate business side effects. You cannot substitute idempotency simply by increasing retry counts or shortening timeouts.

With **DirectChannel**, downstream exceptions can propagate back up the same call stack. With **ExecutorChannel/QueueChannel**, errors may occur after the producer already returned, requiring **ErrorMessage/errorChannel** paths, listener error handlers, advice, or appropriate callbacks. Verify error handling against the exact endpoint in use.

## 10. Criterion 8: Security, Environment, and Connection Lifecycle

Each protocol brings distinct operational requirements:

| Protocol | Resources and Security to Consider |
| --- | --- |
| File | Directory permissions, safe paths, filenames, disk quotas |
| SFTP | SSH host key verification, keys/credentials, session pooling, timeouts/reconnects |
| HTTP | TLS, auth tokens, timeouts, proxies, rate limits, response code contracts |
| JMS/AMQP | Broker credentials, TLS, connection factories, listener containers, topology |
| Kafka | Bootstrap brokers, TLS/SASL, ACLs, consumer groups, serializers |
| Database | JDBC URL, pool, least-privilege accounts, transaction isolation |

In Spring Integration applications, many endpoints implement **Lifecycle/SmartLifecycle** for start/stop control. Polling inbound adapters require schedulers; JMS/AMQP/Kafka inbound endpoints typically depend on listener containers or consumers; outbound endpoints depend on connections/sessions/clients. **isRunning() == true** does not prove the external server is reachable or all messages succeeded.

When starting a multi-stage system, usually **prepare downstream before enabling inbound**; when stopping, **halt new ingestion before stopping processors**. Account for phase order, active tasks, backlog, pending replies, and shared resources. **stop() does not automatically wait for all messages to finish** or recover progress after a crash.

## 11. Selection Matrix by System

The table below is a starting point to **narrow options**, not a technology ranking:

| Technology | Suitable Problems | Common Inbound Mechanism | Checks Before Choosing |
| --- | --- | --- | --- |
| **Local file** | Batch import/export, simple exchange | Directory polling | File completion, permissions, naming, restarts |
| **SFTP** | Cross-organization file exchange over network | File polling/sync | SSH, sessions, remote directory, atomic publish |
| **HTTP** | Online APIs, request–reply, or webhook dispatch | Request-driven | SLA, status/body, auth, timeouts, idempotency |
| **JMS** | Queue/topic integration in JMS ecosystems | Message-driven listener | Destination, transaction/ACK, redelivery, converter |
| **AMQP** | Queues, exchange/binding routing | Message-driven listener | Exchange/routing key, prefetch, ACK/NACK, DLQ |
| **Kafka** | Event streams, partitioned log retention/replay | Consumer/listener | Topic/key/partition, offset, group, retention, ordering |
| **JDBC/database** | Syncing state from tables or writing records | Polling query or outbound update | Watermark, transactions, unique keys, query load |

Never conclude "Kafka is always better than JMS" or "SFTP is always slower than HTTP". Suitability depends on workload, deployment topology, contract requirements, existing infrastructure, and team operational maturity.

### 11.1. Distinguishing Queues from Event Logs

JMS/AMQP are commonly used to distribute work via queues with matching ack/redelivery semantics. Kafka is commonly used for event streams stored by topic/partition when multiple consumer groups or retention-based replay are needed. Still, every platform offers multiple configuration modes; compare by **concrete delivery requirements** rather than labels like "message queue" or "stream".

### 11.2. When Is Database Polling Reasonable?

If the source system only exposes read access to tables, JDBC polling can be a pragmatic option. Query using an **increasing watermark/key or processing status**, backed by proper indexes and batch limits; if the watermark updates at the wrong time, records can be skipped or read twice.

If you control the source schema/application and need reliable event emission after data commits, consider the **outbox** pattern. It coordinates state persistence and event publication far more reliably than guessing changes by timestamps alone.

## 12. Scenario A: Batch Order Import from SFTP

**Hypothetical requirement:** A partner places CSV files on SFTP hourly; each file contains multiple orders. Delays of a few minutes are acceptable. Orders must not be created twice if a file is resent or the app restarts.

**Selection:** Scheduled SFTP inbound adapter, followed by MessageChannel, CSV-parsing transformer, and a service activator validating and persisting orders. If receipts must be exported, use a separate file/SFTP outbound adapter.

~~~mermaid
flowchart LR
    S["SFTP server"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> CH["rawFiles"]
    CH --> T["CSV parser + validation"]
    T --> O["OrderService<br/>idempotency + transaction"]
    O --> OUT["Receipt message"]
    OUT --> OA["SFTP outbound adapter"]
    OA --> D["SFTP receipts"]
~~~

**Mandatory decisions:**

- Synchronize remote files locally or stream them, depending on size and setup.
- Partner convention for publishing **completed files**; avoid reading mid-upload files.
- Filter/metadata store to reduce re-ingestion after restarts.
- Deduplicate by **partnerId + orderId**, not solely by filename.
- Distinguish CSV format errors (usually quarantined) from SFTP network errors (retryable).
- Receipt writing, naming, overwrite avoidance, and partial-order success handling.

SFTP fits an agreed partner file-exchange contract. There is no need to force Kafka simply because the internal app uses messaging: switching protocols requires mutual support and a real business need.

## 13. Scenario B: Online Ordering over HTTP

**Hypothetical requirement:** A client sends POST /orders and needs the order ID or rejection message in the same request. The flow checks inventory, fetches pricing from an external API, and creates the order.

**Selection:** HTTP **inbound gateway** to receive requests and return responses; HTTP **outbound gateway** if the flow needs the response body from the pricing service. Business steps use transformers/service activators and channels matching the SLA.

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant I as Inbound HTTP gateway
    participant F as IntegrationFlow
    participant O as Outbound HTTP gateway
    participant P as Pricing API
    C->>I: POST /orders
    I->>F: Message<OrderRequest>
    F->>O: PriceRequest
    O->>P: HTTP request
    P-->>O: PriceResponse
    O-->>F: Message<PriceResponse>
    F-->>I: OrderResult
    I-->>C: HTTP response
~~~

**Mandatory decisions:**

- Request/response schemas, Content-Type, HTTP status codes, and business error codes.
- Timeouts for client, gateway, external API HTTP client, and retry policies.
- Idempotency key in case the client retries POST after a timeout.
- How to return results for slow processing: synchronous response or 202 Accepted with job ID.
- Authentication, authorization, rate limiting, and stripping sensitive data from headers/logs.

A one-way inbound HTTP adapter does not automatically provide the business response contract of an inbound gateway. If no reply is needed within the same request, you can design asynchronous ingestion with a separate status response.

## 14. Scenario C: Distributing Order Events to Multiple Systems

**Hypothetical requirement:** Once an order-creation transaction commits, analytics, CRM, and warehouse systems must receive the OrderCreated event. Targets may be down temporarily; safe recovery is required.

**Viable selection:** Persist the event into a **transactional outbox** within the business transaction, and have a worker publish via a **Kafka outbound adapter** if the ecosystem requires event streams, retention, and multiple consumer groups. If existing infrastructure uses JMS/AMQP and the workload centers on queue-based distribution, the corresponding adapter also works well.

~~~text
OrderService
  -> Database transaction: Order + OutboxEvent
  -> Outbox polling/worker
  -> MessageChannel<OrderCreated>
  -> Kafka/JMS/AMQP outbound adapter
  -> Broker
  -> Consumer per target system
~~~

**Mandatory decisions:**

- Stable event ID and schemaVersion; data compatibility policy.
- Topic/key/partition for Kafka or destination/routing for JMS/AMQP.
- Recording when outbox items were sent and handling ambiguous ACK states.
- Idempotent consumers since events may be redelivered.
- Retention, dead-letter/retry, and reconciliation procedures when consumers lag.

A broker accepting a message does not mean the warehouse or CRM system succeeded in updating. If a result from a target is needed to continue an in-flight request, design explicit reply/correlation or a stateful async workflow.

## 15. Java DSL Example: Choosing File Inbound Polling for Batch Ingestion

Hypothetical requirement: a partner supplies CSV files in a **local directory** (simulating a file source, extensible to SFTP). A few seconds of latency is acceptable, so a file inbound polling adapter fits. The flow emits **Message<File>**, converts it to a UTF-8 String, and performs simple processing. The goal is to illustrate how selection criteria translate into endpoint configuration.

With Spring Boot, use the Spring Integration starter and **spring-integration-file** compatible with Spring Boot's BOM.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
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
public class BatchFileFlowConfiguration {

    @Bean
    public MessageChannel rawFiles() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(10)))
            .channel("rawFiles")
            .get();
    }

    @Bean
    public IntegrationFlow inspectCsvFlow() {
        return IntegrationFlow.from("rawFiles")
            .transform(File.class, source -> {
                try {
                    return java.nio.file.Files.readString(
                        source.toPath(), StandardCharsets.UTF_8);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .handle(String.class, (content, headers) -> {
                System.out.println(
                    "Received CSV, character count: " + content.length());
                return null; // Illustrative flow ends here.
            })
            .get();
    }
}
~~~

### 15.1. Which Decisions Are Encoded in the Example?

| Criterion | Configuration or Behavior |
| --- | --- |
| Inbound direction | Files.inboundAdapter creates messages from external files |
| Polling | Pollers.fixedDelay sets a 5-second cycle |
| Batching | maxMessagesPerPoll(10) caps messages per poll |
| Source filter | patternFilter("*.csv") selects only matching filenames |
| Channel | rawFiles is a DirectChannel; consumer runs synchronously |
| Payload contract | Message<File> → transformer reads UTF-8 String |
| Final handling | Illustrative handler only logs; no database writes yet |

### 15.2. How to Test

1. Start the application with the configuration above.
2. Place an **orders-001.csv** file with a few lines into **./data/inbox**.
3. Watch the handler print the character count after a poll cycle.
4. Place **readme.txt**: it is ignored by patternFilter.
5. Try a malformed CSV or a very large file to notice the example lacks a parser/streaming, then define extensions based on real requirements.

**Intentional limitations:** The example does not parse CSV, lacks database transactions, does not ensure files finished writing, and has no durable filters or restart idempotency. Before production use, add file-readiness checks, durable source tracking, business deduplication, error routing, and observability. These are the very design criteria that distinguish a demo from a production integration solution.

## 16. From Design to Acceptance Criteria

Choosing an adapter is not enough; specify verifiable outcomes before implementation:

| Requirement | How to Verify |
| --- | --- |
| Correct direction and protocol | Inbound receives data; outbound writes/sends to right target |
| Valid contract | Payload/headers/schema/encoding match consumer expectations |
| Meets latency SLA | Measure receipt, processing, and response times under realistic load |
| Zero loss across restarts | Kill abruptly, restart, verify checkpoints/backlog |
| Zero duplicate business effects | Replay same eventId/orderId and inspect target state |
| Recoverable errors | Simulate timeouts, broker errors, missing permissions, overload; verify retries |
| Bad data quarantined | Send invalid schema payloads and verify error flow |
| Safe stop/start | Stop inbound, wait for processing, resume, check in-flight messages |
| No data leaks | Inspect logs, outbound headers, secrets/credentials |
| Sufficient operational signals | Inbound/outbound metrics, backlog, errors, retries, ACKs, latency, business outcomes |

### 16.1. A Short Decision Record

Before implementing, capture details like these in a design doc:

~~~text
Flow: PartnerOrderImport
Source/target: SFTP partner -> OrderService -> database
Direction: inbound polling
Endpoint: SFTP inbound adapter + poller
Input: UTF-8 CSV, schema v1, file completed via rename
Throughput: hourly batch; acceptable latency < 5 minutes
Channel: DirectChannel for parse/validate; load bounded by DB capacity
Progress: durable metadata store + partnerId/orderId key
Success: business transaction commits; receipt handled separately
Errors: invalid CSV -> quarantine; network error -> retry/backoff; DB error -> recovery
Operations: SFTP secret management, endpoint lifecycle, backlog/error metrics
~~~

Values in this example are **design assumptions** and should be replaced with actual system requirements and measurements.

## 17. Common Mistakes When Choosing Adapters

**Choosing by technology name before defining the communication pattern.** An HTTP flow needing a response cannot be evaluated the same way as a one-way Kafka publish flow.

**Confusing acknowledgments with business outcomes.** JMS/AMQP ACKs, Kafka producer acknowledgments, or HTTP 202 each have distinct scopes; specify the completion milestone your business requires.

**Assuming polling is always inferior.** Polling is entirely sensible when sources only expose scheduled-read APIs or partners deliver batches. Evaluate SLAs and load rather than forcing event-driven everywhere.

**Using QueueChannel and assuming automatic protection against message loss.** Default in-memory queues do not guarantee crash recovery.

**Ignoring payload types when swapping adapters.** Files may emit File, while Kafka emits String/record; re-check transformers and header mappings.

**Increasing concurrency before measuring downstream.** More workers can simply accelerate backlog buildup or overwhelm the target system.

**Retrying infinitely on bad data.** Schema parsing failures never heal through retries; separate transient failures from bad-data errors.

**Using correlation ID as the sole deduplication key.** Correlation supports tracing and request–reply; idempotency requires a stable business key checked where side effects happen.

**Monitoring only endpoint isRunning.** An endpoint can be running while unable to connect, failing every poll, or building backlogs. Observe the entire pipeline.

## 18. Self-Check Questions

1. A partner delivers CSV files nightly and tolerates several minutes of latency. Which inbound direction/mechanism would you choose? What conditions must be checked before production?
2. If an API must return a shipping fee so the flow can compute the total amount, why is an outbound gateway better suited than an outbound adapter?
3. A Kafka consumer runs an internal poll loop. Does that mean every Kafka inbound adapter must configure a Spring Integration poller?
4. Why can raising maxMessagesPerPoll make things worse when downstream is already overloaded?
5. When switching from files to Kafka, which aspects of payload, metadata, ACK/offset, and ordering must be re-evaluated?
6. An order-creation POST times out, yet the target may have already saved it. What mechanism is needed before retrying?
7. When does QueueChannel need persistent storage or replacement with a broker/outbox?
8. Why can JDBC polling based solely on last-updated timestamps miss or duplicate records?
9. If an event is dispatched to two systems and only one target succeeds, what state must be recorded for recovery?
10. Beyond isRunning, which metrics indicate that an adapter and the entire integration flow are healthy?

## Summary

**Choosing an adapter for an integration flow** is a decision about **communication contracts, delivery semantics, and operations**. Start from **data direction**, **one-way vs. request–reply**, and **polling vs. listener**, then verify load, MessageChannel, payload/headers, ACK/offset, retries, idempotency, transactions, security, and lifecycle. File, SFTP, HTTP, JMS, AMQP, Kafka, and databases all have their place when solving the right problem. A solid choice is backed by verifiable configuration and failure-recovery scenarios, not merely the name of the adapter selected.
