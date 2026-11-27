# Publisher Confirms, Publisher Returns, and Unroutable Messages

When an application sends a message to RabbitMQ, a successful send method call only indicates that the application handed the send request to the client/binder. It does not prove the broker received the message, routed it to a queue, or that a consumer processed it. The network may drop after the client writes a frame, the exchange may have no matching queue, or the broker may fail to persist the message due to an internal error.

RabbitMQ provides two complementary mechanisms on the publisher side:

- **Publisher confirms** indicate whether the broker has accepted responsibility for a message or rejected it with a negative acknowledgement.
- **Publisher returns** send a message back to the publisher when it cannot be routed to any queue and the publisher sent it in mandatory mode.

The Spring Cloud Stream RabbitMQ binder integrates these two mechanisms with Spring AMQP. The application can receive results asynchronously via an error channel, or attach correlation data to the message and wait on the publisher confirm Future. This lesson explains the meaning of each outcome, how to configure the binder, and how to handle unroutable messages.

## 1. Why Do Publishers Need Confirmation?

RabbitMQ is a distributed system. After the client writes data to the socket, the application cannot conclude the broker received and processed the message. The connection may drop before the frame reaches the broker; the broker may receive the message while the response is lost; or the exchange may fail to find a destination queue.

Without tracking confirmations, an application can:

- Report success even though the broker never accepted the message.
- Lose messages if the broker stops before writing persistent messages to disk.
- Fail to detect messages dropped because no queue matched.
- Resend messages when the previous attempt's outcome is unknown, creating duplicate records.

Overall processing flow:

~~~mermaid
flowchart TD
    A[Application publishes] --> B[RabbitMQ exchange]
    B --> C{Matching queue?}
    C -->|Yes| D[Queue receives message]
    C -->|No| E{mandatory?}
    E -->|false| F[Discard or Alternate Exchange]
    E -->|true| G[Basic.Return to publisher]
    D --> H[Publisher Confirm ACK]
    F --> I[Publisher Confirm ACK after broker processes route]
    G --> J[Publisher Confirm ACK after Basic.Return]
    D --> K[Consumer receives and processes later]
~~~

Publisher confirms and consumer acknowledgements sit at opposite ends. Confirms reflect the broker taking responsibility for a message; consumer ACKs reflect a consumer confirming a delivery. A publisher confirm does not mean a consumer has read or successfully processed the business logic.

## 2. What Are Publisher Confirms?

Publisher confirms are a mechanism where the broker sends an acknowledgement back to the publisher after handling a publish. When a channel is in confirm mode, RabbitMQ tracks messages published on that channel and sends one of two outcomes:

- **ACK:** the broker has accepted responsibility for the message.
- **NACK:** the broker could not process the message successfully and declines responsibility for it.

An ACK is issued once the message is accepted by all queues the exchange routes to. For persistent messages routed to durable queues, confirmation is sent after the message is persisted durably. For quorum queues, the broker confirms once the quorum replicas have accepted the message per queue semantics.

A NACK is rare and usually relates to an internal broker error while handling a queue. Certain queue length limit configurations with the **reject-publish** overflow policy can also cause publishers to receive a NACK.

### Confirm Is Not Consumer ACK

| Mechanism | Sender | Confirmer | Meaning |
|---|---|---|---|
| Publisher confirm | Producer | RabbitMQ broker | Broker has accepted responsibility or rejected the message. |
| Consumer acknowledgement | Consumer | RabbitMQ broker | Consumer confirms a delivery was processed or requests reject/requeue. |

For example, the broker can ACK a message right after storing it in a durable queue, while the consumer may not yet be started or may be offline. Conversely, a consumer may finish processing a message while the producer never receives the confirm because its connection dropped. Neither outcome replaces the other.

### Confirm Does Not Guarantee Exactly-Once Business Processing

Publisher confirms protect the leg from publisher to broker. They do not cover the consumer's database transaction, HTTP side effects, or the consumer committing its ACK. If a publisher does not receive a confirm before timeout, the outcome is ambiguous: the broker may have received the message while the confirm was lost on the way back.

If you resend in an ambiguous outcome case, the broker may receive two copies. Attach a stable event ID and design idempotent consumers to handle republishing.

## 3. Publisher Returns and Unroutable Messages

RabbitMQ exchanges route messages based on exchange type, routing key, and bindings. A message is **unroutable** when the exchange finds no matching queue.

Examples:

- The exchange exists, but no queue has been bound to it yet.
- The routing key does not match any topic/direct exchange binding.
- The queue was deleted or the binding was removed.
- The producer sends to the right exchange name but uses the wrong routing key.

In AMQP 0-9-1, the **mandatory** property governs how the broker handles unroutable messages:

- **mandatory=false:** this is the protocol default. The broker discards the message or forwards it to an Alternate Exchange if one is configured on the exchange.
- **mandatory=true:** if no queue receives the message and no alternate route handles it, the broker sends **Basic.Return** back to the publisher. The publisher must have a return handler to receive and process the message.

Publisher returns are therefore the mechanism for detecting unroutable messages. They are not the same as a publisher NACK: a return says the message could not be routed to any queue, whereas a NACK says the broker could not successfully process the message.

### Details Inside a Returned Message

When the binder converts a returned message into an error, the **ReturnedAmqpMessageException** payload provides:

| Property | Meaning |
|---|---|
| **failedMessage** | Original Spring Messaging Message that was sent and returned. |
| **amqpMessage** | Raw AMQP message received by Spring AMQP. |
| **replyCode** | Broker reply code, e.g. 312. |
| **replyText** | Short description, usually NO_ROUTE. |
| **exchange** | Exchange to which the publisher sent the message. |
| **routingKey** | Routing key used when publishing. |

Code **312 - NO_ROUTE** typically indicates no queue received the message under the current routing configuration.

### Return Does Not Necessarily Mean the Exchange Does Not Exist

If the exchange does not exist, RabbitMQ raises a channel-level exception and closes the channel; that is not a normal Basic.Return scenario. Returns primarily reflect that the exchange exists, but no routed queue received the message.

If the exchange has an Alternate Exchange and the alternate exchange successfully routes the message, the message is forwarded to the alternate exchange. In that case, the message has been routed and the publisher normally does not receive a returned message for that publish. Always check alternate exchange configuration when investigating messages missing from the main queue.

## 4. Why Checking Confirm ACK Alone Is Not Enough

When a message is unroutable and the publisher sent with **mandatory=true**, RabbitMQ sends Basic.Return first, followed by a publisher confirm ACK for the publish. Here, ACK means the broker processed the publish; it does not assert the message reached a business queue.

If an application checks only ACK, it may mark a message as successfully sent even though the message was just returned.

| Outcome | Confirm | Return | Interpretation |
|---|---|---|---|
| Message routed | ACK | None | Broker accepted the message and routed it to at least one queue. |
| No matching queue, mandatory=true | ACK may still be sent after return | Present | Broker processed the publish, but the message reached no queue. |
| Broker could not process message | NACK | Usually none | Broker declined responsibility; investigate broker/queue error. |
| No confirm before timeout | Unknown | Possibly unknown | Outcome indeterminate; do not conclude the message was definitely lost or definitely received. |

To conclude a message was routed, combine publisher confirm with publisher return. When using Spring AMQP's correlation data, the returned message is attached to the correlation object before the confirm Future completes.

## 5. Enabling Confirms and Returns for the Spring Cloud Stream Rabbit Binder

By default, the RabbitMQ binder uses Spring Boot's ConnectionFactory. Publisher confirms and publisher returns can be configured via Spring Boot properties.

Example:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              use-confirm-header: true
~~~

Meaning of each property:

- **spring.rabbitmq.publisher-confirm-type: correlated** enables correlated publisher confirms. This is required for Spring AMQP to correlate confirm results with CorrelationData.
- **spring.rabbitmq.publisher-returns: true** enables receiving returned messages on the ConnectionFactory.
- **producer.error-channel-enabled: true** tells Spring Cloud Stream to route binder-supported asynchronous send errors to an error channel.
- **use-confirm-header: true** selects the correlation data header mechanism to obtain per-message confirm results.

In older Spring Boot versions, the property to enable confirms may be **spring.rabbitmq.publisher-confirms**. Use the property name matching the Spring Boot/Spring AMQP version managed by your project BOM; in current configurations, prefer publisher-confirm-type.

Do not simply enable publisher returns and assume every unroutable message will be returned. AMQP requires the message to be published with **mandatory=true** for the broker to send Basic.Return. When using RabbitTemplate directly, set mandatory or mandatory-expression appropriately. With the Rabbit binder producer, use the binder's integrated return handling path and test with an unmatched routing key to verify behavior on your deployed version.

## 6. Receiving Errors via the Producer Error Channel

Spring Cloud Stream can create an error channel for asynchronous send results. With the RabbitMQ binder, the two primary publish errors are:

1. Returned message because the message was not routed.
2. Negative publisher confirm because the broker declined to process the message.

To receive these errors on the error channel, simultaneously:

- Enable **producer.error-channel-enabled** on the output binding.
- Enable publisher confirms on the ConnectionFactory.
- Enable publisher returns on the ConnectionFactory if you want to receive returned messages.

The configuration example was shown in the previous section. Then the application can register a handler on the global Spring Integration error channel:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.amqp.support.NackedAmqpMessageException;
import org.springframework.integration.amqp.support.ReturnedAmqpMessageException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class RabbitPublishErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(RabbitPublishErrorHandler.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();

        if (cause instanceof ReturnedAmqpMessageException returned) {
            log.error(
                    "Message has no receiving queue: exchange={}, routingKey={}, code={}, reason={}",
                    returned.getExchange(),
                    returned.getRoutingKey(),
                    returned.getReplyCode(),
                    returned.getReplyText()
            );
            return;
        }

        if (cause instanceof NackedAmqpMessageException nacked) {
            log.error(
                    "RabbitMQ NACK during publish: {}",
                    nacked.getNackReason(),
                    nacked
            );
            return;
        }

        log.error("Asynchronous message send error", cause);
    }
}
~~~

The example above uses the global error channel for illustration. An ErrorMessage for a returned message carries payload **ReturnedAmqpMessageException**; for a negative confirm, the payload is **NackedAmqpMessageException**. Both contain **failedMessage** so the application knows which original message failed.

The error channel does not automatically store messages in a DLQ. The application must decide how to handle them: write an audit log, store in an outbox/retry store, alert operations, fix routing and resend, or move to a parking-lot destination.

## 7. Per-Binding Handling and Distinguishing Error Channels

If multiple output bindings enable producer error channels, the global **errorChannel** may receive errors from multiple sources. When handling them, inspect failedMessage and metadata to identify the binding, exchange, routing key, correlation ID, and event ID.

Spring Cloud Stream also has error channels tied to destination/group for inbound flows. The naming convention is typically **<destination>.<group>.errors**. Producer send failures are asynchronous errors on an output binding; do not confuse them with exceptions thrown by a consumer function while processing an inbound message.

A practical implementation approach:

- Use the correlation header when exact per-message outcomes are needed.
- Use the producer error channel to centrally observe asynchronous errors.
- Attach binding name, event ID, and correlation ID to logs/metrics.
- Do not register multiple handlers consuming the same error channel unless you deliberately designed fan-out.

## 8. Publisher Confirms via confirmAckChannel

The Rabbit binder supports an older mechanism for receiving positive publisher confirms via **confirmAckChannel**. The property value is the name of the Spring MessageChannel receiving confirmations. If the channel does not exist yet, the binder can register a DirectChannel under that name.

Example:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              confirm-ack-channel: orderPublisherConfirms
~~~

The application registers a handler for channel **orderPublisherConfirms** to receive positive confirms:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class RabbitConfirmChannelHandler {

    private static final Logger log =
            LoggerFactory.getLogger(RabbitConfirmChannelHandler.class);

    @ServiceActivator(inputChannel = "orderPublisherConfirms")
    public void onConfirm(Message<?> message) {
        log.info("RabbitMQ publisher confirm: {}", message);
    }
}
~~~

This is a legacy mechanism. Positive confirms go to confirmAckChannel; negative confirms go to the error channel if enabled. By default, confirmAckChannel is **nullChannel**, so positive confirms are discarded unless a channel is specified.

Do not configure both **confirm-ack-channel** and **use-confirm-header** on the same producer binding. These two mechanisms are mutually exclusive. For new code, the correlation data header and Future are usually more convenient because outcomes can be tied directly to the corresponding message.

## 9. Preferred Mechanism: useConfirmHeader and CorrelationData

Since Rabbit binder 3.1, you can place a **CorrelationData** object into the **AmqpHeaders.PUBLISH_CONFIRM_CORRELATION** header. After publishing, the application reads the result from **CorrelationData.getFuture()**. This is the mechanism preferred by the Rabbit binder documentation.

CorrelationData contains:

- An ID used to link the result to the message. When publisher returns are enabled, the ID must be unique so the framework can correlate returned messages.
- A Future that completes when the broker sends a confirm.
- A returned message if the broker could not route the message.

Example sending a message via StreamBridge:

~~~java
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.core.AmqpHeaders;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.connection.CorrelationData.Confirm;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(OrderCreated event) {
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(
                        AmqpHeaders.PUBLISH_CONFIRM_CORRELATION,
                        correlation
                )
                .build();

        boolean sent = streamBridge.send("orderPublisher-out-0", message);
        if (!sent) {
            throw new IllegalStateException(
                    "Failed to send message to output binding");
        }

        try {
            Confirm confirm = correlation.getFuture()
                    .get(10, TimeUnit.SECONDS);

            ReturnedMessage returned = correlation.getReturned();
            if (returned != null) {
                throw new IllegalStateException(
                        "Message has no receiving queue: exchange="
                                + returned.getExchange()
                                + ", routingKey="
                                + returned.getRoutingKey()
                                + ", reason="
                                + returned.getReplyText()
                );
            }

            if (!confirm.isAck()) {
                throw new IllegalStateException(
                        "RabbitMQ NACK: " + confirm.getReason());
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for publisher confirm", ex);
        }
        catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException(
                    "Did not receive publisher confirm in time", ex);
        }
    }
}
~~~

The check order is intentional:

1. Wait for the confirm Future to complete.
2. Check **correlation.getReturned()**. If a returned message is present, the message was not routed to any queue.
3. If there is no return, check **confirm.isAck()**. NACK means the broker declined responsibility.
4. Consider the publish accepted and routed by the broker only when ACK is true and there is no returned message.

In newer Spring AMQP versions, use **getReturned()** to obtain the ReturnedMessage with reply code, reply text, exchange, and routing key. Some older versions had **getReturnedMessage()**; that method was replaced by getReturned() in newer releases.

The example waits up to 10 seconds for illustration. In high-load systems, avoid blocking a business thread per message if you can send in batches or process Futures asynchronously. The binder documentation illustrates sending multiple messages first and then awaiting the Futures, which suits batch listeners.

## 10. Why Does CorrelationData Need a Unique ID?

Publisher confirms and returns are delivered asynchronously. An application may publish hundreds of messages before receiving results. Without a correlation ID, the application cannot easily tell which message an ACK, NACK, or returned message belongs to.

When returns are enabled, Spring AMQP uses the CorrelationData ID to associate Basic.Return with the message awaiting confirmation. Duplicate IDs can miscorrelate results or fail to attach the returned message to the right publish attempt.

Best practices:

- Use a unique UUID or event ID per publish attempt.
- Keep a stable event ID in the payload for business deduplication.
- Use a unique correlation ID for each publish attempt to distinguish retries.

When resending the same event, you can keep the same business event ID while generating a new correlation ID for the new attempt. That way logs can tie attempts of the same event together without mixing up confirm results.

## 11. Handling Unroutable Messages with an Alternate Exchange

RabbitMQ supports **Alternate Exchange (AE)**. When the primary exchange cannot route a message to any queue, the broker can try routing the message through the alternate exchange attached to the primary exchange.

An AE is suitable when you want to retain messages with unmatched routing keys in a separate queue for inspection instead of returning them to the publisher. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              alternate-exchange:
                name: unrouted-orders
                type: topic
                exists: false
                binding:
                  queue: unrouted-orders-audit
                  routing-key: "#"
~~~

This example shows the binder declaring a simple alternate exchange and queue binding. If you need custom queue arguments, durability, or complex topology, provision and bind the resources via separate infrastructure management and configure the binder to use the existing resources.

When an AE receives a message, the message has been routed to a queue on the alternate branch. Consequently, a publisher return does not occur as it would when no route exists at all. Distinguish the two goals:

- **Publisher return:** notifies the publisher that the message was not routed to a queue.
- **Alternate Exchange:** captures/routes unmatched messages into another branch.

An AE does not fix routing keys automatically, nor does it guarantee the business destination queue processed the message. The alternate queue should be monitored and have its own handling process.

## 12. A Returned Message Is Not a Dead Letter Queue

Publisher return occurs on the publish side when a message is not routed to any queue. A Dead Letter Queue (DLQ) is a queue receiving messages dead-lettered from a source queue, typically due to consumer rejection, expired message TTL, or queue limits triggered by policy.

| Criterion | Publisher return | Dead Letter Queue |
|---|---|---|
| Timing | Immediately when the exchange finds no matching route. | After the message enters a queue and gets dead-lettered. |
| Where detected | Publisher. | Broker/queue topology or consumer. |
| Example causes | Missing binding or unmatched routing key. | Consumer reject, expired TTL, queue length/overflow policy. |
| Destination | Publisher return callback or error/correlation channel. | DLQ bound to a DLX. |
| Automatically enters DLQ? | No. | Yes, if queue/DLX are configured properly. |

The Rabbit binder does not automatically send ReturnedAmqpMessageException or NackedAmqpMessageException to a DLQ. The error channel is merely where the application receives errors in-process. If you want to persist failed messages, you must publish the original message to an error/parking-lot queue yourself or save it in a database/outbox with an appropriate retry mechanism.

## 13. Negative Confirm and Returned Message Require Different Handling

The two error types have different causes and remediation paths:

| Error | Possible causes | Appropriate action |
|---|---|---|
| Returned message, NO_ROUTE | Wrong routing key, missing binding, queue not provisioned yet. | Check exchange, queue, binding, and routing key; after fixing the route, resend per policy. |
| NACK | Internal queue error or queue overflow reject-publish. | Check broker logs, queue policy, capacity, and node health; bounded retry if appropriate. |
| Channel exception, exchange does not exist | Publishing to an undeclared or misspelled exchange. | Fix topology/exchange name; verify channel and connection recovery. |
| Confirm timeout | Slow broker/connection or confirm lost in transit. | Mark outcome indeterminate; reconcile or retry with idempotency. |
| StreamBridge.send returns false | Failed to send into the binding at call time per API result. | Check binding, destination, and local error; no broker confirm yet to conclude delivery. |

Do not retry a returned message endlessly if routing has not been fixed. Every retry will continue having no route, generating repeated load and logs. Likewise, NACKs should not be retried indefinitely when the broker is overloaded or a queue is enforcing reject-publish.

## 14. Handling Ambiguous Outcomes After Timeout or Disconnect

A difficult case occurs when the publisher sends a message, the broker receives and persists it, but the connection drops before the ACK reaches the client. The publisher does not know whether the message was received.

If the publisher resends, the broker may receive a second copy. If the publisher does not resend, the broker may have received the message, yet the application never recorded confirmation.

This is why publisher confirms do not create exactly-once delivery. A common strategy:

1. Attach a unique event ID to the payload or business header.
2. Save the publish state to an outbox before sending.
3. Wait for confirm/return and update the outbox state.
4. On timeout, mark the state indeterminate and perform controlled retry.
5. Consumers use the event ID as an idempotency key to skip already-processed duplicates.
6. Maintain a reconciliation process for events stuck in prolonged timeout.

For financial or critical business data, record event ID, correlation ID, exchange, routing key, send timestamp, confirm status, returned metadata, and retry count. Operations can then investigate a publish without piecing together fragmented logs.

## 15. Testing Publisher Confirms and Returns

Unit testing a method that calls StreamBridge cannot prove RabbitMQ received or routed the message. You need integration tests with a real test RabbitMQ broker, such as Testcontainers, to verify actual confirms and returns.

### Successfully Routed Message Scenario

1. Create an exchange and queue.
2. Bind the queue to the exchange with a matching routing key.
3. Enable correlated publisher confirms and publisher returns.
4. Publish a mandatory message.
5. Wait for the confirm Future.
6. Verify ACK and no returned message.
7. Read from the queue to verify the message is actually present.

### No Matching Queue Scenario

1. Create an exchange without binding a queue, or use a mismatched routing key.
2. Enable publisher returns and publish mandatory.
3. Receive the returned message.
4. Verify reply code, reply text, exchange, and routing key.
5. Wait for confirm and verify the returned message was attached to CorrelationData before the Future completed.
6. Verify the application does not mark the message as routed solely because of confirm ACK.

### Test Matrix

| Scenario | Setup | Expected verification |
|---|---|---|
| Successful route | Valid exchange, queue, and binding. | Confirm ACK, no return. |
| Missing binding | Exchange exists with no matching queue; mandatory=true. | Returned message, typically reply code 312 and NO_ROUTE. |
| Wrong routing key | Queue has a binding, but key mismatches; mandatory=true. | Returned message containing the exchange and routing key used. |
| Non-mandatory | Message unroutable and mandatory=false. | Message may be discarded or sent to AE; no return. |
| Alternate Exchange | Primary exchange does not route, but AE has a matching queue. | Message received by AE; not treated as an unrouted return. |
| Negative confirm | Configure queue overflow reject-publish or simulate appropriate broker failure. | NACK or publish error received and recorded. |
| Non-existent exchange | Publish to an undeclared exchange name. | Channel-level exception, not confused with NO_ROUTE return. |
| Confirm timeout | Lower timeout or drop connection in test. | Application marks outcome indeterminate, does not conclude message was definitely lost. |
| Multiple messages | Send multiple messages with distinct correlation IDs. | Each confirm/return matches the right message. |
| Producer error channel | Enable error-channel-enabled and configure confirms/returns. | ErrorMessage contains expected exception and failedMessage. |
| Consumer inactive | Durable queue exists with no active consumer. | Publisher can still receive ACK because broker accepted message into queue. |
| Consumer processing error | Consumer receives message and rejects or sends to DLQ. | Do not confuse consumer failure with publisher return. |

### Metrics to Monitor

- Publisher ACK and NACK counts.
- Returned message counts by exchange and routing key.
- Ratio of NO_ROUTE to total publishes.
- Confirm wait timeout count.
- Pending confirm count and confirm latency.
- Messages routed to Alternate Exchange.
- Retry count after publish failures.
- Events sitting unconfirmed in the outbox.

Do not log full payloads if they contain personal or sensitive data. Logging event ID, correlation ID, and routing metadata is usually sufficient for tracing.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Confirm not received | ConnectionFactory does not have correlated confirms enabled or wrong version property used. | Check publisher-confirm-type and actual ConnectionFactory. |
| Returned message not received | Publisher returns not enabled or message not sent mandatory. | Enable publisher-returns and verify return handling/mandatory on producer. |
| Confirm ACK received but message missing from main queue | Message may be unroutable with mandatory=false, or routed through Alternate Exchange. | Combine return with confirm; check AE and routing. |
| NACK confused with NO_ROUTE | The two responses have different meanings. | Inspect NackedAmqpMessageException and ReturnedAmqpMessageException separately. |
| Error channel receives no errors | Producer lacks error-channel-enabled or ConnectionFactory lacks confirms/returns. | Verify all three settings. |
| Positive confirm never arrives on channel | confirmAckChannel is still nullChannel or channel not declared. | Set confirm-ack-channel; or use use-confirm-header. |
| Both confirm mechanisms configured | useConfirmHeader and confirmAckChannel are mutually exclusive. | Pick one mechanism per binding. |
| Returned message cannot correlate | CorrelationData ID not unique or missing when returns enabled. | Generate a unique correlation ID for each publish attempt. |
| Retries cause duplicate messages | Timeout left publish outcome unknown and app resent. | Use outbox, event ID, and idempotent consumers. |
| Expecting returns in DLQ but finding none | Rabbit binder does not automatically route producer errors to DLQ. | Handle error channel explicitly and publish/persist failed messages. |

When investigating, check in order: exchange exists, queue exists, binding/routing key, mandatory, publisher returns, correlated confirms, error-channel-enabled, correlation ID, and broker state. Read both reply code/reply text and the confirm result to determine accurately whether the message was routed.

## 17. Pre-Deployment Checklist

- [ ] ConnectionFactory enables publisher confirms in correlated mode.
- [ ] Publisher returns are enabled if unroutable messages must be detected.
- [ ] Producer sends mandatory when unroutable message detection is required.
- [ ] Output binding enables error-channel-enabled if receiving async send errors via error channel.
- [ ] Choose either use-confirm-header or confirm-ack-channel; never configure both simultaneously.
- [ ] CorrelationData has a unique ID for each publish attempt.
- [ ] Application inspects both ACK/NACK and returned message.
- [ ] Do not treat StreamBridge.send returning true as a broker confirm.
- [ ] Timeouts and handling for indeterminate publish states are in place.
- [ ] Event ID and idempotency handle duplicates during retries.
- [ ] Processes exist for returned messages, NACKs, and channel exceptions.
- [ ] Never assume producer errors are automatically routed to a DLQ.
- [ ] Integration tests verify successful routing, NO_ROUTE, AE, and NACK.
- [ ] Metrics track confirm latency, returns, NACKs, and retries.

Publisher confirms indicate RabbitMQ accepted responsibility for a message; publisher returns notify when a message could not be routed to any queue while published as mandatory. Both outcomes must be checked together: an unroutable message can still receive a confirm ACK after the broker sends a return. The Spring Cloud Stream Rabbit binder supports receiving outcomes via the producer error channel or the correlation data header with Future<Confirm>. By combining confirms, returns, routing tests, an outbox, and idempotent consumers, an application can detect unroutable messages early and manage send states safely.

## References

- [Spring Cloud Stream — RabbitMQ Binder Reference Guide: Publisher Confirms](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Binding Properties: errorChannelEnabled](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring AMQP — Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Publishers and Unroutable Message Handling](https://www.rabbitmq.com/docs/publishers)