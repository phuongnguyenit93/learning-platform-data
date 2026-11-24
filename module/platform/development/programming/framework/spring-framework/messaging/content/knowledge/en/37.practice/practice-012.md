# Reviewing Technology Choices from Requirements to Verification Results

> Scope: practicing technology decision-making for messaging systems in Spring. This lesson moves from business requirements, choosing patterns and transports, evaluating trade-offs, and prototyping to verifying with metrics and recording a reviewable decision.

## 1. Objectives of a Technology Review

Choosing technology does not start with the question "should we use RabbitMQ or Kafka?". It starts with the problem to be solved and evidence showing that a given choice solves that problem.

A high-quality decision must be able to answer:

1. What behavior does the system need to perform, and who uses that behavior?
2. What are the mandatory requirements? Which attributes are merely preferences?
3. Which interaction model does the system need: request/reply, command queue, event stream, broadcast, or bidirectional streaming?
4. Which transport and framework meet the requirements at an acceptable operational cost?
5. Which assumptions have been tested, and which assumptions remain risky?
6. What do the prototype and test results prove?
7. When should the decision be revisited?

A technology choice is not complete just because a dependency was added or the application starts up successfully. You must prove that the message path, errors, security, load, recovery, and operability satisfy the agreed criteria.

## 2. Distinguishing Decision Layers

In a Spring Messaging application, there are multiple related decisions that are not synonymous:

| Layer | Question to decide | Example |
|---|---|---|
| Message contract | What does the message contain, and how are versions and IDs structured? | Event envelope, schema version, correlation ID |
| Interaction pattern | How do the two sides exchange messages? | Request-Response, competing consumers, publish-subscribe |
| Transport/protocol | Which protocol carries the messages? | AMQP, Kafka protocol, JMS, RSocket, HTTP |
| Broker/platform | Which system stores and distributes messages? | RabbitMQ, Kafka cluster, Artemis |
| Integration framework | How are steps within the application connected? | Spring Integration, Spring Messaging |
| Adapter/client | Which API does the application use to talk to the transport? | Spring AMQP, Spring Kafka, Spring JMS, RSocketRequester |
| Operations | Who deploys, monitors, backs up, upgrades, and handles incidents? | Cluster topology, metrics, alerts, retention, runbook |

**Spring Integration is a framework for connecting systems and building message flows; it does not replace a broker on its own.** Channels like DirectChannel or QueueChannel can run in process memory. When durable message storage or inter-process communication is required, a transport/broker or an appropriately backed channel is needed.

Spring Integration supports adapters and gateways for many systems, including AMQP, JMS, Kafka, RSocket, HTTP, TCP, and files. Spring Boot also provides dedicated messaging integrations for JMS, AMQP/RabbitMQ, Kafka, Pulsar, RSocket, and Spring Integration. Therefore, choose the transport layer and the flow orchestration layer separately before deciding whether both are needed.

Examples:

- An application that only needs to receive messages from RabbitMQ and invoke a service can use a Spring AMQP listener directly.
- A flow that needs to receive messages, normalize, filter, route across multiple endpoints, and emit to multiple systems can benefit from Spring Integration.
- An internal pipeline within the same process may only need Spring Integration with DirectChannel; there is no need to deploy a broker if durability or inter-process communication is not required.

## 3. Gathering Requirements Before Building a Technology Shortlist

### 3.1. Describe the Business Flow in User Language

Specify clearly:

- Who emits the request or event?
- Who receives it and owns processing?
- Does the message represent a command, an event, or a query?
- Does the caller need an immediate result?
- How long can a consumer be offline?
- How many independent consumers are there?
- Will messages be reprocessed, replayed, or archived?
- When a message fails, who handles it and what is the remediation SLA?

Avoid starting from product names. Describe the flow using verbs and business outcomes, for example: "Checkout confirms an order; the system must deliver the fulfillment command to a worker even while workers are restarting; each order must create a shipment only once; operations must be able to inspect failed messages and replay them after fixing data."

### 3.2. Translate Requirements into Measurable Criteria

A requirement such as "fast", "stable", or "high-load" cannot be verified without concrete numbers or conditions.

| Attribute | Question to answer | How to measure |
|---|---|---|
| Throughput | How many messages/sec at normal and peak load? | Messages/second, consumer count, batch size |
| Latency | How long from producer send until consumer starts/finishes processing? | p50, p95, p99 |
| Durability | What failure types must confirmed messages survive? | Process restart, broker restart, node failure |
| Delivery semantics | Are redeliveries, losses, or duplicate processing allowed? | Redelivery, acknowledgement, idempotency |
| Ordering | Is global ordering needed or only per key? | Ordering per orderId/partition/queue |
| Fan-out | How many independent consumer groups need to receive the same event? | Subscription/consumer group count |
| Replay/retention | Must historical data be re-read, and for how long? | Retention, offset/sequence, replay tests |
| Availability | What are the maximum downtime and RTO/RPO? | Failover and recovery exercises |
| Security | Who may publish, consume, route, and view data? | TLS, authentication, authorization, audit |
| Operability | How can operations monitor and recover the system? | Dashboards, alerts, runbooks, backup/restore |
| Compatibility | Can producers/consumers upgrade independently? | Contract fixtures, schema evolution tests |
| Cost | What are the infrastructure, operational, and development costs? | CPU, RAM, storage, licenses, on-call effort |

Distinguish **mandatory requirements** from **preferences**. For instance, "messages confirmed by the broker must survive a single-node restart" may be a hard gate. "Easier to write code" is usually a preference criterion. An option with a high overall score must still be rejected if it violates a hard gate.

### 3.3. Write Quality-Attribute Scenarios

Use the structure: *context -> stimulus/failure -> expected response -> measure*.

Example:

- Context: 1,000 messages/sec are published to the fulfillment queue.
- Failure: a consumer process stops while processing a message.
- Response: the unacknowledged message is redelivered; a new consumer continues processing.
- Measure: zero broker-confirmed messages lost; redelivery is detected; duplicate processing does not create a second shipment.

Another example:

- Context: an analytics consumer needs to re-read events from 14 days ago.
- Failure: the consumer is redeployed and needs to rebuild its projection.
- Response: the consumer re-reads from the appropriate offset within the retention window.
- Measure: the post-replay projection matches control data and rebuild time meets the SLA.

These scenarios lead to different choices. A work queue and an event log with retention/replay represent two distinct needs, even though both are casually called a "message queue" in everyday conversation.

## 4. Choose the Interaction Pattern Before Choosing the Transport

| Need | Suitable pattern | Points to verify |
|---|---|---|
| Send a request and need one response | Request-Response / Gateway | Timeouts, correlation, reply routing, errors when caller disconnects |
| Send a command for one worker to process | Point-to-Point / Competing Consumers | Durability, acknowledgement, retries, dead-letter, idempotency |
| Emit events to multiple independent systems | Publish-Subscribe | Each consumer has its own subscription, fan-out, retention/replay |
| Send a continuous stream of events | Event Stream | Partition key, offsets, retention, consumer lag |
| Bidirectional exchange over an active session | Channel / Bidirectional Streaming | Backpressure, cancellation, keepalive, reconnect |
| Transform and route across multiple systems | Integration Flow | Adapters, transformers, filters, routers, error flows |
| Fetch data periodically | Polling / MessageSource | Poll interval, concurrency, locking/claiming, duplicate processing |

Do not use request/reply just because an API gateway is handy if the business logic truly requires asynchronous processing. Conversely, do not stand up a broker for a simple query needing an immediate response if HTTP/WebClient already meets the SLA and error model.

## 5. Common Options in the Spring Ecosystem

### 5.1. In-Process Channels

**DirectChannel** dispatches messages synchronously to a single subscriber. It fits simple internal flows where producer and consumer run in the same process.

**QueueChannel** holds messages in an internal queue to decouple producer and consumer in time. This queue does not become durable storage by itself; process termination can lose in-memory messages.

**PublishSubscribeChannel** sends messages to multiple subscribers in the same application. It serves internal fan-out and does not create durable copies across restarts.

Choose internal channels when:
- Messages only need to live for the process lifetime.
- No independent consumers in other services are needed.
- No replay is needed after application restarts.
- Low latency and in-process simplicity are priorities.

Do not use internal channels to satisfy durable queue requirements across multiple services.

### 5.2. RabbitMQ/AMQP with Spring AMQP and Spring Integration

RabbitMQ generally fits command/work queues, exchange-based routing, competing consumers, request/reply via gateways, and fan-out via exchange/queue bindings.

Spring AMQP provides abstractions such as RabbitTemplate, listener containers, and message converters. Spring Integration offers inbound/outbound channel adapters and gateways to wire AMQP into flows.

Common strengths:
- Flexible routing via exchanges, routing keys, and bindings.
- Queues well suited for competing consumers.
- Configurable acknowledgements, publisher confirms, and dead-letter/retry policies.
- Fits command and job flows that require processing followed by acknowledgement.

Points to verify:
- Are durable queues and persistent messages configured properly?
- Does the publisher wait for confirms before treating a message as accepted?
- Does the consumer ACK after processing succeeds or before side effects complete?
- Are retries bounded and backed by a dead-letter policy?
- Do queue type, replication, and topology satisfy the failure model?
- Does routing send unmatched messages to an alternate exchange or handle errors explicitly?

**Publisher confirms and consumer acknowledgements are two independent mechanisms.** Confirms verify the broker received the publish per configured semantics; consumer ACKs tell the broker a delivery was processed so the broker can remove the message. Enabling one does not replace the other. Configuring durable queues alone also does not prove the entire path is lossless.

Spring Integration includes AMQP-backed channels, yet the documentation distinguishes channel persistence from work distribution to peer applications. When multiple applications need to consume a queue together, use channel adapters/listener containers or Spring AMQP listeners rather than confusing internal AMQP-backed channels with a work-distribution mechanism.

### 5.3. Apache Kafka with Spring for Apache Kafka

Kafka fits when data is a partitioned ordered event log requiring retention, multiple independent consumer groups, replay, and projection rebuilding.

Spring for Apache Kafka provides:
- KafkaTemplate for publishing.
- `@KafkaListener` and listener containers for consuming.
- Offset management, retry/error handling, and transaction support.
- Serialization, deserialization, and message header mapping.
- Test support for testing producers/consumers.

Points to verify:
- Does the partition key preserve ordering for the same aggregate?
- Is the partition count sufficient for throughput and concurrency?
- Are dashboards and alerts in place for consumer lag?
- Is retention long enough for replay?
- Are offset commits/acknowledgements chosen appropriately relative to side effects?
- Are consumers idempotent when records are redelivered?
- How are schema evolution and payload compatibility managed?

Kafka does not guarantee global ordering across all partitions. If per-orderId ordering is required, choose a key so events with the same orderId land in the same partition and check consumer concurrency.

### 5.4. JMS with Brokers like ActiveMQ Artemis

JMS is a standard Java messaging API. Spring JMS provides sending/receiving via JmsTemplate/JmsClient and listener containers; Spring Integration offers JMS adapters/gateways.

JMS is worth considering when:
- The organization already operates a JMS broker with stable operational procedures.
- API-level portability across compatible JMS providers is required.
- The system uses queues/topics, listeners, transactions, and acknowledgements in the JMS model.
- Existing enterprise systems already integrate over JMS.

Points to verify:
- Are the specific provider and broker version compatible with the runtime?
- How are destinations, durable subscriptions, and acknowledgement modes configured?
- Which resources are covered by transaction boundaries?
- Do vendor-specific features reduce practical portability?

JMS is an API/contract, not the name of a broker. Specify the actual broker/provider in your decision.

### 5.5. RSocket

RSocket is an asynchronous messaging protocol over byte-stream transports, supporting interaction models such as Request-Response, Request-Stream, Fire-and-Forget, and Channel. Spring Messaging provides requesters/responders and Spring Boot can auto-configure codecs and handlers.

RSocket fits when two sides need bidirectional communication, data streaming, backpressure, and cancellation over an active connection.

Do not choose RSocket solely to replace a durable broker. A connection protocol does not inherently provide log retention or durable queues for offline consumers. If messages must survive service disconnections, separate persistence/broker mechanisms are required.

### 5.6. HTTP/REST and WebClient

HTTP suits request/reply, resource-oriented APIs, and interactions requiring a clear response within the request. WebClient supports reactive HTTP.

HTTP can be a simple choice if the caller needs an immediate result and does not require broker retention, replay, or decoupled consumers. If work must continue after the response returns, the API can accept a command, durably persist the command/outbox, and return accepted; downstream processing continues via messaging.

Do not treat an HTTP request timeout as proof that the server did not execute side effects. If the response is lost after server processing, client retries can send duplicate commands. An idempotency key is required when operations must not repeat.

## 6. Conditional Comparison Matrix

The table below is only an initial guide; it does not replace benchmarks and topology-specific verification.

| Option | Work queue/routing | Event replay | Request/reply | Bidirectional streaming | Cross-process durability |
|---|---|---|---|---|---|
| DirectChannel | No, in-process only | No | Possible via internal gateway | Not primary purpose | No |
| QueueChannel | Internal queue | No | Possible via flow | Not primary purpose | Not durable by default |
| RabbitMQ/AMQP | Very strong fit | Limited by queue/stream and configured retention | Has gateway/request-reply | Not primary choice | Yes, if topology/persistence are configured properly |
| Kafka | Usable, though primary model is log/partition | Very strong fit | Not primary request/reply model | Not primary model | Yes, via replication/retention/acks |
| JMS/Artemis | Good fit | Depends on provider/storage mechanism | Good fit | Not primary model | Yes, per broker/provider |
| RSocket | Not a durable work queue | No | Very strong fit | Very strong fit | Connection protocol; requires separate persistence |
| HTTP/WebClient | No built-in queue | No | Very strong fit | HTTP streaming usable for some scenarios | Not durable by default |

Do not compare technologies merely by feature count. A broker feature that is not configured, monitored, and tested is not a capability the system can rely on.

## 7. Filtering Hard Constraints Before Scoring

Create an exclusion checklist. For example:

- Must preserve accepted messages across process restarts.
- Consumers may be down for 10 minutes while producers keep publishing.
- At least two independent consumer groups must read the same event.
- Must replay 14 days of historical messages.
- System may deploy only in an approved data region.
- Only use library versions still supported and compatible with current Java/Spring versions.

If a requirement mandates 14-day replay, DirectChannel, QueueChannel, and standalone RSocket are eliminated immediately. Do not award high scores for development speed to compensate for a violated hard constraint.

Each hard gate should include:
- Requirement source or responsible approver.
- Verification method.
- Pass/fail evidence.
- Remediation plan if unmet.

## 8. Weighted Trade-Off Scoring

After filtering hard gates, score the remaining candidates on the same scale.

Suggested rating scale:

- 1: unsuitable or requires heavy workarounds.
- 2: partially meets needs, with significant risks.
- 3: meets requirements with some conditions.
- 4: good fit, risks are manageable.
- 5: direct fit, backed by evidence and team operational readiness.

Formula:

\[
Score = \frac{\sum (weight_i \times rating_i)}{5}
\]

Weights sum to 100 so results fall on a 0–100 scale. Scores are meaningful only when assumptions and evidence are recorded for each rating. If evidence is missing, mark it "unknown" and run a spike; do not arbitrarily assign a 4 or 5.

### 8.1. Example: Fulfillment Command Queue

Suppose sample requirements are:
- Fulfillment commands must be durably stored when consumers pause temporarily.
- Multiple workers consume the same queue to share load.
- Routing by command type and priority is required.
- Bounded retries, dead-lettering, and redelivery are required.
- Multi-week full event replay is not needed.
- Operations already has experience with RabbitMQ and Artemis.

Hard gates eliminate internal channels and standalone RSocket because they do not satisfy a durable work queue. The three remaining candidates are scored as follows:

| Criterion | Weight | RabbitMQ | Kafka | JMS/Artemis |
|---|---:|---:|---:|---:|
| Durable delivery | 25 | 5 | 5 | 5 |
| Routing and competing consumers | 20 | 5 | 4 | 4 |
| Retry and dead-letter | 15 | 5 | 4 | 4 |
| Replay/retention for this use case | 10 | 3 | 5 | 3 |
| Ordering by key | 10 | 4 | 3 | 4 |
| Spring integration | 10 | 5 | 5 | 4 |
| Existing operational experience | 10 | 5 | 3 | 3 |
| **Sample total** | **100** | **94** | **85** | **81** |

The scores above are illustrative evaluations under hypothetical requirements, not product benchmarks. If the use case shifts toward an event log requiring long-term replay across multiple consumer groups, replay weight increases and Kafka may become the better fit. If the organization already operates a JMS provider at scale and requires interoperability with legacy systems, operational/JMS compatibility scores also change.

## 9. Prototypes Must Test the Biggest Risks

You do not need to build the entire product to evaluate a technology. Build a small vertical slice capable of exposing risky assumptions.

A minimal messaging prototype should include:

1. A producer sending representative payloads with message ID, schema version, and correlation ID.
2. A real transport/broker with a near-production topology.
3. A real consumer running at expected concurrency.
4. Validation, idempotency, and error handling.
5. Sufficient metrics/logs/tracing for observability.
6. Tests for restarts, redelivery, duplicates, malformed payloads, and timeouts.
7. Load tests with realistic payloads and key distributions.

Do not benchmark only a producer sending a short string to a broker on a laptop. That result does not prove a production system can achieve the required throughput, latency, or durability.

### 9.1. Checks by Candidate Type

**RabbitMQ/AMQP**
- Create durable exchanges/queues and bindings per target topology.
- Publish persistent messages and enable publisher confirms as required.
- Consumer ACKs after side effects finish per transaction boundaries.
- Stop a consumer mid-processing to verify redelivery.
- Test retry limits, DLQ, unmatched routing, and publisher returns.
- Test queue type/replication under node failures.

**Kafka**
- Choose topic partitions and keys matching ordering requirements.
- Check consumer groups, offset commits, and consumer lag.
- Restart consumers before and after commits to observe redelivery.
- Replay from older offsets and verify projections.
- Check retention, rebalances, partition expansion, and retry/DLT policies.

**JMS**
- Check queues/topics and durable subscriptions.
- Check acknowledgement modes and transaction rollbacks.
- Restart consumers/brokers per the failure model.
- Check provider-specific behavior and compatibility.
- Verify redelivery counts, DLQ, and listener concurrency.

**RSocket**
- Verify requester/responder interaction models.
- Measure latency and throughput with realistic payloads.
- Check cancellation, backpressure, timeouts, reconnects, and keepalives.
- Prove how messages are persisted if receivers go offline when required by business rules.
- Check auth metadata, codecs, and error mapping.

**Spring Integration**
- Trace the flow from adapter through channels, transformers/filters/routers to handlers.
- Verify channel types match threading and durability needs.
- Check poller intervals, concurrency, and backlogs.
- Check error channels, retry advice, and shutdown lifecycle.
- Use mock endpoints for unit/flow tests and real transports for integration tests.

## 10. Define Acceptance Criteria Before Running the Prototype

The numbers below are examples illustrating how to write criteria. On real projects, replace them with owner-confirmed SLAs and load targets.

| Sample goal | Verification method | Passes when |
|---|---|---|
| 1,000 messages/sec for 15 minutes | Load test with representative payloads | Stable throughput without continuously growing backlog |
| p95 enqueue-to-handler under 300 ms | Timestamps at producer and consumer | p95 stays within threshold at target load |
| Zero broker-confirmed messages lost in restart tests | Publish, await confirm, scripted restart, verify IDs | Every accepted ID is processed or in a recoverable state |
| Redelivery when consumer dies before ACK | Kill consumer between handler and ACK | Message is redelivered without duplicate side effects |
| Bounded retries | Inject intentional failures | Exact attempt count, backoff, and routing to DLQ |
| Old/new schema compatibility | Run contract fixture tests | Supported versions decode cleanly; unsupported versions rejected |
| Security | Bad tokens, unauthorized principals, misconfigured TLS | No unauthorized access; no secrets leaked in logs |
| Backlog recovery | Stop consumers to build a defined backlog | Backlog drains completely within the agreed deadline |

Define "accepted message" and "processed successfully" precisely. For RabbitMQ, distinguish publisher confirms from consumer ACKs. For Kafka, distinguish publish acknowledgements from offset commits. For JMS, explicitly state the transaction/acknowledgement mode. Without defining these milestones, a "zero message loss" test is meaningless.

## 11. Interpreting Results and Making the Decision

After the prototype, record results per criterion:

| Criterion | Target | Measured result | Pass/Fail | Evidence |
|---|---|---|---|---|
| Throughput | 1,000 msg/s | 1,120 msg/s | Pass | Load test run 03 |
| p95 latency | <300 ms | 245 ms | Pass | Metrics export |
| Restart recovery | No lost accepted IDs | 10,000/10,000 recovered | Pass | Restart test report |
| Duplicate handling | No duplicate shipments | 1 shipment/ID | Pass | DB assertion |
| DLQ | Max 3 retries | 3 retries then DLQ | Pass | Broker trace |
| Ops readiness | Dashboards and alerts | Missing queue age alert | Fail | Ops review |

Do not ignore a failing criterion simply because the overall score remains high. You can:
- Fix the configuration and re-run the test.
- Adjust the architecture to satisfy the requirement.
- Select another candidate.
- Request a requirement change from the owner with documented rationale and impact.

Prototype results are valid only under the tested conditions. Record broker version, topology, hardware, payload size, concurrency, network, JVM flags, Spring versions, and test duration. If conditions differ from production, note those limitations in the conclusion.

## 12. From Verification Results to Spring Configuration

Suppose the prototype selects RabbitMQ for work queues and Spring Integration to orchestrate flows.

Separation of responsibilities:

- Spring Integration: ingests messages into flows, transforms, validates, routes, and invokes handlers.
- Spring AMQP: connects to RabbitMQ, converts payloads, publishes, and consumes.
- RabbitMQ: exchanges, queues, bindings, delivery, ACKs/confirms, and broker-side routing.
- Domain service: idempotency, transactions, and business rules.
- Observability: measures publish confirms, queue depth/age, redeliveries, DLQ, and handler latency.

The flow example below is an illustrative configuration; ConnectionFactory, AmqpTemplate, exchanges, routing keys, and topology must be declared beforehand:

~~~java
@Bean
IntegrationFlow publishFulfillment(AmqpTemplate amqpTemplate) {
    return IntegrationFlow.from("orders.ready")
        .filter(OrderReady.class, order -> order.orderId() != null)
        .handle(Amqp.outboundAdapter(amqpTemplate)
            .exchangeName("orders.events")
            .routingKey("orders.fulfillment"))
        .get();
}
~~~

Consumers can use an inbound channel adapter or a Spring AMQP listener to read from the queue and hand off to an internal flow. Choose adapters vs. direct listeners based on flow complexity. If there is only a single handler, do not add an integration flow layer just for extra abstraction.

In real deployments:
- Declare exchanges, queues, bindings, and policies via infrastructure as code.
- Configure persistent delivery mode, publisher confirms/returns, and appropriate consumer acknowledgements.
- Tune prefetch/concurrency according to throughput and processing duration.
- Set retry limits, backoff, DLQ, and alerts.
- Keep message IDs stable across retries and process idempotently.
- Do not assume database and broker transactions automatically form an atomic distributed transaction.
- Use outbox/inbox when you need to close gaps between database commits and publish/consume.

## 13. Verifying Results in Java 17: Weighted Decision Scorer

The standalone example below computes weighted scores from team-evaluated ratings. It does not benchmark brokers; it makes scoring transparent and repeatable.

Create **TechnologyDecisionDemo.java**:

~~~java
import java.util.List;

public class TechnologyDecisionDemo {

    record Criterion(String name, int weight) {}

    record Candidate(String name, List<Integer> ratings) {}

    public static void main(String[] args) {
        List<Criterion> criteria = List.of(
            new Criterion("Durable delivery", 25),
            new Criterion("Routing and workers", 20),
            new Criterion("Retry and dead-letter", 15),
            new Criterion("Replay fit", 10),
            new Criterion("Ordering by key", 10),
            new Criterion("Spring integration", 10),
            new Criterion("Operations fit", 10)
        );

        List<Candidate> candidates = List.of(
            new Candidate("RabbitMQ / Spring AMQP",
                List.of(5, 5, 5, 3, 4, 5, 5)),
            new Candidate("Kafka / Spring Kafka",
                List.of(5, 4, 4, 5, 3, 5, 3)),
            new Candidate("JMS / Artemis",
                List.of(5, 4, 4, 3, 4, 4, 3))
        );

        int totalWeight = criteria.stream()
            .mapToInt(Criterion::weight)
            .sum();

        if (totalWeight != 100) {
            throw new IllegalStateException("Weights must sum to 100");
        }

        for (Candidate candidate : candidates) {
            if (candidate.ratings().size() != criteria.size()) {
                throw new IllegalArgumentException("Rating count mismatch");
            }

            int weightedTotal = 0;
            for (int i = 0; i < criteria.size(); i++) {
                int rating = candidate.ratings().get(i);
                if (rating < 1 || rating > 5) {
                    throw new IllegalArgumentException("Rating must be 1..5");
                }
                weightedTotal += criteria.get(i).weight() * rating;
            }

            int score = weightedTotal / 5;
            System.out.println(candidate.name() + " = " + score + "/100");
        }
    }
}
~~~

Compile and run:

~~~bash
javac TechnologyDecisionDemo.java
java TechnologyDecisionDemo
~~~

Output:

~~~text
RabbitMQ / Spring AMQP = 94/100
Kafka / Spring Kafka = 85/100
JMS / Artemis = 81/100
~~~

The program checks that weights sum to 100 and ratings fall in the 1–5 range. It does not enforce hard gates; hard gates must be evaluated before placing candidates on the shortlist. Scores assist discussion and are neither performance benchmarks nor quality guarantees.

## 14. Recording Decisions with an Architecture Decision Record (ADR)

Every major decision should have a concise ADR so others can understand why it was chosen and what would trigger a change.

Template:

~~~markdown
# ADR-00X: Choosing Transport for the Fulfillment Flow

- Status: Proposed / Accepted / Superseded
- Date:
- Owners:
- Related requirements:
- Review date:

## Context
Describe the problem, load, SLA, failure model, consumers, and related systems.

## Decision drivers
List hard constraints and weighted criteria.

## Options considered
RabbitMQ, Kafka, JMS/Artemis, RSocket, or other options.

## Decision
Specify transport, broker, Spring adapter/framework, and interaction pattern.

## Evidence
Link prototypes, load tests, restart tests, security tests, contract tests, and ops reviews.

## Consequences
Operational cost, retry semantics, retention, ordering, security, and remaining limitations.

## Revisit when
Conditions under which this decision must be re-evaluated.
~~~

An ADR is not a technology marketing document. Record drawbacks and remaining risks as well. If a decision changes, create a new ADR and link the old one; do not rewrite history as if the current choice were always the original one.

## 15. Controlled Rollout and Post-Release Verification

Even after passing the prototype, a controlled rollout is required:

1. Finalize infrastructure as code, secrets, TLS, queue/topic policies, and alerts.
2. Deploy consumers first if consumers must understand a new schema.
3. Enable the producer via canary or small traffic slice.
4. Monitor publish errors, confirm latency, consumer lag/queue age, redeliveries, DLQ, handler p95/p99, and resource usage.
5. Ramp traffic gradually once metrics stabilize.
6. Test restarts/failover and replay per approved runbooks.
7. Verify business outcomes, such as successful shipments created and duplicate order counts.
8. Save production metrics to compare against acceptance criteria.

If migrating between two transports, define how to avoid inconsistent dual-writes. A transactional outbox, an idempotent bridge, or a controlled cutover phase is usually safer than publishing independently to two brokers from separate code paths.

### 15.1. Signs It Is Time to Revisit the Choice

- Queue age or consumer lag grows continuously despite reasonable scaling.
- Retention/storage costs exceed budget.
- Frequent replays are needed yet the current transport does not support them conveniently.
- Multiple systems end up building custom workarounds for routing, retries, or ordering.
- The broker or library reaches end-of-life.
- Operational incidents frequently exceed the team's capacity.
- Security, data residency, or compliance requirements change.
- Real-world workload differs drastically from prototype load.

Do not swap technologies merely because a new product appeared. Identify which requirements changed and what evidence shows the previous choice no longer fits.

## 16. Common Mistakes During Technology Reviews

1. **Picking a product before describing requirements.** Easily turns every problem into a fit for a familiar tool.
2. **Confusing frameworks with brokers.** Spring Integration orchestrates flows; brokers handle storage/distribution per their own semantics.
3. **Scoring before hard gates.** A high-scoring option that fails durability/security must still be rejected.
4. **Using unrepresentative benchmarks.** Small payloads, one producer, and one consumer do not reflect production workloads.
5. **Not testing failures.** Happy paths do not prove redelivery, recovery, idempotency, or DLQ.
6. **Relying on the phrase "exactly-once".** You must define scope, transactions, and side effects; a message ID alone does not produce exactly-once.
7. **Ignoring ordering.** Queues/partitions/concurrency/redeliveries can alter observed ordering from expectations.
8. **Not measuring operability.** Missing queue age, lag, retry count, and DLQ alerts make recovery hard.
9. **Picking incompatible versions.** Check compatibility matrices across Java, Spring Boot, Spring Integration, Spring AMQP/Kafka/JMS, and brokers.
10. **Failing to record assumptions.** Future ADR readers will not know which workload the scores assumed.
11. **Skipping post-rollout verification.** A passing prototype does not guarantee production behavior when topology, network, and load differ.

## 17. Review Checklist from Requirements to Results

### Requirements
- [ ] Owners have confirmed functional and non-functional requirements.
- [ ] Throughput, latency, retention, availability, and recovery targets exist.
- [ ] Interaction models, consumer topologies, and ordering requirements are defined.
- [ ] Hard constraints are separated from preferences.

### Architecture and Selection
- [ ] Message contracts, patterns, transports, brokers, and integration frameworks are clearly distinguished.
- [ ] Selected an appropriate shortlist and documented why other candidates were excluded.
- [ ] Hard gates were checked before weighted scoring.
- [ ] Compatibility checked across Java, Spring, and broker/client versions.

### Prototype and Verification
- [ ] Prototype uses near-production payloads, topology, and concurrency.
- [ ] Tests cover happy path, timeouts, restarts, redelivery, duplicates, and malformed messages.
- [ ] Load tests, security tests, and schema/contract tests are included.
- [ ] Metrics/logs/traces prove the results.
- [ ] Every acceptance criterion has a pass/fail status and evidence link.

### Decision and Operations
- [ ] ADR records context, options, decision, consequences, and revisit conditions.
- [ ] Runbooks exist for retries, DLQ, replay, restarts, and failover.
- [ ] Dashboards/alerts cover backlogs, lag, errors, and latency.
- [ ] Rollout/cutover plan and post-release business outcome verification exist.

## References

- [Spring Boot — Messaging](https://docs.spring.io/spring-boot/reference/messaging/index.html): integrations for JMS, AMQP/RabbitMQ, Kafka, Pulsar, and STOMP.
- [Spring Boot — Spring Integration](https://docs.spring.io/spring-boot/reference/messaging/spring-integration.html): starters, auto-configuration, pollers, and Spring Integration transport modules.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html): building IntegrationFlows and connecting flows via MessageChannels.
- [Spring Integration — AMQP Support](https://docs.spring.io/spring-integration/reference/7.1/amqp.html): inbound/outbound channel adapters, gateways, and AMQP-backed channels.
- [Spring Integration — AMQP-backed Channels](https://docs.spring.io/spring-integration/reference/7.1-SNAPSHOT/amqp/channels.html): distinguishing point-to-point, publish-subscribe, and channel persistence goals.
- [Spring for Apache Kafka — Reference](https://docs.spring.io/spring-kafka/reference/kafka.html): producers, listeners, partitions/offsets, transactions, serialization, monitoring, and error handling.
- [Spring for Apache Kafka — Project and Compatibility](https://spring.io/projects/spring-kafka): features and compatibility matrix for Spring Kafka, Spring Integration for Kafka, Kafka client, and Spring Boot.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): interaction models, codecs, RSocketRequester, and server auto-configuration.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): two independent confirmation mechanisms and limits to understand when verifying delivery.
- [Spring AMQP — Request/Reply](https://docs.spring.io/spring-amqp/reference/amqp/request-reply.html): request/reply and publisher confirms in Spring AMQP.
