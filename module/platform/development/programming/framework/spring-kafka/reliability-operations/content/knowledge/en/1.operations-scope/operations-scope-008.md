# Responsibility Boundaries Between Application and Broker

In a reliable Spring Kafka system, both the application and the Kafka broker participate in a message's path, yet each side is responsible for a different part. The application decides **what a message means, how it is sent and processed, and when processing is considered successful**. The broker is responsible for **accepting records, storing logs, replicating data, delivering records to consumers, and maintaining consumer group state**.

This boundary must be clearly understood during design, configuration, and incident response. The broker can confirm that a record was written to Kafka, yet it cannot know on its own that a transaction in the application's database completed. Conversely, the application can execute business logic properly, yet it cannot guarantee data survives a broker or disk failure if the cluster is not configured appropriately.

## 1. Viewing the System from Both Sides

A typical Kafka flow has three components:

- **Producer application**: creates events, determines keys, serializes data, and sends records via the Kafka client. In Spring applications, this part commonly uses **KafkaTemplate**.
- **Kafka broker/cluster**: receives write requests, manages partitions and leaders, writes logs, replicates data, stores per retention policy, and serves read requests.
- **Consumer application**: reads records, deserializes, executes business logic, and decides when to acknowledge offsets. In Spring Kafka, this part commonly uses **@KafkaListener** and listener containers.

~~~mermaid
flowchart LR
    A["Producer application<br/>Create event, key, serialize"] -->|"Produce request"| B["Kafka broker<br/>Leader, log, replication"]
    B -->|"Produce acknowledgement"| A
    C["Kafka broker<br/>Partitions and group coordination"] -->|"Fetch records"| D["Consumer application<br/>Deserialize, business processing"]
    D -->|"Commit offset"| C
~~~

Spring Kafka is the application-side integration layer. **KafkaTemplate**, listener containers, acknowledgement modes, error handlers, and transaction integration are mechanisms Spring provides for the application to use Kafka. They do not turn Spring into a broker, nor do they replace cluster operations responsibilities.

## 2. Responsibility Allocation Table

| Concern | Application / Spring Kafka | Kafka Broker / Platform |
|---|---|---|
| Event semantics | Defines events, validates business data, decides when to emit events | Stores byte records; does not understand event business semantics |
| Serialization | Chooses serializers, payload formats, manages schemas and version compatibility | Receives and stores keys/values as bytes |
| Partitioning | Chooses keys or partitions per business needs; designs keys for load distribution and ordering | Manages partitions, leaders, and partition reads/writes |
| Writing data | Configures producer, sends records, observes results, and handles send errors | Accepts requests, appends to logs, and replicates per configuration |
| Data durability | Chooses acknowledgement level matching application requirements | Performs replication, manages ISR, and persists logs |
| Reading data | Configures consumer, polls, deserializes, and processes records | Serves fetch requests and coordinates consumer groups |
| Offsets | Chooses group ID and commit timing aligned with processing progress | Stores committed offsets and manages group coordination |
| Consumer business logic | Defines successful processing, prevents duplicate processing, and manages side effects | Does not know whether business logic completed |
| Retries and DLT | Defines retryable error types, backoff, attempt limits, and recovery workflows | Stores retry/DLT records if the application publishes them to topics |
| Retention | Proposes retention duration based on replay and business needs | Enforces retention or log compaction on topics |
| Security | Manages credentials, client config, and prevents secret leaks | Authenticates, authorizes, and enforces ACLs/authorizers per cluster policy |
| Capacity and availability | Controls send/read rates, concurrency, and behavior when dependencies slow down | Manages broker resources, disk capacity, replication, network, and serving availability |

Some items are shared responsibilities. For example, the platform team may create topics and configure retention, while the application team must specify the required replay window. The platform team may grant ACLs, while the application must use the right principal and handle authorization failures. Boundaries should be documented as operational agreements per topic or domain.

## 3. Path of a Record When the Producer Sends

### 3.1 What the Application Does

Before Kafka receives data, the producer application must:

1. Decide which event to emit and ensure its contents accurately reflect business state.
2. Choose a key. The key is typically the identifier of the aggregate or entity requiring ordering, such as **orderId**.
3. Serialize key and value into bytes using configured serializers.
4. Send the record to the topic. The producer client uses metadata to locate the target partition and broker leader.
5. Observe the send result. The application must handle send failures rather than assuming calling **send** means data was persisted.

Example with **KafkaTemplate**:

~~~java
kafkaTemplate.send("orders.created", event.orderId(), event)
    .whenComplete((result, error) -> {
        if (error != null) {
            // Record the send failure and route to the appropriate recovery flow.
            log.error("Could not publish order event", error);
            return;
        }

        // Broker acknowledged the record per producer configuration.
        log.debug("Published order event to partition {}",
                result.getRecordMetadata().partition());
    });
~~~

A successful future result indicates the producer received an acknowledgement per send configuration. It does not prove the consumer has read the record, consumer business logic has run, or the target database has committed.

If an HTTP API may return success only after Kafka acknowledges the event, the application must wait on the send result in a manner compatible with request timeouts. If updating the database and emitting an event must survive failures together, design an outbox or an appropriate coordination mechanism; merely calling **KafkaTemplate.send** after a database write does not create an atomic transaction across both systems.

### 3.2 What the Broker Does

Upon receiving a produce request, the target partition's leader broker validates the request and access permissions per configuration, then appends the record to its log. Follower replicas fetch data from the leader and update replica state. The producer receives an acknowledgement based on **acks** configuration and replication status.

Configurations commonly paired together:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

On the cluster side, an example default policy:

~~~properties
default.replication.factor=3
min.insync.replicas=2
~~~

With replication factor 3 and **min.insync.replicas** 2, a write using **acks=all** requires at least two replicas in the ISR to be accepted. **acks=all** waits for replicas currently in the ISR to acknowledge; it does not mean always waiting for every originally configured replica. If the ISR falls below the minimum threshold, the broker can reject writes to uphold the configured data-protection level.

**default.replication.factor** is the default when creating topics if no explicit replication factor is specified. Individual topics can have their own settings; therefore, inspect actual topic configuration rather than looking only at broker defaults.

### 3.3 Limits of Producer Idempotence

**enable.idempotence=true** helps the Kafka producer avoid creating duplicate records due to internal producer retries within the scope Kafka supports. This is an important safeguard when sending over unreliable networks.

However, producer idempotence does not automatically eliminate duplicate business events. For example, a payment request retried by a client may cause the application to emit a new event after the earlier producer send succeeded but the response was lost. To prevent this, the application needs idempotency keys, business state checks, or unique constraints in the database.

The broker also cannot decide on its own that two records with identical contents represent the same business action. Two byte-identical records can still be two valid events.

## 4. Path of a Record When the Consumer Reads

### 4.1 Broker Manages Delivery, Application Manages Processing

A consumer joins a consumer group using a group ID. The broker's group coordinator manages membership, generations, and group state; consumer-side assignors determine which partitions go to each consumer. Within the same group, at any given time, a partition is assigned to at most one active consumer member.

The consumer polls records from the broker. The Kafka client handles fetching and deserializing per configuration; the Spring listener container coordinates polling and invokes the listener. The listener executes business logic such as writing to a database, calling another service, or emitting a downstream event.

The broker knows which offsets the consumer has committed. The broker cannot know whether the listener updated a database, sent an email, or completed an external side effect.

### 4.2 Offsets Are Confirmed Read Positions

An offset is a record's position within a partition. A committed offset indicates how far the consumer group has confirmed reading. An offset is not independent proof that all corresponding business side effects have completed.

In Spring Kafka, listener containers offer acknowledgement modes such as **RECORD**, **BATCH**, **MANUAL**, and **MANUAL_IMMEDIATE**. With container-managed modes, commit timing depends on the acknowledgement mode and listener execution outcome. Choose a mode based on how the application defines completion for a batch or record.

Consumer example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.applyOnce(event.eventId(), event);
}
~~~

In this example, **applyOnce** represents a business operation capable of recognizing and skipping already-processed events. When the listener returns normally, the container handles acknowledgement/commit per configuration. If the listener throws an exception, the error passes to the configured error handler.

### 4.3 Why Consumers Need Idempotency

Suppose a consumer reads the record at offset 42 and updates the database successfully. Immediately afterward, the process crashes before the new offset is committed. When the consumer restarts, Kafka may redeliver the record at offset 42. The database has already received the first side effect, yet Kafka still considers that record uncommitted.

This is a common reason consumers require idempotency. Implementation approaches include:

- Storing processed **eventId** values in the database with a unique constraint so the same event cannot apply side effects twice.
- Designing updates as upserts or conditional updates so re-running produces the correct outcome.
- Using an inbox table to record received events in the same transaction as business updates.
- Routing side effects through an outbox when downstream events must be emitted after a database commit.

For typical database processing, the common choice is at-least-once delivery combined with an idempotent consumer. The application accepts possible redeliveries and ensures business operations are not duplicated.

### 4.4 Exactly-Once Has a Specific Scope

Kafka transactions can coordinate reading records, writing output records, and committing offsets within a single Kafka transaction. Consumers reading with **isolation.level=read_committed** see only records from committed transactions. Spring Kafka supports transaction integration for suitable Kafka flows.

This scope does not automatically cover a relational database, REST API, or external system. If a listener updates a database and then writes to Kafka, a Kafka transaction does not automatically roll back the database when the Kafka transaction fails. For multi-system flows, use outbox/inbox, idempotency, or an explicitly designed transaction coordination pattern. Use the term exactly-once only when the exact resources and side effects inside the guarantee scope are identified.

## 5. Guarantees the Broker Provides vs. Work the Application Must Finish

### 5.1 Storage, Replication, and Retention

Brokers manage per-partition logs, cross-broker replication, leader elections, and retention or log compaction enforcement. These mechanisms protect and manage data inside Kafka according to cluster/topic configurations.

The application must determine how long data must be retained, what replay window is needed, and whether long-term archival is required in another system. Retention is not a permanent business system of record. Once records expire, brokers may delete data per policy. With log compaction, Kafka retains the latest value per key via compaction; that is not equivalent to keeping a complete event history.

### 5.2 Ordering and Partition Keys

Kafka preserves record ordering within a single partition. Brokers do not guarantee global ordering across multiple partitions.

The application decides keys and parallel processing behavior. If all events for the same order must be processed in sequence, the producer must use a stable key like **orderId** so those events land in the same partition. Consumers must also avoid offloading asynchronous work outside the listener in ways that complete side effects out of order.

Increasing partition counts can boost parallelism, yet it can affect key distribution and ordering in ways the application must evaluate. The broker cannot fix a key design that mismatches business requirements.

### 5.3 Retries and Dead-Letter Topics

There are different types of retries:

- **Producer retry**: the Kafka producer attempts to resend when encountering recoverable transport or broker errors.
- **Consumer/listener retry**: the application attempts to reprocess when a listener encounters errors.
- **Business retry**: the application schedules a retry of a business operation after a delay, potentially needing a dedicated workflow or retry topic.

Spring Kafka provides error-handling and recovery mechanisms, such as **DefaultErrorHandler** and **DeadLetterPublishingRecoverer**, to build error policies. The application must define which errors are retryable, backoff durations, attempt caps, which errors should not be retried, and when records route to a DLT.

A dead-letter topic is a standard Kafka topic. The broker simply stores records sent to that topic by a producer. The broker does not create DLTs automatically, does not decide which records are poison messages, and does not schedule replays. The application and platform teams must align on read/write permissions, retention, capacity, alerts, error metadata format, and replay procedures. When replaying, preserve recognition of previously processed events so side effects are not repeated.

### 5.4 Schemas and Invalid Data

Brokers store keys/values as bytes. Brokers do not verify that JSON contains required fields, that an Avro schema is compatible, or that a status value is domain-valid.

The application is responsible for serialization/deserialization, business data validation, and schema error handling. If an organization uses a Schema Registry, the registry and compatibility policies are part of the data platform; producers/consumers must still adhere to the schema contract. A record can be written by a broker successfully yet still fail deserialization in the consumer.

## 6. Division of Labor in Production Operations

### Kafka Platform Team

The platform team is typically responsible for:

- Operating brokers, controllers, networking, storage, upgrades, and capacity planning.
- Setting replication policies, rack awareness, ISR policies, default retention, and quotas.
- Creating topics or managing topic provisioning, partitions, and topic-level configurations.
- Configuring authentication, authorization, TLS, ACLs/authorizers, and provisioning principal permissions.
- Monitoring cluster health: broker availability, under-replicated partitions, offline partitions, disk usage, request latency, and replication health.
- Providing bootstrap servers, topic contracts, capacity limits, and cluster incident procedures.

### Application Development Team

The application team is typically responsible for:

- Defining event contracts, schemas, keys, and the meaning of each topic.
- Configuring producer/consumer clients to match durability, latency, and throughput needs.
- Managing group IDs, concurrency, poll behavior, and acknowledgement/commit strategies.
- Ensuring idempotent consumer processing and controlling side effects outside Kafka.
- Defining retries, backoff, DLTs, poison-message alerts, and replay workflows.
- Monitoring send errors, deserialization errors, listener failures, consumer lag, and processing latency.
- Ensuring the application handles timeouts, unavailable brokers, rebalances, duplicate deliveries, and invalid data.

### Decisions Requiring Alignment

| Decision | Requires Platform Team | Requires Application Team |
|---|---|---|
| Topic creation | Provisioning workflow, permissions, cluster limits | Topic name, purpose, owner, and event contract |
| Partition count | Cluster capacity and operational limits | Throughput, key distribution, and required parallelism |
| Replication/retention | Policies and actual settings | Acceptable data loss level, replay window |
| Security | Principals, ACLs, TLS, and credential provisioning | Using the right credentials, bootstrap servers, and handling authorization failures |
| DLT/replay | Capacity, permissions, retention, and topic monitoring | DLT routing criteria, error format, duplicate side-effect prevention, and replay approval |
| SLOs/alerts | Cluster and broker metrics | Producer/consumer metrics, business metrics, and actions on SLO breach |

Every topic should have a clear owner. The owner needs to know who may publish, who may consume, what the key signifies, what rules govern schema evolution, how long retention lasts, where the DLT resides, and who is authorized to trigger replays. Missing this information leads to incidents bouncing back and forth between application and platform teams.

## 7. Diagnosing Incidents Along the Proper Boundaries

| Symptom | Application Side to Check | Broker/Platform Side to Check |
|---|---|---|
| Producer timeout or send failure | Future/callback, timeouts, retries, bootstrap servers, DNS/network from runtime, serializers, and credentials | Broker availability, request latency, leaders, ISR, quotas, ACLs, and network |
| **NotEnoughReplicas** or **NotEnoughReplicasAfterAppend** error | **acks**, retry policy, and how the application responds to publish failures | Replication factor, **min.insync.replicas**, ISR, broker/replica health |
| Broker ACKed but consumer does not see record | Correct topic, group ID, subscription, offsets, deserializer, filters, and listener errors | Topic/partition existence, leader health, retention, ACLs, and fetch capability |
| Rising consumer lag | Processing duration, concurrency, consumer count, downstream database/API, retry errors, and pause/resume | Fetch latency, broker load, disk/network, and partition distribution |
| Record processed repeatedly | Commit timing, listener failure after side effect, rebalances, and idempotency | Group coordination and continuity of committed offsets |
| Out-of-order records | Keys, partition count, async processing, retries, and application concurrency | Verify partitions/leaders; broker preserves order only within each partition |
| Records continuously entering DLT | Stack traces, schema errors, poison data, retry classification, and recovery code | DLT existence, publish permissions, retention, and capacity |
| Consumer continuously rebalancing | Per-poll processing time, heartbeats, **max.poll.interval.ms**, session timeout, and shutdown behavior | Group coordinator health, network, and cluster stability |

During an incident, pinpoint the last step with observable evidence:

1. Did the producer construct the event?
2. Did the producer client send the request?
3. Did the broker acknowledge the write?
4. Did the consumer group receive the partition assignment and fetch the record?
5. Did the listener begin processing?
6. Did the business side effect commit?
7. Was the offset committed?

Every answer must rely on verifiable logs, metrics, traces, or state. For instance, a "send initiated" log proves only that the application started sending; an acknowledgement log proves the producer received broker confirmation. Likewise, a "listener entered" log does not prove the database transaction committed.

## 8. Configuration Example and Reading Scope Correctly

A minimal application configuration can clarify several client-side decisions:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: billing-service
      enable-auto-commit: false
~~~

Meaning:

- **bootstrap-servers** gives the client initial addresses to fetch cluster metadata.
- **acks: all** requires the producer to wait for acknowledgements per the current ISR.
- **enable.idempotence: true** enables duplicate prevention for internal producer retries within Kafka's supported scope.
- **group-id** identifies the consumer group the application joins.
- **enable-auto-commit: false** prevents the Kafka client from committing offsets on timers independent of how the listener container manages processing. The Spring Kafka container can manage commits per acknowledgement mode.

Application configuration cannot substitute for cluster configuration. For example, setting **acks: all** in Spring Boot does not automatically raise replication factor or **min.insync.replicas**. Both sides must be configured compatibly. Similarly, disabling auto commit does not automatically make the consumer idempotent; the application still needs to pick a commit strategy and protect side effects.

If using Kafka transactions and consumers must read only committed data, configure **isolation.level=read_committed** on the corresponding consumer. Enable this setting only when the flow actually uses a transactional producer and those semantics are required by the application.

## 9. Pre-Production Flow Checklist

**Event Contract**

- [ ] Topic has a clear owner, description, producers, and consumers.
- [ ] Keys are selected based on partitioning and ordering needs.
- [ ] Schemas, serializers, and compatibility rules are agreed upon.
- [ ] Rules exist for handling malformed or invalid events.

**Durability and Data Publishing**

- [ ] Topic replication factor, ISR policy, and retention fit requirements.
- [ ] Producer has appropriate acknowledgement, idempotence, timeout, and retry settings.
- [ ] Application observes send outcomes and has a recovery path for publish failures.
- [ ] Database-to-Kafka flows use an outbox or suitable consistency mechanism.

**Consumption and Processing**

- [ ] Group ID and consumer/concurrency counts fit partition counts.
- [ ] Acknowledgement mode and commit timing accurately reflect business completion.
- [ ] Consumers implement idempotency to tolerate redelivery.
- [ ] Listeners have bounded processing limits, timeouts, and defined shutdown/rebalance behavior.

**Retries and Operations**

- [ ] Retries classify errors, use backoff, and cap attempt counts.
- [ ] DLTs have an owner, retention, alerts, access controls, and a replay procedure.
- [ ] Metrics/logs exist for publish failures, listener failures, consumer lag, processing latency, and DLT rates.
- [ ] Runbooks clearly specify when the application team acts and when the Kafka platform team is needed.
- [ ] Tests or drills cover broker unavailability, rebalances, duplicate deliveries, poison messages, and downstream outages.

## 10. Principles to Maintain During Design

The broker guarantees storage, replication, delivery, and group coordination mechanisms within the bounds of cluster configuration. The application guarantees data semantics, producer behavior, consumer progress, and correctness of business side effects. Spring Kafka provides the application-side tools to implement those decisions.

Therefore, an acknowledgement from the broker must be understood as confirmation at the Kafka layer; a committed offset must be understood as a consumer group's confirmed read position. To guarantee a business operation completes accurately, the system must connect these milestones with appropriate transactions, idempotency, retries, and observability on the application side. When every milestone has a clear owner and verifiable evidence, operations teams can isolate whether an incident lies in the client, business logic, or cluster and recover the responsible component cleanly.
