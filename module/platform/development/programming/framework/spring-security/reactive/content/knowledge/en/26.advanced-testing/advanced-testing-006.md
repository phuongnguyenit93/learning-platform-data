# Testing mockJwt(), mockOpaqueToken(), and Authority Mapping in Spring Security Reactive Resource Server

## Goals and scope

In Spring WebFlux, a Resource Server typically protects APIs with JWT or opaque bearer tokens. This lesson focuses on **testing simulated authentication and authorization decisions** with `WebTestClient`, rather than requiring a live Authorization Server for every test.

After this lesson, you will be able to:

- Use **mockJwt()** to create a `JwtAuthenticationToken` for a request and test permissions derived from `scope`/`scp` claims or specified authorities.
- Use **mockOpaqueToken()** to create a `BearerTokenAuthentication` with explicit attributes and authorities.
- Distinguish **claims/attributes** (token data) from **GrantedAuthority** (actual permissions checked by `hasAuthority`/`hasRole`).
- Properly test all three states: unauthenticated → HTTP 401; authenticated without permission → HTTP 403; sufficient permission → HTTP 200 or the endpoint's success status.
- Know when to test the real **ReactiveJwtDecoder**, **ReactiveOpaqueTokenIntrospector**, or converter instead of relying solely on mock authentication.

## 1. How does a Resource Server turn a token into authorities?

With a real JWT, the general pipeline is:

~~~text
Authorization: Bearer <JWT>
    → ServerAuthenticationConverter / AuthenticationWebFilter
    → ReactiveJwtDecoder (verifies signature, issuer, exp, ...)
    → Jwt → Authentication (JWT authentication converter)
    → authorities
    → SecurityWebFilterChain / method security
    → 200 / 403
~~~

With an opaque token, the Resource Server sends the token value to an introspection service (or a custom introspector implementation); the result is mapped into principal, attributes, and authorities before authorization is evaluated.

**By default with JWTs**, Spring Security reads `scope` or `scp` and prefixes each scope with **SCOPE_**. For example:

| Claim/token data | Authority used for authorization | Check expression |
| --- | --- | --- |
| scope = "reports.read reports.write" | SCOPE_reports.read, SCOPE_reports.write | hasAuthority("SCOPE_reports.read") |
| scp = ["reports.read"] | SCOPE_reports.read | hasAuthority("SCOPE_reports.read") |
| roles = ["ADMIN"] | Does not automatically become ROLE_ADMIN under default JWT config | Requires custom converter or explicit test authorities |
| permissions = ["reports.read"] | Does not automatically become an authority under default JWT config | Requires converter for the permissions claim |

**hasAuthority("X")** matches the exact authority string `X`; **hasRole("ADMIN")** normally checks for authority **ROLE_ADMIN**. `SCOPE_reports.read`, `ROLE_ADMIN`, and `reports.read` are three different strings. A JWT claim containing the text "ADMIN" does not automatically mean the caller holds `ROLE_ADMIN`.

In a real application, the same endpoint may check permissions both in `SecurityWebFilterChain` and in method security (such as `@PreAuthorize`). Tests must initialize the exact configuration under test; running a controller completely isolated from Spring Security can produce misleading results.

## 2. Two mock tools in WebFlux

| Item | mockJwt() | mockOpaqueToken() |
| --- | --- | --- |
| API location | SecurityMockServerConfigurers.mockJwt | SecurityMockServerConfigurers.mockOpaqueToken |
| Simulated Authentication | JwtAuthenticationToken | BearerTokenAuthentication |
| Data customized in tests | .jwt(builder -> ...), .authorities(...) | .attributes(map -> ...), .authorities(...), .principal(...) |
| Default | JWT with sub=user and scope=read; has SCOPE_read | Principal/attributes with sub=user; has SCOPE_read |
| Suited for | Endpoints using `@AuthenticationPrincipal Jwt`, JWT scopes, authorization | Endpoints using `BearerTokenAuthentication`/opaque principal, post-introspection authorities |
| Does NOT check | Signature, JWK, issuer, expiration via real decoder | HTTP introspection, client credentials, active status from provider |

Both are **WebTestClientConfigurer**s. Core syntax:

~~~java
client.mutateWith(mockJwt())
      .get().uri("/reports")
      .exchange();

client.mutateWith(mockOpaqueToken())
      .get().uri("/reports")
      .exchange();
~~~

These calls place a test authentication into the WebFlux request context. They **do not create a validly signed bearer token** and do not ensure the real token verification flow ran. In particular, in opaque tests, adding an attribute via `.attributes(...)` **does not mean authorities are automatically recomputed**; set `.authorities(...)` when you want to control the permissions granted by introspection.

## 3. Dependencies and wiring WebTestClient with Spring Security

With Spring Boot 3.x and Java 17+, a WebFlux Resource Server project can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

test {
    useJUnitPlatform()
}
~~~

The Gradle snippet above goes in the `build.gradle` of a project configured with the corresponding Spring Boot / Dependency Management plugins. It is the **dependencies and test task** portion, not a standalone complete `build.gradle`.

When constructing the client manually, bind security to the ApplicationContext:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

Static imports:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
~~~

If using a test slice, test annotation, or auto-configured `WebTestClient`, still make sure security filters/method security are actually present in the test context. **WebTestClient.bindToController(...)** does not automatically bring in the application's full `SecurityWebFilterChain`.

## 4. Complete example: 401, 403, 200 with both mocks

The standalone example below tests **authorization in WebFlux** against the same two endpoints. `TestConfig` creates a real `SecurityWebFilterChain` while intentionally omitting a JWT decoder or opaque introspector: the goal is to demonstrate authorization rules once mock authentication is supplied. Section 7 shows how to step up to integration tests running through real bearer token handling.

File: src/test/java/example/security/ReactiveAuthorizationTest.java

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.EnableWebFlux;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = ReactiveAuthorizationTest.TestConfig.class)
class ReactiveAuthorizationTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void missingAuthenticationReturns401() {
        client.get().uri("/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void jwtScopeClaimGrantsRead() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("sub", "alice")
                               .claim("scope", "reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void jwtWrongAuthorityReturns403() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.write")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void opaqueWithExplicitReadAuthorityReturns200() {
        client.mutateWith(mockOpaqueToken()
                .attributes(attrs -> attrs.put("sub", "bob"))
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void opaqueAttributeAloneDoesNotGrantReadAuthority() {
        client.mutateWith(mockOpaqueToken()
                .attributes(attrs -> attrs.put("scope", "reports.read")))
                .get().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postRequiresWriteAuthority() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
                .post().uri("/reports")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.write")))
                .post().uri("/reports")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Configuration
    @EnableWebFlux
    @EnableWebFluxSecurity
    static class TestConfig {
        @Bean
        SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
            return http
                    .csrf(ServerHttpSecurity.CsrfSpec::disable)
                    .authorizeExchange(exchanges -> exchanges
                            .pathMatchers(HttpMethod.GET, "/reports")
                                .hasAuthority("SCOPE_reports.read")
                            .pathMatchers(HttpMethod.POST, "/reports")
                                .hasAuthority("SCOPE_reports.write")
                            .anyExchange().denyAll())
                    .build();
        }

        @Bean
        ReportsController reportsController() {
            return new ReportsController();
        }
    }

    @RestController
    static class ReportsController {
        @GetMapping("/reports")
        public Mono<String> read() {
            return Mono.just("report");
        }

        @PostMapping("/reports")
        public Mono<String> write() {
            return Mono.just("created");
        }
    }
}
~~~

Run the tests in a Gradle project declaring the dependencies from Section 3:

~~~bash
./gradlew test --tests example.security.ReactiveAuthorizationTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.ReactiveAuthorizationTest
~~~

Expected result: **6 tests PASS**; the program prints no fixed stdout, so do not assume a specific console line. HTTP statuses are asserted directly in each test.

Why **CSRF is disabled** in the example: we want POST requests to succeed or fail based on authority, not missing CSRF tokens. In applications using sessions/cookies, evaluate CSRF against your real threat model; do not copy that config change blindly.

Key point: even though both mocks work in this security test context, it **does not prove the application has enabled both JWT and opaque Resource Server modes**. Production normally selects a token type per its contract with the Authorization Server; test each mode against its real configuration.

## 5. Mapping JWT authorities from scope/scp and custom claims

### 5.1. Testing default scopes

For JWTs, **mockJwt().jwt(...)** accepts a `Jwt.Builder` customizer. With `scope="reports.read"` as in the example above, default `mockJwt` applies the rule generating `SCOPE_reports.read`. You can test empty permissions by removing the default scope:

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claims(claims -> claims.remove("scope"))))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isForbidden();
~~~

Or set the desired authorities directly:

~~~java
client.mutateWith(mockJwt()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("ROLE_AUDITOR")))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

**.authorities(...)** represents the already-mapped permissions, not the claim. If a test assigns `SCOPE_reports.read` directly, it only verifies the rule; it **does not test custom claim-to-authority conversion code**.

### 5.2. Custom permissions claim: share the converter with production

Suppose the Identity Provider sends a JWT with:

~~~json
{
  "sub": "alice",
  "permissions": ["reports.read", "reports.write"]
}
~~~

Default JWT configuration does not read the `permissions` field. Use `JwtGrantedAuthoritiesConverter` to specify the claim name and prefix:

~~~java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("SCOPE_");
~~~

To **test the converter**, pass that converter into `mockJwt()` instead of hardcoding authorities:

~~~java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .claim("permissions", java.util.List.of("reports.read"))
            .claims(claims -> claims.remove("scope")))
        .authorities(permissions))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

In a production reactive Resource Server, the same converter must be wired into `JwtAuthenticationConverter` and adapted into a reactive converter. **The following snippet is an illustrative configuration** placed in a configuration class with the proper imports:

~~~java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter delegate = new JwtAuthenticationConverter();
delegate.setJwtGrantedAuthoritiesConverter(permissions);

ReactiveJwtAuthenticationConverterAdapter reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(delegate);

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(reactiveConverter)));
~~~

The classes above belong to `org.springframework.security.oauth2.server.resource.authentication`; `ReactiveJwtAuthenticationConverterAdapter` adapts a synchronous converter into a reactive one. In real application code, extract the converter into a shared bean/helper so tests do not accidentally diverge from production configuration.

If you want to keep **both default scopes and custom permissions**, combine converters (e.g. `DelegatingJwtGrantedAuthoritiesConverter`) rather than replacing the default converter with one that reads only `permissions`. When converting a `roles` field to `ROLE_`, security rules must match `ROLE_ADMIN`; do not call `hasRole("ROLE_ADMIN")`, because `hasRole` automatically prepends `ROLE_` by convention.

A good test suite includes **both allow and deny tests**: for instance `permissions=["reports.read"]` gives GET 200, while `permissions=["reports.write"]` alone gives GET 403.

## 6. Opaque token authority mapping and introspection

Opaque tokens generally do not carry claims for the application to decode locally. The application calls **`ReactiveOpaqueTokenIntrospector`** to obtain principal, attributes, and authorities. With `mockOpaqueToken()`:

~~~java
client.mutateWith(mockOpaqueToken()
        .attributes(attrs -> {
            attrs.put("sub", "alice");
            attrs.put("tenant_id", "tenant-a");
            attrs.put("scope", "reports.read");
        })
        .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Here three attributes simulate principal data; **only `.authorities(...)`** determines the simulated permissions. A `"scope"` value inside attributes **must not be treated as proof** that the application's custom introspector properly maps scopes. To test a specific principal, you can pass `.principal(OAuth2AuthenticatedPrincipal)` and test controllers/handlers reading from `BearerTokenAuthentication`.

For real tokens, the corresponding opaque Resource Server config looks like:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(org.springframework.security.config.Customizer.withDefaults()));
~~~

JWT mode uses:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(org.springframework.security.config.Customizer.withDefaults()));
~~~

These two snippets are **alternative configurations**; each requires the matching decoder/introspector and provider settings. Do not combine them arbitrarily and assume the application supports both modes simultaneously.

When a custom introspector converts a `"roles"` attribute into `ROLE_ADMIN`, test that logic directly (or call HTTP with a stubbed introspector) and inspect the returned set of authorities. Writing only `mockOpaqueToken().authorities(ROLE_ADMIN)` skips testing the real mapping bug surface.

## 7. Boundary between unit/security tests and integration tests

**Mock authentication** is great for testing rules, controller principal binding, and method security, but **skips bearer token decoding/verification**. To test the real path through `AuthenticationWebFilter`:

1. Initialize the real `SecurityWebFilterChain` with `.oauth2ResourceServer(...jwt(...))` **or** `.opaqueToken(...)`.
2. Provide a `ReactiveJwtDecoder`/`ReactiveOpaqueTokenIntrospector` test double in the `ApplicationContext`; with Spring Boot 3.3 you can use `@MockBean`, while newer Boot versions provide `@MockitoBean`.
3. Send **`Authorization: Bearer <token value>`** via `WebTestClient` instead of using `mutateWith(mockJwt())` or `mutateWith(mockOpaqueToken())`.
4. Verify the decoder/introspector was invoked, authorities come from the application's actual converter, and the response is 200/401/403. Use WireMock/Testcontainers or a real Authorization Server when testing introspection endpoints, JWK rotation, or full protocol behavior.

Example snippet for a **JWT pipeline test** (assuming the client uses JWT Resource Server config and `jwtDecoder` is a mock bean):

~~~java
Jwt decoded = Jwt.withTokenValue("test-jwt")
        .header("alg", "RS256")
        .claim("sub", "alice")
        .claim("scope", "reports.read")
        .build();

when(jwtDecoder.decode("test-jwt")).thenReturn(Mono.just(decoded));

client.get().uri("/reports")
      .headers(headers -> headers.setBearerAuth("test-jwt"))
      .exchange()
      .expectStatus().isOk();
~~~

Mocking the decoder tests **the converter and authorization post-decode**; it still does not validate signature/issuer/expiration with real cryptography. Place stubbing inside a test class configured with Mockito; this snippet **is not a standalone Java program**.

Example snippet for an **opaque pipeline test** (opaque mode configured, `introspector` is a mock bean):

~~~java
OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
                java.util.Map.of("sub", "alice", "scope", "reports.read"),
                java.util.List.of(
                    new SimpleGrantedAuthority("SCOPE_reports.read")));

when(introspector.introspect("opaque-ok")).thenReturn(Mono.just(principal));

client.get().uri("/reports")
      .headers(headers -> headers.setBearerAuth("opaque-ok"))
      .exchange()
      .expectStatus().isOk();
~~~

Common classes: `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, and `DefaultOAuth2AuthenticatedPrincipal`. Results depend on the configured real converter/introspector; to prove custom mapping rules, avoid directly stubbing an already-"correct" output and instead invoke the actual mapping used in production.

Additionally, **401 for an invalid token** only makes sense when the authentication filter actually executes against a token/header or the decoder/introspector returns an error; calling `mockJwt()` and setting `exp` in the past **is not enough to prove runtime expiration validation**.

## 8. Matrix of required test cases

| Scenario | Recommended input | Expected |
| --- | --- | --- |
| No authentication | GET /reports, no mutateWith | 401 |
| JWT with read scope | mockJwt().jwt(scope=reports.read) | 200 |
| JWT missing read permission | mockJwt().authorities(SCOPE_reports.write) | 403 |
| JWT without scope | mockJwt() after removing scope claim | 403 |
| Opaque with permission | mockOpaqueToken().authorities(SCOPE_reports.read) | 200 |
| Opaque with scope attribute only, missing authority | mockOpaqueToken().attributes(...) | 403 |
| POST with read permission, missing write | SCOPE_reports.read | 403 |
| POST with write permission | SCOPE_reports.write | 200 |
| Custom JWT permissions | converter from permissions → SCOPE_... | 200/403 per specific authority |
| Real invalid/expired token | Bearer header + decoder/introspector or server stub | 401, verify real error handler |

The matrix can be implemented with parameterized tests, provided each case has a clear failure reason. If the real endpoint uses `@PreAuthorize`, keep method security enabled and test cases where the HTTP rule permits the request while the method rule denies it.

## 9. Common mistakes and fixes

- **Confusing claims with authorities.** JWT `permissions=["ADMIN"]` does not automatically grant `ROLE_ADMIN`; opaque `.attributes("scope", ...)` does not replace `.authorities(...)`. Fix the converter or mock post-mapping authorities depending on the layer under test.
- **Wrong prefix or delimiter.** `scope` `"reports.read"` yields `SCOPE_reports.read`, not `reports.read`, `ROLE_reports.read`, or `SCOPE_reports:read`.
- **Tests accidentally passing because default mockJwt has SCOPE_read.** For negative permission tests, remove `scope` or set authorities lacking the required permission.
- **Testing a converter by assigning fixed authorities.** That bypasses the converter; pass the same `JwtGrantedAuthoritiesConverter` via `.authorities(converter)` or invoke the real pipeline with a stubbed decoder.
- **Forgetting springSecurity() when manually binding WebTestClient.** `SecurityMockServerConfigurers` must be applied to the client/context properly.
- **Confusing 401 and 403.** 401 means unauthenticated/unable to authenticate; 403 means authenticated but denied by authorization policy. Custom entry points/handlers can create exceptions, so test against real configuration.
- **CSRF masking authorization errors on POST.** If the API uses CSRF, add `mockCsrf` or valid tokens; for stateless bearer APIs, configure CSRF appropriately. Never conclude an authority is missing when CSRF actually caused the failure.
- **Using mock JWTs to test signatures or expiration.** Mocks inject an already-accepted authentication; test decoders/validators via bearer headers or dedicated decoder tests.
- **Using WebMvc MockMvc for WebFlux.** This uses `WebTestClient` with `SecurityMockServerConfigurers` (reactive), not Servlet's `SecurityMockMvcRequestPostProcessors`.
- **Skipping negative tests.** A passing HTTP 200 test does not prove an endpoint blocks unauthorized accounts; always include appropriate 403 and 401 cases.

## 10. Knowledge self-check

1. What authority does a JWT with `scope="reports.read"` generate by default? **SCOPE_reports.read.**
2. Why can `mockOpaqueToken().attributes(attrs -> attrs.put("scope", "reports.read"))` still result in 403? **Attributes do not replace authorities on the simulated Authentication; the endpoint checks authorities.**
3. When using `hasRole("ADMIN")`, which authority is required? **ROLE_ADMIN.**
4. Does a test using `mockJwt().authorities(SCOPE_reports.read)` verify a custom claim converter? **No; it specifies the post-mapping authority directly.**
5. To test the flow bearer → decoder → converter → authorization, what should you do? **Send a bearer header against the real Resource Server config, stub the appropriate decoder/introspector, and assert authorities; use full integration tests when cryptographic or HTTP introspection verification is needed.**

## Official documentation

- Spring Security — Testing OAuth 2.0 with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html

Examples use the Spring Security 6.x / Spring Boot 3.x model with WebFlux and Java 17+; when upgrading major versions, re-verify the corresponding APIs and dependencies.
