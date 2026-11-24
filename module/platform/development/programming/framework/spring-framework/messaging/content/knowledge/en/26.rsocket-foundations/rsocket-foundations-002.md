# Requester, Responder, and Bidirectional Symmetry

## Objectives

RSocket is a bidirectional, asynchronous, multiplexed communication protocol over a single connection. When establishing a connection, one side typically initiates the transport and the other accepts it. However, once RSocket SETUP completes, requester and responder roles are determined per request: either endpoint can initiate a request, and the other endpoint responds.

This lesson explains the difference between client/server and requester/responder, the four interaction models of RSocket, how to use RSocketRequester in Spring, how a client can also act as a responder, and how to design bidirectional flows without blocking the reactive pipeline.

After this lesson, you will be able to:

- Distinguish connection-level roles from per-request roles.
- Choose properly between Request-Response, Fire-and-Forget, Request-Stream, or Request-Channel.
- Send requests from client to server using RSocketRequester.
- Allow the server to actively call back into a connected client.
- Register responders on both sides using @MessageMapping.
- Understand back pressure, cancellation, metadata, and the limits of bidirectional communication.

## 1. How Is Client/Server Different from Requester/Responder?

At the transport layer, the client is usually the side that initiates the TCP or WebSocket connection; the server is the side that listens and accepts connections. RSocket uses the SETUP frame for both ends to agree on connection details such as MIME types and protocol configuration.

After SETUP succeeds, the client/server distinction no longer dictates who may send requests. Both endpoints can initiate requests over the same connection. Within a specific request:

- **Requester** is the side that sends the request frame and initiates the interaction.
- **Responder** is the side that receives the request, processes it, and emits responses if the interaction requires responses.

One connection can carry multiple concurrent requests in both directions. Therefore, a device called a client at the connection layer can act as a responder for a request sent by the server, and immediately afterward act as a requester when sending another request to the server.

Example in a device monitoring application:

- The device sends telemetry to the server: the device is the requester, the server is the responder.
- The server pushes new configuration to the device: the server is the requester, the device is the responder.
- The device sends configuration acknowledgment status: the device is the requester again.
- The server asks the device to emit a stream of measurements for several minutes: the server is the requester, the device is the responder for that request-stream.

This is RSocket's symmetry: both endpoints can initiate interactions, unconstrained by a model where clients only send and servers only reply.

## 2. The Four RSocket Interaction Types

RSocket defines four primary request types:

| Type | Requester sends | Responder returns | Use case |
| --- | --- | --- | --- |
| Request-Response | One message | One message | Lookups, calculations, reading state |
| Fire-and-Forget | One message | No response payload | Sending events that need no direct result |
| Request-Stream | One message | A stream of multiple messages | Monitoring metrics, querying large lists |
| Request-Channel | A stream of messages | A stream of responses | Continuous bidirectional data exchange |

Each interaction is represented by its own stream id within the connection. Streams can run concurrently and are multiplexed over the same transport.

### Request-Response

The requester sends one message and waits for exactly one response. In Java with Spring, the single response type is typically Mono<T>.

~~~text
Requester                  Responder
    |                           |
    | ---- request  ----------> |
    | <--- response ----------- |
    |                           |
~~~

Example: client sends a product code and receives one ProductView.

### Fire-and-Forget

The requester sends one message and does not wait for a response payload. This fits events that do not require a direct business reply.

~~~text
Requester                  Responder
    |                           |
    | ---- event -------------> |
    |                           |
~~~

Having no response payload does not mean the application guarantees successful processing. The requester only knows that sending at the protocol layer completed according to API semantics; knowing whether business processing completed requires a separate acknowledgment mechanism.

### Request-Stream

The requester sends an initial message, and the responder returns multiple messages over time. In Spring, the response is typically Flux<T>.

~~~text
Requester                  Responder
    |                           |
    | ---- query -------------> |
    | <--- item 1 ------------- |
    | <--- item 2 ------------- |
    | <--- item 3 ------------- |
    | <--- COMPLETE ------------|
~~~

Example: client requests sensor data for a device and receives a continuous stream of measurements.

### Request-Channel

The requester sends a stream of messages and simultaneously receives a stream of responses. This is the clearest bidirectional form within a single interaction.

~~~text
Requester                  Responder
    |                           |
    | ---- request stream ----> |
    | <--- response stream ---- |
    | ---- next request ------> |
    | <--- next response ------ |
    | ---- COMPLETE ----------> |
    | <--- COMPLETE ----------- |
~~~

Example: both sides send updates in a collaborative session, or the client continuously sends sensor samples while the server returns corresponding alerts.

Request-Channel is not two independent request-responses stitched together manually. It is a single interaction with two payload streams tied to the same stream, sharing flow control and lifecycle.

## 3. Reactive Streams and Back Pressure

RSocket carries Reactive Streams semantics across network boundaries. With Request-Stream and Request-Channel, the requester signals demand so the responder knows how many more elements it may send.

In Java, Spring uses familiar Reactor types:

- Mono<T>: zero or one element.
- Flux<T>: a stream that may contain multiple elements, complete normally, error, or remain unbounded.

The requester does not have to buffer all data into memory before processing it. It can request batches of elements, process them, and then request more. Demand signals propagate over the protocol, helping the responder pace emission according to the requester's consumption capacity.

Benefits:

- Limits uncontrolled buffer growth when consumers are slow.
- Enables streaming processing of large datasets.
- Supports cancellation when the requester no longer needs results.
- Establishes an end-to-end reactive pipeline from the publisher on the responder application to the subscriber on the requester.

Back pressure does not replace all resource-limiting measures. Applications still need limits on concurrency, payload size, processing time, and external resources such as databases or files.

## 4. Using RSocketRequester from the Client

Spring provides RSocketRequester as a fluent API to send requests and encode/decode data and metadata.

TCP connection example:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

Or connecting over WebSocket:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Creating a requester does not necessarily open the connection immediately. The connection is established when the first request executes; the requester can reuse the connection across multiple interactions.

Request call pattern:

~~~java
Mono<ProductView> response = requester
        .route("catalog.product")
        .data(new ProductQuery("SKU-42"))
        .retrieveMono(ProductView.class);
~~~

Steps:

1. route("catalog.product") sets the route in request metadata.
2. data(...) supplies the payload.
3. retrieveMono(ProductView.class) declares a single response type and returns Mono<ProductView>.

If the responder returns multiple elements, use retrieveFlux:

~~~java
Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class);
~~~

If the request needs no payload, omit data():

~~~java
Mono<ServerStatus> status = requester
        .route("system.status")
        .retrieveMono(ServerStatus.class);
~~~

If no response payload is needed, use send():

~~~java
Mono<Void> sent = requester
        .route("audit.record")
        .data(new AuditEvent("USER_LOGIN", "alice"))
        .send();
~~~

The Mono<Void> from send() indicates that sending completed at the API layer; it does not confirm that the responder successfully processed the business event. If a processing outcome is needed, use Request-Response or another acknowledgment mechanism.

## 5. Server-Side Responder with @MessageMapping

Spring supports annotated responders via @MessageMapping. A request-handling method can accept a payload and return Mono or Flux depending on the interaction type.

Server responder example:

~~~java
package com.example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

@Controller
public class CatalogResponder {

    @MessageMapping("catalog.product")
    public Mono<ProductView> product(ProductQuery query) {
        return productService.find(query.sku());
    }

    @MessageMapping("prices.watch")
    public Flux<PriceUpdate> watch(PriceWatchRequest request) {
        return priceService.watch(request.sku());
    }

    @MessageMapping("audit.record")
    public Mono<Void> record(AuditEvent event) {
        return auditService.append(event);
    }
}
~~~

The example above illustrates three cardinalities:

| Input payload | Return value | Interaction |
| --- | --- | --- |
| One payload | Mono<ProductView> | Request-Response |
| One payload | Flux<PriceUpdate> | Request-Stream |
| One payload | Mono<Void> | Fire-and-Forget |

The services and DTOs are business components of the application; the controller snippet only illustrates how Spring maps routes and cardinality. Corresponding ProductQuery, ProductView, PriceWatchRequest, PriceUpdate, and AuditEvent types must be declared in the project.

Spring determines the interaction type from the input and output cardinality. For request-channel, the input is a multi-element publisher, such as Flux<Event>, and the method returns Flux<Response> or another protocol-supported cardinality.

## 6. The Server Can Also Be a Requester

Symmetry becomes evident when the server wants to actively send a request to a connected client.

In @ConnectMapping or @MessageMapping methods, Spring can provide an RSocketRequester representing that connection. The server uses that requester to send requests to the client.

Example: when a device connects, the server asks the device to send its current status:

~~~java
@Controller
public class DeviceConnectionHandler {

    @ConnectMapping("device")
    public Mono<Void> connected(RSocketRequester requester) {
        return Mono.fromRunnable(() ->
                requester.route("device.status")
                        .retrieveMono(DeviceStatus.class)
                        .subscribe(
                                this::recordStatus,
                                this::recordFailure
                        )
        );
    }

    private void recordStatus(DeviceStatus status) {
        // Update device status.
    }

    private void recordFailure(Throwable error) {
        // Record error for request to device.
    }
}
~~~

The key idea is that the request to the client is launched asynchronously and independently from SETUP processing. @ConnectMapping handles the SETUP frame before other requests can start; do not hold the SETUP thread waiting for another RSocket request to finish.

In real applications, manage the subscription or disposable returned from the reactive pipeline if the request is a long-lived stream, and release it when the connection closes. The example above uses a short-lived Request-Response to illustrate the server acting as a requester.

It is also possible to inject RSocketRequester in a @MessageMapping method if the server needs to send a request back while handling a client request.

## 7. The Client Can Also Act as a Responder

A client does not only send requests to the server. It can register @MessageMapping methods so the server can call back into it.

Spring supports registering a client-side responder via RSocketMessageHandler.responder(...) and attaching it to RSocketConnector:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientHandler());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
~~~

Client-side handler class:

~~~java
@Controller
public class ClientHandler {

    @MessageMapping("device.apply-config")
    public Mono<ConfigResult> applyConfig(DeviceConfig config) {
        return deviceService.apply(config);
    }

    @MessageMapping("device.ping")
    public Mono<Pong> ping(Ping request) {
        return Mono.just(new Pong(request.timestamp()));
    }
}
~~~

After the connection is established, the server can send requests to route device.apply-config or device.ping to the client. The client becomes the responder for those requests, even though it initiated the TCP connection.

When an application has multiple controller types or multiple client responders in the same ApplicationContext, configure an appropriate handler-detection predicate to avoid scanning the wrong controllers. RSocketMessageHandler allows customizing the handler predicate.

## 8. A Complete Bidirectional Flow

Suppose a device management system has a server and a device:

1. The device opens a TCP connection to the server and sends SETUP.
2. The server handles @ConnectMapping to authenticate metadata and create session state.
3. The server obtains the device's RSocketRequester and sends a device.status request.
4. The device handles the request with ClientHandler.@MessageMapping and returns DeviceStatus.
5. The device continues sending telemetry to the server via route device.telemetry.
6. The server processes telemetry in @MessageMapping.
7. When temperature exceeds a threshold, the server sends a device.apply-config request.
8. The device applies the configuration and returns ConfigResult.
9. Both sides continue exchanging independent requests over the same connection until the connection closes.

In this flow, roles switch per request. There is no need to open a new TCP connection just because the server needs to invoke an operation on the device.

## 9. Metadata and Routes

An RSocket message has two main parts:

- Data: business payload, usually encoded in JSON, CBOR, Protobuf, or another format.
- Metadata: control or contextual information such as route, security tokens, and tracing.

In Spring, RSocketRequester supports adding metadata:

~~~java
MimeType authMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .metadata(accessToken, authMimeType)
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class);
~~~

Routes are typically passed through routing metadata. Spring's RSocketMessageHandler decodes the route to locate the matching @MessageMapping method. Composite metadata allows a single message to contain multiple independent metadata entries, each with its own MIME type.

Do not place secrets in routes or logs. Authentication metadata must be encrypted in transit, verified on the receiving side, and never written in plaintext to logs.

## 10. Codec and MIME Type Configuration

Both ends must agree on how data and metadata are encoded during SETUP. RSocketRequester.Builder allows configuring:

- dataMimeType(...): MIME type for data.
- metadataMimeType(...): MIME type for metadata.
- setupData(...): data in SETUP.
- setupRoute(...): route in SETUP metadata.
- setupMetadata(...): additional metadata in SETUP.
- rsocketStrategies(...): configures encoders, decoders, and metadata extractors.

Spring only registers basic codecs for String, byte[], and ByteBuffer unless other codecs are added. To send JSON or CBOR DTOs, the application needs the corresponding encoder/decoder, typically via spring-web.

CBOR configuration example:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

If both ends use incompatible MIME types or schemas, requests may connect successfully yet fail payload decoding when handling interactions. Check both SETUP configuration and the codecs registered on each side.

## 11. Back Pressure, Cancellation, and Stream Lifecycle

With Request-Stream and Request-Channel, the requester controls demand. The responder should not emit unbounded data into a consumer unable to process it.

In Reactor:

- subscribe() starts consuming a publisher.
- request(n) is the demand concept on a Reactive Streams subscriber.
- cancel() stops consumption and signals stream cancellation.
- onComplete() signals normal stream completion.
- onError(error) signals stream termination due to an error.

Spring and RSocket propagate demand across the protocol so the responder can pace emitted messages. When the client cancels a subscription or times out, cancellation can propagate to the responder and help stop remaining work.

Example limiting elements on the requester:

~~~java
Flux<PriceUpdate> firstTen = requester
        .route("prices.watch")
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class)
        .take(10);
~~~

take(10) completes after receiving ten elements and cancels the rest of the stream. Responders should design data sources to react to cancellation so they do not continue unnecessary queries or event emission.

## 12. Error Handling and Timeouts

Errors can occur at multiple layers:

- TCP/WebSocket connection or SETUP failure.
- Route or responder not found.
- Payload/metadata cannot be decoded.
- Business logic returns an error.
- Request timeout or connection closed mid-stream.
- Client cancels the interaction before the responder finishes.

With Reactor, handle errors in the pipeline:

~~~java
Mono<ProductView> product = requester
        .route("catalog.product")
        .data(new ProductQuery("SKU-42"))
        .retrieveMono(ProductView.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(error -> fallbackProduct());
~~~

Timeout is a requester-side policy; it does not automatically guarantee all responder-side work has stopped. For long-lived streams, clearly define when a stream ends, when to retry, when to reconnect, and whether retrying could duplicate an operation.

Do not blindly retry Fire-and-Forget if the operation is not idempotent. If a request may be resent after a timeout, use an idempotency key or event ID so the responder can detect duplicates.

## 13. Keepalive, Session Resumption, and Long-Lived Connections

RSocket supports keepalive to detect dead connections. RSocketRequester.Builder allows deeper configuration via the rsocketConnector(...) callback, such as keepalive interval, lifetime, interceptors, or session resumption.

Session resumption is designed to recover connections after network disruptions, but it requires maintaining protocol state and has configuration limits. Do not assume that every completed request or business side effect will be automatically recovered. Applications still need idempotency, timeouts, and business state design.

For long-lived connections:

- Set keepalive interval and lifetime appropriately for the network environment.
- Monitor connection state and release resources on close.
- Limit concurrent streams if each stream consumes significant resources.
- Use back pressure to control producers.
- Define a clear reconnect/resume policy.
- Monitor latency, failed request counts, active stream counts, and buffer usage.

## 14. When Should Each Interaction Be Used?

| Need | Interaction | Example |
| --- | --- | --- |
| Send data and need exactly one result | Request-Response | Look up device information |
| Emit an event with no response needed | Fire-and-Forget | Log non-critical telemetry |
| Send one query, receive many results | Request-Stream | Stream sensor metrics |
| Both sides send data within one session | Request-Channel | Sync state or interactive stream processing |
| Server needs to invoke an operation on client | Server as requester, client as responder | Push configuration down to device |
| Client needs to invoke an operation on server | Client as requester, server as responder | Register device |

Request-Channel is a two-stream interaction bound to a single request. Meanwhile, the server and client initiating separate requests in both directions represent multiple independent interactions over one connection. Both approaches can coexist.

## 15. Testing Bidirectional Symmetry

A good integration test should demonstrate that both endpoints can initiate requests:

1. Start the RSocket server and register server-side responders.
2. Connect the client to the server using RSocketRequester.
3. Have the client send a Request-Response to a server route and assert the result.
4. Configure ClientHandler as the client's responder.
5. Have the server obtain the connection's RSocketRequester and send a request to a client-side route.
6. Verify the client processes the request and returns a response.
7. Test Request-Stream and verify back pressure/cancellation work.
8. Close the connection and verify resources are released.
9. Verify errors for missing routes, timeouts, and payloads with wrong MIME types.

When testing symmetry, do not only test that the client can call the server. Include at least one test where the server initiates a request to the client to confirm the client responder is registered properly.

## 16. Common Pitfalls

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Requests from client succeed but server cannot call client | Client responder not registered on connector | Check SocketAcceptor and connector.acceptor(...). |
| Route does not match | Wrong route, separator, or route matcher | Compare route in requester with @MessageMapping. |
| DTO cannot be decoded | Incompatible MIME type or codecs on both ends | Check dataMimeType, metadataMimeType, Encoder, and Decoder. |
| Server request inside @ConnectMapping hangs | Holding SETUP flow waiting on a request to the client | Launch request independently without blocking SETUP handling. |
| Stream consumes too much memory | Responder emits faster than consumer or lacks back pressure | Use Flux properly, check demand and buffer limits. |
| Timeout causes business logic to run twice | Retrying a non-idempotent request | Use idempotency key or sequence/event id. |
| Connection lost yet application retains resources | Close/error not handled or streams not cleaned up | Monitor connection lifecycle and cancel related publishers. |
| Client and server roles confused | Equating client with requester, server with responder | Identify requester/responder per individual interaction. |

## 17. Key Takeaways

- Client/server describes who opens the transport; requester/responder describes roles in each individual request.
- After SETUP, either endpoint can initiate requests over the same connection.
- RSocket supports Request-Response, Fire-and-Forget, Request-Stream, and Request-Channel.
- RSocketRequester is Spring's API for sending requests, routes, data, and metadata.
- The server can use the connection-bound RSocketRequester to call back to the client.
- The client can also act as a responder using RSocketMessageHandler.responder(...) and connector.acceptor(...).
- Mono represents at most one response; Flux represents a stream of multiple responses.
- Back pressure, cancellation, and timeouts must be designed alongside stream lifecycles.
- Symmetry does not automatically imply exactly-once, durable delivery, or safe retries.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-requester)
- [Spring Framework — Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-annotated-responders)
- [Spring Framework — RSocket Interface](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-interface)
- [RSocket Protocol — Specification](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

