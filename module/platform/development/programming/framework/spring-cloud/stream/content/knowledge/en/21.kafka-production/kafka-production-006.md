# Receiving Send Results, Record Metadata, and Asynchronous Send Errors

When a Spring Cloud Stream application publishes a message to Kafka, the send call and the broker confirming the record write happen at two different times. With an asynchronous producer, the application can continue processing right after placing the message into the send pipeline, while the Kafka client is still waiting to send the request, receive the acknowledgment, or handle an error. Checking only the initial send call can cause the application to miss errors that occur afterward.

The Kafka binder provides mechanisms to observe send results. With the Kafka message-channel binder, you can enable synchronous sending with `sync`, receive metadata for successful records via `recordMetadataChannel`, and route asynchronous send errors to an error channel with `errorChannelEnabled`. With the Reactive Kafka binder, `resultMetadataChannel` provides a `SenderResult` containing success info, errors, and corresponding metadata.

This lesson explains how to choose the appropriate mechanism, read topic/partition/offset, correlate results with the original message, handle send failures, and test success, timeout, or broker write-rejection scenarios.

## Learning objectives

After this lesson, you will be able to:

- Distinguish passing a message into a send channel from Kafka confirming that the record was written.
- Explain the difference between synchronous and asynchronous sending.
- Configure `sync` and `sendTimeoutExpression` for a Kafka producer binding.
- Receive successful send results via `recordMetadataChannel`.
- Read `KafkaHeaders.RECORD_METADATA` and the fields of `RecordMetadata`.
- Enable `errorChannelEnabled` to receive asynchronous send errors.
- Inspect `KafkaSendFailureException`, the original failed message, and the `ProducerRecord`.
- Use the Reactive Kafka binder's `resultMetadataChannel` to receive `SenderResult`.
- Design correlation, retries, and send-result observation without introducing duplicate side effects.

## 1. Lifecycle of a Kafka send

A producer sends a record through several steps:

1. The application creates a Spring `Message<?>` and sends it to an output binding.
2. Spring Cloud Stream converts the payload and headers and builds a Kafka `ProducerRecord`.
3. The Kafka producer places the record into an internal buffer and sends a request to the broker.
4. The broker validates the request, writes the record to the partition, and returns an acknowledgment according to the `acks` configuration.
5. The Kafka client completes the send result or reports an error.
6. The binder delivers the result back to the application via the configured synchronous mechanism, metadata channel, or error channel.

~~~mermaid
sequenceDiagram
    participant A as Spring Cloud Stream app
    participant B as Kafka binder
    participant P as Kafka producer
    participant K as Kafka broker
    A->>B: Send Message
    B->>P: ProducerRecord
    P-->>A: Return from async send
    P->>K: Produce request
    K-->>P: Ack / error
    P-->>B: Send completion
    B-->>A: RecordMetadata or ErrorMessage
~~~

In asynchronous mode, control can return to the application before step 4 or 5. Therefore:

- A send call returning without throwing an exception does not prove the broker wrote the record.
- A boolean return value from a message-sending API usually only confirms that the send into the channel was accepted according to that API; do not treat it by default as a broker acknowledgment.
- A successful metadata result indicates that the Kafka client completed the send according to the active acknowledgment policy.
- A successful send result does not prove that a consumer has read or processed the record.

Be explicit about which signal answers which question: whether the application handed the message to the binder, whether the broker wrote the record, or whether the consumer completed the business work.

## 2. Synchronous and asynchronous sending

The Kafka message-channel binder uses an asynchronous producer by default. The Kafka producer `sync` property lets you wait for the send result before completing the message-handling operation.

| Mode | Behavior | Advantages | Trade-offs |
|---|---|---|---|
| `sync: false` | Sends asynchronously; does not wait for broker acknowledgment on the calling thread | Good throughput, does not block caller for long | Must observe success/failure results via channels |
| `sync: true` | Waits for the send result before returning | Send errors can be reported directly on the calling thread | Increases latency and holds threads while waiting |

### Configuring synchronous sending

Example output binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              sendTimeoutExpression: "headers['sendTimeoutMs']"
~~~

`sync: true` instructs the producer to wait for the send result. `sendTimeoutExpression` is a SpEL expression evaluated on the message to determine how long to wait for acknowledgment, in milliseconds. The example above reads the timeout from the `sendTimeoutMs` header. If per-message timeouts are unnecessary, you can omit this property and use your version's default configuration.

With synchronous sending, send errors or timeouts can propagate back to the caller as exceptions. Therefore, publishing code needs an appropriate exception-catching and handling policy:

~~~java
public void publish(OrderCreated event) {
    try {
        streamBridge.send("publishOrder-out-0", event);
    }
    catch (RuntimeException ex) {
        log.error("Failed to send OrderCreated {}", event.eventId(), ex);
        throw ex;
    }
}
~~~

This example illustrates the synchronous error path. In a real application, classify exceptions by cause, decide on retries at a single clear layer, and use a stable event ID to prevent duplicate sends.

Do not enable `sync: true` for every flow just to observe results more easily. Waiting for acknowledgment on every message can hurt throughput and increase request or function processing times. If you need to track many concurrent sends, asynchronous mode combined with correlation is usually a better fit.

## 3. sendTimeoutExpression

`sendTimeoutExpression` is used by the Kafka binder during synchronous sending to determine the acknowledgment wait time. The value is measured in milliseconds.

You can use a fixed timeout:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              sendTimeoutExpression: "5000"
~~~

Or use a header so each message has its own wait budget:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("sendTimeoutMs", 3000L)
    .build();

streamBridge.send("publishOrder-out-0", message);
~~~

When using a header-based timeout, ensure the data type and unit are milliseconds. Too short a timeout can trigger an error even though the broker can still complete the request afterward; too long a timeout holds threads for an extended period when the broker or network runs into trouble.

A timeout is not definitive proof that a record was not written. If the client times out after the broker has written the record but the acknowledgment was lost on the return path, resending can create a duplicate record. For critical business messages, use event IDs, idempotency, and a controlled retry strategy.

## 4. Receiving metadata for successfully sent records

The Kafka binder has the `recordMetadataChannel` property. This property takes the bean name of a Spring `MessageChannel`. On a successful send, the binder sends a result message to that channel. The message contains the converted outbound payload and the `KafkaHeaders.RECORD_METADATA` header carrying the `RecordMetadata` object provided by the Kafka client.

Metadata tells you where the record was written:

| Metadata field | Meaning |
|---|---|
| `topic()` | Name of the topic that received the record |
| `partition()` | Partition to which the record was written |
| `offset()` | Offset of the record within the partition |
| `timestamp()` | Timestamp recorded by the producer/broker per configuration |
| `serializedKeySize()` | Key size after serialization |
| `serializedValueSize()` | Value size after serialization |

Metadata helps you:
- Trace a message to its topic, partition, and offset.
- Cross-check records with data observed via Kafka CLI or admin tools.
- Record publish outcomes in logs or audits.
- Analyze partition distribution and send latency.
- Link a send to the originating business operation if the application uses a correlation ID.

### Declaring a channel to receive results

Example creating a `DirectChannel` and handling results:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Configuration
class KafkaSendResultChannels {

    @Bean
    MessageChannel orderSendResults() {
        return new DirectChannel();
    }
}

@Component
class KafkaSendResultHandler {

    private static final Logger log = LoggerFactory.getLogger(KafkaSendResultHandler.class);

    @ServiceActivator(inputChannel = "orderSendResults")
    public void handleSuccessfulSend(Message<?> result) {
        RecordMetadata metadata = result.getHeaders().get(
            KafkaHeaders.RECORD_METADATA,
            RecordMetadata.class
        );

        if (metadata == null) {
            log.warn("Send result does not contain RecordMetadata");
            return;
        }

        log.info(
            "Kafka record written: topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

Binder configuration pointing to the channel bean:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              recordMetadataChannel: orderSendResults
~~~

The name `orderSendResults` must match the `MessageChannel` bean name. If the bean does not exist or the configured name is wrong, the binder cannot deliver results to the intended channel.

### Metadata is not the business message content

`RecordMetadata` is metadata provided by the Kafka client after sending. It does not replace the payload, event ID, or correlation ID. When you need to trace back to the business message, record both the event ID and metadata:

~~~java
log.info(
    "eventId={}, topic={}, partition={}, offset={}",
    eventId,
    metadata.topic(),
    metadata.partition(),
    metadata.offset()
);
~~~

Do not use offset alone as a business identifier. An offset is meaningful only within a specific topic partition and can differ if a message is resent or replayed to another topic.

## 5. Correlating send results with the original message

When multiple messages are sent concurrently, results can complete in a different order than the send order. Do not match results by list position or assume callbacks always arrive in order.

Use a stable correlation ID for each send. For example:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setCorrelationId(event.eventId())
    .build();

streamBridge.send("publishOrder-out-0", message);
~~~

The success result is delivered to `recordMetadataChannel` along with the sent message and metadata. The application can read the correlation ID from the message headers and combine it with `RecordMetadata` to log or update publish state.

A correlation ID should:
- Be unique across sends currently awaiting results.
- Remain unchanged when retrying the same business event.
- Contain no sensitive data.
- Be searchable in logs, traces, or outbox tables.
- Have an expiration rule if the application stores pending result state in memory.

Do not use a single global variable to store the correlation ID of the latest send. Concurrent sends will overwrite each other.

## 6. Enabling an error channel for asynchronous send errors

When a producer sends asynchronously, certain errors surface only after the initial call has returned, such as:
- Broker unavailable or connection lost.
- Request timed out.
- Broker rejected the write due to authorization or a nonexistent topic.
- Serialization error occurring while the producer processes the record.
- Metadata or network error during sending.

The generic `errorChannelEnabled` property on an output binding routes asynchronous send errors to an error channel when the binder supports that mechanism. The default is `false`.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            errorChannelEnabled: true
~~~

With the Kafka binder, the payload of the `ErrorMessage` for a send failure is `KafkaSendFailureException`. This exception provides:

- `getFailedMessage()`: the original Spring Messaging `Message<?>` that failed to send.
- `getRecord()`: the Kafka `ProducerRecord` created from that message.
- `getCause()`: the root cause of the send failure.

The producer error channel must be handled by the application. The Kafka binder does not automatically route producer send failures to a DLQ like a consumer DLQ mechanism does. The application must decide whether to log, retry, move to a parking lot, or report an error to the calling system.

### Handling send errors via errorChannel

Example registering a global handler and processing only Kafka send failures:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.kafka.support.KafkaSendFailureException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.apache.kafka.clients.producer.ProducerRecord;

@Component
public class KafkaSendErrorHandler {

    private static final Logger log = LoggerFactory.getLogger(KafkaSendErrorHandler.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void handleApplicationError(ErrorMessage errorMessage) {
        Object payload = errorMessage.getPayload();

        if (payload instanceof KafkaSendFailureException failure) {
            Message<?> failedMessage = failure.getFailedMessage();
            ProducerRecord<?, ?> record = failure.getRecord();

            log.error(
                "Kafka send failed: topic={}, key={}, event={}",
                record.topic(),
                record.key(),
                failedMessage.getHeaders().get("eventId"),
                failure
            );

            // Record the error and route to retry/parking-lot per application policy.
            return;
        }

        log.error("Application error: {}", payload);
    }
}
~~~

The global `errorChannel` can receive many kinds of application errors, not just Kafka producer errors. Therefore, the handler must inspect the payload type or route by binding before processing. If using multiple binders, do not assume every exception is a `KafkaSendFailureException`.

If you need a dedicated handler for a single output binding, you can register a subscriber for that destination's error channel following the naming convention of your Spring Cloud Stream version. Cross-check the version documentation and test the actual channel name; do not guess the name from the topic without verification.

## 7. Analyzing KafkaSendFailureException

When receiving a send error, retain enough information for investigation:

| Information | Purpose |
|---|---|
| `failedMessage` | Identify the payload and headers of the message the application sent |
| `ProducerRecord` | Identify the target topic, key, partition, timestamp, and headers |
| `cause` | Determine whether it was a network, timeout, serialization, authorization, or broker error |
| `eventId` / correlation ID | Link the error to the business operation and send attempt |
| Binding name | Identify the output binding and producer configuration |
| Timestamp and attempt count | Analyze whether the error is transient or persistent |

Do not log the entire payload if it contains personal data, tokens, or payment details. You can log the event ID, topic, sanitized key, exception type, and trace ID for traceability.

### Classifying send errors

| Error category | Examples | Handling approach |
|---|---|---|
| Transient | Network timeout, broker leader transition | Bounded retry with backoff |
| Configuration/permissions | Topic does not exist, ACL denied, wrong credentials | Fix configuration or permissions; avoid infinite retries |
| Data | Serialization failed due to invalid payload | Quarantine the message and investigate data |
| Overload | Buffer full, broker throttling | Throttle rate, adjust capacity and quotas |
| Indeterminate outcome | Timeout after the broker may already have written the record | Retry with idempotency or reconcile |

Not every timeout proves the broker failed to write the record. If the acknowledgment was lost after the record was written, a retry can create a duplicate record. When a message represents a business operation, the producer should carry a stable event ID and the consumer should be idempotent.

## 8. Distinguishing producer errors from consumer DLQs

The Kafka binder's DLQ typically handles records that a consumer cannot process after retries. Producer errors happen on the outbound path and are not automatically routed into a consumer DLQ.

| Error type | Where it occurs | Observation/handling mechanism |
|---|---|---|
| Producer send failure | Application sending → Kafka | `recordMetadataChannel` for success; `errorChannelEnabled` for async errors |
| Consumer processing failure | Kafka → receiving application | Consumer binding retry, error handler, and DLQ |
| Deserialization failure | Kafka client/binder decoding record | Binder's dedicated deserialization error handling mechanism |
| Downstream business failure | Business-processing function/service | Consumer and business retry/recovery |

If a producer send fails, there is no valid record on the target topic for a consumer DLQ to process. The sending application must decide how to recover the original message.

## 9. Asynchronous sending with the Reactive Kafka binder

The Kafka message-channel binder and the Reactive Kafka binder use different result-receiving mechanisms. The Reactive Kafka binder is built on Reactor Kafka. Since version 4.0.3, the binder supports `resultMetadataChannel` to receive `SenderResult<?>` for send operations.

`SenderResult` provides:
- `correlationMetadata()`: metadata attached by the application to correlate results with sends.
- `exception()`: the error if the send failed.
- `recordMetadata()`: Kafka metadata of the successfully sent record.

The result channel must be a `FluxMessageChannel`.

Example declaring the channel and handler:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.FluxMessageChannel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.kafka.sender.SenderResult;

@Configuration
class ReactiveSendResultChannels {

    @Bean
    FluxMessageChannel orderSenderResults() {
        return new FluxMessageChannel();
    }
}

@Component
class ReactiveSendResultHandler {

    private static final Logger log = LoggerFactory.getLogger(ReactiveSendResultHandler.class);

    @ServiceActivator(inputChannel = "orderSenderResults")
    public void handleReactiveSendResult(SenderResult<String> result) {
        if (result.exception() != null) {
            log.error(
                "Reactive Kafka send failed, correlation={}",
                result.correlationMetadata(),
                result.exception()
            );
            return;
        }

        RecordMetadata metadata = result.recordMetadata();

        log.info(
            "Reactive send success, correlation={}, topic={}, partition={}, offset={}",
            result.correlationMetadata(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              resultMetadataChannel: orderSenderResults
~~~

When sending, the application attaches a correlation ID:

~~~java
streamBridge.send(
    "publishOrder-out-0",
    MessageBuilder.withPayload(event)
        .setCorrelationId(event.eventId())
        .build()
);
~~~

With reactive functions, the output message must carry a correlation ID header so the send result can return the matching correlation metadata. The correlation value should be unique at least for the duration the send is awaiting its result.

Do not confuse `resultMetadataChannel` of the Reactive Kafka binder with `recordMetadataChannel` of the Kafka message-channel binder. The two mechanisms have different channel types and result types.

## 10. Comparing the two result-receiving mechanisms

| Criterion | Kafka message-channel binder | Reactive Kafka binder |
|---|---|---|
| Synchronous sending | `sync: true` | Does not use this same binder property |
| Success result | `recordMetadataChannel` | `resultMetadataChannel` |
| Channel type | Spring `MessageChannel` | `FluxMessageChannel` |
| Payload/result | Message carrying `KafkaHeaders.RECORD_METADATA` header | `SenderResult<?>` |
| Metadata | `RecordMetadata` | `RecordMetadata` |
| Async send error | Producer error channel when `errorChannelEnabled` is enabled | `SenderResult.exception()` |
| Correlation | Uses application message ID/correlation header | `SenderResult.correlationMetadata()` |
| Supported versions | Per current Kafka binder | `resultMetadataChannel` from 4.0.3 |

Choose the mechanism matching the binder your application actually uses. Do not place reactive binder properties on the message-channel binder and expect the same result type.

## 11. Retrying and handling failed send results

When receiving a producer error, the application can:
1. Record the failed message in an outbox table or retry store.
2. Classify the exception.
3. Retry transient errors with a bounded attempt count and backoff.
4. Keep the same event ID and correlation ID across attempts.
5. Move permanent errors to a parking lot for investigation.
6. Trigger alerts when error rates or wait times exceed thresholds.

Do not retry immediately inside the error handler itself without bounds. If the broker is disconnected, many messages can trigger a retry storm and exhaust application threads or buffers.

A retry workflow should persist:
- Original event ID.
- Attempt count so far.
- Timestamp of the most recent attempt.
- Exception type and cause details.
- Target topic/binding.
- Current status: PENDING, RETRYING, SENT, or PARKED.

### Avoiding error loops

If an error handler uses the exact same failing output binding to publish retry messages, the retry message can also fail and loop back to the error channel. Enforce a maximum attempt limit and a separate parking-lot mechanism to break the loop.

Do not mark an event SENT simply because `StreamBridge.send()` returned true while the producer still sends asynchronously. Update the status to broker-confirmed only when receiving a result signal consistent with the producer configuration.

## 12. Metadata and send durability

Success metadata must be interpreted in light of the Kafka producer configuration. The Kafka producer `acks` property dictates the acknowledgment level the producer waits for:

- `acks=0`: the producer does not wait for broker acknowledgment; the result does not provide the same durability evidence as modes with acknowledgment.
- `acks=1`: the leader acknowledges after writing the record to its local log.
- `acks=all` (or `-1`): waits for in-sync replicas to acknowledge per broker configuration.

For applications requiring high durability, choose `acks`, replication factor, and `min.insync.replicas` matching your Kafka cluster policy. `recordMetadataChannel` only reports the producer's send outcome under the chosen acknowledgment policy; it does not increase durability on its own.

Example producer configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          producerProperties:
            acks: all
            enable.idempotence: true
~~~

This is a binder-level Kafka client configuration. If configuring per binding, use `spring.cloud.stream.kafka.bindings.<binding>.producer.configuration` per your version's documentation. Enabling idempotent producer limits duplicates from retries within a producer session; it does not replace business idempotency when the application replays events after a restart or resends from an outbox.

## 13. Observability and operations

To know whether publishing is healthy, monitor:

| Metric | Meaning |
|---|---|
| Send success count | Number of sends completed successfully |
| Send failure count | Number of failed sends |
| Send latency | Time from send initiation to receiving the result |
| Timeout count | Number of acknowledgment waits exceeding limits |
| Pending sends | Number of sends without a result yet |
| Error channel rate | Rate of asynchronous errors |
| Topic/partition distribution | Distribution of records across partitions |
| Retry count | Number of retry attempts |
| Parking-lot count | Number of quarantined messages |
| Producer buffer wait | Time spent waiting on buffer/metadata/broker |

Logs should include event ID, correlation ID, binding, topic, partition, offset, exception type, and trace ID. Do not log full sensitive payloads. Include metrics for pending sends and send failures to detect situations where the application still accepts requests while Kafka fails to record them.

When stopping the application, allow the producer time to flush/close via the binder lifecycle. If the process is killed right after enqueuing an async send but before the producer completes, the message may not have been written. For critical messages, combine a durable outbox with send result confirmation.

## 14. Testing send results and asynchronous errors

### Testing success metadata

1. Start a Kafka broker and create a topic with multiple partitions.
2. Configure `recordMetadataChannel` with a valid channel bean.
3. Send a message carrying an event ID.
4. Verify the handler receives the result message.
5. Read `KafkaHeaders.RECORD_METADATA`.
6. Inspect topic, partition, and offset.
7. Use a Kafka consumer or CLI to confirm the record actually exists at that position.

### Testing asynchronous errors

1. Configure `sync: false` and `errorChannelEnabled: true`.
2. Send a message while the broker is healthy to verify the success path.
3. Simulate an unavailable broker or a broker rejecting requests.
4. Verify the error handler receives `KafkaSendFailureException`.
5. Verify `failedMessage` and `ProducerRecord` contain the expected details.
6. Restore the broker and verify the retry/parking-lot policy.
7. Verify the message is not marked SENT before a success result arrives.

### Testing timeouts and indeterminate outcomes

- Set a timeout shorter than the broker's response time.
- Simulate the case where the broker writes the record but the acknowledgment back to the client is delayed or lost.
- Verify the application does not assume a timeout means the record does not exist.
- Retry with the same event ID and verify the idempotency/deduplication policy.

### Testing the Reactive Kafka binder

- Use a `FluxMessageChannel` as `resultMetadataChannel`.
- Send a message with a correlation ID.
- Verify `SenderResult` contains the matching correlation metadata.
- Check `exception()` on send failure and `recordMetadata()` on success.
- Execute multiple concurrent sends and verify results match their correlations accurately.

## 15. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Not receiving success metadata | Channel bean not declared or wrong `recordMetadataChannel` name | Cross-check bean name and binding config |
| Metadata header is null | Message is not a success result or channel received the wrong message | Inspect payload and `KafkaHeaders.RECORD_METADATA` header |
| Not seeing async errors | `errorChannelEnabled` is off or binder does not support async results in that config | Check property and binder version |
| Errors do not reach handler | Not subscribed to error channel or handler not initialized | Check Spring Integration flow and global error channel |
| Caller thinks send succeeded but record is missing | Sending async and checking only the initial call return | Use metadata/error channel or sync mode |
| Sync sending reduces throughput | Waiting for acknowledgment on every send | Evaluate async result channel and proper batching |
| Retrying after timeout creates duplicates | Broker may have written the record before the response was lost | Use event ID/idempotency and reconciliation |
| Error handler causes a retry loop | Unbounded retries or resending into the failing binding | Enforce attempt limits, backoff, and a parking lot |
| Not receiving SenderResult | Using the regular binder or channel is not FluxMessageChannel | Use the Reactive Kafka binder and configure for the right version |
| Correlation mismatch | Non-unique ID or function output drops correlation header | Attach stable correlation ID and inspect headers |

## 16. Lab: tracking OrderCreated send results

Build a producer that sends `OrderCreated` to the `orders` topic:

1. Declare a function or service publishing messages via the `publishOrder-out-0` binding.
2. Attach a stable event ID and correlation ID to each message.
3. Configure destination `orders`.
4. Declare a `MessageChannel` bean to receive success results.
5. Point `recordMetadataChannel` to the bean.
6. Enable `errorChannelEnabled: true`.
7. Write a handler that reads metadata and logs topic, partition, and offset alongside the event ID.
8. Write an error handler that catches `KafkaSendFailureException` and records the failed message/record/cause.
9. Send a message with the broker running and verify the metadata.
10. Stop the broker in the test environment and verify the async error is received.
11. Restart the broker and perform bounded retries.
12. Verify that a timeout does not cause the application to produce duplicate side effects.
13. Try the Reactive Kafka binder variant with `resultMetadataChannel` and `SenderResult`.

Acceptance checklist:

| Item | Result to verify |
|---|---|
| Send mode | Sync or async is explicitly known |
| Timeout | Wait unit and limit are configured |
| Success channel | Receives the right message and RecordMetadata |
| Metadata | Contains topic, partition, offset |
| Error channel | Captures async errors when enabled |
| Failure payload | Can read failedMessage, ProducerRecord, and cause |
| Correlation | Results match the original event accurately |
| Retry | Bounded attempts, backoff, and parking lot |
| Durability | Metadata interpreted per acks setting |
| Reactive binder | Uses FluxMessageChannel/SenderResult properly if applicable |
| Observability | Logs/metrics cover success, failure, latency, and retries |

## Conclusion

A Kafka producer can send synchronously or asynchronously. With the Kafka message-channel binder, `sync` waits for the send result on the calling thread; `recordMetadataChannel` receives successful results with `KafkaHeaders.RECORD_METADATA`; and `errorChannelEnabled` routes asynchronous send failures to an error channel. The error payload is `KafkaSendFailureException`, containing the original message and `ProducerRecord`; the application decides how to retry or quarantine failures.

With the Reactive Kafka binder from version 4.0.3 onward, `resultMetadataChannel` receives `SenderResult` via a `FluxMessageChannel`, including correlation metadata, exception, and RecordMetadata. Correlate results using a stable event ID, interpret metadata according to your `acks` policy, treat timeouts as potentially indeterminate outcomes, and test against a real broker. A successful send result confirms the producer completed per Kafka settings—it does not mean the consumer has finished business processing.

## References

- [Spring Cloud Stream – Kafka Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream – Kafka Error Channels](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/error-channels.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Reactor Kafka – Sender API](https://projectreactor.io/docs/kafka/release/reference/)
