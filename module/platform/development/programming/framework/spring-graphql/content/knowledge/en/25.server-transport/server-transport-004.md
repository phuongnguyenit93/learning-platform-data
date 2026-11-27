# WebSocket transport

GraphQL is typically invoked via an HTTP request that returns a single response. This works well for Queries and Mutations, but Subscriptions require a long-lived connection so the server can send multiple results over time. **WebSocket transport** provides a bidirectional channel between client and server, allowing clients to subscribe to operations, receive events, and unsubscribe over the same connection.

Spring for GraphQL supports GraphQL over WebSocket alongside HTTP and RSocket. The WebSocket handler uses the GraphQL over WebSocket Protocol, dispatches each operation to the GraphQL execution chain, and sends results back to the client. A single WebSocket session can carry multiple concurrent operations, so applications must manage authentication, resources, timeouts, and connection lifecycles.

## When should you use WebSocket transport?

WebSocket is suitable when clients need continuous data updates or a bidirectional connection:

- Tracking order or transaction status.
- Receiving inventory, price, or auction status updates.
- Receiving live notifications in dashboards.
- Real-time collaborative data updates.
- Running multiple GraphQL subscriptions over one connection.

Transport comparison:

| Transport | Communication pattern | Common use cases |
| --- | --- | --- |
| HTTP | Individual request and response | Query, Mutation |
| Server-Sent Events (SSE) | Client sends an HTTP request; server streams events one-way | Subscriptions when the client only needs to receive data |
| WebSocket | Bidirectional connection, multiple messages within the same session | Subscriptions, multiplexing multiple operations, and bidirectional interaction |
| RSocket | Message protocol with request-response and request-stream | Reactive systems or service-to-service communication |

WebSocket is not mandatory for every Subscription. If the client only needs to receive a stream from the server and does not need bidirectional communication after opening the stream, SSE can be simpler. WebSocket is useful when you need multiple operations on the same connection, control messages, and multiplexing.

## Configuring the WebSocket endpoint in Spring Boot

Spring Boot does not enable the GraphQL WebSocket endpoint by default. Applications need to configure the path using the `spring.graphql.websocket.path` property.

For Servlet/Spring MVC applications, add the WebSocket starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
}
~~~

For Spring WebFlux applications, use the WebFlux starter; there is no need to add `spring-boot-starter-websocket` separately:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Configure the endpoint and timeout limits:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 25s
~~~

Meaning:

- `path`: path of the WebSocket endpoint.
- `connection-init-timeout`: how long to wait for the connection initialization message from the client. Spring Boot currently defaults to 60 seconds if not configured.
- `keep-alive`: maximum idle interval before the server sends a ping to keep the connection alive.

The WebSocket path can match the HTTP path if configured that way. Clients must still use the proper scheme: `ws://` when unencrypted and `wss://` when using TLS. In production environments, prefer WSS.

Do not mix MVC and WebFlux starters arbitrarily. Choose the web stack according to your application architecture so Spring Boot creates the appropriate WebSocket handler and I/O model.

## GraphQL over WebSocket Protocol

Spring for GraphQL uses the GraphQL over WebSocket Protocol from the `graphql-ws` library, with the WebSocket subprotocol named **graphql-transport-ws**. This is the newer protocol replacing the older `subscriptions-transport-ws` protocol; the two protocols are incompatible.

Client and server must agree on the same subprotocol during the WebSocket handshake. If the client only supports the older protocol, the connection may be established at the WebSocket layer, but GraphQL messages will not be exchanged in the format the server expects.

Main messages:

| Message | Direction | Meaning |
| --- | --- | --- |
| connection_init | Client → Server | Initializes the GraphQL session and may carry an authentication payload |
| connection_ack | Server → Client | Server accepts the connection initialization |
| subscribe | Client → Server | Sends a GraphQL operation with an ID |
| next | Server → Client | Sends a result for an operation |
| error | Server → Client | Reports an error terminating the operation |
| complete | Bidirectional | Signals operation completion or client cancellation of an operation |
| ping / pong | Bidirectional | Checks connectivity and keeps the session alive |

## Lifecycle of a WebSocket connection

A GraphQL connection typically goes through these steps:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant W as WebSocket Endpoint
    participant G as GraphQL Engine
    participant S as Subscription Source

    C->>W: WebSocket handshake
    Note over C,W: Subprotocol graphql-transport-ws
    C->>W: connection_init
    W-->>C: connection_ack
    C->>W: subscribe (id, payload)
    W->>G: Execute GraphQL operation
    G->>S: Subscribe to event publisher
    S-->>G: Event
    G-->>C: next (id, result)
    S-->>G: Event
    G-->>C: next (id, result)
    C->>W: complete (id)
    W->>S: Cancel publisher
    W-->>C: Connection remains open
~~~

Details:

1. The client opens a WebSocket connection and negotiates the subprotocol.
2. The client sends `connection_init`, optionally with a payload containing authentication credentials.
3. The server acknowledges with `connection_ack`.
4. The client sends `subscribe` with an operation ID and GraphQL payload.
5. The server executes the operation; for a Subscription, each event produces a `next` message.
6. When the stream finishes, the server sends `complete` or `error`.
7. The client can send `complete` to cancel one operation while keeping the connection open for other operations.

The server may require `connection_init` within a bounded time. If the client does not send this message in time, the connection may be closed. Do not treat a successful WebSocket handshake as the GraphQL session being ready; wait for `connection_ack` before sending operations.

## A single connection can multiplex multiple operations

A WebSocket session does not correspond to a single Subscription. Clients can send multiple `subscribe` messages with different IDs over the same connection:

~~~json
{
  "id": "stock-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { stockChanged(productId: \"p-1\") { availableQuantity } }"
  }
}
~~~

Another operation with its own ID:

~~~json
{
  "id": "order-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { orderChanged(orderId: \"o-10\") { status } }"
  }
}
~~~

The server distinguishes results by operation ID:

~~~json
{
  "id": "stock-1",
  "type": "next",
  "payload": {
    "data": {
      "stockChanged": {
        "availableQuantity": 18
      }
    }
  }
}
~~~

Each ID must be unique within the connection at any given time. The client uses `complete` with the matching ID to cancel the corresponding operation. Remaining subscriptions continue running until they complete, are cancelled, or the connection closes.

Multiplexing reduces the number of sockets a client needs to open. However, it also allows a single connection to consume more server resources; limit concurrent operations and measure load per session.

## The subscribe message contains a GraphQL operation

The payload of `subscribe` contains content similar to a standard GraphQL request:

~~~json
{
  "id": "order-watch-1",
  "type": "subscribe",
  "payload": {
    "operationName": "WatchOrder",
    "query": "subscription WatchOrder($id: ID!) { orderChanged(orderId: $id) { id status updatedAt } }",
    "variables": {
      "id": "order-100"
    }
  }
}
~~~

The server processes the query document, operation name, and variables according to GraphQL semantics. WebSocket is only a transport; it does not change how GraphQL validates the schema, arguments, selection sets, resolvers, or authorization.

WebSocket can also be used for a Query or Mutation returning a single result. However, in typical applications, HTTP remains the simpler choice for request-response; WebSocket is usually enabled to support Subscriptions or multiple operations over the same session.

## Mapping Subscriptions still uses @SubscriptionMapping

The transport does not change how resolvers are declared. Subscription fields are still mapped with `@SubscriptionMapping` and typically return `Flux<T>`:

~~~graphql
type Subscription {
  orderChanged(orderId: ID!): OrderEvent!
}

type OrderEvent {
  id: ID!
  orderId: ID!
  status: String!
  updatedAt: String!
}
~~~

A Java DTO can represent the same fields:

~~~java
public record OrderEvent(
        String id,
        String orderId,
        String status,
        String updatedAt) {
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderChanged(@Argument String orderId) {
        return eventService.eventsFor(orderId);
    }
}
~~~

When a client sends an operation over WebSocket, Spring GraphQL invokes the same annotated controller and service as when executing a subscription over other streaming-capable transports. Each `Flux` element is resolved by the GraphQL runtime into a payload according to the selection set.

## Authentication via HTTP handshake or connection_init

WebSocket has two common points for authentication:

**HTTP handshake**

WebSocket begins with an HTTP upgrade request. The application can authenticate cookies or HTTP headers at the Spring Security layer before accepting the handshake. The authenticated principal can then be used in subsequent GraphQL requests over that connection.

**GraphQL connection_init payload**

Clients can send authentication information in the `connection_init` message:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
~~~

Spring for GraphQL provides built-in `AuthenticationWebSocketInterceptor` support for both MVC and WebFlux to read credentials from the `connection_init` payload, authenticate, and propagate `SecurityContext` to subsequent requests on the connection. Choose the mechanism that fits how clients provide credentials and your application's Spring Security configuration.

Do not pass tokens in the query string because URLs can appear in access logs, browser history, proxy logs, or telemetry. Authentication payloads and headers must also not be logged verbatim.

## WebSocketGraphQlInterceptor and WebGraphQlInterceptor

Spring for GraphQL provides two levels of interception:

| Interceptor | Scope | Responsibilities |
| --- | --- | --- |
| WebGraphQlInterceptor | Each GraphQL request over HTTP or WebSocket | Read request, populate `GraphQLContext`, modify `ExecutionInput` or response |
| WebSocketGraphQlInterceptor | WebSocket connection lifecycle and requests on the connection | Handle connection start/termination, cancellation, and WebSocket callbacks |

`WebSocketGraphQlInterceptor` extends `WebGraphQlInterceptor`. It adds callbacks for connection lifecycle and client cancellation. An interceptor chain can contain at most one `WebSocketGraphQlInterceptor`; standard `WebGraphQlInterceptor` beans can still process individual GraphQL operations.

Spring Boot automatically registers `WebGraphQlInterceptor` beans with the web transport. If you need custom WebSocket lifecycle handling, configure `WebSocketGraphQlInterceptor` in the `WebGraphQlHandler` chain according to the mechanism for your Spring for GraphQL version.

Do not use a connection-level interceptor to replace per-field authorization. A user can subscribe to multiple operations targeting different resources on the same connection; each operation still requires appropriate access checks.

## Securing long-lived subscriptions

Connection authentication only establishes identity at session setup time. A subscription can outlive an access token or login session. Applications must decide how to handle when:

- A token expires while the connection is still open.
- A user logs out or their account is locked.
- Access rights to an order or tenant are revoked.
- A new operation requests a different resource over the same connection.
- A client sends too many operations or oversized payloads.

Check permissions when an operation is registered and consider re-checking while the stream is active if permissions can change. When credentials expire or the principal is revoked, cancel the operation or close the connection according to security policy.

With cookie authentication, consider Cross-Site WebSocket Hijacking. Validate the handshake `Origin`, configure explicit allowed origins, protect cookies with appropriate attributes, and apply matching authentication/CSRF policies. CORS for HTTP endpoints does not automatically replace `Origin` validation and WebSocket handshake authentication.

## Keep-alive, timeouts, and connection lifecycle

A WebSocket can remain open for a long time without sending messages. Proxies, load balancers, or NATs may close idle connections. GraphQL over WebSocket supports `ping` and `pong`; Spring Boot provides the `spring.graphql.websocket.keep-alive` property to configure the server to send pings when a connection is idle.

Clients can also send pings to check connectivity. Distinguish between:

- **WebSocket ping/pong:** checks the connection layer.
- **GraphQL connection_init/connection_ack:** initializes the GraphQL session.
- **Operation subscribe/next/complete:** lifecycle of each GraphQL operation.

`connection-init-timeout` limits how long the server waits for the session initialization message. It is not a timeout for each Subscription. Operation timeouts or subscription lifetimes must be designed separately based on business requirements.

When a client closes a connection, the server must cancel active operations and release event source subscriptions. If the client reconnects, that is a new connection; the application must not assume old subscriptions automatically resume. To support resuming, use a cursor or event ID and a data source capable of reading from a prior position.

## Resource management and session limits

A single WebSocket connection can hold many concurrent Subscriptions. Spring for GraphQL recommends configuring appropriate resource limits:

- Maximum open connections on the web server or connector.
- Maximum message buffer size in the WebSocket container.
- Concurrent subscriptions per session.
- Connection timeouts and keep-alive intervals.
- Payload sizes and GraphQL operation depth/complexity limits.
- Subscriptions per user, tenant, or client.

`GraphQlWebSocketHandler` offers a `maxSubscriptionsPerSession` option when configuring the handler manually. By default it is unlimited; when a configured limit is reached, the session may be closed. With Spring MVC, message buffer limits are configured via the Jakarta WebSocket `ServerContainer`; with WebFlux, the corresponding configuration depends on the reactive server in use.

Do not apply a single arbitrary limit across all systems. Base limits on payload size, event frequency, memory, CPU, and event source capacity. Monitor open connections, active operations, event throughput, errors, and cancellations to tune them.

## Reverse proxies and multi-instance deployments

When WebSocket traffic passes through a reverse proxy or load balancer, it must support HTTP Upgrade and keep the connection open after the handshake:

- Allow `Upgrade` and `Connection` headers to be forwarded.
- Use a sufficiently long idle timeout for WebSocket connections.
- Ensure proxies do not buffer or close streams based on short HTTP timeouts.
- Use TLS/WSS on public endpoints.
- Check health, connection limits, and message limits on the server.

Once the handshake succeeds, the connection is bound to the instance that accepted it. If the client reconnects, the load balancer may route it to a different instance. Therefore, event sources and shared state across instances should rely on an external broker or distributed system rather than an in-memory `Sinks` or collection inside a single process.

Sticky sessions can help with certain infrastructures, but they do not replace shared event infrastructure and do not solve subscription recovery after a lost connection.

## CORS and WebSocket Origin

HTTP CORS governs whether browsers can read responses from another origin and handles preflight requests. A WebSocket handshake includes an `Origin` header but does not use CORS preflight the way standard HTTP requests do. Therefore, configure allowed-origin checks at the WebSocket endpoint or corresponding security/proxy layer.

Only allow trusted frontend origins. Do not accept all origins when the endpoint uses cookies or user credentials. Origin validation is a defense layer against cross-site access; it does not replace authentication and authorization.

## Testing with WebSocketGraphQlTester

Spring for GraphQL provides `WebSocketGraphQlTester` to test GraphQL over WebSocket. The tester uses a `WebSocketClient` and keeps a shared connection for requests; you can call `stop()` to close the connection after the test.

Test dependency:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Create the tester:

~~~java
import java.net.URI;

import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI url = URI.create("ws://localhost:8080/graphql");
WebSocketClient client = new ReactorNettyWebSocketClient();

WebSocketGraphQlTester tester =
        WebSocketGraphQlTester.builder(url, client).build();
~~~

Execute a subscription:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<OrderEvent> events = tester.document("""
        subscription WatchOrder($id: ID!) {
            orderChanged(orderId: $id) {
                id
                orderId
                status
                updatedAt
            }
        }
        """)
        .variable("id", "order-100")
        .executeSubscription()
        .toFlux("orderChanged", OrderEvent.class);

StepVerifier.create(events.take(2))
        .expectNextMatches(event ->
                event.orderId().equals("order-100"))
        .expectNextMatches(event ->
                event.orderId().equals("order-100"))
        .verifyComplete();

tester.stop();
~~~

`executeSubscription()` returns a response stream. `toFlux()` extracts data from a path in each payload so `StepVerifier` can assert on events. When using `take(2)`, the test `Flux` cancels the subscription after two elements; the transport sends a `complete` message so the server cancels the corresponding operation.

What to test:

- Client and server negotiate the correct subprotocol.
- `connection_init` is processed and `connection_ack` is received.
- Subscription receives multiple payloads matching the operation ID.
- Two subscriptions on the same connection do not mix data.
- Client cancels one operation while another remains active.
- Closing the connection cancels active publishers.
- Invalid credentials are rejected.
- Connection-init timeout, keep-alive, and reconnect are handled properly.
- Operation count and message size limits are enforced.
- Proxies or production environments do not close connections prematurely.

## Common errors

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| HTTP GraphQL works, but WebSocket fails to connect | WebSocket endpoint is not enabled | Configure `spring.graphql.websocket.path` |
| Servlet app lacks a WebSocket handler | Missing WebSocket starter | Add `spring-boot-starter-websocket` |
| Client does not receive `connection_ack` | Missing `connection_init`, wrong protocol, or auth failure | Check subprotocol, payload, and init timeout |
| Server ignores operations | Client uses an older protocol | Use `graphql-transport-ws` |
| Multiple subscriptions mix results | Client reuses IDs or multiplex handling is wrong | Use unique IDs and route messages by ID |
| Unsubscribed, yet publisher keeps running | Cancellation does not propagate to the source | Check cancellation callbacks and cleanup |
| Connection closes while idle | Proxy timeout or keep-alive misconfigured | Configure ping/pong and proxy timeouts |
| WebSocket works locally, but fails behind a proxy | `Upgrade` not forwarded or `Origin` blocked | Check proxy headers and allowed origins |
| User receives unauthorized data | Only authenticated at handshake, not per operation | Enforce resource-level authorization |
| Server runs out of memory | Too many connections, subscriptions, or message buffers | Set limits and monitor metrics |
| Reconnect loses events | New connection does not auto-resume old subscriptions | Design cursors/replay and resubscribe |

## Design principles for WebSocket transport

When implementing WebSocket transport for Spring for GraphQL, keep these in mind:

1. **Enable the endpoint explicitly.** Configure `spring.graphql.websocket.path`; choose the starter matching MVC or WebFlux.
2. **Use the right protocol.** Both client and server must support `graphql-transport-ws`, not the legacy `subscriptions-transport-ws` protocol.
3. **Wait for connection acknowledgement.** Send `connection_init` and wait for `connection_ack` before subscribing.
4. **Multiplex with distinct operation IDs.** One connection can carry many operations, but each ID must be unique.
5. **Separate connection lifecycle from operation lifecycle.** `WebSocketGraphQlInterceptor` handles connection events; `WebGraphQlInterceptor` handles each GraphQL request.
6. **Authenticate and authorize at the right scope.** Check handshake or connection payload, then still check permissions per operation and resource.
7. **Configure keep-alive and timeouts.** Align server, client, reverse proxy, and load balancer settings.
8. **Limit resources.** Control connections, concurrent subscriptions, message buffers, and payload sizes.
9. **Design reconnects with cursors.** A new connection does not automatically resume previous operations.
10. **Test with WebSocketGraphQlTester.** Verify protocol, multiplexing, cancellation, and cleanup over the real transport.

WebSocket transport provides a bidirectional connection and multiplexes multiple GraphQL operations in a single session. Spring for GraphQL uses the `graphql-transport-ws` GraphQL over WebSocket Protocol, supporting `connection_init`, `subscribe`, `next`, `complete`, and connection-management messages. When properly configured with endpoints, authentication, interceptors, keep-alive, resource limits, and tested for reconnects/cancellations, applications can run Subscriptions reliably over WebSocket.

## References

- [Spring Boot - Spring for GraphQL: WebSocket endpoint and starter](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL - Server Transports: WebSocket and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - Testing: WebSocketGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws)
