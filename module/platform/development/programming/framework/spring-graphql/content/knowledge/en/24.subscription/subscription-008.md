# Subscription error handling in Spring for GraphQL

A GraphQL subscription maintains an event stream after the client subscribes successfully. Because the stream can run for a long time, errors can arise at several points: while validating the request, while creating the publisher, while resolving an event, or when the publisher terminates with an error signal.

A key distinction in Spring for GraphQL is between an error during a single field execution and a terminal error from the subscription publisher. `DataFetcherExceptionResolver` handles exceptions thrown by data fetchers during GraphQL execution. Once the subscription publisher has been returned and the transport begins subscribing, if the publisher signals `onError`, you must use `SubscriptionExceptionResolver` to convert the exception into a list of `GraphQLError`s sent to the client.

## 1. Subscription lifecycle and potential failure points

Example schema for tracking order changes:

~~~graphql
type Query {
    order(id: ID!): Order
}

type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type Order {
    id: ID!
    status: String!
}

type OrderEvent {
    orderId: ID!
    status: String!
    occurredAt: String!
}
~~~

Client subscribes:

~~~graphql
subscription TrackOrder {
    orderUpdated(orderId: "order-10") {
        orderId
        status
        occurredAt
    }
}
~~~

Once the subscription is established, the server emits one GraphQL response per event. The stream can continue until the client cancels, the publisher completes, or the publisher terminates with an error.

~~~mermaid
flowchart TD
    A[Client sends Subscription] --> B[Parse and validate document]
    B -->|Invalid request| C[Request-level GraphQL errors]
    B -->|Valid| D[Run @SubscriptionMapping]
    D -->|Method throws before returning Publisher| E[DataFetcherExceptionResolver]
    D -->|Returns Publisher| F[Transport subscribes]
    F --> G[Publisher emits event]
    G --> H[GraphQL resolves selection set]
    H -->|Event field error| I[DataFetcherExceptionResolver]
    I --> J[Event response has data/errors]
    H -->|Success| J
    J --> G
    F -->|Publisher onError| K[SubscriptionExceptionResolver]
    K --> L[Transport sends final error message]
    F -->|Complete or client cancel| M[End subscription]
~~~

The diagram highlights the distinct error-handling points. A field error inside an event can be recorded in that event's response, whereas a terminal error from the publisher ends the entire subscription.

## 2. Distinguishing types of Subscription errors

| Timing | Example | Appropriate handling mechanism |
| --- | --- | --- |
| Before execution | Malformed GraphQL document, unknown field, invalid argument type | Request-level GraphQL errors; no data fetcher runs yet. |
| Calling `@SubscriptionMapping` method | Stream not found or unable to initialize publisher | `DataFetcherExceptionResolver` as an initial data fetcher exception. |
| Resolving a field of an event | Resolver for `OrderEvent.customer` fails | `DataFetcherExceptionResolver`; error belongs to that event's response. |
| Publisher already running and emits `onError` | Broker disconnects, event source times out, broken stream | `SubscriptionExceptionResolver`; transport sends terminal subscription error. |
| Client loses transport connection | WebSocket closes or network interruption | Client handles `GraphQlTransportException` and reconnection policy. |

Not every error occurring while a client holds a subscription is a publisher error. For example, if an event is emitted and a child field resolver fails, GraphQL can return that event with partial `data` and `errors`; the source publisher can still emit subsequent events.

## 3. Why doesn't DataFetcherExceptionResolver handle publisher errors?

The root subscription data fetcher's sole job is to create and return the initial publisher. Afterward, the transport subscribes to that publisher to receive events. If the publisher emits `onError` after that point, the error no longer occurs inside the initial data fetcher invocation.

Therefore, `DataFetcherExceptionResolver` cannot handle exceptions that terminate the subscription publisher. Spring for GraphQL provides a dedicated contract, `SubscriptionExceptionResolver`, for this case.

Remember three rules:

- `@SubscriptionMapping` method throws before returning a publisher: handled as a data fetcher exception.
- A field data fetcher within an individual event throws an exception: handled by `DataFetcherExceptionResolver`.
- The source publisher emits `onError` after the subscription is established: handled by `SubscriptionExceptionResolver`.

## 4. Creating a Subscription resolver with SubscriptionExceptionResolverAdapter

`SubscriptionExceptionResolverAdapter` is a Spring for GraphQL convenience base class in package `org.springframework.graphql.execution`. The adapter implements the reactive contract and lets you override `resolveToSingleError` or `resolveToMultipleErrors`.

Example mapping an event source failure to a safe GraphQL error:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.execution.SubscriptionExceptionResolverAdapter;
import org.springframework.stereotype.Component;

@Component
public class OrderSubscriptionExceptionResolver
        extends SubscriptionExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(Throwable exception) {
        if (exception instanceof OrderEventSourceException) {
            return GraphqlErrorBuilder.newError()
                    .message("Unable to continue receiving order updates")
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .extensions(Map.of("code", "ORDER_EVENT_SOURCE_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
~~~

In this example:

- Only `OrderEventSourceException` is handled by this resolver.
- `resolveToSingleError` returns a `GraphQLError` with a generic message and a stable error code.
- Returning `null` indicates this resolver does not handle the exception; the next resolver in the chain may try.
- Never expose stack traces, broker details, server addresses, or sensitive data in the message returned to the client.

The adapter also supports `resolveToMultipleErrors` if one exception needs to be represented as multiple GraphQL errors. Typically, a terminal stream error needs only one error with a clear code.

## 5. Registering SubscriptionExceptionResolver

With the Spring Boot GraphQL starter, beans implementing `SubscriptionExceptionResolver` are automatically discovered and added to `GraphQlSource` in order. Thus, the `@Component` example above is registered automatically.

If your application builds `GraphQlSource` manually, add the resolvers to the builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .subscriptionExceptionResolvers(List.of(orderSubscriptionExceptionResolver))
        .build();
~~~

This snippet assumes `schemaResource` and `orderSubscriptionExceptionResolver` are already created or injected. When configuring `GraphQlSource` manually, make sure the resolver list is actually attached to the source used by `ExecutionGraphQlService`.

Multiple `SubscriptionExceptionResolver` instances can be registered. Spring invokes them in order until one returns a list of errors. Order specialized resolvers before generic fallback resolvers so domain errors are mapped accurately.

## 6. Empty results from a resolver have two different meanings

The `SubscriptionExceptionResolver` contract returns `Mono<List<GraphQLError>>`:

| Result | Meaning |
| --- | --- |
| `Mono.just(List.of(error))` | Handled the exception and has an error to send to the client. |
| `Mono.just(List.of())` | Handled the exception and intentionally sends no GraphQL error. |
| `Mono.empty()` | Resolver did not handle it; allows the next resolver to try. |

When extending `SubscriptionExceptionResolverAdapter`, returning `null` from `resolveToSingleError` or `resolveToMultipleErrors` indicates unresolved. Do not confuse `Mono.empty()` with `Mono.just(List.of())`: one delegates to another resolver, while the other confirms the exception was handled without sending errors.

Avoid returning an empty list merely to suppress every error. If a stream terminates without the client receiving error details, the UI may assume the subscription ended normally or have no idea why events stopped arriving.

## 7. Mapping errors in `@SubscriptionMapping`

The controller should focus on creating the publisher and translating technical failures into meaningful domain exceptions. A dedicated resolver then decides how to turn those exceptions into GraphQL errors.

~~~java
import java.time.Duration;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument("orderId") String orderId) {
        return eventService.events(orderId)
                .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                        .filter(this::isTransientFailure))
                .onErrorMap(error -> new OrderEventSourceException(error));
    }

    private boolean isTransientFailure(Throwable error) {
        return error instanceof EventBrokerUnavailableException
                || error instanceof EventSourceTimeoutException;
    }
}
~~~

This example assumes `eventService.events` returns `Flux<OrderEvent>`. The publisher retries up to three times with backoff for transient failures; if it still fails, `onErrorMap` converts the error into `OrderEventSourceException`. When the publisher eventually emits `onError`, `OrderSubscriptionExceptionResolver` can map that exception to a GraphQL error.

Do not retry every exception indefinitely. Validation failures, authorization errors, or non-retryable business errors should fail fast. Retrying can cause events to be replayed or missed around reconnection windows; for high-reliability streams, pair retries with event IDs/cursors and a resume mechanism.

## 8. Single-event errors vs. stream-terminating errors

Suppose the publisher emits an `OrderEvent`, but the resolver for its `customer` field fails. That error occurs while GraphQL completes the selection set for that event. It is handled as a normal data fetcher error and appears in that event's response.

~~~json
{
  "data": {
    "orderUpdated": {
      "orderId": "order-10",
      "status": "SHIPPED",
      "customer": null
    }
  },
  "errors": [
    {
      "message": "Unable to load customer information",
      "path": ["orderUpdated", "customer"]
    }
  ]
}
~~~

This illustrative response can be emitted for a single event while the publisher continues emitting subsequent events if the source remains healthy. Null propagation also depends on nullability in the SDL.

Conversely, if the event broker disconnects and the publisher signals `onError`, the subscription emits no further events. Spring invokes `SubscriptionExceptionResolver`, and the transport sends the final error notification to the client.

## 9. To continue a stream after an error, recover inside the publisher

`SubscriptionExceptionResolver` only converts terminal exceptions into GraphQL errors. It does not restart the publisher, emit substitute events, or keep the subscription alive.

If an error is recoverable and business logic wants the subscription to continue, handle it inside the Reactor pipeline before the publisher terminates:

~~~java
return eventService.events(orderId)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .filter(this::isTransientFailure));
~~~

Or use `onErrorResume` to switch to a fallback publisher when that makes sense:

~~~java
return eventService.events(orderId)
        .onErrorResume(CacheUnavailableException.class,
                error -> fallbackEventService.events(orderId));
~~~

Only use a fallback if the alternative source satisfies the data contract and enforces equivalent access permissions. Never turn a security error or data corruption error into an empty stream to hide the problem.

If you need to notify the client of a warning while keeping the stream open, model the warning as an event in the schema instead of emitting a terminal GraphQL error.

## 10. Modeling warnings as events when the stream must continue

A terminal GraphQL error fits when the subscription cannot continue. If a warning is a valid part of the business flow, you can represent it using a union:

~~~graphql
type OrderChanged {
    orderId: ID!
    status: String!
}

type OrderStreamWarning {
    code: String!
    message: String!
}

union OrderSubscriptionEvent = OrderChanged | OrderStreamWarning

type Subscription {
    orderEvents(orderId: ID!): OrderSubscriptionEvent!
}
~~~

The client can distinguish update events from warnings:

~~~graphql
subscription {
    orderEvents(orderId: "order-10") {
        __typename
        ... on OrderChanged {
            orderId
            status
        }
        ... on OrderStreamWarning {
            code
            message
        }
    }
}
~~~

With this model, a warning is data inside an event and the publisher can continue. Do not put stack traces or infrastructure details into `message`; warning payloads must still comply with API security policies.

## 11. How does the client receive Subscription errors?

With `WebSocketGraphQlClient`, if the server sends a final error message for the subscription, the client-side `Flux` terminates with `SubscriptionErrorException`. This exception provides `getErrors()` to read the list of GraphQL errors in the payload.

Example:

~~~java
import org.springframework.graphql.client.SubscriptionErrorException;
import reactor.core.publisher.Flux;

Flux<OrderEvent> updates = graphQlClient.document("""
        subscription TrackOrder {
            orderUpdated(orderId: "order-10") {
                orderId
                status
            }
        }
        """)
        .retrieveSubscription("orderUpdated")
        .toEntity(OrderEvent.class);

updates.doOnError(error -> {
    if (error instanceof SubscriptionErrorException subscriptionError) {
        subscriptionError.getErrors().forEach(item ->
                log.warn("Subscription ended with GraphQL error: {}", item.getMessage()));
    }
}).subscribe(this::handleOrderEvent);
~~~

This snippet assumes `graphQlClient` is a `WebSocketGraphQlClient`, and `log` and `handleOrderEvent` are already defined. `retrieveSubscription` decodes one field from each response. When the server ends the subscription with an error message, the stream signals an error rather than emitting further `OrderEvent` items.

## 12. Distinguishing SubscriptionErrorException from transport errors

Not every client-side error comes from the server intentionally ending the subscription:

| Client error | Meaning | Handling direction |
| --- | --- | --- |
| `SubscriptionErrorException` | Server sent a final GraphQL error message for the subscription | Inspect `getErrors()`, classify error codes, and decide whether to re-subscribe. |
| `WebSocketDisconnectedException` | WebSocket connection was closed or lost | Check connectivity and reconnection policy. |
| `GraphQlTransportException` | Transport-layer failure | Classify by root cause; do not treat all of them as business errors. |
| GraphQL errors in an event response | A field of one event failed while the event response was still emitted | Read field-level errors and decide whether to render partial data. |

`SubscriptionErrorException` is a subclass of `GraphQlTransportException`, carrying the list of GraphQL errors from the WebSocket error message. Connection drops are a separate scenario and may require their own reconnection strategy.

## 13. Client-side retry and duplicate event possibilities

Clients can use Reactor `retryWhen` to re-subscribe after transport errors or recoverable subscription errors. However, reconnecting does not automatically restore the exact prior position in the stream.

Simple example:

~~~java
updates.retryWhen(Retry.backoff(3, Duration.ofSeconds(2))
        .filter(this::isRetryableSubscriptionFailure));
~~~

Retry only errors identified as transient. Do not repeatedly retry `FORBIDDEN`, `UNAUTHORIZED`, malformed requests, or subscriptions rejected due to business state.

For critical events, design additionally:

- Unique event IDs so clients can deduplicate events.
- Cursors or offsets so clients can request resumption from the last processed position.
- Checkpointing rules after an event is processed successfully.
- A server-side event replay window for a defined retention period.

Without cursors/replay, clients may miss events during disconnection windows. If the server replays older events on reconnect, clients may receive duplicates. These are data/transport design requirements and are not solved by `SubscriptionExceptionResolver` alone.

## 14. Securing information in subscription errors

Subscriptions often run for a long time and may carry user- or tenant-specific data. When mapping errors:

1. Never return raw exception messages from databases, brokers, or HTTP clients.
2. Never put tokens, auth headers, SQL, internal hostnames, or stack traces into `extensions`.
3. Use stable error codes so clients can classify errors, such as `ORDER_EVENT_SOURCE_UNAVAILABLE`.
4. Return only enough information for the client to show an error or decide to re-subscribe.
5. Log the root cause on the server with appropriate correlation IDs and execution metadata.
6. Avoid logging event payloads or sensitive personal data unless necessary.

If access rights are revoked while a stream is running, define a policy to terminate the subscription or stop emitting events. Never assume authorization only needs checking once at subscribe time if business rules require live permission enforcement.

## 15. Logging and observing errors

When handling publisher errors, record:

- Subscription field name or operation name.
- GraphQL error code returned to the client.
- Correlation ID or execution ID if available.
- Stream start and end timestamps.
- Number of events emitted before the error.
- Categorized internal root cause.
- Retry count and reconnection outcome if applicable.

Do not use `doOnError` as a replacement for `SubscriptionExceptionResolver`. `doOnError` only observes errors inside the publisher; the resolver is responsible for mapping terminal errors into GraphQL errors. You can combine both: Reactor operators record metrics/correlation, while the resolver standardizes errors for the transport.

## 16. Testing Subscription errors

Test across multiple layers.

### Testing SubscriptionExceptionResolver

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void mapsOrderEventSourceException() {
    OrderSubscriptionExceptionResolver resolver =
            new OrderSubscriptionExceptionResolver();

    StepVerifier.create(resolver.resolveException(
                    new OrderEventSourceException(new RuntimeException("broker down"))))
            .assertNext(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Unable to continue receiving order updates");
            })
            .verifyComplete();
}
~~~

This test verifies that the resolver maps the exception into one GraphQL error without leaking the internal `"broker down"` message.

### Testing a stream that emits an event and then terminates with an error

With a subscription-capable tester, you can assert events before the error and the terminal error signal:

~~~java
Flux<String> statuses = graphQlTester.document("""
        subscription {
            orderUpdated(orderId: "order-10") {
                status
            }
        }
        """)
        .executeSubscription()
        .toFlux("orderUpdated.status", String.class);

StepVerifier.create(statuses)
        .expectNext("CREATED")
        .expectError()
        .verify();
~~~

This is a skeleton example: the test fixture must provide a publisher that emits `CREATED` and then signals `OrderEventSourceException`, and the GraphQL source must be configured with `SubscriptionExceptionResolver`. If you need to verify the exact errors delivered over WebSocket, use `WebSocketGraphQlTester` or `WebSocketGraphQlClient` in an integration test and assert `SubscriptionErrorException.getErrors()`.

### Scenarios to test

1. Schema-invalid subscription requests are rejected before creating a publisher.
2. `@SubscriptionMapping` method throws an exception while initializing the publisher.
3. Publisher emits one or more events and then terminates with `onError`.
4. `SubscriptionExceptionResolver` maps domain exceptions to the right error code and message.
5. Exceptions unhandled by one resolver fall through to the next resolver.
6. Child field resolver errors affect only the corresponding event response according to nullability.
7. Publisher retries apply only to transient errors and are bounded.
8. Client distinguishes `SubscriptionErrorException` from transport disconnection errors.
9. Client cancellation cancels upstream and releases resources.
10. Error payloads do not leak internal data.

## 17. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `DataFetcherExceptionResolver` does not catch stream errors | Publisher was already returned and the error happened after the transport subscribed | Register a `SubscriptionExceptionResolver`. |
| `@GraphQlExceptionHandler` does not handle publisher `onError` | Handler methods only cover exceptions during data fetcher/controller invocation | Use `SubscriptionExceptionResolver` for terminal stream errors. |
| Client only sees stream termination | No resolver maps the error or the resolver is not registered | Check bean discovery or `GraphQlSource` builder wiring. |
| Stream stops after a single transient error | Publisher emits `onError` with no retry/recovery | Use retry/fallback inside the publisher if business rules permit. |
| Retries produce duplicate events | Server/client reconnects without event IDs or cursors | Design deduplication and resume support. |
| Resolver maps every error to the same code | Missing exception classification or overly broad catch-all | Map specific domain exceptions and leave unknown ones unresolved. |
| Client retries authorization errors too | Not distinguishing `SubscriptionErrorException` from transport errors or error codes | Retry only recoverable failures. |
| Broker/database details leak out | Using exception message directly as GraphQL message | Use generic messages and stable error codes. |
| Business warnings terminate the stream | Using `Flux.error` for conditions that should allow continuing | Model warnings as event data types. |

## 18. Checklist for Subscription error handling

1. Classify errors by stage: request validation, resolver initialization, event field resolution, or terminal publisher error.
2. Use `DataFetcherExceptionResolver` for data fetcher errors during execution.
3. Use `SubscriptionExceptionResolver` for publisher `onError` after the subscription has started.
4. Register resolvers via Spring Boot bean discovery or `GraphQlSource.Builder`.
5. Return GraphQL errors with stable codes, safe messages, and proper error classifications.
6. Have non-matching resolvers return `null`/unresolved so the next resolver can handle the exception.
7. Use retry/fallback inside the publisher when failures are recoverable and business rules allow.
8. Model non-fatal warnings as event data when the stream should continue.
9. Distinguish `SubscriptionErrorException` from transport disconnection errors on the client.
10. Design event IDs/cursors if resume and deduplication are needed.
11. Test terminal errors, per-event errors, retries, cancellation, and error payload security.

`SubscriptionExceptionResolver` is the dedicated extension point for terminal errors of a subscription publisher. By cleanly separating request errors, per-event field errors, and stream `onError` signals, applications can return consistent GraphQL errors, preserve valid events, and help clients decide appropriately between displaying an error, retrying, or re-subscribing.

References: [Spring for GraphQL — Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution-exceptions-subscriptions), [SubscriptionExceptionResolver API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/SubscriptionExceptionResolver.html), and [Spring for GraphQL Client — Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html#client.graphqlclient.requests.subscriptions).
