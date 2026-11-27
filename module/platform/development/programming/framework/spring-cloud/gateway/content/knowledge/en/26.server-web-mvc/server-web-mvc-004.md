# Declaring Web MVC Routes via Configuration or Java DSL

## 1. Problem: One Route, Two Declaration Styles

In a microservices architecture, **Spring Cloud Gateway** serves as the common entry point: route predicates select where requests are handled, filter chains modify paths/headers, service discovery locates upstream instances, and policies for authentication, rate limiting, circuit breakers, retries, TLS, and request observability enable safe operations.

Spring Cloud Gateway has two server branches to distinguish:

- **Server WebFlux** is built on WebFlux, Project Reactor, and Netty; its Java DSL typically uses `RouteLocatorBuilder`, `RouteLocator`, and `GatewayFilter`.
- **Server Web MVC** is built on **Servlet and Spring WebMvc.fn**; its Java DSL creates `RouterFunction<ServerResponse>` from `GatewayRouterFunctions` and `HandlerFunctions.http()`.

The topic **"Declaring Web MVC Routes via Configuration or Java DSL"** belongs to the **Server Web MVC** chapter of the **SPRING_CLOUD_GATEWAY** module. This hands-on lesson revolves around a single route:

~~~text
Client:
  GET http://localhost:8080/api/catalog/products/42

Gateway Server Web MVC:
  Path=/api/catalog/**
  Method=GET
  StripPrefix=1
  AddRequestHeader=X-Edge-Source, mvc-gateway

Mock catalog-service:
  GET http://localhost:8081/catalog/products/42
  X-Edge-Source: mvc-gateway
~~~

We will define this route using **YAML** and the **Java DSL**, then verify both approaches produce the same outcome. The lesson also covers multiple routes, combining predicates, `lb://`, and common configuration pitfalls.

> **Important note on versions:** Spring Cloud Gateway **Server MVC 4.2** uses starter `spring-cloud-starter-gateway-mvc` and property `spring.cloud.gateway.mvc.routes`. Documentation for **Server Web MVC 4.3/5.x** uses starter `spring-cloud-starter-gateway-server-webmvc` and property `spring.cloud.gateway.server.webmvc.routes`. These are release-train variants; **do not declare both simultaneously** "just to be safe." Always verify the BOM, dependencies, and effective configuration of your actual application.

### Learning Outcomes

After this lesson, you will be able to:

1. Recognize how WebMvc.fn routes differ from reactive WebFlux routes.
2. Declare `id`, `uri`, `predicates`, and `filters` in YAML for the right version.
3. Write Java DSL routes using `@Bean RouterFunction<ServerResponse>`, `route("id")`, `http()`, and `before(uri(...))`.
4. Combine Path, Method, and Host; transform paths with `StripPrefix`/`RewritePath`.
5. Use service discovery via `lb://` (YAML) or `lb()` (Java).
6. Test real requests reaching upstream while avoiding route overlap, SSRF, and missing security.

## 2. How Server Web MVC Processes Requests

In Gateway Server Web MVC, routes are regular **Spring WebMvc.fn** `RouterFunction` definitions paired with an HTTP proxy handler supplied by Gateway.

~~~mermaid
flowchart LR
    C["HTTP Client"] --> T["Servlet Container<br/>Tomcat / Jetty"]
    T --> M["Spring MVC HandlerMapping"]
    M --> P{"RequestPredicate<br/>Path / Method / Host"}
    P -->|"Match"| B["Before filters<br/>URI, StripPrefix, Header"]
    P -->|"No"| N["Other route or no match"]
    B --> H["HandlerFunctions.http()"]
    H --> U["Upstream HTTP service"]
    U --> A["Response / after filters"]
    A --> C
~~~

Three parts make up a route:

| Component | Question | Example |
| --- | --- | --- |
| **Predicate** | Which requests are allowed to match this route? | Path, Method, Host |
| **Handler** | Once matched, what does the handler do? | `HandlerFunctions.http()` HTTP proxy |
| **Filter** | Which request/response transforms or policies apply? | `StripPrefix`, `AddRequestHeader`, retry |

Core Java types:

~~~java
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions
org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions
org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions
~~~

**Do not use `Mono<Void>`, `ServerWebExchange`, or `RouteLocatorBuilder` from WebFlux examples** to declare MVC routes. MVC uses the Servlet model with WebMvc.fn before/after/handler filters.

### 2.1. Distinguishing Public URL, Route Path, and Target URI

| Component | URL or path |
| --- | --- |
| Browser/client sends | `http://localhost:8080/api/catalog/products/42` |
| Gateway MVC matches | `/api/catalog/products/42` |
| After `StripPrefix=1` | `/catalog/products/42` |
| Upstream origin | `http://localhost:8081` |
| Backend receives | `GET /catalog/products/42` |

**A path in `uri` should not be relied upon to implicitly add a prefix.** Gateway MVC's *How It Works* documentation states that paths declared in a route URI are ignored. If you need to alter paths, use a supported `StripPrefix`, `SetPath`, `PrefixPath`, or `RewritePath` filter and verify the final path upstream.

## 3. Preparing the Right Stack Dependencies

### 3.1. 4.3/5.x Line — Server Web MVC

In a `pom.xml` whose versions are managed by a compatible **Spring Cloud BOM**:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

This Server Web MVC branch works with Servlet runtimes like Tomcat/Jetty. Do not mistake it for a reactive Netty program just because the library name contains Gateway.

### 3.2. 4.2 Line — Server MVC

~~~xml
<!-- For a release train compatible with SCG MVC 4.2 -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-mvc</artifactId>
</dependency>
~~~

Do not add both starters to the same application without explicit guidance from your chosen release. If a project already uses the **Server WebFlux** starter, do not apply the MVC routes in this lesson as if they shared the same runtime.

### 3.3. Prerequisites for Running Examples

- Gateway at `http://localhost:8080`.
- Mock catalog backend at `http://localhost:8081`, supporting `GET /catalog/products/42`.
- Mock order backend at `http://localhost:8082`, supporting `POST /orders/create`.
- Compatible Spring Boot / Spring Cloud versions.
- If Spring Security is enabled, use Servlet `SecurityFilterChain`; provide test credentials for protected routes.
- For `lb://`, Spring Cloud LoadBalancer and an appropriate `ServiceInstance` source are required.

`localhost` illustrates processes running on the **same host**. In Kubernetes or Docker, it does not point to another pod/container; use service DNS.

## 4. Declaring Routes via YAML in Server Web MVC 4.3/5.x

Main fields of a route:

| Field | Meaning | Example |
| --- | --- | --- |
| `id` | Route identifier | `catalog-read` |
| `uri` | Proxy target address | `http://localhost:8081` |
| `predicates` | Conditions selecting requests | `Path`, `Method`, `Host` |
| `filters` | Route transforms/policies | `StripPrefix`, `AddRequestHeader` |
| `order` | Ordering value when supported by model/config | Must be verified by integration tests |
| `metadata` | Additional metadata if supported by version | Does not replace authentication |

Example `application.yml` for **4.3/5.x**:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Explanation:

1. `Path=/api/catalog/**` permits catalog paths.
2. `Method=GET` restricts the route to GET requests.
3. Predicates within the same route are **AND-combined**: both Path and Method must match.
4. `StripPrefix=1` removes the first segment (`api`), so the backend receives `/catalog/products/42`.
5. `AddRequestHeader` appends `X-Edge-Source: mvc-gateway` sent to the backend.
6. `uri` identifies the HTTP request origin and does not itself enforce business logic or security.

Example client request:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: localhost:8080
~~~

Expected request seen by the mock backend:

~~~http
GET /catalog/products/42 HTTP/1.1
X-Edge-Source: mvc-gateway
~~~

This is **expected behavior**, not an executed test output. The outbound `Host` header also depends on the HTTP proxy/client and filters; inspect it at the backend rather than hardcoding assumptions about `Host`.

### 4.1. Mind the Namespace Name

In MVC 4.3/5.x, `spring.cloud.gateway.server.webmvc.routes` **differs** from:

~~~yaml
# COUNTER-EXAMPLE: this is not the routes namespace for MVC 4.3/5.x.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
~~~

`server.webflux` is for Server **WebFlux**. A syntactically valid YAML file using the wrong prefix will fail to bind as an MVC route, yielding 404s. Inspect startup logs, `configprops`, and test actual routes.

### 4.2. Do Not Enable the Equivalent Java Route at the Same Time

This lesson uses the same Path/Method in both YAML and Java to teach both styles. When running:

- Pick **YAML** and disable the equivalent Java bean; or
- Pick **Java DSL** and remove/disable the equivalent YAML route.

If both match `GET /api/catalog/**`, you create route overlap and cannot easily tell which handled the request. There is no guarantee across versions that Java routes automatically override YAML or vice versa.

## 5. YAML Variant for Server MVC 4.2

In the **4.2** branch, the routes property is `spring.cloud.gateway.mvc.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: catalog-read
            uri: http://localhost:8081
            predicates:
              - Path=/api/catalog/**
              - Method=GET
            filters:
              - StripPrefix=1
              - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Version table:

| Branch | Starter | Route prefix |
| --- | --- | --- |
| **MVC 4.2** | `spring-cloud-starter-gateway-mvc` | `spring.cloud.gateway.mvc.routes` |
| **Web MVC 4.3/5.x** | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |
| **WebFlux** | Corresponding WebFlux starter | Separate WebFlux prefix; do not use either prefix above |

**Do not keep both route lists side by side to cover every version.** During upgrades, perform a reviewed migration, keep only the configuration read by the active version, and test routes after startup.

## 6. Declaring Routes via Java DSL

The recommended Java DSL uses `GatewayRouterFunctions.route("route-id")` and `HandlerFunctions.http()`.

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
public class CatalogRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogReadRoute() {
        return route("catalog-read")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:8081"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }
}
~~~

Line-by-line mapping:

| Java DSL | YAML |
| --- | --- |
| `route("catalog-read")` | `id: catalog-read` |
| `.GET("/api/catalog/**", http())` | `Path=/api/catalog/**`, `Method=GET` |
| `.before(uri("http://localhost:8081"))` | `uri: http://localhost:8081` |
| `.before(stripPrefix(1))` | `StripPrefix=1` |
| `.before(addRequestHeader("X-Edge-Source", "mvc-gateway"))` | `AddRequestHeader=X-Edge-Source, mvc-gateway` |
| `.build()` | Completed route definition |

The `@Bean` must reside within component scan coverage. If the Java class is not registered, the route will not appear even though the code compiles.

### 6.1. Why Use `GatewayRouterFunctions.route("id")`?

Spring WebMvc.fn provides a plain builder:

~~~java
import static org.springframework.web.servlet.function.RouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

// Example inside a @Bean returning RouterFunction<ServerResponse>:
return route()
        .GET("/get", http())
        .before(uri("https://example.org"))
        .build();
~~~

Gateway also provides `org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route(String routeId)`, which attaches the **route ID to request metadata**, useful for advanced Gateway filters and observability. For production-grade Gateway routes, `route("catalog-read")` preserves an explicit identifier.

**Do not confuse** this with WebFlux's `RouteLocatorBuilder` just because both have a method named `route`.

### 6.2. Why Does `http()` Go with `before(uri())`?

Current Gateway MVC docs guide users to write:

~~~java
.GET("/api/catalog/**", http())
.before(uri("http://localhost:8081"))
~~~

The parameterless `http()` looks up the target URI from request attributes populated by filters such as `uri()`. Since **4.1.7** docs, `HandlerFunctions.http(String)` and `http(URI)` are marked deprecated; the newer style standardizes how target URIs are managed.

Without a URI filter or an appropriate load-balancer filter, the HTTP handler has no target. Therefore, never write `.GET("/api/catalog/**", http()).build()` expecting it to call upstream on its own.

## 7. Declaring Multiple Routes in YAML

Example with catalog reads and order writes:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway

            - id: orders-write
              uri: http://localhost:8082
              predicates:
                - Path=/api/orders/**
                - Method=POST
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Expected routing matrix:

| Client request | Matching route | Upstream request |
| --- | --- | --- |
| GET `/api/catalog/products/42` | `catalog-read` | GET `/catalog/products/42` on 8081 |
| POST `/api/orders/create` | `orders-write` | POST `/orders/create` on 8082 |
| POST `/api/catalog/products` | Matches neither route above | Not proxied via `catalog-read` |
| GET `/api/orders/42` | Matches neither route above | Not proxied via `orders-write` |
| GET `/api/unknown` | No match | Not proxied |

The final HTTP status on an unmatched route depends on other `HandlerMapping` beans, Spring Security, and application config; it may be 404/405 or another response. The **key assertion** is that requests do not reach the backend through the wrong route.

### 7.1. Method Predicates Do Not Replace Authorization

`Method=POST` selects the write route, yet **does not prevent duplicate transactions** or authenticate the user. For `POST /payments`, enforce permissions, input validation, credential-appropriate CSRF protection, and `Idempotency-Key`/backend deduplication if retries are enabled.

## 8. Declaring Multiple Routes via Java DSL

Multiple `RouterFunction` beans can be registered:

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
public class GatewayRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogRead() {
        return route("catalog-read")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:8081"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }

    @Bean
    RouterFunction<ServerResponse> ordersWrite() {
        return route("orders-write")
                .POST("/api/orders/**", http())
                .before(uri("http://localhost:8082"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }
}
~~~

These two Java beans are an **alternative**, not meant to run simultaneously with YAML routes sharing the same Paths/IDs during comparison. When combining both approaches, govern ownership and precedence explicitly.

### 8.1. With Java DSL, You Can Organize by Domain

For example, `CatalogRoutes`, `OrdersRoutes`, and `PartnerRoutes` classes can each own a group of endpoints. Even then, you still need:

- A single source of truth for route IDs.
- Tests for predicate conflicts across classes.
- Rules for managing target URIs per environment.
- Logging/metrics keyed by stable route IDs.
- Code reviews on changes touching authentication or target hosts.

## 9. Combining Advanced Predicates in Java

Spring WebMvc.fn `RequestPredicate` supports `.and()`, `.or()`, and `.negate()`. Gateway MVC adds `GatewayRequestPredicates` for common conditions.

### 9.1. Combining Host and Path

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.host;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

@Configuration
class PartnerRoutes {

    @Bean
    RouterFunction<ServerResponse> partnerCatalog() {
        return route("partner-catalog")
                .route(
                    host("partner.example.test")
                        .and(path("/partner/catalog/**")),
                    http())
                .before(uri("http://localhost:8081"))
                .build();
    }
}
~~~

This route requires **Host = partner.example.test AND Path match**. To restrict it to GET-only, add `method(HttpMethod.GET)` or use the appropriate builder method to maintain consistent semantics.

`Host` is HTTP metadata that can be spoofed depending on network context; **Host predicates do not replace authentication**. Require verified tokens/API keys, TLS, and service-level authorization.

### 9.2. OR and NEGATE

An API group may allow two paths:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

// An example RequestPredicate:
path("/api/catalog/**").or(path("/api/products/**"))
~~~

Or match paths excluding a specific prefix:

~~~java
// Illustrates RequestPredicate operators only, not a security policy.
path("/api/**").and(path("/api/admin/**").negate())
~~~

These operators help express routing logic, yet **you must never treat path NEGATION as the sole protection for `/api/admin/**`**. Spring Security and backend authorization must still enforce access control.

### 9.3. YAML Path + Method Is AND

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
~~~

All predicates within the same route must match together. In Java, `.GET(path, http())` expresses the equivalent Method+Path condition for simple cases.

## 10. Gateway MVC Filters: `before`, `after`, and `filter`

In **WebMvc.fn**, the API groups serve different purposes:

| Group | Examples | Purpose |
| --- | --- | --- |
| `before` | `BeforeFilterFunctions.uri`, `stripPrefix`, `addRequestHeader` | Transforms `ServerRequest` before the proxy handler |
| `after` | `AfterFilterFunctions` functions | Transforms `ServerResponse` where appropriate |
| `filter` | `LoadBalancerFilterFunctions.lb`, resilience filters | Wraps handler logic or handles advanced routing |
| WebFlux GatewayFilter | Reactive `GlobalFilter`, `GatewayFilter` | **Not** used directly as WebMvc.fn filters |

Example:

~~~java
.before(uri("http://localhost:8081"))
.before(stripPrefix(1))
.before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
~~~

The order of request transformations can affect the final target, especially when combining path filters with load balancing. Do not assume WebFlux filters share identical Java parameters or behavior when moved to MVC.

### 10.1. Writing a Small Custom Before Filter

If you truly need a custom request transformation, WebMvc.fn lets `before` accept a `Function<ServerRequest, ServerRequest>`:

~~~java
import org.springframework.web.servlet.function.ServerRequest;
import java.util.function.Function;

static Function<ServerRequest, ServerRequest> addRequestTag() {
    return request -> ServerRequest.from(request)
            .header("X-Gateway-Tag", "catalog")
            .build();
}
~~~

Then invoke it:

~~~java
.before(addRequestTag())
~~~

However, for operations already provided by Gateway like adding headers, **prefer built-in filters** to minimize custom code and ease upgrades and testing.

**Do not place tokens or raw user identities into headers just because a Java filter can.** Identity-bearing headers must come from trusted authentication and be validated downstream per contract.

## 11. Service Discovery: `lb://` in YAML and `lb()` in Java

### 11.1. YAML

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-read-lb
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

`lb://ORDER-SERVICE` is a special URI scheme. Gateway MVC requires LoadBalancer/discovery to resolve instances for service ID `ORDER-SERVICE`. It does not start a registry or invent instances on its own.

### 11.2. Java DSL

Gateway Server MVC documentation requires calling **`lb()` explicitly** in the Java DSL:

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.LoadBalancerFilterFunctions.lb;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
class OrdersLoadBalancedRoutes {

    @Bean
    RouterFunction<ServerResponse> ordersRead() {
        return route("orders-read-lb")
                .GET("/api/orders/**", http())
                .before(stripPrefix(1))
                .filter(lb("ORDER-SERVICE"))
                .build();
    }
}
~~~

**Crucial details:**

- YAML `uri: lb://ORDER-SERVICE` and Java `.filter(lb("ORDER-SERVICE"))` both describe routing via `ServiceInstance`.
- Java uses the parameterless `http()`, while the LoadBalancer filter resolves the final URI.
- When using `stripPrefix()` or `setPath()`, apply them **before `lb()`** to prevent malformed route URLs.
- When no service instance exists, the default response is typically **503**; check your version's error policy.
- `ServiceInstance.isSecure` may determine HTTP vs. HTTPS for the backend hop; inbound HTTPS does not guarantee outbound HTTPS.

**Do not add `@LoadBalanced RestClient.Builder` to Gateway MVC's internal HTTP client.** Gateway has its own proxy client; attempting to load-balance again through a `RestClient` interceptor can break the URL already resolved by `lb()`.

### 11.3. Expected Processing Flow

~~~text
GET /api/orders/42
 -> StripPrefix(1)
 -> /orders/42
 -> lb("ORDER-SERVICE")
 -> ServiceInstance(host=orders-1, port=8080)
 -> Proxy HTTP GET /orders/42
~~~

This is an illustrative flow. To verify, mock/discovery tests must inspect **the exact path received by the backend**, not just a 200 status at the client.

## 12. `RewritePath` When `StripPrefix` Is Not Enough

Suppose you want to transform:

~~~text
/public/catalog/products/42 -> /catalog/products/42
~~~

For static prefixes, `StripPrefix=1` is usually simpler. For complex mappings, you can use `RewritePath` with regex.

Illustrative Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.rewritePath;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

// Body inside a @Bean returning RouterFunction<ServerResponse>:
return route("legacy-path-rewrite")
        .GET("/legacy/**", http())
        .before(uri("http://localhost:8081"))
        .before(rewritePath("/legacy/(.*)", "/$1"))
        .build();
~~~

The Java snippet captures regex group 1. In YAML, `$`/`${...}` can easily be misinterpreted by Spring property placeholders or the YAML parser; consult the `RewritePath` docs for your **exact version** and test replacements with varied paths, including URL-encoded characters.

**Note:** Gateway MVC documentation warns that **paths written inside the target URI are ignored**. To prepend `/v2` upstream, do not write `uri: http://host/v2` expecting it to work automatically. Use the appropriate path filter and assert the backend path.

## 13. Avoiding Route Overlap and Duplicate Route IDs

Suppose you declare:

~~~text
Route A: Path=/api/**
Route B: Path=/api/orders/**
Request: GET /api/orders/42
~~~

Both A and B can match. If A proxies to another gateway or an unauthenticated target, the impact can be far worse than a 404.

**Do not assume "the most specific route always wins"** when combining multiple `RouterFunction` beans, YAML routes, route metadata, and other MVC handlers. Instead:

1. Keep predicates sufficiently narrow, combining Method/Host as needed.
2. Never duplicate route IDs across YAML and Java.
3. Establish clear route ownership; avoid assuming "Java overrides YAML."
4. Check registration/precedence rules of your **exact version** if overlap is unavoidable.
5. Write integration tests for `/api/orders`, `/api/orders/`, `/api/orders/42`, and `/api/orders-old`.
6. Run security/authorization tests whenever adding a new route.

### 13.1. Java DSL Does Not Mean Arbitrary Runtime Route Updates

A `@Bean RouterFunction` created when the `ApplicationContext` starts does not automatically change if you edit a Java file or YAML on disk. Updating routes at runtime requires mechanisms supported by your **Server MVC** version; do not copy WebFlux's `RouteDefinitionRepository`/`RefreshRoutesEvent` directly.

Across multiple replicas, verify every replica runs the updated route/app version rather than editing config on a single pod.

## 14. Where Does MVC Differ from WebFlux?

| Topic | Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- | --- |
| Runtime | WebFlux/Reactor/Netty | Servlet/Tomcat/Jetty |
| Java route | `RouteLocatorBuilder`, `RouteLocator` | `RouterFunction<ServerResponse>`, `GatewayRouterFunctions` |
| Proxy handler | Reactive routing chain | `HandlerFunctions.http()` |
| Context | `ServerWebExchange` | `ServerRequest` / Servlet |
| Route filters | `GatewayFilter`, `GlobalFilter` | `.before()`, `.after()`, `.filter()` |
| Security | `SecurityWebFilterChain` | Servlet `SecurityFilterChain` |
| Config | Dedicated WebFlux prefix | `gateway.mvc` (4.2) or `gateway.server.webmvc` (4.3/5.x) |

Bad copy-paste counter-example:

~~~java
// This is Gateway WebFlux style, NOT Server Web MVC Java DSL:
@Bean
RouteLocator customRoutes(RouteLocatorBuilder builder) {
    return builder.routes()
            .route("catalog", r -> r.path("/api/catalog/**")
                    .uri("http://localhost:8081"))
            .build();
}
~~~

In MVC, Java routes must return `RouterFunction<ServerResponse>`; this is not a trivial import swap.

### 14.1. Security Uses the Servlet Chain

Short example of Servlet Security style:

~~~java
// Standalone snippet; requires @Bean, imports, and Resource Server configuration.
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

This example uses a Bearer JWT resource server; when using cookie/session authentication, evaluate and enable proper **CSRF protection** rather than disabling CSRF mechanically. Security filters are never replaced by a `Host` route predicate or client-sent `X-User` headers.

## 15. Testing YAML and Java DSL with `curl`

### 15.1. Preparation

Assume Gateway runs on port 8080 and the mock upstream runs on port 8081. Enable **either the YAML route or the Java bean**, never both for the same path.

Send:

~~~bash
curl -i http://localhost:8080/api/catalog/products/42
~~~

The mock upstream should record:

~~~text
Method = GET
Path = /catalog/products/42
X-Edge-Source = mvc-gateway
~~~

This is an **expected outcome**, not an executed test.

### 15.2. Testing Method Mismatch

~~~bash
curl -i -X POST http://localhost:8080/api/catalog/products/42
~~~

Route `catalog-read` must not proxy POST to the catalog backend. Client-side status codes may vary depending on `HandlerMapping`, Security, and other handlers; the key assertion is that **the upstream counter does not increment via the GET route**.

### 15.3. Testing Query Strings

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42?lang=vi"
~~~

With a config that does not alter queries, the backend is expected to receive path `/catalog/products/42` and query `lang=vi`. Verify at the mock server rather than relying only on the response body if the mock returns static data.

### 15.4. Comparing the Java Approach

Disable the YAML route, enable the equivalent `@Bean RouterFunction`, restart, re-run the three `curl` commands above, and compare method/path/header/outcome. Never enable both configs at once when proving equivalence.

If the Java route does not trigger, check:

- Is the `@Configuration` class inside component scan?
- Is the `RouterFunction` bean registered?
- Are imports for `GatewayRouterFunctions.route`, `HandlerFunctions.http`, and `BeforeFilterFunctions.uri` right?
- Is another route/Controller matching the path first?
- Is the mock backend running?
- Are the property/starter right for the chosen version?

## 16. Automated Testing with Servlet/MVC Tools

The right toolset is **`MockMvc`**, `@SpringBootTest(webEnvironment = RANDOM_PORT)` + an HTTP test client, and a mock upstream such as WireMock/MockWebServer. **Do not** use `StepVerifier`/`MockServerWebExchange` as the primary approach for a pure Servlet Gateway MVC.

An integration test should:

1. Start Gateway with **one route style**.
2. Start a mock catalog backend on a port injected via properties or test configuration.
3. Have the backend return 200 and JSON containing the ID.
4. Send GET to the gateway test port; assert status/body.
5. Verify the backend received **exactly** `GET /catalog/products/42`.
6. Verify `X-Edge-Source` appears with the single expected value.
7. Send POST to the same path; assert the backend **did not** receive another request via the GET route.
8. Test an unmatched path and a boundary path.
9. Test a disconnected backend to observe error mapping.
10. When security is active, test missing tokens/missing permissions to ensure routes cannot be bypassed.

Pseudo-test illustrating assertions:

~~~java
// Pseudocode, not an actual API from a specific library:
gateway.get("/api/catalog/products/42").expectStatus(200);
catalogStub.verifyRequest("GET", "/catalog/products/42");
catalogStub.verifyHeader("X-Edge-Source", "mvc-gateway");

gateway.post("/api/catalog/products/42").expectNotProxiedBy("catalog-read");
catalogStub.verifyRequestCount(1);
~~~

Names like `expectNotProxiedBy` only **describe what to assert**, not methods you can copy and run directly. In implementation, use the real APIs of `MockMvc`, RestAssured, WireMock, or MockWebServer.

## 17. Security and Operations of MVC Routes

Declaring routes is only part of a Gateway. Moving to production requires:

- **Authentication/authorization:** use Spring Security Servlet and enforce resource permissions at the backend.
- **Input validation:** `Path`/`Host` do not replace business data validation.
- **TLS:** inbound HTTPS does not create outbound HTTPS; choose secure URIs/ServiceInstances per policy.
- **SSRF:** target URIs must come from trusted config/allowlists, never arbitrary client queries/headers.
- **Retries:** never retry payment/order POSTs without backend idempotency.
- **Rate limiting:** key on verified identities, never client-supplied `X-User-ID`.
- **Circuit breakers:** fallbacks must never report false success if the backend executed a write whose response was lost.
- **CORS:** governs browser JavaScript, not authentication.
- **Observability:** track route IDs, methods, upstream paths, statuses, latency, and retry counts.
- **Deployment:** updating YAML/Java routes requires a rollout/reload strategy tested on your Server MVC version.

Never log raw `Authorization`, `Cookie`, access tokens, PII, or sensitive request bodies in the Gateway. Never put dynamic request IDs into high-cardinality metric labels.

## 18. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| YAML route not created | Wrong WebFlux/MVC or 4.2/4.3 prefix | Check starter, `configprops`, and route tests |
| Java route unused | Class not scanned, bean not loaded | Inspect `ApplicationContext` |
| Copied `RouteLocatorBuilder` into MVC | Used WebFlux API | Switch to `RouterFunction<ServerResponse>` |
| `http()` has no target | Missing `before(uri(...))`/LB | Specify an explicit target |
| `http("...")` marked deprecated | Older API | Use `http()` + `uri()` |
| Backend gets wrong path | Missing/wrong `StripPrefix` | Assert request path at mock |
| `uri: http://backend/base` does not prepend `/base` | Misunderstood URI path | Use a path filter |
| POST proxied by GET route | Route overlap or missing `Method=GET` | Separate predicates |
| Unpredictable route ordering | Overly broad routes or duplicate bean/YAML | Eliminate overlap, test precedence |
| Java lb route errors | Forgot `.filter(lb())` or missing discovery | Use the proper LB API |
| LB selects URL with wrong path | `lb()` placed before path filters | Transform path before LB |
| `Service Instance cannot be null` error | Double LB from `@LoadBalanced RestClient` | Do not attach LB interceptor to internal proxy |
| Works locally, fails in Docker | Used localhost for another container | Use Service DNS |
| 401/403 despite Path match | Servlet Security blocked request | Check auth/scope/CSRF |
| Right body, wrong backend | Multiple routes matched | Upstream request counter and trace |
| Changed YAML with no effect | Not restarted/reloaded | Use version-appropriate deployment/reload mechanism |
| Client sees CORS errors | Invalid CORS/credentials/preflight | Configure Servlet CORS and Security |
| `X-Edge-Source` header missing | Filter didn't run or different route matched | Inspect upstream headers |
| 503 on `lb://` | Service registry has no instances | Check discovery health |
| SSRF risk | URI taken from unchecked client data | Allowlist and egress policy |

## 19. Comprehensive Hands-On Exercise

**Scenario:** A Gateway Server Web MVC receives GET catalog and POST orders, backed by two mock services.

Requirements:

1. Pick a release train and declare the **correct MVC starter**.
2. Write `catalog-read` in YAML with `Path=/api/catalog/**` and `Method=GET`.
3. Add `StripPrefix=1` and header `X-Edge-Source: mvc-gateway`.
4. Create `orders-write` in YAML with `Method=POST` and `uri: http://localhost:8082`.
5. Assert GET catalog proxies to `/catalog/products/42`; POST catalog does not hit the GET route.
6. Disable YAML routes and write two equivalent `@Bean RouterFunction<ServerResponse>` routes in Java.
7. Try combining `Host` + `Path` with `.and()`; do not use Host in place of authentication.
8. Try an `orders-read-lb` route via `lb://ORDER-SERVICE` or `lb("ORDER-SERVICE")` once discovery is available.
9. Test intentional route overlap with `Path=/api/**`; observe and eliminate the conflict.
10. Test upstream errors, auth, latency, and real paths/headers before considering the route safe.

### Test Matrix

| Case | Expected outcome |
| --- | --- |
| T1: YAML MVC right prefix | Route is registered |
| T2: GET catalog | Backend receives `/catalog/products/42` |
| T3: POST catalog | Not proxied by the GET route |
| T4: Header filter | Backend receives `X-Edge-Source: mvc-gateway` |
| T5: Equivalent Java DSL | Path/method/header/response match YAML |
| T6: Wrong WebFlux prefix | Test shows MVC route was not loaded |
| T7: `lb://` missing instances | Reports discovery/503 status, does not invent services |
| T8: Route overlap | Test identifies selected route and eliminates duplication |
| T9: Unauthorized request | Blocked by security per policy |
| T10: Backend 5xx | Error/traces attribute to right route without hiding error |

These are **test criteria**, not claims that the examples have already been executed.

## 20. Pre-Production Checklist

- [ ] Project uses **Gateway Server Web MVC** on the Servlet stack.
- [ ] Starter and routes namespace match the **actual version**.
- [ ] Route `id` is unique with a clear owner.
- [ ] Path/Method/Host predicates are tight enough; unintended overlap avoided.
- [ ] YAML and Java DSL do not register duplicate routes.
- [ ] Java beans return `RouterFunction<ServerResponse>`, not WebFlux `RouteLocatorBuilder`.
- [ ] `GatewayRouterFunctions.route("id")` is used when route metadata is needed.
- [ ] `HandlerFunctions.http()` receives its target from `before(uri(...))` or `lb()`.
- [ ] Path filters are tested upstream; never rely on paths inside target URIs.
- [ ] `stripPrefix()` executes before `lb()`.
- [ ] `@LoadBalanced RestClient` is not blindly attached to Gateway's HTTP proxy.
- [ ] Mock upstream integration tests cover GET/POST/query/headers and unmatched routes.
- [ ] Spring Security Servlet, TLS, CSRF/CORS, and backend auth are properly configured.
- [ ] Target URIs are never chosen from untrusted client headers/queries.
- [ ] Retries/rate-limiting/circuit breakers are evaluated per business semantics.
- [ ] Metrics, logs, traces, and upstream request counters exist with credentials redacted.
- [ ] Environments use valid DNS/ports; no `localhost` left in production pods.
- [ ] A rollout/rollback plan exists for updating routes across replicas.
- [ ] Documentation for Gateway **Server Web MVC** matching the active release has been checked.

## 21. Summary and Official References

**Spring Cloud Gateway Server Web MVC** uses Servlet/Spring WebMvc.fn to build API Gateways. There are two main ways to declare routes:

- **YAML:** specify `id`, `uri`, `predicates`, and `filters` under `spring.cloud.gateway.mvc.routes` in 4.2 or `spring.cloud.gateway.server.webmvc.routes` in 4.3/5.x.
- **Java DSL:** register `@Bean RouterFunction<ServerResponse>`, build routes with `GatewayRouterFunctions.route("id")`, use `HandlerFunctions.http()` to proxy, and `.before(uri(...))`/`.before(stripPrefix(...))` to configure target and path.

Do not mix WebFlux DSL with MVC, do not assume URIs automatically append paths, and do not treat `Host` predicates as auth. For service discovery, YAML uses `lb://service-id`, while Java DSL requires the `lb("service-id")` filter per MVC docs. **Testing at the upstream** is the reliable way to verify method, path, headers, and target.

### Official Documentation

- [Spring Cloud Gateway Server Web MVC 5.0 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Spring Cloud Gateway Server MVC 4.2 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway-server-mvc/starter.html).
- [Spring Cloud Gateway Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/java-routes-api.html).
- [Spring Cloud Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Spring Cloud Gateway Server Web MVC — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html).
- [Spring Cloud Gateway Server Web MVC — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/stripprefix.html).
- [Spring Cloud Gateway Server Web MVC — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/addrequestheader.html).
- [Spring Cloud Gateway Server Web MVC — LoadBalancer](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html).
- [Spring Cloud Gateway Server Web MVC — RewritePath](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/rewritepath.html).
