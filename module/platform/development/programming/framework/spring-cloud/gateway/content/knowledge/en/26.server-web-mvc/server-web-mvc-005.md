# GatewayRequestPredicates and Supported Predicates in Spring Cloud Gateway Server Web MVC

When building an API Gateway, every request must first be **matched to the right route** before being forwarded to the corresponding microservice. The question "does this request match a route?" is answered by a **request predicate**: a condition checking HTTP method, path, host, header, cookie, query parameter, time window, or traffic weight. If a condition is wrong or overly broad, a request can hit the wrong backend, miss essential protection filters, or return 404 even when the service is healthy.

In **SPRING_CLOUD_GATEWAY**, two variants must be distinguished: **Gateway Server WebFlux** uses the reactive ecosystem, whereas **Gateway Server Web MVC** uses the **Spring MVC Servlet stack** and **WebMvc.fn** functional routing. This lesson belongs to the **Server Web MVC** chapter, focusing on `GatewayRequestPredicates`, supported predicates, predicate composition, testing, and security boundaries when the Gateway also handles authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

> **Version scope:** Java examples use package `org.springframework.cloud.gateway.server.mvc.*` and `spring.cloud.gateway.server.webmvc.routes` configuration from modern supported Gateway Server MVC lines. Older docs may use namespace `spring.cloud.gateway.mvc.routes` or differ in starter/DSL. The predicate list, especially `Version`, can **differ between Gateway 4.x and 5.x**. Always check the exact Spring Boot, Spring Cloud release train, starter, and matching MVC documentation. Do not apply these Java APIs verbatim to WebFlux.

## 1. Where Do Predicates Sit in Gateway Server Web MVC?

A **request predicate** is a function that inspects a `ServerRequest` and returns match or no-match. In Server MVC, routes are represented as **`RouterFunction<ServerResponse>`**, integrated into **Spring WebMvc.fn**'s `HandlerMapping` infrastructure.

~~~mermaid
flowchart TD
    C["HTTP request from client"] --> S["Servlet filters / Spring Security"]
    S --> HM["Spring MVC HandlerMapping"]
    HM --> P{"RouterFunction + RequestPredicate match?"}
    P -->|No| N["Try other matching route/handler; possibly 404/405"]
    P -->|Yes| F["Gateway MVC HandlerFilterFunctions"]
    F --> H["HandlerFunctions.http()"]
    H --> LB["HTTP routing or load balancing"]
    LB --> B["Backend microservice"]
    B --> R["Response to client via MVC Gateway"]
~~~

**Distinguishing three jobs:**

| Mechanism | Purpose | Example |
|---|---|---|
| **Predicate** | Determines which requests are routed | `Path=/api/orders/**` and `Method=GET` |
| **Handler function** | Processes the matched request; Gateway typically HTTP-proxies | `HandlerFunctions.http()` |
| **Handler filter function** | Runs before/after handler, transforms request/response, or enforces policy | `BeforeFilterFunctions.uri(...)`, appropriate path/header filters |

A predicate **does not forward the request by itself**. Nor is it **equivalent to authentication/authorization**. A request matching `Host=admin.example.test` does not prove the caller has admin privileges: `Host` is HTTP request data that must be governed through ingress and Spring Security.

### How Servlet MVC Differs from Reactive WebFlux

| Criterion | Gateway Server Web MVC | Gateway Server WebFlux |
|---|---|---|
| Web foundation | Spring MVC / Servlet stack | Spring WebFlux / reactive stack |
| Request type in functional routing | `org.springframework.web.servlet.function.ServerRequest` | `ServerWebExchange` in reactive gateway |
| Route extension points | `RouterFunction`, `RequestPredicate`, `HandlerFilterFunction` | `RouteDefinition`, predicate factory, `GatewayFilter`/`GlobalFilter` |
| Extended predicate class | `GatewayRequestPredicates` | WebFlux route predicate factories |
| Common security | Servlet `SecurityFilterChain` / `HttpSecurity` | Reactive `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Routing filters | MVC handler/before/after filter functions | Reactive `GatewayFilter`/`GlobalFilter` |
| Version-dependent config | `server.webmvc` group or legacy namespace | `server.webflux` group or legacy namespace |

**Do not add both starters and assume they differ only by name.** MVC and WebFlux have different request models, filters, threading, and integrations. When writing code, check imports and the actual web stack to avoid calling similarly named APIs by mistake.

## 2. What Is `GatewayRequestPredicates`?

The central class for this lesson is:

~~~java
org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates
~~~

It provides factory methods returning **`RequestPredicate`** instances for use in WebMvc.fn. Gateway MVC **reuses many Spring WebMvc.fn predicates** while adding Gateway-specific ones.

Names commonly seen in Gateway Server MVC docs:

- `after(...)`, `before(...)`, `between(...)`: time-based conditions.
- `cookie(...)`: cookie name and value regex.
- `header(...)`: HTTP header name and value regex.
- `host(...)`: hostname patterns; may contain URI template variables.
- `method(...)`: one or more HTTP methods.
- `path(...)`: one or more `PathPattern`s.
- `query(...)`: query parameter existence or value regex.
- `weight(...)`: route selection by group and weight.
- **`version(...)`**: API version condition in newer versions supporting Spring MVC's API version strategy.

**Do not assume every WebFlux predicate name exists as an identically named method in MVC's `GatewayRequestPredicates`.** For example, `RemoteAddr` and `XForwardedRemoteAddr` appear in WebFlux docs, yet **are not in the main list on the Gateway Request Predicates page for Server MVC 4.3/5.0**. If you need IP restrictions or forwarded-address checks in MVC, verify actual APIs/extensions and design a Servlet/proxy solution respecting trust boundaries; do not copy `GatewayRequestPredicates.remoteAddr(...)` from WebFlux.

### Common Java DSL Syntax

A Java route can combine route ID, predicate, HTTP handler, and a before filter specifying the target:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

@Configuration(proxyBeanMethods = false)
class GatewayMvcRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogRoute() {
        return route("catalog-route")
            .route(path("/api/catalog/**"), http())
            .before(uri("http://localhost:9090"))
            .build();
    }
}
~~~

What this configuration means:

1. `route("catalog-route")` creates a builder with a **route ID** used for Gateway metadata/observability.
2. `path("/api/catalog/**")` checks the incoming path.
3. `http()` is the handler that proxies requests to the resolved target.
4. `before(uri("http://localhost:9090"))` sets the target URI during pre-handler processing.
5. `build()` returns `RouterFunction<ServerResponse>` for Spring MVC registration.

`GatewayRouterFunctions.route(String)` is helpful when an explicit route ID is needed. Spring WebMvc.fn also has `RouterFunctions.route()` for general functional APIs; **do not confuse the two factories just because both are named `route`**.

## 3. Supported Predicates and Compatibility Scope

This table summarizes the predicate groups described in **Gateway Server MVC** documentation. Examples show **matching conditions** only, excluding target URIs/filters.

| Predicate | Primary inputs | YAML example | Meaning |
|---|---|---|---|
| **After** | Timestamp with timezone | `After=2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]` | Matches after instant |
| **Before** | Timestamp with timezone | `Before=2027-12-31T00:00:00+07:00[Asia/Ho_Chi_Minh]` | Matches before instant |
| **Between** | Two ordered timestamps | `Between=<start>,<end>` | Matches inside time window |
| **Cookie** | Name, regex | `Cookie=channel,partner` | Cookie `channel` matches regex |
| **Header** | Name, regex | `Header=X-Channel,partner` | Header matches |
| **Host** | List of hostname patterns | `Host=**.example.test` | Matches by host |
| **Method** | One or more HTTP methods | `Method=GET,HEAD` | Matches by method |
| **Path** | List of path patterns | `Path=/api/items/**` | Matches by path |
| **Query** | Param, optional regex | `Query=lang,(vi|en)` | Query param exists and matches |
| **Weight** | Group, weight integer | `Weight=catalog-rollout,8` | Selects via weighted distribution |
| **Version** | Fixed or baseline version | `Version=1.3` or `Version=1.1+` | **Version-dependent** and `ApiVersionStrategy` |

**Note on `Version`:** The Gateway Server MVC **5.0** reference describes `Version` based on Spring Framework's `spring.mvc.apiversion.*`. The **4.3** page focuses on After/Before/Between/Cookie/Header/Host/Method/Path/Query/Weight and **does not list `Version`** in that list. Therefore, **do not apply `Version` to a 4.x release without checking the API**.

**Note on WebMvc.fn:** `GatewayRequestPredicates` is not the entire set of predicates `RequestPredicate` can express in Spring MVC. Predicates from `RequestPredicates` such as `accept`, `contentType`, etc. can be used in the Java DSL depending on the Spring Framework version, yet **you should not call all of them Gateway-specific predicates** or assume an equivalent YAML Gateway shortcut exists.

## 4. `Path`: Selecting URLs with Spring `PathPattern`

`Path` is usually the most important condition. It uses Spring MVC's `PathPattern` mechanism to match paths.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-by-path
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
~~~

The route matches paths like `/api/catalog/items/42`, which does not guarantee the backend actually exposes `/api/catalog/items/42`. **Route matching and path rewriting are two separate concerns.**

### Path Variables

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

// Inside a @Bean returning RouterFunction<ServerResponse>:
return route("item-by-id")
    .route(path("/api/items/{itemId}"), http())
    .before(uri("http://localhost:9090"))
    .build();
~~~

On `GET /api/items/42`, the path pattern matches and extracts `itemId`. In MVC, `RequestPredicate` and `RouterFunction` store URI template variables in **request attributes**, and MVC utilities such as `MvcUtils.getUriTemplateVariables(request)` can access them in the proper context.

**Do not retrieve variables directly from `ServerWebExchange`** as in WebFlux code; this is MVC `ServerRequest`. Path variables also **do not automatically modify** the downstream URI unless you configure an appropriate filter/rewrite.

### Things to Test with `Path`

- Are `/api/items/42` and `/api/items/42/` handled consistently?
- Does `/api/items` match `/api/items/**` as intended?
- Does case sensitivity match requirements?
- Are percent-encoded slashes, dot segments, multiple slashes, and Unicode normalization equivalent across ingress/Gateway/backend?
- Does a broad `/**` pattern shadow another protected route?
- Can route IDs/priorities or router function ordering send requests to the wrong route?

**`Path` is not the final authorization layer.** Backends must still check permissions on the item or tenant. Do not rely on `/api/public/**` to decide whether a request is authorized to read data.

## 5. `Method`: Distinguishing GET, HEAD, POST, and Other Operations

The `method(...)` predicate selects one or more HTTP methods. In Server MVC, `GatewayRequestPredicates.method` serves as a convenient counterpart to WebMvc.fn's method predicates.

~~~java
import org.springframework.http.HttpMethod;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;

var readMethods = method(HttpMethod.GET, HttpMethod.HEAD);
~~~

Combined with `Path` in YAML:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: read-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET,HEAD
~~~

This is a **read-only route by HTTP method**, yet the backend must still enforce idempotency and authorization semantics. A declared `GET` that triggers dangerous side effects is a business bug that predicates cannot fix.

### Builder Method + Path Shortcut

`RouterFunctions.Builder` also provides a shorthand combining method and path:

~~~java
@Bean
RouterFunction<ServerResponse> getCatalogRoute() {
    return route("catalog-get")
        .GET("/api/catalog/**", http())
        .before(uri("http://localhost:9090"))
        .build();
}
~~~

This is typically shorter than `path(...).and(method(HttpMethod.GET))` when you only need GET + Path.

**Watch out for `OPTIONS` and CORS preflight:** A route matching only `Method=GET` may not match `OPTIONS` sent by browsers ahead of CORS requests. Do not hastily open the route to all methods; configure CORS and Spring Security/Servlet filters properly, then test `OPTIONS` end-to-end.

## 6. `Host`: Selecting Virtual Hosts and Domains

`host(...)` uses Ant-style hostname patterns with dots as separators. For example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: public-catalog-host
              uri: http://localhost:9090
              predicates:
                - Host=**.api.example.test
                - Path=/catalog/**
~~~

An application separating `catalog.api.example.test` and `admin.api.example.test` can use a `Host` predicate, provided wildcard patterns are carefully governed.

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.host;

var approvedHost = host("catalog.api.example.test");
~~~

### URI Template Variables from `Host`

A pattern like `{tenant}.api.example.test` can capture a `tenant` variable. Gateway MVC stores URI template variables in request attributes; handler filters can reference them using supported APIs.

**Warning:** `tenant` in a hostname **is not proof the caller is authorized for that tenant**. The `Host` header can be set by clients or altered across reverse proxies. Combine TLS/ingress host ownership, trusted proxies, authentication, tenant authorization, and backend checks.

## 7. `Header`: Name and Value Regex

`header(name, regexp)` matches only requests carrying a header whose value matches the regex. Example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-partner-channel
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

Request:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: gateway.example.test
X-Channel: partner
~~~

Matches the route if the header and all other predicates also hold.

Java:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

var channelCondition = header("X-Channel", "partner");
~~~

Because `regexp` uses Java regular expressions, note:

- `partner` differs from `partner-2` depending on how the implementation matches.
- A pattern like `\d+` in a Java string must be written `"\\d+"` to preserve the regex backslash.
- Regex is not `PathPattern` wildcard syntax; they are two different pattern languages.
- A header can have multiple values; never guess how the matcher handles multi-value headers on critical paths without testing.
- Overly complex patterns can burn CPU on long inputs. Bound lengths and avoid patterns prone to catastrophic backtracking.

**Do not use `Header=X-Role,admin` to authorize admins.** Any client can send that header. To protect endpoints, use Servlet Spring Security `SecurityFilterChain` or a trusted authentication layer in front.

## 8. `Cookie`: Matching by Cookie Name and Regex

`cookie(name, regexp)` inspects cookies on the incoming request:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: cookie-demo
              uri: http://localhost:9090
              predicates:
                - Path=/api/demo/**
                - Cookie=channel,partner
~~~

Java:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.cookie;

var cookieCondition = cookie("channel", "partner");
~~~

**Cookies are also client-controlled input.** A cookie may hold a server-verified session ID, yet simply seeing a cookie value matching regex `admin` **does not prove an authenticated session**.

In systems using Spring Security Servlet, user identity must come from the security context/principal after authentication. Cookie-based predicates or filters work for **convenience routing**, such as testing on opted-in clients, never for granting privileges.

### Cookie Variants and Limitations

- Clients can send multiple cookies with the same name from different domains/paths.
- Browsers enforce `SameSite`, `Secure`, and `HttpOnly` per cookie policy.
- Raw `Cookie` headers are unsuitable for verbatim logging.
- Sticky routing based on arbitrary cookies may lose stability if users clear cookies; design explicit stickiness mechanisms.
- Never place session IDs into metric tags or audit logs.

## 9. `Query`: Checking Parameter Presence or Value Regex

`query(...)` has two common forms:

1. Require only that a query parameter be **present**.
2. Require the parameter's value to match a regex.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: has-preview-flag
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Query=preview

            - id: language-filter
              uri: http://localhost:9091
              predicates:
                - Path=/api/articles/**
                - 'Query=lang,(vi|en)'
~~~

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.query;

var hasPreview = query("preview");
var vietnameseOrEnglish = query("lang", "(vi|en)");
~~~

**Never treat the presence of a query parameter as proof a feature is authorized.** `?preview=true` can be added by any client. If preview data is confidential or unreleased, the backend must still verify permissions.

### Repeated Values and Encoding

Test URLs such as:

~~~text
/api/articles?lang=vi
/api/articles?lang=en
/api/articles?lang=fr
/api/articles?lang=vi&lang=en
/api/articles?lang=
/api/articles?lang=%76%69
~~~

How repeated query parameters are picked, percent-encoding is decoded, and regex matching behaves must be verified with real requests on your Gateway version, especially when routing affects data or policy. Unexpected parsing/regex behavior can route requests to the wrong service.

## 10. `After`, `Before`, `Between`: Time-Based Conditions

These predicates route based on **the server's clock when evaluating the request**.

- `after(ZonedDateTime)`: matches requests after the instant.
- `before(ZonedDateTime)`: matches requests before the instant.
- `between(ZonedDateTime, ZonedDateTime)`: matches within an interval; the second instant must be after the first.

Example of a 2027 rollout window with an explicit timezone:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-launch-window
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - After=2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]
                - Before=2027-02-01T00:00:00+07:00[Asia/Ho_Chi_Minh]
~~~

Both conditions on the route must hold simultaneously. When using `Between` instead, pass both instants in the syntax supported by your release train.

Java:

~~~java
import java.time.ZonedDateTime;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.between;

var launchWindow = between(
    ZonedDateTime.parse(
        "2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]"),
    ZonedDateTime.parse(
        "2027-02-01T00:00:00+07:00[Asia/Ho_Chi_Minh]")
);
~~~

Some documentation lines support passing **epoch milliseconds** in configuration. Do not confuse epoch milliseconds with seconds, or omit timezones and rely on the server's default timezone.

### What Risks Do Time Conditions Carry?

| Risk | Impact | How to check |
|---|---|---|
| Clock skew across Gateway nodes | Same request yields different outcomes on different nodes | Sync NTP/clocks and monitor nodes |
| Missing timezone/offset | Window opens/closes at the wrong hour | Always use explicit `ZonedDateTime` |
| DST in daylight-saving zones | Cutoff shifts in local time | Test near DST transitions if applicable |
| Second timestamp not after first | Invalid config or unexpected matching | Validate at startup/deploy |
| Boundary equality differences | Tests fail right on the boundary | Test before/at/after per implementation contract |
| Using time predicates for access control | Route may open before security policy is ready | Enforce independent Spring Security protection |

**Never use `After`/`Before`/`Between` as a security revocation mechanism.** They perform clock-based route selection, not authentication, authorization, controlled feature flags, or release governance.

## 11. `Weight`: Canary Traffic by Group and Weight

`weight(group, weight)` distributes requests across routes in the **same group** according to weights. Example with two catalog versions:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-stable
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Weight=catalog-rollout,8

            - id: catalog-canary
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Weight=catalog-rollout,2
~~~

The goal is roughly **80% traffic** to stable and **20%** to canary when other conditions match equally and weighting is applied correctly.

**Never guarantee an exact 8/10 split in every batch of 10 requests.** This is a statistical distribution; use a sufficiently large sample size, measure by route ID, and run real tests.

Equivalent Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.weight;

@Bean
RouterFunction<ServerResponse> catalogCanaryRoutes() {
    return route("catalog-stable")
        .route(weight("catalog-rollout", 8)
            .and(path("/api/catalog/**")), http())
        .before(uri("http://localhost:9090"))
        .build()
        .and(route("catalog-canary")
            .route(weight("catalog-rollout", 2)
                .and(path("/api/catalog/**")), http())
            .before(uri("http://localhost:9091"))
            .build());
}
~~~

### What `Weight` Does Not Provide Automatically

- **Not sticky per user**; the same user may hit stable on one request and canary on the next.
- Does not imply a canary deployment passed health/readiness checks.
- Does not automatically resolve token audience, session sharing, schema, or cache compatibility.
- Does not restrict traffic by geography or tenant.
- Does not ensure both routes share identical fallback/circuit-breaker policies.

For safe rollouts, distribute **within the same intended path/method/host scope**, keep security filters and resource budgets consistent, monitor errors/latency per route, and have a rollback plan.

## 12. `Version`: Newer Predicate Requiring `ApiVersionStrategy`

In newer Gateway Server MVC versions supporting `Version`, route matching can evaluate API versions extracted by **Spring Framework's `ApiVersionStrategy`**.

Example configuring a header-based version resolver and routing by version:

~~~yaml
spring:
  mvc:
    apiversion:
      use:
        header: X-API-Version

  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-v13
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Version=1.3

            - id: catalog-v11-plus
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Version=1.1+
~~~

Meaning in supported documentation:

- `Version=1.3`: matches exact version `1.3`.
- `Version=1.1+`: matches version `1.1` or higher per version comparison strategy.
- `spring.mvc.apiversion.use.header` configures how the version is extracted from requests.

**Do not apply this snippet to Gateway 4.3 or a Spring Framework version lacking MVC API versioning support.** Property names and behavior must be confirmed against your target version.

### Fail-Open Risk When Resolver Is Missing

Gateway MVC **5.0** docs note a critical behavior: **when no `ApiVersionStrategy` is configured, the `Version` predicate may treat requests as matching rather than blocking them**. Therefore, if using version routes to separate sensitive APIs:

1. Configure the strategy with an explicit version source.
2. Test requests with valid, missing, wrong, and malformed versions.
3. Never treat a client-chosen version header as authentication or authorization.
4. Check route ordering/conflicts, especially when baseline `1.1+` and exact `1.3` routes can both match.
5. Maintain backend compatibility; version routing does not transform schemas or bodies.

**Important:** Missing-strategy behavior and tie-breaking may vary across releases. Never design access control solely around version predicates.

## 13. Combining Predicates with AND, OR, and Negation

**WebMvc.fn** `RequestPredicate` supports combining conditions with `and(...)`, `or(...)`, and—on supported framework APIs—`negate()`.

### AND: All Conditions Must Hold

~~~java
import org.springframework.http.HttpMethod;

import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

var partnerCatalog = path("/api/catalog/**")
    .and(method(HttpMethod.GET))
    .and(header("X-Channel", "partner"));
~~~

Requests match when path, GET method, and header **all match simultaneously**.

Listing multiple predicates on the **same YAML route** expresses the same AND logic:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: partner-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

### OR: Any One Branch Matching Suffices

~~~java
var eitherVersionPath = path("/api/v1/catalog/**")
    .or(path("/api/v2/catalog/**"));
~~~

Use OR when branches truly belong to the **same route/handler**. When merely combining two paths, `path("/api/v1/catalog/**", "/api/v2/catalog/**")` is also worth considering.

**Do not treat multiple items under `predicates:` in a YAML route as OR.** For static configs, use multi-pattern support within a single predicate or define separate routes; do not invent an `Or=...` syntax unless your Gateway version provides one.

### Parentheses for Clear Logic

~~~java
var policy = path("/api/catalog/**")
    .and(method(HttpMethod.GET))
    .and(
        header("X-Channel", "partner")
            .or(query("preview"))
    );
~~~

Meaning:

~~~text
Path matches
  AND Method=GET
  AND (X-Channel=partner OR query parameter preview present)
~~~

The Java expression above uses `preview` as an **illustrative routing signal**, not authorization to view preview data. Authentication and authorization must still be enforced independently.

### Negation

`RequestPredicate.negate()` can exclude a group of requests in the Java DSL where supported. However, **never rely on negating Headers/Queries to prevent security identity spoofing**: clients control those inputs, and configs with nested OR/NOT branches easily create unintended match regions.

~~~mermaid
flowchart TD
    A["Incoming request"] --> P{"Path=/api/catalog/**?"}
    P -->|No| X["No match"]
    P -->|Yes| M{"Method=GET?"}
    M -->|No| X
    M -->|Yes| CH{"Header X-Channel=partner OR Query preview present?"}
    CH -->|Yes| Y["Route matches -> HandlerFunctions.http()"]
    CH -->|No| X
~~~

## 14. WebMvc.fn Predicates Are Not Necessarily Gateway-Specific

`GatewayRequestPredicates` builds on **Spring WebMvc.fn**. In the Java DSL, you may also encounter Spring Framework predicates:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;

var expectsJson = accept(MediaType.APPLICATION_JSON);
var sendsJson = contentType(MediaType.APPLICATION_JSON);
~~~

The two conditions differ:

- `accept(application/json)` checks the representation the client **can accept** (typically via the `Accept` header).
- `contentType(application/json)` checks the media type of the request body (via `Content-Type`).

They can help select handlers in WebMvc.fn, but:

1. **Do not refer to them as `GatewayRequestPredicates` methods when they actually come from `RequestPredicates`.**
2. Do not assume every functional predicate has a matching YAML Gateway route predicate syntax.
3. Do not treat client-sent `Content-Type` as proof of a valid body; backends must still validate payload/schema.
4. Test CORS, method matching, and error handling against the live MVC runtime.

### `RemoteAddr` and IP-Based Routing

Many WebFlux guides feature `RemoteAddr` and `XForwardedRemoteAddr` predicates. **Do not copy that list straight to Gateway MVC** when your version's MVC documentation does not expose them. IP-based routing in the Servlet stack may require:

- A trusted ingress/WAF or server-layer routing.
- A custom `RequestPredicate` inspecting `ServerRequest.servletRequest()`/remote address via supported APIs, after establishing proxy trust.
- Checking `Forwarded`/`X-Forwarded-For` configuration in the web server/Spring MVC to prevent IP spoofing.

**Never treat raw `X-Forwarded-For` as an access credential.** Rely only on forwarded metadata controlled by a trusted proxy chain; backends still need authorization.

## 15. Configuring the Same Logic in Java DSL and YAML

Suppose the business goal is: allow only GET requests under `/api/catalog/**` carrying header `X-Channel: partner` to reach the catalog backend.

### Option 1: Java DSL

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

@Configuration(proxyBeanMethods = false)
public class CatalogGatewayMvcConfiguration {

    @Bean
    public RouterFunction<ServerResponse> partnerCatalogRoute() {
        return route("partner-catalog")
            .route(
                path("/api/catalog/**")
                    .and(method(HttpMethod.GET))
                    .and(header("X-Channel", "partner")),
                http()
            )
            .before(uri("http://localhost:9090"))
            .build();
    }
}
~~~

### Option 2: YAML

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: partner-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

**Do not declare both definitions with the same route ID simultaneously in one app expecting them to represent one route.** Choose a single configuration mechanism (or manage distinct IDs and precedence explicitly) to avoid duplicate routes and unintended selection.

### Comparison

| Criterion | Java DSL | YAML |
|---|---|---|
| Expression reuse in Java | High, easy `and`/`or`/custom predicates | Bound by configuration binder syntax |
| Route config review | Requires reading code and tests | Routes and parameters easily visible |
| Custom `RequestPredicate` | Directly in code | Requires appropriate binder/infrastructure |
| Config changes | Standard code build/deploy | Configurable through deployment config |
| Type checking | Compiler checks API | Startup/binding catches errors |
| Risks | Missing tests, DSL changes per version | Wrong namespace, predicate typos, order/route overlap |

Choose Java when clear boolean composition or custom predicates are required; choose YAML when standard, easily reviewable conditions suffice. In either case, **never let untrusted users decide URIs, regexes, filters, hosts, or route priorities**.

## 16. Route Selection Does Not Enforce Security Policy

A request matching all route predicates can still be unauthorized.

### Who Controls Headers, Cookies, Queries, and Hosts?

| Data | Can the client set it? | Should it be used for authorization? |
|---|---|---|
| `X-Role` / `X-Channel` | Yes | No, unless verified by a trusted layer |
| Arbitrary Cookie | Yes | No; must validate session/credential |
| Query `?admin=true` | Yes | No |
| `Host` | Spoofable depending on ingress/TLS/proxy | Never alone |
| `Authorization: Bearer ...` | Client sends token, system must verify | Validate via **Spring Security** before trusting |
| Verified JWT claims | Issued by trusted issuer and validated | Can feed authorization policies |
| Forwarded IP | Spoofable if proxy does not strip | Only via trusted-proxy policy |

Gateway Server MVC normally integrates **Spring Security Servlet**. Route predicates run during WebMvc.fn matching; they **do not** validate JWTs, roles/scopes, session fixation, or CSRF.

To protect `/api/admin/**`, configure a dedicated `SecurityFilterChain` and enforce backend authorization. When multiple Spring Security filter chains or separate management ports exist, test each path/method/host explicitly rather than assuming an unmatched route cannot be reached elsewhere.

### CORS Preflight and Method Predicates

Browsers may send `OPTIONS` preflight requests before POST/GET calls with custom headers. A `Method=POST` route normally does not match `OPTIONS`; preflight outcomes depend on Servlet/Spring MVC CORS, Spring Security, and reverse proxies. **Never add `OPTIONS` unconditionally to every route**; configure CORS policies for allowed origins/methods/headers, then verify with browsers and cURL.

### Wildcard `Host` Routes

`Host=**.example.test` can match many hostnames belonging to different tenants/vhosts. For multitenancy, pair this with proper **tenant routing + authorization**, never merely extracting a template variable from `Host` and forwarding requests to user-influenced targets.

## 17. Testing Predicates Beyond a Single Happy-Path Request

A lab should verify all of the following together:

1. **A matching request** hits the route and reaches the backend.
2. **A near-miss request failing one condition** does not enter that route.
3. No **other route** accidentally catches the rejected request.
4. No security headers are lost or cross-tenant data leaked.
5. Proxy/encoding/duplicate-header/route-overlap edge cases behave as designed.

### Lab Environment

Assume:

- Gateway Server MVC at `http://localhost:8080`.
- Test echo backend at `http://localhost:9090`, returning path/method and test HTTP status; never echoing real `Authorization`/`Cookie`.
- Route `partner-catalog` from Section 15.
- No other route overlapping `/api/catalog/**` in the baseline test setup.
- Explicit lab Spring Security policy; if auth is enabled, pass valid test credentials.

### Step 1 — All Three Conditions Match

~~~bash
curl -i \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Expect **route match**, backend invoked. Final HTTP status depends on backend/test security; never use HTTP 200 as sole proof if another handler sits in front.

### Step 2 — Wrong Header

~~~bash
curl -i \
  -H "X-Channel: guest" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Expect `partner-catalog` **not to match**. Response may be 404, 405, 401/403, or another route depending on the app; the key is that the partner-route backend **is not called**.

### Step 3 — Wrong Method

~~~bash
curl -i -X POST \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Expect no match on the GET-only route. If the app has another POST handler, a response may still return; therefore, tests must verify **route ID/target backend**, not status alone.

### Step 4 — Wrong Path

~~~bash
curl -i \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/orders/42"
~~~

Does not match `Path=/api/catalog/**`.

### Step 5 — CORS Preflight Case

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: X-Channel" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Observe `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and status against real policy. Never assume `GatewayRequestPredicates.method(GET)` handles `OPTIONS`.

### Predicate Test Matrix

| Predicate | Positive test | Negative/boundary test |
|---|---|---|
| Path | `/api/catalog/items/42` | Other paths, trailing slash, encoded slash |
| Method | Allowed GET | Disallowed POST/DELETE |
| Host | Host matching pattern | Other tenant host, spoofed Host, proxy host |
| Header | Value matching regex | Missing header, multi-value, near-match regex |
| Cookie | Matching cookie name/value | Forged cookie, duplicate names, missing cookie |
| Query | `lang=vi` | `lang=fr`, repeated param, percent-encoding |
| After/Before | Request inside window | Before/at/after boundary, clock-skewed nodes |
| Between | Valid time bounds | Reversed bounds, timezone mismatch |
| Weight | Many requests close to target ratio | Small sample, route overlap, unhealthy canary |
| Version (if supported) | Valid version | Missing resolver, missing/malformed version, baseline overlap |

## 18. Direct Unit Tests with `RequestPredicate` and Mock `ServerRequest`

Because Server MVC uses **WebMvc.fn `RequestPredicate`**, matching logic can be unit-tested without booting the entire Gateway. Example testing `Path` + `Method` + `Header` with `MockHttpServletRequest`:

~~~java
package example.gateway.mvc;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.converter.StringHttpMessageConverter;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.function.RequestPredicate;
import org.springframework.web.servlet.function.ServerRequest;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

class GatewayRequestPredicateTest {

    private final RequestPredicate predicate =
        path("/api/catalog/**")
            .and(method(HttpMethod.GET))
            .and(header("X-Channel", "partner"));

    private ServerRequest request(
            String httpMethod, String uri, String channel) {

        MockHttpServletRequest servletRequest =
            new MockHttpServletRequest(httpMethod, uri);

        if (channel != null) {
            servletRequest.addHeader("X-Channel", channel);
        }

        return ServerRequest.create(
            servletRequest, List.of(new StringHttpMessageConverter()));
    }

    @Test
    void matchesWhenAllConditionsAreTrue() {
        assertTrue(predicate.test(request(
            "GET", "/api/catalog/items/42", "partner")));
    }

    @Test
    void rejectsDifferentMethod() {
        assertFalse(predicate.test(request(
            "POST", "/api/catalog/items/42", "partner")));
    }

    @Test
    void rejectsDifferentHeader() {
        assertFalse(predicate.test(request(
            "GET", "/api/catalog/items/42", "guest")));
    }
}
~~~

**Test goal:** verify `AND` logic and API behavior on a given Spring Framework version. This snippet requires `spring-test`, JUnit, and matching test dependencies. It **does not yet prove** that Spring registered the route bean, YAML bound properly, or Gateway forwards to the desired URI.

### Integration Tests Still Needed

An integration test with a real Gateway MVC runtime and mock HTTP backend must verify:

- Whether the route ID is registered in `HandlerMapping`.
- Whether URI `http://localhost:9090` is actually used.
- Whether matching/non-matching requests call the backend.
- Whether URI/path/header filters execute properly before `HandlerFunctions.http()`.
- Which layer generates 404/405/401/403 responses.
- Whether adding another route alters **route ordering/conflicts**.
- Whether startup still succeeds on the supported Java/Boot/Cloud baseline.

Do not conclude production config is sound based solely on the three unit tests above.

## 19. Troubleshooting: When MVC Routes Do Not Match

| Symptom | Causes to inspect | How to check |
|---|---|---|
| Cannot find `GatewayRequestPredicates` | Using WebFlux starter, wrong artifact/version, wrong import | Verify Gateway Server MVC and package |
| YAML routes not loaded | Wrong `server.webmvc` / legacy namespace | Check `configprops` for your release train |
| Path matches yet returns 404 | Mismatched Method/Header/Host/Query; route unregistered | Test each predicate and route ID |
| GET method does not match | Builder/route accepts a different method | Compare predicate vs. actual HTTP method |
| Host matches directly yet fails behind ingress | Proxy rewrote `Host` | Check `Host`/forwarded host and trusted proxies |
| Header/Cookie/Query regex fails | Regex escaping, YAML quoting, repeated values | Test live inputs and canonicalization |
| Used `and` when `or` was intended | Wrong boolean logic | Group branches explicitly in Java DSL |
| Assumed multiple YAML predicates are OR | Multiple predicates in one route are AND | Use multi-patterns or separate routes |
| Time predicate fails on one node | Clock/timezone skew | Check NTP/timezones and boundaries |
| Weight split is not 80/20 over 10 requests | Sample too small, different group or predicates | Measure statistically with larger samples |
| `Version` does not work | Unsupported in Gateway version or missing `ApiVersionStrategy` | Check Spring MVC version strategy and tests |
| `RemoteAddr` method missing | Copied WebFlux API to MVC | Use a custom MVC predicate/edge policy if needed |
| Security returns 401/403 before route | Servlet Spring Security blocked it | Inspect dedicated `SecurityFilterChain` |
| `OPTIONS` preflight rejected | Method predicate only GET/POST; wrong CORS/security | Check CORS at MVC/Servlet layer |
| Backend returns 404 after route matched | Path/URI not rewritten properly | Inspect real request arriving at backend |
| New route steals traffic from old route | Overlapping pattern/host/order | Review all `RouterFunction`s, priorities, and route IDs |
| Client-sent header treated as permission | Used predicate instead of authorization | Separate authentication and authorization |
| Canary Weight config breaks after deploy | Incompatible schemas/auth across targets | Roll back, check health and traffic split |

### 6-Question Fault Isolation Flow

1. Is the app running **Gateway Server Web MVC** or WebFlux?
2. Is the route declared in **YAML** or **Java DSL**, with the right namespace/imports?
3. Which `Path`, `Method`, `Host`, `Header`, `Cookie`, `Query`, time, or version condition rejects the request?
4. Is another route/handler matching first or a security filter blocking it?
5. Once matched, does `HandlerFunctions.http()` forward to the right backend/path/instance?
6. Did the final HTTP status come from Gateway routing, Servlet security, ingress, or downstream?

Never "fix" issues by changing predicates to `Path=/**` or opening global `permitAll`: that turns a matching bug into a security incident.

## 20. Acceptance Checklist and Practice Exercises

### Checklist

- [ ] I know **Server Web MVC** runs on Servlet/WebMvc.fn, not reactive WebFlux.
- [ ] I import `GatewayRequestPredicates` from package `server.mvc.predicate`.
- [ ] I understand `RouterFunction<ServerResponse>`, `HandlerFunctions.http()`, and `BeforeFilterFunctions.uri(...)`.
- [ ] I distinguish route-selecting predicates from forwarding handlers/filters.
- [ ] I use `Path` with `PathPattern` syntax and test URLs containing template variables.
- [ ] I know `Method` and `.GET(...)` in the Java DSL.
- [ ] I know `Header`, `Cookie`, and `Query` use regex and are not authentication mechanisms.
- [ ] I verify `Host`/virtual hosts and proxy trust boundaries.
- [ ] I know `After`, `Before`, and `Between` require timezone-aware timestamps and synced clocks.
- [ ] I know `Weight` distributes by group/weight, is not sticky, and does not guarantee exact ratios on small samples.
- [ ] I use `Version` only when supported by Gateway/MVC and after configuring `ApiVersionStrategy`.
- [ ] I never copy `RemoteAddr`/`XForwardedRemoteAddr` from WebFlux docs to MVC without verifying the API.
- [ ] I use `and`/`or`/`negate` deliberately and never mistake multiple YAML predicates for OR.
- [ ] I never label `RequestPredicates` methods as `GatewayRequestPredicates`-specific features.
- [ ] I test route conflicts, wildcard Path/Host patterns, and route priorities.
- [ ] I never treat client-declared Host/Header/Cookie/Query values as access proof.
- [ ] I maintain Spring Security Servlet authN/authZ, rate limiting, TLS, and backend authorization independently.
- [ ] I have tested CORS preflight `OPTIONS`, forwarded paths, backend errors, and header/proxy edge cases.
- [ ] I run unit tests on WebMvc.fn predicates alongside Gateway → backend integration tests.
- [ ] I verify config namespaces/starters/versions whenever upgrading Spring Cloud release trains.

### Practice Exercises

**Exercise 1 — AND:** Build a route matching `GET /api/public/articles/**` only when `Query=lang,(vi|en)`. Test `lang=vi`, `lang=fr`, missing param, and a POST request.

**Exercise 2 — OR:** Use the Java DSL to route both `/api/v1/catalog/**` and `/api/v2/catalog/**` to one backend; compare against two separate YAML routes and check ordering.

**Exercise 3 — Host:** Create two routes sharing a path but differing by `Host`. Test direct requests and requests through ingress; prove a client cannot bypass authorization using `Host` alone.

**Exercise 4 — Time window:** Use `Between` for a maintenance window with an explicit timezone; test before, right on the boundary, and after the cutoff across two Gateway nodes.

**Exercise 5 — Canary:** Configure `Weight=catalog-rollout,9` and `Weight=catalog-rollout,1` for the same path. Send enough test requests to verify traffic split, 5xx handling, latency, and auth policies on stable/canary.

**Exercise 6 — Version (if supported):** Configure `spring.mvc.apiversion.use.header` and `Version=1.3`. Test missing header, wrong version, valid version, then remove the resolver in the lab to observe version-specific behavior.

**Exercise 7 — Security invariants:** Try adding `Header=X-Role,admin` on a sensitive route; explain why Spring Security Servlet and backend authorization are still required.

## Official Documentation

- [Spring Cloud Gateway — Gateway Request Predicates, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html) — predicate list and Java/YAML examples for the current line.
- [Spring Cloud Gateway 4.3 — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html) — compare the 4.3 predicate set, especially since `Version` is not listed there.
- [Spring Cloud Gateway — Java Routes API, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/java-routes-api.html) — `RouterFunctions.Builder`, `GatewayRouterFunctions`, and `HandlerFunctions.http()`.
- [Spring Cloud Gateway — How It Works, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html) — `HandlerMapping` mechanics and handler/filter types.
- [Spring Framework — WebMvc.fn](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html) — `RouterFunction`, `RequestPredicate`, `and`/`or`, and composing functional routes.
- [Spring Framework — MVC API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-versioning.html) — `ApiVersionStrategy` and version resolution on supported lines.
- [Spring Security — Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/index.html) — authentication, authorization, and `SecurityFilterChain`; never use predicates in place of security.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html) — property binding and environment-based configuration management.

**Takeaway:** `GatewayRequestPredicates` in **Spring Cloud Gateway Server Web MVC** builds request-matching conditions for **WebMvc.fn `RouterFunction`** routes, covering **Path, Method, Host, Header, Cookie, Query, After, Before, Between, Weight**, and **Version on supported lines**. Choose the right stack, distinguish **predicates from filters and authentication**, understand `and`/`or`, check namespaces/predicates per release train, and test requests that **must not match**. A syntactically valid matching route does not guarantee it targets the right backend or is safe to expose.
