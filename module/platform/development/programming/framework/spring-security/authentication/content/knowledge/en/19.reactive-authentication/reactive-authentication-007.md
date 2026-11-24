# ReactiveAuthenticationManagerResolver: Selecting a Manager by Request Context

## Lesson Objectives

In **Spring Security WebFlux**, an application sometimes has to authenticate requests using **different strategies**. For example, tenant A and tenant B have separate API key stores; or a Resource Server must accept JWTs from two Identity Providers with different issuers/JWK Sets.

`ReactiveAuthenticationManagerResolver<C>` addresses that exact requirement: **selecting a ReactiveAuthenticationManager based on context**. In WebFlux HTTP, the common context is `ServerWebExchange`. The resolver picks **which component performs authentication**; the selected manager itself decides whether credentials are valid.

After this lesson, you will be able to:

1. Distinguish `ReactiveAuthenticationManagerResolver`, `ReactiveAuthenticationManager`, `ServerAuthenticationConverter`, `AuthenticationWebFilter`, and `SecurityWebFilterChain`.
2. Explain the `Mono<ReactiveAuthenticationManager>` return contract of `resolve(context)`, without confusing it with the `Mono<Authentication>` result of `authenticate(input)`.
3. Write a resolver selecting a manager by exact URL path or controlled tenant context.
4. Integrate a resolver into a runnable Spring Boot WebFlux app using Java 17+ and test with curl/WebTestClient.
5. Use `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` for a multi-issuer JWT Resource Server.
6. Spot risks when trusting unverified headers/claims, dynamically creating JWT decoders for arbitrary issuers, doing blocking I/O on the event loop, or granting authorities to the wrong tenant.

**Scope:** Spring Security 6.5.x, Spring Boot 3.5.x, Java 17+, and **Reactive WebFlux**. Servlet concepts such as `HttpSecurity`, `SecurityFilterChain`, `AuthenticationManagerResolver<HttpServletRequest>`, and `OncePerRequestFilter` are **different APIs** and must not be substituted mechanically.

## 1. Why Select a Manager per Request?

Suppose an API serves two enterprise customers:

~~~text
GET /api/alpha/me
  Authorization: Bearer <alpha credential>
  -> requires manager authenticating alpha

GET /api/beta/me
  Authorization: Bearer <beta credential>
  -> requires manager authenticating beta
~~~

If a single manager accepted every credential, the app could accidentally let an alpha key access beta resources. Selecting separate managers clarifies the boundary, yet **does not replace authorization**: once a key is authenticated, you must still verify the user/app is allowed to access the right tenant and resource.

A multi-issuer Resource Server may receive:

~~~text
JWT A: iss = https://identity.example.org/issuer-a
JWT B: iss = https://identity.example.org/issuer-b

Issuer A: signing key/JWKS, audience, and role policy A
Issuer B: signing key/JWKS, audience, and role policy B
~~~

Manager A and manager B can use separate decoders and validators. The resolver picks the right manager by context; the token must still have its **signature, issuer, audience, and expiration verified** inside the manager.

### When Should You Not Use a Resolver?

If the system has only one mechanism and one issuer, use a single `ReactiveAuthenticationManager` or standard Resource Server `jwt()` configuration. A resolver adds complexity for trust boundaries, caching, failure handling, and unit testing; use it only when the strategy must vary per request.

## 2. API Contracts of Resolver and Manager

Java contracts:

~~~java
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}

public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Both interfaces belong to `org.springframework.security.authentication`. In WebFlux:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver;

Mono<ReactiveAuthenticationManager> managerMono =
    resolver.resolve(exchange);
~~~

| Component | Input | Output | Responsibility |
| --- | --- | --- | --- |
| `ServerAuthenticationConverter` | `ServerWebExchange` | Untrusted `Mono<Authentication>` | Extracts credentials from the request |
| `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Request context | `Mono<ReactiveAuthenticationManager>` | Picks which manager will check |
| `ReactiveAuthenticationManager` | Authentication request token | `Mono<Authentication>` | Verifies credentials or rejects |
| `AuthenticationWebFilter` | Exchange and converter/resolver/manager | Response or continues filter chain | Coordinates authentication, failure/success |
| `SecurityWebFilterChain` | Exchange | Matching WebFilter chain | Route protection and authorization policy |

**Key point:** `resolve()` returns **a manager**, not a login result. Only after the manager runs `authenticate()` successfully do you have a trusted `Authentication`.

### Three Reactive Result Forms

- `Mono.just(manager)`: a manager was selected.
- `Mono.error(exception)`: invalid context or the system cannot select a strategy.
- `Mono.empty()`: no manager selected. **Do not treat empty as allowing access**; behavior depends on the component using the resolver, and authorization must fail closed.

Similarly, for a manager:

- `Mono.just(authenticatedResult)`: authentication succeeded.
- `Mono.error(AuthenticationException)`: invalid credentials or disallowed status.
- `Mono.empty()`: manager did not produce a result; never use as a way to signal “authentication succeeded”.

Never flip an input token from `authenticated=false` to true inside the converter merely because a header exists. Every principal and authority in the result must be verified/issued by the manager from a trusted server-side source.

## 3. Request Flow in Spring Security WebFlux

~~~text
HTTP request
      |
      v
SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      +--> ServerAuthenticationConverter
      |        -> Mono<Authentication> (untrusted)
      |
      +--> ReactiveAuthenticationManagerResolver<ServerWebExchange>
      |        -> read request context
      |        -> select Mono<ReactiveAuthenticationManager>
      |
      +--> selectedManager.authenticate(input)
      |        -> verify credentials, tenant, account status
      |
      +---- success: trusted Authentication
      |        -> ReactiveSecurityContextHolder (Reactor Context)
      |        -> authorization and handler
      |
      +---- failure: AuthenticationException
               -> failure handler / 401
~~~

`AuthenticationWebFilter` has a constructor taking `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. The filter also takes a `ServerAuthenticationConverter` and a matcher deciding which requests attempt authentication.

For OAuth2 Resource Server, the `ServerHttpSecurity.oauth2ResourceServer(...)` DSL provides `authenticationManagerResolver(...)` to plug in a resolver dedicated to bearer tokens.

### ReactiveSecurityContextHolder Differs from Servlet ThreadLocal

Spring Security WebFlux uses the Reactor Context and `ReactiveSecurityContextHolder` to propagate authentication state across the reactive chain. You should not read state via `SecurityContextHolder.getContext()` and assume it survives across every async step like Servlet code.

Inside handlers, you can accept `Mono<Principal>` or use Spring Security's reactive APIs. Once a request finishes, never retain a `ServerWebExchange` reference inside a singleton/cache.

## 4. Where Is It Safe to Select Context From?

### 4.1. Server-Configured Exact Paths

A resolver can choose the alpha manager for `/api/alpha/me` and the beta manager for `/api/beta/me`. Exact matching keeps the learning model clear and reduces unintended fallbacks.

However, **the URL does not prove the caller is tenant alpha**. The alpha manager must actually verify alpha credentials, and authorization must protect alpha's resources.

### 4.2. The X-Tenant Header

~~~http
GET /api/data HTTP/1.1
X-Tenant: beta
Authorization: Bearer some-client-supplied-value
~~~

`X-Tenant` is client input. It can serve as a **hint for selecting a manager**, provided you:

1. Allow only tenants in a server-managed allowlist/registry.
2. Verify credentials with the matching manager.
3. Bind the verified principal, issuer, audience, and tenant.
4. Check access permissions for that tenant's resources.

If the header is injected by a reverse proxy, trust it only when the proxy **strips/overwrites client-sent headers** and requests reach the backend exclusively through the trusted path.

### 4.3. Host, Forwarded Headers, and Subdomains

A host like `alpha.example.com` can select a tenant. Yet `Host`, `X-Forwarded-Host`, and `Forwarded` headers can be spoofed if ingress/proxies do not sanitize them.

Normalize origins/trusted proxies, map hosts to tenants server-side, enforce an allowlist, and test spoofing. Never turn an arbitrary client-requested host into an issuer/JWKS URL.

### 4.4. Unverified Issuer in a JWT

A JWT contains an `iss` claim readable before signature verification. When using issuer to pick a decoder, `iss` is only an **untrusted routing hint**.

Safe approach:

~~~text
Read JWT iss (untrusted)
        |
        v
Compare against configured TRUSTED issuers
        |
        +-- absent -> REJECT
        |
        +-- present -> select corresponding manager
                    |
                    v
             verify JWT signature
             check iss/exp/nbf/aud
                    |
                    v
             issue trusted Authentication
~~~

**Never instantiate decoders for arbitrary `iss` values sent by clients.** An attacker could stand up their own Authorization Server, issue valid JWTs signed with their keys, and get your API to accept them—or force your backend to fetch internal URLs via discovery/JWKS (**SSRF**).

## 5. Runnable Java 17+ Sample: Two Managers by Exact Route

The example below avoids depending on an external JWT issuer so you can exercise the resolver directly:

- `GET /api/alpha/me` uses demo key `alpha-demo-key`.
- `GET /api/beta/me` uses demo key `beta-demo-key`.
- The resolver inspects the **exact path** and picks a server-initialized manager.
- The converter reads `Authorization: Bearer` and creates an `unauthenticated` token.
- The corresponding manager verifies the credential and builds a trusted principal/authority.
- The API uses **NoOpServerSecurityContextRepository**: subsequent requests must supply the key again.
- Wrong, missing, or cross-tenant keys are rejected.

**Use hardcoded keys for training only.** Production requires high-entropy randomly generated keys, secure verifier storage, TLS, rotation/revocation, quotas/rate limits, and auditing. For real JWTs, prefer OAuth2 Resource Server over manual Bearer string checks.

### 5.1. Gradle Project

~~~text
reactive-resolver-demo/
  settings.gradle
  build.gradle
  src/main/java/example/reactive/ResolverDemoApplication.java
  src/test/java/example/reactive/ResolverDemoApplicationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-resolver-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add `spring-boot-starter-web` to the demo. When both MVC and WebFlux starters are present, Spring Boot defaults to **Servlet** web application type, causing confusion between `HttpSecurity` and `ServerHttpSecurity`.

### 5.2. Complete Java File

`src/main/java/example/reactive/ResolverDemoApplication.java`:

~~~java
package example.reactive;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ResolverDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResolverDemoApplication.class, args);
    }

    private static ReactiveAuthenticationManager managerFor(
            String expectedKey, String principal, String authority) {

        return request -> Mono.defer(() -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            Object credentials = request.getCredentials();
            if (!(credentials instanceof String supplied)) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            // Illustrative: production must not hardcode API keys.
            boolean valid = MessageDigest.isEqual(
                expectedKey.getBytes(StandardCharsets.UTF_8),
                supplied.getBytes(StandardCharsets.UTF_8)
            );

            if (!valid) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    null,
                    List.of(new SimpleGrantedAuthority(authority))
                );

            return Mono.just(verified);
        });
    }

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
            authenticationManagerResolver() {

        ReactiveAuthenticationManager alpha =
            managerFor("alpha-demo-key",
                "svc-alpha", "SCOPE_alpha.read");

        ReactiveAuthenticationManager beta =
            managerFor("beta-demo-key",
                "svc-beta", "SCOPE_beta.read");

        return exchange -> {
            String path = exchange.getRequest().getPath()
                .pathWithinApplication().value();

            // Do not take trusted tenant/role from client headers.
            return switch (path) {
                case "/api/alpha/me" -> Mono.just(alpha);
                case "/api/beta/me" -> Mono.just(beta);
                default -> Mono.error(
                    new BadCredentialsException("Unsupported route")
                );
            };
        };
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                resolver) {

        AuthenticationWebFilter authenticationWebFilter =
            new AuthenticationWebFilter(resolver);

        ServerAuthenticationConverter converter = exchange -> {
            List<String> authValues = exchange.getRequest()
                .getHeaders().getOrEmpty(HttpHeaders.AUTHORIZATION);

            if (authValues.isEmpty()) {
                return Mono.empty();
            }
            if (authValues.size() != 1) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            String header = authValues.get(0);
            if (!header.regionMatches(true, 0, "Bearer ", 0, 7)) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            String rawKey = header.substring(7);
            if (rawKey.isBlank()
                    || rawKey.length() > 256
                    || rawKey.indexOf(' ') >= 0) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "incoming", rawKey
                )
            );
        };

        authenticationWebFilter.setServerAuthenticationConverter(converter);
        authenticationWebFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                "/api/alpha/me", "/api/beta/me"
            )
        );
        authenticationWebFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );
        authenticationWebFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        http
            .httpBasic(spec -> spec.disable())
            .formLogin(spec -> spec.disable())
            // Only for header-only API demo not relying on cookies.
            // Real apps need a corresponding CSRF threat model.
            .csrf(spec -> spec.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/alpha/me")
                    .hasAuthority("SCOPE_alpha.read")
                .pathMatchers("/api/beta/me")
                    .hasAuthority("SCOPE_beta.read")
                .anyExchange().denyAll()
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
                )
            )
            .addFilterAt(authenticationWebFilter,
                SecurityWebFiltersOrder.AUTHENTICATION);

        return http.build();
    }

    @RestController
    public static class Api {
        @GetMapping("/api/{tenant}/me")
        Mono<Map<String, String>> me(
                @PathVariable String tenant,
                Mono<Principal> principal) {
            return principal.map(p -> Map.of(
                "tenant", tenant,
                "principal", p.getName()
            ));
        }
    }
}
~~~

### 5.3. Explaining the Actual Execution Path

**Step 1 — HTTP request:** the caller invokes `/api/alpha/me` and sends `Authorization: Bearer alpha-demo-key`.

**Step 2 — Converter:** parses only the header, bounds its size, and builds `UsernamePasswordAuthenticationToken.unauthenticated`. The string `incoming` is merely a label on the request token, not a verified principal.

**Step 3 — Resolver:** reads the exchange's exact path and returns `Mono.just(alpha)`. Never treats the token value itself as proof to select another tenant or instantiate an arbitrary manager.

**Step 4 — Manager:** the alpha manager checks the key. If it matches, it returns a new result with principal `svc-alpha` and authority `SCOPE_alpha.read`. If it does not match, it returns `Mono.error(new BadCredentialsException(...))`.

**Step 5 — Filter:** places the Authentication result into the reactive context, or uses the failure handler to return 401.

**Step 6 — Authorization:** the alpha endpoint requires the authority granted by the alpha manager. A valid result missing that scope would still be rejected.

**Step 7 — Next request:** no login session is persisted via `NoOpServerSecurityContextRepository`. Every request must send fresh credentials.

**Why return Mono.defer?** It defers running the check logic until subscription. However, `Mono.defer` does not make blocking work non-blocking; in this demo every operation is a tiny in-memory check.

### 5.4. Launching and Testing with curl

From a project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Defaults to `http://localhost:8080` if the port is unchanged.

**Alpha key calling alpha:**

~~~bash
curl -i -H 'Authorization: Bearer alpha-demo-key' \
  http://localhost:8080/api/alpha/me
~~~

Expect **HTTP 200**, JSON response with `tenant=alpha` and `principal=svc-alpha`. Example:

~~~json
{"tenant":"alpha","principal":"svc-alpha"}
~~~

JSON field order may vary; do not write tests comparing raw JSON strings literally unless needed.

**Beta key calling beta:**

~~~bash
curl -i -H 'Authorization: Bearer beta-demo-key' \
  http://localhost:8080/api/beta/me
~~~

Expect 200 with `tenant=beta` and `principal=svc-beta`.

**Alpha key calling beta:**

~~~bash
curl -i -H 'Authorization: Bearer alpha-demo-key' \
  http://localhost:8080/api/beta/me
~~~

Expect **401**, because the beta manager does not recognize alpha's credential.

**Missing header:**

~~~bash
curl -i http://localhost:8080/api/alpha/me
~~~

Expect **401**. The converter emits no Authentication, and authorization protects the endpoint.

**Non-Bearer header:**

~~~bash
curl -i -H 'Authorization: NotBearer something' \
  http://localhost:8080/api/alpha/me
~~~

Expect **401**.

**Stateless:** after a valid alpha request, call alpha again without headers. The second request must still be rejected rather than inheriting Authentication.

### 5.5. WebTestClient Integration Tests

Create `src/test/java/example/reactive/ResolverDemoApplicationTest.java`:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ResolverDemoApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void alphaAcceptsOnlyItsCredential() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("alpha")
            .jsonPath("$.principal").isEqualTo("svc-alpha");
    }

    @Test
    void betaAcceptsOnlyItsCredential() {
        client.get().uri("/api/beta/me")
            .header("Authorization", "Bearer beta-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta")
            .jsonPath("$.principal").isEqualTo("svc-beta");
    }

    @Test
    void alphaCredentialIsRejectedByBetaManager() {
        client.get().uri("/api/beta/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingCredentialIsRejected() {
        client.get().uri("/api/alpha/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void invalidCredentialIsRejected() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer wrong-key")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void laterRequestDoesNotReuseAuthentication() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/alpha/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

There are **6 @Test methods**. When they pass, Gradle prints **BUILD SUCCESSFUL**; the HTML report normally lives at `build/reports/tests/test/index.html`.

These tests exercise the **real** converter, resolver, managers, and SecurityWebFilterChain rather than mocking a manager that always succeeds. Verifying “alpha key fails on beta” matters more than merely asserting `resolve(exchange)` returns a non-null manager.

**Limitations:** the example has no JWT signer, IdP, or real database; it demonstrates dynamic manager selection rather than replacing production JWT signature/issuer/audience tests or secret stores.

## 6. Real-World Configuration: Multi-Issuer JWT with JwtIssuerReactiveAuthenticationManagerResolver

When a Spring Security WebFlux Resource Server accepts JWTs from two trusted issuers, there is no need to hand-write parsing/JWS verification.

Add the Resource Server dependency to your WebFlux project:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

**Replace the custom AuthenticationWebFilter demo above**—do not keep two filters processing `Authorization: Bearer` without explicitly designing their order.

Configuration excerpt in a Spring Configuration class:

~~~java
@Bean
SecurityWebFilterChain resourceServerChain(ServerHttpSecurity http) {

    JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(
                "https://identity.example.org/issuer-a",
                "https://identity.example.org/issuer-b"
            );

    http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver)
        );

    return http.build();
}
~~~

Typical imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
~~~

This is **integration code**, not a self-running application class. You need real Issuer Metadata/JWKS endpoints, valid JWTs from those issuers, the Resource Server dependency, and matching Spring Boot configuration.

### 6.1. Multi-Issuer Mechanism

`JwtIssuerReactiveAuthenticationManagerResolver`:

1. Extracts the Bearer token from ServerWebExchange.
2. Reads `iss` as a **hint to select the strategy**.
3. Matches the issuer against the **trusted issuers** list.
4. Creates/selects the matching `JwtReactiveAuthenticationManager`.
5. The manager/decoder verifies the JWT signature and claims.
6. The security chain runs authorization against the authenticated result.

Calling `fromTrustedIssuers(...)` is the critical anchor in this model: never accept arbitrary unknown issuers. Spring Security 6.5 notes that per-issuer managers can be created **lazily** on the first request, avoiding coupling app startup to every IdP being online immediately.

**Remember:** an `iss` string inside an unverified JWT **does not prove** that issuer is trustworthy. The allowlist decides which decoder may be used; after that, signature, `iss`, expiration, audience, and policy must still be verified.

### 6.2. Audience Validation Is Separate from Issuer Validation

For example, a token is validly signed by issuer A yet contains:

~~~text
iss = https://identity.example.org/issuer-a
aud = payment-service
exp = still valid
signature = valid
~~~

If this API is `inventory-service` and expects that audience, that token **must not be authorized**, even though issuer A is allowlisted. Configure an appropriate `OAuth2TokenValidator<Jwt>` on each decoder, or configure Resource Server/BOM audience validation in your environment.

When a manager is selected per issuer, enforce policy:

- Exact `iss`.
- Trusted signing/JWS algorithm and public keys.
- `exp`, `nbf`, and reasonable clock skew.
- `aud` and potentially token type/client binding.
- Per-issuer scope/role mapping that never exceeds the verified tenant.

### 6.3. Dynamic Issuers and SSRF

Spring Security lets you pass a resolver keyed by issuer string:

~~~java
// Illustrative code; trustedManagers is a server-managed Map.
ReactiveAuthenticationManagerResolver<String> lookup =
    issuer -> Mono.justOrEmpty(trustedManagers.get(issuer));

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(lookup);
~~~

**Look up only in a server-managed map/registry.** Never construct a new `ReactiveJwtDecoder` from an arbitrary URL supplied by the token:

~~~java
// UNSAFE if untrustedIssuer comes from an unverified JWT:
ReactiveJwtDecoders.fromIssuerLocation(untrustedIssuer);
~~~

There are two classes of risk: attackers trick the server into fetching arbitrary URLs (**SSRF**), and attackers stand up their own valid issuer so the system accepts untrusted JWTs.

Dynamic tenants require a clear lifecycle: who can add/remove issuers, configuration versioning, cache eviction, manager count caps, JWKS rotation, timeouts, and metrics. If an issuer is removed from the trust store while a cached manager remains, the app must enforce consistent invalidation.

### 6.4. Supporting Both JWTs and Opaque Tokens in One App

Some tenants issue JWTs while others issue opaque tokens requiring introspection. The resolver can pick managers with different implementations.

Never distinguish token types solely by **dot count** or strings resembling a JWT: clients can craft arbitrary strings. Choose the strategy from a **constrained context/tenant**, then run full validation. For opaque tokens, validate the introspection response and scopes; for JWTs, verify the cryptographic signature and claims.

## 7. Resolver vs. Multiple SecurityWebFilterChains

An architecture may choose:

**Approach A — one SecurityWebFilterChain + resolver:** suitable when multiple tenants share the same Bearer authentication filter type but differ in manager/JWT issuer.

**Approach B — multiple SecurityWebFilterChains:** suitable when APIs and web UIs have completely different mechanisms and policies—for instance, stateless Bearer APIs alongside a form-login/cookie web UI with CSRF and sessions.

Directional template (not a standalone class):

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(resource -> resource
            .authenticationManagerResolver(apiResolver)
        )
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain web(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Variables and imports like `apiResolver`, `@Order`, and `Customizer` must be declared. This is an **organizational template**; with multiple chains, ensure Spring injects builders with proper lifecycles, and test `securityMatcher` and chain ordering. Never copy into an existing app without checking which chain actually handles each URL.

**Key difference:** a resolver swaps the *manager*, but does not automatically alter CSRF, sessions, exception handlers, or chain-wide request matchers. When those policies also differ, multiple chains are cleaner.

## 8. Why Never Block the Event Loop?

`Mono` does not turn a blocking API into a non-blocking one.

Wrong:

~~~java
// blockingLookup() runs immediately, potentially blocking the event loop thread.
return Mono.just(blockingLookup(tenant));
~~~

If the config store has a reactive API, use reactive operators:

~~~java
return reactiveRepository.findByTenant(tenant)
    .map(config -> managerFactory.forTrustedConfig(config));
~~~

This is an **illustrative snippet**: the repository and factory must be defined, and the factory should cache/reuse managers appropriately. When only JDBC/blocking APIs exist, use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` for bounded isolation with timeouts, circuit breakers, and metrics instead of `block()`.

Never instantiate a fresh decoder/JWK client on every request; separate tenant/issuer management from the hot path and use bounded caches with invalidation.

## 9. Distinguishing WebFlux and Servlet

| Servlet | WebFlux reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `AuthenticationManagerResolver<HttpServletRequest>` | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` |
| `Filter` / `OncePerRequestFilter` | `WebFilter` / `AuthenticationWebFilter` |
| `SecurityContextHolder` typically thread-local | `ReactiveSecurityContextHolder` via Reactor Context |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |

Never use `ThreadLocal` to carry tenant state across reactive stages. When business context must travel through the chain, use the Reactor Context or proper WebFlux mechanisms, and ensure untrusted request data never becomes security authority.

## 10. HTTP Statuses and Failure Branches

| Scenario | Typical result | Notes |
| --- | --- | --- |
| No credentials sent, endpoint requires auth | **401** | Unauthenticated |
| Wrong API key sent | **401** | Rejected by selected manager |
| Alpha key sent to beta | **401** | Must not fall back to alpha |
| Valid credentials lacking required scope | **403** | Rejected by authorization |
| JWT issuer not allowlisted | **401** | No trusted manager found |
| JWT fails signature/iss/exp/aud | **401** | Rejected by JWT decoder/manager |
| Tenant config backend error | Typically **5xx/503** per handler | Must not fail open |
| Disallowed URL | 403 or 404 per chain/router | Must not return resource |
| Duplicate/malformed Authorization header | **401** | Not parsed into a trusted token |

In a real OAuth2 Resource Server, the entry point can send `WWW-Authenticate: Bearer ...` per RFC; replacing it with `HttpStatusServerEntryPoint` as in the demo returns a plain status only. Do not break protocol headers if API clients depend on them.

## 11. Security Traps and Programming Bugs

### 11.1. Letting the Client Pick an Issuer and Instantiating a Decoder

This is **SSRF + attacker-controlled issuer trust**. Only build/select managers from a server-side allowlist, never from an arbitrary URL inside a JWT.

### 11.2. Treating a Header Role as a GrantedAuthority

`X-Role: ADMIN` does not prove the user is an admin. Converters must never build trusted tokens carrying client-supplied authorities.

### 11.3. Skipping aud Validation

A trusted issuer's signature only proves that issuer signed the token; it does not prove the token was issued for your API. Validate audience and token purpose.

### 11.4. Falling Back to a Weak Manager

If a tenant is not found, never fall back to a default manager accepting another credential type. Fail closed.

### 11.5. Wrapping Blocking JDBC in Mono.just

Calling a blocking query still stalls the event-loop even though the result is wrapped in a Mono. Use a reactive client or bounded `boundedElastic` when necessary.

### 11.6. Caching Results by Raw Token

Never store Bearer secrets in maps or logs. Cache strategies by trusted issuer/tenant registry; if caching token validation, enforce expiry, revocation, and memory bounds.

### 11.7. Trusting Internet Host Headers as Internal Truth

Control `Host` and `Forwarded` at the proxy; never let clients route themselves to an admin manager via a header alone.

### 11.8. Manager Setting Authentication=true Before Checking

Credential parsing is not authentication. Build a trusted token only after verifying the key/JWT and checking user/tenant status.

### 11.9. Skipping Cross-Tenant and Missing-Credential Tests

Testing only the alpha→alpha happy path can miss an alpha key working on beta. Negative-path tests are mandatory.

### 11.10. Using a WebFlux Filter While Reading Servlet SecurityContextHolder

In WebFlux, Authentication lives in the reactive context; use `ReactiveSecurityContextHolder` or reactive handler arguments.

### 11.11. Creating a New JWT Manager per Request

JWK discovery can introduce latency or DoS risk. Cache per trusted issuer, bound concurrent initialization, and handle outages.

### 11.12. Tenant Mismatch in Query/Body

The resolver may pick the right manager by path, yet a controller reads `tenantId` from JSON to query another tenant's database. Domain/service authorization must compare the verified tenant against the target resource.

## 12. Production Testing Strategy

| Test | What to verify |
| --- | --- |
| Resolver picks alpha from exact path | Does not pick beta |
| Resolver picks beta from exact path | Does not pick alpha |
| Alpha key on beta | Rejected |
| Missing/malformed/duplicate Authorization | Does not produce trusted Authentication |
| Unknown path/tenant | Fails closed |
| Authenticated with wrong authority | 403 |
| Subsequent request without header | Does not inherit context |
| Trusted JWT issuer A/B | Picks matching decoder |
| Unregistered JWT issuer | 401 and never calls arbitrary JWKS URL |
| JWT A signed with B's key | Rejected |
| JWT with wrong aud/exp/nbf | Rejected |
| Dynamic issuer add/remove | Cache/trust revocation works properly |
| Tenant configuration store down | Never falls back to success |
| Multi-chain routing | Right chain handles URL |

To test multi-issuer JWTs, spin up **two mock JWK Set servers/issuers with distinct key pairs**, mint genuinely signed test JWTs, and test audience, issuer, and key rotation. Never treat successful Base64 payload decoding as proof a token was verified.

To unit-test the resolver path alone, you can use `MockServerWebExchange`:

~~~java
// Illustrative code inside a JUnit test with an existing resolver bean.
MockServerWebExchange exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/alpha/me")
);

StepVerifier.create(resolver.resolve(exchange))
    .assertNext(manager -> assertNotNull(manager))
    .verifyComplete();
~~~

This test proves only that *a* manager was resolved, **not that it is the right alpha manager** unless you verify its identity or run it with alpha credentials. That is why the integration tests in Section 5.5 validate end-to-end behavior.

## 13. Pre-Production Checklist

- [ ] Clearly justify using a resolver over a single manager or multiple chains.
- [ ] Request context sources have been reviewed for trust boundaries.
- [ ] Manager/issuer allowlist exists and missing tenants are handled safely.
- [ ] Converter produces untrusted Authentication and never assigns roles from headers.
- [ ] Manager verifies credentials, issuer, signature, aud, exp/nbf, tenant, and account status.
- [ ] Authorization checks resource ownership, not just tenant routes.
- [ ] Resolver performs no blocking I/O on the event loop.
- [ ] Never creates unbounded managers/decoders per request; uses caching and invalidation.
- [ ] 401/403/5xx are distinct; never fails open on backend errors.
- [ ] NoOp/reactive security context repository aligns with session policy.
- [ ] Never logs raw Authorization headers, tokens, or secrets.
- [ ] Tests cover cross-tenant access, untrusted issuers, invalid JWT signatures, audience, and key rotation.
- [ ] Separates WebFlux APIs from Servlet APIs cleanly when adapting examples.
- [ ] Protects CSRF according to how clients actually transmit credentials; never disables it merely because endpoints are JSON.

## 14. Self-Check

**Question 1.** What does `resolve(exchange)` return?  
**Answer:** `Mono<ReactiveAuthenticationManager>`. It does not create a successful Authentication itself.

**Question 2.** Why must an alpha key sent to `/api/beta/me` be rejected?  
**Answer:** The URL selects the beta manager, which rejects the alpha key; there is no fallback to alpha.

**Question 3.** Is the `X-Tenant` header proof that the user belongs to that tenant?  
**Answer:** No, it is untrusted input. Credentials and tenant binding must be verified in the manager/authorization.

**Question 4.** Is it safe to build a JWT decoder from any `iss` inside a token?  
**Answer:** No, that risks accepting attacker-controlled issuers and SSRF. Use an allowlist of trusted issuers.

**Question 5.** Should a properly signed JWT with another API's audience be accepted?  
**Answer:** No when the API requires its own audience; `aud` must be validated in addition to signature/issuer.

**Question 6.** Is `Mono.just(jdbc.find(...))` non-blocking?  
**Answer:** No. The JDBC call executes before the Mono is created and can block the event loop.

**Question 7.** When are multiple SecurityWebFilterChains better than a resolver?  
**Answer:** When not only the manager, but also mechanisms, cookies, CSRF, sessions, and authorization differ between APIs and web UIs.

**Question 8.** Why must WebTestClient test missing credentials and cross-tenant requests?  
**Answer:** Because a resolver passing the happy path does not prove invalid credentials or other tenants are blocked.

**Question 9.** Is `ReactiveSecurityContextHolder` the same as Servlet's ThreadLocal?  
**Answer:** No. It uses the Reactor Context to carry Authentication across the reactive pipeline.

**Question 10.** When the config store fails, should you fall back to a default manager for all tenants?  
**Answer:** No. Fail closed and report the error properly to avoid lowering security guarantees.

## Official References

- [Spring Security 6.5 — OAuth2 Resource Server Multi-tenancy (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security 6.5 — JWT Resource Server (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
