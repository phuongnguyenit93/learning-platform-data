# FallbackHeaders and Permitted Error Details to Forward in Spring Cloud Gateway

When a microservice fails, **Spring Cloud Gateway** can trigger `CircuitBreaker` to route the request to a backup path (**fallback**). However, the fallback service may need to know *why* the request was diverted in order to return an appropriate result or record the incident. If the Gateway sends raw exception contents in HTTP headers, it risks leaking implementation details, sensitive data, or internal upstream information.

`FallbackHeaders` is a **GatewayFilter Factory** designed for when **the Gateway forwards to a fallback path, and another route forwards the request to an external fallback application**. It reads exception details attached to the exchange by the CircuitBreaker mechanism and **adds request headers carrying the exception type and message** before forwarding.

This lesson belongs to the **Circuit Breakers and Fallbacks** chapter of **SPRING_CLOUD_GATEWAY**. The goal is not merely enabling the filter, but **deciding which error details are permitted to cross a trust boundary**. We combine route predicates, the filter chain, path/header transformations, service discovery, authentication, rate limiting, retries, TLS, and request observability to operate a microservices Gateway safely.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux** with the `spring.cloud.gateway.routes` namespace common in Gateway 4.x releases. Newer release lines or Gateway Server MVC may change starters, namespaces, and integration behavior. Factory/property names must be verified against the **version-matched** documentation before use. Addresses and service names below are illustrative environments only.

## 1. CircuitBreaker, fallbackUri, and FallbackHeaders Have Different Responsibilities

Suppose the Gateway routes `GET /api/catalog/42` to `catalog-service`. If the downstream is unavailable, we may need to return a backup notice such as `503` with a generic error payload.

There are four distinct responsibilities:

| Component | Question Solved | Role |
|---|---|---|
| `CircuitBreaker` GatewayFilter | When does a downstream call fail or trip the circuit? | Detects failures per circuit breaker policy and diverts to fallback if configured |
| `fallbackUri: forward:/fallback` | Which internal path handles the fallback? | **Forwards inside the Gateway application** to a matching handler/route |
| `FallbackHeaders` GatewayFilter | Which error metadata does the route to an external fallback app receive? | Reads CircuitBreaker exception details and adds **request headers** |
| Fallback service | Which HTTP status/body does the final client receive? | Produces a safe response, either degraded data or a generic error |

`FallbackHeaders` **does not detect failures itself**, **does not replace CircuitBreaker**, **does not generate a fallback response itself**, and **does not select downstream instances**. It is a metadata transport component for the fallback application when an appropriate error context exists.

A route using CircuitBreaker whose fallback is handled entirely by an internal handler **does not necessarily need** `FallbackHeaders`. Conversely, putting `FallbackHeaders` on a route without CircuitBreaker exception context will not invent a failure reason on its own.

### Two-Route Flow to an External Fallback Service

~~~mermaid
flowchart TD
    C["Client GET /api/catalog/42"] --> M["Route catalog-main"]
    M --> CB["CircuitBreaker: catalogBreaker"]
    CB -->|Success| S["catalog-service"]
    S --> OK["Normal response"]
    CB -->|Failure / circuit open per policy| FW["forward:/fallback"]
    FW --> R["Route catalog-fallback"]
    R --> FH["FallbackHeaders reads exception metadata"]
    FH --> EX["Fallback service via http:// or lb://"]
    EX --> SAFE["Generate safe status/body"]
    SAFE --> C
    OK --> C
~~~

**Key takeaway:** `fallbackUri` and the fallback route's URI are **two addresses with different roles**. `forward:/fallback` uses the `forward:` scheme to dispatch inside the Gateway; `uri: http://localhost:9095` or `lb://fallback-service` in the second route specifies where the fallback application actually runs.

## 2. Why Is FallbackHeaders Needed When the Fallback Lives in Another Application?

During a CircuitBreaker flow, the exception can be stored in a **`ServerWebExchange` attribute** accessible to filters and handlers inside the Gateway. However, when the Gateway sends an HTTP request to an **external fallback application**, Java attributes inside the exchange **do not automatically appear** in the downstream process.

For example, when a call to `catalog-service` gets connection refused:

~~~text
Gateway exchange (inside the Gateway process):
  failure = ConnectException / request failed

HTTP request from Gateway to fallback service:
  Carries only method, URI, headers, body... per routing mechanics
  Does not carry the full Java ServerWebExchange
~~~

`FallbackHeaders` helps **place certain failure details into request headers** during routing to the fallback service so the external app can classify the scenario, record metrics, or choose a degraded response.

This **improves information sharing along an internal path**, not a recommendation to send exception messages to external clients. Request headers sent to the fallback service and response headers returned to browsers go in opposite directions.

### Do Not Confuse with Response Headers

~~~http
GET /fallback HTTP/1.1
Host: fallback.internal.test
Execution-Exception-Type: java.net.ConnectException
Execution-Exception-Message: Connection refused
~~~

The snippet above illustrates the **Gateway → fallback service request**. If the fallback service returns:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"CATALOG_TEMPORARILY_UNAVAILABLE","message":"Please retry later"}
~~~

then browsers usually see only the **response status/body** returned by the fallback service and Gateway. `FallbackHeaders` does not automatically copy all exception headers into the client response; however, **the fallback application could accidentally echo them**, so design and test to guarantee no leakage.

## 3. Four Header Types That FallbackHeaders Can Generate

Per the `FallbackHeaders` model in Gateway Server WebFlux, four header-name properties can be customized. The common default header names are:

| Configuration Property | Default Header Name | Semantic Value |
|---|---|---|
| `executionExceptionTypeHeaderName` | `Execution-Exception-Type` | Class/type name of the exception stored by the circuit breaker for the execution |
| `executionExceptionMessageHeaderName` | `Execution-Exception-Message` | The `message` content of that exception |
| `rootCauseExceptionTypeHeaderName` | `Root-Cause-Exception-Type` | Class/type name of the root cause when found |
| `rootCauseExceptionMessageHeaderName` | `Root-Cause-Exception-Message` | The `message` content of the root cause when found |

**Not every fallback request contains all four headers.** When no exception attribute is present or no root cause is found, the corresponding header may be absent. Exception messages can be empty, `null` at the API level, or constrained by HTTP header validity rules; the fallback app must handle missing headers without assuming every value is always present.

### How Execution Exception Differs from Root Cause

Suppose an HTTP call fails, and the exception recorded by CircuitBreaker looks like:

~~~text
ReactiveClientException
  caused by ConnectionException
    caused by ConnectException("Connection refused")
~~~

- **Execution exception** is the top-level exception representing the execution stored in the CircuitBreaker context; it may be a wrapper.
- **Root cause** is the deeper cause down the `cause` chain if found.

When a circuit is **OPEN**, it may produce an exception indicating "call not permitted" rather than a new connection error. Therefore, do not assume every fallback invocation has a `ConnectException` root cause.

**Do not treat class names as a long-term business contract.** After upgrading libraries or changing implementations (Reactor Netty, Resilience4j, load balancer), exception types or messages can change even when the user-facing meaning stays the same.

### Message Contents Can Be Sensitive

Exception messages can inadvertently contain:

- Internal hostnames, service IDs, ports, URIs, and query strings.
- Partial filesystem paths, class/package names, SQL snippets, or schema structure.
- User data if logging/exception handling fails to mask details.
- In some downstream-generated errors, request context containing tokens or sensitive identifiers.

**Customizing header names does not sanitize the contents.** Renaming `Execution-Exception-Message` to `X-Edge-Error-Detail` only changes the name—it **does not strip secrets**. That is the most important security limitation of `FallbackHeaders`.

## 4. Minimal Configuration: CircuitBreaker Forward and External Fallback Route

Suppose:

- Gateway listens on `http://localhost:8080`.
- Catalog backend is at `http://localhost:9090`.
- Trusted fallback application is at `http://localhost:9095`, exposing `GET /fallback`.

Illustrative configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback

        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - name: FallbackHeaders
~~~

**How to read it:**

1. Request `/api/catalog/42` matches route `catalog-main`.
2. `CircuitBreaker` protects calls to the catalog backend per configured policy.
3. If the call fails under conditions handled by CircuitBreaker, Gateway forwards internally to `/fallback`.
4. Route `catalog-fallback` matches `/fallback` and applies `FallbackHeaders`.
5. Gateway sends the request to the fallback app at `http://localhost:9095`; the fallback service can receive exception request headers.
6. The fallback service decides the **final HTTP response**.

The example above is an **internal lab** for observing headers, not a configuration to expose verbatim on the Internet. `/fallback` can be called directly by clients; in production, the fallback route requires proper access boundaries and header filtering.

### Why Doesn't `fallbackUri` Point Directly to an External URL?

With the CircuitBreaker GatewayFilter, `fallbackUri` is supported by design to **forward** to an internal path such as `forward:/fallback`. If your fallback application runs on another host/service, use a **second route** with `http://...` or `lb://...` matching the forwarded path.

Do not replace it with:

~~~yaml
# DO NOT assume CircuitBreaker supports direct fallbacks like this:
fallbackUri: http://localhost:9095/fallback
~~~

When calling an external fallback service, follow the **internal forward → fallback route → FallbackHeaders → outbound routing** pattern above and verify against your exact Gateway version.

## 5. Customizing Header Names

An operations team may want a consistent prefix on internal traffic, such as `X-Edge-Fallback-*`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - name: FallbackHeaders
              args:
                executionExceptionTypeHeaderName: X-Edge-Fallback-Exec-Type
                executionExceptionMessageHeaderName: X-Edge-Fallback-Exec-Message
                rootCauseExceptionTypeHeaderName: X-Edge-Fallback-Root-Type
                rootCauseExceptionMessageHeaderName: X-Edge-Fallback-Root-Message
~~~

This is an **alternative fallback route** replacing `catalog-fallback` in Section 4, not a YAML snippet to append into the same application with a duplicate route ID.

The `args` properties accept **HTTP header names**, not static exception values. The exception type/message is pulled from the execution context at runtime when present.

| Operational Requirement | Capability of FallbackHeaders |
|---|---|
| Rename the four headers | Yes, via the four properties above |
| Pass exception metadata into request headers | Yes, when matching error context exists |
| Translate into a single safe business code like `UPSTREAM_UNAVAILABLE` | **Does not do this on its own** merely by renaming headers |
| Mask tokens, internal addresses, or PII in messages | **Does not do this on its own** |
| Authenticate the fallback service | No |
| Force the fallback response to 503 | No |
| Transmit a complete stack trace | Not part of the contract defined by these four headers |

**Only rename headers when you genuinely need a clear internal contract.** If policy forbids sending raw exception messages to external applications, **do not enable `FallbackHeaders` just to rename them**; use safe error classification or emit a sanitized message via an appropriate custom handler/filter.

## 6. Exact Path of the Request and Error Metadata

A failing request undergoes two distinct routing hops: first calling catalog, then calling fallback.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant U as catalog-service
    participant F as fallback-service
    C->>G: GET /api/catalog/42
    G->>G: Match catalog-main + CircuitBreaker
    G->>U: Forward request to catalog
    U--xG: Connection error / exception
    Note over G: CircuitBreaker records failure and selects forward:/fallback
    G->>G: Match route catalog-fallback
    G->>G: FallbackHeaders reads execution exception / root cause
    G->>F: GET /fallback + error headers (if present)
    F->>F: Use metadata internally only, do not echo raw message
    F-->>G: 503 + generic error JSON
    G-->>C: 503 + generic error JSON
~~~

In real requests, route config, HTTP method, path rewrites, filter order, and per-version forwarding mechanics can affect the final path/headers. The diagram intentionally shows the **conceptual** flow. Observe real requests at the fallback service to confirm which path and headers it receives and whether `SetPath`/`RewritePath` is needed.

### Where Does the Metadata Go?

Failure details from **CircuitBreaker execution** are stored in the **exchange context** inside the Gateway. `FallbackHeaders` reads that context when running on the fallback route and mutates the **request**. Do not confuse it with:

- Claims inside a JWT.
- Request headers sent originally by the client.
- HTTP response status/body returned by the catalog backend.
- Logs or traces emitted by monitoring systems.
- Error JSON responses ultimately produced by the fallback service.

**Exchange attributes do not cross process boundaries on their own.** Request headers are the transport mechanism to the fallback service in this pattern.

### What If Someone Calls `/fallback` Directly?

A client could call:

~~~http
GET /fallback HTTP/1.1
Host: gateway.example.test
Execution-Exception-Type: forged-by-client
~~~

A direct request does not necessarily have an execution exception just created by CircuitBreaker. `FallbackHeaders` is not a **provenance verification** mechanism for pre-existing headers. Thus, if the fallback endpoint is public and the backend trusts those headers unchecked, clients can inject **spoofed metadata**.

At a minimum, strip headers that clients can supply themselves before attaching Gateway-managed metadata, and restrict access to the fallback route. The next section examines this trust boundary in detail.

## 7. Policy on Permitted Error Information to Forward

**There is no "universally safe" header list for every organization.** Classify based on actual contents, trust level of the fallback service, and business needs.

| Information Type | Risk Level | Recommendation |
|---|---|---|
| Abstract business error code, e.g., `UPSTREAM_UNAVAILABLE` | Low if it reveals no internals | Prefer using in contracts/responses |
| Random correlation ID without identity | Low–medium | Can forward for log lookup; validate format/origin |
| Exception class name, e.g., `ConnectException` | Medium | Forward only over internal channels when justified |
| Root-cause exception class | Medium–high | Can reveal libraries/frameworks or topology |
| Raw exception message | High or unknown | By default **do not cross trust boundaries** without review |
| Internal URI/hostname and query string | High depending on endpoint | Never return to clients; consider masking even between services |
| Access tokens, API keys, cookies/session IDs | Very high | **Never place in error headers/logs** |
| Full stack trace, SQL/connection strings | Very high | Store only in secured diagnostic systems; avoid HTTP metadata |

A practical policy might define:

- **Clients receive only:** `code`, user message, correlation ID, contract status; optionally `Retry-After` when a reasonable wait estimate exists.
- **Internal fallback service receives:** **sanitized** error category code, approved route/service ID, correlation ID.
- **Internal observability receives:** detailed technical cause as needed, but with tokens/PII redacted and restricted read access.

### Is FallbackHeaders Suitable Across Every Trust Boundary?

**No.** The factory is built to forward **execution exception details**, including messages. If the fallback app is managed by a third party or sits in a lower-trust security zone, sending raw messages can violate data policies.

If you only need a stable `CATALOG_UNAVAILABLE` code, better options include:

1. Letting the fallback service return that code based on the known route/endpoint context, **without FallbackHeaders**; or
2. Building a custom Gateway handler/filter that classifies exceptions, **strips sensitive details**, and emits only allowed headers; or
3. Keeping `FallbackHeaders` inside a trusted internal network with strict outbound header stripping/allowlisting tested thoroughly.

Do not treat renaming the four headers as a sanitization step.

## 8. Preventing Spoofing and Blocking Credential Leaks on the Fallback Route

When a fallback route might receive both internal forwards and direct client requests, avoid mixing **client-supplied headers** with **Gateway-generated headers**.

In a lab route using default names, you can apply request-header removal filters before `FallbackHeaders`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - RemoveRequestHeader=Execution-Exception-Type
            - RemoveRequestHeader=Execution-Exception-Message
            - RemoveRequestHeader=Root-Cause-Exception-Type
            - RemoveRequestHeader=Root-Cause-Exception-Message
            - RemoveRequestHeader=Authorization
            - RemoveRequestHeader=Cookie
            - name: FallbackHeaders
~~~

**This configuration is suitable only in a lab or an approved internal path.** It expresses the intent to strip matching client-supplied headers and avoid forwarding credentials unnecessarily to the fallback service. However, `FallbackHeaders` afterward can still add **raw exception messages**, so it is **not enough on its own** to enforce a sanitized-codes-only policy.

Additional notes:

- `RemoveRequestHeader` is a **request** filter; it does not scrub details already leaked into logs, bodies, or responses.
- Filters must actually execute in the intended order **before outbound routing**. Verify the request received by the backend and effects of default/global filters.
- Clients can still call `/fallback` directly if the route/path is public. Restrict it at the ingress/network/security layer and check whether blocking that path affects internal forwarding.
- If the fallback service needs authentication, use dedicated **service-to-service authentication**, not wholesale forwarding of client Authorization/Cookies.
- Behind proxies, inspect `Forwarded`, `X-Forwarded-*`, `Host`, and internal headers per trusted-proxy policy.
- Removing only the four default names **does not strip custom names** if you switched to `X-Edge-Fallback-*`. Keep the removal list synchronized with actual configured names.

**Do not rely on `FallbackHeaders` only running on exceptions to prove the caller is the internal Gateway.** Request origin must be verified via networking, service identity/credentials, or an equivalent trust mechanism.

## 9. Safer Option When You Only Need an Error Code

If security requirements forbid **sending exception class names or messages to the fallback service**, prefer a fixed fallback endpoint and safe response without `FallbackHeaders`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback

        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - RemoveRequestHeader=Authorization
            - RemoveRequestHeader=Cookie
            - SetRequestHeader=X-Edge-Fallback-Category,CATALOG_UNAVAILABLE
~~~

In this example, the fallback service knows the **fallback category by route/endpoint**, without needing raw exceptions. The category header is internal metadata only. **Do not trust this header if clients can call the fallback route directly**; still block or authenticate callers and strip client-supplied headers before setting trusted headers.

If you genuinely need to distinguish `TIMEOUT`, `CIRCUIT_OPEN`, and `CONNECTION_FAILURE`, use a classifier **emitting a small allowlist of normalized codes** based on the exception in the Gateway, never stuffing raw messages or stack traces into headers. Send deep details to secured logs/tracing.

### Do Not Mechanically Turn Raw Errors into 200

A fallback can be designed under two patterns:

- **Degraded success:** returns a meaningful backup result, potentially `200` if the business contract permits and clients know data may be stale.
- **Service unavailable:** returns `503`/appropriate error code with stable JSON so clients know the request was not processed.

Not every fallback is a success. Returning 200 for every outage corrupts SLO monitoring, masks upstream failures, and causes clients to make wrong decisions. The fallback service must pick statuses per the API contract.

## 10. How Should the Fallback Service Handle Headers?

An illustrative Spring WebFlux controller (in the **external fallback app**, not code inside the Gateway):

~~~java
package example.fallback;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogFallbackController {

    @GetMapping("/fallback")
    public Mono<ResponseEntity<Map<String, String>>> fallback(
        @RequestHeader(value = "Execution-Exception-Type", required = false)
        String executionType) {

        // Classify only for internal metrics when the caller is trusted.
        // Do not include raw exception class/message in client responses.
        String safeCode = "CATALOG_TEMPORARILY_UNAVAILABLE";

        return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", safeCode,
                "message", "Catalog is temporarily unavailable"
            )));
    }
}
~~~

The controller deliberately **does not echo `executionType`**. Nor does it use exception classes for authorization or routing decisions. If metrics by error group are needed, classify only after verifying the caller and validating header values, using **bounded cardinality** (a finite label set). Never use raw class names or messages as metric labels or log keys, which creates high cardinality and leaks information.

For production, a fallback endpoint typically needs to:

- Accept a **published** set of HTTP methods and paths; never blindly return success for every method without proper semantics.
- Return content type, status, and JSON body consistent with the API contract.
- Restrict data read permissions and network reachability; the fallback should be lighter than the primary downstream.
- Have independent timeouts, health checks, and monitoring so the fallback does not become a new single point of failure.
- Prevent infinite loops: **the fallback route must never call back into the failing catalog route** or forward back to `/fallback`.

## 11. CircuitBreaker Configuration: Which Failures Actually Trigger Fallback?

`FallbackHeaders` is useful only if **CircuitBreaker has triggered the fallback branch and has failure metadata**. Therefore, you must understand which outcomes count as failures.

An illustrative configuration can specify HTTP statuses to treat as CircuitBreaker failures:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback
                statusCodes:
                  - 500
                  - 502
                  - 503
~~~

**Key point:** an HTTP `500` response from the backend **does not automatically produce an exception/fallback** if the filter and version are not configured to treat that status as a failure. `statusCodes` specifies which HTTP codes are handled as failures per the factory's contract in that version.

Do not add `401`/`403` to the list just to "hide errors": they usually signal auth/permission problems and should be returned meaningfully to clients. Likewise, `404` can be a completely valid "not found" error, not a sign of a broken backend.

### Do Not Equate Exception Types with HTTP Statuses

| Failure Source | What to Verify | Metadata FallbackHeaders Might See |
|---|---|---|
| Upstream connection refused | Does the routing call emit an exception? | Execution exception class/message |
| Timeout | Created by WebClient/Netty/TimeLimiter or another layer? | Possibly a timeout exception or wrapper |
| Circuit is OPEN | Was the call rejected by the breaker and sent to fallback? | Possibly a "call not permitted" exception |
| Backend returns 503 | Is `statusCodes: 503` or matching policy set? | Depends on how the factory translates statuses into errors |
| Backend returns 404 | Should 404 count as an error? | Usually **should not** trigger fallback automatically |
| Security blocks with 401/403 before routing | Did the request reach CircuitBreaker GatewayFilter? | Usually **no** metadata from the route's circuit breaker |
| Rate limiter returns 429 | Does limiter block before or after breaker per filter order? | Not an upstream failure by default |

**Fallbacks must not mask security errors.** An HTTP 401 rejected by Gateway security before routing will not run the route's CircuitBreaker filter; that behavior should be preserved in your design.

### Resilience4j and Instance Names

When using Spring Cloud CircuitBreaker with an implementation such as Resilience4j, the name `catalogBreaker` links to instance settings per the matching release train.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBreaker:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
~~~

This is an **example of circuit breaker parameters**, insufficient on its own without the reactive CircuitBreaker starter and timeout configuration. Gateway Server WebFlux typically needs Reactor-capable integration, such as the Resilience4j starter matching your Spring Cloud CircuitBreaker version. Timeouts, TimeLimiter, and OPEN/HALF_OPEN states must be tested practically; do not use illustrative thresholds as production defaults.

## 12. Interaction with Retry, Timeouts, and LoadBalancer

A Gateway request may traverse `Retry`, `CircuitBreaker`, and `lb://catalog-service`. Filter ordering determines whether CircuitBreaker sees **one failure after multiple retries** or each individual attempt in a retry sequence.

Conceptual flow:

~~~text
Client request
   -> Authentication / Rate limit
   -> CircuitBreaker + Retry in a verified order
   -> LoadBalancer selects catalog instance
   -> Downstream attempts
   -> If failed per policy: forward:/fallback
   -> FallbackHeaders on the fallback route
~~~

Do not assume simply placing two YAML lines in one order guarantees uniform semantics across all implementations for exceptions, response statuses, route ordering, global filters, and retry callbacks. Observe execution order and outbound attempt counts.

| Feature | Risk If Coordinated Poorly | What to Verify |
|---|---|---|
| `Retry` | One client request creates multiple requests to a failing upstream | Budget, max retries, backoff, idempotency |
| CircuitBreaker | Opens too early or fails to reflect real errors | Sliding window, thresholds, recorded exceptions/statuses |
| Timeout/TimeLimiter | Holds requests too long; fallback also slows down | Timeouts for upstream and fallback; resource caps |
| `lb://` | One failing instance drives up failure rate | Health, discovery state, load balancing, per-instance failures |
| Rate limiting | Requests entering fallback could be counted twice if fallback route also has a limiter | Quota design on main route and fallback route |
| Cache/degraded data | Clients receive stale data as if fresh | Transparent status/metadata per contract |
| Streaming/SSE | Error occurs after response commits | Never promise a fallback can replace an already partially sent response |

**SSE and committed responses:** a stream may have already sent headers and several chunks to the client before downstream fails. At that point, you cannot always switch to a brand-new fallback response with a different status/body. Fallback design must respect HTTP response lifecycle limits.

## 13. Securing the Fallback Route and Trust Boundaries

Typically the path spans at least three trust zones:

~~~mermaid
flowchart LR
    C["Public client / browser"] --> E["Ingress / Gateway"]
    E -->|TLS, authenticated route| U["catalog-service"]
    E -->|Internal fallback route| F["fallback-service"]
    E --> LOG["Logs / tracing"]
    F --> LOG
    X["Client sets error headers"] -.-> E
~~~

**Define who is allowed to send requests to `/fallback`.** If this route is exposed to the Internet, an attacker can call it directly or probe known header names. If the fallback backend uses exception headers to decide what data to return, it could be manipulated by an untrusted caller.

Operational controls:

1. **Block or restrict direct access** to the fallback path at the appropriate ingress/security/network layer while ensuring internal forwards still work under the actual lifecycle.
2. **Sanitize request headers** to remove client-supplied headers before the Gateway attaches trusted metadata.
3. **Do not forward `Authorization`, `Cookie`, or API keys** to the fallback service if unnecessary; if service identity is needed, use mTLS/service tokens instead of end-user credentials.
4. **Protect Gateway → fallback with TLS/mTLS** or network isolation and validate certificate trust if policy requires.
5. **Never trust raw exception classes/messages** for authorization decisions; they are strictly diagnostic.
6. **Never echo raw error headers** into responses, browser devtools, public logs, or metric labels.
7. **Cap metadata size/rate**, set timeouts, and monitor fallback responses. Exception messages from some libraries can be unpredictably long.
8. **Separate backend errors from authentication/authorization errors.** Never trigger a 200 fallback for a user who was never authorized.
9. **Audit proxy/filter ordering** so trusted headers set by the Gateway are not overwritten by a downstream layer.
10. **Ensure the fallback service cannot loop** or become a bypass gateway to sensitive data.

### Note on Passing Correlation IDs

A correlation ID validated or generated at the Gateway is helpful for the fallback service. However, **never use a session ID or access token as a correlation ID**. IDs must have reasonable format/length bounds, contain no PII, have controlled log lookup permissions, and not be unboundedly client-controlled.

You can attach a header such as `X-Request-Id` managed by a dedicated tracing/Gateway filter. `FallbackHeaders` **does not generate correlation IDs** and does not replace standard trace propagation such as `traceparent`.

## 14. Hands-On Lab: Which Headers Does the Fallback Service Receive?

### Preparing Three Components

- **Gateway:** `http://localhost:8080` with both `catalog-main` and `catalog-fallback` routes from Section 4.
- **Catalog backend:** `http://localhost:9090`, exposing `GET /api/catalog/42` when running.
- **Fallback backend:** `http://localhost:9095`, endpoint `GET /fallback`, able to log **header names and presence**, without logging/echoing sensitive values raw.

In the lab, to inspect failure metadata safely, use a mock fallback HTTP server returning safe JSON; if no mock server exists, stand up an actual backend before testing. Run in an isolated environment without real tokens.

### Step 1 — Happy Path Without Triggering Fallback

Start both backends, then send:

~~~bash
curl -i "http://localhost:8080/api/catalog/42"
~~~

Expect the request to reach the catalog backend and return a normal response. The fallback service **is not called** when catalog responds successfully under CircuitBreaker policy.

### Step 2 — Catalog Unavailable

Stop only the catalog backend on `localhost:9090`, leaving the fallback backend running:

~~~bash
curl -i "http://localhost:8080/api/catalog/42"
~~~

If CircuitBreaker and the forward route are configured properly, the request flows through `forward:/fallback`, matches `catalog-fallback`, and reaches the fallback backend.

The fallback backend should safely log:

~~~text
method: GET
path: /fallback
has Execution-Exception-Type: true
has Execution-Exception-Message: true/false (depending on error)
has Root-Cause-Exception-Type: true/false
has Root-Cause-Exception-Message: true/false

response to caller:
  HTTP 503
  {"code":"CATALOG_TEMPORARILY_UNAVAILABLE", ...}
~~~

**Do not assert that all four headers must always be present**, as exception/root cause vary by scenario and version. Observe actual details, confirm the fallback reason, and ensure no raw exception appears in the final response.

### Step 3 — HTTP `statusCodes` Case

Bring the catalog backend back up returning HTTP `503`. With the `CircuitBreaker.statusCodes` config from Section 11 (if supported by your version), Gateway can treat 503 as a failure handled via fallback. Then remove `statusCodes` and compare, to see the difference between an **HTTP error response** and an **exception** in CircuitBreaker mechanics.

Never use `404` to simulate outages by default, since resource-not-found can be a valid business response.

### Step 4 — Direct Calls to the Fallback Route and Spoofing Test

In a **controlled test environment**:

~~~bash
curl -i "http://localhost:8080/fallback" \
  -H "Execution-Exception-Type: forged-client-value" \
  -H "Execution-Exception-Message: forged-message"
~~~

Before deploying to production, verify that:

- Direct client requests are not treated as valid internal fallbacks.
- The backend never trusts `forged-client-value` to grant access or return sensitive data.
- Incoming headers with matching names are stripped per policy.
- Not every request matching `Path=/fallback` automatically has a CircuitBreaker-created exception.

If you block direct access at security/ingress, the probe may receive **403/404** per policy. If direct access still receives 200 from the fallback backend, investigate whether the endpoint was unintentionally made public.

### Step 5 — Verifying the Fallback Route Does Not Receive Secrets

Run in a test environment with **dummy values**, never real credentials:

~~~bash
curl -i "http://localhost:8080/api/catalog/42" \
  -H "Authorization: Bearer demo-only-token" \
  -H "Cookie: SESSION=demo-only-cookie"
~~~

If the fallback route strips `Authorization` and `Cookie`, the backend must not see them when requests reach `/fallback`. If it still receives them, inspect route/filter order, forward behavior, and other proxy components. Never treat a single test as sufficient in multi-instance Gateway deployments.

### Test Matrix

| Case | CircuitBreaker Fallback? | Error Headers at Fallback Service | Final HTTP Response |
|---|---|---|---|
| Catalog returns 200 | No | No fallback request | 200 or catalog status |
| Catalog connection fails | Yes if policy/route right | Exception details depending on error | Per fallback backend, e.g., 503 |
| Catalog returns 503, `statusCodes` includes 503 | Likely yes | Metadata depends on how factory handles status | Per fallback backend |
| Catalog returns 503, status not marked as failure | Not necessarily | May not call fallback | May return 503 directly |
| Client calls `/fallback` directly | Not from catalog CircuitBreaker | No CB metadata; client headers could be forged | Should be blocked or untrusted |
| Invalid JWT | Spring Security may block before route | No route fallback | Typically 401 |
| Request exceeds rate limit | May block before CircuitBreaker | Not necessarily any fallback | Typically 429 |

## 15. Troubleshooting Common Incidents

| Symptom | Where to Check | Resolution |
|---|---|---|
| Catalog fails, yet fallback does not run | CircuitBreaker not attached to route, or status not treated as failure | Verify factory, `statusCodes`, exceptions, and route predicates |
| "invalid fallbackUri" or forward fails as expected | `fallbackUri` wrong scheme/path | Use `forward:/fallback` and a dedicated fallback route |
| Forward to `/fallback` returns 404 | No handler/route matching fallback path | Check Path predicate, handler mapping, route order |
| Fallback service is never called | Wrong external URI, DNS, load balancer, network, or TLS error | Test fallback route directly in lab and check outbound routing |
| No exception headers present | `FallbackHeaders` missing on fallback route, or no exchange exception attribute | Check runtime routes, CB flow, actual failure info |
| Type present, but root cause missing | Exception has no cause chain, or different implementation | Handle optional headers gracefully in fallback service |
| Raw exception appears in client response | Fallback backend echoed headers/message or error serializer leaked details | Return generic code/message, redact logs, strip unsafe headers |
| Duplicate or spoofed error headers | Client sent headers directly or filter ran multiple times | Strip incoming header names before `FallbackHeaders`; check filter order |
| 200 fallback keeps dashboards "green" | SLO measures final HTTP status without fallback metric | Separate degraded success from upstream failures |
| HTTP 401/403 triggers fallback | Wrong `statusCodes` or improper security exception handling | Do not treat auth errors as outages; audit policies |
| Fallback is also slow/failing | Backup backend unhealthy, missing timeout/network isolation | Set timeouts, health checks, and final error handling |
| Fails only on one Gateway node | Different route/circuit breaker instance config | Check rollout, caches, config, registry, CB metrics |
| Request enters a fallback loop | Fallback route also has CircuitBreaker forwarding to same path | Remove recursion; separate routes/handlers cleanly |

### 6-Point Verification Checklist

1. **Did the request match the main route** and pass through the CircuitBreaker filter?
2. **Which failure source** triggered CircuitBreaker: exception, status code, timeout, or OPEN circuit?
3. **Did `forward:/fallback` reach the right fallback handler/route**?
4. **Did `FallbackHeaders` run on the fallback route** and find the exception metadata?
5. **Did the request reaching the fallback service** have the right method/path/headers without leaking credentials?
6. **Does the final response** have a safe status/body, and does observability record fallback count, cause, and latency properly?

Combine route ID, circuit breaker name, outcome, correlation ID, latency, and properly configured distributed tracing; **never use raw exception messages as metric labels**, and never log Bearer tokens, cookies, or session IDs.

## 16. Pre-Production Checklist

- [ ] I can distinguish `CircuitBreaker`, `fallbackUri: forward:/fallback`, and `FallbackHeaders`.
- [ ] I understand `FallbackHeaders` adds **request headers sent to the fallback service**, not automatic response headers to clients.
- [ ] I know the four header types—execution type/message and root-cause type/message—and when they may be absent.
- [ ] I verified header/arg names against the exact Gateway Server WebFlux version.
- [ ] I do not treat renaming headers as hiding exception contents.
- [ ] I only use the factory to pass detailed failure info when the fallback service is a **trusted and authorized** recipient.
- [ ] I defined an explicit list of permitted error details, preferring normalized error codes and correlation IDs.
- [ ] I never echo raw exceptions, stack traces, hostnames, SQL details, credentials, or PII into responses.
- [ ] I strip client-supplied headers that could spoof Gateway metadata.
- [ ] I locked down direct access to the fallback route or ensured the fallback backend does not trust client-supplied headers.
- [ ] I do not forward Authorization/Cookies to the fallback unnecessarily and use service-to-service authentication if needed.
- [ ] I have TLS/mTLS, network isolation, and certificate trust policies for the Gateway → fallback hop.
- [ ] I tested connection errors, timeouts, OPEN circuits, and `statusCodes` per real policies.
- [ ] I do not turn business 401/403/404 responses into outage fallbacks unless explicitly designed.
- [ ] I understand Retry/CircuitBreaker order, outbound attempt counts, and rate limiting effects.
- [ ] I prevent fallback routes from looping or serving backup data that violates contracts.
- [ ] I checked committed responses/streaming behavior if the app uses SSE or large downloads.
- [ ] I monitor fallback counts, error rates, latency, circuit states, and backend availability across multiple Gateway nodes.
- [ ] I ran end-to-end tests through ingress/proxies, not only against Gateway localhost directly.
- [ ] I specifically audited whether debug data leaks via headers, logs, traces, or metrics.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — see **FallbackHeaders GatewayFilter Factory**, **CircuitBreaker GatewayFilter Factory**, fallback configuration, and version-matched **Server WebFlux** routing.
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/) — circuit breaker integration, Resilience4j, and instance names.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html) — exchange attributes, request mutation, and reactive HTTP lifecycle.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — HTTP headers and multi-value lists.
- [Resilience4j Documentation](https://resilience4j.readme.io/docs/circuitbreaker) — CLOSED/OPEN/HALF_OPEN states, failure rates, and breaker configuration.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — status and HTTP field semantics.

**Key takeaway:** `FallbackHeaders` bridges **CircuitBreaker exception metadata** to **request headers of an external fallback application**, typically via **CircuitBreaker → `forward:/fallback` → fallback route → FallbackHeaders → fallback service**. It aids diagnostics but **does not protect data by itself**: class names and especially raw exception messages must only be sent to authorized recipients. In public contracts, prefer **stable statuses/error codes, generic messages, and correlation IDs**, while keeping detailed technical errors inside controlled observability systems.
