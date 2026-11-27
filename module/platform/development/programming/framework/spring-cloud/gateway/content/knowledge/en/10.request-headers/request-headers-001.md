# AddRequestHeader and SetRequestHeader: Adding or Replacing Values in Spring Cloud Gateway

In **SPRING_CLOUD_GATEWAY**, an API Gateway does not only select a backend using route predicates; it can also modify the HTTP request before forwarding it. Two of the most easily confused **GatewayFilter Factories** are `AddRequestHeader` and `SetRequestHeader`: both affect **headers on the request sent downstream to a service**, but they differ in how they handle existing values.

This lesson belongs to the **Request Headers** chapter and explains exactly when to add, when to replace, shortcut/expanded YAML syntax, multi-value header semantics, the impact of filter order, and how to verify behavior from downstream. These decisions relate directly to correlation ID propagation, route identification, service discovery, authentication, rate limiting, circuit breaking, retries, TLS, and request observability across a microservices system.

> **Scope:** Examples use the common syntax of **Spring Cloud Gateway Server WebFlux 4.x** with `spring.cloud.gateway.routes`. Starter names, configuration namespaces, and APIs may differ in newer release lines or in **Gateway Server MVC**. Check your actual Spring Boot, Spring Cloud, and Gateway variant versions before applying.

## 1. Quick Comparison: Add vs. Set

Suppose a client sends the following to the Gateway:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
X-Edge-Source: mobile-client
~~~

A route with the filter `AddRequestHeader=X-Edge-Source,edge-gateway` will append the value `edge-gateway` to the header named `X-Edge-Source`. If the route uses `SetRequestHeader=X-Edge-Source,edge-gateway`, the Gateway replaces that header's value set with the new value.

| State before filter | `AddRequestHeader=X-Edge-Source,edge-gateway` | `SetRequestHeader=X-Edge-Source,edge-gateway` |
|---|---|---|
| Header does not exist yet | Has one value: `edge-gateway` | Has one value: `edge-gateway` |
| Header has `mobile-client` | Has two values: `mobile-client` and `edge-gateway` | Only `edge-gateway` remains |
| Header has `a` and `b` | Keeps `a`, `b`, and adds `edge-gateway` | Replaces all values with `edge-gateway` |
| Header name uses different casing | Still targets the same header name | Still targets the same header name |

**Add = append a value to the existing list. Set = replace the entire list of values for that header name.** Both are purely filter configuration actions; neither validates header contents on its own nor creates a security policy.

At the Spring WebFlux API layer, you can think of the effect as similar to these two operations on `HttpHeaders`:

~~~java
headers.add("X-Edge-Source", "edge-gateway"); // Add value
headers.set("X-Edge-Source", "edge-gateway"); // Replace existing values
~~~

This is a **behavioral illustration**, not the verbatim source code of the two factories. The actual request object in WebFlux is modeled as immutable; the filters create/mutate an appropriate request to pass the modified headers down the processing chain.

## 2. At Which Stage Are Headers Modified?

When a request arrives at Gateway Server WebFlux, the system typically executes the following steps:

1. The HTTP/WebFlux component receives the request and may apply `WebFilter` instances or Spring Security.
2. The Gateway evaluates route predicates such as `Path`, `Method`, `Host`, and `Header` to select a route.
3. `FilteringWebHandler` executes the chain of `GlobalFilter` and `GatewayFilter` instances corresponding to the selected route.
4. `AddRequestHeader` or `SetRequestHeader` produces a forwarded request carrying the new header.
5. The routing filter sends the request downstream via a static URI or a mechanism such as `lb://` with an appropriate load balancer/service discovery setup.
6. The downstream response travels back through the processing chain and is returned to the client.

~~~mermaid
flowchart TD
    C["Client sends request + headers"] --> S["WebFlux / Spring Security"]
    S --> P{"Route predicates match?"}
    P -->|No| N["GatewayFilters for this route do not run"]
    P -->|Yes| G["Gateway filter chain"]
    G --> A{"Header filter"}
    A -->|AddRequestHeader| AD["Keep old values + add new value"]
    A -->|SetRequestHeader| ST["Replace all values for the header name"]
    AD --> R["Route to downstream"]
    ST --> R
    R --> D["Backend receives transformed request"]
    D --> B["Response returns to Gateway and client"]
~~~

**Common pitfall:** The `Header` **route predicate** inspects the incoming request's headers when the Gateway is selecting a route. By contrast, `AddRequestHeader`/`SetRequestHeader` are **filters that run after route selection**. If you add a header using a GatewayFilter on the same route, that new header **cannot make the route's own Header predicate retroactively match**.

For example, a route requiring `Header=X-Client-Tier,premium` will not be selected for a request missing `X-Client-Tier`, even if `SetRequestHeader=X-Client-Tier,premium` is configured underneath that route.

## 3. Shortcut Syntax in YAML

For the `orders` route, to **add** the header `X-Edge-Source: edge-gateway` before calling the backend:

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
            - AddRequestHeader=X-Edge-Source,edge-gateway
~~~

If you want to **overwrite all values** of the same header, simply change the factory name:

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
            - SetRequestHeader=X-Edge-Source,edge-gateway
~~~

Each example is an **alternative configuration**. For the request `GET /api/orders/42`, `StripPrefix=1` removes the `api` segment, so downstream receives the path `/orders/42` assuming no other components modify the path.

In shortcut syntax, the pattern is:

~~~text
AddRequestHeader=<header-name>,<header-value>
SetRequestHeader=<header-name>,<header-value>
~~~

The **first value is the header name**, and the **second value is the header content**. Swapping the two positions will cause the Gateway to mistakenly use the value as the header name.

Do not confuse the comma separating the two shortcut arguments with an HTTP header **whose value contains a comma**. When the content is complex, prefer the expanded syntax shown in the next section.

## 4. Expanded Syntax with `name` and `args`

Use the expanded form when you need clear readability of the name and value, especially during code reviews:

**Adding a value:**

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
            - name: AddRequestHeader
              args:
                name: X-Edge-Source
                value: edge-gateway
~~~

**Replacing a value:**

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
            - name: SetRequestHeader
              args:
                name: X-Edge-Source
                value: edge-gateway
~~~

Here there are **two different meanings of the key `name`**:

- `filters[0].name` is the factory name: `AddRequestHeader` or `SetRequestHeader`.
- `filters[0].args.name` is the HTTP header name: `X-Edge-Source`.
- `filters[0].args.value` is the HTTP header value: `edge-gateway`.

Both shortcut and expanded forms are converted into the corresponding filter configuration when the Gateway creates the route. With the same factory and arguments, they aim for the exact same request-processing behavior.

| Goal | Shortcut | Expanded (`filters` containing map items) |
|---|---|---|
| Add a value | `AddRequestHeader=X-Edge-Source,edge-gateway` | `name: AddRequestHeader`, `args.name: X-Edge-Source`, `args.value: edge-gateway` |
| Replace all values | `SetRequestHeader=X-Edge-Source,edge-gateway` | `name: SetRequestHeader`, `args.name: X-Edge-Source`, `args.value: edge-gateway` |

## 5. An HTTP Header Can Have Multiple Values

An important point is that **a header name does not necessarily have only one value**. In Spring, `HttpHeaders` uses a `MultiValueMap<String, String>` model; a single header name can map to a **list of multiple strings**.

For example, suppose a request from the client contains two lines with the same header name:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
X-Feature-Flag: alpha
X-Feature-Flag: beta
~~~

Conceptual result:

~~~text
Initially:
  X-Feature-Flag -> ["alpha", "beta"]

After AddRequestHeader=X-Feature-Flag,gamma:
  X-Feature-Flag -> ["alpha", "beta", "gamma"]

After SetRequestHeader=X-Feature-Flag,gamma:
  X-Feature-Flag -> ["gamma"]
~~~

**Do not use the number of header lines seen on the wire as your sole proof.** HTTP clients, proxies, or servers may represent certain multi-value headers across multiple lines or combine values onto a single line, depending on the semantics of each header and the HTTP version. Verify the **list of values received by the backend**, rather than only checking how a tool prints them.

A comma inside a single string such as `X-Feature-Flag: alpha,beta` **does not automatically equate** to two separate values `alpha` and `beta` in `HttpHeaders`. For headers with list syntax, the backend may split them according to the applicable HTTP rules. Some headers, especially `Set-Cookie` on the response side, have special rules; do not mechanically apply comma-joining to all header names.

### Header Names Are Case-Insensitive

In HTTP, `X-Edge-Source`, `x-edge-source`, and `X-EDGE-SOURCE` semantically refer to the exact same header name. Therefore, `SetRequestHeader` must be understood as replacing the values of the **header by name**, not creating a new header just because the letter casing differs.

Pick a consistent casing style for documentation and logs, but never rely on uppercase/lowercase differences for authorization or trust checks.

## 6. Add Then Set, or Set Then Add: Filter Order Changes the Outcome

When multiple filters touch the **same header name**, execution order determines the final state:

~~~yaml
filters:
  - AddRequestHeader=X-Flow,first
  - SetRequestHeader=X-Flow,final
~~~

In a simple route, if both filters execute their request modification in this order, the final state will be **`X-Flow: final`**: `SetRequestHeader` discards the earlier values.

Reversing the order:

~~~yaml
filters:
  - SetRequestHeader=X-Flow,final
  - AddRequestHeader=X-Flow,extra
~~~

The expected final result is **two values** `final` and `extra` in the request reaching downstream.

~~~mermaid
flowchart LR
    I["Initial request: X-Flow=client"] --> A["Add first"]
    A --> S["Set final"]
    S --> O["Downstream: [final]"]
    I --> S2["Set final"]
    S2 --> A2["Add extra"]
    A2 --> O2["Downstream: [final, extra]"]
~~~

This example uses **GatewayFilters on the same route**, executing in their listed order. In real systems, `default-filters`, `GlobalFilter` instances, filters with explicit `Ordered` values, and other outbound HTTP components may act before or after. When debugging, inspect the **actual request received downstream** rather than inferring behavior solely from YAML line order.

### Combining with RemoveRequestHeader

If you want to set a single uniform value, `SetRequestHeader` is usually sufficient because it replaces all values for the corresponding header name:

~~~yaml
filters:
  - SetRequestHeader=X-Edge-Source,edge-gateway
~~~

Some teams use `RemoveRequestHeader` first to express a policy of stripping untrusted incoming headers:

~~~yaml
filters:
  - RemoveRequestHeader=X-Internal-User
  # Only re-attach identity via trusted logic if business requirements truly demand it.
~~~

You should not add `X-Internal-User` from a static string and treat the request as authenticated. Identity propagation must come from a trusted security context, combined with network policies that prevent clients from accessing the backend directly.

## 7. When to Use Add vs. Set?

| Scenario | Usually appropriate choice | Reason |
|---|---|---|
| Appending a diagnostic label to a multi-value header collaboratively built by trusted proxies | `AddRequestHeader` after confirming header semantics | Preserves existing values |
| Setting a trusted route name or edge service name without accepting forged values from the client | `SetRequestHeader` | Overwrites client-supplied values |
| Standardizing a gateway-managed header | `SetRequestHeader` | Avoids conflicting multiple values |
| Adding a tag alongside existing tags | `AddRequestHeader` if downstream genuinely supports multiple values | Preserves list semantics |
| Removing an entire sensitive header that should not be forwarded downstream | `RemoveRequestHeader` | Neither adding nor replacing |
| Passing authenticated user identity to downstream | Security-integrated filter or trusted custom filter | Value must come from authentication results, not a YAML constant |
| Forwarding an OAuth2 access token according to policy | Appropriate mechanism such as Token Relay, Spring Security | `Add`/`Set` cannot replace OAuth2 token handling |
| Setting a dynamic correlation ID per request | Tracing integration or custom filter that checks/generates IDs | A static configuration string does not generate unique IDs |
| Modifying a response header returned to the client | `AddResponseHeader` or `SetResponseHeader` | The two factories covered here only affect requests |

**Selection rule:** if a header is owned by the Gateway and downstream must receive **exactly one value**, `SetRequestHeader` is the clearer choice. Only consider `AddRequestHeader` when the header semantically supports **multiple independent values** and existing values must be preserved.

## 8. Passing Values Extracted from Route URI Variables

In Gateway Server WebFlux lines that support URI variable expansion, `AddRequestHeader` and `SetRequestHeader` can reference variables extracted by a route predicate.

For example, matching `Host` by subdomain:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: tenant-catalog
          uri: http://localhost:9091
          predicates:
            - Host={tenant}.example.test
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Route-Tenant,{tenant}
~~~

Suppose the Gateway receives a request with Host `shop-a.example.test` and path `/api/catalog/42`. When the `Host` and `Path` predicates match, `{tenant}` can be replaced with `shop-a`, and the backend receives `X-Route-Tenant: shop-a` provided the route/filter/version supports it as described.

Equivalent example using `AddRequestHeader`:

~~~yaml
filters:
  - AddRequestHeader=X-Route-Tenant,{tenant}
~~~

The difference remains that **add keeps the original value** if the client already supplied `X-Route-Tenant`, whereas **set replaces it**. For internal tenant-routing headers, you usually want to **overwrite client-supplied values** and trust only the predicate result verified at the proxy layer.

**Trust boundary warning:** `Host` and forwarded headers can still be spoofed depending on your network, proxy, and TLS setup. A `tenant` extracted from the URL **does not prove** the user belongs to that tenant. The backend must verify the tenant against authenticated identity/claims and access permissions; only read `X-Route-Tenant` as auxiliary routing or logging metadata when an explicit trust contract exists.

Do not treat `{tenant}` as a general template syntax capable of extracting anything from a request. It only expands when a corresponding variable is provided by a predicate or a mechanism supported by your Gateway version.

## 9. Shortcut Limitations with Comma-Containing Values

Shortcut syntax typically splits the factory name and its arguments positionally using `=` and commas. For example:

~~~yaml
filters:
  - AddRequestHeader=X-Region,ap-southeast
~~~

If you need a **string value containing a comma**, such as `east,west`, the expanded form expresses your intent clearly:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Regions
      value: 'east,west'
~~~

Here `east,west` is **a single string value**. If you want two independent values, and downstream supports multi-value headers, you can apply two filters to add each value:

~~~yaml
filters:
  - AddRequestHeader=X-Regions,east
  - AddRequestHeader=X-Regions,west
~~~

The intended result is that `X-Regions` carries two values `east` and `west` in the downstream request. If another proxy or filter modifies the same header, verify the actual behavior.

**Do not write the shortcut `AddRequestHeader=X-Regions,east,west` assuming the Gateway will interpret it as two values to add.** This factory's shortcut syntax specifies a header name and a single value argument; argument counts, escaping, and handling of extra arguments depend on implementation and version details.

### Special Characters in YAML

When a value contains `:`, `#`, `{`, commas, leading/trailing spaces, or characters that the parser could interpret as another type, use appropriate quotes. For instance, a literal string value `true` should be quoted explicitly:

~~~yaml
filters:
  - name: SetRequestHeader
    args:
      name: X-Feature-Enabled
      value: 'true'
~~~

In the expanded declaration, `args.value` is the header value rather than the factory name. If you use Spring Boot configuration placeholders, account for values changing across profiles/environments and verify against the actual runtime version.

## 10. `default-filters` Configuration and Scope of Application

When multiple routes need the same header, some Gateway Server WebFlux lines support `default-filters` to apply default filters across routes created by the corresponding configuration mechanism:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - SetRequestHeader=X-Edge-Environment,staging
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
        - id: catalog
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
~~~

In the `staging` environment, these routes are expected to send `X-Edge-Environment: staging` downstream when the default filter is applied. For production, set the value according to the actual environment configuration and **never accidentally hardcode staging**.

Distinguish clearly between:

- **Per-route filter:** participates only when that specific route is selected.
- **Default filter:** attached to routes via the mechanism supported by your Gateway version.
- **GlobalFilter:** shared logic at the Gateway chain layer, not an item under `filters` declared directly inside each route.
- **WebFilter/Spring Security:** may run before route matching, with a different scope from `GatewayFilter`.

When both a default filter and a route filter modify the same header name, verify the **final execution order**. Do not assume a "per-route" filter always runs after every default filter, or that a "global" filter always runs first; check the filter order and trace the actual request received downstream.

## 11. Hands-On Exercise: Observing Values at the Backend

To accurately distinguish Add from Set, measure the **request headers at downstream**, rather than looking only at the `curl` command sent to the Gateway.

### Setup

Assume:

- Gateway Server WebFlux is listening at `http://localhost:8080`.
- An echo backend is running at `http://localhost:9090`, exposing a `GET /echo` endpoint that returns the **received header values** as JSON or in logs.
- Any additional security, retry, or proxy filters are accounted for so the output is clear. Ideally run this in an isolated test environment.

Declare two routes as follows:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: demo-add
          uri: http://localhost:9090
          predicates:
            - Path=/demo/add/**
          filters:
            - StripPrefix=2
            - AddRequestHeader=X-Workshop,from-gateway

        - id: demo-set
          uri: http://localhost:9090
          predicates:
            - Path=/demo/set/**
          filters:
            - StripPrefix=2
            - SetRequestHeader=X-Workshop,from-gateway
~~~

`StripPrefix=2` removes `demo` and `add` or `set`, turning both `/demo/add/echo` and `/demo/set/echo` into `/echo` before calling the backend.

### Step 1 — Send a Header from the Client

~~~bash
curl -i -H "X-Workshop: from-client" http://localhost:8080/demo/add/echo
curl -i -H "X-Workshop: from-client" http://localhost:8080/demo/set/echo
~~~

On Windows PowerShell, if `curl` is aliased to a different cmdlet rather than the standard CLI tool, use `curl.exe`.

Inspect the echo output or logs from the backend:

| Route | Header sent by client | Values the backend should see |
|---|---|---|
| `demo-add` | `from-client` | `from-client` **and** `from-gateway` |
| `demo-set` | `from-client` | Only `from-gateway` |

If the backend returns JSON formatted as an array or a comma-joined string, check the echo application's contract before drawing conclusions. The goal is to verify the **values**, not a particular HTTP display format.

### Step 2 — Omit the Header on the Client

~~~bash
curl -i http://localhost:8080/demo/add/echo
curl -i http://localhost:8080/demo/set/echo
~~~

With no initial `X-Workshop` header, both approaches should produce the same result: **`from-gateway`**. From this test, it becomes clear that the difference between Add and Set only appears when **the header already has a value before the filter runs**.

### Step 3 — Test Multiple Input Values

~~~bash
curl -i -H "X-Workshop: alpha" -H "X-Workshop: beta" http://localhost:8080/demo/add/echo
curl -i -H "X-Workshop: alpha" -H "X-Workshop: beta" http://localhost:8080/demo/set/echo
~~~

With Add, the backend is expected to see `alpha`, `beta`, `from-gateway`. With Set, the backend is expected to see **only** `from-gateway`. Make sure the HTTP client, proxies, and echo app actually preserve/display multi-value headers so the test is meaningful.

### Step 4 — Reverse Filter Order and Predict

In a separate test route, add:

~~~yaml
filters:
  - SetRequestHeader=X-Workshop,first
  - AddRequestHeader=X-Workshop,second
~~~

Predict that the backend receives both `first` and `second`. Swap the order to Add then Set and check which values remain at the backend. This is a practical way to learn filter order, especially useful before introducing default/global filters.

### Step 5 — Test an Unmatched Route

~~~bash
curl -i -H "X-Workshop: from-client" http://localhost:8080/unknown/path
~~~

If no other route or handler exists, the Gateway may return HTTP 404. Do not expect `AddRequestHeader` or `SetRequestHeader` from `demo-add`/`demo-set` to run on that request.

### Recording Results

| Check | Passing indicator | Likely failure category if not passing |
|---|---|---|
| Add route receives request | Backend sees both client and Gateway values | Predicate, factory configuration, filter order |
| Set route receives request | Backend sees only the Gateway value | Confused Add/Set, overwritten by a later filter |
| Request without input header | Both routes add the Gateway value | Wrong route or header name |
| Request with multiple values | Add keeps then appends; Set replaces all | Proxy/echo merged headers, misconfiguration |
| Path after StripPrefix | Backend receives `/echo` | Route/path filter |
| Unmatched route | Not forwarded to backend via the two test routes | Different predicate/handler |

## 12. Security and Trust Boundaries of Request Headers

Headers carrying client-submitted data are **not trustworthy by default**. Certain header names require explicit policy handling:

| Header / header group | Risk of uncontrolled Add/Set | Recommended approach |
|---|---|---|
| `Authorization` | Overwriting real tokens, appending multiple tokens, or forwarding wrong credentials | Use proper authentication, authorization, and Token Relay mechanisms; never hardcode tokens in YAML |
| `Cookie` | Mixing sessions/cookies or leaking unnecessary data | Forward cookies only intentionally, preserving domain boundaries and session policies |
| `X-Forwarded-For`, `Forwarded` | Client spoofs IP address or proxy chain | Configure trusted proxies and forwarded-header handling appropriate for your version |
| `Host` | Wrong virtual host, invalid signatures, or misrouting | Use `PreserveHostHeader` or host-routing mechanisms appropriately when truly needed |
| `X-Internal-User`, `X-User-Role` | Client claims arbitrary identity or roles | Strip untrusted values and re-attach only from a valid security context |
| Correlation ID / trace headers | Broken trace correlation or allowing spoofed IDs | Use standard propagation/tracing and validate/sanitize incoming values |
| `Content-Length`, `Transfer-Encoding` | Broken request framing, proxy errors, or request smuggling risks | Let the HTTP server/client and dedicated filters manage them; never modify manually with generic Add/Set |
| Hop-by-hop headers such as `Connection` | Broken semantics across proxies and potential connection failures | Rely on standard Gateway/HTTP-stack header filtering; do not forward arbitrarily |

Do not use `SetRequestHeader` with a constant such as `X-Authenticated: true` as a substitute for permission checks. **Authentication** must come from Spring Security or an authoritative component. **Rate limiting** needs its own policy and a trusted key; if a rate limiter reads a client-controlled header, an attacker can rotate its value to bypass limits.

With `lb://order-service`, header filters still modify the **request sent to the selected instance**, while the `lb://` URI also requires working service discovery and load balancing. `CircuitBreaker`/`Retry` may trigger multiple request attempts downstream; immutable headers like `X-Edge-Source` can be reused across attempts, whereas correlation IDs or idempotency state require policy-driven management. TLS on both legs (client → Gateway and Gateway → downstream) is also configured separately; adding headers does not replace TLS.

## 13. Troubleshooting Common Issues

| Symptom | What to check first | Resolution |
|---|---|---|
| Backend does not receive the new header | Did the route match? Is the filter bound? Does it match WebFlux/MVC and your version? | Check route definitions, logs, and backend requests |
| Header unexpectedly appears with two values | `AddRequestHeader` was used when the incoming header already existed | Use `SetRequestHeader` if downstream expects a single value |
| Only the Gateway value remains, but client value should be kept | `SetRequestHeader` was used | Switch to `AddRequestHeader` when a valid multi-value contract exists |
| Header is overwritten even though the route looks right | A default filter, GlobalFilter, or another proxy modifies the same name | Trace filter order and each HTTP hop |
| Used `AddRequestHeader=X-A,a,b` but backend receives wrong result | Comma in shortcut was parsed as argument separator | Use expanded `name`/`args.value` |
| `{tenant}` is not substituted | Predicate did not extract the variable, wrong placeholder, or version mismatch | Verify `Host`/`Path` predicates and URI variable support |
| Header does not appear in the client response | Using a **RequestHeader** filter instead of a **ResponseHeader** filter | Check the header downstream or switch to a response filter |
| Client sends header with different casing and Set behaves unexpectedly | Multiple filters/proxies are acting, not case-sensitive HTTP names | Inspect the full pipeline and actual value list |
| 401/403 response before routing and route filter did not run | Spring Security rejected the request before route selection | Inspect security `WebFilter`s; do not expect route filters to run |
| Header changes after deployment, but only for some requests | Gateway instances are running different configs or versions | Check each instance, reload/cache/rollout state, and metrics |

When inspecting headers carrying tokens, sessions, IPs, or personal data, **never log full values**. Prefer logging header names, value counts, synthetic test values, or properly handled hashes paired with controlled correlation IDs.

## 14. Production Readiness Checklist

- [ ] I understand the difference between **`AddRequestHeader` appending** and **`SetRequestHeader` replacing all values**.
- [ ] I know these headers are modified in the **request sent downstream**, not in the response returned to the client.
- [ ] I confirmed the route matches and do not expect route filters to act before route predicates.
- [ ] I declared the correct factory name and `name`/`value` arguments, or shortcut parameters in the proper order.
- [ ] I understand a header can hold multiple values and header names are case-insensitive.
- [ ] I know when to preserve multiple values and when to enforce **a single final value**.
- [ ] I verified filter order, default filters, and other components that could modify the same header.
- [ ] I use the expanded syntax when values contain commas or special YAML characters.
- [ ] I only reference URI variables when a predicate actually provides the corresponding variable.
- [ ] I tested with a downstream echo backend or header logs, covering missing, single, and multiple client values.
- [ ] I avoid directly modifying hop-by-hop headers, framing headers, and credentials with static filters.
- [ ] I do not use client-controlled headers as proof of authentication, authorization, or a trusted rate-limit key.
- [ ] I verified Gateway version compatibility, service discovery, retry/circuit breaker behavior, and TLS paths when those features are enabled.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up **AddRequestHeader GatewayFilter Factory**, **SetRequestHeader GatewayFilter Factory**, **RemoveRequestHeader**, and **Global Filters** for your **exact Gateway version**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — project versions and documentation links.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — multi-value header model and `add`/`set` operations.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, request mutation, and HTTP pipeline.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — general rules for HTTP field names, values, and semantics.

**Key takeaway:** `AddRequestHeader` **appends a value** and may leave multiple values for the same header name; `SetRequestHeader` **overwrites all values** so downstream receives the value set by the Gateway. Choosing the right one depends on your backend's HTTP contract, filter ordering, and trust boundaries for client-supplied data.
