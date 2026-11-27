# RewriteRequestParameter and Query Parameter Replacement Rules in Spring Cloud Gateway

In **SPRING_CLOUD_GATEWAY**, clients frequently pass data in the URL, such as `GET /api/products?campaign=summer&sort=price`. The Gateway may need to normalize a query parameter before forwarding the request to a microservice: replacing `campaign=summer` with an approved campaign code, aligning the parameter with a newer backend API, or collapsing duplicate values. **`RewriteRequestParameter`** is the GatewayFilter Factory designed for **replacing the value of an already-present query parameter**.

An easily overlooked nuance is that this filter **does not add the parameter when the name is absent**, and when a name appears multiple times, it **replaces all values with a single replacement value**. This lesson belongs to the **HTTP Body Handling** chapter and focuses on those exact rules, configuration syntax, interaction with route predicates and other filters, URL encoding, downstream verification, and security/operational risks.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux 4.x** with the `spring.cloud.gateway.routes` configuration namespace. Newer lines such as Gateway Server WebFlux 5.x may use `spring.cloud.gateway.server.webflux.routes`; Gateway Server MVC has a different configuration variant. Always verify your actual Gateway version, Spring Cloud release train, and web stack. URLs, hostnames, and campaign names in this lesson are illustrative examples, not ready-made production configurations.

## 1. Where Do Query Parameters Live in an HTTP Request?

Consider this request:

~~~http
GET /api/products/42?campaign=summer&sort=price HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Its parts can be separated as follows:

| Component | Example Value | Role |
|---|---|---|
| HTTP method | `GET` | Indicates the action requested by the client |
| Path | `/api/products/42` | Path segment handled by route predicates and path filters |
| Query string | `campaign=summer&sort=price` | Name/value pairs following the `?` |
| Query parameter | `campaign` → `summer` | A named parameter and its value |
| Request header | `Accept: application/json` | Request metadata |
| Request body | None in this example | Payload separate from URL/query; may be JSON, form data, or raw bytes |

**A query parameter is not an HTTP body.** Although covered in the broader “HTTP Body Handling” topic, `RewriteRequestParameter` only alters the **query string in the request URI sent downstream**; it does not modify JSON bodies, form bodies, request headers, or paths. To transform a body, use a mechanism such as `ModifyRequestBody` for your version; to rewrite paths, check `RewritePath`/`StripPrefix`; to alter headers, use header filters.

A query string can contain **multiple values for the same name**:

~~~text
/api/products?campaign=summer&campaign=winter&sort=price
~~~

At the WebFlux layer, `ServerHttpRequest.getQueryParams()` represents this using a multi-value structure, conceptually:

~~~text
campaign -> [summer, winter]
sort     -> [price]
~~~

Therefore, saying “replace a query parameter” requires clarifying: replace one value or replace the **entire list**? `RewriteRequestParameter` applies the second rule.

## 2. The Contract of `RewriteRequestParameter`

The filter accepts **two parameters**:

- `name`: the query parameter name to match, such as `campaign`.
- `replacement`: the new value to substitute, such as `fall2027`.

Shortcut syntax:

~~~text
RewriteRequestParameter=<name>,<replacement>
~~~

With this configuration:

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
~~~

the expected behavior is:

| Input Query String | Forwarded Logical Query String | Explanation |
|---|---|---|
| `?campaign=summer` | `?campaign=fall2027` | Replaces the value of the existing parameter |
| `?campaign=summer&sort=price` | `?campaign=fall2027&sort=price` | Preserves other parameters |
| `?campaign=summer&campaign=winter` | `?campaign=fall2027` | **Multiple values with the same name collapse to one** |
| `?sort=price` | `?sort=price` | **No `campaign` → nothing added** |
| No `?` at all | Still no `campaign` | Does not synthesize a query string |
| `?campaign=` | `?campaign=fall2027` | Name exists with an empty value; can be replaced |
| `?Campaign=summer` | `?Campaign=summer` | Different casing; does not match `campaign` |

**This table shows logical query parameter semantics**; it does not guarantee that parameter ordering, percent-encoding case, or `+` vs. `%20` on the wire are preserved byte-for-byte. The framework may rebuild the URI with appropriate encoding.

Key properties:

1. **Applies only to requests that match the route owning the filter.** It is not a blanket transformation across every request entering the gateway.
2. **Replaces all values for a single parameter name.** If the name appears multiple times, the result for that name is a single new value.
3. **Does not create a missing parameter.** If you need to add one when absent, use another approach such as `AddRequestParameter` with controlled conditions.
4. **Does not use regex for partial string replacement.** `replacement` is a replacement value, not an arbitrary pattern search-and-replace expression.
5. **Does not alter HTTP method, path, headers, or body.** Other request parts are handled by their respective filters.

### Comparison with Similarly Named Filters

| Factory | When Name Already Exists | When Name Is Absent | Scope |
|---|---|---|---|
| `RewriteRequestParameter` | Replaces all values for the name with **one** value | Leaves unchanged; does not add | Request query |
| `AddRequestParameter` | Appends a new value, potentially creating multiple values | Adds the new parameter | Request query |
| `RemoveRequestParameter` | Removes the parameter by name from query | Nothing to remove | Request query |
| `RewritePath` | Transforms the **path** via rules/regex | Not a query operation | Request path |
| `SetRequestHeader` | Overwrites header value by name | Creates header by name | Request header |
| `ModifyRequestBody` | Transforms payload via body mechanism | Depends on handler/body filter | Request body |

**Do not swap `RewriteRequestParameter` with `AddRequestParameter` just because both take two strings.** The former performs **conditional replacement**, while the latter performs **addition**.

## 3. Complete Route Configuration Example

Suppose the Gateway listens on port `8080`, and a catalog backend listens on `9090` serving `GET /products/42`. Clients call `/api/products/42` with any campaign; the Gateway should ensure the backend always receives `campaign=fall2027` whenever the client passed `campaign`.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-campaign
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - RewriteRequestParameter=campaign,fall2027
~~~

Explanation:

1. `Path=/api/products/**` matches the request **path**; `Method=GET` restricts the HTTP method.
2. Only when all predicates match does the Gateway select `catalog-campaign` and run the route's filters.
3. `StripPrefix=1` removes the `api` segment from the path, turning `/api/products/42` into `/products/42`.
4. `RewriteRequestParameter` inspects the **query**. If `campaign` is present, it replaces all its values with `fall2027`.
5. The routing filter sends the modified request to `http://localhost:9090`; in Docker or Kubernetes environments, `localhost` must be replaced with the actual downstream address reachable from the Gateway process.

Example flow:

~~~mermaid
flowchart LR
    C["GET /api/products/42?campaign=summer&sort=price"] --> P["Path + Method match"]
    P --> F1["StripPrefix=1"]
    F1 --> F2["RewriteRequestParameter campaign → fall2027"]
    F2 --> D["Backend: /products/42?campaign=fall2027&sort=price"]
    D --> R["Response back to client"]
~~~

**Important observation:** The URI the client used to call the Gateway **does not change on the client**. The filter creates a forwarded request with an adjusted URI for downstream. When the backend responds, the Gateway returns the response along the chain; this filter does not change the query displayed in a browser address bar via a redirect.

### Expanded Syntax: `name` and `args`

You can also configure it as follows:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-campaign
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: RewriteRequestParameter
              args:
                name: campaign
                replacement: fall2027
~~~

The two occurrences of `name` here have **different meanings**:

- `filters[1].name`: selects the **factory** named `RewriteRequestParameter`.
- `filters[1].args.name`: the **query parameter** name to replace, i.e., `campaign`.
- `filters[1].args.replacement`: the new value, i.e., `fall2027`.

Do not change `args.replacement` to `args.value` out of habit from `AddRequestParameter`; each factory defines its own field names and contract.

### Shortcut vs. Expanded Form?

| Situation | Recommendation |
|---|---|
| Short name and value, no commas | Shortcut is easy to read: `RewriteRequestParameter=campaign,fall2027` |
| Clear parameter visibility needed for code review | Expanded: `name` + `args.name` + `args.replacement` |
| Replacement contains commas or YAML-sensitive characters | Expanded with proper string quoting |
| Project has many filters with complex arguments | Prefer expanded to avoid argument-order and field mistakes |
| Upgrading release train | Check **version-specific documentation**; do not mix syntax across versions |

## 4. Rules for Duplicate, Missing, and Empty Parameters

### 4.1. Multiple Values with the Same Name

Request:

~~~http
GET /api/products/42?campaign=summer&campaign=winter&sort=price HTTP/1.1
Host: gateway.example.test
~~~

The Gateway applies `RewriteRequestParameter=campaign,fall2027`. The backend is expected to receive **one** value `fall2027` for `campaign`, while `sort=price` is logically preserved.

~~~text
Before filter:
  campaign -> ["summer", "winter"]
  sort     -> ["price"]

After filter:
  campaign -> ["fall2027"]
  sort     -> ["price"]
~~~

This prevents situations where a backend reads the **first value** while another middleware reads the **last value** of a repeated parameter. However, this is **not an authentication or sanitization measure**: other parameters or other routes can still cause ambiguity if left uncontrolled.

### 4.2. Missing Parameter Name

Request:

~~~http
GET /api/products/42?sort=price HTTP/1.1
Host: gateway.example.test
~~~

Because `campaign` **does not exist**, the filter does not inject `campaign=fall2027`. If the backend requires this parameter, **configuring `RewriteRequestParameter` alone is not enough**.

Different design options:

- **Require the client to provide it:** use a `Query` route predicate or backend validation; return an explicit error when missing.
- **Always add a value:** use `AddRequestParameter` per policy while accounting for duplicate-name behavior.
- **Add only when missing:** requires explicit conditional logic (such as a custom filter or backend handling); do not assume `RewriteRequestParameter` does this automatically.

### 4.3. Present Name with an Empty Value

For `?campaign=` or `?campaign`, distinguish between **name present** and **name absent**. At the framework's query-parsing layer, cases where the name appears with an empty value still represent the parameter being present; `RewriteRequestParameter` will replace that value.

Include both `?campaign=` and `?campaign` in integration tests because query parsing/encoding across proxies and frameworks can differ, especially with non-standard clients.

### 4.4. Query Parameter Names Are Case-Sensitive

In query strings, `campaign` and `Campaign` are normally treated as **two distinct names**. Do not apply HTTP header rules (case-insensitive header names) to query parameters.

~~~text
Input:    ?campaign=summer&Campaign=winter
Filter:   RewriteRequestParameter=campaign,fall2027
Expected: campaign=fall2027, Campaign=winter
~~~

If your API needs case normalization for parameter names, define a public convention and normalize in the backend or a dedicated filter; do not assume this factory lowercases the entire query string.

## 5. Relationship Between `Query` Route Predicate and `RewriteRequestParameter`

A **`Query` Route Predicate** inspects request parameters **while the Gateway is selecting a route**. `RewriteRequestParameter` is a **GatewayFilter that runs after the route is selected**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as RoutePredicateHandlerMapping
    participant F as GatewayFilterChain
    participant B as Backend
    C->>M: GET /products?campaign=summer
    M->>M: Check Path / Query / Method on original request
    alt Route matches
        M->>F: Hand off selected route
        F->>F: RewriteRequestParameter campaign = fall2027
        F->>B: GET /products?campaign=fall2027
        B-->>C: Response via Gateway
    else Route does not match
        M-->>C: Try other routes or handlers
    end
~~~

Example:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: selected-by-query
          uri: http://localhost:9090
          predicates:
            - Path=/products/**
            - Query=campaign,summer
          filters:
            - RewriteRequestParameter=campaign,fall2027
~~~

- Request `GET /products/42?campaign=summer`: the `Query` predicate **matches the original value**; the route is selected and the filter replaces the value sent to the backend.
- Request `GET /products/42?campaign=fall2027`: does not match the `summer` expression on this route's predicate, even though `fall2027` is the value the filter would produce if selected.
- Request without `campaign`: the predicate does not match; this route's filter does not run.

**Conclusion:** Never design a route whose predicate requires a query value produced by that same route's filter unless the predicate already matches the original request. The logical order is **route matching → GatewayFilter → routing**, never the reverse.

## 6. Combining `AddRequestParameter` and `RemoveRequestParameter`

### Add First, Rewrite Second

~~~yaml
filters:
  - AddRequestParameter=campaign,from-gateway
  - RewriteRequestParameter=campaign,fall2027
~~~

In a standard chain executing request transformations in this order:

- If the client **did not send `campaign`**, `AddRequestParameter` adds `campaign=from-gateway`, and `RewriteRequestParameter` turns it into `campaign=fall2027`.
- If the client sent `campaign=summer`, Add produces `[summer, from-gateway]`, and Rewrite collapses it to `[fall2027]`.

Thus, **Add then Rewrite** creates an “always have one final value” effect. Still, **verify actual filter order**, especially when default filters, global filters, or custom `Ordered` filters are present.

### Rewrite First, Add Second

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
  - AddRequestParameter=campaign,from-gateway
~~~

If the inbound request has `campaign`, Rewrite sets `fall2027`, and then Add appends `from-gateway`. The backend may receive **two values**, defeating the single-value effect of `RewriteRequestParameter` alone.

If the inbound request **lacks `campaign`**, Rewrite does nothing, and Add creates `campaign=from-gateway`. These two filter orders are therefore **not equivalent**.

### Remove Before or After Rewrite

~~~yaml
filters:
  - RemoveRequestParameter=campaign
  - RewriteRequestParameter=campaign,fall2027
~~~

After Remove, `campaign` is gone, so Rewrite **has nothing to replace**. Reversing the order:

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
  - RemoveRequestParameter=campaign
~~~

means the newly replaced value is ultimately deleted as well. Putting both on the same route only makes sense when you fully understand the logic and filter ordering.

| Order on a Simple Route | Input `?campaign=old` | Logical Result |
|---|---|---|
| Rewrite only | `old` | `fall2027` |
| Add then Rewrite | `old` | `fall2027` |
| Rewrite then Add | `old` | `fall2027` and `from-gateway` |
| Remove then Rewrite | `old` | No `campaign` |
| Rewrite then Remove | `old` | No `campaign` |

**Do not confuse `Route.order` with filter order.** `Route.order` controls priority among candidate routes during matching; filter order governs execution sequence within a selected route's chain. `GlobalFilter`s and internal filters also participate, so verify the actual downstream request when configurations grow complex.

## 7. URL Encoding and Special Characters

Query parameters in an HTTP URI may contain spaces, `&`, `=`, `#`, Unicode characters, and characters needing percent-encoding. For instance, the logical value `blue & green` cannot be appended directly to a URL with a raw `&` because `&` delimits parameters.

**Prefer expanded syntax** when values are hard to read in shortcut syntax:

~~~yaml
filters:
  - name: RewriteRequestParameter
    args:
      name: label
      replacement: 'blue & green'
~~~

At runtime, the value must be encoded into a valid URI via Spring Framework's URI encoding/building mechanics for your Gateway version. **Do not assume** whether the wire output will be `blue%20%26%20green` or `blue+%26+green`: space encoding and query parsing depend on the HTTP layer and framework. Inspect both the **decoded value at downstream** and the **raw query** if your API contract cares about exact bytes.

Points to keep in mind:

- `&` separates query pairs; `=` separates names and values by common convention. When they appear inside data, they must be properly encoded.
- `#` starts a client-side URI fragment; fragments are normally **never sent in HTTP requests to servers**. Do not expect the Gateway to treat fragments as query parameters.
- `+` may be interpreted as a space under form-URL-encoding rules in some components; do not assume identical semantics across every backend.
- Unicode characters are encoded via UTF-8 and percent-encoding in URIs as needed; test end-to-end with Vietnamese/non-ASCII characters.
- Never build queries by string concatenation like `oldUri + "&campaign=" + userInput`. If writing a custom filter, use proper URI builder APIs, preserve existing parameters, and encode safely.

### Commas in Shortcut Syntax

Shortcut syntax uses a comma to separate `name` and `replacement`. If the replacement contains a comma, such as `east,west`, use the expanded form:

~~~yaml
filters:
  - name: RewriteRequestParameter
    args:
      name: region
      replacement: 'east,west'
~~~

This specifies **a single string value `east,west`**. Never write `RewriteRequestParameter=region,east,west` and assume the factory splits three tokens the way you intend.

### Signed Queries (Signed URLs)

Some systems compute HMAC signatures or presigned URLs over the **query string** or a canonicalized URI representation. Even when replacing `campaign` is technically valid, it can **break the signature** if that parameter is part of the signed input. For signed URLs:

1. Identify which component verifies the signature: Gateway, backend, or storage service.
2. Never alter the query after signing if doing so violates the signing contract.
3. If normalization is needed, perform it before signing or redesign the signing/authorization sequence in a verified order.
4. Test raw query strings, encoding, and duplicate parameter names in security integration tests.

## 8. Interaction with Headers, Body, and Response

`RewriteRequestParameter` edits the **request URI** without changing JSON body content. For example, a client sends:

~~~http
POST /api/orders?campaign=summer HTTP/1.1
Host: gateway.example.test
Content-Type: application/json

{"campaign":"summer","quantity":2}
~~~

If the route permits `POST` and applies `RewriteRequestParameter=campaign,fall2027`, the backend may receive URI `/api/orders?campaign=fall2027` (or a path rewritten by another filter), while the body still holds `"campaign":"summer"` unless another body filter intervenes.

**Never rely on duplicate fields across query and body and assume they stay consistent.** The backend must define the authoritative source: query, body, or token claims. If the API contract requires them to match, enforce explicit validation or redesign the request.

Similarly:

- `AddRequestHeader` and `SetRequestHeader` modify **request headers**, leaving query parameters untouched.
- `RewritePath` and `StripPrefix` modify the **path**, leaving `campaign` in the query unchanged.
- `RemoveResponseHeader`, `SetResponseHeader`, and `SetStatus` affect the **response**, not the query forwarded to the backend.
- `ModifyRequestBody` transforms payloads, involving buffering/serialization, which is completely separate from `RewriteRequestParameter`.

This helps isolate failures: if the backend receives the right path but wrong `campaign`, inspect query filters; if it receives the right query but wrong body, inspect body handling/contracts; if the response status is wrong, check downstream, error handling, retries, circuit breakers, and response filters.

## 9. Security and Operational Impact

Rewriting a query parameter looks simple, yet it interacts with other layers:

| Topic | Potential Impact | How to Control |
|---|---|---|
| **Authentication/authorization** | Query changed after auth or diverges from token claims | Never use query rewriting for authorization; backend must validate claims/permissions |
| **Rate limiting** | Distinct client values collapse into one downstream value; limiters at other layers may see different keys | Pick a reliable `KeyResolver` and verify where the limiter runs in the chain |
| **Cache/CDN** | Cache keys may include raw URI/query; client and backend see different names/values | Normalize queries before caching and align cache-key strategy |
| **Circuit breaker/retry** | Each retry uses the rewritten request; multiple attempts amplify backend load | Retry only appropriate operations with clear timeouts/backoff/idempotency |
| **Service discovery** | Query stays on forwarded URI while `lb://`/load balancer picks instance | Ensure URI and service instance resolution are right; never confuse query with service ID |
| **TLS and URL signing** | Query may be signed data, whereas TLS only encrypts transport | Maintain TLS on both hops and verify signatures relative to rewrites |
| **Observability** | Gateway logs may record original URI while backend logs rewritten URI | Attach route ID/correlation ID and record rewrites without leaking sensitive values |
| **Personal data** | Queries frequently land in access logs, browser history, analytics, and proxies | Keep tokens and PII out of URLs; redact sensitive queries in all logs |

### Do Not Use Rewriting to “Sanitize” Input

Replacing `campaign=anything` with `fall2027` does not make the rest of the request safe. Clients can still send extra unhandled parameters, oversized values, tricky Unicode, or malicious payloads in headers and bodies. The backend must still validate all inputs against the API contract, enforce request size limits, and verify access control.

If you run **multiple Gateway instances**, confirm all nodes loaded the same route/filter configuration; if one node is stale, the backend may observe two different `campaign` shapes depending on which instance the load balancer picks.

## 10. Hands-On Lab: Verifying the Query at Downstream

### Preparing the Echo Backend

Assume a backend at `http://localhost:9090` exposes `GET /products/42` returning JSON or logging received query parameters. With Spring WebFlux, an illustrative controller in a **separate backend application** could be:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProductEchoController {

    @GetMapping("/products/{id}")
    public Mono<Map<String, Object>> echo(@PathVariable String id,
                                           ServerHttpRequest request) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("productId", id);
        data.put("rawQuery", request.getURI().getRawQuery());
        data.put("queryParams", request.getQueryParams());
        return Mono.just(data);
    }
}
~~~

This controller is meant for a **WebFlux demo backend** with its own starter/web server, not code to drop into the Gateway if your architecture keeps the Gateway purely for routing. In production, avoid echoing sensitive query parameters.

### Test Gateway Configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: rewrite-query-demo
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - RewriteRequestParameter=campaign,fall2027
~~~

Assume the Gateway runs at `http://localhost:8080`. Ensure the configuration is loaded via restart or your version's route-refresh mechanism. Then run:

~~~bash
# 1. Initial value present
curl -i "http://localhost:8080/api/products/42?campaign=summer&sort=price"

# 2. Two values with the same name
curl -i "http://localhost:8080/api/products/42?campaign=summer&campaign=winter"

# 3. Missing campaign parameter
curl -i "http://localhost:8080/api/products/42?sort=price"

# 4. Empty value
curl -i "http://localhost:8080/api/products/42?campaign="

# 5. Different casing in name
curl -i "http://localhost:8080/api/products/42?Campaign=summer"
~~~

Expected `queryParams` received by the backend:

| Test | `campaign` Value at Backend | Notes |
|---|---|---|
| 1 | `[fall2027]` | `sort=price` remains intact |
| 2 | `[fall2027]` | Both values collapsed into one |
| 3 | No `campaign` key | Not added |
| 4 | `[fall2027]` | Name was present despite empty value |
| 5 | No `campaign` key; `Campaign=[summer]` | Query names are case-sensitive |

If actual output differs, call the backend **directly** to verify how the controller parses queries; inspect the actual URI arriving downstream, active routes, filter order, Gateway logs, and any intermediary proxies. Do not blame the filter solely from a `404` or `5xx`: `404` may be a missed route, and `5xx` may be an unreachable backend.

### Comparing with `AddRequestParameter`

Temporarily swap only that filter line to:

~~~yaml
filters:
  - StripPrefix=1
  - AddRequestParameter=campaign,fall2027
~~~

Re-run tests 2 and 3:

- Test 2: you will see **both the old values and the new value**, instead of only `fall2027`.
- Test 3: the backend sees `campaign=fall2027` even though the client never sent that parameter.

Restore `RewriteRequestParameter` after testing if policy requires replacing only **existing** parameters.

### Testing Non-Matching Path/Method

~~~bash
curl -i -X POST "http://localhost:8080/api/products/42?campaign=summer"
curl -i "http://localhost:8080/other/products/42?campaign=summer"
~~~

Neither request satisfies the example route's predicates. Assuming no other matching route/handler exists, neither is forwarded by `rewrite-query-demo`; `RewriteRequestParameter` not executing here is architecturally correct.

## 11. Common Pitfalls

| Symptom / Misconception | Explanation | Resolution |
|---|---|---|
| `RewriteRequestParameter` does not add a missing key | This is by design, not a bug | Use `AddRequestParameter`, validation, or explicit conditional logic |
| Client sends `campaign=old&campaign=new`, backend sees one new value | Factory replaces **all values of that name** with one value | Do not use Rewrite in this way if multi-value history must be kept |
| Does not replace capitalized `Campaign` | Query parameter names are case-sensitive | Standardize API contract or add dedicated normalization logic |
| YAML parses cleanly, yet filter does not run | Route did not match, wrong version/namespace, typo in factory name, or routes not refreshed | Check `RouteDefinition`, runtime version, route ID, and logs |
| Wrote `args.value` in expanded config | Rewrite uses field name `replacement` | Change to `args.replacement` |
| Query gets `+` or `%20` differently than before | URL encoding/normalization or proxies may alter raw representation | Compare decoded values and raw query against contract |
| Backend URL signature verification fails | Query was modified after signing | Redesign signing/validation order; never mutate signed URLs blindly |
| Backend still sees old JSON body | Factory only alters query string, not body | Use appropriate body transformation/validation |
| `Query` predicate misses even though filter sets that value | Route matching happens **before** `GatewayFilter` execution | Match predicates against the original request or use another route |
| Two Gateway nodes produce different results | Config drift, stale route cache, or version mismatch | Verify rollout and route refresh across every instance |
| `429`/`401`/`403` requests never hit rewrite filter | Blocked by security or rate limiter before rewrite or route matching | Inspect actual filter order and scope |
| Response body changes even though query is correct | Downstream acts on the new parameter via business logic | Verify backend contract, caches/fallbacks, and response status |

## 12. Implementation Checklist

- [ ] I understand that the query string belongs to the **request URI**, distinct from path, headers, and body.
- [ ] I understand `RewriteRequestParameter(name, replacement)` only replaces a **present parameter**.
- [ ] I know multiple values sharing the same name are collapsed into **one** value.
- [ ] I do not expect the filter to create a parameter when the name is absent.
- [ ] I have distinguished it from `AddRequestParameter`, `RemoveRequestParameter`, `RewritePath`, and `ModifyRequestBody`.
- [ ] I use valid shortcut syntax or `name` + `args.name` + `args.replacement`.
- [ ] I tested empty values, duplicate names, case variations, and values requiring URL encoding.
- [ ] I know route predicates evaluate **before** the rewrite filter executes.
- [ ] I verified filter order when combining Add/Remove/default/global filters.
- [ ] I tested against an echo backend and checked both **raw query** and **decoded query params**.
- [ ] I reviewed impacts on signed queries, cache keys, auth, rate limiting, retries/circuit breakers, TLS, and service discovery if applicable.
- [ ] I keep tokens and personal data out of queries and logs, and still enforce validation at the backend.
- [ ] I verified the Gateway/WebFlux/MVC version and route-refresh mechanism for my deployment environment.

## Official References

- [RewriteRequestParameter GatewayFilter Factory — Spring Cloud Gateway Server WebFlux 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriterequestparameter-factory.html) — documents `name`, `replacement`, and multi-value replacement rules.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — choose your exact version and flavor; also see `AddRequestParameter`, `RemoveRequestParameter`, and route predicates.
- [Spring Framework — ServerHttpRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html) — URI and query parameters on WebFlux requests.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html) — handling URIs, queries, and encoding when writing custom filters.
- [RFC 3986: Uniform Resource Identifier](https://www.rfc-editor.org/rfc/rfc3986) — URI syntax and percent-encoding.

**Key Takeaway:** `RewriteRequestParameter=campaign,fall2027` **replaces only when `campaign` is present**, **collapses all `campaign` values into one new value**, and **never adds `campaign` if missing**. Test single-value, multi-value, empty, missing, and signed-URL cases; that is the reliable way for the Gateway to normalize queries without breaking contracts between clients and microservices.
