# API Version Routing by Path or Header

## 1. Context: One API, Multiple Contracts Must Coexist

As a microservices system evolves, an API often serves multiple generations of clients: un-updated mobile apps, a web frontend running the latest release, partner integration systems, or internal applications. When a change is **not backward-compatible**, deploying a new backend without version routing can cause older clients to receive malformed JSON structures, miss required fields, or encounter unexpected business behavior.

In **Spring Cloud Gateway (SCG)**, a common pattern is **API version routing**: the gateway reads version information from the **path** or an **HTTP request header**, selects the right route, and forwards the request to the backend implementing the corresponding contract.

The two requests below can express the same intent:

~~~http
GET /api/v1/catalog/items/42 HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: api.example.test
X-API-Version: 1
~~~

The difference is **which component of the request carries the version**. The gateway needs clear rules for reading, validating, and forwarding that version; the backend needs to understand whether the request selected the `v1` or `v2` contract.

In the **SPRING_CLOUD_GATEWAY** module, we already have building blocks such as **route predicates, the filter chain, path/header rewriting, service discovery, Spring Security, rate limiting, circuit breakers, retries, TLS, and observability**. The lesson **“API Version Routing by Path or Header”**, in the **Routing Patterns** chapter, combines these pieces into an architecture for deploying multiple versions safely, testing them easily, and retiring older versions on schedule.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **API contract version** from **deployment version**, **database schema version**, and **canary traffic splitting**.
2. Configure two routes `/api/v1/catalog/**` and `/api/v2/catalog/**` using the Spring Cloud Gateway `Path` predicate.
3. Configure two routes with the same path `/api/catalog/**` but different `Header=X-API-Version` values, and understand regex matching.
4. Use `Method`, `StripPrefix`, `RemoveRequestHeader`, `SetRequestHeader`, and `SetResponseHeader` in the right direction.
5. Handle **missing/invalid/unsupported/duplicate/conflicting versions** under a predictable contract.
6. Explain **route order, catch-all routes, and filter order**, and avoid misrouting versions.
7. Design **`Vary: X-API-Version`**, ETag, and cache behavior properly when versioning via headers.
8. Separate API versioning from authentication/authorization, and never trust a client header as proof of identity.
9. Test realistically with **backend stubs**, comparing the request the backend receives against the response the client receives, including 400/404/503 errors and rollouts.
10. Plan migration, deprecation, Sunset, and per-API-version usage observability to retire old versions in a controlled way.

> **Example scope:** The primary configuration uses **Spring Cloud Gateway Server WebFlux**, with the `spring.cloud.gateway.server.webflux.routes` namespace on supported release lines. Older lines may use `spring.cloud.gateway.routes`; **Gateway Server Web MVC** has its own dependencies, namespace, and filter chain. Pin the Spring Boot/Spring Cloud BOM and inspect the configuration metadata for your exact version before deploying. Hostnames and figures in this lesson are **lab examples**, not real endpoints.

## 2. “API Version” Does Not Mean “Application Version”

Before writing YAML, decide precisely **what is being versioned**.

| Concept | Example | Is it a client-side contract selection key? |
| --- | --- | --- |
| **API contract version** | `/api/v1/catalog` or `X-API-Version: 2` | **Yes**, when different contracts are incompatible |
| **Backend build/release version** | `catalog:2026.11.24-rc3` | No; multiple builds can serve API v1 together |
| **Kubernetes Deployment revision** | `catalog-v2-7d9c...` | No; this is a rollout artifact |
| **Database schema version** | Flyway migration V37 | Not directly; a schema may be shared across multiple API contracts |
| **Canary rollout** | 10% traffic to v2 code and 90% to v1 code | Does not create API v2 by itself; only distributes traffic |
| **Content/media-type representation** | `application/vnd.example.catalog.v2+json` | Can be a representation negotiation mechanism, but is a different contract from a custom header |
| **SDK SemVer** | `catalog-client 3.2.1` | Does not necessarily correspond to the server API major version |

### When Do You Need API v2?

Several changes are likely to break the v1 contract:

- Changing the `price` field type from an integer to an object containing `amount`/`currency`.
- Renaming or removing a field that older clients are required to read.
- Changing the HTTP method from `GET` to `POST` or altering resource ID semantics.
- Changing pagination semantics, error codes, or authorization requirements.
- Switching between incompatible representations, even if the backend URL stays the same.

Conversely, adding a JSON field *may* be backward-compatible if clients are designed to ignore unknown fields; however, never assume every client or SDK does so. Base versioning decisions on **contract tests**, not merely on release counts.

### Contract Versions Can Coexist on a Single Backend

~~~mermaid
flowchart LR
    C["Clients"] --> G["Spring Cloud Gateway"]
    G -->|"v1 contract"| V1["catalog-v1 adapter"]
    G -->|"v2 contract"| V2["catalog-v2 adapter"]
    V1 --> Domain["Shared domain service / database"]
    V2 --> Domain
~~~

SCG can route to two separate backend deployments, **or** both versions can be served inside the same backend application with separate handlers/adapters. The runtime topology is a design choice; **an API version does not force you to duplicate databases or infrastructure**.

## 3. Path Versioning vs. Header Versioning: A Deliberate Comparison

| Criterion | Path versioning | Header versioning |
| --- | --- | --- |
| Sample request | `GET /api/v1/catalog/items/42` | `GET /api/catalog/items/42` + `X-API-Version: 1` |
| Visibility in URLs/route logs | Explicit in the path | Not visible from inspecting the URL alone |
| Ease of use with browsers/curl/links | Usually more convenient | Client must set a request header |
| Bookmarking and sharing URLs | The URL identifies the version | The same URL can return multiple representations |
| CDN/caching | Versions are typically separated by URI | Requires proper cache key/`Vary` handling by header |
| Reverse proxy/load balancer support | Path matching is universal | Must forward the header and enforce cache/header policies |
| API docs and examples | Easy to separate `/v1`, `/v2` | Must document the required header clearly in OpenAPI/docs |
| Risk of invalid version input from clients | `/v3` path or unintended route match | Missing header, multiple values, malformed value, proxy stripping |
| OpenAPI/server URLs | Typically distinguished by base path | Uses appropriate parameter/header contracts |
| Multi-client evolution | Can maintain two paths in parallel | Can keep endpoint paths stable with header negotiation |
| When appropriate | Public REST APIs, linkable resources, simple observability | Internal APIs, SDK-controlled clients, need for a stable URL |

**Neither option is universally better in every environment.** For public APIs with diverse, asynchronous clients, path versioning is usually easier to discover. For tightly controlled SDK clients that need stable URLs, header versioning can make sense. You can support **both during a transition period**, but you must define rules for **when the path says v1 while the header says v2**.

### Recommendation: Standardize on One Internal Canonical Key

Even if the public API supports both mechanisms, the backend should receive a **canonical internal version context determined by the Gateway** (for example `X-Resolved-Api-Version: 1`), rather than trusting both the client's raw path and raw header independently. This internal header **must be reset by the Gateway** and **is not proof of identity**; the backend still authenticates the caller and verifies permissions.

## 4. Routing Flow and Three Trust Boundaries

~~~mermaid
flowchart TD
    C["Client: URL or X-API-Version"] --> E["Ingress / edge reverse proxy"]
    E --> S["Spring Security / request validation"]
    S --> R{"SCG Route predicates"}
    R -->|"Path /api/v1/catalog"| V1["Route catalog-v1"]
    R -->|"Path /api/v2/catalog"| V2["Route catalog-v2"]
    R -->|"Header X-API-Version: 1"| H1["Route catalog-header-v1"]
    R -->|"Header X-API-Version: 2"| H2["Route catalog-header-v2"]
    V1 --> F["Rewrite path + normalize upstream headers"]
    V2 --> F
    H1 --> F
    H2 --> F
    F --> U["Approved Catalog upstream"]
    U --> O["Response status/headers/body"]
    O --> C
~~~

The routes above are **four sample branches**, not four mandatory backends. When a route is selected:

1. **Inbound boundary:** The client controls the URL and request headers. Never treat `X-API-Version` as trusted authorization data.
2. **Gateway boundary:** Route predicates determine the **contract**; filters rewrite the path and replace Gateway-owned headers; Spring Security enforces permissions.
3. **Outbound boundary:** The SCG HTTP client calls an approved upstream URI/service. The backend receives the normalized request and verifies identity and resource authorization on its own.

A request that **matches no route** can terminate at the Gateway (for example with 404) with zero calls to the backend. A request blocked by Spring Security (401/403) should also produce zero outbound HTTP attempts. These scenarios must be measured separately in tests rather than lumping every error together as “backend 404”.

## 5. Designing the Contract and Routing Table Before Writing YAML

Assume Catalog exposes:

- **v1:** `{"id":"42","price":1000}`.
- **v2:** `{"id":"42","price":{"amount":1000,"currency":"VND"}}`.

Each version's backend receives the same internal path:

~~~text
GET /items/42?lang=vi
~~~

Routing plan:

| Client request | Version | Gateway route ID | Backend URI | Backend path |
| --- | --- | --- | --- | --- |
| `GET /api/v1/catalog/items/42` | 1 | `catalog-path-v1` | `http://catalog-v1.internal:8080` | `/items/42` |
| `GET /api/v2/catalog/items/42` | 2 | `catalog-path-v2` | `http://catalog-v2.internal:8080` | `/items/42` |
| `GET /api/catalog/items/42` + `X-API-Version: 1` | 1 | `catalog-header-v1` | `http://catalog-v1.internal:8080` | `/items/42` |
| `GET /api/catalog/items/42` + `X-API-Version: 2` | 2 | `catalog-header-v2` | `http://catalog-v2.internal:8080` | `/items/42` |

In the lab, both URIs must be replaced with the addresses of **backend stubs**. In production, hostnames must come from controlled configuration/discovery, never from a client-supplied query parameter or header. If internal TLS is needed, use `https://...` and configure hostname/certificate verification; the HTTP URIs in the example are solely for route illustration.

### Decisions to Make Up Front

1. Are only **v1 and v2** supported, or is there a default version?
2. Is a missing header a 400 error, or does it use a documented default?
3. Do path-versioned endpoints also accept the header? If so, how are conflicts handled?
4. For an unknown version `v3`, which status code (400/404/406/410) does the contract specify?
5. Do both backend versions share the same authentication/scope/tenant model?
6. Do CDN and browser caches distinguish the two versions in their cache keys?
7. When retiring v1, how are the response and Sunset/deprecation timeline communicated?

Every answer should be captured in the **test matrix**, not only in a wiki.

## 6. Configuring Spring Cloud Gateway: Path-Based Routes

In Gateway Server WebFlux, the `Path` route predicate selects routes based on the HTTP request path. Each route has an `id`, `uri`, `predicates`, and optionally `filters`.

### 6.1. Two Explicit v1/v2 Routes

This is **one** complete configuration file for the lab, combining both path and header strategies so they can be tested together. The four routes **do not overlap** because the two groups use distinct path patterns.

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            # OPTION A: version is in the path.
            - id: catalog-path-v1
              order: 0
              uri: ${catalog.v1-base-url}
              predicates:
                - Path=/api/v1/catalog/**
                - Method=GET
              filters:
                - StripPrefix=3
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,1
                - SetResponseHeader=X-Resolved-Api-Version,1

            - id: catalog-path-v2
              order: 0
              uri: ${catalog.v2-base-url}
              predicates:
                - Path=/api/v2/catalog/**
                - Method=GET
              filters:
                - StripPrefix=3
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,2
                - SetResponseHeader=X-Resolved-Api-Version,2

            # OPTION B: version is in X-API-Version.
            - id: catalog-header-v1
              order: 0
              uri: ${catalog.v1-base-url}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-API-Version, ^1$
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,1
                - SetResponseHeader=X-Resolved-Api-Version,1

            - id: catalog-header-v2
              order: 0
              uri: ${catalog.v2-base-url}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-API-Version, ^2$
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,2
                - SetResponseHeader=X-Resolved-Api-Version,2

catalog:
  v1-base-url: http://127.0.0.1:9001
  v2-base-url: http://127.0.0.1:9002
~~~

**Ports 9001/9002 are local examples only.** In real tests, use backend stubs on ephemeral ports injected via `@DynamicPropertySource`. In production, declare URIs from a controlled configuration source or `lb://` with verified discovery integration. Never take an upstream URI from a client-sent header such as `X-Backend-Url`.

### 6.2. Why StripPrefix=3 for Path Versioning?

Given the request:

~~~text
/api/v1/catalog/items/42?lang=vi
  1   2      3      4    5
~~~

The first three path segments are `api`, `v1`, and `catalog`. `StripPrefix=3` removes them so the backend receives:

~~~http
GET /items/42?lang=vi HTTP/1.1
X-Resolved-Api-Version: 1
~~~

The query string `lang=vi` does not become a path segment; the filter preserves it as expected. Even so, **paths containing special encoding, encoded slashes, plus signs, or double slashes** can be affected by the URI parser, upstream proxies, and the Spring Cloud Gateway version; test raw URIs on the actual runtime.

If backend v1 requires `/v1/items/42` instead of `/items/42`, do not reuse `StripPrefix=3` as-is: adjust the rewrite rule or the backend contract. Do not “fix” it by rewriting at ingress and stripping again in SCG without a clear path diagram.

### 6.3. Both Directions: SetRequestHeader and SetResponseHeader

| Filter | Recipient | Purpose |
| --- | --- | --- |
| `RemoveRequestHeader=X-API-Version` | **Upstream request** | Removes the raw client header after the Gateway has selected the version |
| `SetRequestHeader=X-Resolved-Api-Version,1` | **Upstream request** | Overwrites the canonical Gateway-managed header |
| `SetResponseHeader=X-Resolved-Api-Version,1` | **Client response** | Communicates the contract version that actually served the route |
| `StripPrefix=3` | **Upstream request path** | Removes the version prefix before calling the backend |

Specifically, `SetRequestHeader` **replaces the value**; `AddRequestHeader` typically **appends a value**, which can cause the backend to receive two different versions if the client sends a spoofed header first. The `X-Resolved-Api-Version` header remains strictly internal metadata and **is not proof that the client is authorized to call the API**.

### 6.4. Prefix Root and Trailing Slashes

`Path=/api/v1/catalog/**` is used to match resources beneath the prefix. Behavior on `/api/v1/catalog`, `/api/v1/catalog/`, or requests with encoded slashes depends on the path matcher/version and trailing-slash configuration. If the contract permits calling the collection root, **write dedicated tests** and consider adding explicit patterns; never assume all variants match identically.

## 7. Header-Based Configuration: Same URL, Different Route

In the `catalog-header-v1` and `catalog-header-v2` routes from Section 6, the request path is identical:

~~~text
/api/catalog/items/42
~~~

The Gateway differentiates them using the **Header route predicate**:

~~~yaml
# Excerpt of predicates in the same route:
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-API-Version, ^1$
~~~

A header value of `1` selects v1; `2` selects v2, provided the request satisfies all predicates on the corresponding route.

### 7.1. Anchored Regular Expressions

`Header=X-API-Version, ^1$` applies a regex to the **header value**. The `^` and `$` anchors enforce an **exact value** of `1`, preventing accidental matches on values such as `10`, `v1`, or `preview-1`.

| Header sent by client | Should v1 route match? | Should v2 route match? |
| --- | --- | --- |
| `X-API-Version: 1` | Yes | No |
| `X-API-Version: 2` | No | Yes |
| `X-API-Version: 10` | No | No |
| `X-API-Version: v1` | No | No |
| `X-API-Version: 1,2` | No under exact regex | No under exact regex |
| Missing header | No | No |
| Two header fields `1` and `2` | **Risk** that each route matches one value | **Risk** that each route matches one value |

The last row is critical: some Header predicate implementations evaluate **each value across multiple HTTP header values**. If a client sends repeated `X-API-Version` headers—one with `1` and one with `2`—one route can match `1` while another matches `2`. Therefore, **exact regex matching does not replace duplicate-header validation**. When multiple version values are present, return an error per the contract **before route selection** (see Section 9).

### 7.2. StripPrefix=2 for Header Versioning

~~~text
/api/catalog/items/42?lang=vi
  1      2     3    4
~~~

Here there are only two prefix segments, `api` and `catalog`; `StripPrefix=2` reduces the path to `/items/42`. If you accidentally use `StripPrefix=3` as in path versioning, the request becomes `/42` and the backend returns 404.

### 7.3. Normalize Header Versions Before the Backend

In the Section 6 configuration:

~~~text
Client:   X-API-Version: 1
            |
SCG:      Header predicate selects catalog-header-v1
            |
SCG:      RemoveRequestHeader: X-API-Version
            |
SCG:      SetRequestHeader: X-Resolved-Api-Version: 1
            |
Backend:  X-Resolved-Api-Version: 1
~~~

As a result, the backend does not need to parse varied client version formats itself. However, **the backend should only trust the version from an authenticated route/config rather than any client able to reach the backend directly**. If the backend relies on the canonical header to pick a contract while remaining directly reachable, a client could forge that header; enforce appropriate network policies, mTLS/service identity, or backend validation.

### 7.4. Header Routing and Browser Behavior

A cross-origin browser HTTP fetch sending a custom `X-API-Version` header can trigger a **CORS preflight OPTIONS** request. The route accepts only `Method=GET`, whereas the preflight uses `OPTIONS` and typically **does not carry `X-API-Version` in the same form as the actual GET**. Configure CORS at the ingress/Gateway/Spring Security layer to handle `OPTIONS` properly—**do not force preflight requests to satisfy the GET Header predicate**.

## 8. Route Matching Is Logical AND; Route Order Is Not a Business Fallback

In SCG, predicates within a route are combined with logical **AND**. For the route:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-API-Version, ^2$
~~~

the request must simultaneously have a valid path, method GET, and a valid version header value to match **that route**. This is not “Path OR Method OR Header”.

### 8.1. Avoid Catch-All Routes Swallowing Versionless Requests

Dangerous example:

~~~yaml
# ANTI-PATTERN when no default version is approved.
- id: catalog-catch-all
  uri: http://catalog-v2.internal:8080
  predicates:
    - Path=/api/catalog/**
~~~

A request missing `X-API-Version` can fall into the catch-all route and be sent to v2, causing clients that declared no version to receive an unexpected new contract. In API versioning, **failing to match is usually safer than silently switching contracts**, unless an explicit default has been published.

### 8.2. `order` Does Not Replace Version Validation Policy

Routes have an `order` field; in standard route resolution, lower values have higher priority. Nevertheless:

- Routes designed to be **non-overlapping** are far easier to maintain than routes relying on ordering.
- If two routes match simultaneously, ordering may pick one of them; this is not proof that the client cleanly declared a single version.
- When multiple routes share the same `order`, do not rely on declaration order or unspecified `RouteDefinitionLocator` internals as a business contract.
- A global `Path=/**` route can shadow versioned routes if priorities are misconfigured.
- Spring Security/WebFilters and route predicates run at **different layers**; route order does not alter authorization.

**Preferred design:** A clear, mutually exclusive set of predicates, a validator for ambiguous/missing versions, and regression tests covering route IDs and backends. `order` is a tool for managing route priority, not a mechanism for picking “whichever version is newer”.

### 8.3. A Route Match Does Not Prove the Backend Will Respond Correctly

After matching a route, the Gateway must still resolve the URI/`lb://` service instance, acquire an outbound connection, forward headers/body, and receive a response. The backend might:

- Be unavailable → 502/503 per transport policy.
- Return 404 due to a wrong `StripPrefix` or a nonexistent item.
- Return a legitimate operational/business 503/429.
- Return JSON from the wrong version because the service deployment/config is out of sync.

**Tests must inspect what the backend actually received**, not merely assert a route match or an HTTP 200 response.

## 9. Handling Missing, Malformed, and Conflicting Headers with a WebFilter

Route predicates **select routes**; they are not an API validator that emits a contract-defined error payload. When a header fails to match a route, the Gateway normally continues searching other routes; if none match, the response is typically 404. If you want to return **400 Bad Request** for missing, invalid, or conflicting versions, implement **a dedicated validation step**, cover it with tests, and position it properly in the pipeline.

### 9.1. Lab Contract

| Scenario | Intended behavior |
| --- | --- |
| `GET /api/v1/catalog/items/42` without version header | Allow through, select path v1 |
| `GET /api/v1/catalog/items/42` + header `1` | Allow through, select path v1; strip raw header before backend |
| `GET /api/v1/catalog/items/42` + header `2` | Return **400**, do not call backend |
| `GET /api/catalog/items/42` without header | Return **400**, do not silently select v1 or v2 |
| `GET /api/catalog/items/42` + header `3` | Return **400** under the lab custom-header contract |
| `GET /api/catalog/items/42` + two values `1` and `2` | Return **400** as ambiguous |
| `GET /api/v3/catalog/items/42` | **404** because no v3 path route exists, assuming no catch-all |
| `OPTIONS /api/catalog/items/42` (CORS preflight) | Pass through to CORS/security handling, do not require version header |

### 9.2. Example WebFlux WebFilter for Version Contract Validation

~~~java
import java.util.List;

import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class ApiVersionValidationWebFilter implements WebFilter {

    private static final String HEADER = "X-API-Version";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    ) {
        // Do not force OPTIONS preflight or other methods into this GET contract.
        if (!HttpMethod.GET.equals(exchange.getRequest().getMethod())) {
            return chain.filter(exchange);
        }

        String path = exchange.getRequest().getURI().getRawPath();
        List<String> versions =
                exchange.getRequest().getHeaders().get(HEADER);
        String fromPath = versionInPath(path);

        if (fromPath != null) {
            // Path already specifies v1/v2; if a header is present, it must be consistent.
            if (versions != null &&
                    (versions.size() != 1
                    || !fromPath.equals(versions.get(0)))) {
                return badRequest(exchange);
            }
        } else if (isHeaderVersionedCatalogPath(path)) {
            // For /api/catalog/**, require exactly one value: 1 or 2.
            if (versions == null || versions.size() != 1
                    || (!"1".equals(versions.get(0))
                    && !"2".equals(versions.get(0)))) {
                return badRequest(exchange);
            }
        }

        return chain.filter(exchange);
    }

    private static String versionInPath(String path) {
        if (path.equals("/api/v1/catalog")
                || path.startsWith("/api/v1/catalog/")) {
            return "1";
        }
        if (path.equals("/api/v2/catalog")
                || path.startsWith("/api/v2/catalog/")) {
            return "2";
        }
        return null;
    }

    private static boolean isHeaderVersionedCatalogPath(String path) {
        return path.equals("/api/catalog")
                || path.startsWith("/api/catalog/");
    }

    private static Mono<Void> badRequest(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    }
}
~~~

This example **returns no error body**; it simply illustrates an easily testable validator for two versions and one path group. If your API requires `application/problem+json` per RFC 9457, use appropriate error handling to emit the proper body, status, and headers without writing raw tokens into responses or logs.

**Limitations to understand:**

1. `WebFilter` is a **WebFlux** component running at the web layer rather than a `GatewayFilter` scoped solely to a matched route. Apply it only to the exact paths and methods you intend to enforce.
2. It does not replace Spring Security: the ordering between security filters and this validator determines whether a request with both invalid authentication and an invalid version receives 400 or 401/403.
3. Do not use the raw path matching shown here as an authorization rule. Servlet, Netty, and ingress layers may handle encoded slashes, double slashes, and percent encoding differently; test and normalize paths at the proper boundary.
4. Versions other than `v1`/`v2` in the **path** are not intercepted by this validator; they simply fail to match routes. To return 410 or 400 for retired versions, define an explicit tombstone/error route.
5. A single HTTP header field `X-API-Version: 1,2` is **one string** and is also rejected. Two separate HTTP header fields are rejected because `versions.size() != 1`.
6. If your organization uses other custom filters to rewrite paths before validation, document which stage path is inspected; never assume the raw URI matches every route representation.

### 9.3. Why Not Use a Catch-All Route to Return 400?

You could create a lower-priority `Path=/api/catalog/**` route and return an error in a `forward:` handler, but you must ensure it **never shadows valid routes**, never triggers outbound calls, and does not conflict with security. For validating a single header, an explicit `WebFilter` or validation component is usually easier to audit. In systems with many API versions, a shared version-negotiation policy works well when backed by a complete route-conflict matrix.

## 10. Choosing HTTP Status Codes for Invalid or Retired Versions

No single HTTP status code is mandated for every API versioning scheme. What matters is **public documentation, consistent encoding, and distinguishing client input errors from backend failures and migration behavior**.

| Case | Candidate status | Interpretation |
| --- | --- | --- |
| Missing `X-API-Version` when required | **400** | Client omitted a required parameter/header per contract |
| Malformed or multi-valued version header | **400** | Request is invalid or ambiguous |
| Unsupported version header | **400** or dedicated policy status | Do not silently upgrade or downgrade the version |
| Nonexistent path `/api/v3/...` | **404** (common) | No route exists for that URL version |
| Retired version, actively announced as discontinued | **410 Gone** if using a tombstone route | Send only when intentionally signaling the route/resource is permanently gone |
| `Accept` content negotiation has no matching representation | **406 Not Acceptable** when semantically appropriate | Fits content negotiation, not automatically emitted by a Header predicate |
| Client lacks permission for the version | **401/403** per security contract | A valid version does not grant access |
| Backend unavailable | **502/503/504** depending on failure and policy | Never report “invalid version” for an actual transport/backend failure |

### Never Default Silently to “Latest” Without a Contract

Some teams want an empty header to automatically pick the **latest version**. That sounds convenient, yet creates real hazards:

- Changes in v2 semantics can break older clients without those clients changing a single request.
- A shared cache on the same URL may store the newer representation and serve it to incompatible clients.
- During rolling deployments, Gateway replicas could disagree on the default version.
- Error rates may spike for only a subset of clients, making root cause detection harder.

If you genuinely need a default, **pin it to an explicit published version** (for instance, v1 until a scheduled migration milestone), document the cutoff, and write tests for the transition. Never use `latest` as an alias that shifts automatically with each deployment.

### Error Responses Should Help Clients Fix Requests

With custom-header versioning, an error payload might look like this:

~~~json
{
  "type": "https://api.example.test/problems/invalid-api-version",
  "title": "Invalid API version",
  "status": 400,
  "detail": "Use one X-API-Version header with value 1 or 2."
}
~~~

This is an **illustrative contract**, not a body automatically produced by the `WebFilter` in Section 9. If you choose to support `application/problem+json`, implement proper content type and serialization while ensuring backend URLs, security exceptions, and credentials never leak into error payloads.

## 11. Path Rewriting, Query Preservation, and URI Encoding

Within a Gateway stack, multiple layers can alter the URI: ingress, Spring Cloud Gateway `StripPrefix`/`RewritePath`, the HTTP client, and the backend router. Versioned routing easily breaks if two layers modify the same segment.

### 11.1. Comparing Paths Before and After Filters

| Client path | Route | StripPrefix | Expected backend path |
| --- | --- | --- | --- |
| `/api/v1/catalog/items/42` | `catalog-path-v1` | 3 | `/items/42` |
| `/api/v2/catalog/items/42` | `catalog-path-v2` | 3 | `/items/42` |
| `/api/catalog/items/42` + header `1` | `catalog-header-v1` | 2 | `/items/42` |
| `/api/catalog/items/42` + header `2` | `catalog-header-v2` | 2 | `/items/42` |

### 11.2. Query Strings and Percent Encoding Are Part of the Contract

~~~http
GET /api/v2/catalog/items/42?lang=vi&tag=a%2Bb HTTP/1.1
X-API-Version: 2
~~~

The backend may need to distinguish `tag=a%2Bb` (a literal plus after decoding) from `tag=a+b` (commonly interpreted as a space in form-style query parsing). If a custom rewrite decodes and re-encodes incorrectly, request signatures, cache keys, or search semantics can change.

Therefore, test all of the following:

- Empty queries, multiple parameters, and repeated parameters.
- `+`, `%2B`, `%20`, and UTF-8 percent-encoded Unicode characters.
- Encoded slashes `%2F`, double slashes, trailing slashes, and semicolons if relevant to the contract.
- Path variables with special characters, which some ingress, Servlet, or Netty versions may reject before Gateway routing.
- The raw query/backend URI recorded by the stub, **not only decoded `getParameter()` values**.

Avoid naive string replacements like `path.replace("/v1", "")` on uncontrolled raw URLs: they can accidentally strip `v1` from the middle of another segment or corrupt slashes. Use explicit filters/path rules and test encoded edge cases.

### 11.3. Double-Rewrite Bugs from Ingress

~~~text
Client:         /api/v1/catalog/items/42
Ingress:        strip /api  -> /v1/catalog/items/42
SCG Path:       /api/v1/catalog/**   <-- DOES NOT MATCH
Backend HITS:   0
~~~

To avoid this, designate **a single owner** for rewriting:

1. Either ingress/Gateway API matches only host/path and forwards the full prefix intact to SCG, letting SCG strip it as in the YAML.
2. Or ingress rewrites according to a strict contract, and SCG route predicates/filters are authored for the already-rewritten path.

**Do not assume the Path predicate strips the prefix by itself.** It selects the route; `StripPrefix`/`RewritePath` is what mutates the request path.

### 11.4. When RewritePath Is Genuinely Needed

When the backend path has a different structure rather than simply dropping leading segments, use `RewritePath` with appropriate regex and capture groups. For example, if v2 `/api/v2/catalog/items/42` needs to become `/inventory/items/42`:

~~~yaml
# Excerpt of a standalone filter for illustration; DO NOT combine with StripPrefix on that route.
filters:
  - RewritePath=/api/v2/catalog/(?<segment>.*), /inventory/$\{segment}
~~~

In YAML/Spring property binding, escaping the replacement as `$\{segment}` (the `$` escaped with a backslash as shown in SCG documentation examples) prevents Spring from treating it as a property placeholder. Exact escaping rules depend on how YAML/strings are parsed, so always **test the actual URI sent to the backend** rather than relying on visual inspection. Never combine a `RewritePath` expecting the original prefix with a `StripPrefix` that has already removed it.

## 12. Cache, Vary, and ETag: The Hardest Part of Header Versioning

With path versioning, the two contracts normally have **two distinct URIs**:

~~~text
/api/v1/catalog/items/42
/api/v2/catalog/items/42
~~~

With header versioning, the URI is **identical**, yet the response body differs:

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-API-Version: 1
~~~

~~~json
{"id":"42","price":1000}
~~~

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-API-Version: 2
~~~

~~~json
{"id":"42","price":{"amount":1000,"currency":"VND"}}
~~~

If a shared cache or CDN keys **only on the URL**, a v2 client may receive cached v1 JSON and vice versa. For caches that honor HTTP semantics, the response must declare that the representation varies by `X-API-Version`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: X-API-Version
ETag: "catalog-v2-item-42-r7"
~~~

### 12.1. `Vary` Is Part of the Response Contract

- `Vary: X-API-Version` tells caches to select the cached response according to that request header's value.
- If the response also varies by `Accept-Encoding`, `Accept-Language`, or `Origin` for CORS, preserve those valid dimensions—**do not overwrite the entire `Vary` header with a single new value**.
- `Vary: *` has special semantics; do not append other values alongside it arbitrarily.
- Some CDNs enforce custom cache policies or omit custom headers from their cache key unless configured; **configure the CDN and test against real HTTP caches**.
- `Vary` does not replace authentication or cache privacy. Personalized or secret-bearing responses may require `Cache-Control: private, no-store`.

### 12.2. Do Not Blindly Use `SetResponseHeader=Vary`

A configuration such as:

~~~yaml
# ANTI-PATTERN if upstream already sends Vary: Accept-Encoding, Origin.
filters:
  - SetResponseHeader=Vary,X-API-Version
~~~

can **overwrite and lose** existing `Vary` values emitted by the backend, Spring Security, or CORS. In header-versioned systems, use a response policy that **merges `Vary` tokens** (such as a tested response decorator/custom filter) or set it directly at the backend origin for each representation.

### 12.3. Example `GlobalFilter` That Appends `Vary` Without Deleting Existing Values

~~~java
import java.util.Arrays;
import java.util.List;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class ApiVersionVaryGlobalFilter
        implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        Route route = exchange.getAttribute(
                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);

        if (route == null ||
                !route.getId().startsWith("catalog-header-v")) {
            return chain.filter(exchange);
        }

        exchange.getResponse().beforeCommit(() -> {
            HttpHeaders responseHeaders =
                    exchange.getResponse().getHeaders();
            List<String> fields =
                    responseHeaders.get(HttpHeaders.VARY);

            boolean alreadyCovered = fields != null
                    && fields.stream()
                    .flatMap(field ->
                            Arrays.stream(field.split(",")))
                    .map(String::trim)
                    .anyMatch(token -> token.equals("*")
                            || token.equalsIgnoreCase("X-API-Version"));

            if (!alreadyCovered) {
                responseHeaders.add(
                        HttpHeaders.VARY, "X-API-Version");
            }

            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

**Purpose:** When a response passes through a `catalog-header-v*` route, adds a valid `Vary` entry if `X-API-Version` or `*` is not already present. This **does not verify CDN cache policies**, does not guarantee the upstream builds proper ETags, and does not replace `Cache-Control` handling for sensitive data. A `GlobalFilter` runs only when a request matches a Gateway route; requests blocked early by Security or missing routes will not necessarily pass through it.

### 12.4. ETags Must Represent the Exact Versioned Representation

Since the v1 body has integer `1000` and the v2 body has an object, the two byte representations differ. A backend must never casually reuse the **same strong ETag** across them. If a Gateway filter transforms JSON, the `ETag`, `Content-Length`, `Content-Encoding`, and `Content-Type` must match the **actual** body sent to the client.

### 12.5. Conditional GET and Status 304

When a client sends `If-None-Match`, the backend or cache must validate against the **matching API version**. A 304 response missing `Vary` or `ETag` can cause caches to select the wrong representation. Test v1→v2 on the same URL with different validators and repeated requests; do not test only `GET` 200.

## 13. Header Versioning vs. `Accept`/Media-Type Versioning

Beyond custom headers like `X-API-Version`, HTTP provides **content negotiation** through `Accept` and `Content-Type`. For example:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Accept: application/vnd.example.catalog.v2+json
~~~

A backend can select the v2 representation upon seeing that media type; if no matching representation exists, **406 Not Acceptable** may be the right status. However, this is **a different versioning protocol** and is not automatically equivalent to `X-API-Version: 2`.

### 13.1. Why a Simple `Accept` Regex Is Not a Full Parser

~~~yaml
# Illustrates route concept ONLY; NOT full HTTP content negotiation.
predicates:
  - Header=Accept, .*application/vnd\.example\.catalog\.v2\+json.*
~~~

An `Accept` header value can contain **multiple media ranges**, parameters, `q=` quality factors, wildcards, and varied ordering. A regex checking only for the `v2` substring could select v2 even when the client explicitly sent `q=0` (not acceptable) or gave another media type higher priority. It can also match malformed strings.

If a product adopts `Accept`-based versioning, use a **parser/negotiation strategy that respects HTTP semantics**, tested with multiple `Accept` values and quality factors, or keep negotiation policy in the appropriate backend/app layer. The Spring Cloud Gateway `Header` predicate suits **simple, exact/regex-defined version headers**, not full HTTP content negotiation.

### 13.2. Request `Content-Type` Differs from Response `Accept`

- `Accept` indicates which response representation the client wants.
- Request `Content-Type` indicates the format of the body the client is sending.
- An API v2 route may accept `Content-Type: application/json` and return `application/vnd.example.catalog.v2+json` if specified by the contract.
- Never treat request `Content-Type` as the version selector if your contract specifies `X-API-Version` or the path.

### 13.3. Avoid Multiple Sources of Truth

Example request:

~~~http
GET /api/v1/catalog/items/42 HTTP/1.1
X-API-Version: 2
Accept: application/vnd.example.catalog.v2+json
~~~

Here there are **three conflicting signals**. If a system supports multiple negotiation methods during migration, define **which takes precedence and which cases are rejected**, and test them thoroughly. The easiest policy to govern is usually **one authoritative source for contract selection**, requiring any secondary hints to agree with it.

## 14. Security: Version Is a Contract Choice, Not Proof of Authorization

The client controls `/api/v2/...` and `X-API-Version: 2`. Therefore, choosing an API version **does not authenticate a user**, prove tenant membership, grant `ROLE_ADMIN`, or replace resource authorization.

### 14.1. Spring Security Must Cover Every Version

Example requirements:

- Catalog GET v1/v2 is public.
- Orders GET v1/v2 requires scope `orders.read`.
- All other requests are denied by default.

For **Server WebFlux** and a Bearer-only Resource Server application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET,
                                "/api/v1/catalog/**",
                                "/api/v2/catalog/**",
                                "/api/catalog/**")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/v1/orders/**",
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Only appropriate for stateless APIs that use Bearer tokens exclusively.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

**Note:** This illustrates security rules for the listed routes only; it does not cover all CORS/preflight, Actuator/health, error handling, or authorization rules of a production system. If Kubernetes probes call health endpoints, apply a separate probe policy on the management network. If browsers use cookie/session authentication, **never disable CSRF unconditionally**. Configure the resource-server JWT issuer, JWKS, signature verification, `aud` (per-API audience), expiration, and authority mapping properly; validators may also need per-release audience checks.

If the Gateway routes `/api/v2/orders/**` while Spring Security protects only `/api/v1/orders/**`, v2 becomes an **authorization bypass**. Security matchers must be updated alongside route definitions. Write tests across every version, non-GET methods, encoded/trailing-slash paths, and default/catch-all routes.

### 14.2. The Backend Must Still Enforce Business Authorization

The Orders backend must enforce **principal/tenant/resource ownership**; a user holding `orders.read` is not automatically entitled to read any other user's orders. If the backend can be reached outside the Gateway or via another route, it cannot simply trust `X-Resolved-Api-Version` and skip authentication.

### 14.3. Token Forwarding Must Not Be Driven by Version Alone

Separate v1/v2 backends may require **different audiences** or distinct service credentials. Do not automatically forward a client's bearer token to every upstream just because a route changed from v1 to v2:

- Pass an **access token** only to resource servers permitted to receive it under the proper issuer, audience, and scopes.
- Consider token exchange or service credentials for calls crossing trust boundaries.
- Do not send refresh tokens, ID tokens, or session cookies to backends that do not need them.
- Use TLS/mTLS and hostname verification on sensitive hops.
- Never log raw `Authorization` or `Cookie` headers in logs, traces, or metrics.
- When a public Catalog application needs no user identity, strip credentials before outbound forwarding if policy allows.

### 14.4. `X-API-Version` Is a Client-Supplied Header

It must never be used as:

- A principal identity, tenant ID, or role.
- A signature/secret proving the caller is the official mobile app.
- A signal granting access to admin APIs.
- The sole trusted input for rate-limit keys.
- A dynamic URL/hostname for selecting arbitrary backends.

Even Gateway-set headers such as `X-Resolved-Api-Version` are **only trustworthy when the backend accepts them exclusively from an authenticated Gateway with no direct bypass path**.

## 15. Rate Limiting, Retry, Circuit Breakers, and Version Isolation

API version routing pairs with Spring Cloud Gateway resilience features, but **versioning must never become a random load distribution trick or a way to bypass quotas**.

### 15.1. Rate Limiting Must Account for Clients Switching Versions

If the quota is 100 requests/minute/user across the entire Catalog API, a client must not exceed it by splitting traffic simultaneously across:

~~~text
50 req/min -> /api/v1/catalog
50 req/min -> /api/v2/catalog
50 req/min -> /api/catalog, X-API-Version: 1
~~~

You must decide whether quotas apply per **operation/principal/tenant** or per **principal + version**. If a client-supplied version is part of the key, callers can multiply their quota by rotating versions. For distributed rate limiters, verify both the key resolver and the shared store across Gateway replicas.

### 15.2. Retries Must Not Switch Versions After Errors

A v1 request that receives 503 from Catalog v1 **must not automatically fail over to Catalog v2** just to return 200: the v2 JSON structure can break the v1 client. Retries, load balancing, and circuit breaker fallbacks must preserve the **exact API contract**.

| Incident | Contract-safe action |
| --- | --- |
| v1 instance A timeout | Bounded retry to a **compatible v1 instance** if method/idempotency permits |
| v1 backend 503 | Preserve 503 or return a designed v1 fallback |
| v2 circuit OPEN | Return v2 error/fallback; **never return a v1 body masquerading as v2** |
| v1 already sunset | Return the published retirement response; never silently route to v2 |
| POST order creation reset after backend may have committed | Do not retry automatically without an idempotency key/deduplication |

### 15.3. Multi-Layer Retry Amplification Formula

If the client retries up to 3 attempts, the Gateway retries up to 2 attempts per client call, and a backend SDK retries 2 attempts, a single logical operation can generate up to:

\[
3 \times 2 \times 2 = 12\ \text{outbound attempts}
\]

This is an upper-bound example for sequential retry layers, excluding fan-out or hedging. Monitor **attempt counts, status codes, latency, and overall deadlines**—do not look only at the final HTTP 200.

### 15.4. Circuit Breakers and Contract-Aware Fallbacks

Each API version may have its own SLO, error classification, and fallback behavior. An open v2 breaker does not necessarily require opening the v1 breaker; however, shared dependencies, connection pools, or databases can cause failures to cascade across both. Do not create two breaker names and assume physical resources are isolated. Any cross-version fallback requires a **tested contract-transforming adapter**, not merely swapping the upstream URI.

## 16. API Versioning vs. Canary / Blue-Green Rollouts

Two models that are easily confused:

~~~mermaid
flowchart TD
    C["Client selected API v1"] --> G["Gateway route v1"]
    G --> W{"Canary within the same v1 contract"}
    W -->|"90%"| OLD["Backend build A: returns v1 JSON"]
    W -->|"10%"| NEW["Backend build B: still returns v1 JSON"]
    V2["Client selected API v2"] --> G2["Gateway route v2"]
    G2 --> NEW2["Backend supporting v2 JSON"]
~~~

**API versioning** selects a **contract**. **Canary** selects a **build/implementation** while upholding the promised contract. If 10% of v1 requests are weighted to a new build that only speaks v2 JSON, the rollout breaks compatibility rather than implementing valid version routing.

### Strategy Overview

| Strategy | Goal | Requirement |
| --- | --- | --- |
| Path/header version routes | Select v1 or v2 contract per client | Unambiguous route predicates |
| Canary v1 build B | Test a new implementation while keeping the v1 contract | Contract tests and separate traffic/metrics |
| Blue-green backend v2 | Replace v2 instances during rollout | Both blue and green satisfy the v2 contract |
| Shadow/mirror | Measure a new backend without using its response | No side effects or PII leaks |
| Client migration v1→v2 | Consumers upgrade contracts on schedule | SDK/docs, observability, deprecation |

If you plan to use the `Weight` route predicate or weighted backends, verify the feature and configuration against your exact SCG version; never use `Weight` to choose between v1 and v2 **when the client has explicitly requested a version**. Traffic weighting is also subject to sample size and algorithm behavior; 90/10 does not guarantee an exact 9/1 split in every window of 10 requests.

## 17. Service Discovery and Kubernetes Environments

The URIs in the Section 6 YAML are static:

~~~yaml
catalog:
  v1-base-url: http://127.0.0.1:9001
  v2-base-url: http://127.0.0.1:9002
~~~

In Kubernetes, you can use separate **Service DNS** names for the two contract implementations:

~~~yaml
catalog:
  v1-base-url: http://catalog-v1.apps.svc.cluster.local:8080
  v2-base-url: http://catalog-v2.apps.svc.cluster.local:8080
~~~

Or point the route to SCG service discovery:

~~~yaml
# Excerpt of a RouteDefinition, only when LoadBalancer/ServiceInstances are configured.
- id: catalog-path-v2
  uri: lb://catalog-v2
  predicates:
    - Path=/api/v2/catalog/**
    - Method=GET
  filters:
    - StripPrefix=3
    - SetRequestHeader=X-Resolved-Api-Version,2
~~~

`lb://catalog-v2` **is not automatically equivalent to Kubernetes DNS**: it requires Spring Cloud LoadBalancer and an appropriate `ServiceInstance` supplier or discovery integration. Conversely, when a route uses a Kubernetes Service FQDN, the HTTP client routes via cluster DNS/network routing and may not need client-side `lb://`.

### What If Both Versions Share One Service?

You can have a single `catalog-service` that supports both v1 and v2 internally. Both routes can point to the same URI, provided the backend reads the **canonical version context** and separates the contracts cleanly. That is not an architectural flaw; it can enable shared domain logic and reduce operational overhead. The trade-off is that deploying a new build affects both versions, requiring regression tests for **both v1 and v2**.

### TLS, Host, and Forwarded Headers

- For HTTPS backends, hostname/SNI/CA trust must be configured properly; never disable hostname verification to make tests pass.
- Never use client-sent `Host` or `X-Forwarded-Host` headers to determine the backend target URI or version.
- Ingress may rewrite paths or normalize forwarded metadata; ensure SCG receives the expected prefix to match routes.
- Connection pools to v1/v2 instances must be managed alongside backend/connection lifetimes; never assume updating a DNS record immediately drains all pooled connections.
- For cross-namespace Kubernetes Services, Kubernetes RBAC/NetworkPolicy and application authorization are independent layers.

## 18. Do Gateway Server Web MVC and Proxy Exchange Apply the Same Ideas?

**Yes at the architectural level**, though you cannot copy WebFlux code or configuration verbatim:

| Aspect | Server WebFlux | Server Web MVC | Proxy Exchange |
| --- | --- | --- | --- |
| Web runtime | Reactor/WebFlux | Servlet/Spring MVC/WebMvc.fn | MVC or WebFlux controller utility |
| Route declarations | RouteDefinition YAML/Java DSL | WebMvc.fn route definitions/filters | `ProxyExchange<T>` inside a controller |
| API version matching | `Path`, `Header`, `Method` predicates | Equivalent predicates supported by the release | `@GetMapping` + handler header/path validation |
| Request path/header transform | Gateway WebFlux filters | Gateway Server MVC before/after filters | Controller/ProxyExchange URI, request headers |
| Security | `SecurityWebFilterChain` | Servlet `SecurityFilterChain` | Security of the controller stack |
| Backend HTTP client | Reactor Netty in most setups | MVC stack HTTP client/request factory | HTTP client depending on MVC/WebFlux Proxy Exchange |

On newer lines, the Gateway Server MVC namespace may be `spring.cloud.gateway.server.webmvc.routes`, while older lines use `spring.cloud.gateway.mvc.routes`. **Do not use WebFlux's `org.springframework.cloud.gateway.filter.GlobalFilter` directly in Gateway Server MVC.** Rather than translating APIs by name alone, pick one runtime and verify the starter, BOM, predicates, and filter signatures with integration tests.

With Proxy Exchange, version routing is typically expressed via `@GetMapping` or handler logic plus `ProxyExchange.header(...)`/URI mapping rather than Gateway Server `RouteDefinition` YAML. Switching to Proxy Exchange merely to write `if/else` version header checks increases application code you must maintain, so evaluate that trade-off carefully.

## 19. Deprecation, Sunset, and the API Version Lifecycle

Versioning only pays off long-term when backed by a **process to evolve and retire versions**. If v1 must stay alive forever for lack of migration telemetry, every route, backend, filter, and security policy bloats and expands the risk surface.

### 19.1. Lifecycle States

~~~mermaid
flowchart LR
    D["Design + contract tests"] --> P["Preview / limited clients"]
    P --> S["Supported"]
    S --> DE["Deprecated: migration schedule set"]
    DE --> SU["Sunset: end-of-support cutoff"]
    SU --> R["Retired: 404/410 per policy"]
~~~

| State | Primary actions | Key metrics |
| --- | --- | --- |
| Preview | Allowlisted clients; contract not broadly committed | Error rate, feedback |
| Supported | Full docs/SDK/tests, stable capacity and auth | Requests/status/latency by version |
| Deprecated | Publish v2, migration guide, freeze breaking changes on v1 | Active v1 clients remaining |
| Sunset pending | Set cutoff and handle exceptions for critical partners | Declining `v1` traffic, contacted clients |
| Retired | Remove route or serve intentional 410 tombstone handler | Residual v1 requests, support incidents |

**Deprecation does not mean immediately returning errors.** During the transition window, v1 continues serving while urging migration. Never decommission backend v1 solely because aggregate metrics look low; inspect traffic by partner, region, SDK, method, and daily/weekly/monthly cycles.

### 19.2. Using HTTP Response Headers Under a Published Contract

HTTP provides standardized mechanisms for communicating end-of-support notices, such as **Deprecation** (RFC 9745) and **Sunset** (RFC 8594). However, syntax, timing, and client/CDN support vary; your application must adhere to the standards and published docs rather than inventing a custom `deprecated: yes` header and expecting clients to interpret it.

Example **Sunset** header carrying an HTTP-date under a published policy:

~~~http
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://docs.example.test/migration/catalog-v2>; rel="deprecation"
~~~

The date above is **illustrative only**, not a real deadline. Define which versions emit the header, exact UTC timestamps, and support links. For `Deprecation`, follow the syntax matching the standard and framework version in use rather than emitting an arbitrary unverified Unix timestamp.

### 19.3. Retiring the v1 Route Safely

One approach:

1. **Announce and measure:** Track `catalog-path-v1`/`catalog-header-v1` via metrics and group consumers.
2. **Update SDKs and docs:** Reflect the new v2 JSON, schema, and errors; verify clients with tests.
3. **Canary client migration:** Intentionally move selected clients to `X-API-Version: 2` or the v2 path rather than forcing everyone at once.
4. **Sunset review:** API owners, Security, SRE, and customers confirm the cutoff date.
5. **Retirement:** Keep a short-lived 410 handler pointing to docs, or remove the route so it returns 404, according to the contract.
6. **Rollback:** If a critical client missed the upgrade, verify whether v1 can be re-enabled and whether data/contracts remain compatible.

Never keep a `catalog-path-v1` route and point its URI to v2 just to cover a missing v1 backend; that creates a **silent breaking change** and hides which clients have not migrated.

## 20. OpenAPI, SDKs, and Per-Version Usage Observability

### 20.1. Documenting Path Versions

You can maintain two independent OpenAPI documents:

~~~text
catalog-v1-openapi.yaml:
  servers: [{url: https://api.example.test/api/v1}]
  /catalog/items/{id} -> price: integer

catalog-v2-openapi.yaml:
  servers: [{url: https://api.example.test/api/v2}]
  /catalog/items/{id} -> price: {amount, currency}
~~~

This is an **abbreviated sketch**, not a complete OpenAPI file. The key point is that docs and SDKs must capture **the two distinct response schemas**, rather than merely adding `/v2` to the URL while keeping the v1 schema.

### 20.2. Documenting Header Versions

An OpenAPI parameter can describe the required header:

~~~yaml
# Excerpt inside operation.parameters, not a complete document.
parameters:
  - name: X-API-Version
    in: header
    required: true
    description: API contract version. Supported values are "1" and "2".
    schema:
      type: string
      enum: ["1", "2"]
~~~

When two versions return **different response JSON schemas on the same path and method**, structure OpenAPI so docs and SDKs genuinely distinguish them (such as version-specific API definitions or tooling-supported conditions). A standalone `enum: ["1","2"]` parameter **does not automatically make code generators emit distinct v1/v2 DTOs**.

### 20.3. Tracking Client Migration with Telemetry

| Metric / dimension | Purpose | Cardinality / Privacy |
| --- | --- | --- |
| **route ID** (`catalog-header-v1`) | Count calls per version | Bounded |
| **final status** | Detect 400/404/503 spikes during migration | Bounded |
| **upstream service** | Distinguish Catalog v1/v2 backends | Bounded by inventory |
| **client SDK version** from controlled identity/metadata | Identify clients needing migration | Use a bounded taxonomy only, not unbounded raw user agents |
| **business owner/tenant** | Contact customers yet to migrate | Avoid PII/high-cardinality metric labels; analyze in an access-controlled system |
| **response schema validation** | Catch v2 accidentally returning v1 shape | Do not log raw user payloads |
| **outbound attempts** | Detect retry storms on a specific version | Bounded version/route labels |

With Spring Cloud Gateway, `gateway.requests` and Micrometer/Actuator meters (when enabled) can provide route-level telemetry, **though exact meter names, tags, and exposure depend on the release**. Verify against your running environment instead of assuming `gateway.requests` is always active.

**Never store raw `Authorization`, `Cookie`, PII-laden queries, or user bodies in logs/traces** just to track version adoption. When you need to check a specific partner's version, use an analytics system with proper access controls and retention instead of stuffing tenant or user IDs into metric labels.

### 20.4. Distinguishing Response Provenance

A v1 request returning HTTP 404 can stem from:

~~~text
Security/cors/filter: blocked before Gateway routing
Gateway: no matching route
Gateway: route matched, but backend URI/instance unavailable
Backend v1: item 42 genuinely does not exist
~~~

Identical status codes can carry completely different meanings. When debugging, combine **backend request counters, route IDs, trace context, upstream status, and final status** to pinpoint the source. Do not collapse every versioning error into 404 and erase migration visibility.

## 21. Backend Stub: Proving Which Version the Real Backend Received

A mock controller is insufficient for testing Gateway routes. We need a real **HTTP backend stub** listening on an ephemeral loopback port that records every incoming request. Below is a lab/CI-only fixture built with JDK `com.sun.net.httpserver.HttpServer` (Java 17+).

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

final class CatalogVersionStub implements AutoCloseable {

    private final HttpServer server;
    private final String version;

    final AtomicInteger calls = new AtomicInteger();
    final AtomicReference<String> lastMethod = new AtomicReference<>();
    final AtomicReference<String> lastRawPath = new AtomicReference<>();
    final AtomicReference<String> lastRawQuery = new AtomicReference<>();
    final AtomicReference<String> lastResolved = new AtomicReference<>();
    final AtomicReference<String> lastClientHeader = new AtomicReference<>();

    CatalogVersionStub(String version) throws IOException {
        this.version = version;
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    void reset() {
        calls.set(0);
        lastMethod.set(null);
        lastRawPath.set(null);
        lastRawQuery.set(null);
        lastResolved.set(null);
        lastClientHeader.set(null);
    }

    private void handle(HttpExchange exchange) throws IOException {
        calls.incrementAndGet();
        String path = exchange.getRequestURI().getRawPath();
        lastMethod.set(exchange.getRequestMethod());
        lastRawPath.set(path);
        lastRawQuery.set(exchange.getRequestURI().getRawQuery());
        lastResolved.set(exchange.getRequestHeaders()
                .getFirst("X-Resolved-Api-Version"));
        lastClientHeader.set(exchange.getRequestHeaders()
                .getFirst("X-API-Version"));

        int status = path.endsWith("/missing") ? 404
                : path.endsWith("/busy") ? 503 : 200;

        String body;
        if (status == 404) {
            body = "{\"error\":\"NOT_FOUND\",\"version\":\""
                    + version + "\"}";
        } else if (status == 503) {
            body = "{\"error\":\"UPSTREAM_BUSY\",\"version\":\""
                    + version + "\"}";
        } else if ("1".equals(version)) {
            body = "{\"id\":\"42\",\"price\":1000"
                    + ",\"version\":\"1\"}";
        } else {
            body = "{\"id\":\"42\",\"price\":{"
                    + "\"amount\":1000,\"currency\":\"VND\"}"
                    + ",\"version\":\"2\"}";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.getResponseHeaders().set(
                "ETag", "\"catalog-v" + version + "-r1\"");
        exchange.getResponseHeaders().set(
                "Cache-Control", "public, max-age=30");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
~~~

**This is a test fixture**, not a production HTTP server. It accepts only `GET` on test paths under a simplified contract, with synthetic error status codes. Never grant the stub access to secrets or connections to production backends. With Java modules, `HttpServer` resides in the `jdk.httpserver` module.

### What the Backend Journal Must Prove

| Request to Gateway | Stub invoked | `lastRawPath` | `lastResolved` | JSON schema |
| --- | --- | --- | --- | --- |
| Path v1 | v1 | `/items/42` | `1` | `price` is a number |
| Path v2 | v2 | `/items/42` | `2` | `price` is an object |
| Header v1 | v1 | `/items/42` | `1` | `price` is a number |
| Header v2 | v2 | `/items/42` | `2` | `price` is an object |
| Missing/ambiguous header | **No stub** | None | None | Zero outbound calls |

**Note:** `lastRawPath` and `lastResolved` store only the latest request state, which suffices for sequential single-request tests. For retries or concurrent requests, use a **thread-safe request journal keyed by correlation ID** instead of inferring all attempts from a single `AtomicReference`. You can replace this fixture with WireMock or MockWebServer for deeper tests involving delays, resets, headers, and multi-attempt assertions.

## 22. HTTP Integration Test: One Gateway, Two Versions, Two Routing Mechanisms

Unit tests for individual predicates or filters are useful, but they **do not replace** tests over a real HTTP socket. The example below uses **Spring Boot `RANDOM_PORT`** for Gateway Server WebFlux, the JDK `HttpClient` for inbound requests, and two `CatalogVersionStub` instances for the v1/v2 backends.

### 22.1. Test App Setup

Place the four-route YAML from Section 6 in a test profile `application-versioning-test.yml` (or equivalent test configuration) so that `catalog.v1-base-url` and `catalog.v2-base-url` can be overridden with the ephemeral ports of the backend stubs.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("versioning-test")
@Execution(ExecutionMode.SAME_THREAD)
class VersionedCatalogGatewayIntegrationTest {

    static final CatalogVersionStub V1 = startStub("1");
    static final CatalogVersionStub V2 = startStub("2");

    @DynamicPropertySource
    static void targetUris(DynamicPropertyRegistry registry) {
        registry.add("catalog.v1-base-url", V1::baseUrl);
        registry.add("catalog.v2-base-url", V2::baseUrl);
    }

    @LocalServerPort
    int gatewayPort;

    final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private static CatalogVersionStub startStub(String version) {
        try {
            return new CatalogVersionStub(version);
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @BeforeEach
    void reset() {
        V1.reset();
        V2.reset();
    }

    @AfterAll
    static void stopStubs() {
        V1.close();
        V2.close();
    }

    private HttpResponse<String> get(
            String path,
            String... versionHeaderValues
    ) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:"
                                + gatewayPort + path))
                .timeout(Duration.ofSeconds(5))
                .GET();

        for (String value : versionHeaderValues) {
            builder.header("X-API-Version", value);
        }
        return client.send(
                builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void pathV1SelectsV1AndPreservesQuery() throws Exception {
        HttpResponse<String> response =
                get("/api/v1/catalog/items/42?lang=vi");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"price\":1000"));
        assertEquals("1", response.headers()
                .firstValue("X-Resolved-Api-Version").orElse(""));
        assertEquals(1, V1.calls.get());
        assertEquals(0, V2.calls.get());
        assertEquals("GET", V1.lastMethod.get());
        assertEquals("/items/42", V1.lastRawPath.get());
        assertEquals("lang=vi", V1.lastRawQuery.get());
        assertEquals("1", V1.lastResolved.get());
        assertNull(V1.lastClientHeader.get());
    }

    @Test
    void pathV2KeepsDifferentContract() throws Exception {
        HttpResponse<String> response =
                get("/api/v2/catalog/items/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body()
                .contains("\"price\":{\"amount\":1000"));
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
        assertEquals("2", V2.lastResolved.get());
    }

    @Test
    void headerV2SelectsV2AndReturnsVary() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/42", "2");

        assertEquals(200, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
        assertEquals("/items/42", V2.lastRawPath.get());
        assertEquals("2", V2.lastResolved.get());
        assertNull(V2.lastClientHeader.get());
        assertTrue(response.headers().allValues("Vary")
                .stream().anyMatch(
                        field -> field.toLowerCase()
                                .contains("x-api-version")));
        assertEquals("\"catalog-v2-r1\"", response.headers()
                .firstValue("ETag").orElse(""));
    }

    @Test
    void missingHeaderDoesNotSilentlyChooseLatest() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/42");

        assertEquals(400, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void repeatedHeaderOrConflictIsRejected() throws Exception {
        assertEquals(400,
                get("/api/catalog/items/42", "1", "2")
                        .statusCode());
        assertEquals(400,
                get("/api/v1/catalog/items/42", "2")
                        .statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void backend404Remains404WithoutCrossVersionFallback()
            throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/missing", "1");

        assertEquals(404, response.statusCode());
        assertTrue(response.body().contains("NOT_FOUND"));
        assertEquals(1, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void backend503IsNotAutomaticallyHidden() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/busy", "2");

        assertEquals(503, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
    }
}
~~~

**This is illustrative test code, not executed in this lesson.** A real project needs a compatible Gateway Server WebFlux starter/BOM, Spring Boot Test + JUnit 5, the four-route YAML loaded, and `ApiVersionValidationWebFilter` + `ApiVersionVaryGlobalFilter` included in component scan. Do not let security tests accidentally block Catalog requests; security integration tests should be written **separately** and must prove that 401/403 responses incur zero backend attempts.

**Configuration and lifecycle limitations:**

- `CatalogVersionStub` uses port `0` for both backends; `@DynamicPropertySource` injects the URIs before the context builds the routes.
- `@Execution(SAME_THREAD)` prevents test methods in this class from running concurrently; across multiple test classes or context caching, proper fixture ownership is also required.
- The HTTP client uses `Redirect.NEVER` so HTTP 3xx responses from backends or routes are never hidden.
- The 404/503 responses are **backend-generated HTTP responses**, not DNS/TCP/TLS exceptions; test transport failures separately.
- Exact status, body, and header behavior also depends on the filter chain and Spring Cloud Gateway version; when changing route filters or security policies, update tests to match the **contract**, not simply to turn tests green.
- These tests do not yet cover load, CORS `OPTIONS`, signed JWTs, TLS, large bodies, or retry injection. Those are separate layers and must not be inferred from the seven test methods above.

### 22.2. Testing Deliberately Spoofed Client Headers

Besides `X-API-Version`, a client could send `X-Resolved-Api-Version: attacker`. The Gateway's `SetRequestHeader` filter must **overwrite** that value before calling the backend. Add a test:

~~~java
@Test
void clientCannotOverrideCanonicalVersionHeader() throws Exception {
    HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + gatewayPort
                            + "/api/catalog/items/42"))
            .header("X-API-Version", "1")
            .header("X-Resolved-Api-Version", "attacker")
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

    assertEquals(200, response.statusCode());
    assertEquals("1", V1.lastResolved.get());
}
~~~

This snippet is **a method inside `VersionedCatalogGatewayIntegrationTest`**, not a standalone file. It proves that the version header is normalized at the Gateway HTTP hop; it does not prove that the backend authenticates the Gateway's identity via mTLS or tokens.

### 22.3. Testing Real ETags and Response Schemas

For the same item `42`:

1. Call header v1 and record the `ETag` and v1 JSON.
2. Call header v2 and record the `ETag` and v2 JSON.
3. Verify `Vary: X-API-Version` on both responses.
4. Ensure a v1 response from a simulated cache is never served when the client requests v2.
5. Send v1's `If-None-Match` when requesting v2; it must never return a 304 for the wrong representation.
6. If the contract requires CORS, verify `OPTIONS` preflight and the actual `GET` with `X-API-Version`.

Because the Section 21 backend stub does not implement conditional GET/304, **304 and cache-revalidation tests require an enhanced fixture**. Never mark them PASS until a backend or cache implementing that behavior is present.

## 23. Full Test Matrix Before Deploying API Version Routing

| ID | Scenario | Appropriate tool | Required evidence |
| --- | --- | --- | --- |
| V01 | Path v1 to backend v1 | HTTP client + stub v1 | V1 HITS=1, v2 HITS=0 |
| V02 | Path v2 to backend v2 | HTTP client + stub v2 | V2 HITS=1, v1 HITS=0 |
| V03 | Header `1` to backend v1 | HTTP client + stub | Backend sees canonical version 1 |
| V04 | Header `2` to backend v2 | HTTP client + stub | Backend sees canonical version 2 |
| V05 | Path v1 with header `2` | HTTP client | 400, zero backend calls |
| V06 | Path v2 with header `1` | HTTP client | 400, zero backend calls |
| V07 | Missing header version | HTTP client | 400, no silent fallback |
| V08 | Header version `3` | HTTP client | Contract-defined error, never routed to v1/v2 |
| V09 | Two header values `1`/`2` | HTTP client | 400, no ambiguous routing |
| V10 | Single header `1,2` | HTTP client | 400 |
| V11 | Client sends `X-Resolved-Api-Version: attacker` | Stub journal | Gateway overwrites with 1/2 |
| V12 | Request path received by backend | Stub raw-path journal | `/items/42`, no double strip |
| V13 | Query `lang=vi` | Stub raw-query journal | Query preserved |
| V14 | Query `tag=a%2Bb` | HTTP client + stub | Not turned into a space outside contract |
| V15 | Encoded slash / double slash | Real HTTP client | Normalized/rejected per spec/container |
| V16 | Differently cased header name | HTTP client | `x-api-version` handled identically to `X-API-Version` |
| V17 | GET-only route receives POST | HTTP client | Zero outbound attempts |
| V18 | Unknown path `/api/v3/...` | HTTP client | 404 or explicit status per policy |
| V19 | Catch-all route on same prefix | Route test + stub | Never swallows missing/invalid versions |
| V20 | Header v1/v2 JSON responses | HTTP client + JSON schema | V1/v2 schemas differ per contract |
| V21 | Header v1/v2 cache isolation | CDN/cache integration | `Vary` and cache key are accurate |
| V22 | ETag and `If-None-Match` | HTTP client/cache fixture | Never returns 304 for the wrong version |
| V23 | Backend 404 v1 | Stub journal | Client receives 404 from the right backend |
| V24 | Backend 503 v2 | Stub journal | No fallback to v1 |
| V25 | Backend connect timeout | Fault injection | 502/503/504 per contract, finite deadline |
| V26 | Retry v1 instance A→B | Stub with counter | All attempts stay on v1 and remain bounded |
| V27 | Circuit breaker v2 OPEN | Fault injection | Backend not called, v2 fallback served |
| V28 | Rate limit across path/header aliases | Security/rate limiter test | Quota cannot be multiplied by switching aliases |
| V29 | Anonymous call to versioned private API | Spring Security test | Rejected before backend |
| V30 | JWT missing scope / wrong audience | Signed test token | Rejected with zero backend calls |
| V31 | Public Catalog and credential forwarding | Stub header-name journal | No token/cookie leaked against policy |
| V32 | CORS preflight `OPTIONS` | Browser/HTTP test | `Access-Control-Allow-Headers` and policy accurate |
| V33 | Proxy strips `X-API-Version` | Ingress/SCG e2e | Explicit error, no wrong default version |
| V34 | Deployment v2 build rollback | Canary integration | v1/v2 API contracts remain intact |
| V35 | Deprecation/Sunset on v1 | HTTP tests | Emitted only on published routes and dates |
| V36 | Multi-replica route config drift | E2E per Pod | Replicas never select different versions |

### Prioritizing Tests

- **Every commit:** V01–V13, V17–V20, V23–V24, V29 (with appropriate context).
- **Before release/migration:** V14–V16, V21–V22, V25–V28, V30–V33, V35.
- **Approved canary/chaos testing:** V34, V36, and load/connection-failure tests.

You do not need to run every test as destructive e2e in production. Fault scenarios (timeouts, open circuits, rate-limiter store outages, backend swaps) belong in a **sandbox/test namespace** using synthetic data, bounded request counts, and clear rollback steps.

## 24. Diagnosing Version Misrouting Bugs

When someone reports “I called v1 and got v2 JSON,” observe the actual request path rather than immediately tweaking `order` or swapping backend URIs.

| Symptom | Likely cause | Evidence / remediation |
| --- | --- | --- |
| `/api/v1/...` returns v2 schema | Route URI points to wrong service, or backend build broke v1 contract | Route ID, outbound target, and JSON schema test |
| Header `1` occasionally hits v2 | Client/proxy sent multiple header values; overlapping predicates | Request header count, 400 validator, not regex alone |
| Missing header still hits v2 | Catch-all/default route picks latest | Remove catch-all or publish/freeze an explicit default |
| Correct header returns 404 at Gateway | Wrong config namespace, Header predicate mismatch, wrong Method | Protected Actuator route definitions; route ID test |
| Path v1 returns 404 at backend | Wrong `StripPrefix` or double rewrite at ingress | Backend raw path/HITS; inspect both layers |
| V1 returns 404 at Gateway, backend HITS=0 | No route/method/path match or blocked by another filter | Spring WebFlux route predicates/security status |
| `/api/v3` returns v2 | Overly generic route or inappropriate fallback | Remove path catch-all or add explicit unsupported policy |
| POST to a GET route still hits backend | Another/catch-all route matched POST; missing security rules | Route ID and backend method journal |
| Same URL, v2 client gets cached v1 JSON | Missing `Vary`, cache key ignores version | CDN cache test, response headers, distinct ETags |
| `Vary: Accept-Encoding` disappears | `SetResponseHeader=Vary` overwrote the header | Merge `Vary` tokens and test compression/caching |
| 304 returns wrong schema | Shared ETag across v1/v2 | Revalidation test per exact version |
| Browser reports CORS error, curl returns 200 | Preflight `OPTIONS` unhandled or `X-API-Version` not allowed | Browser preflight headers, Security/CORS policy |
| Client sent header but backend never sees it | Gateway intentionally ran `RemoveRequestHeader`, or ingress stripped it | Verify canonical `X-Resolved-Api-Version` at backend |
| Backend sees unexpected `X-API-Version` | Header stripping didn't run or wrong route matched | Backend journal, filter order, version config |
| Client spoofs `X-Resolved-Api-Version` and backend trusts it | Used `AddRequestHeader` or backend directly reachable | `SetRequestHeader` + network identity/auth |
| V2 endpoint bypasses JWT requirement | Security matcher covers only v1 | Test anonymous/wrong-scope across **every** version |
| Rate limiter quota doubles across both aliases | Key resolver uses client-chosen raw path/version | Stable principal/operation budget, shared store |
| Retrying v1 onto v2 returns 200 | Fallback/LoadBalancer mixes service contracts | Version-bound upstream sets and explicit adapters |
| V1 outage shows only 200 on dashboard | Fallback masks upstream failure | Separate upstream outcome from final status |
| One Gateway replica responds differently | Route config/BOM/filter versions out of sync | Per-replica config revision and smoke tests |
| Header regex fails to match | Case sensitivity of the **value**, whitespace, pattern, q-values | Test exact raw values and regex contract |
| Encoded plus/slash alters path | Ingress/URI decoder/`RewritePath` mis-normalizes | Real HTTP raw query/path journal |
| V1 has `Sunset` header, and v2 does too | Response filter/global policy scoped too broadly | Scope by route ID and add response tests |
| Backend 503 only on header version | Header route URI misconfigured, missing endpoints | Backend target/`ServiceInstance` and exception type |
| Route matches but outbound connect/TLS fails | DNS/port/cert/truststore or pool issue | Separate routing success from transport failures |

### Single-Request Runbook

1. **Record the contract:** Did the client use path or header versioning? Which method, URL template, and expected version?
2. **Verify the inbound boundary:** Did ingress modify the path, `Host`, `X-API-Version`, or HTTP method?
3. **Verify validation:** Does the request have exactly one header? Do path and header conflict? Did Security block before routing?
4. **Verify route selection:** Which route ID matched, and what are its `order` and predicates?
5. **Verify the filter chain:** Did `StripPrefix` and `SetRequestHeader` produce the expected upstream path and header?
6. **Verify the upstream:** Which v1/v2 backend was chosen? Were there `ServiceInstance`, DNS/TCP/TLS, or HTTP client pool errors?
7. **Verify the response:** What were the backend status, schema, and ETag? Did the Gateway rewrite response headers or body?
8. **Verify cache/CDN:** Are `Vary`, `Cache-Control`, and `ETag` version-distinct? Does the CDN honor the custom header?
9. **Verify retries/fallback:** How many outbound attempts did one client request generate, and did any attempt switch contracts?
10. **Reproduce in the lab:** Use v1/v2 stubs and a test profile—never production tokens or live edits to production-serving routes.

Never enable full Reactor Netty wiretap or HTTP header dumps to debug versioning when requests contain JWTs, Cookies, or PII. Rely on **route IDs, outbound attempt counts, synthetic-data backend stubs, and bounded-metadata tracing**.

### Sample `curl` Commands to Test the Contract in a Test Environment

~~~bash
# Assume the test Gateway runs on port 8080, NOT production.
GATEWAY_URL='http://127.0.0.1:8080'

# Select v1 via path; expects numeric price.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/v1/catalog/items/42?lang=vi"

# Select v2 via path; expects object price.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/v2/catalog/items/42?lang=vi"

# Select v1 via header.
curl --silent --show-error -i \
  -H 'X-API-Version: 1' \
  "$GATEWAY_URL/api/catalog/items/42"

# Select v2 via header; inspect Vary and ETag.
curl --silent --show-error -i \
  -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/catalog/items/42"

# Missing version header: lab policy returns 400.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/catalog/items/42"

# Path v1 / header v2 conflict: lab policy returns 400.
curl --silent --show-error -i \
  -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/v1/catalog/items/42"

# Two version values: lab policy returns 400.
curl --silent --show-error -i \
  -H 'X-API-Version: 1' -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/catalog/items/42"
~~~

These are **commands to run in the lab**, not recorded outputs. If you run them against Spring Security–protected routes, supply a valid test identity/token or an approved auth test mechanism; HTTP 401/403 may fire before the validator. Never put real tokens in shell history, and avoid verbose commands that dump credentials.

### Dedicated CORS Preflight Check for Header Versioning

~~~bash
curl --silent --show-error -i -X OPTIONS \
  -H 'Origin: https://frontend.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-api-version' \
  "$GATEWAY_URL/api/catalog/items/42"
~~~

If cross-origin frontends are permitted, the preflight response must satisfy that origin's CORS policy. `X-API-Version` may need to appear in `Access-Control-Allow-Headers`. **A successful CORS preflight does not grant permission to read data**, and combining wildcard origins with credentials must follow proper HTTP semantics; never open all origins just to make tests pass.

## 25. Capstone Lab: From Route YAML to Migration

**Scenario:** Catalog v1 still serves older mobile apps; Catalog v2 returns a restructured `price` field. The team deploys a Spring Cloud Gateway Server WebFlux instance in front of both backends, supporting both **path-based** and **header-based** API versioning during the migration window.

### Part A — Lock Architecture and Contracts

1. Record the exact **Spring Boot, Spring Cloud BOM, Gateway Server WebFlux, and Java versions** in use.
2. Lock the v1/v2 contracts with two independent JSON schemas or DTO tests, especially the `price` field.
3. Diagram the flow: client → ingress (if present) → SCG → Catalog v1/v2.
4. Set the rule: paths `/api/v1|v2/catalog/**` do not require a header; if supplied, it must match the path version.
5. Set the rule: header path `/api/catalog/**` requires **exactly one** `X-API-Version: 1` or `2`.
6. Set the error policy: missing/invalid/duplicate/conflicting headers return 400; unknown `/api/v3/...` matches no route and returns 404.
7. Assign explicit owners for rewrites, `Vary` caching, authentication, and version deprecation headers.

### Part B — Configure the Gateway

1. Use the four routes from Section 6, substituting `catalog.v1-base-url` and `catalog.v2-base-url` with test stub endpoints.
2. Verify exact `Path`, `Method`, and `Header` predicates, with regex anchors on header values.
3. Test `StripPrefix=3` for the path scheme and `StripPrefix=2` for the header scheme.
4. Strip raw `X-API-Version` before the backend and set Gateway-owned `X-Resolved-Api-Version`.
5. Use `SetResponseHeader` to expose the selected version header on responses.
6. Add `ApiVersionValidationWebFilter` to return 400 on conflicting or malformed inputs.
7. Add `ApiVersionVaryGlobalFilter` for the header scheme without destroying `Vary` values emitted by the backend.
8. Ensure API auth, CORS `OPTIONS`, and health/management routes are not accidentally blocked by the validator.

### Part C — Verify Over HTTP

1. Start two `CatalogVersionStub` instances (v1/v2) on ephemeral ports.
2. Invoke all four request forms and assert **status, body schema, and response version header**.
3. On the backend, assert **request count, raw path/query, and `X-Resolved-Api-Version`**.
4. Send requests with two version header values and path/header conflicts: assert 400 and backend HITS=0.
5. Verify query `lang=vi&tag=a%2Bb` over real HTTP sockets.
6. Make stub v1 return 404 and v2 return 503; confirm clients get those exact statuses without falling back across versions.
7. Send `X-Resolved-Api-Version: attacker`; verify the backend receives the proper canonical version.
8. Add ETag/`Vary`/cache and browser preflight tests; the baseline fixture does not fully test 304 conditional requests.

### Part D — Security and Operations

1. Enable Spring Security on private APIs for **both v1 and v2**, testing anonymous and wrong-scope requests.
2. Use signed test JWTs to verify issuer, audience, and signature—do not rely solely on mock authorization `.with(jwt())` tests.
3. Verify the Orders backend still enforces resource ownership; the version header grants no permissions.
4. Validate Service DNS or `lb://` discovery, readiness, and no-instance behavior against the real topology.
5. Track route ID, upstream status, final status, and outbound attempts; never log raw tokens or PII-bearing queries.
6. Design rate-limit keys and quotas so the two version aliases cannot accidentally multiply a user's quota.
7. Test a canary of a new v1 build while preserving the v1 schema; **never** use a canary to return v2 JSON to a v1 client.

### Part E — Simulate the v1→v2 Migration

1. Create a v1 test SDK client that understands only `price: integer`.
2. Create a v2 test SDK client that understands only `price.amount` and `price.currency`.
3. Measure v1/v2 traffic by route IDs without parsing raw user IDs.
4. Announce v1 deprecation in docs and response metadata per policy while keeping v1 running during transition.
5. Upgrade the v1 test client to v2 and verify JSON, schema, and error handling.
6. In the sandbox, retire v1 at a simulated Sunset cutoff: return 410 via a tombstone handler or 404 via route removal per contract.
7. Test rolling back to v1 post-migration if data and backends still support it, without silently switching the v1 route to v2 JSON.

### Acceptance Checklist

| Item | Required evidence |
| --- | --- |
| Architecture | Diagram of v1/v2 routes, both versioning schemes, and security boundaries |
| Routing | Two `Path` predicates, two `Header` predicates, route IDs, and backend URIs |
| Request transform | Stub proof of `StripPrefix` and the canonical request header |
| Response contract | Distinct v1/v2 JSON shapes, status codes, and response version header |
| Cache safety | `Vary: X-API-Version`, representation-specific ETags, zero cache leaks |
| Version validation | Missing/unsupported/duplicate/conflict tests |
| Security | Anonymous/wrong-scope rejections, token audience/ownership, zero credential leaks |
| Resilience | Retries/circuits never switch versions; outbound attempts remain bounded |
| Observability | Bounded route ID/version counters, errors with clear provenance |
| Migration | v1→v2 docs/SDK, Sunset policy, and rollback plan |

**Pass criteria:** The learner proves via HTTP and the backend journal that a request **selects the right API contract, backend, path/header, and response schema**, while invalid versions are never silently routed to “latest” and neither caching nor authorization is bypassed.

## 26. Anti-Patterns to Avoid and Pre-Merge Checklist

| Anti-pattern | Consequence | Replacement |
| --- | --- | --- |
| Using `Path=/api/{version}/...` and routing everything to v2 without validation | Unknown v3 or v1 routed to wrong contract | Explicit routes or a validator with a strict mapping table |
| Using `Header=X-API-Version, 1` with loose regex | Can match unintended values depending on pattern | `^1$`, `^2$`, and reject duplicates |
| Header route without version defaults to latest | Silent breaking change | Published fixed default or 400 |
| Allowing two v1/v2 header values through | Ambiguous route matching | WebFilter rejecting `size != 1` |
| Allowing path v1 + header v2 through | Backend receives conflicting signals | 400 or tested precedence contract |
| Using `AddRequestHeader` for canonical version | Spoofing clients can inject multiple values | Overwrite with `SetRequestHeader` |
| Treating the version header as a principal | Authorization bypass | Spring Security and backend resource authorization |
| Forgetting to protect v2 endpoints in security matchers | V2 bypasses authorization | Security tests across every version and method |
| Setting `StripPrefix=3` for both schemes | Header path loses the `items` segment | Path=3, Header=2 as in the example |
| Both ingress and SCG strip `/api` | Route fails to match or hits wrong backend | Designate one rewrite owner |
| Using a dynamic target from a client header | SSRF, token egress | Static config / approved service discovery |
| Header v2 on the same URL without `Vary` | Shared cache serves stale v1 JSON | `Vary` and cache key policy |
| Overwriting `Vary` when adding version | Breaks compression/CORS cache semantics | Merge field tokens and test |
| Reusing the same strong ETag across different v1/v2 bodies | Incorrect 304 / cache hits | Per-representation validators |
| Retrying v1 onto v2 when v1 fails | Violates client contract | Same-version fallback or explicit adapter |
| Canarying v1 traffic onto a build returning only v2 | Breaks existing clients | Canary only within the same API contract |
| Rate limit key = raw version header | Clients rotate headers to expand quota | Key by identity/operation policy |
| Public Actuator/Gateway route admin endpoints | Attackers read or modify routes | Management security / network isolation |
| Logging raw `Authorization` and URL queries | Leaks secrets/PII | Metadata allowlist, bounded telemetry |
| Asserting HTTP 200 only | Hides which backend/route version actually served | Backend journal + response schema checks |
| Using only `MockMvc`/`WebTestClient` mocks | Does not prove real outbound TCP/HTTP | `RANDOM_PORT` integration tests + stubs |
| Dropping WebFlux `GlobalFilter` into Gateway MVC | Wrong runtime/filter chain | Use the matching MVC APIs and starter |
| Deleting v1 immediately upon v2 deploy | Breaks un-migrated clients en masse | Deprecation, telemetry, migration, Sunset |

### Technical Checklist

~~~text
[ ] Version represents an API contract, never confused with build/canary.
[ ] Path or header scheme selected, or an explicit combination rule defined.
[ ] Path/Method/Header route predicates match precisely without overlap.
[ ] Exact header version regex and duplicate/malformed handling tested.
[ ] Unknown/missing/conflicting versions return contract-defined HTTP statuses.
[ ] StripPrefix/RewritePath preserve raw URI/query and handle encoded paths properly.
[ ] SetRequestHeader replaces any client-sent canonical header; avoid casual Add.
[ ] Upstream URIs/service IDs belong to an allowlist, never client-controlled.
[ ] Security matchers protect v1/v2, all methods, and all path aliases.
[ ] Backend independently verifies identity, tenant, and resource ownership.
[ ] Tokens/Cookies forwarded only when audience, permission, and trust boundaries allow.
[ ] Header versioning enforces accurate Vary/cache keys and per-representation ETags.
[ ] CORS preflight OPTIONS has its own policy, unblocked by GET Header predicates.
[ ] Rate limiting, retries, and circuit breakers never multiply quotas or switch contracts.
[ ] Backend stubs verify path, method, headers, and outbound attempt counts.
[ ] HTTP tests verify status, response schema, 4xx/5xx handling, and cache safety.
[ ] Metrics by route ID/version remain bounded; logs/traces exclude secrets.
[ ] Rollout/canary/rollback, deprecation, and Sunset plan exist for v1.
[ ] BOM, starter, and property namespace match the actual Gateway runtime.
~~~

## 27. Summary

- **API version routing** selects a **request/response contract** for the client—not automatically the newest build or a canary. Keep API v1/v2 distinct from deployment revisions and database schemas.
- With **path versioning**, routes `/api/v1/catalog/**` and `/api/v2/catalog/**` use `Path` and `Method` predicates. This lesson's example uses `StripPrefix=3` so the backend receives `/items/42`.
- With **header versioning**, a single URL `/api/catalog/**` combines with `Header=X-API-Version, ^1$` or `^2$`. The example uses `StripPrefix=2`; **one** unambiguous header value is required so multiple values never trigger ambiguous routing.
- **Route predicates only match**; they do not validate inputs or return 400 on their own. A dedicated `WebFilter` or validation layer rejects missing, malformed, or conflicting versions, whereas unmatched paths typically yield 404 if no fallback route exists.
- **Normalize upstream metadata:** use `RemoveRequestHeader` and `SetRequestHeader` so the backend receives a Gateway-owned `X-Resolved-Api-Version`; `SetResponseHeader` informs the client of the resolved version. This is **not an authentication mechanism**.
- **Header-based versioning requires cache isolation.** Because the same URI serves two JSON representations, configure `Vary: X-API-Version`, proper `ETag`/`Content-Type`/`Cache-Control`, and CDN rules without overwriting other `Vary` tokens.
- **Security must cover every version and alias:** Spring Security/JWT checks, backend tenant/resource authorization, token audiences, rate limiting, and trusted proxy policies must span both path and header routes. Never treat raw client headers as principals, roles, or backend URIs.
- **Resilience preserves the contract:** retries, circuit breakers, and load balancing for v1 must stay on backends serving v1; never fail over to v2 on error. A canary build inside a route must never silently alter that route's JSON schema.
- **HTTP integration tests verify both sides:** the client receives the expected status, schema, and headers; the backend stub confirms the target URI, raw path/query, canonical header, and outbound attempt count. Test 400, 404, 503, duplicate headers, CORS, caching, and security.
- **Plan the version lifecycle:** maintain docs and SDKs, track adoption per route ID, announce deprecation/Sunset, retire v1 as scheduled, and maintain a rollback strategy. Never let `latest` shift dynamically with deployments when clients did not select a version.

In short, a solid version-aware **SPRING_CLOUD_GATEWAY** system does far more than “inspect a path or header to pick a URL.” It **enforces the right contract, preserves HTTP semantics, protects every entry point, prevents caches or retries from returning the wrong version, and provides the telemetry and tests needed to migrate clients safely**.

### References and Version Alignment

- **Spring Cloud Gateway Reference — Route Predicate Factories:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Cloud Gateway — GatewayFilter Factories** (Path, Header, Method, StripPrefix, RewritePath, SetRequestHeader, SetResponseHeader): https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security Reactive Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **HTTP Semantics, RFC 9110** (Accept, Vary, conditional requests, status codes): https://www.rfc-editor.org/rfc/rfc9110
- **Deprecation HTTP Response Header Field, RFC 9745:** https://www.rfc-editor.org/rfc/rfc9745
- **Sunset HTTP Header Field, RFC 8594:** https://www.rfc-editor.org/rfc/rfc8594
- **OpenAPI Specification:** https://spec.openapis.org/oas/latest.html

**Note on using the examples:** The Java and YAML snippets in this lesson describe a **Gateway Server WebFlux** configuration with two path-based routes and two header-based routes, intended for learning and testing with synthetic data. Property names, starters, filter APIs, and meters may vary across Spring Cloud Gateway releases; these examples do not replace live execution tests, security reviews, or academic QA verification (STEP 6).
