# acks and Write Acknowledgement Levels

In Kafka, a producer sends records to the partition's broker leader and receives responses about the write result. The **acks** property determines what level of broker acknowledgement the producer requires before considering a send successful. This is a core choice in the **Durable Producer** chapter because it directly affects broker fault tolerance, record loss risk, and write latency.

Choosing an ACK level is not merely choosing between fast and safe. You must understand when an ACK is sent, which replicas must participate, what conditions cause a broker to reject a write, and what the application will do when no response arrives. A sound configuration must coordinate **acks**, replication factor, **min.insync.replicas**, ISR, idempotent producer, timeouts, and application error handling.

## 1. What Is an ACK in the Kafka Write Flow?

Each topic is divided into partitions. Each partition has one leader and may have follower replicas on other brokers. The producer sends records to the target partition's leader. The leader writes the record to its log and followers fetch data from the leader to maintain copies.

High-level flow:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Partition leader
    participant F1 as Follower 1
    participant F2 as Follower 2
    P->>L: Produce record
    L->>L: Append to log
    F1->>L: Fetch data
    L-->>F1: New record
    F2->>L: Fetch data
    L-->>F2: New record
    L-->>P: ACK per acks configuration
~~~

The diagram illustrates replication; in reality, followers actively fetch data from the leader. The producer does not send a separate write to each replica. The producer sends the request to the leader, and Kafka manages replication.

An ACK is the broker's response to a write request. From the producer's perspective, a successful ACK means the request satisfied the configured acknowledgement level. It does not mean every configured replica has received the data, nor does it mean every copy has been physically flushed to storage devices.

Steps to distinguish:

1. The producer serializes the record, determines the partition, and sends the request.
2. The leader receives the request and appends the record to its log.
3. Followers in the ISR replicate data from the leader.
4. The leader returns a response according to the ACK policy.
5. The producer receives the response and completes the corresponding future/callback.

If the connection drops after the leader writes the record but before the producer receives the ACK, the producer cannot know whether the request was written. This is an **ambiguous outcome** situation. Retrying can create duplicate records if idempotence or proper deduplication mechanisms are absent.

## 2. The Three acks Levels

Kafka producers support three main acknowledgement levels: **acks=0**, **acks=1**, and **acks=all**. The value **acks=-1** is an alias for **acks=all**.

### 2.1 acks=0 — Do Not Wait for Acknowledgement

With **acks=0**, the producer sends requests without waiting for the broker to return an ACK. The producer can continue sending quickly because it does not wait for write responses.

Characteristics:

- The producer has no confirmation that the broker received or appended the record.
- If the request is lost in transit, the broker is unavailable, or the broker rejects the write, the producer has no ACK to accurately detect the outcome.
- Producer-side retries cannot rely on broker error responses because the producer does not wait for a response.
- Latency observed at the producer is lower, but reliability of write outcomes is the lowest of the three levels.

**acks=0** is only suitable for data that can be lost, regenerated, or is non-critical to business operations, such as certain telemetry streams where sample loss is acceptable. Do not use it for orders, payments, transaction states, business commands, or events that require durable storage.

### 2.2 acks=1 — Leader Acknowledgement

With **acks=1**, the producer receives an ACK after the leader appends the record to its local log. The leader does not need to wait for followers in the ISR to confirm that record before responding.

Characteristics:

- The producer knows the leader received and appended the record.
- Latency is typically lower than **acks=all**, especially when followers have replication lag.
- If the leader fails after sending the ACK but before followers replicate the record, the record may no longer exist on an eligible successor replica.
- This acknowledgement level does not protect against all sudden leader-loss scenarios.

For example, a partition has leader A and followers B, C. The producer sends a record to A. A appends the record and immediately returns an ACK. Before B and C replicate the record, A loses power. If B is elected as the new leader and does not yet have that record, a record the producer considered successfully sent can disappear from the served log.

Therefore, **acks=1** is better suited for data that can tolerate a small risk of record loss in exchange for lower latency. Do not assume an ACK from the leader means the record already exists on multiple brokers.

### 2.3 acks=all — Wait for ISR Acknowledgement

With **acks=all**, the leader waits for replicas currently in the ISR (in-sync replicas) set to confirm they have caught up to the record before returning an ACK. This is the level typically chosen for critical business data.

Characteristics:

- The producer receives an ACK after the record is appended and ISR replicas satisfy the acknowledgement condition.
- Better protection when the leader suffers a failure after writing.
- Latency may increase due to waiting for replication.
- If the ISR count is lower than **min.insync.replicas**, the broker rejects the write request instead of accepting it at a replication level insufficient under policy.

Important point: **acks=all does not mean every replica declared by the replication factor must acknowledge.** It waits for replicas currently in the ISR at write time. Replicas removed from the ISR due to lag or disconnection are not in the set required to ACK that request.

This means actual protection depends on how many ISR members remain active. A topic with replication factor 3 that only has 1 ISR left no longer has the same redundancy as when all 3 ISRs are present. You must configure **min.insync.replicas** to define the minimum threshold at which the broker accepts writes.

## 3. Comparing acks=0, acks=1, and acks=all

| Property | acks=0 | acks=1 | acks=all |
|---|---|---|---|
| Wait for broker ACK | No | Yes | Yes |
| Success response condition | No ACK from broker | Leader appends record | Replicas currently in ISR satisfy acknowledgement |
| Depends on followers before ACK | No | No | Yes |
| Ability to detect write errors via broker response | Very limited | Yes | Yes |
| Risk if leader fails right after ACK | No confirmation to evaluate | May lose unreplicated records | Lower when ISR is sufficient and configured properly |
| Write latency | Usually lowest | Usually low | Can be higher |
| Suitable for | Data that can be lost | Data less sensitive to record loss | Data requiring high durability |

This table describes general trends. Actual latency depends on load, batch size, network, broker disk, ISR count, and broker placement. You cannot deduce a fixed latency number solely from the ACK value.

## 4. ISR, Replication Factor, and min.insync.replicas

To properly understand **acks=all**, three concepts must be distinguished.

### 4.1 Replication factor

Replication factor (RF) is the number of replicas configured per partition, including the leader. For example, RF=3 means a partition has one leader and two follower replicas.

RF provides redundancy when a broker fails. However, having three replicas does not mean all three always stay caught up with each other. Followers can lag or lose connectivity.

Replicas of the same partition should be distributed across independent brokers and failure domains. If all three replicas sit on a single physical node or a single AZ, an outage of that node/AZ can lose all copies.

### 4.2 ISR — in-sync replicas

ISR is the set of replicas currently considered caught up with the leader according to Kafka's replication mechanism and configured thresholds. ISR includes the leader and qualifying followers.

Example:

- RF=3: partition has leader A, follower B, and follower C.
- Initially ISR = {A, B, C}.
- B lags beyond the threshold or disconnects, so Kafka removes B from the ISR.
- ISR is now {A, C}.
- If C also leaves the ISR, ISR only contains {A}.

As the ISR count drops, the partition's fault tolerance decreases. A partition with only the leader in the ISR may still serve some requests if policy permits, but it no longer has an up-to-date copy to safely take over if the leader fails.

ISR can change over time. Therefore, evaluating durability must be based on the ISR state at write time, not just looking at the replication factor in topic configuration.

### 4.3 min.insync.replicas

**min.insync.replicas** sets the minimum number of replicas that must be in the ISR for the broker to accept writes with **acks=all**.

Suppose:

- Replication factor = 3.
- min.insync.replicas = 2.
- Producer uses acks=all.

Scenarios:

| Current ISR | Broker handling of write with acks=all |
|---|---|
| 3 replicas | Allows write; waits for all 3 ISRs to acknowledge |
| 2 replicas | Allows write; waits for both 2 ISRs to acknowledge |
| 1 replica | Rejects write because it is below min ISR |

This configuration creates a clear trade-off: when the cluster degrades below the threshold, Kafka rejects writes to protect the committed durability level. The application must accept temporary write failures, perform bounded retries, and raise operational alerts.

Without setting an appropriate min ISR, **acks=all** can still accept writes when the ISR is down to a single replica. In that case, the name "all" does not guarantee multiple copies; it merely means all replicas currently remaining in the ISR acknowledged.

### 4.4 Choosing RF and min ISR

A common configuration for critical data is:

- RF=3.
- min.insync.replicas=2.
- Producer uses acks=all.

This configuration permits writes when at least two ISRs remain, and requests are acknowledged by all current ISRs. If one replica falls behind, the partition can continue accepting writes with two ISRs. If only one ISR remains, the broker rejects writes until replication recovers.

This is not the optimal configuration for every system. Choosing RF and min ISR requires considering:

- Maximum data loss acceptable to the business.
- Number of brokers and physical failure domains.
- Load capacity when one broker/AZ is lost.
- Replication latency between brokers.
- Availability requirements: whether the system accepts pausing writes to preserve durability.
- Storage capacity and replication cost.

RF=3 is only meaningful when the three replicas are genuinely distributed independently. Verify rack awareness or the corresponding placement mechanism in the deployment environment.

## 5. What Happens When a Broker or Replica Fails?

Several typical scenarios illustrate the relationship between ACK and cluster state.

### 5.1 Losing One Follower

Suppose RF=3, initial ISR has A, B, C. Broker B disconnects and is removed from the ISR, leaving A and C in the ISR.

With min ISR=2 and acks=all:

- The broker can still accept writes.
- Leader A waits for A and C to fulfill replication.
- Redundancy drops from three replicas to two.
- An alert should fire because the partition is missing one replica relative to its replication factor.

When B recovers and catches up to the leader, B can be re-added to the ISR. Do not rely solely on broker "online" status; verify partition replicas have caught up and ISR has recovered.

### 5.2 Losing the Leader

If A is the leader and fails, Kafka must elect a new leader from eligible replicas. If B or C remains in the ISR, one of those replicas can become leader.

With acks=all and properly designed min ISR, ACKed records have a higher probability of being preserved because they were confirmed by ISRs. However, the ability to continue accepting writes depends on the remaining ISR count after leader election and min ISR.

If no eligible replica exists, the partition may have no leader and be unable to serve writes until recovery. This is the trade-off between consistency/durability and availability.

### 5.3 ISR Drops Below min ISR

Suppose RF=3, min ISR=2, yet currently ISR only has one replica. When a producer sends with acks=all, the broker rejects writes because the minimum threshold is not met.

This is data-protection behavior. Do not immediately lower min ISR or switch to acks=1 just to eliminate producer errors. Doing so can turn a replication-degradation warning into actual data loss risk.

The handling sequence should be:

1. Identify the missing partition and broker replica.
2. Check brokers, disks, network, and follower fetch status.
3. Restore the replica so ISR reaches the threshold.
4. Monitor producer errors and replication metrics until stable.
5. Only alter policy after evaluating durability requirements and making an explicit operational decision.

### 5.4 Leader Returns ACK Then Crashes

With acks=1, the leader can ACK before followers replicate the record. If the leader fails immediately afterward, the record may be missing from the replica elected as the new leader.

With acks=all, the leader only ACKs after replicas in the ISR confirm. This reduces the risk of losing ACKed records when a broker fails. Actual protection still depends on ISR, leader election configuration, and whether replicas truly reside in independent failure domains.

### 5.5 Losing Multiple Brokers or an Entire AZ

If multiple replicas of the same partition fail simultaneously, ISR may drop below min ISR or no eligible leader replica may remain. Producers will receive write errors or the partition will become unavailable.

If replicas are distributed across multiple AZs and one AZ goes down, the remaining AZs can continue serving if sufficient ISR and capacity remain. If all replicas sit inside the failed AZ, RF=3 offers no protection against that outage.

## 6. ACK Does Not Equal fsync or Protection Against Every Failure

Understanding the limits of ACK avoids over-interpreting its guarantees.

**acks=all** confirms replication under the Kafka protocol. It does not mean the broker performs a mandatory fsync to storage devices for every record before responding. Kafka leverages the OS page cache and OS flushing mechanisms to optimize performance. Therefore, an ACK must not be interpreted as "every copy has been physically written to disk in a way immune to all power failures."

Durability also depends on:

- ISR count and replication quality.
- Independence of brokers and failure domains.
- Leader election configuration, specifically whether electing out-of-sync replicas is permitted.
- Filesystem, disk controller, and storage infrastructure health.
- Retention settings and topic administrative operations.
- Cluster recovery capability and backup/DR.

### 6.1 Unclean leader election

When all replicas in the ISR are unavailable, Kafka may have an option regarding whether to allow a replica outside the ISR to become leader. Allowing unclean leader election can restore a partition leader sooner, but an out-of-sync replica may be missing records previously ACKed by the old leader.

Disabling unclean leader election prevents electing an out-of-sync replica as leader, thereby prioritizing preservation of replicated data. In return, the partition may remain unavailable until an eligible replica recovers.

This is a cluster-level durability/availability decision. Understand the Kafka version, cluster configuration, and runbook before changing it.

## 7. Combining acks with Idempotent Producer and Retries

ACK determines the broker's acknowledgement level. Idempotence solves a different problem: resending requests when the previous send's outcome is ambiguous.

Example:

1. Producer sends a record to the leader.
2. Broker writes the record and sends an ACK.
3. Network disconnects before the ACK reaches the producer.
4. Producer sees a timeout and retries sending.
5. Without idempotence, the retry can create another record identical to the previous one.

An idempotent producer uses a producer identity and sequence number so the broker recognizes retries from the same producer session and deduplicates retries at the protocol layer.

To use idempotence, compatible settings are required. In modern Kafka clients, idempotence requires **acks=all**; retry and max in-flight request settings must also satisfy client version conditions. Enable it explicitly and inspect startup/config logs rather than relying on defaults that vary across versions.

Example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

**delivery.timeout.ms** limits the total time the producer attempts to complete sending, including request waits and retries. Once expired, the application receives a send error. The value must suit the SLA, request timeout, broker latency, and expected recovery time.

An idempotent producer does not replace business-level idempotency. If the application restarts and initiates a new send for the same business command, Kafka may treat it as a new record. Include a stable event id or business key so consumers can deduplicate when needed.

### 7.1 Retries Are Not a Fix for Durability Errors

Retries help overcome transient errors such as leader elections, network interruptions, or broker restarts. However, retries cannot fix a misconfigured replication policy or a cluster missing multiple replicas for an extended period.

Avoid:

- Infinite retries causing the producer buffer to fill up.
- Excessively long timeouts holding resources and masking incidents.
- Multiple retry layers multiplying call counts: application retries, Kafka producer retries, and downstream retries.
- Simultaneous retries without backoff/jitter overloading the cluster right as it recovers.

When a producer fails due to ISR below min ISR, retries only succeed after replication recovers or policy changes. Applications should implement backoff, overall timeouts, and error-type-based alerts.

## 8. Configuring acks in Spring Kafka

Spring Boot provides properties to configure producer ACKs. The example below uses a common durable configuration for critical data:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Meaning:

- **bootstrap-servers**: broker addresses used to discover cluster metadata.
- **acks: all**: producer requires acknowledgement from the ISR.
- **enable.idempotence: true**: enables idempotent producer to prevent duplicates from retries within the same producer session.
- **delivery.timeout.ms**: caps total send time.
- **request.timeout.ms**: wait time for a response to one request.

Timeout values are only examples. Do not copy them verbatim into every system. Measure latency, determine SLA, record sizes, and expected broker recovery times, then tune accordingly.

### 8.1 Topic and Broker Configuration

**min.insync.replicas** is a topic or broker configuration, not a producer property. Example topic configuration:

~~~properties
replication.factor=3
min.insync.replicas=2
~~~

In real deployments, replication factor is typically specified at topic creation or via admin tools. **min.insync.replicas** can be set at the topic or broker level depending on cluster administration practices. Verify the effective topic configuration, as broker-level defaults may differ from topic overrides.

A producer cannot raise min ISR itself by setting a property in the application. Changing replication policies must be administered on the Kafka side.

### 8.2 ProducerFactory and KafkaTemplate

If configuring in Java instead of Spring Boot YAML, producer properties can be passed into ProducerFactory:

~~~java
@Bean
ProducerFactory<String, OrderCreated> producerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
              StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
              JsonSerializer.class);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);

    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

The example focuses on properties related to ACK and durability. Real applications must configure serializers, security, schemas, transactions, and error observability suitable for the environment.

### 8.3 Handling Send Results in the Application

With KafkaTemplate, applications can observe send results asynchronously. Never ignore the future when business logic needs to know whether the broker acknowledged the record.

Example:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka publish failed for orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Published orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

A success callback means the producer received a successful response under the configured ACK policy. Error callbacks must be recorded and handled per business rules. If sending fails, the application must decide whether to persist for later retry, return an error to the caller, or use transactional outbox.

Do not just log an error and drop the record if it is a mandatory event to emit. For critical business flows, transactional outbox typically ensures publish intent is not lost once the database commits.

## 9. Reading Producer Errors Related to ACK

Common errors:

| Error or symptom | Possible meaning | Investigation direction |
|---|---|---|
| NotEnoughReplicasException | ISR lower than min ISR when broker processed the request | Check ISR, broker replicas, network, and effective min ISR |
| NotEnoughReplicasAfterAppendException | Record was appended but insufficient replicas satisfied conditions afterward | Check ISR changes during the write and partition state |
| TimeoutException | Producer did not complete the request within the time limit | Check broker latency, network, request timeout, delivery timeout, and retries |
| NetworkException | Broker connection interrupted | Check DNS, routing, TLS, firewall, and broker availability |
| NotLeaderOrFollowerException | Request reached a broker no longer leader or unsuitable for the role | Check metadata refresh, leader election, and broker state |
| RecordTooLargeException | Record exceeds size limit | Check producer max request size and broker/topic limits |

Exception names may differ by context or client version, and some errors are wrapped inside a general exception. Read the root cause, topic, partition, and request metadata rather than relying only on the outermost message.

**NotEnoughReplicas** does not necessarily mean a broker has completely crashed. The broker may still be running while follower lag or disconnection reduced the ISR. That is why ISR and broker health must be observed together.

## 10. ACK Selection Matrix by Business Need

| Data type | Typical ACK level considered | Rationale and conditions |
|---|---|---|
| Metrics/telemetry where sample loss is tolerable | acks=0 or acks=1 | Only when the system tolerates data loss and can re-aggregate |
| Non-critical application logs | acks=1 or acks=all | Depends on retention needs and tolerance for log loss |
| Standard business events | acks=all | Should pair with appropriate RF, min ISR, and idempotence |
| Orders, payments, account states | acks=all | Requires high durability, business idempotency, and appropriate outbox/transaction flow |
| Events regenerable from another source | acks=1 or acks=all | Decide based on regeneration cost and impact of loss |

There is no single right ACK level for all topics. One cluster may serve multiple data tiers with differing requirements, but policies must be explicitly governed per topic and business domain. Avoid letting default settings inadvertently dictate durability for critical data.

## 11. Latency, Throughput, and Batching

The ACK level affects producer latency. With acks=all, the producer may have to wait for the slowest follower in the ISR. When a follower experiences high network latency or disk I/O, response times can increase.

However, do not trade away durability just to save a few milliseconds if data cannot be regenerated. Before changing ACK, check:

- Batch size and linger time.
- Compression.
- Partition count and key distribution.
- Broker request latency.
- Network round trip between brokers.
- Follower fetch lag and ISR churn.
- Disk I/O and request handler saturation.
- Number of in-flight requests and producer batching capability.

Batching and compression can improve throughput while keeping acks=all. Optimization should start from measured bottlenecks. If latency increases due to follower lag, look for the root cause in brokers/network/disk instead of automatically downgrading ACK.

## 12. Observing Durability and Alerting

Producer metrics only reflect one side. Combine metrics from the producer, broker, and partitions.

**Producer side:**

- Record send rate and record error rate.
- Request latency and request size.
- Retry rate and retried request count.
- Record queue time and buffer available bytes.
- Timeout or send error counts.
- Send success rate per topic.

**Kafka side:**

- Under-replicated partitions.
- Under-min-ISR partitions.
- Offline partitions.
- ISR shrink/expand rate.
- Leader election rate and partition leader distribution.
- Produce request latency, request handler saturation.
- Follower fetch lag, disk usage, and network throughput.

**Application side:**

- Number of events pending emission that have not yet been published.
- Outbox backlog and age of the oldest outbox row.
- Event send retry count.
- Final failed event count and replayed event count.
- Correlation/event id to reconcile database with Kafka.

Set alerts for **under-min-ISR** and **under-replicated partitions**. These two signals mean different things: a partition can be missing a replica while still meeting min ISR for writes; or it can drop below min ISR and cause producer writes to be rejected. Monitor both.

A producer still succeeding in sending records does not prove the entire topic has full replication. Conversely, a producer receiving errors due to min ISR may mean the system is protecting durability as designed. Inspect producer errors alongside ISR state before deciding on action.

## 13. Procedure When Producer Receives ACK Errors

When write errors related to replicas or ACKs occur, proceed in order:

1. Identify the topic, partition, producer client, error timestamp, and root exception type.
2. Check effective producer config: acks, idempotence, retries, request timeout, and delivery timeout.
3. Check the partition leader and current ISR list.
4. Check which broker is disconnected, which follower is lagging, and whether any broker is restarting or has overloaded disk/network.
5. Verify effective min.insync.replicas on the topic/broker and the replication factor.
6. Restore the broker or network so followers catch up, monitoring ISR recovery.
7. Confirm producer retries succeeded or the application persisted events for resending.
8. Reconcile event id and offset to determine whether the record was written before the timeout.
9. After recovery, verify under-replicated and under-min-ISR partitions have returned to normal thresholds.

Do not delete topics, reduce replication factor, or lower min ISR as an initial reflex. Those actions can weaken durability or cause data loss. If the business must keep accepting requests while Kafka cannot meet write thresholds, consider storing events in an outbox or another pre-designed durable queue.

## 14. Testing Write Acknowledgement Levels

Test in staging or a test cluster with a topology similar to production. Useful scenarios include:

- Send records with RF=3, min ISR=2, and acks=all; verify writes succeed when ISR has 2 or 3 replicas.
- Cause one follower to leave ISR; verify the producer can still write while min ISR is satisfied and observe under-replicated partitions.
- Cause ISR to drop below min ISR; verify the broker rejects writes with acks=all and the application handles errors gracefully.
- Restore the follower; verify the replica catches up and ISR returns.
- Stop the leader; verify leader election, producer retries, and that ACKed records remain readable after recovery.
- Sever the network after the broker may have written but before the producer receives the ACK; verify the idempotent producer limits duplicates from retries within the same session.
- Test outbox/replay to verify business events are not lost when Kafka temporarily cannot accept writes.

Each test should document hypothesis, stop condition, record id, topic/partition, expected result, and observed data. Never run fault injection in production without scope, approval, and safe stop mechanisms.

## 15. Misconceptions to Avoid

**"acks=all means every broker in the cluster acknowledges."** False. Only replicas in the target partition's ISR participate in acknowledgement.

**"Replication factor=3 guarantees three synchronous copies at all times."** False. RF is the configured replica count; ISR can shrink due to replica lag or disconnection.

**"acks=all automatically protects when ISR drops to one replica."** Not necessarily. If min ISR allows one replica, the broker can still accept writes with only one ISR. You must set an appropriate min.insync.replicas.

**"A successful ACK means the record has been fsynced to every disk."** False. ACK reflects Kafka's replication condition; it is not a synchronous fsync guarantee per record across all devices.

**"acks=all guarantees exactly-once."** False. ACK concerns write acknowledgement. Exactly-once requires an idempotent producer or transactions within their applicable scope; side effects outside Kafka still need idempotency or coordination mechanisms.

**"If the producer times out, the record was definitely not written."** False. The broker may have appended the record while the response was lost on the network. Handle ambiguous outcomes and prevent duplicates.

**"If the producer reports NotEnoughReplicas, just switch to acks=1."** That change lowers the acknowledgement level. First restore ISR and evaluate durability requirements. Only change policy once risks are understood and an operational decision is made.

## 16. Configuration and Operations Checklist

**Durability design**

- [ ] Each topic is classified by criticality and data regenerability.
- [ ] Replication factor matches broker count and physical failure domains.
- [ ] Replicas of the same partition are distributed across independent brokers/racks/AZs.
- [ ] min.insync.replicas is explicitly set according to topic policy.
- [ ] Producers use acks=all for data requiring high durability.
- [ ] Unclean leader election is evaluated against the durability vs. availability trade-off.

**Producer**

- [ ] Idempotent producer is enabled for flows needing duplicate protection on retry.
- [ ] Timeouts and retries have bounds aligned with SLA.
- [ ] Send futures/callbacks are observed; errors are not ignored.
- [ ] Critical events have a stable event id or business key.
- [ ] An outbox or durable persistence mechanism exists when Kafka temporarily rejects writes.

**Observability and recovery**

- [ ] Monitor ISR, under-replicated, and under-min-ISR partitions.
- [ ] Monitor producer errors, retries, timeouts, and request latency.
- [ ] Runbooks exist for handling NotEnoughReplicas and leader loss.
- [ ] Procedures exist to reconcile event id, topic, partition, and offset.
- [ ] Follower loss, leader loss, and below-threshold ISR have been rehearsed in an appropriate environment.

The ACK level is part of the durability contract between the producer and Kafka. For critical data, configuring **acks=all** together with replication factor, **min.insync.replicas**, independently placed ISRs, and an idempotent producer builds a durable write foundation. When the cluster can no longer meet the replication threshold, rejecting writes can be the right behavior to protect data; applications need timeouts, retries, observability, and mechanisms to persist publish intent for controlled recovery.

