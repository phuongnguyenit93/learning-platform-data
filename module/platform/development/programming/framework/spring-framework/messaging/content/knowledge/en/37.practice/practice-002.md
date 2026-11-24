# Experimenting with Interceptors, Payload Conversion, and Runtime Errors

## Objectives

After this lesson, you will be able to:

- Determine when interceptors run in the message sending and receiving lifecycle.
- Distinguish between ChannelInterceptor and ExecutorChannelInterceptor.
- Use MessageConverter and codecs to convert payloads between objects, JSON, strings, and bytes.
- Configure payload conversion for STOMP/WebSocket and RSocket.
- Categorize errors during sending, conversion, routing, and message processing.
- Write unit tests and integration tests to reproduce runtime errors, verify results, and avoid breaking unrelated connections.

## 1. Viewing the Message Pipeline as Observable Boundaries

A message in Spring Messaging typically passes through a sequence of steps:

1. The producer creates the payload and metadata.
2. MessageChannel receives the message.
3. Interceptors can inspect, add headers, record timing, or reject the message.
4. The adapter/transport turns the message into frames or wire data.
5. The receiving side decodes and converts the payload to the data type required by the handler.
6. The message is routed to the handler.
7. The handler executes business logic and returns a result or emits an error.

An error can occur at any step. For example:

- The producer sends a message, but the channel rejects it.
- An interceptor detects a missing required header.
- The payload cannot be converted from JSON to a DTO.
- The route has no corresponding handler.
- The handler throws an exception while accessing the database.
- The transport closes while a response is being sent.

When experimenting, observe each boundary. If you only look at the final exception, you might confuse a payload conversion error with a business logic error or a transport error.

## 2. ChannelInterceptor: Observing and Modifying Messages on a Channel

ChannelInterceptor is a hook at the MessageChannel layer. It allows observing or modifying messages when a channel sends/receives data. Commonly used methods:

| Callback | Timing | Purpose |
| --- | --- | --- |
| preSend | Before the channel sends the message | Inspect, add headers, replace message, or reject |
| postSend | After the channel performs send | Record whether the send succeeded or failed |
| afterSendCompletion | After the entire send process completes | Cleanup and record exceptions if any |
| preReceive | Before a polling channel receives a message | Allow or prevent the receive call |
| postReceive | After receive retrieves a message | Observe or modify the received message |
| afterReceiveCompletion | After the receive process completes | Cleanup after receive |

Example interceptor that records the message type and adds an internal header:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object contentType = message.getHeaders()
                .get("contentType");

        return MessageBuilder.fromMessage(message)
                .setHeader("audit.channel", channel.toString())
                .setHeader("audit.hasContentType", contentType != null)
                .build();
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println("sent=" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        if (ex != null) {
            System.err.println("send failed: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Key points to remember:

- **preSend** can return a new Message to replace the message about to be sent.
- Returning **null** means stopping the sending of that message. This is intentional behavior, so do not return null due to an unhandled programming error.
- MessageHeaders are immutable. Use MessageBuilder.fromMessage(...) to create a new message instead of modifying the header map directly.
- **postSend** indicates the result of the send operation on the channel; it does not prove that the consumer completed business processing or that data was committed.
- **afterSendCompletion** is suitable for cleanup and recording errors from the send process. Do not use this callback to execute business side effects again.

### Registering an Interceptor

For channels supporting InterceptableChannel, you can register an interceptor via the addInterceptor API. The example below uses Spring Integration's DirectChannel:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class ChannelConfiguration {

    @Bean
    MessageChannel ordersChannel(AuditChannelInterceptor interceptor) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

If the application uses channels created by the framework or an adapter, configure interceptors via the supported abstraction instead of replacing a container-managed channel.

### Interceptors for Asynchronous Processing

ChannelInterceptor observes channel activity. For channels that dispatch to subscribers via an executor, **ExecutorChannelInterceptor** provides additional callbacks around handler invocation:

- **beforeHandle:** runs immediately before the handler receives the message on the execution thread.
- **afterMessageHandled:** runs after the handler completes or throws an exception.

This is the appropriate place to measure handler processing time or attach context for execution. It should not be used as a substitute for proper trace context propagation across executors; context propagation needs to be configured separately.

Do not block the event loop or message-sending thread with blocking work inside an interceptor. Interceptors sit on the message path, so a slow operation inside one can increase latency for many requests.

## 3. Experimenting with Interceptors: Inspect, Enrich, and Reject

An interceptor typically has three technical responsibilities:

1. Validate required metadata, such as correlation ID or content type.
2. Enrich metadata for observability, such as ingestion timestamp or logical channel name.
3. Reject messages that fail channel-level conditions if that is the channel's technical policy.

Example interceptor requiring a correlation ID:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class CorrelationIdInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object correlationId =
                message.getHeaders().get("correlationId");

        if (correlationId == null ||
                correlationId.toString().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing correlationId");
        }

        return message;
    }
}
~~~

In a real-world application, clearly decide whether a missing correlation ID will be rejected, newly generated, or converted into a structured error. If an interceptor throws an exception, the producer may receive the error immediately during the send operation depending on the channel type and dispatch mechanism. With asynchronous processing, errors occurring on the consumer thread may follow a different error handling path.

Do not put all business validation into an interceptor. For example, checking order quantity, access permissions, or order status should live in the handler/domain service, where sufficient context is available and clear business errors can be returned.

## 4. MessageConverter: Payload Conversion and Content Type

Spring Messaging separates the payload from metadata. **MessageConverter** converts the payload between Java objects and a format suitable for the message/transport.

Common converters:

- **StringMessageConverter:** converts String payloads.
- **ByteArrayMessageConverter:** works with byte[].
- **MappingJackson2MessageConverter:** converts between objects and JSON when the application uses Jackson 2.
- **CompositeMessageConverter:** tries a configured list of converters.

Converter selection is typically based on content type and payload/target type. For example:

| Content type | Wire payload | Desired Java type |
| --- | --- | --- |
| text/plain | UTF-8 string | String |
| application/json | JSON | DTO/record |
| application/octet-stream | Bytes | byte[] |
| application/cbor | CBOR | DTO if a compatible codec is configured |

Content type is not just a decorative label. If a producer sends JSON while declaring text/plain, the converter may choose the wrong decoding strategy. If a consumer expects a DTO but no compatible converter is present, the message may fail before the handler runs.

### Trying a Round-Trip with a JSON Converter

The following example demonstrates converting a DTO into a JSON message and decoding it back. The sample uses MappingJackson2MessageConverter in an application using Jackson 2; with other Spring/Jackson versions, choose the compatible converter managed by your project.

~~~java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

public class PayloadConversionDemo {

    record CreateOrder(String customerId, int quantity) {}

    public static void main(String[] args) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        CreateOrder input = new CreateOrder("C-17", 2);

        MessageHeaders headers = new MessageHeaders(Map.of(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON));

        Message<?> message = converter.toMessage(input, headers);

        CreateOrder output = (CreateOrder) converter.fromMessage(
                message, CreateOrder.class);

        if (!input.equals(output)) {
            throw new AssertionError("JSON round-trip failed");
        }

        System.out.println("contentType=" +
                message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("payloadType=" +
                message.getPayload().getClass().getSimpleName());
        System.out.println("order=" + output);
    }
}
~~~

Illustrative output:

~~~text
contentType=application/json
payloadType=byte[]
order=CreateOrder[customerId=C-17, quantity=2]
~~~

The intermediate payload type depends on the converter and configuration. With MappingJackson2MessageConverter, JSON data is represented as byte[] in the message in this example; the handler receiving the message on the other side will have it decoded to the target type by the converter.

When testing in a project, use the same Jackson version and ObjectMapper configuration as the real application. Date/time settings, naming strategies, polymorphic types, and custom modules can produce different results.

## 5. Payload Conversion in STOMP/WebSocket

With STOMP, frames have a command, native headers, and a body. Spring converts the body into arguments of `@MessageMapping` methods through the configured MessageConverters.

Example handler receiving a DTO:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
class OrderMessageController {

    @MessageMapping("/orders.create")
    public OrderResult create(@Payload CreateOrder command) {
        return new OrderResult("accepted", command.customerId());
    }
}
~~~

When a client sends JSON, the frame needs to declare an appropriate content type, usually application/json. Spring uses the corresponding converter to instantiate CreateOrder before invoking the handler. If conversion fails, the handler may not be executed at all.

Configuring custom converters in WebSocketMessageBrokerConfigurer:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompMessageConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public boolean configureMessageConverters(
            List<MessageConverter> converters) {

        converters.add(new MappingJackson2MessageConverter());

        // false: allow Spring to register additional default converters.
        return false;
    }
}
~~~

If you only want to use the exact converters you declare, return true and ensure the list already includes the necessary converters for String, byte[], and JSON. In a Spring Boot application, check auto-configuration settings before registering extra converters to avoid duplicates or unintended changes to default behavior.

When testing STOMP, verify all of the following:
- The content type header on the frame.
- The actual JSON payload.
- The DTO received by the handler.
- The returned result or ERROR frame when JSON is malformed.

Do not only test calling the controller directly with a DTO, because that bypasses the decoding step that this experiment needs to verify.

## 6. Payload Conversion in RSocket

RSocket separates data and metadata. Spring uses **RSocketStrategies** to configure encoders/decoders and conversion components. The data MIME type lets both sides agree on how to interpret the payload.

Example configuring strategies with Jackson 2 codecs when an application needs to add those codecs:

~~~java
import org.springframework.core.codec.Decoder;
import org.springframework.core.codec.Encoder;
import org.springframework.core.codec.Jackson2JsonDecoder;
import org.springframework.core.codec.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
~~~

If the default strategies already include a suitable JSON codec, do not add duplicates. When configuring custom codecs, verify codec ordering and the corresponding MIME types.

You can use strategies and a JSON MIME type when creating a requester:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
~~~

The server side also needs compatible RSocketStrategies configured. Both ends must agree on the data MIME type, codec, and data types. If the client sends CBOR while the server decodes JSON, an error occurs before the handler processes the payload.

Do not confuse data MIME type with route metadata. The route tells RSocket which handler a message is routed to; the data MIME type tells it how to decode the data section. Metadata can contain the route and other protocol information.

## 7. Runtime Errors: Categorize Before Handling

Common errors in a message pipeline:

| Category | Example | Where typically detected |
| --- | --- | --- |
| Send/dispatch | Channel cannot send, subscriber no longer active | Producer/channel |
| Interceptor | Missing header or policy rejects message | preSend/beforeHandle |
| Conversion | Malformed JSON, unsupported content type, incompatible DTO | MessageConverter/codec |
| Routing | No handler for destination/route | Dispatcher |
| Validation | Missing field, value out of range | Handler/validation layer |
| Business | Database error, invalid state | Service/domain |
| Transport | Socket closed, timeout, peer reset | Transport/client |
| Overload | Executor full, buffer overflow, request exceeds limit | Channel/executor/runtime |

Key exceptions in Spring Messaging include:

- **MessageConversionException:** payload cannot be converted by the converter.
- **MessageDeliveryException:** error while delivering a message to a channel/consumer.
- **MessageHandlingException:** error while handling a message at a handler.
- **MessagingException:** base class carrying messaging error details; in many cases failedMessage can be accessed.

Do not catch every exception and return a success response. Preserve the error classification and translate it into a result appropriate for the protocol.

## 8. Handling Errors Across Spring Messaging Layers

### Errors in @MessageMapping

In a messaging controller, `@MessageExceptionHandler` can be used to map handler exceptions to a structured error response:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
class OrderErrorController {

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendTo("/topic/order-errors")
    public ErrorResponse handleInvalidMessage(
            IllegalArgumentException error) {

        return new ErrorResponse(
                "INVALID_MESSAGE",
                "Invalid message");
    }
}
~~~

This is an illustrative pattern for a messaging controller; the specific destination and error delivery approach need to match the STOMP or RSocket endpoint in use. Do not return stack traces, SQL, internal hostnames, or sensitive data to clients.

### Errors in a Spring Integration Flow

If the application uses Spring Integration, a message flow can send errors to an error channel. ErrorMessage carries a Throwable and can carry the failed message via MessagingException. Handlers can be registered on the error channel to record, classify, or route errors to the appropriate place.

Do not assume every plain Spring MessageChannel automatically has an error channel. Error channels are part of Spring Integration's messaging flow mechanism and must be configured according to that architecture.

### Errors in RSocket/Reactor

For an RSocket controller returning Mono or Flux, errors can be emitted as publisher terminal signals. You can use onErrorMap to map internal exceptions to appropriate protocol/application exceptions, or handle them in an exception handler supported by the controller infrastructure.

Do not use onErrorResume to turn all errors into an empty publisher. Doing so can make the client think the request succeeded with no data. If business logic has a valid empty result, distinguish it clearly from an error.

### Transport Errors

When a transport closes, pending requests may terminate with an error. This is not a payload conversion error. Handle reconnect or retry at the client layer with limits and backoff; do not retry infinitely inside an interceptor or handler. For operations with side effects, idempotency is required to avoid duplicate execution if a response is lost after the server has committed.

## 9. End-to-End Experiment

You can run the lab with the following steps:

1. Create a channel and register AuditChannelInterceptor.
2. Send a message with a valid correlation ID and content type.
3. Verify the interceptor sees the message, the added header appears, and the handler receives the expected payload.
4. Send a message missing the correlation ID; verify the message is rejected according to policy.
5. Send valid JSON with content type application/json; verify the DTO is constructed properly.
6. Send malformed JSON or an unsupported content type; verify the conversion error occurs and the handler does not run.
7. Send a message with a non-existent route; verify routing errors are distinct from conversion errors.
8. Have the handler throw a business exception; verify error mapping returns a safe error.
9. Close the transport while a request is pending; verify connection errors are observed separately.
10. Resend a valid request after the error; verify the system continues operating.

For each step, record:
- Input headers and content type.
- Payload type before and after conversion.
- Which interceptor callbacks executed.
- Whether the handler was invoked.
- Exception class and layer where it originated.
- Observed response/error signal.
- Whether the connection remains active after the error.

## 10. Automated Testing

### Unit Testing an Interceptor

You can invoke preSend directly to verify headers are added and the message payload is unchanged:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class AuditChannelInterceptorTest {

    @Test
    void addsAuditHeadersWithoutChangingPayload() {
        AuditChannelInterceptor interceptor =
                new AuditChannelInterceptor();

        Message<String> input = MessageBuilder
                .withPayload("order-created")
                .setHeader("contentType", "application/json")
                .build();

        Message<?> output = interceptor.preSend(input, message -> true);

        assertNotNull(output);
        assertEquals("order-created", output.getPayload());
        assertEquals(
                true,
                output.getHeaders().get("audit.hasContentType"));
    }
}
~~~

This unit test verifies the interceptor's logic. It does not prove the interceptor is registered on the actual channel or invoked during transport.

### Unit Testing Conversion

Use the actual converter to verify DTO/JSON round-trips. Add tests for:
- Incompatible content types.
- Malformed JSON.
- Missing or wrongly typed fields.
- DTOs with generics/nested objects.
- Date/time and custom serializers if used by the application.
- byte[] payloads larger than configured limits.

Assert both the exception type and that the handler/service is not invoked when conversion fails.

### Integration Testing STOMP/RSocket

Start a real endpoint on a random port and use the protocol's test client. Send frames/messages over the network to verify serialization, header mapping, routing, and error paths. Calling controller methods directly cannot replace this integration test.

With RSocket, use StepVerifier to assert terminal signals and finite timeouts. With STOMP, verify native headers, content type, response destination, and session close behavior when a protocol error occurs.

Do not use Thread.sleep to wait for messages. Use latches, Awaitility, or StepVerifier with timeouts for reliable CI tests.

## 11. Diagnosing Errors in Production

When a message fails, collect enough information to identify the boundary:

- Validated/normalized message ID or correlation ID.
- Destination/route or channel name.
- Content type and payload type, without necessarily logging the entire payload.
- Interceptor name and callbacks that ran.
- Exception class, cause chain, and failed message metadata if safe.
- Trace ID/span ID if tracing is configured.
- Send timestamp, handler start timestamp, and completion timestamp.
- Active task count, queue depth, and connection state.

Avoid logging raw payloads, access tokens, session cookies, personal data, or unfiltered headers. Use an allowlist for headers permitted in logs.

Metrics should have low cardinality: channel, operation, converter type, error category. Do not use message ID, customer ID, or trace ID as metric tags.

A useful dashboard can monitor:
- Send failure rate.
- Conversion error rate.
- Handler error rate.
- Message processing latency.
- Executor queue depth and rejected task count.
- Connection close/reset count.
- Retry/redelivery message count.

## 12. Common Experimental Pitfalls

- **Confusing postSend with completed business processing:** postSend only reflects the channel send result.
- **Mutating MessageHeaders directly:** headers are immutable; create a new message using MessageBuilder.
- **Using an interceptor to hold all business validation:** makes logic hard to test and blurs technical errors with business errors.
- **Forgetting content type:** the converter may not pick the right decoding strategy.
- **Testing converters only with in-memory objects:** skips wire byte serialization and headers.
- **Registering custom converters while dropping default ones:** String or byte[] may stop working.
- **Adding duplicate codecs to RSocketStrategies:** can cause unintended selection or unpredictable decoding order.
- **Swallowing exceptions with an empty publisher:** clients cannot distinguish an empty result from an error.
- **Retrying inside an interceptor:** easily creates loops, duplicate side effects, and increased load.
- **Logging full payloads:** risks data exposure and bloats logs.
- **Using mocks to conclude transport is correct:** only network integration tests verify framing, serialization, and connection lifecycle.

## 13. Completion Checklist

- [ ] Clearly identified interceptor ordering and channel callback scopes.
- [ ] Distinguished ChannelInterceptor and ExecutorChannelInterceptor.
- [ ] Verified preSend can replace a message or reject a message.
- [ ] MessageHeaders are recreated rather than mutated directly.
- [ ] Converter is selected based on content type and target type.
- [ ] Tested valid JSON, malformed JSON, and unsupported content types.
- [ ] STOMP native headers and body verified on real frames.
- [ ] RSocket data MIME type and codecs compatible on both ends.
- [ ] Conversion, routing, handler, and transport errors categorized separately.
- [ ] Exceptions mapped to safe responses without exposing internals.
- [ ] Both unit tests and integration tests use finite timeouts.
- [ ] Logs/metrics are sufficient for diagnosis without sensitive payloads or high-cardinality tags.

## References

- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework API — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework API — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
