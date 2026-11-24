# request.timeout.ms in Spring Kafka Producer

In Spring Kafka, the **request.timeout.ms** property defines how long the Kafka producer waits for a response to a single request sent to a broker. If the broker does not reply within this time, the producer treats the request as timed out and may retry under the current configuration; when no further retries are possible, the send fails.

This is part of operating a durable producer. Too low a value can trigger unnecessary retries when a broker or network is temporarily slow. Too high a value delays incident detection in the application. To configure it properly, consider request timeout alongside delivery timeout, retries, acknowledgements, and how the application observes send outcomes.

## 1. What Does request.timeout.ms Control?

A Kafka producer sends requests over TCP connections to brokers. When configured to wait for acknowledgements, the producer must receive a response to know how the broker processed the request. `request.timeout.ms` is the response wait limit for that single request.

Simple flow:

~~~text
Application
   |
   | producer.send(record)
   v
Kafka producer
   |
   | ProduceRequest
   v
Kafka broker
   |
   | process request, write record, and build response
   v
Kafka producer
   |
   +--> receive response before timeout: proceed per broker result
   |
   +--> no response in time: timeout, may retry
~~~

In the Kafka Java producer, the common default for `request.timeout.ms` is 30,000 ms (30 seconds). Confirm the default for the exact Kafka client version your application uses; Spring Boot normally passes this setting to the Kafka client via producer properties.

The value is specified in milliseconds. For example, 45,000 equals 45 seconds.

Keep in mind that a timeout only indicates the producer did not receive a response on time. It **does not prove the broker failed to write the record**. The broker may have written it successfully while the response was lost in transit or arrived too late. Thus, after a request timeout, the send outcome can remain ambiguous to the application.

## 2. Distinguishing request.timeout.ms from Other Timeouts

A producer has multiple time limits. Each setting protects a different part of the send pipeline.

| Setting | Scope of control | When time expires |
|---|---|---|
| request.timeout.ms | Response wait time for a single request to a broker | Request may be retried or fail |
| delivery.timeout.ms | Total maximum time for producer to report send result after send is called | Record delivery expires and future completes with error |
| max.block.ms | Time a send call may wait for metadata or buffer space | The send call may throw TimeoutException before returning a future |
| Future.get(timeout) | Time application code waits for the future result | Only the application wait call expires; background send may continue |

### request.timeout.ms and delivery.timeout.ms

These are the two settings most frequently confused.

- `request.timeout.ms` caps how long to wait for a response to one specific request.
- `delivery.timeout.ms` caps the total time the producer is allowed to complete delivering a record, measured from when send returns. This time includes batch waiting, acknowledgement waiting, and retries for recoverable errors.

Kafka requires `delivery.timeout.ms` to be greater than or equal to the sum of `request.timeout.ms` and `linger.ms`. If you increase request timeout, check delivery timeout so the configuration remains valid.

Example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

With the configuration above, one request can wait up to 45 seconds for a response; the producer has a total record delivery budget of 120 seconds. That overall budget allows the producer to handle multiple retry cycles if other conditions permit.

Do not mistake `delivery.timeout.ms` for the wait time of a single request. If brokers respond slowly repeatedly or requests must retry, total record delivery time is the critical limit governing the final outcome.

### request.timeout.ms and max.block.ms

`max.block.ms` can block the `send` call itself when the producer needs to fetch metadata or wait for free buffer space. Once metadata is ready and the record enters the send pipeline, the producer continues asynchronously.

Thus, there are two distinct phases:

1. The `send` call needs metadata or buffer space. `max.block.ms` caps waiting during this phase.
2. The record is inside the producer. `request.timeout.ms` and `delivery.timeout.ms` govern waiting for responses and completing record delivery.

Increasing `request.timeout.ms` does not resolve producer buffer exhaustion or metadata fetch failures. When `send` blocks, inspect buffer memory, send rate, metadata, and `max.block.ms`.

### request.timeout.ms and Future.get(timeout)

Spring Kafka returns a future for the send result. If code calls `future.get(2, TimeUnit.SECONDS)`, two seconds is the application code's wait limit. It does not alter `request.timeout.ms` and does not automatically cancel the request being processed by the producer.

Example:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", order).get(2, TimeUnit.SECONDS);
~~~

If two seconds pass before the future completes, the `get` call can throw `java.util.concurrent.TimeoutException`. The producer may still finish sending afterward. The application must explicitly handle continuing to track the future and avoid sending a brand-new record merely because the waiting code timed out.

## 3. How Request Timeout Interacts with acks

How long a producer waits for a response is influenced by the acknowledgement policy.

| acks | Meaning | Relationship with request timeout |
|---|---|---|
| 0 | Producer does not wait for broker record acknowledgement | No acknowledgement response to wait for on ProduceRequest in the normal sense |
| 1 | Partition leader acknowledges after writing record to local log | Waits for response from the leader |
| all | Replicas currently in ISR acknowledge per Kafka rules | May wait longer when ISR replicas are slow or ISR changes |

For systems needing high durability, producers typically use `acks=all` paired with appropriate `min.insync.replicas` on brokers/topics. When the ISR replica count drops below `min.insync.replicas`, the broker can reject writes rather than acknowledging a write below the configured durability level.

`request.timeout.ms` should be long enough to cover reasonable broker response times under normal load and replication conditions. If set too low, the producer may retry while the broker is still processing the original request.

Kafka documentation recommends setting `request.timeout.ms` larger than the broker's `replica.lag.time.max.ms` to reduce unnecessary retries caused by slow broker or replica responses. Evaluate these two settings together, especially when using `acks=all`.

## 4. Configuring request.timeout.ms in Spring Boot

Spring Boot provides producer properties configuration to pass Kafka client settings. `request.timeout.ms` is a Kafka producer property, so place it in the producer's `properties` map.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

Key points to note:

- `acks: all` requires broker acknowledgement per ISR.
- `enable.idempotence: true` enables the idempotent producer so Kafka safely handles retries performed by the producer within the same producer session.
- `request.timeout.ms`: 45 seconds is an illustrative example, not an optimal value for every environment.
- `delivery.timeout.ms`: 120 seconds is the overall record delivery budget in the example.
- `linger.ms`: 5 ms is the maximum batching wait before sending under suitable conditions.

The bracketed key syntax ensures Spring Boot preserves dotted Kafka property names when binding the map. If the application uses `application.properties`, it can be declared as:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[request.timeout.ms]=45000
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[linger.ms]=5
~~~

If the application builds `ProducerFactory` manually instead of using Spring Boot auto-configuration, add the property to the configuration map passed to `DefaultKafkaProducerFactory`. Ensure `KafkaTemplate` uses that exact `ProducerFactory`; if multiple producer factories exist, placing the setting on a factory unused by the listener or template has no effect.

## 5. Sending Records and Observing Results in Spring Kafka

Do not treat calling `KafkaTemplate.send` as proof the broker acknowledged the record. Sending occurs asynchronously; the application must handle completion or failure outcomes.

Example with a Spring Kafka version providing the `CompletableFuture` API:

~~~java
@Service
public class OrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders", event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        handleSendFailure(event, exception);
                        return;
                    }

                    var metadata = result.getRecordMetadata();
                    log.info(
                            "Published order event: topic={}, partition={}, offset={}",
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset()
                    );
                });
    }

    private void handleSendFailure(
            OrderCreated event,
            Throwable exception) {
        log.error(
                "Could not publish order event, eventId={}",
                event.eventId(),
                exception
        );
    }
}
~~~

Data type names and business methods in the example are illustrative. Spring Kafka 3.x uses `CompletableFuture` for send results; older versions may use `ListenableFuture`. Use the API appropriate for your project's library version.

When the future completes successfully, the application can read record metadata such as topic, partition, and offset. When the future completes with an error, record the cause and apply the application's recovery policy.

If an error occurs due to a request timeout, do not assume the record was definitely not written. The broker may have processed the request while the producer missed the response. If the application initiates a new send itself, that is an independent send and can create duplicate records.

## 6. Idempotent Producer and Retries After Timeout

A request timeout creates an uncertain situation: the broker may not have received the request, may still be processing it, or may have written the record while the response was lost.

Kafka's idempotent producer helps handle internal producer retries using a producer ID and sequence number. When the producer retries a batch under Kafka's mechanism, the broker can recognize and deduplicate repeated writes belonging to the same sequence chain.

Typical configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
~~~

An idempotent producer has compatibility requirements for `acks`, `retries`, and `max.in.flight.requests.per.connection`. In modern Kafka versions, enabling idempotence requires compatible related settings or the client applies compatible defaults. If overriding these properties, verify the effective configuration when the producer initializes.

Idempotence protects Kafka producer retries within a producer session. It does not automatically recognize two separate `send` calls from business code as the same event. For example, if the application gets a timeout and calls `publish(event)` again, the second call can be treated as a new send.

For critical business events:

- Assign a stable `eventId` before sending.
- Use an idempotent producer to protect internal retries.
- Do not generate a new `eventId` when recovering the same event emission.
- Design idempotent consumers to handle cases where the application resends after an uncertain previous outcome.
- Log `eventId` alongside send errors for investigation and reconciliation.

Do not use a low request timeout paired with continuous resends from the business layer. That pattern can turn a brief network glitch into multiple duplicate records.

## 7. Choosing a Value for request.timeout.ms

No single number fits every Kafka cluster. Choose a value based on actual response times, fault tolerance, and the deadline within which the application needs an outcome.

### When the Value Is Too Low

A low value can cause:

- Requests treated as failed while the broker is still processing them.
- Increased retries during high broker load or slow replication.
- Repeated requests adding network and broker load.
- The application receiving errors sooner than the cluster's realistic recovery window.
- Harder-to-interpret send outcomes if the application re-emits records itself.

For instance, if brokers normally need 8 to 12 seconds to respond during cluster recovery, setting request timeout to 2 seconds can cause the producer to constantly expire and retry right when the cluster needs reduced load.

### When the Value Is Too High

A high value can cause:

- Delayed detection of unresponsive brokers.
- Record futures staying pending longer.
- The application holding more in-flight work awaiting results.
- Prolonged recovery and error-handling times.
- Upstream callers timing out before the producer, creating mismatched waiting states.

For example, if an API calling the producer allows only 10 seconds while Kafka request timeout is 90 seconds, the API may already return an error to the client while the producer keeps trying to send. If the client retries the business action, the system needs idempotency mechanisms to avoid duplicate effects.

### Value Selection Procedure

1. Measure producer request latency under normal and peak loads.
2. Determine acceptable response times during broker leader changes or ISR fluctuations.
3. Set request timeout large enough to avoid false timeouts from normal latency jitter.
4. Set delivery timeout greater than or equal to request timeout plus linger.
5. Compare delivery timeout against timeouts in upstream caller layers.
6. Check `replica.lag.time.max.ms` when using `acks=all`.
7. Test with slow brokers, dropped connections, and leader failovers to observe retries and failure reporting times.
8. Monitor retry rate, send errors, and latency after deployment.

For example, 45 seconds for request timeout and 120 seconds for delivery timeout can serve as a starting point for testing in a system needing a relatively wide recovery window. Tune based on cluster metrics and client version; do not copy these values without measuring.

## 8. Observability and Incident Handling

When a producer reports timeouts, distinguish response errors, connection errors, replica acknowledgement errors, and total delivery time expirations.

Useful signals to monitor:

| Metric or signal | Operational meaning |
|---|---|
| request-latency-avg | Average request response latency |
| request-latency-max | Maximum request response latency |
| record-retry-rate | Frequency of record retries |
| record-error-rate | Rate of failed record sends |
| record-send-rate | Rate of records sent |
| requests-in-flight | Number of requests awaiting processing/response |
| bufferpool-wait-time | Time the producer waits for buffer space |
| Timeout and delivery failure logs | Timestamp, error type, and affected records |

Exact metric names may vary by Kafka client version, exporter, and metrics system. With Spring Kafka, Micrometer can be integrated to export producer metrics and correlate them with application logs.

When investigating a wave of timeouts, check in order:

1. **Network and connectivity:** packet loss, DNS, firewall, TCP connections, connection setup times, and broker disconnect errors.
2. **Brokers:** request handler saturation, CPU, disk latency, network throughput, request queues, and broker logs.
3. **Replication:** ISR shrinks, replica lag, under-replicated partitions, and `min.insync.replicas`.
4. **Producer:** request latency, retry rate, error rate, buffer pool waits, and in-flight request counts.
5. **Timing settings:** `request.timeout.ms`, `delivery.timeout.ms`, `linger.ms`, `max.block.ms`, and application caller timeouts.
6. **Business outcomes:** `eventId`, future states, record metadata on success, and replay history.

### Common Scenarios

**Slow but recovering broker**

Too low a request timeout can make the producer retry endlessly. Check broker latency and load before raising timeouts. If latency increased due to broker overload, raising timeouts only avoids premature failures; it does not fix the overload cause.

**Partition leader changes**

During leader election, the producer may hit connection errors or retriable errors. Retries and idempotence help the producer recover under Kafka's mechanism. Delivery timeout still bounds the record's total wait time.

**ISR fails to satisfy min.insync.replicas**

With `acks=all`, the broker can reject writes when insufficient replicas are in sync. This is a durability condition failure, not simply a request timeout. Raising request timeout cannot create more replicas in the ISR; restore replication or review availability/durability policy.

**Future completes with error after a long wait**

Inspect the root exception, elapsed time from send to error, and retry metrics. If the error is a delivery timeout, the record exceeded its total delivery budget. If application code merely timed out on `Future.get`, the producer may still be processing the record.

**Producer buffer full**

If send calls wait too long for buffer space, examine `max.block.ms`, `buffer.memory`, batch size, broker ingestion rate, and network capacity. `request.timeout.ms` is not the setting that resolves buffer exhaustion.

## 9. Safe Configuration Principles

- Set `request.timeout.ms` based on measured broker and network latency.
- Ensure `delivery.timeout.ms` is greater than or equal to `request.timeout.ms` plus `linger.ms`.
- Use `acks=all` when high durability is required and set `min.insync.replicas` appropriate to replica count.
- Enable idempotent producer when safe retries are required.
- Do not treat timeouts as proof a record was not written.
- Do not resend an event with a new send call unless you have a stable `eventId` and deduplication policy.
- Distinguish Kafka client timeouts from `Future.get` or HTTP caller timeouts.
- Monitor retry rate, request latency, buffer waits, and delivery errors.
- Test slow brokers, disconnects, leader changes, and ISR shrinks before finalizing production settings.
- When using multiple `ProducerFactory` instances, confirm `KafkaTemplate` actually uses the factory configured with the intended `request.timeout.ms`.

## 10. Complete Configuration Example and How to Read It

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

Reading the configuration layer by layer:

- The producer waits up to 45 seconds for a single request's response.
- The producer has a total record delivery budget of 120 seconds from when send returns.
- The producer may accumulate records within the configured linger window before sending a batch.
- The producer requires ISR acknowledgement.
- The producer enables idempotence so Kafka safely handles internal retries.

If the broker responds in 200 ms, requests complete far faster than the 45-second cap. A timeout is an upper bound on waiting for a response, not a delay the producer intentionally waits before every send.

If the broker does not respond, the producer can retry within retry and delivery timeout limits. When total delivery time exceeds delivery timeout, the future fails. If the application handles that error by re-emitting via an independent send command, rely on `eventId` and an idempotent consumer to handle the possibility that the broker already wrote the first record.

In Spring Kafka operations, `request.timeout.ms` must be evaluated alongside `delivery.timeout.ms`, retries, `acks`, idempotence, and application caller timeouts. Proper configuration lets the producer absorb transient latency and errors while still failing within an observable, recoverable window.
