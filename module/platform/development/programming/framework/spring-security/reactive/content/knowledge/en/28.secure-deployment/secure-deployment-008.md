# Failing Safely When JWK, Introspection, or Authorization Services Are Unavailable (Spring Security Reactive)

## 1. Objectives and Context

A Resource Server built with **Spring Boot 3.x, Spring WebFlux, and Spring Security 6.x** typically relies on one or more external security services. When those services suffer timeouts, DNS/TLS errors, HTTP 429/5xx, malformed responses, or maintenance windows, the application must still preserve its access boundaries.

Three common dependencies:

- **JWK Set (JWKS)**: holds public keys from the Identity Provider (IdP) to verify JSON Web Token (JWT) signatures. If the valid key is already cached, a JWT can sometimes be verified **locally** even while the IdP is offline.
- **Token introspection**: the Resource Server asks the IdP whether a token has `active=true`. Without a trusted reply, there is no proof the token remains valid.
- **Authorization service / PDP (Policy Decision Point)**: after authentication, the app asks "may subject S perform action A on resource R?" Without a valid **permit** decision, the protected action must not execute.

Learning outcomes: distinguish **invalid token**, **forbidden**, and **dependency unavailable**; enforce **fail closed**; configure JWT/opaque tokens; build a `ReactiveAuthorizationManager` that denies on PDP failure; understand limits of caching, retries, and circuit breakers; design tests alongside metrics/alerts.

**Security invariant:** never grant access by skipping signature verification, skipping token expiration checks, defaulting tokens to `active=true`, or reusing a stale permit that can no longer be verified. Fail closed means never performing sensitive actions without sufficient proof—it does not mean every technical error must return HTTP 403.

## 2. Authentication and Authorization Must Remain Separate

```text
HTTP request arrives at Spring WebFlux
  |
  +-- Truly public route? ----------> Apply declared public policy
  |
  +-- Protected route
        |
        +-- Authentication: JWT or opaque token
        |     |
        |     +-- Token verified ------------> Trusted Authentication
        |     +-- Invalid / unverifiable ----> DO NOT grant access
        |
        +-- Authorization: local rules and/or PDP
              |
              +-- Valid permit decision -----> Allowed to proceed
              +-- Deny / error / no result --> DO NOT grant access
```

A valid JWT only proves the token was issued under active authentication rules; it **does not automatically permit** creating orders, deleting records, reading another tenant's resources, or executing transactions. Conversely, a PDP outage does not suddenly make a token "invalid." Both stages should have distinct error codes and telemetry.

| Situation | Security Conclusion | Typical HTTP Status |
| --- | --- | --- |
| Missing token, bad signature, expired, wrong issuer/audience; introspection returns `active=false` | Not validly authenticated | `401 Unauthorized` |
| Valid Authentication but missing scope/role or PDP returns deny | Insufficient authority | `403 Forbidden` |
| Cannot fetch required keys; introspection times out; PDP unreachable | **Insufficient proof to grant access** | May intentionally return `503 Service Unavailable`; framework defaults/error handling may yield another code |
| Request hits an explicitly approved public route | No authentication required per that route's policy | Normal handling |

Never claim Spring Security converts every network error into 503 by default. The status code depends on exceptions, filters, entry point/access-denied handlers/gateways, and framework version. **Never handle 401/403/503 errors by opening up access.**

## 3. When the JWK Set Is Unavailable: Evaluate Keys and Tokens Separately

### 3.1 JWKS Does Not Need to Be Called for Every JWT

With JWT configuration, Spring Security uses public keys fetched from the IdP's JWK Set to verify signatures, then validates `iss`, `exp`, `nbf`, `aud`, and allowed algorithms per configuration. Scopes are typically mapped to `SCOPE_...` authorities.

When JWKS is offline:

1. **JWT signed by cached key K1, and K1 is still trusted**: signature and claims can still be verified locally. Proceed only if all token constraints and authorization checks pass.
2. **JWT carries `kid=K2` not present in cache**: cannot prove signature with a trusted key, so reject; record JWKS fetch failure or cache miss.
3. **JWT uses K1 but signature is invalid / expired / wrong audience**: reject even when the key is cached.
4. **Cache holds no keys or only revoked keys**: never authenticate tokens just because the key service is down.

**Distinguish "JWKS unreachable" from "a valid matching public key is still present in a valid cache."** JWKS caches have TTL, refresh, rotation, and revocation semantics per implementation; never choose "stale forever" for availability, as a revoked public key could remain trusted indefinitely. There is no single safe TTL for every system.

### 3.2 Configuring a JWT Resource Server for WebFlux

Requires `spring-boot-starter-webflux` and `spring-boot-starter-oauth2-resource-server`. Example **`application-jwt.yml`** (activate the `jwt` profile when running; URLs are illustrative):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/demo
          jwk-set-uri: https://idp.example.com/realms/demo/jwks.json
          audiences:
            - payments-api
```

`issuer-uri` preserves `iss` verification, while `jwk-set-uri` pins the key-set endpoint so startup does not need to discover the JWKS URL from metadata. Spring Security reactive auto-configuration defers initialization/discovery appropriately in many setups; if building a custom `ReactiveJwtDecoder`, verify whether bean creation triggers immediate network calls at startup. **An application starting successfully does not guarantee the first JWT request will succeed if JWKS is down.**

Never:

- Accept a JWT without verifying its signature, or trust arbitrary algorithms like `alg=none`.
- Trust a `jku` URL supplied by an untrusted token header instead of the configured trusted JWK URI.
- Skip `iss`, `aud`, token expiration, or key rotation checks just to reduce errors.
- Log tokens/secrets/private keys while diagnosing incidents.
- Treat a token as authenticated data merely because its Base64 payload parses.

If JWTs require near-real-time revocation, design an appropriate revocation mechanism upfront (e.g., introspection, short token lifetimes, or managed revocation); **a valid JWT signature alone does not tell you whether the token was just revoked at the IdP**.

### 3.3 Key Rotation During an Outage

Example: the IdP rotates from K1 to K2. Requests carrying unexpired K1 tokens may still be verified using cached K1 if policy permits. Requests carrying K2 tokens must be rejected until K2 is fetched; once the JWKS endpoint recovers, the decoder should refresh the key set and succeed on subsequent requests. Also test emergency K1 revocation and allowed stale-cache windows. Never "guess" a key from the token or skip verification.

## 4. Introspection Unavailable: "Unknown" Is Not "Active"

Opaque access tokens must normally be verified by the Resource Server via `ReactiveOpaqueTokenIntrospector` and the introspection endpoint. When a valid response has `active=true`, build `Authentication` and authorities from verified attributes. If `active=false`, the token is no longer valid.

Example **`application-opaque.yml`**, used only when choosing introspection (separate from the JWT config above):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: "REPLACE_WITH_RUNTIME_CLIENT_ID"
          client-secret: "REPLACE_WITH_SECRET_MANAGER_VALUE"
```

The two values above are **placeholders only**; never store real client secrets in source control. In production, use environment variables/secret managers and approved credential injection. HTTPS must verify the IdP's certificate and hostname.

| Introspection Response | Interpretation | Handling |
| --- | --- | --- |
| `active=true`, valid schema and required attributes | Token verified | May proceed to authorization |
| `active=false` | Invalid / possibly revoked | Deny authentication, typically 401 |
| HTTP 401/403 from introspection endpoint | **Resource server's** own credentials to IdP may be wrong | Deny, raise operational alert; do not assume the user's token is at fault |
| Timeout/DNS/TLS/HTTP 429 or 5xx | Cannot tell if token is still active | Deny, classify as `dependency_unavailable` |
| HTTP 200 but JSON lacks `active`, is empty, or invalid schema | Response provides no valid proof | Deny and log protocol error |

Code illustrating how to **bound execution time** when the project already has a trusted `ReactiveOpaqueTokenIntrospector`:

```java
import java.time.Duration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

// Illustrative method only, not a standalone runnable Java class.
ReactiveOpaqueTokenIntrospector withDeadline(
        ReactiveOpaqueTokenIntrospector delegate) {
    return token -> delegate.introspect(token)
            .timeout(Duration.ofMillis(500));
}
```

The wrapper emits a principal only if the underlying introspector completes authentication successfully. Timeouts produce an error and **must never** be turned into a default `OAuth2AuthenticatedPrincipal`. Also configure appropriate connect/response timeouts on the HTTP client rather than relying solely on `Mono.timeout`; 500 ms is illustrative and must match real SLOs.

Caching warning: a **positive introspection cache** can keep a token `active=true` after it was revoked or permissions changed. Cache only if the design explicitly allows revocation lag, with a bounded TTL tied to token expiry, complete context in cache keys, and an invalidation plan. If near-real-time active verification is required, **never use stale cached results as a fallback when the IdP is down**.

## 5. PDP (Authorization Service) Unavailable: Without Permit, Do Not Execute

When an endpoint relies on dynamic authorization from an external policy service, the proper flow is:

1. Spring Security validates the token and establishes a trusted identity.
2. The API calls the PDP with **subject + action + resource + required tenant/context** over a trusted channel.
3. Only a valid `permit=true` matching the request grants access; `permit=false` denies.
4. If the PDP times out/5xx, returns invalid/missing `permit` JSON, or yields no decision, the app **does not execute the action**.

**Never use** a rule like "if PDP fails, any authenticated user is allowed." Being logged in does not grant permission to read another tenant's data, execute transactions, or modify someone else's privileges.

### 5.1 Spring Security WebFlux Example with `ReactiveAuthorizationManager`

The following Java 17+ snippet is **a configuration class** for a Boot 3.x/Spring Security 6.x app; it does not run standalone. It requires `@SpringBootApplication`, JWT config from section 3, and a matching PDP API. File `src/main/java/demo/ApiSecurityConfig.java`:

```java
package demo;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthorizationManager<AuthorizationContext> policyManager) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/sensitive/**").access(policyManager)
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    ReactiveAuthorizationManager<AuthorizationContext> policyManager(
            WebClient.Builder builder) {
        WebClient pdp = builder
                .baseUrl("https://pdp.internal.example")
                .build();

        return (authentication, context) -> authentication
                .flatMap(auth -> pdp.post()
                        .uri("/v1/decisions")
                        .bodyValue(new PdpRequest(
                                auth.getName(),
                                "read:sensitive",
                                context.getExchange().getRequest()
                                        .getPath().value()))
                        .retrieve()
                        .bodyToMono(PdpResponse.class)
                        .timeout(Duration.ofMillis(300))
                        .map(reply -> new AuthorizationDecision(
                                Boolean.TRUE.equals(reply.permit())))
                        .defaultIfEmpty(new AuthorizationDecision(false))
                        .onErrorReturn(new AuthorizationDecision(false)))
                .defaultIfEmpty(new AuthorizationDecision(false));
    }

    public record PdpRequest(String subject, String action, String resource) {}
    public record PdpResponse(Boolean permit) {}
}
```

Assumed PDP contract: HTTP `POST /v1/decisions` accepts JSON with `subject`, `action`, `resource`; returns JSON `{"permit":true}` or `{"permit":false}`. The URL and action are illustrative; in a real app, mTLS/service credentials, tenant, HTTP method, object ID, policy version, and business fields must be authenticated, bound, and sent with accurate context—avoiding over-broad access from hardcoding one action across multiple operations.

**Why this code fails closed:**

- `Boolean.TRUE.equals(...)` allows only exact `true`; `null` or `false` denies.
- `defaultIfEmpty(new AuthorizationDecision(false))` blocks empty replies or an empty authentication stream.
- `onErrorReturn(new AuthorizationDecision(false))` catches timeouts, connection failures, 4xx/5xx, and JSON parse errors; it **never** falls back to granted.
- `anyExchange().denyAll()` denies undeclared routes by default. `/healthz` illustrates an intentional public route; each app must define its own endpoints.
- `WebClient`/`Mono` stays reactive and never calls `.block()` on the event loop.

In this demo, an authenticated request hitting a failing PDP typically returns **403** due to `AuthorizationDecision(false)`. That **does not mean** a PDP outage is "user lacks permission": record dedicated technical metrics/logs. If the product needs 503 to signal a dependency outage, design dedicated error handling and HTTP responses at the appropriate layer, testing rigorously so **zero business logic executes** before sending the response. Never turn deny into allow just to change an HTTP status code.

If the Resource Server chooses opaque tokens instead of JWTs, the matching `SecurityWebFilterChain` branch is:

```java
// Replace the oauth2ResourceServer(...jwt...) branch in the example above:
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

And apply the `opaquetoken` config from section 4. Never assume Spring picks the right mode automatically when both `jwt` and `opaquetoken` appear in YAML; design an explicit authentication path.

### 5.2 What to Add When Using a Real PDP

- **Protect API–PDP communication**: HTTPS/mTLS, service identity, endpoint verification; never trust an endpoint URL supplied by user requests.
- **Bind policy inputs**: authority, tenant, resource, action, subject, and policy version must match the current request; never reuse a permit decision from another request.
- **Prevent replay or mismatched responses** if the PDP protocol requires it: correlation/nonce and contract validation.
- **Enforce authorization at the right point**: when policy depends on database state, prevent time-of-check/time-of-use races and guard sensitive operations at the service/repository layer as needed.
- **Telemetry**: add metrics and logs distinguishing real PDP denials from PDP unavailability; never log bearer tokens, client secrets, or full payloads containing personal data.
- **Dedicated CSRF for write operations**: `/sensitive/**` here uses GET; if POST/PUT exist and the app uses browser cookies/sessions, CSRF must still be enforced per the authentication model. Never disable CSRF app-wide just to test a PDP.

## 6. Timeouts, Retries, Circuit Breakers, Bulkheads, and Caching

### 6.1 Reactive Does Not Mean Automatically Safe Timeouts

Use `WebClient`, `Mono.timeout(...)`, or HTTP client settings to keep dependency calls from hanging indefinitely. Bound connect, TLS, response, and pool acquisition times; choose deadlines aligned with end-to-end SLOs. The 300/500 ms numbers here only illustrate syntax, not universal defaults for every infrastructure.

Retries must have a **total budget**, capped attempts, backoff/jitter, and error classification: certain timeouts/429/5xx may be retried if endpoint semantics permit; **never retry** invalid JWT signatures, `active=false`, policy `deny`, or bad credentials. Retry a `POST` to a PDP/introspection endpoint only when the operation is truly idempotent or confirmed safe by the provider. Avoid multi-layer retry amplification across gateway/client/API/IdP during outages.

An **open** circuit breaker should shed load by failing dependency calls fast; never convert open → permit. Bulkheads/concurrency limits keep a slow PDP from starving the entire Reactor event loop. Never invoke blocking SDKs or `Thread.sleep()` on the event loop; if a dependency is blocking, isolate it on a bounded dedicated scheduler and load-test it.

### 6.2 Do Not Lump All Caches Together

| Cache | What Can Survive During Dependency Outage? | Main Risks |
| --- | --- | --- |
| **JWKS cache** | Signature verification for tokens using already-known trusted keys | Key rotation/revocation, overly long TTL |
| **Positive introspection cache** | Reusing previously verified active status, only if policy allows | Token already revoked or permissions changed before TTL expires |
| **PDP permit cache** | Reusing decisions for the exact same subject/action/resource, only per approved contract | Stale privileges, cross-tenant leakage, mutated resource, incomplete cache key |
| **PDP deny cache** | Can shed load while permissions remain unchanged | Denying users who were subsequently granted valid access |

Never use `last known permit` indefinitely, never cache tokens without age limits, and never reuse a permit response for resource A to grant resource B. If special availability guarantees are needed, require an approved design covering risk/TTL/invalidation; fail-open by default is a vulnerability.

## 7. Anti-Patterns to Eliminate

**Wrong: interpreting an outage as permission.**

```java
// Dangerous illustration: requestPermissionFromPdp returns Mono<Boolean>
return requestPermissionFromPdp()
        .onErrorReturn(true);
```

**Right for access decisions: only a valid PDP grants permission.**

```java
// Illustrative method, does not run standalone
return requestPermissionFromPdp()
        .timeout(java.time.Duration.ofMillis(300))
        .onErrorReturn(false)
        .defaultIfEmpty(false);
```

For better operations, pair fail-closed behavior with distinct error classification (timeout/5xx/parse/denied) instead of lumping everything into "user unauthorized" on dashboards.

Other mistakes:

- Disabling JWT/CSRF checks or enabling `anyExchange().permitAll()` in production during an IdP outage.
- Accepting a JWT just because it parses, without a trusted verification key.
- Synthesizing a mock principal with default roles or treating unrejected tokens as active when introspection fails.
- Assuming a cached key K1 means any JWT with any `kid` is valid.
- Logging bearer tokens, full JWTs, introspection secrets, or raw policy payloads for debugging.
- Caching PDP responses without keying on subject, tenant, action, resource, and policy version.
- Infinite retries, blocking the event loop, or setting timeouts so high requests hang without deadlines.
- Skipping authorization checks in internal services merely because a gateway already authenticated the request.

## 8. Testing Dependency Failures and Security Invariants

Use stubbed/mocked IdP, JWKS, and PDP services, block network traffic, or inject latency. Expectations below must be verified on **HTTP responses, metrics, and side effects**, not solely via unit tests of the policy class.

| Test Condition | Expectation |
| --- | --- |
| Valid K1-signed JWT, K1 cached, then JWKS offline | May authenticate if cache/key remain trusted; all claims/permissions still checked |
| JWT using uncached K2 while JWKS offline | Authentication rejected, no business logic executed |
| Invalid JWT signature, expired, or wrong issuer/audience | Rejected even while JWKS is online |
| Introspection returns `active=false` | Authentication rejected, typically 401 |
| Introspection timeout/429/5xx, TLS error, JSON missing `active` | Rejected; dependency error recorded, never faked active |
| PDP `permit=true` for matching context | Only policy-matching requests execute |
| PDP `permit=false` | Business logic blocked, typically 403 |
| PDP timeout/500/204/JSON missing permit | Blocked, outage metric emitted, HTTP status matches contract |
| PDP returns permit for a different subject/resource | Never treated as a valid permit |
| Dependency recovers, keys rotate, policy changes | Only current tokens and decisions take effect; no lingering bypass |
| Stress test under slow PDP/IdP | Deadlines, bounded retries, breakers/bulkheads protect resources |
| Defined public endpoints | Remain within public scope; protected endpoints never accidentally open |

**Especially for state-mutating operations**, inspect the database, outbox, broker, payment gateway, and downstream systems: zero side effects may occur when authentication/authorization denies. If business requests are retried, use dedicated idempotency keys; retries must never duplicate transactions.

A contract-style test scenario:

```text
Given:
  JWT token is validly authenticated
  GET /sensitive/orders/42 must consult the PDP
  PDP does not reply within the deadline

When:
  Send request to the WebFlux Resource Server

Then:
  No sensitive data returned and no privileged action executed
  Telemetry distinguishes "pdp_unavailable" from "pdp_denied"
  No Authorization header, token, or secret leaked in logs
  HTTP status matches tested policy (e.g., 403 on fallback deny)
```

This is a test scenario, **not output automatically generated by Spring Security**.

## 9. Observability and Operational Runbooks

Metrics to track:

- `jwks_fetch_failure`, `unknown_kid`, JWK cache age, and failed token verifications grouped by cause; never put raw tokens into metric labels.
- Introspection latency, timeouts, 429s, 5xxs, Resource Server credential auth failures, and `active=false` rate.
- PDP `permit/deny/unavailable` counts, latency, timeouts, open breakers, fallback denials, and queued requests.
- HTTP 401/403/503 rates, distinguishing **token_invalid**, **access_denied**, and **security_dependency_unavailable**.
- SLOs and outage durations per dependency to tune timeouts/retries sensibly.

In Reactor/WebFlux, one request can hop across threads, so use correlation IDs/tracing to stitch events rather than relying solely on thread names. Logs need redaction, tight access controls, and retention; never record full JWTs, bearer tokens, client secrets, PINs, or unnecessary PII. Keep metric labels low-cardinality; never attach subjects or arbitrary ID-bearing URLs to time series.

**Incident runbook:**

1. Identify the exact dependency and failure mode: DNS/TLS, network, 429/5xx, credentials, JWKS rotation, cache miss, or policy service timeout.
2. Confirm protected routes still deny without proof; inspect errors/metrics, never enable `permitAll` to suppress errors.
3. Bound retries, check breakers, pools, latency, and traffic bursts; keep `liveness` independent if designed that way to avoid restart loops.
4. Fix network, secrets, issuer/JWKS endpoints, key rotation, or PDP; never paste secrets into chat/runbook logs.
5. After recovery, test valid/invalid tokens, policy allow/deny, and timeouts; verify cache refresh and zero lingering bypasses.
6. Document root cause, requests rejected due to outage, user impact, and improvements to SLOs, alerts, TTLs, timeouts, and dependency blast radius.

Readiness probes should reflect serving capability appropriate to the architecture, while weighing the risk of **dropping the entire cluster from the load balancer** when a shared IdP/PDP loses connectivity. Liveness should not automatically fail solely because an IdP is offline.

## 10. Production Readiness Checklist

- [ ] Every sensitive endpoint requires authentication and authorization; public routes exist only where design permits.
- [ ] JWT verifies signatures, key source, `iss`, `aud`, and `exp/nbf`; JWKS caching/rotation/revocation follow defined policy.
- [ ] Opaque tokens authenticate only on successful introspection with valid payload data.
- [ ] PDP grants access only on `permit=true` bound to the exact subject/action/resource.
- [ ] Timeouts, retries, circuit breakers, and HTTP clients are bounded; outages never turn into allow.
- [ ] Permit/active caches, if present, have approved TTLs, cache keys, and revocation SLAs.
- [ ] 401/403/503 status codes are tested under real config; telemetry separates invalid/deny/outage.
- [ ] Zero side effects occur when authorization fails; business retries use idempotency.
- [ ] Secrets and tokens never appear in responses/logs/metrics; IdP/PDP connections are secured.
- [ ] Fault-injection tests, alerts/dashboards, and recovery runbooks are in place.

## Official Documentation

- Spring Security — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — OAuth2 Resource Server on WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Boot 3.3 — Spring Security Resource Server configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Reactor — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
