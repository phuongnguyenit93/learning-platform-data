# Preventing Token Logging or Forwarding to Untrusted Destinations

## 1. A Valid Token Can Still Leak at the API Gateway

In a microservices system, **Spring Cloud Gateway** acts as the entry point: it matches routes with predicates, executes filter chains, transforms paths/headers, resolves services via `lb://`, calls backends over HTTP(S), and records operational telemetry. Requests passing through the Gateway often carry the most sensitive data: **access tokens, session cookies, API keys, and identity attributes**.

Validating a token successfully **does not mean the token is safe from leakage**. A valid token can still be:

- Written to access logs or debug logs when a filter dumps full request headers.
- Emitted via Reactor Netty wiretap/HTTP client logging, tracing, or a custom exception handler.
- Forwarded verbatim to a backend that **has no need** for that token.
- Sent to an untrusted service due to a misconfigured route, dynamic routing, or poisoned service discovery records.
- Exposed in URL query strings, `Location` redirects, `Referer` headers, browser history, caches, dashboards, or observability tools.
- Retained in response `Set-Cookie` headers or copied into unintended message queues/analytics systems.

Example of a public route pointing to a third party without removing `Authorization`:

~~~text
Client
  GET /api/public/recommendations
  Authorization: Bearer <access-token>
        |
        v
Spring Cloud Gateway
        |
        v
https://recommendation-vendor.example
  Authorization: Bearer <access-token>  <-- LEAKAGE RISK
~~~

If an upstream receives a token meant for another API, that token can end up in the third party's logs, traces, or storage. The recipient **is not authorized to use the token** merely because the Gateway sent it, yet the Gateway must never distribute a bearer credential that any holder could replay elsewhere.

This lesson belongs to the **Sessions and Tokens** chapter of **Spring Cloud Gateway**. Its focus is **controlling where tokens travel** and **keeping tokens out of telemetry**, complementing authentication, authorization, TLS, rate limiting, circuit breakers, and request observability. Examples use **Spring Cloud Gateway Server WebFlux**, reactive Spring Security, and Reactor Netty.

**Expected outcomes:** After this lesson, you can define trust boundaries per route, permit or strip credentials as needed, distinguish token types, implement safe logging, audit debug/wiretap settings, and build tests that catch token leaks. You will also understand why relying on a single filter or a regex masking `Bearer` strings is never enough.

> **Core principle:** Send tokens only to **approved recipients**, matching **audience/scope**, over secured channels; **never record raw tokens in logs, metrics, traces, or client error responses**.

## 2. Classifying Secrets Before Deciding to Forward

The items below serve distinct purposes and lifecycles:

| Type | Where Commonly Found | Where Permitted | Primary Risk |
|---|---|---|---|
| **OAuth2 access token** | `Authorization: Bearer ...` | Resource servers matching audience and scope | Anyone holding a bearer token can use it while valid |
| **Refresh token** | Secure server-side storage or AS-designed flow | Component authorized to refresh tokens | Typically longer-lived/mints new tokens; higher value than access tokens |
| **OIDC ID token** | OAuth2/OIDC client | Client app verifying login event per OIDC contract | Not an access token substitute for calling APIs |
| **Session ID** | Cookie, e.g., `SESSION=...` | Application/session store that issued the session | Can allow session hijacking if leaked |
| **API key** | Dedicated header, occasionally query (discouraged) | API/service with registered key and scope | Often a long-lived secret if unrotated |
| **CSRF token** | Header/form or session mechanism | App's anti-CSRF flow | Should not be treated as an access token or logged raw |
| **Authorization code / PKCE verifier** | OAuth2 redirect and client flow | OAuth2 client/Authorization Server during exchange | Leakage can break flow security if combined with other factors |

**An access token is not an ID token.** An ID token targets the OAuth2 client as its audience and confirms identity in OpenID Connect; it is not a blanket pass to call `orders-service`. **Refresh tokens must never be sent to business APIs either**: refreshing belongs solely to authorized components.

A self-contained JWT has a header/payload decodable to JSON claims, **yet unverified claims must never be trusted**. Never log full JWTs just to "inspect permissions"; read verified attributes from Spring Security's `Authentication` or trusted context.

### Do not look at just one header

Secrets can appear in many places:

- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie`, or custom headers like `X-API-Key`, `X-Auth-Token`.
- URL query parameters like `?access_token=...`, `?api_key=...`, `?session=...`.
- Login, token refresh, OAuth2 callback, and API credential payloads.
- WebSocket handshakes, GraphQL variables, request/response error payloads, trace baggage.
- Configuration secrets in environment variables, JVM system properties, exception messages, or route metadata.

A logging rule masking only `Authorization` **is insufficient** if the team still logs full URLs, cookies, request bodies, or OAuth2 debug dumps.

## 3. Diagram of Gateway Trust Boundaries

A Gateway has at least three token-related trust boundaries:

~~~mermaid
flowchart TD
    U[Browser / Mobile / Partner] -->|Bearer token, session cookie| G[Spring Cloud Gateway]
    G --> A[AuthN/AuthZ: Spring Security]
    A --> P{Route + egress policy}
    P -->|Public catalog, no credentials| C[Catalog service]
    P -->|Orders, scoped access token| O[Orders service]
    P -->|External vendor, no credentials| V[Third-party service]
    G -. Safe metadata only .-> L[Logs / Metrics / Tracing]
    G -->|Configured internal auth only| I[Identity service]
~~~

**Boundary 1 — client → Gateway:** Clients may send invalid credentials, spoofed headers, sensitive URLs, or arbitrary bodies. The Gateway authenticates per policy and never treats raw input as trusted identity.

**Boundary 2 — Gateway → backend:** The Gateway becomes an HTTP client, picking a `uri` from a route or load balancer. A request passing Gateway authentication **does not grant automatic permission** to pass raw credentials to every backend. Forwarding tokens must depend on **the target service, audience, token type, and policy**.

**Boundary 3 — Gateway → telemetry:** Logs, metrics, traces, error tracking, APM, SIEM, and support tools have their own users, retention, exporters, and access controls. Data sent there must be **safe metadata**, never replayable credentials.

An "internal" network does not mean every service inside it shares the same trust level. Reporting services, analytics pipelines, and third-party support tools should never receive admin API tokens or user refresh tokens.

## 4. Do Not Confuse Successful Authentication with Token-Forwarding Policy

In Gateway Server WebFlux, Spring Security can validate Bearer JWTs:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

This configures **inbound token validation** per your Spring Security version and validators, yet **is not a policy that automatically strips `Authorization` when proxying**. In an HTTP reverse proxy, without a credential-stripping filter, the `Authorization` header can still pass upstream alongside other request headers. Verify actual behavior in your Gateway version and filter chain rather than assuming "the token was validated, so the Gateway keeps it".

Three independent questions:

1. **Inbound validation:** is the client-sent token valid for our Gateway/API?
2. **Authorization:** is the principal allowed to invoke this endpoint?
3. **Outbound release:** is it permissible to **disclose this credential** to the chosen service? Do the token's audience/scope and transport channel fit?

A request can pass questions (1) and (2) while the answer to (3) remains **no**.

### Audience matters more than a target URL "looking internal"

Example:

~~~json
{
  "iss": "https://identity.example.test/realms/store",
  "sub": "user-742",
  "aud": ["shop-gateway"],
  "scope": "catalog.read orders.read",
  "exp": 1999999999
}
~~~

This is only an **illustrative JWT payload**, not a signed JWT. If the token carries audience `shop-gateway` only, do not assume it was issued for `orders-service`. Each backend must validate **its own** audience; otherwise a token issued for system A risks misuse at system B (token substitution).

Therefore, even for approved internal services, **token exchange**, delegated tokens, or audience/privilege-scoped internal identity mechanisms may be required instead of copying the client's raw access token.

## 5. Per-Route Policy: Default-Deny Credential Forwarding

Draft an egress table **before writing YAML**:

| Route | Approved Destination | Inbound Credential | Outbound Decision |
|---|---|---|---|
| `public-products` | `lb://catalog-service` | Clients might still send `Authorization` to public APIs | **Strip unnecessary `Authorization`/cookies** |
| `orders-private` | `lb://orders-service` | Validated access token | Forward access token only if Orders is an allowed audience and validates it independently |
| `admin-private` | `lb://admin-service` | Admin-authorized token | Forward only admin-policy-approved credentials over secured channels |
| `partner-recommendations` | `https://vendor.example.test` | Any | **Strip all internal credentials**; if a vendor key is needed, use the Gateway's **own** credential |
| `login-token` | Identity/Authorization Server | Credentials or authorization code | Send only flow-authorized secrets to trusted IdP endpoints |
| `unlisted/dynamic` | Unapproved | Any | **Never forward tokens**; ideally do not expose the route |

**Deny-by-default for token egress** means **never forward automatically** just because a route matched. In complex setups, enforce guards across route config, networking, service token validation, and automated tests—never rely solely on route IDs if target URIs can change later.

### Do not forward all cookies out of habit

Cookies can carry session IDs, refresh tokens, CSRF cookies, or preferences. A public catalog route usually **needs no** session cookie. Forwarding Gateway-domain `Cookie` headers to external analytics/vendors risks both credential theft and user privacy leaks.

If a backend genuinely uses cookie auth, define the contract explicitly rather than stripping `Cookie` blindly and breaking the app. Conversely, with Bearer tokens, verify whether any cookie should ever reach the backend.

## 6. RemoveRequestHeader: Simple Prevention on Unauthenticated Routes

For well-known routes, the **`RemoveRequestHeader` GatewayFilter Factory** strips headers from requests before sending them upstream.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-products
              uri: lb://catalog-service
              predicates:
                - Path=/api/public/products/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=Proxy-Authorization
                - RemoveRequestHeader=X-API-Key

            - id: partner-recommendations
              uri: https://vendor.example.test
              predicates:
                - Path=/api/public/recommendations/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=Proxy-Authorization
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Auth-Token

            - id: orders-private
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - RemoveRequestHeader=Cookie
~~~

**Explanation:**

- Both public routes avoid sending client tokens/cookies to services that do not need them.
- Routes to external vendors especially require a **default-strip credential** policy; if the vendor needs an API key, provision it via secret management and dedicated integration rather than **forwarding a user's API key**.
- The Orders route illustrates **stripping only `Cookie`** while letting `Authorization` reach the service. **This is valid only when** policy allows forwarding and the Orders backend validates the token's audience/scope. If the token targets the Gateway alone, **change the mechanism** rather than copying the token.
- `RemoveRequestHeader` removes only the named headers; it **does not strip** tokens in query strings, bodies, or other custom headers. HTTP header names are case-insensitive.

**Prerequisites:** `lb://` requires Spring Cloud LoadBalancer and a controlled `ServiceInstance` source. `https://vendor.example.test` is an illustrative address, not a real target to send traffic to. In older Spring Cloud Gateway WebFlux lines, the YAML prefix is typically `spring.cloud.gateway.routes` rather than `spring.cloud.gateway.server.webflux.routes`. Use your deployment's exact namespace.

### Watch filter ordering

`RemoveRequestHeader` does not establish a permanent invariant if **a later filter re-adds `Authorization`**. For example, a misordered `TokenRelay`, `SetRequestHeader=Authorization,...`, or custom `GatewayFilter` can reintroduce credentials.

Always **audit the entire filter chain**, not a single YAML line; integration tests must assert **the exact headers received by the backend**. For centralized egress enforcement, check right near the final HTTP send step and lock down extension points by policy rather than assuming the first filter in YAML runs last.

### Combine route controls with network controls

Even with all auth headers stripped, a dynamic route could still hit an internal metadata or admin service. **Route destination allowlists, trusted service discovery, TLS/mTLS, and network policies** remain essential; stripping credentials does not stop SSRF or unauthorized internal access on its own.

## 7. TokenRelay Does Not Mean "Every Token Is Forwardable"

Spring Cloud Gateway provides the **`TokenRelay` GatewayFilter Factory** in setups using **Spring Security OAuth2 Client**. It can fetch the authorized client's access token and attach it to proxied backend requests. This supports OAuth2 login flows and downstream delegation, **but does not prove the destination is trusted or that the token has the right audience**.

Illustrative config on a controlled route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: protected-orders
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - TokenRelay=
~~~

**Understanding this example accurately:**

- Use only when the app has an **OAuth2 Client config/authorized-client context**; starter names and auto-configuration depend on version.
- `TokenRelay` differs from simply enabling `oauth2ResourceServer().jwt()`. A resource server validating Bearer tokens **is not automatically an OAuth2 Client** holding an authorized client to relay.
- The relayed access token must carry valid permissions and **audience for the Orders service**. Otherwise, the backend must reject it or the system must perform token exchange.
- Never attach `TokenRelay` to routes hitting **unapproved vendors**, dynamic routes with arbitrary hosts, or public endpoints needing no tokens.
- If other filters on the route read/write `Authorization`, verify **filter order** and the exact header reaching upstream.
- Factory names, support, and configuration syntax can vary across Spring Cloud Gateway lines; check your active version.

### Token forwarding, token exchange, and service credentials

| Approach | Meaning | When Sensible? |
|---|---|---|
| **Forward access token** | Backend receives the client's token | Backend is a valid audience, shares the trust model, and validates it itself |
| **Token exchange / on-behalf-of** | Gateway or trusted component exchanges for a backend-specific token | Narrower audience/scope or service boundary separation is needed |
| **Service-to-service credential** | Gateway authenticates itself to the backend | Backend expects system identity without original user tokens |
| **Send no credentials** | Upstream receives request stripped of tokens/cookies | Public/anonymous service or vendor needing no identity |

Never use one **shared admin token** to proxy all user requests to backends. That breaks attribution and turns user calls into privileged Gateway actions. With token exchange, protect keys, acting subjects, scopes, TTLs, audit trails, and IdP revocation policies.

### Distinguishing session login from bearer-only requests

A browser logged in via OAuth2 Login holds a Gateway session cookie and an authorized-client record, allowing `TokenRelay` to use that context. In a stateless Bearer JWT API, a client sending `Authorization` to the Gateway which proxies the header is a **different** flow. Never infer session cookies, CSRF, or OAuth2 client state merely from the presence of a JWT.

## 8. Service Discovery and Dynamic Routes: Who Actually Receives the Token?

In Gateway Server WebFlux, route URI `lb://orders-service` can be resolved by **`ReactiveLoadBalancerClientFilter`** to a concrete `ServiceInstance`, such as `https://orders-2.internal.example:8443`. The actual HTTP connection goes to that instance, not the logical service ID string.

~~~mermaid
flowchart TD
    A[Authorized route: lb://orders-service] --> B[LoadBalancer resolves ServiceInstance]
    B --> C{Host / namespace / certificate trusted?}
    C -->|Yes| D[HTTP(S) request to approved instance]
    C -->|No| E[Reject routing or do not release credential]
    D --> F[Backend validates audience, token and user permission]
~~~

**A route ID is not final proof of where a token lands.** If route `orders-private` has its URI pointed to an external host, or if a registry receives a malicious entry, an allowlist based solely on route names cannot stop credentials from reaching untrusted targets.

A trustworthy policy must cover:

1. **Route definition sources:** only authorized roles/pipelines may modify route URIs, predicates, and filters.
2. **Service discovery:** restrict registry write permissions, isolate namespaces/environments/tenants, and validate system-registered instances.
3. **Actual target:** enforce host, scheme, port, network, or service identity; never let `lb://` resolve to unapproved addresses.
4. **TLS:** verify certificates, hostnames, and CAs; enforce mTLS when service-to-service identity is required.
5. **Token scope/audience:** backends independently validate tokens per service and operation; use token exchange when needed.
6. **Redirects/fallbacks:** never allow backends or filters to redirect tokens to unapproved hosts.

### SSRF warning in dynamic routing

Never build an outbound URI directly from a client header such as:

~~~http
X-Target-URL: http://127.0.0.1:8081/admin
~~~

and route requests there. Attackers can force the Gateway to hit admin/metadata endpoints or internal networks. If requests also carry Bearer tokens, the bug becomes **SSRF combined with credential leakage**.

Restrict destinations via allowlists/trusted service records, block unnecessary schemes and ports, authorize dynamic routing access, and enforce network egress policies. Never validate only a hostname string before DNS or service discovery resolution while ignoring the final resolved address.

### Do not turn backend 302s into token broadcasters

HTTP redirects start a new transaction; whether a client or HTTP client follows redirects and carries `Authorization` to a new host depends on configuration and implementation. Never assume "clients always drop `Authorization` across hosts", and never configure HTTP clients to auto-follow redirects to arbitrary hosts with tokens attached. **Treat redirect targets as a fresh trust boundary**, checked per hop, method, and credential.

## 9. Log Sources That Can Leak Tokens

Even if you never write `log.info(token)`, tokens can leak indirectly. Inventory every sink:

| Source | What Might Be Logged | Mitigation |
|---|---|---|
| Ingress/CDN/WAF access logs | Full URLs, query strings, certain request headers | Never put tokens in URLs; configure safe log formats/headers |
| Gateway HTTP server access logs | URIs, statuses, timings, client IPs | Log only route templates and needed metadata; scrub query strings |
| Reactor Netty `wiretap` | Detailed bytes/headers of HTTP exchanges when enabled | Keep disabled in production except approved, protected diagnostics |
| Custom Gateway `GlobalFilter` | `exchange.getRequest().getHeaders()`, body, `getURI()` | Use a log-field allowlist; never dump raw requests/responses |
| Spring Security/OAuth2 `DEBUG`/`TRACE` | Auth flows, tokens/claims/headers per component/version | Restrict log levels; inspect sample output before enabling |
| Exception handling | URIs, headers, or messages echoing raw input secrets | Log/return error codes and trace IDs, never raw input |
| Distributed tracing/APM | URLs, request headers, baggage, attributes | Header capture allowlists, URL sanitization, secured exporters |
| Metrics | Full URLs, user IDs, tokens, or queries as labels | Use bounded-cardinality labels only, such as route ID/status |
| Backend/sidecar logs | `Authorization`/cookies after proxying | Strip unneeded credentials; enforce uniform logging policies |
| Support/debug artifacts | HAR files, `curl -v`, screenshots, heap dumps | Redact, restrict access, enforce retention and sharing controls |

**Never call `request.getHeaders().toString()`, `exchange.toString()`, or serialize whole requests to logs** expecting default middleware to mask tokens automatically. A new serializer, custom filter, or library upgrade can alter formatting and leak raw values.

### Wiretap and log levels

In Gateway WebFlux versions supporting these properties, explicitly **disabling wiretap** looks like:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            wiretap: false
          httpserver:
            wiretap: false
~~~

**Do not mistake this for disabling all logging.** This configures one Gateway namespace; older versions often use `spring.cloud.gateway.httpclient.wiretap` and `spring.cloud.gateway.httpserver.wiretap`. Reactor Netty, web containers, ingress, Spring Security, and APMs also maintain separate loggers. Verify bound properties and inspect actual logs in staging.

Avoid enabling `TRACE` broadly on `reactor.netty`, `org.springframework.security`, or HTTP wire logging while handling real tokens. If deep diagnostics are unavoidable, use **synthetic test data**, short enablement windows, strict log ACLs, and policy-driven deletion.

### Watch URL access logs

Even logging only `request URI` is dangerous when tokens travel in query strings:

~~~text
GET /callback?code=<authorization-code>&state=<state> HTTP/1.1
GET /stream?access_token=<token> HTTP/1.1
~~~

Do not try to "fix" this merely by masking the `Authorization` header. Authorization codes and access tokens can both leak through URL logs, browser histories, referrers, and monitoring tools. Fix the protocol usage and **omit/redact raw query strings** wherever callbacks or streams are logged.

## 10. Sample `GlobalFilter` Logging Safe Metadata Only

A clean approach is **logging strictly allowlisted fields**, never touching full request headers or bodies. Example in Gateway Server WebFlux:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class SafeGatewayAccessLogFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGatewayAccessLogFilter.class);

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String method = exchange.getRequest().getMethod() == null
                ? "UNKNOWN"
                : exchange.getRequest().getMethod().name();

        return chain.filter(exchange).doFinally(signal -> {
            Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
            String routeId = route == null ? "unmatched" : route.getId();
            HttpStatusCode status = exchange.getResponse().getStatusCode();
            String statusText = status == null
                    ? "unknown"
                    : Integer.toString(status.value());

            // Never log full URI, Authorization, Cookie, body, or tokens.
            log.info("gatewayRoute={} method={} status={} signal={}",
                    routeId, method, statusText, signal);
        });
    }
}
~~~

**Why does this reduce token leakage risk?**

- `route.getId()` comes from system-managed route definitions rather than raw queries or client paths. **Still control route ID/metadata sources**, as dynamic route IDs could echo untrusted input if unrestricted.
- `method`, `status`, and `signal` are bounded metadata requiring no credential inspection.
- `doFinally` observes `onComplete`, `onError`, or cancellation reactively without subscribing manually or blocking the event loop.
- Avoiding `getURI().toString()` prevents logging queries containing tokens, authorization codes, or private search terms.

This is an **illustrative logging filter only**. It does not replace access/proxy logs, telemetry security, or outbound `Authorization`-stripping policies. A `GlobalFilter` also runs only on Gateway routes, not WebFlux controllers or Actuator endpoints. For web-layer logging, apply equivalent WebFlux mechanisms and the same allowlist principle.

### Tracing individual requests

Prefer **observability-generated trace IDs** with validated/normalized values and strict access control. Never use access tokens, session IDs, raw `Authorization` headers, or unkeyed token hashes as trace IDs. Hashing does not make tokens universally safe and can create unauthorized persistent user-tracking identifiers.

Record only genuinely needed attributes: route ID, HTTP method, status, signal, latency, and error category. **Never put full URLs with queries**, secret headers, or bodies into trace tags. Apply the same discipline when instrumenting outbound HTTP clients on the Gateway → backend hop.

## 11. Never Rely on "Mask Everything" Regex as Your Sole Defense

A common anti-pattern:

~~~java
// DO NOT DO THIS: anti-pattern example.
log.info("request={}", exchange.getRequest().getHeaders());
~~~

followed by running a regex over log lines to replace `Bearer ...` with `***`. This easily fails when tokens:

- Use JWT, opaque, multi-line, URL-encoded, or split-field formats.
- Appear inside queries, bodies, or cookies rather than strings starting with `Bearer`.
- Span repeated headers or varying casing.
- Pass through a logger/exporter **before the redaction step runs**.
- Surface inside exception stack traces, debug snapshots, HTTP wiretaps, or message payloads.

**The best defense is never collecting secret values in the first place.** When a tiny set of headers is strictly needed for diagnostics, build an explicit allowlist like `User-Agent` or a validated correlation ID—and audit even headers that may hold user data. Configure loggers and trace exporters to ignore `Authorization`, `Cookie`, and `Set-Cookie` upfront.

### Check response headers as well

Leaks are not limited to requests:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<session-secret>; Secure; HttpOnly; SameSite=Lax
~~~

Response loggers, body dumpers, or support tools can log `Set-Cookie` and accidentally expose sessions. If the Gateway returns tokens in a login JSON body, response-body logging can leak tokens too. The "no secrets in logs" rule must hold **in both directions**.

## 12. Session Cookies, Refresh Tokens, and CSRF

A Gateway may receive browser requests carrying session cookies instead of `Bearer` headers. Secure cookies typically need attributes like:

~~~http
Set-Cookie: SESSION=<opaque-secret>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

This is a **policy illustration**: choosing `SameSite=Lax`, `Strict`, or `None` depends on login flows, origins, and cross-site needs. `SameSite=None` requires `Secure` in modern browsers. `HttpOnly` reduces JavaScript cookie access, **yet does not neutralize XSS or CSRF**, and `Secure` only enforces HTTPS transit—never making a cookie safe once logged or sent to unauthorized services.

### Cookie forwarding differs from browser cookies

Browsers govern cookie sending by domain, path, `SameSite`, and `Secure`. Once the Gateway receives `Cookie`, it becomes a **new HTTP client** calling upstream. Copying the raw `Cookie` header to another service bypasses the browser's cookie scoping rules; do not expect the browser to stop the Gateway from doing that.

When sessions live **strictly at the Gateway**, backends have no need for `SESSION`. Strip session cookies when proxying unless an explicit contract requires them. When backends authenticate sessions themselves, explicitly define session stores, cookie scope, domains, CSRF, per-hop security, and revocation.

### Refresh tokens and session stores

Refresh tokens belong only in the component authorized to refresh access tokens, encrypted/protected at rest with tight access controls and rotation/revocation per Authorization Server design. **Never forward refresh tokens to Catalog or Orders services** merely because the system uses OAuth2.

Never put refresh tokens into trace baggage/attributes, exposed Redis keys, token-store logs, or error bodies. Even inside Redis/session stores, enforce ACLs, inter-service TLS, TTLs, encryption policies, and console/admin access controls.

### CSRF and CORS do not replace keeping tokens secret

When authenticating via auto-sent browser cookies/sessions, enforce **CSRF** protection on state-changing actions. When frontends call APIs cross-origin, configure **CORS** with explicit origin allowlists and handle preflight before auth when required.

CORS restricts **browsers** only; it never stops a non-browser HTTP client or Gateway holding a token from sending it to another host. Likewise, CSRF protection never stops a developer from enabling wiretap or printing session cookies to logs.

## 13. Never Put Tokens in URLs, Paths, or Fragments for Routing Convenience

A Bearer token in a query parameter:

~~~http
GET /api/reports?access_token=<secret> HTTP/1.1
~~~

can surface in:

- Reverse proxy, CDN, or Gateway access logs.
- Browser history and bookmarks.
- Analytics/monitoring capturing raw URLs.
- Links pasted to support or external partners.
- `Referer` headers under certain navigations and browser policies.
- Caches keyed on URLs or cache metadata.

**Recommendation:** For standard HTTP APIs, use `Authorization: Bearer ...` over HTTPS with clear header-logging and forwarding policies. Never put refresh tokens in queries or paths. URL fragments `#...` are omitted from standard HTTP request targets, yet remain readable by JavaScript, browser extensions, and client-side analytics—so **never treat fragments as safe credential storage**.

### OAuth2 callbacks with authorization codes

The Authorization Code flow carries a **short-lived authorization code** in the callback URL per protocol. Although a code differs from an access token, it remains sensitive data. With Authorization Code + PKCE, stealing a code alone typically cannot redeem a token without a valid `code_verifier`, yet **that is never an excuse to log codes**.

Avoid logging callback query strings, protect `state`/`code_verifier`, lock down redirect URIs, and enforce TLS. On callback errors, return a safe error code/trace ID instead of echoing `code`, `state`, or the raw URL in responses.

### WebSocket and EventSource

Some browser APIs restrict setting custom `Authorization` headers (such as the browser WebSocket API and native `EventSource`). Never work around this by moving long-lived access tokens into `?token=...` and ignoring logging policies.

Architectural options to evaluate per app:

- Session cookies protected with `Secure`, `HttpOnly`, `SameSite`/CSRF, and **Origin validation** on WebSocket handshakes.
- A prior authenticated HTTP call issuing a **short-lived, audience-bound, single-use ticket** for the realtime connection, strictly excluded from logs.
- Clients capable of setting `Authorization` headers natively where protocol and environment permit securely.

None of these options is automatically safe; audit for token/ticket leakage in ingress access logs and replay risks. **HTTP keep-alive does not protect bearer tokens**; TLS protects transit only, never copies sitting in logs or untrusted upstreams.

## 14. Tracing, Baggage, and Metrics: Credentials Are Not Observability Data

Distributed tracing is invaluable for diagnosing why a Gateway request failed in route predicates, filter chains, Spring Cloud LoadBalancer, timeouts, or `CircuitBreaker`. However, **trace propagation** must never carry Bearer tokens as attributes or baggage.

Examples of sensible telemetry:

~~~text
gateway.route.id = orders-private
http.request.method = GET
http.response.status_code = 200
upstream.service = orders-service
error.type = connection_timeout (if applicable)
trace_id = <generated-id>
~~~

Examples **unfit** for tags/labels:

~~~text
http.request.header.authorization = Bearer <token>
http.request.header.cookie = SESSION=<secret>
url.full = /api/orders/42?access_token=<secret>
user.access_token = <token>
session.id = <session-id>
~~~

Tracing **baggage** propagates across multiple services, so putting credentials in baggage **spreads secrets laterally**. Tokens must never serve as correlation IDs; request/trace IDs need independent semantics and validation when accepted from clients.

Practical rules:

1. Capture only an **allowlist** of non-sensitive HTTP headers.
2. Strip query strings from span names/URL attributes, or sanitize against an allowlist of strictly needed params.
3. Use **route templates or route IDs** instead of full raw paths/queries as metric labels.
4. Bound label cardinality; tokens, session IDs, and user IDs create huge cardinality.
5. Apply redaction both in the SDK/agent **before export** and at the collector/exporter as defense in depth.
6. Restrict trace/log viewer permissions, storage locations, retention, third-party exports, and deletion workflows.

### Log error categories instead of secrets

When JWT validation fails, log:

~~~text
route=orders-private result=authentication_failed cause=expired_token
~~~

instead of:

~~~text
Authorization failed for Bearer eyJ...
~~~

Standardize error labels so full exception messages containing raw input never land in logs. Even extracting claims like issuer/subject/tenant requires evaluating personal data rules and access boundaries; never assume all JWT claims are safe to log.

## 15. TLS Protects Transit, Not Recipient Trustworthiness

Evaluate both hops separately:

~~~mermaid
flowchart LR
    Client[Client] -->|HTTPS / TLS 1| Gateway[Spring Cloud Gateway]
    Gateway -->|HTTPS / TLS 2| Upstream[Trusted backend]
~~~

TLS on client → Gateway protects credentials in transit from clients. If TLS terminates at ingress, the Gateway may receive internal HTTP, still requiring proper network segmentation and trust boundaries. On Gateway → backend, verify:

- **HTTPS is actually used** when required by policy.
- Certificate chains, hostnames/SANs, and truststores are valid; **never disable verification** to silence errors.
- With service discovery, `lb://` resolves only to valid hosts/ports/secure schemes inside trusted zones.
- With **mTLS**, certificate service identities are verified and bound to access rights.
- Proxies/sidecars never reroute tokens to unapproved destinations via unreviewed rewrites or redirects.

**HTTPS to an unapproved vendor is still a token leak.** TLS protects data on the wire to **the recipient**, without making that recipient authorized to hold the credential.

For `Forwarded`/`X-Forwarded-Host` headers, trust only authenticated or infrastructure-controlled proxies. If a custom `GatewayFilter` builds outbound URLs or redirects from these headers, clients could hijack the host. Use strict allowlists and validate the final URI.

## 16. Mid-Flow Failures, Retries, and CircuitBreakers Can Duplicate Tokens

The Gateway may call upstream multiple times when using `Retry` `GatewayFilter` or similar resilience mechanisms. Each retry resends the **`Authorization` header**, request body, and other credentials to the selected instance. If a retry hits an untrusted target due to misconfiguration/poisoned discovery, the token is sent repeatedly.

**Retries must be governed by the egress policy:**

- Every retry attempt must obey the exact same audience/destination/credential policy.
- Never retry against another service sharing an interface if it is not approved to receive the token.
- Bound retry counts, deadlines, and allowed HTTP methods.
- For `POST /orders` or payments, require idempotency keys and backend contracts to prevent duplicate side effects.
- Never dump `Authorization`, `Cookie`, or raw header-bearing exceptions into retry/circuit-breaker logs.

**CircuitBreaker fallbacks** may forward to an internal URI like `forward:/internal/fallback`. Fallback handlers must never log the full exchange or treat client-supplied `Authorization` as verified authorization without passing a trusted security context. Never let `401`/`403` auth errors fall back to a fake `200` success.

### Committed responses cannot "switch to 401"

With SSE/NDJSON, the response may have already flushed `200` and partial body chunks. If upstream fails or auth is revoked mid-stream, the Gateway cannot rewind and alter committed status/headers. Stream designs need explicit expiration/disconnect controls, credential refresh, and controlled reconnects—**never embed stream tokens inside error events** sent to clients.

## 17. A Custom GatewayFilter Illustrating Credential Stripping

When the built-in `RemoveRequestHeader` meets your needs, **always prefer it**. When conditional logic is required, you can write a `GatewayFilter` stripping specified credentials **before passing the request to the next filter**.

~~~java
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;

final class CredentialStrippingGatewayFilter {

    private CredentialStrippingGatewayFilter() {}

    static GatewayFilter forAnonymousUpstream() {
        return (exchange, chain) -> {
            ServerHttpRequest sanitized = exchange.getRequest()
                    .mutate()
                    .headers(headers -> {
                        headers.remove(HttpHeaders.AUTHORIZATION);
                        headers.remove(HttpHeaders.COOKIE);
                        headers.remove(HttpHeaders.PROXY_AUTHORIZATION);
                        headers.remove("X-API-Key");
                        headers.remove("X-Auth-Token");
                    })
                    .build();

            return chain.filter(
                    exchange.mutate().request(sanitized).build());
        };
    }
}
~~~

The code above:

1. Never reads or logs the **value** of any token.
2. Builds a request decorator with the specified credential headers removed.
3. Passes the **updated exchange** down the chain via `chain.filter(updatedExchange)`.
4. Returns the `Mono<Void>` publisher to the framework without calling `subscribe()` or `block()`.

In Java Route DSL, attach the filter **strictly to reviewed routes**, for example:

~~~java
// Illustrative snippet inside RouteLocatorBuilder.routes().
.route("public-catalog", r -> r.path("/api/public/products/**")
        .filters(f -> f.filter(
                CredentialStrippingGatewayFilter.forAnonymousUpstream()))
        .uri("lb://catalog-service"))
~~~

This is an **alternative** to the YAML `RemoveRequestHeader` filters in section 6; do not stack both redundantly. In a real project, place the route DSL inside a full `RouteLocator` configuration with version-compatible dependencies.

**Security limitations:** This filter strips listed headers only **at the point it executes**. A later filter could re-attach a token; credentials in URLs/bodies remain untouched; route targets could change. Therefore, it is **not a complete egress enforcement solution** on its own. Combine route policies, trusted discovery, filter-order controls, upstream header tests, and network/TLS protections as analyzed above.

### Unit test: downstream sees neither `Authorization` nor `Cookie`

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CredentialStrippingGatewayFilterTest {

    @Test
    void doesNotPassCredentialsToNextFilter() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/public/products/42")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer synthetic-only")
                        .header(HttpHeaders.COOKIE, "SESSION=synthetic-only")
                        .header("X-API-Key", "synthetic-only")
                        .build());

        AtomicInteger calls = new AtomicInteger();
        GatewayFilterChain downstream = nextExchange -> {
            calls.incrementAndGet();
            HttpHeaders headers = nextExchange.getRequest().getHeaders();

            assertThat(headers.containsKey(HttpHeaders.AUTHORIZATION)).isFalse();
            assertThat(headers.containsKey(HttpHeaders.COOKIE)).isFalse();
            assertThat(headers.containsKey("X-API-Key")).isFalse();
            return Mono.empty();
        };

        StepVerifier.create(
                CredentialStrippingGatewayFilter.forAnonymousUpstream()
                        .filter(exchange, downstream)
        ).verifyComplete();

        assertThat(calls.get()).isEqualTo(1);
    }
}
~~~

This test requires compatible JUnit 5, Spring Test, Reactor Test, and AssertJ versions. It **verifies only the exchange passed to the next filter**, not the final headers sent on the wire by Reactor Netty. Add **integration tests against an upstream stub** verifying final headers after all filters and load balancing. The string `synthetic-only` is dummy test data; never put real access tokens into source code.

## 18. Two-Way Anti-Leakage Test Matrix

The goal is not merely returning `200`/`401`/`403`, but ensuring **secrets never appear anywhere they are forbidden**. For each route, test:

| Scenario | Outcome to Confirm |
|---|---|
| Anonymous request to Catalog | Gateway calls Catalog cleanly without injecting credentials |
| Request carrying valid JWT to public Catalog | Catalog **receives no `Authorization`/`Cookie`** if unneeded by contract |
| Request carrying Orders JWT to Orders route | Forwarded only with matching audience/policy; Orders validates independently |
| Wrong issuer or expired JWT | Security blocks per policy; private upstreams never called |
| User-authority JWT hitting admin route | `403`; admin backend receives neither request nor token |
| Request to vendor route carrying `Authorization`/`Cookie`/API key | Vendor stub receives none of the forbidden headers |
| Service discovery returns unallowlisted instance | Credentials never sent to that instance; policy fails closed |
| A later filter accidentally injects `Authorization` | Integration test catches the leaked egress header |
| Backend returns redirect to untrusted host | Token never auto-forwarded across unapproved hop |
| Login/refresh response carries tokens | Logs, metrics, and traces record neither response bodies nor `Set-Cookie` |
| Client puts token in query or path | Rejected or sanitized per policy; never logged or forwarded casually |
| Errors, timeouts, retries, CircuitBreaker fallbacks | Never dump headers/bodies/tokens in exceptions or error responses |
| WebSocket/SSE reconnects | Tickets/cookies/tokens never logged or sent to wrong services |

### Testing with a backend stub

In your test environment, create an upstream stub that **records in memory** whether forbidden headers arrived, e.g.:

~~~json
{
  "receivedAuthorization": false,
  "receivedCookie": false,
  "receivedApiKey": false
}
~~~

The stub **should never echo token values**, only return booleans or assert against the received request. This lets automated tests verify safety without accidentally creating a public secret-echoing endpoint.

### Canary tokens in the test pipeline

Create a **short-lived, test-environment-only synthetic credential** with a distinct marker value; send it across relevant routes and scan logs, trace storage, and test output to ensure it never appears verbatim. Scan **all real sinks**—ingress, Gateway, backend stub, APM, and error reporting—not just the Gateway console.

With Spring Security Resource Server, **a dummy JWT lacking a valid signature may be rejected with `401` before public route filters even run**, even under `permitAll`. Therefore, test egress using a **valid test JWT from a test issuer** or a controlled test security setup, rather than assuming `Bearer abc` reaches route filters.

### Test-only curl examples

~~~bash
# Never place real tokens directly in commands or curl -v.
# This variable must hold a short-lived TEST token from the test environment.
curl -i \
  -H "Authorization: Bearer ${TEST_ACCESS_TOKEN}" \
  'http://localhost:8080/api/public/products/42'

# Test an auth-required route; backend checks audience/scope independently.
curl -i \
  -H "Authorization: Bearer ${TEST_ACCESS_TOKEN}" \
  'http://localhost:8080/api/orders/42'
~~~

These commands show how to invoke tests, **not proof of execution**. Run against local/HTTPS test labs, never with production tokens; remember process args, terminal history, CI logs, and shell tracing can expose secrets if unguarded. In automated tests, use secret management and HTTP test clients so tokens never appear in process arguments or logs.

## 19. Incident Scenario and Response When a Token Leak Is Discovered

Suppose one day `TRACE` logs on the Gateway are found storing raw `Authorization` headers on the Orders route. Turning off logging immediately is necessary yet **insufficient**, because copies may already sit in log archives and APMs.

Conceptual incident response workflow:

1. **Contain immediately:** disable unnecessary dumps/wiretap, halt misconfigured exporters, and lock down log access; preserve evidence per incident-response policy.
2. **Identify the leaked secret type:** access token, refresh token, session cookie, or signing key? Impact and remediation differ.
3. **Map timeframe and storage locations:** Gateway, ingress, sidecars, backends, APM, SIEM, backups, support attachments, and test/prod environments.
4. **Revoke/limit replayability:** revoke or invalidate tokens/sessions if supported by IdP/session store; for short-lived tokens lacking instant revocation, combine TTLs, privilege tightening, and anomaly detection.
5. **Rotate secrets where warranted:** rotate exposed refresh tokens, API keys, or client credentials; **do not assume a global signing-key rotation is required** for one leaked access token unless evidence shows the signing key or issuer was compromised.
6. **Hunt for suspicious access:** signs of unexpected token use, unauthorized routes/services, or anomalous admin actions. Keep real tokens out of alerts.
7. **Purge stored copies:** execute deletion, retention, legal hold, notification, and copy-control procedures per organizational policy.
8. **Fix the root cause:** switch logging to allowlists, add egress stripping/policies, tighten route/discovery controls, and add integration tests.
9. **Prevent recurrence:** audit framework upgrades, debug toggles, APM instrumentation changes, and ingress config changes.

If only **one user's access token** leaked, revoking that user's token/session is usually more targeted than invalidating the entire system. If a **broadly scoped refresh token** leaked, account for newly minted access tokens; if a **signing key or OAuth2 client secret** leaked, the blast radius is much larger.

### Design alerts that do not repeat the leak

A secret-detection scanner finding credentials in logs must never post **the raw credential string** into team Slack, email, or tickets. Alert with leak type, sink location, time window, incident ID, and an access-controlled reference. Secret scanners can use dedicated markers/fingerprints and strict read ACLs without creating a new central archive of copied tokens.

## 20. Secure Deployment Checklist for Spring Cloud Gateway

Before promoting any new route to production, verify layer by layer:

| Layer | Verification Question | Expected Evidence |
|---|---|---|
| **Route classification** | Public, authenticated, admin, internal, or third party? | Route inventory with owner and security policy |
| **Authentication** | Are inbound tokens checked for signature, issuer, expiry, and right audience? | Valid/invalid token tests and Spring Security policy |
| **Authorization** | Does caller hold right scope/role/resource ownership? | Anonymous/user/admin tests and backend ownership checks |
| **Token egress** | Does the route truly need a token? Which type and audience? | Token allowlist/stripping policy and backend tests |
| **Other credentials** | Are Cookies, API keys, `Proxy-Authorization`, or refresh tokens needed? | Tests verifying zero unintended forwarding |
| **Target URI** | Are routes, redirects, discovery, and hosts/ports controlled by trusted sources? | Registry/route RBAC, host allowlists, network policies |
| **TLS/mTLS** | Are certificates and service identities verified on outbound hops? | TLS, truststore, hostname, and mTLS tests if required |
| **Logging** | Are full headers, queries, bodies, `Set-Cookie`, or secret-bearing errors logged? | Config audit and canary-token test results |
| **Tracing/metrics** | Are `Authorization`, `Cookie`, or URL tokens captured in baggage/tags? | Span payload, exporter, and metric label audits |
| **HTTP filters** | Does `RemoveRequestHeader` run before egress? Can later filters re-add tokens? | Integration tests against upstream stubs |
| **Errors/retries** | Can retries/fallbacks route tokens elsewhere or print secrets? | Timeout, no-instance, redirect, and retry tests |
| **Management** | Are Actuator, route definitions, configs, diagnostics, and logs protected? | Access controls; only necessary endpoints exposed |
| **Storage** | Are access/refresh tokens and sessions kept in secure stores? | TTL, rotation/revocation, encryption, and ACLs |
| **Incident response** | If a token leaks, can you find copies and revoke it? | Runbook, safe alerts, purge/rotation procedures |

Specifically, a route can be **functionally passing** yet **fail security**. For example:

~~~text
GET /api/public/products/42 -> 200 OK
~~~

does not prove the backend **received no access token**, the CDN **did not log queries**, or telemetry **did not capture `Cookie`**. Security testing requires evidence from **destination stubs and data sinks**, not merely status codes and JSON bodies.

### Extra rules for dynamic routes

If the application permits runtime route creation/edits, every change must pass review and automated checks equivalent to code deployments:

1. Never route from the Internet to internal addresses or metadata endpoints outside allowlists.
2. Never let a new service ID automatically receive user/admin tokens.
3. Never downgrade `https://` to `http://` on outbound hops requiring protection.
4. Never attach `TokenRelay` or `SetRequestHeader=Authorization` to vendor routes without approval.
5. Never expose Actuator/Gateway route-management endpoints to the Internet for untrusted egress edits.
6. Never build proxy URIs from user queries/headers, and never rely solely on route IDs when resolved hosts can change.

**Fail closed:** if service identity, audience, or token-forwarding authority cannot be confirmed, never release credentials "just to see if the backend accepts them".

## 21. Comprehensive Exercise: Protecting One Public Route and One Private Route

**Scenario:** An API gateway serves public Catalog, login-protected Orders, scope-restricted Admin, and an external recommendations vendor. The Gateway uses filter chains, discovery, TLS, and tracing. Your team must prove **tokens never appear in logs and never forward to unapproved services**.

### Part A — Design the egress policy

1. Build a matrix like section 5: route ID, URI, service identity, credential type, audience, authorities, and forward yes/no.
2. Enforce **deny-by-default forwarding** for any route outside the allowlist.
3. On Catalog and Vendor, use `RemoveRequestHeader` to strip `Authorization`, `Cookie`, API keys, and unnecessary custom token headers.
4. For Orders, decide whether the client's token matches Orders' audience or requires token exchange; have the backend enforce per-order ownership.
5. For Admin, verify authorities and service identity over TLS/mTLS per policy; never send the same credential to analytics services.

### Part B — Configure safe logging

1. Disable HTTP server/client wiretap or verify it is off anywhere real credentials flow.
2. Add `SafeGatewayAccessLogFilter` from section 10 or equivalent logging/metrics tooling recording only route ID, method, status, signal, and latency if needed.
3. Configure ingress, sidecars, backend stubs, and APM not to store `Authorization`, `Cookie`, `Set-Cookie`, raw queries, or login bodies.
4. Ensure JWT validation errors and `CircuitBreaker` fallbacks never log full exceptions/messages containing tokens.

### Part C — Run trust-boundary tests

1. Using a **valid test access token** from a test issuer with right audience/scope, call public Catalog. Upstream stub must confirm **zero `Authorization`/`Cookie` headers**.
2. Call Orders with an Orders-audience token; backend validates token and returns ownership-checked data.
3. Call Admin with a regular user token; Gateway rejects and admin upstream **is never called**.
4. Call Vendor with test token and dummy API key; stub sees zero client credentials.
5. Point a discovery instance or test route host to an **unallowlisted** target; verify policy blocks sending the token.
6. In an **isolated test environment**, temporarily enable a filter re-adding `Authorization` after removal; verify the integration test catches the leak, then remove the bad filter.
7. Trigger errors/timeouts/retries and inspect traces/APM/exported logs to confirm zero replayable credentials appear.

### Part D — Audit URLs and sessions for tokens

1. Send a test request with query parameter `access_token` carrying a **dummy value**; verify the route rejects/sanitizes per policy. Never use real tokens.
2. Verify login/OAuth2 callbacks keep codes, verifiers, access tokens, and refresh tokens out of access logs.
3. Verify session response `Set-Cookie` headers are never dumped into logs/traces.
4. Test SSE/WebSocket handshakes in the lab; verify tickets/credentials follow contract and are never logged by ingress.
5. Confirm test tokens/secrets expire or get revoked after completing the lab.

**Pass criteria:** (1) Approved destinations receive only required credentials; (2) Catalog/Vendor receive zero unauthorized tokens/cookies; (3) private/admin backends verify tokens/audiences/permissions themselves; (4) logs, traces, metrics, error responses, and debug artifacts contain zero raw tokens; (5) TLS and route/discovery sources are protected; (6) test matrix, upstream stub evidence, and leak-response runbook are complete.

## 22. Common Misconceptions

| Misconception | Reality |
|---|---|
| "Once the Gateway validates the JWT, `Authorization` won't be forwarded." | Validation and forwarding are separate decisions; verify outbound headers explicitly. |
| "Services inside our VPC can safely receive any token." | An internal network does not make every service a valid audience or trust domain. |
| "Tokens sent over HTTPS are safe to send to any vendor." | TLS secures the wire; it grants no authorization to the recipient. |
| "Adding `TokenRelay` automatically secures private routes." | `TokenRelay` needs an OAuth2 client context and does not replace authN/authZ/audience checks. |
| "Stripping `Authorization` on public routes is enough." | Audit `Cookie`, API keys, queries, bodies, `Set-Cookie`, later filters, and all log/trace sinks. |
| "Masking `Bearer` with a regex is sufficient." | Secrets take many forms across many sinks; avoid collecting secrets upfront. |
| "Turning off Gateway logs stops token leaks." | Ingress, CDNs, backends, Netty wiretap, APM, SIEM, or support artifacts can still retain them. |
| "Route name is allowlisted, so the host is trusted." | Service discovery, route rewrites, and redirects can alter the real target; verify trust to the final endpoint. |
| "CORS stops tokens from being forwarded to other services." | CORS is a browser policy and does not govern Gateway proxying. |
| "A validly signed JWT works across all microservices." | Must verify issuer, expiry, audience, scope, and resource permissions; token exchange may be needed. |
| "Disabling logs closes a token-leak incident." | Old copies still exist; perform proper revocation/rotation and incident management. |

## 23. Summary

- **Access tokens, refresh tokens, ID tokens, session cookies, and API keys serve different purposes**; never let every credential ride along on every request by default.
- **Authenticating at the Gateway does not automatically establish a safe outbound policy.** Each route must define approved targets, audiences/scopes, and forwardable credential types.
- Use `RemoveRequestHeader` or tested filters to **strip `Authorization`, `Cookie`, and unnecessary secrets** from requests to public Catalogs, vendors, or unauthorized services.
- **`TokenRelay` is solely a mechanism to pass an access token in an OAuth2 Client context**; it does not replace audience policies, service identity, TLS, authorization, or token exchange when needed.
- **Never log raw headers, query strings, sensitive request/response bodies, `Cookie`, `Set-Cookie`, JWTs, or authorization codes.** Log safe allowlisted metadata like route ID, method, status, and valid trace IDs.
- **Wiretap, ingress logs, APM, tracing baggage, metrics, and error handlers** can all leak secrets; audit both inbound and outbound paths.
- **Service discovery, dynamic routes, redirects, retries, and fallbacks** can alter where credentials go or duplicate requests. Protect route sources, resolved targets, network egress, and TLS/mTLS.
- **Testing at backend stubs and telemetry sinks** is the only way to prove tokens are neither improperly forwarded nor logged. If a leak happens, remediate both the credentials and stored copies rather than merely disabling debug logging.

Keeping tokens bound to their rightful **recipient, purpose, lifetime, and permission scope** is foundational for Spring Cloud Gateway to act as a secure, observable, and operable microservices entry point.
