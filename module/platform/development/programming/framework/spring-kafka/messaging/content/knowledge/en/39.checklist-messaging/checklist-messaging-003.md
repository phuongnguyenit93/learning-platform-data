# Producer Configuration Checklist

A producer is the component that publishes events from an application into Kafka. A well-configured producer must simultaneously satisfy data durability, error handling, throughput, latency, security, and observability. In Spring Kafka, producer configuration is usually declared via Spring Boot properties or a custom `ProducerFactory`; `KafkaTemplate` uses that factory to send records.

Use this checklist before deploying a new producer or changing the configuration of a running producer. The values in the examples are starting points for evaluation, not optimal configurations for every workload. Choose values based on SLA, event size, partition count, broker capacity, and business requirements.

## 1. Define requirements before configuring

Before choosing serializers, acknowledgements, or compression, align on what kind of data stream the producer serves.

- [ ] Identify target topics and the service owning each topic.
- [ ] Identify event types, schemas, keys, and typical payload sizes.
- [ ] Determine whether events must maintain ordering per entity/key.
- [ ] Determine acceptable data loss when brokers or networks fail.
- [ ] Determine average throughput, peak records/second, and bytes/second.
- [ ] Determine target latency, e.g., p95/p99 from application send to broker acknowledgement.
- [ ] Determine whether the producer needs transactions or only idempotent delivery.
- [ ] Identify runtime environments: local, test, staging, production, Kubernetes, or VM.
- [ ] Identify which consumers and connectors will read the topic to check serializer/compression compatibility.
- [ ] Identify operational owners, dashboards, alerts, and publish failure handling procedures.

Do not choose configurations solely by records per second. A producer sending many small events across many partitions has different batching characteristics than a producer sending large payloads to a few partitions.

## 2. Verify the Kafka cluster and target topic

A producer only sends successfully when the broker and topic match the chosen configuration.

- [ ] `bootstrap.servers` points to the bootstrap endpoints of the right cluster and environment.
- [ ] DNS, routes, firewalls, and TLS handshakes from the application to brokers work.
- [ ] Target topics are provisioned or have a controlled topic creation workflow.
- [ ] Partition count matches throughput and consumer parallelism.
- [ ] Replication factor matches broker count and fault-tolerance requirements.
- [ ] Topic `min.insync.replicas` aligns with the acknowledgement policy.
- [ ] Topic has `max.message.bytes` sufficient for designed records/batches.
- [ ] Topic cleanup policy and retention match the event lifecycle.
- [ ] Leader/ISR and broker health are checked before rollout.

With a producer using `acks=all`, `min.insync.replicas` sets the minimum in-sync replicas required for the broker to accept writes. For example, a topic with replication factor 3 and `min.insync.replicas=2` requires at least two in-sync replicas for writes with `acks=all`. If ISR drops below the threshold, the producer receives an error instead of silently accepting lower durability.

Do not set a replication factor greater than the number of brokers capable of storing replicas. Single-broker local configs normally differ from multi-broker production clusters.

## 3. Configure connectivity and producer identity

With Spring Boot, basic connection config in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
      - kafka-3.example.internal:9092
    producer:
      client-id: orders-service
```

Connectivity checklist:

- [ ] Use multiple bootstrap broker endpoints if the environment provides a broker list.
- [ ] Do not hard-code production addresses in source code.
- [ ] Separate local, test, staging, and production configs via profiles/secrets/config management.
- [ ] Set `client.id` to identify the service, instance, and environment when needed.
- [ ] Do not use `client.id` as the transactional ID; the two properties serve different purposes.
- [ ] Verify the application connects to the right cluster before allowing business events to be published.

`bootstrap.servers` is only an initial list of addresses for the client to fetch metadata; the producer can connect to other brokers after receiving metadata from the cluster.

## 4. Choose key and partition strategy

The key affects which partition a record is sent to and therefore processing order.

- [ ] Choose a stable key per entity requiring ordering, such as `orderId`, `accountId`, or `customerId`.
- [ ] Do not use a random key if events of the same entity must be processed sequentially.
- [ ] Check key distribution to prevent a hot key from overloading a partition.
- [ ] Do not change key formatting or the partitioner without evaluating the impact on ordering.
- [ ] Only specify a partition directly when there is a clear operational requirement.
- [ ] If the key is null, understand how the partitioner distributes records in the Kafka client version in use.
- [ ] Maintain compatibility between the producer's key serializer and the consumer's key deserializer.

Kafka only guarantees ordering within a single partition. Records with the same key are typically routed to the same partition by the default partitioner, though changing partition count can map a key to a different partition. Do not assume global ordering across multiple partitions.

Example sending an event with `orderId` as the key:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload);
    }
}
```

In the example, events with the same `orderId` are generally routed to the same partition, preserving relative order within that partition.

## 5. Configure serializers and schemas

Serializers convert keys/values from Java objects into byte arrays. Producers and consumers must agree on the wire format.

- [ ] Choose a key serializer matching the key type: String, Long, UUID, or byte array.
- [ ] Choose an appropriate value serializer: JSON, Avro, Protobuf, JSON Schema, or bytes.
- [ ] Verify generated schema classes and serializer dependencies are on the runtime classpath.
- [ ] If using Schema Registry, configure `schema.registry.url` and credentials properly.
- [ ] Choose a consistent subject naming strategy.
- [ ] Decide whether `auto.register.schemas` is allowed to be enabled in that environment.
- [ ] Check the compatibility policy before deploying a new schema.
- [ ] Do not confuse Spring Kafka `JsonSerializer` with Confluent `KafkaJsonSchemaSerializer`.
- [ ] Verify consumers and connectors can deserialize payloads emitted by the producer.
- [ ] Include tests for old payloads, new payloads, and serialization errors.

Example JSON producer in Spring Boot:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

If using Avro with Confluent Schema Registry, the value serializer may be `io.confluent.kafka.serializers.KafkaAvroSerializer`; consumers need the corresponding deserializer. Do not configure an Avro producer and leave consumers using `StringDeserializer`.

Serialization errors are usually not fixed by retrying to send the same object. Distinguish data/serializer errors from transient broker or network errors.

## 6. Choose an acknowledgement policy

The producer property `acks` controls how many broker acknowledgements the producer waits for before considering a send successful.

| Value | Behavior | Considerations |
|---|---|---|
| `0` | Producer does not wait for broker acknowledgement | Throughput/latency may be better, but the producer does not know if the broker received the record |
| `1` | Waits for leader to confirm local write | Records can be lost if the leader fails before replicas receive the data |
| `all` or `-1` | Waits for all replicas currently in the ISR to acknowledge | Usually suited for business events needing high durability; combine with `min.insync.replicas` |

Spring Boot example:

```yaml
spring:
  kafka:
    producer:
      acks: all
```

Checklist:

- [ ] Choose `acks=all` for events that cannot easily be recreated or business flows requiring high durability.
- [ ] Check topic `min.insync.replicas` so the policy has practical meaning.
- [ ] Only use `acks=0` when missing broker acknowledgement is acceptable and risks are measured.
- [ ] Do not treat `acks=all` as a guarantee that data has been processed by consumers.
- [ ] Define clearly when the publish API returns success: broker ack, transaction commit, or downstream processing.

`acks=all` does not mean every replica configured in the replication factor must be online; it requires the replicas currently in the ISR. The `min.insync.replicas` threshold sets the minimum ISR for the broker to accept writes.

## 7. Idempotence, retries, and timeouts

Network errors can prevent the producer from knowing whether the broker wrote a record. Retries resend the request; an idempotent producer helps Kafka eliminate duplicates from retries within the same producer session/sequence under Kafka's supported guarantees.

- [ ] Enable `enable.idempotence=true` for producers that need to limit retry duplicates.
- [ ] Avoid conflicting configurations among idempotence, `acks`, `retries`, and `max.in.flight.requests.per.connection`.
- [ ] When idempotence is enabled, keep `max.in.flight.requests.per.connection` within Kafka's supported limit (maximum 5 with modern idempotent producers).
- [ ] Set `delivery.timeout.ms` to the maximum time the application accepts for a single send.
- [ ] Set `request.timeout.ms` appropriately for broker/network latency and smaller than `delivery.timeout.ms`.
- [ ] Understand that `max.block.ms` bounds how long calls can block when metadata/buffers are not ready.
- [ ] Do not set a low retry count just to hide errors; with idempotence, the Kafka client can retry within the delivery timeout.
- [ ] Classify retryable and non-retryable errors at the application layer.
- [ ] For timeouts with unknown outcomes, use event IDs/idempotency at the consumer if business logic cannot tolerate duplicates.

Example reliability configuration:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[max.block.ms]": 60000
```

Modern Kafka producers often enable idempotence by default when compatible conditions are met, but declaring it explicitly helps reviewers see the intent. Check the effective Kafka client values rather than relying on assumptions about defaults across versions.

Idempotence does not make database, HTTP, or email side effects exactly-once. If the application retries the entire business flow and resends an event from a different producer session, event IDs and consumer idempotency are needed to prevent duplicate processing.

## 8. Distinguish producer retries from business retries

There are two different retry layers:

| Layer | Scope | Examples |
|---|---|---|
| Kafka producer retry | Resending requests on transient errors per Kafka client | Broker leader change, request timeout, or retryable network error |
| Application retry | Re-invoking business logic or the publish operation | Service re-running a use case after failure, retry job, or outbox publisher re-running |

- [ ] Do not wrap Kafka retries in a tight application retry loop without backoff.
- [ ] Do not retry serialization, authorization, or record-too-large errors indefinitely.
- [ ] For application-layer retries, enforce attempt limits, backoff, and metrics.
- [ ] If a send timeout leaves the outcome unknown, do not assume the record was definitely not written.
- [ ] Use an outbox or durable event emission mechanism if database changes and event publishing must not drift apart.

Producer retries do not replace consumer retries or dead-letter handling. Each layer addresses a different class of failure at a different boundary.

## 9. Configure batching and linger

Kafka groups records into batches per partition to reduce request counts and improve compression efficiency.

- [ ] Measure average `batch.size` and batch fill ratio before changing values.
- [ ] Choose `batch.size` according to throughput, partition count, and memory budget.
- [ ] Use `linger.ms` to give the producer extra time to accumulate records when batches are not yet full.
- [ ] Measure p95/p99 latency after changing linger.
- [ ] Verify `buffer.memory` is sufficient for the partition count and producer concurrency.
- [ ] Monitor producer buffer exhaustion and waiting threads.
- [ ] Do not call `flush()` after every message; doing so defeats batching.

Example starting point:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      buffer-memory: 67108864
      properties:
        "[linger.ms]": 5
```

`batch-size` and `buffer-memory` are in bytes. Values of 64 KiB and 64 MiB are only examples; workloads with large payloads or many partitions may need different budgets. Increasing batch size does not guarantee batches will fill if traffic per partition is low.

## 10. Choose compression

Compression reduces transmitted and stored bytes at the expense of compression/decompression CPU.

- [ ] Run a baseline with `none`.
- [ ] Benchmark `lz4`, `snappy`, `zstd`, and `gzip` on representative payloads.
- [ ] Configure `spring.kafka.producer.compression-type` or `compression.type`.
- [ ] Check whether topic `compression.type` preserves the producer codec (`producer`) or causes the broker to recompress.
- [ ] Measure `compression-rate-avg`, batch size, producer/broker/consumer CPU, and network bytes.
- [ ] Verify connectors and non-Java clients support the chosen codec.
- [ ] Do not pick a codec based solely on compression ratio; evaluate latency and CPU as well.

Example:

```yaml
spring:
  kafka:
    producer:
      compression-type: lz4
```

`lz4` is often a reasonable starting point when balancing CPU and network, though actual results depend on the data. Already-compressed or encrypted payloads may see minimal reduction.

## 11. Record and request size limits

Large payloads can exceed producer, broker, or consumer fetch limits.

- [ ] Measure actual key, value, header, and record-batch sizes.
- [ ] Check producer `max.request.size`.
- [ ] Check broker `message.max.bytes` and topic `max.message.bytes` per Kafka version.
- [ ] Check consumer `fetch.max.bytes` and `max.partition.fetch.bytes`.
- [ ] Do not raise limits only on the producer while forgetting the broker and consumer.
- [ ] Evaluate memory, network, GC, and serialization time for large payloads.
- [ ] Consider storing large blobs in object storage and sending only a reference/metadata via Kafka.

Compression does not guarantee an oversized record will be accepted. A single large record can still exceed limits even when a batch has a good compression ratio.

## 12. Security and ACLs

Production producers must authenticate with the cluster and only have permission to publish to assigned topics.

- [ ] Choose the right security protocol: `SASL_SSL`, `SSL`, or the cluster's protocol.
- [ ] Configure SASL mechanisms and credentials via a secret manager/secret environment.
- [ ] Configure truststore/keystore when the cluster requires TLS client authentication.
- [ ] Do not commit passwords, API keys, JAAS configs, or private keys into the repository.
- [ ] Producer principal has `WRITE` and `DESCRIBE` on target topics per ACL policy.
- [ ] If using transactions, the principal has required permissions on the transactional ID.
- [ ] Check certificate rotation and credential expiration.
- [ ] Test connectivity in a production-like environment.

Illustrative SASL/SSL example; mechanism names and credentials must come from the cluster:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": PLAIN
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.plain.PlainLoginModule required username="API_KEY" password="API_SECRET";'
```

Replace `API_KEY` and `API_SECRET` with values injected from a secret manager at runtime; do not store real credentials in configuration files or source control. Do not use PLAIN over unencrypted connections. With SASL/SSL, TLS protects credentials and data in transit. Exact authentication details must follow the guidelines of the Kafka platform in use.

## 13. Transactions when atomic publishing is needed

If a business operation must send multiple records as a single commit/abort unit, Kafka transactions can be used. With Spring Boot, configure `transaction-id-prefix` so the producer factory supports transactions.

- [ ] Only enable transactions when the use case needs atomic multi-record sends or consume-transform-produce.
- [ ] Configure `spring.kafka.producer.transaction-id-prefix` uniquely across active instances.
- [ ] Ensure `KafkaTemplate` and `KafkaTransactionManager` use the right `ProducerFactory`.
- [ ] Set `transaction.timeout.ms` within broker limits.
- [ ] Consumers that must skip aborted transaction records must use `isolation.level=read_committed`.
- [ ] If input offsets must be committed with output records, use a transactional listener container/offset coordination properly.
- [ ] Do not assume a Kafka transaction covers databases or HTTP services.

Example prefix for one instance:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-pod-a-orders-tx-
```

Prefixes must differ across concurrent pods/instances to avoid producer fencing. If only sending a single independent record without needing atomic multi-record writes, an idempotent producer may suffice without transactions.

## 14. Using KafkaTemplate safely

`KafkaTemplate` is designed to be shared across a Spring application. It acquires producers from `ProducerFactory`, manages send operations, and provides futures for results.

- [ ] Inject a configured `KafkaTemplate` instead of creating a new producer per message.
- [ ] Validate topic, key, value, and headers before sending.
- [ ] Use futures/callbacks to observe send success and failure.
- [ ] Do not block request threads too long unless synchronous behavior is required.
- [ ] Do not call `flush()` per record.
- [ ] Do not swallow exceptions in callbacks if the system needs to record publish failures.
- [ ] Include event ID/correlation ID in headers or payload per contract.
- [ ] Do not log full payloads containing sensitive data.

Example with Spring Kafka 3.x:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    EventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String topic,
            String key,
            String payload
    ) {
        return kafkaTemplate.send(topic, key, payload);
    }
}
```

Spring Kafka 3.x returns `CompletableFuture` from send APIs; older versions may use `ListenableFuture`. Follow the exact API of your project's dependency.

If a response to the caller is needed after broker acknowledgement, the caller can wait on the future at an appropriate boundary. Do not block HTTP request threads waiting on Kafka indefinitely; set timeouts and handle unknown outcomes idempotently.

## 15. Producer observability

You cannot operate a producer well if you only know whether the application logs exceptions.

- [ ] Export Kafka producer metrics via JMX/Micrometer according to the monitoring stack.
- [ ] Monitor `record-send-rate`, `record-error-rate`, and `record-retry-rate`.
- [ ] Monitor `request-latency-avg`/`request-latency-max`.
- [ ] Monitor `record-queue-time-avg` and `batch-size-avg`.
- [ ] Monitor `compression-rate-avg`.
- [ ] Monitor `buffer-available-bytes` and `waiting-threads`.
- [ ] Track timeouts, serialization failures, authorization failures, and broker disconnects.
- [ ] Tag `client.id`, service, environment, and topic in logs/metrics where appropriate.
- [ ] Include correlation IDs/event IDs to trace publishes to consumers.
- [ ] Set alerts for error rate, latency, buffer pressure, and sustained publish failures.

Common symptoms:

| Symptom | Causes to investigate |
|---|---|
| `record-error-rate` increases | Broker, ACL, serialization, message size, or timeout |
| `record-retry-rate` increases | Flaky network, leader changes, or overloaded broker |
| `record-queue-time-avg` increases | Producer buffer waiting to send, slow broker, or batches not drained |
| `buffer-available-bytes` is low | Producer cannot send fast enough or buffer memory is too small |
| `waiting-threads` increases | Application threads waiting long for metadata/buffer |
| Request latency increases | Broker/network, ISR, or request queue |
| Poor compression ratio | Small batches or incompressible payloads |

Metric names and export mechanisms can differ across Kafka client versions. Build dashboards from the actual metrics exposed in the deployment environment.

## 16. Test the producer before release

Unit tests that mock `KafkaTemplate` only verify that code calls the right method; they do not verify broker acknowledgements, serializers, ACLs, or transaction markers.

- [ ] Unit test event mapping: fields, key, headers, and topic.
- [ ] Test serialization/deserialization round-trip.
- [ ] Integration test with a real Kafka broker or appropriate Testcontainers/Embedded Kafka.
- [ ] Verify records are written to the right topic, partition, and key.
- [ ] Verify send futures succeed and errors propagate to callers.
- [ ] Test broker unavailable, timeouts, and retry behavior.
- [ ] Test records exceeding size limits.
- [ ] Test missing ACL permissions.
- [ ] If using Schema Registry, test schema registration/lookup and compatibility.
- [ ] If using transactions, test commits, aborts, and `read_committed` consumers.
- [ ] Run representative load to measure throughput, latency, CPU, network, and compression.

Tests should verify results on the broker/consumer rather than only counting mock invocations. For transactions and idempotence, a real broker is required to verify semantics.

## 17. Rollout and configuration change checklist

Changing producer configs can affect the entire event stream. Roll out incrementally and ensure rollback capability.

- [ ] Record current configuration and baseline metrics before changes.
- [ ] Change one group of properties at a time to isolate cause and effect.
- [ ] Verify broker/client and consumer compatibility before adopting new codecs or properties.
- [ ] Test in staging with production-like data and throughput.
- [ ] Canary one instance or a small producer workload if possible.
- [ ] Monitor error rate, latency, retries, buffers, CPU, and network after rollout.
- [ ] Verify consumers receive events with the right schema and per-key ordering.
- [ ] Have a rollback plan and know which configs can change at runtime vs. require a restart.
- [ ] Do not change serializer, key strategy, transaction ID prefix, and compression simultaneously without end-to-end testing.
- [ ] Update runbooks, dashboards, and configuration docs after changes.

Some producer properties apply when a new producer is created; changing Spring config does not necessarily update existing producer instances. Determine the lifecycle/restart behavior of `ProducerFactory` and the application before relying on dynamic config.

## 18. Reference configuration table

The table below is a starting template for a business-event producer; tune it according to your workload and system requirements.

| Property | Example | Purpose |
|---|---|---|
| `bootstrap-servers` | `kafka-1:9092,kafka-2:9092` | Cluster connection |
| `client-id` | `orders-service` | Identifies producer in metrics/logs |
| `key-serializer` | `StringSerializer` | Serializes key |
| `value-serializer` | `JsonSerializer` | Serializes value |
| `acks` | `all` | Waits for ISR acknowledgement |
| `enable.idempotence` | `true` | Prevents producer retry duplicates within Kafka scope |
| `delivery.timeout.ms` | `120000` | Upper bound for completing a send |
| `request.timeout.ms` | `30000` | Broker request timeout |
| `batch-size` | `65536` | Target batch size |
| `linger.ms` | `5` | Batch accumulation delay |
| `buffer-memory` | `67108864` | Producer accumulator memory |
| `compression-type` | `lz4` | Compresses record batches |
| `max.request.size` | Per payload/SLA | Producer request limit |

Combined example:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
    producer:
      client-id: orders-service
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[max.block.ms]": 60000
        "[linger.ms]": 5
```

This template omits security, Schema Registry, and transactions because those depend on the specific cluster and contract. Do not copy it verbatim to production without verifying `min.insync.replicas`, message size limits, credentials, throughput, and latency SLAs.

## 19. Final checklist before production

### Connectivity and topics

- [ ] Right cluster, bootstrap servers, and environment.
- [ ] Topics exist with correct partitions/replication/ISR.
- [ ] Topic size limits and retention are appropriate.

### Serialization and keys

- [ ] Key/value serializers match consumer contracts.
- [ ] Schema Registry/subjects/compatibility verified if applicable.
- [ ] Keys preserve proper ordering and avoid hot partitions.

### Reliability

- [ ] `acks` matches required durability.
- [ ] Idempotence enabled when needed.
- [ ] Retries and timeouts have reasonable bounds.
- [ ] Serialization/authorization errors are not retried infinitely.
- [ ] Event IDs/idempotency exist for flows prone to duplicate sends.

### Performance

- [ ] Batch size, linger, buffer, and compression are benchmarked.
- [ ] CPU, network, latency, and buffer pressure stay within budget.
- [ ] Record/request sizes stay within limits across the whole pipeline.

### Security and operations

- [ ] TLS/SASL and ACLs enforce least privilege.
- [ ] Secrets are absent from source control.
- [ ] Metrics, logs, traces, and alerts are configured.
- [ ] Integration tests and rollout/rollback plans are ready.
- [ ] Owner and runbook exist for handling publish failures.

A producer is configured properly when events are serialized per contract, routed to the right partitions, acknowledged by brokers at the chosen durability level, errors are observable, and throughput/latency remain within SLA. Use this checklist as a pre-production gate, then continue comparing against live metrics to tune for your workload rather than treating example numbers as optimal defaults.
