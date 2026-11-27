# AUTO, MANUAL, and NONE Acknowledgement Modes

RabbitMQ delivers messages to consumers using a push mechanism. After receiving a message, the consumer needs to inform the broker whether the message has been processed, needs to be redelivered, or can be removed from the queue. That signal is called an acknowledgement (ack). The acknowledgement mode determines who sends the ack and when the broker is allowed to delete the message from the queue.

The Spring Cloud Stream Rabbit binder supports three modes: `AUTO`, `MANUAL`, and `NONE`. `AUTO` lets the listener container acknowledge after successful processing; `MANUAL` delegates acknowledgement control to application code via the Rabbit channel and delivery tag; `NONE` sends no ack because the broker considers the message acknowledged immediately upon delivery. The Rabbit binder default is `AUTO`.

Choosing the wrong mode can cause message loss or repeated redelivery. This lesson explains the ack lifecycle, how to configure each mode in Spring Cloud Stream, how to use `basicAck`, `basicNack`, and `basicReject`, and how to coordinate acknowledgements with retry, dead-letter queues (DLQ), prefetch, and idempotency.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish RabbitMQ acknowledgements from publisher confirms.
- Describe the acknowledgement timing of AUTO, MANUAL, and NONE.
- Configure `acknowledgeMode` on a Rabbit consumer binding.
- Use `AmqpHeaders.CHANNEL` and `AmqpHeaders.DELIVERY_TAG` in MANUAL mode.
- Choose between `basicAck`, `basicNack`, and `basicReject`.
- Understand the impact of requeue, retry, and DLQ.
- Avoid message loss, redelivery loops, and duplicate acknowledgements.
- Tune prefetch based on the number of unacknowledged messages.
- Test scenarios where a consumer completes, fails, or stops abruptly.

## 1. What Is an Acknowledgement in RabbitMQ?

When a consumer subscribes to receive messages from a queue, RabbitMQ pushes messages to the consumer. With manual or container-managed acknowledgement, a message remains in an unacknowledged (unacked) state until the broker receives a valid ack.

Basic flow:

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant C as Consumer
    Q->>C: Deliver message (deliveryTag=42)
    Note over Q: Message is in unacked state
    C->>C: Business processing
    C->>Q: basicAck(42, false)
    Note over Q: Broker removes message from queue
~~~

An ack tells the broker that the consumer has taken responsibility for completing message processing. If the consumer loses its connection before acking, RabbitMQ can return the unacked message to the ready state to deliver it to another consumer. Therefore, a consumer may receive the same message again even if the previous attempt partially executed or even committed to the database.

Concepts to distinguish:

- **Delivery:** the broker transfers a message to the consumer.
- **Acknowledgement:** the consumer confirms it has processed the message or decides to discard/requeue it.
- **Publisher confirm:** the broker confirms the publish result to the producer.
- **Message durability:** the message and queue are configured to survive crashes/restarts under the corresponding conditions.

Consumer acks do not replace publisher confirms. Nor do acks by themselves guarantee that a message was persisted durably before the consumer received it; durability depends on queue type, message delivery mode, replication, and broker configuration.

## 2. The Three Acknowledgement Modes

| Mode | Who acknowledges? | Timing | Behavior when consumer dies before processing |
|---|---|---|---|
| `AUTO` | Spring listener container | After listener processing completes normally | Unacked message is redelivered |
| `MANUAL` | Application code | When the application calls `basicAck`, `basicNack`, or `basicReject` | Unacked message is redelivered when channel/connection closes |
| `NONE` | No ack frame from consumer; RabbitMQ auto-acks on delivery | Immediately when the broker sends the message | Message may already be removed from the queue even if the application has not finished processing |

The naming can be confusing: Spring AMQP's `AUTO` means the container automatically sends an ack after the listener completes. RabbitMQ calls the mode without acknowledgements *auto-ack*; in Spring, that mode corresponds to `NONE`.

The Spring Cloud Stream Rabbit binder defaults to `AUTO`. Switch to `MANUAL` only when the application truly needs per-message ack/nack decisions. `NONE` is suitable for data that can tolerate loss and prioritizes throughput over delivery guarantees.

## 3. Configuring acknowledgeMode in Spring Cloud Stream

This property belongs specifically to the Rabbit binder and is placed under the prefix:

`spring.cloud.stream.rabbit.bindings.<bindingName>.consumer.`

Example for an order-receiving binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
~~~

You can set a default value for multiple Rabbit bindings with:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        default:
          consumer:
            acknowledgeMode: AUTO
~~~

Binding-specific configuration overrides the default configuration. Do not confuse this prefix with `spring.cloud.stream.bindings.<bindingName>.consumer`, which holds generic consumer properties such as concurrency and retry.

Valid values are `AUTO`, `MANUAL`, and `NONE`. If omitted, the binder uses `AUTO`.

## 4. AUTO: Container Acknowledges After Successful Processing

With `AUTO`, the listener container manages acknowledgements. When the handler completes normally, the container sends an ack to RabbitMQ. If the handler throws an exception, the container/error handler handles the failure according to retry, requeue, and DLQ configuration.

Example consumer function:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumer {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
~~~

AUTO configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
~~~

If `orderService.process` completes normally, the container acknowledges the message. If it throws an exception, Spring Cloud Stream can retry according to `maxAttempts` before moving to failure handling. Final behavior also depends on `requeueRejected`, DLQ topology, and binder configuration.

### When Is AUTO Suitable?

AUTO is usually a good choice for most business consumers because:

- Business code does not have to manually manage delivery tags.
- Ack is sent only after the handler completes normally.
- Retry and DLQ can integrate with framework error handling.
- It reduces the risk of forgetting to ack or acking the wrong message.

Note: "handler completes normally" is a framework signal and does not by itself prove every external side effect is durable. If the handler catches an exception, only logs it, and returns normally, the container can ack the message. Do not swallow errors if you want the framework to retry or route the message to the failure path.

### AUTO and Asynchronous Processing

If the handler offloads work to an internal thread or queue and returns immediately, the container may consider the listener finished and ack the message before the background work completes. Ensure the listener completion boundary accurately reflects when business processing has been durably completed. For async processing, use a model that properly supports async or consider manual acknowledgement after thoroughly understanding the channel lifecycle.

## 5. MANUAL: Application Acknowledges Explicitly

With `MANUAL`, the container does not automatically ack when the listener returns. Application code must decide whether the message succeeded, needs redelivery, or should be rejected. Spring AMQP places the Rabbit channel and delivery tag in the message headers:

- `AmqpHeaders.CHANNEL` (header `amqp_channel`) contains `com.rabbitmq.client.Channel`.
- `AmqpHeaders.DELIVERY_TAG` (header `amqp_deliveryTag`) contains the message's delivery tag.

Configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: MANUAL
              autoBindDlq: true
~~~

### Acknowledging a Successful Message

Once business processing is complete and data has been persisted durably, call:

~~~java
channel.basicAck(deliveryTag, false);
~~~

The second parameter is `multiple`:
- `false`: acknowledges only this delivery tag.
- `true`: acknowledges all unacked delivery tags on the channel with a value less than or equal to the current tag.

When processing each message independently, `false` is typically used. Only use `true` when the application precisely manages the completion order of every prior delivery on the channel. If an earlier message is still being processed, acking with multiple can accidentally acknowledge that message.

### Nack and Reject

If the message cannot be processed, the application can choose:

~~~java
channel.basicNack(deliveryTag, false, true);
~~~

`basicNack` allows:
- Specifying one delivery or multiple deliveries via `multiple`.
- Choosing `requeue=true` to return the message to the queue.
- Choosing `requeue=false` to reject; if the queue has a matching dead-letter exchange, the message is dead-lettered according to broker configuration.

`basicReject` applies to a single delivery tag:

~~~java
channel.basicReject(deliveryTag, false);
~~~

Comparison table:

| API | Scope | Supports requeue? | Purpose |
|---|---|---|---|
| `basicAck(tag, multiple)` | One or more unacked deliveries | No | Confirm successful processing |
| `basicNack(tag, multiple, requeue)` | One or more unacked deliveries | Yes | Redeliver or reject |
| `basicReject(tag, requeue)` | One delivery | Yes | Reject a single message |

When using `requeue=false`, a message is routed to a DLQ only if the queue has a dead-letter exchange configured; otherwise, RabbitMQ may discard the message. Never assume reject always creates a DLQ.

### MANUAL Example with Spring Cloud Stream

~~~java
import java.io.IOException;
import java.util.function.Consumer;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class ManualAckOrderConsumer {

    @Bean
    Consumer<Message<OrderCreated>> processOrderManually(
            OrderService orderService) {

        return message -> {
            Channel channel = message.getHeaders().get(
                AmqpHeaders.CHANNEL, Channel.class
            );
            Long deliveryTag = message.getHeaders().get(
                AmqpHeaders.DELIVERY_TAG, Long.class
            );

            try {
                orderService.process(message.getPayload());
            }
            catch (TemporaryOrderException ex) {
                try {
                    channel.basicNack(deliveryTag, false, true);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Failed to request RabbitMQ to redeliver message", ackError
                    );
                }
                return;
            }
            catch (InvalidOrderException ex) {
                try {
                    channel.basicReject(deliveryTag, false);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Failed to reject message", ackError
                    );
                }
                return;
            }
            catch (RuntimeException ex) {
                try {
                    // Requires DLX/DLQ to isolate unclassified errors.
                    channel.basicNack(deliveryTag, false, false);
                }
                catch (IOException ackError) {
                    throw new AmqpException(
                        "Failed to isolate failed message", ackError
                    );
                }
                return;
            }

            try {
                channel.basicAck(deliveryTag, false);
            }
            catch (IOException ackError) {
                throw new AmqpException(
                    "Failed to acknowledge message", ackError
                );
            }
        };
    }
}
~~~

This example demonstrates making the ack decision within the same message-processing context. In real-world applications, you must:
- Ensure `channel` and `deliveryTag` are present when the binding runs in MANUAL mode.
- Ack only once per delivery.
- Not ack before business changes have been committed.
- Not retain the channel for arbitrary use after the handler finishes.
- Handle I/O errors when sending ack/nack because the connection may have already closed.
- Use idempotency because the broker may redeliver if the ack is lost or does not reach the broker.

A Channel is an active connection object; it cannot be safely serialized or stored in a database for later processing. Only use the channel within the scope of the current delivery. For asynchronous processing, you must explicitly design the channel lifecycle, threads, and acknowledgement timing; do not arbitrarily pass the channel to a thread pool.

## 6. NONE: Broker Acknowledges Immediately on Delivery

With `NONE`, the consumer does not send acknowledgements. RabbitMQ considers a message acknowledged immediately when sending it to the consumer (also called auto-ack). If the process dies right after receiving but before finishing processing, the message may already be removed from the queue and will not be redelivered.

Configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        metricsConsumer-in-0:
          destination: telemetry
          group: metrics-reader
      rabbit:
        bindings:
          metricsConsumer-in-0:
            consumer:
              acknowledgeMode: NONE
~~~

NONE may be suitable for data that:
- Can suffer partial loss without affecting the business.
- Can be regenerated from another source.
- Is telemetry or transient metrics where speed matters more than processing every single message.
- Does not trigger irreversible side effects.

Do not use NONE for payments, orders, inventory, or events requiring guaranteed processing. Once a message is delivered, the broker no longer waits for consumer confirmation. Restarting the application does not recover auto-acked messages.

`NONE` is incompatible with Rabbit channel transactions (`transacted: true` / `channelTransacted=true`). If you need channel transactions, choose AUTO or MANUAL and test commit/rollback together with acknowledgements.

### NONE Is Not a Faster AUTO Mode

AUTO still waits for the listener to finish before the container sends an ack. NONE skips that step. The difference is delivery guarantee, not just performance. When choosing NONE, the application accepts the risk of message loss in the window from when the broker delivers until the application finishes processing.

## 7. Reliability Comparison and Business-Driven Selection

| Requirement | Recommended mode | Reason |
|---|---|---|
| Order and payment processing | AUTO | Container acks after processing; convenient integrated retry/DLQ |
| Ack only after database write or custom step completes | MANUAL | Application controls the exact ack timing |
| Classify errors to requeue or reject immediately | MANUAL | Code decides the message's disposition |
| Telemetry counts that can tolerate loss | NONE | No waiting for ack, prioritizes throughput |
| Consumer with complex logic needing multi-delivery management | Controlled MANUAL | Can batch-ack, but must track tags and ordering |
| Standard business consumer | AUTO | Less manual operational code and fewer ack bugs |

No mode automatically provides exactly-once processing. Both AUTO and MANUAL can lead to redelivery if the consumer dies after committing business changes but before the broker receives the ack. Consumers still need to be idempotent.

## 8. Delivery Tag and Channel Must Be Managed Properly

A delivery tag is a delivery identifier assigned by RabbitMQ per channel. It is not a global message ID and cannot be used on another channel.

Important rules:

1. Use the exact channel that accompanied the delivery.
2. Do not use one message's delivery tag to ack another message.
3. Do not use a tag after the channel has closed.
4. Do not ack the same tag twice.
5. Be careful with `multiple=true` during concurrent processing.
6. Do not store the channel in an entity or database.
7. Do not treat the delivery tag as a business deduplication key.

If a consumer receives the same message again, the new delivery tag may differ. To detect duplicate events, use an event ID or business key in the payload/header, not the delivery tag.

## 9. Requeue, Retry, and Loop Risks

`basicNack(tag, false, true)` instructs RabbitMQ to return the message to the queue. If a failing message is immediately picked up by a consumer and fails again, it can create a continuous redelivery loop:

~~~mermaid
flowchart TD
    A["Queue delivers message"] --> B["Consumer processes"]
    B --> C{"Success?"}
    C -->|Yes| D["Ack"]
    C -->|No| E["Nack requeue=true"]
    E --> A
~~~

A tight loop can:
- Generate high CPU and network load.
- Cause a single failing message to consume most of the consumer's time.
- Inflate processing attempts and logs.
- Prevent other messages from making progress.
- Overload the broker and downstream services.

For transient errors, use retry with backoff or delayed retry instead of immediate continuous requeue. For unrecoverable data errors, reject with `requeue=false` and route to a DLQ if the topology is configured.

### Spring Cloud Stream Retry

The generic consumer property `maxAttempts` specifies the maximum number of processing attempts, including the first attempt; the default is typically 3. You can configure backoff:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 1000
            backOffMaxInterval: 10000
            backOffMultiplier: 2.0
~~~

With AUTO, let exceptions propagate out of the handler so the framework applies retry. Do not catch the exception and return normally if you want retry. Once retries are exhausted, the Rabbit binder handles the failure according to properties such as `requeueRejected`, `autoBindDlq`, and `republishToDlq`.

With MANUAL, the application already decides ack/nack itself. Clearly define which layer owns retry and test the interaction between framework retry and application-invoked ack/nack calls. Avoid configuring two independent retry mechanisms that multiply attempts unexpectedly.

## 10. Combining AUTO with DLQ

The Rabbit binder can automatically declare a dead-letter queue and bind that queue to a dead-letter exchange when `autoBindDlq` is enabled. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: AUTO
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
~~~

Key points to understand:

- `autoBindDlq` defaults to `false`; enable it so the binder declares the DLQ and binds it to the DLX as configured.
- `republishToDlq` defaults to `true` when the binder republishes failed messages to the DLQ; the binder can add the exception message and stack trace to headers.
- `requeueRejected` determines whether failed deliveries are requeued when retry is disabled or `republishToDlq=false`; the current default is `false`.
- DLQ name, DLX, and routing key can be configured separately.
- A DLQ does not fix payloads automatically; an investigation and replay process is needed.

Do not confuse the binder republishing a message after retries are exhausted with `basicReject(..., false)` called by the application in MANUAL mode. Manual rejection relies on the queue's dead-letter exchange/topology; the reject path may not attach the same set of error headers as binder retry recovery.

## 11. Prefetch and Unacknowledged Message Count

Prefetch limits how many messages RabbitMQ can deliver ahead of time before receiving acks from the consumer. It is the throttling mechanism for in-flight messages.

Example:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledgeMode: MANUAL
              prefetch: 20
~~~

With prefetch 20, the broker can deliver up to around 20 unacked messages per consumer according to the configured QoS. As the consumer acks messages, the broker can deliver more messages to maintain the in-flight volume.

Prefetch too high:
- Increases memory usage and the number of messages held inside the application.
- Can cause one consumer to hold many messages while other consumers sit idle.
- When a consumer dies, many messages are requeued at once.
- Increases latency for waiting messages if one consumer processes slowly.

Prefetch too low:
- Can reduce throughput because the consumer frequently waits for the broker to deliver more messages.
- Underutilizes parallel processing capacity when tasks have wait times.

Choose prefetch based on processing time, message size, concurrency, memory, and latency targets. With manual ack, monitor unacked message counts and ensure the application does not hold messages for too long.

## 12. Acknowledgement Does Not Replace Transactions and Idempotency

A common scenario:

1. Consumer writes to the database successfully.
2. Consumer calls `basicAck`.
3. Connection drops before RabbitMQ receives the ack.
4. RabbitMQ redelivers the message.
5. Consumer writes to the database again.

Even though the application called ack, it cannot know for sure whether the broker received it if the connection drops right afterward. Therefore, business processing must tolerate redelivery.

Mitigations:

- Use a stable event ID to identify messages.
- Create a unique constraint or inbox table to deduplicate.
- Combine the inbox record and business database changes in the same transaction.
- Use an idempotency key for external APIs.
- Ack after business changes have committed.
- Do not treat calling ack as a distributed transaction between RabbitMQ and the database.

If you need to publish a follow-up message after writing to the database, use a transactional outbox. The outbox ensures the publish request is saved alongside the business changes; downstream consumers still need idempotency because the relay may republish.

## 13. Error Handling in Each Mode

| Scenario | AUTO | MANUAL | NONE |
|---|---|---|---|
| Handler succeeds | Container acks | Application calls basicAck | Broker already treated it as acked on delivery |
| Handler throws exception | Container/error handler handles retry/reject | Must ensure delivery is acked/nacked; unacked messages are requeued on channel close | Message may already be removed from the queue |
| Application wants requeue | Use failure/requeue configuration | Call basicNack/basicReject with requeue=true | Cannot request redelivery via ack |
| Application wants DLQ | Configure binder DLQ and failure path | Reject/nack requeue=false with configured DLX | No delivery left to move to DLQ after auto-ack |
| Process crashes mid-processing | Unacked message is redelivered | Unacked message is redelivered | Message may be lost |
| Forgetting to ack | Not applicable to handler code | Message stays unacked until channel closes or timeout/connection recovery | Not applicable |

With MANUAL, if code fails to call ack or nack, the message stays in the unacked state. It can tie up resources and will not be delivered to other consumers until the channel closes or the broker handles a connection failure. This is why every code branch must make an explicit disposition decision.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Messages lost when consumer crashes | Using NONE | Switch to AUTO or MANUAL |
| Message redelivered despite database commit | Broker did not receive ack | Use inbox/idempotency |
| Message loops infinitely | Nack with requeue=true for permanent errors | Classify errors, use DLQ or retry with backoff |
| Consumer holds many unacked messages | Forgot to ack in MANUAL | Audit all branches and channel lifecycle |
| Wrong message acked | Wrong delivery tag or channel used | Read headers from the current message |
| Batch ack loses unprocessed messages | Using multiple=true during parallel processing | Use false or manage completion order |
| DLQ does not receive messages | Missing DLX or autoBindDlq not enabled | Check queue arguments and binder topology |
| AUTO acks despite business error | Handler catches exception and returns normally | Rethrow exception so failure handling triggers |
| Too many retries | Nested retries between framework and MANUAL code | Designate one layer to own retry |
| Unacked count grows continuously | Slow consumer or missing ack | Adjust prefetch/concurrency and fix error handling |
| Using channel after message finishes | Saving channel to ack from background work | Keep ack operations within the delivery lifecycle |

## 15. Testing AUTO, MANUAL, and NONE

You should run integration tests against a real RabbitMQ instance or Testcontainers. The test binder can test function logic, but it does not fully simulate the broker's acknowledgement protocol and redelivery behavior.

### Testing AUTO

1. Create a queue and binding with a stable group.
2. Send a valid message.
3. Verify the handler processes successfully and the message disappears from ready/unacked.
4. Send a message that causes the handler to throw an exception.
5. Verify retry and failure path match configuration.
6. Stop the consumer before processing completes and verify the message is redelivered.

### Testing MANUAL

1. Configure `acknowledgeMode: MANUAL`.
2. Verify the message includes channel and delivery tag headers.
3. Send a valid message; call basicAck after the database commit.
4. Verify the message is removed from the queue.
5. Send a transient-error message; call basicNack with requeue=true and observe redelivery.
6. Send a permanent-error message; call basicReject with requeue=false and verify the DLQ receives the message if configured.
7. Simulate channel close before ack and verify the unacked message is redelivered.
8. Verify the same delivery tag is never acked twice.

### Testing NONE

1. Configure `acknowledgeMode: NONE`.
2. Send a message and verify the broker treats the delivery as immediately acknowledged.
3. Stop the consumer after receiving but before finishing processing.
4. Verify the message is not redelivered as in manual ack mode.
5. Evaluate which business data can accept the risk of message loss.

### Observing in RabbitMQ

Use the RabbitMQ Management UI or metrics to monitor:
- Ready messages.
- Unacked messages.
- Consumer count.
- Redelivery rate.
- Queue ingress/egress.
- DLQ depth.
- Consumer processing latency.

A test that only verifies the function was invoked is not enough to prove ack works properly. You must observe the queue state and broker redelivery behavior.

## 16. Hands-On Exercise: Order Processing Consumer

Build a `processOrder` consumer reading from destination `orders` with group `order-processor`:

1. Start with `AUTO` and write a function that returns normally only after the service commits to the database.
2. Send a valid message and verify the broker receives the ack.
3. Have the service throw a transient exception; verify retry behavior according to `maxAttempts`.
4. Enable DLQ and inspect the message after retries are exhausted.
5. Switch to `MANUAL`, retrieving the channel and delivery tag from headers.
6. Call basicAck after the business transaction succeeds.
7. For transient errors, test basicNack with requeue=true in a test environment.
8. For permanent errors, use basicReject with requeue=false and verify DLX/DLQ.
9. Simulate a process crash after database commit but before ack; verify redelivery does not produce duplicate side effects.
10. Test `NONE` with loss-tolerant telemetry and observe the difference when the consumer stops abruptly.
11. Tune prefetch and monitor unacked message counts.
12. Document the chosen acknowledgement mode along with the business rationale.

Acceptance checklist:

| Item | Expected outcome |
|---|---|
| AUTO | Container acks after listener succeeds |
| MANUAL | Application acks/nacks with correct delivery tag and channel |
| NONE | Message loss risk understood and accepted |
| Exception | Failure path is not swallowed |
| Retry | Bounded with appropriate backoff |
| DLQ | Reject/failure routes to proper dead-letter topology |
| Prefetch | Unacked messages stay within limits |
| Idempotency | Redelivery does not repeat side effects |
| Channel lifecycle | Channel is not retained or used after delivery |
| Observability | Ready, unacked, redelivery, and DLQ are monitored |

## Conclusion

`AUTO`, `MANUAL`, and `NONE` determine when and by whom messages are acknowledged in RabbitMQ. AUTO is the default suited for most Spring Cloud Stream consumers: the container acks after the listener completes normally. MANUAL lets the application control individual deliveries using `basicAck`, `basicNack`, or `basicReject`. NONE uses broker auto-ack and can lose messages if the consumer stops after receiving them.

Choose the mode based on data criticality, coordinate retry/DLQ and prefetch, and design idempotent consumers to tolerate redelivery. Acks only confirm delivery on the consumer side; publisher confirms, queue durability, and transactions are separate mechanisms that must be configured and tested appropriately.

## References

- [Spring Cloud Stream – RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring AMQP – Message Listener Container Acknowledge Mode](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring Integration – Inbound Endpoint Acknowledge Mode](https://docs.spring.io/spring-integration/reference/amqp/inbound-ack.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
