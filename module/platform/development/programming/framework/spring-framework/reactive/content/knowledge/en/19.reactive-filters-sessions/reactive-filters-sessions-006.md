# Request Attributes and How They Differ from Reactor Context

In **Spring WebFlux**, a request can pass through many WebFilters, controllers, and services before completing. Those components sometimes need to share metadata such as a request ID, resolved tenant, locale information, or data verified by a filter. Spring provides two common mechanisms that have different scopes:

- **Request attributes** belong to a specific ServerWebExchange object. They are suitable for a WebFilter to set data and then a controller or another component to read it back within the same HTTP request.
- **Reactor Context** belongs to a reactive subscription. It propagates metadata along the subscriber chain, even when the pipeline switches schedulers/threads, and is read via ContextView.

These two mechanisms do not synchronize with each other automatically. Calling contextWrite does not automatically write into exchange.getAttributes(); setting a request attribute also does not automatically create a key in Reactor Context. Spring has a separate bridge to put the ServerWebExchange itself into Reactor Context, but that bridge does not automatically copy all request attributes.

## 1. Learning Objectives

After this lesson, you can:

1. Explain where request attributes are stored and how their lifecycle is tied to the HTTP exchange.
2. Set a request attribute in a WebFilter and read it with ServerWebExchange or @RequestAttribute.
3. Explain that Reactor Context is data per subscriber/subscription, not a per-thread variable.
4. Use contextWrite, deferContextual, and ContextView to pass/read metadata in a reactive pipeline.
5. Distinguish the propagation direction of Context from the emission direction of onNext/onError/onComplete signals.
6. Understand ServerWebExchangeContextFilter and how to get the exchange from Reactor Context when that filter is present.
7. Choose the right mechanism for request metadata, tracing, security, transactions, and business data.
8. Avoid mistakes such as subscribing yourself, holding an exchange in a singleton, sharing mutable state, or expecting request attributes to appear automatically in Reactor Context.
9. Test request isolation and context propagation with WebTestClient and StepVerifier.

## 2. What Are Request Attributes?

In WebFlux, each HTTP request is represented by a ServerWebExchange. The exchange holds the request, response, session, and a map of attributes used within the scope of the current request.

Important APIs:

~~~java
Map<String, Object> attributes = exchange.getAttributes();

exchange.getAttributes().put("app.requestId", "req-42");

String requestId =
    exchange.getAttribute("app.requestId");

String tenant =
    exchange.getAttributeOrDefault("app.tenant", "public");
~~~

- getAttributes() returns the mutable map of the current exchange.
- getAttribute(name) reads the attribute if it exists; the value may be null.
- getRequiredAttribute(name) reads a required value and throws an error if it does not exist.
- getAttributeOrDefault(name, defaultValue) reads or returns a default value.

Request attributes are usually created by server-side code: a WebFilter, a handler, or a component processing the request before the controller. For example, a filter validates a header, looks up the tenant from the host, generates a request ID, or stores request-analysis results for the controller to use.

**A request attribute is not an HTTP header and does not come directly from the client.** The client only sends data through the protocol such as path, query, headers, cookies, and body. Server code decides whether to put that data into exchange attributes. If a value is derived from client input, you still must validate it and apply trust rules before using it.

### 2.1. Lifecycle and Scope

Request attributes are tied to one ServerWebExchange:

~~~text
HTTP request A
    |
    v
ServerWebExchange A
    |
    +-- attributes: requestId=A
    +-- attributes: tenant=tenant-1
    |
    +-- WebFilter
    +-- Controller
    +-- Service (if passed exchange/value)
    |
    v
Response A completes
~~~

Request B has its own exchange and its own attributes map. You should not save a request attribute into a field of a singleton bean and use it for the next request. Nor should you keep a ServerWebExchange in a cache/global map after the request ends.

Request attributes are a mutable map. Even though an exchange belongs to one request, a pipeline can have multiple asynchronous callbacks. Write data at one clear step before calling the next chain, prefer immutable values, and avoid multiple concurrent branches mutating the same map or mutable object.

### 2.2. Reading an Attribute in a Controller with @RequestAttribute

Spring WebFlux supports @RequestAttribute to retrieve an attribute created earlier, for example by a WebFilter:

~~~java
@GetMapping("/debug/request")
Mono<String> debug(
        @RequestAttribute("app.requestId") String requestId) {
    return Mono.just("requestId=" + requestId);
}
~~~

If the attribute is optional, you can declare required=false or use Optional according to the parameter type and appropriate resolver:

~~~java
@GetMapping("/debug/optional")
Mono<String> debugOptional(
        @RequestAttribute(
            name = "app.client", required = false
        ) Optional<String> client) {
    return Mono.just(client.orElse("unknown"));
}
~~~

If the attribute is required but the filter did not set it, the argument resolver cannot supply a value and the request enters error handling. This is usually a configuration/lifecycle mistake: the filter is not registered, the filter order is unsuitable, or the key between writer and reader does not match.

### 2.3. Reading Directly via ServerWebExchange

When a handler needs multiple attributes or needs to operate on the response/request, receive the exchange directly:

~~~java
@GetMapping("/debug/exchange")
Mono<Map<String, String>> debug(ServerWebExchange exchange) {
    String requestId =
        exchange.getAttributeOrDefault("app.requestId", "missing");

    String path = exchange.getRequest().getURI().getPath();

    return Mono.just(Map.of(
        "requestId", requestId,
        "path", path
    ));
}
~~~

This approach is explicit and convenient when you need the request/response/session. However, if a service only needs the request ID, passing a String or a metadata DTO is usually easier to test and reduces coupling to Spring WebFlux compared to passing the whole ServerWebExchange deep into the business layer.

## 3. Creating Request Attributes in a WebFilter

WebFilter is the natural place to create or normalize metadata before a request reaches the controller. The filter receives ServerWebExchange and WebFilterChain:

~~~java
@Component
class RequestMetadataFilter implements WebFilter {

    static final String REQUEST_ID_ATTRIBUTE = "app.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(
            REQUEST_ID_ATTRIBUTE, requestId
        );

        return chain.filter(exchange);
    }
}
~~~

The example above generates a new ID for each request. Because the attribute is set **before** the chain.filter(exchange) call, subsequent filters/controllers can read it.

If you need to accept an ID sent by the client, validate the format and limit its length before using it. For example:

~~~java
String candidate =
    exchange.getRequest().getHeaders().getFirst("X-Request-Id");

String requestId =
    candidate != null && candidate.matches("[A-Za-z0-9._-]{1,64}")
        ? candidate
        : UUID.randomUUID().toString();

exchange.getAttributes().put(
    RequestMetadataFilter.REQUEST_ID_ATTRIBUTE, requestId
);
~~~

Do not put an unvalidated header string directly into logs or responses. Control characters/newlines can cause log injection or create issues in downstream systems.

### 3.1. Filter Chain and Order

WebFilters are called in a chain. An outer filter can prepare data before delegating; later filters and the controller read the prepared data.

~~~text
Request
  |
  v
Filter A: creates requestId
  |
  v
Filter B: checks/writes tenant
  |
  v
DispatcherHandler
  |
  v
Controller
  |
  v
Response
~~~

If filter B needs data created by filter A, you must ensure A runs before B via appropriate order configuration. Do not rely on the random order of bean discovery. When a value depends on authentication, place the filter after the corresponding authentication step; do not arbitrarily choose the highest precedence if that makes the filter run before security.

### 3.2. Returning the Publisher from the Filter

A WebFilter must return Mono<Void> representing the entire request processing:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    exchange.getAttributes().put("app.started", Boolean.TRUE);

    return chain.filter(exchange)
        .doOnSuccess(ignored ->
            exchange.getAttributes().put("app.completed", Boolean.TRUE)
        );
}
~~~

This is a snippet illustrating the lifecycle. Do not call chain.filter(exchange).subscribe() inside a filter. Calling subscribe manually creates a secondary subscription, detaching the lifecycle from the main request and making error/cancellation propagation difficult. Return the composed publisher so WebFlux manages the subscription.

## 4. What Is Reactor Context?

Reactor Context is a key-value context attached to a subscriber/subscription in Reactor. It is designed to carry metadata across a reactive chain without needing to pass the same parameter through every lambda.

Commonly used types/APIs:

| API | Role |
| --- | --- |
| Context | A context that can be created/updated with immutable operations such as put, delete, putAll. |
| ContextView | A read-only view, used to read existing keys. |
| contextWrite(...) | Creates a new Context for upstream operators at the position where it is placed. |
| Mono.deferContextual(...) | Reads the subscription's Context when the publisher is subscribed. |
| Flux.deferContextual(...) | Same for Flux. |
| view.get(key) | Gets the value; throws an error if the key does not exist. |
| view.getOrDefault(key, fallback) | Gets the value or fallback. |
| view.hasKey(key) | Checks whether the key exists. |

Pure Reactor example:

~~~java
static final String REQUEST_ID_KEY = "app.requestId";

Mono<String> result = Mono.deferContextual(view -> {
    String requestId =
        view.getOrDefault(REQUEST_ID_KEY, "missing");

    return Mono.just("requestId=" + requestId);
}).contextWrite(context ->
    context.put(REQUEST_ID_KEY, "req-42")
);
~~~

When subscribed, the publisher reads the value req-42. That value is not stored in a specific thread; it lives in the subscription's Context.

### 4.1. Context Is Not ThreadLocal

ThreadLocal binds data to the current Java thread. Reactor Context binds data to the subscriber chain.

~~~text
ThreadLocal:
  Thread A -> value A
  Thread B -> value B or null

Reactor Context:
  Subscription A -> requestId=A
  Subscription B -> requestId=B
~~~

A reactive chain can run across multiple threads due to publishOn, subscribeOn, or asynchronous I/O. Context can still be read accurately across Reactor operators because it is passed along the subscription. Plain ThreadLocal does not automatically follow the request when a callback switches threads.

Context is also not a global variable: the same Mono can be subscribed multiple times with different Contexts. This lets each request keep its own metadata as long as the application does not share mutable objects inside Context itself.

### 4.2. Context Is Immutable, but Values Can Be Mutable

Operations like put/delete create a new Context; they do not mutate a shared Context:

~~~java
Context first = Context.of("app.requestId", "A");
Context second = first.put("app.requestId", "B");

// first still has A; second has B.
~~~

However, the stored value can be a mutable object. If you put a HashMap, list, or stateful shared object into Context and mutate it from multiple callbacks, there is still a risk of race conditions. Prefer String, UUID, immutable DTOs, or small values with a clear lifecycle.

### 4.3. Which Direction Does Context Propagate?

Data signals normally flow from source to subscriber:

~~~text
source -- onNext --> map --> flatMap --> subscriber
~~~

Context is provided during subscription in the opposite direction, from downstream to upstream:

~~~text
subscriber -- Context --> contextWrite --> flatMap --> map --> source
~~~

Therefore contextWrite is usually placed **downstream** of the code that needs to read Context. For example:

~~~java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("app.mode", "default"))
);

Mono<String> result = source
    .contextWrite(context -> context.put("app.mode", "request"));
~~~

The source sees the value request. If contextWrite is placed upstream of the operator that needs to read, the new Context may not be in the subscription context that the operator sees.

## 5. How Do Request Attributes and Reactor Context Differ?

| Criterion | Request attributes | Reactor Context |
| --- | --- | --- |
| Where stored | ServerWebExchange map | Subscriber/subscription Context |
| Scope | One HTTP exchange | One reactive subscription |
| Data type | Mutable map | Immutable Context structure; values can still be mutable |
| How to write | exchange.getAttributes().put(...) | contextWrite(...) |
| How to read | getAttribute(...), @RequestAttribute | deferContextual(...), ContextView |
| Thread switching | Does not rely on threads; accessed via exchange | Follows Reactor's subscriber chain |
| Who can read | Components with the exchange or argument resolver | Operators/publishers with ContextView |
| Automatic sync | No | No |
| Suitable use | Filter-to-controller metadata within one request | Tracing, transaction/security context, and metadata across a reactive chain |

### 5.1. When to Use Request Attributes?

Use request attributes when:

- A WebFilter has analyzed the request and wants the controller to read back the result.
- You need to store information directly related to ServerWebExchange, such as a routing decision or metadata created by a filter.
- The controller needs to access data via @RequestAttribute.
- One HTTP-handling component needs to share a result with another component in the same exchange.

Example: a filter resolves the tenant from a verified host and saves the tenant ID in the exchange; the controller reads the tenant using @RequestAttribute.

### 5.2. When to Use Reactor Context?

Use Reactor Context when:

- Multiple operators/services in the same reactive subscription need a correlation ID.
- You need to pass tracing/transaction/security metadata across flatMap or schedulers.
- You do not want to pass the same metadata through many lambdas just to serve a cross-cutting concern.
- A reactive library/framework already has integration with Reactor Context.

Example: a service uses Mono.deferContextual to get the trace ID and attach it to telemetry or a reactive client.

### 5.3. When to Pass Explicit Parameters?

If data is business input, pass it via parameters or a DTO:

~~~java
Mono<Order> createOrder(
        String tenantId,
        CreateOrderCommand command) {
    // ...
}
~~~

The tenant ID in the example is part of the business contract and needs permission checking. Putting all data into Reactor Context makes dependencies harder to see and harder to test. Context suits cross-cutting metadata; explicit parameters suit data that logic needs to decide the outcome.

## 6. Request Attributes Are Not Automatically Copied to Reactor Context

The following two snippets act on two different places:

~~~java
exchange.getAttributes().put("app.requestId", "req-42");
~~~

~~~java
return publisher.contextWrite(context ->
    context.put("app.requestId", "req-42")
);
~~~

The first snippet updates the exchange attribute map. The second snippet provides a key in Reactor Context to the upstream subscription. There is no default rule that automatically copies all attributes into Context or vice versa.

If the controller uses @RequestAttribute, it reads the exchange. If the service uses deferContextual, it reads Context. To give both groups of components the same request ID, the filter must actively put the same value into both mechanisms, or the design should use only one mechanism and pass appropriate parameters.

Do not generate two independent values for the same metadata if they can diverge. In the filter, create a single requestId, then write that same variable into both exchange attributes and Context.

## 7. The ServerWebExchangeContextFilter Bridge

Spring provides ServerWebExchangeContextFilter to put **the ServerWebExchange itself** into Reactor Context under a dedicated key. This allows reactive code to retrieve the exchange from ContextView without passing the exchange through every method.

Main APIs:

- ServerWebExchangeContextFilter.EXCHANGE_CONTEXT_ATTRIBUTE: the key storing the exchange.
- ServerWebExchangeContextFilter.getExchange(ContextView): returns Optional<ServerWebExchange> if the exchange is present in Context.
- This class has existed since Spring Framework 5.2.

Example:

~~~java
Mono<String> requestId = Mono.deferContextual(view -> {
    return ServerWebExchangeContextFilter.getExchange(view)
        .map(exchange ->
            Mono.just(exchange.getAttributeOrDefault(
                "app.requestId", "missing"
            ))
        )
        .orElseGet(() -> Mono.just("exchange-not-available"));
}).flatMap(publisher -> publisher);
~~~

This is an integration snippet with import org.springframework.web.filter.reactive.ServerWebExchangeContextFilter. The bridge only makes the exchange accessible from Reactor Context; it **does not automatically copy each key in exchange.getAttributes() into a separate key in Context**. Code must still retrieve the attribute from the exchange.

### 7.1. Ensure the Filter Is in the Chain

The Javadoc describes that getExchange(ContextView) works when ServerWebExchangeContextFilter is in the filter chain. If the application needs to use this API, confirm that the filter is registered in the chain; you can declare a WebFilter bean in WebFlux configuration:

~~~java
@Configuration
class WebFilterConfiguration {

    @Bean
    ServerWebExchangeContextFilter serverWebExchangeContextFilter() {
        return new ServerWebExchangeContextFilter();
    }
}
~~~

Do not create duplicate registrations. If the application/framework has already added this filter, use the existing one. Whether the filter is in the chain and the order of other filters are part of configuration that needs testing.

### 7.2. Do Not Use the Bridge as a Global Data Store

The exchange in Context still belongs to that request/subscription. Do not take the exchange from Context and store it in a singleton, global cache, or a task running after the response completes. Only use it within the scope of the request being processed; if a service needs a simple value, reading the value and passing a parameter reduces coupling to WebFlux.

## 8. Complete Example: One WebFilter Writing Both Context Types

The following example uses Java 17 and Spring Boot WebFlux. The filter generates a request ID, writes it to exchange attributes for the controller to read with @RequestAttribute, and writes the same ID into Reactor Context for the reactive service to read with deferContextual.

### 8.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.2. src/main/java/demo/RequestContextApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestContextApplication.class, args);
    }
}
~~~

### 8.3. src/main/java/demo/RequestMetadataFilter.java

~~~java
package demo;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class RequestMetadataFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
        "app.requestId";

    public static final String REQUEST_ID_CONTEXT_KEY =
        "app.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String candidate =
            exchange.getRequest().getHeaders()
                .getFirst("X-Request-Id");

        String requestId =
            candidate != null
                && candidate.matches("[A-Za-z0-9._-]{1,64}")
                    ? candidate
                    : UUID.randomUUID().toString();

        // For @RequestAttribute or exchange.getAttribute(...).
        exchange.getAttributes().put(
            REQUEST_ID_ATTRIBUTE, requestId
        );

        // For operators/services in the reactive subscription.
        return chain.filter(exchange)
            .contextWrite(context ->
                context.put(REQUEST_ID_CONTEXT_KEY, requestId)
            );
    }
}
~~~

The same requestId value is written into both mechanisms. The filter does not need to call subscribe; the publisher from the chain is returned to WebFlux. A header sent by the client is accepted only if it matches the allowed format; otherwise the server generates a UUID.

### 8.4. src/main/java/demo/RequestMetadataService.java

~~~java
package demo;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class RequestMetadataService {

    public Mono<Map<String, String>> currentRequest() {
        return Mono.deferContextual(view -> {
            String requestId = view.getOrDefault(
                RequestMetadataFilter.REQUEST_ID_CONTEXT_KEY,
                "missing"
            );

            return Mono.just(Map.of(
                "source", "reactor-context",
                "requestId", requestId
            ));
        });
    }
}
~~~

The service does not need to receive ServerWebExchange. It reads metadata from the current subscription. If the publisher is subscribed outside the WebFilter chain, the key may be absent; the example uses the value missing to represent that case. For required data, you should fail clearly or pass an explicit parameter instead of silently using a fallback.

### 8.5. src/main/java/demo/RequestMetadataController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class RequestMetadataController {

    private final RequestMetadataService service;

    public RequestMetadataController(RequestMetadataService service) {
        this.service = service;
    }

    @GetMapping("/debug/request-attribute")
    Mono<Map<String, String>> fromRequestAttribute(
            @RequestAttribute(
                RequestMetadataFilter.REQUEST_ID_ATTRIBUTE
            ) String requestId) {

        return Mono.just(Map.of(
            "source", "request-attribute",
            "requestId", requestId
        ));
    }

    @GetMapping("/debug/reactor-context")
    Mono<Map<String, String>> fromReactorContext() {
        return service.currentRequest();
    }
}
~~~

The two endpoints read the same request ID but from two different sources:

- /debug/request-attribute uses the @RequestAttribute argument resolver.
- /debug/reactor-context calls the service that reads the subscription's ContextView.

If both endpoints are called with the same valid X-Request-Id header, both return the same value produced by the filter. If called outside the filter chain, the required request attribute may fail to resolve and the Context key may also not exist.

### 8.6. Running and Calling

Start:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Call the request attribute endpoint:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/debug/request-attribute
~~~

Expected body:

~~~json
{"source":"request-attribute","requestId":"req-42"}
~~~

Call the Reactor Context endpoint:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/debug/reactor-context
~~~

Expected body:

~~~json
{"source":"reactor-context","requestId":"req-42"}
~~~

If the header is omitted, the filter generates a new UUID so the body still has requestId, though the value changes on each request. There is no fixed stdout for a randomly generated UUID.

## 9. Context Still Follows the Reactive Chain When Switching Schedulers

An important benefit of Reactor Context is that data does not depend on the current thread. Example:

~~~java
Mono<String> result = Mono.just("work")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.deferContextual(view -> {
            String requestId =
                view.getOrDefault("app.requestId", "missing");

            return Mono.just(
                value + " for " + requestId
            );
        })
    )
    .contextWrite(context ->
        context.put("app.requestId", "req-42")
    );
~~~

When subscribed, the result is work for req-42. publishOn can switch downstream callbacks to another worker, but Context is still propagated through Reactor operators.

This does not mean every async API outside Reactor automatically preserves Context. If code calls a plain ExecutorService or CompletableFuture and runs callbacks outside the subscriber chain, pass the needed value via a variable/argument or use a compatible context propagation mechanism. Do not assume Reactor Context automatically turns into ThreadLocal.

## 10. Separating Request Attributes, Reactor Context, and Other Context Types

The names sound similar, but their roles are different:

| Mechanism | Scope | Usage example |
| --- | --- | --- |
| ServerWebExchange attributes | One HTTP exchange | Filter stores resolved request ID/tenant for the controller to read |
| Reactor Context | One subscription | Trace ID, transaction/security metadata in a reactive chain |
| WebSession attributes | User session | UI preferences, session data that needs to persist across requests |
| HTTP headers/cookies | Request/response protocol | Authorization, Accept-Language, correlation header |
| Spring ApplicationContext | Application/container | Beans, configuration, application lifecycle |
| ThreadLocal/MDC | Java thread | Imperative libraries or logging with proper bridging/restoring |

Do not put information that needs to live across multiple requests into exchange attributes. Do not use Reactor Context instead of a database/session. Do not use Spring ApplicationContext as a place to store request data. Do not use plain ThreadLocal to pass metadata through a pipeline that can switch threads.

### 10.1. Spring Security Reactive

Authentication information in WebFlux should be accessed via Spring Security's reactive API, such as ReactiveSecurityContextHolder, rather than storing Authentication in an arbitrary request attribute yourself and treating it as a trusted authority source.

Spring Security reactive uses a context mechanism tied to reactive execution. Do not overwrite the framework's internal keys yourself. If you need a tenant or request ID, separate them clearly from Authentication and check permissions according to the security policy.

### 10.2. Reactive Transaction

The reactive transaction manager binds the transaction context to reactive execution. When using TransactionalOperator or @Transactional on reactive methods properly, keep the work inside the same publisher chain so the transaction is applied correctly. Calling subscribe() manually creates a secondary subscription that can detach from the intended transaction.

Request attributes can hold a business reference code or request info, but do not replace the transaction context.

### 10.3. Tracing and Correlation

A simple request ID can be stored in an exchange attribute for the controller to read, and in Reactor Context for a reactive service to read. For distributed tracing, prefer Micrometer Tracing/standard propagation so trace/span context crosses HTTP or message brokers. Reactor Context within one process does not automatically propagate over the network to another service.

## 11. Security and Design Risks

### 11.1. Do Not Trust Data Just Because It Is in Request Attributes

A request attribute is usually set by server code, but the value may originate from a client header, query, or cookie. For example, a tenantId read from X-Tenant does not prove the caller has permission to access that tenant.

The right process:

1. Read input from the request.
2. Validate the format and look up the tenant/user from a trusted source.
3. Verify the principal is allowed to access the tenant.
4. Only after verification, put the checked metadata into exchange attributes or Reactor Context.
5. The business layer still checks authorization at the required boundaries.

### 11.2. Avoid Key Collisions

Do not use overly generic keys like id, user, or tenant in an application with multiple filters/libraries. Use a stable namespace such as app.requestId, app.tenant, or static final constants.

With Reactor Context, you can use a dedicated key object shared between writer and reader. Do not create two independent new key objects and expect them to be equal.

### 11.3. Do Not Store Unnecessary Sensitive Data

Do not put access tokens, passwords, the entire request body, or personal data into Context/attributes just for convenience of access. Metadata may be logged, dumped, or read by another component. Store only minimal values and control where they are consumed.

### 11.4. Do Not Share Mutable Objects Across Processing Branches

An immutable Context does not make the objects inside it automatically immutable. The request attributes map is also mutable. If multiple flatMap branches access and mutate the same object, you must synchronize or replace it with immutable data. The simplest way is usually to write once before the chain runs and read-only afterward.

### 11.5. Do Not Hold the Exchange Beyond the Request Lifecycle

ServerWebExchange contains the request/response and resources tied to processing. Do not put it into a static field, singleton state, or a queue running in the background after the response completes. If background work is needed, extract the small needed values into an independent command/DTO before the request ends.

## 12. Testing with WebTestClient and StepVerifier

Testing needs to confirm that the two mechanisms work separately and do not leak data across requests/subscriptions.

Create tests in the project from section 8:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.filter.reactive.ServerWebExchangeContextFilter;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

class RequestMetadataTest {

    private final WebTestClient client =
        WebTestClient.bindToController(
            new RequestMetadataController(
                new RequestMetadataService()
            )
        )
        .webFilter(
            new RequestMetadataFilter(),
            new ServerWebExchangeContextFilter()
        )
        .build();

    @Test
    void requestAttributeIsCreatedByFilter() {
        client.get()
            .uri("/debug/request-attribute")
            .header("X-Request-Id", "req-A")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.source")
            .isEqualTo("request-attribute")
            .jsonPath("$.requestId")
            .isEqualTo("req-A");
    }

    @Test
    void reactorContextIsCreatedByFilter() {
        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "req-B")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.source")
            .isEqualTo("reactor-context")
            .jsonPath("$.requestId")
            .isEqualTo("req-B");
    }

    @Test
    void twoRequestsDoNotShareRequestId() {
        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "request-one")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.requestId")
            .isEqualTo("request-one");

        client.get()
            .uri("/debug/reactor-context")
            .header("X-Request-Id", "request-two")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.requestId")
            .isEqualTo("request-two");
    }

    @Test
    void contextIsIsolatedPerSubscription() {
        Mono<String> shared = Mono.deferContextual(view ->
            Mono.just(view.get("app.requestId"))
        );

        StepVerifier.create(
                shared.contextWrite(Context.of("app.requestId", "A"))
            )
            .expectNext("A")
            .verifyComplete();

        StepVerifier.create(
                shared.contextWrite(Context.of("app.requestId", "B"))
            )
            .expectNext("B")
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Or on Windows:

~~~powershell
.\gradlew.bat test
~~~

The four tests verify:

- The filter sets the request attribute before the controller argument resolver runs.
- The filter sets Reactor Context for the publisher subscribed by WebFlux.
- Two HTTP requests have separate request IDs and do not reuse data from the previous request.
- The same Mono can be subscribed with two independent Contexts.

The test uses WebTestClient bound directly to the controller and adds the WebFilters to the test chain. If using @WebFluxTest or @SpringBootTest, configure the filters as in the real application and verify order/registration in the application context. A Context unit test does not replace a filter chain integration test.

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking exchange.getAttributes().put automatically adds a key to Reactor Context | Service using deferContextual cannot find the key | Write separately to Context with contextWrite or pass a parameter |
| Thinking contextWrite updates request attributes | @RequestAttribute does not see the value | Write to exchange.getAttributes() in the filter |
| Setting an attribute after chain.filter(exchange) | Controller may have already run before the value is written | Set before delegating to the chain |
| Calling subscribe() in a WebFilter/service | Creates a secondary subscription, detaching error/cancellation/context | Return the composed publisher |
| Using ThreadLocal in place of Context | Metadata may be lost or mixed when threads are reused | Use Reactor Context or a controlled bridge |
| Using @RequestAttribute without a filter creating the key | Argument resolver lacks a required value | Register the filter, unify keys, or allow optional |
| Putting all business data into Context | Dependencies are hidden, hard to test and maintain | Pass explicit parameters/DTOs |
| Storing ServerWebExchange in a singleton | Request data can leak to another request, holding resources too long | Use only within the request lifecycle |
| Thinking an immutable Context means values are also immutable | Mutable objects can still race | Use immutable values |
| Trusting tenantId just because it is in a request attribute | May trust unauthenticated client input | Verify identity and authorization before storing |
| Thinking ServerWebExchangeContextFilter copies all attributes | ContextView does not have each attribute key as expected | Get the exchange via getExchange then read the attribute, or put a separate key |
| Using Context as a cross-network propagation mechanism | Other services do not receive the metadata | Use HTTP/message headers and tracing propagation |
| Creating different key objects at write and read sites | Context lookup cannot find the key | Use the same static final key |
| Ignoring filter order | Later filter reads metadata before the filter creates it | Configure order and test the filter chain |
| Using request attributes for a background job | Exchange may already be finished when the job runs | Extract needed DTO/values before enqueuing |

## 14. Checklist for Choosing a Mechanism

Before storing metadata, determine:

1. **Who does the metadata belong to?** One HTTP exchange, one reactive subscription, a user session, or the whole application?
2. **Who needs to read it?** Does a controller need @RequestAttribute, a component need the exchange, or reactive services/operators need ContextView?
3. **Is the data business input?** If so, pass it by parameter or DTO instead of hiding it in Context.
4. **Has the data source been authenticated/validated?** Client-sent headers/queries/cookies do not automatically become trusted information when placed into attributes.
5. **Which filter creates the value?** Ensure the filter runs before consumers and writes before delegating.
6. **Are both mechanisms needed?** If so, create one single value and write the same value to both exchange and Context.
7. **Are there scheduler switches or nested publishers?** Test Context across flatMap/publishOn and avoid manual subscribe.
8. **Is there a boundary outside Reactor?** Pass metadata explicitly or configure context propagation for the executor/library.
9. **Is the value mutable or sensitive?** Prefer small immutable metadata, namespaced keys, and restricted access.
10. **Have you tested isolation?** Send two requests with different IDs and verify data does not mix.

**Remember:** Request attributes are data attached to ServerWebExchange, convenient for sharing metadata between a WebFilter and a controller within the same HTTP request. Reactor Context is data attached to a subscriber/subscription, suitable for propagating metadata across a reactive chain and across scheduler switches. The two mechanisms are separate; only a bridge or explicit writing connects them. Use explicit parameters for business data, and keep metadata within the proper scope of its lifecycle.

## References

- Spring Framework — WebFlux @RequestAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestattrib.html
- Spring Framework — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — ServerWebExchangeContextFilter API: https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/web/filter/reactive/ServerWebExchangeContextFilter.html
- Spring Framework — WebFlux WebFilter and WebHandler: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Context-Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
