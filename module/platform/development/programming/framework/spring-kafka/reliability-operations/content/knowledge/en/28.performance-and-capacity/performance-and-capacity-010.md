# Bottlenecks from DLT Publishing

## Goal

In Spring Kafka, a Dead Letter Topic (DLT) is where records are stored when they cannot be processed successfully after the retry policy or are classified as non-retryable errors. A DLT preserves failed data for investigation and replay, yet the publishing path to the DLT is also part of the consumption pipeline.

A DLT publishing bottleneck occurs when the consumer cannot forward failed records to the DLT fast enough or when sending fails. If the error handler must wait for the send result, the listener thread is held up; if send errors are not handled properly, a record may be marked recovered even though it was not safely persisted. Both situations impact reliability and throughput.

This lesson focuses on the path from listener to DLT: error generation rate, recoverer configuration, Kafka producer, target topic, and broker capacity.

## Processing Flow and Potential Bottleneck Points

A common flow with **DefaultErrorHandler** and **DeadLetterPublishingRecoverer**:

~~~text
Kafka source topic
       |
       v
Listener processes record
       |
       +---- success -------------------------> commit offset
       |
       +---- failure
                |
                v
          retry + backoff
                |
                +---- retry succeeds ---------> commit offset
                |
                +---- retries exhausted / non-retryable
                              |
                              v
                 DeadLetterPublishingRecoverer
                              |
                              v
                       KafkaTemplate
                              |
                              v
                         Broker
                              |
                              v
                         DLT topic
~~~

The publish path can slow down at several points: the producer waiting on metadata or buffers, the broker processing requests slowly, missing target partitions, insufficient ISR, ACL denials, or a serializer unable to convert the payload. When the recoverer waits for send confirmation, that wait sits directly on the consumer's critical processing path.

Distinguish three kinds of latency:

- **Slow listener:** high business processing duration before the record is routed to the DLT.
- **Slow DLT publish:** high duration from when the recoverer sends until the producer receives a successful send result.
- **Slow DLT consumer:** records have already been written to the DLT, yet the system reading and processing the DLT falls behind.

High DLT consumer lag does not automatically mean publishing is bottlenecked. The producer can still write normally while the DLT consumer falls behind; only when the broker comes under pressure on disk space, quotas, replication, or I/O can that backlog indirectly affect the write path.

## Operational Symptoms

Symptoms that commonly appear together:

- Source topic consumer lag climbs even though processing time for valid records has not changed.
- The rate of records routed to the DLT spikes abruptly; DLT ingress rises far above baseline.
- Listener threads spend substantial time inside the error handler or waiting for DLT send results.
- Producer metrics show rising **record-error-rate**, **record-retry-rate**, request latency, or buffer pool wait times.
- Logs report send errors such as **TimeoutException**, **NotEnoughReplicas**, **UnknownTopicOrPartition**, **TopicAuthorizationException**, **RecordTooLargeException**, or serialization errors.
- The DLT topic has partitions missing a leader, insufficient ISR, or one partition receiving unusually high traffic.

A single symptom alone is inconclusive. For example, rising source consumer lag can also stem from slow listener processing, rebalances, slow broker reads, or failing downstream dependencies. Correlate the timestamp of lag growth with DLT publish timing and producer metrics.

## Common Root Causes

### 1. Sudden Spike in Failing Records

A data defect or contract change can cause most records to fail together—for example, an incompatible new schema, a downed downstream service, out-of-range input values, or a bug deployed to the listener.

Retries multiply processing attempts before records route to the DLT. If retries are excessive, backoff is too short, or the failure is systemic, the consumer keeps burning resources while the DLT still receives a heavy stream of records. This is a retry storm.

Measure the failed-record ratio against total incoming records, average retry attempts, and DLT ingress rate. If error rates spike alongside a deployment or data change, fix the root cause before adding capacity.

### 2. DLT Topic Missing Partitions or Unavailable

The default **DeadLetterPublishingRecoverer** configuration typically builds the destination name by appending the **.DLT** suffix and preserving the source partition. If the source topic has 12 partitions, the DLT needs matching partitions when using this mapping.

Failure scenarios:

- The DLT was not created in an environment where auto topic creation is disabled.
- The DLT has fewer partitions than the source topic.
- Target partitions lack a leader or replicas have fallen out of ISR.
- Topic name or partition resolver is misconfigured.
- The producer lacks **WRITE** permission on the DLT or permissions needed to fetch metadata.
- Retention, quotas, or broker disk limits prevent the broker from accepting more data.

Pre-create DLT topics before consumers start and manage topics through infrastructure workflows. Never rely on auto-creation for production error handling.

### 3. Kafka Producer Experiencing Backpressure

DLT publishing uses a Kafka producer via **KafkaTemplate**. The producer can slow down when:

- Error record rate exceeds the throughput the producer or broker can currently serve.
- Producer buffers fill up; **send()** calls may block on buffers up to **max.block.ms**.
- Topic or partition metadata is not yet ready.
- Brokers respond slowly, retries climb, or requests time out frequently.
- One partition runs hot due to key distribution or source-to-DLT partition mapping.
- Producer batch/compression settings poorly match record size and rate.

Settings typically inspected include **batch.size**, **linger.ms**, **compression.type**, **buffer.memory**, **max.block.ms**, **request.timeout.ms**, **delivery.timeout.ms**, **acks**, and **retries**. Do not raise or lower these values wholesale: base changes on metrics and durability requirements.

### 4. Broker or Cluster Out of Capacity

The DLT usually shares the Kafka cluster with the source topic. When the cluster is already near CPU, disk I/O, network, request handler, or quota limits, the DLT producer experiences the same pressure.

**acks=all** combined with **min.insync.replicas** protects durability, yet can cause publishes to fail or stall when ISR is insufficient. Lowering **acks** or **min.insync.replicas** to hide symptoms can weaken data protection. Only alter durability after thoroughly evaluating risks and system requirements.

### 5. Oversized Payloads, Serializers, and Headers

The DLT must preserve original data for investigation or replay. However, a failing payload may be incompatible with the DLT producer's serializer.

A common case is deserialization failure: the listener lacks a valid Java object yet still needs to send raw bytes to the DLT. Use a deserializer/serializer setup supporting both deserialized types and raw **byte[]** from failed records, typically via **ErrorHandlingDeserializer** paired with an appropriate DLT serializer.

Beyond the payload, headers containing exception messages or stack traces can enlarge records substantially. If a record exceeds producer **max.request.size** or broker message limits, DLT publishing fails with a size error. Keep diagnostic headers bounded in size and check both producer and broker limits.

### 6. Consumer Threads Held Waiting for Publish

**KafkaTemplate.send()** has an asynchronous API, yet the recoverer can be configured to await the send result to confirm the record entered the DLT. For instance, enabling **setFailIfSendResultIsError(true)** propagates send failures back to the error handler. This is a valuable reliability choice, yet when brokers are slow, listener threads are held longer.

If every listener thread waits on a slow publish, consumer throughput drops and source lag climbs. Raising concurrency does not always help: if the producer or broker is the bottleneck, adding listener threads only creates more requests competing for the same resource.

## Step-by-Step Investigation

### Step 1: Establish Timing and Scope

Record the incident start time, consumer group, source topic, DLT topic, affected partition count, and most recent deployment or configuration change. Compare against pre-incident baselines.

Determine whether the issue affects all partitions or only a few. If only one partition has abnormal lag or DLT ingress, inspect key distribution, leaders, and partition mapping before scaling cluster-wide capacity.

### Step 2: Inspect Recoverer and Producer Errors

Check logs around the time records route to the DLT. Classify errors:

| Error or Symptom | What to Check |
|---|---|
| **TimeoutException** | Broker latency, network, metadata, buffers, and producer timeouts |
| **NotEnoughReplicas** | ISR, replication factor, and **min.insync.replicas** |
| **UnknownTopicOrPartition** | DLT name, topic existence, and target partitions |
| **TopicAuthorizationException** | ACLs of the principal used by the DLT producer |
| **RecordTooLargeException** | Payload, exception headers, and size limits |
| **SerializationException** | Whether the serializer supports the actual type of failing records |
| Rising producer buffer wait | Send rate, **buffer.memory**, broker throughput, and request duration |

Do not look only for listener exceptions. Check for exceptions raised during recoverer publishing as well.

### Step 3: Inspect Topics and Consumer Lag

Use Kafka CLI commands with your environment's bootstrap server and topic/group names:

~~~bash
kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --describe --topic orders.DLT

kafka-consumer-groups.sh --bootstrap-server "$BOOTSTRAP" --describe --group orders-consumer
~~~

Verify the DLT has enough partitions for the mapping strategy, partitions have leaders, and ISR satisfies replication policy. Compare source consumer lag against DLT consumer lag to pinpoint whether the bottleneck lies in publishing or in post-publish processing.

### Step 4: Correlate Metrics

Monitor these metric groups over the same time window:

| Group | Metrics to Inspect | Meaning |
|---|---|---|
| DLT ingress | Records/second, bytes/second by topic and partition | Rate at which failing records are sent |
| Recoverer | Recovery count, publish latency, publish failure count | Duration and outcome of routing records |
| Producer | **record-error-rate**, **record-retry-rate**, **request-latency-avg**, **bufferpool-wait-time**, **buffer-available-bytes**, **record-queue-time-avg**, **outgoing-byte-rate**, **batch-size-avg** | Whether the producer faces backpressure or slow brokers |
| Source consumer | Lag per partition, listener duration, retry count, rebalances | Impact on source stream throughput |
| Broker | Request latency, network/disk I/O, under-replicated partitions, ISR, and quotas | Whether the cluster has sufficient write capacity |
| DLT consumer | Lag and processing rate | Ability to handle records after they are published |

Exact metric names and exposure depend on Kafka, Spring Kafka, and monitoring stack versions. Use available JMX/Micrometer exporters to pull equivalent metrics if display names differ.

### Step 5: Estimate Required Capacity

Approximate DLT data rate:

~~~text
DLT bytes/second
    = failing records/second × average size per record
~~~

For example, with 400 failing records per second averaging 12 KB each:

- DLT payload rate is roughly 4.8 MB/s.
- With replication factor 3, the cluster must serve additional replication traffic; internal write volume is roughly 14.4 MB/s before factoring in overhead, protocol framing, and compression efficiency.

Calculate traffic per partition separately to spot hot partitions. When estimating capacity, use record size after adding headers and use peak-incident failure rates rather than quiet-day averages.

## Remediation Actions

### Immediate Incident Response

1. Verify the DLT topic exists, has sufficient partitions, healthy leaders/ISR, and valid producer ACLs.
2. If failures stem from a deployment or dependency, stop or roll back the faulty change to cut the rate of records entering the DLT.
3. If one partition is overloaded, identify the distribution cause before changing concurrency or partition mapping.
4. Restore broker, network, quota, or disk capacity if that is the root cause.
5. Keep unpublished records in a retryable or recoverable state. Never treat a record as recovered if DLT send fails.
6. Once the publish path stabilizes, watch DLT ingress, source lag, and producer error rate before replaying data at high speed.

### Short-Term Improvements

- Pre-create DLT topics with partition counts and replication matching the source topic.
- Configure bounded retries with sufficient backoff to prevent retry storms during systemic errors.
- Enable DLT send failure detection so the error handler knows when publishing fails; verify exact behavior for your Spring Kafka version.
- Tune producer batching, compression, and buffers based on record size, throughput, and real metrics.
- Consider a dedicated producer factory for the DLT if a shared producer competes for resources with other publish flows. This isolates client-side resources; it does not increase shared broker capacity.
- Set DLT retention long enough for operations teams to investigate, and provision storage for peak error rates.

### Long-Term Improvements

- Track DLT ingress and publish failures as first-class operational metrics; alert on publish failures or DLT rates spiking above baseline.
- Test DLT broker unavailability, bad ACLs, missing partitions, and oversized payloads. Verify no records are lost when the recoverer fails.
- Separate retryable errors from non-retryable errors; avoid long retries for deterministic data errors.
- Maintain a rate-limited replay workflow with deduplication and loop protection when replayed records fail again.
- If the system uses Kafka transactions, design the recoverer and after-rollback handling around the application's transaction model. Do not blindly apply a non-transactional error handler config; ensure DLT publishing and offset handling obey atomicity requirements.

## Spring Kafka Configuration Example

The example below illustrates a non-transactional error handler. The recoverer maps records to the same-numbered partition on a topic suffixed with **.DLT**; therefore, the DLT must be created with enough partitions. **FixedBackOff** bounds retry attempts before handing the record to the recoverer.

~~~java
@Bean
DefaultErrorHandler dltErrorHandler(KafkaTemplate<Object, Object> kafkaTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) ->
                            new TopicPartition(
                                    record.topic() + ".DLT",
                                    record.partition()));

    // Propagate publish error back to the error handler if the broker fails to accept the record.
    recoverer.setFailIfSendResultIsError(true);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
~~~

Attach the error handler to the listener container factory:

~~~java
factory.setCommonErrorHandler(dltErrorHandler);
~~~

Points to verify when applying:

- **KafkaTemplate**'s serializer must support the actual value types. For deserialization errors, preserve and publish raw bytes.
- The DLT must have partitions matching source partitions if the resolver preserves partition numbers.
- **setFailIfSendResultIsError(true)** feeds publish errors back to the error handler, though it can make the listener wait on send results. Pick timeouts and retries based on SLOs.
- Retry counts, retryable exception types, and backoffs must align with your Spring Kafka version and error characteristics.
- If the container uses transactions, use transaction-compatible after-rollback processing and recoverers for that version.

## Incident Closure Checklist

- [ ] Identified the root cause of the spike in failing records.
- [ ] DLT topic exists, has sufficient partitions, stable leaders/ISR, and valid ACLs.
- [ ] DLT producer has no remaining send errors or abnormal buffer waits.
- [ ] Source consumer lag drops as expected after publishing recovers.
- [ ] DLT consumer can drain the backlog and retention is long enough to keep data.
- [ ] Replay workflow is rate-limited and prevents duplicate processing.
- [ ] Added alerts for DLT publish failures, abnormal DLT ingress, and source lag.


