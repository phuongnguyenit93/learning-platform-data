# Lazy Connections, Requester Reuse, and Resource Management

## 1. Objectives and Context

In Spring Messaging, **RSocketRequester** is the high-level API for sending requests over an RSocket connection. It lets applications work with Java objects and metadata rather than manually manipulating RSocket byte buffers directly. This topic focuses on three decisions that directly affect performance and stability:

- When the network connection is actually opened.
- Why a single requester should be reused across multiple requests.
- Who is responsible for closing connections and stopping running streams.

RSocket supports Request-Response, Request-Stream, Request-Channel, and Fire-and-Forget interactions. A single connection can carry multiple concurrent requests; therefore, a requester typically represents a long-lived communication channel to a remote service rather than a single one-off call.

## 2. How Lazy Connection Works

With the current API from Spring Framework 5.3 onward, you can create a requester using TCP or WebSocket:

~~~java
RSocketRequester tcpRequester =
        RSocketRequester.builder().tcp("localhost", 7000);

RSocketRequester webSocketRequester =
        RSocketRequester.builder()
                .websocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Both calls create the client configuration and return an RSocketRequester. They **do not open a network connection immediately when creating the requester**. When the first request is executed, the RSocket client establishes the transport and sends the SETUP frame. The connection is shared for subsequent requests.

This is lazy connection at the transport level. Distinguish it from Reactor's laziness:

1. Creating RSocketRequester only prepares the client and connection configuration.
2. Calling route, data, and retrieveMono/retrieveFlux creates a Publisher describing the request.
3. The Publisher only starts processing when there is a subscriber. When the request actually runs, the client connects if there is no usable connection yet.

Example:

~~~java
RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

Mono<Product> productMono = requester
        .route("catalog.find")
        .data("SKU-001")
        .retrieveMono(Product.class);

// No request is sent merely because the productMono variable was created.
// The request starts when the Publisher is subscribed.
~~~

In a WebFlux application, return the Mono or Flux to the caller so the framework manages the subscription:

~~~java
@GetMapping("/products/{sku}")
public Mono<Product> find(@PathVariable String sku) {
    return catalogClient.find(sku);
}
~~~

Do not call block() on the event loop of a reactive application. block() turns an asynchronous call into a blocking call and can degrade concurrency capacity. Only consider block() at a genuinely synchronous boundary, such as a command-line program, and always set an appropriate timeout.

Lazy connection helps applications avoid opening sockets to a service that has never been called. It also allows initializing RSocket-dependent services while Spring builds the ApplicationContext without forcing the remote service to be ready at that exact moment. Conversely, DNS errors, transport errors, SETUP-frame authentication failures, or an unready server may only surface on the first request. If you need to check readiness, actively execute a health request with a timeout in the application's health check process.

## 3. Reusing a Requester and Shared Connections

An RSocketRequester created via tcp() or websocket() uses an underlying RSocketClient. Requests are sent concurrently over a shared connection; the client can re-establish the connection when needed. This matches RSocket's multiplexing model: multiple requests and streams coexist on a single connection.

For a fixed remote service, the standard pattern is to create one requester in the Spring context and inject it into the services that need it. Do not create a new requester for every HTTP request, every repository call, or every service method invocation.

Benefits of reuse:

- Reduces the number of TCP/WebSocket setups and SETUP frame exchanges.
- Avoids creating many unnecessary clients and connections.
- Allows concurrent requests to share one RSocket connection.
- Centralizes transport, codec, metadata, and lifecycle configuration in one place.

A requester is typically reused within the same endpoint, transport, and connection configuration scope. If two services have different hosts, ports, transports, or connection-level authentication credentials, create a separate requester for each configuration. Do not share a single requester merely because two services use the same data types.

### Configuring a Requester in Spring Boot

Spring Boot auto-configures RSocketRequester.Builder and the required RSocketStrategies when appropriate RSocket configuration is present. The builder is registered in prototype scope because it holds configuration state; each injection point receives a new instance. Use a builder once to create a requester with a definite configuration.

Properties configuration example:

~~~java
@ConfigurationProperties(prefix = "app.rsocket.catalog")
public record CatalogRSocketProperties(String host, int port) {
}
~~~

~~~yaml
app:
  rsocket:
    catalog:
      host: localhost
      port: 7000
~~~

Register the requester as a bean:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogRSocketProperties.class)
public class RSocketClientConfiguration {

    @Bean(destroyMethod = "dispose")
    RSocketRequester catalogRequester(
            RSocketRequester.Builder builder,
            CatalogRSocketProperties properties) {

        return builder.tcp(properties.host(), properties.port());
    }
}
~~~

The bean method receives a fresh builder from Spring Boot, configures the endpoint, and returns the requester. The bean can be injected into multiple services. The destroyMethod = "dispose" attribute tells Spring to close the requester when the ApplicationContext stops.

You can replace TCP with WebSocket if the server exposes an RSocket endpoint over WebSocket:

~~~java
return builder.websocket(
        URI.create("ws://localhost:8080/rsocket"));
~~~

The endpoint and routes must match the responder configuration. For secure WebSocket, use an HTTPS/WSS URI matching the system's environment and authentication configuration.

### Using the Requester in a Service

~~~java
@Service
public class CatalogClient {

    private final RSocketRequester requester;

    public CatalogClient(
            @Qualifier("catalogRequester") RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<Product> find(String sku) {
        return requester.route("catalog.find")
                .data(sku)
                .retrieveMono(Product.class)
                .timeout(Duration.ofSeconds(3));
    }

    public Flux<Product> watch(String category) {
        return requester.route("catalog.watch")
                .data(category)
                .retrieveFlux(Product.class);
    }

    public Mono<Void> publish(CatalogChanged event) {
        return requester.route("catalog.changed")
                .data(event)
                .send();
    }
}
~~~

Exchanged data types can be records:

~~~java
public record Product(String sku, String name) {
}

public record CatalogChanged(String sku, String status) {
}
~~~

This is client-side illustration code; the server needs to implement the catalog.find, catalog.watch, and catalog.changed routes with compatible payload/response types. Objects must be encodable and decodable by registered codecs.

If there are multiple fixed requesters, you can declare multiple beans with distinct names and endpoints. Each @Bean method should receive its own builder. If creating requesters dynamically for multiple endpoints, you can obtain new builders via ObjectProvider<RSocketRequester.Builder>; in that case, the application must also manage the created requesters and dispose them when an endpoint is removed from the system.

## 4. Requests, Data, Metadata, and Publishers

A request is typically described as a chain of operations:

- route(String): selects the handler route on the receiving side; the route is passed in metadata.
- data(Object): sets the data payload. Can pass a single object or a Publisher such as Mono/Flux.
- metadata(Object, MimeType): adds metadata to the request, such as an authentication token or tracing information.
- retrieveMono(Class): receives at most one result.
- retrieveFlux(Class): receives a stream of results.
- send(): sends Fire-and-Forget and returns Mono<Void>.

Request-Response example:

~~~java
Mono<Product> result = requester.route("catalog.find")
        .data("SKU-001")
        .retrieveMono(Product.class);
~~~

Request-Stream example:

~~~java
Flux<Product> results = requester.route("catalog.by-category")
        .data("books")
        .retrieveFlux(Product.class);
~~~

Request-Channel example, where both input and output can be streams:

~~~java
Flux<Reply> replies = requester.route("chat.channel")
        .data(incomingMessages, ChatMessage.class)
        .retrieveFlux(Reply.class);
~~~

For a multi-element Publisher of the same type, the data(Publisher, Class) or data(Publisher, ParameterizedTypeReference) overload explicitly declares the element type so the encoder does not have to re-infer it for every element.

RSocket supports Reactive Streams and backpressure. With Request-Stream or Request-Channel, subscriber demand is propagated to the data producer. Subscribers can request appropriate batch sizes and cancel subscriptions when the stream is no longer needed. Therefore, preserve Mono/Flux across the processing chain rather than converting early to collections via block or collecting the entire stream into memory.

### Per-Request Metadata vs. Connection-Level Metadata

Metadata can be attached per request:

~~~java
MimeType bearerMimeType =
        MimeType.valueOf(
                "message/x.rsocket.authentication.bearer.v0");

Mono<Product> result = requester.route("catalog.find")
        .metadata(accessToken, bearerMimeType)
        .data("SKU-001")
        .retrieveMono(Product.class);
~~~

The example above requires a matching metadata encoder and the responder must support the corresponding MIME type. Default composite metadata allows combining multiple metadata entries with their own MIME types.

The builder also has setupData(), setupRoute(), and setupMetadata(). These values go into the connection-level SETUP frame, so they fit information shared across the entire connection lifetime. Metadata such as tokens that vary per user or per request should usually be passed at the request level. If authentication identity is tied to SETUP, create a requester scoped to that identity and do not share it across different users.

### Fire-and-Forget Is Not Business Confirmation

send() returns Mono<Void> indicating that sending the message completed on the requester side. It **does not confirm that the receiving handler processed the business logic successfully**. If you need to know whether the receiver saved data, updated state, or finished a task, design a Request-Response route so the responder returns an explicit result/acknowledgement.

## 5. Lifecycle and Closing Resources

RSocketRequester implements Reactor Disposable. dispose() closes the underlying client transport connection and notifies subscribers; isDisposed() indicates whether the requester has been disposed. The dispose() API has been available since Spring Framework 5.3.7.

For an application-owned requester, close it when the application stops:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester catalogRequester(RSocketRequester.Builder builder) {
    return builder.tcp("localhost", 7000);
}
~~~

Spring calls dispose() when the bean is destroyed while closing the ApplicationContext. If creating a requester outside the Spring container, clearly define ownership and call dispose() in a shutdown hook or an appropriate finally block.

**Do not dispose the requester after each request.** Multiple services and concurrent requests may be sharing the requester. Disposing at the request level closes the connection for other requests and forces subsequent calls to reinitialize the client/connection. Ownership should remain centralized in the bean or lifecycle-managing component, while consuming services only issue requests.

For long-lived streams, manage subscriptions separately from the requester's lifecycle. When a user leaves a screen or a task ends, cancel that stream's subscription to stop receiving data. When the application stops, disposing the requester closes the client and notifies active subscriptions. Do not keep a subscribed Flux running indefinitely if nothing is consuming the data anymore.

A requester injected into a server-side @MessageMapping or @ConnectMapping method represents the connection of the calling client. This is a requester tied to a specific connection; do not place it into a singleton shared across all clients. Use it within the scope of handling that connection and let the RSocket infrastructure manage server-side connection lifecycles.

## 6. Disconnection, Timeouts, and Retries

With a requester created from tcp() or websocket(), the RSocket client uses a shared connection and can re-establish the connection when needed. This helps subsequent requests continue working after certain disconnection scenarios. However, do not assume every in-flight request will automatically be resent or completed. An in-flight request can fail when the transport drops; the application must handle errors on that Publisher.

You can set timeouts and retries for appropriate operations:

~~~java
return requester.route("catalog.find")
        .data(sku)
        .retrieveMono(Product.class)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200)));
~~~

Retries should only be applied when business semantics allow. Read queries are generally easier to retry than write commands. If retrying a command that creates an order, deducts funds, or emits an event, the request may have been processed on the first attempt while the response was lost; the retry could execute the business operation again. Use an idempotency key, transaction ID, or deduplication mechanism on the receiving side before retrying write operations.

The timeout in the example above limits wait time for the request's Publisher. It does not replace keepalive settings, connection timeouts, or reconnect policies at the RSocketConnector layer. When you need to customize keepalive, session resumption, interceptors, or reconnect behavior, use the builder's rsocketConnector(...) callback and choose policies suited to the system.

## 7. RSocketStrategies and Codecs

RSocketRequester works with Java objects through RSocketStrategies, where Encoders and Decoders are registered for data and metadata. If codecs do not support the payload type, requests can fail during encoding or decoding.

Spring Framework's default only includes basic codecs for String, byte[], and ByteBuffer. Spring Boot auto-configures RSocketStrategies and can register CBOR/JSON when the corresponding Jackson libraries are present. If another format is needed, add the corresponding encoder/decoder and configure them centrally.

RSocketStrategies is designed for reuse. You can share codec configuration between client and server in the same application. Codec configuration should stay stable per requester; do not recreate strategies for every request. If a connection needs a different MIME type, create a requester with the corresponding connection configuration.

## 8. Common Mistakes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Creating a requester per HTTP request | Increases clients and connections, wastes resources | Create a shared bean for a fixed endpoint |
| Disposing after each call | Closes the connection other requests are using | Dispose when the bean or application stops |
| Creating Mono/Flux without subscribing | Request does not run | Return Publisher to caller or subscribe at an appropriate boundary |
| Calling subscribe() arbitrarily inside services | Stream runs detached from processing chain, hard to manage errors and cancellation | Prefer composing and returning Publisher; if detaching, handle errors and retain cancellation handle |
| Using one Builder to create multiple requesters with different configs | Builder configuration may accumulate or be misapplied | Obtain a fresh builder for each configuration |
| Treating send() as processing confirmation | May lose business confirmation | Use Request-Response if an ack is needed |
| Assuming reconnect will replay failed requests | May miss or duplicate business operations | Handle errors and controlled retries, prioritizing idempotency |
| Putting per-user tokens into setupMetadata and sharing requester | Risk of using the wrong identity across requests | Use per-request metadata or separate requesters per auth scope |
| Failing to cancel long-lived streams when unused | Subscribers and data streams continue occupying resources | Cancel the subscription when the task ends |

## 9. How to Verify and Debug

When checking a requester, verify in order:

1. **Endpoint configuration:** host, port, or WebSocket URI is correct; server is listening on the matching transport.
2. **First connection:** creating the bean does not mean it is connected. Send a real request and inspect SETUP/transport logs to confirm connection.
3. **Routes and payloads:** client route matches server @MessageMapping; data types and codecs are compatible.
4. **Reuse:** invoke multiple requests through the same bean and observe server-side connection logs. With the same requester, requests should share the active connection.
5. **Concurrency and backpressure:** test multiple concurrent requests and large-data streams; confirm the subscriber can throttle or cancel the stream.
6. **Application shutdown:** stop the Spring context and verify the requester is disposed; no streams belonging to the application keep running.

You can use @ConnectMapping on the responder to log when a new connection is established. If SETUP logs appear every time a normal request is called, check whether the application is continuously creating new requesters or disposing the requester too early.

An RSocketRequester created with tcp()/websocket() uses RSocketClient. In this case, the rsocket() method may return null because the requester does not directly hold a connected RSocket. Do not use rsocket() as a way to check whether a requester is connected. Instead, check request behavior, dispose state, and transport-layer logs/metrics.

## 10. Design Takeaways

- One stable endpoint and authentication scope typically has one reused RSocketRequester.
- The connection is opened when the first request actually runs; bean creation does not prove the server is ready.
- Mono/Flux only executes when subscribed; keep reactive flows end-to-end across the application.
- Multiple requests can run concurrently over a shared connection.
- Ownership of a requester belongs to the lifecycle-managing component; dispose it when that component stops.
- Cancel a stream's subscription when it is no longer needed; do not dispose a shared requester to stop a single stream.
- Use per-request metadata for data that changes per request; use SETUP for connection-level configuration.
- Retries must account for business idempotency and the possibility that the responder processed the request before the connection dropped.

## 11. API Differences Across Versions

- Since Spring Framework 5.3, prefer Builder.tcp(host, port), Builder.websocket(uri), and Builder.transport(...). The older connectTcp(), connectWebSocket(), and connect() methods were deprecated in 5.3.
- The old connectTcp()/connectWebSocket() APIs returned Mono<RSocketRequester>; connection occurred when the Publisher was subscribed. When maintaining Spring 5.2 code, subscribe or block with timeout at the proper boundary and manage the requester after obtaining it.
- RSocketRequester has dispose()/isDisposed() since Spring Framework 5.3.7. For older versions, verify the actual API before using destroyMethod = "dispose".
- The Spring Boot examples above use the builder auto-configured by Boot. In applications using only Spring Framework, you must supply RSocketStrategies and required client configurations yourself.

## References

- Spring Framework Reference — RSocket: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework Javadoc — RSocketRequester: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Framework Javadoc — RSocketRequester.Builder: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Boot Reference — RSocket: https://docs.spring.io/spring-boot/reference/messaging/rsocket.html
