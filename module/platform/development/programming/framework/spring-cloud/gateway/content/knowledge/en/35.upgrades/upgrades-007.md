# Switching Between Server WebFlux and Server Web MVC Using a Feature Matrix

Spring Cloud Gateway provides two Gateway Server implementations: **WebFlux** and **Web MVC**. Both can serve as the entry point for microservices, matching routes by request, transforming paths/headers, forwarding HTTP traffic, and integrating capabilities like load balancing, security, circuit breakers, and retries. However, the two options rest on different web models and differ in extension APIs, proxy clients, and certain specialized features.

For the **SPRING_CLOUD_GATEWAY** module, switching stacks must start from real operational requirements: whether the application needs end-to-end reactivity, auto-generated routes from a service registry, which rate limiter type is needed, which APIs custom filters currently use, or whether compatibility with an existing Servlet container and MVC libraries is required. Changing only the starter and YAML prefix is not enough to guarantee equivalent behavior.

## Identify the Exact Gateway Server Type

This article covers **Gateway Server**—the component receiving client requests, selecting routes, and proxying requests upstream. Spring Cloud Gateway also offers a ProxyExchange variant where a controller invokes proxying via a `ProxyExchange` object; that is a different integration pattern and is outside the comparison here.

### Server WebFlux

Gateway Server WebFlux is built on Spring WebFlux, Project Reactor, and the Netty runtime. Requests are represented by `ServerWebExchange`; per-route filters use `GatewayFilter`, while filters conditionally applied across multiple routes can use `GlobalFilter`. The processing pipeline can stay asynchronous and non-blocking when every participating component uses non-blocking APIs.

This option fits when Gateway must handle high connection concurrency, uses reactive clients/data access, or depends on reactive Spring Cloud Gateway extensions. Gateway Server WebFlux requires Spring Boot's Netty runtime and does not run inside a traditional Servlet container or WAR packaging. Calling blocking APIs from the event loop can stall processing; if a blocking library must be integrated, isolate it and measure the impact under real load.

### Server Web MVC

Gateway Server Web MVC is built on Spring MVC and the `WebMvc.fn` API. Routes are represented by `RouterFunction`, proxy handlers use `HandlerFunction`, predicates use `RequestPredicate`, and filters use `HandlerFilterFunction`. Filters can be organized into `before`, `after`, or advanced groups that handle both requests and responses.

This option fits Servlet applications, Spring MVC, Servlet Filters, and existing synchronous libraries. Gateway Server Web MVC runs on Servlet runtimes such as Tomcat and Jetty. Backend proxying uses Spring Boot's `RestClient` infrastructure, so timeouts, TLS, and HTTP client observability follow Spring Boot's model.

## Feature Matrix and Differences to Evaluate

The table below describes Gateway Server capabilities in current Spring Cloud Gateway documentation. “Yes” means a documented mechanism exists; it does not mean the API, properties, or runtime behavior are identical. Always verify the exact Spring Boot and Spring Cloud Release Train versions of your project before finalizing a design.

| Criterion | Server WebFlux | Server Web MVC | Impact when switching |
|---|---|---|---|
| Runtime | Spring WebFlux, Reactor, Netty | Spring MVC, Servlet API; Tomcat/Jetty | Must change web stack and evaluate I/O, thread, and timeout handling |
| Route model | `Route`, `RouteLocator`, `ServerWebExchange` | `RouterFunction`, `HandlerFunction`, `ServerRequest`/`ServerResponse` | Java routes and custom predicates/filters are not directly reusable |
| Common predicates | Path, Method, Host, Header, Cookie, Query, time, weight, and other Gateway predicates | Reuses `WebMvc.fn` predicates and `GatewayRequestPredicates`; includes Path, Method, Host, Header, Cookie, Query, time, weight, and version-specific capabilities | Verify specific predicates, path rules, and data types; do not compare YAML names alone |
| Extension filters | `GatewayFilter`, `GlobalFilter`, reactive `Mono`, and `GatewayFilterChain` | `HandlerFilterFunction`, `BeforeFilterFunctions`, `AfterFilterFunctions`, advanced filter groups | Rewrite custom filters, handle before/after ordering, and update request/response access |
| Routes from service registry | Includes `DiscoveryClient RouteDefinitionLocator` to auto-generate routes from registered services | Supports `lb://serviceId`/LoadBalancer for declared routes; Server Web MVC docs do not describe an auto-generating route locator equivalent to WebFlux | If relying on auto-generated routes, design a separate route source before moving to MVC |
| Load balancing | `lb://serviceId` via reactive load balancer | `lb://serviceId` or `lb()` in Java DSL via Spring Cloud LoadBalancer | Both require the LoadBalancer dependency; verify filter ordering when writing Java DSL manually |
| Rate limiting | `RequestRateLimiter`; Redis RateLimiter uses token bucket and reactive Redis starter | `RateLimiter` based on Bucket4j; `keyResolver` is configured via Java DSL | Must migrate algorithm, keys, state backend, and configuration; do not copy YAML as-is |
| Circuit breaker / retry | Gateway filters on the reactive chain | `CircuitBreakerFilterFunctions` and `RetryFilterFunctions` in `WebMvc.fn` | Check fallbacks, exceptions, filter order, and request idempotency |
| WebSocket | WebSocket routing on WebFlux/Netty | WebSocket proxying supported; requires `spring-boot-starter-websocket` | MVC does not relay ping frames as received; retries, circuit breakers, and body-processing filters do not apply after connection establishment |
| Security | Spring Security reactive, `SecurityWebFilterChain`, and matching token relay integration | Spring Security Servlet, `SecurityFilterChain`, OAuth2 client/resource server | Rewrite security configs for the stack; verify JWT, sessions, CORS, and token relay |
| TLS to upstream | Reactor Netty HTTP client config under `spring.cloud.gateway.server.webflux.httpclient.ssl.*` | Uses Spring Boot `RestClient`, `spring.http.client`, and `spring.ssl.bundle` | Migrate trust stores, SSL bundles, timeouts, and test certificates against the new client |
| Observability | Includes Gateway metrics filter with route metrics like `spring.cloud.gateway.requests` and `routeId`/`routeUri` tags | Uses Spring MVC HTTP server and `RestClient` HTTP client observability; do not assume Gateway metrics/tags match WebFlux | Update dashboards, alerts, and tracing; add route tags if business requires them |
| Servlet Filter | Servlet Filters cannot be used as reactive Gateway extension points | Can integrate Servlet Filters; pay attention to ordering with `FormFilter` | Audit filters reading bodies/parameters, especially `application/x-www-form-urlencoded` requests |

## Choose the Stack by Operational Requirements

Prefer **WebFlux** when one or more of the following are mandatory:

- The application needs end-to-end reactivity and upstream calls use non-blocking I/O.
- Existing `GlobalFilter`/`GatewayFilter` implementations or extensions depending on `ServerWebExchange` and Reactor are needed.
- `DiscoveryClient RouteDefinitionLocator` is needed to auto-generate routes from Eureka, Consul, Zookeeper, or compatible registries.
- `RequestRateLimiter` with Redis RateLimiter and existing quota management are needed.
- The system uses WebSocket routing and requires WebFlux/Netty capabilities such as proxying ping frames.

Prefer **Web MVC** when:

- Gateway is part of a Spring MVC/Servlet application and needs to share Servlet Filters, Spring Security Servlet, or synchronous libraries.
- Deployment infrastructure standardizes on Tomcat/Jetty or has Servlet compatibility requirements.
- The development team wants to extend routes via `RouterFunction`, `RequestPredicate`, and `HandlerFilterFunction`.
- Rate-limiting needs align with Bucket4j and the team accepts configuring key resolvers in Java DSL.
- Routes can be declared explicitly or the project is ready to manage generating routes from the service registry itself.

Do not choose WebFlux solely expecting higher performance, nor choose Web MVC solely because the app currently includes an MVC dependency. Load-test with realistic concurrent connections, upstream latencies, request body sizes, blocking behavior, and deployment thread limits. Results depend on the entire processing pipeline, not just the receiving framework.

## Differences That Can Alter Behavior

### Route discovery and load balancing

WebFlux can enable a route locator backed by `DiscoveryClient`. By default, Gateway creates routes shaped like `/{serviceId}/**`, uses the `lb://serviceId` URI, and rewrites the path to strip the service ID before forwarding upstream. When overriding the discovery locator's filter list manually, re-declare the default `RewritePath` if you still want to strip the service ID from the path.

Web MVC supports load balancing for declared routes using `lb://serviceId` URIs or the `lb()` filter in Java DSL. This resolves instance selection for a declared route; it does not mean auto-discovering and generating routes from every service in the registry. If the system currently relies on auto-generated routes, generate routes from a managed source or keep WebFlux for that requirement.

Static route example following the matching structure of both stacks:

```yaml
# WebFlux: spring.cloud.gateway.server.webflux.routes
# Web MVC: spring.cloud.gateway.server.webmvc.routes
spring:
  cloud:
    gateway:
      server:
        webflux: # change to webmvc when using Server Web MVC
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

This example only illustrates static routing and load balancing. For Web MVC, routes are resolved by the LoadBalancer filter; if writing Java DSL and calling `lb()` explicitly, place it after path-modifying filters such as `setPath()` or `stripPrefix()` so the URI resolves properly. When using `lb://` config, Gateway orders the scheme filter automatically.

### Rate limiting

The two stacks use different rate-limiting mechanisms. WebFlux uses `RequestRateLimiter`; Redis RateLimiter uses the token-bucket algorithm with `replenishRate`, `burstCapacity`, and `requestedTokens`, requiring `spring-boot-starter-data-redis-reactive`. Example:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-api
              uri: lb://public-api
              predicates:
                - Path=/api/public/**
              filters:
                - name: RequestRateLimiter
                  args:
                    redis-rate-limiter.replenishRate: 10
                    redis-rate-limiter.burstCapacity: 20
                    redis-rate-limiter.requestedTokens: 1
```

Web MVC has a `RateLimiter` based on Bucket4j. The key resolver is a `Function<ServerRequest, String>` and current documentation requires configuring the key resolver via Java DSL. Example:

```java
@Bean
RouterFunction<ServerResponse> limitedRoute() {
    return route("limited-api")
        .GET("/api/public/**", http())
        .before(uri("https://public-api.internal"))
        .filter(rateLimit(config -> config
            .setCapacity(100)
            .setPeriod(Duration.ofMinutes(1))
            .setKeyResolver(request -> {
                var principal = request.servletRequest().getUserPrincipal();
                return principal == null ? "anonymous" : principal.getName();
            })))
        .build();
}
```

This example illustrates keying by principal; policies for unauthenticated requests must be designed explicitly. In production, choose an appropriate distributed backend so Gateway instances share buckets; local caches fit only testing or per-instance limits. When switching stacks, re-check quotas, bursts, refill periods, 429/403 responses on missing keys, and cross-pod consistency.

### Custom filters and execution order

In WebFlux, custom filters receive `ServerWebExchange` and `GatewayFilterChain`; async logic typically returns `Mono<Void>`. `GlobalFilter` beans combine with route filters and sort by `Ordered`, affecting both pre-proxy and post-proxy phases.

In Web MVC, custom filters rely on `HandlerFilterFunction<ServerResponse, ServerResponse>`. Request-only mutations can use `BeforeFilterFunctions`; response-only mutations can use `AfterFilterFunctions`; advanced filters handling both phases live in dedicated groups such as circuit breaker, load balancer, retry, and token relay. MVC routes also sit inside `RouterFunction`, so they compose with `WebMvc.fn` APIs.

Do not convert a `GlobalFilter` into a Servlet Filter mechanically. Servlet Filters execute at the Servlet chain boundary, whereas `HandlerFilterFunction` runs inside the route's handler chain. Choose the right extension point for the desired scope, then test execution order for authentication, logging, header mutations, path rewrites, and response handling.

If a Servlet Filter reads request parameters directly, check its order relative to Gateway MVC's `FormFilter`. For `application/x-www-form-urlencoded`, the Servlet container merges form bodies with query parameters; `FormFilter` restores the form body for upstream. Filters reading parameters before `FormFilter` must be ordered according to the documentation.

### WebSocket

Both stacks can proxy WebSockets. With Web MVC, add `spring-boot-starter-websocket` and configure `ws://`/`wss://` routes, or use HTTP/HTTPS/LB URIs for requests carrying `Upgrade: websocket`. After handshake, MVC relays text, binary, and pong frames; ping frames are handled by the Servlet WebSocket API at the container and are not forwarded verbatim. Filters modifying response bodies, retries, and circuit breakers do not apply to message streams once the connection is established. If the application relies on heartbeats to monitor the backend, use application-level heartbeats.

When migrating WebSockets, test handshakes, subprotocols, `Origin`, connection duration, idle timeouts, reconnects, and connection closure. Test the path through the real load balancer and ingress rather than inferring behavior from working HTTP routes.

### TLS, security, and observability

Inbound TLS remains configured on the application server via `server.ssl`. Outbound TLS differs: WebFlux uses Reactor Netty HTTP client config; Web MVC uses `RestClient` and Spring Boot SSL bundles, such as `spring.http.client.ssl.bundle` paired with `spring.ssl.bundle`. Do not carry WebFlux `httpclient.ssl.*` keys straight over to MVC. Never use a trust manager that accepts all certificates in production.

Security must also match the web stack. WebFlux uses a reactive security chain; Web MVC uses a Servlet `SecurityFilterChain`. After switching, re-verify resource server JWT/opaque tokens, OAuth2 login, token relay, sessions, CSRF, CORS, and management endpoints. With MVC, Spring Security enforces `StrictHttpFirewall`; relax URL rules only when downstream genuinely requires it and risk has been assessed.

WebFlux provides a Gateway metrics filter recording `routeId`, `routeUri`, status, and HTTP method. Web MVC relies on Spring MVC HTTP server and `RestClient` HTTP client observability. If existing dashboards filter by route ID or use the `spring.cloud.gateway.requests` metric, list required metrics/tags, add MVC instrumentation if needed, and update alerts before shifting traffic.

## Updating Dependencies and Configuration Namespaces

Starting with Spring Cloud 2025.0, starter names explicitly indicate the web stack. Use the Spring Cloud BOM compatible with your Spring Boot version and choose exactly one Gateway Server starter:

```xml
<!-- Gateway Server WebFlux -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>

<!-- Or Gateway Server Web MVC -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Do not add both starters as a way to switch at runtime. Create separate configs/build profiles if you need to test both variants, and verify the dependency tree does not pull in the wrong web stack or a Spring Cloud version from another release train.

In Spring Cloud 2025.0 and above, the corresponding configuration prefixes are:

| Stack | Configuration prefix |
|---|---|
| Server WebFlux | `spring.cloud.gateway.server.webflux.*` |
| Server Web MVC | `spring.cloud.gateway.server.webmvc.*` |

In older release trains, prefixes may be `spring.cloud.gateway.*` for WebFlux and `spring.cloud.gateway.mvc.*` for Web MVC. Do not apply new prefixes to an unsupported version. `spring-boot-properties-migrator` can help flag legacy properties during transition, but you must still update configuration sources and remove the migrator afterward.

## Safe Migration Roadmap

1. **Establish a baseline:** record Spring Boot/Spring Cloud versions, starters, runtime, route IDs, predicates, filters, URIs, discovery locator, LoadBalancer, rate limiter, security, TLS, WebSockets, metrics, and traces.
2. **Evaluate the feature matrix:** mark mandatory features, replaceable features, and features needing custom implementation. Specifically check `DiscoveryClient` auto-generated routes, Redis rate limiter, `GlobalFilter`, and custom filters.
3. **Create a test branch:** update the BOM and starter for the target stack; migrate prefixes; remove conflicting dependencies; keep baseline configs for comparison.
4. **Migrate routes and filters:** preserve route IDs, predicates, upstreams, and transformation intent. Rewrite custom filters/Java DSL against the new APIs; swap rate limiter, discovery, or TLS implementations as needed.
5. **Functional testing:** test route matching, route order, path/header rewrites, queries/bodies, status codes, load balancing, discovery, fallbacks, retries, rate limits, security, TLS, and WebSockets.
6. **Load and fault testing:** simulate slow upstreams, connection failures, timeouts, and missing instances; measure throughput, p95/p99 latency, CPU, heap, threads, connection pools, and error rates. Test large request bodies with retries/body caching.
7. **Canary deployment:** send a slice of traffic through the new stack, comparing status codes, matched routes, upstreams, latency, metrics, and traces. Increase traffic only when acceptance criteria are met.
8. **Prepare rollback:** keep artifacts, configs, and dashboards of the old stack; document how to shift traffic back and sync route/config state across instances.

## Minimum Post-Migration Test Suite

| Scenario | What to confirm |
|---|---|
| Path, Host, Method, Header, Cookie, and Query | Correct route selected; overlapping routes preserve order |
| `StripPrefix`, `RewritePath`, `SetPath`, header filters | Upstream receives exact path/headers; responses do not leak internal headers |
| `lb://orders-service` | Picks an instance, handles zero instances properly, and does not send the wrong scheme |
| Discovery locator (if used) | New services are discovered, routes generated accurately, and service ID path segment rewritten |
| Rate limit | Per-user/API-key quotas, burst, reset, distributed state, and over-limit responses |
| Circuit breaker and retry | Correct fallbacks; non-idempotent operations not retried unprotected; no unintended duplicate requests |
| OAuth2/JWT and token relay | Authentication, authorization, audience/scope, and downstream token headers accurate |
| HTTPS to Gateway and upstream | Certificates, hostname verification, trust stores, timeouts, and mTLS (if used) work |
| WebSocket | Handshake, `Origin`, subprotocol, heartbeat, reconnect, and closure |
| Metrics and tracing | Dashboards/alerts have route, status, latency, and correlation IDs after stack change |

## Signs of an Incomplete Migration

- The MVC app starts up, yet routes previously auto-generated from `DiscoveryClient` vanish.
- Rate limiting still returns 429, yet buckets are no longer shared across instances.
- Logging or auth filters run in the wrong order after converting from `GlobalFilter` to Servlet/handler filters.
- Upstream TLS fails because legacy trust-store settings are no longer used by `RestClient`.
- WebSocket handshake succeeds, yet heartbeats or backend error handling changed.
- Dashboards lose route ID metrics, preventing route- or upstream-scoped alerts from detecting failures.

When encountering these symptoms, return to the feature matrix to determine whether the discrepancy sits in the runtime, extension points, dependencies, or configuration. Do not declare completion solely because the application builds and health checks return `UP`.

## References

- [Spring Cloud Gateway — Overview of Server and Proxy Exchange Variants](https://docs.spring.io/spring-cloud-gateway/reference/index.html)
- [How to Include Spring Cloud Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html)
- [How to Include Spring Cloud Gateway Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/starter.html)
- [Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html)
- [Server Web MVC — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html)
- [Server Web MVC — Gateway Handler Filter Functions](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-handler-filter-functions.html)
- [Server Web MVC — RateLimiter Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/ratelimiter.html)
- [Server Web MVC — LoadBalancer Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html)
- [Server Web MVC — TLS and SSL](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/tls-and-ssl.html)
- [Server Web MVC — WebSockets](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/websockets.html)
- [Server WebFlux — DiscoveryClient Route Definition Locator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/the-discoveryclient-route-definition-locator.html)
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)

Switching between WebFlux and Web MVC changes Gateway's runtime and extension model. Use the matrix to lock down non-negotiable features, then migrate dependencies, namespaces, filters, discovery, rate limiting, TLS, and request observability step by step. A migration is complete only when real requests and failure behavior match the system's operational requirements.
