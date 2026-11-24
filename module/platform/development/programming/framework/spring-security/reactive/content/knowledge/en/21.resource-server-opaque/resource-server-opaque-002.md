# Token Introspection and the Trust Boundary with the Authorization Server

## 1. What Problem Does This Lesson Solve?

In a Spring WebFlux application acting as an **OAuth 2.0 Resource Server**, a client sends an access token to call an API:

```http
GET /api/reports HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer <opaque-access-token>
```

When the token is **opaque**, the Resource Server (RS) cannot read the token string itself to verify its status. The RS typically must send the token to a trusted **Authorization Server (AS)** **Introspection Endpoint** per RFC 7662. The AS returns whether the token is active, the granted scopes, subject, client, audience, and any other metadata the AS permits the RS to see.

**Lesson:** Token introspection and the trust boundary with the Authorization Server.  
**Parent Chapter:** Resource Server Opaque.  
**Module:** Spring Security - reactive.

Two questions must be kept separate:

1. **Authentication/token validity:** Is the token active, unexpired/unrevoked, and genuinely verified by a trusted AS?
2. **Authorization/resource suitability:** Even if the token is active, was it issued for **reports-api**, the right issuer/client/tenant, and does it have sufficient permissions to access the specific endpoint?

The most dangerous fallacy is assuming **"the AS returned active=true, so the request is allowed to do anything."** The Authorization Server provides verified token data, but the Resource Server remains responsible for enforcing token usage boundaries for **its own resources**.

### Learning Objectives

After this lesson, you can:

1. Describe token introspection per RFC 7662 using HTTPS POST, form body, RS credentials, and JSON responses.
2. Distinguish opaque tokens from JWTs and know that JWTs can still be introspected when revocation checks are required.
3. Distinguish HTTP 200/`active:false` from the AS, HTTP 401/403/5xx from the **introspection endpoint**, and HTTP 401/403 returned by the **Resource Server API** to clients.
4. Explain the roles of `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `OpaqueTokenReactiveAuthenticationManager`, `BearerTokenAuthentication`, and `OAuth2AuthenticatedPrincipal`.
5. Configure Spring Security 6.5 WebFlux with `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` and Spring Boot 3.x.
6. Add local validation for `iss`, `aud`, and `client_id` when those claims belong to the data contract with the AS.
7. Understand mapping scopes to `SCOPE_*`, and the difference between 401 (missing/invalid token) and 403 (authenticated but lacking permission).
8. Design an AS/RS trust boundary with TLS, credential management, audience restriction, claim minimization, network egress policy, no-open-redirect, and SSRF protection.
9. Handle AS unavailability, timeouts, concurrency, and revocation/caching trade-offs in a **fail-closed** manner.
10. Write a Java 17+ Spring Boot WebFlux application with an introspector wrapper, protected REST endpoints, and 17 sample test cases; understand why fake tests cannot replace real HTTP introspection integration tests.
11. Diagnose multi-issuer/tenant confusion, token substitution, stale introspection responses, and token leakage through logs.

**Illustrative versions:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor/WebFlux. The `example.invalid` domain and sample tokens/credentials are fake. Examples run once a Gradle wrapper from Initializr is present; calling a real AS requires valid endpoint details and credentials not included in this lesson.

## 2. How Do Opaque Access Tokens Differ from JWTs?

### 2.1. Opaque Token

An opaque access token may simply be a random string:

```text
tok_9b02_opaque_value_for_illustration
```

The Resource Server should not infer the user, scope, or audience from the shape of the string. It may be a handle to data stored in the AS or a proprietary format unknown to the RS. **Never** Base64-decode a token yourself and trust metadata that the client itself could control.

The RS receives a Bearer request and asks the AS: is this token known to the AS, still active, and usable for the requested resource?

### 2.2. JWT Does Not Mean "Do Not Introspect"

JWTs typically carry claims and a signature; the RS can verify a JWT locally using JWKS, issuer, audience, expiration, and appropriate validators. However, a JWT-formatted token can still be routed through an **opaque-token introspection flow** when the system requires online revocation status. Spring Security's `opaqueToken` does not require the token string to be unparseable: it specifies **the introspection verification strategy**.

| Aspect | JWT Validation at RS | Opaque Token Introspection |
|---|---|---|
| Primary verification | Signed claims/JWKS and validators | Response from AS via a trusted endpoint |
| Near-real-time revocation | Requires additional mechanisms | AS can return inactive after revocation |
| Per-request network dependency | Usually none, aside from key refresh | May require calling AS on every request |
| Claims/roles | From verified JWT | From verified introspection response |
| Primary risks | Incorrect key/alg/iss/aud/expiry handling | AS outage, latency, token leakage in network/logs, stale cache |
| Endpoint authorization | Still owned by RS | Still owned by RS |

**Token introspection** is not OIDC `/userinfo`, not token exchange, and does not itself revoke tokens:
- Introspection: verifies token status and metadata.
- UserInfo: OIDC user claims; does not replace resource-server token validation.
- Token exchange: obtains another token intended for downstream resources/delegation.
- Revocation: asks the AS to revoke a token.
- Resource Server: ultimately decides whether a subject may read a given record.

## 3. RFC 7662: Request, Response, and Semantics

### 3.1. Complete Flow

```text
[OAuth2 Client]
      |
      | GET /api/reports
      | Authorization: Bearer T
      v
[Resource Server: Spring WebFlux]
      |
      | 1. Receive and extract Bearer token T
      | 2. HTTPS POST /oauth2/introspect
      |    Authorization: Basic <RS credentials>
      |    Content-Type: application/x-www-form-urlencoded
      |    token=T
      v
[Trusted Authorization Server]
      |
      | 3. Authenticate RS introspection client
      | 4. Check token and metadata RS is allowed to view
      | 5. Return JSON active true/false, scope, iss, aud, sub...
      v
[Resource Server]
      |
      | 6. active=true? issuer/audience/client_id valid?
      | 7. Map scope -> SCOPE_* authorities
      | 8. Route/tenant/resource authorization
      v
[Controller/Service if all checks pass]
```

The AS and RS represent two distinct identities:
- **The client calling the API with a Bearer token** holds OAuth2 access token T.
- **The RS calling introspection with client credentials** is authorized by the AS to query token status.

Introspection credentials are **not** access token T, and may differ from the client secret an OAuth2 Client uses when requesting tokens at the token endpoint.

### 3.2. HTTP POST Form per RFC 7662

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.invalid
Authorization: Basic <base64-of-introspection-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-token>&token_type_hint=access_token
```

- `token` is the required body parameter.
- `token_type_hint` is only an **optional hint** to help the AS process the lookup; it does not replace token verification.
- `application/x-www-form-urlencoded` is the standard request content type.
- Introspection requests require **TLS** and RS authentication per the AS contract.
- The Basic auth example is only valid when supported by the AS; mTLS/client assertions or other methods may be used per policy.
- **Never put the token in a URL query** because proxy logs, history, traces, and referrers can record URLs.
- Base64 in Basic auth is not encryption: the entire connection must be protected with TLS, certificate validation, and hostname verification.

### 3.3. active=true Result

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "report.read report.export",
  "client_id": "reports-frontend",
  "token_type": "Bearer",
  "sub": "user-42",
  "aud": ["reports-api"],
  "iss": "https://issuer.example.invalid/",
  "iat": 1767996400,
  "exp": 1768000000
}
```

The `iat`/`exp` values illustrate Unix timestamp formatting; **they do not mean the token is valid today**. The AS must compute `active` from current state rather than returning a static response.

| Claim | Meaning | Key Point to Remember |
|---|---|---|
| `active` | Boolean indicating whether the RS may trust the token as active | Required by RFC 7662 |
| `scope` | Capabilities, typically a space-separated string | Spring maps to `SCOPE_*`, does not replace audience |
| `client_id` | OAuth client that was issued the token | Distinct from the RS's introspection client credential |
| `sub` | Subject of the token | Not necessarily an email, not unique across multiple issuers |
| `aud` | Resource Server audience the token is intended for | Must match the API's policy when required |
| `iss` | AS issuer identifier | Match against trusted issuer per agreed contract |
| `exp` | Token expiration time | AS usually uses this to compute active; RS may add checks |
| `iat` | Issued-at time | Does not grant permissions by itself |
| `token_type` | Token type, e.g., Bearer | Does not mean access to every endpoint is permitted |

**RFC 7662 only mandates the `active` field**; remaining fields depend on the AS. If the product relies on `iss`, `aud`, and `client_id` for policy, require the AS to provide the exact **claims schema**, or build equivalent trusted binding. Never silently allow tokens missing an audience.

### 3.4. active=false Result

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

This is a **protocol-level HTTP success**, yet the token is **not permitted for use**. Reasons include expiration, revocation, non-existence, or the AS not allowing this RS to inspect the token's status. To minimize information disclosure, the RFC recommends omitting reasons or other claims for inactive tokens.

**HTTP 200 does not equal an active token.** Spring Security must reject the token when `active:false`; the API typically returns 401 to the caller.

### 3.5. AS 401/403/429/5xx vs. API 401/403

| Scenario | Responding Party | Meaning |
|---|---|---|
| HTTP 200 + active=false | AS | Valid introspection query, token is inactive |
| HTTP 200 + active=true | AS | Token can proceed to RS claims and permission checks |
| HTTP 401 | AS | RS introspection credential is wrong/expired or AS rejects auth |
| HTTP 403 | AS, provider-dependent | RS introspection client lacks permission to query |
| HTTP 429/5xx/timeout | AS/network | Unable to verify token due to dependency failure |
| HTTP 401 | RS API | Caller is missing a Bearer token or presented an unacceptable one |
| HTTP 403 | RS API | Caller is authenticated but lacks permission for the endpoint |

An operational **AS 401** does not automatically translate to "the user entered a wrong password"; check secrets/client authentication between RS and AS. During an AS outage, **never** return 2xx or execute protected side effects. You may return a generic 5xx/503 per policy or security exception handling, but never fail open.

## 4. Trust Boundary Between AS and RS

### 4.1. Who Decides What?

**The AS is authoritative on:**
- Did the AS issue the token?
- Is the token within its time window and unrevoked?
- Is the token active for the authenticated RS making the query?
- Which subject, OAuth client, scopes, and audience is the token bound to?
- Is this RS permitted to call introspection?

**The RS is responsible for:**
- Did the introspection response truly come from a trusted configured AS?
- Are TLS, credentials, and AS authentication valid?
- Do the issuer and audience match the current API?
- Is the OAuth client or tenant on the business allowlist?
- Does the principal hold the required authority for the route?
- Is the subject authorized to view the specific record/tenant?

An `active:true` at the AS does not replace final checks. Especially when an AS serves multiple APIs, a token issued for `payments-api` must not be automatically accepted by `reports-api` just because the token exists and has a matching scope name.

### 4.2. Token Substitution and Confused Deputy

Example:
- Token A: `active=true`, `scope=report.read`, `aud=payments-api`.
- Token B: `active=true`, `scope=report.read`, `aud=reports-api`.

The `reports-api` RS must **reject Token A** despite the identical scope name; otherwise, a token issued for another system could be replayed against reports. This is a form of token substitution / resource confusion.

Recommended constraints:

```text
Verified by AS:
  active == true

Enforced by RS:
  iss == expectedTrustedIssuer
  aud contains "reports-api"
  client_id belongs to allowedOAuthClients (if business requires)
  authorities contains SCOPE_report.read
  subject/tenant/resource ACL grants this operation
```

If the AS omits required claims, **fail closed** and fix the AS-RS contract. Use only data from trusted provenance; never take role/issuer from `X-User` headers or caller-supplied query parameters.

### 4.3. Do Not Send Tokens to User-Specified AS Endpoints

Dangerous design:

```text
GET /api/resource?introspection_url=https://attacker.example.invalid/check
Authorization: Bearer T
```

If the RS picks the introspection endpoint from caller input, it can send the **entire access token T** and RS credentials to an attacker. That is exfiltration and potentially SSRF.

Select the AS exclusively from trusted configuration or verified tenant routing. In multi-issuer setups, **opaque tokens have no self-proving issuer**, so you cannot trust an unverified prefix or header as truth. You should also avoid probing **every AS** with the same token to see which one returns active.

### 4.4. TLS and Network Policy

- Introspection URIs must enforce HTTPS per trust policy.
- Validate the certificate chain and hostname. Never use `trustAll` or disable SSL verification.
- Store RS credentials in a secret manager/env and rotate them; never commit them.
- The AS authenticates the RS and scopes the introspection client by principle of least privilege.
- Prevent automatic redirects from the AS introspection endpoint to another host, especially where tokens or Basic headers could be forwarded.
- Enforce an egress allowlist for AS hostnames/IPs/service identities; evaluate DNS rebinding/SSRF and proxy routing risks.
- Do not expose token endpoints or AS introspection credentials for arbitrary internal apps to use.
- Configure timeouts, connection pools, concurrency limits, and quotas on the RS->AS path.
- With mTLS, use dedicated client certificates and identity binding matching the AS contract.
- Protect the access token in the request body; never log raw requests/responses containing claims.

### 4.5. client_id in the Response Is Not the RS Introspection Client ID

In the response, `client_id=reports-frontend` is the OAuth client that **received the access token from the AS**. The credential the RS uses to call the AS to **introspect** might be `reports-resource-server`. These are two distinct OAuth identities:

```text
OAuth client (reports-frontend)
  -> receives token from AS
  -> calls reports-api with Bearer token

Resource server (reports-api)
  -> uses its own introspection-client credential
  -> calls AS to ask if the token is active
```

Do not confuse the `client_id` claim with the RS's own credential, and never grant permissions by checking the RS credential instead of the subject/tenant.

## 5. Spring Security WebFlux 6.5 Integration

### 5.1. Key Classes

| Class/Interface | Role |
|---|---|
| `ServerHttpSecurity` | Reactive inbound HTTP security DSL |
| `SecurityWebFilterChain` | WebFilter chain executing authentication/authorization |
| `ReactiveOpaqueTokenIntrospector` | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `SpringReactiveOpaqueTokenIntrospector` | Standard HTTP client calling the token introspection endpoint |
| `OpaqueTokenReactiveAuthenticationManager` | Authenticates opaque bearer tokens and creates Authentication |
| `BearerTokenAuthentication` | Authentication produced after successful introspection |
| `OAuth2AuthenticatedPrincipal` | Attributes and authorities returned by the verified introspector |
| `DefaultOAuth2AuthenticatedPrincipal` | Common principal implementation, convenient for tests |
| `BadOpaqueTokenException` | Error for invalid tokens |
| `ReactiveSecurityContextHolder` | Reactor Context carrying SecurityContext in WebFlux |
| `@AuthenticationPrincipal` | Injects the authenticated principal into a controller |
| `WebTestClient` | Tests request/response flows through WebFlux |

**Do not confuse with Servlet classes:**
- WebFlux: `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `ServerHttpSecurity`.
- Servlet: `OpaqueTokenIntrospector`, `SpringOpaqueTokenIntrospector`, `HttpSecurity`.

A WebFlux controller should never call `.block()` to invoke introspection on the event loop. Spring Security's reactive filter composition already manages the publisher lifecycle.

### 5.2. Minimal Spring Boot Configuration

From Spring Boot 3.x onward, properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.invalid/oauth2/introspect
          client-id: resource-server-client
          client-secret: secret-from-secret-manager
```

This is a configuration shape sample **without real credentials**. In production, inject via environment/secret manager; never commit `client-secret` to Git. Boot creates `ReactiveOpaqueTokenIntrospector` when the required properties and beans are present; `SpringReactiveOpaqueTokenIntrospector` is the Spring Security 6.5 default implementation.

Example Java configuration snippet:

```java
@Bean
SecurityWebFilterChain chain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/reports/**")
                .hasAuthority("SCOPE_report.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
```

This is a **snippet** requiring imports/bean context and properties. Choosing `opaqueToken` authenticates via the introspection endpoint rather than locally verifying JWTs with JWKs. If the API needs local claim policies, provide a `ReactiveOpaqueTokenIntrospector` wrapper instead of modifying client parsing code.

### 5.3. SpringReactiveOpaqueTokenIntrospector Builder

Spring Security 6.5 provides a builder:

```java
ReactiveOpaqueTokenIntrospector delegate =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(introspectionClientId)
        .clientSecret(introspectionClientSecret)
        .build();
```

**Version note:** The constructor accepting three Strings is deprecated in 6.5; prefer the builder. The reactive class lives in `org.springframework.security.oauth2.server.resource.introspection`.

You can supply a custom bean or `.opaqueToken(opaque -> opaque.introspector(myIntrospector))` to override default configuration. If multiple candidates of the same type exist, disambiguate the bean explicitly; avoid mixing auto-config properties with a custom bean without knowing which one executes.

### 5.4. Mapping Scope to Authorities

If the AS returns:

```json
{"active":true,"scope":"report.read report.export"}
```

Spring Security typically maps this to:

```text
SCOPE_report.read
SCOPE_report.export
```

DSL:

```java
.pathMatchers("/api/reports/**")
    .hasAuthority("SCOPE_report.read")
```

This is a snippet of authorization rules. `SCOPE_*` proves what permissions appear in the introspected token, **not** that the issuer/audience/client ID/tenant are right. Per-record authorization rules must still be enforced by the business service.

### 5.5. Principal and Reactor Context

After authentication, a controller can receive:

```java
@GetMapping("/api/whoami")
Mono<String> whoami(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getName());
}
```

This is a snippet; the method must reside in a `@RestController` with proper imports. In other reactive code, use `ReactiveSecurityContextHolder.getContext()` instead of assuming thread-bound `ThreadLocal` state. Never return the raw token or all sensitive claims in JSON.

## 6. Timing, Revocation, Caching, and Availability

### 6.1. Introspection Is a Critical-Path Dependency

A WebFlux Resource Server may need to introspect every Bearer request, adding network RTT and load on the AS. When the AS is slow or down:
- API latency rises.
- Connection pools can saturate.
- Timeouts/concurrency limits/circuit breakers need explicit deadlines.
- Unverified tokens must **never** reach business handlers.
- Monitoring must distinguish AS 401 credential failures, `active=false`, 429/5xx, and timeouts.

Use non-blocking `WebClient` with connection/response timeouts; never invoke blocking HTTP clients on the event loop. Apply bounded retries with backoff/jitter only for transient errors if policy allows; never retry indefinitely on inactive/invalid tokens or AS credential 401s.

### 6.2. Fail-Closed, Not "Temporarily Allow Through"

Wrong:

```java
// ANTI-PATTERN example, do not implement:
return delegate.introspect(token)
    .onErrorResume(error ->
        Mono.just(previouslyAuthenticatedPrincipal));
```

When the AS fails, reusing an old principal or treating anonymous as authenticated bypasses revocation, audience, and tenant isolation. Instead, propagate the error so the protected request is **not** processed; if you want a generic HTTP 503 for AS unavailability, handle it in error mapping and observability without producing a successful Authentication.

### 6.3. Caching Introspection Results Has Trade-offs

RFC 7662 permits caching results to reduce load, **at the expense of state freshness**. If the AS revokes a token at 10:00 while the RS caches `active=true` until 10:15, the token may still be accepted during that window.

Cache design requires:
- Short TTL, never exceeding token expiry or revocation policy.
- Namespacing by trusted issuer, audience, tenant, and policy when results depend on context.
- Safe cache keys that do not expose raw tokens in logs/traces; use a properly designed hash/HMAC.
- Controlled negative caching of `active=false` without leaking token existence.
- Never caching AS 401/5xx/timeouts as "permanently invalid token" or as success.
- Invalidation/push mechanisms if near-real-time revocation is required.
- Avoiding misuse of a global `Mono.cache()` that causes user A's principal to be served to B.
- Testing expired/revoked flows and multi-node cache consistency.

**Online introspection** enables faster revocation, but caching indefinitely forfeits that advantage. Choose TTL based on business risk, not an arbitrary constant.

### 6.4. Privacy Leakage Channels

Introspection requests carry the **raw token** to the AS. Never log:
- Incoming `Authorization: Bearer ...`.
- RS->AS Basic credentials.
- Form body `token=...`.
- Access/refresh tokens and client secrets.
- Full introspection JSON containing PII.
- Raw query params and exception messages containing tokens.

The AS should return only the claims the RS needs for authorization; inactive responses should generally contain only `active:false`. Metrics should use status/error categories, normalized AS host, latency, and secret-free correlation IDs. Rate-limit token guessing/abuse and grant the introspection client only minimal query privileges.

### 6.5. Multi-Tenant / Multi-AS

If the RS serves multiple tenants across different AS instances, never:
- Choose the introspection URL from arbitrary query/`Host` inputs.
- Probe every AS sequentially with the same token.
- Trust a client-supplied `iss` prior to introspection.
- Share one global token-to-principal cache without separating issuer/tenant.
- Merge subjects from two issuers solely by `sub` or email.

You need trusted tenant resolution, fixed per-tenant AS endpoints, separate credentials, separate expected audiences/issuers, network egress policies, scoped caches, and auditing. `iss+sub` is generally a more stable key than `sub` alone when identities come from multiple issuers.

## 7. Spring Boot 3.5 WebFlux Demo: Introspection and Local Trust Policy

The app has:
- `GET /health` public.
- `GET /api/reports` requiring `SCOPE_report.read`, an active token with matching `iss`, `aud`, and `client_id`.
- `GET /api/admin` requiring `SCOPE_report.admin`.
- `BoundaryIntrospector` calling the delegate introspector and then checking expected claims.
- `@Profile("test")` in JUnit replacing the network AS with a fake delegate, while still running the WebFlux security filter.

**Intentional limitation:** the demo hostname `auth.example.invalid` has no real AS, so protected calls in normal runtime will not succeed. `/health` works offline. Tests only need fake fixtures and send no tokens over the network.

### 7.1. Initializing the Project

Create a Gradle Groovy project from [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot 3.5.x:
- Spring Reactive Web.
- Spring Security.
- OAuth2 Resource Server.
- Spring Boot Starter Test, Spring Security Test, Reactor Test.

The `dependencies` section of `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is **only the dependencies block**, not a full `build.gradle`. Keep plugins, repositories, Java toolchain, and Gradle wrapper from Initializr. Avoid adding `spring-boot-starter-web` when inbound traffic requires WebFlux, because Boot 3.x favors MVC if both starters are present.

Layout:

```text
src/main/java/demo/opaque/
  OpaqueBoundaryApplication.java
  BoundaryIntrospector.java
  IntrospectionConfig.java
  SecurityConfig.java
  ReportsController.java
src/test/java/demo/opaque/
  OpaqueBoundaryWebTests.java
  BoundaryIntrospectorTests.java
```

### 7.2. OpaqueBoundaryApplication.java

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueBoundaryApplication.class, args);
    }
}
```

### 7.3. BoundaryIntrospector.java: Checking iss/aud/client

```java
package demo.opaque;

import java.time.Duration;
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class BoundaryIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    public static final String EXPECTED_ISSUER =
        "https://issuer.example.invalid/";
    public static final String EXPECTED_AUDIENCE =
        "reports-api";
    public static final String EXPECTED_CLIENT =
        "reports-frontend";

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration timeout;

    public BoundaryIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration timeout) {
        this.delegate = Objects.requireNonNull(delegate);
        this.timeout = Objects.requireNonNull(timeout);
        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException(
                "Introspection timeout must be positive");
        }
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(
            String token) {
        return delegate.introspect(token)
            .timeout(timeout)
            .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                    "No valid introspection result")))
            .flatMap(principal -> {
                if (!EXPECTED_ISSUER.equals(
                        principal.getAttribute("iss"))
                        || !EXPECTED_CLIENT.equals(
                            principal.getAttribute("client_id"))
                        || !audienceAllowed(
                            principal.getAttribute("aud"))) {
                    return Mono.error(
                        new BadOpaqueTokenException(
                            "Token is not intended for this API"));
                }
                return Mono.just(principal);
            });
    }

    private boolean audienceAllowed(Object raw) {
        if (raw instanceof String single) {
            return EXPECTED_AUDIENCE.equals(single);
        }
        if (raw instanceof Collection<?> multiple) {
            return multiple.stream()
                .anyMatch(EXPECTED_AUDIENCE::equals);
        }
        return false;
    }
}
```

Explanation:

1. `delegate` is responsible for verifying `active` with the AS. The wrapper **never** marks a token active on its own.
2. `timeout` sets a deadline on the Mono; when exceeded, no principal is returned successfully. Production also needs connect/response timeouts, bulkheads, and circuit breakers at the network layer.
3. `iss` and `client_id` are compared strictly against the contract; `client_id` here is the OAuth client receiving the token, **not** the RS's introspection credential.
4. `aud` accepts a single audience string or a collection per provider schema; if missing or another type, it rejects by default.
5. Policy failures throw `BadOpaqueTokenException` so security infrastructure never builds a successful Authentication.
6. Do not add authorities here; scope mapping is produced by the trusted delegate.
7. The `EXPECTED_*` values are hardcoded for the demo. Production uses trusted config/allowlists and multiple clients if required by business rules.
8. With an AS that omits optional `aud`/`iss` claims, **the demo will reject all tokens**. Align the AS-RS schema or an equivalent trusted binding rather than disabling checks while debugging.

### 7.4. IntrospectionConfig.java: HTTP Delegate to AS

```java
package demo.opaque;

import java.net.URI;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    @Profile("!test")
    ReactiveOpaqueTokenIntrospector introspector() {

        String uri = System.getenv().getOrDefault(
            "INTROSPECTION_URI",
            "https://auth.example.invalid/oauth2/introspect");
        String clientId = System.getenv().getOrDefault(
            "INTROSPECTION_CLIENT_ID",
            "demo-resource-server");
        String secret = System.getenv().getOrDefault(
            "INTROSPECTION_CLIENT_SECRET",
            "non-production-placeholder");

        URI endpoint = URI.create(uri);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || !"auth.example.invalid".equalsIgnoreCase(
                    endpoint.getHost())
                || endpoint.getRawUserInfo() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException(
                "Untrusted introspection endpoint");
        }

        ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(secret)
                .build();

        return new BoundaryIntrospector(
            delegate, Duration.ofSeconds(3));
    }
}
```

This practice code reads environment variables with **non-functional demo defaults**. In real deployments, you must:
- Require real credentials from a secret manager; do not keep default secrets.
- Replace the `auth.example.invalid` hostname pin with a reviewed AS allowlist.
- Configure TLS certificate/hostname verification, egress ACLs, redirect handling, and connect/response timeouts.
- Issue dedicated credentials to the RS and rotate them appropriately.
- Align expected issuer/aud/client in `BoundaryIntrospector` with the real AS.

`@Profile("!test")` excludes the remote bean when tests run under the `test` profile; the test fixture supplies a wrapped fake introspector. Never run the `test` profile in production.

The Spring Security 6.5 builder replaces the deprecated 3-String constructor. There is no `.block()` or manual HTTP call in controllers; the delegate handles reactive HTTP.

### 7.5. SecurityConfig.java: WebFlux Bearer Auth and Route Scopes

```java
package demo.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain chain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_report.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_report.admin")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

This is an inbound Resource Server, not an OAuth2 Client handling browser login. `httpBasic` and `formLogin` are disabled to protect the API via Bearer tokens. The demo only exposes GET protected endpoints; if you add POST/PUT/PATCH/DELETE alongside browser-auto-sent credentials, evaluate CSRF per your threat model and **do not** disable CSRF indiscriminately.

`SCOPE_report.read`/`SCOPE_report.admin` are authorities; records with real tenant/ACL rules still need service/database policies. Never let users choose roles via request headers or query parameters.

### 7.6. ReportsController.java

```java
package demo.opaque;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    public record ReportView(
            String subject, String resource, String summary) {
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/reports")
    public Mono<ReportView> reports(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ReportView(
            principal.getName(),
            "reports-api",
            "Report data is protected"));
    }

    @GetMapping("/api/admin")
    public Mono<String> admin(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just("admin access for " + principal.getName());
    }
}
```

Never expose raw Bearer tokens, Basic credentials, full introspection claims, or unnecessary PII in responses. `principal.getName()` depends on the trusted principal returned; do not assume it is always an email.

### 7.7. Running the Demo

From the Gradle root:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Test health:

```bash
curl -i http://localhost:8080/health
```

Expected HTTP 200, body `ok` (headers/charset depend on framework version). Protected request without token:

```bash
curl -i http://localhost:8080/api/reports
```

Expected HTTP 401. With the `auth.example.invalid` placeholder, **no real token** will pass introspection; that is the expected behavior, not a Spring bug. Running for real requires an AS and a token with matching `active`, `iss`, `aud`, `client_id`, and scopes per the contract.

## 8. WebTestClient Integration Tests Using an Offline Fake Introspector

The tests below **do not stand up a fake HTTP AS**. Instead, `@ActiveProfiles("test")` excludes the remote bean and `@TestConfiguration` registers a fake delegate with deterministic outcomes, wrapped by the real `BoundaryIntrospector`. Goal: test the WebFlux security chain, local issuer/audience/client policy, and endpoint scope decisions.

File `src/test/java/demo/opaque/OpaqueBoundaryWebTests.java`:

```java
package demo.opaque;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(OpaqueBoundaryWebTests.FakeConfig.class)
class OpaqueBoundaryWebTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeConfig {

        @Bean
        ReactiveOpaqueTokenIntrospector introspector() {
            ReactiveOpaqueTokenIntrospector fake = token ->
                switch (token) {
                    case "valid-read" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "valid-admin" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.admin"));
                    case "no-scope" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            ""));
                    case "wrong-audience" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("payments-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "wrong-issuer" -> Mono.just(
                        principal(
                            "https://untrusted.example.invalid/",
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "wrong-client" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            "untrusted-client",
                            "report.read"));
                    case "no-audience" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            null,
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    default -> Mono.error(
                        new BadOpaqueTokenException(
                            "Inactive or unknown test token"));
                };

            return new BoundaryIntrospector(
                fake, Duration.ofSeconds(2));
        }

        private static OAuth2AuthenticatedPrincipal principal(
                String issuer, Object audience,
                String clientId, String scope) {
            var attrs = new java.util.HashMap<String, Object>();
            attrs.put("sub", "user-42");
            attrs.put("iss", issuer);
            if (audience != null) {
                attrs.put("aud", audience);
            }
            attrs.put("client_id", clientId);
            attrs.put("scope", scope);

            List<GrantedAuthority> authorities = scope.isBlank()
                ? List.of()
                : List.of(new SimpleGrantedAuthority(
                    "SCOPE_" + scope));

            return new DefaultOAuth2AuthenticatedPrincipal(
                "user-42", attrs, authorities);
        }
    }

    @Test
    void healthDoesNotRequireToken() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerIsUnauthorized() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveTokenIsUnauthorized() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("inactive"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReadTokenWorks() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("valid-read"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("user-42")
            .jsonPath("$.resource").isEqualTo("reports-api");
    }

    @Test
    void readTokenCannotUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("valid-read"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminScopeCanUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("valid-admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("admin access for user-42");
    }

    @Test
    void wrongAudienceIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-audience"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-issuer"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongClientIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-client"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingAudienceFailsClosed() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("no-audience"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeYieldsForbidden() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("no-scope"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**11 integration test methods**. Key takeaways:
- Missing/inactive token: API returns 401.
- Token with right issuer/audience/client and proper scope: 200.
- Active token with wrong issuer/aud/client or missing aud: local wrapper rejects before business logic.
- Authenticated token lacking `SCOPE_report.read`: 403.
- Fake tokens never contact a real AS; `@Profile("!test")` excludes the remote bean during tests.

**Important:** The fake introspector creates `DefaultOAuth2AuthenticatedPrincipal` and authorities directly to simulate verified results. It does **not** prove HTTP `active:false` is handled by the AS parser, does not verify Basic credentials/TLS, and is not a valid IdP. Never copy the fake bean into production runtime.

## 9. Unit Tests Verifying Fail-Closed BoundaryIntrospector

File `src/test/java/demo/opaque/BoundaryIntrospectorTests.java`:

```java
package demo.opaque;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertSame;

class BoundaryIntrospectorTests {

    private OAuth2AuthenticatedPrincipal principal(
            String issuer, Object audience, String client) {
        var attrs = new java.util.HashMap<String, Object>();
        attrs.put("sub", "subject-7");
        attrs.put("iss", issuer);
        if (audience != null) {
            attrs.put("aud", audience);
        }
        attrs.put("client_id", client);

        List<GrantedAuthority> authorities = List.of(
            new SimpleGrantedAuthority("SCOPE_report.read"));
        return new DefaultOAuth2AuthenticatedPrincipal(
            "subject-7", attrs, authorities);
    }

    private BoundaryIntrospector guard(
            ReactiveOpaqueTokenIntrospector delegate) {
        return new BoundaryIntrospector(
            delegate, Duration.ofSeconds(2));
    }

    @Test
    void acceptsTrustedPrincipalWithoutPrivilegeChanges() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            List.of("reports-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .assertNext(actual -> assertSame(p, actual))
            .verifyComplete();
    }

    @Test
    void rejectsWrongAudience() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            List.of("payments-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void rejectsWrongIssuer() {
        var p = principal(
            "https://other.example.invalid/",
            List.of("reports-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void rejectsMissingAudience() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            null,
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void inactiveDelegateErrorIsNotConvertedToSuccess() {
        ReactiveOpaqueTokenIntrospector delegate = token ->
            Mono.error(new BadOpaqueTokenException("inactive"));

        StepVerifier.create(guard(delegate)
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void unavailableAsErrorIsNotConvertedToSuccess() {
        ReactiveOpaqueTokenIntrospector delegate = token ->
            Mono.error(new OAuth2IntrospectionException(
                "AS unavailable"));

        StepVerifier.create(guard(delegate)
                .introspect("fake-token"))
            .expectError(OAuth2IntrospectionException.class)
            .verify();
    }
}
```

**6 StepVerifier tests**. They verify that trusted principals are not modified to elevate privileges, wrong/missing audience/issuer are rejected, and delegate errors are never converted into authenticated success.

You can add a `Mono.empty()` unit test to verify `switchIfEmpty` rejects missing principal results, plus a virtual-time test for the deadline. Avoid real wall-clock timers in short timeout tests where high CI load causes flakiness.

### 9.1. Running the Tests

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

A total of **17 test methods** are defined (11 WebTestClient + 6 unit). **This is a static inspection of the code**, without confirming a Gradle run. On other versions, check the actual APIs, statuses, and exceptions; never "fix failures" by removing audience checks or allowing `active:false`.

## 10. Additional HTTP Integration Tests Needed with a Mock AS

The fake principal tests above check local policy, **not RFC 7662 over HTTP**. In staging/CI, use a trusted mock HTTP AS (WireMock or MockWebServer) and point a test introspector instance to the controlled test address. Never use production tokens/secrets.

Important cases:

1. AS receives **HTTP POST**, not GET.
2. Form body contains `token` (and `token_type_hint` if sent by the client); never put the token in the URL.
3. RS uses the exact client authentication per AS contract, e.g., Basic/mTLS.
4. AS returns `200 {"active":false}` -> RS does not authenticate.
5. AS returns `200 {"active":true,...}` with expected issuer/aud/client/scopes -> RS may proceed.
6. AS returns active=true but wrong audience -> wrapper rejects.
7. AS 401 due to bad introspection client credentials -> denied, operational error metric distinct from inactive token.
8. AS 429, 500, timeout, malformed JSON, missing active -> never issue an authenticated principal.
9. AS redirects to another host -> never leak Bearer token or Basic credentials across redirects.
10. Token revoked right after a prior request passed -> verify cache TTL/invalidation.
11. TLS certificate/hostname validation and trusted DNS/network egress policy.
12. Verify the AS does not return user/token info beyond the RS introspection client's authorization.

A `curl` request to understand the protocol (using **test credentials only** in a secret-protected environment):

```bash
curl --request POST \
  --url "https://auth.example.invalid/oauth2/introspect" \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$TEST_ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token"
```

This is **illustrative**: the `example.invalid` domain will not work. With real tokens/credentials, avoid pasting them into terminal history, tickets, CI logs, or URLs. HTTP tests can run against a mock server without Internet access or a real AS.

## 11. Troubleshooting: AS, RS, and Security Chain States

| Symptom | Possible Cause | Resolution |
|---|---|---|
| AS 200 but API 401 | AS returned active=false or local claim check failed | Check active and issuer/aud/client policy; never log raw tokens |
| AS returns 401, multiple APIs fail together | **RS->AS** credentials wrong/expired | Check introspection client auth/secret rotation |
| API 403 despite active token | Missing `SCOPE_*`/tenant ACL | Inspect scope mapping and authorization rules |
| AS outage causes API 5xx | Network introspection dependency | Timeouts/bulkhead/monitoring, fail closed |
| API still returns 200 during AS outage | Overly stale cache or fallback allow | Remove fail-open behavior, review TTL/circuit breaker |
| Missing audience yet token active | AS omits optional aud claim | Agree on claims schema or another binding; never auto-allow |
| JWT token introspected successfully | OpaqueToken mode is the validation strategy | Can be intentional when revocation is needed |
| Correct AS host but TLS disabled | Unsafe trust configuration | Enable hostname/certificate verification |
| RS sends token to user-chosen AS | SSRF/token exfiltration | Trusted endpoint allowlist, never arbitrary URLs |
| Multi-tenant accepts another tenant's token | Wrong routing/cache/issuer/audience | Trusted tenant resolution and namespace policy |
| `.block()` in ReactiveOpaqueTokenIntrospector | Blocking event loop | Use non-blocking Reactor/WebClient |
| `/health` 200 while `/api/reports` fails | Public health vs. unavailable AS | Separate readiness/AS metrics |
| Scope auto-mapped to role ADMIN | Custom converter trusts arbitrary claims | Map only validated trusted claims |
| Secret in `application.yml` committed to Git | Exposed credentials | Secret manager/env and rotation |
| Fake tests pass while AS returns bad JSON | HTTP protocol/delegate untested | Mock AS HTTP tests and contract checks |
| Caching delays revocation | TTL too long | Shorten TTL/add invalidation and test |
| AS Basic credentials in logs | Logger/interceptor logs headers | Redaction in app, proxy, APM |
| RS overloaded when AS is slow | Missing deadlines/concurrency limits | Timeouts, bulkheads, quotas, backpressure |
| Token active but wrong `client_id` | Token issued for another app | Enforce client allowlist per contract |
| Subjects from multiple issuers collided | Keying only by `sub` or email | Key by issuer + subject and tenant |

### 11.1. Investigation Workflow

1. Confirm Spring **WebFlux inbound** and the right `ReactiveOpaqueTokenIntrospector` class, not its Servlet counterpart.
2. Check missing/malformed Bearer headers first without logging tokens.
3. Verify trusted introspection endpoint, TLS, credentials, and AS entitlement for the RS.
4. Inspect AS HTTP status separately from `active` content; avoid logging full JSON.
5. Check missing/invalid `iss`, `aud`, `client_id` against the data contract.
6. Check scope-to-authority mapping and endpoint policies; distinguish API 401 vs. 403.
7. An unavailable AS must never produce a successful principal or execute business side effects.
8. If caching, check TTL, issuer namespace, token revocation, and invalidation.
9. Check multi-node setup, proxies, egress DNS/IP, rate limiting, and concurrency.
10. Cross-check with HTTP integration tests, not just fake-principal tests.

## 12. Exercises with Answers

### Exercise 1 — Does HTTP 200 Mean the Token Is Active?

The AS returns HTTP 200 with `{"active":false}`. Should the user be granted access?

**Answer:** No. The HTTP status succeeded for the introspection request, while the body states the token is inactive. The RS rejects authentication; the API typically returns 401.

### Exercise 2 — When the AS Returns 401, Whose Fault Is It?

The AS introspection endpoint rejects Basic credentials.

**Answer:** Those are the credentials the RS uses to query the AS, which does not imply the end user entered a wrong password. Fix the introspection client permissions/secret/mTLS rather than letting tokens through.

### Exercise 3 — active=true but Audience Is payments-api

The `reports-api` RS receives an active token with `aud=payments-api` and scope `report.read`.

**Answer:** Reject it because the audience does not target `reports-api`. Scope does not replace resource binding; prevent token substitution.

### Exercise 4 — Must JWTs Always Use a Local Decoder?

**Answer:** No. A JWT can be introspected if online revocation status is needed or the AS contract requires it. "Opaque" in the DSL refers to the introspection method, not prohibiting JWT formatting.

### Exercise 5 — Distinguish RS Credentials from OAuth client_id

**Answer:** RS->AS credentials authorize querying introspection; the `client_id` claim in token metadata identifies the OAuth client issued the access token. They are two separate identities with different permissions and rotation.

### Exercise 6 — Should Previously Passed Tokens Be Trusted During an AS Outage?

**Answer:** Not under the demo's fail-closed policy. Cached active state creates a revocation window; without a valid result or an approved cache policy, grant no new access.

### Exercise 7 — Why POST Body Instead of GET Query?

**Answer:** Form POST is the RFC 7662 protocol and keeps tokens out of URLs that leak into logs/history. Still enforce TLS and protect bodies/Authorization headers from logging.

### Exercise 8 — Why Not Auto-Map Email to Admin?

**Answer:** Unverified email/username/role claims under policy cannot grant privileges on their own. Map only trusted claims, matching issuer/tenant, and evaluate business authorization.

### Exercise 9 — What Happens If active Is Cached Too Long?

**Answer:** Revoked tokens can still be accepted until TTL expires, delaying revocation effect. Match TTL to expiry/risk; invalidation may be required.

### Exercise 10 — What to Do If Issuer/Audience Is Missing?

**Answer:** If the RS contract requires those claims, fail closed and fix the schema or verification mechanism. Never allow "any audience" simply because the AS returned `active=true`.

### Exercise 11 — Should Multi-AS Probe Both Endpoints with the Same Token?

**Answer:** Not by default. An opaque token is a secret, and sending it to an untrusted AS leaks it. Route using trusted tenant context and dedicated AS definitions.

### Exercise 12 — Do @TestConfiguration Tests Prove Basic/TLS?

**Answer:** No. The fake introspector returns a principal directly and only tests WebFlux and local claims policy. You need HTTP mock AS / real provider tests for POST, TLS, credentials, and `active` JSON parsing.

### Exercise 13 — How Do 401 and 403 Differ?

**Answer:** API 401 means unauthenticated or invalid authentication; 403 means a principal exists but is unauthorized for the endpoint. Meanwhile, an AS 401 can mean the RS's own introspection client credentials failed.

### Exercise 14 — Health 200 While API Fails?

**Answer:** Public health only proves the process/route is running. Protected APIs also depend on the AS, tokens, audiences, scopes, and policies; design separate readiness/AS monitoring.

### Exercise 15 — Token Appears in AS Logs?

**Answer:** Stop logging raw tokens, redact logs/traces, revoke/rotate as needed, assess impact, and tighten permissions/TTL. Never paste tokens into tickets or chat.

### Exercise 16 — Should Every RS Share One Introspection Client Secret?

**Answer:** Preferably not if the AS supports separate credentials. Issue per-RS credentials for least privilege, easier rotation/revocation, and auditing so one leaked credential does not compromise every service.

## 13. Production Deployment Checklist

- [ ] Define trusted AS introspection URIs and tenant routing in server configuration.
- [ ] Keep HTTPS/TLS certificate and hostname verification enabled at all times.
- [ ] Use dedicated RS introspection credentials stored in a secret manager with rotation.
- [ ] Send RFC 7662 form POST with the token in the body, never in URL queries.
- [ ] Ensure the AS authenticates the RS and returns only needed claims; inactive responses leak no reasons.
- [ ] `ReactiveOpaqueTokenIntrospector` verifies active status and never reads claims from caller headers.
- [ ] Check `iss`/`aud`/`client_id` per contract; fail closed on missing claims.
- [ ] Ensure accurate scope-to-authority mapping while preserving route/tenant/row ACLs.
- [ ] Do not confuse AS HTTP 401 with API 401, or `active:true` with full authorization.
- [ ] Never use unverified email/username claims to grant admin privileges.
- [ ] Configure clear timeouts and concurrency limits; never block the Reactor event loop.
- [ ] Ensure AS outage/429/5xx/timeout never produces an authenticated principal.
- [ ] Bound caching with TTL/invalidation/issuer namespace per revocation policy.
- [ ] Never probe arbitrary endpoints across multiple AS instances with tokens.
- [ ] Enforce egress allowlists, DNS/IP restrictions, and SSRF/redirect protections.
- [ ] Ensure logs/APM/traces/correlation never leak tokens, Basic credentials, or PII.
- [ ] Protect APIs with rate limiting, abuse detection, HTTPS, and generic error handling.
- [ ] Cover inactive, wrong issuer/audience/client, and missing scopes in `WebTestClient` tests.
- [ ] Verify AS POST, active true/false, 401/5xx, and TLS in HTTP integration tests.
- [ ] Maintain runbooks for leaked tokens/client secrets and AS outages.

## 14. Final Summary

```text
Client -> Authorization: Bearer T -> WebFlux Resource Server
   |
   v
ReactiveOpaqueTokenIntrospector
   |
   +-- HTTPS POST T to trusted AS
   |   authenticated with RS introspection client credentials
   |
   +-- AS returns active true/false + claims
   |
   +-- active=false -> deny
   +-- timeout/AS error -> fail closed
   +-- active=true ->
          check trusted issuer
          check audience reports-api
          check allowed client_id
          map scope -> SCOPE_*
          route + resource/tenant authorization
                   |
                   +-- pass -> business handler
                   +-- fail authn -> 401
                   +-- insufficient scope -> 403

TRUST BOUNDARY:
  AS is the authoritative source of metadata/token state
  RS controls policy for its own resources
  TLS + credentials + claim checks + authorization
  caching/timeouts/network logs must never open up access
```

**Key message:** Introspection tells you whether a trusted Authorization Server recognizes the token as **active**, but the Resource Server decides whether that token may be **used on a specific resource and operation**. Sound design verifies audience/issuer/client and scopes, secures RS->AS with TLS and credentials, and grants no access when a token cannot be verified.

## 15. References

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html)
- [Spring Security — BadOpaqueTokenException API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — OAuth2 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
