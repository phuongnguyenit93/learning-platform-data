# max.in.flight.requests.per.connection

In a Kafka producer, **max.in.flight.requests.per.connection** limits the number of requests sent to a broker that have not yet received a response on the same network connection. This property determines how many requests the producer can pipeline sequentially without waiting for each individual acknowledgement. It directly affects network round-trip utilization, throughput, latency, and record ordering when the producer has to retry.

In Spring Kafka, this is a property of the underlying Apache Kafka producer beneath **KafkaTemplate**. Spring Kafka does not alter its meaning: the application calls **KafkaTemplate.send()**, the producer batches records and sends ProduceRequests to brokers. The in-flight limit applies at the connection layer between the producer and each broker.

## 1. What Is an In-Flight Request?

A request becomes in-flight once the producer sends it over a connection to a broker and awaits a response. When the broker replies, that request no longer occupies an in-flight slot. If the limit is 5, the producer can have up to five unacknowledged requests on a single broker connection at the same time.

Example with value 1:

~~~text
Producer                         Broker
   |                               |
   |------ Request A ------------->|
   |                               |
   |       wait for response       |
   |<----- Response A -------------|
   |                               |
   |------ Request B ------------->|
   |                               |
   |       wait for response       |
   |<----- Response B -------------|
~~~

The producer sends the next request on that connection only after the pending request receives a response. This creates a sequential send stream, but each request incurs a full network round trip before the next request can depart.

With value 5:

~~~text
Producer                         Broker
   |                               |
   |------ Request A ------------->|
   |------ Request B ------------->|
   |------ Request C ------------->|
   |------ Request D ------------->|
   |------ Request E ------------->|
   |                               |
   |<----- Response B -------------|
   |<----- Response A -------------|
   |<----- Response D -------------|
   |<----- Response C -------------|
   |<----- Response E -------------|
~~~

The producer can transmit multiple requests before receiving the first request's response. Responses may arrive at different times. This pipelining lets the producer utilize network transit and broker processing time, especially when latency between the application and brokers is high.

The limit is counted per connection to each broker. It is not a cluster-wide total request cap. If a producer connects to multiple brokers, each connection has its own limit. Nor is it the number of records, partitions, or concurrent **KafkaTemplate.send()** calls allowed.

A single ProduceRequest can hold batches for one or more partitions led by that broker. Therefore, one in-flight request does not equal one record. Nor does every **send()** call immediately create a separate request: the producer may wait to accumulate multiple records into a batch before sending.

## 2. How Does This Property Coordinate with Batching?

The Kafka producer has several mechanisms controlling data transmission. Distinguish **max.in.flight.requests.per.connection** from batching properties:

| Property | Controls | Primary impact |
|---|---|---|
| **batch.size** | Target batch size per partition | Larger batches can boost compression efficiency and throughput, but may require more time or memory to fill. |
| **linger.ms** | Time producer waits for extra records before sending a batch | Increases batching opportunity in exchange for some added latency. |
| **buffer.memory** | Producer memory used to hold records waiting to be sent | Determines capacity for pending batches. |
| **max.in.flight.requests.per.connection** | Sent requests awaiting response per broker connection | Controls network request pipelining depth. |

**batch.size** and **linger.ms** determine when the producer has enough data to form a request. **max.in.flight.requests.per.connection** determines how many requests can be sent without waiting for broker responses.

Consequently, raising **max.in.flight.requests.per.connection** does not automatically make batches larger. With small batches, the producer may simply send more smaller requests. Conversely, large batches do not mean the producer only has one pending request.

**KafkaTemplate.send()** is an asynchronous API, yet that does not mean every **send()** call corresponds to an independent network request in flight. Records are held in the accumulator, batched per partition, and transmitted to brokers on the producer's schedule.

When in-flight requests hit the limit, the sender must wait for a response to free a slot before sending more requests on that connection. While waiting, batches remain inside the producer. If the application produces data faster than brokers can accept it, buffer usage climbs; when producer memory runs out, **send()** calls may block waiting for buffer allocation and eventually time out per **max.block.ms**.

## 3. Why Can the In-Flight Limit Affect Ordering?

Kafka preserves record order within each partition. However, when a producer allows multiple concurrent in-flight requests and must retry, log append order can change if idempotence is disabled.

Suppose a producer sends two consecutive batches to the same partition:

1. Request A containing batch A is sent to the broker.
2. Request B containing batch B is sent before the producer receives A's response.
3. The broker processes B successfully, while request A hits a transient error and needs a retry.
4. Without idempotence, A's retry can reach the broker after B has already been written.
5. The partition log can contain B before A, even though the application sent A before B.

Illustration:

~~~text
Application order:     A  ->  B

Initial send:          A  ->  B
Responses:             A fails, B succeeds
Retry without
idempotence:           B  ->  A (retry)

Observed order
in partition:          B  ->  A
~~~

This is why Kafka documentation warns that when retries are enabled and **max.in.flight.requests.per.connection** exceeds 1, records can be reordered if idempotence is disabled.

Setting the value to 1 limits each connection to one unacknowledged request. When request A needs a retry, request B has not yet been sent on that connection; the producer must resolve A before sending the next request. This prevents reordering caused by multiple concurrent in-flight requests, at the cost of significantly reduced throughput.

This limit does not create global ordering:

- Kafka only guarantees ordering within a single partition.
- Two different partitions have no guaranteed joint order.
- Two independent producers can write to the same partition; one producer's setting does not coordinate ordering across producers.
- If the application explicitly calls **send()** again to emit a business event a second time, that is a new send and is not treated as an internal retry of the same request.

When business ordering matters, use a stable key such as **orderId** so records for the same order route to the same partition. Then configure idempotence so producer retries do not reorder batches from that producer.

## 4. Idempotent Producer Enables Pipelining While Preserving Order

An idempotent producer eliminates duplicate and reordering risks from internal producer retries. Kafka assigns a producer ID and tracks per-partition batch sequence numbers. The broker uses this information to detect duplicate batches and enforce sequence ordering.

When a request loses its response, the producer can resend the batch with the same sequence information. The broker recognizes it as a retry of the earlier batch rather than appending a duplicate as a new batch. Sequence numbers also allow the broker to detect out-of-order batches.

With idempotence enabled, Kafka permits up to five in-flight requests per connection:

~~~properties
enable.idempotence=true
max.in.flight.requests.per.connection=5
acks=all
~~~

With this compatible setup, the producer can keep multiple pending requests to achieve higher throughput while still maintaining partition order during retries. There is no need to set **max.in.flight.requests.per.connection=1** purely to protect ordering if the producer uses idempotence and the client supports this configuration.

When idempotence is enabled, key configuration requirements include:

- **acks=all**.
- **retries** greater than 0; let the producer retry within **delivery.timeout.ms**.
- **max.in.flight.requests.per.connection** no greater than 5.

If idempotence is enabled explicitly alongside incompatible settings, the Kafka producer can refuse to initialize with a configuration error. Check producer startup logs instead of assuming the client silently adjusts every value.

In modern Kafka clients, idempotence is often enabled by default. Still, default behavior depends on client version and can be altered by other settings. Explicitly set **enable.idempotence=true** for producers needing reliability and verify the exact Kafka client version Spring Kafka actually uses.

### Idempotence Does Not Solve Every Duplicate Case

Idempotence protects internal retries within the same producer session. It does not automatically recognize two independent sends having identical content or the same event ID.

For example, an application processes an HTTP request twice and calls **KafkaTemplate.send()** twice. Those two calls can produce two valid records in Kafka, even with idempotence enabled. Likewise, if the application resends a record itself after a future reports an ambiguous failure, the new call can produce another record.

For business-level deduplication, generate stable event IDs, persist publish state durably when needed, and design idempotent consumers. Producer idempotence and business idempotency solve two distinct layers of problems.

## 5. Default Values and Limits

Kafka producers typically default to:

~~~properties
max.in.flight.requests.per.connection=5
~~~

Valid values must be positive integers. With idempotence enabled, the maximum supported value is 5. With idempotence disabled, the client may allow higher values, though retries with multiple in-flight requests can alter record ordering.

| Value | Behavior | When to consider |
|---|---|---|
| **1** | Only one unacknowledged request per connection | Needed to serialize requests on a connection and accept lower throughput; typically chosen when not using idempotence yet still avoiding retry reordering. |
| **2 to 4** | Allows moderate pipelining | Worth testing when balancing pending request count against network utilization. |
| **5** | Allows up to five in-flight requests per connection | Common value, compatible with idempotent producer, and usually a sensible starting point. |
| **Greater than 5** | Accepted when idempotence is disabled | Incompatible with idempotence; must understand retry reordering risks and only consider after load benchmarking. |

Do not drop to 1 out of habit. If the producer already enables idempotence, a value of 5 allows pipelining while maintaining ordering within Kafka producer guarantees. Setting 1 forces each broker connection to wait a full response round trip before sending the next request, making network latency dominate throughput.

Conversely, do not raise the value arbitrarily. With idempotence enabled, values over 5 are incompatible. With idempotence disabled, multiple in-flight requests plus retries can reorder records in a partition.

## 6. Configuring in Spring Boot and Spring Kafka

**max.in.flight.requests.per.connection** is a Kafka client property. Spring Boot passes extra properties under **spring.kafka.producer.properties** down to the Apache Kafka producer.

Example in **application.yml**:

~~~yaml
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
~~~

Bracketed keys preserve dotted Kafka property names when Spring Boot binds the map. An equivalent declaration in **application.properties**:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.retries=2147483647
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
~~~

Configuration meaning:

- **acks=all**: waits for acknowledgements from replicas currently in the ISR.
- **enable.idempotence=true**: prevents duplicates from internal producer retries and preserves batch order within supported limits.
- **max.in.flight.requests.per.connection=5**: allows up to five unacknowledged requests per broker connection.
- **retries**: allows the producer to retry retriable errors; **delivery.timeout.ms** still bounds total record delivery time.
- **request.timeout.ms**: caps response wait time for a single request.
- **delivery.timeout.ms**: caps total time the producer spends trying to deliver a record, including batch waiting, requests, and retries.

Timeout values in the example are only starting points. Tune them according to network latency, broker recovery time, and system SLOs. **max.in.flight.requests.per.connection** neither replaces timeouts nor determines how long the producer retries.

If building the producer via Java configuration instead of Spring Boot auto-configuration, pass Kafka client properties directly:

~~~java
Map<String, Object> producerProps = new HashMap<>();
producerProps.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092");
producerProps.put(
        ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
        true);
producerProps.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5);
producerProps.put(
        ProducerConfig.ACKS_CONFIG,
        "all");

ProducerFactory<String, String> producerFactory =
        new DefaultKafkaProducerFactory<>(producerProps);

KafkaTemplate<String, String> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
~~~

This snippet illustrates setting properties on the producer factory. In real applications, add serializers, bootstrap servers, security, and environment-appropriate properties.

### When the Producer Uses Transactions

Kafka's transactional producer also builds on idempotence. When Spring Kafka configures **transaction-id-prefix**, producers are created with a transactional ID and idempotence is used. In that case, still keep **max.in.flight.requests.per.connection** no greater than 5.

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-a-
      acks: all
      properties:
        "[max.in.flight.requests.per.connection]": 5
~~~

The prefix must yield a unique transactional ID for each concurrently running application instance. The in-flight property only controls pending request count; it does not start transactions, commit transactions, or replace transaction manager configuration.

## 7. Choosing a Value Based on Requirements

### Standard Case: Idempotence Enabled

For modern business producers, start with **enable.idempotence=true** and **max.in.flight.requests.per.connection=5**. This is a balanced choice: the producer can send multiple requests per connection, cut round-trip wait time, and maintain partition batch order during retries.

No need to drop to 1 just because the system requires events with the same key to stay ordered. Ensure events with the same key route to the same partition while keeping idempotence enabled.

### When Idempotence Is Disabled

If idempotence is disabled, consider the relationship between retries and ordering:

- If retries equals 0, the producer does not retry failed requests; retry-induced reordering cannot occur, but records can be lost on transient errors.
- If retries exceeds 0 and in-flight exceeds 1, records can be reordered within a partition when an earlier request requires retry.
- If ordering must be preserved across retries without enabling idempotence, setting 1 serializes requests per connection at the cost of lower throughput.

Whenever possible, enable idempotence instead of relying on **max.in.flight.requests.per.connection=1** to compensate for disabling idempotence. Idempotence handles both retry duplicates and sequence order while allowing pipelining.

### High-Throughput Scenarios

With high network latency, allowing only one in-flight request can leave connections idle while the producer waits on brokers. Allowing multiple in-flight requests hides part of the round-trip time. However, final throughput still depends on partition count, batch size, linger, compression, broker speed, replication, disk, and network.

You cannot assume raising the value from 1 to 5 will increase throughput by exactly five times. Requests vary in size, brokers may be the bottleneck, and the producer may be limited by serialization or buffers.

Measure under near-production load:

1. Hold partition count, replication, payload, and record emission rate constant.
2. Compare values 1 and 5 with idempotence enabled.
3. Track throughput, p95/p99 latency, request latency, retry rate, and buffer waits.
4. Test behavior during broker leader changes or transient network latency/errors.
5. Pick the value that meets SLOs with reasonable resources.

## 8. Impact on Latency and Backpressure

Low values reduce pending requests, yet also underutilize connections. If a broker responds slowly, the producer must wait for a response before sending more requests. One slow request can force subsequent batches to wait on the producer side even when ready.

High values let the producer keep sending requests while earlier requests are still being processed. This typically helps when network round trips account for a substantial portion of send time. However, it does not make brokers process faster and does not remove broker resource limits.

When the producer generates records faster than brokers can process:

1. In-flight requests fill the allowed slots.
2. New batches pile up in the accumulator when they cannot be sent.
3. Producer buffer utilization rises.
4. When the buffer lacks space, **send()** may block waiting for buffer allocation up to **max.block.ms**.
5. If a buffer cannot be acquired in time, the application can receive **TimeoutException**.

Therefore, raising the in-flight limit is not a fix for every bottleneck. Inspect broker latency, batch size, compression, partition count, buffer memory, publish rate, and buffer allocation wait times.

## 9. Monitoring in Production

When tuning **max.in.flight.requests.per.connection**, monitor metrics reflecting both send capacity and waiting levels:

| Metric | Meaning during investigation |
|---|---|
| **requests-in-flight** (if exposed per node by client/exporter) | Number of requests awaiting response on a broker connection. |
| Average and max request latency | Time brokers take to respond to requests; high latency can keep in-flight slots occupied longer. |
| Record send rate / byte rate | Rate at which the producer sends records and volume. |
| Record retry rate | How often the producer retries; sudden spikes may indicate unstable brokers or network. |
| Record error rate | Final send failure rate. |
| Record queue time | Time records wait in the producer before sending. |
| Buffer pool wait time | Time the producer waits for buffer space, useful under backpressure. |
| Batch size and compression rate | Indicates batching and compression efficiency. |

Exact metric names and exporter presentation can vary by Kafka client version and observability stack. Check the actual metrics exposed by your running client rather than assuming every exporter publishes identical names.

Common signals and investigation directions:

- Low throughput, high request latency, **max.in.flight** set to 1: test value 5 with idempotence enabled to evaluate pipelining gains.
- Rising retry rate and rising request latency: investigate brokers, leader elections, network, and replication before increasing limits.
- Rising buffer waits: the producer is experiencing backpressure; check publish rate, broker capacity, and batch configuration.
- Producer fails to initialize after property change: check **enable.idempotence**, **acks**, **retries**, and the maximum limit of 5.
- Records reordered: verify idempotence is actually enabled, whether application-level resends occur, or whether multiple producers write to the same partition.

## 10. Common Misconceptions

**Value 5 means only five records are sent at once.** False. It is the count of unacknowledged requests per broker connection. One request can contain many records across multiple batches.

**Value 5 is a cluster-wide total request limit.** False. The limit is enforced per broker connection.

**KafkaTemplate.send() is asynchronous, so the in-flight limit does not matter.** False. The async API avoids blocking callers immediately, while the Kafka producer still manages pending requests on each connection.

**Setting 1 is always the best way to preserve order.** False. It serializes requests on a connection and can hurt throughput. With idempotence enabled, values up to 5 still preserve ordering within the producer's scope.

**Setting greater than 5 always increases throughput.** False. With idempotence enabled, values above 5 are incompatible. With idempotence disabled, retries can reorder records; brokers or the network may also be the bottleneck.

**Idempotence prevents all duplicate sends.** False. It prevents duplicates from internal producer retries, not two independent **send()** calls for the same business event.

**This property establishes ordering across partitions.** False. Kafka only guarantees ordering within a single partition. Choose an appropriate key for records that must stay ordered.

## 11. Configuration and Verification Procedure

When adding a producer or tuning an existing configuration, follow this sequence:

1. Identify the Kafka client version used by Spring Kafka, as idempotence defaults and some configuration details depend on version.
2. Determine whether the producer needs retries and per-partition record order preservation.
3. Enable **enable.idempotence=true** for producers needing reliability.
4. Set **acks=all**, allow retries, and keep **max.in.flight.requests.per.connection** between 1 and 5.
5. Start with value 5 unless measured evidence justifies lowering it.
6. Ensure records requiring ordering share the same key and route to the same partition.
7. Verify the producer initializes cleanly with no compatibility configuration errors.
8. Measure throughput, latency, retries, and buffer waits under representative load.
9. Test behavior during temporary broker disconnects or leader re-elections.
10. Document final values and rationale so operations can explain and reproduce the configuration.

**max.in.flight.requests.per.connection** is a pipelining tuning knob on the producer. A value of 5 usually fits modern idempotent producers: it utilizes connections better than 1 while maintaining ordering within Kafka producer guarantees. Only lower it when measurements or operational constraints demonstrate a concrete benefit, and always evaluate idempotence, retries, and key/partitioning as a cohesive group.
