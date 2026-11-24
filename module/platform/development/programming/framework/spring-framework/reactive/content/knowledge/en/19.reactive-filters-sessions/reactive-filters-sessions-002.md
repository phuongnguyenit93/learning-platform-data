# Filter Order with Ordered and @Order

**Context:** Spring Framework Reactive → **Filters and Sessions**.

In Spring WebFlux, `WebFilter` is an interception point at the web layer used to apply common logic before and after a request passes through the rest of the filter chain and the handler. Things commonly placed here include correlation ID, logging, CORS, authentication, tenant checks, request throttling, metrics observation, and session integration.

When there are multiple `WebFilter`s, order matters a lot. A filter that creates the request context must run before a filter that needs to read that context; CORS must be handled at the right position relative to security; a filter that logs the response needs to wrap the processing it wants to observe. Spring lets you define the order in two ways:

- **`@Order(value)`:** declare the order with an annotation on a class or bean method.
- **`Ordered#getOrder()`:** provide the order in code through the `Ordered` interface.

The core rule: **the smaller the order number, the higher the priority and the earlier the filter is called**. If filter A has order 10 and filter B has order 20, the request goes into A and then B; when processing ends, the after part of B runs before the after part of A.

## 1. Where Does WebFilter Sit in WebFlux?

A request passes through the server adapter and the web handler chain. `WebFilter` wraps the next processing step:

```text
HTTP request
    |
    v
WebFilter A (order = 10)
    |  before
    v
WebFilter B (order = 20)
    |  before
    v
WebFilter C (order = 30)
    |  before
    v
DispatcherHandler / Router / Controller
    |
    v
Response completes or errors
    |
    v
WebFilter C (after)
    |
    v
WebFilter B (after)
    |
    v
WebFilter A (after)
    |
    v
HTTP response
```

Each filter receives a `ServerWebExchange` and a `WebFilterChain`, then returns a `Mono<Void>`:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

- `ServerWebExchange` contains the request, response, attributes, and access to the session.
- `WebFilterChain` lets you call the next filter or the final handler.
- `Mono<Void>` represents the moment request/response processing completes; errors and cancellation are also propagated through the publisher.

A filter can **let the request continue** with `return chain.filter(exchange)`, or **stop the chain** by creating its own response and not calling the next filter. For example, a failed authentication can return 401 right in the filter.

Spring WebFlux automatically detects `WebFilter` beans in the application context and puts them into the web handler chain. When order is needed, a bean can use `@Order` or implement `Ordered`. <https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html>

## 2. The Order Number Rule

`Ordered` defines two useful constants:

| Constant | Value | Meaning |
|---|---:|---|
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Highest priority |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Lowest priority |

Example:

| Filter | Order | Request order |
|---|---:|---:|
| Correlation ID | -200 | 1 |
| Authentication context | -100 | 2 |
| Audit | 0 | 3 |
| Response metrics | 100 | 4 |

The numbers are illustrative only. Choose values based on your application's actual filters, Spring Security, and auto-configuration. Do not copy a Spring Boot order value from another version and assume it is always the same.

### 2.1. Smaller Numbers Run First

```java
@Order(10)
@Component
class FirstFilter implements WebFilter {
    // ...
}

@Order(20)
@Component
class SecondFilter implements WebFilter {
    // ...
}
```

`FirstFilter` has higher precedence than `SecondFilter` because 10 is smaller than 20.

Do not interpret "order 20 is larger" as "runs earlier". With `Ordered`, the larger the value, the lower the priority.

### 2.2. Equal Values Have No Stable Order

If two filters both have order 10, Spring does not guarantee which one comes first. The `Ordered` Javadoc states clearly that elements with the same order may be sorted in an arbitrary position.

Do not rely on:

- The declaration order of classes in a file.
- The alphabetical order of bean names.
- The order in which components are scanned.
- The order you happen to see in the log on a single run.

If the order has business meaning, assign different values, for example 10, 20, 30. See the [Ordered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html).

## 3. Approach 1: Using @Order

`@Order` is an annotation that declares order. For a component-style `WebFilter`, put the annotation on the class:

```java
@Component
@Order(10)
public class CorrelationWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getAttributes().put(
                "request.source", "web");

        return chain.filter(exchange);
    }
}
```

Spring registers this bean and uses the value 10 when sorting filters. The annotation does not create a bean by itself; the class must still be registered through component scanning or bean configuration.

You can put `@Order` on a `@Bean` method:

```java
@Configuration
class WebFilterConfiguration {

    @Bean
    @Order(15)
    WebFilter tenantContextFilter() {
        return (exchange, chain) -> {
            exchange.getAttributes().put(
                    "tenant.checked", Boolean.TRUE);
            return chain.filter(exchange);
        };
    }
}
```

This is useful when you do not want to attach an annotation to the class, or the filter is created from a factory method. `@Order` supports classes and bean methods; the default value if not declared is `Ordered.LOWEST_PRECEDENCE`.

### 3.1. @Order Is Not the Run Order of Every Kind of Filter

This annotation only takes effect at extension points that support ordering. In this lesson, it is used for `WebFilter` beans managed by WebFlux.

Do not infer that attaching `@Order` to any object automatically changes every filter chain. For example, a `HandlerFilterFunction` in WebFlux.fn is combined into a `RouterFunction` according to how the router is built; it is not a global `WebFilter` bean sorted in the same group just because it has an annotation.

## 4. Approach 2: Implementing Ordered

When the order needs to be computed in code or the class manages the value itself, implement `Ordered`:

```java
@Component
public class AuditWebFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange);
    }
}
```

Spring calls `getOrder()` to get the precedence. The example above places the filter at order 20.

You can return a constant instead of a literal number:

```java
@Override
public int getOrder() {
    return Ordered.LOWEST_PRECEDENCE - 100;
}
```

This is usually easier to read when you need to express "near the end of the chain" instead of an arbitrary number. However, avoid addition/subtraction that can overflow at the two extreme values.

### 4.1. Should You Choose @Order or Ordered?

| Criterion | `@Order` | `Ordered` |
|---|---|---|
| How it is declared | Annotation | Implement an interface |
| Value | Fixed on the class or bean method | Returned from `getOrder()` |
| Easy to see in review | Clear right on the bean | Need to look at the method |
| Dynamically computed value | Not suitable | Can be computed in code |
| Use when | Simple, stable order | Need programmatic logic or configuration |

For a filter with a fixed order, `@Order` is usually concise. For a component that needs to decide its order in code, `Ordered` is more suitable.

**Avoid declaring two order sources on the same filter** unless there is a clear reason. Choose one way so readers do not have to guess which value is used. When a class implements `Ordered`, the programmatic value from `getOrder()` is the order source to pay attention to.

## 5. Why Is the Response Order Reversed?

The filter chain works in a nested fashion. The earlier filter calls the next filter and holds the publisher that the later filter returns:

```java
return chain.filter(exchange)
        .doFinally(signal -> log.info("after"));
```

If A calls B, B calls C, and C calls the handler, the before part runs in the order A → B → C. When the publisher ends, the callbacks on the way back are executed C → B → A.

Example:

```text
A before
  B before
    Handler
  B after
A after
```

This is a useful way to understand:

- Opening/closing a tracing span.
- Recording request time.
- Setting and cleaning up context.
- Logging status after the response completes.
- Observing errors or cancellation.

`doFinally` runs on complete, error, or cancel. If you only want to handle success, consider `doOnSuccess`; if you want to observe errors, use `doOnError`. Do not put cleanup only on the success branch if the resource must also be released on error or client disconnect.

## 6. Example of Three Filters with a Clear Order

Suppose the application has three responsibilities:

1. A correlation filter attaches a request ID.
2. An authentication filter reads authentication information.
3. An audit filter records the processing result.

An illustrative order:

```java
@Component
@Order(10)
class CorrelationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();
        exchange.getAttributes().put("requestId", requestId);

        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("request {} finished: {}",
                                requestId, signal));
    }
}

@Component
@Order(20)
class AuthenticationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String token = exchange.getRequest().getHeaders()
                .getFirst("Authorization");

        if (token == null) {
            exchange.getResponse().setStatusCode(
                    HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}

@Component
class AuditWebFilter implements WebFilter, Ordered {
    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("audit finished: {}", signal));
    }
}
```

This is a structural example; it needs imports, a logger, a token validator, and a real audit policy. The authentication snippet above only checks that the header exists and **does not verify the signature/token**.

The request order going in is correlation → authentication → audit → handler. If Authorization is missing, the authentication filter returns 401 and does not call the chain further; the audit filter and handler behind it are not run. The correlation filter still receives the end signal to write its log.

In production, you should use Spring Security for authentication/authorization instead of building your own security mechanism with an illustrative filter. The order values of your own filters need to be coordinated with Spring Security's filter chain and the filters Boot configures automatically.

## 7. A Filter Can Stop the Chain (Short-Circuit)

Not every filter is required to call `chain.filter`. Example of rejecting a request:

```java
@Component
@Order(5)
class MaintenanceFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        boolean maintenance = true;

        if (maintenance) {
            exchange.getResponse().setStatusCode(
                    HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

If this filter comes before the other filters, the request stops here. The filters after it and the handler are not called. The outer filters that already called the chain still observe the completion of the response.

Short-circuit is useful for maintenance mode, rejecting requests over quota, or CORS preflight depending on configuration. Make sure the response is completed with a reactive API; do not call `block()` or `subscribe()` to `setComplete()` yourself.

## 8. Global WebFilter and Per-Route HandlerFilterFunction

WebFlux has two levels of filters that are often confused:

| Type | API | Scope | How order is determined |
|---|---|---|---|
| Global web filter | `WebFilter` | Web handler chain, applies broadly to requests | `Ordered` / `@Order` |
| Functional route filter | `HandlerFilterFunction<T,R>` | A route or group of routes in WebFlux.fn | How filters are combined in the RouterFunction builder |
| Security filter chain | WebFlux Security | Security chain managed by Spring Security | The order of the security chain and the position of the corresponding WebFilter bean |

Example of a route-local filter:

```java
@Bean
RouterFunction<ServerResponse> routes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .filter((request, next) -> {
                if (request.headers().firstHeader("X-Client") == null) {
                    return ServerResponse.badRequest().build();
                }
                return next.handle(request);
            })
            .build();
}
```

This is a snippet that needs `PeopleHandler` and imports. The filter belongs only to the declared router. `@Order` on a `HandlerFilterFunction` bean does not automatically put it into the global `WebFilter` chain.

If you need a filter for all requests, use `WebFilter`. If the logic only concerns a group of routes, a route-local filter limits the scope and makes dependencies clearer.

## 9. Order with Spring Security, CORS, and Integrated Filters

In a real application, the chain contains both your own filters and framework filters:

- CORS needs to be handled at a suitable position before the security step that might reject the preflight.
- Authentication/authorization needs to run before the business handler.
- A correlation ID usually needs to exist early so that even authentication errors are tagged with a trace code.
- Audit/metrics may need to wrap the processing to observe the status and terminal signal.
- A filter that transforms the request/headers needs to run before a filter that reads the transformed values.

Spring recommends using appropriate CORS support and ensuring the CORS filter comes before the Spring Security filter chain when combining the two mechanisms. <https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html>

Spring Boot can also automatically register WebFilters such as observability or Spring Security. Their order values depend on the version and configuration. Check the documentation for the exact Boot version you are running; do not treat the order table of an old release as a constant for every project. <https://docs.spring.io/spring-boot/reference/web/reactive.html>

**Do not use order numbers to replace security configuration.** If you need to define CORS, authentication, or authorization, configure the right subsystem and only use order to set the relative position between filters.

## 10. A Filter Working with WebSession Must Stay Reactive

`ServerWebExchange` provides `getSession()`, which returns `Mono<WebSession>`. When a filter needs to read the session, compose the publisher instead of blocking the thread:

```java
@Component
@Order(15)
class SessionUserFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return exchange.getSession()
                .flatMap(session -> {
                    String userId =
                            session.getAttribute("userId");

                    if (userId == null) {
                        exchange.getResponse().setStatusCode(
                                HttpStatus.UNAUTHORIZED);
                        return exchange.getResponse().setComplete();
                    }

                    exchange.getAttributes().put(
                            "userId", userId);

                    return chain.filter(exchange);
                });
    }
}
```

This is a snippet that needs WebSession configuration, a session store, and a real authentication policy. It illustrates getting the session in a reactive way; whether a session is newly created when it does not yet exist depends on the `WebSessionManager` and how the session is retrieved. Do not use this example to replace a complete authentication mechanism.

The order of session filters needs to be decided by dependency:

- A filter that needs the session first must run before a filter that reads attributes from the session.
- A session-based authentication filter must run before the business handler.
- A post-processing audit filter can read the user ID that has been set in the exchange attribute.
- Do not store sensitive data carelessly in the session or exchange attributes.

Do not call `exchange.getSession().block()`. Waiting for the session must stay inside the `Mono<Void>` chain so that cancellation and errors still belong to the current request.

## 11. A Runnable Java 17+ Integration Example: Verifying Order with WebTestClient

The example below uses Spring Boot WebFlux and JUnit 5. The two filters use two different mechanisms: one filter uses `@Order`, the other implements `Ordered`. The test sends a request to the embedded server and confirms the before/after order around the handler.

Project structure:

```text
webflux-filter-order-demo/
├── pom.xml
└── src
    ├── main/java/demo/FilterOrderApplication.java
    └── test/java/demo/FilterOrderIntegrationTest.java
```

### 11.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-filter-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 11.2. FilterOrderApplication.java

```java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FilterOrderApplication {

    public static final List<String> EVENTS =
            new CopyOnWriteArrayList<>();

    public static void main(String[] args) {
        SpringApplication.run(
                FilterOrderApplication.class, args);
    }
}

@Component
@Order(10)
class CorrelationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            FilterOrderApplication.EVENTS.add(
                    "correlation:before");

            return chain.filter(exchange)
                    .doFinally(signal ->
                            FilterOrderApplication.EVENTS.add(
                                    "correlation:after"));
        });
    }
}

@Component
class AuditFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            FilterOrderApplication.EVENTS.add(
                    "audit:before");

            return chain.filter(exchange)
                    .doFinally(signal ->
                            FilterOrderApplication.EVENTS.add(
                                    "audit:after"));
        });
    }
}

@RestController
class ProbeController {

    @GetMapping("/probe")
    Mono<String> probe() {
        FilterOrderApplication.EVENTS.add("handler");
        return Mono.just("ok");
    }
}
```

### 11.3. FilterOrderIntegrationTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterOrderIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    void clearEvents() {
        FilterOrderApplication.EVENTS.clear();
    }

    @Test
    void filtersRunInAscendingOrderAndUnwindInReverse() {
        webTestClient.get()
                .uri("/probe")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ok");

        assertThat(FilterOrderApplication.EVENTS)
                .containsExactly(
                        "correlation:before",
                        "audit:before",
                        "handler",
                        "audit:after",
                        "correlation:after");
    }
}
```

Run the test from the project directory with JDK 17+ and Maven:

```bash
mvn test
```

**The event sequence the assertion requires:**

```text
correlation:before
audit:before
handler
audit:after
correlation:after
```

The test does not depend on Spring Boot's startup log order. It confirms the order observed within a single request through the embedded WebFlux server. If you add another filter to the application context, update the expectations according to the actual order.

## 12. Debugging Filter Order

When filters run in the wrong order, check these steps:

1. Is the filter actually registered as a bean?
2. Does the bean implement `WebFilter` correctly?
3. Does the order come from `@Order` on the class/bean method or from `Ordered#getOrder()`?
4. Is there another filter with the same order?
5. Is Spring Security or an auto-configured filter involved?
6. Does the filter call `chain.filter(exchange)`, or is it short-circuiting?
7. Is a route-local `HandlerFilterFunction` being confused with a global `WebFilter`?
8. Are the before/after logs placed in the publisher chain at the right position?
9. Do multiple contexts/child contexts or a custom server configuration change the filter list?
10. Does the test run the right application context and server mode as in production?

You can enable the appropriate framework logging or log the filter name/order at initialization. Do not just look at bean initialization time logs: **bean creation order is not solid evidence of request execution order**.

## 13. Common Mistakes

1. **Thinking a larger order runs first.** Only the smaller number has higher precedence.
2. **Two filters with the same order but expecting a fixed order.** Equal values do not guarantee order; use different numbers.
3. **Setting @Order but the class is not a bean.** The annotation does not register the filter by itself.
4. **Implementing Ordered but forgetting getOrder().** Without the correct programmatic value, the desired order is not achieved.
5. **Using @Order on a HandlerFilterFunction and expecting global sorting.** A route-local filter is combined in the RouterFunction and does not belong to the WebFilter bean group.
6. **Confusing request order with response order.** The request goes in by precedence; the post-processing part comes back out in the reverse order.
7. **Writing the after log right after calling chain.filter.** An asynchronous publisher may not have finished yet; put the callback in the chain with the appropriate doFinally/doOnSuccess.
8. **Not calling chain.filter and thinking the request still reaches the controller.** Not delegating means the filter is stopping the chain.
9. **Calling subscribe in a filter.** It creates a detached subscription, losing the error/cancel link with the request.
10. **Calling block in a filter.** It blocks the event loop and breaks non-blocking execution.
11. **Placing CORS after security when the preflight needs to be handled first.** Configure the order following Spring's CORS/Security guidance.
12. **Hard-coding Boot's order from old documentation.** Built-in filters and orders can change by version/configuration.
13. **Using order to replace authorization.** Order does not verify identity or access rights by itself.
14. **Keeping mutable request state in fields of a singleton filter.** Many concurrent requests will overwrite each other's data; use exchange attributes or Reactor Context.
15. **Forgetting the error/cancel branches during cleanup.** Use doFinally or reactive resource management to clean up on every terminal path.
16. **Assuming a filter runs only once when the application starts.** A filter is called for each exchange/request, not just once.
17. **Using a global filter for logic that belongs to only one route.** Consider HandlerFilterFunction to narrow the scope.
18. **Reading the session with block.** Use `exchange.getSession()` and compose the Mono instead of blocking the thread.

## 14. Design Checklist

Before adding or changing a filter, answer:

- Is the filter a global `WebFilter` or a route-local `HandlerFilterFunction`?
- Is the filter registered as a bean in the right application context?
- Which filters does it need to run before and which after?
- Have you chosen one clear order source: `@Order` or `Ordered`?
- Do the order values differ in the places where order truly matters?
- Are Spring Boot/Security/CORS filters involved?
- Do request pre-processing and response post-processing happen in the expected order?
- Can the filter short-circuit? Are the status and body correct for the contract?
- If using the session, do you compose `Mono<WebSession>` without blocking?
- Are all errors and cancellation propagated/cleaned up correctly?
- Is there an integration test confirming the event sequence before and after the handler?
- Is request-specific state kept in the exchange/context instead of singleton fields?

**Remember:** `@Order` and `Ordered` both declare precedence for a `WebFilter` bean. **A smaller order number runs first; a larger order number runs later.** Because a filter wraps the chain, the before part goes in by ascending order, while the after part comes back out in the reverse order. Equal values have no guaranteed order. Coordinate the order with CORS, Spring Security, session, and auto-configured filters; use an integration test to confirm the actual sequence.

## References

- Spring Framework — [Reactive Core: WebFilter registration and ordering](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Ordered Javadoc: precedence and equal-order behavior](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html).
- Spring Framework — [@Order Javadoc: annotation targets and default order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html).
- Spring Boot — [Reactive Web Applications: WebFilter beans and auto-configured order](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Spring Framework — [WebFlux Functional Endpoints: HandlerFilterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework — [WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html).
