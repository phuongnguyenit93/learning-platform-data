# Forwarding Only Allowed Headers

In a microservice architecture, `order-service` may call `inventory-service` using the logical URL `http://inventory-service`. Spring Cloud LoadBalancer looks up `ServiceInstance`s by service ID, picks a replica, and lets `RestClient`, `RestTemplate`, `WebClient`, or OpenFeign send the HTTP request to the target. Alongside the URL, method, and body, a request carries **HTTP headers**; if a service accidentally copies all headers received from its caller to downstream, data that should never cross a trust boundary can be forwarded as well.

For example, an `Authorization` header meant for a public API may not fit `inventory-service`; a browser `Cookie` should not travel along internal calls; `X-Forwarded-Host` or `X-Tenant-Id` self-supplied by an untrusted client can deceive routing and authorization logic; and connection-control headers like `Connection` must not be copied blindly onto a new HTTP hop.

**Core principle of this lesson:** when service A calls service B, **construct new headers from an allowlist designed for that specific operation**, rather than copying all inbound headers and stripping a few "dangerous-looking" names. A header should only be forwarded when it is genuinely needed, its value has been validated/normalized, the recipient is permitted to see it, and the HTTP client is left in charge of managing protocol fields.

## 1. Trust Boundaries Across a LoadBalancer Call Chain

Suppose the business flow is:

```text
Browser / External Client
        |
        v
API Gateway (authenticates, normalizes request)
        |
        v
order-service
        |  @LoadBalanced RestClient/WebClient/Feign
        v
Spring Cloud LoadBalancer selects inventory-A or inventory-B
        |
        v
inventory-service
```

An inbound request might contain:

```http
GET /api/orders/42 HTTP/1.1
Host: public.example.test
Authorization: Bearer <external-access-token>
Cookie: session=<browser-session>
X-Forwarded-Host: attacker.example.test
X-Tenant-Id: forged-tenant
Accept-Language: vi
X-Correlation-Id: user-controlled-value
Connection: keep-alive
```

You must **not** pass that request through verbatim as:

```http
GET /api/v1/items/42 HTTP/1.1
Host: inventory-service
Authorization: Bearer <external-access-token>
Cookie: session=<browser-session>
X-Forwarded-Host: attacker.example.test
X-Tenant-Id: forged-tenant
...
```

Because the two calls differ in **audience, access permissions, transport hop, target host, and API contract**. The fact that the API Gateway authenticated the caller does not make every header sent by the caller trustworthy. In particular, an `X-User-Id` header is not proof of identity if it was self-asserted externally.

```mermaid
flowchart TD
    E[External client: untrusted headers] --> G[Gateway: authenticate, strip spoofed headers, create trusted context]
    G --> A[order-service]
    A --> P[Per-operation allowlist header projection]
    P --> L[Spring Cloud LoadBalancer: select ServiceInstance]
    L --> H[HTTP client builds new request]
    H --> B[inventory-service]
    A -.-> X[Never copy full inbound headers]
    P -.-> Y[Never relay Cookie / Authorization / X-Forwarded-* arbitrarily]
```

**LoadBalancer does not automatically filter sensitive data out of inbound requests.** It picks a target by `service ID` and matching discovery/metadata; the application, gateway, and HTTP client themselves must decide which headers accompany an outbound request.

## 2. Why Is an Allowlist Safer Than Copy-All or a Denylist?

There are three common approaches:

| Approach | Implementation | Risk |
|---|---|---|
| **Copy-all** | Copies all inbound headers onto the outgoing request | Leaks tokens, cookies, spoofed headers, hop-by-hop fields, proxy metadata |
| **Denylist** | Copies everything except banned names | New/renamed headers slip right through; no clear boundary |
| **Allowlist** | Outbound request contains only names and values permitted for the operation | Easy to audit; unknown data is not transmitted by default |

Example of code you **should not use**:

```java
// WRONG: bulk-copying data from an external request into downstream.
restClient.get()
        .uri("/api/v1/items/42")
        .headers(out -> out.addAll(incomingHeaders))
        .retrieve()
        .body(ItemDto.class);
```

It is not just `Authorization` or `Cookie`: later a middleware layer might add `X-Internal-Role`, `X-Debug-Token`, or `X-Session-Metadata` to inbound headers. With copy-all, they get forwarded automatically without privacy or security review.

**An allowlist is an application contract**, and should be defined through concrete decisions:

1. Which headers are meaningful for the operation? For example, `Accept-Language` for localizing item descriptions.
2. Who is allowed to set the value? External caller, API Gateway after authentication, or `order-service` deriving it from security context?
3. What type, length, format, and allowed set must the value satisfy?
4. Is the recipient authorized to use this data? Does it need scoping by tenant/scope/audience?
5. Is the header an HTTP transport, tracing, or identity field that the framework must handle specially?

There is no single allowlist that works for every service. For an inventory GET, `Accept-Language` may make sense; for a charge-creation POST, a normalized `Idempotency-Key` may be needed, whereas there is no reason to send browser cookies or website tokens.

## 3. Classifying Headers Before Forwarding

| Header / Group | Typical Decision | Explanation |
|---|---|---|
| `Accept-Language` | **Conditionally allowed** | Useful for localized content; must validate/sanitize |
| `X-Correlation-Id` | **Use trusted value only** | Created or normalized by gateway; used to correlate logs, not a credential |
| `traceparent`, `tracestate` | **Let tracing library handle** | Context propagation must follow trust policy, never blind copy |
| `baggage` | **Strictly bounded** | Can contain PII, tenant, or sensitive data; transmit only approved fields |
| `Idempotency-Key` | **Only on appropriate write operations** | Requires stable key, format/size limits, and scoping per tenant/operation |
| `If-Match` / `If-None-Match` | **Per API contract** | Meaningful for optimistic locking or cache validation |
| `Accept` / `Content-Type` | **Set per outbound request** | Depends on target body/representation; do not copy blindly from inbound |
| `Authorization` | **Never relay arbitrarily** | Token must match audience, scopes, and delegation policy |
| `Cookie`, `Set-Cookie` | **Never copy by default** | Browser/session data should not travel to unrelated services |
| `X-User-Id`, `X-Role`, `X-Tenant-Id` | **Never trust client-sent headers** | Identity/roles/tenant must come from authenticated context |
| `Forwarded`, `X-Forwarded-*`, `X-Real-IP` | **Never forward raw inbound** | Only trusted proxies may construct/normalize them, preventing spoofing |
| `Host`, `Content-Length`, `Transfer-Encoding` | **Let HTTP transport construct** | Tied to target connection and framing; never copy from original request |
| `Connection`, `Keep-Alive`, `Upgrade` | **Do not forward across new hops** | Usually hop-by-hop; handled by proxy/client per HTTP semantics |
| `Proxy-Authorization` / `Proxy-Authenticate` | **Do not relay to app upstreams** | Headers meant for proxy authentication |
| `X-Debug-*` or unfamiliar internal headers | **Deny by default** | Require explicit review and approval; never use wildcards |

**Note:** This is an example policy table for service-to-service microservice requests, not a rigid HTTP list banning every name in every architecture. For instance, a properly configured reverse proxy can emit `Forwarded` or `X-Forwarded-For` at the trust boundary. The key rule is **never take a value self-asserted by an external client and trust it as if the proxy verified it**.

### 3.1. Hop-by-Hop Headers and Transport-Managed Fields

Under HTTP semantics, `Connection` can list **header names that apply solely to the current connection**:

```http
Connection: keep-alive, X-Connection-Debug
X-Connection-Debug: internal
```

A standards-compliant HTTP intermediary must not blindly forward fields listed in `Connection` to the next hop. Because that list **can vary per request**, banning only the literal `Connection` header while copying all other headers still fails. For outbound RestClient/WebClient/Feign calls, building fresh headers from a small allowlist and letting the HTTP stack handle protocol fields is far safer.

`Host` should never come from the inbound request: the HTTP client must build authority/host from the selected `ServiceInstance`'s URI. Do not manually set `Content-Length` when the library already manages framing and body; sending a mismatched byte count causes protocol errors and creates security issues in complex proxy setups.

Headers such as `Accept-Encoding`, `TE`, `Transfer-Encoding`, `Trailer`, and `Upgrade` carry protocol-specific semantics; exclude them from business allowlists unless you are genuinely implementing a compliant HTTP proxy.

## 4. Authentication, Identity, and Tenant: Presence of a Header Does Not Equal Trust

Three common anti-patterns:

```text
inbound.Authorization            -> outbound.Authorization       (blind token relay)
inbound.X-Tenant-Id              -> outbound.X-Tenant-Id         (trusting user-claimed tenant)
inbound.X-Forwarded-For          -> outbound.X-Forwarded-For     (trusting user-claimed IP)
```

Risks include **credential leakage**, crossing audience boundaries, acting on the wrong tenant, and bypassing header-based authorization logic.

### 4.1. Two Service-to-Service Authentication Models to Distinguish

**Service-to-service identity:** `order-service` identifies itself as a service when calling `inventory-service`. It can use OAuth 2.0 client credentials or infrastructure-managed mTLS/service identity. Outbound credentials are issued and managed by the security layer—**never copied from an inbound user token**.

**On-behalf-of / user delegation:** some operations must execute on a user's behalf. In that case, the token must be checked for audience, scopes, expiry, and delegation policy; the system may require token exchange or an authorization-server-backed delegation flow. Never assume an access token issued for `api.example.test` is automatically valid for `inventory-service`.

Service B must still enforce resource/tenant authorization. An internal header does not become an authentication source if an untrusted connection could forge it.

### 4.2. Never Derive Identity from Caller-Supplied Headers

Suppose a caller sends:

```http
X-User-Id: admin
X-Role: SUPERUSER
X-Tenant-Id: tenant-other
```

If the gateway fails to strip/overwrite these headers, an interceptor copying them verbatim downstream can trick `inventory-service` into trusting spoofed values. Instead, identity claims must originate from the **authenticated principal/claims object** and pass through a trusted delegation mechanism or an authenticated, integrity-protected internal context.

If a project uses an internal tenant header under an explicit contract, verify that the internal channel's caller is genuinely authenticated, the tenant value matches the principal, and downstream **rejects** the same header arriving over untrusted public channels. Treating an internal header as a bare arbitrary string is insufficient.

## 5. Tracing and Correlation: Enabling Observability Does Not Grant Permissions

`traceparent` and `tracestate` are typically produced/managed by OpenTelemetry/Micrometer Tracing or equivalent instrumentation. They connect spans along A → B → C, yet they **prove nothing** about who authenticated and must never be used for access control.

For requests arriving from the Internet, a gateway may accept a valid `traceparent` per tracing policy or start a new trace; trusting external sampling flags, baggage, or metadata requires explicit rules. **Never put tokens, passwords, card numbers, emails, or user permissions into `baggage` just for convenient debugging.**

An application-defined `X-Correlation-Id` can help tie logs across services. Restrict its length/characters to prevent CR/LF injection, and **never use a correlation ID as a credential or authorization key**.

For instance, an app accepting an external `X-Correlation-Id` must sanitize/normalize it at ingress, generating a new ID if invalid. However, if the threat model forbids client control over correlation IDs, always generate a fresh ID at the gateway.

Never copy all tracing headers manually via `incomingHeaders` and also let instrumentation inject them again: that can duplicate values, corrupt context, or accidentally propagate disallowed baggage.

## 6. Designing a Per-Operation Header Projection Layer

Instead of calling `HttpHeaders.addAll(inbound)` on outbound requests, build a helper that **constructs fresh** `HttpHeaders` from approved names. For a lab example of **GET item read**, you only need:

- `Accept: application/json` set by the gateway itself, not copied from the incoming request.
- `Accept-Language` if the input is an approved simple language tag.
- `X-Correlation-Id` generated by ingress/gateway or validated from a trusted context.

In this example, **do not** forward `Authorization`, `Cookie`, `X-Tenant-Id`, `Forwarded`, `Host`, `Connection`, or any unlisted header.

```java
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

public final class AllowedHeaderProjector {

    private static final Pattern CORRELATION_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    // Intentionally narrow policy for lab: vi, en, en-US...
    // Not a full HTTP Accept-Language parser.
    private static final Pattern SIMPLE_LANGUAGE =
            Pattern.compile("[A-Za-z]{2,3}(?:-[A-Za-z]{2})?");

    private AllowedHeaderProjector() {
    }

    public static HttpHeaders forItemRead(
            HttpHeaders incoming, String trustedCorrelationId) {

        Objects.requireNonNull(incoming, "incoming headers");
        Objects.requireNonNull(trustedCorrelationId, "correlation id");

        if (!CORRELATION_ID.matcher(trustedCorrelationId).matches()) {
            throw new IllegalArgumentException(
                    "Invalid trusted correlation identifier");
        }

        HttpHeaders outgoing = new HttpHeaders();
        outgoing.setAccept(List.of(MediaType.APPLICATION_JSON));
        outgoing.set("X-Correlation-Id", trustedCorrelationId);

        List<String> languages =
                incoming.get(HttpHeaders.ACCEPT_LANGUAGE);

        // Accept only a single simple field-value.
        // Multiple values or invalid strings are not relayed.
        if (languages != null && languages.size() == 1) {
            String language = languages.get(0);
            if (SIMPLE_LANGUAGE.matcher(language).matches()) {
                outgoing.set(HttpHeaders.ACCEPT_LANGUAGE, language);
            }
        }

        return outgoing;
    }
}
```

Key details:

1. `outgoing` is a **new instance**; there is no copy-all anywhere.
2. `Accept` comes from the **outbound contract**, not from browser-sent headers.
3. `Accept-Language` is restricted to an **intentionally simple syntax** in the lab. Real headers can carry lists and `q` weights; full support requires a proper parser, size limits, and normalization before forwarding. Never widen forwarding blindly by removing the regex.
4. `X-Correlation-Id` comes solely from a **trusted parameter**, created/validated by a trusted layer. The helper does not verify the parameter's provenance: callers of the helper must uphold that boundary.
5. Malformed `Accept-Language` values are dropped rather than forwarded downstream; stricter systems may choose to return HTTP 400 per contract.

**Scope limitation:** this example only governs **application-originated request headers**. The HTTP transport will still generate valid protocol fields like `Host`, `Content-Length`, or connection headers, and tracing instrumentation may add configured context. Do not inspect raw wire bytes expecting only the three headers above.

### 6.1. Generating a Correlation ID at the Trust Boundary

A sample `order-service` controller can generate a new ID rather than trusting an externally supplied value:

```java
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ItemProxyController {

    private final InventoryGateway gateway;

    ItemProxyController(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/api/proxy/items/{id}")
    ItemDto get(
            @PathVariable String id,
            @RequestHeader HttpHeaders inboundHeaders) {

        // Each inbound request gets an application-generated correlation ID.
        // May be taken from a trusted gateway context if infrastructure verified it.
        String trustedCorrelationId = UUID.randomUUID().toString();

        return gateway.getItem(
                id, inboundHeaders, trustedCorrelationId);
    }
}
```

This controller does not relay `inboundHeaders.getFirst("X-Correlation-Id")`, does not use cookies, and does not treat `X-Tenant-Id` as access permission. In systems with centralized tracing, leverage instrumentation-managed traces/spans rather than minting ad-hoc IDs per hop; this example simply illustrates **a trusted origin for an application header**.

## 7. RestClient: Sending Allowed Headers Through a Service ID

A Spring Boot app on Spring Framework 6.1+ and compatible Spring Cloud can define a `@LoadBalanced RestClient.Builder`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

The gateway applies the projector for the exact operation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ItemDto(String id, String name, int available) {
}

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    ItemDto getItem(
            String id,
            HttpHeaders incoming,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                incoming, trustedCorrelationId);

        return restClient.get()
                .uri("/api/v1/items/{id}", id)
                .headers(outgoing -> outgoing.addAll(allowed))
                .retrieve()
                .body(ItemDto.class);
    }
}
```

`outgoing.addAll(allowed)` is **completely different** from `addAll(incoming)`: `allowed` is freshly constructed from a validated allowlist. When using a `@LoadBalanced` `RestClient.Builder` and discovery knows `inventory-service`, LoadBalancer selects a `ServiceInstance` per call as configured; header filtering does not alter Round Robin/Random algorithms.

Example `application-lab.yml` with two instances:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8091
              - uri: http://localhost:8092
```

Lab prerequisites: Spring Cloud BOM compatible with Spring Boot; client includes `spring-cloud-starter-loadbalancer` and the matching HTTP starter. `SimpleDiscoveryClient` only provides a static list; it does not validate headers for the app and does not perform full instance health discovery. Inside containers, `localhost` refers to the client's container, not the host or provider container.

### 7.1. RestTemplate Also Needs a Fresh HttpEntity

For code using `@LoadBalanced RestTemplate`:

```java
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

ItemDto findWithRestTemplate(
        RestTemplate loadBalancedRestTemplate,
        String id,
        HttpHeaders incoming,
        String trustedCorrelationId) {

    HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
            incoming, trustedCorrelationId);

    HttpEntity<Void> request = new HttpEntity<>(allowed);

    ResponseEntity<ItemDto> response =
            loadBalancedRestTemplate.exchange(
                    "http://inventory-service/api/v1/items/{id}",
                    HttpMethod.GET,
                    request,
                    ItemDto.class,
                    id);

    return response.getBody();
}
```

This is an **illustrative method**, assuming the passed-in `RestTemplate` is configured with LoadBalancer and proper timeouts. Never write `new HttpEntity<>(incoming)` when sourced from a public request: doing so bypasses the allowlist policy.

## 8. WebClient: Avoid Copy-All in Reactive Filters

With Spring WebFlux, `@LoadBalanced WebClient.Builder` enables calls by service ID:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Gateway applying only projected headers:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final WebClient client;

    ReactiveInventoryGateway(
            @Qualifier("loadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<ItemDto> getItem(
            String id,
            HttpHeaders inbound,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                inbound, trustedCorrelationId);

        return client.get()
                .uri("/api/v1/items/{id}", id)
                .headers(headers -> headers.addAll(allowed))
                .retrieve()
                .bodyToMono(ItemDto.class);
    }
}
```

Because WebClient requests typically execute upon subscription, code must not rely on a `ThreadLocal`/`RequestContextHolder` at HTTP send time to silently grab inbound headers; threads can differ and context can be lost or misapplied. **Pass normalized values explicitly** through an operation context object or Reactor Context with explicit rules.

When using an `ExchangeFilterFunction` to attach shared headers, ensure the filter only adds authenticated/authorized headers (such as managed tracing), never copying `ServerHttpRequest.getHeaders()` wholesale. Be especially careful not to inject user tokens into all outbound requests via a shared `WebClient.Builder`.

## 9. OpenFeign: Declare Allowed Headers Explicitly in the API Contract

Feign can accept allowed headers as explicit method parameters, avoiding a `RequestInterceptor` that reads the entire `HttpServletRequest`:

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/api/v1/items/{id}")
    ItemDto getItem(
            @PathVariable("id") String id,
            @RequestHeader("Accept-Language") String language,
            @RequestHeader("X-Correlation-Id") String correlationId);
}
```

The client app needs `spring-cloud-starter-openfeign`, `spring-cloud-starter-loadbalancer`, and a Spring Cloud BOM compatible with Spring Boot. Enable `@EnableFeignClients` on the Spring Boot app or configure the Feign scan scope; the interface above uses `ItemDto` defined in section 7.

The service layer normalizes inputs before calling:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;

@Service
class InventoryFeignGateway {
    private final InventoryFeignClient client;

    InventoryFeignGateway(InventoryFeignClient client) {
        this.client = client;
    }

    ItemDto getItem(
            String id,
            HttpHeaders incoming,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                incoming, trustedCorrelationId);

        // Example contract requires a language; fallback is "vi".
        String language = allowed.getFirst(HttpHeaders.ACCEPT_LANGUAGE);
        if (language == null) {
            language = "vi";
        }
        return client.getItem(
                id, language, allowed.getFirst("X-Correlation-Id"));
    }
}
```

Benefit: during interface review, readers see the exact **two application headers** the operation accepts. Feign's HTTP layer can still add protocol headers, encoder headers, or tracing instrumentation as appropriate.

If choosing a `RequestInterceptor` because many methods share context, configure the interceptor **per Feign client** and read solely from a trusted context. Avoid patterns like:

```java
// WRONG: bulk-relaying values controlled by the inbound caller.
// Especially dangerous for Authorization, Cookie, X-User-Id...
template.headers(incomingHeaders);
```

This snippet illustrates an **anti-pattern**, not a runnable snippet with full imports. Avoid registering a global interceptor carrying credentials for one downstream that accidentally leaks tokens to other service IDs.

### Having an OpenFeign ErrorDecoder Does Not Mean Headers Are Filtered

`ErrorDecoder` maps HTTP error responses to exceptions; it **does not validate** outbound headers. A Feign client with a proper `ErrorDecoder` can still leak browser cookies or tokens if a `RequestInterceptor` copies all inbound headers.

## 10. Write Operations: Idempotency-Key Is Not an Arbitrarily Copied Header

For POSTs creating reservations or payments, safe retries usually require **a stable logical operation identifier**. An `Idempotency-Key` header can be used, but should only be sent when the downstream API has an explicit contract for deduplication, tenant scoping, and result retention window.

Key differences:

| GET Read Item | POST Create Reservation |
|---|---|
| Usually needs no idempotency key | May require an idempotency key |
| `Accept-Language` may be allowed | `Content-Type: application/json` per request body |
| `X-Correlation-Id` from trusted context | `X-Correlation-Id` from trusted context |
| No reason to auto-relay browser cookies | No reason to auto-relay browser cookies |
| Bounded GET retries are generally safer | POST retries are safe only if server prevents duplicate side effects |

In a dedicated header policy class for POST:

```java
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

final class ReservationHeaderProjector {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    private ReservationHeaderProjector() {
    }

    static HttpHeaders forCreate(
            String trustedCorrelationId,
            String stableOperationKey) {

        Objects.requireNonNull(trustedCorrelationId);
        Objects.requireNonNull(stableOperationKey);

        if (!SAFE_ID.matcher(trustedCorrelationId).matches()
                || !SAFE_ID.matcher(stableOperationKey).matches()) {
            throw new IllegalArgumentException(
                    "Invalid internal operation metadata");
        }

        HttpHeaders out = new HttpHeaders();
        out.setAccept(List.of(MediaType.APPLICATION_JSON));
        out.setContentType(MediaType.APPLICATION_JSON);
        out.set("X-Correlation-Id", trustedCorrelationId);
        out.set("Idempotency-Key", stableOperationKey);
        return out;
    }
}
```

This is a **format-bounding example**, not a substitute for authentication/authorization or key randomness. `stableOperationKey` must be generated **once per logical business operation**, persisted/reused across retry attempts, and bound downstream to the operation, tenant/principal, and payload fingerprint. Never treat an unauthenticated user-supplied `Idempotency-Key` as proof that a transaction exists or belongs to them.

If a write request retries with a new key on each attempt, the server may treat them as **two distinct operations**. If retries shift from `reservation-A` to `reservation-B`, the idempotency store must be shared and concurrency-safe, not a local `HashMap` per instance.

### Controlled RestClient POST Example

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ReservationCommand(String itemId, int quantity) {
}

record ReservationResult(String reservationId) {
}

@Service
class ReservationGateway {

    private final RestClient client;

    ReservationGateway(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://reservation-service")
                .build();
    }

    ReservationResult reserve(
            ReservationCommand command,
            String trustedCorrelationId,
            String stableOperationKey) {

        HttpHeaders allowed = ReservationHeaderProjector.forCreate(
                trustedCorrelationId, stableOperationKey);

        return client.post()
                .uri("/api/v1/reservations")
                .headers(out -> out.addAll(allowed))
                .body(command)
                .retrieve()
                .body(ReservationResult.class);
    }
}
```

The snippet uses `@Qualifier` to inject **the exact `@LoadBalanced` bean**, rather than relying on parameter names when multiple builders exist. This demonstrates header sending; it **does not enable retries by itself** and **does not implement server-side idempotency**.

## 11. Response Headers Also Need Their Own Allowlist

The A→B request direction and B→A response direction are **two separate policy boundaries**. Never assume that because `Accept-Language` was safe to send, every response header from the provider is safe to return to the browser.

| Response Header | Example Policy for Public API Output |
|---|---|
| `Content-Type` | Set according to the body the gateway **actually returns**, never copied blindly after transforming data |
| `ETag` / `Last-Modified` | Forward only if still valid for the public representation |
| `Cache-Control` | Governed by gateway cache policy, preventing accidental caching of tenant/private data |
| `Retry-After` | Usable when returning 429/503, after parsing and clamping to bounds |
| `X-Correlation-Id` | If exposed, use the trusted-system-generated/normalized ID |
| `Set-Cookie` | Do not forward internal cookies by default |
| `WWW-Authenticate` | Do not reflect internal challenges to browsers with a different audience |
| `Server`, `X-Powered-By`, internal debug headers | Usually stripped or normalized to minimize infrastructure disclosure |
| `Transfer-Encoding`, `Connection` | Managed by the responding hop's HTTP stack |

For example, suppose a provider returns `Cache-Control: public` on a response holding tenant-private inventory data: if a proxy copies it verbatim, shared caches can store data beyond its intended scope. Similarly, if a proxy transforms the body while still copying upstream's `ETag`, the validator may no longer match the representation delivered to the user.

Never copy `Set-Cookie` from `inventory-service` into a public-domain cookie unless it is part of an approved session design. Nor should you reflect raw error bodies, internal trace headers, or another service's auth challenges verbatim.

### 11.1. Forwarding Status Does Not Mean Forwarding All Metadata

A gateway may choose to return HTTP 404 when upstream returns `ITEM_NOT_FOUND`, or 503 when downstream is temporarily unavailable. Even while preserving the status code, **error payloads and response headers** must still be rebuilt per the public contract to avoid leaking hostnames, stack traces, tokens, and internal routing details.

## 12. When Should You Avoid an Overly Broad Allowlist?

A header safe for operation A can be dangerous for operation B:

| Operation | Headers to Consider | Headers Not to Auto-"Inherit" |
|---|---|---|
| GET catalog | `Accept-Language` | `Idempotency-Key`, user session cookies |
| GET tenant data | Verified auth context, audience-scoped delegation | Browser-asserted `X-Tenant-Id` |
| POST create charge | Stable `Idempotency-Key`, content type, right-audience auth | Website cookies, wrong-audience bearer tokens |
| File upload | Real body `Content-Type`, validated metadata | Caller-claimed `Content-Length` mismatching body |
| Cross-region gateway call | Trace context, trusted region/zone policy | External `X-Forwarded-Host` or tenant headers |

Never combine every header ever allowed on any endpoint into **a single global allowlist** applied to all Feign/RestClient/WebClient calls. Policies must carry **context: target service, operation, data sensitivity, and trust boundary**.

### Header Names Are Case-Insensitive

HTTP field names are case-insensitive: `authorization` and `Authorization` have identical semantics. If a policy compares names using case-sensitive `equals`, attackers can bypass a flawed denylist simply by varying capitalization.

In the `AllowedHeaderProjector` example, we **only query approved names** via `HttpHeaders` and populate a brand-new `HttpHeaders`. That avoids building a denylist across dozens of casing combinations or `X-*` wildcards.

### Headers Can Appear Multiple Times

A request may contain multiple values for the same header, or a single field-value containing a comma-separated list. Do not naively call `getFirst()` on sensitive headers when the contract forbids multiple values; gateways and providers may parse duplicates differently. Policies must specify **whether single or multiple values are allowed, how to normalize them, and how to handle duplicates**.

In section 6's helper, `Accept-Language` with multiple field-values is ignored; that is a simplified lab choice. For `Authorization` or identity headers, never accept ambiguous multi-values and never auto-relay them.

## 13. Lab: Inspecting Requests at the Provider Instead of Only Reading Client Code

The lab uses:

| Component | Port / Service ID | Role |
|---|---|---|
| `order-service` | `localhost:8080` | Receives untrusted requests, applies allowlist, calls downstream |
| `inventory-A` | `localhost:8091` | Returns items, logs received header names |
| `inventory-B` | `localhost:8092` | Identical contract, lets us observe when LoadBalancer picks another replica |
| Logical Service ID | `inventory-service` | Used by `@LoadBalanced` clients |

Configure `SimpleDiscoveryClient` as in section 7. Both providers expose the same endpoint so headers can be observed at both A and B:

```java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryDemoController {

    private final String instanceName;

    InventoryDemoController(@Value("${server.port}") int port) {
        this.instanceName = "inventory-" + port;
    }

    @GetMapping("/api/v1/items/{id}")
    ItemDto item(
            @PathVariable String id,
            @RequestHeader HttpHeaders received) {

        // Log only header names and presence in the lab.
        // Never log token values, cookies, or identities.
        System.out.println(Map.of(
                "instance", instanceName,
                "acceptLanguagePresent",
                    received.containsKey(HttpHeaders.ACCEPT_LANGUAGE),
                "authPresent",
                    received.containsKey(HttpHeaders.AUTHORIZATION),
                "cookiePresent",
                    received.containsKey(HttpHeaders.COOKIE),
                "tenantHeaderPresent",
                    received.containsKey("X-Tenant-Id"),
                "forwardedHostPresent",
                    received.containsKey("X-Forwarded-Host")));

        return new ItemDto(id, instanceName, 12);
    }
}
```

This code is for a **learning environment**: printing every request to stdout is not a production monitoring strategy. Fields like `authPresent` record only **booleans**, never credential values. `ItemDto` on provider and client must share `(String id, String name, int available)` to deserialize cleanly.

Run both provider processes:

```bash
# Terminal A
java -jar inventory-service.jar --server.port=8091

# Terminal B
java -jar inventory-service.jar --server.port=8092
```

Check responses directly:

```bash
curl -i http://localhost:8091/api/v1/items/42
curl -i http://localhost:8092/api/v1/items/42
```

Then start `order-service` with `ItemProxyController` and `InventoryGateway` from sections 6–7. Send a request containing both allowed headers and intentionally disallowed headers:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'Accept-Language: vi' \
  -H 'Authorization: Bearer example-external-token' \
  -H 'Cookie: session=browser-session-example' \
  -H 'X-Tenant-Id: tenant-forged' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Internal-Debug: enabled' \
  -H 'X-Correlation-Id: caller-chosen-value'
```

These are **synthetic lab values**, containing no real credentials. With section 6's helper and no extra auth/tracing layers auto-adding headers, expected observations at the provider are:

| Inbound Header | Present on Outbound? | Reason |
|---|---|---|
| `Accept-Language: vi` | Yes | Valid per GET allowlist |
| `Authorization: Bearer example-...` | **No** | External token is not relayed |
| `Cookie: session=...` | **No** | Browser session is not relayed |
| `X-Tenant-Id: tenant-forged` | **No** | Caller-claimed tenant is untrusted |
| `X-Forwarded-Host: attacker...` | **Spoofed value not forwarded** | Proxy info from untrusted client is not relayed |
| `X-Internal-Debug: enabled` | **No** | Not in allowlist |
| `X-Correlation-Id: caller-chosen-value` | **Original value not kept** | Controller generates a fresh ID |
| `Accept: application/json` | Yes | Set by gateway per outbound contract |
| `Host` | May be present | **Generated by HTTP transport**, not taken from inbound host |

In systems with service authentication or proxy/tracing filters, **certain headers may be legitimately added after the allowlist step**. In that case, verify the value's provenance: an `Authorization` issued by an authorized client for the right audience is completely different from an `Authorization` copied from a browser. Never write a naive production assertion like "no outbound request may ever contain Authorization".

### 13.1. Invalid Input Checks

Try an `Accept-Language` outside the supported syntax:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'Accept-Language: vi,en;q=0.8'
```

Under the lab policy, the list-style value is dropped because the helper supports only one simple language tag; the request can still succeed since `Accept-Language` is optional. For APIs needing full HTTP header support, replace the helper with a parser/validator designed for lists and q-values—never copy raw unvalidated strings straight through.

Try sending unfamiliar headers:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'X-Superuser: true' \
  -H 'X-Internal-Role: admin'
```

Neither header must **ever be copied** to `inventory-service`. If they are ever added later for a legitimate feature, they must go through security review and an updated policy—never appear automatically simply because clients started sending them.

### 13.2. Observing Both Replicas

Send multiple sequential requests through `order-service` and inspect logs on both `inventory-A` and `inventory-B`. With two healthy instances in the static list and Round Robin active, both should receive requests under the configured selection policy. Regardless of which instance is picked, **the allowlist must yield the same safe result**.

This is why interceptors must never synthesize headers from local instance metadata or ambiguous cache state: requests to A and B must uphold the same **security contract**, not just the same business endpoint.

## 14. Unit Tests for the Allowlist and Integration Tests Over Real HTTP

### 14.1. Unit Test: Unlisted Names Do Not Slip Through

Place the test class in a client module with `spring-boot-starter-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

class AllowedHeaderProjectorTest {

    @Test
    void forwardsOnlyApprovedApplicationHeaders() {
        HttpHeaders inbound = new HttpHeaders();
        inbound.set(HttpHeaders.ACCEPT_LANGUAGE, "vi");
        inbound.set("authorization", "Bearer fake-secret");
        inbound.set(HttpHeaders.COOKIE, "session=abc");
        inbound.set("X-Forwarded-Host", "attacker.example.test");
        inbound.set("X-Tenant-Id", "another-tenant");
        inbound.set("X-Internal-Debug", "true");
        inbound.set("X-Correlation-Id", "caller-controlled");

        HttpHeaders result = AllowedHeaderProjector.forItemRead(
                inbound, "trusted-123");

        assertEquals("vi",
                result.getFirst(HttpHeaders.ACCEPT_LANGUAGE));
        assertEquals("application/json",
                result.getFirst(HttpHeaders.ACCEPT));
        assertEquals("trusted-123",
                result.getFirst("X-Correlation-Id"));

        assertNull(result.getFirst(HttpHeaders.AUTHORIZATION));
        assertNull(result.getFirst(HttpHeaders.COOKIE));
        assertNull(result.getFirst("X-Tenant-Id"));
        assertNull(result.getFirst("X-Forwarded-Host"));
        assertNull(result.getFirst("X-Internal-Debug"));
        assertFalse(result.containsKey(HttpHeaders.HOST));

        // Only the three application header names are produced by the projector.
        assertEquals(3, result.size());
    }

    @Test
    void ignoresUnsupportedLanguageFormat() {
        HttpHeaders inbound = new HttpHeaders();
        inbound.set(HttpHeaders.ACCEPT_LANGUAGE, "vi,en;q=0.8");

        HttpHeaders result = AllowedHeaderProjector.forItemRead(
                inbound, "trusted-456");

        assertNull(result.getFirst(HttpHeaders.ACCEPT_LANGUAGE));
    }

    @Test
    void rejectsInvalidTrustedCorrelationId() {
        HttpHeaders inbound = new HttpHeaders();
        assertThrows(IllegalArgumentException.class,
                () -> AllowedHeaderProjector.forItemRead(
                        inbound, "bad id with spaces"));
    }
}
```

This is a unit test of **header projection**, not verification of the full HTTP transport. The output `HttpHeaders` lacks `Host`, yet the transport still adds `Host` when sending HTTP/1.1. If a security filter later attaches a right-audience service token, the projector test does not need to know about that.

### 14.2. Integration Tests Must Verify Headers Actually Arriving at the Provider

A strong integration test should include:

1. An HTTP stub server running on a dynamic port.
2. `SimpleDiscoveryClient` in the test context returning that stub's address as an instance.
3. A **real** `@LoadBalanced RestClient`, WebClient, or Feign client sending requests by service ID.
4. The stub server recording received headers and returning valid JSON.
5. Assertions proving `Accept-Language` and the normalized correlation ID arrived, while inbound `Cookie`, external tokens, spoofed tenants, and debug headers **were not relayed**.

Example key assertions (pseudocode, not default Spring APIs):

```text
captured.get("Accept-Language") == "vi"
captured.get("X-Correlation-Id") == trustedId

captured.get("Authorization") != inboundBearerToken
captured.has("Cookie") == false
captured.has("X-Tenant-Id") == false
captured.get("X-Forwarded-Host") != "attacker.example.test"
captured.has("X-Internal-Debug") == false

selectedInstance.serviceId == "inventory-service"
providerReceivedRequest == true
```

If the system intentionally enables proxy header generation or OAuth2 token relay, phrase certain assertions as **"does not receive the spoofed value supplied by the inbound client"** rather than "header is always absent". What matters is verifying **the provenance and authorization of the value**, not simply whether a header name appears on the wire.

Never mock out the entire network layer and claim service ID routing/LoadBalancer behavior is proven; such mocks only test one layer's logic, missing interceptors, proxies, transport framing, and the real HTTP server receiving headers.

## 15. Controlling Filters, Proxies, and Libraries That Auto-Add Headers

An allowlist inside a gateway is **not the entire security policy**. Outbound headers can be added across multiple layers:

- Per-client filters/interceptors on RestClient, RestTemplate, WebClient, or OpenFeign.
- HTTP authentication components (OAuth2 authorized clients, service token providers).
- Tracing instrumentation (OpenTelemetry/Micrometer Tracing).
- API Gateway/ingress, service mesh, reverse proxies, or egress proxies.
- The HTTP transport setting `Host`, `Content-Length`, and connection-management headers.

Therefore, define request construction order and "**who owns each header**":

```mermaid
flowchart LR
    A[Incoming request] --> B[Ingress verify/normalize]
    B --> C[Per-operation allowlist]
    C --> D[Authorized token/context injector]
    D --> E[Tracing instrumentation]
    E --> F[HTTP transport]
    F --> G[LoadBalancer-selected destination]
    G --> H[Network proxy / destination]
```

This diagram shows a **conceptual model**; actual ordering between filters and LoadBalancer in HTTP clients can vary by integration. Inspect your actual stack rather than relying on the diagram to assert absolute execution order.

**Critical rule:** if a shared `WebClient` has an interceptor injecting a Bearer token for `billing-service`, never reuse that same instance to call `inventory-service` when the two services require different audiences/scopes. Select token providers by target, not by "whatever token happened to be on the inbound request".

### 15.1. Additional Defensive Checks

| Control Point | Checks to Enforce |
|---|---|
| API Gateway | Strip/overwrite externally claimed identity/proxy headers |
| Ingress → service | Authenticate connections, separate trusted vs. untrusted networks |
| Service code | Build headers strictly via **per-operation** allowlists |
| Auth injector | Right audience/scope tokens; never relay session/browser cookies |
| Tracing | Propagate only permitted context; restrict baggage and exclude PII |
| HTTP transport | Avoid manual framing/`Host` overrides; enforce timeouts and valid TLS |
| Egress proxy | Enforce routing, header rewrites, and prevent secrets from leaving to external targets |
| Downstream | Re-authenticate callers, verify authz/tenant/resource rather than trusting headers named "internal" |

Spring Cloud LoadBalancer selects a `ServiceInstance` from discovery; that **does not guarantee the destination is trustworthy or runs valid TLS**. When using HTTPS/mTLS, clients must verify certificates and policies for the destination. Discovery metadata and zone/instance configs never substitute for authentication and authorization.

## 16. Observing Header Violations Without Logging Sensitive Data

An allowlist policy should be measured and alerted on, yet **never log full blocked header values**, as those could be sensitive tokens or cookies.

Suggested metrics/logs:

| Signal | Purpose |
|---|---|
| `serviceId` / `operation` | Identify which policy applied |
| `headerPolicyVersion` | Correlate changes across deployments |
| `allowedHeaderNames` (bounded) | Inspect permitted header names |
| `droppedHeaderCount` | Detect requests carrying lots of stripped metadata |
| `invalidHeaderCategory` | E.g., invalid language format, bad correlation ID, externally supplied identity headers |
| `selectedInstance` | Confirm calls still route through LoadBalancer properly |
| `authAudience` / scope category | Confirm outbound tokens target the right service (without logging the token) |
| `traceId`, `spanId` | Link calls and incidents across hops |
| `httpStatus` / `exceptionClass` | Tell policy rejections apart from provider/transport failures |

These are **suggested instrumentation names**, not built-in Spring Cloud metrics. When emitting metrics, never use full header values, correlation IDs, user IDs, request URIs with IDs, or tokens as high-cardinality labels. Store detailed traces in systems with proper retention and access controls.

### When Unexpected Headers Are Detected at the Provider

1. Identify the **header name and origin**: inbound user, gateway, app filter, auth component, tracing, or proxy. **Never record secret values** in incident reports.
2. Check whether the request went through the **right `@LoadBalanced` bean** or used a different client bypassing the projector.
3. Check for any **global interceptor** copying `HttpServletRequest`, `ServerHttpRequest`, or `RequestContextHolder`.
4. Confirm policies per **service ID and operation**: another Feign client may have accidentally registered a global interceptor.
5. Compare raw requests arriving at the provider with requests leaving the HTTP client if proxies sit in between.
6. If it is `Authorization`, verify **token provenance and audience**, not just presence/absence.
7. If it is a proxy header, verify whether the trusted proxy stripped/overwrote external values before forwarding.
8. Write a regression test for the newly spotted header to prevent recurrence.

### Distinguishing Policy Errors from LoadBalancer Errors

A request lacking valid auth can receive 401/403 from downstream even when LoadBalancer picked the exact right instance. Conversely, a wrong service ID can prevent LoadBalancer from picking any instance even when the allowlist is spotless. **Never "fix" 401 or 503 errors by forwarding all headers**: identify which layer raised the error and the target's authentication contract.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `outgoing.addAll(incoming)` | Leaks every new/unreviewed header | Construct fresh `HttpHeaders` from allowlist |
| Denylist missing `Cookie`/`Authorization` | Exposes sessions or access tokens | Per-operation allowlist |
| Copying `Host` from public request | Wrong logical target, routing/authority bugs | Let HTTP client set `Host` from target URI |
| Trusting Internet-sent `X-Forwarded-Host`, `X-Real-IP` | Header spoofing, broken security decisions | Trusted gateway strips/overwrites/normalizes |
| Trusting `X-Tenant-Id` to select data | Cross-tenant access | Derive tenant from authenticated principal/security context |
| Forwarding raw Bearer tokens to every service | Audience/scope mismatch, credential exposure | Appropriate service token or delegation |
| Copying `Content-Length` from inbound request | Broken framing, HTTP parsing inconsistencies | Let HTTP transport compute it |
| Blocking only `Connection` while copying headers it lists | Leaks metadata meant for the prior hop | Avoid copy-all; adhere to HTTP semantics |
| Forwarding `baggage` with PII | Spreads sensitive data into traces | Restrict baggage to approved schema |
| Retrying POST with a new idempotency key per attempt | Creates duplicate side effects | Use one stable key per logical operation |
| Copying internal service `Set-Cookie` responses | Leaks cookies, creates cross-domain sessions | Separate response allowlist |
| Copying `Cache-Control: public` on tenant data | Cross-scope caching | Enforce cache policies at API boundary |
| Testing only the projector, not the wire | Misses interceptors/proxies adding headers | Integration test against a real HTTP server |
| Enabling global filter copying `RequestContextHolder` | Context mix-ups or leaks to other services | Per-client policies and explicit trusted context |

## 18. Pre-Deployment Checklist

- [ ] Define trust boundaries from external client → gateway → service A → service B.
- [ ] Enforce **per-service/per-operation allowlists**, never copying all inbound headers.
- [ ] Every allowed header name has a business rationale, format, length, cardinality, and provenance policy.
- [ ] Never relay `Authorization`/`Cookie` from public clients without explicitly designed delegation.
- [ ] Derive identity/tenant/roles strictly from **authenticated** context; downstream still enforces authz.
- [ ] Let HTTP transport manage `Host`, framing, and connection headers; never copy from inbound.
- [ ] Trust `Forwarded`/`X-Forwarded-*` values only behind properly configured proxies.
- [ ] Let instrumentation manage tracing propagation; keep sensitive data out of baggage.
- [ ] Send `Idempotency-Key` only on appropriate operations, stable across retries, bound to tenant/operation on server.
- [ ] Maintain **two separate allowlist policies** for request headers vs. response headers.
- [ ] Verify global interceptors/filters and token providers do not override policy.
- [ ] Have unit tests for header projection and integration tests over real HTTP requests to providers.
- [ ] Test varied header casing, duplicate values, oversized strings, and malformed values.
- [ ] Across multi-instance LoadBalancer setups, verify every replica receives the exact approved contract headers.
- [ ] Keep tokens, cookies, PII, and raw baggage out of metrics/logs while retaining traces to separate auth, selection, and transport failures.

## 19. Summary

**Forwarding only allowed headers** means **actively constructing a fresh outbound request** from the target service's contract rather than carrying the inbound request intact across microservices. `Accept-Language` can be forwarded after normalization, `X-Correlation-Id` can be minted at the trust boundary, and `Idempotency-Key` may be needed for write operations; meanwhile tokens, cookies, self-claimed tenants, proxy headers, and connection-control headers require dedicated policies or must never be relayed.

In Spring Cloud LoadBalancer, **`ServiceInstance` selection and header security are two independent responsibilities**. Whether LoadBalancer picks instance A or B, outbound policies must yield consistent results. Combining per-operation allowlists, right-audience tokens, safe tracing, wire-level provider tests, and header-source observability minimizes data leakage and prevents untrusted inputs from distorting access control or internal routing.

### References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): HTTP field definitions, `Connection`, and intermediary header handling.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): framing, `Host`, and HTTP/1.1 processing requirements.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `RestTemplate`, and `WebClient`.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service IDs, `ServiceInstance`, and HTTP client integration.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@FeignClient`, request interceptors, and client configuration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context and baggage.
