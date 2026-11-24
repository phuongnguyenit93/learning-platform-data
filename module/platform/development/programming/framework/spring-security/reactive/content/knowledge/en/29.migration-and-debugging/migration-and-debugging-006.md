# Diagnosing 401 Despite Sending Credentials in Spring Security Reactive

## 1. Goal: Pinpoint the Exact Failure Point Instead of Guessing Passwords

A request to a Spring WebFlux API may carry `Authorization: Basic ...`, `Authorization: Bearer ...`, or a session cookie and still receive `HTTP 401 Unauthorized`. That the client "sent credentials" only proves **the client's intent**; it does not prove that:

1. The credentials reached the intended application intact after the browser, reverse proxy, and gateway.
2. The selected `SecurityWebFilterChain` actually supports that credential type.
3. The filter successfully converted the request data into an authentication object.
4. The `ReactiveAuthenticationManager`/JWT decoder/user service succeeded in verifying them.
5. `Authentication` was placed into the right Reactor Context before authorization checks ran.
6. The component returning 401 was Spring Security rather than a gateway or another upstream hop.

This lesson belongs to **Migration and debugging**: it emphasizes evidence-based diagnosis when migrating from Servlet to WebFlux or from Basic/session login to Bearer JWT. The end goal is identifying **failure location + root cause + fix + regression test**, rather than masking symptoms with `permitAll()` or disabling security controls.

## 2. Read HTTP Status Codes Properly Before Editing Configuration

| Code/symptom | Typical meaning | Next inspection step |
| --- | --- | --- |
| **401** | Authentication not accepted, missing/invalid credentials, or entry point demands login | `WWW-Authenticate`, authentication filter, token/password, session |
| **403** | Authenticated but insufficient privileges, or rejected by CSRF/CORS/security policy | `GrantedAuthority`, `hasRole`/`hasAuthority`, CSRF, CORS |
| **302** to login/IdP | Browser login flow is redirecting | `Location`, session cookie, callback, saved request |
| **404** | Router/path/route does not exist or prefix mismatch | URL through proxy, controller mapping, gateway |
| **5xx** | Failure in gateway, decoder, IdP/JWK endpoint, application, or infrastructure | Server logs, trace ID, dependencies, and stack trace |

These are **common conventions**, not rigid theorems: an application may install a custom `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`, or a gateway may rewrite status codes. Always determine **who generated the response** before assigning blame.

`401` is named **Unauthorized** in the HTTP specification, yet semantically indicates that authentication was not accepted. By HTTP protocol, a 401 response often includes one or more `WWW-Authenticate` challenges (such as `Basic realm="..."` or `Bearer error="invalid_token"`); this header helps identify which security mechanism answered. Never infer from an empty response body that the request bypassed security filters.

With Bearer tokens, a valid token lacking a required scope usually produces **403** (possibly with `insufficient_scope`), whereas an expired JWT or invalid signature usually produces **401** (possibly with `invalid_token`). Misconfigured CORS preflight handling can turn into 401 or surface as a "CORS error" in the browser; a missing CSRF token on POST typically produces 403. Inspect the actual HTTP response rather than relying solely on a frontend error banner.

## 3. Request Path Through WebFlux Security

```text
Client/Browser/WebClient
    |
    v
Reverse proxy / API gateway
    |   Are Authorization/Cookie headers preserved?
    v
WebFlux WebFilter chain
    |
    v
Spring Security WebFilterChainProxy
    |   Selects right SecurityWebFilterChain via securityMatcher and @Order?
    v
Authentication WebFilter (Basic / Bearer / OAuth2 login / ...)
    |   Extracts credentials? Matching scheme?
    v
ReactiveAuthenticationManager / ReactiveJwtDecoder / user store
    |   Password/signature/issuer/timestamps/validation valid?
    v
Authentication in ReactiveSecurityContextHolder (Reactor Context)
    |   Authenticated and expected authorities present?
    v
AuthorizationWebFilter / Reactive method security
    |   Sufficient permission/role/scope/owner?
    v
Handler -> Response
```

When authentication fails, Spring Security delegates to the matching authentication failure handler/entry point. When authorization lacks permissions, the access-denied handler participates. **One `SecurityWebFilterChain` is chosen per request**: configuring Bearer on another chain will not help a request that matched the Basic chain. And `pathMatchers` inside `authorizeExchange` governs **access rules within the selected chain**; it does not act as the chain's `securityMatcher`.

In Reactive, `ReactiveSecurityContextHolder` stores/reads `SecurityContext` via the **subscriber's Reactor Context**. Servlet/`ThreadLocal`-style `SecurityContextHolder.getContext()` is not a reliable authentication source in WebFlux. Switching threads via `publishOn` inside an unbroken Reactor chain does not automatically lose Context; breaking the chain with a detached `subscribe()`, non-Reactor callbacks, or global mutable state is what typically causes context failures.

## 4. Five-Stage Diagnostic Workflow

### Stage 1 — Observe the Real Response and Where It Originated

Use a minimal request **without following redirects automatically** so the initial response is not obscured. Example for an internal endpoint using Basic:

```bash
# No credentials; expected 401 when protected with Basic.
curl -i http://localhost:8080/api/me

# curl prompts for password interactively when only username is passed.
curl -i --user alice http://localhost:8080/api/me
```

For a valid test Bearer token already issued:

```bash
# ACCESS_TOKEN previously provisioned in the test environment; do not print tokens to logs.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/me
```

The examples above use Bash syntax. In PowerShell, environment variables are referenced as `$env:ACCESS_TOKEN`, and you can invoke `curl.exe` to run the real curl CLI. Never put real tokens or passwords into command history, URL queries, log screenshots, or tickets. Never pass `curl -L` when inspecting the initial redirect, and never enable raw tracing that dumps full `Authorization` headers.

Record **timestamp, correlation/request ID, method, public URL, status, `WWW-Authenticate`, `Location`, `Server`/gateway headers, and a sanitized body**. Compare:

- A direct request to the app on a trusted test network (if permitted) versus a request routed through the public gateway.
- Outcomes with the same credentials on different paths (e.g., `/api/me` vs. `/web/me`).
- Whether the application actually received the request (access logs, trace ID propagated across the proxy).

If the gateway returns 401 while the application **has no corresponding request**, investigate gateway configuration and auth policies first; do not edit `SecurityWebFilterChain`.

### Stage 2 — Verify Credentials Actually Reached Upstream

For Bearer, the default syntax is:

```http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...<token-redacted>
```

For Basic, requests use the `Basic` scheme followed by Base64 of `username:password`; Base64 **is not encryption**, so transmit only over HTTPS. Do not confuse `Proxy-Authorization` with application `Authorization`: some proxies use a separate header for proxy auth and may strip or rewrite headers forwarded upstream.

Check common transport errors:

- Frontend **minted a token** but omitted `Authorization` on the real API request, or attached the header to client A while request B used a different HTTP client instance.
- Extra spaces, quotes, or newlines inside the Bearer header; `Bearer undefined`, `Bearer null`, or a double-Base64-encoded token.
- Browser redirected to a different origin and dropped sensitive headers as expected; compare the final request URL.
- API gateway, ingress, or reverse proxy stripped `Authorization` or replaced it with an internal credential; check forwarding policies across trusted hops.
- `WebClient` calling service B only authenticated the **inbound request to service A**. Bearer headers do not automatically "propagate" onto every outbound `WebClient` call.
- In browser session logins, cookies were not sent due to `SameSite`, `Secure`, `Path`, `Domain`, `credentials`, expired sessions, or host mismatch.

To confirm header presence inside the application, log only a **Boolean** such as `authorizationPresent=true` or a sanitized scheme name, alongside the request ID. Never print full tokens/Basic values, cookies, entire header maps, or authorization codes.

### Stage 3 — Check the Selected Chain and Enabled Auth Mechanisms

An `/api/**` endpoint using JWT requires a chain configured with `oauth2ResourceServer(...jwt...)`. Having only `oauth2Login(...)` means the app supports browser OAuth2 login—it **does not automatically turn endpoints into a JWT Resource Server**. Enabling only `httpBasic()` likewise will not decode `Authorization: Bearer ...`.

In Spring Boot, declaring your own `SecurityWebFilterChain` bean can replace auto-configuration's default filter chain. Therefore, having dependencies or `issuer-uri` properties does not prove a request enters a JWT-enabled chain; inspect actual beans, `@Order`, and `securityMatcher`.

Multi-chain example (configuration snippet to place inside an `@Configuration @EnableWebFluxSecurity` class, requiring a configured JWT decoder):

```java
@Bean
@Order(0)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(1)
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Key additional imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

**Configuration warning:** this illustrates **two chains with different mechanisms**, not a drop-in replacement for an existing production configuration. It requires `spring-boot-starter-oauth2-resource-server`, a `ReactiveJwtDecoder` configured from a valid issuer/JWK, and review of endpoints outside `/api/**`. If a proxy adds/strips a public prefix, check the actual URL/path the app receives when matching. Never place a catch-all chain at higher priority such that the `/api/**` chain can never be selected.

### Stage 4 — Analyze Credential Verification and Authentication Creation

Verify according to the exact credential type, **never guessing just because a header looks valid**.

#### HTTP Basic / Username-Password

- The server must enable `httpBasic(...)` on the chain matching the request.
- Spring Security must have the appropriate `ReactiveUserDetailsService`/`ReactiveAuthenticationManager`, the user must be enabled/unlocked, and the password must match `PasswordEncoder`.
- With `DelegatingPasswordEncoder`, stored passwords normally carry prefixes like `{bcrypt}...`. Missing prefixes or incompatible encoders cause auth failures or config errors; never switch production to plaintext.
- If using form login, verify the login POST, session cookie, and CSRF separately; sending HTTP Basic credentials to an app that only enables form login may not authenticate.

#### JWT Bearer Resource Server

- The default header is `Authorization: Bearer <access-token>`. Custom headers or query params are ignored unless `ServerBearerTokenAuthenticationConverter` is configured; prefer the standard header.
- The JWT must be well-formed, its signature/`alg`/`kid` must match public keys from the JWK Set, `iss` must match the expected issuer, `exp`/`nbf` must be valid, and server clocks must be accurate.
- `aud` is an important security check for your API, **yet is not validated by default in every Resource Server setup**; configure an audience validator per your system contract.
- Staging tokens, OIDC ID tokens, or refresh tokens are **not automatically valid access tokens** accepted by an API.
- Unreachable JWK endpoints can fail decoding in various ways—even returning 5xx depending on the error; check real exceptions/logs before labeling it a "bad token".
- A valid JWT missing a scope/role is mainly an **authorization issue**, usually returning 403 rather than requiring signature/issuer changes.
- For opaque tokens, use introspection (`ReactiveOpaqueTokenIntrospector`) rather than a JWT decoder; verify URI, client credentials, active/expiry status, and network errors.

Spring Boot JWT Resource Server example (illustrative `application.yml` snippet; `issuer-uri` must match your real environment):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/api
```

With `issuer-uri`, Spring can use discovery metadata to locate the JWK Set and validate `iss`. If the server does not publish compatible discovery metadata, configure `jwk-set-uri` and an issuer validator per the docs; never "fix 401" by disabling signature, expiry, or issuer validation.

#### WebSession/Cookie After OAuth2/OIDC Login

- Being redirected back from the IdP to the callback **does not guarantee** subsequent API calls carry an authenticated `WebSession`.
- Open DevTools → Network; confirm `Set-Cookie` from the app was accepted by the browser and the cookie is sent on authenticated API requests.
- For cross-origin `fetch` with cookies, configure `credentials: 'include'` on the client where appropriate, plus CORS credentials and an explicit origin allowlist on the server; same-origin `fetch` follows its own defaults.
- If 401 occurs after callback, inspect `SameSite`, `Secure`, `Path`, domain, session TTL, cache/store, and multi-replica sharing; `invalid_state`/redirect loops often indicate lost sessions.
- Distinguish **session** cookies from **CSRF** cookies. Having a CSRF cookie does not prove login; having a session cookie does not guarantee the session hasn't expired.

### Stage 5 — Determine Authorization Errors vs. Lost Reactor Context

Once authentication succeeds:

- With JWTs, Spring typically maps `scope`/`scp` to authorities like `SCOPE_orders.read`. `hasRole("ADMIN")` checks `ROLE_ADMIN`, unlike `hasAuthority("ADMIN")`. Missing scopes/roles cause **403**, not invalid-token errors.
- For endpoints with `@PreAuthorize`, verify reactive method security is enabled and calls go through the reactive proxy. Inspect both URL rules and method rules.
- In WebFlux, read principals inside pipelines via `ReactiveSecurityContextHolder.getContext()` or WebFlux principal arguments. Never read thread-based `SecurityContextHolder` and conclude the user is anonymous.
- If a controller starts with a valid `Authentication` yet a downstream service lacks context, search for nested `subscribe()` calls, callbacks outside the Reactor chain, or publishers constructed and subscribed independently. `publishOn` by itself does not prove context loss.
- If 401 happens **before the controller is ever invoked**, inspect converters, managers, chains, and gateways rather than guessing context was lost inside business logic.

## 5. Runnable Java 17+ Example: Distinguishing Missing Credentials, Invalid Credentials, and Missing Permissions

The following fixture is a minimal WebFlux app running under JUnit 5 with Basic authentication and `/api/me`. To reproduce 401/403 **without needing a real JWT issuer**, the tests separate each state cleanly:

- Missing Basic header → **401**.
- Basic with wrong password → **401**.
- Bearer string sent to a Basic-only chain → **401**.
- Valid Basic to `/api/me` → **200** with body equal to the principal.
- Valid Basic without `ADMIN` role to `/api/admin` → **403**.

File `src/test/java/example/security/Reactive401DiagnosticTest.java`:

```java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = Reactive401DiagnosticTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class Reactive401DiagnosticTest {

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
    void missingCredentialsReturn401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicPasswordReturns401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void bearerIsNotAcceptedByBasicOnlyChain() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("not-a-jwt"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctBasicCredentialsReturnPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "correct"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void validUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "correct"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, ProbeController.class})
    static class TestApplication {}

    @Configuration(proxyBeanMethods = false)
    @EnableWebFluxSecurity
    static class SecurityConfig {

        @Bean
        SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(ex -> ex
                            .pathMatchers("/api/admin").hasRole("ADMIN")
                            .pathMatchers("/api/**").authenticated()
                            .anyExchange().denyAll())
                    .httpBasic(Customizer.withDefaults())
                    .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                    .build();
        }

        @Bean
        MapReactiveUserDetailsService users() {
            return new MapReactiveUserDetailsService(
                    User.withUsername("alice")
                            .password("{noop}correct")
                            .roles("USER")
                            .build());
        }
    }

    @RestController
    static class ProbeController {

        @GetMapping("/api/me")
        Mono<String> currentPrincipal() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(context -> context.getAuthentication().getName());
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin");
        }
    }
}
```

**Detailed fixture explanation:** `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` runs the real context's WebFlux `WebFilter` chain; `setBasicAuth` builds a proper Basic header; `MapReactiveUserDetailsService` provides a fixed test user; `ReactiveSecurityContextHolder` proves the controller sees authentication via Reactor Context. `{noop}` is acceptable only for **fake credentials in tests**—never choose this password storage scheme in production.

Two 401 tests answer two distinct questions: "is the header present?" and "does the manager accept the header?". Testing Bearer against a Basic-only chain shows that **an Authorization header can be present yet produce no valid Authentication**. The 403 test proves valid credentials lacking permissions are a separate failure from authentication.

### Dependencies and Run Command

Add these dependencies to `build.gradle` in a Spring Boot 3.x project using Boot's BOM; explicit versions are unnecessary when managed by the project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Run in a project with a compatible wrapper and dependencies:

```bash
./gradlew test --tests 'example.security.Reactive401DiagnosticTest'
```

On Windows use `gradlew.bat test --tests "example.security.Reactive401DiagnosticTest"`. Expect **5 tests PASS** (no mandatory business stdout); if any status differs from expectations, inspect the classpath, filter chain, or actual build setup. This fixture test connects to no real gateway, verifies no JWT signatures, and tests no browser cookie policies.

## 6. Inspecting Bearer JWT Cases Specifically

### 6.1. WebFlux Resource Server Sample

Java 17+ sample configuration for an API accepting JWTs; this is a complete config class, though it **still requires a real issuer/JWK endpoint** at runtime:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class JwtApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Add `spring-boot-starter-oauth2-resource-server` and `issuer-uri` as in Section 4. If multiple chains are used, add `securityMatcher`/`@Order` as in the multi-chain example; permitting `/api/public/**` does not automatically allow endpoints outside the matcher in another chain.

**When a real JWT returns 401**, check in order:

1. Proper `Bearer` scheme, no duplicated prefix, not altered by a gateway.
2. JWT header `alg`/`kid` compatible with the key set/trust policy; `alg=none` never accepted.
3. `iss` matches the configured issuer character-for-character; `exp`/`nbf` and system clocks have no abnormal skew.
4. Token belongs to the right environment and is an access token; compare `aud` against the audience required by the API, configuring an audience validator if needed.
5. IdP discovery/JWKS reachable from the server, valid HTTPS/certificates, caching, and key rotation.
6. Sanitized exception logs distinguish `JwtValidationException`/decoder/HTTP 401 vs. other infrastructure failures. Never infer root cause from status 401 alone.

**Seeing JWT claims via Base64URL decoding does not prove the signature is valid.** Never paste user tokens into untrusted online JWT decoder websites. When inspecting claims, use an organization-approved local tool without exposing tokens; signatures, issuers, timestamps, and audiences must be verified server-side.

### 6.2. Mock JWT and Real Tokens Test Different Things

`spring-security-test` offers `mockJwt()` to test WebFlux authorization rules once a Resource Server setup is in place:

```java
// Illustrative test snippet in a class with client + Resource Server chain.
// Does not validate signature/issuer/expiry of a real token.
client.mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("scope", "orders.read")))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
```

Static import:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
```

Simulating authentication only proves endpoints and security rules behave properly **once a valid `Authentication` exists**. To diagnose 401s caused by token validation, add integration tests using real JWTs signed with a test key against a configured decoder, covering valid, expired, wrong-issuer, wrong-signature, and wrong-audience tokens when `aud` is enforced. Never claim "JWT authentication is verified" solely because `mockJwt()` passed.

## 7. Items Easily Missed When Migrating Servlet → Reactive

| Familiar Servlet pattern | WebFlux Reactive check | If missed |
| --- | --- | --- |
| `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` | Legacy config fails to protect WebFlux as expected |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Reactive security chain is not configured properly |
| `UserDetailsService` | `ReactiveUserDetailsService` | Manager cannot use the expected reactive user source |
| `JwtDecoder` | `ReactiveJwtDecoder` | Reactive Resource Server lacks the proper decoder |
| `SecurityContextHolder` via `ThreadLocal` | `ReactiveSecurityContextHolder` via Reactor Context | Misreads anonymous or fails to find `Authentication` |
| Servlet `Filter`/`OncePerRequestFilter` | WebFlux `WebFilter`/Security `WebFilter` | Custom authentication does not run on reactive requests |
| MVC `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` for reactive method auth | Method-level permission checks do not enforce properly |
| `HttpSession`, `JSESSIONID` | `WebSession` and WebFlux cookie/session manager | Browser sends cookie, yet server cannot find the session |

**You cannot fix 401 simply by swapping imports.** When migrating code, trace the entire path: matching filter chain → converter → reactive manager/decoder → context → authorization. An application carrying both MVC and WebFlux dependencies may boot with an unexpected web application type; inspect startup logs, dependency trees, and which framework actually serves inbound HTTP.

## 8. CORS, CSRF, and Browsers: Do Not Confuse Error Layers

### 8.1. CORS Preflight

An SPA at `https://ui.example.com` calling `https://api.example.com` with an `Authorization` header can trigger the browser to send an automatic **OPTIONS preflight** before GET/POST:

```http
OPTIONS /api/me HTTP/1.1
Origin: https://ui.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

This preflight **carries no Bearer token or session cookie** like the real API request. If security runs before CORS and demands authentication for `OPTIONS`, the browser reports a CORS failure and never sends the main request. Spring Security's guidance for WebFlux is to handle CORS **before** security, typically via proper CORS configuration/`CorsWebFilter`. Never solve this by disabling authentication altogether or allowing every origin with credentials.

Test preflight independently:

```bash
curl -i -X OPTIONS https://api.example.com/api/me \
  -H "Origin: https://ui.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expect status/`Access-Control-Allow-Origin`/`Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` matching application policy. Preflights hitting a public gateway may also be blocked before Spring; correlate traces.

### 8.2. CSRF

If `POST`/`PUT`/`DELETE` with cookies/sessions returns 403 while `GET` returns 200, inspect CSRF tokens, headers/form fields, and sessions first. Spring Security WebFlux enables CSRF protection; do not disable it application-wide just to turn 403 into 200. For stateless Bearer APIs, evaluate CSRF policy based on whether browsers send credentials automatically and the threat model, not merely the word "REST".

### 8.3. Browser Sessions vs. Bearer JWT

In browser login, after a successful OAuth2 callback, the API only has an authenticated session once it receives a valid session cookie. If the UI uses `fetch` against a different API host, `credentials`/CORS/`SameSite` and cookie scope determine whether the cookie travels along. If an SPA holds a token in memory and attaches a Bearer header itself, session cookies are irrelevant to that request. Identify **which model** the app actually uses before applying fixes.

## 9. WebClient Calling Another Service: 401 Appears Downstream

Suppose inbound requests to **service A** are authenticated, yet inside A, `WebClient` calls **service B** and B returns 401. That 401 does not necessarily come from A; inbound request tokens are not automatically attached to outbound `WebClient` calls.

If A is a JWT Resource Server and policy permits forwarding the access token to B, Spring Security provides `ServerBearerExchangeFilterFunction`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamClientConfig {

    @Bean
    WebClient downstreamClient(WebClient.Builder builder) {
        return builder
                .filter(new ServerBearerExchangeFilterFunction())
                .build();
    }
}
```

Use this propagation only when B is a **valid audience/recipient** of the token and security policy permits it. For service-to-service calls or token exchange, separate credentials/tokens from `ReactiveOAuth2AuthorizedClientManager` may be required instead of forwarding the user's token. The filter function can extract a Bearer token only when the current authentication context holds a matching token; non-Reactor callbacks or lost context can cause outbound requests to omit the token.

To diagnose: correlate request IDs between A→B, inspect B's returned status, check header **presence/absence** at B, and verify authorization policies—never log raw tokens. Tests should distinguish A returning 401 inbound vs. A returning an error payload after B returned 401.

## 10. Root-Cause Lookup Table from Observed Symptoms

| Symptom | Primary hypothesis | Evidence and remediation |
| --- | --- | --- |
| Browser sends header, Spring never sees it | Stripped by gateway/proxy or different origin | Compare trace IDs and header presence at each trusted hop |
| Basic works on `/web`, 401 on `/api` | Two chains select different mechanisms | Inspect `@Order` and `securityMatcher`; never assume the entire app uses Basic |
| Every Bearer token gets 401 | Resource Server not enabled, wrong header converter, or wrong decoder | Inspect chain and `ReactiveJwtDecoder` before changing tokens |
| JWT fails only after changing environments | `iss`/`aud`/JWK/clock mismatch | Compare token metadata against environment issuer and validators |
| JWT verified, endpoint still rejects | Missing scope/role or method security | Inspect sanitized `Authentication.getAuthorities()`; usually 403 |
| Web login succeeds, yet API returns 401 | Cookie not sent or session expired | Check DevTools cookies, `SameSite`/`Secure`/`Path`/`Domain`/TTL |
| Postman/curl works, browser sees CORS error | OPTIONS preflight blocked or CORS rejects origin/header | Test preflight directly; evaluate CORS before security |
| GET 200, POST 403 | Missing/invalid CSRF token, or method-specific rule | Inspect CSRF and HTTP method rules before blaming authentication |
| 401 behind proxy, 200 direct to app | Gateway authorization or dropped headers | Identify which hop generated the response and inspect forwarding policy |
| Service A auth OK, call to service B returns 401 | `WebClient` sent no token or token invalid for B | Distinguish inbound vs. outbound auth, audience, and client config |
| Principal empty on another Reactor thread | Used Servlet ThreadLocal or detached subscription | Use `ReactiveSecurityContextHolder` and keep a single reactive chain |
| Failure happens only on certain pods | Config/keys/clock/session store mismatch across replicas | Compare deployment config, clocks, and session persistence per replica |

## 11. Safe Logging and Regression Testing

Enable debug logging in **controlled test/staging environments** when needed, for example:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

If TRACE is needed, use it only for brief diagnostic windows with restricted log access; some libraries, gateways, and HTTP clients log headers or sensitive payloads at trace level. Restore normal logging levels once the issue is found. Never print tokens, passwords, cookie/session IDs, client secrets, authorization codes, signatures, or full `Authorization` headers.

For each reproduction, record:

1. **Request ID**, HTTP method, public path, auth scheme (without credential values), status, and response origin.
2. Matched chain, which filter/manager/decoder actually executed, and whether a user/token was found.
3. Authentication outcome: authenticated/anonymous, authority names only if allowed by security policy, and sanitized exception classes.
4. URL/headers across proxies and browser/session state when relevant.
5. Post-fix tests: missing → 401; malformed/wrong credentials → 401; valid credentials → 200; valid but insufficient privilege → 403; CORS preflight works; credentials never leak to unauthorized services.

Never change `AuthenticationEntryPoint` to return 200/302/403 just to "silence 401"; custom entry points should only be used when an explicit response design requires them and tests confirm protocol correctness. Never bypass issuer/expiry/signature validation, CSRF, or endpoint permissions.

## 12. Quick Decision Tree

```text
START: client claims credentials were sent yet receives 401
 |
 +-- Is there a response/trace at Spring WebFlux?
 |      +-- NO: check gateway, proxy, ingress, routing, which hop returned 401
 |      +-- YES:
 |           |
 |           +-- Did upstream receive the right Authorization/Cookie?
 |           |      +-- NO: check browser/client, redirects, WebClient, proxy
 |           |      +-- YES:
 |           |           |
 |           |           +-- Did the matched chain enable the right auth scheme?
 |           |           |      +-- NO: fix @Order/securityMatcher and Basic/Bearer/login
 |           |           |      +-- YES:
 |           |           |           |
 |           |           |           +-- Did converter/manager/decoder authenticate OK?
 |           |           |           |      +-- NO: password/issuer/exp/nbf/JWK/token type
 |           |           |           |      +-- YES: check Authentication/authorities,
 |           |           |           |                URL/method rules, custom entry point,
 |           |           |           |                and whether response is actually 403
 |
 +-- Only browsers failing? check CORS preflight/cookies/CSRF
 +-- Only downstream failing? check credential propagation and audience
 +-- After fix: run 401/200/403 tests and verify public-path requests
```

## 13. Pre-Closing Checklist for a 401 Bug

- [ ] Evidence confirms **where 401 was returned**, response headers, and request ID; not guessed from frontend UI.
- [ ] Confirmed credentials reach the right hop, path, and `Authorization` scheme or cookie scope.
- [ ] Confirmed the **actually matched** `SecurityWebFilterChain` supports the intended auth method.
- [ ] For Basic: checked reactive user store, password encoder, and account state; no plaintext in production.
- [ ] For JWT: checked decoder/issuer/exp/nbf/keys/JWK and audience policy; distinguished access tokens from ID tokens.
- [ ] For browsers: checked CORS preflight, session cookies, and CSRF separately; did not conflate 401 with 403.
- [ ] For `WebClient`: distinguished inbound vs. outbound auth and token audience rules.
- [ ] Used `ReactiveSecurityContextHolder` properly in Reactor chains; did not rely on Servlet ThreadLocal.
- [ ] Automated tests cover 401 missing/invalid credentials, 200 valid credentials, 403 insufficient permissions, and proxy/IdP integration where relevant.
- [ ] Sensitive data is redacted in logs and tickets; the fix does not weaken security controls.

## References

- [Spring Security — WebFlux Security Configuration, Multiple SecurityWebFilterChains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest and Rule Ordering](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — Testing Authentication with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html).
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- [Spring Security — Testing OAuth2/JWT with mockJwt](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html).
- [Spring Security — CORS in WebFlux](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Reactor — Context and Context-Propagation](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
