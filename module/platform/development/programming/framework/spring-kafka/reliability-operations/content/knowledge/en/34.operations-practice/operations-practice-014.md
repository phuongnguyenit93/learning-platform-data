# Comprehensive Incident Handling Exercise in Spring Kafka Reliability Operations

## 1. Objectives of the Practice Exercise

A Kafka consumer can still be in `RUNNING` state, its Kubernetes pod can still report `Ready`, and offsets can still be committing, while the business system is losing progress: failed records are routed en masse to the Dead Letter Topic (DLT), database records are not updating, several partitions keep changing ownership, and the operations team only receives scattered alerts.

In production, this kind of incident rarely has a single cause or one obvious metric. You must piece together multiple sources of evidence to understand **what is happening**, **which events are affected**, **what can be mitigated immediately**, and **when recovery can be declared**.

The **“Comprehensive Incident Handling Exercise”** belongs to **Operations Practice** in the **Spring Kafka Reliability Operations** module. It is an end-to-end simulation exercise designed for developers, SREs, on-call engineers, and event-driven system designers.

After completing it, learners will be able to:

1. Recognize a Kafka incident across lag, error rates, DLT, rebalances, database metrics, and business outcomes.
2. Build an incident timeline and separate **symptoms**, **direct causes**, **root causes**, and **consequences**.
3. Form hypotheses and verify evidence before changing configurations or resetting offsets.
4. Select safe mitigations when a canary consumer fails, the database is overloaded, and the retry policy triggers a DLT storm.
5. Inspect committed offsets, partition ownership, and replay behavior after crashes/rebalances.
6. Reconcile processed events, DLT records, duplicate deliveries, and database side effects.
7. Plan an approved DLT replay with idempotency and post-replay verification.
8. Write an incident report covering timelines, impact assessment, action items, and regression tests.

**All systems, logs, metrics, timestamps, and figures in this exercise are simulated data.** No real production incident is claimed. State-mutating commands should only be run in controlled lab/staging environments; in production, follow your organization's permissions and change management processes.

Examples use Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka, PostgreSQL, Kubernetes, and JUnit 5. Exact syntax and options should be adapted to the client, broker, and tool versions in use.

## 2. Incident Scenario Overview

An e-commerce system consumes events from topic `orders.events` to update order state in table `order_projection`.

Simulated architecture:

```text
                   Order Service
                        |
                        v
               Kafka topic orders.events
                  4 partitions (P0-P3)
                        |
                        v
            Group: order-projection
               /               \
        Stable consumer      Canary consumer
        version 1.8.0        version 1.9.0
        2 pods, 1 thread     1 pod, 1 thread
               \               /
                \             /
                 v           v
                 PostgreSQL cluster
                     |
                     v
              order_projection
                     |
                     v
             Order API/dashboard

            Unprocessable records
                        |
                        v
               orders.events.DLT
                        |
                        v
                 DLT audit/replay
```

Under normal conditions:

- The topic has 4 partitions with an average ingress rate of around 100 records/second.
- Two stable pods share work inside the same consumer group.
- Consumers use `enable.auto.commit=false` and container `AckMode.RECORD`.
- The handler writes to the database via a JDBC transaction with a duplicate-prevention marker keyed by `eventId`.
- `DefaultErrorHandler` retries transient errors and publishes to the DLT once retries are exhausted.
- Dashboards track lag, handler errors, records sent to DLT, processing latency, and the database pool.
- A canary deployment mechanism shares the same group to test version 1.9.0.

The simulated incident occurs right after promoting the canary to production. Around the same time, the event schema changed and the database began running out of connections. Some records went unprocessed; as lag climbed, pods rebalanced and potentially redelivered previously processed records.

### Recovery Objectives

In this lab, treat the following goals as constraints:

| Constraint | Meaning |
| --- | --- |
| No silent event loss | Every event must have an outcome: processed, pending, or quarantined with traceability |
| No duplicate side effects | One valid `eventId` does not mutate business data multiple times outside rules |
| No arbitrary group offset resets | Offsets only change under controlled procedures and target data evaluation |
| DLT has ownership | Every DLT case requires investigation and resolution |
| Rollback capability | A verified stable version and rollback path exist without erasing history |
| Recovery evidence | Consumer progress, DLT backlog, and business reconciliation meet defined criteria |
| Do not mask failures | A green consumer steadily dumping records to the DLT is not full recovery |

These are evaluation criteria for the exercise, not a default SLA applicable to every organization.

## 3. Technical Distinction of Signals

Before investigating, align on what common dashboard concepts actually mean.

| Signal | What It Tells You | What You Cannot Conclude Alone |
| --- | --- | --- |
| Consumer lag | Difference between log end and consumption/commit progress per metric | Not directly equal to the count of failed business events |
| Committed offset | Resume position of a consumer group on a partition | Does not prove DB side effects are accurate |
| Retry attempts | A record/operation was re-invoked per policy | Not equal to the number of distinct failed events |
| DLT publish count | Records were routed to the DLT per policy | Does not prove events were handled at the business level |
| Rebalance count | Group membership/assignment changed | Does not itself prove message loss |
| Handler exception | An error occurred during a processing attempt | Does not prove the job/consumer ultimately failed |
| Pod readiness | App meets defined health criteria | Does not guarantee the consumer owns partitions or is making progress |
| DB connection pool pending | Requests are waiting for connections | Does not itself prove Kafka is the root cause |
| Duplicate delivery | A Kafka record/event may be re-processed | Not synonymous with writing duplicate business results |
| Business reconciliation mismatch | Output differs from expected state | Requires checking offsets, validation, DLT, source, and DB to explain |

**Crucial point:** lag can drop because failed records are successfully published to the DLT while the source offset keeps advancing. If a dashboard only watches lag, operations might declare recovery while thousands of orders remain unapplied.

## 4. Pre-Incident System Baseline

Simulated data at 08:55, before canary deployment:

| Metric | Baseline |
| --- | ---: |
| Message ingress | 100 records/s |
| Consumer processing | ~100 records/s |
| Total group lag | 35 records |
| p95 handler latency | 120 ms |
| Retryable error rate | 0.2% of deliveries |
| DLT rate | 0–1 record/hour |
| Rebalances | 0 in the last 30 minutes |
| PostgreSQL pool active/max | 7/20 |
| Connection acquisition pending | 0 |
| Stable pods | 2 |
| Canary pods | 0 |
| Business reconciliation | No discrepancy detected |

These figures are purely a **comparison baseline**. A system running at 100 records/s does not always need a pool size of 20 or a 120 ms p95.

### Exercise Data Conventions

Source topic:

```text
orders.events
  partitions: 0, 1, 2, 3
  key: orderId
  value: OrderEvent JSON
```

A valid event:

```json
{
  "eventId": "evt-701",
  "orderId": "order-1092",
  "version": 5,
  "status": "PAID",
  "occurredAt": "2026-11-16T01:00:05Z"
}
```

An event unsupported by a version:

```json
{
  "eventId": "evt-702",
  "orderId": "order-1093",
  "version": 6,
  "status": "RETURN_REQUESTED",
  "occurredAt": "2026-11-16T01:00:06Z"
}
```

Simulated scenario: the producer started emitting status `RETURN_REQUESTED` under a contract update, while validation in canary version 1.9.0 still uses the old enum and treats this status as non-retryable. This is a hypothesis to test with evidence, not a pre-investigation conclusion.

## 5. Incident Dataset: Simulated Timeline

Timestamps follow lab local time. Figures are sample snapshots; ingress/processing rate at one instant is not the average across the whole interval between snapshots.

| Time | Observed Event | Total Lag | New DLT in Last 5 Min | DB Pool Active/Max |
| --- | --- | ---: | ---: | ---: |
| 08:55 | Stable v1.8.0 running normally | 35 | 0 | 7/20 |
| 09:00 | Canary v1.9.0 begins joining group | 80 | 0 | 8/20 |
| 09:02 | Rebalance completes, canary gets P3 | 140 | 0 | 9/20 |
| 09:04 | Canary logs show unknown status errors | 420 | 12 | 12/20 |
| 09:07 | Connection acquisition timeouts increase | 2,300 | 55 | 20/20 |
| 09:10 | Retry rate rises, another partition transfer occurs | 6,400 | 310 | 20/20 |
| 09:13 | Business write rate significantly below ingest | 13,900 | 920 | 20/20 |
| 09:16 | Canary scaled back and connection pressure addressed | 16,100 | 1,050 | 15/20 |
| 09:20 | Stable increases processing, lag begins falling | 12,700 | 30 | 11/20 |
| 09:32 | Source progress approaches baseline | 480 | 0 | 9/20 |
| 09:40 | Lag near baseline, DLT cases remain | 55 | 0 | 8/20 |

This table only describes **system signals** and when mitigation began. It does not confirm all bugs were fixed at 09:16 or all business cases resolved by 09:40.

### Questions to Answer from the Timeline

1. Why did lag start climbing after the canary joined?
2. Is the new status error responsible for all the lag or only part of it?
3. Is database pool saturation the root cause, an effect of the canary, or a concurrent failure?
4. Why were so many DLT records produced while the DB was unavailable?
5. Could the 09:10 rebalance cause records to be redelivered?
6. When lag returned to 55 at 09:40, could the incident be closed immediately?
7. What evidence should be saved to know which events the canary handled before rollback?

Answers must rely on the logs, metrics, Kafka group state, and business data in the following sections.

## 6. Collected Log Samples

These are simulated logs used as exercise evidence.

### 6.1. Canary Joins the Group

```text
09:00:11 INFO  event=consumer.start
  app=order-projection version=1.9.0 track=canary
  groupId=order-projection

09:00:13 INFO  event=kafka.rebalance.revoked
  pod=order-projection-stable-b
  partitions=[orders.events-3]

09:02:02 INFO  event=kafka.rebalance.assigned
  pod=order-projection-canary
  partitions=[orders.events-3]
```

This is evidence that the canary received P3 at that time. It does **not** prove the canary receives an exact fraction of traffic because partitions can have uneven heat.

### 6.2. Schema/Validation Error

```text
09:04:19 WARN  event=order.consume.failed
  track=canary topic=orders.events
  partition=3 offset=8112
  exception=InvalidOrderEventException
  reason=UNKNOWN_STATUS

09:04:19 INFO  event=order.dlt.publish.requested
  sourceTopic=orders.events sourcePartition=3
  sourceOffset=8112 target=orders.events.DLT

09:04:19 INFO  event=order.dlt.publish.confirmed
  sourceTopic=orders.events sourcePartition=3
  sourceOffset=8112 targetPartition=3
```

Only `publish.confirmed` confirms the producer sent it successfully. A standalone `publish.requested` line does not prove the record is in the DLT.

### 6.3. Database Pool Failure

```text
09:07:03 ERROR event=order.consume.failed
  track=stable topic=orders.events
  partition=0 offset=15120
  exception=CannotGetJdbcConnectionException
  cause=Connection is not available,
        request timed out after 3000ms

09:07:05 WARN  event=order.retry
  topic=orders.events partition=0 offset=15120
  attempt=2 reason=DB_CONNECTION_TIMEOUT

09:07:09 ERROR event=order.dlt.publish.confirmed
  sourceTopic=orders.events sourcePartition=0
  sourceOffset=15120
  exception=CannotGetJdbcConnectionException
```

This excerpt shows the stable version also hits database errors, refuting the overly simple explanation “every failure came from parser v1.9.0”. At the same time, it suggests the retry budget is pushing broad infrastructure failures into the DLT.

### 6.4. Rebalance and Redelivery

```text
09:10:32 WARN  event=kafka.poll.progress.warning
  pod=order-projection-canary
  elapsedSinceSuccessfulPollMs=306000

09:10:35 WARN  event=kafka.partitions.lost
  pod=order-projection-canary
  partitions=[orders.events-3]

09:10:38 INFO  event=kafka.partitions.assigned
  pod=order-projection-stable-a
  partitions=[orders.events-3]

09:10:41 INFO  event=order.duplicate.suppressed
  pod=order-projection-stable-a
  eventId=evt-698
  sourcePartition=3
```

This can occur if the poll loop is held too long or a consumer loses group membership. Check `max.poll.interval.ms`, listener processing, heartbeats, and group protocol settings before concluding the exact cause of assignment loss.

The duplicate suppression log proves the handler saw an event whose marker already existed; it is **not** proof that the DB was wrongly written twice.

## 7. Kafka Consumer Group State

Simulated output from a group query at 09:13:

```text
GROUP             TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-projection  orders.events  0          15700           18700           3000
order-projection  orders.events  1          16200           19400           3200
order-projection  orders.events  2          14300           18100           3800
order-projection  orders.events  3          8250            12150           3900
TOTAL                                                                     13900
```

These offsets are **group committed offsets per partition**, not the count of records written to the database. Do not use `CURRENT-OFFSET=15700` to infer that exactly 15,700 business events succeeded.

Read-only commands you can run:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

And inspect the topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events
```

In production, obtain bootstrap addresses, SASL/TLS client properties, and Kafka credentials from the active runbook. Never paste credentials into shell history or incident documents.

### While the Group Is Rebalancing

During a rebalance, owners, offsets, and lag can fluctuate rapidly. A single `--describe` snapshot is insufficient to conclude the group has stabilized. Compare multiple samples or check assignment/event metrics to see the real state.

If a group has no committed offset, tools may show missing values or dashes; do not convert them into zeros without understanding the context.

## 8. Initial Consumer Configuration Documentation

Partial configuration supplied for the exercise:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    topic: orders.events
    dlt-topic: orders.events.DLT
```

Points to evaluate:

- `enable-auto-commit=false` and `ack-mode=record` let the container manage progress per record.
- `max.poll.interval.ms=300000` is 5 minutes; if synchronous processing exceeds this limit, the consumer can lose membership depending on client/protocol behavior.
- `max-poll-records=100` affects records per poll, yet does not directly bound total processing time across all records.
- `auto-offset-reset=earliest` only matters when no valid committed offset exists; it does not make the group re-read the whole topic after rollback.
- `acks=all` makes the producer wait for Kafka acknowledgments, yet does not create an exactly-once business effect in PostgreSQL.
- Pods in the same group split **partitions**, not HTTP-style traffic percentages.

In the lab, ensure environment configs point bootstrap servers to test Kafka, not a production cluster.

## 9. Pre-Incident Retry and DLT Policy

Core error handler code in the scenario:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class ConsumerErrorConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                template,
                (record, exception) -> new TopicPartition(
                    "orders.events.DLT",
                    record.partition()
                )
            );

        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
            );

        errorHandler.addNotRetryableExceptions(
            InvalidOrderEventException.class
        );

        return errorHandler;
    }
}
```

`InvalidOrderEventException` is an application-defined exception. Other exceptions, including many database connection errors, may be retried under default classification and then sent to the recoverer once attempts are exhausted.

**Issue to spot:** current policy pushes even widespread transient database outages to the DLT after a few retries. That might fit certain workloads, yet in this exercise business events should only be quarantined for **unprocessable data/record errors**, while infrastructure outages should prevent committing/dumping batches into the DLT without an operational decision. Hence this is a **policy gap to fix**, not merely an issue of raising retry counts.

### Retry Count

`new FixedBackOff(1_000L, 2L)` means:

```text
Initial handler invocation: attempt 1
  if error -> wait 1 second

Retry 1: attempt 2
  if error -> wait 1 second

Retry 2: attempt 3
  if error -> recoverer (DLT)
```

If the record is redelivered after a rebalance or process crash, additional attempts can occur in another execution. Do not treat three total invocations as an end-to-end Kafka exactly-once guarantee.

## 10. Database Schema and Idempotency Rules

To avoid duplicating business state, the app stores a marker per event and updates the projection by version.

PostgreSQL example:

```sql
CREATE TABLE processed_order_event (
    projection_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    last_event_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_processed_order_event_time
    ON processed_order_event (processed_at);
```

A compliant handler can use a transaction:

```java
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
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                projection_name, event_id
            ) VALUES ('order-projection', ?)
            ON CONFLICT (projection_name, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, last_event_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                last_event_version = EXCLUDED.last_event_version,
                current_status = EXCLUDED.current_status,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_projection.last_event_version
                < EXCLUDED.last_event_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

The example assumes record `OrderEvent` provides accessors `eventId()`, `orderId()`, `version()`, `status()`, and `JdbcTemplate` shares the datasource with the JDBC transaction manager.

**Guarantee scope:**

- If the database transaction rolls back, the marker and projection roll back together.
- If the database commits and the consumer dies before committing the Kafka offset, the record can be redelivered and the marker skips reprocessing.
- The version condition prevents an older event from overwriting newer state.
- If a business rule requires processing every consecutive version, you must also check gaps and ordering; `last_event_version` alone is not enough.
- If there are HTTP calls, emails, or Kafka publishes outside the transaction, a separate idempotency/outbox mechanism is needed.

**Do not use Kafka offsets as the sole business uniqueness key** when a business event can arrive from multiple sources or replays. Offsets are useful for tracing a record, while the idempotency key should reflect the event/operation semantics.

## 11. Roles During the Drill

Assign roles rather than having one person do everything alone:

| Role | Responsibilities |
| --- | --- |
| Incident Commander (IC) | Coordinates, classifies severity, selects mitigations, decides incident closure |
| Kafka investigator | Group state, partition assignments, offsets, broker/producer errors |
| Application investigator | Release diffs, exception classes, retry/DLT behavior, handler latency |
| Database investigator | Pool, timeouts, locks, slow queries, committed business rows |
| Scribe/communications | Timeline, hypotheses, decisions, timestamps of changes, stakeholder updates |
| Reviewer/observer | Observes process, demands evidence, scores rubric after the drill |

In small teams, one person may hold multiple roles, yet you should still separate **who proposes a change** from **who verifies its impact** for high-risk actions.

Before starting, everyone must know the lab environment, namespace, Kafka bootstrap, test database, resource cleanup, and rollback steps.

## 12. Initializing a Safe Lab Environment

The exercise can run at two levels:

**Level A — Paper evidence analysis:** no need to start Kafka. Learners use the simulated timeline, logs, and metric snapshots to plan actions and write a postmortem.

**Level B — Live fault injection in a lab:** use Embedded Kafka/Testcontainers or a dedicated staging Kafka/PostgreSQL cluster. Never inject faults into production to complete the exercise.

### Suggested Lab Topology

```text
Lab orchestrator
  |
  +-- Kafka broker / Kafka test cluster
  |     orders.events.lab (4 partitions)
  |     orders.events.lab.DLT (4 partitions)
  |
  +-- PostgreSQL test
  |     order_projection
  |     processed_order_event
  |
  +-- stable-consumer-v1 (2 instances)
  |
  +-- canary-consumer-v2 (1 instance)
  |
  +-- load-generator
  |
  +-- metrics/log collector
```

For topic `orders.events.lab`, keep all groups, databases, and credentials isolated from production. If testing rebalance failures and process crashes, consumers should run in separate processes/containers; calling `container.stop()` from a test JVM mostly simulates a graceful leave, not a true `SIGKILL`/network drop.

### Test Data

Prepare at least:

- 1,000 valid events with unique `eventId` values and `orderId` keys distributed across all four partitions.
- 20 events with the new status `RETURN_REQUESTED`.
- 10 malformed JSON events.
- 20 duplicate-`eventId` events to test idempotency.
- Several older-version events arriving after newer versions.
- A batch of events where the handler simulates DB timeouts for a controlled interval.

Each batch should have known counts and business keys so you can reconcile without relying solely on Kafka callback counts.

## 13. Phase 1 — Detection and Opening the Incident

### Exercise for On-Call

Suppose at 09:07 three alerts fire:

```text
ALERT 1: kafka_consumer_lag_total > 2000
         group=order-projection

ALERT 2: jdbc_pool_pending_connections > 20
         service=order-projection

ALERT 3: dlt_publish_rate_5m > 50
         topic=orders.events.DLT
```

Metric names are illustrative. Real applications may use Kafka client metrics, Micrometer, JMX exporters, or custom metrics.

Learners should:

1. Record detection time, impacted group, and incident owner.
2. Identify impacted customer segments, orders, or business flows.
3. Verify dashboards show fresh data rather than stale metrics.
4. Inspect consumer group state and success rate, not just pod health.
5. Rate severity against system SLOs rather than raw log volume.
6. Post an initial incident update: what is known, what is unknown, and next actions.

### Sample Status Update

> Since around 09:04, consumer group `order-projection` has shown rising lag and DLT rates alongside database connection acquisition timeouts. Failed records may not yet be applied to order status. The team is scoping impact, separating schema errors from infrastructure failures, and preparing to scale down the canary. There is no confirmed permanent data loss; do not reset offsets during investigation.

The message deliberately separates **risk** from **confirmed facts**. Never declare data loss or full recovery before having evidence.

## 14. Phase 2 — Layered Evidence Collection

Create an evidence table recording sources and timestamps:

| Need to Know | Tool/Source | Output to Save |
| --- | --- | --- |
| How many partitions does the topic have? | Kafka Admin/CLI | Partition count, leaders, ISR if relevant |
| Which partitions does the group own? | Consumer group description, rebalance logs | Member → topic-partition |
| Which partitions have rising lag? | Kafka metrics/group describe | Lag per partition and timestamp |
| Are records going to the DLT? | DLT consumer/audit | Original topic/partition/offset, exception type |
| At which stage is the listener failing? | Application logs/traces | Deserialize, validate, DB, external API |
| Is the DB overloaded? | HikariCP/DB metrics | Active/idle/pending, locks, slow queries |
| Is the canary running new code? | Deployment/release metadata | Image digest/version, start time |
| Is there duplicate delivery? | Application logs/DB markers | eventId and delivery/apply counts |
| Is the producer having issues? | Producer metrics/broker logs | Send failures, auth errors, delivery latency |
| Where have source offsets committed? | Kafka group metadata | Committed offset per partition |
| Is business data accurate? | SQL/API reconciliation | eventId marker, order status, version |

**Do not merge logs across sources by timestamp assuming every node clock is perfectly synchronized.** When building an exact timeline, verify timezone, clock skew, and timestamp sources.

### Read-Only Kafka Commands

Examples:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events.lab

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection-lab

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

`--list` may return unrelated groups; use only in labs or authorized environments.

### Read-Only Kubernetes Commands

```bash
kubectl -n kafka-lab get deployments
kubectl -n kafka-lab get pods -l app=order-projection
kubectl -n kafka-lab describe deployment/order-projection-canary
kubectl -n kafka-lab logs deployment/order-projection-canary --since=30m
```

These commands only collect information. In production, confirm kube-context, namespace, and permissions before taking any next step.

## 15. Phase 3 — Forming and Testing Hypotheses

Do not jump straight to a fix just because logs coincide with a deploy. List falsifiable hypotheses.

| Hypothesis | Supporting Evidence | Evidence Needed to Refute/Confirm |
| --- | --- | --- |
| H1: Parser v1.9.0 lacks support for the new status | Unknown-status appears only on canary, DLT P3 | Compare schema/enum release diff, source event types, stable behavior |
| H2: DB connection shortage slows every member | Both stable and canary see timeouts; pool 20/20 | Query per-pod pool metrics, DB connection count, locks/slow queries |
| H3: Retry policy turns outage into DLT storm | DLT spikes alongside transient JDBC errors | Audit DLT exception distribution and error handler config |
| H4: Rebalance caused data loss | Partition lost/assigned, duplicate delivery | Committed offsets and marker/DB reconciliation; is any key truly missing? |
| H5: Kafka broker error caused lag growth | Lag increase and rebalance | Broker health, replication, producer errors, coordinator logs |
| H6: New DB query in canary holds connections too long | Errors appear post-deploy, pool saturates | SQL trace, transaction duration, thread dumps, version diff |
| H7: DLT producer lacks write permissions | DLT exception while source stalls | Inspect publish confirmations and ACL errors; current evidence shows confirmed sends |

From the earlier log samples:

- There is support for H1, though you must confirm the enum change and scope.
- H2 is strongly supported since stable also hits DB timeouts.
- H3 is a **clear policy issue** if broad outages must not go to the DLT.
- Rebalances and duplicate suppression are **not enough** to conclude lost business events.
- `dlt.publish.confirmed` for offset 8112 weakens H7 for that record, though it does not rule out DLT producer errors at another point in time.

Separate the **incident trigger** from **amplifying mechanisms**. A canary change might raise DB latency; the retry policy turns it into a DLT backlog; rebalances may be a consequence of blocked handlers.

## 16. Phase 4 — Assessing Impact and Severity

### Do Not Use Consumer Lag Alone to Measure Impact

At 09:13, lag is 13,900. That figure represents offset backlog at that moment. It does **not** tell you exactly how many orders were lost or un-updated, because:

- Failed events may be waiting on retries.
- Events may have their source offsets committed while sitting in the DLT.
- Duplicate deliveries may have been blocked at the DB.
- One order can span multiple events/versions.
- Some events may be filtered out by policy.

Evaluate at minimum:

1. Count of **unique event IDs** emitted during the impacted window.
2. Count of event IDs successfully applied to the business store.
3. Count of pending events in the source group (by offset/range).
4. Count of events sent to DLT and still unresolved.
5. Count of events with unknown outcomes requiring reconciliation.
6. Count of customers/orders whose visible status lags behind the source.

### Event-ID Reconciliation Example

Suppose during the investigation window, the publisher lists 20,000 unique event IDs:

```text
Published unique events:           20,000
Processed marker unique events:   18,700
DLT source event IDs not applied:  1,000
Pending / unknown at snapshot:       300
-----------------------------------------
Accounting total:                 20,000
```

This is an **illustrative breakdown into non-overlapping buckets at a single snapshot**. In production, deduplicate eventIds, reconcile events appearing in both DLT and DB, and publish totals only when the upstream event-ID source is trustworthy.

If no published event index exists, reconcile against producer outbox tables, event catalogs, retained topic records, or upstream audits. Do not treat `LOG-END-OFFSET` directly as total business events across the system.

## 17. Phase 5 — Safe Mitigation Decisions

Mitigation usually proceeds along **two parallel tracks**:

- Reduce or remove regression introduced by the canary.
- Relieve database pressure and stop the retry/DLT storm.

### 17.1. Controlled Canary Stop

In the lab:

```bash
kubectl -n kafka-lab scale deployment/order-projection-canary \
  --replicas=0
```

This mutates system state and should only run in authorized lab/staging environments. In production, verify namespace/context, permissions, and incident change procedures.

After stopping the canary:

1. Wait for the group rebalance.
2. Confirm stable consumers take over the required partitions.
3. Monitor consumer lag and processing rate.
4. Check for redelivered events during ownership changes.
5. Do not mistake rolling back an image for rolling back committed data.

**Do not reset offsets just because the canary failed.** Group offsets belong to the group, not solely to the canary pod.

### 17.2. Relieving DB Connection Pressure

Depending on root cause:

- Lower concurrency or the number of consumers issuing concurrent DB calls.
- Cap in-flight requests and inspect DB connection acquisition timeouts.
- Pause/stop consumption per runbook if the backend cannot accept more load.
- Inspect long-running transactions, connection leaks, slow queries, or v1.9.0 logic changes.
- Restore database/downstream capacity using authorized mechanisms.

**Raising the pool from 20 to 200 is not a default fix.** If the database only supports 30 effective connections, enlarging the pool can destabilize it further. Measure DB server capacity and why connections are being held.

### 17.3. Avoiding DLT Storms During Broad Infrastructure Outages

If policy states that **transient DB outages must not mass-route to the DLT**, you can:

1. Pause/stop processing during the outage, holding source offsets back for unprocessed records.
2. Add circuit breakers, longer backoff, retry budgets, and infrastructure alerts.
3. Separate invalid data from dependency outages at the exception classification layer.
4. Choose fail-stop or controlled resume for infrastructure faults rather than treating DLT as default recovery.
5. Reserve the DLT for data/record-specific errors or policy-approved cases.

Having `DefaultErrorHandler` publish to DLT upon retry exhaustion is a configured behavior; it does not automatically tell a “widespread DB outage” apart from a “poison record”. **Changing semantics requires changing policy and adding regression tests**, not just relabeling logs.

### When Is Canary Rollback Insufficient as a Mitigation?

If the same error already occurred before the canary, stems from the shared database cluster, or comes from a producer schema change incompatible with stable as well, rollback alone will not solve the entire incident. Treat rollback as a hypothesis with measurable impact and verify metrics afterward.

## 18. Phase 6 — Observing the System Post-Mitigation

After every change, verify **recovery signals**, rather than just watching error logs drop.

| Signal | Tentative Sign of Improvement | What Still Needs Checking |
| --- | --- | --- |
| Consumer group | Stable assignments, no constant rebalances | Are members actually polling and processing? |
| Lag | Drops over time with steady ingress | Is it dropping via successful processing or DLT routing? |
| Processing throughput | Exceeds ingress long enough to drain backlog | Does DB remain stable under catch-up load? |
| DLT rate | No longer spiking abnormally | Is there a plan for existing DLT backlog? |
| DB pool | Active/pending/latency drop | Any hidden connection leaks or long transactions? |
| Handler errors | Retryable errors drop | Are unknown status/validation errors still occurring? |
| Business reconciliation | Mismatches shrink, pending events resolve | Version/order accuracy, duplicate side effects |
| App resources | CPU/heap/GC stable | Any growing retry queues or thread backlogs? |

### Backlog Drain Time Example

If after mitigation there is 16,000 lag, average ingress is 100 records/s, and consumer throughput averages 160 records/s, the theoretical drain rate is:

```text
Net drain rate = 160 - 100 = 60 records/second
Estimated drain duration = 16,000 / 60 ≈ 267 seconds
                        ≈ 4.4 minutes
```

This estimate assumes **rates and conditions stay steady**, not a guaranteed deadline. If retries/DLT, partition skew, or DB throughput fluctuate, actual duration will differ. Even as lag falls, still check business outcomes.

## 19. Phase 7 — Reconciling Offsets and Business Data

### 19.1. SQL Querying Markers Over Time

```sql
SELECT
    DATE_TRUNC('minute', processed_at) AS minute_bucket,
    COUNT(*) AS unique_processed_events
FROM processed_order_event
WHERE processed_at >= TIMESTAMPTZ '2026-11-16 02:00:00+00'
  AND processed_at <  TIMESTAMPTZ '2026-11-16 03:00:00+00'
GROUP BY 1
ORDER BY 1;
```

Timestamps are for lab illustration only. Pay attention when comparing UTC timestamps against monitoring UI timezones.

### 19.2. Checking for Duplicates in the Marker Table

With a primary key on `(projection_name, event_id)`, the table cannot hold two rows with identical keys while the constraint is active. You can still query to confirm existing data:

```sql
SELECT projection_name, event_id, COUNT(*) AS row_count
FROM processed_order_event
GROUP BY projection_name, event_id
HAVING COUNT(*) > 1;
```

An empty result only proves no duplicates exist **in the marker table**; it does not prove two emails or HTTP calls were not sent. Verify each external downstream side effect separately.

### 19.3. Reconciling State Versions

```sql
SELECT
    order_id,
    last_event_version,
    current_status,
    updated_at
FROM order_projection
WHERE order_id IN ('order-1092', 'order-1093')
ORDER BY order_id;
```

If upstream keeps a reliable final-state table/tracker per order, compare it against the projection. When an order reached event version 7 at source while the projection sits at version 5, determine whether events 6/7 are pending, in the DLT, or filtered by policy.

### 19.4. Do Not Compare Offset Counts Blindly Using `COUNT(*)`

Kafka offsets can have gaps due to retention/compaction deletions or transaction control/batching depending on how you read them. One event might not map 1:1 to a business marker. Therefore, reconciling by business key/`eventId` over a reliable time window/source snapshot is stronger than matching raw offsets to row counts.

## 20. Phase 8 — Investigating and Processing the DLT

In this incident, the DLT holds at least two distinct groups to separate:

- **Group A:** `InvalidOrderEventException: UNKNOWN_STATUS` — compatibility/validation error.
- **Group B:** `CannotGetJdbcConnectionException` — infrastructure dependency failure combined with a retry policy unsuited for broad outages.

These two groups should not be replayed together blindly without preconditions.

### 20.1. Collecting DLT Cases

Suggested case table:

```sql
CREATE TABLE order_dlt_case (
    source_topic VARCHAR(200) NOT NULL,
    source_partition INTEGER NOT NULL,
    source_offset BIGINT NOT NULL,
    event_id VARCHAR(120),
    error_category VARCHAR(80) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'NEW',
    first_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    replay_request_id VARCHAR(120),
    PRIMARY KEY (
        source_topic, source_partition, source_offset
    )
);
```

DLT headers from `DeadLetterPublishingRecoverer` normally include source details and exception metadata; read the exact header constants/formats for your Spring Kafka version. If a source record is sent to the DLT multiple times at different DLT offsets, keying by **original source topic-partition-offset** prevents duplicate case entries (within a defined consumer scope).

If multiple consumer groups or services share the audit store, include projection/group identity in the key to avoid conflating separate cases.

### 20.2. Prioritizing by Reprocessability

| Error Group | Precondition Before Replay | Risk |
| --- | --- | --- |
| Unknown status | Deploy consumer supporting the status or apply new migration/validation rule | Replaying too early sends it straight back to DLT |
| DB timeout | Database healthy, suitable retry/circuit breaker in place | Mass replay can overload DB again |
| Malformed JSON | Audited payload repair or manual handling | Retrying the same payload will not fix itself |
| Permission failure | Fix permissions/secrets per process | Replays fail again while unauthorized |
| Unknown exception | Classify root cause and verify handling | Can create an infinite replay loop |

### 20.3. Rate-Limited Replay

Operational workflow:

1. Finalize the case list by error group, source coordinate, and `eventId`.
2. Confirm the consumer version supports the data and the backend is healthy.
3. Check markers so already-validly-processed events are not re-sent if policy permits skipping.
4. Obtain approval for scope, event count limit, and replay rate.
5. Publish to a dedicated replay topic or source per design, attaching a correlation/replay request ID.
6. Observe actual outcomes in the business store, not just Kafka send acknowledgments.
7. Mark cases `RESOLVED` only after confirming outcomes.
8. Audit payload versions and replay reasons; never silently mutate original records.

**Do not reset all consumer group offsets back to the beginning of the topic.** Overly broad resets trigger massive load and duplicate side effects across millions of processed events. Case-list replay controls the blast radius.

### DLT Records Can Duplicate

If a DLT publish succeeds yet the source offset does not commit due to a crash, Kafka can redeliver the source record and the recoverer can publish it to the DLT again. Deduplicate by source coordinate/event ID in audit tracking. A new DLT offset is **not necessarily a new business failure**.

## 21. Sub-Problem: The DLT Producer Also Fails

Suppose during the outage, the Kafka DLT topic has the wrong partition count or the service account lacks WRITE permissions.

Simulated symptom:

```text
ERROR event=orders.dlt.publish.failed
  sourceTopic=orders.events
  sourcePartition=3 sourceOffset=8175
  target=orders.events.DLT
  exception=TopicAuthorizationException
```

If the recoverer is not configured to treat publish failures as errors, the system can mistakenly believe the record was quarantined and advance the source offset undesirably.

In Spring Kafka 3.x, `DeadLetterPublishingRecoverer` offers options such as:

```java
recoverer.setFailIfSendResultIsError(true);
```

This treats send-result failures as recovery failures. Still, how the container retries, seeks, commits offsets, and transitions state depends on `DefaultErrorHandler` and `KafkaTemplate` configuration. Write integration tests for your exact version rather than relying solely on the method's existence.

### Follow-Up Questions

- Should you manually create the DLT topic right in the middle of an incident?
- How many partitions must the DLT topic have if the recoverer uses `record.partition()`?
- If the DLT loses WRITE permission, should you keep committing source offsets?
- If half the records already hit the DLT, how do you prevent duplicate auditing/replaying?

Answers must be grounded in your data guarantees and operational authorities, not simply making error logs disappear.

## 22. Sub-Problem: Rebalance and Duplicate Delivery

After the canary leaves the group, stable takes over P3. If the canary committed to the DB for a record without committing the Kafka offset, stable can read that record again.

```text
Consumer canary:
  poll P3 offset 8109
       |
       v
  DB transaction COMMIT
       |
       X process loses partition
       |
       v
  Kafka offset commit incomplete

Consumer stable:
  assigned P3
       |
       v
  re-reads offset 8109
       |
       v
  processed_order_event already has eventId
       |
       v
  Duplicate side effect skipped
```

This is normal under at-least-once semantics. Distinguish:

- **Duplicate delivery:** the same record/event is passed to the handler again.
- **Duplicate processing attempt:** the handler runs its logic multiple times, possibly before commit or after rollback.
- **Duplicate business side effect:** data, money, or emails are actually mutated twice.

Only the third outcome is wrong if business rules forbid it. A single idempotency marker can block DB duplicates yet does not automatically protect external HTTP/email calls.

### How to Test It

In the lab, create an event with a fixed `eventId`, let the handler write to the DB, then simulate a replay. Expect the DB marker not to duplicate and the projection not to mutate improperly. To reproduce a crash right at the **DB committed, Kafka offset uncommitted** boundary, use fault injection or an independent process; do not assume a polite `container.stop()` creates the same race.

## 23. Phase 9 — Updating Retry Policy Post-Incident

A root cause review may propose changing policy rather than just raising retry limits.

### 23.1. Target Policies by Error Type

| Error Category | Nature | Target Policy |
| --- | --- | --- |
| Validation/unsupported schema | Record-specific, won't self-heal | Audited DLT/quarantine; fix consumer/schema and replay |
| Isolated DB timeout | Potentially transient | Bounded retries with backoff and time cap |
| Widespread DB outage | Infrastructure unavailable | Circuit breaker/pause/fail-stop, alert; avoid DLT storms per business rules |
| Serialization/producer error | Payload and producer dependent | Do not falsely commit source if DLT publish fails |
| Unknown programming bug | Unlikely transient | Escalate, avoid endless retries |
| External API 429 | May return `Retry-After` | Backoff/rate limit per API contract |
| Duplicate event ID | May be valid redelivery | Skip side effect via idempotency marker, do not DLT by default |

Some financial systems choose **never to skip/commit source** merely because a record goes to DLT, whereas analytics pipelines allow DLT quarantine to preserve throughput. Document the data-policy decision explicitly instead of forcing one policy onto every workload.

### 23.2. Avoiding Nested Retries

A handler might use Spring Retry or HTTP client retries while `DefaultErrorHandler` retries the listener itself. If the client retries 3 times and the container retries 3 times, one business operation can generate far more calls than expected.

To investigate retry storms, measure attempts at **every layer**:

```text
Kafka record delivery
    |
    +-- DefaultErrorHandler retry budget
            |
            +-- Service method
                    |
                    +-- HTTP/JDBC client retry budget
```

The target design must bound total retry budgets, timeouts, and backoff coordination. Never let two layers retry unboundedly.

## 24. Is Non-Blocking Retry the Immediate Fix for This Incident?

Spring Kafka provides `@RetryableTopic`, which routes failed records to retry topics so the source partition is not blocked long. However, it does not inherently solve a database outage or schema incompatibility.

Mechanism illustration:

```text
orders.events
   |
   +-- normal success
   |
   +-- temporary failure -> orders.events-retry-...
                              |
                              +-- retry later
                              |
                              +-- exhausted -> DLT
```

The upside is that poison records do not stall the source partition continuously. Yet:

- It introduces additional retry topics, consumers, offsets, and ACLs.
- Later records on source can be processed ahead of records waiting on a retry topic.
- Workloads needing per-key ordering require versioning/ordering rules.
- When a DB outage affects all records, retry topics still fill up with huge backlogs.
- Combining `@RetryableTopic` with blocking retries can multiply total attempts beyond expectations.

Therefore, mid-incident, **do not switch to an untested retry topology** merely to push lag down. Favor simple, rollback-safe measures with verified evidence. Evaluate non-blocking retry architecture via controlled testing after the incident.

## 25. Testing the Incident Scenario with Embedded Kafka

Embedded Kafka suits verifying retries, DLT routing, and core processing in JVM tests. It does not faithfully reproduce broker outages, cluster ISR shifts, process crashes, or network partitions.

Illustrative Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

For the PostgreSQL `ON CONFLICT` example, use a test PostgreSQL instance or Testcontainers when exercising the real business SQL. H2 only works when test SQL is dialect-compatible or the business tier is mocked.

### 25.1. Setting Up the Test Broker and Topics

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=order-projection-it",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "app.kafka.topic=orders.events.lab",
    "app.kafka.dlt-topic=orders.events.lab.DLT"
})
@EmbeddedKafka(
    partitions = 4,
    topics = {
        "orders.events.lab",
        "orders.events.lab.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class OrderIncidentIntegrationTest {
    // Write tests in the sections below.
}
```

If the app defines topic beans or `KafkaAdmin`, avoid declaring identically named topics with mismatched partition counts in the same test context. Use distinct group IDs per suite to avoid reusing stray committed offsets.

### 25.2. Testing Non-Retryable Event Routing to DLT

Assume the listener parses JSON and throws `InvalidOrderEventException` on unknown statuses.

```java
@Autowired
KafkaTemplate<String, String> producer;

@Autowired
EmbeddedKafkaBroker broker;

@Test
void unknownStatusIsQuarantined() throws Exception {

    String payload = """
        {
          "eventId":"evt-it-invalid-1",
          "orderId":"order-it-1",
          "version":1,
          "status":"UNKNOWN_TEST_STATUS"
        }
        """;

    producer.send(
        "orders.events.lab",
        3,
        "order-it-1",
        payload
    ).get(10, TimeUnit.SECONDS);

    Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.consumerProps(
            "dlt-verifier-" + UUID.randomUUID(),
            "false",
            broker
        )
    );

    props.put("auto.offset.reset", "earliest");

    try (Consumer<String, String> verifier =
            new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new StringDeserializer()
            ).createConsumer()) {

        ConsumerRecord<String, String> dlt =
            KafkaTestUtils.getSingleRecord(
                verifier,
                "orders.events.lab.DLT",
                Duration.ofSeconds(20)
            );

        assertEquals(payload, dlt.value());
        assertEquals("order-it-1", dlt.key());
        assertEquals(3, dlt.partition());
    }
}
```

This is an illustrative method; add imports for JUnit, Spring Kafka, Kafka client, `Map`, `UUID`, `Duration`, `TimeUnit`, and corresponding test beans. To keep tests isolated and reliable, wait for the source listener to receive partition assignments before publishing, isolate topic/group data, and ensure no extraneous DLT records pollute the test.

**Goal:** prove the specific record was recovered into the DLT, rather than merely seeing an exception log. Also verify the DB projection was not updated for the invalid record.

### 25.3. Testing Transient Retry Followed by Success

Using a fake dependency:

```java
AtomicInteger attempts = new AtomicInteger();

OrderDependency fake = event -> {
    int call = attempts.incrementAndGet();

    if (call <= 2) {
        throw new TemporaryOrderDependencyException(
            "Controlled transient outage",
            new IllegalStateException("test-only")
        );
    }
};
```

With `FixedBackOff(1000L, 2L)` and matching retryable policy, assertions:

1. The event eventually succeeds.
2. No DLT record is produced for that event.
3. The service is re-invoked per policy in an isolated single-record scenario.
4. Business side effects commit only once.
5. The group can still process valid subsequent events.

Do not rely solely on `attempts==3` to claim success; business DB state and DLT absence are the primary proof.

### 25.4. Testing Retry Exhaustion and Recoverer Failure

Two independent scenarios:

- Dependency always throws transient errors: verify current policy routes to the DLT once the retry budget runs out.
- DLT producer fails to send: verify the recovery error propagates and the system does **not silently** mark the source record as successfully processed.

Do not delete real topics or revoke production permissions. Use mock `KafkaTemplate`/Testcontainers or lab topics/credentials to inject controlled failures. When mocking send errors, also simulate asynchronous future failures depending on producer API version; throwing synchronously from the send method alone may miss send-result error handling.

## 26. Testing Rebalances and Consumer Crashes

A comprehensive incident drill should also exercise partition ownership transitions.

### Testing Graceful Leave in the Lab

1. Create a 4-partition topic and two consumer containers A/B in the same group.
2. Start A, wait until A is assigned all partitions.
3. Start B, wait for Kafka to rebalance partitions.
4. Assert the union of assignments equals all partitions and their intersection is empty once stable.
5. Stop B and wait for A to reclaim partitions.
6. Send a new event and confirm the handler keeps processing.

Example Awaitility check:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> pa = assigned(a);
        Set<TopicPartition> pb = assigned(b);

        assertFalse(pa.isEmpty());
        assertFalse(pb.isEmpty());
        assertTrue(Collections.disjoint(pa, pb));

        Set<TopicPartition> all =
            new HashSet<>(pa);
        all.addAll(pb);

        assertEquals(4, all.size());
    });
```

`assigned(...)` is a helper returning the current partition set, converting `null` to an empty set; `a` and `b` represent started containers. Do not assert that consumer A must always get partitions 0/1; that depends on the assignor.

### Testing Process Crashes

If the goal is to open the window where DB commit succeeds yet Kafka offset is uncommitted, you need:

- Consumers running in separate processes/containers.
- Fault injection confirming the DB committed event X.
- Abruptly killing the consumer before the offset commits.
- Verifying the committed offset stayed behind.
- Letting another member take over and observing redelivery.
- Verifying the idempotency marker blocks duplicate side effects.

A polite `container.stop()` normally lets the consumer finish/commit and is **not** an equivalent crash test. Testcontainers or a staging setup is better suited here.

## 27. Phase-by-Phase Decision-Making Exercise

To prevent the drill from turning into mechanical steps, learners must record their **decisions** at each phase.

| Phase | Decision Question | Minimum Evidence |
| --- | --- | --- |
| Detect | Is this an incident or a brief spike? | Lag/DLT/DB metrics, timestamps |
| Triage | Which customer/order segments are impacted? | Business KPIs and event ID window |
| Hypothesize | Is there one failure mode or multiple? | Logs from stable/canary, DB, Kafka |
| Mitigate | Roll back canary or reduce DB load first? | Impact, error rate, rollback feasibility |
| Stabilize | Is the system progressing steadily? | Assignment, throughput, lag trend |
| Recover | Which DLT cases can be replayed? | Root cause fixed, idempotency, approval |
| Verify | Are outputs accurate? | Business reconciliation and DLT case status |
| Close | Can the incident be closed? | SLO, owner sign-off, unresolved risks |
| Prevent | What policies and tests must change? | Root causes, action items, deadlines |

Every decision should note: **who decided**, **when**, **based on what data**, **what risk was accepted**, and **how to roll back the decision**.

## 28. Learner Question Set

### Group A — Diagnosis

1. From the timeline, identify at least three symptoms and two distinct causal hypotheses.
2. What does rising DLT count during a DB outage tell you about the retry policy?
3. Why does `pod Ready` not prove the consumer is processing properly?
4. Can you conclude P3 events were lost when the canary lost partition ownership?
5. Why can an event appear in the DLT while source consumer lag still decreases?
6. Which metrics distinguish pool exhaustion from connection leaks vs slow DB queries?

### Group B — Mitigation

7. When should consumption be paused/stopped rather than increasing retry attempts?
8. Why shouldn't you multiply the Hikari pool size by ten immediately?
9. After rolling back the canary, what must you check before declaring stability?
10. If the DLT producer fails, is it permissible to keep committing source offsets?
11. If `RETURN_REQUESTED` is a valid schema change, what are the short-term and long-term actions?
12. When multiple stable pods also see DB timeouts, will rolling back only the canary suffice?

### Group C — Data Correctness

13. What is the difference between duplicate delivery and duplicate side effects?
14. Why might the DLT contain two records for the same source topic-partition-offset?
15. Why is `eventId` usually better than `JobExecution ID` or Kafka offset for business idempotency?
16. If projection version is 7 and a retried record of version 6 arrives again, what must the handler do?
17. Does a SQL query showing “no duplicate markers” prove no duplicate emails were sent?
18. Why is resetting offsets to earliest not a safe DLT replay plan?

### Group D — Recovery and Post-Verification

19. What conditions permit replaying DB failures, and what conditions permit replaying schema failures?
20. If lag returns to baseline while 1,000 DLT cases remain `NEW`, can the incident be closed?
21. Which metrics are required to estimate backlog recovery time after mitigation?
22. How must a postmortem distinguish the trigger from contributing factors?
23. Which integration tests are needed to prevent recurrence?
24. Which new alerts would catch a DLT storm earlier?
25. If the same incident happened on a consumer using `@RetryableTopic`, what differences in offsets and ordering would you investigate?

## 29. Incident Report Submission Template

Learners should produce a report suitable for pasting into an incident management system.

### 29.1. Executive Summary

```text
Incident ID: LAB-KAFKA-20261116-01
Severity: [SEV level per lab policy]
Start: 09:04
Detected: 09:07
Mitigation start: 09:16
Service: order-projection
Group: order-projection
Source topic: orders.events
DLT topic: orders.events.DLT

Summary:
  [2–4 sentences: which systems, which customers,
   what impact, why recovery was needed]
```

### 29.2. Timeline

| Time | Evidence | Action/Observation | Owner |
| --- | --- | --- | --- |
| 09:00 | Canary deploy log | v1.9.0 joins group | Release owner |
| 09:04 | InvalidOrderEventException | DLT begins rising | On-call |
| 09:07 | Hikari pool metrics | Connection timeouts climb | DBA |
| 09:10 | Rebalance/lag | P3 ownership transferred | Kafka owner |
| 09:16 | Mitigation record | Canary stopped, DB pressure addressed | IC |
| 09:32 | Lag/throughput metrics | Backlog nearly drained | On-call |
| 09:40 | Business reconciliation | Unresolved DLT cases remain | Business owner |

These milestones come from the simulated dataset; in a live lab run, replace them with real timestamps and evidence.

### 29.3. Impact Assessment

Must document:

- Count of event IDs in the impacted window.
- Count of event IDs processed successfully.
- Count of event IDs in the DLT, broken down by error category.
- Count of pending/unknown events and identification method.
- Count of orders/customers with delayed or incorrect states.
- Confirmed duplicate business side effects (if any).
- Duration below SLO and backlog drain duration.

If data is incomplete, write `unknown, reconciling` instead of inventing numbers.

### 29.4. Root Cause and Contributing Factors

Structure:

```text
Trigger:
  [Evidenced initiating event]

Direct causes:
  [E.g. parser lacks new enum support, connection timeouts]

Contributing factors:
  [E.g. retry-to-DLT policy on DB outage,
   missing canary coverage gate, missing timeouts]

Detection gap:
  [E.g. alerting only on lag, not DLT rate by exception]

Recovery gap:
  [E.g. DLT lacked owner and replay runbook]

What went well:
  [Steps that limited impact]

What to improve:
  [Changes with owners and deadlines]
```

Do not blame an individual merely for executing a deployment. Postmortems should focus on system mechanisms, guardrails, and decisions made with the information available at the time.

### 29.5. Action Items

| Action | Type | Priority | Owner | Completion Evidence |
| --- | --- | --- | --- | --- |
| Add enum/status compatibility tests | Prevention | High | Application team | Integration tests passing on corpus |
| Separate DB outage policy from poison DLT | Prevention | High | Kafka team | Failure-mode tests and runbook |
| Alert on DLT rate by exception class | Detection | High | SRE | Alert test fires signal |
| Add business reconciliation | Detection | High | Data/Backend | Dashboard keyed by eventId |
| Test canary receiving representative load | Deployment | Medium | Release team | Canary gate with verified exposure |
| Test process crash between DB/offset commit | Reliability | Medium | QA/SRE | Lab test showing redelivery and idempotency |
| Build approved DLT replay workflow | Recovery | High | Operations | Lab replay with audit log |
| Tune DB connection acquisition/SQL | Capacity | Based on evidence | DBA | Metrics post load test |

Every action needs a clear owner, due date, and verification criteria; never write vague goals like “improve monitoring”.

## 30. Exercise Grading Rubric

Total 100 points:

| Criterion | Max Points | Requirements |
| --- | ---: | --- |
| Multi-source diagnosis | 20 | Uses Kafka, DB, app, release, and business metrics; avoids premature conclusions |
| Root-cause classification | 15 | Separates schema, DB, retry/DLT, and rebalance issues |
| Safe mitigation | 15 | Rollback/circuit breaker without arbitrary offset resets |
| Data correctness | 15 | Distinguishes lag, DLT, replay, duplicate delivery, and side effects |
| Recovery and replay | 15 | Approvals, rate limits, idempotency, outcome reconciliation |
| Reliability testing | 10 | Covers retries, DLT failures, crashes/rebalances |
| Communication and postmortem | 10 | Timeline, impact, owners, action items, evidence |

**Mandatory passing conditions:** do not propose steps that silently lose records, never delete metadata or indiscriminately reset group offsets, and never declare recovery based solely on pod readiness or consumer lag.

Not every passing answer chooses identical mitigations. Points are earned by how you use evidence, control risk, measure impact, and verify results.

## 31. Suggested Approach for the Simulated Scenario

This section serves as a reference guide after learners complete triage independently.

### 31.1. Key Findings

From the evidence:

- Canary v1.9.0 was assigned P3 and hit unknown-status errors on specific records, pointing to schema compatibility issues.
- Stable also hit DB connection timeouts, so the DB issue is not confined solely to the canary.
- DLT spiked alongside transient JDBC errors, showing that an exhaust-then-DLT retry policy turns brief outages into large quarantine backlogs.
- Rebalances and duplicate suppression signal a need for reconciliation; they do not by themselves prove data loss or duplicate side effects.
- Falling lag post-mitigation shows progress, yet remaining DLT items require a separate workflow.

### 31.2. Sensible Remediation Path

1. Open the incident, assign roles, confirm scope, and capture baseline.
2. Gather group assignments, per-partition lag, canary/stable errors, and DB metrics.
3. Halt canary expansion; consider stopping the canary due to isolated schema errors.
4. Relieve DB pressure according to actual cause (queries/connections/throughput), rather than blindly enlarging the pool.
5. Prevent DB-outage DLT storms per business policy, holding unprocessed records to retry/resume after backend stability returns.
6. Wait for the group to stabilize; confirm business throughput and lag truly recover.
7. Separate DLT items into schema failures and DB outage groups, checking markers before replay.
8. Replay under rate limits once parser/schema and DB are fixed, reconciling business outcomes.
9. Close the incident only when data and SLOs meet agreed thresholds and open cases have clear owners/plans.
10. Track action items: compatibility tests, retry policy, DLT alerts, crash-window tests, business reconciliation.

From the simulated tables alone, you cannot prove whether the canary directly triggered DB pool exhaustion or another query/DB fault occurred concurrently. **This must be marked unconfirmed until SQL traces or additional DB evidence exist.**

### 31.3. What Not to Do

- Increase `retryLimit` infinitely hoping the DB heals on its own.
- Mark the incident resolved when lag hits 0 while thousands of records sit in the DLT.
- Repeatedly run `kubectl delete pod` to “speed up rebalances”.
- Reset source group offsets to earliest without an idempotency/reconciliation plan.
- Delete the DLT topic assuming every record is “ignorable technical noise”.
- Upgrade all consumers to v1.9.0 while the canary handles one partition and is throwing errors.
- Assume `@KafkaListener` returning normally means HTTP/email/DB side effects happened exactly once.
- Raise the Hikari pool size past DB capacity without measuring.
- Claim “zero duplicates” solely because the marker table has unique keys while external side effects exist.

## 32. Advanced Variants for SRE/Backend Teams

Once the team finishes the base scenario, expand it using these common failure modes.

### Variant A — DLT Publish Rejected

Revoke DLT WRITE permissions in the **lab environment** so the recoverer hits `TopicAuthorizationException`. Require learners to prove source records are not falsely marked successful and that proper alerts fire.

### Variant B — Broker Coordinator Shift

In a multi-broker lab, inject a coordinator disruption with supported test tooling. Observe rebalances, stabilization time, member ownership, and redeliveries. Never test cluster behavior on a single embedded broker and extrapolate to production HA.

### Variant C — Downstream HTTP Times Out After Executing

The handler calls an order-status update API. The API commits yet the response times out; the Kafka consumer retries. Require API-level idempotency keys and target-state reconciliation rather than local DB markers alone.

### Variant D — Non-Blocking Retry Reorders Events

Replace `DefaultErrorHandler` with retry topics. Event version 5 goes to retry while version 6 is processed first. Require version guards or appropriate per-key ordering mechanisms.

### Variant E — Hot Partition

One partition receives 80% of all messages while three others carry light load. The canary receives the hot partition and falls behind even though partition counts look balanced. Require checking partition skew rather than comparing stable/canary solely by pod count.

### Variant F — Static Membership Duplicate `group.instance.id`

Start two lab consumers sharing the same static member ID. Observe fencing/rebalancing under the active group protocol/assignor, then fix how stable unique identities are assigned per consumer instance.

### Variant G — DLT Contains Sensitive Data

Add PII fields to events and require designing failure evidence capture without dumping raw payloads into logs/emails, enforcing ACLs, retention, and audited access.

### Variant H — Producer Outbox and Replay

Upstream uses an outbox. Compare outbox event IDs against consumed, DLT, and pending counts; compute accurate impact instead of treating log-end offsets as business event totals.

## 33. Drill Completion Checklist

Before considering the exercise complete, confirm:

- [ ] A timeline exists from detection through stabilization.
- [ ] Schema errors, database faults, retry/DLT policies, and rebalances are distinguished.
- [ ] At least one hypothesis was verified or refuted with evidence.
- [ ] No mutating operations were run on production offsets/topics/databases for experimentation.
- [ ] Mitigation decisions, executors, and rollback paths are documented.
- [ ] Consumer group progress after assignment stabilization is proven.
- [ ] DLT cases and event IDs are reconciled rather than reporting lag alone.
- [ ] Duplicate effects in the DB and external systems (if any) are checked.
- [ ] Controlled and audited DLT replay procedure is documented.
- [ ] Tests or test proposals exist for DLT publish failure, crash windows, and unknown statuses.
- [ ] Impact report states metrics and clear denominator definitions.
- [ ] Action items include owners, priorities, and completion criteria.
- [ ] Unconfirmed items are explicitly noted instead of assuming full root cause was found.
- [ ] Incident closure conditions are agreed with business owner/on-call.

The checklist helps learners self-verify exercise coverage; it does not replace verifying real operational conditions in each organization.

## 34. Summary

**Comprehensive incident handling in Spring Kafka** ties together multiple layers: producers, brokers, consumer groups, assignment/rebalance, retries, DLT, offset commits, database transactions, idempotency, deployments, and business outcomes. A single signal can mislead: dropping consumer lag does not mean every event was applied; a Ready pod does not mean the listener is making progress; a successful DLT publish does not mean business success.

In the simulated scenario, the canary exposed data compatibility faults, the database pool saturated, the retry policy pushed too many infrastructure faults to the DLT, and rebalances introduced redelivery potential. Recovery must balance **immediate impact reduction**, **protecting data from loss/duplication**, **preserving investigative evidence**, and **reconciling after DLT processing**. Never treat incidents by raising retries infinitely, resetting offsets recklessly, or ignoring DLT backlogs.

The habit to build is: **detect → contain → gather evidence → classify failures → rollback-safe mitigation → verify progress → recover/replay → business reconciliation → postmortem and regression tests**. When every step is backed by concrete evidence and clear ownership, Spring Kafka systems can weather multi-factor incidents while preserving data reliability.
