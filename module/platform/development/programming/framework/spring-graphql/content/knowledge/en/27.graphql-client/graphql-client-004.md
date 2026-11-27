# RSocketGraphQlClient in Spring for GraphQL

`RSocketGraphQlClient` is Spring for GraphQL's client that uses RSocket to send GraphQL operations to a server. It implements the common `GraphQlClient` contract, so building queries, passing variables, reading responses, and handling subscriptions are almost identical to the HTTP or WebSocket clients. The difference lies in how the RSocket connection, route, metadata, and session lifecycle are configured.

RSocket is a connection-oriented transport that supports multiplexing. A single `RSocketGraphQlClient` maintains a shared session across multiple requests; the session is established automatically when the first request is sent or can be started explicitly via `start()`. When the connection is lost, the client attempts to re-establish it on the next request or when `start()` is called again. Therefore, applications should usually use one client instance per GraphQL server rather than creating a new client for each query.

## 1. What is RSocketGraphQlClient?

Spring for GraphQL defines `GraphQlClient` as a unified, transport-agnostic API for executing GraphQL requests. The main implementations include:

| Client | Transport | Characteristics |
| --- | --- | --- |
| `HttpSyncGraphQlClient` | HTTP via `RestClient` | Blocking API |
| `HttpGraphQlClient` | HTTP via `WebClient` | Reactive, non-blocking |
| `WebSocketGraphQlClient` | WebSocket | Long-lived session, supports streaming |
| `RSocketGraphQlClient` | RSocket over TCP or WebSocket | Long-lived session, multiplexing, and streaming |

`RSocketGraphQlClient` uses Spring Messaging's `RSocketRequester` underneath. The client packages GraphQL requests into RSocket payloads and sends them to the route configured on the server for the GraphQL handler.

RSocket can run over TCP or WebSocket. The transports on both sides must be compatible: a TCP client must connect to a TCP RSocket server; a WebSocket client requires a WebSocket endpoint configured to accept RSocket.

## 2. When should RSocket be used?

RSocket is suitable when an application needs service-to-service or client-to-server communication over a long-lived session, especially when there are many concurrent requests or streaming is required.

Common scenarios:

- A backend service calling another GraphQL service with many operations over a single connection.
- An application needing subscriptions to receive continuously changing data.
- An internal system already using RSocket for request-response or request-stream.
- Wanting to use the same `GraphQlClient` API while choosing the RSocket transport.
- Needing to multiplex multiple GraphQL requests over one session.

RSocket does not automatically make GraphQL queries faster. Performance depends on payload size, network latency, the server, the database, how requests are multiplexed, and concurrency. If the application only needs simple GraphQL calls over HTTP without requiring sessions or streaming, `HttpGraphQlClient` may be a better fit.

## 3. Adding dependencies and configuring the RSocket server

With Spring Boot, the server application needs the GraphQL starter and RSocket starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
}
~~~

The RSocket starter provides TCP or WebSocket transport. Example server configuration using TCP port `7000` and route `graphql`:

~~~yaml
spring:
  rsocket:
    server:
      port: 7000
  graphql:
    rsocket:
      mapping: graphql
~~~

`spring.graphql.rsocket.mapping` specifies the route where the GraphQL handler listens. The client must also send to this exact route. When the RSocket server and GraphQL mapping are configured, Spring Boot registers the GraphQL handler on the RSocket transport.

Schemas and annotated controllers are still configured just like other transports. Example:

~~~graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument("id") String id) {
        return productService.findById(id);
    }
}
~~~

The RSocket transport only changes how requests travel to the server. Schemas, resolvers, DataLoaders, validation, and exception handling still work according to the standard Spring for GraphQL mechanisms.

## 4. Creating a client over TCP

Creating directly via the builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.RSocketGraphQlClient;

@Configuration(proxyBeanMethods = false)
public class ProductClientConfiguration {

    @Bean
    public RSocketGraphQlClient productGraphQlClient() {
        return RSocketGraphQlClient.builder()
                .tcp("localhost", 7000)
                .route("graphql")
                .build();
    }
}
~~~

Key steps:

1. `RSocketGraphQlClient.builder()` creates a new builder based on an `RSocketRequester.Builder` customized for GraphQL.
2. `tcp(host, port)` selects the TCP transport and the RSocket server address.
3. `route("graphql")` sets the route metadata so the server routes requests to the GraphQL handler.
4. `build()` creates the client instance.

By default, the builder sets the data MIME type to `application/graphql+json` and registers the necessary JSON codecs. You typically do not need to configure the MIME type manually if the server uses Spring for GraphQL's default configuration.

## 5. Connecting over the WebSocket transport

If the server exposes RSocket over WebSocket, the client can configure the URI:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.RSocketGraphQlClient;

@Configuration(proxyBeanMethods = false)
public class ProductClientConfiguration {

    @Bean
    public RSocketGraphQlClient productGraphQlClient() {
        return RSocketGraphQlClient.builder()
                .webSocket(URI.create("ws://localhost:8080/rsocket"))
                .route("graphql")
                .build();
    }
}
~~~

In production environments with TLS, use a `wss://...` URI and configure the appropriate certificates/SSL on the transport. The `/rsocket` path in the example is the RSocket server's WebSocket mapping; it is distinct from the GraphQL route `graphql` sent in RSocket metadata.

You can create the transport explicitly and pass it to the builder:

~~~java
import java.net.URI;

import io.rsocket.transport.netty.client.WebsocketClientTransport;
import org.springframework.graphql.client.RSocketGraphQlClient;

URI uri = URI.create("ws://localhost:8080/rsocket");
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .clientTransport(WebsocketClientTransport.create(uri))
        .route("graphql")
        .build();
~~~

`clientTransport(...)` is useful when you need to supply a custom-configured `ClientTransport`. If you only need standard TCP or WebSocket, `tcp(...)` and `webSocket(...)` are more concise.

## 6. Using Spring Boot auto-configured RSocketGraphQlClient

When an application has Spring Boot RSocket and GraphQL auto-configuration enabled, Boot provides an `RSocketGraphQlClient.Builder<?>` bean. You can inject the builder into a component and create the client:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.stereotype.Component;

@Component
public class ProductGraphQlGateway {

    private final RSocketGraphQlClient client;

    public ProductGraphQlGateway(RSocketGraphQlClient.Builder<?> builder) {
        this.client = builder
                .tcp("catalog.internal", 7000)
                .route("graphql")
                .build();
    }
}
~~~

The auto-configured builder lets the application reuse Spring Boot's shared configuration. The client instance should be created once and retained for subsequent requests.

If you need multiple GraphQL servers, create a separate client for each server. Do not take a builder already configured with a route/transport for server A and assume it will automatically switch to server B without calling `mutate()` or creating another builder.

## 7. Sending queries and reading results

After creating the client, sending requests works just like other `GraphQlClient` implementations:

~~~java
import reactor.core.publisher.Mono;

public Mono<Product> findProduct(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class);
}
~~~

`document(...)` accepts the GraphQL operation. `variable(...)` passes a value for a variable in the operation. `retrieve("product")` selects the path relative to `data` in the response, and `toEntity(Product.class)` converts the value into a Java object.

Multiple variables can be used:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<Product>> searchProducts(String keyword, int first) {
    return client.document("""
            query SearchProducts($keyword: String!, $first: Int!) {
                searchProducts(keyword: $keyword, first: $first) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("keyword", keyword)
            .variable("first", first)
            .retrieve("searchProducts")
            .toEntityList(Product.class);
}
~~~

These methods do not block. They return `Mono<T>` or `Flux<T>`; the caller decides how to compose and subscribe according to the application's reactive model.

## 8. Using execute when the full GraphQL response is needed

`retrieve(...)` is a shortcut to fetch a single field by path. When you need to inspect `data`, `errors`, or multiple fields in the response, use `execute()`:

~~~java
import org.springframework.graphql.client.ClientGraphQlResponse;
import reactor.core.publisher.Mono;

public Mono<ClientGraphQlResponse> executeProductQuery(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("id", id)
            .execute();
}
~~~

The caller can inspect the response:

~~~java
return executeProductQuery(id)
        .map(response -> {
            if (!response.isValid()) {
                // Request-level failure: the response may contain only errors.
                throw new IllegalStateException("GraphQL request was rejected");
            }

            var productField = response.field("product");
            if (productField.getValue() == null && !productField.getErrors().isEmpty()) {
                // The field failed during execution.
                throw new IllegalStateException("Product field could not be resolved");
            }

            return productField.toEntity(Product.class);
        });
~~~

In real applications, retain GraphQL errors or translate them into domain exceptions with appropriate context rather than throwing a generic `IllegalStateException`. `execute()` is useful when distinguishing request failures, field-level errors, and valid null values.

## 9. Understanding FieldAccessException

When using `retrieve(path)`, Spring for GraphQL needs to read the field at the selected path. Decoding may raise `FieldAccessException` if the field does not exist or has a null value accompanied by a GraphQL error.

~~~java
import org.springframework.graphql.client.FieldAccessException;
import reactor.core.publisher.Mono;

public Mono<Product> findProductOrFallback(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) { id name price }
            }
            """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class)
            .onErrorResume(FieldAccessException.class, exception -> {
                var response = exception.getResponse();
                var field = exception.getField();
                // Inspect response errors and decide on a domain fallback.
                return Mono.empty();
            });
}
~~~

`FieldAccessException` provides the failing response and field so the caller can inspect GraphQL errors, path, and value. If the field exists but cannot be decoded into the requested Java type, the client may raise `GraphQlClientException` instead of `FieldAccessException`.

Do not catch `FieldAccessException` and blindly return `Mono.empty()` for every case. A valid null field, a field whose resolver errored, and a response missing the field are distinct situations; inspect the errors and business policy before choosing a fallback.

## 10. Using GraphQL documents from files

You do not have to write operations as strings in Java. You can store documents in `src/main/resources/graphql-documents/`:

~~~graphql
query ProductById($id: ID!) {
    product(id: $id) {
        id
        name
        price
    }
}
~~~

Example file `src/main/resources/graphql-documents/productById.graphql`:

~~~java
public Mono<Product> findProduct(String id) {
    return client.documentName("productById")
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class);
}
~~~

`documentName("productById")` locates `productById.graphql` in the default classpath document source. This separates operations from Java code, making syntax highlighting, GraphQL IDE plugins, and isolated query review easier.

## 11. RSocketGraphQlClient subscription support

RSocket supports streaming, so `RSocketGraphQlClient` can execute GraphQL subscriptions. Schema example:

~~~graphql
type Subscription {
    stockPrice(symbol: String!): StockPrice!
}

type StockPrice {
    symbol: String!
    price: Float!
    updatedAt: String!
}
~~~

Client opening a subscription:

~~~java
import reactor.core.publisher.Flux;

public Flux<StockPrice> stockPrices(String symbol) {
    return client.document("""
            subscription StockPriceUpdates($symbol: String!) {
                stockPrice(symbol: $symbol) {
                    symbol
                    price
                    updatedAt
                }
            }
            """)
            .variable("symbol", symbol)
            .retrieveSubscription("stockPrice")
            .toEntity(StockPrice.class);
}
~~~

`retrieveSubscription(...)` returns `Flux<T>` because the server can emit multiple results over time. If you need to inspect errors and metadata for each event, use `executeSubscription()` to process `ClientGraphQlResponse` instead of decoding only one field.

When the client cancels the subscription by cancelling the `Flux`, the transport sends the corresponding completion/cancellation signal to the server. Operators such as `take(n)`, `timeout(...)`, or cancelling the `Subscription` can terminate the stream.

## 12. Session lifecycle: start, stop, and reconnect

Unlike `HttpGraphQlClient`, the RSocket client needs to establish a session. There are two approaches:

**Automatic connection:** create the client and send a request. The session is opened when the first request needs a connection.

~~~java
Mono<Product> product = client.document("{ product(id: \"p-1\") { id name price } }")
        .retrieve("product")
        .toEntity(Product.class);
~~~

**Explicit startup:** call `start()` when the application is ready or before sending requests:

~~~java
Mono<Product> warmupAndFetch = client.start()
        .then(findProduct("p-1"));
~~~

`start()` returns `Mono<Void>` that completes once the session is established. If the application needs to ensure the connection is ready before accepting traffic, include this step in lifecycle/startup orchestration and handle connection failures.

When the application stops, call `stop()` to close the session:

~~~java
client.stop().subscribe();
~~~

`stop()` cancels in-flight requests, closes the session, and rejects new requests on that client. The API documentation notes that session disposal is triggered immediately; do not treat `stop()` as a mechanism to wait for all business work to drain.

If the session is lost, `RSocketGraphQlClient` can reconnect on the next request or when `start()` is called again. That does not mean every in-flight request is safely replayed. For mutations, design idempotency and retry policies carefully to avoid writing data twice.

## 13. Using one client instance per server

The RSocket client is connection-oriented and multiplexed: one session can serve multiple concurrent GraphQL requests. Therefore, you should normally create one shared instance per server:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductGraphQlGateway {

    private final RSocketGraphQlClient client;

    public ProductGraphQlGateway(RSocketGraphQlClient.Builder<?> builder) {
        this.client = builder
                .tcp("catalog.internal", 7000)
                .route("graphql")
                .build();
    }

    public Mono<Product> findById(String id) {
        return client.document("""
                query Product($id: ID!) {
                    product(id: $id) { id name price }
                }
                """)
                .variable("id", id)
                .retrieve("product")
                .toEntity(Product.class);
    }
}
~~~

Do not create a new client inside every `findById` method call. Each instance creates its own session, causing the application to open unnecessary connections and lose the benefits of multiplexing.

If you need a client with a different configuration from an existing one, use `mutate()` to create an independent builder and build a new client. Note that the new client is a distinct instance and will establish its own session.

## 14. Configuring route, MIME type, and RSocketRequester

`RSocketGraphQlClient.Builder` provides important options:

| Method | Purpose |
| --- | --- |
| `tcp(host, port)` | Selects the TCP transport |
| `webSocket(uri)` | Selects the WebSocket transport |
| `clientTransport(transport)` | Uses a pre-configured `ClientTransport` |
| `route(route)` | Sets route metadata for the GraphQL handler |
| `dataMimeType(mimeType)` | Changes the data payload MIME type |
| `rsocketRequester(consumer)` | Customizes the underlying `RSocketRequester.Builder` |
| `build()` | Builds the `RSocketGraphQlClient` |

The default data MIME type is `application/graphql+json`. You can change it to `application/json` if the server or integration environment requires it, but both sides must agree on the payload format.

`rsocketRequester(...)` is intended for advanced RSocket requester configuration, such as setup metadata, MIME types, codecs, or transport options. When using authentication metadata, both client and server must be configured with the same security mechanism; the GraphQL route does not replace authentication.

## 15. Authentication and transport security

RSocket is a transport; it does not determine on its own whether a user is authorized to execute a GraphQL operation. The application must configure authentication and authorization at the RSocket/Spring Security layer or using the system's appropriate security mechanism.

Several principles:

1. Use TLS when transmitting data over untrusted networks; with secure WebSocket, use `wss://`.
2. Pass credentials through RSocket authentication metadata or the configured security mechanism; do not embed tokens in GraphQL query strings.
3. Authenticate on the server before allowing operations to execute.
4. Enforce authorization in resolvers/services per resource; a long-lived session does not mean permissions never change.
5. Maintain an expiration or credential refresh policy for long-lived sessions.
6. Do not log access tokens, passwords, or sensitive metadata.

If using `rsocketRequester(...)` to configure setup metadata, align it with how the server reads metadata and the Spring Security RSocket setup in use. Do not copy an arbitrary authentication MIME type unless the server has a matching decoder registered.

## 16. GraphQlClient interceptors

`RSocketGraphQlClient` inherits the common interceptor configuration from `GraphQlClient`. With a non-blocking client, use `GraphQlClientInterceptor` to observe or transform requests/responses:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Mono;

public class LoggingGraphQlClientInterceptor implements GraphQlClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingGraphQlClientInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain
    ) {
        long started = System.nanoTime();

        return chain.next(request)
                .doOnNext(response -> {
                    long elapsed = System.nanoTime() - started;
                    log.debug("GraphQL client request completed in {} ns", elapsed);
                });
    }
}
~~~

Register the interceptor via the builder:

~~~java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .tcp("localhost", 7000)
        .route("graphql")
        .interceptor(new LoggingGraphQlClientInterceptor())
        .build();
~~~

Interceptors are suitable for tracing, metrics, or adding metadata at the client request level as supported by the API. Do not log full variables if they may contain sensitive information.

## 17. Handling transport and GraphQL errors

When using RSocket, distinguish two categories of errors:

| Error category | Example | Handling approach |
| --- | --- | --- |
| GraphQL error | Validation error, resolver exception, null field with error | Inspect `ClientGraphQlResponse`, `errors`, `path`, and `extensions` |
| RSocket transport error | Connection failed, closed session, timeout, or disconnect | Check endpoint, route, network, timeout, and retry policy |
| Decode/binding error | Response field cannot be converted to Java type | Check selection set, DTO, scalars, and codecs |
| Subscription error | Server sends a subscription error or stream terminates abnormally | Handle `SubscriptionErrorException` and transport errors in the Flux |

For subscriptions, the stream can terminate with `SubscriptionErrorException` when the server sends an error message. If the session/connection drops, the client may receive `GraphQlTransportException`. Reactor `retry` can be used where appropriate, but distinguish transient errors from business errors that should not be retried.

Do not blindly retry mutations. If the response is lost after the server has already committed a mutation, resending the request can perform the action twice. Use an idempotency key or design idempotent mutations if retries are required.

## 18. Testing RSocketGraphQlClient

Integration testing should have a test RSocket server with a GraphQL mapping, then create a client pointing to the test port/route. Verify:

1. The client connects via TCP and the exact route.
2. Queries pass variables and decode into the right DTOs.
3. Mutations return the expected response and are not unintentionally retried.
4. `execute()` allows reading GraphQL errors and partial data.
5. Subscriptions emit multiple events and stop when the Flux is cancelled.
6. The session is re-established after a server restart or closed connection.
7. `stop()` closes the session and the client rejects new requests.
8. Authentication metadata is validated by the server and authorization is enforced.

Example testing request logic at the component level (assuming the client is configured and the test server is running):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class ProductGraphQlClientTests {

    @Autowired
    ProductGraphQlGateway gateway;

    @Test
    void retrievesProductOverRSocket() {
        StepVerifier.create(gateway.findById("p-1"))
                .expectNextMatches(product ->
                        product.id().equals("p-1") && !product.name().isBlank()
                )
                .verifyComplete();
    }
}
~~~

The test above assumes the RSocket server and the `graphql` route have been started in the test context, and that fixture data contains product `p-1`. In tests that start a server manually, manage dynamic ports and shut down the server after the test to avoid port conflicts.

## 19. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot establish session | Wrong host/port, transport, or server not running | Check RSocket listener and TCP/WebSocket configuration |
| Server does not receive GraphQL request | Client route differs from `spring.graphql.rsocket.mapping` | Align routes on both sides |
| WebSocket connection fails | Wrong URI or WebSocket transport not enabled on server | Check scheme, path, and WebSocket mapping |
| Payload fails to decode | Incompatible data MIME type or codec | Use default `application/graphql+json` or align configuration on both sides |
| Every request creates a new connection | Creating `RSocketGraphQlClient` inside every method | Use one long-lived instance per server |
| First request has connection latency | Session is established lazily on first request | Call `start()` during startup if warm-up is needed |
| Subscription emits no events | Server field is not a subscription stream or transport does not support streaming | Check schema, resolver, and RSocket server |
| Stream stops after disconnect | Session lost or server closed connection | Classify transport errors and apply controlled subscription retry |
| Mutation executed twice after retry | Non-idempotent retry | Use an idempotency key or do not auto-retry mutations |
| Request rejected despite successful connection | Missing or invalid authentication/authorization metadata | Check RSocket Security and server policy |

## 20. Implementation workflow for RSocketGraphQlClient

When integrating a GraphQL client over RSocket:

1. Determine whether the server uses RSocket over TCP or WebSocket.
2. Enable the RSocket server and GraphQL route via Spring Boot or corresponding RSocket configuration.
3. Add the required GraphQL and RSocket dependencies.
4. Create `RSocketGraphQlClient` using the builder, choosing the transport and route matching the server.
5. Keep one client instance per server to share the session and multiplex requests.
6. Send queries/mutations using `document`, `variable`, `retrieve`, or `execute`.
7. Use `retrieveSubscription` or `executeSubscription` for GraphQL subscriptions.
8. Use `start()` if the connection should be ready before the first request; call `stop()` when client lifecycle management ends.
9. Configure authentication, TLS, timeouts, and retries according to system policy.
10. Test queries, GraphQL errors, transport errors, subscriptions, reconnection, and cancellation.

`RSocketGraphQlClient` provides a reactive GraphQL client over a long-lived RSocket session. When routes, transports, and client lifecycle are configured properly, the application can reuse the same session across many requests and receive subscription streams through the same `GraphQlClient` API.

## References

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — RSocketGraphQlClient API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/client/RSocketGraphQlClient.html)
- [Spring for GraphQL — RSocketGraphQlClient.Builder API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/client/RSocketGraphQlClient.Builder.html)
- [Spring Boot — Spring for GraphQL and RSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
