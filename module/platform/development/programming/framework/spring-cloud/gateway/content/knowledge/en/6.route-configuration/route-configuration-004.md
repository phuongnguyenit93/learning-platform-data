# Shortcut Syntax vs. Fully Expanded `name` and `args` Declarations in Spring Cloud Gateway

In **SPRING_CLOUD_GATEWAY**, a route typically consists of a target URI, **route predicates** to select requests, and **Gateway filters** to transform or control the processing flow. When reading the documentation, you will encounter two ways to declare the same predicate or filter:

- **Shortcut notation**: packs the factory name and its arguments into a single string such as `Path=/api/orders/**` or `StripPrefix=1`.
- **Fully expanded notation**: explicitly writes the factory name under `name`, and places named parameters under `args`.

This lesson belongs to the **Route Configuration** chapter and explains how to convert between the two notations, determine when they are equivalent, avoid argument-splitting pitfalls, and verify behavior with real requests. This is a foundational skill for configuring routing, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability in microservices systems.

> **Scope:** The YAML examples use the common declaration style of **Spring Cloud Gateway Server WebFlux 4.x** with `spring.cloud.gateway.routes`. In other release lines, the namespace or starter name may change; Gateway Server MVC also has its own configuration and API. Always select documentation matching your exact version and variant before copying.

## 1. Two Ways to Express the Same Definition

Consider a route that accepts requests to `/api/orders/**` and drops the first path segment before forwarding to the backend.

**Shortcut notation:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

**Fully expanded notation:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
          filters:
            - name: StripPrefix
              args:
                parts: 1
~~~

In both examples, assuming the backend at `localhost:9090` has an endpoint `GET /orders/42`, a `GET /api/orders/42` request through the gateway is forwarded as `GET /orders/42` (provided no other filter modifies the path). Both notations describe **the same `Path` predicate** and **the same `StripPrefix` filter** with equivalent values.

What they share is not identical YAML strings, but the **final configuration bound to the factory**:

| Element | Shortcut | Expanded | Meaning |
|---|---|---|---|
| Predicate | `Path=/api/orders/**` | `name: Path` + `args.patterns` | Matches the URL path |
| Filter | `StripPrefix=1` | `name: StripPrefix` + `args.parts: 1` | Strips one leading path segment |
| Where declared | A string item in a list | An object/map item in a list | Both are parsed into a route definition |
| Expressiveness | Concise; positional values | Explicit; named fields | Easier to review when there are many parameters |

**There are not two different kinds of filters.** In equivalent cases, the Gateway converts both declaration styles into a shared configuration and creates the same underlying processing object.

## 2. YAML Structure to Remember

A `RouteDefinition` describes an ID, URI, predicates, and filters:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: my-route
          uri: http://localhost:9090
          order: 0
          predicates: []
          filters: []
~~~

Three levels that must not be confused:

1. **Route**: `id`, `uri`, `order`, `predicates`, `filters`. `uri` is the routing destination; it is not an argument to a predicate or filter.
2. **A predicate or filter item**: can be a shortcut string or a map containing `name` and `args`.
3. **Factory arguments**: specific keys under `args`, such as `patterns`, `parts`, `name`, `value`.

The same word `name` can appear in two different places:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

- `filters[0].name` selects the **AddRequestHeader** factory.
- `filters[0].args.name` is the **HTTP header name** `X-Edge-Origin`.
- `filters[0].args.value` is the **header value** `gateway`.

If you put `X-Edge-Origin` directly into `filters[0].name` or omit `args` when using the expanded form, the Gateway will not receive the right factory name or parameters.

## 3. How Does the Gateway Interpret Shortcut Syntax?

Shortcut syntax typically follows the pattern:

~~~text
- <FactoryName>=<value-1>,<value-2>,...
~~~

For example:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
filters:
  - AddRequestHeader=X-Edge-Origin,gateway
  - StripPrefix=1
~~~

One way to visualize the WebFlux route-loading process:

~~~mermaid
flowchart TD
    Y["YAML route"] --> D{"Which form does a predicate/filter item use?"}
    D -->|"Shortcut string"| S["Split factory name and positional values"]
    D -->|"Map name + args"| F["Read factory name and named parameter map"]
    S --> B["Bind and validate factory configuration"]
    F --> B
    B --> C["RoutePredicateFactory / GatewayFilterFactory"]
    C --> R["Create runtime predicate or GatewayFilter"]
    R --> RT["Route used for requests"]
~~~

In the corresponding implementations, a shortcut is mapped to internal parameters in the order defined by the factory (for example, via the `shortcutFieldOrder()` mechanism of `ShortcutConfigurable`). Therefore:

- **Argument order is part of shortcut syntax.** `AddRequestHeader=X-Edge-Origin,gateway` is different from `AddRequestHeader=gateway,X-Edge-Origin`.
- **Keys inside `args` are configuration field names**, not first or second positions. For `AddRequestHeader`, the standard names are `name` and `value`.
- **Not every factory has a shortcut**, and not every complex configuration fits cleanly onto a single line.
- Details on parameter order, count, and types **depend on the factory and version**. Do not extrapolate from examples of other factories.

Internally in `PredicateDefinition` or `FilterDefinition`, shortcuts may be stored under synthetic parameter keys such as `_genkey_0`, then mapped according to the factory's configuration when building the `Route`. These keys are **implementation details**; configuration authors should prefer the public field names in the `name`/`args` form.

## 4. Equivalent Predicate Examples

### 4.1. Path: URL Path Condition

Shortcut:

~~~yaml
predicates:
  - Path=/api/products/**
~~~

Expanded:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/products/**
~~~

The expanded form makes multiple patterns easy to read:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/products/**
        - /catalog/**
~~~

Multiple patterns inside **one `Path` predicate** are generally treated as alternatives. Conversely, multiple **separate predicates** within the same route must **all be satisfied simultaneously** (AND).

If you need advanced options such as trailing-slash handling, check the API/config fields of `PathRoutePredicateFactory` for your exact version; do not assume parameter names from one version work in another.

### 4.2. Method: Restricting HTTP Methods

Shortcut:

~~~yaml
predicates:
  - Method=GET,POST
~~~

Expanded:

~~~yaml
predicates:
  - name: Method
    args:
      methods:
        - GET
        - POST
~~~

Here `GET` and `POST` are the methods accepted by **a single `Method` predicate**. If a route declares both `Path` and `Method`, a request must match both the path and one of the listed methods.

### 4.3. Header: Header Name and Regular Expression

Shortcut when the regex contains no commas:

~~~yaml
predicates:
  - Header=X-Client-Id,.+
~~~

Expanded:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '.+'
~~~

The `Header` predicate checks the header value against a regex, not a "fuzzy" substring match. When the regex is complex or contains commas, the expanded form is safer and easier to read:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '^[0-9]{1,3}$'
~~~

The expression `^[0-9]{1,3}$` accepts one to three digits. The comma in `{1,3}` is **part of the regex**; if you put that entire regex into a shortcut that splits parameters by commas, the string can be split incorrectly. Use the expanded form to keep the value intact.

## 5. Equivalent GatewayFilter Examples

### 5.1. StripPrefix: Dropping Path Segments

Shortcut:

~~~yaml
filters:
  - StripPrefix=2
~~~

Expanded:

~~~yaml
filters:
  - name: StripPrefix
    args:
      parts: 2
~~~

For the request `/api/v1/orders/42`, `StripPrefix=2` drops the two segments `api` and `v1`, so the backend receives `/orders/42` if no other component alters the path.

### 5.2. AddRequestHeader: Adding a Header Sent Downstream

Shortcut:

~~~yaml
filters:
  - AddRequestHeader=X-Edge-Origin,gateway
~~~

Expanded:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

Note the semantic differences across header factories:

- **AddRequestHeader** appends a header value; if the header already exists, the request may carry multiple values.
- **SetRequestHeader** sets/replaces the header value according to the factory's behavior.
- **RemoveRequestHeader** removes a header by name.

These factories serve different purposes even though they all deal with HTTP headers. Do not swap factory names just to "write less."

### 5.3. AddRequestParameter: Adding a Query Parameter

Shortcut:

~~~yaml
filters:
  - AddRequestParameter=source,gateway
~~~

Expanded:

~~~yaml
filters:
  - name: AddRequestParameter
    args:
      name: source
      value: gateway
~~~

For example, `GET /items?sort=asc` can be forwarded with the query parameter `source=gateway`. This modifies the downstream request and is **not a Route Predicate**.

### 5.4. SetResponseHeader: Modifying a Response Header

Shortcut:

~~~yaml
filters:
  - SetResponseHeader=X-Served-By,edge-gateway
~~~

Expanded:

~~~yaml
filters:
  - name: SetResponseHeader
    args:
      name: X-Served-By
      value: edge-gateway
~~~

Unlike `AddRequestHeader`, this filter modifies a **response header**. When verifying it, inspect the headers in the response received by the client; do not look for it in the downstream request.

### Quick Comparison Table

| Component | Shortcut syntax | `args` fields in expanded form |
|---|---|---|
| Path predicate | `Path=/api/**` | `patterns: [/api/**]` |
| Method predicate | `Method=GET,POST` | `methods: [GET, POST]` |
| Header predicate | `Header=X-Token,.+` | `header: X-Token`, `regexp: '.+'` |
| StripPrefix filter | `StripPrefix=1` | `parts: 1` |
| AddRequestHeader filter | `AddRequestHeader=X-Trace,edge` | `name: X-Trace`, `value: edge` |
| AddRequestParameter filter | `AddRequestParameter=source,edge` | `name: source`, `value: edge` |
| SetResponseHeader filter | `SetResponseHeader=X-Edge,yes` | `name: X-Edge`, `value: 'yes'` |

These are **examples of the listed factories**, not a universal rule for deriving field names for every predicate/filter. When declaring `Retry`, `CircuitBreaker`, `RequestRateLimiter`, or other filters, look up the exact `args` fields supported by that factory.

## 6. Complete Example: Two Routes Configured Using Both Styles

The two routes below serve **two separate APIs**. The products route uses shortcut syntax and the orders route uses expanded syntax to illustrate both styles in the same Gateway WebFlux application.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: products
          uri: http://localhost:9091
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Edge-Origin,gateway

        - id: orders
          uri: http://localhost:9092
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
            - name: Method
              args:
                methods:
                  - GET
          filters:
            - name: StripPrefix
              args:
                parts: 1
            - name: AddRequestHeader
              args:
                name: X-Edge-Origin
                value: gateway
~~~

The example assumes two backends ready to handle `GET /products/42` on port 9091 and `GET /orders/42` on port 9092. Both routes perform **the same kind of check** and **the same kind of transformation** on matching requests.

| Request to Gateway port 8080 | Expected route | Backend path | Notes |
|---|---|---|---|
| `GET /api/products/42` | `products` | `/products/42` | Shortcut filters |
| `GET /api/orders/42` | `orders` | `/orders/42` | Expanded filters |
| `POST /api/products/42` | Does not match `products` | Not forwarded on this route | `Method=GET` does not match |
| `GET /api/unknown/42` | Matches neither route | Not forwarded on either route | `Path` does not match |

If no other route or handler exists, unmatched requests typically receive HTTP 404. If the target backend is not running, a route may **match while the downstream connection step fails**, usually producing a 5xx error; that is not a predicate syntax error.

### Flow Diagram from Configuration to Request

~~~mermaid
sequenceDiagram
    participant C as Config YAML
    participant R as RouteDefinitionRouteLocator
    participant P as Predicate/Filter factories
    participant G as Gateway request pipeline
    participant B as Backend
    C->>R: Provide route definition
    R->>P: Bind args and create predicates/filters
    P-->>R: Runtime objects
    R-->>G: Built Route
    G->>G: Select route matching Path and Method
    G->>G: Run StripPrefix, AddRequestHeader
    G->>B: Forward transformed request
    B-->>G: Response
~~~

This diagram focuses on building routes from **configuration data**. If a route is built with the Java DSL, it may take a different path to construct the `Route`, but requests are still processed through the corresponding pipeline.

## 7. Real Differences Between Shortcut and Fully Expanded Forms

| Criterion | Shortcut syntax | Expanded `name` + `args` |
|---|---|---|
| Length | Short, suits one or two simple parameters | Longer, more explicit |
| Parameter order | **Significant**, must follow factory | Primarily based on map key names |
| Commas in values | Easily conflicts with argument delimiter | Values sit in dedicated fields, safer to preserve |
| Regex or lists | Can be hard to read/escape | Easy to format regexes and lists |
| Code review | Fast for few parameters | Convenient to inspect each parameter |
| Optional parameters | Easy to forget order/defaults | Supported properties can be declared explicitly |
| When factory lacks shortcut | Cannot be used | Usually the appropriate choice |
| Request execution behavior | No inherent advantage for equivalent config | No inherent advantage for equivalent config |

**YAML length does not determine HTTP runtime performance.** Once a route is successfully created with the same predicate/filter/config, the Gateway executes the same kind of runtime handlers. Choose syntax based on clarity, parameter complexity, and maintainability.

### Practical Selection Guidelines

- Use **shortcut** for factories with short, obvious arguments such as `Path`, `Method`, `StripPrefix`, and simple cases of `AddRequestHeader`.
- Use **expanded** when there are multiple fields, values containing commas, regexes, lists, optional parameters, or when each parameter's meaning should be self-documenting.
- Use **expanded along with factory documentation** when configuring rate limiting, circuit breakers, retries, or external integrations; never guess `name`/`args` pairs from unrelated examples.
- Within a single application, you can use **both styles** across different routes or elements. Keep conventions consistent within each configuration group for easier reviews.

## 8. YAML Declaration Pitfalls

### 8.1. Mixing Up List and Map Structures

Correct — `predicates` is a list where each map item has `name` and `args`:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
  - name: Method
    args:
      methods:
        - GET
~~~

Wrong — placing `Method` at the same level as `args` inside **one map item** as though it were a Path argument:

~~~yaml
# WRONG: this structure does not express two separate predicates
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
    Method: GET
~~~

### 8.2. Wrong `args` Field Name

Wrong:

~~~yaml
# WRONG: StripPrefix usually expects the "parts" field, not "prefix"
filters:
  - name: StripPrefix
    args:
      prefix: 1
~~~

Correct:

~~~yaml
filters:
  - name: StripPrefix
    args:
      parts: 1
~~~

If an argument name is wrong, binding or validation can cause startup, refresh, or filter-creation errors depending on the factory and version. There is not always an obvious YAML syntax error because the YAML itself may still be completely valid.

### 8.3. Reversing Shortcut Argument Order

Unintended behavior:

~~~yaml
# Intended to add X-Edge-Origin: gateway, but the order is reversed
filters:
  - AddRequestHeader=gateway,X-Edge-Origin
~~~

For the `AddRequestHeader` factory, the first value is used as the **header name** and the second as the **header value**; the result no longer matches the original intent. The expanded form helps prevent this mistake:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

### 8.4. Values Containing Commas and Special Characters

Regexes with quantifiers like `{1,3}`, header values containing commas, or rewrite expressions with capture groups all require care in shortcut syntax. Prefer `name` and `args` to **separate parameter structure from value content**.

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Id
      regexp: '^[A-Z]{2,4}[0-9]{1,3}$'
~~~

With `RewritePath`, path transformations can involve regexes, capture groups, and replacement strings using `$` plus a group name. Follow the escaping rules of your exact Spring Cloud Gateway version so **Spring property placeholders** do not misinterpret the symbols. Do not just guess quotes or backslashes without testing actual requests to downstream.

YAML has other special characters such as `:`, `#`, `&`, `*`, and brackets. Whenever a value risks being parsed differently than intended, quote it appropriately. In a **single-quoted YAML string**, backslashes are normally kept literal; in a **double-quoted string**, backslashes participate in YAML's escape sequences.

### 8.5. Forgetting to Quote Strings That Look Like Booleans or Numbers

Some `args` values must be **character strings**, yet the YAML parser may interpret `true`, `false`, or numbers as non-string types. For example, `SetResponseHeader` with the literal text `true` should be quoted explicitly:

~~~yaml
filters:
  - name: SetResponseHeader
    args:
      name: X-Feature-Enabled
      value: 'true'
~~~

This is especially helpful during config reviews or when placeholders/environment overrides are involved. Fields that genuinely expect a Boolean or number should still receive the type supported by the factory.

### 8.6. Mistaking Multiple Predicates for OR

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
~~~

Here the Gateway selects the route only when **Path AND Method** both match. If you want one of several paths, declare multiple patterns inside **one `Path` predicate** using syntax supported by your version, such as the `patterns` list shown earlier; do not add two independent `Path` items and assume the Gateway applies OR.

### 8.7. Mixing WebFlux and Server MVC Configurations

You cannot conclude that a factory or `args` key works in Gateway Server MVC just because it shares a similar name in WebFlux. The two variants can differ in starters, namespaces, DSLs, and filter handling. For the examples in this lesson, verify that your project actually uses **Gateway Server WebFlux** and the matching version.

## 9. Expanded Syntax for Advanced Configuration

When moving to authentication, rate limiting, circuit breakers, and retries, many filters take additional fields and external integrations. The expanded style makes each condition clearly visible.

Example of a `Retry` filter for a **GET-only** route in a WebFlux version supporting this configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: reports
          uri: http://localhost:9093
          predicates:
            - Path=/api/reports/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                statuses:
                  - BAD_GATEWAY
~~~

The example assumes the downstream on port 9093 is running and suitable for idempotent GET retries. The filter can retry upon encountering the configured status, subject to the factory/version's rules. Do not interpret `retries: 2` as a system-wide cap on total HTTP requests; it describes the retry count configured on the filter within its execution scope. Backoff, exception, and status-code parameters must be verified against the documentation for the same version.

**Operational note:** retries can amplify load and latency. Never blindly retry transaction-creating `POST` requests or non-idempotent operations; review timeouts, circuit breakers, retry limits, and downstream idempotency policies.

For **RequestRateLimiter**, an expanded configuration typically requires rate-limiter parameters and may require a `KeyResolver` bean, Redis, or another backend. For **CircuitBreaker**, you may need a circuit breaker name, fallback, and the corresponding resilience library. Never assemble these factories from guessed shortcuts; always verify field names, dependencies, and versions.

## 10. When Service Discovery or Security Is Involved

The `name`/`args` syntax **only directly affects how predicates and GatewayFilters are declared**. Other parts of the route do not change merely because you chose shortcut or expanded syntax.

**Service discovery:** example route using `lb://order-service`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://order-service
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
          filters:
            - StripPrefix=1
~~~

`lb://order-service` belongs to the **route's `uri`**, not to `args` of `Path` or `StripPrefix`. To run in practice, discovery/load-balancer components must be configured and instances of `order-service` must be available. Using the expanded form does not enable discovery by itself.

**Authentication:** Spring Security can intercept requests at the web layer before the Gateway selects a route; GatewayFilters related to token relay or authorization also have their own scope and conditions. Converting `Path=/api/orders/**` to `name: Path` + `args` **does not alter the nature of security policies**.

**TLS and observability:** HTTPS listeners, HTTP client trust, Micrometer/tracing, or Actuator are configured on their respective components, not merely via shortcuts. Route ID, filters, and URI remain key pieces of information for tagging logs/metrics and verifying requests reach the right downstream.

## 11. How to Diagnose Differences Between Expanded and Shortcut Forms

If refactoring from shortcut to expanded causes a route not to match or to transform requests incorrectly, check in order:

1. **Which version is the project actually running?** Confirm Spring Boot, Spring Cloud BOM, the Gateway artifact, and WebFlux/MVC; read the matching documentation.
2. **Did YAML parse and bind properly?** Check indentation under `predicates`/`filters`, `-` list markers, and the `name` and `args` keys.
3. **Which factory was selected?** Are names like `Path`, `Header`, and `AddRequestHeader` accurate? A factory name is not an HTTP header name or route name.
4. **Which field names were used?** `patterns`, `methods`, `header`, `regexp`, `parts`, and `value` must match the factory's configuration; do not arbitrarily change singular/plural forms.
5. **Did values preserve their intended meaning?** Check regexes, commas, quotes, data types, placeholders, and positional argument order.
6. **Was the route built and reloaded?** Check startup/refresh logs and the active route list; a restart or supported refresh mechanism may be required.
7. **Which steps did the real request pass through?** Distinguish unmatched predicates, skipped filters, failed downstream connections, and responses modified by other filters.

In versions with appropriate Spring Boot Actuator/Gateway management endpoints, you can inspect loaded routes and refresh them per the official documentation. Management endpoints are not necessarily enabled by default; expose them only in controlled environments with proper access controls, and never publicly expose write/edit route permissions.

| Symptom | Primary suspect | Evidence to gather |
|---|---|---|
| YAML fails to load | Bad indentation, list/map mismatch, wrong config prefix | Binding logs or bound configuration properties |
| Data loads but route is not created | Factory not found, wrong `args` name/type | `RouteDefinition`/`Route` creation logs, validation errors |
| Route exists but returns 404 | Predicate does not match or route order | Actual method, path, host/headers |
| Downstream path is wrong | Non-equivalent `StripPrefix` or `RewritePath` | Request arriving at backend, filter order |
| Downstream header is wrong | `args.name`/`args.value` swapped, overwritten by another filter | Downstream header logs/echo |
| Old config still runs after refactoring | Route/cache not refreshed, wrong profile/instance | Active route list on the instance actually receiving traffic |
| 5xx status despite matched route | Backend/TLS/DNS/discovery or filter failure | Route state, routing logs, and downstream logs |

## 12. Hands-On Exercise to Self-Verify Both Notations

**Prerequisites:** a Gateway Server WebFlux supporting the configuration namespace in this lesson running at `http://localhost:8080`; a mock backend at `http://localhost:9090` capable of logging request path, method, and headers, returning HTTP 200 for `GET /orders/42`.

### Step 1 — Shortcut Configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Edge-Origin,gateway
~~~

Send requests:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42
~~~

Record: which route was selected, backend path/headers, and client HTTP status. The GET request is expected to reach the backend at `/orders/42` with header `X-Edge-Origin: gateway`. POST does not match this route's `Method=GET`.

### Step 2 — Switch to Expanded Form

Replace only `predicates` and `filters` with:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/orders/**
  - name: Method
    args:
      methods:
        - GET
filters:
  - name: StripPrefix
    args:
      parts: 1
  - name: AddRequestHeader
    args:
      name: X-Edge-Origin
      value: gateway
~~~

This snippet represents **fields inside one route**, not a standalone application YAML file. Keep `id`, `uri`, and the rest unchanged. Restart the application or use your version's route-reload procedure; confirm the new route is active, then re-run both `curl` commands.

### Step 3 — Compare Evidence

| Criterion | Shortcut | Expanded | Expectation |
|---|---|---|---|
| ID and URI | `orders`, `localhost:9090` | Same as shortcut | Unchanged |
| GET matches | Yes | Yes | Identical |
| POST matches this route | No | No | Identical |
| Backend path for GET | `/orders/42` | `/orders/42` | Identical |
| Backend header | `X-Edge-Origin: gateway` | Same name/value | Identical |
| Response status/body | Depends on backend | Depends on backend | No difference due to syntax |

If results differ, **do not immediately conclude that expanded syntax is slower or buggy**. Compare the loaded `RouteDefinition`/`Route`, bound parameters, and the request traversal through the chain to find the discrepancy.

### Step 4 — Intentional Fault Test

In a learning environment, replace `parts: 1` with `prefix: 1` or swap the two values in the `AddRequestHeader` shortcut. Observe the logs/route-loading behavior and what the backend receives; then restore the valid configuration. This test helps distinguish **syntactically valid YAML** from **semantically valid factory configuration**.

## 13. Checklist Before Promoting Routes to Microservices

- [ ] I have confirmed the exact version and variant: **Spring Cloud Gateway Server WebFlux** or **Server MVC**.
- [ ] I know `predicates` and `filters` are **lists** that can contain shortcut strings or `name`/`args` maps as supported by my version.
- [ ] I understand shortcut syntax relies on **positional values**, whereas expanded syntax relies on **field names**.
- [ ] I have verified exact `args` names such as `patterns`, `methods`, `parts`, `name`, and `value`.
- [ ] I choose expanded syntax whenever regexes, lists, commas, or complex configs could cause confusion.
- [ ] I distinguish **Add** from **Set**, and request headers from response headers.
- [ ] I know multiple predicates on the same route combine with AND, independently of route order and filter order.
- [ ] I have tested with real requests and observed downstream path/headers and client responses.
- [ ] I have verified the refresh/restart mechanism and inspected the active `Route` list after editing config.
- [ ] I do not confuse `lb://` URIs, authentication, TLS, or observability settings with predicate/filter arguments.
- [ ] I have reviewed security, rate limiting, and retry/circuit-breaker configurations against the exact factory and dependencies when those features are enabled.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — documentation for route configuration, route predicates, GatewayFilter factories, and fully expanded/shortcut examples; always select your exact version.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — project information, releases, and documentation links.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — how Spring Boot reads YAML/properties and property placeholders.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — the reactive HTTP processing foundation used by Gateway Server WebFlux.

**Remember:** `Path=/api/**` and `name: Path` with `args.patterns` can produce the exact same predicate; `StripPrefix=1` and `name: StripPrefix` with `args.parts: 1` can produce the exact same filter. Focus on **the factory name, the parameters actually bound, and runtime request behavior**, because those three factors determine whether a route works properly.
