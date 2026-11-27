# Learning Path from Message Flows to Distributed Flows

## 1. Destination of the Learning Path

In a small application, you can handle requests with a sequence of method calls: receive the order, validate data, calculate the price, save the result, and reply. When a system has multiple data sources, multiple processing branches, or independently deployed services, direct calls easily couple components tightly together. **Spring Integration** lets you express data exchange as a *message flow* grounded in **Enterprise Integration Patterns (EIP)**: each step receives a message, performs one clear responsibility, and passes it to the next step over a channel.

The goal of this introductory lesson is to map out a practical, measurable learning path moving from synchronous flows inside one application to asynchronous, resilient flows deployed across multiple processes. Core techniques include **Gateway, Filter, Transformer, Router, Splitter, Aggregator, correlation, retry, error channel**, paired with testing and observability for each processing branch.

After completing the path, learners should be able to:

1. Explain **message, payload, headers, channel, endpoint** and distinguish synchronous calls from asynchronous messaging.
2. Design flows with Spring Integration Java DSL, determining which branch a message will traverse and why.
3. Preserve correlation information when splitting/aggregating messages and handle failures, duplicates, and timeouts.
4. Decide when a broker, persistent state storage, multi-instance scaling, and compensation mechanisms are needed.
5. Prove behavior through tests, metrics, logs, and traces rather than merely seeing the program run successfully once.

## 2. Foundational Model: From Method Calls to Message Flows

A **Message** consists of a **payload** (business data) and **headers** (metadata such as message ID, timestamp, correlation ID, reply channel). A **MessageChannel** transports messages between endpoints. An **Endpoint** performs actions such as filtering, transforming, routing, invoking a service, or connecting to external systems. Separating these three concepts lets you change how messages are sent and received without rewriting all business logic.

~~~mermaid
flowchart LR
    G[Gateway: receive request] --> C[orders.in]
    C --> F{Filter: valid?}
    F -->|No| X[orders.invalid]
    F -->|Yes| T[Transformer: normalize]
    T --> R{Router: region}
    R -->|VN| V[orders.vn]
    R -->|Other| I[orders.intl]
~~~

In this diagram, **Gateway** is the entry point, **Filter** checks conditions, **Transformer** produces a uniform data shape, and **Router** selects the branch. These components do not need to know who created the message or who will process it downstream of the channel.

Key distinctions:

| Component | Function | Design Question |
|---|---|---|
| Gateway | Introduces an application call into the flow, optionally receiving a reply | Does the caller need an immediate reply or only an acknowledgement of receipt? |
| Channel | Transfers messages between endpoints | Dispatch immediately, buffer in a queue, or hand off to an executor? |
| Filter | Accepts or drops messages by predicate | Where do dropped messages go, and must the reason be recorded? |
| Transformer | Converts payload structure or content | Which headers and identifiers must be preserved? |
| Router | Selects one or more target branches by criteria | Is there a default branch and handling for unknown values? |
| Splitter | Splits one message into multiple parts | How are group membership and part counts identified? |
| Aggregator | Combines related messages into a result | When are enough parts received to release, and when does it time out? |
| Service Activator | Invokes business logic | Does the logic have side effects requiring retry or idempotency? |

**DirectChannel** normally dispatches work to a handler on the sender's execution thread; it creates no durability boundary. **ExecutorChannel** moves the handler onto an executor, changing the execution context, yet by itself provides no durable queue. **QueueChannel** stores messages in a local queue for a poller or consumer to retrieve; durability across restarts depends on configuring a message store. Only a broker like Kafka or RabbitMQ establishes a communication boundary across processes, and even then you must design appropriate retries and data guarantees.

## 3. Seven-Stage Learning Path

Work through these in order, since each stage builds on the previous one. The running exercise is **multi-region order processing**: ingest orders, validate, normalize, classify, split line items, process concurrently, aggregate results, record errors, and finally integrate an independent service.

| Stage | Core Knowledge | Mandatory Exercise | Completion Criteria |
|---|---|---|---|
| **1. Local message flow** | Message, headers, channel, Gateway, Java DSL | Accept an order via Gateway, forward to handler | Draw and run a one-way flow; verify payload and headers |
| **2. Branching and transformation** | Filter, Transformer, Router, discard/default channel | Reject bad orders, normalize region, route VN/international | Every input has a deterministic path, including invalid inputs |
| **3. Splitting and aggregating** | Splitter, Aggregator, sequence, correlation | Split an order into line items, price each line, then aggregate | Never mix two orders; handle incomplete or expired groups |
| **4. Asynchrony and backpressure** | ExecutorChannel, QueueChannel, poller, ordering | Move a flow segment to async execution; bound queued work | Measure throughput, latency, and behavior as backlog grows |
| **5. Error recovery** | ErrorMessage, error channel, retry, backoff, idempotency | Simulate timeouts, transient failures, duplicate messages | Distinguish retryable vs. non-retryable; failures have a sink and monitoring |
| **6. Distributed via broker** | AMQP/Kafka/JMS adapters, consumers, durability, outbox | Split producer and worker into two apps communicating via a broker | Restarting a worker loses no acknowledged business work |
| **7. Testing and observability** | Flow tests, correlation, metrics, traces, load, ops | Test every branch and failure; build per-flow dashboard | Trace an order end-to-end and explain any failures |

Stages are **skill milestones**, not fixed day counts. They can be grouped into four practice cycles: (1) local flows and branching, (2) split/aggregate and asynchrony, (3) errors and reliability, (4) brokers, integration testing, and observability.

## 4. Stages 1–2: Building a Working Flow

With Spring Boot, you can start with the `spring-boot-starter-integration` dependency; for tests, add `spring-integration-test` in `test` scope. Java DSL describes processing pipelines clearly and makes naming channels straightforward.

The minimal example below uses Java records (Java 17+) to demonstrate **Gateway → Filter → Transformer → Router**. Standard Java, Spring, and Spring Integration imports are omitted for readability.

~~~java
record Order(String id, String region, BigDecimal amount) {}
record NormalizedOrder(String id, String region, BigDecimal amount) {}

@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    void submit(Order order);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlows {
    @Bean
    IntegrationFlow classifyOrders() {
        return IntegrationFlow.from("orders.in")
            .filter(Order.class,
                o -> o.id() != null && !o.id().isBlank()
                    && o.region() != null && !o.region().isBlank()
                    && o.amount() != null && o.amount().signum() > 0,
                f -> f.discardChannel("orders.invalid"))
            .transform(Order.class,
                o -> new NormalizedOrder(
                    o.id(),
                    o.region().trim().toUpperCase(Locale.ROOT),
                    o.amount()))
            .route(NormalizedOrder.class, NormalizedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                    .defaultOutputChannel("orders.intl"))
            .get();
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(m -> System.out.println("VN: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow internationalOrders() {
        return IntegrationFlow.from("orders.intl")
            .handle(m -> System.out.println("INTL: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.invalid")
            .handle(m -> System.out.println("INVALID: " + m.getPayload()))
            .get();
    }
}
~~~

Calling `orderGateway.submit(new Order("O-101", "vn", new BigDecimal("120000")))` takes the VN branch. Region `SG` enters the international branch; blank IDs or invalid amounts move to the discard channel. This is a **learning example**: handlers currently print logs, whereas a real system should call appropriate services and record rejection reasons per business policy.

In a flow using `DirectChannel`, endpoints can execute on the sender's thread. Thus **a Gateway with a `void` return type does not mean background processing**. Only introducing an asynchronous boundary or an appropriate queue alters caller blocking and error behavior.

**Extension exercise:** add a Router for customer tier, create a default branch for unsupported values, and ensure every branch has a handler. Test three cases: valid domestic order, international order, and invalid order. Keep `orderId` in the payload or headers for downstream tracing.

## 5. Stage 3: Splitter, Aggregator, and Correlation

An order with multiple line items often requires per-line inventory checks or fee calculations. **Splitter** generates child messages; **Aggregator** combines only parts belonging to the same group. This step turns a linear flow into a fan-out/fan-in flow.

~~~mermaid
flowchart LR
    O[Order O-101: three lines] --> S[Splitter]
    S --> A[Line 1]
    S --> B[Line 2]
    S --> C[Line 3]
    A --> P[Check / price]
    B --> P
    C --> P
    P --> G[Aggregator by correlation]
    G --> R[Order result]
~~~

Spring Integration's Splitter can populate sequence headers such as `correlationId`, `sequenceNumber`, and `sequenceSize`. A default Aggregator can use correlation and sequence metadata to group and release batches. When crossing an external system, **verify whether adapters and transformations preserve the required headers**; if not, map them explicitly in event metadata or the payload.

In real problems, maintain a stable business key such as `orderId`. Do not confuse the `messageId` of an individual message transmission with the correlation key of the whole order. Especially under retry/redelivery, one order may produce multiple distinct messages.

Aggregator design must answer four questions simultaneously:

1. **Correlation:** Which messages belong to the same group? Could `tenantId` or `orderId` collide across customers?
2. **Release:** Does reaching `sequenceSize` emit the result, or must all required response types arrive per business rules?
3. **Timeout:** If one line item never finishes, how long will the group wait? Emit a partial result, mark as failed, or route to manual handling?
4. **Message store:** Is the group kept in RAM or a durable store? What happens if the instance holding the group restarts?

To practice, submit two orders A and B, each with three lines; interleave their return results and deliberately delay one line of A. Pass criteria: no result from B leaks into A, no summary is emitted before the release condition is satisfied, and an expired group produces an error record containing `orderId`.

## 6. Stage 4: Changing Execution Semantics and Controlling Backpressure

Moving from synchronous to asynchronous is not just adding threads. You must consider **queue capacity, processing order, latency, shutdown behavior, and recoverability**.

| Flow Connection | Suitable For | What to Test |
|---|---|---|
| `DirectChannel` | Short, synchronous in-process handling | Does a slow handler block the sender? How do exceptions propagate back? |
| `ExecutorChannel` | Offloading work to an in-app executor | How are full thread pools and queues handled? Does order change? |
| `QueueChannel` + poller | Decoupling producer/consumer speeds in-app | How many messages does the poller fetch, how long do they wait, is the store durable? |
| Broker + inbound/outbound adapters | Moving messages across processes or services | How do acks, redelivery, partitions, consumer restarts, and duplicates behave? |

Controlled experiment: send 1,000 orders to a handler simulating 100 ms per order; measure **ingest rate**, **completion rate**, **p95 latency**, **queued message count**, and **failures when queues fill**. Vary worker counts, queue sizes, and input rates to observe: throughput may rise, but latency and memory usage may rise too. Concurrency caps, batch sizes, and load-shedding rejections must be tuned to realistic load.

Do not assume asynchronous processing preserves global ordering. If strict ordering by `orderId` is a hard requirement, design partitioning/keying or appropriate serialization at boundaries that can run concurrently.

## 7. Stage 5: Errors, Retries, and Idempotency

A reliable flow must answer: **when a step breaks, where is the message, who receives the error, should it retry, and will retrying cause side effects?**

**Classify errors before retrying:**

- **Data/business-rule errors:** e.g., negative amounts or invalid order statuses. Typically routed to a rejection channel with a reason, without endless retries.
- **Transient errors:** e.g., timeouts or overloaded downstream dependencies. Retryable with bounded attempts, backoff, and jitter, then routed to failure handling.
- **Indeterminate-outcome errors:** e.g., payment succeeded but the connection dropped before the response arrived. Blindly retrying can create duplicate records without idempotency.

In Spring Integration, endpoints can apply **retry advice** for appropriate operations. For async segments, use an **error channel** to receive `ErrorMessage` according to the endpoint/adapter's error-publishing behavior; in synchronous flows, exceptions can propagate back to the Gateway. Do not assume all errors automatically land on the same error channel. Verify the error path of each inbound adapter and channel explicitly.

Example policy for an invoicing operation:

| Situation | Desired Action |
|---|---|
| Transient HTTP 429/503 | Retry up to configured limit with increasing backoff |
| Invalid payload schema | Route to `orders.invalid`, do not retry |
| Timeout after write operation | Look up by idempotency key before re-executing |
| Retries exhausted | Send to dead-letter queue (DLQ) or manual workflow with context |
| Redelivery of an already-processed event | Detect duplicate by business key and handle safely |

Attach `orderId`, `eventId`, `attempt`, and correlation/tracing context to each execution. **Idempotency** can be implemented with a unique business key, database unique constraints, or a processed-events table. Mark processing complete only when side effects actually succeed, and design transactions/recording carefully to avoid gaps in between.

Fault-injection tests should cover at least: handler throwing exceptions, dependency timeouts, broker redelivery, receiving the same event twice, and crashing after writing data before acking. A flow is not reliable just because it has a retry block.

## 8. Stage 6: Taking Message Flows Across Distributed Boundaries

Once in-process flows are solid, split **producer** (order intake) and **worker** (order processing) into two separate applications. Add a message broker through the corresponding Spring Integration adapters (such as RabbitMQ/AMQP or Kafka depending on requirements). At this point, a message's lifetime and a process's lifetime are no longer the same.

~~~mermaid
flowchart LR
    C[Client] --> API[Order API / Gateway]
    API --> V[Validate + normalize]
    V --> OUT[Outbound adapter]
    OUT --> Q[(Broker: order events)]
    Q --> IN1[Worker A: inbound adapter]
    Q --> IN2[Worker B: inbound adapter]
    IN1 --> F1[Process + persist]
    IN2 --> F2[Process + persist]
    F1 --> RES[(Results / DB)]
    F2 --> RES
    F1 --> ERR[(DLQ / error workflow)]
    F2 --> ERR
~~~

The diagram depicts logical architecture; **whether an event goes to one or multiple consumers** depends on queue, topic, consumer group, and subscription settings. To distribute individual orders across workers, design the appropriate consumer group. To broadcast the same event to multiple independent domains, design separate subscriber groups.

When crossing service boundaries, explicitly decide:

| Issue | Decision That Must Become a Contract |
|---|---|
| **Event contract** | Event name, schema version, required fields, compatibility rules |
| **Delivery** | When to ack, redelivery conditions, retry in app vs. broker |
| **Durability** | Which broker, database, and message store survive restarts |
| **Ordering** | Required ordering key, and which partition or queue preserves it |
| **Deduplication** | Idempotency key, key retention window, duplicate handling |
| **Correlation** | How `orderId`, `correlationId`, `traceId` cross adapters |
| **Consistency** | What happens when DB commits but event publish fails, or vice versa |
| **Failure recovery** | DLQ, replay, alerts, compensation workflows, and operational ownership |

When business logic writes to a database and emits an event, consider **transactional outbox** to reduce the risk of losing events across the commit/publish gap. For multi-service workflows, study **saga/compensation** instead of expecting a single database transaction to span the whole flow.

**Important distinction:** brokers and Spring Integration help implement message transport, yet do not by themselves guarantee *exactly-once* across side effects in databases, HTTP calls, or payment systems. Practical systems combine at-least-once delivery, idempotency, and data consistency safeguards.

The deliverable for this stage is two separately running applications: an API emitting order events and workers receiving/processing them. Try stopping a worker while the producer keeps emitting, restart it, and verify the actual completed order count, redelivery count, and duplicate count.

## 9. Stage 7: Testing and Observing Every Branch

EIP testing should revolve around **message paths** and **observable state**. Spring Integration provides test utilities to replace or spy on endpoints; broker-backed flows additionally need integration tests that actually spin up the adapters and backing infrastructure.

| Test Group | Input / Stimulus | PASS Criteria |
|---|---|---|
| Filter | Order missing ID, non-positive amount | Never reaches processing handler; routed to discard branch |
| Transformer | Region with whitespace/lowercase | Region normalized; business fields preserved accurately |
| Router | VN, international, unknown value | Reaches expected channel per rules; default branch explicit |
| Split/Aggregate | Two interleaved orders, differing part counts | Groups match correlation cleanly with no cross-contamination |
| Timeout | One group fragment missing | Enforces timeout/release policy or measurable failure |
| Retry | Transient failure then recovery | Expected attempt count; no duplicate side effects |
| Error channel | Failure in async endpoint | `ErrorMessage` carries context and is handled |
| Broker | Worker restart, message redelivery | No committed orders lost; duplicates controlled |
| Load | Producer outpaces consumer | Backlog, latency, and expected overload behavior measured |

At minimum, every message should carry tracing attributes: `orderId` (business key), `correlationId` (processing group), `traceId` (cross-service tracing), event type, and processing status. For each endpoint, monitor **received/processed/error counts**, **processing latency**, **backlog**, **retries**, and **timeouts**. Use Micrometer/observability when integrating with Spring Boot and an appropriate observability stack; verify instrumentation and header propagation at every adapter.

When investigating a failed order, operators should be able to reconstruct the path **Gateway → Filter → Router → Splitter → Worker → Aggregator or Error**, along with routing reasons and retry attempts. Logging full payloads alone both lacks context and risks data leaks; prioritize identifiers, statuses, and essential diagnostic fields.

## 10. Capstone Exercise

Build an **Order Processing Integration Flow** system in two phases.

**Phase A — Single application:**

1. Gateway accepts `OrderPlaced(orderId, customerId, region, lines)`.
2. Filter rejects invalid data and logs the reason on the invalid branch.
3. Transformer normalizes region codes and line items.
4. Router selects domestic or international lanes.
5. Splitter splits `lines`; process independently, then Aggregator combines by `orderId` with an explicit timeout.
6. One step simulates transient service failures to practice retry and error channels.

**Phase B — Two applications:** replace the boundary between order intake and processing with a broker; run multiple workers while preserving correlation/idempotency; test restarts, redeliveries, backlogs, and monitor via metrics/traces.

Consider the exercise complete only when you can answer using logs, tests, or measurements:

- Which endpoints did a valid order traverse, and why did the Router pick that branch?
- With two orders processed concurrently, did the Aggregator group each cleanly?
- If one line item fails or arrives late, what is the final outcome?
- If a message is redelivered, is the business action recorded or charged twice?
- If a worker crashes, what data remains in the broker/store and how is it recovered?
- Under rising load, where do bottlenecks and queue limits appear?

## 11. Common Mistakes When Moving to Distributed Flows

**Moving everything onto a broker too early.** Before payload, headers, contracts, and release criteria are clear, a broker only makes problems harder to observe. Clarify the local flow first, then place distributed boundaries where lifecycle separation or independent scaling is genuinely required.

**Assuming asynchronous means durable.** In-memory executors or queues do not preserve messages across restarts. Durability depends on stores, brokers, and ack/transaction policies.

**Losing correlation across split/aggregate.** Across external services, headers may be dropped or reshaped. Define correlation keys explicitly and test end-to-end.

**Retrying every error without idempotency.** Retrying an operation that already succeeded whose response was lost causes duplicate side effects. Classify errors, bound retries, enforce deduplication keys, and provide a final failure sink.

**Testing only the happy path.** Multi-branch flows need tests for discards, default routes, late messages, timeouts, worker restarts, and redeliveries. Per-branch observability must be part of the definition of done.

## 12. Next Steps for Deepening Mastery

After this introduction, follow the progression **Channel/Gateway → Filter/Transformer/Router → Splitter/Aggregator/Correlation → Executor/Queue/Poller → Retry/Error Channel → Broker Adapters → Testing/Observability**. On each topic, keep the same order domain problem so you can compare behavior before and after introducing each pattern.

A flow's maturity is measured not by how many patterns it uses, but by your ability to prove **data reaches the right destination, groups correlate accurately, errors are handled under control, and the system remains observable as it scales across processes**.
