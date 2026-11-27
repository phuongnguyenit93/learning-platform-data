# Bridge Between Two Brokers

**Chapter:** Design patterns  
**Lesson:** Bridge between two brokers  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Context:** Connecting external systems with inbound/outbound adapters, gateways, pollers, and `MessageChannel`; focusing on bridging JMS, AMQP/RabbitMQ, and Kafka while connecting to HTTP, File/SFTP, and JDBC when building or operating integration flows.

> **Main takeaway:** A bridge transfers messages from a **source broker** to a **target broker**, yet it is not merely “connecting two queues” with one config line. Two brokers have **different formats, acknowledgment mechanics, transactions, ordering, routing, retries, and connection lifecycles**. A reliable bridge requires **a message contract**, **clear responsibility boundaries**, **crash recovery**, and **proof of handoff**.

## 1. The Problem: Why Bridge Two Brokers?

A legacy system uses **JMS** to emit order-created events. A newer system consumes via **RabbitMQ**, while the analytics platform runs on **Kafka**. During migration, an enterprise cannot swap every producer and consumer simultaneously.

A **broker-to-broker bridge** consumes messages from side A, transforms contracts if needed, and publishes corresponding messages to side B.

~~~mermaid
flowchart LR
    OLD["Legacy Order Service"] --> JMS["JMS broker / orders.queue"]
    JMS --> SI["Spring Integration Bridge"]
    SI --> AMQP["RabbitMQ / orders.exchange"]
    AMQP --> NEW["Fulfillment Service"]
    SI -.-> STORE["Outbox / Failure Store"]
    STORE -.-> SI
    SI --> OBS["Metrics / Tracing / Audit"]
~~~

Typical goals:

- **Migration:** Gradually shift consumers from one broker to another.
- **Interoperability:** Connect JMS systems to RabbitMQ or Kafka without rewriting all producers.
- **Event distribution:** Forward the same business event to analytics or another application.
- **Boundary isolation:** Separate network zones, tenants, organizations, or security policies.
- **Protocol adaptation:** Translate metadata, routing keys, partition keys, schemas, and payloads.
- **Operational decoupling:** Avoid forcing the source system to upgrade at the target system's pace.

A bridge **must not** be used to paper over semantic mismatches. If the source emits command `CREATE_ORDER` while the target expects event `ORDER_CREATED`, decide explicitly whether **a command is being forwarded** or **an event already happened**. Misrepresenting message intent is a business contract bug, not a broker issue.

### 1.1. Learning objectives

After this lesson, learners can:

1. Distinguish **Messaging Bridge**, `BridgeHandler`, `MessageChannel`, inbound adapters, outbound adapters, and gateways.
2. Design JMS ↔ AMQP or Kafka ↔ JMS / Kafka ↔ RabbitMQ bridges with accurate boundary diagrams.
3. Define contracts for payloads, message keys, headers, correlation, schema versions, and transformation rules.
4. Accurately explain **acknowledgment**, **publish confirmation**, **transactions**, **redelivery**, and **delivery guarantees**.
5. Pinpoint crash windows causing message loss or duplicates and know when **inbox/outbox** is needed.
6. Design retries, error channels, dead-letter queues/topics, idempotency, and controlled replays.
7. Test against real brokers, measure throughput/lag, and build operational runbooks.

## 2. What Is the Bridge Pattern, and What Is It Not?

In **Enterprise Integration Patterns (EIP)**, a bridge connects messaging systems that may use different technologies and conventions. Spring Integration implements EIP patterns via `Message`, `MessageChannel`, adapters, gateways, transformers, routers, filters, and error flows.

However, “bridge” is used at **three distinct levels**:

| Concept | Role | Example |
| --- | --- | --- |
| **Channel bridge / `BridgeHandler`** | Passes Spring Messages between channels **inside** one app | `inputChannel -> bridge -> outputChannel` |
| **Broker-to-broker bridge** | Consumes from broker A and publishes to broker B | JMS queue → RabbitMQ exchange |
| **Broker-native federation/connector** | Broker/connector mechanism managing replication or integration | Kafka Connect, RabbitMQ federation/shovel as suited |

`BridgeHandler` in Spring Integration **does not open connections to two brokers by itself**. A broker bridge typically pairs an **inbound adapter/gateway** at one end, `MessageChannel` and contract handling in the middle, and an **outbound adapter/gateway** at the other end.

### 2.1. Adapter or gateway?

| Component | Suitable case |
| --- | --- |
| **Inbound channel adapter** | Receives one-way messages/events from source, emits to `MessageChannel` |
| **Message-driven inbound adapter** | Source broker pushes messages to a listener instead of app polling on schedule |
| **Outbound channel adapter** | Sends one-way messages to target broker |
| **Gateway** | Request–reply: sends request and awaits reply per contract |
| **MessageChannel** | Transfers internal messages; sync or async depending on channel type |
| **Transformer** | Converts payloads/headers between source and target contracts |
| **Router** | Picks destinations, topics, exchanges, or tenants |
| **Filter** | Blocks invalid or out-of-scope messages |

Do not turn a **one-way event bridge** into a request–reply gateway just to “wait for broker success”: publish confirmation is not a **business reply** from a consumer. Conversely, if the source is an RPC request needing a response, the bridge must handle **reply channels, correlation, and timeouts** instead of forwarding and dropping it.

### 2.2. Transporting vs. translating semantics

**Pass-through bridge:** Preserves stable payload format, translating only protocols and required headers.  
**Transforming bridge:** Normalizes schemas, strips PII, rewrites routing keys, versions contracts, or enriches metadata.

An active bridge can reject invalid messages into **quarantine** instead of guessing missing fields.

## 3. Overall Architecture of a Bridge

~~~mermaid
flowchart TD
    SA["Source broker A"] --> IA["Inbound adapter / listener"]
    IA --> CH["MessageChannel"]
    CH --> VAL["Validate + normalize contract"]
    VAL --> ID["Idempotency / inbox if needed"]
    ID --> MAP["Transform / route / enrich"]
    MAP --> OA["Outbound adapter / publisher"]
    OA --> TA["Target broker B"]
    OA --> CONF{"Publish confirm / transaction result"}
    CONF -->|Success per contract| ACK["Source ACK or commit per policy"]
    CONF -->|Failure / timeout| ERR["Retry, recover, reconcile"]
    ERR --> DLQ["Durable failure store / DLQ / quarantine"]
    DLQ --> REPLAY["Controlled replay"]
    REPLAY --> MAP
    VAL -->|Invalid| DLQ
~~~

The diagram shows **logical responsibility**, not an implication that every adapter holds source messages open until publish confirmation. In durable **outbox-based** bridges, the source can be ACKed once persisted safely to inbox/outbox, while another worker publishes to broker B asynchronously.

### 3.1. Defining the boundaries

A bridge crosses at least three domains:

1. **Source domain:** Broker A, consumer groups/queues, offsets or sessions, authentication, and read permissions.
2. **Application domain:** Spring Messages, channels, mappings, retries, state stores, lifecycles, and observability.
3. **Target domain:** Broker B, producer sessions, routing, keys/partitions, publish confirms, and write permissions.

During outages, domains can **fail independently**. A source JMS transaction does not automatically wrap a RabbitMQ publish or Kafka producer transaction.

### 3.2. A good bridge needs clear ownership

Define:

- Who owns event schemas and versioning?
- Who operates the bridge, broker A, and broker B?
- Who governs retention, DLQs, replays, and processing rates?
- When the source ACKed before the target received it, where does **durable responsibility** live?
- Who can modify routing keys, trust stores, ACLs, or consumer group configs?
- Who triages duplicates, out-of-order arrivals, and invalid events?

Without an owner, a bridge becomes a neglected middleman where nobody knows where a message ended up.

## 4. Comparing JMS, AMQP/RabbitMQ, and Kafka

| Aspect | JMS / compatible brokers | AMQP / RabbitMQ | Apache Kafka |
| --- | --- | --- | --- |
| Common model | Queues and topics per JMS API/provider | Exchanges route to queues; consumers read queues | Partitioned topics; consumer groups track offsets |
| Message identity | `JMSMessageID`, `JMSCorrelationID`, properties | AMQP properties/headers, `messageId`/`correlationId` | Topic/partition/offset, record keys, headers |
| Consume acknowledgment | JMS session transaction or ack mode | Consumer ACK/NACK/reject, requeue per config | Offset commit/ack per consumer/container |
| Publish confirmation | JMS send/session commit per provider/config | Publisher confirms/returns when configured | Producer send ack/future per `acks` and settings |
| Ordering | Depends on queue, session, concurrency/provider | Depends on queue, consumer topology, requeue/redelivery | Record order within **one partition** |
| Durability | Durable queues/topics/messages per config | Durable exchanges/queues and persistent messages | Retention, replication, producer durability configs |
| Dead-letter | Provider DLQ/redelivery policy | DLX, dead-letter routing, TTL/policy | DLT per app/framework or connector |
| Replay | Typically via DLQ/source logic | Republish from DLQ/store per policy | Consumer seek/offset reset or republish under governance |
| Transactions | JMS transacted sessions, provider-dependent | Channel transactions and broker semantics | Producer transactions/idempotent producer scoped to Kafka |

**Note:** This table describes general models, **not guaranteed defaults** across all brokers or Spring releases. JMS is an API/contract; runtime behavior depends on ActiveMQ Artemis, IBM MQ, or other providers.

### 4.1. Kafka is not a JMS queue in a one-to-one sense

In Kafka, records can be read independently by **multiple consumer groups**. Offsets track group position; reading/committing offsets does not delete records from topics. A Kafka → JMS bridge avoiding duplicate publishes must manage **source record keys, consumer groups, offset commits, and target-side idempotency**.

### 4.2. A RabbitMQ exchange is not a queue

Outbound adapters typically publish to an **exchange and routing key**. Exchanges can route to many queues or none at all. **An error-free producer call does not guarantee any consumer received the message**. Verify exchange/queue bindings, mandatory returns, publisher confirms, and topology.

### 4.3. JMS topic subscriptions have their own lifecycle

When a bridge reads a JMS topic instead of a queue, define client IDs, durable subscriptions, shared subscriptions, and provider semantics; restarts or changing subscription IDs can **re-read or miss** messages depending on config. Never apply queue assumptions directly to topic subscribers.

## 5. Message Contracts Crossing Two Brokers

Spring Integration messages hold **payload and headers**, while source/target brokers carry distinct metadata. A bridge must build a **canonical message contract** without dropping essential business and operational fields.

### 5.1. Illustrative envelope

~~~json
{
  "eventId": "evt-T42-971-1",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "producer": "legacy-order-service",
  "occurredAt": "2026-11-23T08:00:00Z",
  "tenantId": "T42",
  "aggregateId": "ORD-971",
  "correlationId": "trace-84021",
  "causationId": "cmd-T42-971",
  "payload": {
    "orderId": "ORD-971",
    "status": "CREATED"
  }
}
~~~

This is an **illustrative application format**, not a payload generated automatically by Spring Integration. Real business data must follow sensitivity classification and schema compatibility rules.

### 5.2. Fields to preserve and their purposes

| Field | Meaning | Forwarding rule |
| --- | --- | --- |
| `eventId` or `operationId` | Stable identifier of the event/operation | **Never change across redeliveries/replays** |
| `eventType` | Business description | Never arbitrarily turn commands into fact events |
| `schemaVersion` | Parsing contract | Validate before publishing |
| `tenantId` | Data scope | Guard cross-tenant isolation; never trust raw headers blindly |
| `aggregateId` | Ordering/partitioning basis | Keep stable across migrations |
| `correlationId` | Links processing steps | Preserve or map explicitly across broker headers |
| `causationId` | Root cause event | Preserve for business tracing |
| `occurredAt` | Original event timestamp | Do not overwrite with bridge receipt time |
| `receivedAt`/`bridgedAt` | Latency observability | Added by bridge under distinct field names |
| `sourceRecordRef` | JMS ID, Rabbit delivery info, Kafka offset | Audit only; **never** use as business ID on republish |
| `traceparent` | Distributed trace if supported | Govern header propagation and trust |

If payloads contain PII, bridges should avoid creating unbounded copies in logs, DLQs, or traces. Use references and appropriate encryption/access controls.

### 5.3. Header mapping is not copy-all

JMS, AMQP, and Kafka use different header types and serialization rules. Not all headers transfer verbatim. For example:

- `JMSCorrelationID` must map onto headers/event fields understood by RabbitMQ/Kafka consumers.
- JMS `JMSReplyTo` is a `Destination` in the source domain; it has no automatic address in the target broker.
- RabbitMQ `deliveryTag` belongs to the source channel, not a reusable target ID.
- Kafka `offset` belongs to the source partition; **never copy it** as the target write offset assigned by target Kafka.
- Spring Integration `MessageHeaders.ID` and `TIMESTAMP` are framework-managed and should not substitute for business `eventId`.
- Headers containing Java objects break cross-broker serializers and non-Java consumers.

**Recommendation:** Allowlist required metadata, enforce explicit primitive types (string, integer, bytes...), and put original transport references in dedicated fields.

## 6. `MessageChannel`: Thread and Transaction Boundaries

A Spring Integration bridge should never pick a `MessageChannel` just because its name sounds right. Channel types dictate **when inbound handlers return** and **whether exceptions unwind back**.

| Channel | Trait | Impact on bridge |
| --- | --- | --- |
| `DirectChannel` | Typically synchronous dispatch on caller thread | Outbound errors can propagate to source listener |
| `ExecutorChannel` | Dispatches via executor/another thread | Source may return before target publish; needs durable handoff |
| In-memory `QueueChannel` | Buffers messages in internal queue | Does not guarantee durability across restarts |
| Persistent queue-backed channel | Backed by configured `MessageStore` | Evaluate store durability, pollers, and source acks |
| `PublishSubscribeChannel` | Fans out to multiple subscribers | One source message can trigger independent side effects |
| `FluxMessageChannel`/reactive | Reactive/backpressure boundary | Errors/lifecycles differ from sync flows; test separately |

### 6.1. Why `DirectChannel` is usually easier to reason about

~~~text
JMS listener thread
    -> DirectChannel
    -> Transform
    -> Rabbit publisher
    -> return/throw
    -> JMS listener decides ACK/rollback per config
~~~

With `DirectChannel`, synchronous publish errors can propagate back to the listener. Still, **publish method return does not equal durable broker acceptance**; RabbitMQ requires publisher confirm/return semantics.

### 6.2. Why an `ExecutorChannel` risks losing messages

~~~text
JMS listener -> ExecutorChannel.send() returns quickly
JMS listener ACKs
Worker thread later tries Rabbit publish -> fails
No durable handoff -> message can be lost
~~~

When async decoupling is needed, use a **persistent handoff** (inbox/outbox or governed message store) rather than an in-memory thread boundary alone.

### 6.3. Fan-out adds failure states

Suppose a message must go to both **RabbitMQ and Kafka**. Rabbit succeeds while Kafka fails. A single boolean `forwarded=true` cannot accurately represent per-destination state.

Each destination needs:

- Its own subscription/routing contract.
- Its own delivery state (`PENDING`, `SENT`, `FAILED`).
- Appropriate retries and idempotency keys.
- Independent backlog/lag monitoring.

## 7. A Simple JMS → RabbitMQ Bridge

Example goal: read from JMS queue `legacy.orders` and publish one-way to RabbitMQ exchange `orders.bridge` with routing key `orders.in`.

### 7.1. Diagram

~~~mermaid
flowchart LR
    JQ["JMS queue: legacy.orders"] --> JIA["Jms message-driven inbound adapter"]
    JIA --> MC["Spring MessageChannel"]
    MC --> AO["Amqp outbound adapter"]
    AO --> EX["Rabbit exchange: orders.bridge"]
    EX --> RQ["Rabbit queue: orders.in"]
    RQ --> C["New consumer"]
~~~

### 7.2. Illustrative Spring Integration Java DSL

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
class SimpleJmsToRabbitBridgeConfig {

    @Bean
    IntegrationFlow jmsToRabbitBridge(
            ConnectionFactory sourceJmsConnectionFactory,
            AmqpTemplate targetRabbitTemplate) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(sourceJmsConnectionFactory)
                        .destination("legacy.orders"))
                .handle(Amqp.outboundAdapter(targetRabbitTemplate)
                        .exchangeName("orders.bridge")
                        .routingKey("orders.in"))
                .get();
    }
}
~~~

**This is a wiring illustration**, not a complete production setup. Check APIs/overloads against your project's **Spring Integration BOM**, and declare `ConnectionFactory`, `AmqpTemplate`, queue/exchange/binding topology, converters, and listener container settings.

### 7.3. What is still missing for reliability

The snippet above **does not automatically**:

1. Declare durable Rabbit exchanges/queues/bindings.
2. Configure publisher confirms/returns and await confirmations.
3. Wrap source JMS transactions and Rabbit publishes in one distributed transaction.
4. Prevent target consumers from seeing duplicates after crashes.
5. Translate arbitrary JMS headers into valid AMQP headers.
6. Define retries, DLQs, or quarantine on errors.
7. Enforce authentication, TLS, ACLs, or payload serialization.
8. Pause intake during prolonged RabbitMQ outages.

Never mark **delivered-to-target** merely because the Java DSL flow returned without throwing.

## 8. Transforming Bridge: Normalizing Schemas Before Publishing

A canonical schema decouples source and destination formats.

~~~text
JMS bytes/TextMessage
   -> message converter
   -> validate schema/source attributes
   -> canonical EventEnvelope
   -> serialize target JSON/Avro/Protobuf
   -> outbound AMQP/Kafka
~~~

### 8.1. Java model example

~~~java
import java.time.Instant;
import java.util.Map;

public record BridgeEvent(
        String eventId,
        String eventType,
        int schemaVersion,
        String tenantId,
        String aggregateId,
        String correlationId,
        Instant occurredAt,
        Map<String, Object> payload) {}
~~~

**Illustrative business mapping:**

~~~java
BridgeEvent normalize(SourceOrderCreated source) {
    if (source.eventId() == null || source.eventId().isBlank()) {
        throw new InvalidSourceContractException("Missing stable eventId");
    }
    return new BridgeEvent(
            source.eventId(),
            "ORDER_CREATED",
            2,
            source.tenantId(),
            source.orderId(),
            source.correlationId(),
            source.occurredAt(),
            Map.of("orderId", source.orderId(), "status", "CREATED")
    );
}
~~~

`SourceOrderCreated` and `InvalidSourceContractException` are **application-defined types**, not Spring APIs. Mappings must handle nulls, schema evolution, timezones, numeric precision, encodings, validation, and sensitive data.

### 8.2. Schema evolution rules

- **Consumer compatibility:** Add optional fields with defaults and clear version bumps.
- **Breaking changes:** Use new versions/topics/routes or migration plans.
- **Unknown fields:** Specify whether consumers ignore or reject them.
- **Serialization:** Never use Java native serialization just because both sides run Java.
- **Schema registry:** When using Avro/Protobuf, define registry endpoints, subject naming, and access permissions.
- **Poison messages:** Invalid schemas go to quarantine/DLQ with an owner, never infinite network retries.

### 8.3. Stripping metadata that should not propagate

Do not forward:

- Internal authentication headers or source broker credentials.
- `replyTo`/temporary destinations unusable in the target broker.
- JVM-specific object headers.
- Debug stack traces or raw sensitive payloads.
- Source delivery tags or consumer session objects.

Replace with standardized business correlation, provenance, and schema metadata.

## 9. Delivery Guarantees: What Promises Are Realistic?

Three common levels:

| Level | Business meaning | Trade-off |
| --- | --- | --- |
| **At-most-once** | Messages may be lost, while avoiding re-sends | Avoids duplicates by accepting potential loss |
| **At-least-once** | May re-send when confirmation is uncertain | Requires idempotent consumers |
| **Exactly-once effect** | One business operation yields one final effect | Requires explicit scoped guarantees, unique keys/transactions, or end-to-end contracts |

**Important:** Never claim “JMS → RabbitMQ/Kafka exactly-once” merely because each broker individually supports transactions or acknowledgments. Across **two distinct brokers**, there is usually no shared atomic commit out of the box.

### 9.1. Source ACK vs. target publish confirm

A bridge tracks two distinct signals:

- **Source ACK/commit:** Does Broker A still hold responsibility to redeliver?
- **Target publish confirm/commit:** Did Broker B persist the message per producer guarantee settings?

Source ACK **before** durable target handoff risks losing messages. Durable target receipt **before** source ACK risks crash-induced redelivery and **duplicates** at the target.

### 9.2. Confirmation is not consumer business success

Rabbit publisher confirms or Kafka producer acks only prove the broker/partition leader (and replicas per policy) accepted the publish per contract. They **do not** prove a consumer updated its database or sent an email.

If business requires final confirmation, build explicit **replies/events/correlation or workflow orchestration**—never conflate publisher confirmations with business completion.

## 10. Critical Crash Windows Table

| Crash timing | Possible outcome | Required action |
| --- | --- | --- |
| Before consuming | Message remains at source | Re-read normally |
| After consume, before persist/target publish | No copy at target yet | Never ACK source before safe handoff |
| After target publish, before confirm | Target **may** have received it | Mark `OUTCOME_UNKNOWN`; use idempotency/reconciliation |
| After target confirm, before source ACK | Source redelivers → duplicate at target | Keep stable event ID for dedupe |
| After source ACK, before audit/outbox write | Bridge state uncertain | Design durable state/correlation or reconcile |
| After outbox persist, before source ACK | Source may redeliver while outbox exists | Unique inbox key/upsert; ACK after verify |
| After target confirm, before marking outbox `SENT` | Outbox worker may republish | Idempotent destination/consumer |
| While moving to DLQ | Failure record may not be saved | Never fake success; retain at source or fallback store |

### 10.1. “Publish method returned” is a weak condition

`RabbitTemplate.convertAndSend(...)` or `KafkaTemplate.send(...)` return per their own semantics. In Kafka, `send` is typically **asynchronous**, requiring inspection of completion/futures; in RabbitMQ, publisher confirms arrive separately and publishing to an exchange does not guarantee reaching a queue if bindings are wrong.

Bridge tests must use **broker integration tests**, observing confirms/returns and verifying records arrive at the target rather than just mocking `verify(send)`.

## 11. Design A: Direct Bridge

~~~text
Source broker -> Spring Integration handler -> Target broker
     |                                        |
     +----------- ACK/rollback policy <-------+
~~~

**Pros:** Fewer components, low latency, straightforward for moderate throughput.  
**Cons:** Holds source consumers/threads during target I/O; lacks atomic cross-broker commits; target outages spike unacked counts, redeliveries, and backlogs.

Required conditions:

1. Source consumer transaction/ack behavior is empirically verified.
2. Target publish enforces confirmations and proper timeouts.
3. If target publish fails to meet guarantees, source **does not ACK** or stores failure **durably before ACK**.
4. Target consumers are idempotent, as duplicates can still happen.
5. Bounded retries, backoff, and DLQ/quarantine are defined.
6. Never use an async in-memory channel as a “safe handoff” boundary.

### 11.1. When is a direct bridge sufficient?

When throughput is moderate, outages are tolerable, the source broker safely buffers/redelivers, messages aren't ultra-sensitive, and **duplicates are handled per contract**. Never pick it solely for shorter DSL code.

### 11.2. If the target broker disconnects

A safe reaction is **backpressure or letting the source retain messages**, rather than consuming/ACKing everything into an in-memory queue. Depending on SLAs, switch to a durable buffer or outbox so the source isn't blocked indefinitely.

## 12. Design B: Inbox/Outbox for Durable Handoff

A bridge that must tolerate either broker being unavailable independently can persist **a message copy and delivery state** in a durable intermediary store.

~~~mermaid
flowchart TD
    A["Broker A"] --> CON["Inbound consumer"]
    CON --> TX["DB transaction"]
    TX --> I["Inbox: unique source/business ID"]
    TX --> O["Outbox: PENDING target delivery"]
    O --> WORK["Outbox publisher / poller"]
    WORK --> B["Broker B"]
    B --> CONF["Broker confirmation"]
    CONF --> MARK["Mark outbox SENT"]
    I -.-> ACK["ACK source after durable handoff"]
    ACK --> A
    MARK --> AUD["Metrics, audit, reconciliation"]
    WORK -->|Failure| WAIT["Backoff / retry / DLQ alert"]
    WAIT --> WORK
~~~

**Important:** Commit races between source broker and DB still exist without distributed transactions. Implementations typically **commit the DB first and then ACK source**, accepting redeliveries and using **unique inbox keys** to avoid duplicate outbox rows. This prevents message loss across common crash windows while still needing concrete transaction/ack tests.

### 12.1. Minimal states

~~~text
Inbound:
    NEW -> DURABLY_ACCEPTED -> SOURCE_ACKED

Outbound:
    PENDING -> IN_FLIGHT -> SENT
                     \-> RETRY_PENDING
                     \-> OUTCOME_UNKNOWN
                     \-> QUARANTINED
~~~

Never mark `SENT` just because the worker called the producer or received an incomplete `send` future.

### 12.2. What do inbox and outbox solve?

- **Inbox:** Deduplicates source redeliveries via stable IDs, preventing duplicate outbox rows.
- **Outbox:** Preserves target publish responsibility after source ACK, surviving restarts.
- **Publisher worker:** Owns independent backoff, rate limits, state, and retries.
- **Correlation:** Links source message → outbox row → target record.

Inbox/outbox **do not automatically create target-side exactly-once effects**. If the target received a message before the outbox updated state, the worker may republish; target consumers still need idempotency.

### 12.3. Illustrative SQL schema

~~~sql
-- General illustrative model, not a built-in Spring Integration schema.
CREATE TABLE bridge_inbox (
    source_system      VARCHAR(120) NOT NULL,
    source_event_id    VARCHAR(220) NOT NULL,
    payload_hash       VARCHAR(128) NOT NULL,
    received_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (source_system, source_event_id)
);

CREATE TABLE bridge_outbox (
    outbox_id          VARCHAR(120) PRIMARY KEY,
    source_system      VARCHAR(120) NOT NULL,
    source_event_id    VARCHAR(220) NOT NULL,
    target_system      VARCHAR(120) NOT NULL,
    destination        VARCHAR(220) NOT NULL,
    status             VARCHAR(40) NOT NULL,
    attempts           INT NOT NULL,
    last_error_code    VARCHAR(120),
    payload_reference  VARCHAR(400) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    UNIQUE (source_system, source_event_id, target_system)
);
~~~

When an event targets multiple destinations, unique keys must include the **destination/consumer contract** if one target system has multiple routes. Real deployments also need appropriate indexes, locks/leases, isolation levels, and cleanup.

### 12.4. When does the source ACK?

~~~text
1. Receive message from broker A.
2. Validate identity/contract and operation key.
3. Inside one DB transaction:
       insert inbox row if absent;
       insert corresponding outbox rows if event is new.
4. Commit DB successfully.
5. Allow source ACK per listener/container configuration.
6. Outbox worker publishes to broker B and awaits confirmation.
7. Mark SENT only upon verified outcome per policy.
~~~

If the app crashes between steps 4 and 5, broker A redelivers; the unique inbox blocks creating duplicate outbox rows. If it crashes after target publish before step 7, the outbox worker may republish; the target consumer deduplicates via the same event ID.

## 13. When to Use Spring Integration vs. Broker-Native Connectors?

Not every broker-to-broker problem warrants a custom Java application.

| Option | Strengths | Limitations |
| --- | --- | --- |
| **Spring Integration adapters** | Full control over transforms, routing, filtering, retries, contracts, and business validation; multi-system integration | App owns state, scaling, monitoring, and failure handling |
| **Kafka Connect + suited connector** | Framework-managed source/sink connectors, offsets, and tasks | Capabilities/semantics vary by connector; heavy transforms fit poorly |
| **RabbitMQ federation/shovel** | Broker-managed forwarding with minimal custom code | No business transforms, schema governance, or cross-broker atomicity |
| **JMS provider bridge / network connector** | Fits single-vendor ecosystems | Provider-dependent semantics and vendor lock-in |
| **CDC/outbox pipeline** | Emits events directly from committed DB state | Requires schema design, ordering, idempotent consumers, and ops |

If you only need byte-identical event forwarding between brokers with strong native connectors, broker-native tooling can be simpler. If you need **contract validation, data cleansing, tenant routing, error orchestration, and HTTP/SFTP/JDBC integration**, Spring Integration models flows cleanly with `MessageChannel` and endpoints.

### 13.1. Selection criteria

1. Are **business schema changes** or complex routing required?
2. Do brokers A/B offer well-supported, operationally stable connectors?
3. Who owns source offsets, producer confirms, and DLQs?
4. Are DB inbox/outbox tables or reconciliation needed?
5. What are the throughput and latency budgets?
6. Are there multi-tenant, sensitive data, or encryption requirements?
7. Can ops monitor native connectors better than a custom integration service?

Never judge by line count alone. A low-code connector lacking traceability or failure control can cost far more in operations.

## 14. Source ACK/Transactions and Target Producer Confirmations

### 14.1. JMS source

With a JMS message-driven inbound adapter, redelivery depends on the **listener container** and JMS session: transacted sessions, client ack, auto ack, error propagation, and provider redelivery settings.

Often **container transactions** let exceptions roll back source delivery. Still, test:

- Do handler exceptions propagate to the listener container?
- Does any error/recovery callback **swallow exceptions**, causing the listener to finish normally?
- Is the container truly using transacted sessions rather than auto-ack?
- Does the message stay/redeliver at source when target publish fails?
- How do connection drops between source ACK and target confirm behave?

A bridge cannot claim JMS redelivers on error without testing **actual container configuration and provider behavior**.

### 14.2. RabbitMQ source and target

**Source side:** Consumer ACK/NACK/reject/requeue determines whether RabbitMQ redelivers or routes to DLX per topology.  
**Target side:** Publisher confirms verify broker receipt per mode; **publisher returns** catch **unroutable** messages when `mandatory` and return callbacks are configured.

| Event | What to verify |
| --- | --- |
| Source `basic.ack` | Does the source queue stop holding the delivery? |
| `basic.nack`/reject without requeue | Does DLX route to DLQ as expected? |
| Target producer return | When an exchange cannot route, does the bridge treat it as a failure? |
| Target publisher confirm | Are publish ACK/NACKs observed per contract? |
| Durable target queue | Do messages survive broker restarts per persistence config? |

**Publisher confirm ACK does not prove a business consumer processed the message**, and failing to inspect unroutable returns can silently drop routing errors.

### 14.3. Kafka source and target

**Source side:** Kafka consumers track offsets per group; the bridge decides at which target/durable-store milestone offsets commit.  
**Target side:** `KafkaTemplate.send(...)` returns completion results/failures; `acks`, retries, idempotent producer, and replication settings shape guarantees.

~~~text
Kafka source record (topic=orders, partition=2, offset=105)
    -> bridge
    -> target broker publish
    -> target confirmation / durable outbox
    -> source offset commit per policy
~~~

**Source offset 105 is not the target offset.** If the target is also Kafka, the producer picks partitions by key and assigns fresh offsets. Preserve `eventId` and `aggregateId` for contract dedup/ordering.

### 14.4. No default XA across heterogeneous brokers

An app can configure transaction managers for JMS or local DBs, and Kafka has transactional producers. Yet **enabling two transaction managers** does not create **one atomic transaction spanning JMS + RabbitMQ + Kafka**.

Options:

- Accept **at-least-once**, idempotent targets, and source rollback/redelivery.
- Use **inbox/outbox** as a durable handoff.
- In ecosystems supporting distributed transactions, evaluate XA/JTA specifically for your products, overhead, and failure modes—never assume universal cross-broker support.

In most modern service integrations, **business idempotency and reconciliation** remain essential even when source/target support transactional features.

## 15. Kafka → RabbitMQ Bridge Example: Offset Boundaries

Suppose Kafka holds topic `billing.events` while legacy services consume notifications from RabbitMQ.

~~~text
Kafka inbound adapter (consumer group bridge-v1)
   -> parse/validate canonical event
   -> transform payload + AMQP headers
   -> Rabbit outbound publisher
   -> confirm result
   -> Kafka offset commit per safe config
~~~

### 15.1. Broker-neutral pseudocode

~~~text
onKafkaRecord(record):
    event = validateAndNormalize(record)
    key = event.stableEventId

    if directBridgeMode:
        targetResult = publishToRabbitWithConfirmation(event)
        if targetResult.confirmedAndRouted:
            commitSourceOffsetWhenSafe(record)
        else:
            propagateFailureToContainer(record)

    if durableHandoffMode:
        durableStore.insertInboxAndOutboxAtomicallyIfNew(key, event)
        commitSourceOffsetWhenSafe(record)
        // Outbox worker publishes later, decoupled from source consumer.
~~~

The pseudocode emphasizes **responsibility ordering**, not Spring Kafka/Rabbit APIs. Producer confirms may arrive via async callbacks; if a direct bridge waits for results, configure timeouts and backpressure. With an outbox, source offsets commit only **after durable handoff** is confirmed.

### 15.2. Kafka DLT differs from RabbitMQ DLQ

When a source Kafka record fails parsing, route it to **Kafka DLT/quarantine** per container error handling. When RabbitMQ publishing fails, retry or save to the **bridge failure store** rather than pushing messages back onto the source topic with a brand-new idempotency key.

Once a message is durably stored in the outbox and RabbitMQ publishing later fails, retries belong to the **outbox worker**, not re-running the entire Kafka consumer unnecessarily.

### 15.3. Bridge Kafka consumer group

Manage Group IDs carefully:

- Changing `group.id` on deploy can re-read history depending on `auto.offset.reset`.
- Adding partitions alters record distribution; ordering holds only within one partition.
- Rebalances or restarts risk redeliveries for uncommitted offsets.
- Multiple pods in one group share partitions; extra pods do not boost throughput if partitions are scarce.
- Deduplication must survive deploys rather than relying on fresh Spring Message IDs.

## 16. Ordering, Partitions, and Routing Keys

**Ordering** is easily lost when crossing brokers. A single sequential consumer on a JMS queue does not keep order if target RabbitMQ runs concurrent consumers. Kafka preserves order **per partition**, not topic-wide.

### 16.1. Per-aggregate ordering

For order events:

~~~text
Event E1: order ORD-971 CREATED
Event E2: order ORD-971 PAID
Event E3: order ORD-971 SHIPPED
~~~

If a concurrent bridge publishes E3 before E2, target consumers observe out-of-order events. Determine:

1. Is ordering **global**, **per-tenant**, or **per-aggregate**?
2. Does the source guarantee ordering?
3. Does the bridge introduce `ExecutorChannel`/concurrency that scrambles order?
4. Do target Kafka keys/partitioning keep the same aggregate on one partition?
5. Do target RabbitMQ consumers process sequentially per aggregate?
6. Does retrying one message block later ones or allow overtaking?

### 16.2. Using stable keys for Kafka

For Kafka targets, `aggregateId` is typically a sound **record key** when per-aggregate ordering is needed. However:

- Empty keys scatter across partitions.
- Changing serializers or partitioners shifts aggregate-to-partition mappings across migrations.
- Changing partition counts alters key-to-partition hashing.
- Multiple producers emitting for one aggregate have no automatic business order without coordination.

Never claim “having a Kafka key guarantees end-to-end ordering” without checking producers, partitioning, and consumption.

### 16.3. Sequence numbers for gap detection

Event contracts can carry `aggregateVersion` or `sequenceNumber`. Target consumers check:

~~~text
lastAppliedVersion(ORD-971) = 4
received version 5 -> apply
received version 5 again -> duplicate, skip
received version 7 -> gap, wait/quarantine/reconcile
received version 3 -> stale, skip per business policy
~~~

This is business state—never derive it from target Kafka offsets or RabbitMQ delivery tags. If version 7 arrives before version 6, skipping version 6 simply because “last seen = 7” can drop valid work.

## 17. Idempotent Receiver at Target and Duplicate Suppression at Bridge

Bridges can be forced to republish messages when target confirms are ambiguous. Build **idempotency** on both sides:

| Layer | What it can do | Limitation |
| --- | --- | --- |
| Source record ID | Detects identical delivery/record | Republishing same event produces a new ID |
| Bridge inbox | Prevents duplicate outbox rows for one event | Does not control all target side effects |
| Bridge outbox | Durable retries using the same event key | Republishes can still reach the target |
| Target broker dedup | Broker-specific if supported | Does not automatically dedupe business logic |
| Target consumer inbox | Ensures operations apply once per key | Needs transactions/unique constraints with business effect |
| Downstream HTTP API | Uses idempotency keys per API contract | Must handle lost responses/unknown outcomes |

### 17.1. Which key to choose?

~~~text
Do not use:
    a fresh bridge-delivery-UUID per attempt

Use:
    sourceSystem + stableEventId + destinationContract

Example:
    legacy-jms:evt-T42-971-1:rabbit-orders-v2
~~~

`destinationContract` separates deliveries to distinct valid consumers/targets. If one event fans out to two targets, each target tracks independent delivery state.

### 17.2. Same key, different payload?

If the inbox already holds `evt-T42-971-1` and a later message changes amount/status, never silently drop it as a duplicate. Store a **payload fingerprint** to catch **key collisions or upstream contract violations** and route to investigation/conflict queues.

### 17.3. Is `MetadataStoreSelector` enough?

Spring Integration's `MetadataStoreSelector` and `IdempotentReceiverInterceptor` detect previously seen keys. However, **marking seen before business commit** risks losing messages on crashes. For durable bridges, consider **transactional inbox/outbox** or coordinating markers with real business state.

## 18. Retry Policies: Transient, Permanent, and Unknown Outcome

| Failure | Example | Usually suitable policy |
| --- | --- | --- |
| **Transient target unavailable** | Rabbit connection reset, Kafka leader failover | Bounded retry, backoff/jitter, and circuit breaker |
| **Backpressure/overload** | Broker flow control, quotas/throttling | Lower concurrency/rate, durable buffering |
| **Permanent schema invalid** | Missing required field, incompatible version | Quarantine/DLQ; no infinite retries |
| **Unauthorized publish** | Wrong ACL/credentials/TLS | Halt/alert, fix config; controlled retry |
| **Unroutable Rabbit message** | Bad binding/routing key | Inspect publisher returns/topology; never treat as success |
| **Oversized payload** | Exceeds broker message size limit | Reject or switch to payload reference per contract |
| **Publish confirm timeout** | Unclear if broker accepted | `OUTCOME_UNKNOWN`; retry with exact same event ID |
| **Source transaction failure** | JMS session commit or Kafka offset commit fails | Accept redelivery; rely on inbox/idempotency |
| **Business conflict** | Same event ID with differing payload | Investigate contract; never auto-mutate events |

### 18.1. Bounded retries and backoff

A bridge must cap attempts **per failure domain**. If Rabbit publisher retries 3 times, Spring Integration handler advice retries 3 times, and source broker redelivers 5 times, total publish attempts can hit **45**—before SDK auto-retries.

Never stack three independent retry layers while looking only at one layer's `maxAttempts`.

### 18.2. When is dead-lettering needed?

- **Permanent invalid:** Quarantine promptly, keeping references and schema versions.
- **Transient exhausted:** Write a durable failure record or keep source redelivery active per runbook.
- **Outcome unknown:** Reconcile before blind replay.
- **No owner:** Escalate; never let DLQs grow unchecked with nobody triaging.

### 18.3. Circuit breakers and pausing intake

During prolonged target broker outages, source consumers can get stuck in retry loops. Combine:

- Concurrency and in-flight caps.
- Rate limiters/backoff with jitter where appropriate.
- Pausing/resuming containers per runbook.
- Handing off to durable outboxes if source consumption must continue.
- Alerting on source backlog and outbox **age**, not count alone.

## 19. `ErrorMessage`, `errorChannel`, and Dead-Lettering in Spring Integration

Spring Messaging's **`ErrorMessage`** carries a `Throwable` payload. Spring Integration provides a global `errorChannel` and supports `errorChannel` headers in eligible error paths.

However:

- A `DirectChannel` handler throwing synchronously can **propagate errors straight to the caller** rather than publishing a global `ErrorMessage`.
- Pollers or async endpoints can use `MessagePublishingErrorHandler` to emit `ErrorMessage`.
- `RequestHandlerRetryAdvice` uses `RecoveryCallback` once retries exhaust.
- `ErrorMessageSendingRecoverer` sends `ErrorMessage` to a configured channel; it **does not automatically publish to a broker DLQ**.

### 19.1. Suggested error route

~~~mermaid
flowchart TD
    H["Broker bridge outbound handler"] --> F{"Publish failed?"}
    F -->|No| OK["Delivery state success per confirmation contract"]
    F -->|Yes| R["Bounded retry"]
    R --> EX{"Exhausted / permanent?"}
    EX -->|No| H
    EX -->|Yes| ERR["RecoveryCallback / ErrorMessage"]
    ERR --> CLASS["Classify failure"]
    CLASS -->|Invalid schema| Q["Quarantine"]
    CLASS -->|Transient exhausted| DL["Durable DLQ/failure store"]
    CLASS -->|Unknown result| REC["Reconciliation queue"]
    Q --> AUD["Audit + owner"]
    DL --> AUD
    REC --> AUD
~~~

### 19.2. Recovery handlers can fail too

If DLQ publishing or failure-DB writes fail, never `catch Exception` and just log if that lets the source ACK without a durable copy.

Designs need a **hard stop**:

~~~text
Target publish failed
  -> recovery store persist failed
  -> propagate error / keep source responsibility / pause intake
  -> alert; never pretend the message recovered
~~~

With an outbox, **the outbox itself can act as the failure store**: messages remain `PENDING`/`RETRY_PENDING` for later attempts instead of copying into a broker DLQ right away.

### 19.3. Source DLQ and target DLQ are not interchangeable

| Failure location | Appropriate storage |
| --- | --- |
| Source payload fails parsing | Source-side quarantine/DLQ or durable failure store |
| Target publish fails persistently | Bridge outbox/recovery store or source redelivery |
| Target consumer processing fails | Target-side DLQ/DLT per consumer policy |
| Unknown publish confirmation | Reconciliation/bridge state using the same event ID |

An event can **reach the target broker** and still land in the target DLQ due to consumer business errors. Those are two separate failures, linked in audits by event ID.

## 20. Designing Dead-Letter Envelopes and Replay

### 20.1. Failure record

~~~json
{
  "failureId": "bridge-fail-20261123-012",
  "bridgeId": "legacy-jms-to-rabbit-v2",
  "source": {
    "broker": "jms",
    "destination": "legacy.orders",
    "sourceRecordRef": "JMS-message-reference"
  },
  "target": {
    "broker": "rabbitmq",
    "exchange": "orders.bridge",
    "routingKey": "orders.in"
  },
  "eventId": "evt-T42-971-1",
  "schemaVersion": 2,
  "correlationId": "trace-84021",
  "attemptsObserved": 3,
  "errorCategory": "TARGET_PUBLISH_TIMEOUT",
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "payloadReference": "encrypted-blob-ref:bridge/evt-T42-971-1",
  "owner": "integration-platform",
  "createdAt": "2026-11-23T08:05:00Z",
  "nextAction": "verify-target-before-republish"
}
~~~

This is an **illustrative business schema**, not an auto-generated `ErrorMessage` payload. Populate `attemptsObserved` from trusted counters or retry context; non-retryable errors may move to recovery after the first attempt.

### 20.2. Safe replay

Before replaying:

1. Confirm the root cause is resolved.
2. Query the target broker/downstream or durable reconciliation state when publish outcomes are uncertain.
3. Keep the **original `eventId`/business operation ID**; attach a separate `replayId`.
4. Never coerce old events into newer schemas without migration rules.
5. Cap replay batch counts and rates.
6. Record owner and approvals when touching production or sensitive data.
7. Verify target consumers do not produce duplicate side effects.
8. Mark resolved only with contract-compliant proof.

~~~text
Original eventId: evt-T42-971-1
Source delivery: JMS-msg-204
First bridge attempt: attempt-001
Dead-letter record: bridge-fail-012
Replay attempt: replay-022

Idempotency key sent to target remains: evt-T42-971-1
~~~

### 20.3. Preventing bidirectional loops

If both **A → B** and **B → A** bridges run, a message originating at A can bounce back to A and loop forever.

Contracts should include:

- Trusted `originSystem`/provenance, never blindly taken from untrusted parties.
- `bridgeRouteId`, `hopCount`, and max hop limits.
- Rules ignoring events already emitted by this bridge unless a genuinely new operation occurred.
- Deduplication by stable event ID + route.
- Never merge two bridges into full-duplex without explicit loop prevention.

## 21. Backpressure, Throughput, and Capacity Planning

If the source emits 10,000 messages/second while the target sustains 2,000, the bridge must manage backlog. Adding threads cannot speed up a slow target and worsens retry storms.

### 21.1. Choosing strategies

| Mechanism | When appropriate | Notes |
| --- | --- | --- |
| Lower consumer concurrency | Target broker overloaded | Watch source lag and SLAs |
| Bounded in-flight messages | Limits RAM and unconfirmed publishes | Use clear timeouts and signals |
| Bounded retries/backoff | Transient failures | Avoid stacking retry multipliers |
| Durable outbox buffer | Target down while source must keep draining | Monitor disk/DB size, retention, cleanup |
| Pause source listeners | Prolonged target outage without safe buffer | Source needs sufficient retention/queue capacity |
| Batching/compression | Cuts overhead for suitable payloads | Watch message size, ordering, and error granularity |
| Partition-aware processing | Preserves per-aggregate ordering while scaling | Never alter partitioners arbitrarily |

### 21.2. Approximate backlog math

~~~text
Input rate  = 10,000 events/second
Output rate =  2,000 events/second
Growth      =  8,000 events/second

After 5 minutes:
    8,000 x 300 = 2,400,000 backlogged events
~~~

This is an **illustrative calculation** before payload sizes, indexing overhead, retries, and replication. At 4 KiB average payload, raw data alone reaches ~9.2 GiB excluding metadata and replicas; build real capacity plans.

### 21.3. Never use in-memory `QueueChannel` as an unbounded buffer

In-memory queues exhaust RAM and lose messages when processes stop. Even with a persistently backed channel, verify **atomic handoffs and transaction/source ACKs**—never equate “persistent queue” with exactly-once.

## 22. Security and Trust Boundaries

A bridge sitting between two brokers often connects two security domains, making it a **sensitive chokepoint**.

### 22.1. Security principles

- **Least privilege:** Identities read only authorized source queues/topics and write only target destinations; never share broker admin credentials.
- **TLS and credential rotation:** Encrypt transport, verify server identities, never hardcode passwords in YAML/repositories.
- **Segregation:** Separate dev/staging/prod, tenants, data regions, and service accounts.
- **Payload validation:** Never trust unverified source headers/payloads, including `tenantId` or `routingKey`.
- **Header allowlists:** Strip tokens, credentials, broker-internal metadata, and debug headers.
- **PII minimization:** Forward only consumer-needed data; encrypt payload references in DLQs/outboxes.
- **ACLs:** Bridge operators should not automatically read every DLQ or alter schemas.
- **Auditing:** Log changes to topology, destination routing, roles, TLS, and connections.
- **Supply chain:** Govern third-party transform/serializer libraries and untrusted input parsing.

### 22.2. Preventing cross-tenant routing

~~~text
Unsafe:
    routingKey = rawMessage.header("tenantDestination")

Safer:
    tenant = authenticateOrValidateTenant(sourceContext, payload)
    routingKey = approvedRoutingTable.lookup(tenant, eventType)
    verifyACL(destination, tenant)
~~~

This pseudocode illustrates boundary protection; `approvedRoutingTable` and `verifyACL` are supplied by application governance.

### 22.3. Avoid logging raw payloads

In error flows, an `ErrorMessage` can wrap failed/original messages holding sensitive payloads. Never dump full `Throwable` and `Message.toString()` to logs unredacted. Safe **event ID, correlation ID, exception category, destination, and payload reference** usually suffice for initial triage.

## 23. Connection Lifecycles and Shutdown

A bridge holds **two connection sets**: source consumers and target publishers. Startup, recovery, and shutdown must account for both sides.

### 23.1. Startup

1. Verify source and target connections, certificates/credentials, and network/TLS.
2. Initialize required topology or verify queues/exchanges/topics exist.
3. Start health/metrics and failure stores/outboxes.
4. If direct bridge requires target readiness, verify target publisher health before opening source intake.
5. Start listeners/pollers with bounded initial concurrency if needed.

**Note:** Never treat `connection opened` as proof of ACLs to consume/publish on real destinations; verify permissions in authorized test environments.

### 23.2. Controlled shutdown

~~~text
Stop accepting new source deliveries
  -> drain/stop in-flight handlers within deadline
  -> confirm/persist pending target publishes
  -> ACK source or leave for redelivery per policy
  -> checkpoint/flush durable state
  -> close producer/consumer connections
~~~

If the shutdown deadline expires before publisher confirms arrive, messages must **stay at source or in durable buffers** per design. Never mark deliveries `SENT` pre-confirm just to shut down faster.

### 23.3. Connection flapping

When the target reconnects repeatedly, expect:

- Multiple in-flight publishes with unknown outcomes.
- Rising source backlogs and redeliveries.
- Repeated producer reconnect/backoff cycles.
- Consumer rebalances (Kafka) or listener restarts.
- Session/channel leaks and memory pressure.

Test reconnects to verify **zero resource leaks**, no reuse of stale broken connections, and no false duplicates from retries.

## 24. Observability: Seeing Where Each Message Is

When a bridge spans systems lacking shared transactions, **observability is essential for reconciliation**, not merely performance tuning.

### 24.1. Four states to distinguish

~~~text
RECEIVED:         Source broker delivered message to the bridge.
DURABLE_ACCEPTED: Bridge persisted durable responsibility (e.g., inbox/outbox).
TARGET_PUBLISHED: Target broker confirmed per chosen guarantee.
BUSINESS_APPLIED: Target consumer completed business logic.
~~~

Bridges usually directly verify only the first three; `BUSINESS_APPLIED` must come from **consumer business acks, reply events, or reconciliation**. Never mark business success from publisher confirms alone.

### 24.2. Suggested metrics

| Metric | Meaning |
| --- | --- |
| `bridge_source_received_total` | Total source messages received |
| `bridge_inbox_deduplicated_total` | Redeliveries caught by inbox |
| `bridge_outbox_pending` | Unfinished outbound records |
| `bridge_outbox_oldest_age_seconds` | Age of oldest record waiting on target |
| `bridge_publish_attempt_total` | Producer invocations including retries |
| `bridge_publish_confirm_total` | Confirmed target publishes |
| `bridge_publish_return_total` | Rabbit unroutable returns if configured |
| `bridge_publish_unknown_total` | Ambiguous publish outcomes |
| `bridge_retry_exhausted_total` | Retries exhausted per policy |
| `bridge_dead_letter_total` | Failures stored/published to DLQ |
| `bridge_replay_total` | Replay attempts (success/failure) |
| `bridge_source_lag` | JMS queue depth / Rabbit depth / Kafka lag at source |
| `bridge_target_lag` | Latency from source receipt to target confirmation |
| `bridge_duplicate_detected_total` | Repeated event IDs across source/replay |
| `bridge_contract_rejected_total` | Rejections from schema/version/tenant errors |
| `bridge_connection_recovery_total` | Reconnect counts per broker |

These are **application-suggested metric names**, not all emitted automatically by Spring Integration. Keep labels to bounded `flow`, `sourceBroker`, `targetBroker`, `errorCategory`, `environment`—never use per-message `eventId` as a label.

### 24.3. Structured logs

~~~json
{
  "event": "bridge.target.publish.unknown",
  "bridgeId": "jms-orders-to-rabbit-v2",
  "sourceBroker": "jms",
  "targetBroker": "rabbitmq",
  "sourceDestination": "legacy.orders",
  "targetDestination": "orders.bridge/orders.in",
  "eventId": "evt-T42-971-1",
  "correlationId": "trace-84021",
  "outboxId": "outbox-0042",
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "attemptsObserved": 2,
  "occurredAt": "2026-11-23T08:10:00Z"
}
~~~

Never log raw JMS properties containing credentials, AMQP Authorization headers, Kafka SASL secrets, sensitive file contents, or raw Spring Message payloads.

### 24.4. Cross-broker tracing

Traces can link:

~~~text
Source consume span
  -> contract normalize span
  -> durable handoff span
  -> target publish span
  -> target consumer span (if propagated)
~~~

Trace contexts may expire across long retention or replays. Durable **`eventId`/`correlationId`** remain mandatory rather than replacing them with per-attempt trace/span IDs.

## 25. Layered Bridge Testing

A strong test suite separates layers so you know **exactly which guarantee was verified**.

| Layer | What is verified | Suitable tools |
| --- | --- | --- |
| **Unit** | Canonical event mapping, routing, keys, validation | JUnit 5, Mockito, AssertJ |
| **Spring Integration component** | Adapter → channel → transformer → handler/error route | Spring Integration Test, mock handlers/sources, `QueueChannel` |
| **Broker integration** | JMS transactions, Rabbit confirms/returns, Kafka offsets/DLT | Testcontainers / embedded brokers as needed |
| **Durability integration** | Inbox/outbox DB commits, uniqueness, outbox retries | Disposable databases, transaction tests |
| **Failure injection** | Crashes post-publish, pre-ACK/mark SENT, target outages | Staging/containers with network faults/restarts |
| **End-to-end** | Messages reach target and consumers apply business state | Test environments simulating both domains |

### 25.1. Tests must not claim beyond their scope

Example unit test:

~~~java
verify(rabbitTemplate).convertAndSend(
        eq("orders.bridge"),
        eq("orders.in"),
        any());
~~~

This only proves **the method was called**—not that the broker received it, the exchange routed to a queue, confirms arrived, consumers processed it, or source JMS committed properly.

### 25.2. Broker integration assertions

For JMS → RabbitMQ:

1. Send a fixture message to the test JMS queue.
2. Start the message-driven inbound adapter against test RabbitMQ topology.
3. Await the message in the target Rabbit queue with bounded timeout.
4. Assert payload/schema, `eventId`, `correlationId`, routing, and allowed headers.
5. Make the Rabbit target unroutable or fail publish: verify error/recovery behavior.
6. Verify source JMS redelivery/ACK or outbox handoff under real configs.
7. Restart the bridge before ACK; verify zero lost events and contract-compliant duplicate handling.

For Kafka → JMS:

1. Produce a Kafka record with defined key/partition/offset.
2. Bridge consumes via a test consumer group.
3. Send to test JMS queue and verify arrival.
4. Stop the JMS broker during publish; verify source offsets do not commit before durable handoff.
5. Restart and verify redeliveries create no duplicate business side effects.

### 25.3. Failure injection matrix

| Failure point | Assertion target |
| --- | --- |
| Source connection drops before receive | No false receipt reported |
| Source receives, target is down | Message stays at source or in durable buffer |
| Target publish succeeds, confirm lost | `UNKNOWN`; retries with identical event ID |
| Confirm succeeds, source ACK fails | Redelivery; target consumer idempotent |
| DB inbox commits, source ACK fails | Unique inbox blocks duplicate outbox rows |
| Outbox publishes, mark SENT fails | Worker retry produces no business duplicates |
| Schema invalid | Fast quarantine; no infinite connection retries |
| Rabbit exchange unroutable | Publisher return treated as failure |
| Kafka DLT publish fails | Never falsely marks record `RECOVERED` |
| Target queue full/quota exceeded | Backpressure, safe source retention |
| App shuts down with in-flight message | Never ACKs prior to handoff or confirm |
| Two concurrent bridge instances | Unique keys/locking/safe partition handling |
| Source republishes event with new transport ID | Business dedup still catches it |
| Replay after target outage | Original event ID preserved; proper owner/audit |
| Misconfigured routing rule | Alert and quarantine; no cross-tenant leak |

### 25.4. Testing failures between two transactions

One critical case:

~~~text
1. Outbox worker publishes evt-T42-971-1 to Rabbit.
2. Rabbit broker ACKs publisher confirm.
3. Bridge process crashes before marking outbox row SENT.
4. Bridge restarts; worker publishes same event again.

Expected:
    Rabbit may receive two deliveries.
    Both carry the same stable eventId.
    Target consumer applies business effect once.
    Outbox eventually reaches reconciled SENT state.
~~~

If a test asserts “Rabbit receives exactly one message” and turns red on two, it demands a guarantee **alien to at-least-once architectures**. Assert **idempotent business outcomes** while measuring duplicates for tuning.

## 26. Hands-On Example: JMS to RabbitMQ via Outbox

Suppose **Learning Orders** wants events moved from JMS queue `legacy.orders` to RabbitMQ exchange `learning.events`. The team picks an outbox to decouple the two broker lifecycles.

### 26.1. Defining the contract

~~~yaml
# Illustrative contract, not auto-generated Spring Integration config.
bridgeId: legacy-jms-to-rabbit-v2
source:
  protocol: jms
  destination: legacy.orders
target:
  protocol: amqp
  exchange: learning.events
  routingKey: order.created.v2
message:
  eventIdField: eventId
  aggregateIdField: orderId
  schemaVersion: 2
  payloadFormat: json
delivery:
  expectedGuarantee: at-least-once
  durableHandoff: jdbc-inbox-outbox
  confirmRequired: true
  targetConsumerIdempotency: required
errorHandling:
  invalidContract: quarantine
  transientPublishFailure: retry-with-backoff
  unknownConfirm: reconcile-and-retry-same-event-id
security:
  headerAllowlist:
    - eventId
    - correlationId
    - schemaVersion
~~~

### 26.2. Phase 1 — Ingest into inbox/outbox

~~~text
JMS inbound receives message M.

validate/M -> canonical event E.
sourceKey = (sourceSystem, E.eventId).
payloadHash = fingerprint(E).

DB transaction:
    if sourceKey absent:
        insert inbox(sourceKey, payloadHash).
        insert outbox(E, targetRoute, status=PENDING).
    else:
        verify payloadHash matches; do not insert duplicate.
commit DB.

Only after durable commit:
    allow JMS session/container to complete according to
    configured transaction and acknowledgment semantics.
~~~

**Limitation:** This is **business pseudocode**, not an XA transaction. If the DB commits while the JMS session fails to commit, JMS redelivery is absorbed by the unique key. If JMS ACKs before the DB commits, events risk loss; hence test real listener/container behavior.

### 26.3. Phase 2 — Publish to RabbitMQ

~~~text
Outbox worker claims a PENDING row with lease/version.
Build target payload + allowlisted AMQP headers.
Publish to learning.events with order.created.v2.
Wait for configured broker publish confirm.
Check mandatory return/unroutable policy.

If broker confirms and routing requirements pass:
    mark row SENT (with confirm metadata).
If confirmed NACK or known failure:
    mark RETRY_PENDING and schedule backoff.
If confirmation is lost/unknown:
    mark OUTCOME_UNKNOWN and retry/reconcile
    using the original eventId.
~~~

A **Rabbit publish return** and a **publisher confirm** are separate signals; handle callbacks/lifecycles per your `RabbitTemplate` and Spring AMQP version. Never use `Thread.sleep` to verify publish success.

### 26.4. Phase 3 — Target consumer

The Rabbit consumer receives the event with `eventId=evt-T42-971-1`, checks its unique business key in its own inbox, and commits the business effect alongside `COMPLETED` status if possible.

When the bridge replays the same event, the consumer can ACK already-`COMPLETED` duplicates without creating another order; for `PROCESSING`/`UNKNOWN` states, wait/reconcile instead of dropping messages blindly.

### 26.5. State transitions

~~~mermaid
stateDiagram-v2
    [*] --> Received
    Received --> DurableAccepted: Inbox/outbox DB commit
    DurableAccepted --> PendingPublish: Source ACK allowed
    PendingPublish --> InFlight: Worker claim
    InFlight --> Sent: Publish confirmed/routed
    InFlight --> RetryPending: Known failure
    InFlight --> Unknown: Confirm result unknown
    RetryPending --> InFlight: Retry bounded
    Unknown --> InFlight: Reconcile / resend with same eventId
    InFlight --> Quarantined: Permanent contract violation
    Sent --> [*]
    Quarantined --> [*]
~~~

This state machine is illustrative; in real systems `Unknown` may require manual intervention and `SENT` does not equal target business `COMPLETED`.

## 27. Migration Plan When Replacing a Broker in Production

Replacing a broker changes **contracts, traffic ownership, and failure modes**. Roll out in phases with clear rollbacks.

### 27.1. Phase 0 — Inventory

- List producers, consumers, queues/topics, consumer groups/subscriptions.
- Document schemas, message sizes, compression, partitioning, priorities, TTLs, and retention.
- Capture ordering, dedupe, DLQ, and business latency requirements.
- Measure baseline source rates, lag, retries, and payload distributions.
- Define business owners and cutover criteria.

### 27.2. Phase 1 — Shadow bridge

Forward messages to the target for **observation** without triggering live side effects from new consumers until safe procedures exist. Reconcile:

- Event counts by stable event IDs.
- Schemas and fingerprints.
- Timings/lag.
- Routing/ordering and missing records.
- Unknown/invalid contracts.

If a shadow consumer also calls external order-creation APIs, it is **no longer safe shadowing**. Disable side effects or use isolated test environments.

### 27.3. Phase 2 — Dual-read or controlled cutover

Strategies:

- **Strangler migration:** Move one consumer group at a time to the target.
- **Canary:** Shift one small tenant/partition/route first.
- **Dual-write/dual-publish:** Only if duplicates, ordering, and reconciliation are solved.
- **Replay/backfill:** Sync history by event ID without duplicating business effects.

**Dual-write** demands extreme care: an app publishing to two brokers can succeed on A and fail on B, creating split-brain history. Using outbox/CDC/bridges with durable state makes reconciliation far easier.

### 27.4. Phase 3 — Transferring ownership

Pin down exact timing for:

1. Which broker new producers write to as authoritative?
2. When old consumers stop executing side effects?
3. Does the bridge continue bidirectionally or one-way only?
4. How are late arrivals and remaining legacy backlog handled?
5. Which system owns replay/retention post-cutover?

Never shut down the bridge solely because a dashboard showed “queue depth = 0” at one instant; check in-flight messages, retries, pending outboxes, delay queues, and DLTs.

### 27.5. Rollback

Rollback plans require:

- Automatic or approver-gated halt conditions.
- Pausing new consumers without losing events.
- Resuming old consumers without replaying already-completed side effects.
- Mapping committed event IDs/offsets and outcomes.
- Handling newer incompatible schema changes against legacy systems.
- Audit records of who decided and final states.

## 28. Runbook When the Target Broker Is Unavailable

### 28.1. Symptoms

Target RabbitMQ returns publisher NACKs/connection timeouts; outbox pending climbs. Source JMS remains healthy and apps keep creating orders.

### 28.2. Diagnosis

1. Check target broker network/TLS/ACLs, exchange/queue bindings, quotas, and health.
2. Check producer client errors, confirms/returns, reconnects, and retry budgets.
3. Confirm whether the bridge runs in **direct** or **durable handoff** mode.
4. Check source queue depth/lag, in-flight/ACKs, and redeliveries.
5. Check outbox age, DB disk/CPU, connection pools, and lease contention.
6. Separate events in `PENDING`, `RETRY_PENDING`, `UNKNOWN`, and `SENT`.
7. Separate schema/routing failures from infrastructure outages—do not lump everything into “Rabbit down.”

### 28.3. Response

- Throttle source consumers or pause intake if buffers near capacity.
- Never delete backlogs or ACK just to make dashboards look green.
- Cap retries and raise backoff to avoid crushing the broker as it recovers.
- For unknown confirms, retry with the exact same event ID and watch duplicates.
- Fix auth/ACL or misrouting via change control rather than infinite retries.
- Prioritize high-SLA events per policy while avoiding unintended per-aggregate reordering.
- Never flush inbox/outbox tables “to free disk” without a recovery plan.

### 28.4. Post-recovery

1. Run canary publishes verifying real confirms and routing.
2. Ramp concurrency/rate gradually within target headroom.
3. Watch source lag and oldest outbox age together.
4. Reconcile source event IDs against target records.
5. Clear DLQs/quarantine and unknown outcomes.
6. Close the incident only once backlogs clear or remaining exceptions have owners/deadlines.
7. Document root cause, retry configs, session lifecycles, and regression tests.

## 29. Common Anti-Patterns

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Treating `BridgeHandler` as a broker connector | Fails to wire real sources/targets | Configure explicit inbound/outbound adapters |
| Pushing to in-memory `ExecutorChannel` and ACKing source | Crashes lose messages | Durable handoff or keep responsibility at source |
| Publishing to target without checking confirms | Unsure if broker accepted/routed | Publisher confirms/returns and verification |
| Treating source JMS transaction as wrapping Rabbit/Kafka | Illusion of cross-broker atomicity | Inbox/outbox + idempotency or proven TX solutions |
| Minting a new event ID on each retry | Target cannot deduplicate | Stable event ID + separate replay ID |
| Copying all JMS/AMQP/Kafka headers | Incompatible types, leaked creds, misrouting | Canonical envelope + allowlist |
| Dropping `replyTo`/correlation for request–reply | Callers hang or get wrong replies | Design gateway reply contracts |
| Confusing Rabbit exchanges with queues | Publish succeeds yet unroutable | Bindings + mandatory returns + tests |
| Using Kafka offset as business event ID | Republishing across topics breaks idempotency | Stable business event ID |
| Unbounded retry stacks | Retry storms, high latency | Bounded attempts/backoff/concurrency |
| Infinitely retrying invalid schemas | Poison messages clog queues | Permanent error → quarantine |
| Treating DLQs as business-resolved | Failures pile up endlessly | Owners, SLAs, reconciliation, and replay |
| Swallowing errors when archiving failures | Source ACKs without durable copy | Fail-safe handling and store-outage tests |
| Deleting pending outbox after source ACK | Loses delivery accountability | Retention, recovery, verified audits |
| One `forwarded=true` flag for multiple targets | Masks single-target failures | Per-target outbox status |
| Ignoring ordering | CREATED/PAID/SHIPPED arrive scrambled | Per-aggregate ordering + sequence/gap checks |
| Two-way bridges without loop guards | Messages bounce A↔B forever | Provenance/hop caps/route dedupe |
| Shadow traffic triggering live side effects | Duplicate orders/transactions | Shadow consumers skip business mutations |
| Stopping bridge at transient queue depth 0 | Misses in-flight, DLQ, or pending outbox | Cutover readiness and reconciliation |
| Copying raw payloads into logs and DLQs | PII/credential leaks | Redaction, encryption, scoped access |

## 30. Self-Check Exercises

### Exercise 1 — JMS ACK before Rabbit publish

**Scenario:** JMS listener receives an event, sends it to `ExecutorChannel`, and returns; the Rabbit publisher on another thread fails. JMS already ACKed.

**Answer:** Without durable handoffs, messages can be lost. Commit/ACK source only after broker confirmation or durable inbox/outbox persistence; verify container semantics.

### Exercise 2 — RabbitMQ confirm ACK yet empty queue

**Scenario:** Rabbit producer receives publisher confirm ACK while the consumer queue stays empty.

**Answer:** The publish likely hit an unroutable exchange/binding. Check `mandatory` returns, exchange/binding/routing keys, and distinguish broker confirm from queue delivery.

### Exercise 3 — Kafka offset copied to target

**Scenario:** Source Kafka offset 120 is attached to the target event and used as a dedup key after republishing.

**Answer:** Offsets identify physical records in one source partition/topic, not stable business event IDs across republishes. Use a stable `eventId`; keep offsets as provenance only.

### Exercise 4 — Outbox `SENT` updated late

**Scenario:** Publisher confirms target receipt, yet the process crashes before updating outbox row `SENT`.

**Answer:** On restart, the outbox worker may republish. Target consumers require idempotency on stable event IDs. Never infer exactly-once from two independent commits.

### Exercise 5 — Source is a command, target is an event

**Scenario:** Source sends `CREATE_ORDER` command; the bridge renames it to `ORDER_CREATED` and publishes before order creation succeeds.

**Answer:** Semantically broken. Fact events emit only after the corresponding result occurred/confirmed. Bridges must never turn commands into successful facts by renaming.

### Exercise 6 — Per-order ordering

**Scenario:** Target Kafka writes events with random keys; consumers can receive `SHIPPED` before `PAID` for the same order.

**Answer:** When business requires per-aggregate ordering, use matching key/partition strategies and consumer concurrency, optionally adding `aggregateVersion` and gap detection.

### Exercise 7 — Prolonged target downtime

**Scenario:** Source emits 10,000 events/s while target takes 2,000 events/s. The bridge buffers everything in an unbounded in-memory `QueueChannel`.

**Answer:** Backlog grows by 8,000 events/s, exhausting RAM and losing messages on restart. Use pause/backpressure or a capacity-planned durable outbox.

### Exercise 8 — Two bridges A → B and B → A

**Scenario:** An event repeatedly bounces back to its source system after crossing the bridge.

**Answer:** Require provenance, route identities, hop limits, and deduplication; never enable full-duplex without explicit loop-prevention policies.

### Exercise 9 — Failure store down

**Scenario:** Target publish fails, the error handler fails to write to DLQ, yet still returns normally so the source ACKs.

**Answer:** High risk of silent loss. Retain source responsibility or write to another durable buffer, propagate failures, and alert per design.

### Exercise 10 — Dual-read migration

**Scenario:** Both old and new consumers call the payment API when events are shadowed to the new broker.

**Answer:** Shadow traffic must never trigger duplicate business side effects. Shadow consumers must validate without committing business work, or rely on explicit business idempotency/cutover ownership.

## 31. Checklist for Building a Broker-to-Broker Bridge

1. **Choose pattern:** In-app bridge, native connector, or CDC/outbox matched to real needs.
2. **Clear scope:** Source/target brokers, queues/topics, subscriptions/groups, environments, and owners.
3. **Clear direction:** One-way A→B or bidirectional with loop guards.
4. **Clear contract:** Command vs. event, schema versions, payloads, event IDs, and encodings.
5. **Canonical headers:** Allowlists, correlation, causation, provenance, tenant mapping.
6. **No leaked internal metadata:** Strip credentials, delivery tags, session objects, and invalid `replyTo`.
7. **Source semantics:** JMS transactions, AMQP ACK/NACK, Kafka offset commits empirically tested.
8. **Target semantics:** Producer confirms/futures, unroutable returns, and durability verified.
9. **No XA illusions:** Crash windows and realistic guarantees explicitly designed.
10. **Durable handoffs:** When ACKing source before target publish, inbox/outbox or matching durable stores exist.
11. **Idempotency:** Stable event IDs across retries/redeliveries/replays; target consumers block duplicate side effects.
12. **Ordering:** Scoped per-aggregate/partition, concurrency aligned, gaps/out-of-order handled.
13. **Retry budgets:** Separate transient/permanent/unknown, bounded backoff, and rate limits.
14. **DLQ/quarantine:** Durable records, owners, retention, and authorized replay paths.
15. **Fail-safe error flows:** Recovery store outages never turn into false ACKs.
16. **Outbox states:** `PENDING`, `IN_FLIGHT`, `RETRY_PENDING`, `UNKNOWN`, `SENT` actively managed.
17. **Backpressure:** Concurrency caps and target-outage policies.
18. **Connection lifecycle:** Startup, reconnects, shutdown, drain, and credential rotation.
19. **Security:** TLS, least privilege, tenant routing, encryption, log redaction.
20. **Real source/target tests:** Broker publishes, ACKs/offsets, Rabbit routing, Kafka DLT, and JMS rollbacks.
21. **Failure injection:** Crash post-DB-commit/pre-ACK and post-target-confirm/pre-`SENT`.
22. **Migration plan:** Shadow/canary/cutover/rollback and event reconciliation.
23. **Observability:** Source lag, oldest outbox age, unknown outcomes, DLQs, and confirm latencies.
24. **Runbooks:** Who pauses intake, who replays, who approves, and when incidents close.

## 32. References

Consult official documentation and **verify against your exact dependency versions** during implementation:

1. **Spring Integration Reference — JMS Support**  
   https://docs.spring.io/spring-integration/reference/jms.html
2. **Spring Integration Reference — AMQP Support**  
   https://docs.spring.io/spring-integration/reference/amqp.html
3. **Spring Integration Reference — Kafka Support**  
   https://docs.spring.io/spring-integration/reference/kafka.html
4. **Spring Integration Reference — Message Channels**  
   https://docs.spring.io/spring-integration/reference/channel.html
5. **Spring Integration Reference — Error Handling**  
   https://docs.spring.io/spring-integration/reference/error-handling.html
6. **Spring Integration Reference — Idempotent Receiver**  
   https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
7. **Spring AMQP Reference — RabbitMQ messaging and template confirms**  
   https://docs.spring.io/spring-amqp/reference/amqp/template.html
8. **Spring Kafka Reference — Kafka template, listener and error handling**  
   https://docs.spring.io/spring-kafka/reference/

Class names, method overloads, transaction/publisher-confirm options, and container configurations in examples may vary across **Spring Integration, Spring AMQP, Spring Kafka, and Spring Boot** versions. Examples in this lesson are study material to adapt and validate against your project BOM; **no builds or broker integration tests were executed during authoring**.

## 33. Summary

A **bridge between two brokers** in Spring Integration combines **inbound adapters/gateways, `MessageChannel`, validation/transformation/routing, and outbound adapters** to transfer messages safely across heterogeneous messaging systems. `BridgeHandler` helps link internal channels, yet **never replaces** endpoint and protocol configuration for JMS, RabbitMQ, or Kafka.

The hardest part is not passing `Message<?>` from one channel to another—it is **preserving delivery accountability** when two brokers have separate transactions, acks, and confirmations. Source ACK before durable handoff risks message loss; target confirm before source ACK risks duplicates. A reliable bridge defines realistic delivery guarantees, preserves stable event IDs, enforces target-side idempotency, provides retries/DLQs/replays, and handles `OUTCOME_UNKNOWN`.

For critical flows, **inbox/outbox** decouples source and target lifecycles while still requiring downstream idempotency and crash-window testing. **Ordering, header mapping, schema versions, backpressure, security, connection lifecycles, and observability** must be designed together. Only when source handoff durability is proven, target publishes are contract-verified, and exceptions have owners/runbooks does a bridge truly support migration and cross-broker integration **without compromising business correctness**.
