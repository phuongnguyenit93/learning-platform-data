# Mapping Interaction Models from Input and Output Types

In Spring Messaging RSocket, Spring determines the interaction model of a handler method based on the **cardinality** (number of messages) of the input payload and the return value. The Java types declared in the method signature determine cardinality: single value, multiple values, or no value. The route name and the actual number of elements emitted at runtime do not change this rule.

The four RSocket models are Request-Response, Request-Stream, Fire-and-Forget, and Channel. An RSocket connection is bidirectional: once the connection is established, both sides can initiate requests and handle requests from the other side.

## 1. Understanding Input and Output Cardinality

Spring inspects the method's payload, typically the parameter annotated with **@Payload**. This annotation can be omitted when Spring can recognize a non-simple-type parameter as the payload.

| Cardinality | Input | Output |
|---|---|---|
| **0** | Method has no payload parameter | **void** or **Mono<Void>** |
| **1** | A concrete object or **Mono<T>** | A concrete object or **Mono<T>** |
| **Many** | **Flux<T>** | **Flux<T>** |

Several distinctions to note:

- **Mono<T>** represents at most one value under Reactor's single-value contract; Spring classifies it as cardinality **1**.
- **Flux<T>** represents a stream that can emit multiple values; Spring classifies it as cardinality **Many**, even when the stream is empty or emits only one element in a particular run.
- **List<T>** is **a single payload object**. **Mono<List<T>>** still has cardinality **1**; it sends a single payload containing a list.
- **Flux<T>** represents multiple separate payloads over a stream. If you want to stream items individually over the network, use **Flux<T>** instead of wrapping everything in a **List<T>**.
- On input, having no payload parameter is cardinality **0**. Infrastructure parameters such as **RSocketRequester**, **@DestinationVariable**, **@Header**, or **@Headers** do not increase payload cardinality.

Cardinality is determined from the declared types, not from the final element count. For example, a method taking **Flux<Event>** still has Many input even if the publisher emits only one event; a method returning **Flux<Result>** still has Many output even if that particular run produces only one result.

## 2. Input/Output Mapping Table

For responder methods using **@MessageMapping**, Spring supports the following combinations:

| Input cardinality | Output cardinality | Interaction model | Meaning |
|---|---|---|---|
| 0 or 1 | 0 | Fire-and-Forget or Request-Response | Receives at most one payload and emits no response value |
| 0 or 1 | 1 | Request-Response | Receives at most one payload, returns one value as a single-value type |
| 0 or 1 | Many | Request-Stream | Receives at most one payload, emits a stream of responses |
| Many | 0, 1, or Many | Channel (Request-Channel) | Receives a stream of payloads; the responder may emit no response, one value, or a stream |

### Request-Response

Used when one request needs one corresponding result. Input can be one payload or no payload; output is a concrete value or **Mono<T>**.

Suitable examples: looking up order status, fetching a user profile, or computing one result from one request.

### Request-Stream

Used when a single initial request produces multiple results over time. Input is one payload or no payload; output is **Flux<T>**.

Suitable examples: tracking stock prices, receiving sensor readings, or receiving events emitted after a subscription query.

### Fire-and-Forget

Used when the sender only needs to send a message and does not need an application-level response payload. Input can be one payload or no payload; output has no value (**void** or **Mono<Void>**).

Suitable examples: sending telemetry, recording an auxiliary event, or issuing a command that does not require business confirmation. If the sender needs to know the operation succeeded, design a response with data, such as **Mono<Receipt>**, and use Request-Response.

### Channel (Request-Channel)

Used when both sides exchange streams of messages within the same interaction. The responder's input is **Flux<T>**; output can be **void**/**Mono<Void>**, a single value, or **Flux<R>**.

Suitable examples: bidirectional chat, interactive data streaming, continuous device control, or exchanging real-time events. Channel supports back pressure: demand for receiving data propagates back to the sender to regulate the rate.

**Note on the first row of the table:** Spring lists both Fire-and-Forget and Request-Response for 0/1 input and 0 output. When the caller needs no response, use Fire-and-Forget. If the business contract requires confirmation, return an explicit confirmation data type rather than relying on a payload-less completion.

## 3. Responder Method Examples

The following code illustrates typical method signatures. This is a controller class intended for an application that already has Spring Messaging, Reactor, and RSocket configuration; by itself, the snippet is not a standalone application runnable with **java** without those dependencies and configuration.

~~~java
import java.time.Instant;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DeviceRSocketController {

    @MessageMapping("device.status")
    public Mono<DeviceStatus> status(DeviceQuery query) {
        return Mono.just(new DeviceStatus(query.deviceId(), "ONLINE"));
    }

    @MessageMapping("device.history")
    public Flux<Reading> history(DeviceQuery query) {
        return Flux.just(
            new Reading(query.deviceId(), 21.5, Instant.parse("2026-01-01T10:00:00Z")),
            new Reading(query.deviceId(), 22.0, Instant.parse("2026-01-01T10:00:01Z"))
        );
    }

    @MessageMapping("audit.append")
    public Mono<Void> append(AuditEvent event) {
        return Mono.fromRunnable(() ->
            System.out.println("Saved event " + event.id())
        );
    }

    @MessageMapping("chat.exchange")
    public Flux<ChatMessage> exchange(@Payload Flux<ChatMessage> incoming) {
        return incoming.map(message ->
            new ChatMessage("server", "Received: " + message.body())
        );
    }

    @MessageMapping("server.time")
    public Mono<Instant> time() {
        return Mono.just(Instant.now());
    }

    public record DeviceQuery(String deviceId) {}
    public record DeviceStatus(String deviceId, String state) {}
    public record Reading(String deviceId, double value, Instant at) {}
    public record AuditEvent(String id) {}
    public record ChatMessage(String sender, String body) {}
}
~~~

Mapping of each method:

| Method | Input | Output | Model |
|---|---|---|---|
| **status** | **DeviceQuery** (1) | **Mono<DeviceStatus>** (1) | Request-Response |
| **history** | **DeviceQuery** (1) | **Flux<Reading>** (Many) | Request-Stream |
| **append** | **AuditEvent** (1) | **Mono<Void>** (0) | Fire-and-Forget or Request-Response depending on caller interaction |
| **exchange** | **Flux<ChatMessage>** (Many) | **Flux<ChatMessage>** (Many) | Channel |
| **time** | No payload (0) | **Mono<Instant>** (1) | Request-Response |

In the **exchange** method, **@Payload** clarifies that **Flux<ChatMessage>** is the input payload stream. If you omit this parameter and only accept **RSocketRequester**, **@Header**, or route variables, the method has no input payload.

## 4. Choosing the Model from the Caller Side with RSocketRequester

**RSocketRequester** provides a fluent API to send data and declare the response type. The interaction model is inferred from the cardinality of the sent data and the retrieval method.

~~~java
// Request-Response: one payload, one result.
Mono<DeviceStatus> status = requester.route("device.status")
    .data(new DeviceQuery("sensor-01"))
    .retrieveMono(DeviceStatus.class);

// Request-Stream: one payload, a stream of results.
Flux<Reading> readings = requester.route("device.history")
    .data(new DeviceQuery("sensor-01"))
    .retrieveFlux(Reading.class);

// Fire-and-Forget: send payload, receive no response payload.
Mono<Void> sent = requester.route("audit.append")
    .data(new AuditEvent("event-001"))
    .send();

// Request-Response without an input payload.
Mono<Instant> serverTime = requester.route("server.time")
    .retrieveMono(Instant.class);

// Channel: send a stream of payloads and receive a stream of responses.
Flux<ChatMessage> replies = requester.route("chat.exchange")
    .data(outboundMessages, ChatMessage.class)
    .retrieveFlux(ChatMessage.class);
~~~

In the Channel example, **outboundMessages** is a **Flux<ChatMessage>**. The **data(Publisher, Class)** overload declares the element type when sending a multi-value publisher; this is useful for selecting the encoder and avoids inferring the type per element. There is an overload accepting **ParameterizedTypeReference** when the element type is generic.

Rules when calling:

- Omit **.data(...)** when the request has no payload.
- Use **.retrieveMono(Type.class)** when the contract returns a single result.
- Use **.retrieveFlux(Type.class)** when the contract returns a stream of results.
- Use **.send()** for Fire-and-Forget. The **Mono<Void>** from **send()** only indicates that the message was sent successfully; it **does not confirm** that the responder has finished business processing.
- For Channel, send an input publisher and receive a response publisher. The RSocketRequester documentation notes that Many-to-one is invalid in the requester API; therefore, keep Channel call contracts returning a response stream (**retrieveFlux**) even if the application currently emits only one element.

## 5. Payload, Metadata, and Serialization

Cardinality only determines the shape of message exchange. It does not determine how data is encoded.

- **Payload** is the business data sent in a request or response.
- **Metadata** carries routing, authentication, or auxiliary data. In Spring, registered metadata can be received via **@Header** or **@Headers**; variables in the route can be received via **@DestinationVariable**.
- **RSocketStrategies** configures encoders and decoders for payload/metadata. Codecs in **spring-web** support formats such as JSON, CBOR, and Protobuf depending on registered dependencies.
- RSocket routes are transmitted via metadata. The route only selects the handler; it does not itself determine Request-Response or Request-Stream.

Example configuring CBOR codecs:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .build();
~~~

Spring Boot can auto-configure RSocket infrastructure and **RSocketStrategies** when using the appropriate starter. Codecs can be customized with beans or by configuring shared strategies for requester and responder.

**@ConnectMapping** handles connection-level events, such as the initial **SETUP** frame and **METADATA_PUSH** notifications. This method may only return **void** or **Mono<Void>**; it does not belong to the **@MessageMapping** request mapping table.

## 6. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| **Mono<List<T>>** is a stream because it contains a list | It is a single payload; its cardinality is 1 |
| **Flux<T>** with only one element is Request-Response | The type is still Many; cardinality is not based on runtime element count |
| A **Flux<T>** parameter is just shorthand for multiple single parameters | It represents an input payload stream and makes the interaction a Channel |
| **Mono<Void>** returns an empty object | It is a valueless output, cardinality 0 |
| Fire-and-Forget confirms the business operation completed | It is a one-way interaction; return a response payload if acknowledgment is needed |
| **@Header** or **@DestinationVariable** is payload | They are metadata/route data and do not change payload cardinality |
| The route name determines the interaction model | The model is determined by input/output cardinality and how the caller initiates the request |

A common design mistake is using Fire-and-Forget for an operation where the caller needs to know the outcome. When confirmation is needed, return a business-meaningful type such as **Mono<AuditReceipt>** and invoke with Request-Response. Conversely, do not collect an entire stream into **Mono<List<T>>** just for convenience if the true requirement is streaming results incrementally; doing so changes the contract from multiple payloads to a single payload.

## 7. Process for Choosing Method Signatures

1. Determine whether the sender has a payload.
2. If there is one payload, use an object type or **Mono<T>**; if sending multiple payloads sequentially, use **Flux<T>**.
3. Determine whether the caller needs no response, one result, or a stream of results.
4. Choose **void**/**Mono<Void>**, a single type/**Mono<T>**, or **Flux<T>** accordingly.
5. Check the combination against the mapping table and pick the matching requester API: **send**, **retrieveMono**, or **retrieveFlux**.
6. Test both sides of the connection: payload type, response type, empty publisher cases, errors, and back pressure.

If a method accepts **Flux** or returns **Flux**, test the stream with multiple elements and verify subscription cancellation/back pressure. With Fire-and-Forget, test handler errors on the responder separately because completion of **send()** is not a business acknowledgment.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, cardinality, **@MessageMapping**, **RSocketRequester**, metadata, and codecs.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration, starter, and **RSocketStrategies**.
