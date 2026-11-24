# Building a Security Test Matrix, Dependency Faults, and Context Leak Tests in Spring Security WebFlux

> **Context:** integrated practice for Spring Boot 3.x, Spring Security 6.x, Java 17+, and WebFlux/Reactor. This lesson builds an **executable and extensible test matrix** covering authentication, authorization, dependency failures, and Security Context isolation across reactive flows. Executable HTTP examples use HTTP Basic with **lab-only** accounts to exercise security branches without an external IdP; JWT/opaque tokens have their own matrix and contract tests. HTTP Basic must run behind HTTPS in real environments.

In reactive systems, receiving HTTP 200 does not prove the system is secure. You must prove that **unauthorized callers are denied**, **dependency failures never turn into granted access**, and **request A's identity never leaks into request B when Reactor switches schedulers or runs two publishers concurrently**.

## 1. Objectives and Deliverables

Learners should be able to:

1. Build an `endpoint × HTTP method × identity × authority × dependency state → expected outcome` matrix.
2. Turn every row of the matrix into a concrete `WebTestClient` test rather than relying purely on controller unit tests.
3. Distinguish **401** (missing/invalid authentication), **403** (authenticated yet under-privileged, or CSRF rejection), **2xx** (allowed), and **5xx** (downstream dependency unavailable).
4. Simulate business service errors, timeouts, empty publishers, IdP token-verification failures, and unavailable authorization policies, verifying the system **fails closed** on sensitive data.
5. Test `ReactiveSecurityContextHolder` per **subscription** and detect caches, global fields, or manual subscriptions that leak identities.
6. Assess the exact scope of `mockUser()`, `mockJwt()`, and `mockOpaqueToken()` compared with real HTTP authentication tests.
7. Produce traceable CI outputs where every failure identifies input, expectation, and observation without writing raw tokens or passwords to logs.

**Deliverable:** a test suite covering the permission matrix, three dependency failure classes, Reactor Context isolation tests, and an integration checklist for JWT/opaque tokens. The learning goal is objective evidence that the app denies properly and isolates properly, not merely having Spring Security in dependencies.

## 2. Three Layers to Test Independently

A WebFlux HTTP request passes through these layers:

```text
HTTP request
   |
   v
[Selected SecurityWebFilterChain]
   |
   +-- authentication
   |      - HTTP Basic / OAuth2 Login / JWT / opaque token
   |      - missing or bad token: usually HTTP 401 or login redirect
   |
   +-- authorization in authorizeExchange
   |      - hasRole / hasAuthority / authenticated / permitAll
   |      - authenticated but lacking permission: usually HTTP 403
   |
   v
[Handler / @PreAuthorize if present]
   |
   +-- accesses identity via ReactiveSecurityContextHolder
   |
   v
[Reactive dependency: R2DBC / WebClient / Redis / IdP / policy service]
   |
   +-- success / empty / 5xx / timeout / connection failure
   |
   v
[HTTP response + redacted trace/metrics]
```

There are **two dependency categories** to distinguish:

- **Authentication/authorization dependencies:** JWK Set, token introspection, external policy decision points (PDP), role/tenant queries. When verification evidence is lacking, never grant access by default. The exact HTTP status depends on the framework, exception mapping, and protocol; measure at the WebFlux layer.
- **Post-authentication business dependencies:** report gateway, R2DBC, Redis, gRPC, WebClient. When a dependency fails, the API can return 503/504/5xx per contract, yet **must never** return another user's/tenant's data or substitute stale unauthorized data.

A 503 response does not mean Security failed. It can prove Security **let the right principal enter the handler**, and then the handler handled downstream failure cleanly. Thus the matrix must record **which layer produced the error**.

## 3. Designing an Actionable Security Matrix

### 3.1. Step One: Describe the Resource Contract

Suppose the application exposes these routes:

| Endpoint and method | Anonymous visitor | Authenticated user | Special permission | Dependency |
| --- | --- | --- | --- | --- |
| `GET /public` | Allowed | Allowed | None | None |
| `GET /api/me` | Blocked | Allowed | `authenticated` | Reactor Security Context |
| `GET /api/report` | Blocked | Only with scope | `SCOPE_reports:read` | Report Gateway |
| `GET /api/admin` | Blocked | ADMIN only | `ROLE_ADMIN` | None |
| `GET /api/tenant/{owner}` | Blocked | Owner only | Ownership check **after** authentication | Reactor Context / business authorization |
| Mutating POST if added later | Per policy | Per policy | Permissions and CSRF | Database |

There are three **lab** accounts:

| Account | Authorities |
| --- | --- |
| `alice` | `ROLE_USER`, `SCOPE_reports:read` |
| `bob` | `ROLE_USER` |
| `admin` | `ROLE_ADMIN`, `SCOPE_reports:read` |

`hasRole("ADMIN")` requires authority **`ROLE_ADMIN`** by default, whereas `hasAuthority("SCOPE_reports:read")` matches the exact mapped scope string. Production JWT/opaque tokens usually require an appropriate converter/mapping; never assume any token containing `role=admin` automatically becomes `ROLE_ADMIN`.

### 3.2. Minimum Requirements Matrix

| ID | Method / route | Identity | Dependency | Expected | What it proves |
| --- | --- | --- | --- | --- | --- |
| M01 | `GET /public` | anonymous | N/A | 200 | Intentionally open public endpoint |
| M02 | `GET /api/me` | anonymous | N/A | 401 Basic | Blocked when unauthenticated |
| M03 | `GET /api/me` | alice | N/A | 200, body `alice` | Context binds the right user |
| M04 | `GET /api/me` | bob | N/A | 200, body `bob` | Does not reuse previous request's identity |
| M05 | `GET /api/admin` | alice | N/A | 403 | Does not treat `authenticated` as ADMIN |
| M06 | `GET /api/admin` | admin | N/A | 200 | Valid ADMIN succeeds |
| M07 | `GET /api/report` | bob | N/A | 403 | Missing scope; dependency not invoked |
| M08 | `GET /api/report` | alice | OK | 200, `report:ready` | Sufficient scope and healthy dependency |
| M09 | `GET /api/report` | alice | runtime error from gateway | 503, no sensitive cause leaked | Never fails open or emits bogus data |
| M10 | `GET /api/report` | alice | unresponsive past timeout | 503 | Bounded wait budget |
| M11 | `GET /api/report` | alice | `Mono.empty()` | 503 | Empty is not treated as success |
| M12 | `GET /api/tenant/alice` | alice | N/A | 200, owner `alice` | Owner can read |
| M13 | `GET /api/tenant/bob` | alice | N/A | 403 | Cross-tenant read blocked |
| M14 | `GET /api/tenant/alice` | bob | N/A | 403 | No data leak when switching callers |
| M15 | Reactor publishers A and B | alice, bob concurrently | scheduler thread switch | A=`alice`, B=`bob` | Independent Security Context per subscription |
| M16 | Fresh Reactor publisher | no context | N/A | `anonymous` | Never “remembers” previous publisher's user |

M01–M14 run over HTTP/`WebTestClient`; M15–M16 use `StepVerifier`. These results form the **contract of the sample application below**. With OAuth2 Login, unauthenticated browsers may see 302 to the IdP instead of 401; with Spring Security Bearer Resource Server, callers typically see 401 with `WWW-Authenticate`. Do not force one hardcoded status onto every authentication scheme.

### 3.3. Why Negative Testing Matters

An `ADMIN → 200` test still passes if someone accidentally changes `hasRole("ADMIN")` to `authenticated()`. Only `alice → 403` catches that regression. Similarly, `valid report scope → 200` is insufficient: you need `bob` missing scope → 403, an unauthenticated user → 401, and proof that the dependency is never called before Security clears.

A strong matrix covers:

- **Positive controls:** right principal/authority and healthy dependencies.
- **Negative authorization:** anonymous, wrong role/scope, wrong owner, undeclared HTTP methods.
- **Negative protocol:** expired tokens, bad signatures, invalid `iss`/`aud`, introspection `active=false`.
- **Fault injection:** upstream 5xx, connection drops, timeouts, malformed responses, unreachable token/JWK issuer.
- **Isolation:** interleaving, scheduler switches, shared caches, missing context, high concurrency.

## 4. Building a Runnable Java 17+ WebFlux Demo Application

### 4.1. Gradle Dependencies

In a Spring Boot 3.3.x project with the Gradle plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`spring-security-test` provides `mockUser`, `mockJwt`, and Spring Security test setup; the HTTP tests below use the **app's real Basic Auth**, so they genuinely traverse `SecurityWebFilterChain`.

### 4.2. Application and Security Configuration

Create `src/main/java/example/securitymatrix/SecurityMatrixApplication.java`:

```java
package example.securitymatrix;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityMatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityMatrixApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/report")
                            .hasAuthority("SCOPE_reports:read")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/tenant/**")
                            .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Strictly for learning examples; NEVER ship {noop}
    // or these fixed passwords to production systems.
    @Bean
    MapReactiveUserDetailsService labUsers() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}pass")
                .authorities("ROLE_USER", "SCOPE_reports:read")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password("{noop}pass")
                .authorities("ROLE_USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}pass")
                .authorities("ROLE_ADMIN", "SCOPE_reports:read")
                .build();
        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    // Replaceable seam in tests to inject errors/timeouts without
    // starting a real database, IdP, or HTTP dependency.
    interface ReportGateway {
        Mono<String> loadReport();
    }

    @Bean
    ReportGateway reportGateway() {
        return () -> Mono.just("report:ready");
    }

    @RestController
    static class DemoApi {
        private final ReportGateway gateway;

        DemoApi(ReportGateway gateway) {
            this.gateway = gateway;
        }

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public:ok");
        }

        @GetMapping("/api/admin")
        Mono<String> adminEndpoint() {
            return Mono.just("admin:ok");
        }

        @GetMapping("/api/me")
        Mono<String> currentUser() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> ctx.getAuthentication().getName());
        }

        @GetMapping("/api/report")
        Mono<String> report() {
            return gateway.loadReport()
                    .timeout(Duration.ofMillis(250))
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("empty report")))
                    .onErrorMap(ex -> new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Report dependency unavailable"));
        }

        @GetMapping("/api/tenant/{owner}")
        Mono<String> tenantData(@PathVariable String owner) {
            return ReactiveSecurityContextHolder.getContext()
                    .map(ctx -> ctx.getAuthentication().getName())
                    .flatMap(requester -> {
                        if (requester.equals(owner)) {
                            return Mono.just("owner:" + owner);
                        }
                        return Mono.error(new ResponseStatusException(
                                HttpStatus.FORBIDDEN,
                                "Tenant access denied"));
                    });
        }
    }
}
```

**Reading the code along the security path:**

1. `authorizeExchange` declares **specific routes before** `anyExchange().denyAll()`. This configuration has a default match-all chain, so no request slips past Spring Security.
2. HTTP Basic uses `MapReactiveUserDetailsService` to construct `Authentication`/authorities for the three lab users. Never use fixed passwords or `{noop}` in production.
3. `/api/me` reads `ReactiveSecurityContextHolder` **inside the publisher subscribed to for the request**, never touching Servlet's `ThreadLocal` `SecurityContextHolder`.
4. `/api/report` reaches the handler only after Security verifies `SCOPE_reports:read`. `ReportGateway` is an interface allowing tests to inject faults. Errors/empty/timeouts over 250 ms map to 503; the underlying exception message is never exposed in the response reason.
5. `/api/tenant/{owner}` illustrates post-authentication ownership checking; production systems must compare trusted tenant IDs/subjects/ACLs rather than using URL usernames as a general tenant policy.
6. All demo endpoints use GET so POST CSRF errors do not mix into the core lesson. Never disable CSRF globally due to missing tokens; add a dedicated CSRF matrix whenever write operations are introduced.

HTTP Basic serves the lab; if migrating to a JWT Bearer Resource Server, configure `.oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))`, configure issuer/audience/trust properly, and test real tokens. `mockJwt` helps test authorization quickly, but does not execute real signature verification.

## 5. WebTestClient Turns the Matrix into Regression Tests

Create `src/test/java/example/securitymatrix/SecurityMatrixApplicationTest.java`:

```java
package example.securitymatrix;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = SecurityMatrixApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityMatrixApplicationTest {

    @Autowired
    WebTestClient client;

    @MockBean
    SecurityMatrixApplication.ReportGateway gateway;

    @BeforeEach
    void healthyReportByDefault() {
        when(gateway.loadReport()).thenReturn(Mono.just("report:ready"));
    }

    @Test
    void publicRouteAndAnonymousProtection() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public:ok");

        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/report")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void eachAuthenticatedRequestGetsItsOwnIdentity() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");
    }

    @Test
    void adminRequiresAdminRoleEvenForValidUsers() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("admin", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:ok");
    }

    @Test
    void reportNeedsScopeAndThenReturnsGatewayData() {
        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report:ready");
    }

    @Test
    void tenantDataCannotBeReadAcrossUsers() {
        client.get().uri("/api/tenant/alice")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("owner:alice");

        client.get().uri("/api/tenant/bob")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/tenant/alice")
                .headers(h -> h.setBasicAuth("bob", "pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void dependencyExceptionDoesNotProduceDataOrLeakSecret() {
        when(gateway.loadReport()).thenReturn(Mono.error(
                new IllegalStateException("internal-db-secret")));

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .consumeWith(result -> {
                    byte[] response = result.getResponseBody();
                    String body = response == null
                            ? ""
                            : new String(response, StandardCharsets.UTF_8);
                    assertFalse(body.contains("internal-db-secret"));
                });
    }

    @Test
    void dependencyTimeoutAndEmptyMustNotBeSuccessful() {
        when(gateway.loadReport()).thenReturn(Mono.never());

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503);

        when(gateway.loadReport()).thenReturn(Mono.empty());

        client.get().uri("/api/report")
                .headers(h -> h.setBasicAuth("alice", "pass"))
                .exchange()
                .expectStatus().isEqualTo(503);
    }
}
```

Run from the project with the Gradle Wrapper:

```bash
./gradlew test --tests 'example.securitymatrix.SecurityMatrixApplicationTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests 'example.securitymatrix.SecurityMatrixApplicationTest'
```

**Expected result when running the sample project properly:** JUnit reports all seven tests as **PASS**. There is no fixed app stdout; assertions verify exact HTTP statuses and bodies. The code is a complete example for Spring Boot 3.3.x; `@MockBean` belongs to Spring Boot 3.3 and in newer Spring Boot versions may be deprecated/replaced by `@MockitoBean` with matching dependencies/test setup.

`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real reactive HTTP server on a random port; `WebTestClient` sends requests through Security filters and handlers. Replacing the gateway with `@MockBean` in tests **does not** bypass Security—only the business dependency is stubbed. That is the strength of this integration test.

**Why does one test check both 503 and exception suppression?** Upstream errors can contain hostnames, JDBC URLs, access tokens, or infrastructure details. APIs must never return raw stack traces/messages to clients. Server logs require redaction and correlation IDs; anti-leakage tests on client response bodies alone do not prove server logging is safe.

## 6. Isolating Reactive Security Context Across Subscriptions

### 6.1. How Reactor Context Differs from ThreadLocal

In WebFlux, the security context travels through the **Reactor subscriber Context**. `ReactiveSecurityContextHolder.getContext()` returns a `Mono<SecurityContext>` scoped to the current subscription. When a pipeline is composed properly with `flatMap`, `map`, `publishOn`, `delayElement`, and `contextWrite`, context normally stays attached to the subscription across Reactor operators; **switching threads in Reactor does not automatically drop the context**.

Common mistakes:

- Using `ThreadLocal`-based `SecurityContextHolder.getContext()` in WebFlux and inferring identity from the worker thread. One thread handles many different requests.
- Storing `Authentication`/username in `static` fields, `ThreadLocal`, singleton fields, or a shared cached `Mono` across all requests.
- Creating a `Mono` that reads the principal and calling manual `subscribe()` detached from the request chain; the new subscription may lose the request context.
- Crossing `CompletableFuture`, non-Reactor SDK callbacks, or custom reactive bridges without propagating context per contract.
- Calling `Mono.cache()` on a publisher containing per-user data and reusing that cached publisher across multiple requests.

**Rule:** per-user/per-tenant data must be computed from the **current subscription's** context, never placed in a shared singleton cache keyed only by path. If caching business data, include identity/tenant/ACL version in the cache key and verify authorization before reading cached values.

### 6.2. Standalone `StepVerifier` Test Proving Context Isolation

Create `src/test/java/example/securitymatrix/ReactiveSecurityContextIsolationTest.java`:

```java
package example.securitymatrix;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSecurityContextIsolationTest {

    private static Mono<String> currentIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .defaultIfEmpty("anonymous");
    }

    @Test
    void twoConcurrentSubscriptionsSeeDifferentIdentities() {
        var a = new UsernamePasswordAuthenticationToken(
                "alice", "unused", List.of());
        var b = new UsernamePasswordAuthenticationToken(
                "bob", "unused", List.of());

        Mono<String> alice = currentIdentity()
                .delayElement(Duration.ofMillis(20))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(a));

        Mono<String> bob = currentIdentity()
                .delayElement(Duration.ofMillis(10))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(b));

        StepVerifier.create(Mono.zip(alice, bob))
                .assertNext(pair -> {
                    assertEquals("alice", pair.getT1());
                    assertEquals("bob", pair.getT2());
                })
                .verifyComplete();

        // A new subscription without context must remain independent.
        StepVerifier.create(currentIdentity())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test --tests 'example.securitymatrix.ReactiveSecurityContextIsolationTest'
```

**Expected:** test PASSES, with `alice` and `bob` never swapped even though `delayElement` triggers asynchronous scheduling. This test proves **Reactor Context is attached per subscription** and read accurately by `ReactiveSecurityContextHolder`. It **does not** by itself prove the HTTP app/filters or app caches never leak data; therefore also run the HTTP tests in section 5 plus real-app concurrency tests whenever shared caches or async bridges exist.

### 6.3. Anti-Pattern: Caching a Mono Holding Request Identity

**Wrong (illustrative snippet, not a standalone class):**

```java
// Singleton field shared across all requests:
private final Mono<String> cachedIdentity =
        ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .cache();
```

`cache()` replays the signals from the very first subscription. If the first subscriber was `alice`, `bob`'s subsequent subscription can receive the cached result `alice`. This is different from **creating a fresh `Mono` per request**; the bug happens because a shared cached publisher holds request-sensitive data.

**Right:**

```java
Mono<String> currentIdentity() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
}
```

If caching query results, use a key and lifecycle designed for multi-tenant data and re-check permissions before returning; never cache `Authentication` itself as an application-wide singleton.

### 6.4. Additional Isolation Scenarios to Monitor

In multi-user systems, also test:

| Scenario | Trigger test | What must never happen |
| --- | --- | --- |
| `publishOn(Schedulers.parallel())` | Two identity Monos with different contexts | Returning the same username due to `ThreadLocal` |
| Concurrent HTTP requests | A and B call the same route with async responses | A receives B's tenant content or vice versa |
| Slow gateway | A times out while B succeeds | B's response data completes into A |
| Unauthenticated new subscriber | Subscribe to a protected `Mono` with no context | Reusing A's context |
| Shared cache | A populates cache, B queries with overly broad key | B receives A's data |
| Manual `.subscribe()` | Launching a pipeline detached from web exchange | Logic sees “empty” context and auto-grants access |
| Context error | `.onErrorResume` after identity lookup | Never defaults to admin or another tenant's principal |

Never use `contextWrite` with a hardcoded principal in production to “fix a lost context”; that bypasses authentication. When bridging to non-reactive APIs, use framework-supported propagation tools or pass an immutable request-scoped identity explicitly, and test for cross-talk under concurrent execution.

## 7. Dependency Failure Matrix

### 7.1. Business Dependencies: R2DBC, WebClient, Redis

| Failure mode | How to simulate in unit/integration tests | Expected behavior |
| --- | --- | --- |
| Success | `Mono.just("report:ready")` | 200 with right payload and owner |
| Empty | `Mono.empty()` | 404/503 per contract; 503 in this example |
| Runtime exception | `Mono.error(new IllegalStateException(...))` | No data returned, standardized HTTP 503 |
| Timeout | `Mono.never()` with `.timeout(...)` | Terminates within finite budget, HTTP 503 |
| Downstream HTTP 429/503 | Mock HTTP server returning matching status | No sensitive data, bounded retry/backoff per policy |
| Connection reset / DNS failure | Stub closes connection / controlled DNS failure | Error classified cleanly, no fail-open fallback |
| Malformed response | Invalid schema or type in body | Malformed JSON never treated as valid |
| Another tenant's data | Gateway intentionally returns another owner's record | Service authorization blocks and suppresses emission |
| Stale cache after revocation | Stale identity / ACL cache | Stale data never drives allow decisions |

**Note:** business caching is not authorization decision caching. A failed dependency might allow a “read-only degraded mode” for **public data** if the contract permits; access checks for sensitive resources must still hold—never write `onErrorReturn(true)` when PDP or tenant ownership fails.

When simulating timeouts, the **stub** delay must exceed the client/operation timeout. Tests should not depend on long JVM or network defaults. With real `WebTestClient`, configure `.timeout(Duration.ofMillis(...))` as needed; the test in section 5 uses 250 ms for fast verification. Pure Reactor logic can use virtual time (`StepVerifier.withVirtualTime`), though a real HTTP server's wall-clock scheduler does not switch to virtual time just because a test calls `withVirtualTime`.

### 7.2. Authentication Dependencies: IdP/JWK/Introspection

In an OAuth2 Resource Server, test the following cases **separately** from the HTTP Basic demo:

| Scenario | Setup | Expected at authentication layer |
| --- | --- | --- |
| Valid JWT, valid JWK | JWT signed by fixture private key; stub serves JWKS public key | Authentication succeeds before authorization runs |
| Expired JWT / future `nbf` | Invalid timestamp claims | Rejected; no valid authentication |
| Bad signature / `kid` mismatch | Signed by another key / wrong header | Rejected; signature untrusted |
| Wrong `iss` / `aud` | JWT claims mismatch validators | Rejected when validators are configured |
| JWKS 503 needing new key | IdP stub returns 503 | Unverified tokens never accepted |
| JWKS 503 with valid cached key | Decoder already caches trusted key | JWT may still verify; **do not** force tests to assume every request hits the IdP |
| Introspection 200 `active=true` | HTTP POST token, Basic client auth; valid JSON | Correct principal/authorities |
| Introspection 200 `active=false` | IdP marks token inactive | Rejected |
| Introspection 500/503/429 | Mock HTTP server returns error | No authenticated principal produced |
| Introspection timeout/connection reset | Network-fault stub | Never fails open |
| Wrong client secret | Endpoint returns 401/403 | Token not treated as “active”; config error recorded |

**Fundamental difference:** JWTs can be verified **locally** once public JWKs are cached; opaque tokens typically require a remote introspection call each time unless custom caching is added. Thus outbound IdP HTTP request counts differ across mechanisms. How upstream errors affect **API statuses** also depends on exception translation; test HTTP on the real app to lock down the 401/5xx contract rather than guessing.

`mockJwt()` and `mockOpaqueToken()` inject synthetic authenticated principals in `WebTestClient` tests without calling HTTP JWKS/introspection or checking cryptographic signatures. Use them to test authorization; use **real signed JWTs + real `NimbusReactiveJwtDecoder` + mock JWK server** or **real `SpringReactiveOpaqueTokenIntrospector` + mock HTTP server** when testing dependency faults.

### 7.3. A Contract Test for Introspection 503

The test below uses `MockWebServer` and the real `SpringReactiveOpaqueTokenIntrospector` (Spring Security 6.5). Add `spring-boot-starter-oauth2-resource-server` to project dependencies for this test alongside `mockwebserver` from section 4.1.

Create `src/test/java/example/securitymatrix/IntrospectionFailureContractTest.java`:

```java
package example.securitymatrix;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class IntrospectionFailureContractTest {

    @Test
    void idp503NeverProducesAnAuthenticatedPrincipal()
            throws IOException, InterruptedException {

        try (MockWebServer idp = new MockWebServer()) {
            idp.start();
            idp.enqueue(new MockResponse()
                    .setResponseCode(503)
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"error\":\"temporarily_unavailable\"}"));

            var introspector = SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(idp.url("/introspect").toString())
                    .clientId("lab-client")
                    .clientSecret("lab-secret")
                    .build();

            StepVerifier.create(introspector.introspect("opaque-lab-token"))
                    .expectError()
                    .verify();

            RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("POST", request.getMethod());
            assertEquals("/introspect", request.getPath());
        }
    }
}
```

Because `MockWebServer` binds to loopback on a dynamic port, the test needs no real IdP and stores no production credentials. Expected outcome: introspection `503` emits `onError`, producing no principal; test **PASSES**. For full coverage, add tests for `active=false`, `active=true`, Basic header/`token` form body, and end-to-end `WebTestClient` with `.opaqueToken(...)`. Never infer that a single component contract test verifies the entire `SecurityWebFilterChain`.

**Version caution:** if your project uses a Spring Security API version other than 6.5, check the introspector builder and JDK compatibility before copying. The rest of this article targets Spring Boot 3.3.x; 6.5 belongs to the Security 6.x line and is not necessarily the version managed by Boot 3.3's BOM. Keep dependency versions consistent across the codebase; never forcibly bump a subset of security modules independently.

## 8. Distinguishing Fail Closed from Returning the Right Status

**Fail closed** means when authentication or authorization cannot be verified, privileged data is never served. It **does not** mean every dependency failure must return 403:

| Failure source | Meaning | Typical appropriate handling |
| --- | --- | --- |
| Missing credentials | Unauthenticated | 401 for HTTP Basic/Bearer; OAuth2 Login may redirect |
| Wrong/expired credentials | Failed authentication | 401 Bearer/Basic per entry point |
| Valid principal missing scope | Unauthorized | 403 |
| Tenant ownership checked and failed | Not owner | 403, or 404 if policy intentionally hides existence |
| PDP fails to return verdict due to 503 | **Unable** to determine permission | Deny access; 503/5xx or policy-defined status |
| Introspection unreachable | Unable to verify opaque token | Deny access; status depends on adapter/handler |
| Report gateway fails after auth | Authorized, yet business call failed | 503/504/5xx without leaking data or secrets |
| Cached JWKS key valid and signature/claims valid | JWT verified without remote call | Proceed per approved cache policy |

Intentionally putting `onErrorReturn(true)` on an authorization predicate or `onErrorResume(e -> Mono.just(Authentication.admin))` is a severe **fail-open** flaw. Never fall back to a default tenant, never reuse a previous user's principal or cached permission verdict, and never grant access when R2DBC role queries time out.

A 401 returned by the **IdP introspection endpoint** does not automatically equal an HTTP 401 returned to the **API caller**: the two hops can map exceptions differently. Ensure you test each layer (decoder/introspector and HTTP filter) separately.

## 9. Controlled Fault-Injection Plan

A well-structured suite progresses logically without needing many live external services:

```text
Unit / StepVerifier
   -> Reactor Context per subscription; timeout/retry/mapError
   -> validate principal + tenant/owner check

Security integration / WebTestClient
   -> anonymous/role/scope/owner
   -> dependency mock: OK / error / empty / never
   -> HTTP status, body, no data leakage

Adapter contract / HTTP stub
   -> JWKS, introspection, WebClient dependency protocol
   -> 200/401/403/429/503/malformed/slow/TLS errors

End-to-end staging
   -> real proxy, IdP, TLS, R2DBC/Redis where applicable
   -> access controls and correlation across components
```

### 9.1. Invariants to Measure

- **Authorization first:** unauthorized requests must never invoke the report gateway. Verify `Mockito.verify(gateway, never()).loadReport()` in a dedicated test sending **only** unauthorized requests; avoid sharing mutable mock counters when another test already called the gateway.
- **No sensitive fallback payloads:** error responses must contain zero records, bearer tokens, passwords, connection strings, or stack traces.
- **Bounded timeouts:** a `Mono.never()` dependency must not hang requests indefinitely; tests enforce a time budget.
- **Isolation:** user A never receives user B's `sub`, `tenantId`, or payload.
- **Right layer:** invalid tokens fail before the handler; business errors occur after auth succeeds; logs distinguish error classes.
- **Bounded retries:** never retry token introspection or non-idempotent POSTs blindly; if retrying idempotent read dependencies, bound attempts and total duration. One retry can multiply traffic; test exact counts against real policy rather than assuming one.
- **Scoped caching:** authorization caches must not be shared across users/tenants; test revocation and TTLs.
- **Non-blocking event loop:** never call `.block()` or blocking JDBC inside reactive handlers; when bridging blocking code is unavoidable, isolate onto a proper scheduler while preserving context and traces.

### 9.2. A Crucial Negative Test

For `/api/admin`, testing `admin → 200` alone is **insufficient**: if a developer replaces `.hasRole("ADMIN")` with `.authenticated()`, that test still passes. Adding `alice → 403` catches the bug. For `/api/report`, `bob → 403` prevents scope loosening. For tenants, always verify **owner A reading tenant B → denied**.

### 9.3. Fixed Test Data Without Real Production Data

Use stable test usernames/tenant IDs, tokens signed with dedicated fixture keys, mock endpoints on dynamic ports, and fixed clocks when testing `exp`/`nbf`. Clean up mock HTTP servers, database containers, sessions, and caches per test. Never require live Internet IdP calls in the unit test suite.

## 10. Testing for Context Leaks Under Concurrent Load

A single `Mono.zip` test proves basic Reactor Context behavior, yet does not catch every **application shared-state** bug. Whenever an application uses caches, static fields, or custom `WebFilter`s, add concurrent HTTP tests:

1. Boot the app on `RANDOM_PORT` using two principals with different permissions and tenants.
2. Send many concurrent A/B requests via `WebTestClient` or an async HTTP client, each with its own credentials and correlation ID. Avoid a mutable global default `Authorization` header shared across threads.
3. In a stubbed service, introduce asymmetric delays (`Mono.delay`) between A and B, optionally switching schedulers with `publishOn` to force interleaving.
4. Assert each response matches the **exact** corresponding user/tenant/record; never read `lastLoggedInUser` or `currentTenant` from singleton fields.
5. Repeat with one timed-out request, one succeeding request, and one 403 request. Denied requests must never touch another user's resource.
6. Verify logs/traces preserve distinct correlation IDs without printing credentials. Run enough iterations to expose races while keeping execution time bounded.

**Subtle bug:** assigning `currentUser` to a `@Service` singleton field. Two interleaved requests can overwrite the field before the `Mono` reads it. Fix this by keeping identity in Reactor Context or immutable per-pipeline parameters, capturing needed values inside subscription-scoped lambdas rather than mutable singleton state.

### Wrong and Right Examples with `flatMap`

**Wrong – pseudocode logic, not standalone:**

```java
// Shared singleton field:
private String currentTenant;

Mono<String> load(String tenant) {
    currentTenant = tenant;
    return gateway.loadFor(currentTenant);
}
```

If `gateway.loadFor(...)` evaluates later or uses a callback reading that field, request B can overwrite A's field. The snippet also fails to verify whether the tenant belongs to the current principal.

**Right – keep tenant local and authorize inside the pipeline:**

```java
Mono<String> loadAuthorized(String requestedTenant) {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(requester -> {
                if (!requester.equals(requestedTenant)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.FORBIDDEN, "Tenant access denied"));
                }
                return gateway.loadFor(requestedTenant);
            });
}
```

The right snippet is an **illustrative code fragment** for a service holding `gateway.loadFor(...)` and the relevant imports, not a standalone runnable class. Production code verifies membership/ownership using trusted IDs and policies; comparing names in the demo simply shows the pipeline shares no mutable fields.

## 11. Common Mistakes When Assembling the Matrix

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing only 200 for admin user | Misses loosened route rules | Add regular-user → 403 and anonymous → 401 tests |
| Using `mockJwt()` and claiming JWK was tested | Skips signature and HTTP JWKS | Add real decoder tests with signed fixture JWTs and IdP stubs |
| Testing opaque tokens only for HTTP 200 | `active=false` also returns HTTP 200 | Assert introspector errors when `active=false` |
| Treating IdP 503 as invalid token | Conflates infra failure with auth failure | Separate error classification and logs; still deny access |
| Using `.onErrorReturn(true)` in policies | Fail-open | Emit error/deny rather than granting access |
| Caching principal in a singleton | User B sees User A's principal | Read Reactor Context per subscription and scope caches |
| Using `ThreadLocal` `SecurityContextHolder` in reactive flows | Null or wrong principal on event loop | Use `ReactiveSecurityContextHolder` |
| Calling `.subscribe()` inside services | Detached subscription loses request context | Compose publishers and let WebFlux subscribe |
| Calling `Thread.sleep` in reactive handlers | Blocks event loop and triggers fake timeouts | Use `Mono.delay`, async I/O, or `boundedElastic` when bridging blocking calls |
| Disabling CSRF because POST tests return 403 | Opens browser session vulnerabilities | Test CSRF explicitly and configure per architecture |
| Asserting status only without inspecting body | Secrets/tenant data can leak in error bodies | Assert response bodies and sensitive headers |
| Tests depend on production IdP or DB | Flaky tests and secret exposure risks | Use mock servers, test DBs, and fixture certificates |
| Mocking gateway while bypassing security chain | Business tests never prove 401/403 | `@SpringBootTest` + `WebTestClient` traversing filters |
| Not testing timeouts | Requests hang forever on unresponsive dependencies | Configure timeouts and fault-inject `Mono.never()` |
| Blaming roles on every 403 | CSRF or method security can produce 403 | Identify the layer and method/route first |

## 12. Metrics, QA Artifacts, and CI

A test report should record:

```text
Scenario: M09
Route: GET /api/report
Identity fixture: alice
Authorities: ROLE_USER, SCOPE_reports:read
Injected dependency state: Mono.error(IllegalStateException)
Expected HTTP status: 503
Expected sensitive body exposure: none
Observed status: [test reports result]
Outcome: PASS / FAIL
```

Every scenario needs a stable ID, route/method, role/scope, dependency state, expected HTTP response, actual observation, and assertion—not a single line saying “security tests pass.” In CI, separate fast suites (authorization, Reactor Context) from HTTP contract suites (IdP stubs, integration), and run staging E2E once environments stabilize.

Add a **sentinel negative test** whenever modifying policies: deliberately relax an admin rule on a test branch and verify the `alice → 403` test fails; that confirms the test actually catches regressions. Restrict fault injection to test/staging environments. Never publish tokens, passwords, private signing keys, or internal secrets/hosts in reports or logs. With `MockWebServer`, you may assert the Basic header against fixture values, yet never print the header to stdout.

### Checklist to Evaluate Lab Completion

- [ ] Matrix covers route × identity × scope/role × dependency state × expected status/body.
- [ ] At least three test classes exist: `WebTestClient` authorization/dependency, Reactor Context isolation, and IdP adapter contract (or equivalent).
- [ ] Anonymous, under-privileged, and authorized users are all tested on sensitive resources.
- [ ] `GET /api/me` returns the right identity for two users; concurrent subscribers never mix contexts.
- [ ] Cross-tenant negative tests exist, and caches/global fields never retain user data.
- [ ] Dependency success, exception, empty, and timeout are tested; timeouts are bounded and errors leak no sensitive data.
- [ ] JWT/opaque tests distinguish mocked auth from real signature/remote introspection checks.
- [ ] No fallback grants permissions when IdP/PDP/R2DBC fails.
- [ ] Every test produces reproducible results in CI.
- [ ] Statuses 401/403/503 are verified per authentication type without over-generalizing across architectures.

## 13. Official References

- [Spring Security 6.5 — WebFlux Security Configuration and Multiple Chains](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html).
- [Spring Security 6.5 — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html).
- [Spring Security 6.5 — Reactive Web Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/index.html).
- [Spring Security 6.5 — OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html).
- [Spring Security 6.5 — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Framework — Testing WebFlux with WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).

**Learning outcome achieved** when your tests demonstrate: *who may view which resource*, *how the API handles failed dependencies*, and *why two reactive requests cannot accidentally share each other's principal, tenant, or data*.