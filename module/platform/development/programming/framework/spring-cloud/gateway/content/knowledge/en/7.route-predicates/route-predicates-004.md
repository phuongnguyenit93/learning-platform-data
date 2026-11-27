# Header: checking headers and regular expressions

## 1. What problem does the Header predicate solve?

In **Spring Cloud Gateway**, each route defines **when** an HTTP request is allowed to select that route and **where** to forward the request. The condition used to select a route is called a **route predicate**. Alongside conditions based on path (`Path`), method (`Method`), and hostname (`Host`), the **Header Route Predicate Factory** lets you choose a route based on the presence and value of an HTTP request header, typically checked with a **regular expression (regex)**.

For example, two clients both call `GET /api/catalog/products`, but a request with `X-Client-Channel: mobile` is routed to a mobile-dedicated backend, while other requests go to the default backend.

~~~mermaid
flowchart LR
    C[Client request] --> G[Spring Cloud Gateway]
    G --> P{Path /api/catalog/**?}
    P -->|No| N[Try another route]
    P -->|Yes| H{Does X-Client-Channel match mobile?}
    H -->|Yes| M[Mobile Catalog API]
    H -->|No| D[Try default route]
~~~

This is a **routing destination selection** mechanism, useful when organizing API versions, splitting traffic by client type, routing canary/experimental traffic, or isolating a group of requests per an HTTP contract. It **does not authenticate identity** and **does not replace authorization**: clients can set most request headers themselves if infrastructure does not control them.

After this lesson, you should be able to:

1. Explain how `Header` checks a header name and value using Java regex.
2. Write routes using both the shortcut and full syntax of Spring Cloud Gateway.
3. Distinguish **case-insensitive header names** from **header values governed by regex**.
4. Combine `Header` with `Path`, `Method`, and default routes using precedence order.
5. Verify matching/non-matching requests and avoid pitfalls with regex, YAML, proxy headers, and security boundaries.

## 2. Structure and meaning of the Header Route Predicate Factory

`Header` has two main arguments:

| Argument | Meaning | Example |
| --- | --- | --- |
| `header` | Name of the HTTP request header to check | `X-Client-Channel` |
| `regexp` | Regular expression used to match the header value | `^(mobile|tablet)$` |

Shortcut form in the `predicates` list:

~~~yaml
predicates:
  - Header=X-Client-Channel, ^(mobile|tablet)$
~~~

Expanded form, convenient when the regex is long or arguments need clear separation:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Channel
      regexp: '^(mobile|tablet)$'
~~~

In both configurations, a request carrying the `X-Client-Channel` header with value `mobile` or `tablet` satisfies the condition. A request missing the header or carrying an incompatible value causes the **predicate to return false**; Gateway continues evaluating other applicable routes, if any. The final HTTP outcome depends on other routes and error-handling configuration, **not always 404**.

**Position in the pipeline:** `Header` is a route selection condition evaluated by `RoutePredicateHandlerMapping`. Only after a route is selected does Gateway run that route's filter chain, such as `StripPrefix`, `AddRequestHeader`, rate limiter, or circuit breaker. Therefore, a filter belonging to the route itself **cannot add a header and cause that same route's predicate to retroactively match**.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant R as RoutePredicateHandlerMapping
    participant F as Gateway Filter Chain
    participant U as Upstream Service
    C->>R: GET /api/catalog/products (X-Client-Channel: mobile)
    R->>R: Path predicate = true
    R->>R: Header predicate = true
    R->>F: Selected route
    F->>F: Apply request/response filters
    F->>U: Forward HTTP request
    U-->>F: HTTP response
    F-->>C: HTTP response
~~~

## 3. Complete route example in Spring Cloud Gateway WebFlux

A **Spring Cloud Gateway Server WebFlux** application can declare:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-mobile
              uri: http://localhost:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - name: Header
                  args:
                    header: X-Client-Channel
                    regexp: '^(mobile|tablet)$'
              filters:
                - StripPrefix=2
~~~

Part-by-part explanation:

| Configuration | Effect |
| --- | --- |
| `id: catalog-mobile` | Stable route name for observability, logging, and management |
| `uri: http://localhost:9001` | Example mock HTTP backend address |
| `Path=/api/catalog/**` | Only considers requests under the `/api/catalog/` prefix |
| `Method=GET` | Applies only to GET requests |
| `Header=X-Client-Channel, ...` | Applies only when the header value satisfies the regex |
| `StripPrefix=2` | Removes the first two path segments before forwarding to the backend |

Given the request:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: localhost:8080
X-Client-Channel: mobile
~~~

The route is selected when **all three** conditions—`Path`, `Method`, and `Header`—are true. The backend receives the request at URL:

~~~text
GET http://localhost:9001/products/42
~~~

`StripPrefix=2` only affects the forwarded path; it **does not change how the Header predicate selected the route**. The address `localhost:9001` here is illustrative; a running backend is required for test calls to return a successful response.

**Version compatibility:** The `spring.cloud.gateway.server.webflux.routes` namespace applies to certain newer Spring Cloud Gateway Server WebFlux versions. In earlier lines, route properties usually took the form `spring.cloud.gateway.routes`. Use **the exact namespace for your version** along with the deployed Server WebFlux starter. **Server Web MVC** is a different variant requiring its own API and configuration reference.

## 4. How regular expressions validate header values

`Header` uses **Java regular expressions** to determine matching values. In the standard Spring Cloud Gateway implementation, matching uses **full-value match** semantics (similar to `String.matches(regexp)`), rather than merely finding a substring in the middle of the string.

Example:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Api-Version
      regexp: '^v[12]$'
~~~

| Value of X-Api-Version | Matches `^v[12]$`? | Reason |
| --- | --- | --- |
| `v1` | Yes | Starts with v followed by 1 |
| `v2` | Yes | Starts with v followed by 2 |
| `v3` | No | 3 is not in the set `[12]` |
| `V1` | No | Regex is case-sensitive by default |
| `v1-beta` | No | Does not match the entire value |
| ` v1` | No | Has a leading whitespace character |
| Header absent | No | No value to match against |

Key symbols:

| Regex symbol | Meaning | Example |
| --- | --- | --- |
| `^` and `$` | Start and end of string anchors | `^mobile$` |
| Alternation | Uses a vertical bar between choices | Accepts `mobile` or `web` |
| `[0-9]` | A single digit | `^[0-9]+$` |
| `+` | One or more times | `^[a-z]+$` |
| `*` | Zero or more times | `^v[0-9]*$` |
| `?` | Preceding element optional | `^v2(?:-beta)?$` |
| `{m,n}` | Repetition count from m to n | `^[a-z]{2,8}$` |
| `(?i)` | Case-insensitive mode | `(?i)^mobile$` |
| `[.]` | Literal dot; not a wildcard | `^v2[.]1$` |

In regex, the vertical bar (`|`) denotes alternation, for example `^(mobile|web)$`. **A standalone dot `.` in regex normally matches any character** (except certain line breaks depending on mode). To match a literal dot, use `[.]` or `\.`.

### Enabling case-insensitive flag only when truly needed

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Channel
      regexp: '(?i)^(mobile|tablet)$'
~~~

With `(?i)`, the values `mobile`, `MOBILE`, and `Mobile` can all match. **Do not enable this flag just to "match more easily"** if the header contract specifies lowercase values; flexibility should be intentional.

### Regex containing commas: prefer expanded syntax

The shortcut syntax separates the predicate name and arguments with commas, so patterns containing **commas**, such as `^[a-z]{2,5}$`, can cause ambiguity when parsing arguments.

~~~yaml
# Clear and avoids ambiguity when the regex contains commas:
predicates:
  - name: Header
    args:
      header: X-Region
      regexp: '^[a-z]{2,5}$'
~~~

The expanded syntax also avoids having to remember shortcut-specific escaping rules. If configuring dynamically via Java DSL, verify the final regex string the framework actually receives, as there is an additional Java string escaping layer.

## 5. YAML rules and regex escaping

A common mistake is assuming YAML strings, Java strings, and regex share the same escaping rules. They are separate layers:

1. **YAML** parses the property value from the configuration file.
2. **Gateway** extracts the `header` and `regexp` parameters and builds the predicate.
3. **Java regex** interprets the expression when matching the header value.

For patterns containing backslashes, wrap the regex in **YAML single quotes**:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Batch-Id
      regexp: '^\d{4}-[A-Z]{2}$'
~~~

This pattern accepts values like `2026-AB`. Inside YAML single quotes, `\` is preserved verbatim for Java regex to process. If you write `regexp: "^\d{4}-[A-Z]{2}$"` in YAML double quotes, `\d` may be rejected by YAML as an invalid escape sequence. You can use double quotes with properly escaped backslashes, though single quotes are usually easier to read.

Example using `[0-9]` to avoid escaping altogether:

~~~yaml
regexp: '^[0-9]{4}-[A-Z]{2}$'
~~~

**Do not evaluate regex by eye alone.** Build a table of valid/invalid values and test spaces, letter casing, empty values, commas, and unusually long inputs.

## 6. Header name, header value, and repeated headers

An HTTP header consists of a **name** and a **value**. They follow different rules:

**Header name:** HTTP field names are **case-insensitive**. Therefore, `X-Client-Channel`, `x-client-channel`, and `X-CLIENT-CHANNEL` refer to the same header field at the protocol level. Use consistent casing in documentation for maintainability.

**Header value:** There is no universal rule across all headers that values are case-insensitive. When the Header predicate uses regex, Java regex matches case-sensitively by default; you can enable `(?i)` if the contract permits.

**Whitespace:** Proxies/frameworks may normalize whitespace depending on context. Never assume a request header is forwarded byte-for-byte from client to application. For contracts you own, define canonical values and test specifically.

**Repeated headers:** HTTP allows representing multiple values in certain fields; forwarding, merging, or comma-splitting depends on header type and infrastructure. When an application receives multiple values, verify how Gateway evaluates each value and how upstream proxies may have merged them. Do not assume `X-Client-Channel: mobile,tablet` will be automatically split into two values `mobile` and `tablet` to match `^(mobile|tablet)$`.

To minimize ambiguity when designing headers for routing, prefer **a single unambiguous value** per contract, such as `X-Client-Channel: mobile`, and define behavior when a client sends multiple values against the contract.

### Some edge values

| Header in request | With regex `^mobile$` | Notes |
| --- | --- | --- |
| `X-Client-Channel: mobile` | Match | Exact string |
| `x-client-channel: mobile` | Match | Header name differs in case |
| `X-Client-Channel: MOBILE` | No | Value differs in case |
| `X-Client-Channel: mobile-beta` | No | Value has a suffix |
| `X-Client-Channel: mobile,tablet` | No if app receives one combined string | Do not assume list splitting |
| Header absent | No | Missing required condition |

If you need to route based on `Content-Type` or `Accept`, note that these headers have their own syntax with media types, parameters, multiple values, and quality weights. An overly simple regex may fail on valid values like `application/json; charset=utf-8` or multiple media types in `Accept`. Consider more suitable predicates/policies instead of reimplementing a protocol parser with regex.

## 7. Combining Header with other predicates

A route with multiple predicates typically requires **all predicates of the route to be true** (AND logic).

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: mobile-orders
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
                - Header=X-Client-Channel, ^mobile$
                - Header=X-Api-Version, ^v2$
              filters:
                - StripPrefix=1
~~~

The route condition is:

~~~text
Path matches /api/orders/**
AND Method = GET
AND X-Client-Channel matches ^mobile$
AND X-Api-Version matches ^v2$
~~~

Examples:

| Method/path | X-Client-Channel | X-Api-Version | Result for mobile-orders route |
| --- | --- | --- | --- |
| GET /api/orders/17 | mobile | v2 | Match |
| GET /api/orders/17 | web | v2 | No match |
| GET /api/orders/17 | mobile | v1 | No match |
| POST /api/orders/17 | mobile | v2 | No match |
| GET /api/catalog/17 | mobile | v2 | No match |
| GET /api/orders/17 | *absent* | v2 | No match |

Two `Header=` entries within the **same route** are two mandatory conditions. If you want **either mobile or web**, write a combined regex `^(mobile|web)$` or define two explicit routes if backends and filters differ.

### When should you use Header instead of another predicate?

| Condition | Suitable predicate | Example |
| --- | --- | --- |
| API path | `Path` | `/api/orders/**` |
| HTTP method | `Method` | `GET`, `POST` |
| Hostname | `Host` | `api.example.com` |
| Query parameter | `Query` | `?source=mobile` |
| HTTP request header | `Header` | `X-Client-Channel: mobile` |
| Cookie | `Cookie` | Cookie with name/value per contract |

Route names, predicates, and filters are not authorization mechanisms. For example, checking `X-Role: admin` with a Header predicate **does not prove** the sender is actually an administrator.

## 8. Choosing between a specialized route and a default route

A very common scenario: one client group has a dedicated backend, while remaining clients still need to reach the default API. Configure the **specific route first** and give the default route lower priority order.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-mobile
              order: -10
              uri: lb://catalog-mobile-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Client-Channel, ^mobile$
              filters:
                - StripPrefix=2

            - id: catalog-default
              order: 0
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
~~~

**Why `order`?** A mobile request also satisfies `Path` and `Method` of the default route. In Spring Cloud Gateway, a route with a **lower `order` value** typically takes precedence when multiple routes match. Setting `catalog-mobile` to `-10` and the default route to `0` ensures the specialized route is chosen first. **Route** order and **GatewayFilter** order are two separate mechanisms.

~~~mermaid
flowchart TD
    A[GET /api/catalog/products] --> B{Header X-Client-Channel = mobile?}
    B -->|Yes| C[Route catalog-mobile, order -10]
    B -->|No or missing| D[Route catalog-default, order 0]
    C --> E[Catalog mobile service]
    D --> F[Catalog service]
~~~

With `lb://`, Gateway requires Spring Cloud LoadBalancer configuration and an appropriate instance resolution source (service discovery or instance definitions). If discovery is not yet set up in a learning environment, substitute `http://localhost:9001` and `http://localhost:9002` with two test backends.

### Avoid relying on YAML declaration order

When multiple routes overlap, set **`order`** explicitly instead of hoping the route listed higher wins. In systems with dynamic routes or configurations merged from multiple sources, physical file order is not a reliably verifiable way to express priority.

If a route matches but the upstream returns 404 or 503, Gateway **does not automatically fall back to try a lower-priority route** like `catalog-default`; fallback to another backend must be designed explicitly based on business and reliability needs.

## 9. Testing with curl and scenario matrix

Suppose the gateway is running on `localhost:8080` and two backends are active per the previous configuration. Using the same path, vary only the header value:

~~~bash
# Mobile route:
curl -i -H 'X-Client-Channel: mobile' \
  http://localhost:8080/api/catalog/products/42

# Default route (no header):
curl -i http://localhost:8080/api/catalog/products/42

# Default route (non-matching value):
curl -i -H 'X-Client-Channel: web' \
  http://localhost:8080/api/catalog/products/42

# Default route because regex is case-sensitive:
curl -i -H 'X-Client-Channel: MOBILE' \
  http://localhost:8080/api/catalog/products/42

# Still matches mobile route even though header name is lowercase:
curl -i -H 'x-client-channel: mobile' \
  http://localhost:8080/api/catalog/products/42
~~~

**Expected route outcomes** for the `^mobile$` example:

| Request | Selected route | Reason |
| --- | --- | --- |
| GET, `X-Client-Channel: mobile` | `catalog-mobile` | Header matches and route has higher precedence |
| GET, no X-Client-Channel | `catalog-default` | Specialized Header predicate does not match |
| GET, `X-Client-Channel: web` | `catalog-default` | Does not match `^mobile$` |
| GET, `X-Client-Channel: MOBILE` | `catalog-default` | Value is case-sensitive |
| GET, `x-client-channel: mobile` | `catalog-mobile` | Header name is case-insensitive |
| POST /api/catalog/products/42 | Neither example route | Both routes require GET |

These commands are only for **testing the configuration** and were not executed in this lesson. Actual HTTP status codes depend on the backend, security, filters, and other routes. To prove which route was selected, return a distinct identifying response body/header from the **test backend** or inspect the route ID via Gateway telemetry; do not infer it solely from a `200` status.

### Dedicated edge-case checks

1. Send a header with an empty value, e.g., `X-Client-Channel:`, and determine expected behavior.
2. Test values with spaces, commas, uppercase letters, and very long strings.
3. Test two header lines with the same name if your client/proxy allows it, and observe what value the gateway actually receives.
4. Send requests through a real ingress/load balancer, not just connecting directly to the gateway on localhost.
5. Send a request that matches no route to distinguish **predicate mismatch** from **upstream error**.

## 10. Header predicate and security considerations

**A route predicate is not an authentication or authorization mechanism.** If a client chooses `X-Client-Channel: mobile`, the client can intentionally enter the mobile route. This is fine when the header simply selects a representation or equivalent backend, but it becomes a vulnerability if the mobile route grants broader access.

Example of an **unsafe** configuration:

~~~yaml
# Do not use a client-supplied header to prove a security role:
predicates:
  - Header=X-User-Role, ^admin$
~~~

Any client capable of sending `X-User-Role: admin` can satisfy that route condition unless a trusted layer has stripped/controlled the value. Even then, the business layer must still **verify permissions on the resource**. Never use route conditions to decide who can view orders, modify payment details, or access sensitive data.

Essential safeguards:

- **Authenticate tokens/sessions with proper mechanisms** (such as Spring Security) before allowing protected actions; fine-grained authorization remains enforced by the responsible service.
- **Identify trusted header sources.** If an internal header is added by an upstream ingress/gateway, that layer must strip external headers of the same name before inserting the verified value; network boundaries between layers must be protected.
- **Never trust self-asserted identity headers** such as `X-User-Id`, `X-User-Role`, or `X-Authenticated` sent by clients.
- **Limit header sizes** at the appropriate HTTP/proxy infrastructure layer; regex does not replace request size controls.
- **Never log sensitive data** such as `Authorization`, tokens, cookies, or personal data in logs, metrics, traces, or error messages.
- **Choose regexes with predictable performance.** Avoid overly complex expressions with nested quantifiers that can cause CPU-expensive backtracking when clients send adversarial strings.

### Common misconception about `AddRequestHeader`

~~~yaml
predicates:
  - Header=X-Trusted-Group, ^gold$
filters:
  - AddRequestHeader=X-Trusted-Group, gold
~~~

This configuration **does not make the route match a request initially missing `X-Trusted-Group`**. Predicates are evaluated to **select the route**, whereas `AddRequestHeader` is a filter **of the selected route** and runs only afterward. To route by trusted group, authenticate and tag at a layer **before route selection**, or use a dedicated predicate/authentication mechanism rather than relying on adding the header inside the route itself.

## 11. Observability, diagnostics, and common configuration mistakes

When requests do not enter the expected route, distinguish three cases: **Gateway found no matching route**, **Gateway selected a different route**, or **the right route was chosen but a filter/backend failed**.

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Header looks right, but route does not match | Regex requires full-string match, wrong casing, or whitespace | Inspect actual received value and test regex explicitly |
| Header name has different casing | Header names are case-insensitive; cause likely lies in value or proxy layer | Inspect the request received by Gateway |
| Mobile request enters default route | Default route has higher-priority order or mobile regex didn't match | Inspect `order`, predicates, and actual route ID |
| Header added in GatewayFilter, yet predicate stays false | Filters run after route selection | Check processing pipeline; move header-setting logic to the right layer |
| Regex is valid in Java, but app fails to load YAML | Double-quoted YAML escaping, shortcut commas, indentation, or wrong namespace | Prefer single quotes, expanded syntax, and inspect loaded configuration |
| Header has commas or multiple values, yet regex doesn't match | Value delivered by HTTP stack/proxy differs from assumption | Send test requests and inspect values at entry point |
| Route matched, but returns 404/503 | Wrong backend path, no instances, upstream error, or filter issue | Check URI, `StripPrefix`, discovery, and backend health |
| Regex is slow or consumes unusual CPU | Pattern risks catastrophic backtracking or very long header value | Simplify regex, cap header sizes, and benchmark with adversarial input |
| Client-sent header selects privileged route | Untrusted header treated as proof of privilege | Move authorization checks to Spring Security/business service |

**Useful observability data** includes route ID, method, public path, HTTP status, latency, request count per route, and filter states such as rate limit/circuit breaker. If Spring Boot Actuator and Gateway observability are enabled, you can use appropriate management endpoints to inspect loaded routes or metrics, depending on version; **restrict access to management endpoints**. Avoid using raw header values as metric labels because they can cause high cardinality and leak data.

Do not turn on full request header logging in production just to debug predicate errors. Log whether the right route was selected and **categorized/safe** values instead of logging tokens and personal information.

## 12. Real-world scenario: API routing by client version

Suppose a system has a reporting API whose response structure is changing between `v1` and `v2`. Clients send a contract header `X-Api-Version` to request a version:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: reports-v2
              order: -10
              uri: lb://reports-v2-service
              predicates:
                - Path=/api/reports/**
                - Header=X-Api-Version, ^v2$
              filters:
                - StripPrefix=2

            - id: reports-v1
              order: 0
              uri: lb://reports-v1-service
              predicates:
                - Path=/api/reports/**
              filters:
                - StripPrefix=2
~~~

A client calls:

~~~bash
curl -i -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports/summary
~~~

Gateway selects `reports-v2` if the request and configuration meet all conditions, then forwards `/summary` to the v2 backend. Missing the header or sending a header other than `v2` selects the default v1 route per the example.

**Design question:** If a client sends `X-Api-Version: v999`, should it silently downgrade to v1 or return an "unsupported version" error? The default route in the config above falls back to v1, but that is an **API contract decision**, not mandatory `Header` behavior. When version differences carry compatibility risks, define an explicit rejection policy rather than silently routing to another version.

Similarly, if using a header for canary routing, letting clients pick their own route can affect stability or safety. Canary cohorts should be assigned by a trusted mechanism, measured, and paired with a clear rollback path.

## 13. Practice exercise and verification criteria

**Context:** The `/api/products/**` API has a general backend and a dedicated backend for mobile clients. Routes apply only to GET requests. Mobile clients send the header `X-Client-Channel: mobile`.

### Part A — Configuration

1. Create route `products-mobile` with `Path`, `Method=GET`, and `Header=X-Client-Channel, ^mobile$`, priority `order: -10`.
2. Create route `products-default` needing only `Path` and `Method=GET`, with `order: 0`.
3. Specify two distinct backend URIs. If using `lb://`, set up LoadBalancer/discovery; if using static HTTP, ensure backends listen on the right ports.
4. Align the path received by the backend; only use `StripPrefix` if the path contract requires transformation.

### Part B — Matrix testing

| Request | Expected |
| --- | --- |
| GET, `X-Client-Channel: mobile` | Selects `products-mobile` |
| GET, header written `x-client-channel: mobile` | Selects `products-mobile` |
| GET, `X-Client-Channel: MOBILE` | Selects `products-default` |
| GET, no header | Selects `products-default` |
| GET, `X-Client-Channel: web` | Selects `products-default` |
| POST, `X-Client-Channel: mobile` | Matches neither GET route |
| GET, path outside `/api/products/**` | Matches neither example route |

### Part C — Extensions and analysis

1. Change the regex to `(?i)^mobile$` and predict the route for `MOBILE`.
2. Add the condition `X-Api-Version: v2` to the mobile route; explain why both headers must match.
3. Try a regex with quantifiers like `^[a-z]{2,5}$` using expanded syntax and verify YAML loads cleanly.
4. Add test cases with an empty header, a header containing commas, or an overly long value, and define expected behavior.
5. Simulate one backend returning 503: verify Gateway **does not automatically fall back to the default route** just because the specialized route's backend failed.
6. Answer for yourself: If a client sends `X-User-Role: admin`, why must it not be used as proof to grant permissions?

**Passing criteria:** You can prove which route was actually selected via logs/telemetry or a test backend; distinguish header names from header values; and accurately explain AND logic, regex behavior, route ordering, and the difference between route predicates and security. A single HTTP 200 response is not enough to conclude the configuration is correct.

## 14. Key takeaways

- **Header Route Predicate Factory** in Spring Cloud Gateway matches **request headers** by name and Java regex. Requests missing the header normally fail that condition.
- **Header names are case-insensitive**; **values are normally matched case-sensitively** unless the regex specifies otherwise. Keep **full-value matching** semantics in mind.
- Use **YAML single quotes** for regexes containing backslashes and consider **`name: Header` / `args`** syntax when patterns are complex or contain commas.
- Within a route, predicates like `Path`, `Method`, and `Header` combine with **AND**. For specialized and default routes, set `order` explicitly and verify which route gets selected.
- **GatewayFilters run after route selection**; adding a header inside a route's filter will not re-evaluate that route's own Header predicate.
- **Client-sent headers can be spoofed.** Header-based routing does not replace authentication, authorization, trusted-header controls, resource limits, or observability.
