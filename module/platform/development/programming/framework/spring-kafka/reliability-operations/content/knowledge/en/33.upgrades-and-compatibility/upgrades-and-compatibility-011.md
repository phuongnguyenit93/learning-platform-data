# Safe Version Rollback in Spring Kafka Reliability Operations

## 1. The Problem: Rolling Back an Application Does Not Roll Back Data

Suppose an `orders-consumer` service runs Spring Kafka, reads topic `orders.events`, and writes orders into PostgreSQL. The development team upgrades from image `1.8.2` to `1.9.0` with several changes:

- Adding a `paymentMethod` field to events.
- Changing retry and DLT logic.
- Altering the `orders` table structure.
- Upgrading Spring Kafka/Kafka client libraries.
- Adjusting consumer concurrency and offset commit timing.

After deployment, latency spikes and some records are processed incorrectly. Operators want to run `kubectl rollout undo` to revert to the old image. That command can restore the **Deployment Pod template**, yet does not automatically restore:

- **Committed offsets** of the Kafka consumer group.
- **Messages** already published to topics by the new producer/consumer version.
- **Schema/serialization contracts** already registered or emitted.
- **Database data** and committed external side effects outside Kafka.
- **ConfigMaps/Secrets** edited independently of the Deployment.
- **Kafka Streams state stores/changelogs** already written by the new version.
- **Topic partitions, broker ACLs, and broker configurations** already modified.

Therefore, a **safe version rollback** is a pre-prepared plan for **returning code and configuration to a stable version while preserving data correctness**.

This lesson belongs to **Upgrades and Compatibility** in *Spring Kafka Reliability Operations*. You will learn to:

1. Classify the rollback type: application, client library, Kafka Streams, or broker.
2. Establish compatibility contracts so the old version can read records created by the new version.
3. Preserve consumer group identity and assess committed offsets during rollback.
4. Design idempotent consumers, outboxes, and reversible database migrations.
5. Structure canary, rolling update, freeze, rollback, resume, and reconciliation phases.
6. Handle risks across retry/DLT, transactions, listener concurrency, and Kafka Streams state.
7. Use Kubernetes rollout history within its real scope rather than confusing it with config/data rollback.
8. Write integration/recovery tests that check data rather than merely status or process exit codes.

Examples use **Spring Boot 3.x, Spring Kafka 3.x, compatible Kafka brokers, and Java 17+**. When upgrading to another major version, consult the release notes and compatibility matrix of the exact deployed versions.

## 2. Classify the Rollback Before Issuing Commands

The term "Kafka version" can refer to multiple distinct layers:

| Layer | Example Change | Can Deployment Rollback Help? | What Must Be Checked |
| --- | --- | --- | --- |
| **Consumer application** | Java logic, listener, retry | Can restore old image | Schemas, offsets, side effects, config. |
| **Producer application** | Event payload, serializer | Can restore old image | New-version messages already published. |
| **Spring Kafka dependency** | Spring Kafka 3.x → another release | Usually rolled back via image/BOM | API semantics, error handlers, listeners. |
| **Kafka Java client** | New client version | Usually rolled back via image | Broker/client protocol compatibility. |
| **Kafka Streams app** | Topology, state store, serde | Image rollback **is not enough** | State/changelog/snapshot formats and topology. |
| **Kafka broker** | Cluster software/protocol version | **Never** use app rollout | Metadata format, cluster feature levels, broker compatibility. |
| **Schema Registry** | New compatibility mode/schema | Registry has its own lifecycle | Reader/writer compatibility; existing data. |
| **Kafka topic/ACLs** | Partitions, retention, policies | No | Infrastructure changes, offsets, record availability. |
| **Database schema** | Add/drop columns, type changes | No | Migrations and data written by the new version. |

**This lesson focuses on rolling back Spring Kafka applications.** Broker downgrades are infrastructure operations with strict version/metadata rules; never treat them as the symmetric inverse of a broker upgrade. Rely on official Kafka release docs and a dedicated cluster test plan.

## 3. Three Questions to Answer Before Rolling Back

Before reverting the image to an old version, verify:

**1. Can the old version still read new data?**

- Can the old consumer deserialize the new schema?
- Does it reject new enums/event types?
- Could a new record trap the old consumer in an infinite failure loop?
- Are files/tables/state written by the new version compatible with the old version?

**2. When resuming, will data be missed or duplicated?**

- Where have consumer group offsets committed?
- Were messages processed without committing offsets, or vice versa?
- Have external side effects outside Kafka already committed?
- Are business IDs/idempotency keys stable across both versions?

**3. Do config and infrastructure still match the old binary?**

- Are ConfigMaps, Secrets, env vars, and feature flags from the new release rolled back alongside it?
- Does the database still have the columns/tables required by the old binary?
- Are ACLs, topic names, serializer classes, and SASL/TLS settings still valid?
- Did retention/compaction expire data needed for replay?

Only when these answers are proven via compatibility tests or controlled operational procedures should rollback be considered safe.

## 4. Example Data Flow Before and After Upgrade

~~~text
                     Kafka topic
                   orders.events
                         |
                         v
                 Consumer group G
                         |
            +------------+-------------+
            |                          |
         Version A                  Version B
         (stable)                  (newly deployed)
            |                          |
            v                          v
       Deserialize v1             Deserialize v1/v2
            |                          |
            v                          v
       PostgreSQL                  PostgreSQL
            |                          |
            +-------------+------------+
                          |
                          v
                 Business side effects
~~~

In a **rolling deployment**, old and new Pods coexist temporarily. If they share `group.id`, Kafka distributes partitions across group consumers via rebalancing; they are **not** two independent systems both receiving every record. Which version owns which partition can shift during rebalances.

That means:

- Producers must emit messages only under schemas both A and B can process during the overlap window.
- B processes partitions assigned to it; upon rollback, A must handle records published while B was active.
- A new consumer group with a different group ID is an **independent** stream with separate committed offsets, not a plain rollback.

## 5. Define the Rollback Plan Before Release

Every release should carry a reproducible configuration record:

| Release Component | Data Stored in Deployment Manifest |
| --- | --- |
| Artifact | Image tag **and immutable digest**. |
| Dependencies | Spring Boot BOM, Spring Kafka, Kafka clients, Java runtime. |
| Deployment | Replicas, container args, resource requests, rollout strategy. |
| Kafka config | Bootstrap cluster, topic names, consumer group, client properties. |
| Security | Auth mechanism, secret reference/version, TLS truststore, ACL changes. |
| Serialization | Event schema versions, serde configuration, compatibility mode. |
| Data | Database migration revision, feature flags, and data contracts. |
| Recovery | Listener ack mode, retry/DLT policy, transactions, idempotency. |
| Observability | Dashboards and release markers used during investigation. |
| Rollback artifact | Old image still retained, migration path, and config revert steps. |

Recording only "previous version=1.8.2" is insufficient. If the Deployment references a fixed-name ConfigMap/Secret, rolling back the Pod template **does not roll back the contents** of those resources.

Use GitOps/Helm/Kustomize with versioned manifests and config snapshots, keep old builds pullable from the registry, and enforce separate approvals for data/offset interventions.

### Choosing When to Roll Back

Potential triggers:

- Business failure rate rises after deploy.
- Consumer lag grows steadily while processing throughput drops.
- DLT rate rises with records lacking a recovery path.
- Producer send errors/latency climb or ACKs fail.
- Deadlock/duplicate/idempotency conflict rates breach thresholds.
- Deserialization/authorization errors appear post-upgrade.
- Output data is corrupted even while Pods report Ready.

Depending on severity, **stop/freeze producers or consumers in a controlled way** before rolling back, rather than always reverting while incompatible messages are still being produced.

## 6. Compatibility: The "Old Reader, New Data" Rule

A safe rollback requires that **the old version can read data produced by the new version during the rollout window**. This criterion matters more than whether the old binary still starts up.

Three relevant compatibility modes:

| Mode | Question |
| --- | --- |
| **Backward compatibility** | Can **new** code/schema read **old** data? |
| **Forward compatibility** | Can **old** code/schema read **new** data? |
| **Full compatibility** | Are both directions supported? |

Schema Registry policies named "BACKWARD/FORWARD/FULL" also carry **format**-specific rules and transitive/non-transitive variants. Never assume from the name alone that every schema edit is valid. Adding a field with a default in Avro may work in one direction, while changing required fields, enums, or field types requires separate analysis.

### 6.1. A JSON Event v1/v2 Example

Version A knows only:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-501",
  "amount": 1200
}
~~~

Version B plans to add a field:

~~~json
{
  "eventId": "evt-1002",
  "orderId": "order-502",
  "amount": 2300,
  "paymentMethod": "CARD"
}
~~~

If version A uses a Jackson DTO that **ignores unknown properties**, the new field may not break it:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        long amount) {
}
~~~

Yet this **does not guarantee semantic compatibility**. If version B changes `amount` from cents to VND, version A can still parse the JSON while computing **wrong monetary amounts**. If B uses `paymentMethod` for critical business decisions, letting A ignore that field may be unacceptable.

A solid contract must verify:

- **Schema**: does it deserialize?
- **Semantics**: do existing fields retain the same meaning?
- **Validation**: does the old version accept the new data per business rules?
- **Side effects**: is processing with the old version safe?
- **Integrity**: are event IDs and business keys preserved?

## 7. Schema Evolution Rules for Rollback Readiness

Common options:

1. **Additive fields**: add optional/defaulted fields without altering existing field meanings.
2. **New event types**: emit only after all relevant consumers support them.
3. **Dual read**: new consumers read both v1 and v2 during the transition period.
4. **Controlled dual write**: if emitting two shapes is unavoidable, use idempotency and clear version differentiation; never emit duplicate business events casually.
5. **Schema Registry policies**: pick compatibility matching rollback direction and test all involved readers/writers.
6. **Deprecation window**: drop old fields only after zero consumers depend on them and retention/replay windows expire.

~~~text
Release A:
  Consumer reads v1
  Producer writes v1

Release B phase 1:
  Consumer reads v1 + v2
  Producer still writes v1

Release B phase 2:
  Consumer reads v1 + v2
  Producer writes v2 only AFTER A rollback is no longer needed
  OR old A has proven v2 compatibility
~~~

Decision rule: while rollback to A remains mandatory, **do not emit v2-only records that A cannot read**. Keep B in a backward-compatible mode behind a feature flag until the rollback window closes.

### When the Schema Already Changed Incompatibly

A rollout undo of the image may no longer suffice. You may have to:

- Keep B running and ship a hotfix instead of rolling back to A.
- Build a compatibility adapter/new consumer to read v2 and translate validly.
- Split a versioned topic with a migration plan and data verification.
- Stop emitting v2, assess existing v2 records, and resolve them before restoring A.

Never delete records or reset offsets arbitrarily to hide schema failures.

## 8. Consumer Group ID and Offsets: What Must Be Preserved

A consumer group ID is **the identity of reading progress**. Within the same group, committed offsets are stored per topic-partition.

~~~text
topic orders.events, partition 0

offset:      100  101  102  103  104  105
                \----- processed ----/
                         |
                  committed offset 104
                   (next record 104)
~~~

In Kafka, a committed offset normally represents **the next offset** a consumer will read. If offset 104 is committed, record 104 may be the next record read (depending on flow/position). Do not confuse "committed up to 104" with "record 104 has already finished processing."

When rolling back to A:

- Preserve `group.id` if you want to resume from the group's current position.
- Never change `auto.offset.reset` just to get a consumer running.
- Never reset offsets unless an **approved replay/data-repair decision** exists.
- Inspect where the group committed and lag per partition.
- Verify target offsets still exist within topic retention.

**Rolling back an image does not rewind committed offsets to before deployment.**

### 8.1. Example of an Atomicity Gap Window

~~~text
T1: B processes record offset 200
T2: B COMMITS change to PostgreSQL
T3: Pod is killed before Kafka offset commit
T4: A rolls back out and re-reads offset 200
T5: A may apply duplicate side effects
~~~

This is standard **at-least-once** behavior whenever database transactions and Kafka offset commits do not share one transaction. The solution is **business-layer idempotency** and reconciliation, not a `kubectl` command.

### 8.2. What Does Changing `group.id` Do?

Suppose release B accidentally sets `group.id=orders-worker-v2`, whereas A used `orders-worker-v1`. Two groups maintain independent offsets.

| New Group Policy | Risk |
| --- | --- |
| `auto.offset.reset=earliest` | Can replay large volumes of old records. |
| `auto.offset.reset=latest` | Can skip records published before the group joined. |
| `auto.offset.reset=none` | Consumer fails when no valid offset exists, surfacing unintended configs. |

Changing `group.id` therefore changes **data-processing identity**. It requires its own migration/cutover plan, never a quick-fix rollback trick.

## 9. Business Invariant: Idempotent Consumers

For rollbacks to tolerate redelivery, enforce a stable deduplication key per **business event**.

Example PostgreSQL tables:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders_projection (
    order_id VARCHAR(100) PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

Within one JDBC transaction, attempt to insert the event ID; apply business changes only if the insert succeeds:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventService {

    private final JdbcTemplate jdbc;

    public OrderEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderCreated event) {
        int inserted = jdbc.update(
            "INSERT INTO processed_events(event_id, order_id) " +
            "VALUES (?, ?) ON CONFLICT (event_id) DO NOTHING",
            event.eventId(), event.orderId());

        if (inserted == 0) {
            // Event was already committed in an earlier attempt.
            return;
        }

        jdbc.update(
            "INSERT INTO orders_projection(order_id, amount) " +
            "VALUES (?, ?) " +
            "ON CONFLICT (order_id) DO UPDATE SET amount=EXCLUDED.amount",
            event.orderId(), event.amount());
    }
}
~~~

This snippet targets **PostgreSQL**; other SQL dialects need equivalent syntax. `OrderCreated` is an application-defined domain model exposing `eventId()`, `orderId()`, and `amount()`.

Key conditions:

- Inserting `processed_events` and updating the projection must occur **in the same database transaction**.
- `eventId` must remain stable across both versions A/B and across retries/restarts.
- Deduplicating by event ID does not catch events with **different IDs carrying the same business meaning**; add business constraints if required.
- Upserts must respect version/order rules: if events arrive out of order, overwriting with the latest amount may be wrong. Sequence/version checks may be needed.
- HTTP/email calls outside the transaction still need corresponding idempotency/outbox mechanisms.

### Spring Kafka 3.x Listener

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final OrderEventService service;

    public OrderConsumer(OrderEventService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "${app.kafka.orders-topic}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void receive(String payload) throws Exception {
        // deserialize + validate with codec per contract.
        OrderCreated event = parseAndValidate(payload);
        service.apply(event);
    }

    private OrderCreated parseAndValidate(String payload) {
        // Application pseudocode: use ObjectMapper/serde with validation.
        throw new UnsupportedOperationException(
            "Implement schema-aware decoding");
    }
}
~~~

`parseAndValidate` is an **illustrative extension point**, not a complete runnable app: implement decoding, validation, and error handling before deployment. Never swallow exceptions in the listener and let the container commit offsets anyway; errors must flow through the error handler per policy.

With `AckMode.RECORD`, `enable.auto.commit=false`, and properly configured container/error handlers, offset commits tie to listener completion. However, **there is no ACID transaction spanning Kafka offsets and PostgreSQL** from ack mode selection alone.

## 10. Database Migrations: Use Expand–Contract

Rollbacks easily fail when release B **drops a column** that A still needs. Design two-phase migrations:

~~~text
Release A
    |
    v
EXPAND Migration
  - add nullable/defaulted columns
  - add new indexes
  - keep old columns
    |
    v
Release B
  - reads old format
  - gradually writes new format
  - compatible with expanded schema
    |
    +----> Rollback A can still read/write
    |
    v
After rollback window closes
CONTRACT Migration
  - drop old columns, apply incompatible constraints
  - this is the point where rolling back to A may no longer be safe
~~~

| DB Change | Safe for Rollback to A? | Notes |
| --- | --- | --- |
| Add nullable column | Usually yes | A can ignore the new column. |
| Add index | Usually yes | Watch index build duration and locks. |
| Add NOT NULL column without default | Potentially no | A's INSERT omitting the column will fail. |
| Rename/drop column A reads | No | A can no longer run. |
| Change meaning of `amount` | Dangerous | A parses it yet computes wrong results. |
| One-way data backfill | Conditional | Needs reconciliation/recovery path if wrong. |

**Database schema rollback is not always "running a down migration."** If B wrote data under the new schema, down migrations can lose data. Prefer expand–contract, feature flags, and maintaining backward compatibility until the rollback window ends.

### Interaction with Schema Registry

Message schemas and database schemas are two separate contracts. Keeping DB tables compatible **does not** guarantee consumer A can deserialize message B. Both must be tested.

## 11. Retry, DLT, and Error Handlers When Reverting to A

In Spring Kafka, releases can alter:

- `DefaultErrorHandler`, retry counts, and `BackOff`.
- `DeadLetterPublishingRecoverer` and DLT destinations.
- `@RetryableTopic`, retry topics, and naming conventions.
- Deserialization exception handling.
- Headers, trace/context, and DLT message formats.
- Acknowledgment/seek/commit behavior.

A new version may send failed events to a DLT with payloads/headers **the old version does not understand**. Rolling back to A and automatically reprocessing the DLT can trigger a poison-message loop.

### Failure Flow to Analyze

~~~text
Source topic record
        |
        v
Release B consumer
        |
        +-- retry succeeds --> DB side effect
        |
        +-- retries exhausted --> DLT (new schema/headers)
                                  |
                             rollback A
                                  |
                                  v
                         A reprocesses DLT?
                            compatible?
~~~

To roll back safely:

1. Keep DLT formats compatible or provide an adapter.
2. Never auto-replay the entire DLT before resolving the root bug.
3. Track DLT counts/lag and classify errors.
4. Ensure no message is processed twice when rolling back mid-retry.
5. Maintain a quarantine/parking policy for payloads A cannot parse.
6. Reconcile idempotency keys when replaying DLT records.

Do not assume every error handler delivers the exact same retry attempts across versions; test boundaries on your exact library version.

## 12. Kafka Transactions and Producer `transactional.id`

If the application uses Kafka transactions or Spring Kafka's consume-transform-produce Exactly Once Semantics, rollbacks must evaluate:

- Where producer transactions begin/commit/abort.
- Whether `transactional.id` prefixes stay stable and unique per instance as required.
- Producer fencing when a new producer reuses the same `transactional.id`.
- Transaction markers and uncommitted records.
- Consumer `isolation.level=read_committed` where required.
- Database side effects outside Kafka transactions remaining unprotected automatically.

~~~text
Release B transactional producer
         |
         +-- Begin Kafka transaction
         +-- Produce output
         +-- Commit offsets in transaction
         |
       (Pod shutdown)
         |
         v
Release A producer comes up
  transaction identity/epoch rules apply
  unfinished transactions must be resolved
~~~

Do not arbitrarily change `transactional.id` to "fix" fencing; two producers may end up active concurrently and break EOS assumptions. Likewise, never reuse **the same `transactional.id`** across two concurrently active instances.

When rolling back transactional apps, rely on the lifecycle/fencing behavior provided by your Spring Kafka and Kafka client versions, shut down old instances cleanly, and test rolling overlap. Exact EOS mode and factory settings must follow documentation for your chosen Spring Kafka and broker versions.

## 13. Kafka Streams: Rollback Also Involves State Stores

Kafka Streams differs from ordinary record listeners because apps can persist **local state stores** and rely on **changelog topics** for recovery.

For example:

~~~text
orders.events
     |
     v
Kafka Streams topology
     |
     +-- aggregate by account
     |
     v
RocksDB local state
     |
     v
Changelog topic + checkpoint
```

If release B alters topology, SerDes, or state-store formats, version A may fail to read state written by B. Image rollback can fail or yield inconsistent state.

Before upgrading a Streams app:

- Check topology/state-store names and SerDe backward compatibility.
- Review Kafka Streams DSL and Processor API changes.
- For state migrations, follow procedures supported by Kafka Streams docs.
- Retain snapshots/backups, retention, and immutable source data needed to rebuild.
- Never delete state directories/changelog topics in production as a first reflex.
- Consider running the new topology alongside the old one with a different `application.id` to compare outputs, ensuring **no duplicate side effects** are emitted.
- Handle `application.id` carefully: changing it alters group identity, internal topics, and state, not just an app display name.

**Kafka Streams rollback may require a reverse state migration plan or rebuilding from immutable inputs**, not just a rolling update.

## 14. Broker Downgrade Is Completely Different from App Rollback

A Java Deployment rollback command **does not** revert Kafka brokers to an older version. A broker upgrade may have changed:

- Metadata formats and cluster feature levels.
- Inter-broker protocol or how brokers use feature flags.
- Raft/KRaft controller metadata, depending on cluster version/config.
- Log/message formats and feature activation.
- Client/broker protocol compatibility windows.
- Metadata/topic/ACL migrations.

Never downgrade brokers just because a new Spring Kafka consumer fails. First classify whether this is an **app regression**, **client compatibility issue**, or **broker incident**.

For brokers:

1. Read exact upgrade/downgrade documentation **from version X to version Y**.
2. Check metadata/feature levels and whether a supported downgrade path exists.
3. Ensure backups, capacity, and cluster health procedures are ready.
4. Test beforehand in a production-like environment.
5. Execute only via the Kafka infrastructure team's runbook.

If Kafka already raised feature levels past the point of no return, demanding an "immediate downgrade" may be **unsafe or unsupported**. Use a forward-fix or a dedicated disaster recovery plan rather than running ad-hoc commands.

## 15. Rollout Strategies That Make Rollback Actually Work

### 15.1. Rolling Deployment

~~~text
T0: A A A
T1: A A B
T2: A B B
T3: B B B

Rollback:
T4: A B B
T5: A A B
T6: A A A
~~~

During the overlap window, A and B must work compatibly on the same topic/group and side effects. Bugs appearing only when A and B run concurrently must also be tested.

### 15.2. Single-Pod Canary

One Pod B can run early to observe metrics. Yet in a Kafka consumer group, one canary in the same group **does not receive a fixed HTTP-style percentage of traffic**. It receives only the partitions assigned by the Kafka coordinator.

If a topic has a single partition, the canary gets either 100% of traffic or 0%. Never claim "1 canary Pod = 10% Kafka traffic." Watch actual partition assignments and real message volume.

### 15.3. Shadow Consumer

A consumer B using a **different group ID** can read a logical copy of the event stream to compare results without blocking group A. However, it maintains separate offsets and may read the entire backlog; you must:

- Put shadow B in **read-only mode or isolated side effects**.
- Guarantee it never sends real payments, emails, or DB mutations.
- Apply appropriate throughput limits and permissions.
- Never confuse shadow group state with production group committed offsets.

Shadowing validates schemas and logic, yet cannot replace canary/rollback tests where B owns real production group partitions.

## 16. Kubernetes Rollout History and Limits of `rollout undo`

Suppose a Deployment is named `orders-worker` in namespace `production`.

### 16.1. Inspect Before Intervening

~~~bash
kubectl get deployment orders-worker -n production
kubectl rollout history deployment/orders-worker -n production
kubectl rollout status deployment/orders-worker -n production
kubectl get pods -n production -l app=orders-worker
~~~

Read the output to check revisions, images, and Ready Pods. Note that a Deployment revision mainly captures the **Pod template**, not a full snapshot of databases, offsets, ConfigMaps, and Secrets.

### 16.2. Rolling Back Image/Pod Template

~~~bash
# Only after deciding to roll back per runbook:
kubectl rollout undo deployment/orders-worker -n production

# Watch Pod rollout status:
kubectl rollout status deployment/orders-worker -n production
~~~

You can target an explicit revision:

~~~bash
kubectl rollout undo deployment/orders-worker \
    -n production --to-revision=12
~~~

**The commands above are documentation examples only, not executed in this lesson.** Verify what image/config references revision 12 holds before applying. With GitOps, the controller may reconcile the Deployment back to Git's desired state; rollbacks must therefore align with the GitOps source of truth.

### 16.3. Do ConfigMaps/Secrets Roll Back Automatically?

Not automatically. If the Pod template still references `orders-config` by a fixed name, the ConfigMap's current contents may still belong to B even after the image reverts to A. Similarly, a rotated Secret may no longer work with client A.

Restore **a compatible image + config version pair**, including:

- Kafka `bootstrap-servers`, topic names, and `group-id`.
- Serializer/deserializer classes and schema version references.
- SASL/TLS settings or secret versions.
- Listener concurrency, ack mode, and retry/DLT policies.
- Feature flags and database migration compatibility.

In GitOps/Helm, pin a commit/release containing all non-secret values; secrets keep their own lifecycle and rotation policy.

## 17. Quiescing Consumers and Handling In-Flight Work

A sensitive rollback may require **pausing incoming message consumption** to curb further side effects while avoiding abruptly killing Pods.

Quiesce goals:

1. Stop handing new work to the misbehaving version unexpectedly.
2. Let in-flight records finish or roll back per policy.
3. Ensure containers/producers flush and complete ack/transaction lifecycles cleanly.
4. Observe consumer group rebalances and committed offsets.
5. Start A in a verified state and resume processing.

Spring Kafka supports managing listener containers (pause/resume/stop) via `KafkaListenerEndpointRegistry` or corresponding container APIs. Conceptual example:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

public final class ConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null) {
            throw new IllegalArgumentException("Unknown listener");
        }
        container.pause();
    }

    public void resume(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null) {
            throw new IllegalArgumentException("Unknown listener");
        }
        container.resume();
    }
}
~~~

This example assumes the app declared `@KafkaListener(id="ordersListener", ...)` and exposes a secured operational API for control calls. `pause()`/`resume()` semantics are not strictly instantaneous; monitor actual container/assignment state. Never expose pause/resume endpoints publicly or perform unaudited manual actions.

Running `kubectl scale deployment --replicas=0` stops consumers, yet **does not guarantee all in-flight records/transactions finished cleanly**. For graceful shutdown, configure appropriate termination grace periods, listener stop timeouts, and producer close behavior, then reconcile.

## 18. Observability: Deciding Whether to Roll Back

Do not judge health solely by liveness/readiness or CPU. A Pod can report Ready while its consumer receives zero records due to a group authorization failure.

Signals to watch:

| Signal | Source | Question |
| --- | --- | --- |
| Consumer lag by group/topic/partition | Kafka metrics/exporters | Is backlog growing after deploy? |
| Records consumed/s | Kafka client metrics | Are records being processed? |
| Listener failure/retry rate | Application metrics | Are business errors climbing? |
| DLT volume/rate | DLT topic and app metrics | Are more records being parked? |
| Commit latency/rebalances | Kafka client metrics | Are consumers losing partitions? |
| Producer send errors/latency | Producer metrics | Are sends getting broker ACKs? |
| DB duplicate/idempotency conflicts | Business metrics/audits | Are side effects duplicating? |
| Business totals/checksums | Application DB/audits | Is data missing or wrong? |
| Version labels | Deployment/observability | Which release emitted each metric? |
| Authentication/ACL failures | Kafka client logs/metrics | Are configs/security broken? |

Exact metric names vary by Spring Kafka, Micrometer, Kafka client, and exporter versions. Never hardcode PromQL for a metric not yet verified in the real environment.

### Sample Canary Success Criteria

~~~text
Within the defined observation window:
- Consumer holds real partition assignments.
- Error rate does not exceed agreed thresholds.
- Consumer lag does not grow continuously from processing errors.
- DLT shows no new error categories.
- Producer send failures do not rise.
- Zero business records lost or duplicated outside semantics.
- DB migrations/serializers remain compatible with A.
- Rollback path to A has been tested.
~~~

A canary receiving zero records is **not enough evidence** to expand rollout, even when Pods are Healthy and error metrics are zero.

## 19. Rollback Decision Checklist

| Item | Gate Question |
| --- | --- |
| Release artifact | Is image A still in the registry with a verified digest? |
| Config | Can A run with current config or must values/secrets revert too? |
| Schema | Can A read records already emitted by B? |
| Kafka offsets | Is group ID preserved, committed positions understood, and no reckless reset planned? |
| Database | Has contract migration avoided breaking A? Is B-written data compatible? |
| Side effects | Are idempotency or reconciliation plans ready? |
| Retry/DLT | Can A parse payloads on retry/DLT topics and is parking available? |
| Kafka transactions | Have transactional ID/prefix/fencing and shutdown been checked? |
| Streams | Can A read B's state/changelogs/topology? |
| Infra | Are broker versions/protocols/ACLs still compatible? |
| Monitoring | Do before/after metrics and release markers exist? |
| Freeze | Should producers stop or consumers pause to protect data contracts? |
| Rollback authority | Who is authorized to decide and who owns the data? |
| Validation | Are integration/canary recovery tests in place? |

If unsure whether A can handle messages already produced by B, do not roll back to A merely because it is the fastest button to press. You may need to **roll forward** with a compatible hotfix to avoid corrupting data.

## 20. Practical Runbook: Consumer App Fails After Deploy

Suppose A was stable, while B causes deserialization errors and rising DLT rates.

### Phase A — Triage

1. Record release revision, timestamp, image digest, and config commit.
2. Confirm group/topic/cluster were not altered unintentionally.
3. Capture failing record/sample details **with secrets/PII stripped**.
4. Check whether B emitted new event types/schemas.
5. Determine the scope of database mutations and DLT records.
6. Check whether A can process remaining queued records and records B already created.

### Phase B — Containment

1. If producer B is emitting an incompatible schema, use feature flags or a controlled pause to stop emitting more.
2. If consumer B is writing corrupt data, pause/stop per runbook and check in-flight work.
3. Preserve data and offsets; never delete topics/DLTs to "clean up."
4. Save snapshots/audits/metrics needed for reconciliation.
5. Lock in image A and its matching config version.

### Phase C — Rollback

1. Revert GitOps/Helm values or verify the Deployment revision containing exact A.
2. Restore **non-sensitive configs** and compatible secret references without reintroducing revoked credentials.
3. Roll out A via the tested strategy while watching readiness and Kafka assignments.
4. Verify A hits zero deserialization failures on the existing backlog.
5. Monitor retry/DLT, consumer lag, and throughput.

### Phase D — Verify Data

1. Reconcile event IDs across the business window.
2. Check for duplicate business side effects and run idempotency audits.
3. Inspect DLT records needing repair/replay.
4. Compare unprocessed counts via lag and output totals.
5. Close incident status; unfreeze producers/streams only after verification completes.

### Phase E — Prevention

1. Add contract tests proving A reads payloads produced by B.
2. Update upgrade plans/data migrations.
3. Document any group ID/config/feature flag changes.
4. Improve observability and quiesce controls.
5. Write a runbook for the exact failure class encountered.

## 21. Testing Compatibility with Producer B and Consumer A

An effective test has the **new code/schema produce records**, then forces the **old version to read** them.

~~~text
Test fixture:
  B serializer -> test Kafka topic -> A deserializer

Expect:
  A parses successfully
  A validates successfully
  A produces right business output
  A creates no extra/duplicate side effects
~~~

If running two versions in one JVM is inconvenient, run two separate processes/container images against a test Kafka broker, or store **golden payloads** produced by B and run A's contract tests against them.

### Golden Payload Tests

~~~java
// Pseudocode illustrating a contract test, independent of fixed format.
byte[] producedByB = loadFixture("order-created-v2.bin");

OrderEvent event = decoderFromReleaseA.decode(producedByB);

assertEquals("evt-1002", event.eventId());
assertEquals("order-502", event.orderId());
assertEquals(2300L, event.amount());
~~~

With Avro/Protobuf/JSON Schema, pass through **real serializers and deserializers** with exact versioned schemas/references rather than parsing JSON manually and assuming compatibility.

Also test:

- B reading A's events.
- A reading B's events when rollback is required.
- A handling error headers/DLT records created by B.
- Schema Registry compatibility for the right subject/format.
- Unknown fields, defaults, new enums, field types, and semantic units.
- Events written before, during, and after the overlap window.

## 22. Rollback Integration Testing with Testcontainers

Testcontainers Kafka + PostgreSQL can build an isolated end-to-end scenario:

~~~text
Test Kafka broker + Test PostgreSQL DB
            |
            v
Seed v1 records
            |
            v
Start consumer A
  assert outputs + committed offsets
            |
            v
Stop A gracefully
            |
            v
Start consumer B
  produce/consume v1,v2 per contract
            |
            v
Stop B gracefully or inject crash
            |
            v
Start A with SAME group.id
            |
            v
Assert:
  A can read remaining messages
  zero duplicate rows/side effects
  offsets advance as expected
  DLT/retry semantics match policy
~~~

Run each version from its actual artifact rather than toggling a feature flag inside one codebase when testing **binary compatibility**. Testcontainers Kafka brokers use an image and API matching your pinned Testcontainers version.

### Fault-Based Test Matrix

| Scenario | What Must Be Proven |
| --- | --- |
| Canary B consumes successfully | B gets assignments and right outputs, not just Pod Ready. |
| B emits additive schema | A deserializes, validates, and processes cleanly. |
| B emits new enum | A does not misprocess or follows approved fallback. |
| B commits DB then crashes before offset commit | A's redelivery creates zero duplicates. |
| B alters retry policy | DLT and retry topics do not stall when A returns. |
| B changes group ID | Test catches shifted identity/offsets rather than treating it as rollback. |
| Database ran expand schema | A continues reading/writing cleanly on expanded schema. |
| Database ran contract dropping column | Test blocks rolling back to A or requires an alternative plan. |
| Producer B sends uncommitted Kafka TX | Per isolation policy, A does not process uncommitted data. |
| Secret rotated from A to B | Binary A can use current credentials or has a compatibility plan. |
| Rollback mid-rebalance | Zero lost data; verify idempotency. |
| Kafka Streams topology changed | State/changelog compatibility tested or separate migration exists. |

## 23. Inspecting Offsets Does Not Mean Auto-Resetting Offsets

When investigating consumer lag or positions, use Kafka CLI in an authorized environment.

~~~bash
# Illustrative syntax with Kafka CLI and proper auth config:
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9093 \
  --command-config client.properties \
  --group orders-worker-v1 \
  --describe
~~~

Provide `client.properties` via a secret manager or secured file; never print JAAS/passwords in logs or command-line arguments.

`--describe` displays committed offsets, log end offsets, lag, and group membership depending on Kafka CLI version. This is **read-only observation**, altering no offsets.

**Never run `--reset-offsets --execute` as a default rollback step.** Resetting offsets can replay massive data volumes or skip records; it requires a dedicated data-repair plan, idempotency, maintenance window, dry-run preview, and approval.

If offsets must change due to a data incident, stop active consumers in the group, lock down exact topic-partition-offsets, check retention, and reconcile outputs; resetting itself never undoes committed transactions.

## 24. Why Config Rollback Must Accompany Image Rollback

Suppose B added:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker-v2
    properties:
      isolation.level: read_committed
app:
  kafka:
    orders-topic: orders.events.v2
~~~

Reverting the image to A while keeping this config can make A:

- Read from group v2 lacking A's offsets.
- Read topic v2 with a schema A does not support.
- Receive unexpected traffic volume or zero records.
- Use TLS/SASL settings/secrets unsupported by older dependencies.

Image + config must therefore be treated as **one release unit**. With Helm, do not rely on `helm rollback` to assume Kafka data/offsets also reverted; Helm manages only release manifest resources, while external state remains.

Feature flags must have their own rollback procedure. A flag B flipped to default `true` in a config service may stay enabled after binary A returns.

## 25. When to Choose Roll Forward Instead of Rollback?

Not every failure should trigger a rollback:

| Situation | Usually Safer Approach |
| --- | --- |
| B has a Java bug while schema/data stay compatible with A | Rollback to A may fit. |
| B already emitted events unreadable by A | Hotfix B or compatibility adapter; hold off rolling back A. |
| Database contract dropped a column A needs | Roll forward/hotfix or verified restore migration. |
| Kafka Streams state changed format | May need a forward-fix or dedicated state migration. |
| Old credentials were revoked | Keep new credentials and make A compatible; never restore revoked secrets. |
| Broker cluster enabled a new feature level disallowing downgrade | Do not blindly downgrade brokers; evaluate forward-fix/DR. |
| B already wrote wrong business data | Containment and separate data repair; image rollback does not fix bad stored data. |

**Rollback is conditional**, not a knee-jerk reflex for every production incident.

## 26. Security Notes During Rollback

When investigating version incidents:

- Never copy JAAS passwords, tokens, or TLS private keys into tickets/logs.
- Never turn on debug dumps of the entire Spring Environment/Kafka Properties.
- Never roll back secrets to revoked or suspected-compromised credentials.
- Restrict permissions on Kubernetes Deployments, group offsets, and topic ACLs.
- Audit who approved the rollback, which revision, when, and what changed.
- Protect golden payloads and production samples containing personal data.
- Never put tokens in Prometheus labels; use low-cardinality release version, group, topic, and error category.
- Ensure Kafka inspection commands use securely provisioned auth configs.

Good operations require both **reliability** and **security**: fixing an outage by disabling TLS or granting Cluster-All ACLs usually triggers a far worse incident.

## 27. Common Mistakes

**1. "Rolling back the image restores the entire pre-deploy state."** False: DB, Kafka offsets, topics, Schema Registry, and external side effects remain.

**2. "Change the group ID to clear consumer lag."** False: creates a different consumer identity; risks replays or skipped backlogs.

**3. "Reset offsets so the data becomes right again."** False: resets do not undo side effects and easily cause duplicates or loss.

**4. "B reads A's events, so A definitely reads B's events."** False: backward compatibility does not imply forward compatibility.

**5. "Serializer parses cleanly, so the schema is safe."** False: field semantics, required validations, and business rules may have changed.

**6. "Every DB migration has a down script."** Data written by B may be incompatible with A; down migrations can destroy data.

**7. "One canary Pod means 10% of Kafka traffic."** False under Kafka consumer group partition assignment.

**8. "ConfigMap/Secret rollbacks are managed by Kubernetes Deployment revisions."** Not automatically.

**9. "A can definitely read B's DLT records."** Headers/payloads, serializers, or retry topic names may have changed.

**10. "`acks=all` + idempotence prevents database duplicates."** Producer idempotence never replaces application idempotency.

**11. "Force-killing Pods ends transactions cleanly."** In-flight work and commits must be reconciled.

**12. "You can downgrade Kafka brokers just like rolling back a consumer JAR."** Broker metadata/feature levels enforce strict support limits.

**13. "Kafka Streams state can always be read backward."** Topology/serde/changelog changes can prevent old builds from recovering.

**14. "Readiness is green, so no rollback is needed."** Business outputs can still be wrong while Pods are Ready.

**15. "Re-deploy A after B and check only exit codes."** Tests must verify record IDs, output totals, idempotency, lag, and DLT.

## 28. Hands-On Exercises

### Exercise 1 — Separate App Rollback from Data Rollback

Describe releases A/B of a Kafka consumer backed by PostgreSQL. List what a Kubernetes Deployment can roll back vs. what cannot auto-revert. Design a release manifest table with image digest, config, schema, and DB revision.

### Exercise 2 — Old Consumer Reads New Payload

Create two v1/v2 DTOs/serdes, adding one optional field in v2. Produce an event with v2 serializer and read it with v1 deserializer. Then change the unit meaning of `amount` while keeping a numeric type and prove a passing parser is insufficient for business correctness.

### Exercise 3 — Crash After DB Commit

In Testcontainers Kafka/PostgreSQL, process event E1 and commit the database, then simulate a crash before the Kafka offset commit. Restart the consumer in the same group and confirm E1 redelivers while the business side effect occurs only once.

### Exercise 4 — Group ID Drift

Test consumer groups v1 and v2 on a test broker. Compare committed offsets and behavior under `earliest`, `latest`, and `none`. Explain why binary rollbacks must preserve the exact group identity.

### Exercise 5 — Expand–Contract DB

Have A write to `orders(id, amount)`. Add a nullable/defaulted `currency` column and deploy B. Test A still runs after B writes valid rows. Next drop a column A requires in a test to prove contract migrations block rollback.

### Exercise 6 — DLT Compatibility

Have B emit new headers and schemas on the DLT. Write a test where A reprocesses or safely parks DLT records. Never auto-forward all DLT records back to source topics without an idempotency/replay plan.

### Exercise 7 — Partitioned Canary

Create a 3-partition Kafka topic with 2 A consumers and 1 canary B consumer in the same group. Observe assignments before/after rebalance and prove B does not receive a fixed percentage of traffic.

### Exercise 8 — Kafka Streams State

Build two topologies with different state stores/SerDes in a test environment, simulate upgrading, then start the old version. Document when migration or rebuild is required; never wipe changelogs/state in production.

### Exercise 9 — Kubernetes Runbook

In a test namespace, deploy A, roll out B, and revert to A via `kubectl rollout undo`. Prove ConfigMaps and DB data retain changed values unless rolled back separately. Check outputs after both rollouts.

### Exercise 10 — Disaster Drill

Simulate release B emitting v2 events incompatible with A. Decide whether to stop producers, roll back, hotfix, or deploy an adapter; document rationale, data impact, reconciliation, and traffic-resume criteria.

## 29. Official References

- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Non-blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [Apache Kafka — Upgrade and Compatibility](https://kafka.apache.org/documentation/#upgrade)
- [Apache Kafka — Kafka Streams Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Kubernetes — Deployments and Rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

