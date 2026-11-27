# Distinguishing Remote Errors, Inactive Tokens, and Denial Policies

In a **Spring Security OAuth 2.0/OIDC Resource Server** running on **Spring WebFlux**, access tokens can be validated using **reactive token introspection**. The Resource Server sends the token to the Authorization Server (AS) via the introspection endpoint, then uses the result to build an `Authentication` and enforce permissions. Unlike local JWT verification, this model also depends on a **remote HTTP call**.

When a request fails, three distinct situations are frequently lumped together as "bad token":

1. **Invalid/inactive token:** The AS returns a valid introspection verdict such as `"active": false`, or the token fails authentication/profile rules defined by the system.
2. **Remote error:** The Resource Server **has no trusted verdict about the token** because of a timeout, DNS/TLS error, HTTP 429/5xx, introspection credential failure, or protocol-violating response.
3. **Policy denial:** The token was accepted, yet the caller lacks the required scope, role, tenant membership, ownership, or relationship to a business resource.

**All three may cause the API to deny access, yet they differ in root cause, HTTP response, retry behavior, caching, and investigation steps.** An HTTP **401 from the introspection endpoint** can mean **the Resource Server's client secret for calling the AS was rejected**—it does **not** mean the user's access token was revoked.

This lesson examines the `ReactiveOpaqueTokenIntrospector` path, **RFC 7662**, **RFC 6750**, **fail-closed** mechanics, Reactor error classification, 401/403/5xx response policy design, retry/cache bounds, and testing with **`StepVerifier`** and **`WebTestClient`**.

## 1. Two Different HTTP Requests: Client → API and API → Authorization Server

The OAuth2 Client calls the API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-token-example
~~~

To verify the token, the Resource Server calls the introspection endpoint using **the Resource Server's own credentials**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-introspection-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-token>
~~~

Token/credential strings in examples are dummy values. Real secrets must be protected and never appear in source code, logs, or public documentation.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant RS as WebFlux Resource Server
    participant AS as Authorization Server
    C->>RS: GET /api/orders/123 + Bearer T
    RS->>AS: POST /introspect with T + RS credentials
    alt AS returns valid verdict: active=false
        AS-->>RS: HTTP 200, {"active":false}
        RS-->>C: Typically 401 + Bearer invalid_token
    else AS returns valid verdict: active=true
        AS-->>RS: HTTP 200, active, scope, aud, sub...
        RS->>RS: Validate token profile and authorities
        alt Missing functional or record-level permission
            RS-->>C: Typically 403 or 404 per policy
        else Authorized
            RS-->>C: Business response
        end
    else Network, TLS, HTTP 429/5xx, schema error...
        AS--xRS: No trusted verdict
        RS->>RS: Fail closed, no valid Authentication created
        RS-->>C: Error response per dependency policy
    end
~~~

**Separate the two status codes:**

- **AS → RS:** HTTP status from the introspection endpoint reflects protocol validity, availability, or the Resource Server's permission to call that endpoint.
- **RS → OAuth Client:** API status reflects authentication, authorization, and failure policy for the inbound request.

An HTTP 401 on the **AS → RS** leg usually requires checking client credentials, mTLS, or introspection access rights; it **cannot be interpreted directly** as `invalid_token` on the **RS → client** leg.

## 2. Processing Flow of `ReactiveOpaqueTokenIntrospector`

In WebFlux, Spring Security uses `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive authentication components.

~~~mermaid
flowchart TD
    A["Authorization: Bearer T"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer Authentication WebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["ReactiveOpaqueTokenIntrospector"]
    E --> F{"Introspection result?"}
    F -- "Valid principal" --> G["BearerTokenAuthentication"]
    G --> H["SecurityContext in Reactor Context"]
    H --> I["AuthorizationWebFilter / method security"]
    I --> J{"Authorized?"}
    J -- "No" --> K["403/404 per policy"]
    J -- "Yes" --> L["Controller / Service"]
    F -- "Token inactive" --> M["Authentication failure, typically 401"]
    F -- "Remote error" --> N["No Authentication created; failure policy"]
~~~

| Component | Responsibility |
| --- | --- |
| `ReactiveOpaqueTokenIntrospector` | Returns a principal or error signal from token verification |
| Remote introspection implementation | Calls the AS over HTTP/TLS and parses responses per contract |
| `OAuth2AuthenticatedPrincipal` | Holds `attributes`, `name`, and `authorities` after introspection |
| `BearerTokenAuthentication` | Standard Authentication when an opaque token is accepted |
| `ReactiveSecurityContextHolder` | Reads SecurityContext from the Reactor subscriber Context |
| `AuthorizationWebFilter` | Enforces HTTP rules such as `authenticated()`, `hasAuthority(...)` |
| Reactive method security | Checks permissions at the service layer when configured |
| Authentication entry point / failure handler | Builds responses when authentication fails |
| Access-denied handler | Handles insufficient privileges after authentication |

The reactive interface has a contract of the form:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

// For a ReactiveOpaqueTokenIntrospector implementation:
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Only a **successful** `Mono<OAuth2AuthenticatedPrincipal>` supplies data for the authentication manager to construct an Authentication. A **`Mono.error(...)`** expresses that the token was rejected or could not be verified—granting no privileges.

**Never arbitrarily use `Mono.empty()` to represent an inactive token.** It does not behave like an explicit error signal; providers and handlers may react differently. Respect the implementation's and error-mapping layer's contract.

## 3. RFC 7662: `active=false` Has Specific Semantics

**OAuth 2.0 Token Introspection – RFC 7662** allows the AS to return token metadata.

Success response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export",
  "token_type": "Bearer",
  "exp": 1893456000
}
~~~

Inactive token response:

~~~json
{
  "active": false
}
~~~

A valid response with `active: false` may represent an expired token, a revoked token, a token unrecognized by the AS, or a policy-denied case where the AS discloses no further details. The API **must not guess the exact reason** when the AS provides only the boolean.

### Distinguishing Inactive from Missing Metadata

| Outcome from AS | Interpretation |
| --- | --- |
| HTTP 200 + `active: false` | Token is inactive per introspection verdict |
| HTTP 200 + `active: true`, contract-valid | Proceed to validation and principal mapping |
| HTTP 200 missing `active` | Schema-incomplete response; **must not assume active** |
| HTTP 200 with string `active: "true"` | Wrong schema type; must fail closed |
| HTTP 200 + `active:true` with wrong `aud` | Token/profile rejected by the API |
| HTTP 200 + `active:true`, missing `scope` | Do not fabricate authorities; authorization may deny |

Other fields usually depend on the issuer:

- `sub` identifies the subject if present; never assume every token represents a human user.
- `client_id` identifies the OAuth client, not automatically a record owner.
- `scope` carries granted functional permissions.
- `exp` supports lifetime/cache checks; NumericDate is typically **epoch seconds**, though the Java type inside the principal may have been converted by the introspector.
- `aud` checks whether the token is intended for this API.
- `tenant_id` is a custom claim; it does not replace live membership/ownership checks.

**`active:true` alone is never enough to read arbitrary resources.** Validate issuer/audience/token purpose per profile and proceed to authorization.

## 4. Remote Errors: No Verdict Yet on the Token

Failures during an introspection call must be understood by **where they occur**:

| Remote signal | Common cause | Must not be inferred |
| --- | --- | --- |
| DNS or TCP connect failure | Cannot resolve/reach AS host | Token was revoked |
| TLS handshake/certificate failure | Cannot establish trusted connection | User's token has an invalid signature |
| Read timeout | Result did not arrive before deadline | `active:false` |
| HTTP 500/502/503/504 | AS or proxy/gateway failed | Token expired |
| HTTP 429 | RS introspection caller was rate limited | Token lacks scope |
| HTTP 401/403 from AS | RS client auth/authorization rejected | OAuth client's token is invalid |
| HTTP 400 from AS | Malformed introspection request or protocol violation | JWT has bad signature |
| HTTP 200 with malformed JSON | Remote protocol/schema error | Safe to let token through |
| HTTP 200 with wrong `active` type | No contract-valid verdict | Token is definitely active |

**Never conflate an HTTP 401 from the introspection endpoint with an HTTP 401 returned by the Resource Server.**

Example of the AS rejecting the Resource Server's credentials:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

This error may require rotating a client secret, checking mTLS, verifying endpoint permissions, or fixing issuer configuration. It proves nothing about token T's status.

Example of an AS outage:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
~~~

Without a valid token response, the Resource Server **cannot build a trusted Authentication** from this call. It must deny access to protected resources, while clearly classifying the dependency failure for operations and choosing the client-facing response.

## 5. Fail Closed: Security Decision Differs from HTTP Status Code

**Fail closed** means that when authentication is required and the token cannot be verified per policy, **no access is granted**.

~~~text
No trusted introspection result
              |
              v
No verified Authentication
              |
              v
Cannot view/modify protected resource
              |
              v
HTTP response per failure policy
~~~

Two independent steps:

1. **Security decision:** Grant no Authentication if the token is inactive, violates profile, or the dependency cannot verify it.
2. **Error representation:** What response goes to the caller? A genuinely invalid token may receive **401 `invalid_token`**; an outage may receive **503** if the application explicitly configured that behavior.

Fail closed **does not require** every remote error to report `invalid_token`. If an API reports "invalid token" during an AS timeout, clients may discard valid tokens, log users out, or enter refresh loops that worsen the outage.

### Two Anti-Patterns to Avoid

~~~java
// WRONG: downgrades an introspection error into an accepted principal.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(guestPrincipal));
~~~

~~~java
// WRONG: swallows errors into empty without an explicit contract.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.empty());
~~~

The first branch can **fail open** if the principal carries authorities; the second can leave the authentication flow in an ambiguous state. It is far better to **preserve a clearly typed error signal** for security layers to handle.

## 6. 401, 403, and 5xx: Response Policies That Must Be Distinguished

| Case | Valid token verdict? | Security outcome | Common response or policy target |
| --- | --- | --- | --- |
| No Bearer sent to protected endpoint | No token | Unauthenticated | **401** + Bearer challenge |
| AS returns `active:false` | No | Authentication failure | Typically **401** + `invalid_token` |
| Wrong audience/issuer/profile | Rejected by API | Authentication failure | Typically **401** |
| AS timeout / 429 / 5xx | **Unknown** | No Authentication granted | Possibly **5xx** per custom failure policy |
| Wrong introspection credentials | **Unknown** | No Authentication granted | Possibly **5xx**, operational alert |
| Malformed response schema from AS | **Unknown** | No Authentication granted | Possibly **5xx**, protocol/dependency error |
| Valid token, missing scope | Yes | Authorization denied | Typically **403**, possibly `insufficient_scope` |
| Valid token, wrong tenant/owner | Yes | Business authorization denied | **403 or 404** per policy |
| Valid token, sufficient permissions | Yes | Allowed to proceed | Business response |

**The table above does not describe an HTTP status guaranteed out of the box by Spring Security for every remote exception.** An implementation may wrap remote exceptions into `AuthenticationException`, leading to different responses depending on the handler. To guarantee 503 on upstream outages, the application must implement **error classification and HTTP mapping at a boundary that preserves root-cause information**, then verify end-to-end.

### 401 and 403 Differ in OAuth 2.0 Meaning

Per **RFC 6750**, the Resource Server may return:

**No token sent:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

**Token sent, but rejected:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Token accepted, but lacks scope:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Headers may also include `realm`, `error_description`, or `scope`. Parameter ordering and response bodies depend on configuration.

**Not every 401 must contain `invalid_token`.** A request without credentials may receive a Bearer challenge **with no error code**. Never include raw access tokens, client secrets, or private metadata in `error_description`.

### 503 as an Example Dependency-Outage Policy

If an API designs this contract itself, a response could look like:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://api.example.com/problems/authentication-dependency",
  "title": "Authentication temporarily unavailable",
  "status": 503,
  "detail": "Please retry later"
}
~~~

This is an **illustrative custom response, not a Spring Security default**. If clients retry automatically, consider whether the operation is idempotent; never blindly repeat a payment-creation POST on a dependency error.

## 7. When Does an Exception Mean an Inactive Token?

Exception types encountered in Spring Security and WebClient:

- `BadOpaqueTokenException`: used to represent a rejected opaque token.
- `OAuth2IntrospectionException`: error during introspection, including implementation-dependent failures.
- `OAuth2AuthenticationException`: OAuth2 authentication error carrying an `OAuth2Error`.
- `AccessDeniedException`: insufficient privileges during authorization—**never proves a token is inactive**.
- WebClient/transport exceptions: HTTP, connect, TLS, or timeout errors; may be wrapped by the framework.

Avoid naive classification like:

~~~java
// INCORRECT: treating every runtime error as invalid_token.
if (error instanceof RuntimeException) {
    return "invalid_token";
}
~~~

For a reliable taxonomy, attach a **specific error category right at the boundary that has full evidence**:

~~~java
enum IntrospectionFailureKind {
    INACTIVE_TOKEN,
    INVALID_TOKEN_PROFILE,
    UPSTREAM_UNAVAILABLE,
    UPSTREAM_AUTHENTICATION_FAILED,
    BAD_INTROSPECTION_RESPONSE,
    UNEXPECTED_FAILURE
}
~~~

This is an **application-defined enum**, not a Spring Security API. Because exceptions can be wrapped across layers, classification logic should inspect the **cause chain** and the active implementation's contract rather than parsing message strings.

**Note:** a generic `OAuth2IntrospectionException` alone is not enough to conclude `active:false` in all cases. Conversely, when introspection genuinely returns `active:false`, preserve a distinct invalid-token signal during mapping.

## 8. Basic Configuration for a Reactive Opaque Token Resource Server

Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Always use a trusted endpoint over TLS and store credentials in a secret manager or protected environment variables.

Security configuration:

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
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

This example assumes a **stateless Bearer-token-only API** with no automatic browser cookie authentication. With sessions/cookies, evaluate CSRF properly instead of disabling it globally.

**When using Spring WebFlux, you need `ReactiveOpaqueTokenIntrospector`**—do not grab a synchronous Servlet `OpaqueTokenIntrospector` and expect it to become non-blocking. How you configure the remote introspector, timeouts, and HTTP client depends on your Spring Security version; use the builder/implementation matching your actual dependencies.

### `permitAll` Does Not Automatically Skip a Sent Token

If `/public/info` sits inside the same reactive security chain with Resource Server enabled:

~~~http
GET /public/info HTTP/1.1
Authorization: Bearer inactive-token
~~~

the filter **may still introspect the token and return 401 before `permitAll()`**. If public routes must ignore any Bearer token sent by callers, configure a separate security chain or an explicit token converter strategy.

## 9. Custom Policy: Active Tokens with the Wrong Audience Must Also Be Rejected

Suppose the AS confirms:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["payments-api"]
}
~~~

This token may be active, yet **is not intended for the Orders API**. A decorator can verify `aud` after the delegate introspector succeeds:

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(principal -> {
                Object aud = principal.getAttribute("aud");
                boolean allowed =
                    "orders-api".equals(aud)
                    || (aud instanceof Collection<?> values
                        && values.contains("orders-api"));

                if (!allowed) {
                    return Mono.error(new BadOpaqueTokenException(
                        "Token audience is not accepted"));
                }
                return Mono.just(principal);
            });
    }
}
~~~

Here:

1. The delegate processes the token and emits the principal **after introspection succeeds**.
2. Policy validates the audience per contract.
3. A wrong audience becomes a **token-acceptance failure**, not a remote error.
4. Missing `aud` is rejected when Orders API requires audience binding.
5. Other constraints (issuer/client binding, `exp`, token purpose/profile) must also be enforced accordingly.

Because this check runs at the **authentication boundary**, it makes sense to reject it as a token not meant for this API. This differs from a user holding a valid token who does not own order 123: that latter case is **object-level authorization**, not an inactive token.

### Wiring a Custom Introspector into `SecurityWebFilterChain`

If you already have a policy-wrapped `ReactiveOpaqueTokenIntrospector` bean, wire it as:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector policyIntrospector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(opaque ->
                opaque.introspector(policyIntrospector)))
        .build();
}
~~~

This is a **wiring sample**; it does not construct the remote introspector itself. The application must construct the policy bean around a trusted, version-compatible remote introspector; if multiple beans share the interface, use qualifiers. Never inject a bean into itself and create a circular dependency.

## 10. Timeouts with Reactor: Emit a Distinct Error, Never Grant a Principal

Reactor operators like `timeout(...)` and `onErrorMap(...)` preserve distinct error types:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class TimedIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;

    public TimedIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline) {
        this.delegate = delegate;
        this.deadline = deadline;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .timeout(deadline)
            .onErrorMap(TimeoutException.class,
                cause -> new IntrospectionUpstreamUnavailableException(
                    "Introspection deadline exceeded", cause));
    }
}

final class IntrospectionUpstreamUnavailableException
        extends RuntimeException {

    IntrospectionUpstreamUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**This snippet only tags the timeout; it does not automatically make Spring Security return 503.** Providers/failure handlers may wrap the exception or choose another status. To ensure remote outage → 503, build an error-translation path at the authentication boundary and verify with real HTTP tests.

Key conditions:

- `deadline` must be positive and fit within the API's latency budget.
- HTTP client connect/read timeouts may throw exception types other than Reactor's `TimeoutException`.
- Never catch every `Exception` and convert it to `BadOpaqueTokenException`, which misreports network outages as invalid tokens.
- `timeout` stops waiting; it does not guarantee the Authorization Server stops processing immediately.
- Bound concurrent/waiting connections to avoid exhausting event loops or connection pools.

**Never call `block()` inside a reactive introspector:**

~~~java
// DO NOT DO THIS:
OAuth2AuthenticatedPrincipal principal =
    delegate.introspect(token).block();
return Mono.just(principal);
~~~

That blocks and creates a separate subscription. Return the publisher directly so Spring Security manages the subscription.

## 11. Retries: Strictly for Genuinely Recoverable Errors

| Scenario | Retry immediately? | Reason |
| --- | --- | --- |
| Token inactive per valid response | **No** | The AS already returned a verdict |
| Wrong audience/issuer/profile | **No** | Policy will not change on retry |
| HTTP 401/403 on introspection client auth | Usually **no** | Fix credentials/permissions |
| HTTP 429 | Possibly, honoring `Retry-After` and budget | Avoid retry storms |
| HTTP 502/503/504 | Limited retries acceptable | Transient errors may recover |
| Connect/read timeout | Limited retries acceptable | Still consumes load and time |
| Malformed schema response | Do not retry indefinitely | Identify the protocol bug |

Example retrying only errors **already classified** as upstream unavailable:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

return delegate.introspect(token)
    .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
        .filter(error ->
            error instanceof IntrospectionUpstreamUnavailableException));
~~~

This is an **illustrative fragment inside a `Mono`-returning method**, not a full Java class. It assumes the adapter actually emits `IntrospectionUpstreamUnavailableException` on transient errors; not every network error converts automatically.

Retries must have an **overall deadline**, capped attempts, and jitter; never retry inactive tokens; and never allow API, gateway, and client layers to stack unbounded retries that overload the AS. Although introspection is usually a read-state operation, verify contract idempotency before retrying an HTTP POST.

### Circuit Breaker and Bulkhead

During an AS outage, a circuit breaker sheds load to the dependency, and a bulkhead caps waiting requests. Yet an open circuit breaker **is not proof that a token is inactive**. Requests requiring authentication must still **fail closed**, returning a clearly defined infrastructure error response.

## 12. Caching, `exp`, and the Revocation Delay Window

Positive caching reduces introspection latency while introducing **revocation lag**:

~~~text
t0:      AS returns active=true for token T, RS caches for 30s
t0+5s:   AS revokes T
t0+10s:  RS cache hit, may still accept T
t0+30s:  cache expires
t0+31s:  RS re-introspects, sees active=false
~~~

With a trusted `exp`, cap reuse:

~~~text
reuseUntil = min(timeOfVerification + maxCacheTtl,
                 tokenExpiresAt - safetyMargin)
~~~

**Cache TTL does not replace `exp` and does not guarantee instant revocation.** If `exp` is unknown or near-real-time revocation is required, disable caching by policy.

### Stale-on-Error Is a Security Trade-Off

Anti-pattern:

~~~java
// NO: on AS error, fall back to an expired cached principal.
return remote.introspect(token)
    .onErrorResume(error -> Mono.just(expiredCachedPrincipal));
~~~

The token may have been revoked or had its scopes reduced; serving expired cache entries alters authentication guarantees. If a system adopts stale-on-error, it requires formal risk approval, a hard stale-age cap, never exceeding `exp`, exemption of sensitive endpoints, and auditing. **The safe default is never using stale expired results.**

### Negative Caching Must Also Classify Errors

Avoid:

~~~text
AS timeout -> store "invalid token" in cache for 10 minutes
~~~

A transient remote error is not an inactive token. Negative caching, if used at all, must cover **only trusted inactive-token verdicts**, with its own short TTL and capacity cap, and never cache network errors as credential failures.

Cache keys are security-sensitive: avoid logging raw tokens; consider HMAC digests with a dedicated key partitioned by issuer/audience/policy, and protect cached principals and authorities.

## 13. An Accepted Token Does Not Mean Sufficient Permissions

Suppose introspection returns:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "tenant_id": "t-7"
}
~~~

The Resource Server can build an Authentication with authority `SCOPE_orders.read`. That alone **does not** confirm user 42 may view order 123.

~~~text
Introspection:
  Token active, valid profile
          |
          v
HTTP authorization:
  Has SCOPE_orders.read?
          |
          v
Business object authorization:
  Does actor still hold membership in tenant?
  Does order belong to requested tenant?
  Is actor owner/manager or holder of an active READ share?
          |
          v
Query scoped properly and return only permitted DTOs
~~~

| Layer | Example failure | Typical response |
| --- | --- | --- |
| Authentication | `active=false` | 401 |
| Token profile | `aud=payments-api` | 401 / invalid token policy |
| Functional authorization | Missing `SCOPE_orders.read` | 403 |
| Object authorization | Order belongs to another tenant | 403 or 404 |
| Business state | Editing finalized order forbidden | 403 or domain-appropriate response |

**Never turn missing scope into an inactive token.** When a valid token lacks functional privileges, returning `invalid_token` can force the client to refresh/re-login and still end up without the needed scope.

### Scope Differs from Record-Level Permissions

A token with `SCOPE_orders.read` allows the **order-reading capability** under policy, yet the service must check tenant, owner, sharing, assignments, and parent-child relationships. Some permissions can change **while the access token is still valid**; when rapid membership revocation is needed, check live data sources or dedicated cache invalidation.

## 14. Reactor Context and Errors Before the Controller

After introspection **succeeds**, the Resource Server places `BearerTokenAuthentication` into the Reactor Context.

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(BearerTokenAuthentication.class)
        .map(BearerTokenAuthentication::getName);
}
~~~

When a token is inactive or remote introspection fails, the HTTP request is blocked **before the controller or service ever executes**. Thus, controllers are not the right place to catch all introspection errors.

In WebFlux, `ReactiveSecurityContextHolder` retrieves SecurityContext per **Reactor subscriber**, unlike `ThreadLocal`-based `SecurityContextHolder`. Never call `block()` or self-`subscribe()` to locate a principal inside a reactive request pipeline.

### Why Might `ControllerAdvice` Miss These Errors?

Authentication errors typically arise inside the **WebFilter chain** and are handled by authentication entry points/failure handlers. A `@RestControllerAdvice` or controller exception handler **does not by default** intercept exceptions thrown before handlers run. To standardize 401/503 responses, place the mapping at the proper boundary in security/reactive HTTP error handling.

## 15. Designing Classification and HTTP Mapping for Remote Errors

An application failure taxonomy might include:

~~~java
enum IntrospectionFailureKind {
    INACTIVE_TOKEN,
    INVALID_TOKEN_PROFILE,
    UPSTREAM_UNAVAILABLE,
    UPSTREAM_AUTHENTICATION_FAILED,
    BAD_INTROSPECTION_RESPONSE,
    UNEXPECTED_FAILURE
}
~~~

This is an **application-defined enum**. A real implementation can have an HTTP client adapter tag the failure kind upon inspecting status/cause, then propagate that signal across the authentication boundary.

Key WebFlux extension points to understand:

- `ServerAuthenticationEntryPoint` handles authentication initiation/challenges.
- WebFilter authentication failure handling processes authentication errors.
- `ServerAccessDeniedHandler` handles post-authentication denials.
- Global reactive error handling can process infrastructure errors **if those errors reach it**.

**Never assume:** throwing a `RuntimeException` from an introspector makes Spring Security return 503 automatically. The provider may wrap it into `AuthenticationException` and the entry point may return 401. To guarantee remote outage → 503, **preserve the remote-error signal across the boundary**, select the right handler, and verify with real HTTP tests.

Design rules:

1. Use `invalid_token` only when you have evidence the token was rejected.
2. Never report an outage as `insufficient_scope`, because token verification never completed.
3. Never turn an RS credential failure into an end-user username/password error.
4. Never let a dependency 5xx allow a request through.
5. Never disclose internal hostnames, introspection client secrets, raw access tokens, or stack traces.

## 16. Logs, Metrics, and Alerts by Root Cause

| Metric/Signal | Meaning |
| --- | --- |
| `introspection_active_total` | Accepted active-token results |
| `introspection_inactive_total` | Inactive tokens per valid verdict |
| `introspection_upstream_failure_total` | Timeouts, TLS, 429/5xx, credential or schema errors |
| `introspection_latency_seconds` | P50/P95/P99 of AS calls |
| `authentication_rejected_total` | Requests failing to produce an Authentication |
| `authorization_denied_total` | Missing scope or post-auth object policy denials |
| `introspection_cache_hit_total` | Reuse rate; monitor alongside revocation lag |

Metric names are **design examples**, not metrics built into every Spring Security version.

Safety rules:

- Record request ID, failure kind, normalized endpoint, issuer alias, and timestamp.
- Never log raw Bearer tokens, Authorization headers, or client secrets.
- Never place tokens or token digests into metric labels, avoiding high cardinality and data exposure.
- Never log entire introspection responses if they contain PII or internal privileges.
- Distinguish 401 caused by inactive tokens from 401 returned by the AS when the RS failed to authenticate itself.

Common diagnostic patterns:

~~~text
API 401s rise + active=false rises:
  Check expired/revoked tokens or tokens unrecognized by the issuer.

AS HTTP 401/403 rises:
  Check introspection client credentials and AS access rights.

AS timeouts/429/5xx rise:
  Check AS availability, network, retry storms, rate limits.

API 403s rise while introspection reports active:
  Check scope mapping, roles, method security, owner/tenant policies.
~~~

## 17. `StepVerifier`: Testing Three Error Signal Branches

In unit tests, you can build a fake `ReactiveOpaqueTokenIntrospector`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

ReactiveOpaqueTokenIntrospector fakeRemote = token -> {
    if ("inactive".equals(token)) {
        return Mono.error(new BadOpaqueTokenException("Token inactive"));
    }
    if ("timeout".equals(token)) {
        return Mono.error(new TimeoutException("Remote timeout"));
    }

    OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("sub", "user-42", "aud", List.of("orders-api")),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );
    return Mono.just(principal);
};
~~~

With `TimedIntrospector` from Section 10:

~~~java
import java.time.Duration;
import reactor.test.StepVerifier;

TimedIntrospector timed = new TimedIntrospector(
    fakeRemote, Duration.ofSeconds(2));

StepVerifier.create(timed.introspect("inactive"))
    .expectError(BadOpaqueTokenException.class)
    .verify();

StepVerifier.create(timed.introspect("timeout"))
    .expectError(IntrospectionUpstreamUnavailableException.class)
    .verify();

StepVerifier.create(timed.introspect("active"))
    .assertNext(principal ->
        org.junit.jupiter.api.Assertions.assertEquals(
            "user-42", principal.getName()))
    .verifyComplete();
~~~

These are **illustrative test snippets using fakes**, not a complete JUnit class. The goal is confirming **inactive tokens and remote timeouts emit two distinct signals**. No real HTTP, TLS, or AS credentials are involved in this unit test.

### Virtual Time vs. Real Timeouts

When testing `timeout(Duration)` with a slow publisher:

~~~java
ReactiveOpaqueTokenIntrospector delayed = token ->
    Mono.delay(Duration.ofSeconds(10))
        .then(Mono.error(new RuntimeException("Unreachable")));
~~~

you can use `StepVerifier.withVirtualTime(...)` provided the publisher is instantiated lazily and relevant schedulers are controlled by virtual time. This tests the **Reactor operator timeout**, not whether real HTTP client connect/read timeouts produce the same exception type.

## 18. `WebTestClient`: HTTP Responses from the Real WebFilter Chain

To test the Bearer path, send real HTTP headers through **`SecurityWebFilterChain`** rather than relying solely on helpers that inject simulated Authentications.

Suppose the app exposes GET `/api/orders/123` returning 200 when permitted, and the WebFlux security chain requires `SCOPE_orders.read`.

~~~java
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveIntrospectionResponseTest {

    @Autowired WebTestClient client;

    @MockitoBean ReactiveOpaqueTokenIntrospector introspector;

    @Test
    void missingTokenReturns401() {
        client.get().uri("/api/orders/123")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void inactiveTokenReturns401() {
        when(introspector.introspect("inactive-token"))
            .thenReturn(Mono.error(
                new BadOpaqueTokenException("Token inactive")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("inactive-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void activeButMissingScopeReturns403() {
        when(introspector.introspect("only-profile"))
            .thenReturn(Mono.just(principal("profile.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("only-profile"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void activeAndEnoughScopeReachesController() {
        when(introspector.introspect("has-orders-read"))
            .thenReturn(Mono.just(principal("orders.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("has-orders-read"))
            .exchange()
            .expectStatus().isOk();
    }

    private static DefaultOAuth2AuthenticatedPrincipal principal(String scope) {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("sub", "user-42", "scope", scope),
            List.of(new SimpleGrantedAuthority("SCOPE_" + scope))
        );
    }
}
~~~

This test exercises the **real filter/provider/authorization chain**, while mocking the introspector. `principal(...)` constructs authorities directly, so it **does not prove scope parsing from a real introspection response**.

**Prerequisites:** the test app must use the reactive opaque Resource Server with a matching endpoint fixture. `@MockitoBean` is supported in recent Spring Test releases (e.g., Spring Framework 6.2+); older projects can use Spring Boot's `@MockBean` as appropriate.

### Testing Remote Outages Without Guessing Status Codes

Mock example:

~~~java
when(introspector.introspect("upstream-timeout"))
    .thenReturn(Mono.error(
        new IntrospectionUpstreamUnavailableException(
            "Timeout", new TimeoutException("Deadline exceeded"))));
~~~

This test **does not automatically ensure a 503 response**. To test that contract:

1. Confirm the introspector emits a typed remote error and returns no principal.
2. Configure authentication/error mapping that preserves the error classification through the provider/filter.
3. Choose the appropriate client-facing 503 status and response body.
4. Send a Bearer request via `WebTestClient` and assert status, headers/body, and that the controller was never invoked.

Only once the system is configured for 503 should you assert:

~~~java
client.get().uri("/api/orders/123")
    .headers(h -> h.setBearerAuth("upstream-timeout"))
    .exchange()
    .expectStatus().isEqualTo(503);
~~~

**The 503 test will not pass by default with only the basic Resource Server setup from Section 8.** Do not confuse desired failure classification with default runtime behavior.

## 19. Testing the Exact Introspection Protocol with an HTTP Stub

A test with a mocked introspector **does not verify**:

- That the remote client sends the proper `POST` form body `token` and Basic/mTLS client credentials.
- That TLS certificates are verified.
- That HTTP 401/403 from the AS is classified differently from `active:false`.
- That HTTP 429/5xx and timeouts are classified with bounded retries.
- That JSON `active:false` is translated into an invalid-token signal by the remote implementation.
- That responses missing `active` or using wrong types are rejected.
- That scope/audience/exp are normalized and mapped to authorities properly.

Write integration tests using an **HTTP stub introspection server** while keeping the real remote introspector:

| AS Stub Response | Expectation |
| --- | --- |
| HTTP 200 + `{"active":true,"scope":"orders.read"}` | Principal/authority per schema |
| HTTP 200 + `{"active":false}` | Token rejected; typically 401 to client |
| HTTP 200 missing `active` | Token rejected; protocol failure |
| HTTP 200 invalid JSON | Token rejected |
| HTTP 401 from AS | Introspection credential/permission error; do not conclude token inactive |
| HTTP 429 | Deny access; apply retry/rate-limit policy within budget |
| HTTP 500/503 | Fail closed; dependency response per contract |
| Network timeout | Fail closed; deadline verified |
| `active:true`, wrong `aud` | Rejected by token profile |
| `active:true`, missing scope | Authentication succeeds, then authorization returns 403 |

HTTP tests should verify **the outbound request sent to the AS test server**, the RS response returned to the OAuth client, and zero business side effects when authentication fails.

### `mockOpaqueToken()` Tests a Different Layer

Spring Security Test includes helpers like `mockOpaqueToken()` for `WebTestClient` in supported versions. It creates a test Authentication to verify HTTP/method authorization, yet **typically bypasses remote introspection**. Never use a passing `mockOpaqueToken()` test as proof that AS HTTP 401/timeout/`active=false` handling works.

## 20. Common Misconceptions

**"AS returning HTTP 401 means the user's token expired."** No. The credentials used to call introspection may themselves have been rejected.

**"On AS timeout, just return `invalid_token` so the frontend refreshes."** There is no proof the token is invalid; doing so can trap clients in logout/refresh loops and amplify load during an outage.

**"`active=true` means the API must return 200."** No. Audience, scopes, ownership, tenancy, business state, and authorization still apply.

**"Missing scope is the same as `active=false`."** No. That is an authorization denial after the token was authenticated, typically returning 403.

**"HTTP 200 introspection missing `active` is a success."** No. Validate responses against the schema and fail closed.

**"We can retry `active=false` in case the AS changes its mind."** Never. That is the token's inactive verdict at the time the AS answered.

**"`onErrorResume(Exception, cachedPrincipal)` preserves availability safely."** No. If the principal is unverified or the cache entry passed its TTL, that is fail-open.

**"Positive caching does not affect revocation."** No. It introduces revocation lag and must be bounded by TTL and `exp`.

**"Every 403 is `insufficient_scope`."** No. CSRF, method security, owner/tenant policies, or custom filters can also return 403.

**"`permitAll` never introspects tokens."** Wrong. A Bearer token sent to a public route inside the same Resource Server chain may still be processed.

**"WebFlux automatically converts every remote exception into 503."** There is no universal guarantee. Design the mapping explicitly and verify with tests.

**"You can read the principal from `ThreadLocal` `SecurityContextHolder` just like Servlet."** In WebFlux, use the Reactor security context or appropriate principal parameters.

## 21. Design Framework for Production Systems

Before deploying reactive introspection to production, answer:

1. **Who issues and verifies tokens?** Use only trusted issuers' introspection endpoints with TLS and client credentials configured.
2. **Which response proves an inactive token?** Separate valid `active:false` verdicts from remote failures.
3. **What is the required token profile?** Audience, issuer, expiration, token purpose, client binding, and claim schema.
4. **Where are remote errors classified?** At the HTTP client/adapter where status and cause are visible; preserve that classification across the authentication boundary.
5. **How is fail-closed guaranteed?** Never create a principal when the token is unverified.
6. **What statuses are returned?** 401 invalid token, 403 insufficient permissions, 5xx dependency error if required by policy and backed by a handler.
7. **How are timeouts and retries bounded?** Overall deadline, connection pool limits, rate limits, jitter, and circuit breakers.
8. **Is caching used?** If so, positive TTL must not exceed `exp`, measure revocation lag, and never serve stale-on-error indefinitely.
9. **Where are business permissions checked?** Scopes at HTTP/method level; tenant/owner/sharing in the service/repository.
10. **Does monitoring separate root causes?** Inactive tokens, upstream unavailability, credential failures, and authorization denials need distinct signals.
11. **Do tests cross every boundary?** `StepVerifier`, `WebTestClient` with Bearer headers, and HTTP stub introspection.
12. **Are sensitive details protected?** Never log raw tokens, client secrets, introspection payloads, or internal stack traces.

**Key takeaway:** In a WebFlux Resource Server, `active:false` is an **inactive-token verdict**, timeouts/429/5xx/401 from the introspection endpoint are **remote verification problems**, and missing scope/owner/tenant are **post-authentication authorization denials**. All three can result in **denying access**, yet **must never be conflated**. A sound design **fails closed, preserves error classification, returns contract-accurate responses, and tests both the Reactor pipeline and the HTTP filter chain**.
