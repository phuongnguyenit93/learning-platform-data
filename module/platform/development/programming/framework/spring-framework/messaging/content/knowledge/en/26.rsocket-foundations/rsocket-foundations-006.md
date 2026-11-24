# Request-Channel and Bidirectional Data Streams

> Scope: Spring Framework RSocket, Java 17+, and Project Reactor. This lesson explains how a request-channel sends a data stream from requester to responder while simultaneously receiving a data stream back; how Spring maps that model using Flux, @MessageMapping, and RSocketRequester; and the principles of backpressure, completion, cancellation, and error handling.

## 1. What Is Request-Channel?

RSocket provides four main interaction models:

| Interaction | Data sent | Data received | Best suited for |
|---|---|---|---|
| Request-Response | One message | One message | Calling an operation and receiving a single result. |
| Request-Stream | One message | One stream | Sending criteria once and receiving multiple results. |
| Request-Channel | One stream | One stream | Both sides exchanging multiple messages concurrently within a single request. |
| Fire-and-Forget | One message | No response payload | Sending a one-way event without needing a result. |

Request-channel is the interaction model that lets the requester send multiple messages while the responder also sends multiple messages back. Both streams can operate concurrently without waiting for the entire request stream to finish before starting to receive responses.

Practical examples:

- A client continuously sends device control commands and receives device status after each command.
- An application sends audio segments or sensor signals while receiving analytical feedback.
- A client sends document edit operations and receives updates or confirmations from the server.
- An interactive data-processing session where the client sends inputs while receiving incremental results.

Request-channel is neither a broadcast topic nor a message-storing queue. It is a single request with a lifecycle, an input stream, and an output stream. When the request completes or is cancelled, the streams belonging to that request also terminate per RSocket semantics.

## 2. Mechanism at the RSocket Layer

Once the RSocket connection is established, the requester starts a channel with a REQUEST_CHANNEL frame. The initial frame carries the first payload (if any) and the initial demand for the response stream. Subsequent request payloads are sent via PAYLOAD frames. The responder likewise sends PAYLOAD frames to emit responses back to the requester.

General flow:

~~~text
Requester                                      Responder
    |                                              |
    |------ REQUEST_CHANNEL (first payload) ------>|
    |                                              |
    |------ PAYLOAD (next request) --------------->|
    |<----- PAYLOAD (first response) --------------|
    |------ PAYLOAD (next request) --------------->|
    |<----- PAYLOAD (next response) ---------------|
    |<----- PAYLOAD (next response) ---------------|
    |------ PAYLOAD (next request) --------------->|
    |                                              |
    |------ COMPLETE / end request stream -------->|
    |<----- COMPLETE / end response stream --------|
    |                                              |
~~~

Request and response frames can interleave. The requester does not have to finish sending all data before receiving replies. The responder can process incoming chunks and emit results as they become available.

RSocket also defines control frames such as REQUEST_N, CANCEL, ERROR, and COMPLETE:

- REQUEST_N signals the additional number of payloads the receiver is ready to accept.
- CANCEL cancels an active request.
- ERROR terminates the request with an error.
- COMPLETE signals that one side has finished emitting its payloads.

RSocket is a bidirectional and symmetric protocol. After the connection is established, both sides can initiate requests. Within a specific request-channel, requester and responder still have clear roles with respect to that request's two streams.

## 3. Spring Identifies Request-Channel via Flux

Spring uses input and output cardinality to infer the interaction model of a `@MessageMapping` method:

| Handler input | Return value | Interaction model |
|---|---|---|
| One payload or no payload | A single value / Mono | Request-Response or Fire-and-Forget depending on signature. |
| One payload or no payload | Flux | Request-Stream. |
| Flux payload | void or Mono<Void> | Request-Channel with no response payload. |
| Flux payload | A single value or Mono | Request-Channel with a single response. |
| Flux payload | Flux | Request-Channel with a response stream. |

The case where both streams have multiple elements is usually the clearest illustration of bidirectional data: the handler accepts Flux<Request> and returns Flux<Response>.

Spring supports Reactive Streams types such as Mono and Flux. With request-channel, the handler's input is a multi-value publisher; the output can also be a multi-value publisher. Spring translates reactive signals into the corresponding RSocket payload streams.

## 4. Writing a Responder with @MessageMapping

The example below receives multiple commands from the client and emits a response event for each command. The RSocket route is chat.channel:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class ChatChannelController {

    public record ClientCommand(String text) {}

    public record ServerEvent(long sequence, String message) {}

    @MessageMapping("chat.channel")
    public Flux<ServerEvent> channel(Flux<ClientCommand> commands) {
        return commands
                .index()
                .map(indexed -> new ServerEvent(
                        indexed.getT1(),
                        "Processed: " + indexed.getT2().text()
                ));
    }
}
~~~

Explanation:

1. @MessageMapping("chat.channel") declares the request route.
2. The Flux<ClientCommand> parameter represents multiple input payloads.
3. index() attaches a 0-based sequence number to each command.
4. map() transforms each command into a ServerEvent.
5. Flux<ServerEvent> is the response stream sent back to the requester.

Because both input and output are Flux, Spring identifies this as Request-Channel. Each command can produce a corresponding response. When the input publisher completes and the transformation finishes processing remaining elements, the response Flux also completes.

In a real example, processing may call an asynchronous service. Use concatMap when processing order and response order must be preserved:

~~~java
@MessageMapping("orders.channel")
public Flux<OrderReply> processOrders(Flux<OrderCommand> commands) {
    return commands.concatMap(orderService::process);
}
~~~

The second snippet assumes orderService.process(OrderCommand) returns Mono<OrderReply>. concatMap processes commands sequentially and preserves response order. If business rules allow parallel processing, flatMap with an appropriate concurrency limit can be used; in that case, response order may differ from request order.

## 5. Sending Request-Channel from the Client with RSocketRequester

RSocketRequester is Spring's fluent API for creating requests and encoding/decoding data and metadata. For a multi-element publisher, pass the publisher to data() and receive responses with retrieveFlux():

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

Flux<ClientCommand> outgoing = Flux.just(
        new ClientCommand("open"),
        new ClientCommand("update"),
        new ClientCommand("close")
);

Flux<ServerEvent> incoming = requester
        .route("chat.channel")
        .data(outgoing, ClientCommand.class)
        .retrieveFlux(ServerEvent.class);

incoming.subscribe(
        event -> System.out.println(event.sequence() + ": " + event.message()),
        error -> System.err.println("Channel failed: " + error.getMessage()),
        () -> System.out.println("Channel completed")
);
~~~

Three steps to understand:

- route() selects the route metadata so the responder finds the right handler.
- data() provides the input publisher. Here outgoing is a Flux, so the requester sends multiple payloads.
- retrieveFlux() declares that the response is a stream of ServerEvent.

Combining multiple request payloads with a response stream creates a request-channel. The requester does not need to call a separate API named requestChannel; Spring infers the interaction model from the cardinality of the data publisher and the requested response type.

The example using Flux.just has a finite data source. The client sends three commands and completes its input. The server processes them and emits ServerEvents. This is easy to test, whereas in long-lived interactive applications, the input is usually a live publisher that emits additional data while responses are being consumed.

## 6. Continuous Exchange with a Live Publisher

To send data in real time, the client can use Reactor Sinks as the command source. Example using a unicast sink with a bounded queue:

~~~java
import java.util.concurrent.ArrayBlockingQueue;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.Disposable;
import reactor.core.publisher.Sinks;

Sinks.Many<ClientCommand> outgoing = Sinks.many()
        .unicast()
        .onBackpressureBuffer(new ArrayBlockingQueue<>(128));

Disposable channelSubscription = requester
        .route("chat.channel")
        .data(outgoing.asFlux(), ClientCommand.class)
        .retrieveFlux(ServerEvent.class)
        .subscribe(
                event -> System.out.println("Server: " + event.message()),
                error -> System.err.println("Channel failed: " + error.getMessage()),
                () -> System.out.println("Channel completed")
        );

// Send multiple commands while the response stream is subscribed.
Sinks.EmitResult first = outgoing.tryEmitNext(new ClientCommand("start"));
Sinks.EmitResult second = outgoing.tryEmitNext(new ClientCommand("move"));
Sinks.EmitResult third = outgoing.tryEmitNext(new ClientCommand("stop"));

// Check EmitResult in real applications to handle cases where the queue is full
// or the sink has terminated.
if (first.isFailure() || second.isFailure() || third.isFailure()) {
    System.err.println("Could not enqueue every command");
}

// When no more request payloads will be sent:
outgoing.tryEmitComplete();
~~~

This example illustrates the bidirectional publisher part. The ClientCommand and ServerEvent types are shared with the controller example above. In a real service, the requester is typically created and managed via Spring configuration or dependency injection; connection and Disposable lifecycles must be managed according to the session lifecycle.

Key points to note:

- Subscribe to the response Flux before emitting commands if immediate replies are needed.
- A unicast sink allows only one subscriber; this fits a single request-channel consuming that publisher.
- A bounded queue avoids holding unbounded data when the producer is faster than the consumer.
- Always check EmitResult. When the queue is full, the sink is cancelled, or it has completed, further emissions can fail.
- To finish normally, call tryEmitComplete() to close the input request stream and wait for the response stream to complete.
- When disposing the Disposable, the requester cancels the response subscription; cancellation propagates as CANCEL for the active request.

Do not use an unbounded queue for hot data sources that can emit faster than the remote peer can process. A bounded queue forces the application to decide explicitly how to handle overflow: reject new data, retry under control, slow the producer down, or persist data to an appropriate storage system.

## 7. Backpressure Between Both Sides

Backpressure is a key aspect of request-channel. RSocket carries Reactive Streams semantics across network boundaries. The receiver signals demand by the number of messages it is ready to accept. When it needs more data, it sends REQUEST_N. The sending publisher must respect this demand.

With Spring and Reactor:

- Flux/Mono represent data sources and reactive signals.
- Subscribers create demand when requesting elements.
- Reactor and RSocket propagate demand over the protocol, without applications manually constructing REQUEST_N frames.
- When the consumer is slow, the data source can be asked to emit more slowly if the source supports backpressure.
- A hot or non-throttlable source may still need buffering or an application-level overflow policy.

Request-channel has two data directions. Each direction has its own lifecycle and demand. The requester consumes the response stream via its subscriber; the responder consumes the request stream via its handler. Whichever side processes slowly will have demand in that direction pace the other side's emission rate.

Backpressure is not per-user rate limiting, not durable message persistence, and does not replace payload size limits. Systems still need business rate limits, message size limits, concurrent channel limits, and buffer memory budgets.

### Source Throttling Example

For finite or throttled sources, Reactor operators let you control pace and element counts:

~~~java
Flux<ClientCommand> outgoing = commandSource
        .onBackpressureBuffer(128)
        .limitRate(32);
~~~

limitRate regulates the number of elements requested from upstream in demand batches. onBackpressureBuffer here has a limit of 128 elements; applications must define behavior when the buffer fills and should not treat buffering as a substitute for throttling producers.

## 8. Completion, Cancellation, and Errors

A request-channel has two payload streams. Distinguish one side stopping data emission from the entire request ending:

- When the input publisher completes, the requester stops sending further request payloads. The responder can still finish or emit remaining generated responses.
- When the responder's response publisher completes, the requester receives the complete signal and the response Flux terminates.
- When the requester cancels the response subscription, RSocket sends CANCEL for the active request; the responder should release related resources.
- When either side emits an error, the request terminates with a protocol error; the other side receives the error and must clean up resources.
- When the RSocket connection closes, active requests on that connection may error or cancel depending on the scenario and resumption configuration.

You can attach doFinally to observe lifecycle termination and release resources:

~~~java
@MessageMapping("telemetry.channel")
public Flux<TelemetryReply> telemetry(Flux<TelemetrySample> samples) {
    return samples
            .map(this::process)
            .doFinally(signal -> releaseChannelResources());
}
~~~

In this example, process and releaseChannelResources represent application logic. doFinally runs when the stream completes, errors, or is cancelled. Resource release must be idempotent and safe across multiple termination paths.

Do not swallow errors by turning every error into a fake success response. Distinguish business errors representable as payloads from protocol or system errors that must terminate the request.

## 9. Distinguishing Request-Channel from Other Interaction Models

| Need | Choice | Reason |
|---|---|---|
| Send one command and receive one result | Request-Response | One-to-one cardinality. |
| Send one criterion and receive multiple results | Request-Stream | Single input, multiple outputs. |
| Send multiple commands and receive multiple replies while sending | Request-Channel | Multiple payloads in both directions. |
| Send one event without needing a response | Fire-and-Forget | One-way, no response payload. |
| Send independent notifications not tied to a specific request | Metadata Push | Uses connection-level METADATA_PUSH frames. |

Request-channel differs from Request-Stream in that the requester can also send multiple payloads after the initiating frame. It differs from Metadata Push because a channel belongs to a specific request with its own lifecycle, whereas metadata push is a connection-level metadata notification.

If the client only sends one object and the server returns Flux, use Request-Stream. Do not use request-channel merely because the response has multiple elements. If the client needs to keep sending additional data while receiving responses, request-channel is the appropriate choice.

## 10. Configuring the Responder and Serialization

In a plain Spring Framework application, RSocketMessageHandler discovers `@Controller` beans with `@MessageMapping` and creates the responder. The application must wire that responder into RSocketServer. In Spring Boot, auto-configuration can create RSocketMessageHandler and configure the requester builder.

Minimal handler configuration in Spring Framework:

~~~java
@Configuration
public class RSocketServerConfig {

    @Bean
    public RSocketMessageHandler rsocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

This snippet only creates the message handler; the server transport still must be bound to the responder provided by handler.responder(). PathPatternRouteMatcher uses a dot as the default route separator for RSocket routes; RSocket routes are metadata, not HTTP URLs. For example, chat.channel is a hierarchical route.

RSocketRequester and RSocketMessageHandler use RSocketStrategies to encode and decode data and metadata. Basic codecs in spring-core support String, byte[], and ByteBuffer. To pass DTOs/records as JSON or CBOR, corresponding encoders/decoders are needed; Jackson codecs typically come from spring-web and can be configured in RSocketStrategies. The Spring Boot RSocket starter provides automatic codec configuration based on dependencies present.

Both sides must agree on MIME types and payload structure. If the server expects ClientCommand yet the client sends JSON with a different schema, decoding errors can occur before the handler runs. When evolving schemas, consider backward compatibility and message versioning.

## 11. Common Pitfalls and Troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| Handler is not invoked | Client route does not match @MessageMapping | Compare route metadata exactly, including dots and route name. |
| Spring does not recognize this as a channel | Handler input is not Flux or a multi-element publisher | Use Flux<T> as input payload when multiple request payloads are needed. |
| Response received only once | Client used retrieveMono or handler returned only one value | Use retrieveFlux and return Flux if a response stream is needed. |
| Request sends yet no response arrives | Handler returns empty Flux, filter drops all elements, or error happens before emit | Inspect input publisher, reactive operators, and sanitized error logs. |
| Fast producer increases memory | Hot source emits faster than consumer with unbounded buffer | Use backpressure-aware sources, bounded queues, and overflow policies. |
| Channel never finishes | Input publisher never completes or response publisher never completes | Check lifecycles of both Flux streams and completion conditions. |
| Resources not released when client leaves | Cancellation not handled | Use doFinally and cleanup safe for COMPLETE, ERROR, CANCEL. |
| DTO cannot be decoded | Incompatible codec, MIME type, or schema | Check RSocketStrategies, encoders/decoders, and MIME types. |
| Server replies out of order | Used flatMap with tasks finishing out of order | Use concatMap if business logic requires preserving order. |

## 12. Request-Channel Design Checklist

1. Do both sides genuinely need to send multiple payloads within the same request?
2. Does the handler use Flux for the input stream and a return type matching the response stream?
3. Does the client use data(Publisher, elementClass) and retrieveFlux with the right types?
4. Does the data source support backpressure or need a bounded buffer?
5. Are there limits on element counts, rates, payload sizes, and concurrent channels?
6. When input completes, can the response complete per business rules?
7. When the client cancels or the connection errors, are resources released?
8. Do both sides share the same codecs, MIME types, and schemas?
9. Is the route stable and properly authorized?
10. Have fast-producer, slow-consumer, mid-stream error, and mid-stream cancellation cases been tested?

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, @MessageMapping, Flux/Mono cardinality, and annotated responders.
- [RSocket Protocol — REQUEST_CHANNEL](https://rsocket.io/about/protocol/): REQUEST_CHANNEL, PAYLOAD, REQUEST_N, COMPLETE, CANCEL, and flow control.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration for RSocketMessageHandler, RSocketStrategies, and RSocketRequester.Builder.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Flux, Sinks, backpressure, cancellation, and error handling.
