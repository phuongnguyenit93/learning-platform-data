# Runbook for Producer Send Failures

## Objective and Scope

This runbook is used when a Java/Spring Kafka application fails to send records to Kafka, sends abnormally slowly, or receives errors while awaiting send results. The objective is to pinpoint the failing layer, restore the sending flow, and preserve events according to business requirements.

The scope covers **KafkaTemplate.send()** calls, the Kafka producer client, broker connectivity, topic access permissions, and broker acknowledgment responses. This runbook does not handle consumer errors after a record has been accepted by the broker, except for the step distinguishing between those two situations.

Consider a record successfully sent only when the future/callback completes successfully according to the **acks** configuration. That confirms the write level requested by the producer; it does not prove that a consumer has read or processed the record.

## 1. Initial Response

When a send failure alert fires:

1. Record the start time, service, environment, application version, topic, cluster, and number of affected instances.
2. Determine whether the error affects a single record, a partition, a topic, or the entire producer. Compare at least one failing instance with another instance if available.
3. Capture the full exception, root cause, trace/correlation ID, topic, masked/hashed key, and record metadata. Do not put sensitive payloads, tokens, passwords, or personal data into logs or tickets.
4. Check recently deployed changes: bootstrap server configuration, serializers, TLS/SASL, ACLs, topics, record size, and client version.
5. If failures started immediately after a deployment or configuration change, consider rolling back per the approved release process. If the broker or network is experiencing a widespread outage, coordinate with the Kafka/platform team before adding load via manual retries.

Do not delete topics, recreate topics, disable authentication/TLS, lower `acks` to 0, or disable idempotence just to make alerts disappear. Those actions can mask the root cause or break data guarantees.

## 2. Identify Which Stage Failed

Calls to **KafkaTemplate.send()** typically return a future to track asynchronous results. However, failures can occur immediately during the `send()` call or later when the producer communicates with the broker.

| Stage | Symptom | Where to check |
|---|---|---|
| Before the record enters the buffer | `send()` throws an exception immediately; common causes include serializer errors, misconfiguration, closed producer, missing metadata, or inability to allocate buffer within the timeout | Serializer, topic/metadata, `max.block.ms`, `buffer.memory`, producer lifecycle |
| Asynchronous send | Future completes exceptionally or callback receives an exception | Broker, network, ACLs, authentication, record size, timeouts, replication |
| Future succeeds but data does not appear where expected | No send exception; downstream application does not receive the record | Target cluster/topic, partition, consumer group, offset, filters, and read timestamp |

Distinguish between these timeouts:

- **max.block.ms** limits how long the producer waits for metadata or buffer space when calling `send()`. It is not the deadline for the broker to acknowledge the record.
- **request.timeout.ms** limits how long the client waits for a response to a single request to the broker.
- **delivery.timeout.ms** limits the total time to deliver a record, including batch wait time and retries. This value must be configured consistently with `request.timeout.ms` and `linger.ms`.

A timeout error may occur after the broker has already written the record, if the producer did not receive the response. In that situation, resending at the application layer can create duplicate records unless the system has business-level idempotency.

## 3. Diagnostic Table by Symptom

| Symptom / common exception | Possible cause | Evidence to inspect | Action |
|---|---|---|---|
| `SerializationException` | Serializer does not support the data type, invalid schema, unhandled null value, or wrong key/value serializer config | Stack trace at serializer, record type, schema/version, DTO changes | Fix the data or serializer; test with the failing record; do not infinitely retry the exact same payload |
| `TimeoutException` during `send` or awaiting delivery | Unable to fetch metadata, slow broker/network, exhausted buffer, or request not acknowledged in time | Stage where it occurred, `max.block.ms`, `delivery.timeout.ms`, request latency, buffer available, broker health | Determine whether the timeout is on client or broker side; fix root cause before tuning timeouts |
| `NotEnoughReplicasException` or `NotEnoughReplicasAfterAppendException` | ISR is smaller than required by `min.insync.replicas` when using `acks=all` | ISR, replica status, disconnected brokers, topic config | Restore replicas/brokers and ISR; keep durability policy intact during investigation |
| `TopicAuthorizationException` or `ClusterAuthorizationException` | Principal lacks required ACLs or is using the wrong principal | Effective principal, topic/cluster ACLs, environment, mounted secrets | Grant minimum required permissions through governance process; verify the principal used by the app |
| `AuthenticationException`, SSL/SASL error, or handshake failure | Expired/incorrect credentials, truststore/keystore mismatch, SASL mechanism, or certificate mismatch | Secret-redacted handshake logs, certificate expiration, auth mechanism, client/broker config | Restore credentials/certificates and matching config; never log secrets |
| `RecordTooLargeException` | Record or batch exceeds limit on producer, broker, or topic | Serialized record size, `max.request.size`, `message.max.bytes`, `max.message.bytes` | Reduce payload or align limits across layers per operational standards |
| `BufferExhaustedException` or timeout waiting for buffer | Producer creates records faster than send rate, broker/network is slow, buffer is too small, or threads are blocked | `buffer-available-bytes`, `bufferpool-wait-time`, `waiting-threads`, send rate, and request latency | Reduce generation rate or apply backpressure; inspect broker/network; increase buffer only after evaluating heap and load |
| `ProducerFencedException` | Another producer used the same transactional ID and fenced the current producer | Transactional ID, app replica count, transaction lifecycle | Ensure a unique transactional ID per logical producer and initialize transactions properly |
| `OutOfOrderSequenceException` or sequence/producer epoch error | Idempotent/transactional producer state error, misconfiguration, or abnormal producer lifecycle | Kafka client logs, transactional ID, retry/in-flight config, restart history | Preserve logs; follow guidance for your Kafka client/version and check idempotence/transaction config |
| `UnknownTopicOrPartitionException` or `InvalidTopicException` | Wrong topic name, topic not yet created, stale metadata, or invalid topic name | Actual topics on cluster, bootstrap servers, environment, describe permissions | Verify target cluster and topic; create the topic through governance process if requested |
| `NetworkException`, `DisconnectException`, or connection timeout | DNS, routing, firewall, broker listener, connection limits, or broker restarts | DNS from pod, connectivity to each broker, broker logs, network policies | Restore network path/listeners; check all brokers advertised in metadata, not just bootstrap servers |

Exception names and how Spring Kafka wraps them may vary by version. Always inspect the full cause chain instead of classifying solely by the outermost exception name.

## 4. Investigation Procedure

### 4.1. Collect Application Logs

Search logs around the alert window, including logs right before the first exception:

~~~bash
kubectl logs -n <namespace> deploy/<service> --since=15m \
  | grep -Ei 'Kafka|producer|SerializationException|TimeoutException|AuthorizationException|AuthenticationException|RecordTooLarge'
~~~

If the workload runs multiple pods, check each affected pod and correlate with restart times:

~~~bash
kubectl get pods -n <namespace> -l app=<service> -o wide
kubectl describe pod -n <namespace> <pod-name>
~~~

Record available fields: timestamp, service/pod, topic, partition (if assigned), masked key, trace ID, exception class, cause chain, and elapsed time from send to failure. Do not enable payload logging or wire protocol logging in production without assessing impact and sensitive data exposure.

### 4.2. Check Cluster and Topic

Confirm the application points to the right cluster for the environment. A reachable bootstrap server does not guarantee every broker advertised in metadata is reachable from the pod.

Use Kafka tools compatible with your environment's version and permissions:

~~~bash
kafka-topics.sh --bootstrap-server <bootstrap-server> \
  --describe --topic <topic-name>
~~~

Check the leader, partitions, replicas, and ISR. If authorization errors occur, ask an authorized operator to inspect ACLs:

~~~bash
kafka-acls.sh --bootstrap-server <bootstrap-server> \
  --list --topic <topic-name>
~~~

Inspect topic configuration when needed:

~~~bash
kafka-configs.sh --bootstrap-server <bootstrap-server> \
  --entity-type topics --entity-name <topic-name> --describe
~~~

These commands may require client properties for TLS/SASL authentication. Do not pass passwords or credential contents directly in shell history or tickets. Run config-modifying commands only with operational approval.

### 4.3. Check Producer and Broker Metrics

Correlate failure timestamps with producer metrics. Exact metric names depend on Kafka client, Spring Kafka, Micrometer, and your exporter, but key signals include:

- **record-send-rate / record-send-total**: rate and total number of records sent.
- **record-error-rate / record-error-total**: send errors.
- **record-retry-rate / record-retry-total**: retry count.
- **request-latency-avg / request-latency-max**: request latency to brokers.
- **record-queue-time-avg**: time records spend in the producer queue/batch.
- **buffer-available-bytes, bufferpool-wait-time-total, and waiting-threads**: buffer pressure.
- Broker side: request handler/network processor saturation, request queue, under-replicated partitions, offline partitions, ISR shrink/expand, disk latency, and broker health.

Interpret correlations:

- Errors and retries rising alongside request latency: prioritize checking brokers, network, and replication.
- Available buffer dropping near 0 while buffer wait increases: producer is experiencing backpressure or cannot deliver records fast enough.
- Errors occurring on only one topic: check ACLs, topic configuration, leader, and record size for that topic.
- Errors occurring simultaneously across multiple topics/instances: prioritize bootstrap/listeners, DNS/network, authentication, or cluster health.
- Sends succeed normally but consumers do not see records: shift investigation to target cluster/topic, partitions, and consumers; stop treating it as a producer send failure.

### 4.4. Check Configuration and Recent Changes

Compare the running configuration against a known-good configuration:

- `bootstrap.servers` and listeners reachable from pods.
- Key/value serializers, schema registry (if used), subject, and schema compatibility.
- Security protocol, SASL mechanism, principal, truststore/keystore, and certificate expiration.
- `acks`, idempotence, `retries`, `delivery.timeout.ms`, `request.timeout.ms`, `linger.ms`.
- `max.block.ms`, `buffer.memory`, and `max.request.size`.
- Topic existence, valid ACLs, record/batch size limits, and `min.insync.replicas`.

Check the effective configuration after Spring Boot property binding; do not rely solely on YAML files in the repository. Secret managers, environment variables, ConfigMaps, or Helm values can override settings.

## 5. Error Handling Pattern in Spring Kafka

In Spring Kafka 3.x, `KafkaTemplate.send()` returns `CompletableFuture<SendResult<K, V>>`. Register `whenComplete` to capture asynchronous results. In Spring Kafka 2.x, the future type may be `ListenableFuture`; adapt the pattern to match your application's version.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

class OrderPublisher {
    private static final Logger log = LoggerFactory.getLogger(OrderPublisher.class);
    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publish(String topic, String key, OrderEvent event, String traceId) {
        try {
            CompletableFuture<SendResult<String, OrderEvent>> future =
                    kafkaTemplate.send(topic, key, event);

            future.whenComplete((result, exception) -> {
                if (exception != null) {
                    Throwable cause = unwrapCompletionException(exception);
                    // Log only safe metadata; do not log payload or secret.
                    log.error("Kafka send failed: topic={}, traceId={}",
                            topic, traceId, cause);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.debug("Kafka send acknowledged: topic={}, partition={}, offset={}",
                        metadata.topic(), metadata.partition(), metadata.offset());
            });
        } catch (RuntimeException exception) {
            // Catch synchronous errors occurring before the future is returned.
            log.error("Kafka send could not be started: topic={}, traceId={}",
                    topic, traceId, exception);
            throw exception;
        }
    }

    private static Throwable unwrapCompletionException(Throwable exception) {
        Throwable current = exception;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

`OrderEvent` is an example application data type. This snippet illustrates observing send results; add business error handling appropriate for your system. Do not call `get()` or `join()` on a request thread solely to wait for sending to finish, as that can block threads and increase latency.

The callback may execute on the producer thread or the thread completing the future. Keep callbacks short and avoid blocking operations or recursively invoking the same send flow. Offload heavy recovery work to a bounded, monitored background mechanism.

## 6. Safe Recovery

Choose actions based on the confirmed root cause:

- **Data/serializer errors:** quarantine bad records per business rules, fix the schema or source data, and replay in a controlled manner. Retrying an unserializable record as-is will continue to fail.
- **Authentication/ACL errors:** restore the required principal, credentials, certificates, or permissions. After fixing, verify the producer establishes a connection and successfully sends an authorized test record.
- **Network/broker/replication errors:** coordinate with the cluster team, restore brokers/routes/ISR, and monitor automatic retries. Avoid adding load via mass restarts or replaying the entire backlog at once.
- **Buffer/backpressure errors:** reduce generation rate, apply upstream backpressure, or increase processing capacity after measuring heap, request latency, and throughput. Simply increasing `buffer.memory` can raise heap pressure without fixing slow brokers.
- **Size errors:** shrink payloads, move large data to object storage and send references if architecture permits, or align limits across producer, broker, and topic after impact assessment.
- **Transactional/fencing errors:** verify transactional IDs, producer ownership, and transaction boundaries. Do not run multiple instances sharing the same transactional ID outside the design.

### 6.1. Retries and Duplicate Record Risk

Prefer Kafka producer retries with idempotence when compatible with your configuration and client version. Idempotence helps the producer prevent duplicates caused by protocol retries within a single producer session; it does not automatically deduplicate records if the application resends the same event after a timeout, restart, or reprocessing from another source.

If you must retry at the application layer:

1. Use a stable event ID to identify the same event across attempts.
2. Define a bounded backoff policy with jitter and a maximum retry limit; avoid hot retry loops.
3. Preserve the key if the key determines partitioning or business ordering.
4. Ensure downstream receivers can deduplicate or process idempotently.
5. Persist retry state durably if events must not be lost across process restarts.
6. Monitor pending record count, oldest record age, retry rate, and records entering terminal failure state.

Do not use a consumer DLQ as a default fallback for producer send failures. If the broker cannot accept a record, the producer cannot assume sending that record to an error topic on the same Kafka cluster will succeed. When zero data loss is required, consider a transactional outbox or durable upstream retry store with a controlled replay process.

### 6.2. When Timeouts Create Uncertain Outcomes

If a producer times out, determine whether the broker may have written the record while the ACK was lost. Before replaying:

- Look up the event ID or business key downstream if the system supports it.
- Inspect offsets/records using authorized tools against the correct cluster/topic/partition.
- If certainty cannot be established, handle under at-least-once policy and ensure consumer deduplication.
- Record the uncertain status to prevent multiple parallel retries.

Do not conclude a record was definitely lost based solely on a `TimeoutException`.

## 7. Reliability Configurations to Review

The example below illustrates important Spring Boot properties. Timeout values are starting points for discussion only; tune them according to your SLO, broker latency, batch size, and acceptable recovery time.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        linger.ms: 5
~~~

Notes for review:

- `acks=all` requires acknowledgment according to the current ISR; combine with `min.insync.replicas` on the topic/broker to define the desired durability level.
- `enable.idempotence=true` ensures producer retries do not create duplicates from protocol retries within Kafka's guarantee scope. Verify `acks`, `retries`, and `max.in.flight.requests.per.connection` compatibility with your client version.
- `delivery.timeout.ms` should be greater than or equal to the sum of `request.timeout.ms` and `linger.ms`; setting it too low can expire records before sufficient retries occur.
- `max.block.ms` affects how long `send()` can block waiting for metadata/buffer. Choose based on the calling flow's latency budget.
- `buffer.memory` and `max.request.size` must fit within heap limits, record/batch sizes, and broker/topic limits.
- If using transactions, review `transactional.id`, transaction timeout, and per-instance producer creation. Do not apply transactional configs to regular producers if the application does not use transactions.

Do not change multiple parameters simultaneously during an incident. Every change must have a hypothesis, scope, approver, measurement method, and rollback plan.

## 8. Confirming Recovery

Close the incident only after verifying conditions appropriate to the impact severity:

- The producer connects to the correct cluster and successfully sends an authorized test record.
- Future/callback completes successfully; topic/partition/offset metadata is valid when `acks` requires acknowledgment.
- Error rate and retry rate have returned to normal thresholds; request latency and buffer wait are no longer abnormally elevated.
- Brokers/topics have appropriate leaders and ISR; no related offline partitions or replication errors remain.
- Backlog/retry store (if any) is draining at a controlled rate; no overdue unprocessed records remain.
- Downstream confirms records are being received per business workflow; check for duplicates if timeouts or replays occurred.
- Alerts have cleared and do not recur during the observation window defined by operational policy.

In the incident report, clearly document the timeline, impact scope, confirmed root cause (or note as undetermined), counts of succeeded/failed/pending records, changes applied, remaining duplicate or data-loss risks, and follow-up monitoring actions.

## 9. Quick Action Checklist

- [ ] Determine whether the error occurs synchronously in `send()` or asynchronously in the future/callback.
- [ ] Capture the full exception and cause chain; protect payloads, credentials, and personal data.
- [ ] Confirm the exact bootstrap servers, cluster, topic, principal, and affected pods.
- [ ] Check serializers/schemas, ACLs/authentication, record sizes, and topic/ISR status.
- [ ] Correlate error/retry rates, request latency, buffer availability, and broker health.
- [ ] Fix the root cause; preserve idempotence and durability per business requirements.
- [ ] Assess whether records may have been written before timeouts prior to replaying.
- [ ] Confirm successful sends, backlog drainage, proper downstream receipt, and stable alerts.
- [ ] Document root cause, impact scope, recovery actions, and residual risks.

