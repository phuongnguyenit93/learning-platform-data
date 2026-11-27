# WebSocketGraphQlClient in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain the role of `WebSocketGraphQlClient` in a Spring for GraphQL application.
- Distinguish the WebSocket client from `HttpGraphQlClient` and `RSocketGraphQlClient`.
- Create a client using `WebSocketGraphQlClient.builder(...)` and a `WebSocketClient`.
- Use the unified fluent API of `GraphQlClient` to send operations.
- Receive subscription streams using `retrieveSubscription(...).toFlux(...)`.
- Understand how a single WebSocket connection serves multiple operations.
- Distinguish the HTTP handshake from the GraphQL WebSocket connection initialization message.
- Pass authentication metadata and protect the connection.
- Manage cancellation, reconnection, and transport errors.
- Test streams using Reactor `StepVerifier`.

## 1. What is WebSocketGraphQlClient?

`WebSocketGraphQlClient` is a GraphQL client that uses the WebSocket transport. The client sends GraphQL operations over a WebSocket connection and receives responses over that same connection.

WebSocket is suitable for subscriptions because the connection can remain open long-term and the server can push multiple responses over time. The client does not need to open a new HTTP request for each event.

For example, an administration application wants to track order status:

~~~graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        status
        changedAt
    }
}
~~~

After subscribing, the server can send multiple `orderStatusChanged` payloads within the same subscription operation. The client turns those payloads into a reactive stream to update the UI or execute business logic.

`WebSocketGraphQlClient` implements the `GraphQlClient` abstraction, so building documents, passing variables, retrieving fields, and converting responses are very similar to Spring's other GraphQL clients.

## 2. When to use WebSocketGraphQlClient?

Spring for GraphQL provides different client transports. Choose the transport based on the interaction style:

| Client | Transport | Suitable use cases |
| --- | --- | --- |
| `HttpGraphQlClient` | HTTP request/response | Standard Queries and Mutations |
| `WebSocketGraphQlClient` | WebSocket | Subscriptions and interactions requiring a long-lived connection |
| `RSocketGraphQlClient` | RSocket | Systems already using RSocket and needing RSocket interaction models |

For a screen that just loads book details and displays them, HTTP is usually simpler. For a screen that needs to receive continuously changing order statuses, WebSocket is the right choice.

An application can use multiple clients simultaneously: HTTP for Queries/Mutations and WebSocket for Subscriptions. There is no need to move every request to WebSocket just because the system has one subscription.

## 3. Creating WebSocketGraphQlClient

`WebSocketGraphQlClient` requires a WebSocket URI and an implementation of Spring's `WebSocketClient`.

Example using Reactor Netty:

~~~java
import java.net.URI;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(
                URI.create("ws://localhost:8080/graphql"),
                new ReactorNettyWebSocketClient()
        ).build();
~~~

Components:

- `ws://` is unencrypted WebSocket, typically used only in local development environments.
- `wss://` is WebSocket over TLS, which should be used in production environments.
- The URI must point to the WebSocket endpoint configured on the server.
- `ReactorNettyWebSocketClient` is a WebSocket client implementation based on Reactor Netty.

If the application uses a different WebSocket implementation, you can pass that implementation to the builder as long as it satisfies the `WebSocketClient` interface.

Do not confuse a WebSocket URI with an HTTP URL. Some servers use the same `/graphql` path for HTTP and WebSocket, but the schemes differ: `http/https` for HTTP and `ws/wss` for WebSocket.

## 4. Configuring a shared client

Create the client once and share it within the application instead of creating a new WebSocket client for each subscription call.

You can register the client as a Spring bean:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

@Configuration
class GraphQlClientConfiguration {

    @Bean
    WebSocketGraphQlClient webSocketGraphQlClient() {
        return WebSocketGraphQlClient.builder(
                URI.create("wss://api.example.com/graphql"),
                new ReactorNettyWebSocketClient()
        ).build();
    }
}
~~~

Then inject the client into components that need to receive events:

~~~java
@Service
class OrderUpdatesClient {

    private final WebSocketGraphQlClient graphQlClient;

    OrderUpdatesClient(WebSocketGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }
}
~~~

A shared client helps manage the connection and multiple operations consistently. Avoid creating a new client every time a user opens a screen unless there is a reason for isolation or separate connection configuration.

The client lifecycle should align with the application lifecycle. When the application stops, allow the client and WebSocket transport to close according to the lifecycle provided by the Spring GraphQL version in use. Do not let connections outlive the component that owns them.

## 5. The common GraphQlClient fluent API

`WebSocketGraphQlClient` uses the `GraphQlClient` request API. A request is typically created with `document(...)`, followed by adding variables or an operation name.

Query example:

~~~java
import reactor.core.publisher.Mono;

Mono<Book> book = graphQlClient.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Mutation example:

~~~java
Mono<Book> updatedBook = graphQlClient.document("""
        mutation RenameBook($id: ID!, $title: String!) {
            renameBook(id: $id, title: $title) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .variable("title", "Spring GraphQL")
        .retrieve("renameBook")
        .toEntity(Book.class);
~~~

Meaning of each step:

1. `document(...)` provides the GraphQL document.
2. `variable(...)` assigns a value to a variable in the document.
3. `retrieve("book")` selects the field to extract from the response.
4. `toEntity(Book.class)` converts the field value into a Java object.
5. The result is `Mono<Book>` because a standard Query/Mutation produces a single response.

This fluent API makes switching between HTTP and WebSocket transports easier. Even so, for standard Queries/Mutations, HTTP is usually the simpler and more appropriate choice.

## 6. Sending a subscription and receiving a Flux

The main difference of the WebSocket client is the API for receiving subscription streams.

Example SDL:

~~~graphql
type OrderStatusChanged {
    orderId: ID!
    status: String!
    changedAt: String!
}

type Subscription {
    orderStatusChanged(orderId: ID!): OrderStatusChanged!
}
~~~

Java payload:

~~~java
import reactor.core.publisher.Flux;

public record OrderStatusChanged(
        String orderId,
        String status,
        String changedAt) {
}
~~~

Client creating a subscription:

~~~java
Flux<OrderStatusChanged> updates =
        graphQlClient.document("""
                subscription WatchOrder($orderId: ID!) {
                    orderStatusChanged(orderId: $orderId) {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .variable("orderId", "order-42")
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);
~~~

`retrieveSubscription("orderStatusChanged")` selects the root subscription field. `toFlux(OrderStatusChanged.class)` converts each field payload into an element in the `Flux`.

Unlike `retrieve(...).toEntity(...)`, a subscription is not converted into a single `Mono` if the client needs to receive multiple events. `Flux` represents a sequence of results over time.

## 7. Handling each event from the subscription stream

The client can register event handlers using Reactor:

~~~java
import reactor.core.Disposable;

Disposable subscription = updates.subscribe(
        event -> log.info(
                "Order status changed orderId={} status={}",
                event.orderId(),
                event.status()
        ),
        error -> log.error(
                "Order update stream failed",
                error
        ),
        () -> log.info("Order update stream completed")
);
~~~

Three handler callbacks:

- `onNext`: receives an event.
- `onError`: stream terminated due to an error.
- `onComplete`: stream completed normally.

A subscription stream is usually kept active while the user is monitoring data. Do not assume the stream always completes after the first event.

If the application needs to update state, convert the event into an action or update the state store according to your application's model. Avoid performing long-blocking work inside the `onNext` callback, as it can slow down event processing.

## 8. Multiple subscriptions on one connection

The WebSocket transport allows multiple operations to run concurrently over the same connection. `WebSocketGraphQlClient` manages sending operations and correlating responses back to their respective operations.

Example of a screen tracking two orders:

~~~java
Flux<OrderStatusChanged> firstOrder =
        graphQlClient.document("""
                subscription {
                    orderStatusChanged(orderId: "order-42") {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);

Flux<OrderStatusChanged> secondOrder =
        graphQlClient.document("""
                subscription {
                    orderStatusChanged(orderId: "order-99") {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);
~~~

Both streams can be subscribed to independently:

~~~java
Disposable first = firstOrder.subscribe(this::handleOrderUpdate);
Disposable second = secondOrder.subscribe(this::handleOrderUpdate);
~~~

Each operation has its own lifecycle. Cancelling `first` should not cancel `second` when both share the same client connection.

Multiplexing avoids opening a separate WebSocket connection for every subscription. However, limit the number of concurrent operations and subscriptions per user to avoid exhausting server resources.

## 9. WebSocket handshake and GraphQL connection initialization

WebSocket starts with an HTTP upgrade handshake. After the connection is upgraded, the GraphQL WebSocket protocol performs a connection initialization step at the application layer.

These two stages are distinct:

1. **Handshake:** the browser/client and server negotiate upgrading the HTTP connection to WebSocket. HTTP headers can be used for authentication at this stage.
2. **Connection initialization:** the client sends an initialization message according to the GraphQL WebSocket protocol; the payload can carry authentication metadata or context as agreed between client and server.

With the popular GraphQL over WebSocket protocol `graphql-transport-ws`, the lifecycle includes messages such as `connection_init`, `connection_ack`, `subscribe`, `next`, `error`, and `complete`.

Do not confuse HTTP handshake headers with the `connection_init` payload. The server may check them at different points. Agree on the authentication mechanism between client and server.

## 10. Passing authentication metadata

Some systems authenticate WebSockets via headers during the handshake, such as a Bearer token. Headers can be configured on the WebSocket transport or builder according to the API of the implementation in use.

Illustrative header configuration example:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(
                URI.create("wss://api.example.com/graphql"),
                new ReactorNettyWebSocketClient()
        )
        .headers(headers -> headers.setBearerAuth(accessToken))
        .build();
~~~

Configuring handshake headers is only suitable when the server authenticates at the HTTP upgrade stage. If the server requires the token in the `connection_init` payload, the client must configure the payload using the supported API/protocol of the version in use.

Notes:

- Do not put tokens in the query string.
- Do not log the `Authorization` header.
- Use `wss://` to encrypt data over the network.
- Tokens that expire while a connection remains open require a refresh or reconnect policy.
- Do not assume updating a token in a Java variable automatically updates an already-open connection.
- The server must still verify authorization for each operation and each resource.

Especially for long-lived WebSocket connections, decide whether the token is validated once at handshake, at connection initialization, or re-validated periodically while active.

## 11. Client interceptors and shared metadata

The Spring GraphQL client supports interceptors to apply common logic across requests, such as:

- Logging the operation name.
- Attaching correlation metadata.
- Standardizing error handling.
- Measuring request duration.
- Adding headers or metadata via supported transport mechanisms.

Interceptors can be configured on the GraphQL client builder. Request/response interceptors at the GraphQL layer are distinct from WebSocket handshake header configuration.

Do not include access tokens, sensitive variables, or entire GraphQL documents in logs. For subscriptions, distinguish logs for operation start, individual events, stream errors, and operation completion; a long-lived stream should not produce overly large payload logs.

If a correlation ID needs to accompany every event, agree with the server on where metadata is generated and passed. Do not use a global mutable value to assign request IDs across multiple concurrent subscriptions.

## 12. Cancellation and closing subscriptions

When a user leaves a screen or no longer needs updates, the client must cancel the subscription.

Example:

~~~java
Disposable subscription = updates.subscribe(this::handleOrderUpdate);

// When no longer tracking the order:
subscription.dispose();
~~~

`dispose()` cancels the subscription on the client side. With the WebSocket GraphQL protocol, the client sends a message terminating the corresponding operation and the server can cancel the associated publisher.

Cancelling one operation does not mean closing the entire WebSocket connection. Other operations on the same client can continue running.

When a UI component is disposed or a service stops, keep the `Disposable` handle to cancel at the right time. If you create a subscription without keeping its handle, the application may keep receiving events after the screen has closed.

## 13. Reconnection and handling connection loss

WebSocket is a long-lived connection, so it can encounter:

- Client network disconnections.
- Server restarts or deployments.
- Reverse proxies closing idle connections.
- Token expiration.
- Keep-alive timeouts.
- Connections rejected or closed due to resource limits.

When a connection drops, active subscriptions may fail or terminate. The application must decide whether to re-subscribe.

A reconnection strategy should define:

1. Which error conditions are retryable.
2. Wait intervals between attempts, with exponential backoff and jitter.
3. Limits on retry count or retry duration.
4. How to refresh credentials before opening a new connection.
5. How to recreate the subscriptions that are still needed.
6. How to avoid duplicate event processing after reconnecting.

Reconnecting does not guarantee receiving events emitted during the disconnection window. If events must not be missed, payloads should carry an event ID or sequence number and the server must support replay/resume from a known position. A WebSocket connection by itself is not a durable message broker.

## 14. Handling GraphQL errors and transport errors

Distinguish GraphQL errors from connection errors:

| Error type | Example | Handling |
| --- | --- | --- |
| GraphQL error in response | User lacks permission to view a field | Read error details/code and handle per API contract |
| Subscription operation error | Server rejects or terminates an operation | Display error state for that subscription |
| Transport error | WebSocket disconnect, handshake failure | Retry/reconnect according to policy |
| Deserialization error | Payload cannot be converted to DTO | Check schema and Java types |
| Application callback error | Event consumer throws an exception | Isolate consumer error and monitor stream |

When using `retrieveSubscription`, if you need full access to the response and errors rather than extracting a single field, use the appropriate subscription execution API for your Spring GraphQL version. Do not ignore GraphQL errors merely because the WebSocket connection remains open.

Do not automatically retry all errors. Authorization or validation errors are usually not resolved by repeatedly reconnecting. Only retry transient errors with bounded limits.

## 15. Backpressure and slow event processing

The client may receive events faster than it can process them. In that case, decide how to throttle or regulate them:

- Process quickly inside callbacks and offload heavy work to an appropriate scheduler.
- Use a bounded buffer if a short-term backlog of events needs to be retained.
- Use `onBackpressureBuffer` with explicit capacity limits and overflow strategy when appropriate.
- Use `sample` or `latest` if only the most recent state is needed and business logic allows dropping intermediate events.
- Terminate the subscription if the consumer cannot keep up within resource limits.

Example:

~~~java
updates
        .onBackpressureBuffer(
                100,
                dropped -> log.warn(
                        "Order event buffer overflow orderId={}",
                        dropped.orderId()
                )
        )
        .subscribe(this::handleOrderUpdate);
~~~

Client-side buffering only manages pressure within the client pipeline. It does not provide durable delivery guarantees and cannot recover events the server already dropped or lost due to connection loss.

If every event matters, you need event IDs, replay, and a data source with retention rather than merely increasing buffer sizes.

## 16. Lifecycle and resources of WebSocketGraphQlClient

A WebSocket client is typically shared throughout the application lifecycle. Manage resources at their proper scopes:

- **Client instance:** typically created once and injected as a Spring bean.
- **Connection:** managed by the client/transport according to its lifecycle.
- **Subscription operation:** each operation can be cancelled independently.
- **Event consumer:** must be stopped when the component no longer uses the stream.

Do not create a new client for every event or every method call. Nor should you close the shared connection just because one screen cancels its subscription.

When the application shuts down, stop application-managed subscriptions and let the client lifecycle complete so the connection/transport is released. If creating a client manually outside the Spring context, manage its lifecycle using the library version's API.

## 17. Testing WebSocketGraphQlClient

You can test event reception streams using Reactor `StepVerifier`.

Example with a controlled test publisher:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.test.StepVerifier;

Flux<OrderStatusChanged> updates = graphQlClient.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                status
                changedAt
            }
        }
        """)
        .variable("orderId", "order-42")
        .retrieveSubscription("orderStatusChanged")
        .toFlux(OrderStatusChanged.class);

StepVerifier.create(updates)
        .assertNext(event -> {
            assertThat(event.orderId()).isEqualTo("order-42");
            assertThat(event.status()).isEqualTo("SHIPPED");
        })
        .thenCancel()
        .verify();
~~~

This form of test requires a running test WebSocket GraphQL server emitting the corresponding events. The test must ensure the server endpoint, subprotocol, and client are compatible.

What to test:

- The client connects to the right `ws://` or `wss://` endpoint.
- The subscription sends the correct document and variables.
- The client receives multiple events in the order guaranteed by the server.
- Two subscriptions on the same client receive their own distinct events.
- `dispose()` cancels the targeted operation properly.
- Cancelling one operation does not stop another operation.
- Handshake or connection initialization is rejected when credentials are invalid.
- Connection loss triggers the configured retry policy.
- GraphQL errors are distinguished from transport errors.
- Consumers do not continue running after the component has stopped.

For tests needing a controlled publisher without opening a socket, you can test the application's `Flux` processing logic separately. However, include at least one integration test over the WebSocket transport to verify connectivity, protocol, and subscription lifecycle.

## 18. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot connect | Using an HTTP URI instead of a WebSocket URI or wrong path | Check `ws://`/`wss://` and the endpoint |
| Handshake rejected | Missing or invalid authentication header | Check the handshake auth mechanism |
| Server does not accept subscription | Client and server disagree on WebSocket subprotocol | Use a GraphQL WebSocket protocol supported by both |
| Subscription emits only one event | Server publisher completes after the first event | Check the server-side event source |
| Old events are missing | Event source does not support replay | Use a snapshot Query or a broker with retention |
| Cancelling one subscription drops another stream | Closing the shared client connection instead of disposing the operation | Dispose the operation's `Disposable` |
| Connection drops without re-subscribing | Reconnect and resubscribe not designed | Add retry with backoff and operation recovery |
| Token expires while connection is open | Authenticated only at handshake time | Refresh credentials and reconnect per policy |
| Client processes events slowly | Blocking callback or unbounded buffer | Optimize consumer and set backpressure limits |
| Duplicate events processed after reconnect | Missing event ID or idempotency | Use sequence/event IDs and idempotent handling |
| Multiple connections created unnecessarily | Creating a client on every call | Share the client bean and manage operations individually |

## 19. WebSocketGraphQlClient integration workflow

When integrating a WebSocket GraphQL client, follow this sequence:

1. **Verify the server endpoint.** Check the WebSocket path and subprotocol supported by the server.
2. **Choose the transport client.** Provide an appropriate `WebSocketClient` implementation.
3. **Create a shared client.** Use `WebSocketGraphQlClient.builder(...)` and manage its lifecycle.
4. **Design the GraphQL document.** Name the operation and declare variables.
5. **Create the stream.** Use `retrieveSubscription(...).toFlux(...)` for subscriptions.
6. **Handle events.** Keep callbacks non-blocking and distinguish `onNext`, `onError`, and `onComplete`.
7. **Secure the connection.** Use TLS and authentication suitable for handshake/connection initialization.
8. **Manage operations.** Retain the `Disposable` and cancel when no longer needed.
9. **Design recovery.** Define reconnect, backoff, resubscribe, and replay rules.
10. **Test.** Use `StepVerifier` alongside integration tests over the WebSocket endpoint.

## 20. Summary

`WebSocketGraphQlClient` is Spring for GraphQL's GraphQL client for the WebSocket transport. The client is created via a builder with a WebSocket URI and a `WebSocketClient` implementation. It uses the shared fluent API of `GraphQlClient` to construct documents, pass variables, and read responses; for subscriptions, `retrieveSubscription(...).toFlux(...)` turns events into a reactive stream.

WebSocket is suited for long-lived update streams and can multiplex multiple operations over a connection. Manage the client at the application level, cancel individual subscriptions via `Disposable`, distinguish the handshake from connection initialization, protect authentication metadata, and establish a bounded reconnection policy. When a connection drops, events may be missed unless the server supports replay. Combining `StepVerifier` with WebSocket integration tests verifies both event reception and lifecycle, cancellation, and transport errors.
