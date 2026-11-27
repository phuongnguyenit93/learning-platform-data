# Servlet and WebMvc.fn Architecture of Gateway Server Web MVC

## 1. What is Gateway Server Web MVC and why understand its architecture?

**Spring Cloud Gateway** provides an entry point for microservices: selecting routes by HTTP conditions, transforming paths/headers, forwarding requests to backends, discovering services, and applying authentication and protection policies such as rate limiting, retry, circuit breaker, or TLS. When building a Gateway, you must choose a **web application model** suited to your project's runtime platform.

One option is **Spring Cloud Gateway Server Web MVC**: the variant of Spring Cloud Gateway built on **Spring MVC, the Servlet API, and WebMvc.fn**. It uses Spring Boot's Servlet platform, lets you declare proxy routes in a functional `RouterFunction` style, and uses familiar Servlet/MVC mechanisms to receive, process, and return HTTP responses.

This **differs from Spring Cloud Gateway Server WebFlux**, which is built on Spring WebFlux and Reactor. Both variants share the same business-level goals but differ significantly in **HTTP runtime, filter programming, request lifecycle, security APIs, and testing tools**. You cannot simply swap a few dependency names and copy a `GlobalFilter` returning `Mono<Void>` into a Server Web MVC application.

This lesson belongs to the **Server Web MVC** chapter of the **SPRING_CLOUD_GATEWAY** module and focuses on Servlet and WebMvc.fn architecture; examples of route predicates, filter chains, rewriting, service discovery, authentication, retry, TLS, and request observability are used to clarify how the components work together.

After this lesson, you will be able to:

1. Describe the path **Servlet container → Servlet Filter chain → DispatcherServlet → WebMvc.fn → Gateway handler/filter → upstream**.
2. Distinguish `HttpServletRequest`, `ServerRequest`, `HandlerFunction`, `RouterFunction`, and `ServerResponse`.
3. Understand **RouterFunctionMapping** and **HandlerFunctionAdapter** in how Spring MVC selects and runs functional handlers.
4. Distinguish **Servlet Filter**, **Spring Security FilterChain**, **Gateway MVC before/after filters**, and the **outbound HTTP client**.
5. Declare a Gateway Server Web MVC route using **YAML** and a route using the **Java RouterFunctions DSL**.
6. Recognize differences between Gateway MVC **namespaces/starters** across release lines.
7. Explain the impact of **Servlet threads, blocking I/O, connection pools, timeouts, and backpressure** on load capacity.
8. Design testing, logging, and operations for a Gateway MVC without widening permissions or leaking credentials.

> **Scope:** This lesson covers **Gateway Server Web MVC**, not Gateway Server WebFlux and not the legacy Spring Cloud Gateway ProxyExchange project. Examples use modern Spring Boot/Spring MVC; starter names, properties, filter factories, and Java DSLs may differ across releases. Choose a compatible Spring Boot + Spring Cloud BOM before applying, then check the actual API of that line.

## 2. Servlet Foundation: Who Actually Receives an HTTP Request?

When a Gateway Server Web MVC application starts, Spring Boot typically starts a **Servlet web application** with an embedded Servlet container, such as Tomcat or Jetty if versions and dependencies align. An HTTP request arrives at a configured server port, is handled by the container via the Servlet API, and is then passed to Spring MVC.

~~~mermaid
flowchart TD
    C["HTTP client"] --> P["Ingress / reverse proxy, if any"]
    P --> T["Servlet container: Tomcat / Jetty"]
    T --> F["Servlet Filter chain"]
    F --> DS["Spring MVC DispatcherServlet"]
    DS --> HM["HandlerMapping"]
    HM --> RF["WebMvc.fn RouterFunction"]
    RF --> HF["Gateway HandlerFunction"]
    HF --> HC["Outbound HTTP client"]
    HC --> U["Catalog / Orders service"]
    U --> HC
    HC --> HF
    HF --> DS
    DS --> T
    T --> C
~~~

In this flow, each component has its own responsibility:

| Component | Role | Do not confuse with |
| --- | --- | --- |
| **Servlet container** | Accepts sockets/HTTP, manages requests and responses, connections, threads, Servlet lifecycle | Reactor Netty of Gateway WebFlux |
| `jakarta.servlet.Filter` | Wraps the request path at the Servlet layer | Gateway MVC before/after filter |
| **Spring Security Servlet filter chain** | Authenticates and authorizes requests before entering the MVC handler | Gateway route predicate |
| `DispatcherServlet` | Front controller of Spring MVC, dispatches to the matching handler | Gateway HTTP client calling the backend |
| `RouterFunctionMapping` | Finds a `HandlerFunction` via WebMvc.fn routing | Reactive `RoutePredicateHandlerMapping` |
| `HandlerFunctionAdapter` | Coordinates execution of the selected `HandlerFunction` | WebFlux `GatewayFilterChain` |
| Gateway **before/handler/after filters** | Modifies requests, proxies, or adjusts responses per DSL/route | Application-wide Servlet Filter |
| **Outbound HTTP client** | Creates a new HTTP request to the backend, receives response | Servlet container receiving inbound traffic |

The model above is a **logical flow**; the container may support async Servlet and some implementations have streaming optimizations, but that **does not turn Server Web MVC into a Reactor-based WebFlux Gateway**.

### Requests at the Servlet Boundary

The underlying Servlet layer uses types such as:

~~~java
jakarta.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletResponse
jakarta.servlet.Filter
jakarta.servlet.FilterChain
~~~

In functional Spring MVC, you typically work at a higher level:

~~~java
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.HandlerFunction
~~~

These two API layers are related but **not identical**. `ServerRequest` is an abstraction aimed at functional handlers; it is **not** WebFlux's `org.springframework.web.reactive.function.server.ServerRequest`. When an IDE auto-imports the wrong reactive package, code fails to compile or mixes runtime models.

### Servlet Threading and I/O

In the traditional Servlet model, a request typically uses a request-handling thread while executing synchronous/blocking logic. The Gateway also uses an outbound HTTP client, connection pool, and dedicated timeouts to call the backend. Therefore, a slow upstream can hold **request threads or I/O resources** for a long time, depending on how the client and Servlet async are implemented.

Do not conclude that "Servlet always handles only one request per thread for the entire lifecycle," because Servlet async can release/dispatch threads at certain stages. Likewise, **do not assume all Gateway MVC filters/HTTP clients are non-blocking** just because the application has a few callbacks or streaming responses. Inspect the implementation and measure **thread occupancy, connection pool, queue depth, and latency**.

## 3. What is WebMvc.fn?

**WebMvc.fn** is Spring MVC's functional HTTP programming model. Instead of having to write a controller with `@RestController` and `@GetMapping`, you can define routes using `RouterFunction<ServerResponse>` and handle them via `HandlerFunction<ServerResponse>`.

Conceptually, a functional route looks like:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().body("Hello from MVC"))
                .build();
~~~

This is a **regular Spring MVC WebMvc.fn** example, not yet a Gateway proxy. It illustrates that:

1. `RouterFunction` holds the request-matching rules.
2. A predicate such as `GET("/hello", ...)` specifies the method/path.
3. `HandlerFunction` receives a `ServerRequest` and returns a `ServerResponse`.
4. `DispatcherServlet`, through the MVC infrastructure, locates and invokes the corresponding handler.

If you want to proxy to a backend instead of generating a Hello string directly, **Gateway Server Web MVC** provides specialized handlers and filters to send outbound requests.

### Annotation MVC and Functional MVC Can Coexist

Within a single Spring MVC application, `@RestController` endpoints and `RouterFunction` routes can be registered together. For example:

- `@RestController` for a custom internal check endpoint.
- `RouterFunction` for Gateway proxy routes.
- Spring Boot Actuator for health/metrics on the management HTTP surface.

However, coexisting **does not mean passing through the same Gateway route filter**. You must know which `HandlerMapping` selects a request and which security/Servlet filters apply along the path. A `Gateway MVC before filter` attached to the Catalog route does not automatically run for `@GetMapping("/internal/info")` in another controller.

### Type Structure

~~~text
RouterFunction<ServerResponse>
    match(ServerRequest)
           |
           v
HandlerFunction<ServerResponse>
    handle(ServerRequest)
           |
           v
ServerResponse
    status + headers + body
~~~

This is the **imperative/function-based** model of WebMvc.fn. Unlike WebFlux Web.fn, an MVC `HandlerFunction` **does not return `Mono<ServerResponse>`**. MVC route filters also do not directly use `Mono<Void>` and `GatewayFilterChain` like Gateway Server WebFlux.

## 4. From DispatcherServlet to Gateway Proxy Handler

A more concrete diagram when a client calls `GET /api/catalog/products/42`:

~~~mermaid
sequenceDiagram
    participant Client
    participant Container as Servlet container
    participant Security as Servlet Security chain
    participant MVC as DispatcherServlet
    participant Router as WebMvc.fn RouterFunctionMapping
    participant Gateway as Gateway handler + filters
    participant Backend as Catalog service
    Client->>Container: GET /api/catalog/products/42
    Container->>Security: Servlet FilterChain
    Security-->>Container: Authorized request continues
    Container->>MVC: Servlet request
    MVC->>Router: Find matching route
    Router-->>MVC: HandlerFunction
    MVC->>Gateway: Execute MVC handler
    Gateway->>Gateway: before filters: path/header changes
    Gateway->>Backend: HTTP request via outbound client
    Backend-->>Gateway: 200 + JSON
    Gateway->>Gateway: after filters: response adjustments
    Gateway-->>MVC: ServerResponse
    MVC-->>Container: HTTP response
    Container-->>Client: 200 + JSON
~~~

**Key steps:**

1. **Container receives the request:** manages the connection, HTTP parser limits, request body, and response stream.
2. **Servlet filters:** can perform encoding, tracing, authentication, and authorization; Spring Security typically sits at this layer.
3. **DispatcherServlet:** looks up a handler using Spring MVC's `HandlerMapping` mechanism.
4. **WebMvc.fn routing:** `RouterFunctionMapping` evaluates route predicates; on match, `HandlerFunctionAdapter` bridges execution of the corresponding handler.
5. **Gateway MVC filters:** before/after steps can alter URI, path, headers, request context, and response according to filter factory/version capabilities.
6. **Gateway HTTP handler:** creates an outbound HTTP request to the selected backend using the appropriate client/request factory and network stack.
7. **Backend returns response:** Gateway processes status/headers/body, applies after steps, and returns `ServerResponse` to MVC.
8. **Container sends response:** the response goes to the client; outer Servlet filters may still run their post-processing logic.

**Critical boundary:** This is a **two-HTTP-connection** flow — client → Gateway and Gateway → backend. The Gateway does not "forward the raw ServletRequest onto another socket"; it must construct **an outbound request** with the appropriate method, URI, headers, and body, then translate the result back to the inbound response.

### Common Confusion: Route Match Does Not Mean Proxy Request Succeeded

A RouterFunction can match successfully, yet outbound execution can:

- Fail to resolve `lb://catalog-service` because discovery has no instances.
- Encounter a DNS, TCP connect, or TLS handshake error.
- Time out because the backend is too slow or the connection pool is exhausted.
- Be short-circuited by a CircuitBreaker according to route policy.
- Have been blocked earlier by Spring Security, so the Gateway handler never runs.

Therefore, you must distinguish **route lookup**, **request filtering**, **outbound transport**, and **response delivery**. An HTTP 404 from an unmatched route differs from an HTTP 404 returned by the Catalog backend, and an HTTP 503 when no instance exists differs from a 503 actively returned by the backend.

## 5. WebMvc.fn Predicates and Gateway MVC Route Predicates

A `RouterFunction` is selected when a request satisfies conditions: path, HTTP method, host, or headers depending on the version's predicates/factories. Gateway Server Web MVC maps that concept into **route definitions** with IDs, URIs, predicates, and filters.

Example design conditions:

| Condition | Meaning | Example |
| --- | --- | --- |
| Path | Accepts a group of paths | `/api/catalog/**` |
| Method | Restricts HTTP methods | `GET`, `HEAD` |
| Header | Matches a header by supported pattern | `X-Api-Version` |
| Host | Routes based on trusted public host | `shop.example.test` |
| Query | Matches query parameters by factory semantics | `page` or `category` |

**Predicates select routes; they do not grant permissions.** A condition like `Host=admin.example.test` or `Header=X-Role,admin` does not prove the user has admin privileges. Spring Security Servlet and backend authorization must enforce authentication/authorization at the trust boundary.

### Unmatched Routes

When no RouterFunction matches, Spring MVC may return 404 according to the application's handler mapping/error handling. However, a catch-all route, static resource handling, annotation controllers, or another handler may claim the request before/after depending on ordering. **Do not assume every 404 is a wrong Gateway predicate**; inspect `HandlerMapping` and actual route definitions.

### Overlapping Routes and Precedence

If you have both `Path=/api/**` and `Path=/api/admin/**`, both may match an admin request. You must know your version's route selection/ordering rules and ensure **security policies are decoupled from route order**. A broad route could send requests to a different backend if selected first. Test exact paths, trailing slashes, encoded slashes, other methods, and path rewrites at ingress.

## 6. Before, Handler, and After: Three Extension Points to Remember

A Gateway MVC route is logically organized as follows:

~~~mermaid
flowchart LR
    Req["ServerRequest"] --> Pred["Route predicate"]
    Pred --> Before["Before filters"]
    Before --> Handler["Gateway HTTP HandlerFunction"]
    Handler --> After["After filters"]
    After --> Resp["ServerResponse"]
~~~

A **Before filter** typically modifies or inspects the request **before** invoking the HTTP handler: changing the request path, target URI, headers, or request attributes. The **HandlerFunction** is where the actual upstream call or response creation happens. An **After filter** can adjust the result after the handler creates the response according to contract and implementation.

### Comparison with Server WebFlux

| Gateway Server Web MVC | Gateway Server WebFlux |
| --- | --- |
| WebMvc.fn `RouterFunction<ServerResponse>` | Spring WebFlux route predicates + reactive handler/filter chain |
| `HandlerFunction<ServerResponse>` | Reactive Gateway handler, `Mono<Void>` chain |
| Before/after/filter functions per Gateway MVC API | `GatewayFilter`/`GlobalFilter` with `chain.filter(exchange)` |
| `ServerRequest` from `web.servlet.function` | `ServerWebExchange` and reactive request/response |
| Servlet `SecurityFilterChain` | Reactive `SecurityWebFilterChain` |
| Servlet container / MVC HTTP client | Reactor/WebFlux HTTP runtime |

**Do not copy Reactor operators** such as `doOnError`, `doFinally`, or `Mono.defer` into a WebMvc.fn filter simply because you are used to writing Gateway Server WebFlux. In MVC, error handling can rely on exceptions, HTTP results, Servlet exception resolvers, and route filter functions.

### An After Filter Is Not a Moment Where Anything Can Be Changed

An after filter operates on the response at the level supported by the framework. However, **response status/headers/body may already be or currently be getting written** depending on the implementation, streaming mode, and filter order. Do not assume a custom after function can revert an already-committed response, read an unbounded body, or turn a partial stream into a different JSON error. Use supported filter APIs and test against a real streaming backend.

### Execution Order When Multiple Filters Are Declared

With multiple before/after functions and filter wrappers, the application order depends on route builder structure, composition, and version. Evaluate each step by asking:

1. **Route predicate:** which route is selected?
2. **Before filters:** what data is transformed before the handler?
3. **Handler:** what final URI, path, headers, and body does it see?
4. **After filters:** at what point do they modify the response?
5. **Servlet filters:** do outer filters read/write the response or block the request?

Do not infer the "final order" solely from filter names, especially when Java DSL and YAML configuration are used together. Use an HTTP stub test that records the **actual request sent upstream** to verify.

## 7. Starters, Versions, and Spring Boot Configuration for Server Web MVC

Spring Cloud Gateway has different variants in the Spring Cloud ecosystem, so **choosing the right starter is an architectural decision**, not just a syntactic one.

For the newer Spring Cloud Gateway Server Web MVC line, the Maven dependency typically looks like:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

In some older lines, the starter name may be `spring-cloud-starter-gateway-mvc`. Use the **artifact name and Spring Cloud BOM supported by your project's Spring Boot version**. Do not mix an old starter into a new BOM or assign arbitrary versions without checking the compatibility matrix.

Example dependency structure:

~~~text
Spring Boot application
   |
   +-- Spring Cloud dependency BOM (compatible version)
   |
   +-- Gateway Server Web MVC starter
   |      +-- Spring MVC / Servlet web runtime
   |      +-- Gateway WebMvc.fn routing / filter support
   |
   +-- Spring Cloud LoadBalancer (if using lb://)
   |
   +-- Spring Security Servlet (if securing gateway)
   |
   +-- Spring Boot Actuator / Micrometer (if observing)
~~~

You do not necessarily need to declare every transitive dependency if the starter already brings them in; what matters is the **actual dependency graph**, compatible versions, and **not accidentally pulling the application into WebFlux Gateway**.

### 7.1. Application Entry Class

A Spring Boot Servlet application typically has a main class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcGatewayApplication.class, args);
    }
}
~~~

This class does not declare routes yet. Spring Boot infers the web application type from dependencies and configuration; with MVC gateway, you need a proper **Servlet web application context**, not forced reactive mode. If an application simultaneously contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot has its own web application type inference rules; **do not add both to "support both MVC and WebFlux"** without verifying the runtime.

### 7.2. Parts That Are Not Directly Compatible

| Familiar Gateway WebFlux component | Why you should not copy it to Web MVC |
| --- | --- |
| `spring-cloud-starter-gateway-server-webflux` | That is the starter for the reactive variant |
| `org.springframework.cloud.gateway.filter.GlobalFilter` | Uses WebFlux's `Mono<Void>` and `ServerWebExchange` |
| `org.springframework.cloud.gateway.filter.GatewayFilter` | Reactive filter chain API differs from MVC handler/filter functions |
| `ServerHttpSecurity` and `SecurityWebFilterChain` | For reactive Spring Security; MVC uses `HttpSecurity` and `SecurityFilterChain` |
| `org.springframework.web.reactive.function.server.RouterFunction` | WebFlux.fn, not `org.springframework.web.servlet.function.RouterFunction` |
| Reactor Netty HTTP client properties | Does not automatically control the Servlet container or MVC outbound client |
| `Mono.defer`, `doFinally` on a Gateway filter | Not the return contract of a WebMvc.fn handler |

You **can still use Reactor in another part of the application** if needed, but that does not change the core HTTP processing contract of Gateway Server Web MVC.

## 8. YAML Example: A Simple Servlet Gateway Route

Suppose:

- The Gateway listens on `localhost:8080`.
- A test Catalog backend listens on `localhost:9001`.
- The client calls `GET /api/catalog/products/42`.
- The Catalog backend exposes `GET /catalog/products/42`.

A configuration on a newer Gateway line supporting the `server.webmvc` namespace:

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
              uri: http://localhost:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET,HEAD
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source,mvc-edge
~~~

**Part-by-part explanation:**

1. `server.port=8080` configures the Boot application's inbound HTTP port.
2. `id=catalog-read` is the route identifier for configuration, testing, and observability.
3. `uri=http://localhost:9001` is the upstream HTTP destination, **not the Gateway port**.
4. `Path=/api/catalog/**` restricts the client URLs accepted by the route.
5. `Method=GET,HEAD` restricts HTTP methods, preventing an unexpected POST from being proxied through a read-only route.
6. `StripPrefix=1` removes the **first path segment**: `/api/catalog/products/42` → `/catalog/products/42`.
7. `AddRequestHeader` adds an illustrative header so the backend can see the request passed through the Gateway. **Do not use a self-added header as proof of authentication.**

The example above **does not automatically provide HTTPS, authentication, rate limiting, or mTLS**. It is suitable for a **local lab**, and any real request reaching the backend should be verified with an HTTP stub. In Docker/Kubernetes deployments, `localhost` inside the Gateway container **does not automatically point to another backend container**; use the proper network DNS/service name.

### 8.1. Version-Dependent YAML Namespace

In earlier Spring Cloud Gateway MVC lines, the route property was commonly:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: catalog-read
            uri: http://localhost:9001
            predicates:
              - Path=/api/catalog/**
~~~

In some newer lines, the namespace may be **`spring.cloud.gateway.server.webmvc.routes`**. Do not declare both simultaneously and guess which configuration applies. Check the Spring Cloud release notes, configuration metadata **of the actual dependency in use**, startup logs, and test that the route actually matches.

**Do not confuse with WebFlux:** `spring.cloud.gateway.server.webflux.routes` or `spring.cloud.gateway.routes` from a different WebFlux project does not guarantee Gateway Server MVC will read the corresponding configuration.

### 8.2. Example Request Flow

~~~text
Client:
    GET http://localhost:8080/api/catalog/products/42?lang=vi
                   |
                   v
Servlet Gateway MVC:
    Match Path=/api/catalog/**, Method=GET
    StripPrefix(1)
    AddRequestHeader(X-Gateway-Source: mvc-edge)
                   |
                   v
Catalog backend:
    GET http://localhost:9001/catalog/products/42?lang=vi
    X-Gateway-Source: mvc-edge
                   |
                   v
Gateway returns upstream response to client
~~~

The query string `lang=vi` in the example should be preserved if no filter intentionally modifies it; however, preserving or re-encoding **special characters, encoded slashes, `+` signs, and percent (`%`) characters** must be tested on the exact version/router. Do not look at one simple ASCII request and conclude all URI encoding is correct.

## 9. Java DSL: Declaring a Gateway Proxy with RouterFunction

Gateway Server Web MVC can let you create routes with a dedicated Java DSL based on WebMvc.fn. A common pattern:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;

@Configuration
public class CatalogGatewayRoutes {

    @Bean
    public RouterFunction<ServerResponse> catalogRoute() {
        return route("catalog-java")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:9001"))
                .build();
    }
}
~~~

**This is a Gateway Server MVC Java DSL pattern** using `GatewayRouterFunctions`, `HandlerFunctions`, and `BeforeFilterFunctions` from the MVC line. Method overloads and packages may differ across releases; verify the Java API matching your BOM.

In this example:

- `route("catalog-java")` creates a route with an explicit ID.
- `.GET("/api/catalog/**", http())` registers a GET predicate and the Gateway HTTP handler.
- `.before(uri("http://localhost:9001"))` specifies the upstream URI before the handler executes.
- `.build()` returns a Spring MVC `RouterFunction<ServerResponse>` that the Spring container can register as a bean.

**Difference from the YAML in Section 8:** This Java DSL sample **has not added StripPrefix yet**, so the backend may receive the full path `/api/catalog/products/42` unless a before filter alters the path. If the backend only supports `/catalog/products/42`, you must attach the corresponding before filter available in your version.

### 9.1. Adding a Path-Modifying Filter When Supported by the API

In MVC lines that provide `BeforeFilterFunctions.stripPrefix`, a route can be expanded as:

~~~java
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;

// Builder method snippet, placed inside the RouterFunction bean above:
return route("catalog-java")
        .GET("/api/catalog/**", http())
        .before(uri("http://localhost:9001"))
        .before(stripPrefix(1))
        .build();
~~~

This is a **replacement for the return statement** of the previous example method, not a standalone second Java file. Check the filter API in your active version; you may need to adjust the order if the builder/filters handle URI and path with different semantics. Use a backend stub to confirm the final URI.

### 9.2. Do Not Write Your Own HTTP Client Inside Each HandlerFunction Unnecessarily

WebMvc.fn allows you to write a custom handler:

~~~java
// Regular WebMvc.fn concept code, not a Gateway proxy factory:
request -> ServerResponse.ok().body("Hello")
~~~

But for a Gateway proxy, **prefer Gateway MVC's dedicated HandlerFunctions and filters** to preserve HTTP semantics, forward headers, stream bodies, integrate discovery, and handle errors. Manually using `RestClient` and copying all request/response headers by hand easily leaks `Authorization`, gets `Content-Length` wrong, forwards hop-by-hop headers, or consumes the body before proxying.

### 9.3. Can the Same Route Be Declared in Both YAML and Java?

Both forms can be used in an application if supported by the framework/version, but **avoid creating two overlapping routes with the same path/method without clear precedence**. For example, if YAML `catalog-read` and Java `catalog-java` both match `GET /api/catalog/**`, one route may be chosen over the other. For a lab, **pick one configuration style** for easier verification, or make ordering/conditions explicit and test them.

## 10. Before Filters: Modifying Requests Before Proxying

Route-scoped before filters can process paths, headers, URIs, queries, or supported request policies. They play a role similar to **pre-routing transformation**, though they are not Servlet filters.

| Change type | Purpose | Risk if misused |
| --- | --- | --- |
| StripPrefix | Removes outer API Gateway prefix segments | Stripping too many segments causes backend 404 |
| RewritePath | Changes URL structure via rules/regex | Losing slashes, query strings, or encoded characters |
| AddRequestHeader | Adds headers for upstream | Header trusted by backend as identity even if spoofable by client |
| RemoveRequestHeader | Removes headers that should not be forwarded | Stripping Authorization on a token-requiring route, or forgetting Cookie on a vendor route |
| SetRequestHeader | Overwrites a header with a system-controlled value | Accidentally turning user-controlled data into trusted metadata |
| URI/upstream selection | Selects backend service | Can lead to SSRF if URI comes from a client header |

### 10.1. Requests Must Be Treated as Untrusted Input

A client can send:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer <client-token>
X-User-Role: ADMIN
X-Forwarded-Host: attacker.example
~~~

The Gateway **must not treat** client-sent `X-User-Role` as an authority. If identity is needed, rely on **Spring Security Servlet SecurityContext** after authentication or an internal identity contract with a trusted source and signature. `Forwarded`/`X-Forwarded-*` headers should only be trusted when coming from a managed proxy/ingress.

If the Catalog route is public and **does not need the user's access token**, consider removing `Authorization` and `Cookie` from outbound requests using Gateway MVC's built-in filters. If Orders requires an access token, forward it only when Orders is an **allowed audience**, over TLS, and with the backend validating the token itself; do not send refresh tokens or ID tokens to every service.

### 10.2. HTTP Headers Are Not Immutable Data Across the Gateway

The Gateway receives an inbound request and creates a new outbound request. Headers such as `Host`, `Connection`, `Transfer-Encoding`, `Content-Length`, and forwarding headers have hop-specific semantics. Do not blindly copy all headers, and do not manually set `Content-Length` using Java character count when the body contains UTF-8 or compression.

Depending on the filter/client/framework, some hop-by-hop headers are handled automatically, but **you must still test** scenarios involving reverse proxies, HTTP/2 ↔ HTTP/1.1, streaming, gzip, and WebSocket upgrades.

### 10.3. Query Strings, Encoded Slashes, and Context Paths

Suppose a client sends:

~~~text
/api/catalog/items/%2F-special?tag=a%2Bb&sort=price%20desc
~~~

A careless path rewrite can:

- Decode `%2F` into a slash and alter the path hierarchy.
- Turn `+` into a space in the query even though the client sent an encoded plus.
- Drop the query string when building the target URL.
- Introduce unexpected double slashes or trailing slashes.
- Change path meaning if ingress already rewrote it before entering the Gateway.

No single normalization rule guarantees equivalence across all proxies/Servlet containers. Test such paths **across the entire ingress → Gateway → backend chain** and apply allowlists/authorization against the path representation actually seen by each layer.

## 11. Service Discovery and `lb://` URIs in MVC Gateway

In microservices, a backend often does not have a single fixed host:port. A route can use a service ID:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

Prerequisites for use:

1. The application has **Spring Cloud LoadBalancer** and an instance source compatible with the Gateway MVC line in use.
2. `orders-service` must resolve to approved `ServiceInstance` entries.
3. The Gateway handles scheme/host/port/TLS appropriately for each instance.
4. The backend protects its own access; service discovery is not authentication.

~~~mermaid
flowchart TD
    P["GET /api/orders/42"] --> G["Gateway MVC route: lb://orders-service"]
    G --> LB["Service instance selection"]
    LB --> A["orders-1.internal:8443"]
    LB --> B["orders-2.internal:8443"]
    A --> H["HTTPS outbound client"]
    B --> H
    H --> R["HTTP response"]
~~~

**Architectural warning:** Do not describe this step using the exact class `ReactiveLoadBalancerClientFilter` from **Gateway WebFlux**, because Gateway Server Web MVC uses a different integration and HTTP routing mechanism. The concept is similar — resolving a service ID to a concrete instance — but the **implementation is not identical**.

### No-Instance vs. Backend 503

If the service registry returns no instances, the Gateway cannot choose a target. The final HTTP result (typically in the unavailable range) depends on the implementation/error handler and policy. If an instance exists and returns `HTTP/1.1 503`, that is a **response from the backend**. You must inspect route ID, service ID, discovery state, HTTP client errors, and backend request counts to distinguish the two.

### Trust Issues with the Registry

An `lb://orders-service` route does not itself prove the final host is trustworthy. If malicious records are written into the registry, tokens could be sent to an unapproved host. Protect registry write permissions, namespaces, egress destinations, TLS certificates/hostnames, and mTLS when needed. **Never allow Internet clients to directly set an arbitrary service ID or upstream URI.**

## 12. Outbound HTTP Client: The Second Connection of Gateway MVC

After route predicates and before filters, the Gateway must issue an outbound HTTP request to the backend. Depending on the Gateway MVC line and HTTP client implementation, the infrastructure may integrate **Spring MVC HTTP client/RestClient** APIs with an appropriate request factory. What matters is not the specific HTTP client class name in an example, but **managing transport as a distinct component**:

~~~text
Incoming:
    Client --TLS/HTTP--> Servlet container --MVC--> Gateway handler

Outgoing:
    Gateway handler --HTTP client connection pool--TLS/HTTP--> Backend
~~~

### Resources to Manage

| Resource | When backend is slow or failing | How to protect |
| --- | --- | --- |
| Servlet request threads | May be held waiting for processing or writing response, depending on implementation | Measure active/busy threads, limit admission/concurrency |
| Outbound connection pool | Connection exhaustion, rising pending acquires | Pool size and timeout matched to backend capacity |
| TCP connect | Hanging connection attempts or refusals | Connect timeout and discovery health |
| TLS handshake | Invalid cert/hostname, handshake timeout | Truststore, hostname verification, mTLS |
| HTTP response | Slow backend or missed deadlines | Intentional response/read timeouts |
| Request/response buffers | Large bodies or long-held streams | Stream properly, bound body size, avoid unnecessary caching |
| Retry/circuit breaker | Multiple attempts or fail fast | Retry budget, idempotency, breaker state |

**Do not assume `spring.cloud.gateway.server.webflux.httpclient.*` controls MVC outbound transport.** Look up the exact properties/APIs of your Gateway MVC/HTTP client version, verify they are actually bound, and measure the effect in tests.

### Timeouts at Three Boundaries

A request can have:

- **Client deadline:** the maximum total time a user will wait.
- **Gateway outbound timeout:** limits on the TCP/TLS/HTTP call to the backend.
- **Backend timeout:** limits on DB, SDK, or downstream service-to-service calls.

If the Gateway sets a very long HTTP client timeout, a hanging backend can hold resources even after the client has given up. If the timeout is too short, valid calls get cut off and retries amplify load. Choose durations based on **API SLOs, workload type, and end-to-end chain limits**; do not copy WebFlux values into MVC without verifying semantics.

### Streaming and Blocking

For large uploads/downloads or SSE/NDJSON, know how Gateway MVC **supports streaming/buffering** for your specific route/filter/HTTP client. Do not assume bodies are always forwarded "zero copy," and do not log full bodies or read `InputStream` into an unbounded byte array.

An HTTP response may **already be committed** once status, headers, or part of the body has started sending. If the backend fails mid-stream, the Gateway cannot go back and send a fresh 503 JSON on the same response. Design reconnect/resume and partial-result handling at the protocol level rather than applying retries as for a short JSON GET.

## 13. Securing Gateway MVC with Spring Security Servlet

Gateway Server Web MVC uses the Spring MVC/Servlet stack, so the appropriate Spring Security mechanism is **`SecurityFilterChain` and `HttpSecurity`**. This differs from WebFlux's `SecurityWebFilterChain`/`ServerHttpSecurity`.

~~~mermaid
flowchart TD
    C["Client + Authorization header"] --> SF["Servlet Security FilterChain"]
    SF --> AUTH{"Valid JWT? Authorized?"}
    AUTH -->|No| DENY["401 / 403"]
    AUTH -->|Yes| DS["DispatcherServlet"]
    DS --> ROUTE["Gateway MVC RouterFunction"]
    ROUTE --> BACK["Outbound HTTP client → backend"]
    BACK --> RES["Response to client"]
~~~

### Spring Security Example for a Stateless Bearer JWT API

Suppose public Catalog, private Orders, and admin APIs all pass through the Gateway. An illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class MvcGatewaySecurity {

    @Bean
    SecurityFilterChain gatewaySecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**")
                                .hasAuthority("SCOPE_admin")
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                // Illustrative only for a Bearer-only API that does not use cookie auth.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

And an **illustrative** JWT validation source in configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

**Security notes:**

1. `issuer-uri` must point to the environment's real trusted IdP, and you must verify the **audience** appropriate for the API/Gateway; do not assume issuer validation already checks audience per business policy.
2. `SCOPE_admin` is only meaningful if the authority converter maps a trusted scope/admin claim to that authority. Never trust client-sent `X-Role: admin`.
3. `requestMatchers("/api/admin/**")` must be tested with the exact base path `/api/admin`, trailing slashes, and path variants. Avoid placing a broad `/api/**.permitAll()` rule before the admin rule.
4. `csrf(csrf -> csrf.disable())` is appropriate only for a **Bearer-only stateless API** after risk assessment; if browsers send session or refresh cookies automatically, CSRF protection must be designed.
5. If management/Actuator endpoints exist, `anyRequest().denyAll()` in the example will block undeclared URLs — that is intentional. Separate security chains or add appropriate matchers for health/operations; do not open all of Actuator just to make readiness green.
6. **Authentication at the Gateway does not replace backend authorization.** Backends must still check order ownership, tenant, audience, and operation-specific permissions.

### Do Not Use Gateway Route Filters Instead of SecurityFilterChain

A Gateway before filter can reject a request before calling the backend, but it only runs **after the corresponding route is selected**. If another endpoint is served by an MVC controller or Actuator handler, the Catalog route filter does not apply to it. Authentication/authorization protecting the HTTP boundary should live in the **Servlet Security FilterChain** or an equivalently scoped mechanism.

### When a Public Route Receives a Malformed Token

A route configured with Spring Security `permitAll()` can still return an authentication error if the client **explicitly sends a malformed Bearer token** and the resource server processes that credential. Do not confuse that error with an unmatched MVC route or a broken Gateway before filter. Test public endpoints separately with **no token**, a valid token, and an invalid token.

## 14. How Do Servlet Filters Differ from Gateway Filters?

There are three filter layers easily lumped together under the word "filter":

| Type | API | Timing/scope | Examples |
| --- | --- | --- | --- |
| **Servlet Filter** | `jakarta.servlet.Filter` and `FilterChain` | Wraps HTTP requests before/after the Servlet, can apply across handlers | Security, encoding, tracing |
| **WebMvc.fn HandlerFilterFunction** | `org.springframework.web.servlet.function.HandlerFilterFunction` | Wraps a functional handler/router function | Narrow logging, policy checks for a group of routes |
| **Gateway MVC before/after filters** | Factories/functions of Spring Cloud Gateway Server MVC | Transforms requests/responses at points supported by the Gateway DSL | StripPrefix, rewrite, request/response headers |

**A Servlet Filter can run before route selection**, whereas a Gateway before/after filter is typically attached to a matched route. If you want to log every HTTP request—including unmatched 404s, Actuator, and internal controllers—instrumentation at the servlet/server layer is more appropriate, while still protecting sensitive data.

### 14.1. HandlerFilterFunction Pattern for Observing Handler Execution Time

**Pure Spring MVC WebMvc.fn** example:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerResponse;

final class MvcRouteTelemetry {
    private static final Logger log =
            LoggerFactory.getLogger(MvcRouteTelemetry.class);

    private MvcRouteTelemetry() {}

    static HandlerFilterFunction<ServerResponse, ServerResponse> timing() {
        return (request, next) -> {
            long startNanos = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                log.debug("mvcHandler outcome=returned status={} elapsedMs={}",
                        response.statusCode().value(),
                        TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startNanos));
                return response;
            } catch (RuntimeException error) {
                log.warn("mvcHandler outcome=exception type={}",
                        error.getClass().getSimpleName());
                throw error;
            }
        };
    }
}
~~~

The goal of this snippet is to **observe when the functional handler returns `ServerResponse`**, not to measure the exact moment all response bytes reach the client. With body streaming, `next.handle(request)` may return before all data is transmitted. Do not use this function as a replacement for HTTP server access metrics or network latency instrumentation.

**Do not log** `request.headers()`, raw URI queries, `Authorization`, `Cookie`, or arbitrary exception messages. If you need to log a route ID, take it from managed configuration metadata, not from a client-controlled string.

### 14.2. Servlet Filters and Asynchronous Dispatch

When MVC/Servlet async is used, a request can pass through multiple dispatch phases depending on dispatcher types and filter registration. A custom filter may run multiple times or miss async/error dispatches if misconfigured. Do not assume "every filter invocation always corresponds to one user request"; when necessary, check the Servlet dispatcher type and test cancellation/error paths.

### 14.3. Error Responses and Post-Processing Filters

If a handler throws an exception, `HandlerExceptionResolver`, MVC error handling, or the Servlet container may produce an error response. A Gateway after filter that only receives a successful response from the handler **will not necessarily see an escaped exception**. Likewise, a Servlet Filter may see the exception before MVC/Servlet error dispatch handles it. This affects metrics; separate **handler returned**, **final HTTP status**, and **error dispatch**.

## 15. Timeouts, Retries, Circuit Breakers, and Fallbacks in MVC Architecture

Both Gateway Web MVC and WebFlux may need to protect backends from cascading failures, but **filter factories, APIs, and implementations are not identical**. Do not copy `CircuitBreaker` or `Retry` route filters from WebFlux assuming all options work on Web MVC.

### 15.1. Timeouts Bound Individual Stages

A request passes through:

~~~text
Client deadline
     |
Servlet inbound read / servlet processing
     |
Outbound pool acquire
     |
TCP connect / TLS handshake
     |
Backend response read
     |
Servlet write response
~~~

Depending on the HTTP client and version, configure **connect timeout, response/read timeout, and pool acquire timeout**. An HTTP client timeout **is not by default a total deadline** from when the client starts sending until the response completes. If the backend is slow, waiting threads/connections can pile up.

### 15.2. Retries Are a Load Amplifier

If the client retries 2 times after the initial attempt, the Gateway retries 2 times after its initial attempt, and the backend SDK also retries 2 times, the theoretical number of attempts reaching the final dependency can be:

\[
3 \times 3 \times 3 = 27
\]

Therefore:

- Pick **one primary retry layer** per operation/dependency whenever possible.
- Only retry methods/errors confirmed safe, such as idempotent GETs hitting transient connection errors.
- Use **retry budgets**, backoff, and jitter; stop once the operation exceeds its deadline.
- Do not retry payment/order POSTs unless the backend supports true **idempotency** and deduplication.
- Do not replay request bodies with large streams/uploads unless replay capability and memory limits are verified.

### 15.3. What Does a Circuit Breaker Do in Gateway MVC?

A CircuitBreaker, when supported by the MVC version, can track error/slow calls and temporarily **short-circuit** outbound requests to a degraded dependency. It complements timeouts, rate limiting, health filtering, and bulkheads.

~~~mermaid
flowchart TD
    R["Gateway MVC route"] --> CB{"Circuit permits call?"}
    CB -->|CLOSED or HALF_OPEN probe| U["Outbound HTTP call"]
    CB -->|OPEN| FB["Fail fast / configured fallback"]
    U --> D["Backend"]
    D --> RES["Client response"]
    FB --> RES
~~~

**Breaker state** and fallback semantics depend on Spring Cloud CircuitBreaker/Resilience4j or the configured MVC version's implementation. Fallback modes may have limitations on URIs and response bodies. If the implementation behavior is unclear, start with a **safe 503 that leaks no data**, rather than pretending a business operation succeeded.

### 15.4. Fallbacks Must Not Hide Security Errors

Do not turn 401/403 into 200. A fallback returning cached Orders must still enforce **correct user/tenant**, cache age, and resource permissions. For payment operations, never return `201 Created` when the backend has not confirmed commit. Fallbacks are part of the **API contract**, not just a way to make 5xx graphs disappear.

## 16. Preserving HTTP Semantics and Route Safety

A proper reverse proxy does not just return JSON; it must also preserve HTTP rules:

| Element | What must be defined | Common mistakes |
| --- | --- | --- |
| Method | Which of GET/HEAD/POST/PATCH/DELETE are allowed on each route? | Accepting POST on a read-only route |
| URI/path | How are rewrites and percent-encoding handled? | Dropping query strings, altering encoded slashes |
| Request headers | Which headers are copied, stripped, or generated by the Gateway? | Leaking Authorization, Cookie, or spoofed forwarded headers |
| Request body | Is it streamed, buffered, compressed, or too large? | Reading all into memory, wrong Content-Length |
| Response status | How do upstream status and Gateway fallback differ? | Returning fake 200 when backend returns 503 |
| Response headers | Cache-Control, Set-Cookie, Location, CORS, Vary | Wrong cookie domain, redirecting to external host |
| Response body | Can it be modified once already committed? | Appending error JSON onto an SSE stream |
| TLS | Do inbound/outbound hops verify certificates? | Disabling hostname verification for convenience |

### 16.1. Forwarded Headers and Proxy Boundaries

In a topology with ingress:

~~~text
Browser --HTTPS--> Ingress --HTTP(S)--> Gateway MVC --HTTPS--> Orders
~~~

The Gateway may need to know the real public host/scheme to construct redirects, response links, or audit records. However, `Forwarded`, `X-Forwarded-Proto`, and `X-Forwarded-Host` headers must come from a **trusted proxy**, never blindly from the client. If a custom before filter uses a client-supplied forwarded host to choose an outbound URI, it can open an SSRF vulnerability.

### 16.2. Two Separate TLS Sides

Client → Gateway TLS and Gateway → backend TLS are **two independent connections**. Public HTTPS does not guarantee the backend also uses HTTPS. Check CA/truststore, hostname/SAN, service identity, and mTLS when required. An **untrusted** backend destination can still receive tokens even over valid TLS; therefore, you also need a **destination allowlist and audience policy**.

### 16.3. Hop-by-Hop Headers and Proxy Authentication

Do not blindly forward `Connection`, `Upgrade`, `Proxy-Authorization`, or transport metadata meaningful only for a single hop. For `Authorization`, forward it only when the receiving service is **permitted and needs** that credential, and let the backend validate it independently. Never pass OIDC login refresh tokens/ID tokens down to business resource servers.

### 16.4. CORS Is Not Authorization

If the frontend runs on a different origin than the Gateway API, browsers may send OPTIONS preflight requests. Configure CORS at the appropriate layer so preflight is handled **before authentication blocks it by mistake**, while the actual request remains authorized. A `permitAll` for OPTIONS does not itself generate or validate `Access-Control-Allow-Origin`. CORS governs browser behavior only; other HTTP clients still go through security.

## 17. Observability and Actuator for a Servlet Gateway

A Gateway MVC needs visibility into **both HTTP sides** and Servlet runtime health:

~~~mermaid
flowchart TD
    I["Inbound HTTP metrics"] --> Obs["Monitoring / tracing"]
    S["Servlet threads, busy/idle, connections"] --> Obs
    R["Gateway route ID, selected handler"] --> Obs
    C["Outbound HTTP client: pool / latency / errors"] --> Obs
    L["LoadBalancer / discovery results"] --> Obs
    F["Circuit breaker / retries / fallbacks"] --> Obs
    B["Backend status and latency"] --> Obs
~~~

Key questions:

1. Did the request enter the **Servlet container** and get blocked by the Security FilterChain, or did it reach a Gateway route?
2. Which route did `RouterFunctionMapping` select? Were there overlapping routes?
3. Did the HTTP client call the backend, or was the request short-circuited by a rate limiter/circuit breaker?
4. If an outbound call ran, how long did it spend in **pool acquire, connect, TLS, and response**?
5. Was the final result seen by the client a backend status, fallback status, or Servlet error response?
6. When errors spike, are **active/busy Servlet threads** and the outbound pool getting exhausted?

### 17.1. Metrics You Should Have

| Conceptual metric | Goal |
| --- | --- |
| Inbound HTTP requests by method/status/route | Measure client-side traffic and outcomes |
| Duration p50/p95/p99 | Identify latency spikes per route |
| Servlet active/busy threads | Detect exhaustion from blocking handlers/outbound calls |
| HTTP outbound connections/pending requests | Spot pool limits or connection problems |
| Upstream calls by service ID | Measure actual calls, separating inbound from retries |
| 401/403 by security outcome | Separate auth failures from backend errors |
| 404: route miss vs backend 404 | Avoid fixing the wrong RouterFunction |
| Circuit OPEN / fallback count | Detect degraded services even when responses are 200 |
| Retry attempts and retry budget | Detect load amplification |
| TLS/connect/read failures | Break down transport errors |
| JVM heap/GC/CPU | Track resource pressure |

Metric names **depend on Spring Boot, Servlet container, HTTP client, Micrometer, and Gateway MVC versions**. Some meters may be disabled by default, require instrumentation, or depend on the client implementation. Do not assert that Spring Cloud Gateway MVC automatically emits all of the above with a single setting.

### 17.2. Actuator and the Management Plane

Spring Boot Actuator can expose `health`, `info`, `metrics`, and management endpoints depending on dependencies/config. **Gateway-specific Actuator capabilities in Server Web MVC may differ from Server WebFlux by version**, so check documentation and actual endpoint mappings rather than assuming `/actuator/gateway/routes` supports full route creation/deletion on every line.

**Never enable `management.endpoints.web.exposure.include: "*"` on a public Gateway** just for debugging. Expose the minimum needed, use a dedicated management port if appropriate, network policy, TLS, and Spring Security Servlet with dedicated operator permissions. Route listings may reveal URIs, metadata/filter arguments, and internal service structure.

### 17.3. Safe Logging

A reasonable log entry:

~~~text
route=catalog-read method=GET status=200 elapsedMs=42
upstreamService=catalog-service attempts=1
~~~

Do not log:

~~~text
Authorization: Bearer <access-token>
Cookie: SESSION=<session-id>
GET /api/orders?access_token=<token>
Set-Cookie: SESSION=<session-id>
~~~

Especially in Servlet systems, **ingress access logs, Tomcat access logs, Spring Security DEBUG, outbound HTTP wire logs, and APM agents** may capture different fields than a custom Gateway filter. Audit every sink, restrict query/header capture, and avoid putting tokens into correlation IDs or metric labels.

### 17.4. Two-Hop Tracing

A trace can connect spans:

~~~text
Client request
    -> Gateway MVC inbound HTTP span
         -> Gateway MVC outbound HTTP span
             -> Catalog service span
~~~

Tracing requires safe propagation through infrastructure such as Micrometer/OpenTelemetry depending on your version. Do not trust arbitrary trace headers from the Internet directly as identity or audit data, and never place JWTs/session cookies into trace baggage. If a Gateway request performs 2 retry attempts, tracing may show multiple outbound spans under one inbound span; **understand the unit of measurement** rather than treating them as two user operations.

## 18. Backend Stub to Prove the Path Through Gateway MVC

An architecture lesson is incomplete if you only look at configuration. You need to prove **which method/path/headers the backend actually receives**, and that the response travels from backend through Gateway to client.

Suppose you run a **separate Catalog stub application** on port 9001. A Spring MVC controller can simulate the backend:

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    @GetMapping("/catalog/products/{id}")
    ResponseEntity<Map<String, Object>> getProduct(
            @PathVariable String id,
            @RequestHeader(
                    name = "X-Gateway-Source",
                    defaultValue = "missing"
            ) String gatewaySource
    ) {
        return ResponseEntity.ok(Map.of(
                "productId", id,
                "gatewaySource", gatewaySource,
                "backend", "catalog-stub-1"));
    }
}
~~~

**Lab requirement:** The stub runs on an HTTP server listening on port 9001, separate from the Gateway port 8080. `server.port=9001` belongs to the **stub application**, not the Gateway. If running multiple services on the same machine/container, verify the network namespace and avoid port conflicts.

With the YAML configuration in Section 8, the request:

~~~bash
curl -i 'http://localhost:8080/api/catalog/products/42'
~~~

can produce the **illustrative** response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"productId":"42","gatewaySource":"mvc-edge","backend":"catalog-stub-1"}
~~~

This is an **expected outcome**, not a command that was executed here. When Spring Security from Section 13 is enabled with `/api/public/**` as public, a request to `/api/catalog/**` falls under **authentication required** by the `/api/**` rule. In that case, **an anonymous curl must receive 401**; you must issue a valid token for the route or use a lab security config allowing Catalog reads. Never switch security to `permitAll()` for all APIs just so an example returns 200.

### 18.1. Aligning Configuration and Tests

There are two approaches:

- **Pure routing lab:** Disable application security on an isolated test Gateway. Use anonymous curl to observe paths/headers and confirm the backend receives the exact expected request.
- **Integrated security lab:** Enable the designed SecurityFilterChain; use a valid test JWT for `/api/catalog/**`, or create a specific public route `/api/public/catalog/**` with consistent predicates and security rules.

Do not mix the two approaches and conclude "the Gateway proxy is broken" when Servlet security is actually returning 401 before reaching the RouterFunction.

### 18.2. Method/Path Matrix

| Client request | Expected Catalog route behavior | What the backend receives if security permits |
| --- | --- | --- |
| `GET /api/catalog/products/42` | Match | `GET /catalog/products/42` |
| `HEAD /api/catalog/products/42` | Match by Method predicate | `HEAD /catalog/products/42`; body not sent to client |
| `POST /api/catalog/products/42` | Does not match GET/HEAD route | No request reaches Catalog via this route |
| `GET /api/other/products/42` | Does not match | No request reaches Catalog via this route |
| `GET /api/catalog/products/42?lang=vi` | Match | Path is stripped, query should be preserved properly |
| `GET /api/catalog/products/%2F42` | Depends on container/path decoding | Test encoded slash and actual normalization |

**Do not equate "route did not match" with a guaranteed 404** if the application also has controllers or a catch-all route. Check the backend request counter or safe traces to verify whether the request actually reached Catalog.

## 19. End-to-End Testing with the Java HTTP Client

For MVC Gateway, `MockMvc` is useful for checking mappings/security at the Spring MVC layer, but to prove **outbound Gateway HTTP client, TCP, TLS, and header rewriting**, run a **full HTTP integration test** against a real backend stub.

Example using JDK `java.net.http.HttpClient` and a Spring Boot integration test:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogMvcGatewayIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void routesRequestToCatalogStub() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                        "http://localhost:" + port
                                + "/api/catalog/products/42"))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("productId"));
        assertTrue(response.body().contains("42"));
        assertTrue(response.body().contains("mvc-edge"));
    }
}
~~~

**Conditions for this example to be meaningful:**

1. The example uses **JDK HttpClient** and Java 17-compatible syntax. Client lifecycle/closing management depends on the specific JDK API; in real tests, reuse clients appropriately rather than creating a new pool per request.
2. The Gateway is running on `RANDOM_PORT` and the route URI points to an active **Catalog stub on 9001**.
3. If Spring Security is enabled, the test must send a valid test token or the endpoint must be permitted by policy; this example assumes a **pure routing lab**.
4. Requires `spring-boot-starter-test` (or corresponding test dependencies) and a separate backend stub.
5. String assertions on JSON are illustrative only; better tests use a JSON parser and verify the backend call counter.

**Tests were not executed here**; this shows how to structure tests in the learner's project. In real CI environments, use a backend stub on a dynamic port and inject the URI/route configuration to avoid port 9001 collisions.

### 19.1. An Essential Test Suite

| Scenario | Expectation |
| --- | --- |
| Matching GET route | Correct upstream, method/path/query/headers |
| POST to GET-only route | Not proxied through that route |
| Backend returns 404 | Distinguished from unmatched-route 404 |
| Backend returns 503 | No automatic retry or fallback when unconfigured |
| Backend TCP refused | HTTP client fails cleanly, does not hang indefinitely |
| Backend delays past timeout | Request ends per designed deadline/fallback |
| Untrusted backend TLS cert | Connection must fail, do not disable verification |
| `lb://` with no instances | Does not send requests to arbitrary hosts |
| User token lacks authority | Servlet Security blocks before backend |
| Admin token with valid scope | Passes security; backend still checks business permissions |
| Client sends spoofed header | Does not create principal/authority from client headers |
| Backend sends Set-Cookie/redirect | Headers handled per trust boundary |
| Large request body | Not buffered unboundedly, no wrong Content-Length |
| Partial SSE then error | Does not append 503 JSON onto already-committed stream |
| Retry/breaker enabled | Count upstream attempts, verify fallback/status |

### 19.2. Security Tests and Proxy Tests Are Different Kinds of Evidence

`MockMvc` can verify that an anonymous request receives 401 or an admin token missing a scope receives 403 under Servlet security. However, it **does not automatically verify** the real outbound HTTP connection to the backend. Conversely, an integration proxy test returning 200 does not prove JWT validation/audience/ownership works. You need both test suites with distinct conditions and test data.

## 20. Servlet Gateway Performance: Threads, Connections, and Realistic Load

A Gateway usually does "thinner" work than a business service: receiving requests, checking policies, and proxying. Still, it can become a **bottleneck** if the backend is slow or a custom filter blocks threads.

### 20.1. Resource Model

~~~mermaid
flowchart LR
    C["N clients"] --> S["Servlet request capacity"]
    S --> F["MVC route + before filters"]
    F --> P["Outbound connection pool"]
    P --> U["Upstream capacity"]
    U --> P
    P --> S
    S --> C
~~~

With traditional blocking processing, serving capacity can be constrained by request threads, outbound connections, queues, and upstream wait times. If a request holds a thread for an average of \(W\) seconds and the arrival rate is \(\lambda\) requests/second, the average number of **concurrent in-flight requests** is approximated by Little's Law:

\[
L = \lambda W
\]

Simple modeling example:

- Gateway receives 500 requests/second.
- Each request stays in the system an average of 0.2 seconds.
- Average concurrent requests are approximately \(500 \times 0.2 = 100\).

If a slow backend pushes average latency up to **2 seconds**, concurrent requests rise to approximately **1,000** at the same arrival rate. Depending on blocking/async implementation, these requests may hold threads, connections, or memory to varying degrees. **Do not treat this formula as a prescription for setting exact `maxThreads`**, because queueing, latency distributions, keep-alive, retries, async Servlet, and multi-hop resources all matter.

### 20.2. Do Virtual Threads Solve Everything?

Supported Spring Boot/JDK lines can leverage **Java virtual threads** for blocking work. They can reduce the cost of holding platform threads during I/O waits, but:

1. They do not make the backend faster or make DB/TCP connections infinite.
2. They do not remove outbound pool limits, file descriptors, heap limits, or socket buffers.
3. They do not guarantee every HTTP client/filter/library is virtual-thread-friendly.
4. Pinning or resource bottlenecks can still occur; real observation is required.
5. They do not turn `Server Web MVC` into `Server WebFlux` and do not change filter APIs.

If considering `spring.threads.virtual.enabled` on a supported Spring Boot line, benchmark and inspect the entire stack rather than turning it on merely because Servlet threads look busy.

### 20.3. Where Is Backpressure?

Reactor/WebFlux has Reactive Streams backpressure. Gateway MVC runs on a Servlet/imperative stack; you must control load via **bounded queues, connection limits, timeouts, admission control, rate limits, bulkheads, and proper streaming/buffering APIs**. TCP also has its own flow control, but that **is not equivalent** to the entire MVC application having end-to-end reactive backpressure.

When a gateway hits 1,000 large uploads, reading full bodies into `byte[]` can cause memory to balloon. Set request-size limits, stream where supported, and never cache bodies solely for retry or logging.

### 20.4. A Useful Load-Testing Workflow

| Stage | Condition | Signals to observe |
| --- | --- | --- |
| Baseline | Backend returns 200 quickly, no retry | Throughput, p95/p99, busy threads |
| Slow upstream | Controlled backend delay | Active requests, connection pool pending |
| No instance | Empty discovery | Error status, no pointless HTTP connect waits |
| Backend 503 | Stub returns error | Retry attempts, circuit state, final status |
| Burst traffic | Short-term load spike | Rate limiter, queue growth, CPU |
| Large response | Downloading large payloads | Memory, socket throughput, body buffering |
| Cancellation | Client disconnects mid-stream | Cleanup, stale connections, server errors |

Do not run load tests like an attack against production. Choose an isolated environment, backend stubs, safe rate limits, and approved latency/QPS targets. **Do not optimize only for HTTP 200**: measure actual requests reaching the backend and verify whether error/degraded responses are reflected accurately.

## 21. Diagnosing Failures by Architectural Layer

When a request is not proxied as expected, identify **which layer it stopped at** instead of increasing timeouts or turning on logs containing credentials.

| Symptom | First layer to investigate | What to check |
| --- | --- | --- |
| Startup fails to create Servlet web server | Dependencies/web application type | Check Server Web MVC starter, Boot/Cloud BOM, no WebFlux mixup |
| Java `RouterFunction` fails to compile | WebMvc.fn packages/API | Use `web.servlet.function`, check Gateway MVC DSL for your release |
| YAML routes not loaded | Configuration binding | `gateway.mvc.routes` or `gateway.server.webmvc.routes` for your version? |
| `GET /api/catalog/...` returns 401 | Spring Security Servlet | Token? Path rule? Issuer/audience? |
| Regular user accesses admin API | Security matcher/order | Does admin rule precede broad rule? Does backend check permissions? |
| HTTP 404 before reaching backend | Servlet HandlerMapping/RouterFunction | Predicates, method, context path, route overlap |
| Backend receives wrong path | Gateway before/path filter | StripPrefix/RewritePath, slashes/query/encoding |
| No `lb://` instance | Discovery/LoadBalancer | Registry, service ID, health, instance metadata |
| Gateway returns 502/503 while backend is up | Outbound transport | DNS/TCP/TLS/HTTP client timeouts; mTLS |
| GET route succeeds but POST does not reach backend | Method predicate | Does route have `Method=GET,HEAD`? |
| Added header missing at backend | Filter order/HTTP client | Was filter attached to route? Was header overwritten? |
| Corrupted upload body or wrong Content-Length | Request/response streaming | Body consumption, encoding, buffer lifetime |
| Added response header unseen by client | After filter/response commit | Already committed? Stripped by upstream proxy? |
| 200 at Gateway but client stream cut off | Network/streaming | Partial write, connection close, client cancel |
| Retries cause heavy backend load spike | Multi-layer retries | Client/ingress/Gateway/SDK attempts; budget |
| Server threads busy while CPU low | Blocking I/O or pool wait | Thread dump, outbound pool, slow backend |
| Servlet Security config doesn't behave as expected | Wrong reactive stack used | Accidentally used `SecurityWebFilterChain` instead of `SecurityFilterChain`? |
| Actuator route listing lacks expected endpoint | Management capability/version | Is endpoint supported in MVC? Enabled/exposed/security/path? |
| Trace missing backend span | HTTP client instrumentation | Check propagation and client integration |

### 21.1. 10-Step Checklist

1. **Which port received the request?** Verify ingress, host, TLS scheme, and Servlet server listener.
2. **Did Servlet Security allow it through?** 401/403 can happen before any Gateway route.
3. **Which HandlerMapping did DispatcherServlet choose?** WebMvc.fn route, annotation controller, or Actuator handler?
4. **Which route matched?** Check path/method/host/header and order.
5. **What did before filters change?** Compare path/query/headers before and after without dumping tokens.
6. **What is the target URI?** Static host or `lb://`? If lb, how was the instance chosen?
7. **What did the outbound HTTP client do?** DNS, pool acquire, connect, TLS, request write, response read.
8. **Did the backend receive the request?** Use a stub counter or a safe backend trace ID.
9. **Who generated the response?** Real backend, Gateway fallback, Servlet error handler, or security layer?
10. **What is resource pressure?** Busy threads, pool, queue, memory, retry attempts, and circuit state.

**Never enable logging of raw Authorization, Cookie, or request bodies** just to tell two layers apart. Use route ID, method, final status, sanitized exception type, backend identifier, and a system-managed trace ID.

### 21.2. When Upgrading Spring Cloud Gateway

Because namespaces and APIs can change across lines, every upgrade requires:

- Checking the **Spring Boot + Spring Cloud BOM**, Server Web MVC starter, and package imports.
- Verifying all route definitions bind to the **correct namespace**.
- Checking Java DSL and before/after filters for the target release.
- Running negative tests for security and the management port.
- Verifying URI/path/query rewriting, header forwarding, and service discovery.
- Running HTTP integration tests with backend stubs for 2xx, 4xx, 5xx, timeouts, and streaming.
- Comparing busy threads, outbound pool, latency, and retry attempts before and after.

Never rely on the application simply starting up successfully to conclude that a route written with an older property still exists.

## 22. Comprehensive Practice Lab: Building a Gateway Server Web MVC for Catalog and Orders

**Scenario:** A team wants to move a simple entry gateway from a demo design to a Servlet-based Gateway Server Web MVC. Clients must call a single API; Catalog is public, Orders is private, and management endpoints must be isolated. This lab does not require a WebFlux project.

### Part A — Build the System

1. Select a **compatible Spring Boot/Cloud BOM**, the exact Gateway Server Web MVC starter name for the release, and add Spring Cloud LoadBalancer when needed.
2. Create `MvcGatewayApplication`, listening on port 8080.
3. Spin up a Catalog stub on port 9001 and an Orders stub on port 9002 in the lab; each stub returns a `handledBy` field and records an in-memory test request count.
4. Create Catalog route `GET /api/catalog/**` with `StripPrefix=1`; Orders `GET /api/orders/**` also strips the path appropriately.
5. Use **either** YAML or Java DSL for Catalog initially; then try the other form in a separate profile/test so there are no two overlapping routes.
6. Test with `curl`/JDK HttpClient that the real backend receives the expected path/query/headers.

### Part B — Security

1. Use Servlet **`SecurityFilterChain`**, not WebFlux `SecurityWebFilterChain`.
2. Configure a public route `/api/public/catalog/**` or apply matching policy to `/api/catalog/**`; ensure security matcher paths and Gateway predicates align.
3. For Orders, require a Bearer JWT with the right issuer, audience, and scope. The Orders backend continues checking order ownership.
4. Prevent cookies, tokens, or API keys from being sent to public Catalog when unnecessary; never use client-supplied headers as permissions.
5. If Actuator is enabled, expose only necessary health/metrics on a protected management network; do not expose route mutation publicly.

### Part C — Service Discovery and Reliability

1. Change the Orders URI from static HTTP to `lb://orders-service` once a test ServiceInstance source is ready.
2. Simulate two Orders instances; verify requests reach real instances via load balancing.
3. Remove one instance from discovery/readiness and observe how the system behaves; do not assume the Gateway retries infinitely.
4. Inject connect refusal, backend 503, and response delay using the stub. Pick bounded timeouts and verify error contracts.
5. If adding retry/circuit breaker, use only factories supported by your Gateway MVC version, with **budgets, idempotency, and test counters**.
6. Test HTTPS to a test upstream with a trusted certificate; certificate errors must be rejected, never disable hostname verification.

### Part D — Boundary Request/Response Checks

| Test | What must be proven |
| --- | --- |
| Normal GET Catalog | Exact `/catalog/products/42` at stub |
| GET with query | `?lang=vi` is not lost |
| POST to GET-only route | Not sent to backend through that route |
| Client sends `X-User-Role: ADMIN` | Admin access is not granted |
| Anonymous calls Orders | Blocked by Servlet Security before backend |
| Valid user token calls Orders | Correct route; backend checks resource permissions |
| Backend 404 | Not confused with route miss |
| No instances in discovery | Does not proxy to arbitrary hosts |
| Backend TLS handshake failure | Safely rejected |
| Cookie/Authorization headers on public Catalog | Not forwarded when route contract does not need them |
| Partial SSE then error | Does not try to replace committed 200 response with 503 JSON |
| Large response body | Not buffered unboundedly or corrupting Content-Length |
| Retry enabled in lab | Attempts stay within limit; no duplicate side effects |
| 2 Gateway replicas | Route/config and Security behavior are consistent |

### Part E — Performance Measurement

1. Test fast Catalog backend responses; record baseline QPS, p95/p99, and Servlet busy threads.
2. Add controlled delay at the backend; observe outbound pool and concurrent requests.
3. Enable appropriate rate limiting/bulkhead if needed and compare.
4. Do not enable retries at client/Gateway/backend simultaneously without a budget; measure real attempts at the stub.
5. Collect health/metrics/tracing **without tokens, Cookies, or raw URL queries**.
6. Scale up gradually in a bounded lab; report whether the bottleneck lies in threads, pool, or upstream.

### Part F — Report to Submit

Document clearly:

- Spring Boot/Gateway versions, starter name, and actual YAML namespace used.
- Diagram of Servlet container → FilterChain → DispatcherServlet → RouterFunction → handler → HTTP client.
- List of route IDs, predicates, before/after filters, and target URIs.
- Evidence that the backend stub received the exact path, headers, method, and request count.
- Security matrix (anonymous/user/admin), CORS, and management permissions.
- Results for connect/TLS/503 errors, and timeouts/retries/fallbacks when configured.
- Metrics for busy threads, outbound connections, and latency.
- Remaining risks, streaming/body-handling decisions, and rollout/rollback plan.

**Pass criteria:** The learner accurately describes the roles of **Servlet/WebMvc.fn**, runs Gateway MVC with at least one real proxy route, verifies security and rewrites via a backend stub, distinguishes errors by layer, avoids misusing WebFlux APIs, and never leaks credentials during request observation.

## 23. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| "Every Gateway is based on WebFlux." | Spring Cloud Gateway has **Server Web MVC** built on Servlet/WebMvc.fn and a separate Server WebFlux variant. |
| "Adding spring-boot-starter-web to WebFlux Gateway switches it to MVC." | You must use the **Gateway Server Web MVC starter** and matching APIs/config. |
| "WebMvc.fn is just WebFlux.fn with different packages." | WebMvc.fn uses `web.servlet.function` and handlers return `ServerResponse` directly. |
| "`RouterFunction` is a Servlet Filter." | RouterFunction matches handlers; Servlet Filters live in the Servlet FilterChain layer. |
| "Gateway before filters always run for every HTTP request." | They belong to their respective routes; Actuator/other controllers may bypass them. |
| "A matched route means the upstream is healthy." | Route selection is distinct from discovery, connection, TLS, and backend response. |
| "WebFlux `GlobalFilter`/Mono<Void> can be copied into Gateway MVC." | The two filter/runtime models are different. |
| "`SecurityWebFilterChain` protects MVC Gateway." | Use Spring Security's **Servlet SecurityFilterChain** for the MVC stack. |
| "Header `X-User-Role` proves admin authority." | Client headers are not authorities; rely on the authenticated principal. |
| "Using `lb://` gives healthy and secure load balancing." | Requires a trusted ServiceInstance source, health checks, TLS, and backend authorization. |
| "HTTP client timeout equals the client's total deadline." | Connect/read/pool/request timeouts have distinct semantics. |
| "Using virtual threads removes the need to bound outbound pools." | Virtual threads do not make dependencies or sockets infinite. |
| "An after filter can change the status after a response has partially streamed." | Committed status/headers cannot be replaced on the same response. |
| "Enabling retries always improves success rate." | Multi-layer retries can amplify load and duplicate side effects. |
| "Having Actuator means every Gateway MVC route endpoint matches WebFlux." | Capabilities and mappings depend on variant/version; verify the actual implementation. |
| "HTTP 200 through the Gateway proves auth, path, and backend are all right." | You must verify response source, upstream counter, token/audience, and resource permissions. |

## 24. Summary

- **Gateway Server Web MVC** is the Spring Cloud Gateway variant based on **Servlet container + Spring MVC + WebMvc.fn**. It still handles microservice entry routing, filters, service discovery, and reliability, but **does not share the same runtime/filter contract** as Gateway Server WebFlux.
- Requests typically flow through **Servlet FilterChain**, **DispatcherServlet**, **RouterFunctionMapping**, **HandlerFunctionAdapter**, then **Gateway MVC before/handler/after**, and the outbound HTTP client to the backend.
- `RouterFunction<ServerResponse>`, `ServerRequest`, and `HandlerFunction<ServerResponse>` belong to **`org.springframework.web.servlet.function`**; do not accidentally import them from `web.reactive.function.server`.
- Gateway MVC's Java DSL can use `GatewayRouterFunctions.route`, `HandlerFunctions.http`, and before filter functions; YAML routes typically define `id`, `uri`, `predicates`, and `filters`. **Starters and namespaces change across releases**, so always check the actual BOM.
- **Servlet Filters and SecurityFilterChain** protect inbound HTTP at a different layer than route-specific Gateway MVC filters. Authentication/authorization must never be replaced by `Path`, `Host`, or client-supplied headers.
- `lb://` handles instance selection given the right integration, but does not replace service identity checks, readiness, TLS, and backend authorization.
- The outbound HTTP client, Servlet threads, timeouts, pools, body streaming, and memory are resource boundaries to monitor. **Virtual threads do not turn the WebMvc.fn model into WebFlux**.
- Retries, circuit breakers, rate limiting, fallbacks, and Actuator can be valuable, but **capabilities/configurations must match the Gateway Server MVC version**; never blindly copy WebFlux config.
- Consider the architecture verified only after **confirming the actual method/path/query/headers at the backend**, separating security/route/transport/upstream errors, and testing timeouts, encoded URLs, TLS, streaming, and load.

Mastering **Servlet, DispatcherServlet, and WebMvc.fn** lets you pinpoint **which layer a request is in, who selects the route, who calls the backend, and who is allowed to modify the response**, enabling you to build a secure, testable, and controllable Spring Cloud Gateway Server Web MVC.
