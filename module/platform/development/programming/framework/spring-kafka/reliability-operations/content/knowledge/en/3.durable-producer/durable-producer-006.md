# delivery.timeout.ms

In a Kafka producer, **delivery.timeout.ms** sets the time limit the producer allows a record to complete sending and report success or failure to the application. This is one of the most important settings for a durable producer because it determines how much time a record has to wait for batching, wait for broker acknowledgement, and retry on recoverable errors.

In Spring Kafka, this setting is passed to the Kafka producer client via producer properties. It operates on the client side, not as a broker timeout setting. Understanding its exact scope helps applications avoid failing too early during brief cluster hiccups while also avoiding keeping records queued too long during outages.

## 1. What Does delivery.timeout.ms Control?

Calling send on a record does not necessarily translate immediately into a broker request. The producer may hold the record in a buffer for batching, wait for metadata, send requests, wait for acknowledgements, and retry on transient errors. These steps consume time.

**delivery.timeout.ms** caps the total time the Kafka producer allows a record to wait for successful delivery or be declared failed. If the record is not delivered within this deadline, the producer completes the send operation with a timeout error. The application receives the error via the send callback or future.

The send flow can be visualized as follows:

~~~mermaid
flowchart TD
    A["Application calls send(record)"] --> B["Producer queues record in buffer"]
    B --> C["Wait for batching per linger.ms"]
    C --> D["Send Produce request to broker"]
    D --> E{"Received successful acknowledgement?"}
    E -->|Yes| F["Complete future successfully"]
    E -->|No, retriable error| G["Wait retry backoff"]
    G --> H{"Delivery time remaining?"}
    H -->|Yes| D
    H -->|No| I["Complete future with timeout error"]
    E -->|Non-retriable error| J["Complete future with corresponding error"]
~~~

This deadline covers pre-send wait time, broker acknowledgement wait time, and time spent on recoverable retries. The producer may fail earlier if it hits a non-retriable error, exhausts configured retries, or if the batch expires earlier.

This is a producer-side record delivery deadline. It is not consumer business-processing time, not Kafka retention duration, and not the maximum duration for an entire HTTP request passing through the application.

## 2. Distinguishing Related Timeouts

Do not tune `delivery.timeout.ms` in isolation. Several producer properties directly relate to record delivery duration while governing different stages.

| Configuration | Scope | Meaning |
|---|---|---|
| **delivery.timeout.ms** | Entire delivery of one record | Caps total time the producer waits to report send outcome |
| **request.timeout.ms** | Single request to a broker | Caps how long the client waits for a response to one request |
| **linger.ms** | Before sending a batch | Time the producer can wait for extra records to build a more efficient batch |
| **retry.backoff.ms** | Between retry attempts | Wait interval before retrying a failed request |
| **retries** | Number of retry attempts | Caps retry count if configured to a finite limit |
| **max.block.ms** | Certain synchronous steps in send | Caps how long a send call waits for metadata or buffer allocation when the producer cannot yet accept the record |

### 2.1 request.timeout.ms: Limit for a Single Request

When a producer sends a Produce request to a broker, the client must wait for a response. **request.timeout.ms** caps how long to wait for that request's response.

If the broker or network does not respond within this time, the client treats the request as failed. If the error is retriable and the record still has time left under the delivery deadline, the producer may resend the request.

For example, request timeout is 30 seconds. A request receiving no response after that period can be retried. A record with a 120-second delivery timeout may go through multiple request and retry cycles, depending on backoff, network conditions, and remaining retries.

Thus, `request.timeout.ms` is a per-request limit, whereas `delivery.timeout.ms` is a per-record time budget.

### 2.2 linger.ms: Batch Accumulation Wait Time

The producer can hold records in the accumulator briefly before sending to group multiple records for the same partition into one batch. **linger.ms** controls this extra wait time.

A larger linger value can improve batching, reduce request counts, and boost throughput under certain workloads. In exchange, records may wait longer before being sent. Batch wait time counts against the delivery timeout budget.

If delivery timeout is set too close to request timeout while still allowing time for linger, the configuration may be invalid or leave insufficient time for a send cycle. Kafka requires:

\[
delivery.timeout.ms \ge request.timeout.ms + linger.ms
\]

For example, with a 30,000 ms request timeout and 5 ms linger, delivery timeout must be at least 30,005 ms. In practice, leave headroom for retries and cluster jitter instead of setting it at the bare minimum.

### 2.3 retry.backoff.ms and retries

When a request hits a recoverable error, the producer may wait **retry.backoff.ms** before trying again. Backoff time also consumes the delivery timeout budget.

**retries** caps retry attempts if configured as a finite number. Therefore, a record can fail before the delivery deadline if retry attempts run out. Conversely, if retries remain but the delivery deadline expires, the producer does not keep trying merely because retries are left.

In modern Kafka clients, delivery timeout is the primary overall bound on the retry process. Do not rely on a large `retries` value to infer the producer will try forever; the record delivery deadline still caps total time.

### 2.4 max.block.ms Does Not Replace delivery.timeout.ms

A producer may have to wait for topic metadata or free buffer space before it can accept a record. **max.block.ms** limits certain synchronous waits inside the send call.

Delivery timeout governs record delivery lifecycle once the producer accepts the record into the send pipeline. Max block controls how long the send call waits to proceed when metadata or buffer space is unavailable. Thus, the duration observed by the application thread around a send call can be affected by both settings.

If an application hits errors waiting for metadata or buffers, merely increasing delivery timeout does not solve the root cause. Check bootstrap servers, metadata, cluster connectivity, buffer size, send rate, and producer health.

## 3. Relationship to acks and Data Durability

Delivery timeout only answers **how long at most the producer waits for an outcome**. It does not determine what acknowledgement level the broker requires, nor does it by itself prevent data loss.

The **acks** property defines the acknowledgement level the producer requires:

- **acks=0**: producer does not wait for broker acknowledgement. Acknowledgement wait deadlines do not carry the same guarantee semantics as acknowledged modes.
- **acks=1**: producer waits for the partition leader to confirm writing the record.
- **acks=all**: producer waits for replicas currently in the ISR to confirm according to Kafka semantics.

For high-durability flows, applications usually combine `acks=all` with appropriate replication factor and `min.insync.replicas` on the cluster side. For example, a topic with replication factor 3 and `min.insync.replicas` 2 can continue accepting writes with `acks=all` when at least two replicas remain in the ISR. If ISR drops below threshold, the broker can reject writes to protect the configured durability level.

Example producer configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
~~~

In this example:

- The producer requires acknowledgements per `acks=all`.
- Idempotence is enabled so the Kafka producer can handle internal retries without creating duplicates from resends within the same producer session.
- Each record has a maximum delivery budget of 120 seconds.
- A single request is capped at a 30-second response wait.
- The producer may wait up to 5 extra ms to form batches.

These values are only starting examples. They must be tuned for actual latency, disruption tolerance, SLOs, and the deployment environment's broker settings.

**Increasing delivery.timeout.ms does not make records more durable.** It merely gives the producer more time to try completing the send. Durability depends on acknowledgements, replication, ISR, cluster state, and related storage decisions.

## 4. Configuring delivery.timeout.ms in Spring Kafka

### 4.1 Spring Boot application properties

Spring Boot lets you pass Kafka client properties through the **spring.kafka.producer.properties** map. Delivery timeout is a Kafka producer client property, so it can be configured here:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      acks: all
      properties:
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
        "[enable.idempotence]": true
~~~

Equivalent properties format:

~~~properties
spring.kafka.bootstrap-servers=broker-1:9092,broker-2:9092
spring.kafka.producer.acks=all
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[linger.ms]=5
spring.kafka.producer.properties[enable.idempotence]=true
~~~

Putting properties in the map ensures Spring Boot passes the exact Kafka client property names, including the dots in **delivery.timeout.ms**. Do not confuse this property with a timeout managed by the Spring listener container.

### 4.2 Configuring via ProducerFactory

If the application builds `ProducerFactory` manually, properties can be set directly in producer configuration:

~~~java
Map<String, Object> props = new HashMap<>();

props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

ProducerFactory<String, OrderCreated> producerFactory =
        new DefaultKafkaProducerFactory<>(props);

KafkaTemplate<String, OrderCreated> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
~~~

Constants in **ProducerConfig** help avoid typos in property names. If the application uses shared producer settings created by Spring Boot, keep configuration in one consistent place so custom ProducerFactory values do not accidentally override application properties.

### 4.3 Choosing Values by Environment

Several selection guidelines:

| Environment / workload profile | Configuration direction |
|---|---|
| Local development | Shorter deadlines can surface misconfigurations quickly, while still satisfying the relation with request timeout and linger |
| Stable production with retries | Allocate enough budget for several request and backoff cycles during brief disruptions |
| Cross-region networks or broker failover | Measure actual latency and recovery duration before choosing a longer deadline |
| APIs with tight response deadlines | Clarify whether the API awaits Kafka acknowledgement or writes via outbox and returns; align deadlines across layers |
| Systems with slow downstream services | Distinguish producer delivery timeout from downstream DB/API timeouts; do not stretch Kafka timeouts to mask failures in another service |

Modern Kafka clients typically default delivery timeout to **120,000 ms**. Still, check the exact Kafka client version your Spring Kafka application uses, as defaults and configurability can change across versions.

## 5. Observing Timeouts in Spring Kafka

In modern Spring Kafka versions, **KafkaTemplate.send** returns a CompletableFuture. Applications should attach callbacks to handle both success and failure outcomes.

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error(
            "Kafka delivery failed for eventId={}",
            event.eventId(),
            error
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
        "Kafka delivery acknowledged: eventId={}, topic={}, partition={}, offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

When the record delivery deadline expires, the future completes with an error. Depending on version and integration layer, the exception seen by the application may be wrapped by Spring in another exception; inspect the root cause rather than just comparing message strings.

Callbacks should log enough context for tracing: event ID, topic, appropriate key, error type, and timestamp. Avoid logging entire sensitive payloads. Callbacks should also stay brief; if time-consuming recovery work is needed, offload it to a controlled executor or background mechanism.

### 5.1 Synchronous Sends and Caller-Layer Timeouts

Applications can call **future.get(timeout)** to limit how long a thread waits for the result. That is an application-side wait timeout, distinct from `delivery.timeout.ms`.

For instance, if an HTTP thread waits only 3 seconds while the producer has a 120-second delivery timeout, `get` can expire after 3 seconds before the producer declares the record failed. The thread stopping its wait does not prove Kafka canceled the send. The record may still be acknowledged by the broker afterward.

Therefore distinguish:

- **Delivery timeout**: Kafka producer decides success or failure of record delivery within its budget.
- **Caller wait timeout**: application thread stops waiting for the result after an application-chosen time.
- **HTTP/request timeout**: gateway, server, or HTTP client terminates the request per its own deadline.

Do not treat a `future.get` timeout as proof the record never entered Kafka. If the application returns an error to the caller and then resends the same business action as a new event, duplicate processing can occur.

## 6. What Happens When delivery.timeout.ms Expires?

When a record cannot be delivered within the deadline, the producer completes the send operation with a timeout error. The application must decide how to persist knowledge of the failed event, whether to retry at the business layer, and how to avoid losing or duplicating events.

Several scenarios must be distinguished:

### 6.1 Broker Temporarily Unavailable

The producer may have failed to send the request or received no response. If the broker recovers before the deadline expires and the error is retriable, the producer can succeed. If the deadline expires before recovery, the future reports an error.

Increasing the deadline can help ride out a short disruption. But if the cluster stays down for long, raising timeouts only makes the application wait longer before receiving an error. It neither recovers brokers nor fixes network faults.

### 6.2 Broker Wrote the Record but Acknowledgement Was Lost

A trickier case occurs when the broker received and wrote the record, yet the response never made it back to the producer due to a dropped network connection. The producer lacks confirmation of success. After retries or deadline expiration, the application may receive an error even though the record was written to Kafka.

Therefore, **a timeout does not always mean the broker definitely did not store the record**. The outcome may be indeterminate from the producer's standpoint.

Producer idempotence helps Kafka handle duplicates from internal producer retries within the producer session and protocol scope. However, if the application initiates a new send after a timeout—especially after a restart or via a different producer session—idempotence does not replace business-layer idempotency.

The proper protection is attaching a stable event ID to the event so consumers can recognize and handle redelivery safely. If the event originates from a database change, transactional outbox persists the business change and publish intent in the same transaction; the publisher can keep retrying unacknowledged outbox rows.

### 6.3 Producer Overloaded or Insufficient Buffer

If the producer sends faster than brokers can ingest, batches can wait a long time in the accumulator. Buffer pressure can also force send-calling threads to wait for memory allocation and hit `max.block.ms`.

In this situation, increasing delivery timeout can make records wait even longer and keep queues holding data for extended periods. Inspect send rate, batch size, buffer memory, sender thread count, broker throughput, and network health before raising the deadline.

### 6.4 Broker Returns a Non-Retriable Error

Some errors are configuration or application-side Kafka client errors, such as authorization failure or serialization errors. Non-retriable errors are reported early without waiting for the full delivery timeout.

If all errors get blamed on timeouts, operations teams can miss the true cause. Classify exceptions and follow the cause chain.

## 7. Building a Safe Retry Strategy

Delivery timeout terminates one producer-side delivery attempt for a record. It does not by itself dictate how the application should retry the business operation.

A retry strategy should have three layers:

1. **Producer internal retries**: handle transient failures within the Kafka client's retries and delivery timeout limits.
2. **Durable application retries**: if sending fails, persist the need to resend in an outbox or durable store instead of holding it only in memory.
3. **Consumer/business idempotency**: if the same event is delivered multiple times, side effects are not executed redundantly.

For example, a publisher reads unsent outbox rows, sends events using KafkaTemplate, and marks rows published only after receiving acknowledgement. If the process stops after Kafka wrote the event but before updating the outbox status, the publisher may resend that event. Consumers must recognize the event ID to handle repeats safely.

Do not write an infinite retry loop directly inside a send callback. Such a loop can tie up threads, generate heavier load while brokers are already overloaded, and stretch requests indefinitely. Retries need backoff, rate limits, durable state, and observability.

### 7.1 Idempotence Does Not Replace Business Idempotency

Enabling **enable.idempotence=true** helps the producer prevent duplicates caused by the producer's own protocol retries. It does not guarantee a business operation is emitted strictly once in all scenarios.

For example, an order service sends an `OrderCreated` event. The broker writes the event, yet the acknowledgement is lost. The application times out and triggers a new send after restarting. If the new event carries a different ID, consumers may treat it as a fresh event and create a second side effect.

If the event ID is stable per business transaction, consumers can check an inbox table or unique constraint before applying side effects. This protection layer is essential when send outcomes are indeterminate.

## 8. Tuning Delivery Timeout to SLOs

No single delivery timeout fits every application. The value must reflect the outage window the system aims to self-heal across, acceptable producer latency, and caller-layer deadlines.

When selecting a value, answer:

- What is the maximum time the application can wait for Kafka to acknowledge a record?
- How long does the cluster typically take to recover a broker or leader during failover?
- What is high-percentile request latency under production load?
- Does the producer need significant batching time?
- How much time do retries and backoff require?
- Do API callers or job schedulers have shorter deadlines than the producer?
- If sending fails, does the application have an outbox or durable replay mechanism?

An illustrative configuration for a producer needing durability might be:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
~~~

A 120-second value gives the producer a budget longer than a single request timeout to handle disruptions and retries. It is only an example. If the SLO demands failing within 5 seconds, a 120-second config may not suit a synchronous request path; revisit the send architecture, caller deadlines, and outbox pattern instead.

Do not drop request timeout too low to force fast failures in every case. Too short a timeout can turn normal latency jitter into continuous retries. Nor should delivery timeout be raised endlessly: long-waiting records occupy buffers, delay alerts, and make business recovery times unpredictable.

## 9. Monitoring the Producer to Pinpoint Timeout Sources

When delivery timeouts occur, inspect both send results and producer health. Counting timeout exceptions alone is insufficient to distinguish slow brokers, network faults, or producer congestion.

Useful Kafka producer metrics include:

| Metric | What to observe |
|---|---|
| **record-error-rate** | Frequency of failed record sends |
| **record-retry-rate** | Frequency of producer retries |
| **request-latency-avg / request-latency-max** | Broker request response latency |
| **record-queue-time-avg / record-queue-time-max** | Time records spend in the producer queue before sending |
| **bufferpool-wait-time** | Time the producer waits for buffer space |
| **bufferpool-wait-ratio** | Ratio of time the producer spends waiting for buffer space |
| **requests-in-flight** | Number of requests currently awaiting response |

Combine metrics with logs containing event ID, topic, partition once metadata is available, exception type, send time, and outbox status. If request latency rises alongside record queue time, check broker load, network, and batching. If buffer wait climbs, check producer rate, buffer memory, and batch drain capacity. If authorization or serialization errors appear, increasing delivery timeout will not fix the root cause.

In Spring Boot, Kafka client metrics can integrate with application observability depending on Micrometer configuration and Spring Boot version. Confirm which metrics are actually exported in your deployment environment and set alerts against system baselines.

## 10. Incident Procedure for Delivery Timeouts

When a producer begins reporting delivery timeouts, investigate in order:

1. **Determine scope**: is one topic, one producer instance, one broker leader, or the entire application affected?
2. **Check root exception**: is the error a request timeout, metadata error, authorization error, serialization error, or something else?
3. **Check latency**: did request latency and record queue time climb before the timeouts?
4. **Check buffers**: is the producer waiting on buffer space or are multiple threads blocked?
5. **Check cluster**: broker availability, leader changes, ISR, request handler saturation, and network.
6. **Verify deadlines**: are delivery timeout, request timeout, linger, retry backoff, and caller deadlines compatible?
7. **Determine business state**: could the record have been written while the acknowledgement was lost? Are stable event IDs and deduplication in place?
8. **Controlled recovery**: restore connectivity or cluster health, allow bounded producer retries, then process pending outbox rows and monitor for duplicates.

Do not simply increase delivery timeout as soon as an incident hits. First determine whether records stalled in batching, request, retry, or buffering. Only adjust the matching timeout or capacity after identifying the cause.

## 11. Common Configuration Errors and Misconceptions

| Misconception | Consequence | Correct understanding |
|---|---|---|
| Delivery timeout is a broker timeout | Adjusting the wrong side | It is a Kafka producer client property |
| Increasing delivery timeout guarantees no lost records | False sense of security | Durability still depends on acks, replication, ISR, and application recovery |
| Request timeout and delivery timeout are the same | Unreasonable deadlines chosen | Request timeout caps one request; delivery timeout caps the entire record delivery process |
| Timeout means the broker did not write | May resend and create duplicates | The broker may have written while the acknowledgement was lost |
| Future.get timeout cancels the send | Application may resend while the old record is still in flight | Caller timeout only stops that thread from waiting |
| High retries means trying forever | Records can still expire | Delivery timeout is the overall deadline |
| Longer timeouts always improve reliability | Delays error detection and holds records longer | Must balance recovery time, SLOs, buffers, and incident handling |

A common configuration mistake is setting delivery timeout smaller than the sum of request timeout and linger. The Kafka client requires delivery timeout to be at least the sum of those two values. Whenever modifying either value, re-verify this relationship so the producer does not fail to initialize.

## 12. Pre-Production Producer Checklist

**Timing configuration**

- [ ] Delivery timeout is set according to SLO and cluster recovery capability.
- [ ] Delivery timeout is greater than or equal to request timeout plus linger.
- [ ] Request timeout reflects real latency and is not too low.
- [ ] Retry backoff and retry count fit the record delivery budget.
- [ ] Max block is evaluated separately for metadata and buffer allocation.

**Durability and error handling**

- [ ] Acks matches the durability requirement of the flow.
- [ ] Topic replication factor and `min.insync.replicas` are confirmed with the platform team.
- [ ] Producer idempotence is enabled where appropriate.
- [ ] Application handles failed futures/callbacks and records event IDs.
- [ ] Timeouts are treated as potentially indeterminate outcomes when acknowledgements are lost.
- [ ] Business-level idempotency and outbox mechanisms exist if durable replay is required.

**Observability and operations**

- [ ] Metrics exist for record errors, retries, request latency, queue time, and buffer wait.
- [ ] Logs contain event ID and sufficient tracing context without exposing sensitive payloads.
- [ ] Alerts exist when timeouts rise above baseline.
- [ ] Runbooks distinguish broker, network, buffer, metadata, and configuration errors.
- [ ] Broker unavailability, failover, lost acknowledgements, and producer restarts have been tested.

## 13. Operational Principles

**delivery.timeout.ms is the time budget for the Kafka producer to finish delivering a record.** It works alongside `request.timeout.ms`, `linger.ms`, `retry.backoff.ms`, and `retries` to decide how long the producer waits before returning a result to the application.

In Spring Kafka, configure this property in producer properties, observe the future from `KafkaTemplate`, and connect send failures to a durable recovery workflow. Pair it with `acks` and replication to achieve the desired durability level, and use event IDs plus idempotent consumers to handle indeterminate send outcomes.

A durable producer needs clear deadlines, bounded retries, observable root causes, and the ability to recover after process or connectivity failures.
