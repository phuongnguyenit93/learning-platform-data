# Choosing an Exchange Model Based on Latency, Durability, and Business Requirements

## 1. Why Must You Choose an Exchange Model?

A system can exchange data in many ways: invoking a function directly, sending a request and waiting for a response, offloading work to background processing, broadcasting events to multiple receivers, or appending events to a stream for consumers to read and replay. These approaches differ in response time, coupling between components, fault tolerance, processing order, and operational cost.

No single model is best for every situation. An operation needing an immediate result to show the user usually fits request-response. A business event that must be processed even if the consumer is temporarily down usually requires a queue or broker with durable storage. An event stream needing multiple independent consumers and historical replay may fit a streaming platform.

In Spring, two decision layers should be distinguished:

- **Business model:** command, query, request-reply, event notification, work queue, or event stream.
- **Transport mechanism:** in-process call, Spring application event, message channel, HTTP, WebSocket/STOMP, JMS, RabbitMQ, Kafka, or another broker.

Spring Messaging provides abstractions such as `Message`, `MessageHeaders`, `MessageChannel`, and `MessageHandler`. These abstractions standardize messages and send/receive points; a `Message` or `MessageChannel` by itself does not guarantee that data will be durably stored, delivered once, or processed asynchronously. Those guarantees come from the implementation, broker, configuration, and business logic.

## 2. Starting from Business Requirements

Before choosing technology, establish what must hold true for the business:

1. Does the caller need an immediate result to decide the next step?
2. If the receiving process stops for a few minutes, can messages be lost?
3. Should a message be processed by one consumer or received by multiple independent consumers?
4. Must ordering be preserved between messages? Globally across the system, or only per order/account?
5. Can a request be reprocessed? If processed twice, would it create duplicate orders, double-charge, or send duplicate notifications?
6. Will volume spike sharply? How must the system rate-limit, queue, or apply backpressure?
7. How long must history be retained, who emitted an event, and from what point must replay start?
8. What maximum wait time and consistency level are acceptable?

Turn the answers into measurable criteria. For instance, an API may have a p95 response budget under 200 ms; an invoice update flow may tolerate a few seconds of delay but cannot lose confirmed events; a UI notification may tolerate loss if the user has already left the page.

Do not apply one fixed latency threshold to every system. Define p50/p95/p99 budgets, timeouts, expected throughput, message size, consumer count, and retention periods based on real workload.

## 3. Main Exchange Models

### 3.1. Synchronous Calls and Request-Response

The caller sends a request and waits for the result within the same interaction flow. This model fits when the result is a precondition to continue: permission checks, data validation, instant pricing, or querying data to display.

**Strengths:** straightforward control flow; errors and results are returned directly; fits operations requiring immediate confirmation.

**Limitations:** response time depends on downstream services; caller and callee impact each other when one side is slow; a caller timeout does not automatically cancel work already running on the server; retrying a request can cause duplicate actions without idempotency.

In a Spring application, calling a method/service directly in the same process is usually simplest. Across service boundaries, HTTP request-response is a common choice. Messaging request-reply can be used when the system already runs a broker and needs message routing, but you must define correlation IDs, reply destinations, timeouts, late-reply handling, and behavior when no consumer is present.

Choose this model when:

- The user or business logic needs to act on an immediate result.
- The operation has predictable processing time and a sensible timeout.
- Dependencies can be controlled and services protected from overly deep synchronous call chains.

Avoid deep chains of synchronous requests across many services for a critical transaction. One slow service can stall the entire path, exhaust connection/thread pools, and trigger cascading failures.

### 3.2. In-Process Asynchronous Processing

The sender hands work off to an executor, channel, or event listener and continues processing. The consumer may run on another thread, yet still belongs to the same application and deployment lifecycle.

In Spring Framework, `ApplicationEventPublisher` supports publishing application events within the same application. `SimpleApplicationEventMulticaster` invokes listeners synchronously by default; configuring an executor can make listeners run asynchronously. Therefore, never assume simply publishing an event automatically runs work in the background.

**Strengths:** reduces caller wait time; no separate broker to operate; fits auxiliary tasks that can be lost on process shutdown if business requirements allow.

**Limitations:** memory and thread pools are bounded by the application instance; events are not durably persisted automatically; restarts or crashes can lose pending work; scaling out instances does not automatically create a reliable shared queue.

Choose this model for tasks like updating a local cache, writing non-critical telemetry, or regenerable post-processing work. Do not use an in-memory executor as the sole storage for payments, orders, or mandatory notifications.

### 3.3. Work Queues / Competing Consumers

The producer sends a task to a queue; within a consumer group, one consumer receives and processes each message delivery. This model fits distributing tasks to workers, pacing processing rates, and absorbing traffic spikes.

**Strengths:** producer and workers are decoupled; worker count can scale up/down; queues provide buffering when send rate exceeds processing rate; brokers can persist messages durably.

**Limitations:** processing can lag as backlog grows; queue depth and message age must be monitored; retries can cause messages to be delivered multiple times; global ordering is typically reduced with multiple consumers or partitions.

Choose a queue when a task must be executed by one worker in a pool, such as generating PDFs, sending transactional emails, processing images, or running order post-processing. If a message carries a command, the consumer should check business state before executing to avoid repeating an already-completed action.

### 3.4. Publish-Subscribe and Event Notification

The producer emits an event; multiple independent consumers can receive copies or read the same event depending on broker mechanics. For example, `OrderPlaced` can trigger inventory reservation, email sending, and analytics updates.

**Strengths:** producer does not need to know all consumers; new consumers can be added without modifying the producer; each consumer group can evolve independently.

**Limitations:** system state becomes eventually consistent; consumers may process at different times; ordering across subscribers is not guaranteed by default; events require stable data contracts.

An event should describe what happened (`OrderPlaced`, `PaymentCaptured`), while a command describes what is requested (`CapturePayment`, `ReserveInventory`). An event consumer should not be interpreted as having received a mandatory command that must succeed. If a step requires confirmation of success to decide the next step, use command/reply or an orchestration workflow with explicit state.

### 3.5. Event Streams / Replayable Logs

In the streaming model, events are appended to a log ordered within a partition and retained according to a retention policy. Consumers track offsets or read positions; multiple consumer groups can read the same stream independently.

**Strengths:** suits high throughput, multiple consumers, data reprocessing, analytics, and building projections; read state can be rebuilt from retained history.

**Limitations:** requires managing partition keys, offsets, retention, schemas, and lag; ordering is normally guaranteed only within a partition; replays can re-execute side effects if consumers are not idempotent.

Choose a stream when event history is a valuable part of the system, multiple independent consumers are needed, or data must be re-read. Do not pick streaming solely because current load looks high; a simple queue can be easier to operate if the requirement is only distributing tasks to workers.

### 3.6. Push Notifications to Clients

Applications can push updates to browsers or devices via WebSocket/STOMP, Server-Sent Events, or other push mechanisms. This is typically a UI update channel, not the canonical store of business state.

If a client disconnects, decide whether notifications can be skipped or whether state must be fetched from an API upon reconnect. For important information, store authoritative state on the backend and use notifications as a signal for the client to fetch fresh data.

## 4. Quick Comparison Table

| Model | Perceived Latency | Default Durability | Coupling | Suitable Scenarios |
| --- | --- | --- | --- | --- |
| Direct in-process call | Low | Tied to application state; no queue | High at call level | Logic needing an immediate result in the same application |
| HTTP request-response | Low to medium, depends on network and downstream | Does not automatically persist requests for reprocessing | Caller depends on endpoint | Queries or commands needing immediate response |
| In-memory async | Caller returns fast; background work may lag | Low; can be lost on process stop | Looser at call time, still same application | Non-critical auxiliary tasks |
| Durable work queue | Can grow with backlog | Can be high with proper broker and config | Producer/consumer decoupled | Workers, retries, absorbing load spikes |
| Pub-sub event | Producer normally does not wait for consumers | Depends on broker/retention and config | Low | One event, multiple independent consumers |
| Event stream | Low upon successful append; consumers have separate lag | Log retained per retention policy | Low | Multiple consumers, replay, analytics, projections |
| WebSocket/STOMP | Low with stable connection | Notifications do not equal durable data | Client depends on endpoint/session | Real-time UI updates |

These are typical tendencies, not framework guarantees. An un-durably configured broker can lose messages; an HTTP service can persist a command to a database before returning; an async channel can still run synchronously if the implementation invokes handlers directly.

## 5. Latency: Measuring the Full Journey

Latency in a message-driven system consists of multiple parts:

1. Time for the producer to build, serialize, and send the payload.
2. Time for network transit or enqueueing.
3. Time the message waits in the backlog.
4. Time for the consumer to receive, deserialize, and process.
5. Time to write results to a database or call other services.

For request-response, users typically perceive the total duration of the entire chain. For async, the producer's response time may be short while end-to-end business completion time remains long. Do not report that the system is faster simply because an API returns early while the backlog grows continuously.

Measure at least:

- p50, p95, and p99 of processing time and wait time.
- Ingress/egress throughput, pending message count, and oldest message age.
- Consumer lag, retry counts, dead-letter counts, and error rate.
- Timeouts, expired request rate, and rejected task counts.

Set deadlines at request boundaries; propagate deadlines/correlation IDs when appropriate; avoid unbounded retries. If downstream is already overloaded, aggressive retries can slow system recovery.

## 6. Durability and Delivery Semantics

### 6.1. Volatile vs. Durable

Messages residing in an instance's memory can be lost on process crash or deployment. A broker with persistent messages, durable queues/topics, replication, and proper write acknowledgements can survive some failures, but the level of protection depends on actual configuration: durable destinations, persistence, replication/quorum, acknowledgements, retention, disk, and failover policies.

Do not conflate these concepts:

- **Durable queue/topic:** destination structure preserved across restarts per broker guarantees.
- **Persistent message:** broker is instructed to store message contents using its persistence mechanism.
- **Publisher confirm/acknowledgement:** producer knows the broker received/wrote the message per the configured confirmation level.
- **Consumer acknowledgement:** consumer confirms it processed or accepted responsibility for processing.
- **Replication:** copies of data across multiple nodes; understand quorum levels and failure models.

A durable queue alone is insufficient if the producer sends messages without confirming writes, the consumer acks before business commit, or the broker lacks appropriate replication settings.

### 6.2. At-Most-Once, At-Least-Once, and Effectively-Once

| Semantics | Characteristics | Design Consequences |
| --- | --- | --- |
| At-most-once | Message is processed at most one time; may be lost | Suitable only when message loss is acceptable or regenerable |
| At-least-once | Message is redelivered until confirmed per policy; duplicates possible | Consumer must tolerate repeated processing |
| Effectively-once in business logic | Multiple deliveries, yet business effect applied once via dedup/idempotency and transactions | Requires unique keys, inbox/dedup records, or conditional updates |

Do not promise “exactly once” for an entire business flow spanning multiple services based solely on broker configuration. A broker may support transactions or exactly-once semantics within a narrow boundary, yet database writes, external API calls, emails, and multi-system updates still require dedicated consistency design.

### 6.3. Idempotency and Deduplication

An idempotent consumer means receiving the same message again does not apply the business logic a second time. A common technique is attaching a stable `eventId` or `messageId`, saving the processed ID in the same transaction as the business change, and placing a unique constraint so two concurrent executions cannot both succeed.

For example, upon receiving `PaymentCaptured` with `eventId=evt-123`, the consumer checks an inbox/dedup table. If the ID is already processed, the consumer skips repeating the effect and acks the message; if not, the consumer writes the dedup record and updates the invoice in the same transaction. Handle races between two consumers claiming the same ID using constraints/locking, not just a `SELECT` before `INSERT`.

For resource-creating commands, you can use an idempotency key generated by the client or upstream service. The key must be scoped to the business action and retained long enough to cover possible retry windows.

### 6.4. Transactional Outbox and Inbox

A common bug is succeeding on a database update while failing to publish the event, or publishing the event successfully and then having the database transaction roll back. If business requirements demand alignment between data changes and emitted events, use the transactional outbox:

1. In the same database transaction, update business data and write an outbox record.
2. A publisher reads unsent outbox records and sends messages to the broker.
3. Upon receiving confirmation per policy, mark the record as sent or record send status.
4. Consumers use an inbox/dedup mechanism to handle duplicate messages safely.

An outbox avoids requiring a distributed transaction between the database and broker. However, the publisher may resend if it crashes after the broker receives the message but before marking the outbox record done; thus consumers still need idempotency. Include retry policies, record cleanup, backlog monitoring, and poison-message handling.

## 7. Ordering, Partitioning, and Consistency

System-wide global ordering usually limits scalability. Many brokers guarantee ordering only within a single queue or partition; multiple consumers, retries, redeliveries, and concurrent processing can make completion order differ from send order.

If events for the same order must stay in sequence, use a consistent partition key such as `orderId`, and ensure consumers process sequentially within that key's scope. If global ordering is unnecessary, do not force all messages into a single partition because it creates a bottleneck.

Consumers should check aggregate version or sequence numbers when out-of-order events must be detected. Early-arriving events can be buffered in a waiting area, trigger a replay request, or be rejected for retry per policy. Never assume the sender's machine timestamp accurately reflects business order.

Eventual consistency means different parts of the system can observe different states for a period of time. UIs and APIs must reflect that: statuses like `PROCESSING`, `PENDING`, or an “updating” notice can be more accurate than returning success as if every consumer has already finished.

## 8. Retries, Timeouts, Dead-Lettering, and Backpressure

### 8.1. Bounded Retries

Retries suit transient failures such as network timeouts or overloaded dependencies. Use a maximum attempt count, exponential backoff, and jitter so multiple consumers do not retry simultaneously. Distinguish transient errors from invalid data, business rule violations, or unsupported schemas; permanent errors should not be retried indefinitely.

### 8.2. Dead-Letter Queues

Messages that cannot be processed after the retry policy is exhausted can be moved to a dead-letter queue (DLQ) or equivalent quarantine. Record the reason, exception, attempt count, timestamp, correlation ID, and metadata so operators can fix data or deploy a new consumer and replay in a controlled manner.

A DLQ is not a trash bin to forget. Set alerts when new messages arrive, classify failures, establish retention periods, and define a replay procedure that avoids creating duplicate business effects.

### 8.3. Backpressure and Resource Limits

If the producer outpaces the consumer over time, backlog grows. Bound in-flight messages, batch sizes, concurrency, prefetch, queue capacity, or send rates. When full, the system must behave deterministically: block the producer, reject, return an error, shed load, or spill to alternate storage.

Do not spawn a new thread per message without bounds. In Spring, executor configuration must account for core/max pool size, queue capacity, rejection policies, and graceful shutdown waiting for tasks. An unbounded queue can turn backpressure into an out-of-memory crash.

## 9. Choosing a Model by Real-World Scenario

| Scenario | Suggested Model | Rationale and Prerequisites |
| --- | --- | --- |
| User needs immediate validation feedback | Synchronous request-response | Returns result/validation directly; set timeouts and downstream bounds |
| Generate PDF invoice after order is accepted | Durable work queue | Decouples file generation time from API; retries and idempotency by invoice ID |
| When an order is placed, inventory and email both need to know | Pub-sub event | Each consumer has its own lifecycle; eventual consistency accepted |
| Multiple consumers need to replay change history | Event stream | Managed retention, offsets, schema evolution, and partition keys |
| Update cart quantity within the same request | Synchronous service/transaction call | User needs immediate result and action usually sits within one data boundary |
| Send “new data available” signal to browser | WebSocket/STOMP or SSE | Client fetches authoritative state from backend upon reconnect |
| Record non-critical metrics or audits in the same process | Async in-process | Low operational cost; use only if loss on restart is acceptable |
| Record a transaction and must emit a corresponding event | Database transaction + outbox + broker | Prevents mismatch between data commit and event publish |

This is a starting point for discussion. Before implementing, verify SLAs, failure modes, peak load, operational cost, and whether the on-call team can support the chosen technology.

## 10. Mapping to Spring Framework and the Spring Ecosystem

### 10.1. Messages and Headers

`org.springframework.messaging.Message<T>` represents a payload alongside `MessageHeaders`. The payload carries business data; headers carry metadata such as correlation ID, event ID, event type, schema version, tenant, or routing information. Do not stuff entire business payloads into headers.

`MessageBuilder` helps construct messages cleanly. The message abstraction lets handlers work with a uniform envelope, though the payload still needs a clear contract and compatibility rules.

### 10.2. MessageChannel and MessageHandler

`MessageChannel` is the message-sending abstraction. `SubscribableChannel` supports registering handlers to receive messages; `PollableChannel` supports consumers retrieving messages via receive/poll operations. The channel type and implementation determine dispatch, blocking, timeouts, and consumer competition.

Never infer that every `MessageChannel` is a durable queue or asynchronous. Spring Framework provides foundational abstractions; implementations and adapters across the Spring ecosystem determine how messages are actually transported.

### 10.3. Distinguishing Spring Framework, Spring Integration, and Broker Adapters

- **Spring Framework Messaging:** defines messages, headers, channels, handlers, and basic dispatch support such as executor-based channels.
- **Spring Integration:** provides many channels and endpoints for integration, such as `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel`, pollers, and adapters. It is a separate module; do not mistake these classes as all belonging to `spring-messaging`.
- **Spring AMQP:** integrates with RabbitMQ/AMQP, providing templates, listener containers, and configurable acknowledgement/retry mechanisms.
- **Spring for Apache Kafka:** integrates with Kafka, producers/consumers, listener containers, transactions, and offset management.
- **Spring JMS:** integrates with JMS providers and listener containers.
- **Spring WebSocket/STOMP:** transports messages between server and clients over WebSocket/STOMP; client connections do not replace durable data storage.

Choose an adapter based on the broker and protocol your system actually needs. Read the specific adapter's configuration for acknowledgements, persistence, retries, transactions, concurrency, and serialization; generic abstractions do not substitute for checking those properties.

### 10.4. Application Events Are Not a Broker

`ApplicationEventPublisher` is useful for internal events within the same Spring application context. By default, listeners are invoked synchronously; if async is configured, work can run on an executor. Application events do not automatically provide durable storage, post-restart retries, or replay across services.

If an event is strictly an internal signal, does not need to survive restarts, and is not an inter-service integration contract, application events may suffice. If an event must be delivered reliably across process boundaries, use durable storage and transport with appropriate guarantees.

## 11. Spring Messaging Example: Creating a Message Envelope

The example below demonstrates wrapping payload and metadata into a Spring `Message`. It does not simulate a broker, queue, persistence, or delivery guarantees; the goal is to show data and metadata clearly separated so transports/handlers can share a contract.

Create a Maven project with structure:

~~~text
message-envelope-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageEnvelopeDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-envelope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/MessageEnvelopeDemo.java`:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageEnvelopeDemo {
    private MessageEnvelopeDemo() {
    }

    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("OrderPlaced: order-42")
                .setHeader("eventType", "OrderPlaced")
                .setHeader("eventId", "evt-42")
                .setHeader("correlationId", "corr-42")
                .setHeader("schemaVersion", 1)
                .build();

        System.out.println(message.getPayload());
        System.out.println("eventType=" + message.getHeaders().get("eventType"));
        System.out.println("eventId=" + message.getHeaders().get("eventId"));
        System.out.println("correlationId=" + message.getHeaders().get("correlationId"));
        System.out.println("schemaVersion=" + message.getHeaders().get("schemaVersion"));
    }
}
~~~

Run from the directory containing `pom.xml` using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageEnvelopeDemo
~~~

Stdout:

~~~text
OrderPlaced: order-42
eventType=OrderPlaced
eventId=evt-42
correlationId=corr-42
schemaVersion=1
~~~

In a real system, the producer can send this message through an appropriate adapter; the consumer must validate the payload, check the schema version, use the event ID for deduplication, and log using the correlation ID. Do not treat successfully constructing a `Message` as proof that a broker stored it or a consumer processed it.

## 12. Common Design Mistakes

- **Choosing async just to make an API look fast:** the caller returns quickly while the backlog grows and business work misses deadlines. Measure end-to-end completion time, not just response time.
- **Using an in-memory queue for data that must be delivered:** restarts can lose jobs. Switch to a durable broker/outbox when business requirements demand it.
- **Assuming messages are delivered only once:** crashing after commit but before ack can cause consumers to redeliver. Design idempotency from the start.
- **Infinitely retrying all errors:** poison messages or bad payloads consume resources forever. Classify errors, bound retries, and use a DLQ.
- **Using a single partition for everything to preserve global order:** throughput becomes capped. Enforce ordering per aggregate/key only when truly required.
- **Emitting events before the business transaction commits:** consumers may observe events for unsaved data. Use appropriate after-commit hooks or transactional outbox.
- **Putting sensitive data into headers/logs:** metadata can also be logged or forwarded across multiple components. Include minimal info and apply access controls/encryption.
- **Using event notification instead of queries:** consumers receive events without enough state to answer current queries. Maintain dedicated projections/read models or query APIs.
- **Neglecting schema management:** producers renaming fields or changing types break older consumers. Maintain versioning and compatibility rules during rollouts.
- **Ignoring backlog/lag:** the system still accepts messages while business outcomes already violate SLAs. Alert on message age and consumer lag, not just process health.

## 13. Decision-Making Process

1. Identify who needs the result and when: immediately in the request, within a few seconds, or anytime within a longer SLA.
2. Determine data loss tolerance: if a process or broker restarts, which messages must be preserved?
3. Choose the topology: single consumer, multiple subscribers, or multiple consumer groups needing replay.
4. Lock down semantics: at-most-once or at-least-once; where dedup keys are stored; how duplicates and out-of-order events are handled.
5. Lock down load and limits: throughput, bursts, queue capacity, concurrency, backpressure, and retention.
6. Select the appropriate Spring adapter: in-process event/channel, Spring Integration, AMQP, Kafka, JMS, or WebSocket/STOMP.
7. Design failure handling before implementation: timeouts, retries, DLQs, poison messages, shutdown, and replay.
8. Test failure modes: kill producer/consumer, restart broker, drop network, send duplicates, send invalid schemas, spike load, and verify recovery.
9. Measure end-to-end SLAs and operational cost; keep complex models only when the business benefit is clear.

## 14. Key Takeaways

Choose an exchange model by starting from business outcomes, latency budgets, data-loss tolerance, multi-consumer needs, ordering, and retryability. Request-response fits immediate results; in-memory async fits auxiliary tasks that can be lost; durable queues fit background jobs; pub-sub fits one event with multiple interested parties; event streams fit multiple consumers and replay capability. Spring Messaging standardizes messages and send/receive points, while durability, delivery semantics, ordering, and retries depend on implementations, brokers, configurations, and consumer design. A sound choice must be measurable, operable, and protect business state when failures occur.