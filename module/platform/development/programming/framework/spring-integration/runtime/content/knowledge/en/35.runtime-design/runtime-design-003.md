# Separating Stateless and Stateful Flows in Spring Integration Runtime

## 1. Design Goal: Where Does State Live, Who Owns It, and Who Recovers It?

In the **SPRING_INTEGRATION_RUNTIME** module, messages are orchestrated through channels, endpoints, consumers, pollers, and executors. These components can execute synchronously, asynchronously, via brokers, or backed by message stores. A sound design answers not only "where does the message go?" but also **"where is the state needed to process the message stored, for how long, and what happens when an instance restarts?"**

The topic **Runtime Design → Separating Stateless and Stateful Flows** focuses on two categories of processing:

- **Stateless processing:** the outcome of each invocation is determined solely by the inputs and dependencies at that call, without needing to maintain per-logical-workflow progress in handler memory across messages. Examples include payload normalization, schema validation, field mapping, and pure routing rules.
- **Stateful processing:** must store or reference information from other messages, prior attempts, or business state over time. Examples include an aggregator waiting for all parts, a resequencer buffering out-of-order messages, deduplication using a metadata store, a process manager awaiting callbacks, a delayed message scheduler, and an idempotent receiver.

**Key takeaway:** a *stateless handler* does not imply a *stateless end-to-end flow*. A pure transformer may receive messages from a durable `QueueChannel` and emit them into an aggregator backed by a `MessageGroupStore`; the overall flow still carries state in queues, group stores, lock registries, and business resources. Conversely, a handler without a `Map` field can still depend on database state and therefore is not a pure transformation in the business sense.

### Design Questions to Answer Before Writing Code

1. Can a single message be processed independently, or does it require **multiple messages sharing a correlation key**?
2. Is state needed only for the duration of a single invocation, or must it survive until subsequent messages?
3. When a pod restarts, must the state be recovered?
4. Do multiple JVMs concurrently process the same group/key; who acquires locks and who emits results?
5. Do we need ordering, deduplication, timeouts, or release/expiry of incomplete groups?
6. At what point is the message acked/committed; can errors/retries duplicate side effects?
7. How large can state grow, when is it cleaned up, and who pays the storage/locking cost?

~~~mermaid
flowchart LR
    P["Producer / ingress"] --> N["Stateless island\nnormalize • validate • route"]
    N --> Q["Durable queue / channel\nwhen needed"]
    Q --> S["Stateful island\naggregate • resequence • dedupe"]
    S --> O["Stateless island\nformat • dispatch"]
    D[("MessageGroupStore / MetadataStore")] <--> S
    L["LockRegistry / transaction"] -.-> S
    O --> R["Outbound adapter"]
    M["Metrics / traces / operations"] -.-> N
    M -.-> S
    M -.-> O
~~~

This is a **responsibility separation diagram**, not a mandate that every flow needs a persistent queue or database. For small workloads, everything may run in one JVM; when durability and multi-node execution are required, state boundaries must be explicit from the design phase.

## 2. Exact Definition: Stateless at Which Scope?

| Scope | What Does "Stateless" Mean? | Examples and Notes |
| --- | --- | --- |
| **Method invocation** | Uses no leftover values from previous invocations | `trim`, JSON decoding, data validation |
| **Handler object** | Bean holds no mutable business progress across messages | Stateless `@Transformer`, `@ServiceActivator` |
| **Message pipeline** | Each message traverses the flow without needing other messages | Simple enrichment and one-to-one conversions |
| **Runtime infrastructure** | No pending queues, retry state, or channel storage | Very rarely strictly true for async flows |
| **Business process** | No need to query long-lived workflow state | Sending a standalone notification |
| **Distributed system** | No state requiring synchronization across JVMs | App tier may be stateless while DB/broker remain stateful |

Never use the term "stateless" without specifying its **scope**. For example:

~~~java
String normalize(String value) {
    return value.trim().toUpperCase(Locale.ROOT);
}
~~~

The function above is *nearly pure* given the `String` input and `Locale.ROOT`. However:

~~~java
Order enrich(Order order) {
    Customer customer = customerRepository.findById(
            order.customerId()).orElseThrow();
    return order.withCustomerTier(customer.tier());
}
~~~

The bean still holds no mutable fields between requests, yet the result depends on **database state**. Here the handler is *application-instance stateless* but *business-state-dependent*. You must evaluate transactions, consistency, and caching during replays.

### `Message` Is Data, Not a State Store

Spring Messaging uses `Message<T>` consisting of a payload and API-level immutable `MessageHeaders`. Headers such as `correlationId`, `sequenceNumber`, and `replyChannel` are metadata traveling with a single message. They **do not automatically create persistent workflow state**.

A message carrying `correlationId=batch-42` is merely a **state lookup key**; previously arrived parts still have to live in a `MessageGroupStore` or another store.

## 3. Signs That a Processing Step Requires State

A processing step is **stateful with respect to a logical workflow** if it must answer any of these questions:

- "Have all N parts of the batch arrived yet?"
- "Sequence 3 has arrived; do we need to wait for sequence 2?"
- "Has this Event ID already been processed?"
- "Was a request sent and are we waiting for a callback/timeout from another service?"
- "Has the correlation group expired or been marked complete?"
- "Which group of messages should be released after a delay?"
- "Did the previous attempt commit while its acknowledgement was lost?"
- "After a restart, in what state should pending work resume?"

These answers generally do not belong in an in-memory `HashMap` field inside a multi-pod handler if losing state on restart is unacceptable.

### Quick Classification Table of EIPs in Spring Integration

| Component / Pattern | Nature | Where Does State Live? |
| --- | --- | --- |
| Pure transformer | Usually stateless | Payload/headers within invocation |
| Filter with pure predicate | Usually stateless | Input and routing decision |
| Header/payload router | Usually stateless | Channel selection rules |
| DB-backed enricher | Bean can be stateless; business logic is state-dependent | Underlying DB/cache dependency |
| Pure service activator | Can be stateless | Invocation |
| `DirectChannel` | Not a persistent message queue | Runtime dispatcher/subscriptions |
| `ExecutorChannel` | Asynchronous; holds pending tasks | Executor queue and active workers |
| `QueueChannel` | Stateful regarding queued waiting | In-memory queue or configured store |
| Aggregator | **Stateful** | `MessageGroupStore`, correlation groups |
| Resequencer | **Stateful** | Message group and sequence state |
| Delayer | **Stateful** | Scheduler/delayed messages, store if configured |
| Idempotent receiver | **Stateful** | `MetadataStore`/deduplication store |
| Accept-once file filter | **Stateful** | In-memory or persistent metadata store |
| Gateway awaiting reply | Temporarily stateful for request/reply | Pending reply context/correlation |
| Outbound TCP client | **Connection-stateful**, even if business handler is stateless | Socket/session/connection factory |
| Transactional handler | Resource state inside transaction | DB/broker/transaction manager |

**You do not need a stateful EIP for every piece of logic that reads a database.** You can separate them: stateless validation/enrichment upfront, and stateful aggregation or workflow coordination at an independent boundary.

## 4. Why Separate "Stateless Islands" from "Stateful Islands"?

Suppose you process line items across many orders. Each line item must be normalized and validated independently, and then **three items** sharing the same `batchId` must be collected before emitting one result.

A monolithic flow often ends up looking like:

~~~java
class BadOrderHandler {
    private final Map<String, List<String>> parts = new HashMap<>();

    void handle(Message<String> message) {
        String batchId = (String) message.getHeaders().get("batchId");
        String normalized = message.getPayload().trim().toUpperCase();
        parts.computeIfAbsent(batchId, key -> new ArrayList<>())
             .add(normalized);

        if (parts.get(batchId).size() == 3) {
            sendBatch(parts.remove(batchId));
        }
    }
}
~~~

The snippet above is an **illustrative anti-pattern**; imports are omitted. Its flaws:

1. `HashMap`/`ArrayList` are not thread-safe under `ExecutorChannel`, multiple consumers, or poller concurrency.
2. Process restart loses all incomplete batch parts.
3. Across multiple pods, each instance sees only a subset of events.
4. "Reached 3" counts duplicates if the broker redelivers.
5. Calling `remove()` before downstream commit can lose output on failure.
6. Without expiry, memory leaks unboundedly on incomplete groups.
7. Hard to observe group age, group size, retry attempts, and lock contention.
8. No clear contract for arrival ordering, invalid events, or partial batches.

Instead of stuffing everything into a mutable singleton handler, split it into:

~~~mermaid
flowchart LR
    I["rawItems"] --> T["Stateless transformer"]
    T --> V["Stateless validation"]
    V --> C["normalizedItems channel"]
    C --> A["Stateful Aggregator"]
    A --> B["completedBatches"]
    B --> O["Stateless output formatter"]
    O --> X["Outbound sender"]
    G[("MessageGroupStore")] <--> A
    K["LockRegistry"] -.-> A
    E["Error / discard flow"] -.-> V
    E -.-> A
~~~

### Benefits of Explicit Boundaries

- **Independent scaling:** CPU-bound normalization scales via stateless workers; the aggregator is constrained by correlation keys and the message store.
- **Swappable infrastructure:** move from an in-memory `SimpleMessageStore` in a demo to a persistent store without rewriting transformers.
- **Fault testing:** kill the aggregator mid-batch and verify recovery; stateless parts remain trivial to unit test.
- **Observability:** measure input rates, pending groups, group expirations, and output rates at the exact right stages.
- **State ownership:** prevent business handlers from mutating maps outside transactions and locking policies.

## 5. Classifying State by Lifetime and Durability

| State Kind | Lifetime | Applicable Tools | Risks |
| --- | --- | --- | --- |
| Local invocation | Microseconds/seconds | Local variables | Not shared; not persisted |
| Ephemeral session | Socket/connection lifetime | TCP connection factory, adapters | Disconnect drops session |
| In-memory queue/group | Until JVM stops or cleanup | `QueueChannel`, `SimpleMessageStore` | Restart loses pending data |
| Persistent message group | Across invocations/restarts | `JdbcMessageStore`, Redis/Mongo store per module | Serializers/migrations/expiry/locking |
| Deduplication metadata | Per retention window | Persistent `MetadataStore` | Bad TTL causes duplicates or unbounded growth |
| Business transaction | Until commit/rollback | RDBMS + transaction manager | Partial side effects/replays |
| Long-running saga state | Hours/days/weeks | Durable workflow store/process manager | Timeouts/cancellations/versioning |
| Observation state | Per trace/span or retention | Micrometer, logs, trace backends | Lost correlation or high cardinality |

Using Redis does not automatically give you the transaction semantics you expect. **Store type, transaction manager, lock registry, serialization, and retries** must be verified together.

### `MessageStore` and `MetadataStore` Are Different

- **`MessageStore` / `MessageGroupStore`:** stores messages or collections of messages by group; aggregators/resequencers inspect members, counts, release, and expiry.
- **`MetadataStore`:** small key-value store for metadata such as processed-file markers or accepted event IDs.
- **Business database:** stores authoritative order/payment state; never replace it with a `MessageGroupStore` just because the store holds a few messages.
- **Broker:** holds backlogs and delivery/ack state; does not manage an aggregator's JVM correlation/release strategies on its own.

Use the right store to enforce business invariants rather than stuffing everything into a shared `Map<String, Object>`.

## 6. Three Principles for Designing State Boundaries

### Principle A: Clean Boundary Between Pure Transforms and Group Coordination

In the stateless section:

- Explicit input and output types/headers.
- Never keep mutable per-order state in a singleton bean.
- Deterministic results wherever possible.
- If external lookups exist, specify consistency/caching and timeouts.
- On exceptions, callers/error flows know how to retry the individual message.

In the stateful section:

- Published **correlation strategy**.
- Explicit **release condition** and **expiry/timeout policy**.
- Defined owner of group state and concurrency control.
- Store durability, recovery/replay, and deduplication if required.
- Outputs emitted under a clear transaction/ack contract.
- Intentional handling of late messages and duplicates.

### Principle B: Never Route State Across a Channel Without Understanding the Channel's Semantics

`DirectChannel` normally runs handlers synchronously; `ExecutorChannel` introduces an async thread boundary; `QueueChannel` buffers messages for a poller; brokers cross process boundaries. Each choice alters transaction propagation, failure visibility, queue wait, and lifecycle.

### Principle C: Establish Consistency Before Optimizing Throughput

Completing a group after N messages **only works if N counts valid unique parts**, not raw deliveries. Under at-least-once transport, a redelivered part can be counted twice without deduplication. Always start design from business invariants before sizing concurrency and scale.

## 7. Correlation Key: Identifying a Logical Group

An aggregator needs to know which messages belong to the same group. In Spring Integration, the `correlationId` header is commonly used to link messages; splitters can also attach `sequenceNumber` and `sequenceSize` to generated parts.

Example message:

~~~java
Message<String> part = MessageBuilder
        .withPayload("  line-1  ")
        .setHeader("batchId", "batch-42")
        .setHeader("eventId", "evt-line-1")
        .setHeader("sequenceNumber", 1)
        .setHeader("sequenceSize", 3)
        .build();
~~~

The strings `"batchId"`, `"sequenceNumber"`, and `"sequenceSize"` above are application headers in the snippet. In production code, when standard headers are needed, reference constants like `IntegrationMessageHeaderAccessor.CORRELATION_ID`, `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER`, and `...SEQUENCE_SIZE` instead of spelling strings manually to avoid typos. When using standard splitters, many sequence/correlation headers are populated automatically.

Questions to answer:

- Is `batchId` **unique within the retention window**?
- If an order has 3 line items, where does the number 3 come from?
- Can messages arrive out of order?
- If `batch-42` already completed and a duplicate arrives late, does it open a new group?
- If a batch never becomes complete, does it expire after a timeout or emit a partial result?
- If a consumer shifts between pods, which store holds state for `batchId`?

### Avoiding Collisions

An ID like `"42"` can collide across tenants or years. Include meaningful namespacing or use a globally unique logical key such as:

~~~text
correlationKey = tenantId + ":" + orderId + ":" + batchVersion
~~~

Never embed secrets inside raw correlation headers if headers may traverse brokers or logs. IDs must remain stable across retries and redeliveries.

## 8. Aggregator: The First Stateful Building Block

The Spring Integration Aggregator is an EIP that collects messages sharing a correlation group in a `MessageGroupStore`, evaluates a `ReleaseStrategy`, and emits output when the condition is satisfied.

~~~mermaid
flowchart TD
    M1["part A / batch-42"] --> AG["Aggregator"]
    M2["part B / batch-42"] --> AG
    M3["part C / batch-42"] --> AG
    AG <--> ST[("MessageGroupStore\nbatch-42 -> members")]
    AG --> R{"ReleaseStrategy?"}
    R -->|Not yet| W["Keep group pending"]
    R -->|Ready| OP["Build aggregate result"]
    OP --> OUT["completedBatches"]
    OUT --> ACK["Output processing + business commit"]
~~~

### CorrelationStrategy

The group ID selector must be deterministic with explicit null handling. Example header lookup:

~~~java
CorrelationStrategy byBatchId =
        message -> message.getHeaders().get("batchId");
~~~

If the header is null, do not lump all unknown messages into a shared `null` group. Route invalid messages to a discard/error flow or reject them before the aggregator.

### ReleaseStrategy

A release strategy can check the count of received parts:

~~~java
ReleaseStrategy fixedThreeParts =
        group -> group.size() >= 3;
~~~

This is a **demo rule**, unsafe when duplicate deliveries are counted as distinct parts. For real business logic, validate **distinct sequence numbers/event IDs**, expected counts, and invariants before release.

### OutputProcessor

Upon release, a `MessageGroupProcessor` constructs the output from the parts. You can use the aggregator's default processor for demos, or a custom processor controlling order and retained data. Do not assume aggregation output is automatically a string, a canonically ordered list, or a message preserving all original headers; check your processor and API version.

## 9. Java 17 + Spring Boot: Separating Two IntegrationFlows

The following example runs with Spring Boot and compatible Spring Integration core/starter dependencies. Create `StatelessStatefulFlowDemoApplication.java` in package `demo.integration`.

**Technical objective:** a stateless flow normalizes each line; a stateful flow collects **three messages sharing the same `batchId`**; output goes to a `QueueChannel` consumed by an `ApplicationRunner`. It uses an in-memory `SimpleMessageStore` for demonstration; **do not** treat this as durable across restarts.

~~~java
package demo.integration;

import java.util.List;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class StatelessStatefulFlowDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StatelessStatefulFlowDemoApplication.class, args);
    }

    @Bean("rawLines")
    MessageChannel rawLines() {
        return new DirectChannel();
    }

    @Bean("normalizedLines")
    MessageChannel normalizedLines() {
        return new DirectChannel();
    }

    @Bean("completedBatches")
    PollableChannel completedBatches() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore batchGroups() {
        // Demo only: state resets when the JVM restarts.
        return new SimpleMessageStore();
    }

    @Bean
    IntegrationFlow normalizationFlow() {
        return IntegrationFlow.from("rawLines")
                .transform(String.class,
                        value -> value.trim().toUpperCase(Locale.ROOT))
                .channel("normalizedLines")
                .get();
    }

    @Bean
    IntegrationFlow aggregationFlow(MessageGroupStore batchGroups) {
        return IntegrationFlow.from("normalizedLines")
                .aggregate(spec -> spec
                        .correlationStrategy(m ->
                                m.getHeaders().get("batchId"))
                        .releaseStrategy(group -> group.size() >= 3)
                        .messageStore(batchGroups)
                        .expireGroupsUponCompletion(true))
                .channel("completedBatches")
                .get();
    }

    @Bean
    ApplicationRunner demonstrate(
            @Qualifier("rawLines") MessageChannel input,
            @Qualifier("completedBatches") PollableChannel output) {

        return args -> {
            String batchId = "batch-42";

            for (String value : List.of(
                    " red ", " blue ", " green ")) {

                boolean accepted = input.send(
                        MessageBuilder.withPayload(value)
                                .setHeader("batchId", batchId)
                                .setHeader("eventId",
                                        "evt-" + value.trim())
                                .build());

                if (!accepted) {
                    throw new IllegalStateException(
                            "Input channel rejected a part");
                }
            }

            Message<?> result = output.receive(2_000);
            if (result == null) {
                throw new IllegalStateException(
                        "Batch was not released");
            }

            System.out.println(
                    "AGGREGATED payload=" + result.getPayload());
        };
    }
}
~~~

### Notes for Newer Spring Integration Versions

The example uses `IntegrationFlow.from(...)` and Java DSL endpoint specs. Do not import `org.springframework.integration.dsl.IntegrationFlows` from older guides if that API is absent in your version. The `aggregate`, `correlationStrategy`, `releaseStrategy` overloads and `MessageGroupStore` configuration should be verified against your actual Spring Integration BOM during build/QA.

### What Happens on Each Event?

1. `ApplicationRunner` sends three line messages to `rawLines`.
2. `DirectChannel` dispatches synchronously through the stateless transform.
3. The transformer produces a trimmed uppercase payload and forwards headers (including `batchId`) per Spring Integration's contract.
4. The stateful aggregator selects the group using `batchId`.
5. `SimpleMessageStore` holds the parts until three arrive.
6. `ReleaseStrategy` returns true, and the aggregator builds the result and sends it to `completedBatches`.
7. `QueueChannel.receive(timeout)` receives the output.
8. After release, `expireGroupsUponCompletion(true)` cleans up the group per implementation; **a late duplicate policy is still required in production**.

Output may look like:

~~~text
AGGREGATED payload=[RED, BLUE, GREEN]
~~~

**Do not hardcode exact payload strings or ordering if code uses concurrent delivery.** The default aggregation processor, headers, and output ordering can vary by flow/config. In a sequential single-JVM demo, the list output illustrates the general concept.

### Production Notes

- `SimpleMessageStore` holds state only in memory and **loses it on restart**.
- A group with 2/3 parts will hang indefinitely without a timeout/expiry policy.
- Duplicate events can falsely satisfy `size() == 3`.
- Never place an in-memory `QueueChannel` ahead of outbound side effects if persistence across restarts is required.
- Ownership/locking is required when multiple nodes process the same group in a shared store.
- Transactions or outbox/durable workflows are needed if release and output emission must not be lost.

## 10. Preparing Dependencies and Running the Demo

If using a Spring Boot 3.x project compatible with Spring Integration 6.x, declare dependencies managed by the Spring Boot BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Never mix an incompatible Spring Integration major version with your Spring Boot/Spring Framework version. When running `StatelessStatefulFlowDemoApplication`, expect one message on `completedBatches` after the third part. Try changing the `batchId` of the third part: the first group will hold only two messages and no result will be released yet.

In STEP 4, the example is written only into Markdown; Gradle or academic QA has not yet been run. When integrating into a project, run compilation tests and integration tests against actual dependencies.

## 11. Separating Flows with Channel Boundaries: DirectChannel or Queue?

The stateless and stateful flows in the example are connected via `DirectChannel`, meaning messages travel from the transformer to the aggregator on the **same call stack**. In a demo, this makes behavior and errors easy to observe.

In production, choose the boundary based on SLA:

| Boundary | When Appropriate | Risks / Costs |
| --- | --- | --- |
| `DirectChannel` | Sync processing needed; transaction may span from caller | Slow handlers stall producers |
| `ExecutorChannel` | Decouple threads and raise concurrency | In-memory queue/tasks, separated transaction context |
| `QueueChannel` + poller | Rate-control via polling, buffer backlog | Delay, queue capacity, durability depends on store |
| Broker channel adapter | Separate services/processes, at-least-once delivery | Ack/replay/schema, duplicates, network costs |
| Reactive channel | Non-blocking/demand-aware flows | Different subscription/error/transaction semantics |

**The right separation question:** if the stateless stage is healthy while the stateful store slows down, should producers keep sending? Only if there is an appropriate bounded/durable buffer, explicit backpressure policy, and clear message retention.

~~~mermaid
flowchart TD
    P["Stateless preprocess workers"] --> C{"Boundary?"}
    C -->|sync| D["DirectChannel\nproducer absorbs aggregator backpressure"]
    C -->|async in-memory| E["ExecutorChannel\nsuitable for non-durable tasks"]
    C -->|durable buffer| Q["Broker or persistent queue"]
    D --> S["Stateful aggregator"]
    E --> S
    Q --> S
    S --> O["Downstream"]
~~~

Adding an executor to raise throughput does not fix a correlation key serialized behind a lock, and can increase contention among concurrent writers hitting the stateful store.

## 12. State Ownership and Scaling Out by Correlation Key

A stateless transformer can typically process messages on any instance. An aggregator, however, requires all parts of the same group to reach **the same state**.

### Three Common Strategies

**Strategy A — Single owner by partition key.**

The broker partitions by `batchId`/`correlationId`; all parts sharing a key are handled by one consumer/partition owner at a time per contract. This reduces contention, though rebalances, failovers, and state recovery still must be handled.

**Strategy B — Shared MessageGroupStore + distributed lock.**

Multiple JVMs access a shared durable store; mutating a message group is coordinated with appropriate locks and transactions. Spring Integration provides `LockRegistry` implementations (JDBC/Redis/ZooKeeper depending on module); configure lock keys, leases, and failure handling properly.

**Strategy C — External workflow coordinator.**

For long-lived sagas and callbacks spanning days, persist state in a business DB/workflow engine; Spring Integration merely transports events, transforms, routes, and invokes the coordinator. Suitable when lifecycles are more complex than an aggregator message group.

| Strategy | Advantages | Risks |
| --- | --- | --- |
| Partition-key owner | Low write contention | Hot keys, rebalancing, complex recovery |
| Shared store + lock | Flexible failover, multi-node | Lock latency, contention, consistency |
| Durable coordinator | Explicit business state, timeouts/versioning | Implementation complexity, operational cost |
| Local in-memory state | Simple, fast | Restarts lose groups, broken scale-out if keys spread |

**A shared `MessageGroupStore` does not automatically guarantee multi-node correctness.** Inspect the exact implementation, serialization, transaction isolation, and lock registry in the same application. If only `SimpleMessageStore` is used, state is not shared across JVMs.

## 13. LockRegistry, Transactions, and Critical Sections

When two workers receive parts of the same `batchId`, they may concurrently:

1. Read group size = 2;
2. Add the third or a duplicate part;
3. Decide to release;
4. Emit output;
5. Mark the group complete/remove it.

Without synchronization, output may be missed or emitted twice. Locks and transactions must protect the **business invariant**, not just an isolated `addMessageToGroup()` call.

~~~mermaid
sequenceDiagram
    participant W1 as Worker A
    participant W2 as Worker B
    participant L as LockRegistry
    participant S as MessageGroupStore
    W1->>L: lock(batch-42)
    W2->>L: lock(batch-42) [wait]
    W1->>S: add part + check release
    W1->>S: mark group / cleanup
    W1->>L: unlock(batch-42)
    L-->>W2: acquired
    W2->>S: load current group state
    W2->>L: unlock(batch-42)
~~~

### Lock Contention Affects Throughput

- Concentrated correlation keys (hot groups) serialize updates.
- Lock leases/TTLs that are too short can let multiple owners process the same key if tasks take long.
- Lock TTLs that are too long or unreleased on error can stall groups.
- Distributed locks depend on network/store calls and can inflate p95/p99 latency.
- Do not scale concurrency indefinitely if threads mainly contend for the same critical section.

### Do Not Confuse Sender Transactions with Aggregator Transactions

A synchronous `DirectChannel` can keep a transaction along the call stack if configured properly. `ExecutorChannel`/poller/broker boundaries introduce async handoffs that may need separate transactions on the worker. Imperative Spring transactions are typically thread-bound and do not automatically cross async boundaries.

If you need **atomicity** between the state store and business DB, verify whether they share a transaction manager/resource. Without distributed transactions, consider **outbox/inbox/idempotency** to mitigate lost or duplicated outputs on crashes between steps.

## 14. Persistence: A Durable MessageStore Is Insufficient If Ack Timing Is Wrong

Suppose an application receives a part from a broker, saves it to `JdbcMessageStore`, and wants to ack the source:

~~~text
broker receive(part)
    -> add part to group store
    -> broker ack
    -> later release full group -> downstream
~~~

If the app acks before the state store commits, a crash can lose the part. If the store commits and the broker ack fails, the source redelivers the part, potentially creating a **duplicate group member**. Therefore you need:

- Clear transaction/ack boundaries and commit ordering.
- Stable `eventId` or `partId` for each logical part.
- Deduplication before adding a part to the group—never treat raw group size as unique part count under at-least-once delivery.
- Durable group state and retention long enough for retries/late parts.
- Reliable output emission after release using an outbox or recoverable workflow.
- Replay capability if the state store corrupts or schema versions change.

`JdbcMessageStore` is one persistence option, yet correctness depends on schema, serializers, indexes, transaction managers, and read/write semantics. Redis/Mongo/other stores differ as well; never swap APIs/classes assuming identical semantics.

## 15. Group Timeouts, Expiry, and Partial Results

A stateful flow cannot retain incomplete groups forever. Suppose a batch needs three line items but one event is lost; an aggregator holding two parts forever causes:

- Growing message group counts across batches.
- Store bloat and unbounded retention.
- Lock registries/metadata retaining obsolete keys.
- Users unable to tell whether an order is pending or failed.
- Alerts claiming "flow is running" while business SLAs fail.

Spring Integration aggregators support **group timeouts**, **expiring groups**, **sending partial results on expiry**, and **discard/expiry handling** depending on API/config/version. Define clearly:

| Scenario | Possible Policy | Consequence |
| --- | --- | --- |
| All three valid parts arrive | Release full group | Produce output and mark completed |
| Incomplete after 2 minutes | Expire and emit error/timeout event | Must record reason and replay capability |
| Incomplete, yet partial result valid | Send partial result on expiry | Use only when the business genuinely accepts partials |
| Part arrives after expiry | Reject/quarantine/reopen per policy | Must not silently duplicate output |
| Duplicate after completion | Dedupe/reply with previous outcome | Do not unintentionally start a new batch |
| Transient state store error | Bounded retry, do not unconditionally ack | Prevents message loss |

### Why Group Timeout Is Not Request Timeout

An HTTP gateway timeout may end the caller's request while the aggregator group still holds state and may release later. Conversely, a group can expire while a caller still holds the connection open. Set timeouts at the **right scope**: gateway reply, aggregator lifetime, broker delivery attempt, and business SLA are four distinct concepts.

### Do Not "Send Partial Results" Just to Free Memory

If an order requires all three line items to compute a total, emitting a two-item list as a success is a business bug. On timeout, emit a **failure/compensation event** carrying the group key, expected/received part IDs, and timestamp to a durable recovery channel. Then clean up state via a runbook instead of silently dropping it.

## 16. Late Messages and Tombstone / Closed-Group Markers

Under at-least-once delivery, a part may arrive **after the aggregator has already released**. If you enable `expireGroupsUponCompletion(true)` and remove the group, a late part can reopen a brand-new group with the same `batchId`.

Thus you need an independent **closed group** policy if the business forbids reopening:

~~~text
batchId=batch-42
expectedPartIds={P1,P2,P3}
received: P1,P2,P3 -> release -> commit output
closedGroupStore[batch-42] = completed
late arrival P2 -> reject/dedupe; do not open new group
~~~

Such a marker can live in a metadata store, inbox, or business DB with a TTL/retention at least as long as the maximum redelivery window. However, `closedGroupStore.put` and `output commit` must be **coordinated**: if marked complete before output actually commits and a crash occurs, subsequent retries may be skipped.

### Retention Must Not Be Guessed

Suppose the broker can replay for 7 days while the closed marker only lasts 1 hour. After 2 days, a duplicate can start a new batch. Align retention policies with source and business semantics; for critical events, completed state in the business DB persists long-term.

## 17. Idempotent Receiver: Stateless Handlers Need State to Prevent Duplicates

Suppose a service activator simply does:

~~~java
void chargeCard(Payment payment) {
    paymentGateway.charge(payment);
}
~~~

The bean holds no mutable fields, yet if the broker redelivers the same `eventId`, the charge may happen **twice**. Thus **business statelessness does not replace idempotency**.

Spring Integration provides the **Idempotent Receiver** pattern and `IdempotentReceiverInterceptor`, backed by a metadata store and key selector. A basic policy stores markers keyed by a stable event ID.

Illustrative CAS logic on `ConcurrentMetadataStore`:

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;

final class DedupGate {

    private final ConcurrentMetadataStore metadataStore;

    DedupGate(ConcurrentMetadataStore metadataStore) {
        this.metadataStore = metadataStore;
    }

    boolean firstSeen(String eventId) {
        return metadataStore.putIfAbsent(
                "event:" + eventId, "claimed") == null;
    }
}
~~~

This snippet demonstrates **atomic per-key claiming for stores supporting that contract**, not full crash correctness. If the claim succeeds and the handler crashes before DB commit, all future retries get rejected even though the side effect never happened. Correctness requires:

1. A transactional inbox or `NEW/PROCESSING/COMPLETED/FAILED` state machine.
2. Atomicity between claim and effect when sharing the same resource/transaction.
3. Retries/leases/reconciliation for stuck `PROCESSING` records.
4. Retention, cleanup, and stable unique keys.
5. An appropriate response when receiving a duplicate of an already-completed item.

### Deduplicate Before the Aggregator

For batch `P1,P2,P3`, if `P2` redelivers:

~~~text
P1 -> group size 1
P2 -> group size 2
P2 duplicate -> group size 3 (wrong!)
P3 -> arrives late, group already released
~~~

Deduplicate by **part ID** before group insertion, or use a release strategy checking distinct members instead of raw `group.size()`. Never use `MessageHeaders.ID` if the adapter generates new IDs on redelivery; select the logical part/event ID from the source.

## 18. Resequencer: Holding State to Restore Order

A stateless handler can process independent messages regardless of arrival order. A **resequencer**, however, must hold ahead-of-order messages while waiting for earlier sequences:

~~~text
Arrival:   seq=3, seq=1, seq=2
Expected:  seq=1, seq=2, seq=3
~~~

To reorder, the resequencer tracks state per correlation group:

- Group ID;
- Sequence numbers received so far;
- Expected size or flush condition;
- Store/lock;
- Timeout for missing sequences;
- Deduplication and gap policies.

Comparison table:

| Concern | Aggregator | Resequencer |
| --- | --- | --- |
| Multiple messages into one result | **Yes** | Usually no |
| Holds a pending group | Yes | Yes |
| Needs correlation/sequence | Possible | Usually yes |
| Needs release strategy | Yes | Yes |
| Output | One aggregated message or result | Multiple messages in sequence order |
| Late/duplicate gaps | Must handle | Must handle |

**Do not solve out-of-order issues merely by adding executor threads.** Raising concurrency often makes arrival order even less predictable. If ordering is a business invariant, design key partitioning, stateful resequencing, and bounded gap policies explicitly.

## 19. Delayers, Schedulers, and Deferred Work Are Also Stateful

`Delayer` holds messages until a release time. Statefulness here is not necessarily a `List` inside a handler—it can be scheduled tasks, message groups/stores, and deadlines.

A process restart can lose delayed tasks if they live solely in memory. If the business requires sending a notification after 24 hours, you need a persisted schedule/workflow/outbox. In production:

- Define deadlines using **business timestamps**, not merely `Thread.sleep`.
- Persist pending messages and deadline state.
- Provide deadline cancellation/update contracts.
- Configure executor/scheduler capacities and timeouts.
- Ensure idempotency if a task runs while its ack is lost.
- Handle expiry/cleanup and replay on application restart.

A single cron/poller is not automatically sufficient to implement a highly durable saga/long-running workflow. Avoid "keeping state" in a singleton map when requirements exceed process lifetime.

## 20. Hidden Statefulness in Filters, Routers, Caches, and Adapters

Aggregators are not the only components with state. Several seemingly stateless components can harbor hidden state:

| Component | When Stateless? | When Does It Become Stateful? |
| --- | --- | --- |
| Filter | Pure predicate `amount > 0` | Filter tracks "seen IDs" or rate-limit counters |
| Router | `payload.type` selects channel | Router uses sticky assignments or mutable rule tables |
| Transformer | Pure field mapping | Transformer maintains mutable caches or incrementing sequences |
| Enricher | Side-effect-free lookup | Cache with refresh/expiry, network state |
| File inbound adapter | Reads new sources per source contract | Accept-once filter stores filenames/metadata |
| HTTP outbound | Holds no business progress | Connection pool still holds connection state |
| TCP client-mode | Handler may hold no workflow state | Connection factory/adapter holds sockets/sessions |
| Retrying advice | Individual invocations can retry independently | Retry context/attempt state, stateful retries |
| Claim-check | Replaces payload with a claim token | Claim-check message store retains payloads |

**Distinguish connection state from workflow state:** having a TCP socket or connection pool **does not force every downstream handler to run on a single stateful node**. However, adapters must manage reconnects, pending replies, and failure semantics at the right layer.

## 21. Managing State with a "Stateless → Durable Queue → Stateful" Structure

A reference design for batch processing:

~~~mermaid
flowchart LR
    IN["Kafka/JMS inbound"] --> S1["Stateless validate + normalize"]
    S1 -->|Invalid| ERR["Quarantine/DLQ"]
    S1 -->|Valid| Q[("Durable staging queue")]
    Q --> D["Part dedupe by eventId"]
    D --> A["Stateful aggregator by batchId"]
    A <--> MS[("Durable MessageGroupStore")]
    A -.-> LR["LockRegistry"]
    A --> OUT[("Outbox / committed result")]
    OUT --> S2["Stateless format + send"]
    S2 --> REM["Remote API / broker"]
    S2 --> REC["Retry / recovery path"]
~~~

### Why Place a Durable Queue in Between?

It creates a load-decoupling boundary:

- Stateless preprocessing scales independently and fast.
- When the aggregator/store slows down, the queue retains pending messages per retention policy.
- Downstream stateful workers can scale up/down within the concurrency contract.
- When stateful workers restart, pending messages remain in the broker/store **if ack/transactions are configured properly**.
- Enables measuring queue dwell time, queue age, and backlog.

**However**, a durable queue does not turn the whole flow into exactly-once. A producer may publish to the queue and crash before acking the source; messages can reappear. A consumer may commit state and crash before acking the queue. Deduplication and outboxes are still needed.

### When Should You Avoid Inserting a Queue?

- Very low latency requirements where a single synchronous transaction scope suffices and is verified.
- Small, stateless workloads that need no durability across restarts.
- Adding a queue complicates ordering/error/reply semantics without clear benefit.
- There is no clear owner for post-queue retries/acks.

Place channels based on **SLOs and failure boundaries**, not a blanket rule of "every step needs a queue".

## 22. Transactions and Retries: Wrong Scopes Lose or Duplicate State

Different scenarios:

| Case | What Happens | Risk |
| --- | --- | --- |
| Stateless validate throws before enqueue | Message never entered stateful store | Safe to retry per message |
| Aggregator store adds part then source ack is lost | Part persisted, source redelivers | Duplicate member |
| Aggregator releases then output send fails | Group may already be complete | Output lost without outbox/retry |
| Handler writes DB then throws before broker ack | Business commit already occurred | Duplicate side effect on redelivery |
| Error swallowed by `onErrorResume` in reactive chain | Publisher completes normally | Adapter may ack without persisted recovery |
| Poller stops mid-transaction | In-flight work may continue or roll back | Never assume stop == rollback |

### Retry Placement Must Match the Unit of Work

- Retrying a **stateless transform** usually requires no workflow progress state; bounded retries are reasonable for transient dependency failures.
- Retrying a **stateful group mutation** must protect part idempotency and transactions; avoid adding the same part repeatedly.
- Retrying **outbound side effects** must preserve business keys so receivers can deduplicate.
- Retrying an entire **outer Flux** can resubscribe to the source and replay already-completed messages; place per-event retries inside the inner publisher.

With `RequestHandlerRetryAdvice`, verify which handler the advice wraps; if group release and side effects share the same advice, multiple attempts can emit duplicate outputs. Do not equate advice retry counts with unique message counts.

### `ErrorMessage` Is Not Compensation

When a stateful aggregator fails, the error handler may emit an `ErrorMessage` carrying `MessagingException.failedMessage`/original message. While helpful for diagnostics, it **does not automatically roll back the state store** or clean up incomplete groups. Define an explicit policy: retry add, expire group, quarantine part, replay, or run a compensating transaction.

## 23. Message Headers and Correlation Must Survive Boundaries

When transitioning from a stateless flow to a stateful flow, preserve sufficient metadata:

| Header / Field | Purpose | Risk If Lost |
| --- | --- | --- |
| `eventId` / `partId` | Deduplicate logical parts | Duplicates go unrecognized |
| `batchId` / `correlationId` | Select message group | Parts enter wrong group or no group |
| `sequenceNumber` | Identify order/position | Incorrect resequencing/release |
| `sequenceSize` | Expected part count | Group never releases or releases early |
| `traceId` | Cross-thread/process observability | Logs cannot be correlated |
| `schemaVersion` | Decode/migrate persisted messages | Store unreadable after deploy |
| `replyChannel`/`errorChannel` | Route replies and errors | Lost replies or misrouted errors |
| `tenantId`/namespace | Isolate keys across tenants | Correlation collisions |

Headers such as `replyChannel` may contain references to bean/channel objects that broker serializers do not always support. **Do not blindly forward all internal headers over the network**; map per contract and use durable reply addresses/correlation keys.

When using `MessageBuilder.fromMessage(...)`, verify critical headers survive transformers, split/aggregate steps, and broker adapters. Never send raw `MessageHeaders.ID` as an idempotency key across retries because rebuilding a message can generate a fresh UUID.

## 24. Observing Stateful Islands with Metrics and Traces

An application can report 100% of endpoints with `isRunning()==true` while 80% of groups sit waiting on a final part and queue backlogs climb. You must monitor **progress**, not just lifecycle state.

| Metric (Suggested, Not Default) | Why It Matters |
| --- | --- |
| `flow.stateless.received.total` | Total messages entering preprocessing |
| `flow.stateless.invalid.total` | Messages rejected/quarantined |
| `flow.stateful.part.accepted.total` | Parts accepted into groups |
| `flow.stateful.part.duplicate.total` | Detects duplicates/replays |
| `flow.stateful.group.pending` | Count of incomplete groups |
| `flow.stateful.group.oldest.age` | Longest-stalled pending group |
| `flow.stateful.group.completed.total` | Throughput by logical group |
| `flow.stateful.group.expired.total` | Timeouts/partials/missing parts |
| `flow.stateful.lock.wait` | Per-key lock contention |
| `flow.stateful.store.read/write.duration` | Storage bottlenecks |
| `flow.queue.depth/oldest.age` | Producer outpacing consumer capacity |
| `flow.output.confirmed.total` | Results acked/committed |
| `flow.output.unknown.total` | Indeterminate outcomes |
| `flow.retry.attempts` | Retry pressure |
| `flow.error.recovered.total` | Recoveries successfully persisted |

Never use raw `eventId`, `batchId`, customer IDs, or full payloads as **metric tags** due to unbounded cardinality. Use endpoint names, event types, outcomes, and exception classes; place logical IDs in traces/logs governed by retention and privacy policies.

### Message History Is Not Group State

The `MessageHistory` header records tracked components a message passed through. It does not store all members of an aggregator group and does not prove output committed. To debug stuck batches, inspect all of:

1. `correlationId` and sequence metadata;
2. `MessageGroupStore` group size/age;
3. LockRegistry/DB lock wait times;
4. Poller/executor active counts and queue age;
5. Error/retry/DLQ records;
6. Trace spans and business completion state.

## 25. Optimizing Throughput: Scaling Stateless Differs from Scaling Stateful

### Stateless Throughput

For an independent CPU-bound transformer, throughput scales nearly linearly with worker count until hitting CPU, scheduler, or downstream bottlenecks. If the handler performs blocking I/O, concurrency is also bounded by connection pools and timeouts.

### Stateful Throughput

If all messages share one `batchId`, the critical section protecting that group forces serialization. Raising workers from 4 to 40 sometimes **only increases lock wait**.

A simple model:

\[
L = \lambda W
\]

Little's Law in steady state, where `L` is the average number of items in the observed scope, `λ` is average throughput, and `W` is average residence time. If a stateful stage processes 50 parts/s with an average wait time of 2 s, an average of ~100 parts are in-flight/queued in that scope, **assuming steady-state stability**.

When input arrives at 100 parts/s while the stateful store completes only 50/s, backlog grows by roughly 50 parts/s, and you cannot mechanically plug numbers into the steady-state formula to predict drain times.

### Measure the Right Bottleneck

| Symptom | Likely Cause | Intervention |
| --- | --- | --- |
| Stateless CPU 100%, stateful store light | CPU-bound normalization/validation | Scale workers, optimize CPU work |
| Stateless idle, high stateful lock wait | Hot correlation key | Partition, reduce contention, redesign key |
| High group age, low queue depth | Missing parts/timeout policy | Expiry, source validation, fault recovery |
| Growing queue depth, slow store writes | Backend storage/serializer/transactions | Indexes, batching, DB tuning |
| Retries spike on output API 503 | Downstream outage | Backoff, circuit breaker, durable outbox |
| Low completion count despite many group releases | Output commit/ack failures | Outbox, reconciliation |
| OOM from unexpiring groups | Unbounded state retention | Timeouts, cleanup, capacity alerts |

**Do not assume every stateful problem is solved by adding threads.** You must know key distribution, lock contention, store throughput, release conditions, and downstream completion.

## 26. Testing: Three Mandatory Levels

### 26.1. Unit Tests for Stateless Parts

Pure functions are easy to test without a Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;

import org.junit.jupiter.api.Test;

class NormalizeLineTest {

    @Test
    void trimsAndUppercasesInput() {
        String result = " green "
                .trim()
                .toUpperCase(Locale.ROOT);

        assertEquals("GREEN", result);
    }
}
~~~

In practice, invoke the actual transformer method/bean rather than duplicating logic inside the test; the snippet above merely illustrates determinism.

### 26.2. Spring Integration Context Tests for Stateful Parts

Use the flow from Section 9 in a test context **without running the ApplicationRunner demo** so no stray state/samples pollute the run:

~~~java
@Test
void releasesOnlyAfterThreeParts() {
    for (int i = 1; i <= 2; i++) {
        assertTrue(input.send(
                MessageBuilder.withPayload("p" + i)
                        .setHeader("batchId", "batch-test")
                        .setHeader("eventId", "evt-" + i)
                        .build()));
    }

    assertNull(completed.receive(100));

    assertTrue(input.send(
            MessageBuilder.withPayload("p3")
                    .setHeader("batchId", "batch-test")
                    .setHeader("eventId", "evt-3")
                    .build()));

    Message<?> result = completed.receive(2_000);
    assertNotNull(result);
}
~~~

This is a **JUnit fragment** requiring injected `MessageChannel input`, `PollableChannel completed`, a dedicated test context, and imports. Do not assert the exact string of the aggregated payload before confirming the output processor and ordering policy.

Add negative tests for:

- Missing `batchId` header;
- Duplicate `eventId` before the third part;
- Parts arriving out of order;
- Two batch keys interleaved;
- Group timeout and late arrivals;
- Handler/output throwing an exception after release.

### 26.3. Fault Integration Tests with Persistent Store/Broker

If survival across restarts/multi-node setups is required, test against a real store/broker or Testcontainers:

1. Send 2/3 parts and confirm the group persisted;
2. Stop/kill the application at a controlled point;
3. Start another instance sharing the same store/schema;
4. Send the final part and verify the batch releases **exactly one logical result**;
5. Redeliver an older part and verify idempotency;
6. Simulate output commit followed by ack failure; test replay/deduplication;
7. Simulate group timeout and expiry;
8. Observe lock leases, deadlocks, or multi-node conflicts;
9. Ensure no ghost/incomplete groups linger uncleaned forever.

**Never conclude durability from an in-memory `SimpleMessageStore` test.** Passing unit tests only prove behavior within the current context.

## 27. Fault-Injection Matrix and Expected State

| Failure Point | Existing State? | What Must Be Verified |
| --- | --- | --- |
| Before stateless transform | No group part yet | Source redelivery/retry if needed |
| After normalize, before durable queue ack | Part may be published twice | Stable partId, broker deduplication |
| When group holds 1/3 | One pending member | Recovery on restart |
| When group holds 2/3 | Pending group | Resumes upon third part |
| Two consumers add to same key | Lock contention | No lost members or duplicate releases |
| Right as parts complete, before output commit | Group may be completed | Outbox/release retry |
| After DB commit, before source ack | Business result exists | Duplicates cause no second side effect |
| Part arrives after group expiry | Group already expired | Late event/quarantine policy |
| Store schema upgraded between parts | Old serialized messages exist | Deserialization/version migration |
| Error flow down | Recovery fails to persist | Propagate failure, never silently ack |
| Redis/JDBC lock loses lease | Shared state sees two owners | Business invariants/reconciliation |
| Cluster rebalance mid-batch | Key ownership changes | Shared/durable state/replay |

### How to Interpret Results

Do not just assert `send()` returns true; on `ExecutorChannel` that may only indicate task handoff, and on `QueueChannel` only enqueue. Verify:

- Final business output;
- Group store state;
- Source ack/offset;
- Idempotency outcome;
- Retry/expired/recovered counts;
- Duplicate side effects on remote systems.

## 28. Operations Runbook for Stateful Stages

### When the Stateless Stage Is Healthy but the Stateful Stage Backlogs

1. Compare input rate and output completion rate over the same time window.
2. Check queue depth, oldest message age, pending message groups, and oldest group age.
3. Measure lock wait/hold times per endpoint without tagging raw correlation keys.
4. Check DB/Redis availability, transaction retries, and serializer errors.
5. Distinguish groups missing parts from groups blocked by deadlocks/lock contention.
6. To shed load, pause ingress or apply bounded rate limits; **never delete queues/groups arbitrarily**.
7. Apply safe group expiration/replay policies aligned with business invariants.
8. During recovery, ramp consumer throughput gradually while watching duplicates and tail latency.

### Performing a Rolling Restart

~~~mermaid
flowchart TD
    A["Plan restart"] --> B["Pause ingress or throttle load"]
    B --> C["Drain current transactions / tasks"]
    C --> D["Verify group store durability"]
    D --> E["Restart one instance"]
    E --> F["Recover group state, locks, subscriptions"]
    F --> G["Send synthetic parts / check output"]
    G --> H{"No duplicates/missing?"}
    H -->|Yes| I["Resume gradually"]
    H -->|No| J["Escalate + quarantine / reconcile"]
~~~

Never switch an in-memory `SimpleMessageStore` to a shared JDBC store by "swapping the bean at runtime" while ignoring in-flight group migration. Establish a migration plan and verify serializer/schema compatibility.

## 29. Common Anti-Patterns

| Anti-Pattern | What Is Wrong? | Appropriate Alternative |
| --- | --- | --- |
| Singleton `HashMap` holding batch state | Non-durable, unsafe across nodes | `MessageGroupStore` + lock + timeout |
| `synchronized` on one instance scaled to multiple pods | Locks only within that JVM | Partition ownership or distributed locks |
| `group.size()==N` with redeliveries | Duplicates falsely satisfy count | Deduplicate by unique part IDs |
| Assuming `expireGroupsUponCompletion` blocks late duplicates | Closed marker may be deleted | Durable completed-group/idempotency marker |
| No group timeout | Leaked pending state | Expiry/quarantine/partial policy |
| Using in-memory `QueueChannel` as a durable store | Restart loses backlog | Persistent store/broker |
| Using `MessageStore` as a business database | Cannot express domain invariants | Business DB/outbox |
| Unbounded whole-stream retries | Replays all side effects | Bounded per-event/group retries |
| Adding executor threads to fix lock contention | Key remains serialized | Key distribution and critical section design |
| Using raw `MessageHeaders.ID` as idempotency key | ID changes when message is rebuilt | Stable business eventId |
| Acking before store commit | Crash loses part | Proper transaction boundaries |
| Marking dedup before commit then crashing | Retries skipped despite missing effect | Inbox state machine/atomic claim |
| Deleting incomplete groups while late messages remain | Loses recoverability | Explicit timeout/retention |
| Omitting stateful metrics | Endpoints running while business stalls | Pending/oldest groups, lock wait, completion |
| Treating a durable store as exactly-once | Side effects outside store can duplicate | Idempotency/outbox/reconciliation |

## 30. Practice Exercises

1. **State classification:** across ten endpoints in your project, identify stateless invocations, stateful infrastructure, and stateful business owners.
2. **Flow separation:** write two `IntegrationFlow` definitions linked by a channel as in Section 9, with explicit endpoint/channel IDs.
3. **Two batches:** send interleaved parts for `batch-A` and `batch-B`; verify they never mix.
4. **Missing part:** send 2/3 parts and stop; inspect pending groups and design a timeout.
5. **Duplicates:** send `P1,P2,P2`, demonstrate why size-based release fails, and add deduplication.
6. **Out of order:** send `P3,P1,P2`; choose an aggregator or resequencer per output contract.
7. **Concurrency:** use an `ExecutorChannel` with concurrency 8; send same-key parts concurrently and measure lock wait and output count.
8. **Persistent store:** replace `SimpleMessageStore` with a persistent store in an integration test; restart after 2/3 parts.
9. **Cluster:** run 2 nodes accessing a shared locked store; verify a batch releases once per business ID.
10. **Expiry:** let an incomplete group exceed timeout, emit a failure event, and verify cleanup.
11. **Late events:** send a part after completion/expiry and verify controlled drop/quarantine/reopen behavior.
12. **DB transaction:** make the output handler throw after DB write; verify rollback/retry and outbox outcomes.
13. **Outbox:** simulate a crash after group release before network send; use an outbox to prevent lost output.
14. **Inbox:** simulate duplicate redelivery after commit; verify the receiver does not execute side effects twice.
15. **Schema migration:** persist a message with an old version, boot new code, and test decoding.
16. **Observability:** measure pending group count, oldest age, completion rate, and lock wait p95.
17. **Scaling:** compare throughput when scaling stateless workers vs. scaling stateful consumers with one hot key.
18. **Runbook:** write a pause-drain-resume plan for a stateful stage holding 100 pending groups.
19. **Control Bus:** stop/start an endpoint by exact ID and verify the group store remains durable without treating lifecycle state as durable outcome.
20. **Design review:** explain why message history, errorChannel, and retry advice do not replace a workflow state store.

### Self-Check Questions

- Is a handler without mutable fields always pure/stateless from a business standpoint?
- Why does `QueueChannel` make the whole pipeline stateful even when the transformer holds no state?
- Why does an aggregator need correlation, release, expiry, and a message store?
- How does `MessageGroupStore` differ from `MetadataStore`?
- Why is `group.size()==3` wrong when duplicate redeliveries exist?
- Does `expireGroupsUponCompletion(true)` automatically block all late events?
- Does a multi-node shared store need distributed locking?
- Why does adding threads fail to resolve a hot correlation key?
- How can retrying after DB commit but before broker ack cause duplicates?
- Why is reading back across a restart mandatory before calling a flow durable?
- What are stateless islands and stateful islands, and what factors determine a good boundary?

## 31. Pre-Production Checklist

- Clearly defined state ownership and logical correlation keys for every workflow.
- Stateless handlers hold no mutable per-workflow data across invocations without an explicit contract.
- Stateful components have explicit stores, locks, transactions, timeouts, and release strategies.
- Late/duplicate policies and stable idempotency keys exist across retries/replays.
- Store durability/serializers/version migrations are tested across restarts.
- Every async channel/broker boundary has an ack/retry/error contract.
- No in-memory queues/groups are used for data that must survive process restarts.
- Bounded capacities exist for queues, state groups, executors, and error flows.
- Group release and output side effects have recovery/outbox or equivalent guarantees.
- Multi-node locking/key partitioning is verified via fault injection.
- Correlation, sequence, event ID, and trace ID cross boundaries with proper header mapping.
- Observability exposes group counts, ages, expired/duplicate counts, and completion rates.
- Stateless and stateful scaling targets real bottlenecks, not worker counts alone.
- Runbooks cover pause/drain/restart/replay, retention, and incident response.
- Unit, integration, and multi-node/crash-recovery tests are cleanly separated.
- STEP 4 only authors content; STEP 6 build/academic QA has not yet been executed.

## 32. Official References

- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): storing messages, message groups, and persistence.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release, group timeouts, and expiry.
- [Spring Integration — Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html): ordering and resequencing state.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): idempotency interceptors and metadata.
- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): metadata persistence.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, ExecutorChannel, QueueChannel.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/polling-consumer.html): pollers and transaction boundaries.
- [Spring Integration — Lock Registry](https://docs.spring.io/spring-integration/reference/distributed-locks.html): concurrency and distributed locks.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): building IntegrationFlows via Java DSL.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, recovery.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): tracked hops and correlation support.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): Micrometer Observation and integration management.
- [Spring Integration — Dynamic Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): registration/lifecycle.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactions and rollback.
