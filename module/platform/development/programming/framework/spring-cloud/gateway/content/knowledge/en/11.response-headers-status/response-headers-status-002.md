# RemoveResponseHeader and Removing Implementation Details in Spring Cloud Gateway

An API Gateway may unintentionally return HTTP response headers that reveal the framework name, reverse proxy, runtime, service version, or internal infrastructure topology. For example, downstream returns `X-Powered-By: Express` or `X-Backend-Version: catalog-2027.06`; even though the client only needs the JSON result, those headers can still pass through the Gateway to the Internet.

In **Spring Cloud Gateway**, `RemoveResponseHeader` is a **GatewayFilter Factory** used to **remove a header name and all of its values from the HTTP response** on the routes where the filter is applied. This lesson belongs to the **Headers and Status** chapter, guiding how to configure it properly, distinguish request/response headers, determine removal scope, handle interactions between the filter chain and response commit, test across proxy layers, and avoid accidentally deleting headers important for HTTP, authentication, caching, CORS, or TLS.

> **Example scope:** The configuration snippets below target **Spring Cloud Gateway Server WebFlux**, using the `spring.cloud.gateway.routes` syntax common in some Gateway 4.x lines. Gateway Server MVC and newer release lines may use different namespaces, starters, or APIs; before applying, check the actual Gateway version and Spring Cloud release train.

## 1. Why can response headers leak implementation details?

An HTTP response consists of a **status line**, **headers**, and (if present) a **body**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Server: catalog-api/2.8
X-Powered-By: ExampleFramework
X-Backend-Version: 2.8.7
X-Request-Id: 72bcf824

{"id":42,"name":"Notebook"}
~~~

In this hypothetical example, `Content-Type` is needed by the client to read JSON, and `X-Request-Id` can be helpful for reporting errors. Conversely, `Server`, `X-Powered-By`, or `X-Backend-Version` can disclose implementation details that the API contract does not need to expose.

**Removing implementation details is a measure to reduce information disclosure surface**, not a comprehensive security solution. Even when headers are removed, clients can still infer technologies from protocol behavior, error messages, or response characteristics. Therefore, you must still patch vulnerabilities, update dependencies, configure TLS, enforce authentication/authorization, and monitor the system.

### Header groups to evaluate

| Header | Data that may be exposed | Action to consider |
|---|---|---|
| `Server` | Server name, software, or version if declared | Remove/reduce detail when policy does not require disclosure; check both Gateway server and external proxies |
| `X-Powered-By` | Downstream framework/runtime | Usually safe to remove if not part of the API contract |
| `X-Backend-Version`, `X-App-Version` | Backend deployment version, build ID | Prefer keeping in internal observability systems if needed, do not expose automatically |
| `X-Backend-Host`, `X-Node-Name` | Hostname or internal topology | Do not expose unless there is a business need |
| `X-Generator` | Content generation tool or framework | Evaluate customer need before exposing |
| `Via`, `X-Cache`, `X-Envoy-Upstream-Service-Time` | Part of the proxy/cache path | Evaluate against standards, proxy requirements, debugging, and infrastructure contracts; **do not remove arbitrarily** |
| `X-Request-Id`, `traceparent` | Request correlation/tracing ID | Can be useful for operational support; consider format and potential data leakage |
| `X-RateLimit-*`, `RateLimit-*` | Rate-limiting policy or metrics | May be part of the API contract; decide according to public policy |

**The list above provides examples to evaluate**, not a list of headers that must all be removed. The usefulness and retention requirements of each header depend on the environment, HTTP standards, proxy/CDN, and the API contract.

## 2. What does `RemoveResponseHeader` do exactly?

The filter takes **one HTTP header name** to remove from the response. If that header appears with multiple values, removing by name eliminates the **entire list of values** for that name, rather than just one specific value.

~~~text
Response from backend:
  X-Powered-By -> ["Framework-A", "Plugin-B"]
  Content-Type -> ["application/json"]

After RemoveResponseHeader=X-Powered-By:
  X-Powered-By -> (no longer present)
  Content-Type -> ["application/json"]
~~~

Characteristics to remember:

- HTTP header names are **case-insensitive**: `Server`, `server`, and `SERVER` refer to the same name semantically.
- The filter **removes** the specified header; it does not rename it, mask part of its value, or replace it with an empty string by default.
- The filter operates on the **response returned to the client**, not the request sent to downstream.
- The filter **does not change the HTTP status** or body. `200`, `404`, `503` remain the status according to the current pipeline, unless another component modifies it.
- One `RemoveResponseHeader` filter is configured for **one header name**; to remove multiple different names, declare multiple filter entries.
- If the header does not exist, removing by name does not create a new header or alter the remaining headers.

Comparison with related factories:

| Factory | HTTP part affected | Effect |
|---|---|---|
| `RemoveRequestHeader` | Gateway → backend request | Removes header before forwarding |
| `RemoveResponseHeader` | Backend/Gateway → client response, within the applicable route scope | Removes all values of the header name |
| `SetResponseHeader` | Response | Sets/replaces the value of the header name |
| `AddResponseHeader` | Response | Appends a value, potentially creating multiple values |
| `DedupeResponseHeader` | Response | Reduces duplicate values according to a strategy supported by the factory |
| `SetStatus` | Response status | Modifies the status code according to its own configuration, **different from** removing a header |

## 3. Short-syntax configuration

Assume the catalog service is running at `http://localhost:9090`; the Gateway receives `/api/catalog/**` requests, strips the `api` segment, and forwards to catalog.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - RemoveResponseHeader=X-Powered-By
            - RemoveResponseHeader=X-Backend-Version
~~~

General syntax:

~~~text
- RemoveResponseHeader=<header-name>
~~~

For example, the backend returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Powered-By: CatalogFramework
X-Backend-Version: 2.8.7
X-Request-Id: 72bcf824
~~~

After the request matches the route and the filter runs successfully **before response commit**, the client is expected to receive:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: 72bcf824
~~~

This is an **illustrative header section**, not the entire actual response. Gateway, Netty, a reverse proxy, or a CDN may add other headers; the result must be verified at the client access point.

### When should you use it on `Server`?

You can add:

~~~yaml
filters:
  - RemoveResponseHeader=Server
  - RemoveResponseHeader=X-Powered-By
~~~

On the corresponding route, this configuration aims to remove `Server` and `X-Powered-By` if they are already present in the response at the stage where the filter intervenes. **There is no guarantee that the `Server` header will disappear from the final response on the Internet**: the Gateway's own HTTP server, a reverse proxy, ingress, or CDN can insert `Server` at a later layer. You must check layers outside the Gateway as well and configure each layer to minimize version-advertising headers.

## 4. Full syntax with `name` and `args`

The same intent written explicitly:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: RemoveResponseHeader
              args:
                name: X-Powered-By
            - name: RemoveResponseHeader
              args:
                name: X-Backend-Version
~~~

Here:

- `filters[0].name` selects the **GatewayFilter Factory** named `RemoveResponseHeader`.
- `filters[0].args.name` is the **HTTP header name** to remove, for example `X-Powered-By`.
- `filters[1]` is an independent filter declaration that removes `X-Backend-Version`.

Both **shortcut** and **expanded** forms can produce equivalent behavior if the right factory name and parameters are used in the same version.

| Style | Example | When to choose |
|---|---|---|
| Shortcut | `RemoveResponseHeader=X-Powered-By` | Short header names, simple configuration |
| Expanded | `name: RemoveResponseHeader` + `args.name: X-Powered-By` | When explicit structure, code review, or uniform YAML convention is needed |

**Common mistake:** Do not set `args.header` or `args.value` by guessing from other factories. In the versions using the illustrated configuration, the header name field of `RemoveResponseHeader` is **`name`**.

## 5. Put filters on each route or configure `default-filters`?

### Route-specific filters

Some services need to expose their version to support clients, while others need to hide it completely. When policy differs per route, configuring `RemoveResponseHeader` **on the route itself** is more appropriate:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-private-metadata
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - RemoveResponseHeader=X-Backend-Version

        - id: public-status
          uri: http://localhost:9091
          predicates:
            - Path=/api/status/**
          filters:
            - StripPrefix=1
~~~

In the example, only the `catalog-private-metadata` route has the filter that removes `X-Backend-Version`. The `public-status` route is not stripped by **that specific filter**, though it may still be affected by common filters or external proxies.

### Default filters for routes

If you want to apply the same policy to multiple Gateway-configured routes, in WebFlux lines that support this property you can use `default-filters`:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveResponseHeader=X-Powered-By
        - RemoveResponseHeader=X-Backend-Version
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

`default-filters` are attached to routes according to the mechanism of the corresponding Gateway version. This reduces repetition when services share the same requirement, but **it should not be understood as covering all HTTP responses produced by the web server**. If a request does not match any Gateway route, or is rejected by Spring Security at the WebFlux layer before route selection, these route/default filters may **not run**.

**Distinguishing scope:**

| Location | Typical effective scope | Covers unmatched 404? |
|---|---|---|
| `filters` inside a route | Requests that selected that route | No |
| `default-filters` | Routes where default filters apply | Not guaranteed |
| Gateway `GlobalFilter` | Processing chain of the selected Gateway route | Not guaranteed |
| Appropriate `WebFilter` in WebFlux | Application HTTP layer, following web filter order | Possibly, if it runs before the component generating that response |
| Reverse proxy/ingress/CDN | Responses passing through the proxy layer, per configuration | Depends on where blocking/response happens and proxy policy |

Choose the configuration layer based on **the scope the policy requires**, not just the fewest lines of YAML.

## 6. Header removal timing and response commit

A header must be removed **before the HTTP response is committed** in order to affect what the client actually receives. Once the status and headers have been sent, modifying them usually has no effect.

A conceptual Gateway Server WebFlux flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant S as Catalog service
    participant P as Reverse proxy / CDN
    C->>G: GET /api/catalog/42
    G->>S: Forward GET /catalog/42
    S-->>G: 200 + Server / X-Powered-By / Content-Type
    Note over G: GatewayFilter response removes header name before commit
    G-->>P: 200 + Content-Type, removed headers no longer present at Gateway layer
    Note over P: Proxy may add its own headers
    P-->>C: Final response
~~~

In a real application, the downstream response is read by the Gateway, and post-filter steps and response routing coordinate to determine when headers are written. **Do not infer solely from the order of lines in YAML that a filter intervened at the right time** if there are custom filters, streaming bodies, or early-committed responses. Verify with real requests and logs when needed.

### If another filter adds the same header back

Illustrative example:

~~~yaml
filters:
  - AddResponseHeader=X-Backend-Version,unknown
  - RemoveResponseHeader=X-Backend-Version
~~~

The intent is to add and then remove the same header. However, the final execution order depends on filter order, default/global filters, and post-processing timing; **do not use this self-contradictory configuration pair in production**. If the goal is to hide the version, eliminate the header source or apply the removal policy at a layer with control over the response before commit.

The reverse can also happen: a GatewayFilter removed a header sent by the backend, but a reverse proxy **after the Gateway** sets its own `Server` header. No change in a route filter can block a header generated **after the response leaves the Gateway**.

### Streaming and error responses

When downstream sends a large file or **Server-Sent Events (SSE)**, response headers may commit right before the first chunk even though the stream continues for minutes. The filter must be applied in the proper response-handling lifecycle **before commit**. Waiting for the stream to finish before removing headers is definitely too late.

When a fallback/circuit breaker or error handler generates a replacement response, headers may come from **the Gateway or the fallback service** instead of the original backend. Check the actual branch generating the response, especially for `401`, `403`, `429`, `503`, redirects, and TLS/downstream errors.

## 7. Removing implementation details vs. removing security headers

Do not use `RemoveResponseHeader` as a blocklist for every header that "looks technical". Many headers govern protocol, safety, and client-side functionality.

| Header or group | Why you should consider keeping it |
|---|---|
| `Content-Type` | Client needs to know the data type (JSON, HTML, file, SSE) |
| `Content-Length`, `Transfer-Encoding`, `Content-Encoding` | Related to framing/compression; altering wrongly can corrupt how the client reads the response |
| `Cache-Control`, `ETag`, `Last-Modified`, `Vary` | Controls caching, revalidation, and how caches distinguish responses |
| `Location` | Needed for `3xx` redirects and certain resource-creation responses |
| `WWW-Authenticate` | Meaningful in authentication scenarios, especially `401` responses |
| `Access-Control-Allow-Origin`, other CORS headers | Browsers need them to enforce CORS policies |
| `Strict-Transport-Security` | HSTS helps clients prefer HTTPS according to the deployed policy |
| `Content-Security-Policy`, `X-Content-Type-Options` | Protects browsers against certain classes of risk |
| `Set-Cookie` | May serve sessions; removing it changes how the client maintains state |
| `Retry-After`, `RateLimit-*` | May be needed for client retry, backoff, and rate-limiting behavior |

**Rule of thumb:** only remove headers that **have been classified** as unnecessary or sensitive and have a clear policy owner. Removing `Server`/`X-Powered-By` is usually easier to justify than removing `Cache-Control`, CORS, or security headers.

In particular, when working with `401`, `403`, and `429` responses, certain headers may be a required part of the communication contract. Removing `WWW-Authenticate` or `Retry-After` unintentionally makes it harder for clients to determine the authentication scheme or wait duration before retrying.

## 8. CORS, cookies, and Gateway-generated responses

### CORS preflight

A browser may send `OPTIONS` before the actual request. Depending on the CORS configuration in the Gateway and WebFlux layer, preflight may be handled **before a normal route is selected**. If the `RemoveResponseHeader` filter is only placed on a route, it might not run for preflight.

Do not use `RemoveResponseHeader=Access-Control-Allow-Origin` as a way to configure CORS security. Define the CORS policy from a trusted source, restrict valid origins/methods/headers, and then test both preflight and actual request responses.

### Responses generated by Spring Security

Spring Security can return `401` or `403` **before the Gateway selects a route**. Route filters are not necessarily executed. If policy requires removing `Server`/`X-Powered-By` from **all responses**, consider an encompassing layer such as a web server/proxy or a `WebFilter` registered early enough.

### Cookies and sessions

Do not remove `Set-Cookie` just because the header contains some implementation information. If a cookie is genuinely unnecessary, **eliminate it at the source that creates the cookie** or configure sessions appropriately. For necessary cookies, check `Secure`, `HttpOnly`, `SameSite`, domain/path, and TLS. Blindly removing the header can cause hard-to-diagnose login failures.

### HTTP error body

Even when version headers are removed, the response body may contain stack traces, class names, hostnames, or internal URIs:

~~~json
{
  "error": "Downstream exception",
  "detail": "com.example.catalog.internal.CatalogServiceException"
}
~~~

`RemoveResponseHeader` **does not modify the JSON body**. To reduce implementation leakage in the body, handle exceptions and error structures in the backend or Gateway using an appropriate mechanism; always retain error codes/correlation IDs useful for internal investigation.

## 9. When you must cover responses that do not go through a Gateway route

With Spring Cloud Gateway Server WebFlux, you can implement a broader `WebFilter` to handle responses from the WebFlux application, including certain responses that do not match a Gateway route. Illustrative example:

~~~java
package example.gateway;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ResponseImplementationHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        ServerHttpResponse response = exchange.getResponse();

        response.beforeCommit(() -> Mono.defer(() -> {
            response.getHeaders().remove("X-Powered-By");
            response.getHeaders().remove("X-Backend-Version");
            return Mono.empty();
        }));

        return chain.filter(exchange);
    }
}
~~~

Characteristics of this code:

- This is a **Spring WebFlux `WebFilter`**, distinct from Spring Cloud Gateway's `GatewayFilter` and `GlobalFilter`.
- The `beforeCommit` callback is registered **before `chain.filter(exchange)`**, so it executes when the response is about to commit.
- `Mono.defer` delays the side effect until the publisher is subscribed/executed.
- Do not perform blocking I/O or call other services inside the callback.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` expresses the intent to register early; you must verify the actual filter order and security/error-handler components in the application.

This is **an optional extension when needed**, not mandatory if you only need to remove headers on a few routes. It also cannot remove headers added by a reverse proxy/CDN **after the Gateway**, or headers added by the transport layer after callbacks have run. For production, compare removing headers **right at the source** versus enforcing policy at the **outermost edge layer**.

## 10. Interactions with gateway filters, routing, and infrastructure

In a real gateway, a response can pass through multiple layers. When a header disappears locally but reappears in production, identify **who creates it** and **which layer runs after the removal step**.

~~~mermaid
flowchart LR
    A["Service backend"] --> B["Spring Cloud Gateway route"]
    B --> C["Gateway web server"]
    C --> D["Ingress / Reverse proxy"]
    D --> E["CDN / Edge"]
    E --> F["Client"]
    B -.->|RemoveResponseHeader at Gateway| C
    D -.->|Proxy may add headers| E
~~~

The diagram only illustrates possible layers; an actual request does not necessarily traverse all of them. Furthermore, the Gateway may sit **behind** an ingress on the request path, while the response still travels **from the Gateway back through the ingress** before reaching the client.

| Component | What to consider when removing headers |
|---|---|
| Route predicates | Filters apply only if the route is selected; if `Path`/`Host`/`Method` does not match, route filters do not run |
| Path rewrite and request headers | Executed on the request path; not equivalent to removing response headers |
| Service discovery / `lb://` | Different downstream instances may emit different sets of headers |
| Default/Global filters | May concurrently modify response headers and affect ordering/final values |
| Circuit breaker, retry, fallback | Response may be produced by another backend or the Gateway after multiple attempts |
| Rate limiting | A `429` response may be generated early, before calling downstream |
| Authentication/authorization | A `401`/`403` response may occur before the Gateway selects a route |
| TLS | Protects transport on each hop; removing headers cannot replace HTTPS or certificate validation |
| Tracing/observability | Consider keeping useful correlation IDs, while avoiding exposing hostnames, PII, and tokens |
| Ingress/CDN | May add headers after the Gateway has removed them |

**Do not hide headers that observability systems or API clients depend on** without a replacement plan. For instance, if clients rely on `Retry-After` after rate limiting, stripping the entire group of "infrastructure-related" headers can cause clients to retry continuously.

## 11. Practice: proving the filter removed the right headers

### Preparing the environment

Assume you have:

- **Gateway Server WebFlux** listening on `http://localhost:8080`.
- **Mock backend** listening on `http://localhost:9090` with endpoint `GET /catalog/items`.
- The backend returns test headers `X-Powered-By: DemoFramework`, `X-Backend-Version: 2.8.7`, `X-Request-Id: test-42`, `Content-Type: application/json`.

The Gateway configuration in section 3 maps `GET /api/catalog/items` to `GET /catalog/items` on the backend. You can use an echo backend or mock HTTP server depending on your environment; this endpoint is **hypothetical for practice**, not a built-in Gateway endpoint.

### Step 1 — Read the response directly from the backend

~~~bash
curl -i http://localhost:9090/catalog/items
~~~

Confirm that the backend actually sends `X-Powered-By` and `X-Backend-Version`. If the backend does not send these two headers yet, the Gateway not returning them **does not prove the filter removed them properly**.

### Step 2 — Call through the Gateway

~~~bash
curl -i http://localhost:8080/api/catalog/items
~~~

In PowerShell where `curl` is an alias for another command, use `curl.exe -i` to get genuine cURL behavior.

Expected:

| Header/code | Direct backend | Through Gateway | Interpretation |
|---|---|---|---|
| `X-Powered-By` | Present | Gone due to filter | Header name removed |
| `X-Backend-Version` | Present | Gone due to filter | Version info removed |
| `Content-Type` | `application/json` | Still matches response | Does not affect body parsing |
| `X-Request-Id` | `test-42` | Still present unless modified elsewhere | Supports diagnostics |
| Status `200` | `200` | `200` unless changed by another component | Filter does not modify status |

Next, test the backend returning `404` with the same two headers. For a request that matched the **Gateway route**, the filter can still remove those headers on the downstream-generated error response. Do not confuse HTTP `404` **from downstream** with HTTP `404` **from the Gateway finding no route**; only the first case is guaranteed to have passed through this route under the assumption.

### Step 3 — Test a multi-value response

Have the backend return `X-Powered-By` with two values (if the test server allows it) and call through the Gateway. Verify that **no values remain** for the name `X-Powered-By`. This is the difference between removing the entire header and modifying a single value.

### Step 4 — Try an unmatched request

~~~bash
curl -i http://localhost:8080/does-not-exist
~~~

If the application has no handler/route for this path, it usually returns `404`. **Do not assume** the filters on route `catalog-api` were executed. To test a removal policy across all responses, perform this check against a broader layer such as a `WebFilter`/web server/edge proxy.

### Step 5 — Check through ingress and real domain

After testing at the Gateway port, test the real access path through proxy/CDN or ingress:

~~~bash
curl -i https://api.example.test/api/catalog/items
~~~

The domain above is illustrative only; replace it with a valid test domain managed by your team. Compare the header set **directly from the Gateway** and **from the Internet/client access point**. If `Server` is still present at the outer layer, verify whether the proxy/CDN added it; do not conclude `RemoveResponseHeader` failed solely from the final output.

### Step 6 — Test error branches and streaming

Run additional cases relevant to your project:

- Backend returns `401`, `403`, `429`, or `503`; verify sensitive headers are removed while required API contract headers remain.
- Circuit breaker/fallback returns a response from another backend or the Gateway; compare the corresponding header sets.
- Streaming/SSE endpoints if any; headers must be removed **before the first chunk reaches the client**.
- Service discovery returns different instances; each backend instance may emit different headers.

Record the **route ID, status, before/after header sets, and Gateway instance** when testing in a multi-node cluster. Do not log tokens, cookies, or personal data verbatim.

## 12. Debugging when the header still appears

| Symptom | Possibilities to check | How to resolve |
|---|---|---|
| Header still exists through Gateway route | Wrong factory/field name, route did not match, filter not loaded | Check `RouteDefinition`, startup logs, version, and request path |
| Header remains on some routes | Only configured `filters` on one route | Apply to remaining routes or `default-filters` if policy is uniform |
| `Server` still appears on public domain | Gateway server/ingress/CDN inserts it after the removal point | Compare hop-by-hop, configure the layer adding the header |
| Unmatched 404 still has header | Route filter does not run when there is no route | Handle at an encompassing HTTP/edge layer |
| `401`/`403` from Spring Security still has header | Security blocks request before Gateway filters | Check `WebFilter` ordering and web server/proxy policy |
| Header disappears on 200 but appears on fallback | Response from another branch or filter skipped/overridden | Check circuit breaker, fallback URI, and filter chain |
| Header reappears after deploy | Older version on some instances; default/global filter or proxy re-adds it | Check rollout, cache, config, and gateway nodes |
| CORS breaks after removing headers | Accidentally removed `Access-Control-Allow-*` or `Vary` | Restore contract headers, fix CORS policy at the source |
| Client cannot log in | Removed `Set-Cookie` or `WWW-Authenticate` | Restore appropriate session/auth mechanism |
| Compressed response or file download fails | Removed protocol headers like `Content-Encoding`/`Content-Length` | Avoid generic removal on framing headers; let the HTTP stack manage them |

**Isolation workflow:** confirm backend **emits the header** → Gateway **selected the right route** → filter **is loaded and runs before commit** → header **is not re-added after the Gateway**. Also compare HTTP status/body to detect whether the request is actually taking a different fallback branch.

## 13. Checklist before applying a header removal policy

- [ ] I have identified which headers truly do not need to be public and who generates them.
- [ ] I distinguish `RemoveResponseHeader` from `RemoveRequestHeader`, `SetResponseHeader`, and `SetStatus`.
- [ ] I have selected the right Gateway version and variant, YAML namespace, and factory name.
- [ ] I know each `RemoveResponseHeader` removes one header name along with **all of its values**.
- [ ] I have checked the differences among route-specific filters, `default-filters`, `GlobalFilter`, and `WebFilter`.
- [ ] I have accounted for unmatched-route `404`s and early `401/403` responses generated by Spring Security.
- [ ] I understand why modifying response headers must happen before commit, especially with streaming.
- [ ] I am not removing security, CORS, caching, authentication, or framing headers that clients require.
- [ ] I have tested direct backend, direct Gateway, and access via ingress/CDN.
- [ ] I have tested 2xx responses and relevant errors, including fallback/retry/rate limiting if enabled.
- [ ] I have checked whether `Server` is re-added at a proxy layer outside the Gateway.
- [ ] I still manage TLS, authentication, dependency updates, rate limiting, and observability as independent policies.
- [ ] I have documented the configuration and test results so the next Gateway upgrade can re-verify them.

## Official documentation

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up the **RemoveResponseHeader GatewayFilter Factory** section and sections on default filters, global filters, and response handling matching your **Gateway version**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — related release train information and entry point to project documentation.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — header management API and `remove` by name.
- [Spring Framework — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html) — response commit lifecycle and `beforeCommit`.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — meaning of HTTP fields, response statuses, and protocol constraints.

**Remember:** `RemoveResponseHeader` helps the Gateway **remove a response header name and all of its values on applicable routes**, suitable for limiting unnecessary disclosure of `X-Powered-By`, versions, or backend hostnames. For the policy to be truly effective, you must verify filter scope, commit timing, error responses, and proxy layers that might add headers after the Gateway—while preserving the headers that HTTP clients and security systems rely on.
