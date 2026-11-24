# Testing Subscriptions and Emitted Data

## 1. What is a GraphQL subscription, and what must be proved?

In Spring Boot using **Spring for GraphQL**, the three common operation types are `query`, `mutation`, and `subscription`:

- **Query:** the client requests data and the server returns a single logical result.
- **Mutation:** the client requests a state change or action and normally receives a single logical result.
- **Subscription:** the client **subscribes to a stream of results** as a data source emits events. A single subscription can produce multiple responses over time, or complete/error/cancel.

For example, in an inventory system: instead of repeatedly polling `query { stock(sku: "SKU-7") }`, the client subscribes:

~~~graphql
subscription WatchStock($sku: ID!) {
  stockUpdated(sku: $sku) {
    sku
    quantity
    sequence
  }
}
~~~

with variables:

~~~json
{"sku":"SKU-7"}
~~~

As the source updates, the server can emit:

~~~json
{"data":{"stockUpdated":{"sku":"SKU-7","quantity":3,"sequence":1}}}
{"data":{"stockUpdated":{"sku":"SKU-7","quantity":5,"sequence":2}}}
~~~

These are **two separate GraphQL responses in a stream**, not a single two-line JSON document sent as a normal HTTP body.

For the topic **"Testing subscriptions and emitted data,"** a reliable test suite should answer:

1. **Is the subscription valid?** Are the GraphQL document, root field name, variables, schema, resolver, and wiring correct?
2. **Are events emitted?** Does the stream emit `onNext`, with each event carrying the expected values, types, and order when ordering is part of the contract?
3. **Is filtering accurate?** Does it receive only events for the permitted `sku`/user/tenant without mixing events from other subscriptions?
4. **How does it terminate?** Finite streams emit `onComplete`; long-lived streams require cancellation; upstream failures need an explicit error policy.
5. **Does the transport work?** Testing a resolver without a network differs from testing a GraphQL subscription over real WebSockets.
6. **Are resources released?** When a subscriber cancels or a client closes the connection, does the publisher stop holding unnecessary resources?

**Do not equate "the controller returned a `Flux`" with "the client subscribed and received events."** Reactor Publishers are usually lazy: without a downstream subscriber, most of the stream never executes.

## 2. GraphQL scope within "GraphQL and SOAP"

The parent category includes **GraphQL and SOAP**, yet `subscription` and emitted event streams in this lesson apply **directly to GraphQL subscriptions**. In Spring for GraphQL, a field on the root `Subscription` type can be mapped with `@SubscriptionMapping` and return a `Flux<T>` or Reactive Streams `Publisher<T>`.

Traditional SOAP relies primarily on XML request/response over HTTP. A SOAP system **can** support event notifications through specifications or architectures such as WS-Eventing or WS-Notification, but **that is not a GraphQL subscription** and does not use `GraphQlTester.executeSubscription()`. Never use a GraphQL test to claim SOAP eventing is verified, or vice versa.

| Aspect | GraphQL subscription | Traditional SOAP |
| --- | --- | --- |
| Contract definition | GraphQL SDL, root `type Subscription` | WSDL/XSD, SOAP envelope/operation |
| Emitted data | Multiple GraphQL execution results | Normally one SOAP message response per request; eventing needs dedicated mechanisms |
| Appropriate Spring test | `GraphQlTester` + `StepVerifier`, WebSocket tester | Spring-WS `MockWebServiceServer`/HTTP SOAP client tests, or real eventing mechanism |
| Common transport | WebSocket, some SSE/RSocket modes | HTTP/SOAP; eventing depends on chosen protocol |
| Core assertions | Per-event payloads, order, completion/cancel/error | SOAP body/header/fault/XSD; separate event callbacks if used |

The remainder of the article stays strictly on topic: **GraphQL subscriptions in Spring Boot**, emitted event data, the GraphQL schema, and transport.

## 3. Which layers does a subscription pass through?

~~~text
GraphQL client
    |
    | subscription document + variables
    v
GraphQL operation / transport
    |                       \
    | server-side test       \ WebSocket integration
    v                        v
GraphQlService            WebSocket server/handler
    \                        /
     \                      /
      v                    v
        GraphQL Java execution
                 |
                 v
      @SubscriptionMapping method
                 |
                 v
          StockFeed.stream(sku)
                 |
                 v
        Flux<StockUpdate> events
                 |
             onNext / onComplete / onError / cancel
                 |
                 v
      GraphQL result per emitted item
                 |
                 v
          tester.toFlux(...)
                 |
                 v
          StepVerifier assertions
~~~

Distinguish two main test styles:

- **Server-side GraphQL slice test:** `@GraphQlTest` + `GraphQlTester` configured by Spring Boot to execute GraphQL **without starting an HTTP/WebSocket server**. It verifies the schema, mappings, decoding, and resolver behavior against supplied collaborators.
- **WebSocket integration test:** `@SpringBootTest(RANDOM_PORT)` with WebFlux and a live WebSocket endpoint, creating `WebSocketGraphQlTester` connected to `ws://127.0.0.1:<port>/graphql`. It verifies the WebSocket handshake/protocol path, server wiring, and events reaching the client.

You can also write **pure Publisher unit tests** with JUnit + Reactor Test without loading Spring, testing operators, errors, backpressure, and cancellation faster.

### Do not confuse an HTTP query with a subscription

`GraphQlTester.document(...).execute()` fits `query` or `mutation`, producing a single response. For `subscription`, use:

~~~java
Flux<StockUpdate> events = tester.document(document)
        .variable("sku", "SKU-7")
        .executeSubscription()
        .toFlux("stockUpdated", StockUpdate.class);
~~~

`toFlux("stockUpdated", StockUpdate.class)` decodes **each response** from `data.stockUpdated` into `StockUpdate`; it does not trigger assertions on event counts without a subscriber. Subscribe using `StepVerifier` and enforce termination or cancellation bounds.

## 4. GraphQL schema and event contracts

Spring Boot auto-discovers schemas when `.graphqls`/`.gqls` files are placed under `src/main/resources/graphql/**`. In this example, we include a minimal `Query` for a valid root query alongside a root subscription.

**File `src/main/resources/graphql/schema.graphqls`:**

~~~graphql
type Query {
  ping: String!
}

type Subscription {
  stockUpdated(sku: ID!): StockUpdate!
}

type StockUpdate {
  sku: ID!
  quantity: Int!
  sequence: Int!
}
~~~

Meaning:

- `stockUpdated` is the GraphQL field name that must match the controller mapping.
- `sku: ID!`: the client must pass a non-null argument (typically an identifier string).
- `StockUpdate!`: **each emitted payload** must conform to a non-null object per the schema. It **does not mean** the subscription is guaranteed to emit at least one item.
- `quantity` and `sequence` are `Int!`: every event must supply valid non-null integers. GraphQL `Int` is a 32-bit signed integer; Java values must fit in that range.
- `sequence` is used to assert **logical event ordering** defined by the API. It is not an ID auto-generated by GraphQL.

A subscription can emit **0, 1, or many events**. If a publisher completes immediately with zero `onNext` signals, both the schema and GraphQL controller can still be technically valid; tests must specify whether that is desired behavior or a business bug.

### Events and responses are not identical

Each `StockUpdate` from the `Flux` is **resolver data**. GraphQL applies the selection set to build `{"data": {"stockUpdated": {...}}}` for each item. A client might request only `sku` and `quantity`; do not assume the GraphQL response includes every Java record field if the document omits them.

If an event breaks a non-null/type contract or the resolver throws an error, the response can contain `errors`, or the stream is handled according to the GraphQL transport policy. Consequently, **GraphQL errors** and **raw Publisher errors** do not necessarily share the exact same Java exception class or stack trace on the client.

## 5. Gradle, WebFlux, and WebSocket configuration

The primary example uses **Java 17, Spring Boot 3.5.16, Boot-managed Spring for GraphQL, Reactor, JUnit Jupiter, Mockito, and WebSocketGraphQlTester**. Do not force an independent GraphQL version incompatible with the BOM.

**File `build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This file assumes a compatible Gradle Wrapper and project settings. Spring Boot manages Spring GraphQL and Reactor versions, so omit explicit versions on `spring-graphql-test` and `reactor-test`.

**File `src/main/resources/application.properties`:**

~~~properties
spring.graphql.websocket.path=/graphql
~~~

`spring-boot-starter-graphql` alone does not expose GraphQL over the network; the WebFlux starter provides the HTTP/WebSocket runtime. In **Spring Boot 3.5**, the GraphQL WebSocket endpoint is **disabled by default** until `spring.graphql.websocket.path` is configured. In a WebFlux application, you do not add a separate `spring-boot-starter-websocket` as you would for Servlet WebSockets; this demo uses WebFlux.

The default GraphQL HTTP path is POST `/graphql`; Spring Boot 3.5 also supports Server-Sent Events (`text/event-stream`) for subscriptions on the HTTP endpoint. However, `GraphQlTester.executeSubscription()` in Spring for GraphQL 1.4 is documented for **server-side testers or `WebSocketGraphQlTester`**. Do not expect `HttpGraphQlTester` to act like a WebSocket tester for HTTP subscriptions; to test SSE, use an appropriate SSE reader and verify transport separately.

### File layout

~~~text
src/main/java/com/example/graphqlsub/
  GraphQlSubscriptionApplication.java
  StockUpdate.java
  StockFeed.java
  DeterministicStockFeed.java
  StockSubscriptionController.java

src/main/resources/
  application.properties
  graphql/schema.graphqls

src/test/java/com/example/graphqlsub/
  StockGraphQlSliceTest.java
  StockSubscriptionWebSocketTest.java
  StockSubscriptionUnitTest.java

build.gradle
~~~

All classes/files in sections 6–9 use package `com.example.graphqlsub`. Each `public` class or interface file name matches its declaration.

## 6. Complete sample application: producer and @SubscriptionMapping

### 6.1. Entry point

**`src/main/java/com/example/graphqlsub/GraphQlSubscriptionApplication.java`:**

~~~java
package com.example.graphqlsub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlSubscriptionApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlSubscriptionApplication.class, args);
    }
}
~~~

### 6.2. Event payload

**`src/main/java/com/example/graphqlsub/StockUpdate.java`:**

~~~java
package com.example.graphqlsub;

public record StockUpdate(
        String sku,
        int quantity,
        int sequence
) {
}
~~~

A Java record makes an ideal immutable DTO. In the example, event order is tracked via `sequence = 1, 2`; avoid wall-clock timestamps or random numbers that cause flaky tests.

### 6.3. Event source interface

**`src/main/java/com/example/graphqlsub/StockFeed.java`:**

~~~java
package com.example.graphqlsub;

import reactor.core.publisher.Flux;

public interface StockFeed {
    Flux<StockUpdate> stream(String sku);
}
~~~

In a real system, the source might read from a message broker, database change stream, `Sinks.Many`, or an upstream reactive client. GraphQL tests only need a controllable `Flux<StockUpdate>`.

### 6.4. Deterministic event source for WebSocket integration

**`src/main/java/com/example/graphqlsub/DeterministicStockFeed.java`:**

~~~java
package com.example.graphqlsub;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class DeterministicStockFeed implements StockFeed {

    @Override
    public Flux<StockUpdate> stream(String sku) {
        if ("UNKNOWN".equals(sku)) {
            return Flux.empty();
        }

        return Flux.just(
                new StockUpdate(sku, 3, 1),
                new StockUpdate(sku, 5, 2)
        );
    }
}
~~~

This source is **not** a production event bus. It immediately emits two items and completes so WebSocket tests do not wait on a message broker or timer. `Flux.just(...)` acts as a cold Publisher here: subscribers receive events upon subscribing. Identical `sku` inputs yield identical data, giving deterministic expected outputs.

In real projects, producers are singletons shared by multiple subscribers. Tests should cover **multiple subscribers** and tenant/security isolation once the event source is no longer deterministic.

### 6.5. Real GraphQL controller

**`src/main/java/com/example/graphqlsub/StockSubscriptionController.java`:**

~~~java
package com.example.graphqlsub;

import java.util.Objects;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class StockSubscriptionController {
    private final StockFeed feed;

    public StockSubscriptionController(StockFeed feed) {
        this.feed = Objects.requireNonNull(feed, "feed");
    }

    @QueryMapping
    public String ping() {
        return "pong";
    }

    @SubscriptionMapping
    public Flux<StockUpdate> stockUpdated(@Argument("sku") String sku) {
        return feed.stream(sku);
    }
}
~~~

`@SubscriptionMapping` maps `stockUpdated` to `Subscription.stockUpdated` in the schema by default. `@Argument("sku")` binds the GraphQL argument to the Java parameter explicitly without depending on compiled parameter-name metadata.

Never call `.subscribe()` or `.block()` inside the controller: the GraphQL infrastructure subscribes and streams events over the transport. A resolver returning a `Flux` with no active client subscription **does not mean an HTTP/WebSocket response stream was created**.

**Do not use `@SchemaMapping(typeName = "Query")` for a subscription field** expecting it to register as a Subscription: the root type and operation must match. `@SubscriptionMapping` is a meta-annotation equivalent to `@SchemaMapping(typeName = "Subscription")`.

## 7. Testing without a network: @GraphQlTest + GraphQlTester

`@GraphQlTest(StockSubscriptionController.class)` loads Spring GraphQL infrastructure and the selected controller without launching an HTTP/WebSocket server. `DeterministicStockFeed` annotated with `@Service` **is normally not scanned by the slice**, so use `@MockitoBean` to supply the mock dependency in the Spring context.

This is ideal for checking **schema + resolver + event decoding + ordering** free of network dependencies.

**File `src/test/java/com/example/graphqlsub/StockGraphQlSliceTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@GraphQlTest(StockSubscriptionController.class)
class StockGraphQlSliceTest {

    private static final String SUBSCRIPTION = """
            subscription WatchStock($sku: ID!) {
              stockUpdated(sku: $sku) {
                sku
                quantity
                sequence
              }
            }
            """;

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    StockFeed feed;

    private Flux<StockUpdate> updates(String sku) {
        return tester.document(SUBSCRIPTION)
                .variable("sku", sku)
                .executeSubscription()
                .toFlux("stockUpdated", StockUpdate.class);
    }

    @Test
    void emitsTwoEventsWithExactValuesAndOrder() {
        StockUpdate first = new StockUpdate("SKU-7", 3, 1);
        StockUpdate second = new StockUpdate("SKU-7", 5, 2);

        when(feed.stream("SKU-7"))
                .thenReturn(Flux.just(first, second));

        StepVerifier.create(updates("SKU-7"))
                .expectNext(first, second)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-7");
    }

    @Test
    void bindsSkuVariableAndReturnsOnlyRequestedSkuEvents() {
        StockUpdate one = new StockUpdate("SKU-9", 8, 1);
        when(feed.stream("SKU-9")).thenReturn(Flux.just(one));

        StepVerifier.create(updates("SKU-9"))
                .expectNext(one)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-9");
    }

    @Test
    void emptyFeedCompletesWithoutAnyPayload() {
        when(feed.stream("UNKNOWN")).thenReturn(Flux.empty());

        StepVerifier.create(updates("UNKNOWN"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("UNKNOWN");
    }

    @Test
    void canInspectIndividualResponseFields() {
        StockUpdate event = new StockUpdate("SKU-7", 3, 1);
        when(feed.stream("SKU-7")).thenReturn(Flux.just(event));

        Flux<GraphQlTester.Response> responses =
                tester.document(SUBSCRIPTION)
                        .variable("sku", "SKU-7")
                        .executeSubscription()
                        .toFlux();

        StepVerifier.create(responses)
                .assertNext(response -> {
                    response.path("stockUpdated.sku")
                            .entity(String.class)
                            .isEqualTo("SKU-7");
                    response.path("stockUpdated.quantity")
                            .entity(Integer.class)
                            .isEqualTo(3);
                    response.path("stockUpdated.sequence")
                            .entity(Integer.class)
                            .isEqualTo(1);
                })
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-7");
    }

    @Test
    void cancellingAfterTwoEventsStopsLongLivedSource() {
        StockUpdate first = new StockUpdate("SKU-7", 3, 1);
        StockUpdate second = new StockUpdate("SKU-7", 5, 2);

        AtomicBoolean cancelled = new AtomicBoolean(false);
        Flux<StockUpdate> source = Flux.concat(
                Flux.just(first, second),
                Flux.<StockUpdate>never()
        ).doOnCancel(() -> cancelled.set(true));

        when(feed.stream("SKU-7")).thenReturn(source);

        StepVerifier.create(updates("SKU-7").take(2))
                .expectNext(first, second)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertTrue(cancelled.get(), "upstream should receive cancellation");
        verify(feed).stream("SKU-7");
    }
}
~~~

### Why is each test valuable?

| Test | Key verification | Bugs it catches |
| --- | --- | --- |
| Two ordered events | Record contents, `sequence=1,2`, completion | Wrong values, missing event, swapped order, non-completing stream |
| `sku` variable | Argument mapping and dependency receives right SKU | Hardcoded SKU or misbound GraphQL variable |
| Empty feed | Zero `onNext` and clean `onComplete` | Fabricating non-existent items, hanging subscription |
| Inspect response fields | Per-event GraphQL serialization/selection set | Wrong field name, numeric/string type mismatch, mapping/schema drift |
| Cancel after 2 events | Downstream `take(2)` propagates cancel upstream | Stream leaking resources after client stops reading |

**Do not stop at Mockito `verify(feed).stream(...)`:** the Java method may be called when GraphQL obtains the Publisher, yet that does not guarantee **events reached downstream**. `StepVerifier` subscribes and asserts each emitted item.

**Do not rely only on `expectNextCount(2)`:** it checks item count without distinguishing `quantity=3` from `quantity=-99` or swapped sequences. When values carry meaning, assert exact records or fields.

### Limitations of slice tests

`cancellingAfterTwoEventsStopsLongLivedSource` proves cancellation along the **server-side GraphQL execution path**. It **does not prove** that a real WebSocket client sends a proper complete/cancel frame or that an external broker unsubscribes; those layers need integration tests and dedicated observability.

The slice class does not use `@SpringBootTest` and performs no WebSocket handshake. `GraphQlTester` succeeding here does not guarantee `spring.graphql.websocket.path` is enabled in deployment.

## 8. Testing real transport: WebSocketGraphQlTester and RANDOM_PORT

When you need to verify that **a subscription is sent from a client and the server streams events over a real WebSocket**, write an integration test with the server listening on a random port.

**File `src/test/java/com/example/graphqlsub/StockSubscriptionWebSocketTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockSubscriptionWebSocketTest {

    private static final String SUBSCRIPTION = """
            subscription WatchStock($sku: ID!) {
              stockUpdated(sku: $sku) {
                sku quantity sequence
              }
            }
            """;

    @LocalServerPort
    int port;

    @Test
    void streamsTwoEventsOverActualWebSocket() {
        String url = "ws://127.0.0.1:" + port + "/graphql";

        WebSocketGraphQlTester tester = WebSocketGraphQlTester.builder(
                url,
                new ReactorNettyWebSocketClient()
        ).build();

        try {
            Flux<StockUpdate> events = tester.document(SUBSCRIPTION)
                    .variable("sku", "SKU-7")
                    .executeSubscription()
                    .toFlux("stockUpdated", StockUpdate.class);

            StepVerifier.create(events)
                    .expectNext(
                            new StockUpdate("SKU-7", 3, 1),
                            new StockUpdate("SKU-7", 5, 2)
                    )
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        } finally {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }

    @Test
    void unknownSkuCompletesWithoutAnEventOverWebSocket() {
        String url = "ws://127.0.0.1:" + port + "/graphql";
        WebSocketGraphQlTester tester = WebSocketGraphQlTester.builder(
                url,
                new ReactorNettyWebSocketClient()
        ).build();

        try {
            Flux<StockUpdate> events = tester.document(SUBSCRIPTION)
                    .variable("sku", "UNKNOWN")
                    .executeSubscription()
                    .toFlux("stockUpdated", StockUpdate.class);

            StepVerifier.create(events)
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        } finally {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }
}
~~~

### Key differences from @GraphQlTest

- `RANDOM_PORT` starts a **real WebFlux HTTP/WebSocket server**. `@LocalServerPort` supplies the dynamic port so tests never hardcode `8080`.
- `WebSocketGraphQlTester` connects to `ws://.../graphql` using `ReactorNettyWebSocketClient`; the server configures `spring.graphql.websocket.path=/graphql`.
- This is a **real socket test**: if the endpoint is disabled, handshake/subprotocol fails, or the handler fails to push events to the transport, the test fails.
- The integration test uses the **real `DeterministicStockFeed`** in the Spring context without Mockito mocks. Outcomes remain predictable because the feed needs no broker.
- `stop()` returns **`Mono<Void>`**: calling `tester.stop();` without subscribing may leave the connection open. In test cleanup, `block(Duration.ofSeconds(5))` ensures the WebSocket session closes; **never call `block()` inside production reactive handlers**.
- `WebSocketGraphQlTester` can multiplex multiple operations over one connection. The example intentionally creates a dedicated tester per test for isolation; a large suite may share and clean up at class level if needed for performance.

**Never claim WebSocket transport is tested just because `@GraphQlTest` returns the right items.** Conversely, when a WebSocket integration test FAILS, run the slice test first: a passing slice with a failing WebSocket test points toward endpoint, property, protocol, security, or handshake issues rather than serialization or resolver logic.

## 9. Pure Publisher unit tests: checking upstream errors without guessing GraphQL error shapes

At the Reactor layer, a source can signal `onError`. However, GraphQL Java and its transport build **GraphQL errors**; the error observed by the client does not necessarily retain the original upstream exception class or message.

Therefore, when you want to verify a **Publisher's error policy**, write a unit test directly against the `Flux`. Do not assert `IllegalStateException` by default on the WebSocket client without first defining the GraphQL API's error contract.

**File `src/test/java/com/example/graphqlsub/StockSubscriptionUnitTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StockSubscriptionUnitTest {

    @Test
    void controllerReturnsPublisherFromFeed() {
        StockFeed fake = sku -> Flux.just(
                new StockUpdate(sku, 3, 1)
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(fake);

        StepVerifier.create(controller.stockUpdated("SKU-7"))
                .expectNext(new StockUpdate("SKU-7", 3, 1))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void upstreamFailureIsVisibleToRawPublisherSubscriber() {
        StockFeed failing = sku -> Flux.error(
                new IllegalStateException("feed unavailable")
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(failing);

        StepVerifier.create(controller.stockUpdated("SKU-7"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "feed unavailable".equals(
                                        error.getMessage()
                                ))
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void independentSubscribersReceiveTheSameColdDemoEvents() {
        StockFeed cold = sku -> Flux.just(
                new StockUpdate(sku, 3, 1),
                new StockUpdate(sku, 5, 2)
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(cold);

        Flux<StockUpdate> events = controller.stockUpdated("SKU-7");
        assertEquals(2L, events.count().block(Duration.ofSeconds(5)));

        StepVerifier.create(events)
                .expectNext(
                        new StockUpdate("SKU-7", 3, 1),
                        new StockUpdate("SKU-7", 5, 2)
                )
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

The final case intentionally exercises a **cold demo publisher**: two independent subscriptions receive the same event sequence. `events.count().block(...)` is called **only inside a unit test** to count items once; never call `block()` in a production WebFlux controller. If the source is a hot `Sinks.Many`, two subscribers can observe different event windows, so cold-source tests must not be taken as a hot-stream contract.

## 10. Emitted data: asserting values, ordering, types, and schema boundaries

Testing a subscription event means more than counting items. Given the GraphQL SDL in section 4, establish the contract:

| Property | Assertion to include | Risk if omitted |
| --- | --- | --- |
| `sku` | Must match the subscribed `sku` | Cross-customer/cross-tenant data leak |
| `quantity` | Must match business value and fit `Int` range | Mapping bug, wrong stock count |
| `sequence` | Strictly increasing if API promises ordering | Client applies updates out of order |
| Event count | Exactly 2 events for the finite demo | Missing or duplicate notifications |
| Nullability | Never violates SDL non-null types | GraphQL errors / null propagation |
| GraphQL selection set | Only requested fields appear in `data` | Schema/resolver/serialization drift |
| Completion | Finite demo completes cleanly | Hanging test, missing cleanup |
| Cancellation | Infinite stream stops when client disconnects | Publisher/broker listener leaks |

In slice tests, use `expectNext(first, second)` when the Java record implements component-wise `equals`. To inspect **individual GraphQL responses** instead of decoded POJOs, use `executeSubscription().toFlux()` and `response.path("stockUpdated.quantity").entity(Integer.class).isEqualTo(...)`, as shown in the example.

### Verifying feed filtering

A subscription scoped by `sku` must not emit events for other SKUs. While the demo builds events directly from the parameter via `new StockUpdate(sku,...)`, checking the `sku` variable suffices for the demo. With a production source backed by a shared event bus, test **filtering in the feed or resolver**:

~~~java
// Illustrative snippet inside a real service:
return allStockUpdates
        .filter(update -> sku.equals(update.sku()));
~~~

This snippet **is not a standalone Java file**. If `allStockUpdates` emits three items in order `SKU-7`, `SKU-9`, `SKU-7`, the test should receive **only the two `SKU-7` items** in their original relative order. When tenants or users are involved, enforce filtering/authorization at the proper security boundary; never rely solely on client-supplied SKU filtering for security.

### GraphQL errors are not HTTP 500 per emitted item

A GraphQL operation can receive a response containing `errors` even when the HTTP request status was 200. Over WebSockets, each payload is a GraphQL execution result and errors travel inside protocol messages rather than a fresh HTTP status code. `toFlux("stockUpdated", StockUpdate.class)` applies path/type assertions and will fail if the response contains GraphQL errors or lacks required data.

When the **contract expects a GraphQL error**, use `toFlux()` to inspect `Response.errors()` via `GraphQlTester`'s API, or assert the error envelope defined by your transport/protocol. Never write `expectError(IllegalStateException.class)` on a WebSocket tester merely because the raw upstream threw `IllegalStateException`; verify the error resolver mapping before asserting.

## 11. Testing completion, cancellation, and long-lived subscriptions

For the two events in the demo, `expectComplete()` is appropriate. However, production event sources typically **never complete on their own** while a user keeps a subscription open.

Do not write:

~~~java
// Unsuitable if the stream is long-lived and never completes:
StepVerifier.create(liveUpdates)
        .expectNextCount(2)
        .verifyComplete();
~~~

On an infinite stream, `verifyComplete()` will hang until timeout. If you only need the first two events:

~~~java
StepVerifier.create(liveUpdates.take(2))
        .expectNext(first, second)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

`take(2)` emits two items and then **cancels upstream** once satisfied—the desired behavior when a test only checks two events. Use `doOnCancel(...)` or `PublisherProbe` at the producer layer to prove subscription cleanup. Never assume cancellation inside a GraphQL slice test automatically proves WebSocket frames and broker unsubscription in production.

To test cancellation **before any event arrives**:

~~~java
StepVerifier.create(Flux.<StockUpdate>never())
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

This is a pure Reactor illustration: a publisher emitting nothing is actively cancelled by the test without waiting forever.

### Timeouts must be meaningful

- Finite streams should carry a bounded test timeout, e.g., `.expectComplete().verify(Duration.ofSeconds(5))`.
- Long-lived streams should use `take(n)`, `thenCancel()`, or contract-defined cancellation.
- Never use `Thread.sleep(...)` to wait for events; with a controllable test producer, use `StepVerifier` and deterministic publishers.
- When tests run against a real message broker and network, timeouts should match CI/environment realities rather than masking race conditions with larger sleeps.
- Never apply `timeout(Duration...)` to a production stream just to make tests PASS if that alters application semantics.

## 12. Virtual time and backpressure: when are they needed?

If a producer uses `Flux.interval(...)` to emit events periodically, tests waiting in real wall-clock time become slow and flaky. Project Reactor Test provides `StepVerifier.withVirtualTime(...)`, ideal for **time-based operators** when the source is created inside the supplier after the virtual scheduler is active.

Pure Reactor example, independent of Spring context:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2)
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(1L)
        .verifyComplete();
~~~

This is an illustrative code body requiring imports for `Duration`, `Flux`, and `StepVerifier`. It verifies `0L` after the first tick and `1L` after the second tick with zero real sleep. If the source or timer was constructed **before** the supplier, virtual time cannot control its scheduler as intended.

### Backpressure is not "one WebSocket event equals one request(n)"

Reactive Streams has `request(n)`, `onNext`, and cancellation, yet GraphQL WebSocket transport adds protocol frames, buffering, and per-result mapping. **Do not assume each network frame maps 1-to-1 to a `request(1)` call**.

- At the producer/service layer: use `StepVerifier.create(flux, 0).thenRequest(1)` when testing controlled demand.
- At the GraphQL response layer: assert events and order, adding stress tests with larger payloads when needed.
- At the transport/broker layer: verify buffer limits, slow-client behavior, and drop/replay/durable-delivery policies separately.

Demand example:

~~~java
StepVerifier.create(
        Flux.just("first", "second"),
        0
)
        .thenRequest(1)
        .expectNext("first")
        .thenRequest(1)
        .expectNext("second")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

This is also a **pure Reactor illustration** and does not test a real GraphQL WebSocket connection. Use it when backpressure is part of the contract, rather than adding it ceremonially to every subscription test.

## 13. Hot vs. cold: common pitfalls when using Sinks.Many

### Cold source

`Flux.just(...)` and `Flux.defer(...)` produce data per subscription; every new subscriber can receive the same demo sequence. Tests expecting `event1, event2, complete` are highly deterministic.

### Hot source

Real sources may be `Sinks.Many<StockUpdate>`, Kafka, Redis pub/sub, or change streams. Events are emitted over time, **can be missed if the subscriber has not actually subscribed yet**, and different subscribers can join at different points.

Illustrative producer snippet:

~~~java
Sinks.Many<StockUpdate> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<StockUpdate> events = sink.asFlux();
~~~

This is illustrative Reactor code requiring `reactor.core.publisher.Sinks`; **it is not a complete subscription lifecycle setup**. Calling `sink.tryEmitNext(event)` before the client or `StepVerifier` actually subscribes can miss the intended product scenario, and buffering/dropping depends on sink type. Never use `Thread.sleep(500)` to guess that a subscription is active.

To test a real event bus:

1. Start the subscription/`StepVerifier` or client and confirm **the subscriber is ready** (latch, handshake acknowledgement, or producer-provided hook).
2. Only then emit test events into the source.
3. Assert exact events and ordering.
4. Cancel/close the connection and verify the source cleans up its registration.
5. Avoid sharing mutable sinks across parallel test classes without isolation.

`Sinks.many().replay().limit(n)` has different replay semantics from `multicast`; pick according to your contract for client reconnects and missed events. Never assume every GraphQL subscription is a reliable queue: GraphQL does not guarantee exactly-once delivery, history retention, or replay across disconnects.

## 14. Multiple subscribers, security, and customer data

In production, the question is not only whether events emit, but **who is allowed to receive which events**.

### Partitioning by SKU/tenant/user

If a client subscribes to SKU A and receives a SKU B event, that is a filtering bug. If a user in tenant X receives a tenant Y event, that can be a severe security vulnerability. Verify with **two concurrent subscriptions**:

| Subscriber | Variables | Events expected | Events forbidden |
| --- | --- | --- | --- |
| Client A | `sku="A"`, tenant X | Updates for A in X | B or tenant Y |
| Client B | `sku="B"`, tenant X | Updates for B in X | A or tenant Y |
| Client C | Tenant Y | Only tenant Y events | Tenant X events |

Never rely solely on `@Argument String sku` from the client to make authorization decisions. In real Spring GraphQL apps, use the authentication principal, GraphQL context, `WebGraphQlInterceptor`, or service-level authorization. Tests must prove **the server never emits unauthorized events**, not merely that the frontend hides them.

### WebSocket auth differs from short-lived HTTP queries

- WebSockets have a **connection handshake**; credentials may be passed in headers or the `connection_init` payload depending on protocol and client.
- Long-lived connections can outlive token expiration or permission changes. Design and test re-authentication and reconnect policies.
- **Do not** assume every `@PreAuthorize` or HTTP filter automatically re-applies cleanly to every streamed event. Verify actual application behavior both at subscription start and on event emission.
- When a client cancels/disconnects, verify listeners and broker subscriptions are disposed.
- If using CORS or cross-origin browser WebSockets, test origin policies, cookies, and sessions matching production deployment.

### Client reconnect and missed events

Reconnect tests should answer: are past events replayed, are cursors/sequence numbers used, can duplicates happen, and how do clients achieve idempotency? Do not assume the GraphQL transport provides exactly-once delivery. For durable delivery guarantees, add broker integration tests and explicit offset/replay policies.

## 15. When errors happen: raw Publisher errors, GraphQL errors, and transport failures

Three error layers are often conflated:

| Error source | Example | Testing approach |
| --- | --- | --- |
| **Raw Publisher** | `Flux.error(new IllegalStateException(...))` | Unit test `StepVerifier.expectErrorMatches` on `Flux` |
| **GraphQL execution/schema** | Non-null field/type violation, resolver exception, invalid document/variables | `GraphQlTester` tests for response errors/paths and contract error resolver |
| **WebSocket/transport** | Endpoint disabled, handshake failure, protocol mismatch, client disconnect | `WebSocketGraphQlTester` integration verifying failure/reconnect/cleanup |

`@SubscriptionMapping` returning `Flux.error(...)` does not mean WebSocket sends the `IllegalStateException` class verbatim. GraphQL Java/Spring for GraphQL converts it into a GraphQL error payload; many setups also mask internal messages to prevent leaks. To test a stable error code, implement an appropriate `DataFetcherExceptionResolver` or GraphQL error extensions first.

**Do not assert HTTP status 200 for individual subscription events over WebSocket.** After the handshake (HTTP upgrade), payloads flow as WebSocket messages; observe GraphQL success/errors at the GraphQL protocol layer rather than HTTP status per event.

When a subscription test hangs:

1. Verify `spring.graphql.websocket.path` and the schema.
2. Confirm the document starts with `subscription` and matches the root field.
3. Check whether upstream emits `onNext` or `onComplete`; `Flux.never()` never completes on its own.
4. Ensure the test subscribes via `StepVerifier.verify(...)`.
5. For hot sources, ensure events are emitted only after the subscription is registered.
6. Check security/`connection_init`, broker readiness, and WebSocket tester cleanup.
7. If decoded output is empty or fails, inspect the GraphQL `data`/`errors` response and selection set.

## 16. Running tests and interpreting results

From the project directory containing the Gradle Wrapper (Java 17+):

~~~bash
./gradlew test --tests "com.example.graphqlsub.StockSubscriptionUnitTest"
./gradlew test --tests "com.example.graphqlsub.StockGraphQlSliceTest"
./gradlew test --tests "com.example.graphqlsub.StockSubscriptionWebSocketTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.graphqlsub.StockSubscriptionUnitTest"
.\gradlew.bat test --tests "com.example.graphqlsub.StockGraphQlSliceTest"
.\gradlew.bat test --tests "com.example.graphqlsub.StockSubscriptionWebSocketTest"
~~~

Based on the code above, there are **3 unit tests + 5 GraphQL slice tests + 2 WebSocket integration tests = 10 test methods**. With proper dependencies, WebSocket endpoint, and schema, all assertions are expected to PASS. **This is an expectation from code analysis, not a JUnit log executed at authoring time.** Tests contain no `System.out.println`, so there is no fixed app stdout; Gradle/Spring logging varies with configuration.

If CI restricts opening sockets or loopback networking, unit and slice tests can still run while the WebSocket integration test may hit infrastructure errors. Never "fix" that by deleting transport tests and claiming WebSockets are tested. Provision an appropriate test environment instead.

### An emission sequence worth verifying

~~~text
GraphQL document accepted
  -> resolver selected with sku="SKU-7"
  -> feed returns Publisher
  -> downstream subscribes
  -> event #1: SKU-7, 3, sequence 1
  -> event #2: SKU-7, 5, sequence 2
  -> stream completes (demo only)
  -> client test completes successfully
~~~

For long-lived sources, replace "stream completes" with "client cancels and publisher releases resources" per contract. Never demand completion from a production subscription intentionally designed to run continuously.

## 17. Common mistakes and fixes

1. **Calling `execute()` instead of `executeSubscription()`.** Fails to test the response stream properly. **Fix:** use `toFlux(...)` with `StepVerifier`.
2. **Calling the controller method returning `Flux` and assuming events emitted.** Nobody subscribed. **Fix:** subscribe and verify signals.
3. **Using `expectNextCount(2)` without inspecting values.** Lets wrong SKUs, quantities, or sequences slip through. **Fix:** `expectNext(expected...)` or field assertions.
4. **Calling `verifyComplete()` on an infinite stream.** Test hangs. **Fix:** `take(n)` or `thenCancel()` with a timeout.
5. **Testing only controller unit tests and claiming WebSockets work.** Skips handshake and subprotocol. **Fix:** add `WebSocketGraphQlTester` integration tests.
6. **Testing only the WebSocket happy path without authorization/multi-tenant checks.** Risks data leaks. **Fix:** add per-user/per-SKU subscriptions and negative tests.
7. **Forgetting `spring.graphql.websocket.path`.** The WebSocket endpoint is disabled by default. **Fix:** configure the endpoint and verify properties.
8. **Mixing `spring-boot-starter-web` and WebFlux without checking the web stack.** Spring Boot may pick MVC when both are on the classpath. **Fix:** choose the intended stack; Servlet WebSockets require a separate starter.
9. **Missing `spring-graphql-test` or `reactor-test`.** Test classes lack `GraphQlTester`/`StepVerifier`. **Fix:** add test dependencies matching the major version.
10. **Using `@Mock` instead of a Spring mock bean in `@GraphQlTest`.** Resolver lacks its collaborator. **Fix:** use Spring Framework 6.2+'s `@MockitoBean`.
11. **Assuming `@GraphQlTest` scans all services/configurations.** The slice is scoped. **Fix:** mock or import required beans explicitly.
12. **Emitting into a hot sink before subscribing.** Tests randomly miss events. **Fix:** synchronize on subscription readiness before emitting.
13. **Comparing raw producer Java exceptions against WebSocket errors.** GraphQL applies error mapping. **Fix:** assert the contract at each layer separately.
14. **Calling `block()` or `subscribe()` inside `@SubscriptionMapping`.** Breaks reactive composition and risks blocking the event loop. **Fix:** return the Publisher directly.
15. **Forgetting to stop `WebSocketGraphQlTester`.** Sessions/threads/resources can linger after the test. **Fix:** call `stop()` and subscribe to the cleanup `Mono`.
16. **Concluding a hot stream replays events because cold tests replay them.** Wrong source semantics. **Fix:** test reconnects and late subscribers against the real sink/broker behavior.
17. **Equating GraphQL subscriptions with SOAP eventing.** Two distinct protocols. **Fix:** test each system's operations, schemas, and transports properly.
18. **Skipping cancellation tests.** Long-lived sources risk leaking broker listeners after clients leave. **Fix:** verify via `doOnCancel`/probes or integration observation.
19. **Asserting strict global event order when parallel backend fan-out offers no ordering guarantee.** Causes flaky tests or false contracts. **Fix:** enforce ordering via sequences/cursors where required by the product.
20. **Confusing GraphQL WebSocket with HTTP SSE.** Testers and transports have different semantics. **Fix:** choose the matching transport tester and state exact verified scope.

## 18. Pre-completion checklist for subscription tests

- [ ] Does the SDL define root `type Subscription` with a field matching `@SubscriptionMapping`?
- [ ] Does the GraphQL operation send `subscription` with the right selection set and variables?
- [ ] Does `@GraphQlTest` load the real resolver while intentionally mocking/importing out-of-slice collaborators?
- [ ] Does the test call `executeSubscription().toFlux(...)` and actually subscribe with `StepVerifier`?
- [ ] Does it assert per-event SKU/ID, quantity, sequence, and expected item count?
- [ ] Are zero-event cases, multi-event cases, and invalid/varying arguments covered?
- [ ] For finite streams, does the test expect completion with a bounded timeout?
- [ ] For long-lived streams, does the test cancel and observe cleanup instead of waiting forever for completion?
- [ ] Do I distinguish raw Publisher errors from GraphQL execution errors and transport errors?
- [ ] Do integration tests enable the WebSocket endpoint, use a random port, and connect with a real client tester?
- [ ] Is `WebSocketGraphQlTester.stop()` subscribed/awaited during cleanup?
- [ ] Do I avoid assuming hot streams replay or emitting before subscriber readiness in live delivery tests?
- [ ] Do I avoid assuming each WebSocket event maps to an HTTP status or exact `request(n)` call?
- [ ] Are tenant/user isolation and authorization tested when subscriptions carry sensitive data?
- [ ] Do event sources use isolated test data without hitting production brokers or depending on test execution order?
- [ ] Have I kept GraphQL subscriptions distinct from SOAP XML request-response or custom SOAP eventing?

**Key takeaway:** Testing GraphQL subscriptions does not end at "the resolver returns a `Flux`." **Subscribe to the stream, verify each emitted event, test completion and cancellation, and be explicit about whether you verified live WebSocket transport or server-side GraphQL execution.** Use `@GraphQlTest` for fast, focused contracts; use `WebSocketGraphQlTester` + `RANDOM_PORT` when proving live socket connectivity and event delivery.

### Official references

- [Spring Boot 3.5 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.5/reference/web/spring-graphql.html)
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL — Testing and Subscriptions](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL 1.4 — GraphQlTester.Subscription API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/test/tester/GraphQlTester.Subscription.html)
- [Spring for GraphQL 1.4 — WebSocketGraphQlTester API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/test/tester/WebSocketGraphQlTester.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [GraphQL Specification — Subscription Operations](https://spec.graphql.org/October2021/#sec-Subscription)