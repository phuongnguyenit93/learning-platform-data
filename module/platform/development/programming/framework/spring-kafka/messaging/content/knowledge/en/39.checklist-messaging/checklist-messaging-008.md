# Pre-Deployment Testing Checklist

## 1. Purpose and scope

This checklist verifies that a Spring Kafka application is ready for deployment to integration, staging, or production environments. The scope includes producers sending events with `KafkaTemplate`, consumers receiving events with `@KafkaListener`, and related Kafka components such as topics, partitions, offsets, consumer groups, serialization, retries, dead-letter topics (DLT), transactions, concurrency, and observability.

A test only proves what it actually exercises. A producer succeeding does not prove consumers handle the message; a consumer receiving a record does not prove offsets commit properly; a transaction committing does not prove a database and Kafka are atomic together. Therefore, test end to end from event contracts to operational behavior under failure.

## 2. How to use this checklist

Mark each item only after collecting test evidence. For inapplicable items, mark `N/A` with a reason; do not leave items blank simply because they were not tested. Each item should retain at least one piece of evidence such as a test report, log, metric, effective configuration, CLI output, or sign-off record.

- [ ] **PASS:** tested with supporting evidence.
- [ ] **FAIL:** tested and failed; requires an owner and remediation plan.
- [ ] **N/A:** not applicable, with documented reason.
- [ ] **NOT TESTED:** not yet checked; cannot be treated as deployment-ready.

Never mark PASS merely because a setting exists in YAML. Verify the actual effective values used by the application and Kafka brokers in the target environment.

## 3. Information to prepare before testing

- [ ] Identify Java, Spring Boot, Spring Kafka, and Kafka client versions in use.
- [ ] Record bootstrap server addresses for the test environment.
- [ ] Record topic names, partition counts, replication factors, and retry/DLT topics.
- [ ] Record each listener's consumer group ID.
- [ ] Record key/value schemas, serializers, deserializers, and event versioning rules.
- [ ] Record AckMode, commit strategy, retry policy, DLT policy, and transaction mode.
- [ ] Record each listener's concurrency, replica count, and partition count.
- [ ] Identify required authentication, TLS/SASL, principals, and ACLs.
- [ ] Define SLOs/SLAs: throughput, p95/p99 processing latency, lag, recovery time, and acceptable error rates.
- [ ] Prepare representative test data: normal payloads, large payloads, boundary values, legacy data, and invalid data.
- [ ] Identify owners for the application, Kafka platform, schema registry, security, and operations.

Version details matter because certain APIs and behaviors change across Spring Kafka/Kafka client releases. Tests must run against the exact dependency lock/BOM and configuration matching the deployable artifact.

## 4. Verify Kafka connectivity configuration

### 4.1. Bootstrap and network

- [ ] Application connects to all declared bootstrap brokers.
- [ ] DNS and `advertised.listeners` return hostnames/ports reachable from application pods or VMs.
- [ ] Network policies, firewalls, security groups, and routing permit required bidirectional traffic.
- [ ] Application handles broker restarts, leader movements, and reconnects.
- [ ] Production configs contain no local broker addresses or developer-only hostnames.
- [ ] Connection and request timeouts fit the environment's network latency.

### 4.2. Authentication, TLS, and ACLs

- [ ] Producer, consumer, and KafkaAdmin use the proper principals/service identities.
- [ ] Certificate chains and broker hostnames verify successfully under TLS.
- [ ] Keytabs, JAAS, truststores, keystores, and credentials come from a secret/config provider.
- [ ] Secrets never appear in Git, images, logs, exceptions, test reports, or artifacts.
- [ ] Producers hold required permissions on target topics.
- [ ] Consumers hold permissions to read topics and join the right consumer groups.
- [ ] KafkaAdmin holds only strictly required administrative permissions.
- [ ] If using transactions, the principal holds permissions on the corresponding transactional IDs.
- [ ] Test an under-privileged principal and confirm brokers reject the unauthorized action properly.
- [ ] Credential/certificate rotation workflow exists and reconnect after rotation has been tested.

### 4.3. Effective producer and consumer configurations

- [ ] Verify `acks`, `enable.idempotence`, `retries`, `delivery.timeout.ms`, `request.timeout.ms`, and `max.in.flight.requests.per.connection` per durability requirements.
- [ ] If relying on producer idempotence, confirm effective settings satisfy the Kafka client version's rules.
- [ ] Verify `key.serializer` and `value.serializer` match actual data types.
- [ ] Verify `key.deserializer` and `value.deserializer` match producer serializers.
- [ ] Verify `group.id`, `auto.offset.reset`, `enable.auto.commit`, `isolation.level`, and `max.poll.records`.
- [ ] If the Spring listener container manages commits, verify Kafka consumer auto commit is not accidentally enabled.
- [ ] Verify AckMode and listener acknowledgment match the chosen commit strategy.
- [ ] Check that test settings like `localhost`, shared group IDs, or unintended `auto.offset.reset=earliest` do not leak into production.
- [ ] Archive effective configuration (with secrets redacted) for reference.

For example, durability-focused producer configs may start with `acks=all` and idempotence, but final settings must fit the Kafka version, replication factor, `min.insync.replicas`, and system latency goals. Do not copy sample configs straight into production without inspecting brokers.

When enabling idempotence explicitly, verify your Kafka client version's constraints—especially `acks=all`, `retries` > 0, and `max.in.flight.requests.per.connection` within idempotent limits. When using transactions, verify the producer factory has transactions enabled and producer properties do not disable required semantics.

## 5. Verify topics and partitions

- [ ] All required topics exist or topic provisioning workflows are verified.
- [ ] Topic names match listener and producer configs exactly.
- [ ] Partition counts support required throughput and consumer concurrency.
- [ ] Replication factors match broker counts and availability requirements.
- [ ] `min.insync.replicas` aligns with `acks=all` and fault-tolerance policy.
- [ ] Retention time/size covers replay, investigation, and recovery windows.
- [ ] `cleanup.policy` (`delete`, `compact`, or combined) matches data semantics.
- [ ] For compacted topics, verify keys are stable and tombstones are handled properly.
- [ ] Retry/DLT topics have proper partitions, replication, retention, and ACLs.
- [ ] Do not increase partitions casually if the application relies on key-to-partition mapping or long-term ordering.
- [ ] Tested behavior on newly created topics, partition expansions, or metadata changes.

Note: Kafka guarantees ordering only within a single partition. If events for the same aggregate require sequential processing, producers must use a stable key such as `orderId`, and consumers must preserve compatible processing rules.

## 6. Test event contracts and serialization

### 6.1. Valid payloads and boundary data

- [ ] Producer sends valid payloads with all required fields.
- [ ] Consumer deserializes payloads and maps fields to the right data types.
- [ ] Test missing fields, null fields, empty strings, negative numbers, boundary values, and timestamps.
- [ ] Test timezones, date-time formats, decimal precision, and enums.
- [ ] Test large payloads near producer, broker, topic, and consumer size limits.
- [ ] Verify Unicode, Vietnamese characters, and multilingual data.
- [ ] Verify required headers: event ID, correlation ID, content type, schema/version, and tenant if applicable.
- [ ] Verify Kafka keys are generated consistently per aggregate needing ordering.

### 6.2. Schema compatibility

- [ ] New consumer version reads events emitted by current producer versions.
- [ ] If supporting rolling deployments, old consumers handle new events within committed backward compatibility.
- [ ] New producers do not emit fields/enums that break old consumers unexpectedly.
- [ ] Test adding optional fields, changing defaults, deprecated fields, and new enum values.
- [ ] If using Schema Registry, verify compatibility mode and subject naming strategy.
- [ ] If using JSON type headers or trusted packages, confirm deserializers trust only necessary packages.
- [ ] Maintain event fixtures for stored/replayable versions for regression testing.

### 6.3. Malformed payloads and deserialization failures

- [ ] Send corrupt or improperly encoded payloads and confirm errors are classified.
- [ ] Confirm deserialization errors are handled before the listener method executes.
- [ ] If failing records must route to error handler/DLT, configure deserializers that preserve error details, such as `ErrorHandlingDeserializer` in Spring Kafka.
- [ ] Verify bad records do not trap the consumer in an infinite loop at the same offset.
- [ ] Verify DLT preserves raw bytes and metadata needed for investigation or replay.
- [ ] Do not log full payloads containing personal data, credentials, or sensitive information.

## 7. Test producers using KafkaTemplate

- [ ] Records publish successfully to the right topic.
- [ ] Key, value, timestamp, partition, and headers match the contract.
- [ ] `SendResult`/record metadata contain valid topic, partition, and offset.
- [ ] Test partition routing both with keys and with null keys.
- [ ] Send multiple events with the same key and verify they land in the same partition.
- [ ] Verify send order for the same key under normal conditions and producer retries.
- [ ] Test callbacks/futures when the broker acknowledges success.
- [ ] Test callbacks/futures when the topic does not exist, ACL denies access, or brokers are unavailable.
- [ ] Confirm the application does not ignore async exceptions from `KafkaTemplate.send()`.
- [ ] Verify timeouts and retries do not cause uncontrolled send loops.
- [ ] Verify producers close cleanly per lifecycle on application shutdown.
- [ ] If using multiple producer factories, verify serializers, security, and transaction configs for each.

Minimal integration test example with an embedded broker:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@EmbeddedKafka(partitions = 3, topics = "orders")
@DirtiesContext
class OrderProducerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Test
    void publishesOrderEvent() throws Exception {
        OrderCreated event = new OrderCreated("order-42", "CREATED");

        SendResult<String, OrderCreated> result = kafkaTemplate
                .send("orders", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        assertEquals("orders", result.getRecordMetadata().topic());
        assertTrue(result.getRecordMetadata().offset() >= 0);
    }
}
```

`OrderCreated` in the example is an application DTO. The example requires `spring-kafka-test` (or the test starter matching your Spring Boot version), the test topic, and an application context with a configured `KafkaTemplate`. The return API of `KafkaTemplate.send()` differs between older and newer Spring Kafka lines; `Future.get()` is used here to wait for the result independently of callback style. An embedded broker suits fast integration tests; staging with broker topology and security matching production is still required.

## 8. Test consumers using @KafkaListener

- [ ] Listener subscribes to the right topics and group ID.
- [ ] Listener receives expected payload, key, headers, and metadata.
- [ ] In a stable group state, each partition is assigned to at most one consumer in the same group.
- [ ] Simulate side effects completing while the consumer dies/rebalances before commit; verify redelivery can occur and idempotency protects business logic.
- [ ] Two independent consumer groups both receive copies of events per pub/sub semantics.
- [ ] New consumers joining or leaving the group do not lose committed records.
- [ ] Test `auto.offset.reset=earliest` and `latest` on a group with no offsets.
- [ ] Verify a group with committed offsets resumes from the right position.
- [ ] Test restarting a consumer after successful processing and before/after commit.
- [ ] Test rebalances while the listener is actively processing.
- [ ] Test multi-consumer concurrency and partition distribution.
- [ ] Confirm excess consumers beyond partition counts do not create false throughput expectations.
- [ ] Confirm listener exceptions route to the error handler properly.
- [ ] Confirm listeners do not swallow exceptions when rollback/retry is needed.
- [ ] Test graceful shutdown and time allowed to finish in-flight records.

`auto.offset.reset` takes effect only when a group has no valid committed offset (or the offset is outside retention); it does not overwrite committed offsets. Tests should use a fresh group ID or intentionally reset offsets when verifying `earliest`/`latest`.

### Testing offsets and delivery semantics

- [ ] Determine whether the application requires at-most-once, at-least-once, or Kafka-scoped consume-transform-produce exactly-once.
- [ ] Verify AckMode and offset commit timing.
- [ ] Simulate crashing after side effects finish but before offsets commit.
- [ ] Confirm duplicate delivery causes no duplicate side effects or is absorbed by idempotency.
- [ ] Simulate failed offset commits after a rebalance.
- [ ] Confirm offsets do not commit before business logic finishes when at-least-once is required.
- [ ] With manual acknowledgment, confirm acknowledge is called only after successful processing.
- [ ] With batch listeners, confirm commit/rollback follows proper batch semantics.

Standard Kafka consumers can redeliver records when a process fails before committing. Consumers must be designed idempotently by event ID or business key whenever side effects can repeat. Do not use correlation ID instead of event ID to deduplicate distinct events belonging to the same business flow.

## 9. Test retries, error handlers, and DLT

### 9.1. Error classification

- [ ] Distinguish transient errors (timeouts, brief network glitches, service unavailable) from permanent errors (bad payloads, business validation failures).
- [ ] Retries apply only to recoverable error types.
- [ ] Non-retryable exceptions are recovered or routed to DLT per policy.
- [ ] Verify retry count, delay, backoff multiplier, max delay, and jitter if used.
- [ ] Verify total retry duration does not exceed poll/transaction timeouts in ways that cause unexpected rebalances or aborts.
- [ ] Confirm the error handler does not retry poison records infinitely.

### 9.2. Dead-letter topics

- [ ] Records failing after retry exhaustion route to the right DLT.
- [ ] DLT records retain payloads/raw bytes, keys, and required headers.
- [ ] Origin metadata such as topic, partition, offset, exception, and delivery attempt are retained per config.
- [ ] Recoverer principal has write permission on the DLT.
- [ ] DLT has sufficiently long retention and is monitored.
- [ ] Procedures exist for triage, data repair, and DLT replay.
- [ ] Replays do not cause duplicate side effects; downstream consumers have idempotency.
- [ ] Prevent DLT consumers from automatically republishing failing records to the main topic in an infinite loop.
- [ ] Test DLT publish failure: is the source offset committed, or does it retry per policy?
- [ ] Alerts trigger when DLT grows rapidly or records sit too long.

### 9.3. Retry topics and ordering

- [ ] If using `@RetryableTopic`, check retry topic names, partitions, and retention.
- [ ] Verify actual retry counts and delays.
- [ ] Verify how ordering can shift when records move through retry topics.
- [ ] If business logic requires strict per-key ordering, ensure the retry strategy prevents newer events from overtaking older ones improperly.
- [ ] Test non-blocking retries and DLT recovery when downstream services come back up.

## 10. Test transactions and exactly-once

- [ ] Transactional producers have unique `transactionIdPrefix` across concurrently running application instances.
- [ ] Producer factory and `KafkaTemplate` share the proper transaction configuration.
- [ ] Send multiple records in one transaction and verify all commit together or all abort together.
- [ ] Simulate an exception before commit and verify aborted records are hidden from `read_committed` consumers.
- [ ] Simulate producer fencing with two producers sharing a transactional ID in an isolated test.
- [ ] Confirm fenced producers are not reused.
- [ ] For consume-transform-produce, verify output records and consumer offsets commit in the same Kafka transaction.
- [ ] Verify consumers use `isolation.level=read_committed` when only committed data may be read.
- [ ] Test transaction timeouts and transaction coordinator unavailability.
- [ ] Test retry/error handling when a listener transaction rolls back.
- [ ] Confirm exceptions are not swallowed before the transaction manager decides to commit.
- [ ] Verify transactional ID ACLs and topic ACLs.
- [ ] Test graceful shutdown while a transaction is open.
- [ ] Test commit timeouts and reconciliation of ambiguous outcomes.

Exactly-once in Kafka has a clear scope: transactions can atomically write output Kafka records and consumer offsets. It does not automatically make database operations, HTTP calls, or external side effects outside Kafka exactly-once. When coordinating databases and Kafka, test Transactional Outbox/CDC and Inbox/idempotency.

## 11. Test partition ordering and concurrency

- [ ] Choose a stable key per aggregate, e.g., `orderId`, `accountId`, or `customerId`.
- [ ] Verify events with the same key route to the same partition.
- [ ] Verify events with different keys can run in parallel without assuming global ordering.
- [ ] Confirm partition count supports required parallelism.
- [ ] Verify total consumer count = replicas × listener concurrency.
- [ ] Test partition assignment when consumer count is less than, equal to, and greater than partition count.
- [ ] Verify scaling replicas up/down triggers expected rebalances and stabilizes again.
- [ ] Verify slow processing does not exceed `max.poll.interval.ms`.
- [ ] Test `max.poll.records` with realistic payloads and processing durations.
- [ ] Confirm consumer threads are not blocked indefinitely by HTTP, databases, or `Thread.sleep()`.
- [ ] If processing asynchronously, verify acknowledgments and backpressure are explicitly designed.
- [ ] Verify thread safety of services invoked from multiple listener threads.

## 12. Test data guarantees and idempotency

- [ ] Every event has a unique event ID stored and propagated consistently.
- [ ] Consumers reprocess the same event ID without unintended repeated side effects.
- [ ] Test duplicates from producer retries, consumer restarts, rebalances, and DLT replays.
- [ ] Test late-arriving or out-of-order events per business policy.
- [ ] Test older event versions and superseded events.
- [ ] When updating databases, use unique constraints/inbox or proper idempotency mechanisms.
- [ ] If using tombstones, verify downstream consumers delete state for the key properly.
- [ ] Data within the retention window can be replayed without corrupting current state.
- [ ] Reconciliation procedures exist for record counts or business invariants between producers and consumers.

## 13. Test observability and alerting

- [ ] Logs include service name, environment, topic, partition, offset, group ID, and event ID where appropriate.
- [ ] Correlation ID propagates via Kafka headers and appears in downstream logs.
- [ ] MDC is cleared after every record; correlation IDs do not leak across consumer threads.
- [ ] Trace context propagates if using Micrometer Tracing/OpenTelemetry.
- [ ] Do not put correlation ID, event ID, order ID, or offset into high-cardinality metric tags.
- [ ] Metrics exist for producer send success/failure and latency.
- [ ] Metrics exist for consumer record rate, processing duration, error rate, and lag.
- [ ] Metrics exist for retry count, DLT publish count, and DLT backlog.
- [ ] Metrics exist for transaction commits/aborts/fencing if transactions are enabled.
- [ ] Metrics exist for rebalance rate, rebalance latency, and consumer count.
- [ ] Dashboards break down errors per topic, group, and listener.
- [ ] Alerts define clear thresholds, sustained durations, and remediation guidance.
- [ ] Verify logs/metrics contain no sensitive payloads, tokens, or secrets.

Alerts should rely on trends and SLOs rather than a single log entry. For instance, lag spiking for a few seconds during a deployment may be normal; steadily rising lag paired with high processing latency requires alerting.

## 14. Performance and load testing

- [ ] Run normal load at expected throughput.
- [ ] Run peak/burst load and verify consumer lag recovers within allowed time.
- [ ] Use payloads sized realistically like production data.
- [ ] Measure producer send latency p95/p99 and send errors.
- [ ] Measure consumer processing latency p95/p99.
- [ ] Measure per-partition lag to detect hot partitions.
- [ ] Check per-partition throughput and key distribution.
- [ ] Monitor CPU, heap, GC pauses, network, disk, and broker request queues.
- [ ] Check buffer exhaustion, request timeouts, and backpressure.
- [ ] Test consumer lag behavior when downstream databases/services slow down.
- [ ] Confirm the system remains stable after load surges and drops back down.
- [ ] Compare results against agreed SLOs rather than arbitrary thresholds.

If a partition has an overly hot key, increasing consumer concurrency will not help because a partition is owned by at most one consumer in a group at any time. Review key distribution or business partitioning instead.

## 15. Resilience and failure-scenario testing

Execute in a controlled environment with active monitoring.

- [ ] Stop one broker and verify producers/consumers recover per replication settings.
- [ ] Restart the leader broker of an active partition.
- [ ] Temporarily interrupt the network between the application and brokers.
- [ ] Inject downstream service timeouts or 5xx errors.
- [ ] Slow down or make the database unavailable if listeners depend on it.
- [ ] Restart a consumer mid-record processing.
- [ ] Kill processes before and after commits to validate delivery semantics.
- [ ] Scale consumers up/down and observe rebalances.
- [ ] Make the coordinator unavailable in a test environment if possible.
- [ ] Verify application recovery once dependencies return to health.
- [ ] Confirm retries do not cause storms or overload downstream systems.
- [ ] Confirm no faulty offset commits skip records.
- [ ] Confirm duplicate deliveries do not corrupt business data.

Do not run chaos tests directly in production without a plan, blast-radius limits, operational approval, and an abort switch.

## 16. Deployment, rolling update, and rollback testing

- [ ] Deployed image/artifact matches the tested commit, version, and dependency lock.
- [ ] Environment configuration is verified prior to rollout.
- [ ] Consumer group ID stays stable when continuing offsets of the same application is intended.
- [ ] If changing group IDs, evaluate re-reading or skipping data under `auto.offset.reset`.
- [ ] Transaction ID prefixes are unique across replicas and never collide unintentionally.
- [ ] Rolling deployments do not take all consumers down simultaneously unexpectedly.
- [ ] Graceful shutdown of listener containers and producer factories is verified.
- [ ] `terminationGracePeriodSeconds`/shutdown timeout accommodates safe termination.
- [ ] New consumer versions are compatible with events from older producers during rollout.
- [ ] If rolling back the application, older consumers can still read events emitted by newer producers.
- [ ] Schema/event versions do not make rollback impossible.
- [ ] Rollback has been rehearsed with test data and real consumer groups.
- [ ] Readiness/liveness probes do not cause restart loops when Kafka is briefly unavailable.
- [ ] Canary or progressive rollout is used when risk warrants it.

## 17. Runbook and operability testing

- [ ] Guides exist for inspecting consumer groups with `kafka-consumer-groups`.
- [ ] Guides exist for inspecting topics, partitions, retention, and ACLs.
- [ ] Guides exist for handling consumer lag and continuous rebalances.
- [ ] Guides exist for handling serialization errors, retries, and DLT backlogs.
- [ ] Guides exist for handling transaction aborts/fencing if transactions are enabled.
- [ ] Guides exist for replaying DLT and reconciling duplicates.
- [ ] Dashboards link correlation IDs with trace IDs when tracing is enabled.
- [ ] On-call recipients and escalation paths are defined.
- [ ] Procedures exist for rotating credentials and recovering expired secrets.
- [ ] Plans exist for broker cluster or Schema Registry unavailability.
- [ ] Rollback runbooks and rollout abort criteria exist.
- [ ] Operations staff have practiced at least one representative failure scenario.

## 18. Minimum test suite by layer

| Testing tier | Goal | Common tools/methods | When to run |
|---|---|---|---|
| Unit tests | Mapping logic, validation, key selection, retry classification | JUnit, Mockito, AssertJ | Every commit |
| Serialization/contract tests | Payload and schema compatibility | Real serializers/deserializers, schema compatibility checks | Every event contract change |
| Embedded Kafka integration | Producers, listeners, offsets, headers, and error handlers | `spring-kafka-test`, `@EmbeddedKafka` | Pull requests/CI |
| Container integration | Behavior close to real brokers, security, KRaft, and broker configs | Testcontainers or Kafka test cluster | CI/staging |
| End-to-end tests | Multi-service/topic flows and side effects | Integration environment | Before release |
| Performance tests | Throughput, latency, lag, and resource usage | Load generator + metrics | Before major releases and topology changes |
| Resilience/chaos tests | Broker/network/downstream failures and recovery | Controlled fault injection | Scheduled or high-risk changes |
| Production smoke tests | Confirm connectivity, publish/consume, and dashboards post-deploy | Synthetic events or canary flows | After rollout |

Embedded Kafka is great for fast, repeatable tests. It does not replace testing against production-like broker topology, replication, ACLs, TLS, quotas, and networking.

## 19. Minimum test-case matrix

| ID | Scenario | Expected result | Evidence |
|---|---|---|---|
| KAF-001 | Producer sends valid event | Send succeeds, right topic/key/partition | Test report + metadata |
| KAF-002 | Consumer receives event | Listener receives right payload and headers | Integration test |
| KAF-003 | Two events with same key | Same partition and order preserved per design | Partition/offset assertion |
| KAF-004 | Invalid payload | Error handler classifies and handles properly | Log + DLT record |
| KAF-005 | Downstream timeout | Retries with backoff and stops at limit | Retry metrics/logs |
| KAF-006 | Retries exhausted | Record routes to DLT per policy | DLT metadata |
| KAF-007 | Consumer restarts before commit | Record may redeliver; idempotency protects side effects | Test + DB state |
| KAF-008 | Consumer group rebalance | Assignment restabilizes, no committed records lost | Group state + offsets |
| KAF-009 | Transaction abort | `read_committed` does not see aborted records | Consumer integration test |
| KAF-010 | Producer fencing | Stale producer cannot continue writing | Exception + broker/client logs |
| KAF-011 | Broker briefly unavailable | Clients reconnect, lag recovers | Metrics + recovery time |
| KAF-012 | Rolling deployment | New consumers stay compatible with in-flight events | Deployment test |
| KAF-013 | DLT replay | Event reprocesses safely | Replay audit + business state |
| KAF-014 | Peak load | Latency/lag stay within SLO or recover within RTO | Load test report |
| KAF-015 | Missing ACL | Broker rejects unauthorized operation properly | Broker authorization log |

## 20. Go/No-Go criteria before deployment

Allow rollout only when all mandatory conditions below are met:

- [ ] No blocker failures remain in unit, contract, or integration tests.
- [ ] Producer/consumer contracts are compatible with event versions currently stored in Kafka.
- [ ] Topics, partitions, replication, retention, and ACLs are provisioned properly.
- [ ] Retries/DLT are tested for both success and failure branches.
- [ ] Offset/acknowledgment semantics and idempotency are verified.
- [ ] If using transactions, commit/abort/fencing and `read_committed` are tested.
- [ ] Security, secret management, and TLS/SASL are verified in the target environment.
- [ ] Performance tests meet agreed SLOs or have written exception sign-off.
- [ ] Dashboards, alerts, runbooks, and on-call operators are ready.
- [ ] Rollout and rollback plans exist with an authorized decision-maker to halt deployment.
- [ ] Any remaining NOT TESTED/FAIL items are documented, risk-assessed, and explicitly approved.

Do not use test pass count as the sole criterion. One critical defect in offsets, duplicate side effects, schema compatibility, DLT, or security can make a release unsafe even when most other tests are green.

## 21. Evidence records to archive

- [ ] Commit SHA, build artifact version, and dependency/BOM versions.
- [ ] Unit, contract, integration, and end-to-end test reports.
- [ ] Topic/partition/replication/ACL validation results.
- [ ] Redacted effective configuration (secrets removed).
- [ ] Load test results including throughput, p95/p99 latency, lag, and resource utilization.
- [ ] Failure/recovery test results and recovery times.
- [ ] DLT/replay and transaction test results if applicable.
- [ ] Dashboard/alert snapshots and runbook version.
- [ ] List of FAIL, NOT TESTED, N/A items and exception approvers.
- [ ] Rollout/rollback plan with assigned owners.

## 22. Quick post-deployment verification checklist

- [ ] Application starts and connects to the Kafka cluster.
- [ ] Canary producer emits an event and receives acknowledgement.
- [ ] Consumer group has expected members and partition assignments.
- [ ] Synthetic event is processed once in business terms or duplicates are absorbed by idempotency.
- [ ] Offsets advance after successful processing.
- [ ] Consumer lag is not climbing continuously.
- [ ] No serialization errors, authorization errors, retry storms, or DLT spikes.
- [ ] Transaction commit/abort rates are normal if transactions are used.
- [ ] Dashboards, alerts, and log correlation work.
- [ ] No abnormal restarts/rebalances after rollout.
- [ ] Operations confirms stability before scaling rollout to all replicas.

## 23. Summary

- Pre-deployment testing must cover producers, consumers, topics/partitions, offsets/groups, serialization, retry/DLT, transactions, concurrency, and operations.
- Every assertion needs evidence; a property present in a file does not guarantee it is active.
- Testing duplicates, restarts, rebalances, retries, and DLT is mandatory to evaluate consumer reliability.
- Kafka exactly-once does not automatically cover databases or systems outside Kafka.
- Embedded Kafka suits quick tests; staging/container tests must confirm production-like topology, security, and broker configs.
- Go/No-Go decisions rely on risk and SLOs, not just test pass percentages.
- Post-rollout requires smoke tests and monitoring of lag, errors, rebalances, DLT, and transaction metrics.

A Spring Kafka application should only deploy once the development team has proven both the happy path and failure behavior, and operations has the metrics, alerts, and runbooks required to detect and recover from incidents.

## References

- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — Topic Configs](https://kafka.apache.org/documentation/#topicconfigs)
