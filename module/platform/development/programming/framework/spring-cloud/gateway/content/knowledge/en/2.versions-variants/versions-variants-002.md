# Comparing Server WebFlux and Server Web MVC in Spring Cloud Gateway

Spring Cloud Gateway is the entry point for a microservices system: it receives requests from clients, selects the destination using **route predicates**, transforms requests/responses through **filters**, and forwards them to downstream services. When building a gateway, you have two **Server** deployment options: **Spring Cloud Gateway Server WebFlux** and **Spring Cloud Gateway Server Web MVC**. Both address routing, authentication, rate limiting, circuit breakers, retries, TLS, and request observability, but they differ in HTTP foundation, extension programming model, and operations.

> **Version scope:** Starter names and configuration prefixes in the examples below follow the Spring Cloud Gateway **5.0.x** line (Spring Cloud 2025.1, Spring Boot 4). Starting from Spring Cloud 2025.0 / Gateway 4.3, the project gradually transitioned to new module names and `server.webflux` / `server.webmvc` prefixes. For 4.2 and earlier systems, check the matching version's documentation before copying configuration.

## 1. Understanding the Two Server Variants

- **Server WebFlux** is built on Spring WebFlux, Project Reactor, and the **Reactor Netty** runtime. Its processing flow is asynchronous and non-blocking, fitting gateways that mainly wait on network I/O and need to sustain many concurrent connections.
- **Server Web MVC** is built on Spring MVC using the **WebMvc.fn** functional API and runs in a **Servlet** container such as Tomcat or Jetty. Developers can continue using the familiar Servlet ecosystem and programming model.
- Both are **gateway servers**, standalone or embedded inside a Spring Boot application. Do not confuse them with the **Proxy Exchange** variant: Proxy Exchange is used inside annotated handlers/controllers, which is not the subject of comparison here.

**Choosing WebFlux or Web MVC for the gateway does not depend on the technology of the downstream microservices.** A WebFlux gateway can perfectly well call a Spring MVC, Node.js, or Go backend; a Web MVC gateway can also call a WebFlux backend. The decision depends on how the gateway itself receives, processes, and forwards traffic.

## 2. Platform Comparison Table

| Criterion | Server WebFlux | Server Web MVC |
|---|---|---|
| Foundation | Spring WebFlux + Reactor | Spring MVC + WebMvc.fn |
| Server-side HTTP runtime | Reactor Netty; does not run as a traditional Servlet/WAR application | Servlet container, typically Tomcat or Jetty |
| Execution model | Event loop and non-blocking I/O; avoid blocking calls on the event loop | Requests handled under the Servlet model; synchronous operations are more straightforward |
| Route extension style | `RouteLocator`, `RouteLocatorBuilder`, `RoutePredicateFactory`, `GatewayFilter`, `GlobalFilter` | `RouterFunction<ServerResponse>`, `RequestPredicate`, `HandlerFunction`, and `HandlerFilterFunction`; `before`/`after` functions |
| Primary request objects | `ServerWebExchange`, `Mono`, `Flux` | `ServerRequest`, `ServerResponse`, Servlet request |
| Filter pipeline | `FilteringWebHandler` coordinates `GlobalFilter` with per-route `GatewayFilter` | WebMvc.fn router and before/after handlers, filters on `RouterFunction` |
| Downstream communication | Typically uses the Reactor Netty HTTP client | HTTP forwarding is performed via Server MVC's handler mechanism |
| Legacy synchronous libraries | Must account for I/O blocking and thread scheduling | Integrates naturally with many Servlet/synchronous libraries |
| Typical rate limiting | `RequestRateLimiter` with Redis or Bucket4j; reactive key resolver | `RateLimiter` based on Bucket4j; key resolver takes `ServerRequest`, configured via Java DSL |
| Spring Security | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Long-lived connection pressure | Non-blocking model advantage if the entire processing path is non-blocking | Supports these scenarios but requires accounting for Servlet resources, buffering, and thread configuration |
| Key caveat | A single blocking operation on the event loop can increase latency for many requests | When many requests wait on I/O, thread and memory resources must be measured and tuned |

There is no rule that "WebFlux is always faster than Web MVC". Actual throughput and latency also depend on backend speed, TLS overhead, number of filters, payload types, connection pools, threads, open connection count, and deployment configuration.

## 3. How Does a Request Travel Through the Gateway?

### 3.1. Server WebFlux Pipeline

~~~mermaid
flowchart LR
    A["Client"] --> B["RoutePredicate / HandlerMapping"]
    B --> C["FilteringWebHandler"]
    C --> D["GlobalFilter + GatewayFilter<br/>pre-processing"]
    D --> E["Reactor Netty HttpClient"]
    E --> F["Microservice"]
    F --> G["Filter post-processing"]
    G --> H["Response to client"]
~~~

1. `HandlerMapping` finds a route whose predicate matches the request (for example, `Path=/api/orders/**`).
2. `FilteringWebHandler` constructs the filter chain by route and priority order.
3. Filters can inspect headers, add metadata, rewrite paths, or apply rate limits or circuit breakers before sending the request.
4. The HTTP client sends the request upstream. Once a response arrives, the post-processing phase of filters runs and returns the response.

In WebFlux, developers typically work with `ServerWebExchange` and reactive types `Mono`/`Flux`. For example, calling synchronous JDBC, `Thread.sleep`, or a blocking HTTP client directly on the event loop can stall capacity for serving other requests. If a blocking operation cannot be avoided, it must be offloaded to an appropriate executor/scheduler and load-tested; offloading threads does not automatically eliminate resource limits.

### 3.2. Server Web MVC Pipeline

~~~mermaid
flowchart LR
    A["Client"] --> B["Servlet container"]
    B --> C["WebMvc.fn RouterFunction / RequestPredicate"]
    C --> D["before / HandlerFilterFunction"]
    D --> E["HandlerFunctions.http()"]
    E --> F["Microservice"]
    F --> G["after / response filters"]
    G --> H["Response to client"]
~~~

Server Web MVC represents routes with `RouterFunction`; the HTTP forwarding handler is typically `HandlerFunctions.http()`. Rather than bringing WebFlux's `GlobalFilter` interface over directly, you extend it using WebMvc.fn/Gateway MVC predicates, `before` filters, `HandlerFilterFunction`, and `after` filters.

For instance, a filter that adds a header before proxying can be written as `.before(addRequestHeader(...))`; a filter wrapping execution can be written as `.filter(...)`. Filter ordering matters, especially when combining URL rewriting with load balancing or retries.

## 4. Setting Up Both Variants

### 4.1. Dependencies

Use **one** appropriate Server starter in the gateway application. The Spring Cloud BOM must be compatible with the project's Spring Boot version.

**WebFlux (Maven):**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
~~~

**Web MVC (Maven):**

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

WebFlux requires Reactor Netty; adding `spring-boot-starter-web` and pulling Spring MVC/Servlet into the same application can cause Spring Boot's web stack detection to behave unexpectedly. When choosing Server Web MVC, use a Servlet runtime and Web MVC dependencies. Do not merely swap the dependency and leave every custom filter unchanged.

### 4.2. The Same Route in Two YAML Configurations

Suppose the order service runs at `http://localhost:9001` and exposes `GET /orders/42`. The gateway needs to accept `GET /api/orders/42`, strip the `api` segment, and add an `X-Gateway` header.

**Server WebFlux — `application.yml`:**

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, webflux
~~~

**Server Web MVC — `application.yml`:**

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, webmvc
~~~

Verify behavior:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

If the order service is running, the request is sent to `http://localhost:9001/orders/42` with `X-Gateway: webflux` or `X-Gateway: webmvc` accordingly. `StripPrefix=1` removes **one leading path segment**, not one character or an arbitrary string prefix. The HTTP response status and body are determined by the backend.

**Key takeaway:** In the Gateway 5.0 branch, the route prefix is `spring.cloud.gateway.server.webflux.routes` or `spring.cloud.gateway.server.webmvc.routes`. The two YAML snippets look identical for common predicate/filter syntax, but that does not mean every filter or parameter on the two stacks is a one-to-one equivalent.

### 4.3. Creating Routes with the Java DSL

**WebFlux** uses `RouteLocatorBuilder`:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebFluxRoutes {
    @Bean
    RouteLocator ordersRoute(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("orders-route", r -> r
                .path("/api/orders/**")
                .filters(f -> f.stripPrefix(1)
                    .addRequestHeader("X-Gateway", "webflux"))
                .uri("http://localhost:9001"))
            .build();
    }
}
~~~

**Web MVC** uses `GatewayRouterFunctions` and `HandlerFunctions`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;

@Configuration
class WebMvcRoutes {
    @Bean
    RouterFunction<ServerResponse> ordersRoute() {
        return route("orders-route")
            .GET("/api/orders/**", http())
            .before(uri("http://localhost:9001"))
            .before(stripPrefix(1))
            .before(addRequestHeader("X-Gateway", "webmvc"))
            .build();
    }
}
~~~

The two classes above are **mutually exclusive alternatives**—do not place both in the same application at the same time. They illustrate the biggest difference when extending the gateway: WebFlux builds routes via a reactive DSL, whereas Web MVC builds a `RouterFunction` via the WebMvc.fn API. If the system only needs simple route configuration, YAML is usually easier to inspect and edit than Java DSL; Java DSL is useful when custom filters or predicates are needed.

## 5. Comparing Core Capabilities When Building an API Gateway

### 5.1. Predicates, Paths, and Headers

Both support common predicates such as `Path`, `Host`, `Method`, `Header`, `Query` and filters such as `StripPrefix`, `RewritePath`, `SetPath`, `AddRequestHeader`, `AddResponseHeader`, `RemoveRequestHeader`. However, **similar-looking names do not guarantee the same interface, execution order, or level of support across every release**.

For example, the route `Path=/api/orders/**` matches `/api/orders/42`; combined with `StripPrefix=1`, upstream receives `/orders/42`. If you want to change `/v1/orders/42` to `/orders/42` using more complex rules, consider `RewritePath` or `SetPath` and test paths containing encoded characters, query strings, and trailing `/`.

Practical notes:

1. A path placed inside the route's `uri` is not a reliable path-rewriting mechanism; use dedicated path filters.
2. Filter order matters: in Server Web MVC, when using `lb()` in Java DSL, place it after path-modifying filters such as `stripPrefix()`; `lb://` configuration has its own ordering behavior.
3. Only add necessary headers; avoid accidentally forwarding sensitive headers or trusting client-supplied `X-Forwarded-*`.

### 5.2. Service Discovery and Load Balancing

In both variants, a `lb://order-service` URI can use Spring Cloud LoadBalancer to resolve a service name to a concrete instance, provided the system supplies an appropriate service discovery mechanism and required dependency, such as `spring-cloud-starter-loadbalancer`.

~~~yaml
# Replaces http://localhost:9001 in each stack's route:
uri: lb://order-service
~~~

`lb://` **does not create a registry**, nor does it automatically discover instances just because you wrote a service name. You need a configured `DiscoveryClient` (Eureka, Consul, Kubernetes discovery, or equivalent), test empty instance lists, and define timeout/retry policies. Either gateway can sit in front of the same set of backends.

### 5.3. Authentication and Authorization

With WebFlux, Spring Security uses `SecurityWebFilterChain` and reactive APIs; with Web MVC, Spring Security uses `SecurityFilterChain` with Servlet mechanisms. Both can validate JWTs as an OAuth2 Resource Server, integrate as an OAuth2 client, and relay tokens when properly configured.

A common design:

~~~text
Client -- Authorization: Bearer <token> --> Gateway
    1. Validate signature, issuer, audience, and token expiration
    2. Check route access permissions
    3. Forward identity/claims according to backend contract
    4. Backend still enforces authorization on its own resources
~~~

Do not treat `AddRequestHeader=Authorization,...` or `TokenRelay` as a substitute for authentication. Token relay depends on the login/OAuth2 context and client configuration; the gateway must avoid leaking tokens in logs or error messages. When allowing public access to health endpoints, configure explicit security matchers on the right web stack.

### 5.4. Rate Limiting: A Notable Difference

**WebFlux:** `RequestRateLimiter` typically uses `RedisRateLimiter` with a token bucket, or a Bucket4j implementation depending on dependencies. `KeyResolver` accepts `ServerWebExchange` and returns `Mono<String>`. Route definition example:

~~~yaml
# Filters snippet in a Server WebFlux route;
# requires reactive Redis and an environment-appropriate KeyResolver.
filters:
  - name: RequestRateLimiter
    args:
      redis-rate-limiter.replenishRate: 10
      redis-rate-limiter.burstCapacity: 20
      redis-rate-limiter.requestedTokens: 1
~~~

When tokens run out, the gateway typically returns **HTTP 429**. `replenishRate=10` is a refill rate of 10 tokens/second, `burstCapacity=20` is the maximum capacity, and `requestedTokens=1` is the number of tokens per request. Choose keys based on trusted user/tenant/client identity, never arbitrary query params editable by the client. Redis fits distributed rate limiting across multiple gateway replicas.

**Web MVC:** the `RateLimiter` filter uses **Bucket4j** and a `KeyResolver` of type `Function<ServerRequest, String>`. Gateway MVC 5.0 documentation notes that the key resolver currently must be configured via **Java DSL**, rather than simply copying WebFlux's `RequestRateLimiter` YAML. When using a local bucket store, limits apply per instance; for a unified quota across instances, an appropriate shared/distributed store is required.

Therefore, when switching between the two stacks, you must re-verify **dependencies, filter names, key generation, and where quota state is stored**, even if the business requirement "100 requests per minute per user" stays unchanged.

### 5.5. Circuit Breaker, Retry, and Fallback

Both support resilience patterns, but the implementing APIs/filters and dependencies must be configured for the specific stack:

- **Circuit breaker** monitors errors or response statuses as configured, opens the circuit when upstream has issues, and can route to a fallback. If using `fallbackUri`, ensure the fallback endpoint is compatible with the active variant and release.
- **Retry** repeats requests on qualifying errors; start with idempotent operations like `GET`, and control retry counts, backoff, and overall timeout.
- **Timeout** defines connection/response wait limits. Increasing retries without managing timeouts can hold resources longer per request and amplify backend outages.

Example: the order service returns 503 for 20 seconds. The gateway can perform bounded retries for `GET /orders/42`, then return an error or fallback. But for `POST /payments`, retrying could create duplicate transactions if the backend does not support idempotency keys. Do not enable retries by default for all HTTP methods.

When retrying requests with a body, some implementations need to **cache the body**, increasing memory consumption. Test large payloads and streaming requests before enabling.

### 5.6. TLS, WebSocket, and Request Observability

**TLS:** Both can serve client-facing HTTPS via Spring Boot SSL configuration (such as `server.ssl.*`) and forward to `https://` upstreams. Inbound TLS to the gateway and outbound TLS from the gateway to the backend are **two separate connections**; outbound HTTP client certificate/trust configuration depends on the web stack. In production, verify upstream certificates instead of disabling TLS validation.

**WebSocket:** WebFlux provides non-blocking WebSocket proxying; Server Web MVC in supported newer releases also provides WebSocket proxying when adding the appropriate WebSocket dependency. With MVC, Servlet WebSocket does not provide backpressure like Reactor streams; consider buffer limits, long-lived connection counts, and observability when choosing an architecture.

**Observability:** Both can integrate Spring Boot Actuator, Micrometer, tracing, and logs with correlation IDs. Monitor at minimum: request count by route, 4xx/5xx rates, p95/p99 latency, upstream errors, retry counts, circuit breaker state, rate-limited requests, open connections, and runtime resources. Metric/tag names and endpoints may vary by version; verify against the running deployment's Actuator.

## 6. Choosing the Right Variant per Use Case

| Scenario | Recommended Direction | Rationale / Conditions |
|---|---|---|
| Gateway mainly proxies high volumes of I/O-bound requests, high concurrency, streaming | Consider **Server WebFlux** | Event loop and non-blocking I/O excel when filters and HTTP client do not block |
| Team already uses Spring MVC, Servlet libraries, and synchronous filter logic | Consider **Server Web MVC** | Easy to leverage existing knowledge, libraries, and Servlet debugging |
| Need custom filters using Reactor `Mono`/`Flux` | **Server WebFlux** | Native API compatibility |
| Need to integrate `HttpServletRequest`, `SecurityFilterChain`, or existing Servlet filters | **Server Web MVC** | Avoids rewriting all logic into reactive style |
| Need distributed Redis rate limiting with existing `RequestRateLimiter` | **WebFlux** has a direct path | Do not assume `RequestRateLimiter` config works identically on MVC |
| Need WebSocket with very many long-lived connections | **Evaluate WebFlux first**, benchmark both if needed | Inspect backpressure model, buffers, and per-connection resource usage |
| Downstream backend is written in Spring MVC | **Either** | Backend technology does not dictate the gateway's web stack |
| Only moderate traffic and basic routes/filters | **Either** | Choose based on maintainability, deployment, and future needs |

**How to decide with data:** Stand up both gateway variants with identical routes, security policies, upstreams, and resource limits. Use a load generator reflecting production traffic (including slow connections, 5xx errors, large payloads, keep-alive), and compare RPS, p95/p99, CPU, heap, GC, threads, and connection counts. Also test a 500 ms slow backend scenario, because gateway issues often appear when **waiting** on upstream rather than when the backend responds immediately.

## 7. Real-World Scenario: Gateway in Front of Three Microservices

Suppose an e-commerce platform has `identity-service`, `catalog-service`, and `order-service`. The gateway exposes a single domain `api.example.com`:

~~~mermaid
flowchart TB
    C["Web / Mobile / Partner"] --> G["API Gateway"]
    G --> A["/api/auth/** → identity-service"]
    G --> B["/api/products/** → catalog-service"]
    G --> D["/api/orders/** → order-service"]
    G -.-> O["Metrics / tracing / logging"]
~~~

Route and policy design:

| Route | Predicate | Transformation | Policy |
|---|---|---|---|
| `auth` | `Path=/api/auth/**` | `StripPrefix=1` | Rate-limit login by trusted key, do not leak tokens |
| `catalog` | `Path=/api/products/**` | `StripPrefix=1` | Explicit timeout, consider caching and `GET` retries |
| `orders` | `Path=/api/orders/**` | `StripPrefix=1` | JWT validation, authorization checks, appropriate circuit breaker |

When the gateway only performs routing, JWT validation, and non-blocking proxying to often-slow services, WebFlux is a strong fit. If the organization already operates many Servlet filters and needs to reuse synchronous components, Web MVC reduces transition costs. In both cases, the backend must still verify order ownership—avoid assuming "every request that passed through the gateway is trusted".

## 8. Common Mistakes When Switching Between WebFlux and Web MVC

1. **Swapping only the starter while keeping custom Java filters unchanged.** A `GlobalFilter` taking `ServerWebExchange` cannot be copied directly into a `HandlerFilterFunction` taking `ServerRequest`. You must change the API and verify execution order.
2. **Copying wrong prefixes from old blog posts.** Older examples use `spring.cloud.gateway.routes` for WebFlux or `spring.cloud.gateway.mvc.routes` for MVC. Newer docs use `spring.cloud.gateway.server.webflux.routes` and `spring.cloud.gateway.server.webmvc.routes`; check the running release.
3. **Pulling a Servlet runtime into WebFlux.** Unintentional dependency combinations can cause Spring Boot to pick a different web application type so the WebFlux gateway fails to start as expected.
4. **Assuming every filter shares the same name/configuration.** Rate limiting is the clearest example: WebFlux `RequestRateLimiter` and MVC `RateLimiter` use different APIs.
5. **Blocking the event loop or ignoring thread limits.** WebFlux must avoid blocking; MVC must monitor thread pools, timeouts, and queued connections. Virtual threads, when enabled appropriately, can help certain blocking workloads, but they do not turn Servlet into a reactive pipeline.
6. **Trusting forwarded headers or logging sensitive data.** Only accept `Forwarded`/`X-Forwarded-*` from trusted proxies per release configuration; scrub tokens, cookies, and sensitive data from logs/traces.
7. **Assuming retries are harmless.** Retrying non-idempotent POST requests can duplicate side effects; additionally, heavy retries when a backend is overloaded add extra pressure.
8. **Misreading benchmark results.** Benchmarks calling an upstream that immediately returns `200` do not measure risks under long-lived connections or slow upstreams. Use a production-representative workload.

## 9. Knowledge Check

**Question 1.** Is it valid to run Gateway Server WebFlux in front of a Spring MVC backend?  
**Answer:** Yes. The gateway's web stack does not force backends to use the same web stack.

**Question 2.** Why should you not write `Thread.sleep(200)` inside a WebFlux `GlobalFilter`?  
**Answer:** A blocking operation occupies the event-loop thread, increasing latency for many requests sharing that thread.

**Question 3.** With `Path=/api/orders/**` and `StripPrefix=1`, what path does `/api/orders/42` become?  
**Answer:** `/orders/42`.

**Question 4.** Can you copy WebFlux's Redis `RequestRateLimiter` configuration to MVC and expect it to work out of the box?  
**Answer:** No. MVC uses its own Bucket4j filter/API and has Java DSL configuration requirements, especially for the key resolver.

**Question 5.** Must you choose WebFlux because the backend uses Reactor?  
**Answer:** No. Choose the web stack based on gateway requirements, actual workload, integration capability, operations, and benchmarks.

## 10. Official Documentation for Version Cross-Checking

- [Spring Cloud Gateway 5.0 — Variants Overview](https://docs.spring.io/spring-cloud-gateway/reference/5.0/index.html).
- [Server WebFlux — Starter and Reactor Netty requirements](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html).
- [Server Web MVC — Starter and Servlet runtime](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Server WebFlux — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html) and [Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/java-routes-api.html).
- [Server WebFlux — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html) and [Server Web MVC — RateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/ratelimiter.html).
- [Spring Cloud 2025.0 — Starter and property prefix rename notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).

> **Version note:** When upgrading Spring Cloud Gateway, always check the exact **release train and version** of your application, because filter capabilities, dependency names, properties, and security options can change across branches.
