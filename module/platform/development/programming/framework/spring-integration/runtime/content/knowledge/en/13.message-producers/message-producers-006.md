# Error Channel of a Message Producer

In Spring Integration Runtime, a message producer is typically an inbound channel adapter that receives data from an external system and emits Spring Messages onto an output channel. When creating or sending a message into the flow fails, an error channel allows the endpoint to convert the error into an ErrorMessage so a separate processing branch can log, classify, alert, store the error, or route it for recovery.

An error channel is not an automatic retry mechanism, nor does it guarantee that the source message will be acknowledged or redelivered. That outcome still depends on the producer type, transactions, acknowledgments, and how the error flow completes.

## Where Does a Message Producer Emit Errors?

A message producer such as a message-driven channel adapter receives data from a broker or transport, converts it into a Spring Message, and sends it to the output channel. Errors can occur while converting data, constructing the message, sending the message to the channel, or when a downstream handler throws an exception on a synchronous path.

~~~mermaid
flowchart LR
    S["Broker / external source"] --> P["Message producer"]
    P --> O["Output channel"]
    O --> F["Integration flow"]
    P -. "exception" .-> E["ErrorMessage"]
    E --> EC["Producer error channel"]
    EC --> H["Error handler / recovery flow"]
~~~

Endpoints based on MessageProducerSupport expose an error channel property. It can be configured with a MessageChannel instance or a bean name. If no error channel is configured, the endpoint propagates the exception back to the message-driven source for the transport/container to handle according to its policy. Setting nullChannel as the error channel discards errors from the processing flow; use this only when ignoring errors is intentional.

## What Does an ErrorMessage Contain?

Spring Integration represents errors as an ErrorMessage. The payload of an ErrorMessage is a Throwable, usually the exception that occurred. An ErrorMessage can also carry originalMessage to trace the message that caused the error, along with relevant headers.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

void inspect(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    // cause: exception to classify or record
    // original: input message if identifiable
}
~~~

Not every error has an originalMessage. For example, an error occurring before a Spring Message is fully constructed may have no original message. When handling errors, always check this value before reading its payload or headers. Avoid logging the full payload if the message contains personal data, secrets, or credentials.

## Configuring a Dedicated Error Channel for a Producer

Example using a JMS message-driven channel adapter. The error channel is attached directly to the producer endpoint:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageChannel;
import jakarta.jms.ConnectionFactory;

@Bean
MessageChannel producerErrorChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow ordersInbound(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from(
                    Jms.messageDrivenChannelAdapter(connectionFactory)
                            .destination("orders")
                            .errorChannel("producerErrorChannel"))
            .channel("orders.input")
            .get();
}
~~~

With the XML namespace, the adapter has a corresponding error-channel attribute:

~~~xml
<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        destination="orders"
        channel="orders.input"
        error-channel="producerErrorChannel"/>
~~~

Other transport adapters may provide equivalent configuration through DSL, namespace, or endpoint beans. At the API level, MessageProducerSupport provides setErrorChannel and setErrorChannelName methods. Check the API of the specific adapter and Spring Integration version in use, because not all inbound source types expose the same configuration attributes.

Create a consumer for the error channel so ErrorMessages are not left unhandled:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
class ProducerErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ProducerErrorHandler.class);

    @ServiceActivator(inputChannel = "producerErrorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        Message<?> original = errorMessage.getOriginalMessage();

        log.error("Inbound producer failed; original message: {}",
                original, cause);

        // Classify the error, emit metrics, or forward to a recovery flow.
    }
}
~~~

If you want to separate error categories, the consumer can forward the ErrorMessage to a router or separate channels—for example, invalid data errors, transient connection errors, and unrecoverable errors. Preserve exception details and message identifiers when routing so they can be correlated with transport logs.

## Distinguishing Three Error Routing Mechanisms

The name errorChannel appears across multiple layers of Spring Integration, but its scope of application differs.

| Mechanism | When it is used | Where the error goes |
|---|---|---|
| errorChannel property on message producer | Producer endpoint encounters an error creating or sending a message into the flow | Channel configured on the endpoint; if absent, the exception propagates back to the message-driven source |
| MessageHeaders.ERROR_CHANNEL header | A message is processed in an asynchronous task and that task throws an exception | Channel in the failing message's header; if absent, falls back to the global errorChannel |
| errorChannel on poller | A scheduler-triggered task to poll a source or run a poller fails | Channel configured for the poller; if unconfigured, uses the scheduler's error handler, typically the global errorChannel |

### Errors in Synchronous Flows

With the default DirectChannel, handlers run on the same thread that calls send. If a handler throws an exception, the exception can propagate back up the call stack to the sender. This is standard Java synchronous behavior. A message-driven producer with its own error channel can catch errors during the message send operation and emit an ErrorMessage to the configured channel. However, do not assume every exception in every synchronous flow is automatically routed to the global errorChannel.

### Errors in Asynchronous Flows

With ExecutorChannel or a task running on a TaskExecutor, the sender may have already finished before the handler raises an exception. The framework uses MessagePublishingErrorHandler to publish an ErrorMessage. This mechanism prefers the errorChannel header of the message being processed; if no header is present, it sends to the global channel named errorChannel.

You can attach a dedicated channel to a message before passing it across an asynchronous boundary:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder.withPayload("order-123")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "ordersAsyncErrors")
        .build();
~~~

This header controls error routing for the asynchronous task processing that message. It does not replace the errorChannel property configured directly on a MessageProducerSupport endpoint.

### Errors in Pollers

For inbound channel adapters using a poller, errors can occur when calling the source, converting data, or sending the message to the output channel. You can configure an error channel on the poller:

~~~java
@InboundChannelAdapter(
        value = "polledInput",
        poller = @Poller(
                fixedDelay = "1000",
                errorChannel = "pollerErrors"
        )
)
public String pollSource() {
    return readNextRecord();
}
~~~

Scheduled poller errors are wrapped into an ErrorMessage by MessagePublishingErrorHandler. If you declare a custom taskScheduler, ensure the scheduler has an appropriate error handler if you want to continue routing errors through a message flow.

## Global errorChannel

Spring Integration creates a default bean named errorChannel. By default, this is a PublishSubscribeChannel with a LoggingHandler registered to log errors at ERROR level. Asynchronous tasks without a dedicated errorChannel header usually send errors to this channel.

You can register a global error-handling endpoint:

~~~java
@Component
class GlobalErrorHandler {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        Message<?> original = errorMessage.getOriginalMessage();

        // Write structured logs, emit metrics, or route the error.
    }
}
~~~

When you need to control distribution, you can define your own errorChannel bean—such as a PublishSubscribeChannel so multiple subscribers receive the same error, or a QueueChannel to decouple error emission from consumption. Choose the channel type according to synchronization, buffering, and backpressure requirements.

Since Spring Integration 5.4.3, the default global errorChannel is configured with requireSubscribers=true. Consequently, when no subscribers remain to receive an ErrorMessage, dispatching can throw MessageDispatchingException. This helps surface missing-consumer issues rather than silently dropping errors. If replacing the default channel or shutting down the application, verify subscribers and behavior when endpoints stop.

## Error Flows and Source Transactions

An error channel specifies where exceptions are handled as messages. An error flow completing normally usually means the error was handled at the messaging layer; it does not automatically instruct the broker to redeliver the message.

For sources supporting transactions or acknowledgments, explicitly decide behavior after an error is sent to the error channel:

- If the error flow records the error and finishes normally, the adapter/container may treat the callback as handled. With a transactional source, the transaction may commit and the message will not be redelivered.
- If you want a rollback or redelivery, the error flow may need to rethrow the exception so it propagates back to the listener container. The exact behavior depends on the transport, transaction manager, and acknowledgment mode.
- If the error involves poison data or cannot be fixed by retries, route the message to a dead-letter queue or a searchable error store to avoid infinite loops.
- If the error is transient, use bounded retries, backoff, and a recovery policy. An error channel does not perform retries on its own.

For the JMS message-driven adapter, Spring Integration documentation explicitly notes that when conversion errors are sent to an error channel, rolling back the transaction requires the error flow to rethrow the exception (or throw another exception). If the error flow finishes normally, the transaction may commit and the message is removed from the source. Verify actual container policies before relying on redelivery behavior.

## Designing Error Consumers

A good error handler preserves context, avoids secondary errors masking the original error, and takes a clear final action.

1. Extract the exception from the ErrorMessage payload and inspect originalMessage if present.
2. Record the correlation ID, message ID, source, endpoint, and exception type. Do not log sensitive data.
3. Classify transient errors vs. unrecoverable errors. Only retry errors likely to succeed on subsequent attempts.
4. Bound retry attempts, use backoff, and ensure operations are idempotent to avoid repeated side effects.
5. For unrecoverable errors, persist the message along with exception details in a searchable store or route to a dead-letter flow.
6. Decide whether to rethrow the exception to request source rollback/redelivery; this decision must align with the transport's transaction and acknowledgment semantics.

Do not merely log and return if the system must guarantee no data loss. Nor should you unconditionally rethrow every error: permanent data errors can cause the broker to redeliver the same message forever.

## Diagnosing When ErrorMessages Do Not Arrive

| Symptom | What to check |
|---|---|
| Exception appears in broker/container logs | Does the producer have an errorChannel configured; is the adapter propagating exceptions back to the source |
| Asynchronous errors appear only on the global errorChannel | Does the message carry the MessageHeaders.ERROR_CHANNEL header; does the header point to the right channel |
| Errors from DirectChannel propagate back to sender | This may be normal synchronous behavior; check if the producer endpoint has its own errorChannel |
| ErrorMessage is emitted but has no consumer | Bean name, channel subscribers, and endpoint lifecycle |
| Source message is not redelivered | Did the error flow finish normally; which transaction manager and acknowledgment mode are in use |
| originalMessage is missing | Did the failure happen before message creation completed, or does ErrorMessageStrategy retain the request message |
| Errors repeat continuously | Retries in adapter, container, or broker; retry limits and dead-letter policy |

When observing runtime behavior, track ErrorMessage counts by producer and exception type, error channel consumption rate, retry counts, messages routed to dead-letter flows, and age of unresolved errors. If the error channel is a QueueChannel, also monitor queue depth to detect when the error handler cannot keep up with error emission rates.

## Choosing the Mechanism by Emission Source

| Scenario | Configuration to consider |
|---|---|
| Message-driven inbound adapter needs its own error-handling branch | errorChannel property on the producer endpoint |
| Multiple asynchronous flows need a default error destination | Global errorChannel |
| Individual messages need error routing to different destinations | MessageHeaders.ERROR_CHANNEL header |
| Inbound adapter polls a source on a schedule | errorChannel on the poller |
| Need broker redelivery when processing fails | Transaction/acknowledgment settings and propagating exceptions back to the source |
| Need to store errors for manual resolution | Error flow writing to an error store or dead-letter channel |

Configure error channels according to where exceptions actually originate, retain message identifiers for traceability, and design commit, rollback, retry, or dead-letter decisions explicitly. Understanding the boundaries between producer endpoints, asynchronous tasks, and pollers makes error diagnosis in Spring Integration Runtime much more accurate.

## References

- [Spring Integration - Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration - JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)
- [MessageProducerSupport API](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/MessageProducerSupport.html)
