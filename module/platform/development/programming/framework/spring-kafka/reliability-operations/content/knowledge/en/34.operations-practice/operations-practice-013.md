# Production Readiness Checklist for Spring Kafka

A system using Spring Kafka may work fine on a developer machine and still fail immediately after going to production: the producer cannot write to a topic due to a missing ACL, consumer lag spikes when a Pod is replaced, messages are processed twice after a rebalance, retry topics have not been provisioned, or the DLT receives failures with nobody handling them. **Production readiness** is the level of readiness across **design, technical verification, monitoring, and operational procedures**, not merely the application's ability to start up successfully.

This is the **“Production Readiness Checklist”** lesson in **Spring Kafka Reliability Operations → Operations Practice**. The content serves as a document you can use for a pre-go-live review session, along with guidance on gathering evidence, defining **GO/NO-GO** criteria, testing failure scenarios, and preparing runbooks for incidents.

> **Acceptance principle:** A checklist item is only marked `PASS` when there is **evidence in a sufficiently representative environment**, an assigned owner, and clear acceptance criteria. `The application ran without errors for 10 minutes` is not evidence that messages will not be lost or duplicated when a broker, consumer, or database fails.

## 1. Objectives, Scope, and Evaluation Principles

A production Kafka system must be able to answer these minimum questions:

1. **Data ingestion:** Can the producer write messages with durability matching the SLA, including during broker leader changes?
2. **Data processing:** Does the consumer commit offsets properly after completing the business side effect?
3. **Failure handling:** Which records are retried, which go to the DLT, who handles them, and can records be lost during error forwarding?
4. **Redelivery:** When a process crashes, rebalances, or redelivers a message, does the business effect remain accurate?
5. **Operations:** Are there dashboards, alerts, on-call rotation, runbooks, and a way to know whether backlog can be drained before retention expires?
6. **Security:** Do apps and automation have the right topic/group/transactional ID permissions, without leaking secrets or breaking tenant isolation?
7. **Changes:** Can you perform rolling deployments, scaling, client/broker upgrades, and rollbacks without losing backlog or breaking payload compatibility?

### 1.1. Scope Under Review

```text
               Ingress / Business API
                         |
                         v
                Producer / Outbox
                         |
                         v
                Main Kafka topics
                         |
          +--------------+---------------+
          |                              |
          v                              v
    Spring Kafka consumer          Other consumer groups
          |
       Business DB / API
          |
     +----+----------+
     |               |
  Success      Error handling
                     |
          +----------+----------+
          |                     |
      Retry path               DLT
          |                     |
    Backoff / retry        Review / replay
          |
     Success / DLT

Cross-cutting: IAM/ACL, schema, capacity, observability,
deployment, incident response, backup, and rollback.
```

If the system only has a producer, skip consumer items **with a documented reason**. If using Kafka Streams or Connect, add separate checklists for internal topics, changelogs, task restarts, connector offsets, and state restoration. Do not mark an out-of-scope item as `PASS`; use `N/A` with an explanation.

### 1.2. Decision Levels

| Result | Meaning | Decision |
| --- | --- | --- |
| `PASS` | Evidence meets the agreed criteria | Can proceed with review |
| `FAIL` | Criteria not met; uncontrolled failure path exists | Fix and re-verify |
| `NOT_TESTED` | No evidence yet or test has not run in a suitable environment | Do not count as passing |
| `N/A` | Item does not apply to the architecture, with justification and owner sign-off | Non-blocking if approved |
| `RISK_ACCEPTED` | Quantified deviation, approved by an authorized person, with compensating controls and an expiry | Allowed only if organizational policy permits |

**GO** when every release-blocking item is `PASS` or has a properly approved exception, critical alerts are active, and rollback is executable. **NO-GO** if there is an unexamined risk of data loss, retry/DLT does not work, production access permissions are missing, idempotency cannot be verified, or there is no recovery plan.

## 2. Information Sheet Before Starting the Review

Before marking the checklist, fill out a sheet matching the release scope:

| Field | Illustrative Value | Why It Is Needed |
| --- | --- | --- |
| Service / Release | `orders-worker` / `1.14.0` | Identifies the image/code being verified |
| Spring Boot / Spring Kafka | Boot 3.x / Spring Kafka 3.x | Bounds API and behavior compatibility |
| Kafka Java client | Version from `runtimeClasspath` | The version actually running, not just declared |
| Kafka cluster | `kafka-prod-a` | Brokers, region, quorum, and policies |
| Main topics | `orders.events` | List of input/output topics with owners |
| Retry/DLT | `orders.events-retry-*`, `orders.events-dlt` | Identifies the full error pipeline |
| Consumer group | `orders-service` | Identifies offsets and assignments |
| Business key | `tenantId + orderId + eventVersion` | Defines business uniqueness |
| SLA/SLO | Example: 99.9% valid events processed within 5 minutes | Translates into measurement and alert thresholds |
| Verification environment | Staging Kafka matching production | Evaluates test reliability |
| Deployment strategy | Rolling 1 Pod at a time | Understands rebalance impact |
| Responsible owners | App owner, Kafka platform, Security, On-call | Leaves no gaps in ownership handoff |
| Rollback target | Previous release image and compatible config | Prevents rolling back code while breaking schema |

The SLO here is an **example**, not a threshold prescribed by Spring Kafka. When calculating SLA, clearly define the denominator: all ingested messages, only valid messages, or messages acknowledged by the producer? That definition directly affects dashboards and how success is measured.

### 2.1. Transaction and Ownership Boundaries

Map out Kafka actions and business data mutations clearly:

```text
Kafka record
   |
   v
@KafkaListener
   |
   +--> validate / deserialize
   |
   +--> BusinessService @Transactional
   |          |
   |          v
   |       Database commit
   |
   +--> callback finishes successfully
   |
   v
Container commits Kafka offset according to AckMode
```

With this diagram, the database commit and the Kafka offset commit are **not a single atomic transaction**. If the process crashes in between, the record can be redelivered. Therefore, an idempotent business effect is a core requirement. Do not write in documentation that `AckMode.RECORD` guarantees exactly-once semantics for an external database.

## 3. Quick Checklist for the GO/NO-GO Meeting

This is a short executive table. Subsequent sections explain the criteria and verification examples.

| Code | Control Gate | Go-Live Blocking Condition | Typical Owner |
| --- | --- | --- | --- |
| `G01` | Event contract and idempotency | Business key, version, replay, and duplicate handling not defined | App / Domain |
| `G02` | Kafka topics | Missing topics, partitions, retention, or replication per SLA | Kafka Platform |
| `G03` | Producer durability | Leader restart not tested, missing `acks`/idempotence, or publish failures unhandled | App / Platform |
| `G04` | Consumer offset & failure | Offset could commit before business success or poison messages unhandled | App |
| `G05` | Retry & DLT | Retry topics/DLT/ACL missing or forwarding fails while record is treated as done | App / Platform |
| `G06` | Security | Overly broad principal permissions, unprotected secrets, or TLS/auth failures | Security / Platform |
| `G07` | Observability | Missing lag, error, or retry/DLT metrics; alerts do not reach on-call | SRE / App |
| `G08` | Capacity & resilience | No load test, no rebalance/crash/scale test, unbounded backlog | App / SRE |
| `G09` | Deployment & rollback | No image pinning, no canary gate, or no rollback plan for schema/topic changes | Release owner |
| `G10` | Runbook & ownership | Unclear who handles DLT, offset resets, incidents, and backfill | On-call / Domain |

Any item `G01`–`G10` lacking evidence should generally be treated as **NO-GO** for critical business flows. Adjust blocking severity based on risk level and organizational policy, not simply because the release window is near.

## 4. Data Contract and Schema Checklist

Kafka brokers store records as bytes; business correctness depends on the schema and how producers/consumers interpret those bytes. A rollout may produce zero broker errors yet still break consumers due to a payload change.

### 4.1. Required Items

- [ ] **Clear topic ownership:** each topic has a business owner, operational owner, data classification, and SLA.
- [ ] **Stable event identity:** there is an `eventId`/business key that stays unchanged across re-publishes of the same logical event.
- [ ] **Meaningful event version:** distinguishes state transitions from duplicates and handles out-of-order updates properly.
- [ ] **Intentional message key selection:** events requiring ordering for the same entity are routed to partitions by an appropriate key.
- [ ] **Bidirectional schema evolution tested when needed:** old consumers read new data and new consumers read old data per the rollout contract.
- [ ] **No PII/secret leakage:** only required fields are published; masking/encryption and retention are appropriate.
- [ ] **Record size limits:** payloads do not exceed broker/topic/producer limits; an external blob reference strategy exists for large data.
- [ ] **Serializer compatibility:** key/value serializers, deserializers, headers, Schema Registry, and subject naming are verified.
- [ ] **Handling path for poison payloads:** deserialization failures do not cause unobservable infinite consumer loops.
- [ ] **Defined reprocess contract:** does re-sending the same event create a new effect, and which version/source wins?

### 4.2. Schema Change Example to Prepare For

Old payload:

```json
{
  "eventId": "ev-301",
  "orderId": "O-301",
  "amount": 1200
}
```

New payload:

```json
{
  "eventId": "ev-301",
  "orderId": "O-301",
  "amount": 1200,
  "currency": "VND",
  "eventVersion": 2
}
```

Adding a new field can be compatible if the old consumer ignores unknown fields and the new consumer has a sensible default. However, this depends on the serializer/parser and schema rules; **do not assume every JSON consumer ignores unknown properties**. For Avro/Protobuf/JSON Schema, use Schema Registry compatibility policies and fixtures from previous releases.

Examples of tests to include: reading the old payload with the new consumer, reading the new payload with the old consumer (if mixed-version deployment requires it), and testing that malformed records are actually routed to the appropriate error mechanism.

## 5. Kafka Cluster, Topics, and Capacity Checklist

An application with sound code can still lose data on failure if it uses a topic with replication factor 1 or overly short retention.

### 5.1. Topic Provisioning

- [ ] Main topics, retry topics, and DLT exist prior to deployment if production disables auto-create.
- [ ] Partition count supports the **desired parallelism** without growing unboundedly and causing metadata overhead.
- [ ] Replication factor matches cluster capability and data/SLA requirements (e.g., RF=3 on clusters with enough brokers, not treated as mandatory for every environment).
- [ ] `min.insync.replicas` is aligned with `acks=all`, with a policy for reduced ISR.
- [ ] Retention for main/retry/DLT covers downtime, backlog, reprocessing, and review time.
- [ ] Cleanup policy (`delete`, `compact`, or both) fits event semantics.
- [ ] Topic configs have an owner and change via IaC/change management; do not rely on implicit broker auto-creation.
- [ ] Retry topics have **enough partitions for routing** if the recoverer preserves the source partition.
- [ ] Topics have appropriate quotas/ACLs for producers, consumers, reprocessing, and admin tasks.
- [ ] Cross-region/DR policy is defined if disaster recovery is required.

### 5.2. Basic CLI Verification

The commands below are for operators in authorized environments:

```bash
# Topic name and brokers/partitions/replicas
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders.events

# Consumer group state, partition offsets, and lag
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service

# Kafka API capabilities advertised by brokers
kafka-broker-api-versions.sh \
  --bootstrap-server broker1:9092
```

For SASL_SSL/mTLS, add `--command-config` pointing to a secured CLI config. **Do not put passwords into commands, logs, or tickets** if policy forbids it. Reaching a single bootstrap server does not prove the client can reach every broker via `advertised.listeners`; test partition leaders and check network/certificate rules accordingly.

### 5.3. Processing Capacity and Backlog

Measure two quantities:

- **Input rate**: actual messages/s or bytes/s at normal load and peak load.
- **Processing throughput**: messages/s **successfully** processed by the consumer after side effects and offset strategy, not just poll count.

If sustained input rate exceeds throughput, consumer lag will grow even while the cluster reports no errors. Also evaluate **backlog drain time** to ensure sufficient margin before topic retention deletes old data.

Illustrative example:

```text
Peak input rate          = 5,000 messages/s
Consumer capacity        = 6,000 messages/s
Backlog after downtime   = 3,600,000 messages

Headroom for drain       = 1,000 messages/s
Estimated drain time     = 3,600 seconds ≈ 1 hour
```

This is an **idealized estimate**, excluding retry/DLT, rebalances, warm-up, DB limits, and throughput degradation under deep queues. In capacity testing, use real measurements with realistic payload distributions, partition skew, and downstream behavior to keep a safe buffer.

### 5.4. Limits to Measure, Not Guess

| Resource | Overload Symptom | Verification Suggestion |
| --- | --- | --- |
| Broker disk | Rising disk usage, insufficient retention, I/O latency | Check peak throughput and storage against SLA |
| Broker network | Rising produce/fetch latency | Load test with real compression/payloads |
| Partitions | One partition has high lag while the group has many consumers | Inspect key skew, hot partitions |
| Consumer CPU/heap | GC pauses, rising processing latency | Profiling and heap/GC metrics |
| Consumer group | Frequent rebalances, idle partitions | Inspect assignment, poll interval, deploy strategy |
| Database | Pool exhaustion, deadlocks, transaction timeouts | Test downstream under increased load |
| External API | Rate limits, timeouts, and retry storms | Backoff, bulkhead, idempotency, capacity agreement |

## 6. Producer Reliability Checklist

Producers must write messages to Kafka with clear semantics: when is a send considered successful, which errors retry, and what happens on callback timeout?

### 6.1. Mandatory Items

- [ ] `acks` and durability policy are chosen according to SLA; typically `acks=all` for critical data.
- [ ] `enable.idempotence` is enabled, or there is a clear reason if not used.
- [ ] `retries`, `delivery.timeout.ms`, `request.timeout.ms`, `linger.ms`, and `batch.size` are controlled and measured under real load.
- [ ] `max.in.flight.requests.per.connection` does not conflict with idempotence/ordering requirements.
- [ ] Every `KafkaTemplate.send()` **observes success/failure**, never firing-and-forgetting while assuming success.
- [ ] Record key/event ID remains stable when the application must re-publish a logical event.
- [ ] Do not send payloads before the required business transaction commits if there is a risk of state divergence; consider transactional outbox.
- [ ] On broker leader changes, producer retries and error handling follow policy.
- [ ] Alerts exist when publish errors, timeouts, or outbox backlog increase.
- [ ] Producer serializer and security principal have write permissions on all relevant topics.

### 6.2. Spring Boot 3.x / Spring Kafka 3.x Configuration Sample

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000

    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest

    listener:
      ack-mode: record
```

This is a **reference configuration**, not a drop-in production configuration. Adjust serializers, retry/transactions, broker addresses, security, and thresholds per SLA. `auto-offset-reset=earliest` only governs behavior when **the group has no committed offset or the offset is no longer valid** per client policy; it does not force the consumer to re-read the whole topic on every restart.

`enable-auto-commit=false` lets the Spring Kafka container manage commits per the acknowledgment mode. `AckMode.RECORD` suits a record-listener example without container transactions; for manual ack or Kafka transactions, commit semantics differ.

Producer idempotence is a safeguard within the Kafka producer protocol; it **does not automatically deduplicate two independent logical `send()` calls** if the application retries publishing as a new send after a timeout. For business guarantees, stable event identity is needed at the application layer.

### 6.3. Error-Observing Publish Sample

```java
package com.example.kafka;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderEventPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String payload) {
        return template.send("orders.events", eventId, payload);
    }
}
```

The caller needs to handle the `CompletableFuture`:

```java
publisher.publish(eventId, payload)
    .whenComplete((result, error) -> {
        if (error != null) {
            // Record publish failure; alert/retry using a stable event ID.
        } else {
            // Kafka acknowledged per producer config.
        }
    });
```

In Spring Kafka 3.x, `KafkaTemplate.send` returns a `CompletableFuture`; if a project still uses Spring Kafka 2.x, the API differs. **Do not change the `KafkaTemplate` version just to copy an example** while ignoring compatibility with Spring Boot, JDK, and brokers.

A successful callback means the broker acknowledged per producer config; it does **not** prove the business consumer has finished processing. Store the `eventId` and publish metadata for reconciliation.

### 6.4. Database → Kafka: Outbox Considerations

If an API both writes an order to the database and publishes an event:

```text
Business transaction:
  UPDATE orders
  INSERT outbox(event_id, payload, status=PENDING)
  COMMIT

Outbox publisher:
  read pending
  publish Kafka event
  mark published (with retries)

Consumer:
  dedup event_id/business key
  apply side effect idempotently
```

Outbox avoids the scenario where the database commits but the process crashes before calling `send`. However, the publisher can still re-send an event if a response is lost or marking status fails. **Outbox is an at-least-once publish pattern**, so consumers must still guard against duplicate processing. Do not promote outbox as proving end-to-end exactly-once without deduplication.

## 7. Consumer and Offset Correctness Checklist

Consumers must define clearly **when a message is considered successfully processed**. Committing the offset before the business transaction finishes risks losing business effects. Committing the business transaction before the offset means a crash can cause message redelivery.

### 7.1. Items to Confirm

- [ ] `group.id` remains stable across rolling deployments; change groups only for intentional migration/backfill.
- [ ] `auto-offset-reset` matches policy when a group has no committed offsets.
- [ ] `enable-auto-commit` and Spring Kafka `AckMode` are controlled, without two places managing offsets inconsistently.
- [ ] The listener only returns success/acknowledges **after** the required business effect has committed.
- [ ] Handlers are idempotent so they tolerate replay when DB committed but Kafka offset did not commit.
- [ ] Deserialization errors enter a controlled error handler/recovery path instead of getting stuck indefinitely.
- [ ] Error classification distinguishes transient faults, malformed payloads, code bugs, and infrastructure failures.
- [ ] `max.poll.interval.ms`, `max.poll.records`, processing duration, and concurrency are measured together.
- [ ] Consumers do not block indefinitely on downstream calls; appropriate timeouts, circuit breakers, and bulkheads exist.
- [ ] Rebalance callbacks and shutdown do not lose in-flight business state.
- [ ] Listener container startup/shutdown semantics are tested under Pod restarts.
- [ ] When pausing/resuming, the team distinguishes requested state from actual paused state.
- [ ] Do not rely on `autoStartup=false` or local pause state while forgetting to coordinate across replicas.

### 7.2. Offsets: The Right Mental Model

```text
Partition orders.events-0
Offset:        100 101 102 103 104

Handler has processed through record 101
Committed offset = 102  (offset of the next record)
```

A Kafka committed offset is normally the **next position to read**. Receiving a record in a listener does not mean it is committed. If the process is killed after processing 101 but before committing offset 102, record 101 may be redelivered. This is behavior you must test for, not automatically a Kafka bug.

### 7.3. Processing Time and `max.poll.interval.ms`

If a listener takes too long before returning to the poll loop, the consumer can be considered unresponsive, triggering a rebalance and replay. Indefinitely increasing `max.poll.interval.ms` only hides symptoms; measure throughput and identify root causes: DB locks, external API timeouts, too many records per poll, or CPU/GC pauses.

Settings to evaluate together:

| Property | Impact | Risk When Misconfigured |
| --- | --- | --- |
| `max.poll.records` | Maximum records returned per poll | Poll batch too large, slow callbacks, and rebalances |
| `max.poll.interval.ms` | Maximum time allowed between polls | Too short causes rebalances; too long delays detecting stuck processes |
| `session.timeout.ms` | Consumer failure detection in group protocol | Not equivalent to allowed business handler runtime |
| `heartbeat.interval.ms` | Heartbeat cadence in classic protocol | Must fit broker/client protocol; do not blindly apply to the new group protocol |
| `concurrency` | Multiple consumer threads/containers | Does not raise throughput if partitions are few or DB is saturated |
| `ack-mode` | When the container commits offsets | Wrong contract causes replay or lost effects |

With newer Kafka releases, the **classic and new consumer group protocols** have different heartbeat/session configurations. Apply only properties matching the actual mode, broker, and client version.

## 8. Idempotency and Transaction Boundaries

This is often the deciding factor for whether a critical-data workload can go live.

### 8.1. Scenario That Must Be Survived

```text
Consumer receives eventId=ev-101
        |
        v
Business DB write succeeds
        |
        v
Process dies before Kafka offset commit
        |
        v
New consumer redelivers ev-101
        |
        v
Business effect must not be duplicated
```

`@Transactional` on the database service rolls back DB changes together within the transaction, but **does not atomically bind the Kafka offset** without designing the corresponding transaction integration. In addition, external HTTP/email side effects outside the database transaction are not rolled back automatically.

### 8.2. PostgreSQL Example: Inbox/Dedup in the Same DB Transaction

Illustrative schema:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id       VARCHAR(80) PRIMARY KEY,
    latest_version BIGINT NOT NULL,
    state          VARCHAR(32) NOT NULL
);
```

Business service:

```java
package com.example.kafka;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(String eventId, String orderId,
                          long version, String state) {

        int inserted = jdbc.update("""
            INSERT INTO processed_event (consumer_name, event_id)
            VALUES ('order-projection', ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, eventId);

        if (inserted == 0) {
            return; // Same event already processed successfully earlier.
        }

        jdbc.update("""
            INSERT INTO order_projection(order_id, latest_version, state)
            VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                latest_version = EXCLUDED.latest_version,
                state = EXCLUDED.state
            WHERE order_projection.latest_version < EXCLUDED.latest_version
            """, orderId, version, state);
    }
}
```

This is a **PostgreSQL example**; do not copy the exact SQL for every database dialect. It assumes `eventId` genuinely identifies one logical event and both SQL statements run within the same database transaction. If the projection write fails, the transaction rolls back **the dedup record as well**, preventing retries from falsely treating it as completed. At the same time, `latest_version` stops older events from overwriting newer state if non-blocking retries reorder events.

`ON CONFLICT DO NOTHING` also has a downside: if two different payloads reuse the same `eventId`, bad data can be masked. For systems with strict audit requirements, also store a checksum/tenant/source and raise an alert when the key collides with differing content instead of silently ignoring it.

Record listener:

```java
@KafkaListener(
    id = "orderProjectionListener",
    topics = "orders.events",
    groupId = "order-projection"
)
public void handle(String jsonPayload) {
    OrderEvent event = parseAndValidate(jsonPayload);

    projectionService.applyOnce(
        event.eventId(),
        event.orderId(),
        event.version(),
        event.state()
    );
}
```

`OrderEvent`, `parseAndValidate`, and `projectionService` are application components to implement; this listener snippet illustrates where the transaction boundary sits. When `AckMode.RECORD` is configured, the container records callback completion, while the Kafka offset commit may occur afterward. If committing the offset fails, idempotency in the business service handles the replay safely.

**Idempotency acceptance checklist:** test sending the same `eventId` twice, test killing the process after DB commit and before offset commit, and test two competing consumer attempts; final output must be accurate per business key, rather than merely counting callback invocations.

## 9. Retry, Backoff, and DLT Checklist

A poison message must not keep a consumer stuck on one offset forever without alerting. At the same time, an invalid-schema record should not be retried forever because it will not magically become valid.

### 9.1. Options

| Mechanism | Characteristics | When to Consider |
| --- | --- | --- |
| Blocking retry in container | Re-attempts on main thread with backoff/error handler | Brief errors, better preservation of partition ordering |
| Non-blocking retry topics | Forwards to retry topic, processes after delay | Temporarily slow downstream, want to free the main consumer |
| DLT | Captures unprocessable records per policy | Need review/quarantine/reprocessing |
| Pause/resume | Temporarily stops pulling more records from partition/container | Maintenance or widespread downstream overload |
| Backfill/replay | Re-runs an input set after fixing the root cause | Intentional recovery, requires idempotency and audit |

**Non-blocking retries break cross-topic processing ordering guarantees.** For example, `ORDER_CREATED` moves to retry while `ORDER_CANCELLED` is processed on the main topic; late processing of `CREATED` can corrupt state if the projection does not check versions. Do not use non-blocking retry with batch listeners or container transaction configurations unsupported by Spring Kafka.

### 9.2. Required Items

- [ ] Exceptions are classified: transient, permanent/validation, deserialization, code/config, security.
- [ ] Retry budget exists: attempts, delays, total timeout, backoff/jitter as needed.
- [ ] `NullPointerException`, invalid schema, or unauthorized config are not retried like transient infrastructure faults.
- [ ] Retry topics and DLT have the right names, partitions, retention, replication, and produce/consume permissions.
- [ ] Forwarding `KafkaTemplate` properly serializes both normal payloads and raw bytes from deserialization errors (if used).
- [ ] Forwarding errors are tested: broker unavailable, ACL denied, serializer mismatch, invalid partition.
- [ ] A record is not treated as “safe in retry” before the broker acknowledges the forward via the appropriate mechanism.
- [ ] DLT handler or DLT review service has an owner, SLA, runbook, retention, and dedup.
- [ ] DLT reprocessing follows event/business key workflows instead of blindly resending and duplicating side effects.
- [ ] Metrics exist for **each retry stage**, DLT arrival, and oldest pending age.
- [ ] Changes to retry topic naming between releases are tested so old backlog is not orphaned.

### 9.3. Illustrative Configuration with `@RetryableTopic`

Spring Kafka 3.x example, **per-record** listener:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 2000,
        multiplier = 2.0,
        maxDelay = 8000
    ),
    include = {TemporaryDownstreamException.class},
    exclude = {InvalidOrderException.class},
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    autoCreateTopics = "false"
)
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "orders-service"
)
public void onOrder(String eventPayload) {
    orderService.applyIdempotently(eventPayload);
}

@DltHandler
public void onDeadLetter(String eventPayload) {
    quarantineService.saveForReview(eventPayload);
}
```

Exceptions, services, and imports must be declared in the real application. This snippet is **not a complete Java class**; its purpose is to illustrate policy. `attempts=4` generally counts the initial attempt plus the remaining retry attempts under the non-blocking policy. With `autoCreateTopics=false`, platform must provision all matching topics **before deployment**.

Retry topic names depend on `topicSuffixingStrategy`, backoff, topic reuse, and Spring Kafka version. Do not hardcode `orders.events-retry-0` for production based solely on an example without verifying the actual topic graph. If using transactions, Kafka Streams, or batch listeners, select a different suitable retry architecture.

### 9.4. DLT Does Not Mean Business Processing Is Complete

An event in the DLT usually has an **incomplete** business state. Track:

```text
eventId
sourceTopic / sourcePartition / sourceOffset
originalKey
errorCategory / exceptionClass
firstFailureAt / lastFailureAt / attempts
DLTTopic / DLTOffset
reviewStatus / reviewedBy
reprocessEventId / resolvedAt
```

Do not just dump raw payloads to logs and purge messages from the DLT. Payloads can contain PII; quarantine requires access controls, redaction/encryption, and retention approved by the domain owner.

## 10. Security, Identity, and Permissions Checklist

Production Kafka often needs more than `READ` on the main topic. The same service principal may need `WRITE` on retry/DLT, reads from generated consumer groups, transactional ID permissions, or Schema Registry access depending on the architecture.

### 10.1. Items to Confirm

- [ ] TLS/SASL/mTLS/OAuth is configured to match the cluster and verified with the real runtime image.
- [ ] `bootstrap.servers` and all advertised broker addresses are reachable; certificate hostname verification is not disabled.
- [ ] Secrets are provisioned via a secret manager, workload identity, or approved mechanism; no tokens in Git/logs.
- [ ] Producer principals only have `WRITE` on required topics and `DESCRIBE` per policy.
- [ ] Consumer principals have `READ` on main and retry/DLT as needed, plus corresponding consumer group permissions.
- [ ] DLT replay tools have separate credentials, auditing, and narrow permissions rather than cluster admin principals.
- [ ] Transactional producers have permissions on the corresponding transactional ID/resource.
- [ ] ACLs are tested with the **same identity type as production**, not just admin credentials.
- [ ] Schema Registry/KMS access matches payload format and encryption needs.
- [ ] Event payloads and logs have data classification, do not expose PII, and do not cross-route tenants.
- [ ] NetworkPolicy/firewalls/egress match broker advertised endpoints and dependencies.
- [ ] Key/certificate rotation, revocation, and incident response are tested or have runbooks.

### 10.2. Suggested Permission Matrix

| Principal | Topic/Resource | Typical Permissions | Notes |
| --- | --- | --- | --- |
| API producer | `orders.events` | `WRITE`, possibly `DESCRIBE` | Does not need topic delete permissions |
| Order consumer | `orders.events` | `READ` + group | Does not need `ALTER` topic |
| Retry forwarding producer | `orders.events-retry-*`, `orders.events-dlt` | `WRITE` | Must test actual failure branches |
| Retry consumers | Retry topics + corresponding groups | `READ` + group | Group IDs may be automatically suffixed |
| DLT review service | DLT topic + store/quarantine | `READ`, restricted data access | Reprocessing requires approval |
| Provisioning pipeline | Topics and ACL IaC | `CREATE/ALTER/DESCRIBE` as needed | Should not be granted to runtime apps |

Actual permissions depend on the Kafka broker/distribution/cloud provider (MSK, Confluent Cloud, etc.) and ACL/IAM model. Do not copy policies verbatim across providers without confirming action/resource mappings.

### 10.3. An Often-Skipped Security Smoke Test

A listener starting successfully **does not prove** retry/DLT forwarding has permissions. In staging:

1. Run the app with a production-equivalent service principal.
2. Send a record that triggers a transient failure.
3. Verify the record forwards to the right retry destination.
4. Keep the failure active so the record reaches the DLT.
5. Confirm the DLT consumer/quarantine receives the record.
6. Read logs to verify no `TopicAuthorizationException`, `GroupAuthorizationException`, or masked serializer error occurred.

This specifically tests **failure path authorization** and cannot be replaced by a happy-path producer test on the main topic.

## 11. Deployment, Resource, and Kubernetes Configuration Checklist

A consumer application can cause duplicate effects during a rolling deploy if two instances re-process records whose offsets were not committed yet. Readiness/liveness, shutdown, consumer group behavior, and capacity must be evaluated together.

### 11.1. Items to Meet

- [ ] Container image is pinned by version/digest and covered by SBOM/scanning per policy.
- [ ] Runtime versions for Java/JDK, Spring Boot, Spring Kafka, and `kafka-clients` are recorded.
- [ ] Resource requests/limits cover peak load, GC, and consumer thread count.
- [ ] Consumer `concurrency` fits partition assignment and downstream concurrency limits.
- [ ] Liveness does not kill the Pod merely because the consumer was intentionally paused or backlog grew.
- [ ] Readiness reflects true business serving capability, not just that the process is alive.
- [ ] Deployment strategy caps simultaneous Pod terminations, with suitable `maxUnavailable`/capacity headroom.
- [ ] `terminationGracePeriodSeconds` allows finishing or stopping in-flight work under normal conditions.
- [ ] Do not assume `SIGTERM` always guarantees Kafka offsets commit before process termination.
- [ ] Scale-out and scale-in have been tested for rebalances, idempotency, and lag recovery.
- [ ] HPA/autoscaling metrics use suitable backlog/capacity signals without causing constant oscillation.
- [ ] No two consumer instances share the same `group.instance.id` if static membership is enabled.
- [ ] Pod security context, secrets, and network policies are appropriate.
- [ ] Canary rollout and auto-stop gates exist if error/lag exceeds thresholds.

### 11.2. Kubernetes Deployment Configuration Example

Illustrative fragment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: orders-worker
          image: registry.example.com/orders-worker:1.14.0
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          env:
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: orders-worker-config
                  key: bootstrapServers
```

This is not a complete production manifest: you also need service accounts, image pull policy, security context, secrets, probes, and actual app variables. Values for `replicas`, memory, CPU, and `terminationGracePeriodSeconds` are only **examples**; base them on load tests, pod startup time, longest record processing time, and SLA.

**Do not configure a liveness probe that kills a consumer simply because of DLT backlog or a downstream pause.** Health checks should separate `process alive`, `Kafka connection`, `business readiness`, and `processing lag`; alert on lag without inducing restart loops.

### 11.3. Graceful Shutdown Must Be Proven by Tests

```text
Kubernetes sends SIGTERM
       |
       v
Spring context shutdown / Kafka listener container stop
       |
       v
Finish or release in-flight work within timeout
       |
       v
Commit offset per contract when processing succeeds
       |
       v
Consumer leaves group / partitions are reassigned
```

If a Pod is killed due to exceeding the grace period or OOM, partially processed records may be redelivered. **This is why idempotency must be tested**, not a reason to raise the grace period infinitely.

## 12. Observability and Alerting Checklist

Production systems need to separate **business success** from **merely reading messages from Kafka**.

### 12.1. Minimum Dashboard

| Group | Metric or Signal | What to Look For |
| --- | --- | --- |
| Producer | send success/failure, retries, request latency p95/p99 | Is Kafka accepting messages reliably? |
| Consumer | lag per group/topic/partition | Where is backlog accumulating? |
| Handler | processed success/failure, processing latency | Is business logic slow or failing? |
| Retry | arrivals, pending lag, oldest pending age | Are records waiting for retry longer than SLA? |
| DLT | arrival rate, unreviewed count, age | Are there unhandled poison events? |
| Offset | commit errors, rebalances, assigned partitions | Is the consumer group stable? |
| Broker | offline/under-replicated partitions, ISR, controller health | Are there availability/durability issues? |
| Database | connection pool usage, transaction failures | Is downstream becoming a bottleneck? |
| Idempotency | duplicates detected, conflicting payloads | Are there abnormal replays or duplicate publishes? |
| Deployment | image/version, active instances, recent rollout | Do incidents correlate with releases? |

Metric names depend on the Spring Kafka/Kafka client/Micrometer/exporter versions in use. **Do not assume Spring Boot exports all of these automatically**; some are custom application metrics, and others require broker exporters or control-plane monitoring.

### 12.2. What Should a Structured Log Contain?

```text
event=kafka.message.processing.failed
service=orders-worker
release=1.14.0
listenerId=ordersListener
groupId=orders-service
topic=orders.events
partition=2
offset=98321
errorCategory=DOWNSTREAM_TIMEOUT
retryDecision=RETRY
correlationId=trace-7cf8
```

Do not log raw payment cards, tokens, passwords, full JWTs, signed URLs, or unnecessary PII. If logging `eventId`/business keys, verify data policy permits it. In metrics, avoid using topic offsets, order IDs, eventIds, or correlationIds as labels because of **very high cardinality**; keep granular IDs in access-controlled audit logs.

### 12.3. Alerts Need Owners

- [ ] Producer error rate/timeouts exceed threshold.
- [ ] Consumer lag grows continuously or estimated drain time exceeds SLA.
- [ ] A single partition has abnormal lag while other partitions are normal.
- [ ] Retry pending age is high or retry rate spikes after a downstream incident.
- [ ] DLT arrival rate spikes or unreviewed DLT items exceed SLA.
- [ ] Forwarding to retry/DLT fails.
- [ ] Consumer group loses members, rebalances repeatedly, or fails offset commits.
- [ ] Broker offline partitions/ISR/quorum show anomalies.
- [ ] Business output reconciliation fails even when main lag is low.
- [ ] Every alert has tested **end-to-end delivery to on-call**, not just verifying a rule exists on a dashboard.

Example thresholds should be set per system: alert if the oldest retry record exceeds 70% of the SLA window, or estimated drain time exceeds remaining retention. Do not apply a single `lag > 1000` rule across every topic regardless of rate, partition count, and message size.

## 13. Pre-Production Testing Checklist

Reliability testing must cover failure paths. `@EmbeddedKafka` is suited for listener wiring and basic retries; Testcontainers or a staging Kafka cluster measures real behavior more accurately. Multi-broker ISR, KRaft quorum, and cloud ACL scenarios require a representative environment; you cannot prove them completely by mocking `KafkaTemplate`.

### 13.1. Test Matrix

| Test ID | Scenario | PASS Condition |
| --- | --- | --- |
| `T01` | Producer sends a valid message | Producer acks; consumer receives payload and produces right output |
| `T02` | Listener receives message with same eventId twice | Business side effect occurs only once per key |
| `T03` | Crash after DB commit before offset commit | Record can replay, output is not duplicated |
| `T04` | Crash before DB commit | No partial output created; record is reprocessed |
| `T05` | Broker leader restart | Producer/consumer recover, lag returns within threshold |
| `T06` | Consumer Pod killed mid-processing | Controlled rebalance/replay; final output accurate |
| `T07` | Database timeout inside callback | Retry/backoff per policy; no false business success committed |
| `T08` | Invalid payload | Goes to DLT/quarantine or defined stop policy |
| `T09` | Transient error then recovery | Processed successfully after retries, not misrouted to DLT |
| `T10` | Retry attempts exhausted | DLT receives record and source metadata, alert triggers |
| `T11` | Retry/DLT forwarding gets ACL denied | Test detects failure, does not report false success |
| `T12` | Old and new schemas coexist | Consumers handle both per rollout contract |
| `T13` | Rolling deploy 1 Pod at a time | Group recovers assignments, no lost business output |
| `T14` | Scale-out then scale-in | Lag, throughput, and idempotency behave as expected |
| `T15` | Pause/resume when downstream slows | Once truly paused, no new deliveries; resume drains backlog |
| `T16` | Retry topic backlog during new version deploy | Old retry topics are not orphaned |
| `T17` | Temporary Kafka cluster unavailability | App fails/recovers per policy, no committed events lost |
| `T18` | DLT review/reprocess an event | Event reprocessed properly, full audit, no duplication |
| `T19` | Load test p95/p99 and burst | Meets SLO with capacity headroom |
| `T20` | Image/config rollback | Consumer keeps reading pending payloads and topics |

The tests above are a recommended catalog to tailor to your architecture. For example, a producer-only service does not need `T15`; a transactional Streams pipeline needs different tests. Each test should document `setup`, `injection point`, `expected result`, `actual result`, evidence, owner, and a ticket when failing.

### 13.2. Minimal `@EmbeddedKafka` Smoke Test

The example below illustrates waiting on broker ack and listener callbacks instead of arbitrary `Thread.sleep` calls:

```java
@SpringBootTest(
    classes = KafkaSmokeTest.TestApplication.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = "readiness.smoke",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaSmokeTest {

    @Autowired KafkaTemplate<String, String> template;
    @Autowired KafkaListenerEndpointRegistry registry;
    @Autowired Probe probe;

    @Test
    void publishesAndConsumes() throws Exception {
        MessageListenerContainer container = Objects.requireNonNull(
            registry.getListenerContainer("readinessListener"));

        ContainerTestUtils.waitForAssignment(container, 1);

        String payload = "ready-" + UUID.randomUUID();
        template.send("readiness.smoke", payload)
            .get(10, TimeUnit.SECONDS);

        assertThat(probe.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(payload);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean Probe probe() { return new Probe(); }
    }

    static class Probe {
        final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "readinessListener",
            topics = "readiness.smoke",
            groupId = "readiness-test-group"
        )
        void receive(String payload) {
            received.add(payload);
        }
    }
}
```

Imports used in the test include: Spring Boot Test, Spring Kafka `@EmbeddedKafka`, `@KafkaListener`, `@EnableKafka`, `KafkaTemplate`, registry, `MessageListenerContainer`, `ContainerTestUtils`, Spring bean/config annotations, `@Test`, JUnit, AssertJ, `Objects`, `UUID`, `BlockingQueue`, `LinkedBlockingQueue`, and `TimeUnit`. Imports are intentionally omitted to keep the structure clear; this is not a verbatim copy-pasteable Java file.

**Limitations:** This test only checks producer/consumer round-trip in an embedded broker. It does not prove database transactions, multi-broker durability, ACLs, runtime TLS, rolling upgrades, or DLT workflows. Those require separate tests.

### 13.3. Testing Idempotency Right at the Crash Boundary

To prove `T03`, use a fixture with a stable event ID and an interception point after DB commit:

```text
Producer sends event ev-101
Consumer A receives ev-101
Business DB commits output
Kafka offset not committed
Kill consumer A cleanly in test
Consumer B redelivers ev-101

Assert:
  - event applied to business state exactly once
  - duplicate attempt recorded in audit
  - offset committed accurately afterward
```

Do not just invoke `listener.onMessage(...)` twice and conclude restarts/rebalances are safe. A double-call unit test is useful, yet it does not verify Kafka offsets and container lifecycle.

### 13.4. Testing Retry/DLT Forwarding

In integration/staging tests, send a record that causes the handler to throw an exception classified as retryable. Wait for the producer ack on main, observe the exact **retry destination**, expected number of attempts, and DLT arrival if failure persists. Use distinct message IDs to isolate concurrent tests. For ACL-denied or serializer error paths, use a dedicated test principal/topic; do not break production cluster configs for testing.

### 13.5. Performance and Soak Testing

Load tests should simulate:

- Real payload size distributions and partition skew.
- Steady-state input, bursts, and post-outage backlog.
- Downstream API/DB p95/p99 latency.
- Batch of records per poll, listener concurrency, and GC behavior.
- Retry storms when a dependency is temporarily unavailable.
- Rolling deploy during active load and backlog.
- Large DLT backlog that does not obscure business status.

Results must record successful throughput, error/timeout rates, consumer lag, drain time, CPU/memory, broker network/disk, DB pool, rebalances, and output reconciliation. **Do not evaluate solely by peak messages/s without failure injection.**

## 14. Offset, Retention, and Replay Operations Checklist

Offset resets and replays are sensitive operations because they can cause messages to be reprocessed or skipped.

### 14.1. Required Items

- [ ] Runbook exists to inspect `group.id`, partitions, committed offsets, end offsets, and lag.
- [ ] Policy defines who is allowed to change offsets, who approves, and what evidence/backups are required.
- [ ] Replay plan uses business keys/idempotency; do not casually create new group IDs against production data.
- [ ] Inputs are still within retention or another storage source exists for backfill when needed.
- [ ] When resetting offsets, the consumer group is placed into the state required by the Kafka CLI/managed platform.
- [ ] A method exists to reconcile the set of processed event IDs before/after replay.
- [ ] Alerts exist when oldest pending lag risks hitting retention.
- [ ] If the topic is compacted, the business team understands they cannot expect to replay full compacted event history.

### 14.2. Inspecting Offsets via CLI

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
```

The output shows current offset, log end offset, and lag by partition. Do not take a single `lag=0` reading as proof that business processing is finished: records might be sitting in retry topics, the DLT, or unacknowledged side effects.

When planning an offset reset, use **dry-run/describe/approval** steps matching the tooling and Kafka release before making live changes. Do not include a copy-pasteable reset-to-earliest command in runbooks without guardrails.

### 14.3. Data Loss from Retention Can Still Occur

Kafka retention is a log cleanup policy. When a consumer is paused too long or backlog grows too large, Kafka can delete data before the group reads it. When a committed offset is deleted from the log, resume behavior follows `auto.offset.reset`/client error policy. **Do not treat `earliest` as a recovery mechanism for records deleted by retention.**

Set an SLO on backlog drain time, alert ahead of the retention window, and keep an external archive solution if long-term backfill is required.

## 15. Upgrade, Compatibility, and Rollback Checklist

A production-ready system can not only run today's version, it can also **be updated without downtime or message loss beyond SLA**.

### 15.1. Items to Confirm

- [ ] Kafka broker release, KRaft metadata feature level, and Java client versions are tracked separately.
- [ ] Spring Boot/Spring Kafka/Kafka clients runtime versions are compatible per release docs.
- [ ] Tested current broker with target client and target broker with current client if upgraded independently.
- [ ] Group protocol/assignment strategy is compatible during mixed client version phases.
- [ ] Rolling deployment produces acceptable rebalances and lag recovers within SLA.
- [ ] New payload schema does not break old consumers while two releases coexist.
- [ ] Retry topic suffixes/naming do not orphan messages remaining in old topics.
- [ ] Image rollback does not require downgrading DB schema or reading a new message format unsupported by the old client.
- [ ] If upgrading brokers, the plan gates on controller quorum/ISR and accounts for **rollback limits after feature finalization**.
- [ ] Canary, soak period, and auto-stop criteria exist when errors/lag/duplicates rise.

### 15.2. A Controlled Release Flow

```text
P0: Freeze contract + inventory versions/topic graph
          |
          v
P1: Staging tests + failure injection
          |
          v
P2: Provision compatible ACL/topics/secrets/schema migration
          |
          v
P3: Canary subset of Pods/traffic
          |
          v
P4: Observe go/no-go gates
          |
   +------+------+
   |             |
  FAIL          PASS
   |             |
Rollback       Rolling deployment
or mitigate       |
                  v
             Soak + reconciliation
                  |
                  v
               Close change
```

In particular, if a release changes Kafka topic naming, schemas, or business database formats, **rolling back code does not mean rolling back data**. Prepare forward/backward migrations and a way to keep consuming old backlog instead of merely keeping the old image.

## 16. Runbook and On-Call Ownership Checklist

A nice dashboard without an alert recipient, access permissions, and remediation steps is not production-ready.

### 16.1. Minimum Runbooks

| Incident | What the Runbook Must Answer | Owner |
| --- | --- | --- |
| Producer repeated timeouts | Broker/ISR/ACL/network or payload? How to retry safely? | App + Kafka Platform |
| Consumer lag rising | Partition skew, DB bottleneck, rebalances, or paused? | On-call + App |
| Large retry backlog | Is downstream still failing? Retry storm? Should main be paused? | App + Downstream owner |
| DLT spike | Schema, payload, auth, or code error? Who triages/reprocesses? | Domain + App |
| `TopicAuthorizationException` | Which principal/resource/action is missing? Who fixes ACL? | Security + Platform |
| Frequent group rebalances | Deployment, static membership, poll interval, or broker coordinator? | App + SRE |
| Stuck poison message | How to move to DLT/quarantine without losing evidence? | App + Domain |
| Replay/backfill | Offset/source version scope, approval, and reconciliation? | Domain + On-call |
| Broker/controller incident | ISR/quorum, failover, producer impact, data durability? | Kafka Platform |
| Release rollback | Can code be rolled back? Are retry topics/schemas still compatible? | Release owner |

### 16.2. Sample Runbook: Sudden Consumer Lag Spike

**Symptom:** `orders-service` lag climbs continuously for 15 minutes; processing throughput is below input rate.

1. **Assess business impact:** how many minutes of delay does the backlog represent? Which SLA is at risk?
2. **Identify scope:** entire group or one partition? Main topic or retry topic? Are other groups affected?
3. **Check cluster:** broker health, ISR/offline partitions, producer errors, network, and recent changes.
4. **Check consumer:** assigned partitions, rebalances, container paused/requested state, poll/processing latency, and GC.
5. **Check downstream:** database pool, deadlocks, external API rate limits, 429/503 responses.
6. **Choose controlled remediation:** restore downstream, throttle input if possible, scale consumers within partition limits, adjust retry budget via change process, or roll back deployment.
7. **Do not reset offsets to “clear lag”**: this can skip unprocessed messages.
8. **Post-recovery reconciliation:** backlog drain, pending retry/DLT, output business keys, and error rates.
9. **Record incident timeline:** start time, actions taken, affected messages, owners, and preventive follow-ups.

If replicas are scaled beyond the Kafka partition count, adding Pods may not increase active processing consumers. If the bottleneck is an external API rate limit, scaling out may worsen the outage.

### 16.3. Sample Runbook: Unreviewed Records in DLT

1. Identify DLT topic, event ID, original topic/partition/offset, and reason code.
2. Distinguish invalid payloads from transient destination errors; for systemic outages, prioritize fixing the root cause first.
3. Ensure only authorized personnel view raw payloads containing sensitive data.
4. Record a decision: `RETRY_AFTER_FIX`, `REJECT_PERMANENTLY`, or `WAIT_FOR_REFERENCE_DATA`.
5. Reprocess under a distinct correlation/replay version while keeping stable business identity/idempotency.
6. Verify success in business output, not merely re-publishing onto the main topic.
7. Update review status, execution/offset of reprocessing, and audit logs.

Do not delete DLT messages just to make a dashboard read zero. Deletion/retention must follow data policy and account accurately for which records were processed.

## 17. Evidence Table for the Production Readiness Review

This is a template you can copy into a release ticket or ADR:

| Item | Owner | Acceptance Evidence | Status |
| --- | --- | --- | --- |
| Business event identity and idempotency | Domain/App | ADR + duplicate/replay tests | `PENDING` |
| Topic config/retention/RF/ISR | Kafka Platform | IaC diff + topic describe | `PENDING` |
| Producer durability and publish failures | App | Config + leader restart test | `PENDING` |
| Consumer ack/commit and crash recovery | App | Process kill test + DB reconciliation | `PENDING` |
| Retry/backoff/DLT routing | App | Staging test + topic graph | `PENDING` |
| Retry/DLT ACL | Security/Platform | Principal-based smoke test | `PENDING` |
| Schema backward/forward compatibility | Data/App | Schema Registry check + fixture tests | `PENDING` |
| Load/burst/soak | SRE/App | Load report with p95/p99, lag, and drain time | `PENDING` |
| Monitoring/alerts/on-call | SRE | Dashboard link + test alert delivery | `PENDING` |
| Rolling deploy/canary | Release owner | Deployment rehearsal + metrics | `PENDING` |
| Rollback with existing backlog | Release owner/App | Rollback rehearsal + compatibility evidence | `PENDING` |
| Incident/DLT/replay runbooks | On-call/Domain | Runbook links + drill record | `PENDING` |

`PENDING` statuses are template placeholders; reviewers must replace them with `PASS`, `FAIL`, `NOT_TESTED`, `N/A`, or `RISK_ACCEPTED` alongside evidence links. Do not mark GO while leaving template `PENDING` items.

### 17.1. Format of an Evidence Record

```yaml
release: orders-worker-1.14.0
environment: staging-kafka
testId: T03
scenario: "DB commit succeeds, process crashes before Kafka offset commit"
owner: orders-team
status: PASS
date: 2026-11-16
artifacts:
  - "link-to-test-report"
  - "link-to-dashboard"
  - "link-to-db-reconciliation"
notes: "Event ev-101 was replayed; business side effect remained unique"
```

This is **illustrative YAML inside the lesson content**, not a QA artifact or summary from a content-generation workflow. In practice, `artifacts` must point to retrievable reports, logs, or dashboards rather than placeholder links.

### 17.2. Final GO/NO-GO Table

| Gate | Desired Outcome | Sign-off |
| --- | --- | --- |
| Data correctness | No uncontrolled path to lose or duplicate business effects | Domain + App |
| Kafka availability | Broker/topic/ACL/retention meet policy | Kafka Platform |
| Resilience | Crash/rebalance/retry/DLT tests pass | App + SRE |
| Security | Secrets, TLS, ACL, PII policy pass | Security |
| Operations | Dashboards, alert delivery, runbooks, on-call ready | SRE/On-call |
| Release | Canary, rollback, and version compatibility pass | Release owner |

**Do not grant GO simply because most cells are `PASS`** if a blocking issue remains such as “DLT lacks write permissions” or “consumer can commit offset before DB transaction”. Any exception must explicitly state impact, scope, expiry, approver, and guardrails.

## 18. End-to-End Scenario Drill

A final drill should combine multiple components rather than testing only a single class in isolation.

### Scenario: Downstream Database Loses Connectivity for 5 Minutes

Assumptions:

- The producer keeps sending `orders.events` successfully.
- The consumer calls the database to build the order projection.
- Connectivity losses are classified as retryable per policy.
- Appropriate retry topics or blocking retry/DLT are configured.
- The listener runs across three Pods.

Drill progression:

```text
T0  Healthy baseline: low Kafka lag, DB updates succeed.
T1  Inject DB outage in staging.
T2  Consumer errors; retry/backoff and alerts fire.
T3  Producer keeps sending records; main/retry lag reflects backlog.
T4  DB recovers.
T5  Retries drain; business output catches up with source.
T6  Inspect DLT, idempotency conflicts, and business reconciliation.
T7  Rolling restart one consumer while backlog still exists.
T8  Verify no lost or duplicated business effects.
```

### Pass Criteria

1. No broker-acknowledged messages lost due to misconfigured error handler commits or forwarding failures.
2. No infinite retry storm overloading the newly recovered DB.
3. Business output reflects all valid event IDs per contract, or unfinished items remain traceable in retry/DLT.
4. DLT holds only records that genuinely exceeded the retry policy, reviewable and reprocessable.
5. Rebalances/rolling restarts do not cause duplicate outputs beyond the idempotency contract.
6. Lag and pending age return below agreed thresholds within the SLO window.
7. Alerts reach the right owner and incident runbooks are actionable.

**Do not induce real outages in production just to check off the list** without approval, blast-radius isolation, and a rollback plan. Use a reproducible staging/chaos environment, ensuring no real payments, emails, or external API calls are triggered.

## 19. Common Production Readiness Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing only happy-path messages | Unknown behavior during retries/crashes/rebalances | Add failure injection and output reconciliation |
| Treating `acks=all` as business exactly-once | App retries can create duplicate events/effects | Stable event ID, outbox, inbox/dedup |
| Watching only main consumer lag | Retry/DLT backlog is hidden | Dashboard covering the entire topology |
| Using `auto.offset.reset=earliest` as a “backup” | Expired-retention messages cannot be recovered | Archive/backfill policy and sufficient retention |
| DLT exists with no owner | Failed records are forgotten | Review SLA, alerts, and reprocess runbook |
| Skipping principal/ACL tests on forwarding | Main listener runs while retry/DLT fails | Smoke test failure paths with real identities |
| Scaling replicas past partition count for throughput | Idle Pods while DB remains the bottleneck | Measure per-partition lag and downstream capacity |
| Changing group ID in normal deploys | Consumers re-read or skip data per reset policy | Keep group ID stable, plan migrations intentionally |
| Monitoring only `isPauseRequested()` | Assume paused before pause takes effect | Observe actual container pause state and callbacks |
| Retrying every `Exception` | Poison records loop endlessly and burn resources | Classify transient vs permanent, define DLT policy |
| Non-blocking retry on strict-ordering events | Later event processes before earlier event | Version-aware state or choose another retry design |
| Setting DLT retention shorter than review SLA | Failure evidence lost before review | Account for outage and backlog handling time |
| Deploying changed retry naming with remaining backlog | Old topic has no active consumer | Drain/migrate and preserve compatibility |
| Liveness kills consumer when DB slows | Repeated crash/rebalance loops, growing lag | Probe true health and avoid restart storms |
| Lowering `min.insync.replicas` to stop producer errors | Sacrifices durability right when cluster is impaired | Restore ISR, preserve data safety policy |
| Rolling back using only the old image | Old code cannot read new schemas/topics | Compatibility plan for both payloads and state |
| Recording no evidence/owner | Review becomes subjective | `PASS`/`FAIL` backed by artifacts, owners, and due dates |

## 20. Checkable Operations Handoff Checklist

The list below is suitable to paste directly into a release ticket. Checkboxes should only be checked after verifying evidence.

### A. Data Contract

- [ ] A01. Business key/event ID and dedup strategy reviewed.
- [ ] A02. Schema evolution and serializer compatibility verified.
- [ ] A03. Message key/partitioning preserves business-required ordering.
- [ ] A04. Replay, tombstones, compaction, and retention defined.
- [ ] A05. Payload security, PII, and tenant isolation approved.

### B. Kafka Infrastructure

- [ ] B01. Main/retry/DLT topics fully provisioned.
- [ ] B02. Replication, min ISR, partitions, cleanup, and retention match SLA.
- [ ] B03. Broker/controller health and metrics have baselines.
- [ ] B04. Clients reach broker advertised listeners over TLS/network.
- [ ] B05. Capacity, quotas, partition skew, and drain times measured.

### C. Producer

- [ ] C01. Producer acks/idempotence/timeouts intentionally configured.
- [ ] C02. Send failures and callbacks/timeouts have logging/alerting/retry policies.
- [ ] C03. Outbox or DB-to-Kafka consistency mechanism evaluated.
- [ ] C04. Producer survives leader changes and temporary broker outages.
- [ ] C05. No duplicate business events published on request retries.

### D. Consumer

- [ ] D01. Offset/ack mode/auto-commit contract verified.
- [ ] D02. DB/API side effects are idempotent under record replay.
- [ ] D03. Listener exceptions properly classified and handled.
- [ ] D04. Poll interval, concurrency, rebalance, and shutdown tested.
- [ ] D05. Duplicate delivery, crash, and rolling restart tests pass.

### E. Retry and DLT

- [ ] E01. Blocking vs non-blocking retry chosen based on ordering/transaction needs.
- [ ] E02. Backoff, attempts, timeouts, and retry budget have SLAs.
- [ ] E03. Retry/DLT topics, serializers, and ACLs work with real principals.
- [ ] E04. DLT review/reprocess workflow has owner and audit.
- [ ] E05. Forwarding failures, exhaustion, and recovery tested.

### F. Security

- [ ] F01. TLS/SASL/IAM/ACLs enforce least privilege.
- [ ] F02. Secrets are absent from code, plaintext logs, and artifacts.
- [ ] F03. Schema Registry/KMS/transactional IDs have appropriate permissions.
- [ ] F04. Data classification and PII retention confirmed.
- [ ] F05. Service accounts, network policies, and certificate rotation ready.

### G. Monitoring and Operations

- [ ] G01. Producer errors/latency and consumer lag monitored.
- [ ] G02. Retry/DLT backlog, oldest age, and reconciliation have metrics.
- [ ] G03. Alerts tested through to actual on-call recipients.
- [ ] G04. Incident, pause/resume, replay, and DLT runbooks approved.
- [ ] G05. After-hours triage and remediation ownership assigned.

### H. Deployment and Resilience

- [ ] H01. Runtime dependency/JDK/Kafka client versions verified.
- [ ] H02. Rolling deployment/canary and rollback plans rehearsed.
- [ ] H03. Resource requests/limits and scaling behavior load tested.
- [ ] H04. Pod termination, rebalance, and state replay tested.
- [ ] H05. Final outputs reconciled after outage and deployment cycle.

### I. Sign-Off

- [ ] I01. All blockers are `PASS` or have properly authorized exceptions.
- [ ] I02. Evidence links, owners, and release ticket updated.
- [ ] I03. Kafka Platform, App, Security, and On-call reviewed their owned items.
- [ ] I04. Rollout window, rollback triggers, and STOP/GO decision-maker clearly defined.
- [ ] I05. Post-deploy soak and business reconciliation scheduled.

## 21. After Go-Live: The Checklist Does Not End at the Deploy Button

After releasing, continue monitoring to verify the system **operates stably**, not merely that it started:

1. **During canary:** verify Kafka produce/consume success, offset commits, retries, DLT, and authentication/serialization errors.
2. **During rolling rollout:** monitor rebalances, lag, message latency, CPU/GC, and downstream pressure; halt rollout if gates are breached.
3. **After rollout:** reconcile business output, event IDs, processing freshness, and pending retry/DLT.
4. **During the soak window:** watch lag recovery and performance under normal/peak load; avoid closing the change too early.
5. **During postmortem if an incident occurs:** preserve evidence, pinpoint the failure boundary, and update tests and runbooks rather than simply bumping retry counts.
6. **Periodically:** drill replay/backfill, audit DLT ownership, retention, ACL rotation, upgrade compatibility, and process-crash recovery.

A service can deploy to production cleanly yet **not be production-ready in steady state** if alerts fail to reach on-call, backlog drains slower than retention, or DLT accumulates unreviewed records.

## 22. Conclusion

A **production readiness checklist** for Spring Kafka is a **provable operational contract**. You must verify together: event contracts, Kafka cluster/topic durability, producer ack/idempotence, consumer offsets/transactions, retry/DLT, security, capacity, monitoring, failure tests, deployment, and runbooks.

For critical systems, the final question before GO is not “is `@KafkaListener` running?” but rather: **When a broker, Pod, or downstream fails right in the middle of processing, does the system detect the failure, preserve committed data, avoid duplicate business effects, drain the backlog, and have clear ownership for recovery?**

When the answer is backed by **tests, reconciliation data, dashboards, and rehearsed procedures**, releases stand on solid ground. Without evidence, the honest status is `NOT_TESTED` or `NO-GO`, not `PASS` based on optimism.

## References

- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): listener containers, `KafkaTemplate`, offset acknowledgments, error handling, retry, and transactions.
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): poll loop, ack modes, commits, concurrency, and lifecycle.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, backoff, and dead-letter recoverer.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry topics, DLT, and ordering/transaction constraints.
- [Spring Kafka — Pausing and Resuming Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): safe container pause/resume.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): scope of EOS with Kafka transactions.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils`, and integration testing.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration, Kafka properties, and runtime integration.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): producer, consumer group, offsets, security, topics, retention, and operations.
- [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination and container lifecycle during rolling deployments.
