# Client interceptor

In Spring for GraphQL, `GraphQlClientInterceptor` is the client-side extension point for observing and intercepting the process of sending GraphQL requests, receiving responses, and consuming subscription streams. It is useful when an application needs shared behaviors such as logging, timing, attaching internal correlation IDs, error tracking, or performing additional processing around requests.

An interceptor participates in the `GraphQlClient` execution chain. It receives a `ClientGraphQlRequest`, forwards the request via `chain.next(request)`, and can then observe the response or error. For subscriptions, the interceptor works with a `Flux` and can track individual events as well as stream termination signals.

Distinguish shared GraphQL interceptors from transport-specific configuration. HTTP headers are configured via `HttpGraphQlClient` or `WebClient`; the WebSocket `connection_init` payload is created via `WebSocketGraphQlClientInterceptor`. `GraphQlClientInterceptor` is not the place to arbitrarily modify HTTP headers or WebSocket handshakes.

## 1. Where does the interceptor sit in GraphQlClient?

Spring for GraphQL provides a shared client workflow across multiple transports:

- `HttpGraphQlClient` sends queries and mutations over HTTP under a non-blocking contract.
- `HttpSyncGraphQlClient` sends HTTP requests under a blocking contract.
- `WebSocketGraphQlClient` uses a WebSocket connection to execute requests and subscriptions.
- `RSocketGraphQlClient` sends requests over an RSocket session.

These clients have their own builders, yet all support configuring interception tailored to their execution model. Thus, a non-blocking `GraphQlClientInterceptor` can be reused across non-blocking transports without rewriting timing or logging logic for each protocol.

~~~mermaid
flowchart TD
    A[Application calls GraphQlClient] --> B[GraphQL RequestSpec]
    B --> C[Client interceptor 1]
    C --> D[Client interceptor 2]
    D --> E[Transport: HTTP / WebSocket / RSocket]
    E --> F[GraphQL server]
    F --> G[ClientGraphQlResponse]
    G --> D
    D --> C
    C --> H[Application reads response]
~~~

An interceptor is part of the client-side chain. It does not run on the server and does not replace `WebGraphQlInterceptor`, which processes requests on the server side.

## 2. Two interceptor types by execution model

Spring for GraphQL has two main interfaces:

| Interface | Execution model | Used with |
| --- | --- | --- |
| `GraphQlClientInterceptor` | Non-blocking, Reactor | `HttpGraphQlClient`, `WebSocketGraphQlClient`, `RSocketGraphQlClient` |
| `SyncGraphQlClientInterceptor` | Blocking | `HttpSyncGraphQlClient` |

`GraphQlClientInterceptor` has two methods:

- `intercept(ClientGraphQlRequest, Chain)` handles single requests, typically queries or mutations, and returns `Mono<ClientGraphQlResponse>`.
- `interceptSubscription(ClientGraphQlRequest, SubscriptionChain)` handles subscriptions and returns `Flux<ClientGraphQlResponse>`.

Both methods have default implementations that simply forward the request. You can override whichever method you need; if you want to apply the same logic to both queries/mutations and subscriptions, override both.

`SyncGraphQlClientInterceptor` has only one synchronous `intercept` method, taking the request and returning the response directly. Do not use `GraphQlClientInterceptor` for a blocking client or call `block()` inside a non-blocking interceptor.

## 3. Structure of a non-blocking interceptor

Example interceptor logging the operation name and execution duration:

~~~java
package com.example.graphql.client;

import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ClientMetricsInterceptor implements GraphQlClientInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(ClientMetricsInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();
        String operationName = request.getOperationName();

        return chain.next(request)
            .doOnNext(response -> {
                long elapsedNanos = System.nanoTime() - startedAt;
                log.debug(
                    "GraphQL operation={} valid={} elapsedNanos={}",
                    operationName,
                    response.isValid(),
                    elapsedNanos
                );
            })
            .doOnError(error ->
                log.warn("GraphQL operation={} failed", operationName, error)
            );
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return Flux.defer(() -> {
            long startedAt = System.nanoTime();
            String operationName = request.getOperationName();

            return chain.next(request)
                .doOnNext(response ->
                    log.debug(
                        "GraphQL subscription operation={} valid={}",
                        operationName,
                        response.isValid()
                    )
                )
                .doOnError(error ->
                    log.warn(
                        "GraphQL subscription operation={} failed",
                        operationName,
                        error
                    )
                )
                .doFinally(signalType -> {
                    long elapsedNanos = System.nanoTime() - startedAt;
                    log.debug(
                        "GraphQL subscription operation={} terminated={} elapsedNanos={}",
                        operationName,
                        signalType,
                        elapsedNanos
                    );
                });
        });
    }
}
~~~

`chain.next(request)` forwards the request to subsequent interceptors and then to the transport. The response flows back through the reactive chain, so you can use `doOnNext` to record metrics and `doOnError` to observe transport errors or errors thrown within the chain.

For subscriptions, `chain.next(request)` returns a `Flux`. `doOnNext` may run multiple times, once per GraphQL response event. `doFinally` receives the termination signal such as complete, error, or cancel. Wrap timer initialization inside `Flux.defer` so each subscription gets its own start timestamp.

Do not call `subscribe()` or `block()` inside an interceptor. Return the publisher so the caller controls subscription, backpressure, and cancellation.

## 4. Registering interceptors on the builder

Example using `HttpGraphQlClient`:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com/graphql")
    .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
    .interceptor(new ClientMetricsInterceptor())
    .build();
~~~

Every request sent through the `graphQlClient` instance passes through the registered interceptor.

Multiple interceptors can be registered on the builder. Separate responsibilities by concern, such as one interceptor for metrics, one for audit metadata, and one for error normalization. Keep each interceptor small so their ordering and effects are easy to verify.

If you need to customize the entire list, the builder provides the `interceptors(...)` API. When multiple interceptors mutate or observe the same request, define the intended order and write tests for the chain instead of relying on assumptions about ordering.

## 5. Forwarding requests and short-circuiting

In the normal case, an interceptor should invoke `chain.next(request)` exactly once and then process the result:

~~~java
@Override
public Mono<ClientGraphQlResponse> intercept(
        ClientGraphQlRequest request,
        Chain chain) {

    return chain.next(request)
        .doOnNext(response -> log.debug("Response received"));
}
~~~

You may omit calling the chain if an interceptor deliberately short-circuits the request and constructs an alternative response, though this is specialized behavior. Skipping the chain without returning an appropriate result prevents the request from reaching the server.

Do not call `chain.next(request)` twice to "retry" a request. For mutations, resending could execute side effects twice. Retries must be designed explicitly based on error category, operation idempotency, and server contract.

Interceptors should also not silently swallow exceptions and return fake responses. Unless an intentional fallback exists, let errors propagate to the caller.

## 6. Reading information from ClientGraphQlRequest

`ClientGraphQlRequest` provides details about the GraphQL request:

- `getDocument()`: the GraphQL document.
- `getOperationName()`: the operation name if present.
- `getVariables()`: the variables map.
- `getExtensions()`: protocol extensions.
- `getAttributes()`: attributes used strictly internally within the client-side interceptor chain.

You can use the operation name and attributes to attach metrics or traces without re-parsing the entire GraphQL document.

Example attaching a correlation ID where the request is built:

~~~java
Mono<BookView> result = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .attribute("correlationId", correlationId)
    .retrieve("book")
    .toEntity(BookView.class);
~~~

Interceptor reading the attribute:

~~~java
Object correlationId = request.getAttributes().get("correlationId");
~~~

Request attributes exist only inside the client process and can be read by interceptors. They are not automatically serialized or sent to the GraphQL server. If data needs to be sent over the wire, use GraphQL variables, protocol extensions, or appropriate transport metadata.

Do not place access tokens, passwords, or secret data into attributes if an interceptor might log all attributes. Explicitly pick only safe fields for observation.

## 7. Distinguishing attributes, extensions, and variables

These three concepts serve different purposes:

| Component | Where used | Sent to server? | Example |
| --- | --- | --- | --- |
| Variables | Inputs of the GraphQL operation | Yes | `id`, `filter`, `page` |
| Extensions | Extended metadata of the GraphQL protocol | Yes, per transport/protocol | tracing metadata or persisted query metadata if supported by both sides |
| Client attributes | Internal processing inside the client interceptor chain | No | internal correlation ID, metric tags, local audit details |

Protocol extension example:

~~~java
graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .extension("clientMetadata", Map.of("source", "catalog-ui"))
    .retrieve("books")
    .toEntityList(BookView.class);
~~~

The server uses extensions only if corresponding support logic exists. Do not use extensions to replace arguments or variables that the schema needs to validate and type-check.

## 8. Observing GraphQL errors in the response

A GraphQL response can contain both data and errors. This differs from transport errors, where the publisher may terminate with an exception.

An interceptor can observe the response before the caller uses `retrieve`:

~~~java
@Override
public Mono<ClientGraphQlResponse> intercept(
        ClientGraphQlRequest request,
        Chain chain) {

    return chain.next(request)
        .doOnNext(response -> {
            if (!response.isValid()) {
                log.warn(
                    "GraphQL response contains errors; operation={}, errors={}",
                    request.getOperationName(),
                    response.getErrors().size()
                );
            }
        });
}
~~~

`response.isValid()` and `response.getErrors()` allow detecting whether a GraphQL response has errors. GraphQL can return partial data alongside errors; do not assume every response containing errors lacks usable data.

If the caller needs fine-grained control, use `execute()` and read `ClientGraphQlResponse`. `retrieve(path)` is a shortcut to decode one field path; it may raise `FieldAccessException` when the field has no value or has associated errors. Type decoding errors may be represented by `GraphQlClientException`.

Do not automatically turn every GraphQL error into a reactive exception inside an interceptor if the application needs to support partial data. Leave the error policy to the client service or caller based on each use case.

## 9. Handling transport errors and retries

Distinguish clearly:

- GraphQL errors are errors returned in the response per the GraphQL protocol.
- Connection errors, timeouts, or codec failures may be propagated as `GraphQlTransportException` or transport-specific exceptions.
- Field decoding errors may surface later when the caller uses `retrieve`.

An interceptor can log errors flowing through the chain:

~~~java
return chain.next(request)
    .doOnError(error ->
        log.warn(
            "GraphQL transport failed for operation={}",
            request.getOperationName(),
            error
        )
    );
~~~

Retries can be placed in an interceptor or at the caller, but you must evaluate whether the operation is safe to resend. Queries typically produce no side effects, whereas mutations may already have been processed by the server before the connection dropped. If retrying mutations, you need an idempotency key or a mechanism to verify command status.

Do not retry GraphQL validation, authorization, or business errors as if they were network failures. Unconditional retries create duplicate load and complicate diagnostics.

## 10. Handling subscriptions with interceptSubscription

`interceptSubscription` is the dedicated extension point for requests returning multiple responses. A subscription can emit hundreds of events and stay open long-term, so the interceptor should preserve the reactive stream.

Example counting events and logging termination timing:

~~~java
@Override
public Flux<ClientGraphQlResponse> interceptSubscription(
        ClientGraphQlRequest request,
        SubscriptionChain chain) {

    return Flux.defer(() -> {
        AtomicLong eventCount = new AtomicLong();

        return chain.next(request)
            .doOnNext(response -> eventCount.incrementAndGet())
            .doFinally(signalType ->
                log.info(
                    "Subscription operation={} events={} signal={}",
                    request.getOperationName(),
                    eventCount.get(),
                    signalType
                )
            );
    });
}
~~~

`doFinally` is invoked when the stream completes, errors, or is cancelled. When the client cancels the subscription, cancellation must continue propagating through the chain to the transport. Avoid calling `collectList()` to await the entire stream because a subscription may never complete naturally.

If an interceptor needs to buffer or transform events, set memory bounds and ensure backpressure is not broken. For logging/metrics, side-effect operators are usually better suited than retaining full responses.

## 11. WebSocketGraphQlClientInterceptor

WebSocket has additional connection-management messages beyond GraphQL operations, such as `connection_init` and `connection_ack`. When you need to hook into these messages, use `WebSocketGraphQlClientInterceptor`.

This interface extends `GraphQlClientInterceptor` and adds two callbacks:

- `connectionInitPayload()` produces the payload sent in the `connection_init` message.
- `handleConnectionAck(payload)` handles the `connection_ack` payload received from the server.

Example sending a bearer token in the initialization payload:

~~~java
package com.example.graphql.client;

import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import reactor.core.publisher.Mono;

public class WebSocketAuthInterceptor
        implements WebSocketGraphQlClientInterceptor {

    private final TokenProvider tokenProvider;

    public WebSocketAuthInterceptor(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return tokenProvider.currentAccessToken()
            .<Object>map(token -> Map.of(
                "Authorization",
                "Bearer " + token
            ));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }
}
~~~

`TokenProvider` is an application abstraction returning a `Mono<String>` containing the current access token. The server must have a matching mechanism to authenticate the `connection_init` payload, such as Spring for GraphQL's WebSocket authentication interceptor.

Registering the interceptor:

~~~java
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

WebSocketGraphQlClient graphQlClient =
    WebSocketGraphQlClient.builder(
            "wss://catalog.example.com/graphql",
            new ReactorNettyWebSocketClient()
        )
        .interceptor(new WebSocketAuthInterceptor(tokenProvider))
        .interceptor(new ClientMetricsInterceptor())
        .build();
~~~

At most one `WebSocketGraphQlClientInterceptor` can exist in the chain. Additional standard `GraphQlClientInterceptor` instances can still be registered to observe individual GraphQL requests and subscriptions.

The WebSocket client keeps a shared connection across multiple operations. The initialization payload is bound to the connection; if a token changes, updating the token in the provider does not automatically update the identity of an already-open connection. The application must close/reconnect the connection according to its credential policy.

## 12. Configuring HTTP headers is not part of GraphQlClientInterceptor

A common mistake is trying to add HTTP headers inside `GraphQlClientInterceptor`. This interface receives the GraphQL request abstraction and provides no API to mutate HTTP transport headers.

With `HttpGraphQlClient`, configure headers via the builder:

~~~java
HttpGraphQlClient graphQlClient =
    HttpGraphQlClient.builder(webClient)
        .headers(headers ->
            headers.setBearerAuth(accessToken)
        )
        .interceptor(new ClientMetricsInterceptor())
        .build();
~~~

If the token changes per request, configuring a static header when building the client may be inappropriate. In that case, use a `WebClient` filter or a transport-layer credential provider mechanism to fetch the token for each HTTP call.

With `WebSocketGraphQlClient`, handshake headers and the `connection_init` payload are two distinct mechanisms. In browsers, the JavaScript WebSocket API does not allow setting arbitrary Authorization headers; the `connection_init` payload is commonly used to send credentials under the GraphQL over WebSocket protocol.

With RSocket, credentials are configured via RSocket setup/metadata or RSocket security mechanisms. A shared GraphQL interceptor can still observe requests/responses, but it does not replace transport metadata configuration.

## 13. Interceptors for blocking HttpSyncGraphQlClient

If the application uses the blocking client, implement `SyncGraphQlClientInterceptor`:

~~~java
package com.example.graphql.client;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.SyncGraphQlClientInterceptor;

public class SyncAuditInterceptor implements SyncGraphQlClientInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SyncAuditInterceptor.class);

    @Override
    public ClientGraphQlResponse intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();

        try {
            ClientGraphQlResponse response = chain.next(request);

            log.debug(
                "GraphQL operation={} valid={} elapsedNanos={}",
                request.getOperationName(),
                response.isValid(),
                System.nanoTime() - startedAt
            );

            return response;
        } catch (RuntimeException exception) {
            log.warn(
                "GraphQL operation={} failed",
                request.getOperationName(),
                exception
            );
            throw exception;
        }
    }
}
~~~

Register with `HttpSyncGraphQlClient`:

~~~java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com/graphql")
    .build();

HttpSyncGraphQlClient graphQlClient =
    HttpSyncGraphQlClient.builder(restClient)
        .interceptor(new SyncAuditInterceptor())
        .build();
~~~

A blocking interceptor calls `chain.next(request)` and receives the response synchronously. Do not return `Mono` or `Flux` in this interface. If the application uses non-blocking `HttpGraphQlClient`, use `GraphQlClientInterceptor`.

## 14. Distinguishing client interceptors and server interceptors

Their names look similar, yet they run on opposite sides:

| Component | Where it runs | Purpose |
| --- | --- | --- |
| `GraphQlClientInterceptor` | Application calling GraphQL | Observe requests/responses from the client perspective |
| `SyncGraphQlClientInterceptor` | Blocking GraphQL client | Synchronous interception for blocking clients |
| `WebSocketGraphQlClientInterceptor` | WebSocket client | Adds connection initialization and acknowledgement callbacks |
| `WebGraphQlInterceptor` | GraphQL server over HTTP/WebSocket | Inspect transport requests, customize ExecutionInput/ExecutionResult |
| `WebSocketGraphQlInterceptor` | GraphQL server over WebSocket | Handle server-side connection lifecycle and cancellation |
| `RSocketQlInterceptor` | GraphQL server over RSocket | Server-side RSocket request/response interception |

For example, a client interceptor can log the operation name before sending a request and the duration when receiving the response. A server interceptor can read HTTP headers, place the principal into the GraphQL context, or add response headers. Using the right extension point avoids accidentally depending on information unavailable on that side.

## 15. Security and sensitive data in interceptors

Interceptors are typically shared across many requests, so handle logs and state carefully:

- Do not log full GraphQL variables if they contain passwords, tokens, personal data, or sensitive information.
- Do not log bearer tokens, cookies, or authentication payload contents.
- Log only the operation name, correlation ID, duration, response status, and error count if sufficient for monitoring.
- Do not store a single user's request data in a mutable field of a singleton interceptor.
- Do not share per-user tokens via a shared client instance if tokens vary by caller.
- Do not treat request attributes as data sent to the server; attributes are strictly client-scoped.

If an interceptor needs to hold per-request state, use method-local variables or the Reactor context. Avoid using an instance field like `currentRequestId` because multiple requests can run concurrently on the same client.

## 16. Testing interceptors

You can unit test an interceptor in isolation by mocking the request, response, and chain. Example with Mockito:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ClientMetricsInterceptorTest {

    @Test
    void delegatesRequestAndReturnsResponse() {
        ClientGraphQlRequest request = mock(ClientGraphQlRequest.class);
        ClientGraphQlResponse response = mock(ClientGraphQlResponse.class);
        GraphQlClientInterceptor.Chain chain =
            mock(GraphQlClientInterceptor.Chain.class);

        when(chain.next(request)).thenReturn(Mono.just(response));

        ClientMetricsInterceptor interceptor =
            new ClientMetricsInterceptor();

        StepVerifier.create(interceptor.intercept(request, chain))
            .expectNext(response)
            .verifyComplete();

        verify(chain).next(request);
    }
}
~~~

This test verifies that the interceptor forwards the request and preserves the response. For interceptors with error-classification logic, add tests for responses with errors, transport errors, and exceptions thrown from the chain.

For subscription interceptors, use a `Flux` simulating multiple responses and verify all events are forwarded. Add cancellation tests to ensure the interceptor does not retain the stream after the subscriber cancels.

Integration tests can use an HTTP mock server to verify headers configured by the transport builder, or a WebSocket test server to verify the `connection_init` payload. GraphQL interceptor tests do not replace transport tests.

## 17. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Interceptor does not run | Not registered on the builder of the active client | Check the exact client instance and builder |
| Using `GraphQlClientInterceptor` with a blocking client | Confused execution models | Use `SyncGraphQlClientInterceptor` |
| Subscriptions are not observed | Overrode `intercept` only without `interceptSubscription` | Implement both methods when needed |
| Request sent twice | Calling `chain.next` multiple times or unsafe mutation retry | Delegate only once; design retries around idempotency |
| HTTP Authorization header missing | Attempted to add header inside `GraphQlClientInterceptor` | Configure the `WebClient`/`HttpGraphQlClient` builder |
| WebSocket connection missing token | Configured HTTP header only while server reads `connection_init` payload | Use `WebSocketGraphQlClientInterceptor` or matching handshake auth |
| WebSocket auth interceptor conflict | Registered multiple `WebSocketGraphQlClientInterceptor` instances | Register at most one interceptor of this type |
| Correlation ID does not reach server | Used `RequestSpec` attribute assuming it gets serialized | Use protocol extension, variable, or transport metadata |
| GraphQL errors treated as connection errors | Failing to distinguish response errors from transport exceptions | Inspect `ClientGraphQlResponse` before decoding |
| Subscription does not terminate | Buffering the whole stream or blocking cancellation | Preserve `Flux`, backpressure, and cancellation propagation |
| Logs leak data | Writing full variables or headers | Log only allowlisted metadata |

## 18. Pre-deployment checklist

- Is the client using a blocking or non-blocking execution model?
- Was the right `SyncGraphQlClientInterceptor` or `GraphQlClientInterceptor` chosen?
- For non-blocking clients, are both single requests and subscriptions handled where needed?
- Does the interceptor call `chain.next(request)` properly and preserve the reactive flow?
- Are interceptors registered on the right builder/client instance?
- Are request attributes properly understood as client-internal data?
- Are HTTP headers, WebSocket connection init, and RSocket metadata configured at their respective transports?
- Are GraphQL errors distinguished from transport/decoding exceptions?
- Do mutation retries have idempotency or safety guarantees?
- Do subscriptions preserve backpressure and propagate cancellation?
- Is there no shared mutable state mixing concurrent requests?
- Are logs free of tokens, cookies, sensitive variables, and sensitive data?
- Have unit tests and integration tests verified the chain, transport, and cancellation?

`GraphQlClientInterceptor` is the extension point for standardizing request and response handling on the client side. Use `GraphQlClientInterceptor` for non-blocking clients, `SyncGraphQlClientInterceptor` for blocking clients, and `WebSocketGraphQlClientInterceptor` when connection initialization/acknowledgement handling is required. Preserving the reactive chain, distinguishing GraphQL errors from transport failures, and configuring headers/metadata at the right transport layer gives the client consistent logging, tracing, authentication, and error handling without cluttering GraphQL call sites.

## References

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientInterceptor.html)
- [SyncGraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SyncGraphQlClientInterceptor.html)
- [WebSocketGraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClientInterceptor.html)
- [ClientGraphQlRequest API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlRequest.html)
