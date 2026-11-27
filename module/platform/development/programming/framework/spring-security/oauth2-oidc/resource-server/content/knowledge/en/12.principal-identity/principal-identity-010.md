# Keeping Sensitive Token Data Out of API Responses and Logs

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, an access token is the proof a client presents to the API to be authenticated. A JWT can carry claims about the subject, client, tenant, and access permissions; an opaque token can be checked against the Authorization Server to retrieve similar information. After authentication, Spring Security places the principal and authorities into an `Authentication` object so the application can enforce authorization.

**An authenticated principal does not mean all token data is cleared for disclosure.** A common mistake is returning `Jwt`, `Authentication`, `OAuth2AuthenticatedPrincipal`, or objects containing the `Authorization` header directly in JSON API responses. Another mistake is using loggers, HTTP tracing, or exception handlers to print raw access tokens, sensitive claims, or credentials sent to introspection endpoints. Those details can persist for long periods in logs, observability backends, error trackers, or customer support tickets, widening the blast radius if anyone gains read access.

This lesson focuses on **keeping sensitive token data out of API responses and logs** within the **Principal and Identity** context: classifying data, selecting minimal principal attributes, designing DTOs, using Spring Security safely, controlling logs and tracing across the request lifecycle, and verifying that the system does not accidentally create a credential leakage path.

> All tokens, hostnames, user identifiers, and tenants shown in examples are fabricated values. Never use real access tokens in documentation, HTTP examples, screenshots, shared test fixtures, or commands recorded in CI.

## 1. Distinguishing Credentials, Claims, Principals, and Returnable Data

Suppose a client calls Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

If the access token is a JWT, it might carry illustrative information such as:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "tenant_id": "tenant-a",
  "jti": "token-id-example",
  "iat": 1924988400,
  "exp": 1924992000,
  "email": "person@example.test",
  "groups": ["sales", "internal"]
}
~~~

This is only an **unsigned payload** for illustration. A trustworthy Resource Server must verify the signature/key source, issuer, timestamps, audience, and token profile requirements before using any claims.

After authentication:

~~~text
HTTP Authorization header:
    Bearer <ACCESS_TOKEN>          ← secret credential
             |
             v
JwtDecoder / OpaqueTokenIntrospector
             |
             v
Authentication:
    principal    = Jwt / OAuth2AuthenticatedPrincipal
    name         = subject or mapped value
    authorities  = SCOPE_orders.read, SCOPE_profile
    credentials  = data held by implementation
             |
             v
Controller/service:
    uses verified identity
    enforces authorization
    builds response DTO with only required business fields
             |
             v
HTTP response:
    NO raw token, Authorization header, or arbitrary claims
~~~

### 1.1. Data Classification Table

| Data | Sensitivity / Risk | Recommended Policy |
|---|---|---|
| **Raw access token** | Bearer credential; anyone holding it can call APIs within the token's scope | **Never return in JSON; never log/trace/metric; never attach to errors** |
| **Refresh token** | Can be used to mint new access tokens; highly sensitive | Must not appear in Resource Server responses/logs |
| **ID token** | May carry identity claims and PII; meant for OIDC clients | Never echo through Resource Server APIs; never substitute for access tokens |
| **`Authorization: Bearer ...`** | Carries raw access token | Redact the entire header at every layer |
| **`Authorization: Basic ...`** for introspection | Carries Base64-encoded client ID/secret, not encrypted by Base64 | Redact the entire header; protect secrets with a secret manager |
| **Client secret / private key** | Application credential or signing key | Never return in responses, log, or commit |
| **Cookie / session identifier** | May act as a session access credential | Never log values; protect via cookie policies |
| **`sub` / username / email** | Identity or personal data; may enable activity correlation | Return only to authorized callers for defined purposes; limit logging |
| **`tenant_id`, groups, roles** | Internal data and organizational scope | Return strictly as needed; never expose the entire token profile |
| **`scope`, `aud`, `iss`, `client_id`** | Usually not secrets themselves, yet reveal structure/permissions and can correlate users | Never dump into public responses or high-cardinality logs |
| **`jti`** | Token identifier that can link requests to one credential | Never log raw in public logs; govern separately if used for audit/revocation |
| **`kid`** | Key identifier; usually public in JOSE/JWKS, yet can be arbitrary input | Use only as limited observability metadata; never trust as auth proof |
| **System-generated Request ID / Trace ID** | Used for operational correlation, not a credential | Safe to return/log when designed to avoid PII and injection |

The **data minimization** principle applies beyond “strict secrets”. A claim like `email` or `sub` may not directly let an attacker call an API, yet it still reveals user identity or activity. Return or log it only with a clear business need, access control, and retention policy.

### 1.2. Why Are Bearer Tokens Especially Sensitive?

Under the Bearer token model, whoever possesses the token can present it to the Resource Server and act under its permissions **without necessarily proving they are the original recipient** via a separate key. As long as the token remains unexpired with matching audience and scopes, leaking it enables privilege abuse throughout its lifetime window.

Some systems deploy sender-constrained tokens (such as DPoP or mTLS-bound tokens) that reduce replayability without matching proof, yet **that still does not justify logging tokens**. Tokens remain security artifacts that can contain PII and must be governed carefully per profile.

**Base64URL encoding of a JWT is not secret encryption.** Anyone holding the token can decode its header and payload to read claims; security comes from signatures and controlling who sees the token, not from the payload looking unreadable at a glance.

## 2. Common Sources of Token Leakage

An API request traverses multiple components before returning a response:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway / Proxy"]
    G --> F["Servlet Filter / Spring Security"]
    F --> S["Controller / Service"]
    S --> R["Response DTO"]
    G -. "access logs" .-> L["Log pipeline / SIEM"]
    F -. "debug / exceptions" .-> L
    S -. "application logs" .-> L
    G -. "tracing" .-> T["APM / Traces"]
    F -. "tracing" .-> T
    S -. "metrics / audit" .-> T
~~~

Leaks can occur across **multiple independent layers**:

| Source | Unsafe Example | Consequence |
|---|---|---|
| Controller response | `return jwt;` or `return authentication;` | Serializer may emit token/attributes into JSON |
| Controller debug endpoint | Returning entire `SecurityContextHolder.getContext()` | Exposes principal, authorities, credentials |
| Exception handler | `return Map.of("error", ex.getMessage())` when message holds token/header | Leaks internal data into HTTP responses |
| Application logger | `log.info("auth={}", authentication)` | Implementation/`toString()` may expose sensitive fields |
| Logging request headers | `log.debug("headers={}", request.getHeaderNames()...)` | Logs `Authorization`, Cookie, API keys |
| Logging query strings / bodies | Token mistakenly passed in query/body | Access logs, tracing, or analytics capture tokens |
| HTTP client to IdP | Logging outbound introspection/token-exchange requests | Leaks introspected tokens and client secrets |
| Gateway / ingress | Access logs capturing headers or full URLs | Copies credentials into centralized log storage |
| Distributed tracing | Attaching tokens, `sub`, or email as span attributes/baggage | Spreads data across services and APM vendors |
| Error reporting | SDK auto-capturing HTTP requests, exceptions, local variables | Tokens land in crash reports |
| Support / debug workflows | Pasting real request cURLs into tickets | Credentials persist in long-lived ticket stores |
| Test / CI pipelines | Printing `Authorization` on test failures | Tokens remain in build logs |

**Redaction inside the Java app alone is insufficient to protect the whole system** if a gateway or APM already captured the token before the request reached the controller. Enforce consistent policies across network, application, observability, and support layers.

## 3. Distinguishing `Jwt`, `Authentication`, and Response DTOs

In a JWT Resource Server, the common principal is a `Jwt` wrapped in a `JwtAuthenticationToken`. The `Jwt` object holds both the token value and verified claims. A controller can inject it:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/me")
    Object me(@AuthenticationPrincipal Jwt jwt) {
        return jwt; // ANTI-PATTERN: never return the whole Jwt.
    }
}
~~~

This is an **anti-pattern** and must not be deployed. Because different versions and serializers serialize different properties, never assume Jackson will strip the token value or sensitive claims on its own. **Never return raw security framework objects.**

Similarly:

~~~java
// ANTI-PATTERN:
@GetMapping("/api/debug/authentication")
public Authentication debug(Authentication authentication) {
    return authentication;
}
~~~

An `Authentication` can contain principal, credentials, authorities, and details. Returning it directly couples the API to internal implementations and widens the data surface beyond the API contract.

### 3.1. Use Explicit DTOs Selecting Only Permitted Fields

A sensible `/api/me` endpoint might only return an approved display identifier and an account label:

~~~java
public record MeResponse(
    String displayName,
    String accountType
) {}
~~~

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MeController {

    @GetMapping("/api/me")
    MeResponse me(@AuthenticationPrincipal Jwt jwt) {
        // Use only verified claims after applying policies.
        String displayName = jwt.getClaimAsString("preferred_username");
        if (displayName == null || displayName.isBlank()) {
            displayName = "Authenticated user";
        }
        return new MeResponse(displayName, "user");
    }
}
~~~

This example assumes the token contract permits using `preferred_username` as a display name, the caller is allowed to receive it, and the endpoint is protected. **Never use `preferred_username` to decide resource ownership**, as display names can change and are not unique. `sub` and issuer/tenant are generally appropriate for identity logic per system policy.

Never expose `jwt.getTokenValue()`, `jwt.getClaims()`, or `jwt.getHeaders()` “for easy debugging”. Whenever a client genuinely needs an attribute, add an **explicit field to a DTO** with an access check rather than returning the whole claim map.

### 3.2. Use Internal Identity and Avoid Returning Raw `sub` to Clients Unnecessarily

Not every application needs to return `sub`. An orders API can read `sub` internally to query the right owner while the response returns only order fields:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer().toString();

        // Record-level authorization belongs in the service/domain.
        return orders.findVisibleOrder(id, issuer, subject);
    }
}
~~~

`OrderService`, `OrderResponse`, and `findVisibleOrder` are application-defined domain components. This illustrates **using claims for internal authorization checks** without echoing claims into JSON. In multi-tenant systems, the identity key may also require a tenant ID per contract.

### 3.3. For Opaque Tokens

If the Resource Server uses introspection, the common principal is `OAuth2AuthenticatedPrincipal`. Avoid doing:

~~~java
// ANTI-PATTERN:
@GetMapping("/api/debug/principal")
Object principal(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal p) {
    return p; // Can expose all introspection attributes.
}
~~~

Replace it with a DTO containing only appropriate fields:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaqueMeController {

    @GetMapping("/api/account-kind")
    AccountKindResponse accountKind(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        // Never return principal.getAttributes() directly.
        return new AccountKindResponse("authenticated");
    }
}

record AccountKindResponse(String kind) {}
~~~

An introspection response can carry `sub`, `scope`, `client_id`, email, or issuer-specific claims. Just because the Authorization Server **is permitted to send** data to the Resource Server does not mean the API is permitted to **forward that raw data** to clients.

## 4. Decoupling Internal Identity from the External JSON Contract

A Resource Server can accept tokens from different clients, where each token profile represents a different subject. Common identity patterns:

| Case | What Principal May Represent | What Never to Assume |
|---|---|---|
| Authorization Code + user consent | End user and client context | That all user claims may be publicly disclosed |
| Client Credentials | Service / application | That a human username or email exists |
| Token Exchange | Delegated principal/client per contract | That `sub` always carries the same meaning as the original token |
| Opaque access token | Principal from introspection | That introspection attributes may be returned publicly |
| Multi-tenant resource | Subject per issuer/tenant | That `sub` is unique across all issuers/tenants |

For API responses, define a **business vocabulary**: display name, order status, product-approved UI flags, or an internal account code that reveals no token details. Never equate DTOs with the claim structure emitted by the Authorization Server.

### 4.1. Never Use Claims as a Dynamic DTO

A common anti-pattern:

~~~java
// ANTI-PATTERN: arbitrarily exposes claims added later by the issuer.
return Map.copyOf(jwt.getClaims());
~~~

Today the JWT holds only `sub` and `scope`; tomorrow the Identity team adds `email`, `phone_number`, or fraud-scoring claims. A “debug” endpoint would automatically leak every newly added field without review.

A DTO with a fixed field list acts as a **contract-level allowlist**. Adding a field requires deciding its source, caller permissions, purpose, personal identifiability, and test coverage.

### 4.2. Be Careful with `Authentication.getName()`

`getName()` is not automatically safe to return publicly. For JWTs, the name may come from `sub` or an app-configured claim like `preferred_username`; for opaque tokens, it depends on the introspector/principal. Never assume `getName()` is always a harmless display code.

An “authenticated” string can still be an email, an employee ID, or an identifier linkable across services. Display decisions belong in the API contract.

## 5. Controlled Logging in a Servlet Resource Server

Spring Security uses several components to authenticate requests: `BearerTokenAuthenticationFilter`, `AuthenticationManager`, `JwtDecoder` or `OpaqueTokenIntrospector`, and then populates `SecurityContextHolder`. Applications sometimes need logs to investigate failures or measure performance, yet **business logs never need raw Bearer tokens**.

### 5.1. Avoid Logging Full Requests, Principals, or Security Contexts

Examples **never to deploy**:

~~~java
// ANTI-PATTERNS:
log.info("Authorization={}", request.getHeader("Authorization"));
log.debug("All headers={}", Collections.list(request.getHeaderNames()));
log.info("Authentication={}", authentication);
log.debug("Principal={}", authentication.getPrincipal());
log.info("JWT={}", jwt.getTokenValue());
log.debug("JWT claims={}", jwt.getClaims());
log.info("Credentials={}", authentication.getCredentials());
log.error("Request failed: {}", request, exception);
~~~

Reasons:

- `Authorization` can contain Bearer access tokens or Basic credentials.
- Other headers can hold API keys, Cookies, or system credentials.
- `Authentication`, principal, and `Jwt` hold security fields; how `toString()` or serializers format them is not an application-level leak-prevention contract.
- `getClaims()` can hold PII, tenant, groups, email, and internal permissions.
- `request.toString()`, exception chains, or HTTP framework loggers can inadvertently capture URLs, queries, headers, or bodies depending on versions and settings.
- Enabling DEBUG/TRACE logging in production can expose data never logged at INFO level.

**Never rely on “the current logger seems to mask tokens” as your sole defense.** A framework upgrade, encoder change, or new dependency can change how objects stringify.

### 5.2. Design Log Events Around an Allowlist

Instead of logging credentials, log an event with **pre-selected fields**:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderAuditEvents {
    private static final Logger log =
        LoggerFactory.getLogger(OrderAuditEvents.class);

    public void orderReadCompleted(String requestId, String outcome) {
        // requestId must be system-generated or safely validated.
        // outcome is a bounded enum/value set, never raw client input.
        log.info(
            "event=order_read result={} request_id={}",
            outcome,
            requestId
        );
    }
}
~~~

Example log output:

~~~text
INFO event=order_read result=allowed request_id=8f5279f1-0fd2-4c1d-a316-24048e5ef3d6
WARN event=order_read result=denied request_id=6220ec22-ea34-4fbd-8026-7a10c2a80f51
~~~

These logs support counting and tracing without broadcasting tokens or subjects. In regulated audit systems that must record who performed an action, use a **separately protected audit store** with an appropriate internal actor ID, event code, restricted read access, and clear retention. Never dump full claims/credentials into standard application logs for audit convenience.

### 5.3. Request IDs Are Not Tokens

To correlate requests with logs, use a **system-generated random request ID**. Example `OncePerRequestFilter` on Servlet:

~~~java
import java.io.IOException;
import java.util.UUID;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        request.setAttribute("requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        MDC.put("requestId", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Register this filter **once** per your actual Servlet/Spring Security setup, avoiding accidentally both auto-registering it as a Servlet filter and adding it to the security chain in a way that executes twice. For cross-service tracing, prefer your organization's configured observability integration so correlation IDs follow standards.

This example intentionally **generates a fresh request ID** rather than accepting arbitrary strings from a client-sent `X-Request-ID` header, preventing log injection or oversized values. If accepting an ID from a trusted gateway, enforce the trust boundary and validate syntax and length.

**MDC relies on thread context.** With async Servlets, `@Async`, or custom executors, never assume MDC/request context propagates automatically across threads; use appropriate context-propagation tooling when needed and clean up per lifecycle. Never copy an access token into MDC to “make logs easier to search”.

### 5.4. Never Put Token Data into MDC

Anti-pattern:

~~~java
// ANTI-PATTERN:
MDC.put("accessToken", jwt.getTokenValue());
MDC.put("subject", jwt.getSubject());  // Requires dedicated policy if ever used.
MDC.put("email", jwt.getClaimAsString("email"));
~~~

MDC is automatically injected into **every log line** when layouts/encoders configure `%X` or JSON structured logging. Putting sensitive values into MDC once replicates that data across hundreds of unrelated log events. Tokens especially have no place in MDC.

More useful fields:

~~~text
requestId
traceId
spanId
serviceName
normalized routeName / operationName
httpStatus
durationBucket
errorCategory
~~~

Avoid using email, raw `sub`, full URLs, or tokens as metric labels: beyond privacy concerns, they cause **high cardinality**, driving up costs and degrading observability storage performance.

## 6. Protecting Error Responses: Authentication Failures Must Not Leak Tokens

An API error response should tell the client what to do next without echoing back the token the client sent. For example, a request with an invalid or expired JWT:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <INVALID_ACCESS_TOKEN>
~~~

Sensible response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{
  "code": "UNAUTHENTICATED",
  "message": "Access token is missing or invalid."
}
~~~

This is an illustrative response; a Spring Security Resource Server may return only the Bearer challenge with an empty body. **There is no requirement to add a JSON body unless your API error contract specifies one.** If you add a body, use neutral messages without echoing JWTs or internal exceptions.

When a token is valid yet lacks the required scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{
  "code": "FORBIDDEN",
  "message": "You do not have permission to perform this action."
}
~~~

The `WWW-Authenticate` header for Bearer tokens follows **RFC 6750** rules. Do not omit the header or stuff arbitrary text into custom handlers. Avoid putting full tokens, the `Authorization` header, or signature verification internals inside `error_description`.

### 6.1. Spring Security Handles 401/403 Before the Controller

In Servlets, Bearer token authentication failures are typically handled by security filters and components like `BearerTokenAuthenticationEntryPoint`, while insufficient permissions are handled via `AccessDeniedHandler`. Therefore, **`@RestControllerAdvice` does not automatically catch authentication errors raised before `DispatcherServlet`**.

A standard Servlet setup:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Spring Security provides appropriate Bearer entry-point and access-denied handling for this Resource Server configuration. If custom JSON errors are needed, register a custom `AuthenticationEntryPoint` and `AccessDeniedHandler` on the security chain, **preserving 401/403 semantics and Bearer challenges**. Error payloads must come from safe public values—never serialize raw `AuthenticationException` or `AccessDeniedException` instances.

### 6.2. Business Error DTOs Must Not Pull Security Details from Exceptions

Example shared DTO:

~~~java
public record ApiError(
    String code,
    String message,
    String requestId
) {}
~~~

For business exceptions inside MVC:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> notFound(OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "ORDER_NOT_FOUND",
                "The requested order was not found.",
                null
            ));
    }
}
~~~

`OrderNotFoundException` is a hypothetical domain exception. This pattern **does not copy `ex.getMessage()` into the response** because exception messages may include sensitive inputs, data sources, or internal details. In real error bodies, retrieve `requestId` from a trusted request context and return it only when permitted by policy.

### 6.3. Do Not Let Debug Error Properties Leak Unwanted Details

Framework error-response, stack-trace, and error-message properties can expose verbose internals if enabled in the wrong environment. In Spring Boot, control options such as **include-message**, **include-stacktrace**, **include-binding-errors**, and default error pages per deployment profile.

Example production configuration:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

These properties restrict Spring Boot's default MVC error payload, yet **do not replace controls in Spring Security filters, gateways, loggers, custom exception handlers, or APMs**. Never assume a YAML property automatically redacts all raw tokens across the stack.

### 6.4. Exception `toString()` Is Not Response Data

Anti-pattern:

~~~java
// ANTI-PATTERN:
return ResponseEntity.status(401).body(
    Map.of("error", exception.toString()));
~~~

Exceptions can contain endpoint URLs, JOSE parsing info, claim values, or request data. Return only public error codes (such as `UNAUTHENTICATED`) and carefully written short messages. Internal logs should likewise avoid printing unknown exception messages; when stack traces are needed, enforce redaction, access controls, and retention limits.

## 7. Security Pitfalls in Automatic HTTP Request/Response Logging

In Spring Boot applications, leaks do not only come from developer-written `log.info()` calls. Tools that **log HTTP wire traffic**, **request/response bodies**, **headers**, **proxies**, or **HTTP clients** can capture sensitive data automatically when configured too verbosely.

### 7.1. Log Layers to Audit

| Layer | Risk | Mitigation |
|---|---|---|
| Servlet container access logs | URL/query and request metadata; may be customized to log headers | Never log `Authorization`, cookies, or sensitive queries |
| Servlet logging filters | Printing all request headers and bodies | Avoid blanket logging; use field allowlists and redaction |
| Spring Security DEBUG/TRACE | Can log authentication/context or exception details | Enable only briefly when needed; scrub sensitive data |
| HTTP clients `RestClient` / `WebClient` | Outbound Bearer tokens, Basic auth, introspection `token` form fields | Never enable full wire/body logging in production |
| Netty / Reactor / Apache HTTP wire logs | Can capture request/response headers and bodies | Disable or configure redaction before capture |
| API gateway / ingress | Full request URLs or headers written to access logs | Log only approved metadata |
| Service mesh / sidecars | HTTP or mTLS telemetry | Never capture credential payloads; review processors/filters |
| APM / error monitoring | Auto-captures headers, queries, local variables | Configure filters/denylists at instrumentation time |

In systems using **OAuth 2.0 opaque token introspection**, outbound requests typically carry form field `token=<ACCESS_TOKEN>` alongside the Resource Server's Basic credentials. Consequently, if an HTTP client logs **the full request body** on introspection calls, both the access token and the introspection admin credential appear together in logs.

### 7.2. Filter at the Source Rather Than Scrubbing After Storage

You can design defense-in-depth layers:

~~~text
Application never emits raw secrets to logs
        ↓
Logging middleware collects only allowlisted fields
        ↓
Collector/agent applies secondary filters and redaction
        ↓
Encrypted log storage + RBAC + retention
        ↓
Access controls and auditing on log queries
~~~

If a header must be **redacted**, **strip the entire value**:

~~~text
Authorization: [REDACTED]
Cookie: [REDACTED]
X-API-Key: [REDACTED]
Proxy-Authorization: [REDACTED]
~~~

Never log “first 6 and last 6 characters” to recognize an access token: partial tokens are still credential-derived data, and combining fragments across sources increases risk. For short tokens, partial leaks expose a large fraction of the secret. When you genuinely need to identify a security event, use an intentionally generated request ID or audit ID.

### 7.3. Query Strings May Already Contain Credentials Due to Client Mistakes

RFC 6750 recommends clients send Bearer tokens in headers; passing tokens in query strings is especially dangerous because queries end up in browser history, reverse proxy logs, Referer headers, metrics, and intermediaries.

Example to avoid:

~~~http
GET /api/orders/42?access_token=<ACCESS_TOKEN> HTTP/1.1
~~~

Even if the Resource Server **rejects** query tokens, proxies or access logs can still record the query from a misbehaving client. Blocking query tokens in the application does not replace sanitizing access logs at gateways, ingress, and telemetry pipelines.

## 8. WebFlux: Sensitive Data Can Also Enter Reactive Logs

If an API uses **Spring WebFlux**, the same principles apply:

- Tokens still arrive via `Authorization: Bearer ...`.
- JWTs are processed via `ReactiveJwtDecoder`, opaque tokens via `ReactiveOpaqueTokenIntrospector`.
- Principals are used solely for identity and authorization checks.
- Responses must be minimal DTOs, never raw `Jwt` or `Authentication` objects.
- Never place tokens into Reactor `Context`, diagnostic logs, MDC, `baggage`, or span attributes in ways that export them to telemetry.

A WebFlux controller:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReactiveMeController {

    @GetMapping("/api/me")
    Mono<PublicProfile> me(@AuthenticationPrincipal Jwt jwt) {
        String displayName = jwt.getClaimAsString("preferred_username");
        if (displayName == null || displayName.isBlank()) {
            displayName = "Authenticated user";
        }
        return Mono.just(new PublicProfile(displayName));
    }
}

record PublicProfile(String displayName) {}
~~~

This assumes the Resource Server accepts JWTs and `/api/me` requires authentication. For opaque tokens, the principal is `OAuth2AuthenticatedPrincipal` and requires a different mapping. Returning a `Mono<Jwt>` or `Mono<Authentication>` over HTTP leaks data just like in Servlet; reactive types **do not automatically hide tokens**.

### 8.1. Avoid Reactor Netty Wiretap Capturing Credentials

When debugging connectivity, teams sometimes enable HTTP wiretap or TRACE logging on Reactor Netty, WebClient, API gateways, or HTTP libraries. Depending on configuration, wire logs print **headers**, **bodies**, or both. When requests carry Bearer tokens, that creates a severe leak.

In production environments:

1. Prefer connection metrics, latency, and status codes over full wire dumps.
2. If temporary logging is unavoidable, enforce **redaction at the source** and restrict log access.
3. Avoid logging OAuth token/introspection calls or downstream API calls carrying credentials.
4. Disable debug logging once investigation ends; verify retention and purge generated logs.

In WebFlux, thread-based MDC does not automatically propagate cleanly across asynchronous/reactive operators. When correlation IDs are needed, use proper context-propagation/tracing tools; **never use tokens as correlation keys**.

### 8.2. Never Let `doOnNext` Log the Whole Principal

Anti-pattern:

~~~java
// ANTI-PATTERN: can expose claims or credentials.
return ReactiveSecurityContextHolder.getContext()
    .doOnNext(context ->
        log.debug("securityContext={}", context));
~~~

An example logging only a pre-selected event:

~~~java
return orderService.findVisibleOrders()
    .doOnSuccess(ignored ->
        log.info("event=orders_lookup outcome=success"));
~~~

`orderService` and `log` are hypothetical application components. If you need to log a request ID, read it from managed tracing/context rather than threading raw access tokens through the stream.

## 9. Tracing, Metrics, and Centralized Logging

Microservice architectures often combine Spring Boot Actuator, Micrometer Observation/Tracing, OpenTelemetry, API gateways, and log aggregators. These tools create **copies of request data** outside the main application.

### 9.1. Which Span Attributes Should and Should Not Be Collected?

| Data Category | Examples to Consider | Examples to Avoid |
|---|---|---|
| HTTP | Method, route template, status, latency | Full request URI containing query credentials |
| Service | Service name, environment, operation name | Unnecessary secret infrastructure details |
| Request correlation | Trace ID, span ID, request ID | Raw Bearer tokens or unapproved token hashes |
| Authentication outcome | `authenticated` / `invalid_token` / `insufficient_scope` (bounded categories) | Entire `Authentication` / `Jwt` / `getClaims()` |
| Identity | Approved internal actor ID in restricted audit sinks | Email, phone, or raw subject in public traces |
| Authorization | Rule/category such as `orders.read` when policy allows | Full group/role claims or sensitive records |

**High-cardinality** values such as emails, raw subjects, `jti`, and token values must never be used as metric labels. Beyond privacy concerns, a unique string per request explodes time-series cardinality and storage cost.

### 9.2. Tracing Baggage Propagates Across Services

Unlike a local JVM variable, distributed tracing **baggage** can be injected into outbound HTTP headers when calling downstream services, and some tools copy baggage into span events/logs. Therefore:

~~~text
Acceptable:
  system-generated trace ID
  normalized operation name

Never put in baggage:
  access tokens
  refresh tokens
  client secrets
  email, phone
  raw JWT claims
~~~

If business logic needs to propagate identity downstream, use a **proper service-to-service authentication model**: access tokens scoped to the downstream audience, token exchange, or an authenticated internal identity mechanism. Never pass an arbitrary `X-User` header and trust it across services without boundaries.

### 9.3. Avoid Echoing Tokens via Error Trackers

Some error-monitoring SDKs automatically collect request headers, query parameters, bodies, or breadcrumbs. Configure them to:

- Strip `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, and API-key headers.
- Strip parameters named `access_token`, `id_token`, `refresh_token`, `client_secret`, and equivalent credential names.
- Avoid auto-capturing all local variables in controllers, decoders, and exception handlers.
- Redact before data leaves for the APM backend, not merely via UI display filters after storage.
- Enforce retention/access limits and have an incident workflow if a leak occurs.

A misbehaving client might send a token under an unexpected parameter name; therefore, an **observability allowlist model** is safer than relying solely on a field denylist.

## 10. Risks at Gateways, Proxies, and CDNs

A Resource Server typically sits behind a load balancer, API gateway, reverse proxy, or service mesh. Those layers see the Bearer header **before** Spring Security validates the token.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway/Ingress
    participant R as Spring Security Resource Server
    participant L as Log/Telemetry Storage
    C->>G: Authorization: Bearer <token>
    Note over G: Auth header must not be written to access logs
    G->>R: Forward request per policy
    R->>R: Verify token, build principal
    R-->>G: Minimal response DTO
    G-->>C: HTTP response without tokens
    G-->>L: Method, route, status, request ID
    R-->>L: Event category, trace ID, status
~~~

Specifically check:

- Whether **access logs** record `$http_authorization`, `%{Authorization}i`, or equivalent variables.
- Whether **request mirroring** copies headers/requests to non-production environments.
- Whether **API analytics** store full URLs/query strings, request bodies, or cookies.
- Whether gateway-generated **error pages** echo request headers, queries, bodies, or diagnostic dumps.
- Whether **WAF/security events** store tokens in sample payloads; if incident evidence must be retained, enforce strict access, retention, and token revocation.
- Whether **HTTP response caching** could cache personalized responses for one principal and serve them to another caller.

### 10.1. Never Cache User Responses Across Identities

Endpoints like `GET /api/me` or `GET /api/orders` return personalized data. Beyond not echoing tokens, ensure shared caches or CDNs never serve User A's response to User B. For private data, define explicit cache policies; you can use:

~~~http
Cache-Control: private, no-store
~~~

This illustrates a policy restricting response caching. **Do not blindly apply `no-store` to public static assets**, yet identity/token-related responses require cache headers suited to sensitivity and gateway behavior. Also never put access tokens into public cache keys or cache metric labels.

### 10.2. Redaction Must Not Rely on One Token Format

A JWT looks like three dot-separated segments, whereas an opaque token can be any string. Never redact only strings that look like JWTs:

~~~text
JWT:    xxxxx.yyyyy.zzzzz
Opaque: opa_7e0d... (illustrative)
~~~

Base redaction rules on **location and data semantics**, such as the `Authorization` header or the `token` form field of introspection calls. Credentials can also appear inside custom JSON payload fields; detect them at application boundaries per contract or avoid body logging altogether.

## 11. Outbound Tokens and Introspection Credentials

A Resource Server may call the Authorization Server or downstream APIs. Here credentials are **intentionally transmitted to valid recipients**, yet must still never appear in responses or logs.

### 11.1. Opaque Token Introspection

HTTP format:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <ENCODED_RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Protect **both the introspected token and the introspection client credentials**. Specifically:

- Never log `Authorization: Basic ...`: Base64 is not encryption.
- Never log form bodies containing `token` or `client_secret`.
- Never log full introspection responses when they contain sensitive subjects, emails, or metadata.
- Never copy raw introspection responses into Orders API HTTP responses.
- Use HTTPS, trusted endpoints, and a secret manager.
- On introspection failures (upstream 401/403, 5xx, timeouts), log only the error category and request ID; never put credentials into exception diagnostics.

Example of a custom HTTP logger recording only:

~~~text
event=introspection_call outcome=success latency_bucket=under_100ms
event=introspection_call outcome=authentication_error latency_bucket=under_100ms
event=introspection_call outcome=timeout latency_bucket=over_500ms
~~~

These latency buckets are illustrative groupings, not default SLOs. An `active=false` introspection result likewise needs no raw token in the logs for the application to reject the request.

### 11.2. Calling Downstream APIs

In a valid microservice design, attaching a Bearer token to **outbound requests targeting the right Resource Server** can be necessary. However:

1. Use only tokens valid for the downstream API's **audience**.
2. If an inbound token targets Orders API, never blindly forward that exact token to Billing API. Use token exchange or acquire a fresh token per contract.
3. Never log outbound requests carrying `Authorization`.
4. Never place outbound tokens in bodies, queries, exceptions, caller responses, or tracing baggage.
5. Never reuse the same client secret or service credential across environments.

**“Do not log tokens” does not mean “never transmit tokens over the network”.** Credentials must still be presented to authorized recipients for authentication; this policy prevents **disclosure outside authorized channels**.

### 11.3. Distinguishing Access Tokens from OIDC ID Tokens

An OIDC client receives an ID token to verify login details, not to call arbitrary Resource Servers. If a “debug” service echoes an ID token, it can leak identity claims while encouraging clients to misuse the wrong token type.

For a Resource Server API:

~~~text
Client → API:
  Authorization: Bearer <ACCESS_TOKEN_FOR_API>

API → Client:
  Business response DTO
  NO: raw access token
  NO: ID token / refresh token
  NO: whole Jwt / Authentication
~~~

Authorization Server token endpoints **exist to issue tokens** and naturally return tokens per the OAuth 2.0 protocol. This lesson targets **Resource Servers / business APIs**, without negating an Authorization Server's legitimate token-issuance role.

## 12. Limiting Sensitive Data in Audits and Debugging

Security monitoring may need to know “who invoked which operation” or “why access was denied”. Even so, auditing and debugging must still have clear purpose, access controls, and retention limits.

### 12.1. Three Tiers of Operational Data

| Tier | What to Store | What to Avoid |
|---|---|---|
| **Operational metrics** | 401/403 counts, error categories, latency, normalized service/route | Raw tokens, user/email identifiers as labels |
| **Application logs** | Request ID, event name, status, operation category | Full `Authentication`, headers, claims, secret-bearing bodies |
| **Restricted security audit** | Minimal actor ID, timestamp, purpose, resource ID per policy, outcome | Raw credentials; details unrelated to investigations |

When audits must link actions to actor identities:

- Choose a consistent identity key using **issuer + subject + tenant** when required by contract, never defaulting to username.
- Protect audit sinks with RBAC, encryption at rest and in transit, retention limits, and access auditing.
- Never copy audit metadata into public logs or traces just for correlation convenience.
- For tenants or emails, consider internal identifiers or pseudonymization per privacy rules.
- Never use raw `jti` or access tokens as general actor keys in application metrics.

### 12.2. Never Embed Credentials in Log Messages Hoping Regex Redaction Catches Them

Anti-pattern:

~~~java
// ANTI-PATTERN:
log.warn("Failed token {} for user {}", token, email);
~~~

Post-hoc regex replacement can miss opaque tokens, truncated tokens, unusual header formats, or different encodings. Better:

~~~java
log.warn("event=authentication_rejected reason=invalid_token");
~~~

If a log event needs a request/trace ID, take it from a trusted source; if detailed error codes are needed, use a bounded enum/constant rather than dumping raw exceptions or claims.

### 12.3. Development and Staging Environments Must Be Protected Too

Never enable full HTTP dumps in development and carry that configuration into staging or production. Specifically:

- Developers may accidentally test with real tokens in the wrong environment.
- Staging data is sometimes copied from production, creating extra PII exposure.
- Build logs and crash reports often persist longer than production logs.
- Customer support tools may hold sample requests pasted from browser DevTools.

Prefer synthetic tokens, test issuers, and isolated keys in non-production environments. If a real credential ever leaks into logs or tickets, treat it as an incident requiring revocation/rotation assessment—not just deleting the line from your screen.

## 13. Testing Responses and Logs Without Real Credentials

An API can implement authentication and authorization properly while still leaking tokens through serialization or logging. Therefore, include **data-leakage tests**, separate from JWT signature tests.

### 13.1. Matrix of Scenarios to Cover

| Scenario | Surface to Inspect | Expectation |
|---|---|---|
| GET `/api/me` with mock JWT carrying email and scope | JSON response | Contains only allowed DTO fields; no raw token or unselected email claim |
| GET protected API with invalid JWT | Error response | Valid 401/Bearer challenge; no echoed Authorization |
| GET protected API with valid JWT missing scope | 403 response | No full claims, credentials, or exception stack trace |
| Opaque introspection `active=true` | API response and logs | Neither introspection response nor Basic credentials exposed |
| Introspection returns 401 or times out | Outbound logs and API error | Form `token` and client secret not logged; request fails authentication |
| JWT decoder receives invalid signature | Application logs / APM | Token and JWS payload not logged; error recorded at allowed category level |
| Client misplaces token in query string | Gateway / access logs | Query credential not logged; API rejects unauthorized transport |
| Custom exception from service | Error body and logs | Does not return sensitive data via `exception.getMessage()` |
| HTTP DEBUG enabled in test environment | Framework / HTTP client logs | No sensitive tokens or headers appear |
| Request traverses proxy / CDN | Access logs and response headers | Credential headers not logged/echoed; private responses not shared-cached |
| Cross-service trace | Spans / baggage | No tokens or unapproved email/PII |
| Test / CI failure | Build output | No real credentials dumped to stdout, stderr, or artifacts |

### 13.2. Testing DTOs with `MockMvc` and Mock Tokens

Suppose the application has the `/api/me` controller from section 3 returning only `MeResponse(displayName, accountType)`. You can use Spring Security Test's `jwt()` post-processor to create a test authentication.

Test dependencies:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MeResponsePrivacyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void meDoesNotEchoCredentialOrPrivateClaims() throws Exception {
        String fakeToken = "test-only-not-a-real-access-token";
        String privateEmail = "private-person@example.test";

        String json = mvc.perform(
                get("/api/me")
                    .with(jwt().jwt(builder -> builder
                        .tokenValue(fakeToken)
                        .claim("sub", "user-123")
                        .claim("preferred_username", "Example User")
                        .claim("email", privateEmail)
                        .claim("scope", "profile")
                    ))
            )
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        assertThat(json).contains("Example User");
        assertThat(json).doesNotContain(fakeToken);
        assertThat(json).doesNotContain(privateEmail);
        assertThat(json).doesNotContain("scope");
    }
}
~~~

This tests **response mapping** and requires a real MVC setup with the `/api/me` endpoint. `jwt()` builds a mock authentication: **it does not run real signature/JWK validation**. Write separate decoder/security-chain tests to prove issuer, audience, and timestamps are validated properly.

For opaque tokens, use `opaqueToken()` test support or stub the introspection endpoint to test response mapping; never put production opaque tokens into tests.

### 13.3. Testing the Absence of Tokens in Application Logs

Spring Boot Test provides `OutputCaptureExtension` to capture stdout/stderr during tests. An integration test can verify a synthetic string **does not appear** in captured output:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeLoggingExampleTest {

    @Test
    void loggingDoesNotContainCredential(CapturedOutput output) {
        String fakeCredential = "fake-token-for-test-only";

        // Invoke the application flow with fakeCredential here
        // using an appropriate test setup, never real credentials.

        assertThat(output.getOut()).doesNotContain(fakeCredential);
        assertThat(output.getErr()).doesNotContain(fakeCredential);
    }
}
~~~

Replace the comment with an actual request/operation in your project's test; otherwise the assertion is illustrative only. `OutputCaptureExtension` **does not prove all log destinations are safe**: it does not capture gateway logs, APM events, remote collectors, or every async appender/sink. Combine tests across all data-receiving layers.

### 13.4. Testing Serialization with a Non-Real Canary Value

A helpful technique is placing a clearly recognizable synthetic value such as:

~~~text
LEAK-CANARY-ACCESS-TOKEN-DO-NOT-USE-001
LEAK-CANARY-EMAIL@example.test
~~~

into test attributes and checking whether it appears in **responses, application logs, proxy logs, traces, or error trackers**. Never use a real credential or place a canary where policy intentionally requires body logging. Canaries test only the code paths actually exercised; they do not replace reviewing logger and telemetry configurations.

### 13.5. What Should Negative Tests Verify?

Beyond verifying valid tokens yield proper responses, test:

- Missing `Authorization` on a protected API → 401; body contains no raw headers.
- Invalid Bearer credential → 401; logs contain no synthetic credential.
- Active access token missing scope → 403; response contains no raw `Jwt` or introspection attributes.
- Exception containing a synthetic sensitive string → HTTP response never echoes the sensitive message.
- Misconfigured HTTP client → errors and logs contain no client secret or Basic header.
- New claim names/types added at the issuer → DTO does not automatically emit new out-of-contract fields.
- Client sends Bearer token in an unsupported location → gateway still does not log query credentials.

**Privacy checks can be automated as part of API testing**, provided you use synthetic data and never store production tokens in test code or CI outputs.

## 14. Responding When an Access Token Appears in Logs

A token showing up in logs is not merely a “formatting issue”. If the token is unexpired and logs were shipped to a centralized backend, an unauthorized party may already have read the credential.

Break incident handling into concrete decisions:

### 14.1. Scope the Exposure

Determine:

1. **Which token/credential type** leaked: access token, refresh token, ID token, Basic client secret, private key, or cookie?
2. Which issuer/resource does the token belong to, and could it still be valid?
3. Where did the logs travel: local console, container logs, collectors, SIEM, APM, backups, tickets, CI artifacts?
4. Who has access, and is there evidence of downloading, viewing, or copying?
5. Which configuration caused the leak, and is it still active?

Never paste the raw token into a second investigation ticket as an example. Use incident IDs, request IDs, or safe metadata with restricted access.

### 14.2. Stop Further Leakage

Disable the body/header logging causing the leak, fix serialization or exception handlers, check gateways/APMs, and roll out the fix. Never merely hide a field in a log-viewer UI while collectors continue receiving and storing raw credentials.

If secrets were exposed, coordinate with Identity/Security teams to consider:

- **Revoking access tokens** if a mechanism exists and risk warrants it.
- **Revoking refresh tokens** and related sessions where appropriate.
- **Rotating client secrets, introspection credentials, or signing keys** if those secrets were exposed. Rotating signing keys has broad impact and requires an explicit incident policy.
- Restricting privileges of still-active credentials and monitoring for anomalous usage.
- Executing compliance notifications per organizational rules if personal data was also exposed.

### 14.3. Clean Up Stored Data and Prevent Recurrence

Identify where logs must be purged, quarantined, given shorter retention, or locked down; remember replicated or backed-up logs may survive deleting a single copy. After fixing, verify with synthetic credentials/canaries that the leak path is closed, and add regression tests and config reviews.

**Never assume an expired token means the incident has no impact**: access logs may contain PII, client secrets, or system internals that remain useful to attackers long after a JWT expires.

## 15. Design Checklist for Principal-Aware Endpoints

Before shipping an API to production, verify:

| Question | Desired Decision |
|---|---|
| Which identity fields does the API truly need to return? | DTO with an explicit field list |
| Are `Jwt`, `Authentication`, or introspection responses returned directly? | **No** |
| Does the DTO change automatically when the issuer adds claims? | **No**; contract changes require review |
| Are any fields email, phone, subject, tenant, group, or role? | Used only when needed and caller is permitted |
| Where are requests/responses logged? | Inventoried sinks with redaction at the source |
| Can gateways log `Authorization` or query strings? | No credentials collected |
| Do outbound HTTP clients enable wiretap or full body logging? | No tokens or secrets collected |
| Do exception handlers return `getMessage()` or stack traces? | No internal details sent to clients |
| Does APM capture headers, bodies, or baggage? | Sensitive fields controlled |
| Are tokens, `sub`, or email used as metric labels? | Not in general metrics; audit actor IDs follow separate policy |
| Is there a request ID / trace ID independent of tokens? | Yes, safely generated and managed |
| Are responses and logs tested with synthetic credentials? | Both success and failure auth cases covered |
| If a token leaks, is there a revocation/rotation runbook? | Clear ownership and execution plan |

### 15.1. Safe Default Pattern for Business APIs

For **Orders API**:

~~~text
Input:
  Authorization: Bearer <access_token>

Authentication:
  JwtDecoder / OpaqueTokenIntrospector
  → principal & GrantedAuthority

Authorization:
  scope / role / tenant / owner policy

Output:
  OrderResponse {
    id,
    status,
    createdAt,
    ... permitted business fields
  }

Application logs:
  event, outcome, requestId, duration

Never output or log:
  token value, Authorization, refresh token, client secret,
  raw Jwt/Authentication, arbitrary claims, sensitive stack traces
~~~

Returning an `OrderResponse` still requires per-record access control; merely removing tokens from JSON **does not guarantee** the returned business data matches the right tenant or owner.

## 16. Self-Check Questions

**Q1.** Once a Resource Server successfully validates a JWT, can it return `Jwt` directly to the client?

**No.** `Jwt` holds the token value and claims the client may not be allowed to receive. Build a DTO with explicitly chosen fields.

**Q2.** Is `authentication.getName()` always safe public data?

**No.** It can be `sub`, a username, or another configured identifier. It may be PII or an internal ID; returning it must follow the API contract.

**Q3.** Can we log `Authorization: Bearer ...` to debug 401 errors?

**No.** Log error categories, request/trace IDs, statuses, and approved metadata. Raw tokens can be replayed as credentials while unexpired.

**Q4.** If a token is an unreadable opaque string, is it safe to log?

**No.** An opaque token is still a bearer credential. It does not need JWT structure to be sensitive.

**Q5.** Is setting `server.error.include-stacktrace=never` enough?

**No.** Security filters, custom exception handlers, access logs, outbound HTTP logging, gateways, APMs, and tracing can all leak independently.

**Q6.** Why not use the token as a correlation ID?

Because a token is a credential. Putting it in MDC, logs, traces, or baggage spreads it across systems and expands risk. Use a dedicated request ID / trace ID.

**Q7.** Can a service calling downstream APIs send a Bearer token?

Yes, when permitted by contract and targeting the right downstream audience, sent only to authorized endpoints over secure channels; **never echo the token in responses or logs**, and never forward an inbound token with the wrong audience.

**Q8.** Does testing with `jwt()` in Spring Security Test prove the real decoder never leaks tokens?

Not completely. That post-processor mocks authentication and bypasses real JWS validation. It tests DTOs and security rules, while logging, gateways, and the real decoder need dedicated tests with synthetic data.

## 17. Conclusion

A Resource Server must use principals and access tokens to **authenticate and enforce permissions**, without forwarding all authentication material to clients or recording it in logs:

1. **Credentials are not response data.** Raw access tokens, refresh tokens, ID tokens, client secrets, and `Authorization` headers must never appear in business JSON.
2. **Principals are not DTOs.** Read only the verified attributes the service needs, then return a DTO with permitted fields; never serialize whole `Jwt`, `Authentication`, or `OAuth2AuthenticatedPrincipal` objects.
3. **Allowlist-based logging.** Log event names, outcomes, request/trace IDs, and normalized metrics rather than raw headers, tokens, arbitrary claims, or exception dumps.
4. **Protect across all layers.** Servlet/WebFlux, gateways, HTTP clients, introspection, distributed tracing, error trackers, and CI can all record sensitive data.
5. **Test and prepare incident response.** Use synthetic credentials to test responses and logs, and maintain runbooks to scope exposure and revoke/rotate credentials if a leak occurs.

Easy rule of thumb:

~~~text
Receive token → verify → build principal → authorize
              → select permitted business fields → return minimal DTO

Logs/traces:
  requestId + event + outcome + status

NEVER:
  echo tokens, serialize security contexts,
  log Authorization headers, dump claims,
  put bearer credentials into baggage/metrics
~~~

**Keeping sensitive token data out of API responses and logs is part of the security contract**, not merely a logger configuration trick. Spring Security helps the API establish identity and permissions; the application must still actively control what data leaves request processing via JSON, telemetry, and operational systems.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
