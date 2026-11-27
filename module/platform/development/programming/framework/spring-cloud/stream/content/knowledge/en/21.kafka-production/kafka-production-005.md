# Synchronous Sending, Asynchronous Sending, and Timeouts

When a Spring Cloud Stream application publishes a message to Kafka, the send call can return before the producer receives an acknowledgment result from the broker. This is an important difference between asynchronous and synchronous sending. Asynchronous sending keeps application threads from waiting for each broker acknowledgment; synchronous sending lets the caller wait for the send result and handle errors directly at the call site, at the cost of higher latency and holding threads longer.

In the Kafka Binder, asynchronous sending is the default behavior of the Kafka client. The Kafka Binder provides the `sync` property per output binding to wait for the send result. Whichever mode you choose, timeouts still must be designed together with `acks`, retries, `delivery.timeout.ms`, `request.timeout.ms`, and limits on waiting for metadata/buffers. A send call returning successfully at the application layer does not always mean the broker has durably persisted the message.

This lesson belongs to the **Publishing to Kafka** chapter of the `SPRING_CLOUD_STREAM` module. We will use `StreamBridge` and output bindings to explain the send flow, distinguish channel acceptance from broker acknowledgment, configure synchronous/asynchronous modes, design timeouts, handle errors, and test under load.

## 1. Message send flow through the Kafka Binder

An application can publish messages from a function output or imperatively via `StreamBridge`. In both cases, the Kafka Binder connects the output binding to a Kafka producer.

```text
Application
   |
   | StreamBridge.send(...) or function output
   v
Output binding / MessageChannel
   |
   v
Kafka Binder
   |
   v
Kafka Producer
   |
   | sends record over network
   v
Kafka broker
   |
   | writes log and returns result per acks
   v
Producer callback / send result
```

Steps can complete at different times:

1. The application hands the message to the output binding.
2. The binder invokes the Kafka producer to send the record.
3. The Kafka producer places the record into a buffer and sends it over the network.
4. The broker receives the record, writes it according to replication settings, and returns an acknowledgment.
5. The producer receives the success or error result.

Asynchronous sending generally allows steps 1 and 2 to complete before step 5. Synchronous sending makes the caller wait for the producer result according to binder configuration. Therefore, understand what the caller is actually waiting on before choosing a mode.

## 2. What is asynchronous sending?

The Kafka Java producer has an asynchronous `send()` API: the method enqueues the record into the send pipeline and returns a `Future`/asynchronous result. The producer can batch records, send multiple records concurrently, and receive acknowledgments later. The Kafka Binder typically uses this mode by default to take advantage of producer batching and network I/O.

With `StreamBridge`, imperative code can send messages as follows:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record OrderPlaced(String eventId, String orderId, long total) {}

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderPlaced event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

`StreamBridge.send` returns a `boolean` indicating whether the message was accepted by the output channel under Spring's send mechanism. When the Kafka producer runs asynchronously, a return value of `true` does not itself prove the broker acknowledged the record. Errors occurring after the producer sends the record must be observed through the callback/error handling mechanisms of the binder and Kafka client.

### Advantages

- The caller does not have to wait for a broker acknowledgment on every record.
- The producer can batch records and leverage `linger.ms` and `batch.size`.
- Throughput is typically higher when sending many messages.
- Request-handling or business threads can move on to other work sooner.

### Limitations

- Broker errors can surface after the send method has already returned.
- The caller does not get a direct broker acknowledgment result solely from `StreamBridge.send`'s boolean.
- If the application shuts down too quickly, you must ensure the producer flushes/closes properly to handle pending records.
- Clear asynchronous error observation and handling mechanisms are required.

Asynchronous sending fits flows that can handle failures via retries/outbox or track publish status afterward. Do not treat `true` from `StreamBridge.send` as proof that a business transaction has been durably stored by the broker.

## 3. What is synchronous sending?

The Kafka Binder supports the `sync` producer property. When `sync: true` is enabled, the binder waits for the send result from the Kafka producer before completing the send call under the binder's synchronous mechanism. If the producer encounters an error or times out, the error is propagated back to the caller per framework rules.

Example output binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
```

`sync` is a Kafka binder-specific property located under `spring.cloud.stream.kafka.bindings.<bindingName>.producer`. It is not a generic property applied uniformly across all binders. For RabbitMQ or Pulsar, send acknowledgment semantics and synchronous configuration are governed by their respective binders.

When `sync: true`, a single send call can wait for the broker response. This helps detect publish failures at the call site, but holds the caller thread for the entire wait duration. If the broker slows down, many threads can get blocked simultaneously and exhaust the web server or worker thread pool.

## 4. Comparing the two modes

| Criterion | Asynchronous (`sync: false`, default) | Synchronous (`sync: true`) |
|---|---|---|
| When caller continues | After the message enters the binder/producer send pipeline | After the send result is determined or timeout/error occurs |
| Broker acknowledgment | Arrives later via callback/error handling | Caller waits for the result per producer configuration |
| Call latency | Usually lower | Depends on network, broker, and replication |
| Throughput | Favorable for batching and sending many records | Can be lower if waiting per record |
| Error handling | Requires observing asynchronous errors | Can catch errors at the call site |
| Thread resources | Holds caller threads less | Holds threads for the wait duration |
| Suitable use cases | Event streams, telemetry, outbox relays tracking results | Flows needing publish results before proceeding |

Neither mode automatically guarantees exactly-once delivery. Confirmation quality also depends on `acks`, replication factor, `min.insync.replicas`, idempotent producer settings, and transactions.

## 5. What does `StreamBridge.send` return?

When using Spring Cloud Stream, distinguish three outcomes:

- **Channel accepted:** the output channel accepted the message for forwarding.
- **Broker acknowledged:** the Kafka producer received an acknowledgment per the `acks` setting.
- **Consumer processed:** the consumer received the message and completed its business side effects.

These three milestones are not identical.

```text
StreamBridge.send(...) == true
          |
          v
Message accepted into output channel
          |
          v
Kafka producer sends record
          |
          v
Broker acks per acks setting
          |
          v
Consumer receives and processes
```

If you need `StreamBridge` to wait for broker acknowledgment, enable `sync: true` on the Kafka output binding. Even then, broker acknowledgment still does not prove a consumer has processed the message. If business logic needs confirmation that the consumer finished, it needs a business acknowledgment, reply message, or persisted state in the target system.

If `send` returns `false`, the application should treat that as a signal that the message was not accepted by the channel mechanism and decide whether to retry or return an error. If `send` returns `true` in asynchronous mode, you still need to track the subsequent publish result.

## 6. Kafka `acks` determines the acknowledgment level

Synchronous mode only determines whether the caller waits for the producer result. The Kafka `acks` property determines what level of confirmation the broker must provide:

| `acks` | Meaning | Trade-off |
|---|---|---|
| `0` | Producer does not wait for broker acknowledgment | Low latency, but no broker confirmation; records can be lost without the producer knowing |
| `1` | Partition leader acknowledges after writing the record to the leader's log | Data loss possible if leader fails before followers catch up |
| `all` or `-1` | Leader waits for replicas in the ISR to acknowledge per Kafka configuration | More durable, but depends on ISR and `min.insync.replicas` |

For critical business messages, consider `acks: all` alongside an appropriate replication factor and `min.insync.replicas`. If you only set `sync: true` with `acks: 0`, the caller receives no broker confirmation that the record was written. Synchronous mode cannot create a higher durability guarantee than the Kafka configuration provides.

Example per-binding configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              sync: true
              configuration:
                acks: all
                enable.idempotence: true
```

`enable.idempotence` helps the Kafka producer prevent certain duplicate writes caused by internal producer retries within the scope of a session/producer identity. It does not replace event IDs and consumer-side idempotency when the application resends the same event via a new call or after a restart.

## 7. Types of timeouts during sending

There is no single timeout governing the entire process. Several timeouts apply to different stages:

| Timeout | Scope | When expired |
|---|---|---|
| `max.block.ms` | How long the producer can block waiting for metadata or buffer space | Producer can throw an error if metadata/buffer cannot be obtained within the limit |
| `request.timeout.ms` | How long to wait for a response to a single request sent to a broker | Request may be treated as failed and retried if policy permits |
| `delivery.timeout.ms` | Maximum total time for a record to be sent successfully or fail, including batching, requests, and retries | Producer completes the record with a timeout error if not delivered within the limit |
| Binder synchronous wait timeout | How long the caller waits for the producer result when `sync` is enabled | Caller receives a timeout error per binder mechanism |
| HTTP/business request timeout | How long an external caller waits for the application to respond | Client may time out even while the producer or broker is still processing |

Kafka client properties can be configured in binder configuration or producer configuration. Exact names, placement, and per-binding override support should be checked against the Spring Cloud Stream Kafka binder version in use.

`delivery.timeout.ms` is the Kafka producer-side record delivery bound; it is not an HTTP request timeout. `max.block.ms` typically applies when the producer needs metadata or buffer space before a request is sent. `request.timeout.ms` applies to a single broker request. When combining them, avoid setting a caller timeout much shorter than the time the producer can continue sending in the background without a reconciliation mechanism.

## 8. Example timeout configuration for the Kafka producer

The following example illustrates binder-level producer configuration:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka-1:9092,kafka-2:9092
          configuration:
            acks: all
            enable.idempotence: true
            request.timeout.ms: 30000
            delivery.timeout.ms: 120000
            max.block.ms: 60000
```

These are illustrative values, not an optimal timeout set for every system. `delivery.timeout.ms` must be greater than or equal to the related request/batching limits as required by the Kafka client. When changing `request.timeout.ms`, revisit `delivery.timeout.ms` and total retry duration. When using multiple bindings with different SLAs, configure producer properties per binding if supported by the binder.

Do not set a short timeout just to make requests return quickly if the application has no way to tell whether the broker received the message. A caller timeout can occur while the producer is still waiting or after the broker has already written the record with a delayed response. This is a common source of publish retries and duplicates.

## 9. A timeout does not guarantee the message was not sent

Suppose a producer sends a record to Kafka. The broker writes the record and sends an acknowledgment, but the network drops before the acknowledgment reaches the producer. The producer experiences a timeout while the record is already in the log.

```text
Producer                         Kafka broker
   |                                  |
   |---------- record ---------------->
   |                                  | write record
   |<--------- acknowledgement -------|
   X network timeout before ack received
```

When a caller sees a timeout, the outcome can be **indeterminate**: the record may never have reached the broker, may have arrived without meeting the required write level, or may already have been written while the acknowledgment was lost. If the application generates a new event ID and resends, consumers may treat it as a brand-new event.

For business messages, generate a stable event ID before the first publish attempt and preserve that ID across retries. Consumers use idempotency/inbox patterns to guard against duplicate side effects. For producers that must recover after restarts, store events and publish state in an outbox rather than holding them solely in memory.

## 10. Producer retries and application retries

The Kafka producer has internal retries for recoverable errors. The producer keeps the record in its buffer and retries according to client settings until it succeeds or exceeds `delivery.timeout.ms`. This is client-layer retrying for a single logical send.

An application retry is a new send call—for example, a service catches a timeout and calls `StreamBridge.send` again. If the first send was already written by the broker while the acknowledgment was lost, the new send can create a second record. Producer idempotence handles some internal producer retries, but it does not replace idempotency for a new call from the application.

| Retry layer | Scope | Notes |
|---|---|---|
| Kafka producer retry | One record within one producer send operation | Coordinates with `delivery.timeout.ms` and idempotence |
| Binder/application retry | Re-invoking the publish operation from application or framework | Can create a new send operation |
| Outbox relay retry | Re-reading the same outbox row not yet marked as sent | Must preserve the event ID so consumers can deduplicate |
| Consumer retry/redelivery | Reprocessing a message after receipt | Consumer must be idempotent |

Do not stack retries across multiple layers without accounting for total attempts. For instance, internal producer retries, plus three application retries, plus an outbox relay running again after a restart can multiply record counts unless event IDs and deduplication are maintained.

## 11. Choosing synchronous vs. asynchronous based on business needs

### Synchronous sending fits when

- A request must know immediately whether the publish was acknowledged by the broker per `acks`.
- Processing cannot continue if publishing fails.
- Send rate is moderate and the latency budget permits waiting on the broker.
- The caller has mechanisms to handle timeouts and indeterminate outcomes.

For example, an administrative action that must record an audit event and report the send status to the caller. If the requirement truly means "broker acknowledged," enable the synchronous producer and choose the appropriate `acks`.

### Asynchronous sending fits when

- Throughput and batching matter more than waiting on individual acknowledgments.
- The caller does not need an immediate broker result.
- The system has an outbox, retries, or publish-error tracking mechanisms.
- Messages can be processed independently after the business request finishes.

For example, telemetry or tracking events can be sent asynchronously, provided the system has metrics, error handling, and an explicit data-loss policy.

Do not pick async just for speed if data cannot be lost and no durability mechanism exists. Likewise, do not pick sync for every message, because waiting on the broker for every send can reduce throughput and saturate thread pools.

## 12. Avoiding holding HTTP threads for too long

If a REST request calls `StreamBridge.send` synchronously, the HTTP handler thread waits for the producer result. When Kafka is slow or unreachable, many requests can block threads simultaneously. This drives up latency, exhausts thread pools, and triggers cascading failures.

Mitigations:

- Set reasonable timeouts for both the producer and business requests.
- Limit the number of concurrent requests allowed to wait on Kafka.
- Keep synchronous sends out of critical paths if SLAs do not allow them.
- Use an outbox to persist events in the same business transaction, then have a relay publish asynchronously.
- Monitor producer wait times, in-flight waiting requests, and thread pool saturation.
- Return `ACCEPTED` once the event is durably saved to the outbox; do not report it as broker-received if the relay has not finished sending.

The outbox pattern fits well when a request needs to commit business state quickly while events must be published reliably. The REST request writes business data and the outbox record in the same database transaction; a separate worker sends outbox entries to Kafka and updates their status. Because the worker can publish duplicates after a crash, consumers still need stable event IDs.

## 13. Sending asynchronously while still tracking results

When using the Kafka Binder with `sync: false`, do not ignore publish errors after `StreamBridge.send` returns. Configure and monitor error handling as supported by the binder, log send failures, track producer metrics, and update outbox state if applicable.

If an application needs a concrete `Future`/`CompletableFuture` per record to tie a publish result to a workflow, `StreamBridge.send`'s boolean API does not expose a Kafka record metadata future directly. You can use a Spring Kafka API such as `KafkaTemplate.send(...)` in a dedicated producer component where specific callbacks/metadata are needed; in return, that component uses Spring Kafka directly instead of relying solely on a Spring Cloud Stream output binding.

Example using Spring Kafka to illustrate bounded waiting for a result:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class DirectKafkaPublisher {

    private final KafkaTemplate<String, OrderPlaced> kafkaTemplate;

    DirectKafkaPublisher(KafkaTemplate<String, OrderPlaced> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderPlaced>> publish(
            OrderPlaced event) {
        return kafkaTemplate.send("orders.events", event.orderId(), event);
    }

    public SendResult<String, OrderPlaced> publishAndWait(OrderPlaced event)
            throws Exception {
        return publish(event).get(5, TimeUnit.SECONDS);
    }
}
```

In modern Spring Kafka, `KafkaTemplate.send` returns `CompletableFuture<SendResult<...>>`. `get(5, SECONDS)` waits at most five seconds on the caller. If that time expires, the future may still complete later; a `get` timeout does not automatically cancel an already-sent record. Handle the indeterminate state and avoid resending with a new event ID.

This example is an option when fine-grained future APIs and `RecordMetadata` are needed. In an application using the Kafka Binder, consider keeping a unified send path through bindings if those lower-level capabilities are unnecessary.

## 14. Producer shutdown and flush

An asynchronous producer may still hold records in its buffer when the application begins shutting down. The Kafka producer must be closed cleanly to flush pending data within configured limits. The Spring container and binder manage the producer lifecycle; do not manually close framework-managed producers.

In an application with an outbox relay, during shutdown you should:

1. Stop accepting new work or pause the polling schedule.
2. Wait for in-flight tasks to finish within the shutdown timeout.
3. Let the producer flush/close via the binder/client lifecycle.
4. Do not mark an outbox record as sent without an appropriate confirmation result.
5. On restart, resume unmarked records using the same event ID.

If the shutdown timeout is too short, the relay can be interrupted mid-send. That does not necessarily lose messages if the outbox retains the records, but it can cause duplicate publishes. Consumer idempotency is an essential safeguard.

## 15. Observing latency and timeouts

Metrics to monitor:

- Time from when the application calls send to when the channel accepts the message.
- Time the producer waits for broker acknowledgment when using sync.
- Timeout counts for `max.block.ms`, requests, and delivery.
- Count of failed or retried records on the producer.
- Producer buffer availability, batch size, request latency, and record error rate.
- Number of pending outbox records, age of the oldest record, and republish count.
- Thread pool saturation when sending synchronously from request handlers.

Logs should include `eventId`, destination, partition key if present, binding name, and error type. Do not log full sensitive payloads. Metric labels should be restricted to normalized binding/destination names; do not use event IDs as high-cardinality labels.

When timeouts spike, distinguish metadata/buffer errors, network request errors, brokers failing to satisfy `acks`, or callers timing out before the producer. Each root cause requires a different remediation.

## 16. Testing synchronous, asynchronous, and timeout behavior

A test suite should include:

| Scenario | How to test | What to verify |
|---|---|---|
| Normal async send | Send messages with `sync: false` | Channel accepts message and broker receives record; async errors are observed |
| Successful sync send | Enable `sync: true`, healthy broker | Caller completes only after producer result per configuration |
| Broker unavailable | Stop broker or block network | Error is observed; wait time obeys configured timeouts |
| `acks: 0` | Send with acks 0 | Send completion is not interpreted as broker confirmation |
| `acks: all` | Use topic with appropriate replication | Verify broker ack respects ISR and `min.insync.replicas` |
| Buffer/metadata unavailable | Start with broker down or exhaust buffer in load test | Verify `max.block.ms` bound |
| Request timeout | Simulate slow broker responses | Verify `request.timeout.ms` and retries |
| Delivery timeout | Keep broker unable to accept records for an extended period | Verify producer finishes the record within `delivery.timeout.ms` budget |
| Caller timeout | Set HTTP timeout shorter than producer timeout | Verify caller timeout does not lead to assuming the record was not sent |
| Shutdown with pending records | Stop application while publishing | Verify lifecycle flush and outbox recovery |
| Publish retry | Simulate lost acknowledgment after broker write | Consumer deduplicates using stable event ID |

The Test Binder is helpful for testing output bindings and Spring Cloud Stream message flows, but it does not fully simulate Kafka producer buffers, acknowledgments, replication, timeouts, and network failures. Timeout/acks scenarios require integration tests with an actual Kafka broker or a test environment capable of controlling the broker.

## 17. Workflow for choosing a send mode

When designing a Kafka producer:

1. Determine whether the caller must know the broker acknowledged the record before continuing.
2. If waiting is unnecessary, keep the producer async and build send-error tracking.
3. If waiting is required, enable `sync: true` on the exact Kafka output binding.
4. Choose `acks` according to durability needs; do not confuse sync with durability.
5. Enable idempotent producer when appropriate and configure replication/ISR on the broker.
6. Set `request.timeout.ms`, `delivery.timeout.ms`, and `max.block.ms` consistently.
7. Budget total wait time alongside HTTP timeouts, shutdown timeouts, and business SLAs.
8. Preserve stable event IDs across all retries; use an outbox if recovery across restarts is needed.
9. Monitor async errors, timeouts, producer metrics, and outbox backlog.
10. Test slow brokers, broker disconnects, lost acknowledgments, and shutdowns.

## 18. Self-check

- [ ] Can explain the difference between asynchronous and synchronous sending.
- [ ] Know that `sync` is a Kafka binder producer property and defaults to asynchronous.
- [ ] Distinguish `StreamBridge.send`'s boolean return value from broker acknowledgment.
- [ ] Can explain the roles of `acks: 0`, `acks: 1`, and `acks: all`.
- [ ] Distinguish `max.block.ms`, `request.timeout.ms`, and `delivery.timeout.ms`.
- [ ] Understand that a caller timeout does not prove the record was not written to Kafka.
- [ ] Distinguish internal Kafka producer retries from application/outbox retries.
- [ ] Know why synchronous sends can exhaust thread pools.
- [ ] Can design stable event IDs and idempotency when republishing.
- [ ] Have tested sync/async modes, acknowledgments, timeouts, broker failures, and shutdowns.

## Conclusion

The Kafka Binder sends asynchronously by default to leverage batching and minimize how long caller threads are held. Enable `sync: true` on an output binding when the application must wait for the Kafka producer send result; however, the actual confirmation guarantee still depends on `acks` and replication settings. `StreamBridge.send` returns a boolean indicating whether the message was accepted by the output channel, not proof in every mode that a consumer processed it or the broker durably persisted it. Distinguish `max.block.ms`, `request.timeout.ms`, `delivery.timeout.ms`, and business timeouts; treat timeouts as potentially indeterminate states, preserve event IDs across retries, and use outbox/idempotency patterns when delivery guarantees are required.
