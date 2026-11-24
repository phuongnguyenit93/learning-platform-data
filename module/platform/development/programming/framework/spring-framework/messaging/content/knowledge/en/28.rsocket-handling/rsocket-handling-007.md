# Handling Reverse Requests from Server to Client in Spring RSocket

## Objectives

In many RSocket applications, the client typically opens a connection to the server and sends requests. However, once the connection is established, the server can also proactively send requests over that same connection to fetch data, ask the client to perform an action, or deliver notifications. This is RSocket's bidirectional communication model.

Spring Framework supports this communication direction via `RSocketRequester` on the server side and a registered responder on the client side. The key is properly understanding requester/responder roles after a connection is established, obtaining the right `RSocketRequester` bound to each connection, and configuring client-side handlers to receive routes sent by the server.

## Why Can the Server Send Requests to the Client?

RSocket is a bidirectional, multiplexed, full-duplex communication protocol. The client initiates the connection at the transport layer and sends the `SETUP` frame, but once the connection is accepted, the client/server distinction no longer restricts which side can send requests. Each endpoint can act as requester or responder on a per-request basis.

For example, after a client connects to the server:

1. The client sends an `inventory.lookup` request to the server; the server processes it and returns a result.
2. The server can send a `client.health` request back over the same connection; the client processes it and returns its status.
3. The server can send a one-way notification to the client using Fire-and-Forget.
4. Both sides can open bidirectional data streams using Request-Channel.

There is no need to open another TCP or WebSocket connection just for the server to send data back. The server uses the active RSocket connection and sends requests in the requester role.

## Four Interaction Models and Data Direction

RSocket defines four primary request types. When the server is the requester and the client is the responder, data direction works as follows:

| Interaction model | Server sends | Client returns | Common call on server |
| --- | --- | --- | --- |
| Request-Response | One payload | One result | `retrieveMono(Type.class)` |
| Request-Stream | One payload | A stream of results | `retrieveFlux(Type.class)` |
| Fire-and-Forget | One payload | No response payload | `send()` |
| Request-Channel | A stream of payloads | Can return a stream of results | `data(Flux, elementType)` and `retrieveFlux(...)` |

Request-Stream means the server sends one request and receives a `Flux` from the client. If the goal is for the server to push multiple data items to the client, choose Request-Channel or send multiple one-way requests; do not confuse `retrieveFlux` with the server streaming payloads outward.

## Relevant Spring Components

- `RSocketRequester`: fluent API for sending requests over an RSocket connection. This API can be used symmetrically on both client and server.
- `@ConnectMapping`: handles the initial `SETUP` frame and connection-level metadata pushes. On the server side, the method can accept an `RSocketRequester` representing the newly established connection.
- `@MessageMapping`: handles routed requests. Methods on either server or client can accept `RSocketRequester` to proactively send requests back to the other side.
- `RSocketMessageHandler`: detects and invokes responder methods annotated with `@MessageMapping` or `@ConnectMapping`.
- `RSocketMessageHandler.responder(...)`: creates a `SocketAcceptor` from handlers to register a client-side responder.
- `RSocketStrategies`: configures encoders, decoders, route matcher, and metadata extractor for requester/responder. Both sides must have codecs compatible with the wire data format.

`@ConnectMapping` is not a handler for all messages from the client. It is for connection setup events and metadata pushes. Routed business requests are handled by `@MessageMapping`.

## Step 1: Registering a Responder on the Client Side

The client must declare the route the server will call. The following example creates a responder handling the `client.health` route and returning a status string:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Mono;

public class ClientResponder {

    @MessageMapping("client.health")
    public Mono<String> health(String command) {
        return Mono.just("READY: " + command);
    }
}
```

Register the handler on `RSocketRequester.Builder` via `SocketAcceptor`: 

```java
import io.rsocket.SocketAcceptor;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientResponder());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
```

This is programmatic handler registration. `RSocketMessageHandler.responder(strategies, ...)` accepts objects with annotated methods and creates the responder. Objects passed directly are not required to carry the `@Controller` stereotype. `PathPatternRouteMatcher` requires `spring-web`; if `spring-web` is not used, the default route matcher can be kept.

`RSocketRequester` in this code snippet is the client's requester, used by the client to send requests to the server. At the same time, `clientResponder` enables the server to send requests back to the client on this same connection. Both capabilities are configured on the same RSocket connection.

The connection is typically established on the first request. The client must register the responder before the connection is used so the server can locate the corresponding route.

### Registering Handlers via a Spring Bean

In a Spring application, you can also declare `RSocketMessageHandler` as a bean and pass `handler.responder()` to the connector:

```java
RSocketMessageHandler handler = applicationContext.getBean(RSocketMessageHandler.class);

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(handler.responder()))
        .tcp("localhost", 7000);
```

When the client has multiple handler groups or shares a context with server-side handlers, pay attention to the predicate that `RSocketMessageHandler` uses to detect handlers. You can configure `setHandlerPredicate` or use a dedicated stereotype to avoid accidentally registering server handlers as the client responder.

## Step 2: Obtaining the Client's Requester on the Server Side

In server-side `@ConnectMapping` and `@MessageMapping` methods, Spring supports injecting an `RSocketRequester` representing the client end of the current connection. The server uses this instance to send requests to the corresponding client.

The following example calls the `client.health` route right after a client connects:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ClientConnectionHandler {

    @ConnectMapping
    public Mono<Void> onConnect(RSocketRequester requester) {
        requester.route("client.health")
                .data("initial-check")
                .retrieveMono(String.class)
                .subscribe(
                        status -> System.out.println("Client status: " + status),
                        error -> System.err.println("Client request failed: " + error.getMessage()));

        return Mono.empty();
    }
}
```

`requester.route("client.health")` puts the route in the request's metadata. `.data(...)` sets the payload sent to the client. `.retrieveMono(String.class)` declares that the server expects a `String` response. The `health` method on `ClientResponder` receives the payload and produces the corresponding response.

### Special Note for `@ConnectMapping`

`@ConnectMapping` handles the `SETUP` frame; the server finishes processing this frame before new requests can start on the connection. Therefore, a reverse request initiated upon connection must be decoupled from the setup processing flow. The example uses `subscribe(...)` to launch the request independently, then returns `Mono<Void>` to complete connection handling.

Do not chain the reverse request into the `Mono<Void>` returned by `@ConnectMapping` in a way that awaits the client response before completing setup. Doing so can cause a deadlock: setup has not completed so the request is not allowed to start, while setup is waiting for the response to that request.

Calling `subscribe()` is the point that actively triggers the publisher. Therefore, provide error-handling callbacks, proper logging, and manage the subscription lifecycle. For logic that requires long-lived coordination, move request sending into a connection session management service rather than letting the setup callback manage all business logic.

## Step 3: Sending Requests from the Server Once the Connection Is Active

Once the connection is established, a server-side `@MessageMapping` method can also accept `RSocketRequester`. For example, the server handles an incoming request while calling back to the client to check its status:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ServerOperationsHandler {

    @MessageMapping("server.check-client")
    public Mono<String> checkClient(String command, RSocketRequester requester) {
        return requester.route("client.health")
                .data(command)
                .retrieveMono(String.class);
    }
}
```

Unlike the `@ConnectMapping` example, here the server can directly return the publisher of the reverse request because the connection is already active. Spring subscribes to the returned `Mono` to produce the response for the original request. This example fits cases where calling the client is part of processing an incoming server request.

## Step 4: Choosing How to Send Notifications or Requests with Responses

### Request-Response When Confirmation from the Client Is Needed

```java
Mono<String> result = requester.route("client.health")
        .data("ping")
        .retrieveMono(String.class);
```

The client handles the route with `Mono<String>`. The server only receives the result when the client returns a response. This is the right choice for commands requiring a result or business confirmation.

### Fire-and-Forget When Only Sending a Notification

```java
Mono<Void> sent = requester.route("client.notification")
        .data("A new task is available")
        .send();
```

The client can handle the route with a method returning `void` or `Mono<Void>`. `send()` completes when the message has been sent according to the protocol; it does not prove that the client has finished executing the handler. If confirmation of receipt or processing is required, use Request-Response and return an explicit `Acknowledgement` type.

### Request-Stream When the Server Needs a Stream of Responses from the Client

```java
Flux<String> reports = requester.route("client.reports")
        .data("collect")
        .retrieveFlux(String.class);
```

The client responder returns `Flux<String>`. This is a response stream flowing from client to server following an initial server request. Backpressure is propagated via RSocket so the server regulates consumption rate.

### Request-Channel When Both Sides Need to Exchange Streams

Request-Channel allows the server to send a stream of payloads while simultaneously receiving a stream of responses from the client. On the server side, you can use the `data(producer, elementClass)` overload to declare the element type when sending a `Flux`:

```java
Flux<Acknowledgement> acknowledgements = requester.route("client.process-events")
        .data(events, Event.class)
        .retrieveFlux(Acknowledgement.class);
```

On the client side, the corresponding handler can receive `Flux<Event>` and return `Flux<Acknowledgement>`. Both streams obey backpressure. Only choose channel when both the request direction and response direction are meaningful in the business logic.

## Step 5: Managing Multiple Client Connections

The `RSocketRequester` received in a handler is bound to a specific connection. If the server needs to send requests from a service or background job outside `@ConnectMapping` or `@MessageMapping`, the application typically needs a registry storing requesters by connection session.

A common organization pattern:

1. When accepting a new connection, authenticate client information from security mechanisms or setup metadata.
2. Store the connection's requester in the registry keyed by client identifier and a unique connection session ID.
3. When a business event occurs, look up the right requester and send to the appropriate route.
4. When the connection closes, remove the corresponding entry to avoid holding stale requesters.
5. When a client reconnects, update the new session and prevent the old session from overwriting or accidentally deleting the new session.

Do not use a single global `RSocketRequester` variable for all clients. Each client has its own connection and responder; sending through client A's requester routes the request to client A. If the same user opens multiple devices, keying the registry solely by user ID can drop a connection. You can use a composite key of user ID and connection/session ID.

`@ConnectMapping` helps handle setup but is not a connection-close callback. Use the RSocket server or transport's connection lifecycle mechanisms to detect closure and clean up the registry. `RSocketRequester` is also a `Disposable`; calling `dispose()` closes the underlying connection, so do not call it merely to remove an entry from a map.

## Data, Metadata, and Codec Compatibility

The route is sent in the request's metadata. The business payload resides in the data section. Both ends must agree on the data MIME type and have encoders/decoders matching the data types.

- Basic types such as `String`, `byte[]`, and `ByteBuffer` are supported by Spring's basic codecs.
- For DTOs, register appropriate codecs such as JSON, CBOR, or Protobuf in `RSocketStrategies` on both client and server.
- If using composite metadata to send tokens, trace context, or custom metadata, the receiving side needs corresponding metadata extractors and decoders.
- The route called by the server must match `@MessageMapping` on the client exactly. Routes are hierarchical names, not HTTP URLs; by default, a dot (`.`) is the hierarchy separator.
- MIME types are declared at the connection level in `SETUP`; changing codecs or payload formats on one side must be reflected on the other side.

The examples in this lesson use `String` to focus on bidirectional flow and leverage basic codecs. When replacing with DTOs, configure encoders/decoders for the DTOs on both sides before sending.

## Security When the Server Calls Back to the Client

Reverse requests can trigger actions on a client device or application, so authentication and authorization policies must apply to this request direction as well:

- Authenticate the connection and client identity before placing the requester into the registry.
- Only send routes that the client is authorized to execute; enforce authorization checks on both server and client sides.
- Do not treat a self-reported `clientId` sent by the client in metadata as a trusted identity unless authenticated.
- Avoid sending access tokens or sensitive data in payloads/logs unless necessary.
- Limit payload size, request rate, and number of active streams according to client capacity.
- Handle reconnects, timeouts, transport errors, and offline clients; do not assume a requester is always alive.

## Common Errors and Troubleshooting

| Symptom | Possible cause | How to check or fix |
| --- | --- | --- |
| Server calls route but client reports handler not found | Client has not registered `SocketAcceptor`, or route mismatch | Check `connector.acceptor(...)`, `RSocketMessageHandler.responder(...)`, and `@MessageMapping` name. |
| Client has handler but server cannot call it | Handler was not included in the responder used for the connection | Check the right `RSocketRequester.Builder` and the connector where the acceptor was attached. |
| Reverse request fails immediately when client connects | Server is awaiting the reverse request while handling `SETUP` | Decouple the request from the `@ConnectMapping` completion publisher; do not await client responses during setup. |
| Send succeeds but unsure if client processed it | Using Fire-and-Forget | Use Request-Response with an acknowledgement if business confirmation is needed. |
| Unable to decode DTO | Incompatible codecs or MIME types on the two sides | Check `RSocketStrategies`, encoders/decoders, and MIME types negotiated in `SETUP`. |
| Server sends to wrong device | Registry uses non-unique key or retains stale requester | Track by connection/session ID and update on reconnect. |
| Sending request to disconnected client | Registry did not clean up entry or requester is already closed | Handle transport errors, monitor connection lifecycle, and remove closed sessions. |
| Stream grows memory or slows down | Backpressure not handled or unbounded subscriptions held | Use bounded `Flux`, handle cancellation, and manage concurrent stream counts. |

## Implementation Checklist

- Client registers responder via `RSocketMessageHandler.responder(...)` or an `RSocketMessageHandler` bean attached to the connector.
- Server-called routes match `@MessageMapping` routes on the client.
- Server retrieves the `RSocketRequester` corresponding to the target connection.
- Requests initiated inside `@ConnectMapping` are decoupled from `SETUP` completion.
- Appropriate interaction model is chosen: Request-Response, Request-Stream, Fire-and-Forget, or Request-Channel.
- Both sides have compatible codecs and MIME types.
- Registry uses unique session identifiers and cleans up requesters when connections close.
- Error handling, reconnects, timeouts, cancellation, backpressure, and access control are in place.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — sections on RSocketRequester, Server Requester, Client Responders, and Annotated Responders.
- [Spring Framework Javadoc — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html) — creating responders and registering handlers.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html) — API for sending requests and managing requesters.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — bidirectional communication model, request frames, and metadata.