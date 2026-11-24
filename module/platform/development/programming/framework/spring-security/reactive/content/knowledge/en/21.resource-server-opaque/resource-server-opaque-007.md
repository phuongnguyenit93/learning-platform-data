# Handling Inactive Tokens, Network Errors, and Provider Unavailability with Spring Security Reactive Opaque Token

> **Module:** Spring Security - reactive  
> **Parent Topic:** Resource Server Opaque  
> **Scope:** Spring WebFlux Resource Server authenticating Bearer tokens via OAuth 2.0 Token Introspection (RFC 7662).  
> **Goal:** Distinguish `active=false` tokens from HTTP/network errors on the introspection endpoint; design **fail-closed** handling, timeouts, retries, circuit breakers, caching, and status/error contracts; implement a Java 17+ example with `ReactiveOpaqueTokenIntrospector` and test failure scenarios.

## 1. Problem: One Access Token, Many Failure Modes

The WebFlux application `reports-api` receives:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.com
Authorization: Bearer opaque-random-token
~~~

The token does not need a JWT structure. The Resource Server sends the token to the Authorization Server's **trusted introspection endpoint** to query its status and claims. Here, the following scenarios may all look like "unable to log in," yet their causes and treatments are completely different:

1. **Truly inactive token:** non-existent, expired, revoked, or unknown to the resource server -> valid introspection response with `"active": false`.
2. **Active token lacking permission:** `"active": true`, yet `scope` lacks `reports.read` or has the wrong tenant/owner.
3. **Introspection service failure:** DNS failure, connection refused, connect/read timeout, TLS handshake error, HTTP 502/503/504, or non-conformant JSON.
4. **Wrong Resource Server client credentials:** the introspection endpoint returns **HTTP 401/403** for **the introspection request itself**.
5. **Overloaded service:** high concurrency, 429 rate limits, retries amplifying query volume, or widespread IdP downtime.

**Security rule:** Whenever token validity cannot be proven, **never create a successful Authentication**. "IdP unresponsive" does **not** mean "token active=true"; never use an anonymous/fallback principal to proceed with private data processing.

## 2. Opaque Tokens and JWTs Can Both Use Introspection

Opaque access tokens are typically unguessable strings containing no data readable by the API. OAuth 2.0 RFC 7662 lets the Resource Server submit a token and receive metadata on `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`, etc. when permitted by the IdP.

Spring Security calls this feature "opaque token" because verification happens **over the network**; in practice, a token may be a JWT and still be introspected to check live status/revocation with the issuer. The Resource Server **should not decode a JWT locally and trust its claims** if system policy mandates live verification against the introspection endpoint.

| Criterion | Opaque Introspection | Offline JWT Signature |
| --- | --- | --- |
| Verification method | Calls Authorization Server over HTTP | Verifies JWS via trusted public key/JWKS |
| Revocation | Can see fresh status on each introspection | Cannot detect revocation prior to `exp` automatically |
| Per-request IdP dependency | Yes without caching | No per request when keys are cached |
| Risk during IdP outage | New authentications are impacted | Can continue verifying JWTs using cached trusted keys |
| Permission data | Provided by introspection response | From signature-verified claims |
| Caching | Must weigh staleness/revocation | Key caching differs from token-active caching |

Never automatically switch from introspection to "local JWT parsing" during an IdP outage to dodge downtime. That **alters the trust contract**, potentially bypassing revocations and skipping audience/claim-profile checks.

## 3. Flow: Request -> Introspection -> Authentication

~~~mermaid
flowchart TD
    A["GET /api/reports + Bearer"] --> B["SecurityWebFilterChain"]
    B --> C["OpaqueTokenReactiveAuthenticationManager"]
    C --> D["ReactiveOpaqueTokenIntrospector"]
    D --> E{"What kind of result does the IdP return?"}
    E -->|"HTTP 200, active=false"| F["Invalid token: 401"]
    E -->|"HTTP 200, active=true"| G["Create OAuth2AuthenticatedPrincipal"]
    E -->|"Timeout, 429, 5xx, network error"| H["Do not authenticate: fail closed"]
    E -->|"Introspection request 401"| I["Wrong Resource Server credentials/config"]
    G --> J{"Allowed by scope/tenant/owner?"}
    J -->|"No"| K["403 / 404 per API contract"]
    J -->|"Yes"| L["Controller / domain service"]
    H --> M["Dependency error per policy, may be designed as 503"]
    I --> M
~~~

**There are two separate HTTP connections:**

- **Client -> Resource Server:** uses `Authorization: Bearer <access-token>`.
- **Resource Server -> Introspection Endpoint:** sends the token as form parameter `token=...`, typically using the **Resource Server's client ID/secret** to authenticate to the IdP.

The HTTP status codes of these two connections **must never be conflated**. A 401 response from the introspection endpoint means the client calling introspection failed to authenticate; whereas a revoked token normally returns **200 + active=false**.

## 4. RFC 7662: active=false Is an HTTP-Level Success Response

Standard introspection request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-access-token>&token_type_hint=access_token
~~~

This is a protocol illustration; never put real tokens or Basic credentials into READMEs, screenshots, or logs. Depending on the IdP, client authentication may use another agreed method.

For an active token:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "alice",
  "scope": "reports.read reports.export",
  "client_id": "report-frontend",
  "aud": "reports-api"
}
~~~

For an inactive token:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

Per **RFC 7662 §2.2**, when a token is inactive, non-existent, or the Resource Server is not allowed to see it, the Authorization Server **must return `active=false`** for an authenticated, valid introspection request. The RFC recommends not disclosing further reasons why the token is inactive. Never return details to external clients like "token revoked at 10:02 by admin."

**Do not misinterpret:** if HTTP is 200 yet the body omits `active`, contains malformed JSON, or has the wrong data type for `active`, that response is **invalid** and must not treat the token as active. If the body is `{"active":"true"}` (a string), do not silently treat it as boolean true unless a compatibility mechanism was explicitly evaluated.

## 5. What Does HTTP 401 at the Introspection Endpoint Mean?

RFC 7662 §2.3 notes: if the Resource Server uses OAuth2 client credentials to authenticate to the introspection endpoint and those credentials are invalid, the endpoint returns HTTP 401.

Distinguish clearly:

| Where the Error Appears | Example | Possible Meaning |
| --- | --- | --- |
| **Introspection endpoint returns HTTP 200** | `{"active":false}` | Access token is inactive or unknown to this Resource Server |
| **Introspection endpoint returns HTTP 401** | `invalid_client` | Resource Server client ID/secret/method is wrong or expired |
| **Introspection endpoint returns HTTP 403** | Insufficient permission to introspect | Resource Server account is not permitted to query token status |
| **Introspection endpoint returns HTTP 429** | Rate limit | Throttled; token status not yet verified |
| **Introspection endpoint returns HTTP 502/503/504** | IdP/gateway failure | No trustworthy verification result available |
| **API client receives HTTP 401** | `WWW-Authenticate: Bearer` | Authentication failed at Resource Server; does not mirror upstream status verbatim |
| **API client receives HTTP 403** | Missing `SCOPE_reports.read` | Authentication may have succeeded, but authorization is insufficient |

**Do not turn every upstream HTTP 401 into "the end-user's token expired."** Check resource-server introspection credentials, OAuth2 client-auth method, secret rotation, endpoint URL, and IdP policy. Conversely, never force `active=true` when introspection credentials are wrong just to avoid an outage.

## 6. Classifying Errors Before Applying Retries

| Category | Signal | Auto-Retry? | Security Decision |
| --- | --- | --- | --- |
| Inactive token | Valid 200, `active=false` | **No** | Reject authentication |
| Malformed token / missing Bearer | Cannot parse inbound header | **No** | 401 |
| Active token lacking scope | `active=true`, insufficient scope | **No** | 403 |
| Upstream 401/403 | Wrong client credentials / introspection permission | **No hot retry** | Fail closed, config alert |
| DNS / connection refused | Connection error | Very limited retry if policy permits | Fail closed |
| Timeout | No response within budget | Very limited retry, with total deadline | Fail closed |
| HTTP 429 | Rate limited | Only per `Retry-After`/budget, avoid storms | Fail closed |
| HTTP 5xx | IdP outage or proxy error | Bounded retry possible for transient failures | Fail closed |
| Bad JSON body / missing active | Protocol/schema error | Usually no; alert | Fail closed |
| TLS certificate error | Untrusted endpoint | **No** | Fail closed, fix TLS/trust |
| Circuit breaker OPEN | IdP deemed unavailable | Do not call network per request | Fail closed |

Retrying an **introspection POST** typically causes no protocol-level data mutation, yet still adds load, cost, and rate-limit pressure. Never retry blindly on every exception or retry on `active=false`. Retries help only for expected transient errors with a **strict total time budget**, concurrency caps, and backoff/jitter.

## 7. Minimum Baseline: Spring Boot Configuration

A Reactive Resource Server authenticating opaque tokens can start with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: resource-server-client
          client-secret: <read-from-secret-store>
~~~

The configuration above is illustrative; never commit real `client-secret` values in YAML. Spring Boot auto-configures `ReactiveOpaqueTokenIntrospector` when WebFlux/OAuth2 Resource Server and these properties are present.

HTTP filter:

~~~java
@Bean
SecurityWebFilterChain chain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/health").permitAll()
            .pathMatchers("/api/reports").hasAuthority(
                "SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
~~~

This is a **snippet** (missing imports/class); the runnable project starts in Section 11. When introspection returns `active=true` and a scope string, Spring maps each scope into an authority prefixed with `SCOPE_`. When `active=false`, no principal is granted.

Do not assume the introspection client survives outages well merely because the config is concise. When latency/SLOs matter, design and test timeouts, observability, bulkheads, circuit breakers, and HTTP response policies.

## 8. Fail-Closed Does Not Mean Every Error Returns the Same HTTP Status

**Security decision:** every introspection error path ensures the request is **not** authenticated. However, the client-facing response depends on Spring Security configuration and error handling:
- Invalid token (`active=false`): **401 Unauthorized** with an appropriate Bearer challenge.
- Active token lacking scope: **403 Forbidden**.
- Introspection service down: may return a **5xx** or another authentication error depending on pipeline/config; do not claim Spring Security always returns 503 by default.
- If the API needs **503 Service Unavailable** for outages, implement an **explicit** error mapping at the authentication/error boundary, test end-to-end, and ensure exceptions are never turned into a successful `Authentication`. Add `Retry-After` only if the system has a reliable recovery window.
- Upstream 401 from a bad secret: internal configuration error; never leak client secrets or IdP error bodies to the Internet.

**Why distinguish?** A 401 may cause mobile/browser clients to pointlessly attempt "re-login"; 503 indicates a dependency is unavailable and can be retried later. Yet **different status codes must never alter the rule of denying access**. Keep the contract consistent across your API gateway, Spring Security authentication entry point, metrics, and clients.

Avoid `onErrorResume(ex -> Mono.just(previousPrincipal))` in the introspector. That is the most dangerous **fail-open** pattern: an IdP outage would effectively reinstate previously revoked permissions.

## 9. Timeouts: Bounding Resource Server Latency

An API request waiting on introspection ties up resources while depending on the network. If the IdP stalls for 30 seconds, users experience an app "hang" even when the controller itself is fast.

Example latency budget (not a one-size-fits-all set of numbers):

~~~text
API total timeout budget:                1500 ms
Introspection connect timeout:             250 ms
Introspection response/read timeout:       800 ms
Reactor overall introspection deadline:   1000 ms
Remaining time:                           ~500 ms (routing/response)
~~~

In production, set budgets from p95/p99 metrics, throughput, SLOs, and error budgets. Never set an arbitrary 10 ms timeout that constantly rejects valid tokens.

There are two layers:
- **HTTP client timeout:** connect timeout and response timeout on the Reactor Netty or `WebClient` connector.
- **Reactive deadline:** `Mono.timeout(Duration)` wrapping the entire introspection operation.

Reactor's timeout **cancels the subscription** when the deadline expires, though it does not guarantee every upstream operation stops instantaneously at the network/proxy layer. Combine HTTP client timeouts, connection pool limits, and total request budgets.

## 10. Retries and Circuit Breakers on the Authentication Path

Sound retries require:
1. Retry only transient network errors or policy-allowed 5xx/429; **never** retry `BadOpaqueTokenException`.
2. Very few attempts (e.g., one retry), exponential backoff + jitter, and a total deadline.
3. Concurrency limits, connection pools, and bulkheads to stop thousands of concurrent requests from flooding the IdP after an outage.
4. Metrics for error rates, retry counts, service time, and circuit state, without logging raw Bearer tokens.
5. When the breaker is OPEN, **reject authentication** immediately; never let stale users pass.
6. Recover via half-open probes with a small quota; only allow active tokens confirmed by a valid response.

~~~mermaid
flowchart TD
    A["Introspect token"] --> B{"Circuit OPEN?"}
    B -->|"Yes"| X["Dependency unavailable -> fail closed"]
    B -->|"No"| C["Call IdP with bounded timeout"]
    C --> D{"Result"}
    D -->|"active=false"| E["401; do not retry"]
    D -->|"active=true"| F["Authn OK, check scope/tenant"]
    D -->|"Transient 5xx/timeout"| G{"Retry budget left?"}
    G -->|"Yes"| H["Backoff/jitter + retry within total deadline"]
    H --> C
    G -->|"No"| X
    D -->|"401 client credentials"| I["Config alert, no hot retry, fail closed"]
~~~

Merely slapping on `retryWhen` does not make a service resilient. On the auth path, a retry storm can take down the authorization server faster. When using Resilience4j or Spring Cloud Circuit Breaker, verify Reactor compatibility and **exclude inactive tokens from breaker failure-rate tracking** since `active=false` is a normal authentication outcome, not a dependency outage.

## 11. Illustrative Java 17+ WebFlux Project

The project has three functional groups:

- Inbound `SecurityWebFilterChain` protecting the API with opaque Bearer tokens.
- `ReactiveOpaqueTokenIntrospector` performing introspection and a timeout wrapper, preserving inactive token errors.
- Tests: wrapper unit tests and `WebTestClient` route/authority tests. **Never use mock auth to claim HTTP introspection succeeded.**

This lesson uses Spring Boot `3.3.13` and Spring Security 6.3.x to pin the constructor API available in that branch. The Spring Boot 3.3 line is past OSS support; production must use a supported release. In Spring Security 6.5+, the builder API `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` is recommended, and older constructors may be deprecated. This is a **version-appropriate choice**; never copy signatures blindly between 6.3 and 7.x.

~~~text
opaque-introspection-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── OpaqueApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GuardedIntrospector.java
    │   │   └── ReportsController.java
    │   └── resources/application.yml
    └── test/java/demo/opaque/
        ├── GuardedIntrospectorTest.java
        └── OpaqueHttpSecurityTest.java
~~~

### 11.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>opaque-introspection-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Do not add `spring-boot-starter-web` because the lab is WebFlux. `spring-security-test` enables `mockOpaqueToken()` in `WebTestClient`; it helps test routes but **bypasses network introspection**.

### 11.2. OpaqueApplication.java

~~~java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
~~~

### 11.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  introspection:
    uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
    client-id: ${INTROSPECTION_CLIENT_ID:lab-api-client}
    client-secret: ${INTROSPECTION_CLIENT_SECRET:lab-placeholder-secret}
    overall-timeout: 800ms
~~~

`.invalid` is a reserved example hostname that **does not exist**. Project startup and unit tests do not contact that endpoint, yet a real HTTP Bearer token cannot be verified against a fake hostname; configure a real IdP or mock introspection server for integration tests.

In production, use a secret manager/encrypted settings, HTTPS, server certificate validation, and dedicated IdP introspection client credentials rather than sharing a frontend login secret. Never log inbound `Authorization` or outbound `client-secret`.

## 12. SecurityConfig.java: Resource Server and Introspector Bean

~~~java
package demo.opaque;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${lab.introspection.uri}") String uri,
            @Value("${lab.introspection.client-id}") String id,
            @Value("${lab.introspection.client-secret}") String secret,
            @Value("${lab.introspection.overall-timeout}")
            Duration timeout) {

        // Constructor API belonging to the lab's Spring Security 6.3.x.
        var delegate = new SpringReactiveOpaqueTokenIntrospector(
            uri, id, secret);

        return new GuardedIntrospector(delegate, timeout);
    }
}
~~~

**What this code guarantees:**
- Bearer tokens are processed by OAuth2 Resource Server without login forms, HTTP Basic, or session credentials.
- Only scope `reports.read` can call `GET /api/reports`; object/tenant checks are still needed in real use cases.
- `ReactiveOpaqueTokenIntrospector` is a Spring Bean replacing Boot's default configuration; there are no two competing beans.
- The wrapper bounds total introspection duration and **never turns errors into a principal**.
- `NoOpServerSecurityContextRepository` prevents storing Bearer Authentication in a session.
- CSRF is disabled **only for a header-only Bearer API**; if cookies, sessions, or browser-auto-sent Basic auth are introduced later, re-evaluate CSRF.

**What this code does not automatically provide:** circuit breakers, request coalescing, distributed caching, custom HTTP 503 mapping, business idempotency, or custom connect timeouts. Those are production hardening steps that must be implemented and tested separately, not assumed just from the wrapper.

## 13. GuardedIntrospector.java: Deadline and Preserving Inactive Errors

~~~java
package demo.opaque;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class GuardedIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;

    public GuardedIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline) {
        this.delegate = Objects.requireNonNull(delegate);
        this.deadline = Objects.requireNonNull(deadline);
        if (deadline.isZero() || deadline.isNegative()) {
            throw new IllegalArgumentException("deadline must be positive");
        }
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .timeout(deadline)
            .onErrorMap(TimeoutException.class,
                ex -> new IntrospectionUnavailableException(
                    "Token introspection deadline exceeded", ex));
    }
}

final class IntrospectionUnavailableException extends RuntimeException {
    IntrospectionUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Why use `Mono.defer`?** Each subscription actually invokes delegate introspection at subscription time rather than triggering synchronous side effects during assembly. `Mono.just(principal)` is only returned once the delegate verifies the token; there is no fallback principal on error.

**Why map only TimeoutException?** The test goal illustrates separating **expired deadline** from `BadOpaqueTokenException` (inactive token). The wrapper does not distort invalid-token errors. Some network/HTTP errors may already be wrapped by Spring's introspector in `OAuth2IntrospectionException`; those errors still fail the stream and **never** produce a successful Authentication. In production, if you need specific metrics, retries, or status codes, inspect the exception hierarchy and root causes for your version.

`IntrospectionUnavailableException` does not automatically yield HTTP 503. Security filters may wrap or re-map authentication errors; response mapping must be added and tested at the authentication failure boundary or gateway. Only the **fail-closed security outcome** can be inferred from the code above.

## 14. ReportsController.java: Returning Data Only When Authenticated

~~~java
package demo.opaque;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(Map.of("subject", principal.getName()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "report", "Visible with reports.read scope"));
    }
}
~~~

Once the token is successfully introspected with the right scope, `GET /api/reports` returns JSON containing the `report` key. The controller never sees the raw token, never infers `active` from the token string, and never attaches a principal from an unverified cache.

In real APIs, the service must add tenant/owner/action authorization, payload validation, and transactions for mutating operations. Scope `reports.read` does not mean reading every organization's reports.

## 15. Unit Tests: Distinguishing Active, Inactive, and Timeout

These tests **genuinely test the wrapper** without calling a live IdP. Stub `ReactiveOpaqueTokenIntrospector` returns:
- `Mono.just(verifiedPrincipal)` for active;
- `Mono.error(new BadOpaqueTokenException(...))` for inactive;
- `Mono.never()` for timeout;
- `Mono.error(new OAuth2IntrospectionException(...))` for simulated HTTP/protocol/network errors.

File `src/test/java/demo/opaque/GuardedIntrospectorTest.java`:

~~~java
package demo.opaque;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class GuardedIntrospectorTest {

    private OAuth2AuthenticatedPrincipal activePrincipal() {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "scope", "reports.read"),
            AuthorityUtils.createAuthorityList("SCOPE_reports.read"));
    }

    @Test
    void activeTokenReturnsVerifiedPrincipal() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.just(activePrincipal());

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("active"))
            .assertNext(principal ->
                assertEquals("alice", principal.getName()))
            .verifyComplete();
    }

    @Test
    void inactiveTokenRemainsAuthenticationFailure() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.error(
                new BadOpaqueTokenException("inactive token"));

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("inactive"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void neverRespondingProviderHitsDeadline() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.never();

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(50));

        StepVerifier.create(guarded.introspect("slow"))
            .expectError(IntrospectionUnavailableException.class)
            .verify();
    }

    @Test
    void providerProtocolFailureCannotProducePrincipal() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.error(
                new OAuth2IntrospectionException(
                    "upstream introspection failure"));

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("upstream-error"))
            .expectError(OAuth2IntrospectionException.class)
            .verify();
    }

    @Test
    void missingDeadlineIsRejectedAtConstruction() {
        org.junit.jupiter.api.Assertions.assertThrows(
            IllegalArgumentException.class,
            () -> new GuardedIntrospector(
                token -> Mono.empty(), Duration.ZERO));
    }
}
~~~

**What the assertions prove:** only active tokens pass a principal through; inactive tokens are not converted into success; timeouts map to the dedicated exception; other introspection errors also fail to yield a principal; invalid deadlines are rejected. They **do not prove** the HTTP request to the Authorization Server used valid Basic auth/form data, nor do they prove 503 status mapping.

When the provider returns `active=false` over the network, `SpringReactiveOpaqueTokenIntrospector` is responsible for signaling an invalid token. The unit tests above simulate that signal via `BadOpaqueTokenException`. To verify real RFC 7662 response parsing, you need the mock HTTP IdP described in Section 18.

## 16. WebTestClient: Resource Server Authorization Without Networking

`mockOpaqueToken()` creates a mock `BearerTokenAuthentication` for test requests. **It bypasses introspection**, so it does not prove the IdP returned `active=true`.

File `src/test/java/demo/opaque/OpaqueHttpSecurityTest.java`:

~~~java
package demo.opaque;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueHttpSecurityTest {

    @Autowired WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingBearerIsUnauthorized() {
        client.get().uri("/api/me")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void mockActiveUserCanReadOwnSubject() {
        client.mutateWith(mockOpaqueToken()
                .attributes(map -> map.put("sub", "alice")))
            .get().uri("/api/me")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void tokenWithInsufficientScopeIsForbidden() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")))
            .get().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void tokenWithReportsScopeMayReadReports() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.report").exists();
    }

    @Test
    void unlistedRouteIsDenied() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/secret-admin")
            .exchange().expectStatus().isForbidden();
    }
}
~~~

**Distinguishing tests:**
- `GuardedIntrospectorTest` focuses on Reactor error/timeout behaviors.
- `OpaqueHttpSecurityTest` focuses on HTTP routes/authorities, while mocking bypasses networking.
- Mock IdP integration tests must exercise GET/POST through the actual WebFlux security chain **without `mockOpaqueToken`** to prove inactive/active/upstream errors affect the real endpoint properly.

There are **5 + 6 = 11 test methods** in the examples. This lesson does not assume Maven was executed on the reader's machine; if pinned versions or HTTP test behavior differ, verify them directly.

## 17. Running the Project and Expected Outcomes

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

Tests should prove **no fallback authentication exists** and verify scopes properly. With `application.yml` pointing to `.invalid`, mock tests do not call the provider; DNS errors appear only if you send a **real Bearer request** without replacing the endpoint.

Run the application:

~~~bash
mvn spring-boot:run
~~~

Health request:

~~~bash
curl -i "http://localhost:8080/public/health"
~~~

Expected JSON:

~~~json
{"status":"up"}
~~~

Private request without token:

~~~bash
curl -i "http://localhost:8080/api/reports"
~~~

Expected 401. To call private routes with a valid token, configure a real introspection endpoint; there are no hardcoded demo tokens in this project.

**Never use `curl -k` in real environments** to skip TLS validation, and never put `Authorization: Bearer ...` into shell history, Jenkins logs, or public screenshots.

## 18. Testing RFC 7662 with a Fake IdP

To test the entire HTTP path, stand up a fake introspection server in integration tests (WireMock, MockWebServer, or a test HTTP server) covering these scenarios using test-controlled endpoints and certificates:

| Fake IdP Returns | Expected from Resource Server |
| --- | --- |
| 200 `{"active":true,"sub":"alice","scope":"reports.read"}` | Authentication succeeds and route allows when scope suffices |
| 200 `{"active":false}` | Authentication rejected, **401** |
| 200 `{"active":true,"scope":"profile"}` | Authn valid, yet reports route returns **403** |
| 200 malformed JSON | Do not authenticate; dependency/protocol error, never 200 |
| 200 missing active | Do not authenticate; never assume active |
| 401 upstream `invalid_client` | Do not authenticate; config/secret error, alert |
| 403 upstream | Do not authenticate; missing introspection permission |
| 429 upstream | Do not authenticate, bounded retry per policy |
| 500/502/503/504 upstream | Do not authenticate, timeout/retry/breaker per policy |
| Connect timeout / read timeout | Do not authenticate, deadline and metrics |
| TLS wrong certificate | Do not authenticate, never disable verification |
| Upstream returns active=true after revoked token | Follows current endpoint result and cache policy; verify IdP contract |

**Do not use only** `mockOpaqueToken()` across all integration tests, as it builds a principal before introspection runs. Send a real Bearer header to the application, point `introspection-uri` at the fake server, and assert request counts and HTTP responses. If you want 503 on outages, add custom error-handling policy and assert **exact 503** there.

During testing, never write raw tokens into CI test logs; use test-generated dummy values and sanitize captured requests/responses.

## 19. Dedicated HTTP Client Timeouts

`Mono.timeout` bounds the total deadline, but production should also set HTTP connection/read timeouts. With Spring WebFlux/Netty, configure them on a dedicated `WebClient` for introspection:

~~~java
// Extension snippet for Spring Security versions with constructor
// SpringReactiveOpaqueTokenIntrospector(String, WebClient).
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
    .responseTimeout(Duration.ofMillis(800));

WebClient idpClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .defaultHeaders(h -> h.setBasicAuth(clientId, clientSecret))
    .build();

var delegate = new SpringReactiveOpaqueTokenIntrospector(
    introspectionUri, idpClient);
~~~

This is an **optional snippet** placed inside a `@Bean` configuration, requiring `java.time.Duration` and injected `clientId`/`clientSecret`; it is not a standalone Java file. Spring Security **6.3.x** provides constructor `(String, WebClient)`. Never attach Basic client credentials to a shared `WebClient`; use a dedicated client targeting only the allowlisted IdP endpoint.

On newer versions with a builder supporting `WebClient` customization, consult the actual version's Javadoc. Avoid accidentally conflicting dual timeout policies. Tune your latency budget from measurements rather than copying 250/800 ms verbatim into every production service.

## 20. Caching active/inactive: Performance vs. Revocation Trade-offs

Continuous introspection adds load to the IdP; caching lowers latency at the cost of stale authorization.

**Positive caching:** caching `active=true` allows a revoked token to remain accepted **until the cache TTL expires**, even if a fresh call to the IdP would return inactive. If the system requires immediate revocation, **do not cache active results** or use reliable push revocation/invalidation signals. If a few seconds of revocation lag is acceptable, document the business SLA explicitly.

**Negative caching:** caching `active=false` very briefly can curb token spray/abuse, provided size is bounded so attackers cannot fill memory with endless random tokens. Never cache a network failure as `active=false` and mistake it for an IdP verdict.

Isolate cache keys by issuer/tenant/resource/client context. Never store raw Bearer tokens as keys in logs or cache dashboards; you can use a keyed HMAC digest of the token with a separate secret while ensuring the digest cannot be replayed as a credential. Caches must enforce eviction and protected storage.

**Reasonable cache TTL:** never exceed the token's `exp` when present unless governed by a special contract; weigh against the revocation SLA and token lifetime. Introspection responses may omit `exp`—apply a strict TTL policy. There is no universal safe default like "5 minutes" for every app.

**Never use stale-while-revalidate to keep serving private requests** when live introspection is down, unless business and security explicitly approve a bounded degraded mode that does not violate revocation requirements. This lab enforces **strict fail-closed behavior**.

## 21. Circuit Breakers, Bulkheads, and Rate Limiting

An IdP outage lasting several minutes can cause a Resource Server to suffer:
- Thousands of requests concurrently waiting for timeouts;
- Exhausted connection pools;
- Concurrent retries triggering a "retry storm";
- Multiple instances taking the IdP down again right as it recovers.

Production design:
1. **Bulkhead/concurrency limit:** cap concurrent introspection calls.
2. **Short total timeout:** never hold requests indefinitely.
3. **Circuit breaker:** temporarily halt calls to the IdP when 5xx/timeouts exceed thresholds.
4. **Half-open probes:** small controlled traffic to detect recovery.
5. **Jitter/backoff:** avoid thundering herds.
6. **Per-client/IP rate limits** at the API edge to curb token spraying.
7. **Metrics:** p50/p95/p99 latency, active vs. inactive, upstream 4xx/5xx, timeouts, breaker state, concurrency.
8. **Alerts:** invalid/rotated secret, 5xx rate, sustained 429s, latency spikes, outage duration.
9. **Recovery tests:** simulate IdP outage and recovery; ensure the breaker does not stay stuck OPEN and revoked tokens do not unexpectedly work again.

**Do not count inactive tokens as system errors that trip the circuit breaker.** `active=false` is a valid negative authentication result. If 80% of incoming tokens are random/non-existent, the circuit breaker must not block legitimate users just because `active=false` spikes.

## 22. HTTP Contract and Client Experience During an IdP Outage

Give clients a clear contract:

- **401**: client is unauthenticated or token is inactive. Clients may trigger refresh/re-auth per OAuth2 flow where appropriate.
- **403**: token is active and Authentication succeeded, yet scope/role or object policy denies access. Do not pointlessly refresh tokens on 403.
- **503**: a **design option** for dependency unavailability supporting client retry/backoff; not guaranteed by Spring defaults. Test custom exception mapping and upstream status sanitization.
- **429**: when the API enforces its own rate limits; distinct from introspection endpoint 429s. Never leak raw provider bodies.
- **Other 5xx**: internal error when no explicit mapping exists; must still fail closed.

Example outage response **when the API explicitly installs a custom 503 mapping** (not produced automatically by the lab project):

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Authentication dependency unavailable","status":503}
~~~

This response omits client secrets, raw tokens, internal issuer URLs, and detailed certificate causes. Attach a system trace ID so operations can look up internal logs. Set `Retry-After` only with a sensible schedule/budget; avoid instructing every client to retry simultaneously.

**Do not let error statuses mislead:** if the system emits 401 on outages due to default error handling, that does not prove the token was `active=false`; safe metrics/logs must distinguish `INVALID_TOKEN` from `INTROSPECTION_UNAVAILABLE`.

## 23. Safe Observability and Logging

Never log:
- Inbound `Authorization: Bearer ...` values;
- Introspection form parameter `token=...`;
- Resource Server `Authorization: Basic ...` client credentials;
- Raw introspection responses containing excessive claims/PII;
- Refresh tokens, session cookies, or downstream credentials.

Safe to log:
- Unguessable trace/correlation IDs;
- Result **category** (active/inactive/error/timeouts);
- Sanitized upstream HTTP status;
- Internal IdP alias, never secrets;
- Duration, timeout category, breaker state, route ID;
- Low-cardinality metric tags (never tag raw tokens, user IDs, or `sub` as high-cardinality labels).

Example log event:

~~~json
{
  "traceId": "trace-example",
  "idpAlias": "corporate-idp",
  "result": "INTROSPECTION_TIMEOUT",
  "durationMs": 801,
  "resource": "reports-api"
}
~~~

This is an illustrative log, not lab stdout. Configure masking in HTTP client wiretaps, APM, proxies, and traces so auto-instrumentation never leaks tokens.

## 24. Distinguishing Request Idempotency and Authentication Retries

An introspection POST is a status query that normally creates no business side effects; bounded retries are acceptable on transient errors. However, the original API request might be `POST /orders/approve` or a funds transfer. If the client sees 503/timeout, it **must not** blindly retry the POST without an idempotency key and business contract.

Similarly, if the Resource Server calls the IdP, runs the controller, and then the downstream response drops, a client retry could repeat side effects. Never conflate "retrying introspection" with "retrying the entire business HTTP request."

When an authentication error occurs **before the controller**, no data may be written. Test failure paths to confirm services are never invoked; if custom filters, tracing, or eager subscriptions perform side effects, audit them too. Spring Security cannot roll back side effects executed before authentication if filters are misordered.

## 25. Layered Troubleshooting

| Symptom | Check First | Resolution |
| --- | --- | --- |
| Every token becomes inactive | Did the IdP truly return `active=false`? | Check issuer/endpoint/resource client permissions |
| Single token rejected | `active=false` or missing scope? | Refresh/re-auth/revoke per proper flow |
| Upstream HTTP 401 | Introspection client ID/secret/auth method | Rotate/fix credentials; **do not** blame user token |
| Upstream HTTP 403 | Client lacks introspection permission | Fix IdP policy / resource server permissions |
| DNS / connect timeout | DNS, proxy, network route | Bounded timeouts, network health |
| TLS handshake failure | Certificate/truststore/mTLS | Fix trust/certs; never disable TLS |
| HTTP 429 | IdP rate limit, token spray/retries | Concurrency cap, retry policy, budgets |
| HTTP 502/503/504 | Provider/gateway outage | Breaker, fail-closed degraded policy, alerts |
| 200 yet malformed JSON | IdP regression / schema mismatch | Fail closed, integration contract tests |
| Active token yet API 403 | Scope/role/tenant authorization | Check `GrantedAuthorities` and domain checks |
| `active=false` yet API 200 | Fail-open fallback / stale cache / mock test | Remove fallback, run real integration checks |
| API returns 503 after provider recovers | Stuck breaker / health routing | Half-open probe, policy-based reset |
| Latency spikes | Timeouts too long, no bulkhead | Tune budgets + pools + per-instance concurrency |
| `mockOpaqueToken` tests always pass | Tests bypass introspection | Add fake IdP + real Bearer header tests |
| Revoked token still passes | Positive cache TTL too long | Reduce TTL, add invalidation, or disable cache |

**Safe debugging:** separate the status of the **introspection request** from the status of the **client-facing API response**, correlate metrics/timestamps/traces without printing raw secrets. Fix configuration issues at the right layer; never disable authentication or accept all tokens when the IdP is hard to reach.

## 26. Self-Check Questions

1. Why is `HTTP 200 {"active":false}` not an HTTP error?
2. Why does HTTP 401 from the introspection endpoint not necessarily mean the user's token expired?
3. When the provider is down, why are `Mono.empty()` or fallback principals unsafe?
4. How does opaque introspection differ from offline JWT verification for revocation and outages?
5. If a token has `active=true` yet lacks `reports.read`, why does the client usually receive 403?
6. Why does `mockOpaqueToken()` fail to prove a real access token was verified by the IdP?
7. Why should Reactor timeouts be paired with HTTP connect/read timeouts?
8. When the circuit breaker is OPEN, may cached principals from earlier requests be accepted?
9. When does caching `active=true` violate an "immediate revocation" requirement?
10. Why can caching network errors as `active=false` distort diagnostics?
11. How does an IdP 429 differ from an API's own rate-limit 429?
12. Why must you not retry infinitely when the IdP returns 503/timeout?
13. When the API returns 503, should clients retry every business POST?
14. How can 401, 403, and 503 be distinguished without leaking tokens or secrets?
15. Right after rotating introspection credentials, what must you monitor to prevent prolonged downtime?
16. Why can a JWT-formatted token also be verified via opaque introspection?
17. Why must `active=false` responses be excluded from the IdP circuit breaker's failure counter?
18. When the provider times out, why is "fail closed" more important than trying to keep returning 200?

## 27. Hands-On Exercises

**A — Inactive token:** Have the fake IdP return 200 `{"active":false}`; send a real HTTP Bearer request via `WebTestClient` and expect 401. Do not use `mockOpaqueToken()`.

**B — Wrong credentials:** Have the fake IdP return 401 to the introspection request; verify the API rejects the request and logs safely with `INTROSPECTION_CLIENT_AUTH_FAILURE` without blaming a revoked user token.

**C — Network timeout:** Make the fake IdP hang; measure the deadline and confirm the controller never runs. Try mapping 503 explicitly if that matches your team's API contract.

**D — 5xx outage:** Have the fake IdP return 503; verify bounded retries and circuit breaker behavior with no success path.

**E — Scope:** Have the fake IdP return `active=true` with scope `profile`; the reports route must deny with 403. Switching scope to `reports.read` yields 200.

**F — Cache revocation:** Cache `active=true` briefly, revoke the token, and observe the stale window. Define an acceptable SLA or disable positive caching.

**G — Negative caching:** Send bursts of random tokens yielding inactive; cap cache size/TTL to prevent memory abuse.

**H — No fail-open:** Deliberately write a wrapper using `onErrorReturn(principalOld)`, write a test exposing the vulnerability, then replace it with fail-closed handling.

**I — Metrics/tracing:** Track inactive vs. 401 introspection credentials vs. 5xx/timeouts with zero tokens in logs.

**J — Recovery:** Simulate IdP downtime followed by recovery; verify half-open breaker probes, no retry storm, and that revoked tokens do not unexpectedly start working.

### Implementation Checklist

- [ ] I distinguish `active=false` from network/provider errors.
- [ ] I understand upstream HTTP 401 can mean introspection client credential failure.
- [ ] I issue an Authentication only when introspection confirms `active=true`.
- [ ] I have no allow-anonymous or stale-principal fallback on auth failures.
- [ ] I bound timeouts and concurrency, applying retries/circuit breakers by error category.
- [ ] I know Spring defaults do not guarantee HTTP 503 for outages without customization/tests.
- [ ] I do not cache active tokens in violation of the revocation SLA.
- [ ] I distinguish 401 authentication, 403 authorization, and 5xx dependency errors.
- [ ] I do not confuse `mockOpaqueToken` with real introspection integration tests.
- [ ] I validate JWT/opaque tokens per the trust contract, never "parsing JWTs to bypass the IdP."
- [ ] I never log inbound/outbound tokens or Basic client credentials.
- [ ] I test inactive, timeouts, 429, 5xx, TLS, malformed schemas, and recovery.

## 28. References

- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html): WebFlux resource server, introspection config, principal, scope mapping.
- [Spring Security — SpringReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html): constructors, builder, and custom `WebClient`.
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): authentication manager.
- [Spring Security — Testing Reactive Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockOpaqueToken()` and test boundaries.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active/false responses, introspection POST, error responses, caching/privacy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization header and error responses.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client, timeouts, filters.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeouts, `onErrorResume`, and mapping.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): bounded retries.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, and object authorization.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS for IdP/API credentials.

**Conclusion:** With Spring Security Reactive Resource Server Opaque, a valid introspection response `{"active":false}` is a **verdict that the token is inactive**; whereas timeouts, 429/5xx, TLS errors, or wrong client credentials mean **unable to verify**. Both must **fail closed**, yet be clearly separated in metrics, alerts, and HTTP contracts. Use `ReactiveOpaqueTokenIntrospector` with timeouts/budgets, bounded retries, breakers/bulkheads, and revocation-SLA-aligned caching; never issue a principal from old results when the IdP fails to confirm. Test **both mock route security and fake HTTP introspection** to prove the system never accidentally lets inactive or unknown tokens through when the provider suffers an outage.