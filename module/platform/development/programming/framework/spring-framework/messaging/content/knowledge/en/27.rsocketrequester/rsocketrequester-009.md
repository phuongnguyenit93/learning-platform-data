# Passing an Input Publisher for Request-Channel Interactions

## Objectives

In RSocket, request-channel is a bidirectional interaction model: the initiator sends a stream of messages and the receiver can return another stream of messages over the same request. With Spring, you can represent the input stream as a Reactive Streams Publisher, typically a Reactor Flux, and then declare the response type with retrieveFlux.

This fits continuous or batched data streams such as telemetry, status updates, business events, sensor data, and processing multiple commands within one interaction session. The client can continue sending new elements while still receiving responses from the server.

## 1. Distinguishing Request-Channel from Other Interaction Models

Spring determines the interaction model based on the cardinality of elements that input and output can emit:

| Input | Output | Interaction model |
| --- | --- | --- |
| A single value or Mono | A single value or Mono | Request-Response |
| A single value or Mono | Flux | Request-Stream |
| Multi-value Publisher, e.g. Flux | Flux | Request-Channel |
| A single value | No response | Fire-and-Forget |

The deciding factor for request-channel is that the input is multi-element. When using RSocketRequester, the common combination is:

~~~java
Flux<Response> responses = requester.route("some.route")
    .data(requestPublisher, Request.class)
    .retrieveFlux(Response.class);
~~~

retrieveFlux performs request-stream or request-channel depending on whether the input is one payload or multiple payloads. With a multi-element Publisher such as Flux, Spring uses request-channel. The input Publisher and output Flux form two data streams tied to the same request.

Do not use retrieveMono for a multi-element Publisher. RSocket has no many-to-one interaction; retrieveMono will raise an error when the input payload is a multi-value Publisher. If you need to receive exactly one aggregated result after sending multiple elements, receive via retrieveFlux and convert to Mono using single() or singleOrEmpty() according to the expected result count rules.

## 2. Passing a Publisher with RSocketRequester

RSocketRequester provides a fluent API chain to declare the route, metadata, input payload, and response type:

- route(String, Object...) specifies the responder's route. The route is sent in the request metadata.
- data(Object) accepts a concrete value, a Reactive Streams Publisher, or a producer that ReactiveAdapterRegistry can adapt into a Publisher.
- data(Object, Class<?>) additionally accepts the element type. For a homogeneous Publisher, Spring can look up a compatible Encoder once at the start of the stream instead of inspecting the type and looking up an Encoder for every element.
- data(Object, ParameterizedTypeReference<?>) is used when the element type has generic type parameters, such as Envelope<OrderEvent>.
- retrieveFlux(Class<?>) or retrieveFlux(ParameterizedTypeReference<?>) declares the response element type and returns a Flux.

Minimal example:

~~~java
Flux<Command> commands = Flux.just(command1, command2, command3);

Flux<Acknowledgement> acknowledgements = requester.route("commands.process")
    .data(commands, Command.class)
    .retrieveFlux(Acknowledgement.class);
~~~

If you omit the type hint, you can use data(commands). For a multi-element stream of the same type, the overload with Class<?> is usually clearer and avoids repeated Encoder lookups. The type hint must match the actual type of each element.

For elements with generic types, pass a ParameterizedTypeReference for the type of each Publisher element:

~~~java
Flux<Envelope<OrderEvent>> events = ...;

ParameterizedTypeReference<Envelope<OrderEvent>> eventType =
    new ParameterizedTypeReference<>() {};

Flux<Acknowledgement> replies = requester.route("orders.ingest")
    .data(events, eventType)
    .retrieveFlux(Acknowledgement.class);
~~~

The type reference here describes Envelope<OrderEvent>, not the outer wrapping Flux type.

## 3. Example: Sending a Price Stream and Receiving Alerts

The example uses Java 17 records as payloads. The client sends multiple PriceTick items; the server filters ticks priced at 100 or above and returns a corresponding PriceAlert for each.

### DTOs

Place each record in its own file:

~~~java
import java.math.BigDecimal;

public record PriceTick(
    String symbol,
    long sequence,
    BigDecimal price
) {}
~~~

~~~java
public record PriceAlert(
    String symbol,
    long sequence,
    String message
) {}
~~~

### Server-Side Responder

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class PriceChannelController {

    @MessageMapping("prices.watch")
    Flux<PriceAlert> watch(@Payload Flux<PriceTick> ticks) {
        return ticks
            .filter(tick -> tick.price().compareTo(new BigDecimal("100.00")) >= 0)
            .map(tick -> new PriceAlert(
                tick.symbol(),
                tick.sequence(),
                "Threshold exceeded: " + tick.price()
            ));
    }
}
~~~

Flux<PriceTick> represents a multi-element input; Flux<PriceAlert> represents a multi-element output. This many-to-many cardinality pair maps to request-channel. Spring receives and decodes each payload and turns them into elements of the input Flux. Results from the returned Flux are encoded and sent back to the requester.

### Client-Side Requester

Assuming the requester has already been configured and connected to the server:

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

class PriceChannelClient {

    private final RSocketRequester requester;

    PriceChannelClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Flux<PriceAlert> watch() {
        Flux<PriceTick> ticks = Flux.just(
            new PriceTick("ACME", 1, new BigDecimal("98.50")),
            new PriceTick("ACME", 2, new BigDecimal("101.25")),
            new PriceTick("ACME", 3, new BigDecimal("103.00"))
        );

        return requester.route("prices.watch")
            .data(ticks, PriceTick.class)
            .retrieveFlux(PriceAlert.class);
    }
}
~~~

You can run the example in a demo application by subscribing to handle the results:

~~~java
client.watch()
    .doOnNext(System.out::println)
    .blockLast();
~~~

The output contains two alerts because the first tick is priced below the threshold:

~~~text
PriceAlert[symbol=ACME, sequence=2, message=Threshold exceeded: 101.25]
PriceAlert[symbol=ACME, sequence=3, message=Threshold exceeded: 103.00]
~~~

These are code snippets within a Spring application already configured with RSocket and codecs; they are not standalone Java programs runnable with only javac. blockLast() is only used for illustration in a command-line application or test. In a real reactive application, return the Flux to the next caller and avoid blocking on an event-loop thread.

## 4. Configuring Connection and Codecs

A basic TCP requester can be created as follows:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

The connection is established when a request is executed. You can use WebSocket instead of TCP via the corresponding builder method if the server is configured on WebSocket.

With Spring Boot, the spring-boot-starter-rsocket dependency provides RSocket infrastructure and supports auto-configuring RSocketStrategies. You can configure a TCP server in application.properties:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Boot auto-configures Jackson JSON/CBOR codecs when the corresponding dependencies are present. If using Spring Framework directly or custom payload types, configure matching Encoders and Decoders in RSocketStrategies on both sides. Codecs must be compatible with the connection's data MIME type; if both sides do not agree on the format, payloads may fail to decode.

## 5. Backpressure and Publisher Lifecycle

RSocket carries Reactive Streams semantics across network boundaries. With request-stream and request-channel, the receiver sends demand signals to regulate how many elements are transmitted. In request-channel, this regulation applies to both the response stream and the input payload stream; the producer does not need to push unbounded data onto the socket proactively.

Several implementation principles:

- Return the Publisher from the responder. Do not call subscribe() inside a @MessageMapping method to detach the stream from the Spring-managed request lifecycle.
- The request only starts when the response Flux is subscribed. Without a subscriber, the reactive chain is not consumed.
- Avoid collectList() for large or unbounded streams because it holds all elements in memory.
- Use concatMap when sequential processing and ordering are required; use flatMap with a concurrency limit when parallel processing is appropriate.
- If the source is a hot Publisher, check emission timing and buffering policies. A source that emits before the request is subscribed may drop elements for late subscribers.
- When the caller cancels the subscription, the request can be cancelled per Reactive Streams mechanics. Application-level operators and tasks should respect cancellation to stop unneeded work.
- Handle errors using operators such as onErrorMap or onErrorResume at the right layer. An unhandled error in the stream typically terminates the interaction.

Backpressure does not replace application-layer resource bounds. You still need to bound concurrency, buffer sizes, processing time, and connection lifetimes based on real load.

## 6. Common Errors

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| retrieveMono throws error when sending Flux | Input has multiple payloads while requesting a single request-response result | Use retrieveFlux; if only one result is needed, use single() or singleOrEmpty() after retrieveFlux |
| Server does not receive request | Route in route(...) does not match @MessageMapping or server is not listening on the right transport/port | Verify exact route and connection configuration |
| Payload encode/decode error | Missing Encoder/Decoder or incompatible data MIME type | Configure consistent RSocketStrategies and codecs on both sides |
| Generic type conversion error | Passing only Class<?> loses nested type information | Use ParameterizedTypeReference for the element type |
| Stream emits no data | Flux has not been subscribed, hot source emitted before subscription, or source produces no elements | Check subscriber and Publisher lifecycle |
| High memory usage over long runs | Unbounded buffers, collectList() on large streams, or unbounded concurrent processing | Bound buffers/concurrency and keep pipeline backpressure-aware |

## 7. Implementation Checklist

1. Confirm the input is genuinely a multi-element stream; use Flux or a multi-value Publisher.
2. Declare the responder to accept Flux<T> and return Flux<R> when bidirectional streaming is needed.
3. Use route(...) matching the @MessageMapping route.
4. Call data(publisher, ElementType.class) or the ParameterizedTypeReference overload for generic elements.
5. Use retrieveFlux(ResponseType.class) to receive the response stream.
6. Configure compatible codecs and data MIME types between requester and responder.
7. Verify backpressure, cancellation, error handling, concurrency, and memory bounds.
8. Test with multiple input elements, interleaved responses, empty sources, mid-stream errors, and client subscription cancellation.

## References

- [Spring Framework Reference — RSocket and RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.RequestSpec — Spring Framework 7.0 API](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [RSocketRequester.RetrieveSpec — Spring Framework 7.0 API](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
