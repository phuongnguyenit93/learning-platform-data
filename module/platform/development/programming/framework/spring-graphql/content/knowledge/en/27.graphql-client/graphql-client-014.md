# WebSocketDisconnectedException

When an application uses Spring for GraphQL to call a server over WebSocket, the connection may close while a GraphQL request or subscription is still running. In that situation, the client can receive **WebSocketDisconnectedException**. This is a transport-layer exception indicating that the client can no longer receive results over the WebSocket for the executing operation.

This exception is in the org.springframework.graphql.client package and extends GraphQlTransportException. It carries details about the running request and the WebSocket close status. Applications can use this information for logging, error classification, and deciding whether to reconnect or re-subscribe.

This exception class has been available since Spring for GraphQL 1.0.0.

Keep in mind that WebSocketDisconnectedException does not mean a GraphQL resolver returned a business error. It indicates that the transport channel was lost while the client was waiting for results. The server may have processed part or all of the request before the connection closed, so recovery must depend on the operation type.

## When does WebSocketDisconnectedException occur?

Spring for GraphQL provides WebSocketGraphQlClient to send GraphQL requests over a shared WebSocket connection. The client can execute Queries, Mutations, and Subscriptions on the same connection. When the connection closes or drops while a request or subscription is running, Spring raises WebSocketDisconnectedException.

Common causes include:

- Server restart, deployment, or session closure.
- Reverse proxy or load balancer closing an idle connection.
- Network interruption between client and server.
- Client device switching networks, sleeping, or losing Wi-Fi.
- WebSocket server encountering an error and closing the connection.
- Firewall or NAT dropping a connection after prolonged inactivity.
- Application calling stop() while operations are still running; the client terminates in-flight requests with an error signal.

The error can happen right after sending a request or after a subscription has already received many events. In both cases, the running operation can no longer receive data over the old connection.

## Position in the exception hierarchy

WebSocketDisconnectedException belongs to the client and transport error hierarchy:

~~~text
Throwable
  └── Exception
      └── RuntimeException
          └── NestedRuntimeException
              └── GraphQlClientException
                  ├── FieldAccessException
                  └── GraphQlTransportException
                      ├── SubscriptionErrorException
                      └── WebSocketDisconnectedException
~~~

Each class has a distinct meaning:

| Exception | Meaning |
| --- | --- |
| GraphQlClientException | Base class for GraphQL client-side exceptions |
| GraphQlTransportException | Error while the transport executes a request or transport encode/decode errors |
| WebSocketDisconnectedException | WebSocket closed or lost while a request/subscription was running |
| SubscriptionErrorException | Server terminated a subscription with a GraphQL over WebSocket error message |
| FieldAccessException | Client cannot access/decode a field at the retrieve path due to field errors or null with errors |

Do not collapse these exceptions into one generic error category. Disconnection requires a reconnection policy; SubscriptionErrorException typically reflects a server-sent error for the operation; FieldAccessException requires checking the GraphQL response and field path.

## Distinguishing transport errors from GraphQL errors

A GraphQL response can contain data and errors. This is a result of GraphQL execution and does not necessarily make Mono or Flux emit an error at the Reactor layer. By contrast, WebSocketDisconnectedException is a transport error signal causing the publisher to terminate with onError.

| Scenario | How the client detects it |
| --- | --- |
| Resolver returns a business error in the GraphQL response | ClientGraphQlResponse contains errors; check isValid or field errors |
| Selected field has errors and retrieve cannot decode it | May emit FieldAccessException |
| Server sends an error message to end a subscription | SubscriptionErrorException |
| WebSocket closes while an operation is running | WebSocketDisconnectedException |
| Unable to establish connection or GraphQL session | May be GraphQlTransportException or another transport/session init exception |

For example, if the server returns the response:

~~~json
{
  "data": {
    "account": null
  },
  "errors": [
    {
      "message": "Account not found",
      "path": ["account"]
    }
  ]
}
~~~

This is a GraphQL execution error. The client received the response, so it can read errors, display an appropriate message, or handle it per business logic.

If the WebSocket drops before the response reaches the client, the client cannot be sure how far the server processed the operation. In that case, WebSocketDisconnectedException represents an indeterminate state of that transport exchange.

## Information readable from the exception

WebSocketDisconnectedException has a constructor taking three pieces of information:

- closeStatusMessage: the connection closure message received.
- request: the GraphQL request that was running when the connection closed.
- status: the CloseStatus of the WebSocket session.

Two useful methods:

| Method | Purpose |
| --- | --- |
| getCloseStatus() | Gets the CloseStatus used to close the WebSocket session |
| getRequest() | Gets the original GraphQlRequest; inherited from GraphQlClientException |

CloseStatus provides the close code and close reason. You can use this code to classify the situation, but do not conclude the root cause from a single code alone. Correlate client, server, and proxy logs along with the timing of the failure.

Logging example:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import org.springframework.web.socket.CloseStatus;

private void logDisconnect(WebSocketDisconnectedException exception) {
    CloseStatus status = exception.getCloseStatus();

    if (status != null) {
        log.warn(
                "GraphQL WebSocket disconnected: code={}, reason={}",
                status.getCode(),
                status.getReason());
    }
    else {
        log.warn("GraphQL WebSocket disconnected: {}", exception.getMessage());
    }

    if (exception.getRequest() != null) {
        log.warn("A GraphQL request was active when the connection closed");
    }
}
~~~

Never write raw access tokens, cookies, sensitive variables, or entire request bodies to logs. To correlate logs, attach a controlled correlation ID and operation name.

## Creating WebSocketGraphQlClient

WebSocketGraphQlClient uses Spring WebFlux's WebSocketClient. Example creating a client with Reactor Netty:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI url = URI.create("wss://api.example.com/graphql");
WebSocketClient transport = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, transport)
                .keepAlive(Duration.ofSeconds(25))
                .build();
~~~

WebSocketGraphQlClient is a connection-oriented client that supports multiplexing. It keeps a shared connection for multiple requests. Reuse one instance per GraphQL server in the application instead of creating a new client per request.

The connection is created automatically when the client begins executing a request. If you want to proactively verify the connection before sending operations, call start():

~~~java
graphQlClient.start()
        .timeout(Duration.ofSeconds(10))
        .block();
~~~

This block() example fits command-line programs or imperative startup flows. In a WebFlux application, do not block the event loop; compose the Mono<Void> from start() into the application's reactive lifecycle.

## How WebSocketGraphQlClient recovers connections

WebSocketGraphQlClient has two distinct behaviors to separate:

1. When the connection is lost, requests or subscriptions running on that connection terminate with an error, which may be WebSocketDisconnectedException.
2. The connection is re-established when the client receives the next request or when start() is called again.

Automatically re-establishing the connection does not mean old operations are automatically replayed. The client cannot know on its own whether a mutation committed on the server, nor can it automatically recover events emitted during the disconnection window.

Overall lifecycle:

~~~mermaid
flowchart TD
    A["GraphQlClient sends operation"] --> B["WebSocket connection is active"]
    B --> C{"Connection still open?"}
    C -->|Yes| D["Receive GraphQL response or event"]
    D --> B
    C -->|No| E["Active operation fails with error"]
    E --> F["WebSocketDisconnectedException"]
    F --> G{"New request or start() called?"}
    G -->|Yes| H["Client establishes new connection"]
    H --> I["Send new operation or re-subscribe"]
    G -->|No| J["Client waits for next request"]
~~~

A new connection is a new GraphQL session. If the server requires connection_init, the client must initialize the session and wait for connection_ack before sending new operations.

## Managing start() and stop()

WebSocketGraphQlClient provides start() and stop():

- start() connects the WebSocket, sends connection_init, and waits for connection_ack. The Mono completes when the GraphQL session is ready to accept requests.
- stop() closes the WebSocket with CloseStatus.NORMAL, terminates running requests with an error signal, and rejects new requests.
- After stop(), start() can be called to allow new requests again.

Example stopping the client when the application shuts down:

~~~java
graphQlClient.stop()
        .timeout(Duration.ofSeconds(5))
        .block();
~~~

This is also an example for imperative flows. In a reactive application, wire stop() into the shutdown process without blocking the event loop.

Do not treat the error signal emitted when the application itself calls stop() as a network failure requiring retries. The exact exception type depends on the session closure scenario. If a retry loop keeps issuing requests while the application is shutting down, the client may reconnect unintentionally and prolong application shutdown.

## Catching WebSocketDisconnectedException with Mono

Queries or Mutations returning a single response are typically executed via Mono:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Mono;

Mono<Account> accountMono = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .doOnError(WebSocketDisconnectedException.class, this::logDisconnect);
~~~

You can map the error to an application error for the caller to handle:

~~~java
Mono<Account> accountMono = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .onErrorMap(
                WebSocketDisconnectedException.class,
                exception -> new RemoteGraphQlUnavailableException(
                        "GraphQL connection was lost", exception));
~~~

Only map the exception when the application layer needs its own abstraction. If the caller needs to inspect CloseStatus or the original request, preserve WebSocketDisconnectedException as the cause or handle it directly.

## Catching errors in a Subscription Flux

Subscriptions return a Flux. If the WebSocket drops while a subscription is running, the Flux can terminate with WebSocketDisconnectedException:

~~~java
import reactor.core.publisher.Flux;

Flux<PriceUpdate> updates = graphQlClient.document("""
        subscription PriceUpdates($symbol: String!) {
            priceUpdates(symbol: $symbol) {
                eventId
                symbol
                price
            }
        }
        """)
        .variable("symbol", "ACME")
        .retrieveSubscription("priceUpdates")
        .toEntity(PriceUpdate.class)
        .doOnError(WebSocketDisconnectedException.class, this::logDisconnect);
~~~

If the server proactively sends an error message for the subscription, the Flux can terminate with SubscriptionErrorException. If the connection closes, the Flux can terminate with WebSocketDisconnectedException. Both cases require different policies:

- SubscriptionErrorException: check GraphQL errors, permissions, input, and server state.
- WebSocketDisconnectedException: check close status, network, proxies, and restart the connection/subscription when appropriate.

Do not convert every error into Flux.empty(). Doing so turns an interrupted subscription into a normally completed stream and leaves the caller unaware that real-time data was cut off.

## Retrying with Reactor

Spring for GraphQL allows using Reactor retry operators to restart a subscription when the connection drops. In production applications, cap the attempt count, add backoff, and retry only specific error types.

Example:

~~~java
import java.time.Duration;

import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

Retry disconnectRetry = Retry.backoff(4, Duration.ofSeconds(1))
        .maxBackoff(Duration.ofSeconds(10))
        .jitter(0.5)
        .filter(WebSocketDisconnectedException.class::isInstance)
        .doBeforeRetry(signal ->
                log.warn(
                        "Retry GraphQL WebSocket after disconnect, attempt={}",
                        signal.totalRetries() + 1));

Flux<PriceUpdate> updates = graphQlClient.document("""
        subscription PriceUpdates($symbol: String!) {
            priceUpdates(symbol: $symbol) {
                eventId
                symbol
                price
            }
        }
        """)
        .variable("symbol", "ACME")
        .retrieveSubscription("priceUpdates")
        .toEntity(PriceUpdate.class)
        .retryWhen(disconnectRetry);
~~~

This policy retries up to four times with exponential wait intervals and jitter. Retries apply only to WebSocketDisconnectedException; GraphQL business errors or other errors continue propagating out.

When a retry creates a new subscription, WebSocketGraphQlClient re-establishes the connection if needed. Each re-subscription is a new operation, not a continuation of the previous byte/event stream.

For read-only queries, bounded retries are generally acceptable if the request has no side effects. For mutations, exercise greater caution because the server may have already applied the change before the connection dropped.

Example retrying a read-only Query:

~~~java
import reactor.core.publisher.Mono;

Mono<Account> account = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .retryWhen(disconnectRetry);
~~~

Only use this when the query causes no side effects and re-reading data after reconnecting aligns with business requirements.

## Do not blindly retry Mutations

Suppose the client sends a mutation:

~~~graphql
mutation Transfer($input: TransferInput!) {
  transfer(input: $input) {
    transactionId
    status
  }
}
~~~

The server might complete the transfer, yet the WebSocket closes before the response reaches the client. The client receives WebSocketDisconnectedException and does not know whether the mutation committed.

If the client retries the mutation immediately, the server might execute the transaction a second time. This is an indeterminate outcome state, not proof that the mutation failed.

Ways to mitigate risk:

- Use a unique idempotency key or command ID per business operation.
- Persist command execution results on the server and ensure the same key is applied at most once.
- After a disconnect, query the transaction status by ID before re-submitting the command.
- Only retry mutations when the API has explicitly designed and tested idempotent semantics.
- Do not rely on client request timeouts or WebSocket close codes to conclude the server has not processed the mutation.

Example mutation carrying a command ID:

~~~graphql
input TransferInput {
  commandId: ID!
  fromAccountId: ID!
  toAccountId: ID!
  amountMinorUnits: Int!
}

type Mutation {
  transfer(input: TransferInput!): TransferResult!
}
~~~

The server must store commandId with a unique constraint or equivalent deduplication mechanism. Upon receiving the same commandId again, the server returns the recorded result instead of performing the side effect a second time.

## Recovering Subscriptions without losing events

Retrying a subscription merely starts a new subscription. If the event source continues emitting while the connection is down, the client may miss events. WebSocketDisconnectedException neither contains missed events nor provides a cursor to resume automatically.

To recover seamlessly, the schema and event source must support a cursor or event ID:

~~~graphql
type Subscription {
  priceUpdates(symbol: String!, afterEventId: ID): PriceUpdate!
}

type PriceUpdate {
  eventId: ID!
  symbol: String!
  price: Float!
}
~~~

The client stores the last event ID successfully processed. When re-subscribing, the client passes that event ID so the server replays subsequent events:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

AtomicReference<String> lastProcessedEventId = new AtomicReference<>();

Flux<PriceUpdate> updates = Flux.defer(() ->
        graphQlClient.document("""
                subscription PriceUpdates(
                    $symbol: String!,
                    $afterEventId: ID
                ) {
                    priceUpdates(
                        symbol: $symbol,
                        afterEventId: $afterEventId
                    ) {
                        eventId
                        symbol
                        price
                    }
                }
                """)
                .variable("symbol", "ACME")
                .variable("afterEventId", lastProcessedEventId.get())
                .retrieveSubscription("priceUpdates")
                .toEntity(PriceUpdate.class))
        .retryWhen(disconnectRetry);
~~~

Flux.defer rebuilds the request spec on each retry re-subscription, so the latest cursor value is read at the time of re-subscribing. When processing events, update the cursor only after business logic succeeds:

~~~java
updates.concatMap(update ->
        processPriceUpdate(update)
                .then(Mono.fromRunnable(() ->
                        lastProcessedEventId.set(update.eventId()))));
~~~

This example uses AtomicReference within a single process. For consumers that must survive restarts, persist checkpoints to a database or durable storage. The server must have event retention and well-defined semantics for afterEventId; if the server does not support replay, a client-side cursor cannot recover missed events by itself.

When the server replays, an event may be redelivered if the client processed it but had not yet persisted the checkpoint. Therefore, event processing should be idempotent by eventId and tolerate duplicates.

## Re-authenticating when a new connection is created

A new WebSocket connection requires initializing a new GraphQL session. If the application sends tokens in connection_init, the token must still be valid on reconnect.

Spring for GraphQL provides WebSocketGraphQlClientInterceptor with connectionInitPayload() and handleConnectionAck() callbacks. You can use connectionInitPayload() to obtain the current access token each time a connection is created:

~~~java
import java.util.Map;

import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor.Chain;
import org.springframework.graphql.client.GraphQlClientInterceptor.SubscriptionChain;
import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class AuthWebSocketInterceptor
        implements WebSocketGraphQlClientInterceptor {

    private final TokenProvider tokenProvider;

    public AuthWebSocketInterceptor(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return tokenProvider.currentAccessToken()
                .map(token -> (Object) Map.of(
                        "Authorization",
                        "Bearer " + token));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {
        return chain.next(request);
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {
        return chain.next(request);
    }
}
~~~

When a token expires, the token provider must refresh the token before the next reconnection attempt. If a connection is rejected due to authentication or authorization, continuously retrying with the same token will not solve the problem. Distinguish credential errors from network errors and only retry after the token is refreshed or the user re-authenticates.

Register the interceptor on the client builder:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .interceptor(new AuthWebSocketInterceptor(tokenProvider))
                .build();
~~~

There should be at most one WebSocketGraphQlClientInterceptor in an interceptor chain. It can be combined with standard GraphQlClientInterceptors for request logging, tracing, or metrics.

## Keep-alive and timeouts

Some proxies and load balancers close WebSockets if there is no traffic for a period of time. WebSocketGraphQlClient supports periodic pings:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .keepAlive(Duration.ofSeconds(25))
                .build();
~~~

Keep-alive helps maintain connections through devices with idle timeouts and can detect certain disconnection scenarios. It does not guarantee the connection always stays alive and does not replace retry or resume logic.

Configure the ping interval shorter than the proxy/load balancer idle timeout with a reasonable buffer. Also monitor:

- Connection closure counts by close code.
- Time from disconnect until successful reconnect.
- Retry counts and retry exhaustion counts.
- Active subscription count.
- Gaps without incoming events.
- Replayed and duplicate event counts after reconnect.
- Connection init or authentication failure rates.

## Testing WebSocketDisconnectedException

Test exception classification and recovery behavior separately.

Scenarios to cover:

1. Server closes WebSocket while a Query is waiting for a response.
2. Server closes connection after a Subscription has emitted several events.
3. Server sends a GraphQL error message while the connection stays open.
4. Client calls stop() while an operation is still running.
5. Client retries and a new connection succeeds.
6. Retries exhaust the allowed limit and the error propagates to the caller.
7. Mutation disconnects after server commit and the client does not cause a second side effect.
8. Subscription reconnects with a cursor and misses no events per the event source's semantics.
9. Token expires and is refreshed before the next connection_init.

You can use StepVerifier to verify the Flux terminates with the expected exception:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(subscriptionFlux)
        .expectNextCount(1)
        .expectError(WebSocketDisconnectedException.class)
        .verify();
~~~

In integration tests, use a test WebSocket server capable of closing the connection at a deterministic point. Then verify the client receives the exception, the close status is preserved, and the in-flight request is identified. For retry tests, the test server should accept the new connection and return events for the re-subscribed operation.

For Subscriptions with replay, tests must verify event IDs, event ordering, duplicates, and checkpoints. Merely verifying that the connection reopened is insufficient to prove no data was lost.

## Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Query or Mutation emits WebSocketDisconnectedException | Connection closed before response reached the client | Check close status, active request, and connectivity |
| Subscription ends unexpectedly | WebSocket dropped while stream was active | Use bounded retries and design resume if needed |
| Confusing disconnect with GraphQL error | Failing to distinguish transport exceptions from response errors | Check exception hierarchy and ClientGraphQlResponse |
| Retrying still fails to connect | Server not ready, proxy failure, or expired credentials | Backoff, verify endpoint, and refresh token |
| Mutation executed twice | Retried after server committed but response was lost | Use command ID / idempotency key |
| Reconnect succeeds but events are missed | New subscription starts from current time | Use cursor, event ID, and server-side replay |
| Duplicate events received after retry | Server replayed events processed before checkpoint | Deduplicate by event ID |
| Retry loop runs during application shutdown | stop() treated as a network error | Distinguish intentional shutdown from unexpected disconnect |
| Keep-alive still does not prevent disconnect | Proxy/server restart or genuine network loss | Combine retries, reconnect, and monitoring |
| New connection rejected | Stale token or changed access permissions | Refresh credentials and re-authenticate |

## Principles for handling WebSocketDisconnectedException

When using WebSocketGraphQlClient, remember:

1. **Identify the right error type.** WebSocketDisconnectedException is a GraphQlTransportException, not a GraphQL business error.
2. **Read CloseStatus and the original request.** Use getCloseStatus() and getRequest() for diagnostics.
3. **Understand reconnect behavior.** The client opens a new connection on the next request or when start() is called; active operations still terminate with an error.
4. **Retry with limits.** Use backoff, jitter, and retry only appropriate transport errors.
5. **Do not blindly retry mutations.** Use idempotency keys or query status before resending.
6. **Resume subscriptions using cursors.** Reconnecting does not automatically replay missed events.
7. **Handle duplicates.** Use event IDs and checkpoint after successful processing.
8. **Refresh authentication.** connection_init on the new connection needs valid credentials.
9. **Distinguish shutdown from failures.** stop() intentionally terminates operations and should not trigger reconnect loops.
10. **Monitor connection lifecycle.** Measure close codes, retries, reconnect latency, active subscriptions, and event gaps.

WebSocketDisconnectedException indicates that a WebSocket connection closed or dropped while a GraphQL request or subscription was active. Spring for GraphQL provides the close status and original request for application diagnostics. WebSocketGraphQlClient can establish a new connection for the next request, while active operations must be retried or re-subscribed according to application policy. Queries can be retried when appropriate; Mutations require idempotency because the server's outcome may be unknown; Subscriptions require cursors and replay if event loss is unacceptable. Classifying errors properly and designing recovery around each operation's semantics enables clients to withstand network disruptions without creating duplicate side effects or losing data.

## References

- [Spring for GraphQL - Client: WebSocketGraphQlClient and Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL API - WebSocketDisconnectedException](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketDisconnectedException.html)
- [Spring for GraphQL API - WebSocketGraphQlClient](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClient.html)
- [Spring for GraphQL API - GraphQlClient.RequestSpec](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
