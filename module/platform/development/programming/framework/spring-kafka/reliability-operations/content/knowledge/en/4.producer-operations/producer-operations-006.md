# Handling NotEnoughReplicas

## 1. What is the NotEnoughReplicas error?

In Kafka, a producer can receive `NotEnoughReplicasException` when the number of in-sync replicas (ISR) falls below the minimum configured for the topic. The error typically occurs when a producer sends with `acks=all` and the broker cannot satisfy the topic's replication policy.

This is a durability protection mechanism. Kafka refuses to acknowledge a write if the number of synchronized replicas does not meet the configured threshold. Therefore, this error usually indicates that the cluster lacks healthy replicas, replicas have fallen behind the leader, or `min.insync.replicas` is configured higher than the number of currently available replicas.

In Spring Kafka, the error surfaces on the producer side used by `KafkaTemplate`. The application may observe the exception directly or wrapped inside a `CompletableFuture`. What needs to be done is to identify which partition lacks ISR, why replicas left ISR, and whether the producer is still retrying within delivery timeout or has reached a final failure.

NotEnoughReplicas does not necessarily mean the entire Kafka cluster is down. A cluster can continue serving reads or writes on other partitions while specific partitions lack sufficient ISR to accept writes.

## 2. Understanding ISR and min.insync.replicas

Each partition has one leader and assigned replicas. Producers send records to the leader. The set of replicas keeping up sufficiently with the leader is called the ISR (in-sync replicas).

Three concepts to distinguish:

- **Replication factor:** the number of replicas assigned to each partition, including the leader.
- **ISR:** replicas currently synchronized enough to participate in write acknowledgements.
- **min.insync.replicas:** the minimum number of replicas that must be in the ISR for the broker to accept a write request with `acks=all`.

Example for a topic with replication factor 3 and `min.insync.replicas=2`:

| Partition state | Assigned replicas | Replicas in ISR | Write result with `acks=all` |
|---|---:|---:|---|
| Normal | 3 | 3 | Accepted; leader waits for replicas in ISR to acknowledge |
| One replica slow or offline | 3 | 2 | Still writable; ISR meets minimum threshold |
| Two replicas slow or offline | 3 | 1 | Rejected because ISR is below 2 |
| No leader available | 3 | 0 or no leader | Cannot write to the partition |

`acks=all` requires the leader to wait for acknowledgement from all replicas currently in the ISR. `min.insync.replicas` sets the lower bound on how many ISR members must be present when accepting writes. The two settings work together: `acks=all` defines how the producer waits for acknowledgement, while `min.insync.replicas` sets the minimum replication level the broker accepts.

### 2.1. Why does Kafka reject writes?

Suppose a partition has three replicas: broker 1 is leader, and brokers 2 and 3 are followers. The topic requires at least two replicas in the ISR.

Initially:

```text
Assigned replicas: 1, 2, 3
ISR:               1, 2, 3
min.insync.replicas = 2
```

Broker 3 suffers a disk failure or loses replication connectivity. After the follower is removed from the ISR:

```text
Assigned replicas: 1, 2, 3
ISR:               1, 2
min.insync.replicas = 2
```

The partition can still accept writes. If broker 2 is also removed from the ISR:

```text
Assigned replicas: 1, 2, 3
ISR:               1
min.insync.replicas = 2
```

The leader now has only one replica in the ISR. With `acks=all`, the broker rejects writes so it does not acknowledge records when replication falls below policy.

This behavior represents an intentional trade-off between availability and durability. When the cluster loses too many replicas, Kafka prioritizes rejecting writes to protect the configured data safety level.

## 3. Distinguishing pre-append and post-append errors

Kafka has two exceptions commonly mentioned in insufficient-ISR scenarios:

| Exception | When it occurs | Meaning |
|---|---|---|
| `NotEnoughReplicasException` | Before appending the record to the leader's log for that request | ISR was already below `min.insync.replicas` when the broker checked write preconditions |
| `NotEnoughReplicasAfterAppendException` | After the leader appended the record but before completing acknowledgement | ISR dropped below the threshold after append; the broker cannot acknowledge per replication policy |

This distinction matters when handling send outcomes.

With `NotEnoughReplicasException`, the broker rejected the request prior to append due to insufficient ISR. With `NotEnoughReplicasAfterAppendException`, the record may already have been appended on the leader, yet acknowledgement could not complete because ISR fell below the threshold. The application should not infer that a send ending with the second exception definitely wrote nothing.

Both exceptions belong to the retriable error group in the Kafka client. The producer can retry automatically when ISR recovers, within the send time limit. If the producer ultimately reports an error to the application, the state of that write may need cautious handling, especially for post-append errors.

If the application issues a new `send()` call as a business retry, the new send can create a distinct record. The idempotent producer protects internal retries of the same batch via producer ID and sequence number; it does not automatically merge two new application-level send calls. For important business events, use stable event IDs, a transactional outbox, or consumer-side deduplication.

## 4. Role of acks and producer configuration

`NotEnoughReplicasException` is typically tied to producers configured with `acks=all`. Different acknowledgement levels behave differently:

| `acks` | Behavior | Relationship to `min.insync.replicas` |
|---|---|---|
| `0` | Producer does not wait for broker acknowledgement | Provides no replication acknowledgement guarantee |
| `1` | Leader acknowledges after local append | Does not enforce the ISR threshold the way `acks=all` does |
| `all` or `-1` | Leader waits for all current ISR replicas to acknowledge | Broker requires ISR to meet `min.insync.replicas` |

Changing `acks=all` to `acks=1` may make the error disappear in some situations because the broker no longer enforces the same minimum ISR condition on writes. However, that changes the data protection level. If the leader fails before the record is replicated, already-acknowledged records can be lost in certain failover scenarios.

Therefore, never treat `acks=1` as the default operational fix. First restore replicas and bring ISR back into policy compliance.

### 4.1. Idempotence and retries

For durable producers, common settings are:

- `enable.idempotence=true`
- `acks=all`
- `retries` greater than 0
- `max.in.flight.requests.per.connection` at most 5

Idempotence helps the broker recognize retries of the same batch and avoid appending duplicates from internal producer retries. `delivery.timeout.ms` caps total time the producer tries to complete a send; a large `retries` value does not mean the producer tries forever.

If ISR recovers within the delivery timeout, the producer can retry successfully. If ISR remains below threshold until delivery timeout expires, the send future completes with an error. The application must observe the exception and act according to business policy.

### 4.2. Configuration in Spring Boot

Example producer configuration in `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
```

Time values are in milliseconds. These are illustrative values; choose delivery timeout based on latency SLOs and how long the business can wait.

**Note:** `min.insync.replicas` is a broker or topic configuration, not a producer property. Do not place it under `spring.kafka.producer.properties` expecting to change the broker's ISR threshold. The producer only sends requests; the broker enforces the synchronized replica count.

## 5. Configuring min.insync.replicas in the right place

A default value can be set at the broker using `min.insync.replicas`. Topics can override it with topic-level config. Check the effective value of the failing topic rather than looking only at a single broker config file.

Example creating a new topic with replication factor 3 and minimum ISR 2:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

To inspect leaders, replicas, and ISRs of a topic:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

To view current topic configuration:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --describe
```

If topic-level config must be changed after assessing risk:

```bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.created \
  --alter \
  --add-config min.insync.replicas=2
```

The commands above illustrate common Kafka CLI tools; use the scripts and admin permissions appropriate for your environment's Kafka deployment. If a topic has no override, the broker-level default determines the effective value.

Do not lower `min.insync.replicas` just to suppress the error before diagnosing replica health. Lowering the threshold can allow producers to receive acknowledgements with fewer copies than originally designed.

## 6. Handling errors in Spring Kafka

`KafkaTemplate.send()` returns an asynchronous result. In modern Spring Kafka, the result is `CompletableFuture<SendResult<K, V>>`. If the producer cannot finish sending after retries, the future completes exceptionally.

Example recording errors:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate
            .send("orders.created", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                        "Kafka publish failed, eventId={}, orderId={}",
                        event.eventId(),
                        event.orderId(),
                        exception
                    );
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.debug(
                    "Kafka publish acknowledged, topic={}, partition={}, offset={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
```

Required imports for the example:

```java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
```

Do not log only a generic message like "Kafka send failed". Retain the exception as the cause, while recording topic, partition if available, event ID, and correlation ID. Avoid logging sensitive payloads.

If error classification is needed, walk the cause chain to find the underlying Kafka exception:

```java
static Throwable rootCause(Throwable error) {
    Throwable current = error;

    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }

    return current;
}
```

Then you can recognize `NotEnoughReplicasException` or `NotEnoughReplicasAfterAppendException` depending on the actual exception returned by the client. Preserve the original exception for investigation and do not assume every send failure is insufficient ISR.

### 6.1. Kafka client retries vs. application retries

Two retry layers must be distinguished:

- **Kafka client retry:** the producer automatically resends retriable requests within the same send attempt, using sequence tracking when idempotence is enabled.
- **Application retry:** the application calls `KafkaTemplate.send()` again after the future fails or times out.

Kafka client retry is the first line and should be tuned consistently with delivery timeout. Application retries require bounded attempts, backoff, and business event identification. With `NotEnoughReplicasAfterAppendException`, the append outcome may be ambiguous to the application. Re-sending as a new record can create business duplicates.

When application-level retries are needed:

1. Preserve the event ID or business idempotency key.
2. Use exponential backoff with jitter to avoid synchronized retry storms across producers.
3. Cap retry count and total retry duration.
4. Put events into an outbox or durable retry queue if the process cannot hold requests in memory.
5. Design consumers to detect and skip already-processed events.
6. Record the final status so operations can handle undelivered events.

Do not retry infinitely inside future callbacks or block web threads with sleep loops. That can exhaust threads and amplify broker incidents.

## 7. Step-by-step diagnostic workflow

When receiving `NotEnoughReplicas` alerts or logs, establish scope before changing configurations.

### Step 1: Identify affected topic and partition

From the exception, producer logs, and record metadata, determine the topic, partition, timestamp, and producer client. If partition is absent in application logs, obtain details from broker logs and producer metrics.

Run:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
```

Inspect the fields:

- `Leader`: the broker currently leading the partition.
- `Replicas`: list of brokers assigned as replicas.
- `Isr`: list of replicas currently in-sync.

Compare the ISR count against the effective `min.insync.replicas`. If ISR is smaller than the threshold, you have confirmed the direct condition triggering the error.

### Step 2: Check effective configuration

Inspect topic-level config and broker defaults. Also check the partition's replication factor. A topic with RF=2 and min ISR=2 requires both replicas in the ISR to write with `acks=all`; it cannot tolerate even one replica leaving the ISR and still keep writing.

Do not confuse replication factor with ISR. RF is the number of assigned replicas in metadata; ISR is the subset currently synchronized at observation time.

### Step 3: Determine why replicas left the ISR

Inspect broker logs around the failure time, especially ISR shrink/expand events and replica fetcher logs. Look for common causes:

- Brokers stopped, crash-looping, or unable to register with the cluster.
- Packet loss, timeouts, or network partitioning between leader and followers.
- Full disks, high disk latency, or offline log directories.
- Replica fetchers falling behind due to high throughput or broker overload.
- CPU, garbage collection, or request queues slowing broker responses.
- Partition skew where one broker carries too many leaders or replicas.
- Replication throttling or insufficient bandwidth limits.

If the leader is offline or a partition has no leader, address the leader/partition state separately. `NotEnoughReplicas` and offline partitions can occur together, though they are distinct states.

### Step 4: Check cluster health and metrics

Commonly useful Kafka broker metrics:

| Metric | Used to detect |
|---|---|
| `UnderReplicatedPartitions` | Partitions with replicas behind the leader |
| `OfflinePartitionsCount` | Partitions lacking an available leader |
| `IsrShrinksPerSec` | Rate at which replicas are removed from ISR |
| `IsrExpandsPerSec` | Rate at which replicas rejoin ISR |
| Request handler idle / request queue | Whether brokers are overloaded processing requests |
| Disk usage and disk latency | Whether brokers face storage pressure |
| Network throughput and errors | Whether replication faces network bottlenecks |

On the producer side, monitor:

- Record retry rate and error rate.
- Request latency and record queue time.
- Produce throttle time.
- Send failure count by topic.
- Publish success rate and p95/p99 latency.

A rising retry rate can signal fluctuating ISRs even while the producer still manages to complete some sends.

### Step 5: Restore replicas and verify ISR

After identifying the cause, restore the broker or network link, fix disk/log directories, or adjust replication capacity. Watch replicas catch up to the leader and rejoin the ISR.

Conclude the incident is resolved only when:

- ISR count meets or exceeds `min.insync.replicas` for affected partitions.
- Under-replicated partitions return to normal per operational targets.
- ISRs stop shrinking/expanding abnormally.
- Producer publishing succeeds again and retry/error rates stabilize.
- No backlog or unsent events remain unaddressed per business procedures.

## 8. Recovery by root cause

| Root cause | Appropriate action | What to confirm |
|---|---|---|
| Follower broker stopped | Recover broker per runbook, check log directories and replica fetcher | Broker re-registers and replicas catch up to leader |
| Unstable inter-broker network | Check routing, firewall, packet loss, DNS, and inter-broker connectivity | Replication fetch stabilizes, ISR stops shrinking |
| Disk full or slow | Free space per retention/runbook, fix bad storage or expand capacity | Log directories online, disk latency normal |
| Replica lag from high load | Check throughput, throttling, broker capacity, and partition skew | Replicas catch up without creating new bottlenecks |
| Imbalanced partition assignment | Plan reassignment and throttle replica movement | New replicas are in ISR before concluding the change |
| `min.insync.replicas` exceeds current capacity | Re-evaluate RF, min ISR, and durability needs with owners | Change is approved and risks are documented |

Never delete log directories, move partitions, or force leader elections just to make the error disappear. Such actions can cause data loss or prolong partition unavailability. Use controlled recovery and reassignment procedures.

### 8.1. When may lowering min.insync.replicas be considered?

Emergencies can arise where a service must restore writes before all replicas recover. Lowering minimum ISR is a decision to reduce data protection because brokers can then accept writes with fewer replicas.

Before considering this:

- Identify the affected topics and partitions.
- Verify how many replicas are genuinely healthy and whether leaders are stable.
- Assess data classification, data loss tolerance, and SLA/RPO.
- Obtain approval from the service owner or reliability owner.
- Scope the change strictly to necessary topics and set a deadline to restore the config.
- Monitor closely until ISR returns to normal, then restore the original minimum ISR.

Never lower `min.insync.replicas` across the entire cluster blindly. Never switch to `acks=1` without understanding the impact. A config change can make producers succeed again while weakening the durability policy designed to prevent data loss.

## 9. Example scenarios

### 9.1. RF=3, min ISR=2, one broker fails

The topic has three replicas across three brokers. Broker 3 fails, leaving two replicas in the ISR. Producers using `acks=all` can still write because ISR equals the minimum threshold.

Action: restore broker 3 so its replica rejoins the ISR; monitor `IsrExpandsPerSec` and `UnderReplicatedPartitions`. Do not lower minimum ISR in this scenario.

### 9.2. RF=3, min ISR=2, two brokers out of sync

Only the leader remains in the ISR. Producers receive `NotEnoughReplicasException`. Kafka rejects writes to uphold the durability policy.

Action: find the disconnected or lagging follower brokers, inspect disk/network, and recover at least one follower so ISR reaches two. Once ISR returns to threshold, producer retries can succeed within delivery timeout.

### 9.3. ISR drops after leader append

The producer sends a record while ISR satisfies the condition. The leader appends the record, but a follower leaves the ISR before acknowledgement completes. The broker may return `NotEnoughReplicasAfterAppendException`.

Action: let the Kafka client retry per producer policy; do not immediately emit a new event via a second `send()` call before checking the first send's status. With an idempotent producer, internal retries of the same batch are recognized by sequence. If the final result fails and the application must resend, use a stable event ID alongside deduplication.

### 9.4. min ISR set equal to replication factor

Topic RF=3, min ISR=3. This configuration requires all three replicas to stay in the ISR at all times for `acks=all` writes. As soon as a single follower leaves the ISR, producers cannot write.

This setting may suit strict durability requirements in a healthy topology, but write availability is lower than RF=3/min ISR=2. Evaluate capacity, failure domains, and recovery speed before setting this threshold.

### 9.5. Producer succeeds but consumer lag grows

If producer publishes are acknowledged, that only indicates Kafka accepted writes under current config. Growing consumer lag is a downstream processing issue. Do not attribute every Kafka issue to `NotEnoughReplicas`.

Inspect consumer groups, processing throughput, downstream latency, rebalances, and offset commit errors. Publish SLIs and processing SLIs must be tracked separately.

## 10. Alerting and operational runbooks

Alert early before producers begin failing. A well-rounded alert set may include:

- Sustained `UnderReplicatedPartitions > 0` on critical topics.
- Abnormal spikes in `IsrShrinksPerSec`.
- Partition ISR falling below `min.insync.replicas`.
- `OfflinePartitionsCount > 0`.
- Concurrent rise in producer retry rate or error rate.
- Publish success dropping or p99 latency breaching SLO.
- Disk, network, or request queues approaching capacity limits.

ISR-based alerts should be evaluated against the topic's effective minimum ISR. Looking solely at `UnderReplicatedPartitions` is not enough to tell whether producers can keep writing: a partition may be under-replicated yet still have enough ISR to meet the minimum, or have only one replica left and already be below threshold.

A concise on-call runbook should document:

1. Affected cluster name, topic, partition, and producer service.
2. Commands to inspect leaders, replicas, and ISRs.
3. Effective `min.insync.replicas` value.
4. Broker logs and dashboards to check.
5. Owners for broker, network, storage, and producer.
6. Replica recovery or reassignment procedure.
7. Criteria confirming the incident is resolved.
8. Approval workflow if changing minimum ISR is necessary.
9. How to identify and handle failed or uncertain-outcome publish events.

## 11. Common mistakes

**Immediately switching to `acks=1`.** This relaxes acknowledgement conditions and can mask unhealthy replicas. First locate and restore replicas.

**Lowering `min.insync.replicas` without assessing risk.** A lower threshold can lose acknowledged data if the leader fails before another copy receives the record.

**Confusing replication factor with ISR.** Three assigned replicas does not mean all three are in sync. Check the actual ISR list.

**Thinking higher retries will fix the broker.** Retries help survive brief glitches. If ISR remains below threshold, the producer will keep retrying until delivery timeout and then fail.

**Retrying with a new send call when the prior outcome is uncertain.** Post-append errors can leave records on the leader. A new application-level send can create business duplicates.

**Putting min ISR in producer properties.** It is a broker/topic setting. Producers cannot unilaterally change the cluster's replication requirements.

**Checking only application logs.** Root causes often sit in brokers, replica fetchers, disks, network, or partition assignments. Correlate producer logs with broker logs and ISRs.

**Treating zero producer errors as end of incident.** Verify unsent events, backlogs, business retries, and consumers to ensure the business flow has recovered.

## 12. Incident checklist

- [ ] Identify topic, partition, producer, and error start time.
- [ ] Check leader, replica list, and ISR.
- [ ] Retrieve the topic's effective `min.insync.replicas` value.
- [ ] Confirm whether the producer uses `acks=all`.
- [ ] Distinguish `NotEnoughReplicasException` from `NotEnoughReplicasAfterAppendException`.
- [ ] Check broker logs, replica fetchers, disks, network, and request queues.
- [ ] Monitor `UnderReplicatedPartitions`, `OfflinePartitionsCount`, and ISR shrink/expand.
- [ ] Restore replicas and confirm ISR meets the threshold.
- [ ] Verify producer retry/error rates and publish SLOs after recovery.
- [ ] Handle failed or uncertain events via event ID/outbox/deduplication.
- [ ] Alter min ISR only after durability assessment, approval, and rollback plan.
- [ ] Record root cause, impact duration, and preventive actions.

## 13. Operational conclusion

`NotEnoughReplicas` indicates Kafka lacks enough synchronized replicas to satisfy the write policy under `acks=all`. The durable fix is to locate partitions missing ISR, determine why replicas left ISR, restore the broker or replication path, and confirm ISR meets the minimum before declaring the producer healthy.

In Spring Kafka, configure producer retries and idempotence appropriately, observe exceptions from `KafkaTemplate` futures, and avoid issuing a new business send when the previous attempt's outcome is uncertain. `min.insync.replicas` must be managed at the broker/topic level as an intentional trade-off between availability and durability.

