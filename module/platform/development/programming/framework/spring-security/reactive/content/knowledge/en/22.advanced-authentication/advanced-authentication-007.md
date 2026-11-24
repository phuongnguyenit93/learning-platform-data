# Selecting Authentication Mechanisms with Matchers and Avoiding Duplicate Processing

> **Context:** Spring Security **Reactive/WebFlux**, Java 17+, Spring Boot 3.3.x / Spring Security 6.3.x. The focus is selecting the right authentication mechanism by **URL, HTTP method, credential type, and API contract** using `ServerWebExchangeMatcher`, `SecurityWebFilterChain.securityMatcher`, and `AuthenticationWebFilter.setRequiresAuthenticationMatcher`; preventing a request from being authenticated by multiple filters simultaneously; and avoiding unintended privilege escalation or acceptance of unwanted credentials. The 3.3.x examples illustrate syntax and are not a recommendation to deploy an end-of-support version to production.

## 1. The Real-World Problem

A WebFlux service serves three kinds of clients:

1. An internal partner system calls `GET /internal/jobs` with an `X-API-Key` header; the service grants it the restricted `SCOPE_jobs.read` authority.
2. A legacy admin/interactive API calls `GET /api/me` using HTTP Basic; users are authenticated via `ReactiveUserDetailsService`.
3. Employees open `GET /web/me` in a browser, logging in via form login and `WebSession`.

If you enable **Basic, API key, and form login on every request**, several problems can occur:

- Both the Basic filter and the API-key filter execute on the same request carrying multiple headers.
- An invalid credential is ignored by one handler and another handler grants access from a remaining credential.
- API requests receive redirects to an HTML login page instead of HTTP 401.
- A custom filter lacking a matcher still runs on `/health`, `/login`, or `/oauth2/**`, consuming the wrong credential type.
- A developer registers a custom `WebFilter` as a Spring bean and also inserts that same object into `SecurityWebFilterChain`, causing it to potentially run **twice** via the global WebFilter chain and the security chain.
- Duplicate token decoding/lookups, repeated session writes, duplicated logs/audits/traces, or authentication manager side effects executing multiple times.

The solution is to **define clear boundaries** between chain selection, filter selection, credential parsing, and authorization.

### One-Sentence Rule

**Each request should enter only one selected `SecurityWebFilterChain`, each credential should have one clear handler, and every authentication success or failure must carry consistent semantics.** This does not prevent other security steps (CSRF, CORS, authorization, logging) from running inside the chain; it prevents unintended or duplicate authentication.

## 2. Three Matcher Layers You Must Distinguish

| Layer | Spring Security Reactive API | Purpose | Effect If Not Matched |
|---|---|---|---|
| **Select security chain** | `ServerHttpSecurity.securityMatcher(ServerWebExchangeMatcher)` | Selects the security configuration applied to the request | Tries the next chain in order; if no chain matches, the request may go unprotected by Spring Security |
| **Select filter authentication attempt** | `AuthenticationWebFilter.setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)` | Decides whether that filter attempts to build an `Authentication` | Filter skips and continues the chain |
| **Select authorization rule** | `authorizeExchange(exchanges -> exchanges.pathMatchers(...).hasRole(...))` | Decides whether existing authorities are sufficient | Evaluates the next rule; `anyExchange()` acts as the chain's fallback |

Diagram:

```text
Request
  |
  v
WebFilterChainProxy
  |
  +-- @Order(0) /internal/** securityMatcher ?
  |          | yes
  |          +--> Internal chain
  |                     |
  |                     +--> AuthenticationWebFilter matcher?
  |                     |             |
  |                     |             +-- no -> skip filter
  |                     |             +-- yes -> converter -> manager
  |                     |
  |                     +--> authorizeExchange pathMatchers/anyExchange
  |
  +-- otherwise, @Order(1) /api/** ?
  |          +--> Basic/API chain
  |
  +-- otherwise, @Order(2) fallback
             +--> Form login / web chain
```

**Important:** Spring Security WebFlux selects **one** first-matching `SecurityWebFilterChain`; it does not "merge" all chains. However, **inside the selected chain**, if a developer enables multiple authentication filters with overlapping matchers, they can still participate together. Splitting chains separates route groups; configuring filter matchers/converters controls mechanism selection **inside** a chain.

## 3. ServerWebExchangeMatcher: Conditions for Reactive Requests

`ServerWebExchangeMatcher` is a Spring Security Reactive interface. It accepts a `ServerWebExchange` and returns a publisher of the match/no-match result:

```java
Mono<ServerWebExchangeMatcher.MatchResult> matches(
    ServerWebExchange exchange);
```

This is an explanatory signature; you do not redeclare the interface yourself. Spring provides useful matchers:

- `PathPatternParserServerWebExchangeMatcher`: matches URLs using Spring WebFlux path patterns, optionally constrained by HTTP method.
- `ServerWebExchangeMatchers.pathMatchers("/internal/**")`.
- `ServerWebExchangeMatchers.pathMatchers(HttpMethod.GET, "/internal/jobs")`.
- `ServerWebExchangeMatchers.matchers(matcherA, matcherB)`: combines conditions with OR where supported by the API version.
- `AndServerWebExchangeMatcher` and `OrServerWebExchangeMatcher` to compose multiple conditions.
- `NegatedServerWebExchangeMatcher` to negate a condition when needed.

**Note:** Path-style matchers are not the same as a `permitAll` authorization rule. A `permitAll()` route **still passes through the Security chain**, so pre-authorization filters such as CSRF or custom authentication filters can still run on it. To skip a specific filter, configure **that filter's** matcher/converter or adjust chain boundaries accordingly.

### 3.1 Path and HTTP Method

```java
ServerWebExchangeMatcher internal =
    ServerWebExchangeMatchers.pathMatchers("/internal/**");

ServerWebExchangeMatcher onlyGetJob =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/internal/jobs");
```

The examples above require imports for `ServerWebExchangeMatcher`, `ServerWebExchangeMatchers`, and `HttpMethod`. `/internal/**` is broad; `GET /internal/jobs` is narrower and does not match POST on the same path.

A good strategy is matching the chain by route group while scoping custom filters strictly to the routes needing that mechanism, e.g.:

```java
http.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/internal/**"));

apiKeyFilter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/internal/jobs"));
```

If you later add `POST /internal/jobs`, you must **explicitly decide** whether to enable the API-key filter and what CSRF policy applies to POST. Never assume a GET matcher protects all methods.

### 3.2 Matching by Header: Should You?

You can write a custom matcher inspecting `Authorization` or `X-API-Key`, but you must separate **routing how to process** from **trusting a credential**:

- Seeing `Authorization: Bearer ...` only shows the client **sent** a Bearer string, not that the token is valid.
- Seeing `X-API-Key` only indicates the request wants API-key handling, not that the key is authorized.
- `Accept: text/html` or `User-Agent` must never be treated as authentication evidence.
- When multiple credential types appear together, enforce an **explicit** policy: reject ambiguity or pick one per route rather than silently trying all until one succeeds.
- When a custom matcher reads headers, never log raw credentials.

**Recommendation:** When URLs clearly distinguish `/internal/**`, `/api/**`, and `/web/**`, prefer splitting `SecurityWebFilterChain` by route; match by header only when you genuinely must support multiple mechanisms on the same endpoint.

## 4. AuthenticationWebFilter: When Exactly Does It Attempt Authentication?

`org.springframework.security.web.server.authentication.AuthenticationWebFilter` is a `WebFilter` dedicated to authentication. Per the Spring Security 6.x Javadoc, the summarized flow is:

1. Invoke `setRequiresAuthenticationMatcher(...)` to determine **whether the request falls within this filter's scope**.
2. If not matched, continue the `WebFilterChain` **without** attempting authentication.
3. If matched, call `ServerAuthenticationConverter.convert(exchange)` to build an initial `Authentication` from the request.
4. Converter returning `Mono.empty()` means **no credential for this mechanism is present**; the filter **skips** and continues the chain without granting permissions.
5. If the converter emits an `Authentication`, the filter calls `ReactiveAuthenticationManager.authenticate(authentication)`.
6. Manager succeeds → `ServerAuthenticationSuccessHandler`, placing authentication into the reactive SecurityContext per the filter's repository.
7. Manager fails with `AuthenticationException` → `ServerAuthenticationFailureHandler` or configured error behavior.

```text
AuthenticationWebFilter
       |
  requires matcher?
       |
   +---+---+
   |       |
  no      yes
   |       |
continue  converter
             |
       +-----+------+
       |            |
   Mono.empty     Authentication
       |            |
    continue      manager
                    |
                +---+-----+
                |         |
             success     failure
                |         |
          SecurityContext  failure handler
                |         |
             continue   401/other policy
```

### 4.1 Two Kinds of "Skip" to Distinguish

- **Matcher does not match:** the filter never calls the converter or manager.
- **Converter returns Mono.empty():** the matcher matched, yet the request **contains no credential for this filter**, so no authentication attempt is created.

On a protected route, "skipping the filter" **does not mean allowing the request**. Without valid authentication from another mechanism, `authorizeExchange().authenticated()` invokes the entry point (typically 401 or a redirect depending on the chain).

**Never** turn a wrong credential into `Mono.empty()` so another mechanism gets a chance:

```java
// WRONG in security semantics:
if (apiKeyIsWrong) {
    return Mono.empty(); // request with WRONG key gets treated as missing key
}
```

When a client submits an invalid credential for the chosen mechanism, the manager must **emit an authentication error** and the handler must return a consistent failure. `Mono.empty()` applies when **no credential** for the mechanism exists, never for "swallowing errors".

### 4.2 Converters Should Not Check Business Permissions

`ServerAuthenticationConverter` only extracts/parses a credential into an unauthenticated `Authentication`. `ReactiveAuthenticationManager` verifies the credential and determines the principal and authorities. `authorizeExchange` or method/service security decides route/data access.

Never read a user role from an `X-Role` request header to build an authenticated `Authentication` without verifying against a trusted source.

### 4.3 Default Converter Is HTTP Basic

If you construct `new AuthenticationWebFilter(manager)` without calling `setServerAuthenticationConverter(...)`, the filter defaults to `ServerHttpBasicAuthenticationConverter`. For a custom API key, you **must assign your own converter**, otherwise the filter will try to read Basic instead of `X-API-Key` and conflict with Basic chains.

## 5. Authenticated ≠ Authorized and Multiple Filters

A successful `Authentication` establishes identity and baseline authorities, not blanket access to every endpoint:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/internal/jobs")
        .hasAuthority("SCOPE_jobs.read")
    .anyExchange().denyAll())
```

An API-key principal should receive `SCOPE_jobs.read` only after verification against a key store/permission policy. Never grant `ROLE_ADMIN` based on a client-sent header string. With multiple API keys, key ID → tenant/permissions mappings must come from a trusted system and check revoked/expiry states.

### 5.1 Why Can Basic + Bearer + API-Key Collide?

Within the same chain, converters might inspect:

- Basic filter: `Authorization: Basic ...`.
- Resource Server bearer filter: `Authorization: Bearer ...`.
- Custom key filter: `X-API-Key: ...`.

A single `Authorization` header holds one primary scheme; clients cannot legally put two schemes in the **same** value, yet they can send multiple header lines or send both `Authorization` and `X-API-Key`. If the key filter does not skip Basic routes, both filters might try to authenticate. When one filter succeeds and the second fails, ordering/failure handlers can produce unpredictable results. Never rely on filter ordering as a "credential fallback" safety mechanism.

**Preferred design:**

1. **One route = one published scheme:** split chains by URL—the simplest approach.
2. If a route must support multiple schemes, use **a single credential dispatcher** to pick one manager/provider, or mutually exclusive tested matchers.
3. When two incompatible credentials appear, **fail closed** (401/400 per contract) instead of trying a stronger credential to "rescue" the request.
4. When cookie sessions and bearer tokens coexist in one app, explicitly decide which routes accept cookies and which are strictly stateless. Never let an authenticated session substitute for an invalid bearer token.
5. When multiple identity sources exist, log non-sensitive correlation/credential types for auditing; never log secrets.

## 6. Selecting One Chain with securityMatcher and @Order

Spring Security WebFlux picks a chain based on the **order of `SecurityWebFilterChain` beans**. Example:

```text
@Order(0): /internal/**    -> Custom X-API-Key
@Order(1): /api/**         -> HTTP Basic
@Order(2): fallback        -> Form Login / WebSession
```

- The first chain matches `/internal/**`; those requests **never enter** the subsequent Basic/form chains.
- The second chain matches `/api/**`; even if a request carries `X-API-Key`, the first chain's key filter **does not exist in this chain**.
- The final chain has no `securityMatcher`, so it matches remaining URLs including `/login`.
- Explicit ordering prevents a broad `/**` matcher from "swallowing" narrower routes ahead of it.

**Never** declare three chains all with `securityMatcher("/**")` expecting every request to pass through all three to accumulate authorities. If no chain matches a URL, Spring Security may leave that URL unprotected; a fallback chain is good practice.

### 6.1 securityMatcher vs authorizeExchange.pathMatchers

```java
// Selects REQUESTS belonging to this chain:
.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**"))

// Once chain is selected, determines who is authorized:
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

If `/api/admin/**` fails to match the intended chain due to a wrong chain matcher, authorization's `pathMatchers` **will not route the request back to the right chain**.

### 6.2 CORS Preflight and OPTIONS

Browsers can send an `OPTIONS` preflight before a cross-origin request with `Origin` and `Access-Control-Request-Method`. This is not an API call requiring "extra login"; a matcher scoped strictly to `GET /internal/jobs` will not treat `OPTIONS` as API-key authentication.

However, skipping the auth filter **does not automatically return 200 for preflight**: you need a proper CORS policy and Security chain handling for `OPTIONS`. Never use `permitAll("/**")` to fix preflight. On header-based APIs not automatically sent by browsers, the CSRF threat model differs from cookie/browser-managed auth; disable CSRF selectively only after evaluation.

## 7. Avoiding Running a WebFilter Twice via Misregistration

This is a major pitfall in Spring Boot WebFlux:

```java
// ANTI-PATTERN: both a global Spring WebFilter bean ...
@Bean
AuthenticationWebFilter apiKeyWebFilter(
        ReactiveAuthenticationManager manager) {
    return new AuthenticationWebFilter(manager);
}

// ... and also adding the same WebFilter into SecurityWebFilterChain:
http.addFilterAt(apiKeyWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

The code above is an **anti-pattern illustration**, omitting full classes/imports. A bean implementing `WebFilter` can be registered by WebFlux/Boot into the **global `WebFilter` chain**, while `addFilterAt` also inserts it into the Spring Security chain. Thus the same custom filter risks being invoked twice per request, or executing outside security-chain boundaries under a different matcher. Exact behavior depends on configuration and auto-registration, so verify rather than assuming Spring deduplicates it.

**Safe approach used in the demo below:** instantiate `new AuthenticationWebFilter(...)` **inside the chain configuration method**, never exposing it as a global `WebFilter` bean. Beans hold only the verifier as a plain helper object, **implementing neither `WebFilter` nor `ReactiveAuthenticationManager` so it cannot affect the default manager**.

```java
@Bean
@Order(0)
SecurityWebFilterChain internalChain(
        ServerHttpSecurity http, ApiKeyVerifier verifier) {

    AuthenticationWebFilter keyFilter =
        new AuthenticationWebFilter(verifier::authenticate);

    keyFilter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers(
            HttpMethod.GET, "/internal/jobs"));

    // set converter and specific failure handler ...

    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/internal/**"))
        .addFilterAt(keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
        .build();
}
```

**This is a condensed snippet**; Section 9 has the complete code. If you write a genuine global `WebFilter` (e.g., request ID tracing), it runs on every route per system ordering; never also insert that same object into a security chain "just to be sure".

## 8. Policies Applied in the Demo

### 8.1 Routes

| Route | Auth Mechanism | Authentication Required? | Notes |
|---|---|---|---|
| `GET /internal/jobs` | `X-API-Key` | Yes | Only valid keys receive `SCOPE_jobs.read` |
| `GET /api/me` | HTTP Basic | Yes | Returns principal username |
| `GET /web/me` | Form login / session | Yes | Unauthenticated browsers are redirected |
| `GET /web/public` | No login required | No | Still passes through fallback security chain |
| `GET /login` | Generated login page | No | Belongs to web chain |
| Other URLs | Fallback web chain, `denyAll()` | Not auto-opened | Prevents accidental exposure from missing chain |

### 8.2 When Clients Send Credentials to the Wrong Route

| Request | Expected Outcome | Why |
|---|---|---|
| `GET /internal/jobs`, valid key | 200 | Key filter matches route and manager accepts |
| `GET /internal/jobs`, wrong key | 401 JSON | Authentication failed; no fallback allowed |
| `GET /internal/jobs`, missing key | 401 JSON | Converter empty; authorization still requires identity |
| `GET /internal/jobs` with Basic only | 401 JSON | Internal chain disables Basic |
| `GET /internal/jobs` with key + Authorization | 401 JSON | Demo intentionally rejects mixed credentials |
| `GET /api/me`, valid Basic | 200 | API chain accepts only Basic |
| `GET /api/me` with `X-API-Key` only | 401 with Basic challenge | Internal API-key filter does not run here |
| `GET /web/me` unauthenticated | Redirect to form login | Web chain enables neither API-key nor Basic |
| `GET /web/public` | 200 | Public route, no API-key attempt |
| `POST /internal/jobs` with key only | Not protected by GET matcher | Other rule/CSRF blocks; design separately before adding writes |

The demo keeps CSRF at its default because only GET endpoints are exposed; **never disable CSRF globally** just to make an example "easy to run". When adding POST, evaluate browser auto-sent credentials, CORS, `Content-Type`, and CSRF per chain.

## 9. Complete Example: Spring Boot 3.3.13, Java 17+

A design-complete runnable project using WebFlux + Spring Security and an in-memory user store. The key `demo-local-api-key` and password `dev-only-password` are strictly for localhost; production requires TLS, high-entropy keys, secret manager/hashing/rotation, and distinct service identities.

### 9.1 Directory Structure

```text
webflux-auth-matchers/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/match/MatchApplication.java
  src/main/java/example/match/ApiKeyVerifier.java
  src/main/java/example/match/SecurityConfiguration.java
  src/main/java/example/match/DemoController.java
  src/test/java/example/match/AuthenticationMatcherTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-auth-matchers'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.match'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
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
```

Servlet `spring-boot-starter-web` is not included in the project. `spring-security-test` provides WebFlux security test support when mock principals or CSRF helpers are needed, though the matrix below mostly sends real credentials to catch matcher bugs.

**src/main/resources/application.yml**

```yaml
demo:
  internal-api-key: demo-local-api-key
```

Never use this demo value as a production credential. In real environments, configure `demo.internal-api-key: ${INTERNAL_API_KEY}` supplied via a secret manager, paired with hashing and a rotation strategy. Never reuse the example credential as a real secret.

### 9.2 Application

**src/main/java/example/match/MatchApplication.java**

```java
package example.match;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatchApplication.class, args);
    }
}
```

### 9.3 ApiKeyVerifier: Verify Key Exactly Once, Never Trust Raw Headers

**src/main/java/example/match/ApiKeyVerifier.java**

```java
package example.match;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;

public final class ApiKeyVerifier {

    // Type lets converter record requests with multiple/mixed headers.
    // Never let toString() print the raw API key.
    public record SubmittedKey(String value, boolean malformed) {
        @Override
        public String toString() {
            return "[REDACTED]";
        }
    }

    private final byte[] expected;
    private final AtomicInteger attempts = new AtomicInteger();

    public ApiKeyVerifier(String configuredKey) {
        if (configuredKey == null || configuredKey.isBlank()) {
            throw new IllegalArgumentException("API key is required");
        }
        this.expected = configuredKey.getBytes(StandardCharsets.UTF_8);
    }

    public Mono<Authentication> authenticate(Authentication candidate) {
        return Mono.defer(() -> {
            attempts.incrementAndGet();

            Object credentials = candidate.getCredentials();
            if (!(credentials instanceof SubmittedKey submitted)
                    || submitted.malformed()
                    || !MessageDigest.isEqual(
                        expected,
                        submitted.value().getBytes(StandardCharsets.UTF_8))) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "internal-service",
                    null,
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_jobs.read"))));
        });
    }

    // Used only to prove one request does not invoke the manager repeatedly.
    public int attemptCount() {
        return attempts.get();
    }
}
```

**Analysis:**

- `ApiKeyVerifier` **does not implement `WebFilter`**, so Spring Boot will not auto-register it as a global `WebFilter`.
- It also **does not implement `ReactiveAuthenticationManager` directly as a bean** to avoid becoming the default authentication manager on Basic/form-login chains. Instead, the method reference `verifier::authenticate` satisfies the functional interface in `AuthenticationWebFilter`'s constructor.
- `AtomicInteger` is for **testing**, not a production security metric; never log secrets.
- `MessageDigest.isEqual` compares byte arrays to reduce early-exit string comparison risk. In production, keys need sufficient entropy, hashed/key-identifier/rotation storage, rate limits, TLS, and revocation; never rely solely on a demo string.
- Wrong keys emit `Mono.error(BadCredentialsException)`, **never** `Mono.empty()` to let another authentication mechanism try.
- Successful authentication grants only `SCOPE_jobs.read`. Never grant `ROLE_ADMIN` or read permissions from client-supplied headers.
- Never read `expected` from an HTTP request, query parameter, or debug endpoint.

### 9.4 SecurityConfiguration: 3 Chains, One Custom Filter in the Right Chain

**src/main/java/example/match/SecurityConfiguration.java**

```java
package example.match;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String API_KEY_HEADER = "X-API-Key";

    @Bean
    ApiKeyVerifier apiKeyVerifier(
            @Value("${demo.internal-api-key}") String configuredKey) {
        return new ApiKeyVerifier(configuredKey);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-only-password"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain internalChain(
            ServerHttpSecurity http,
            ApiKeyVerifier verifier) {

        // Do NOT @Bean AuthenticationWebFilter to avoid a global WebFilter.
        AuthenticationWebFilter keyFilter =
            new AuthenticationWebFilter(verifier::authenticate);

        // Second matcher layer: filter only cares about GET /internal/jobs.
        keyFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/internal/jobs"));

        // When matcher matches but no key is present, do not attempt authentication.
        keyFilter.setServerAuthenticationConverter(exchange -> {
            List<String> keys =
                exchange.getRequest().getHeaders().get(API_KEY_HEADER);

            if (keys == null || keys.isEmpty()) {
                return Mono.empty();
            }

            String submitted = keys.get(0) == null ? "" : keys.get(0);
            boolean malformed = keys.size() != 1
                || submitted.isBlank()
                || exchange.getRequest().getHeaders()
                    .containsKey(HttpHeaders.AUTHORIZATION);

            // If client provides a malformed key, still emit an
            // unauthenticated Authentication for the manager to reject;
            // DO NOT ignore it so another mechanism proceeds.
            return Mono.just(
                org.springframework.security.authentication
                    .UsernamePasswordAuthenticationToken.unauthenticated(
                        "internal-service",
                        new ApiKeyVerifier.SubmittedKey(
                            submitted, malformed)));
        });

        // Failure from wrong key or mixed credentials.
        keyFilter.setAuthenticationFailureHandler((filterExchange, ex) ->
            problem(filterExchange.getExchange(),
                HttpStatus.UNAUTHORIZED, "invalid_api_key"));

        // Key is authenticated for the current request only, no session created.
        keyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/internal/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/internal/jobs")
                    .hasAuthority("SCOPE_jobs.read")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((exchange, ex) ->
                    problem(exchange, HttpStatus.UNAUTHORIZED,
                        "api_key_required"))
                .accessDeniedHandler((exchange, ex) ->
                    problem(exchange, HttpStatus.FORBIDDEN,
                        "access_denied")))
            .addFilterAt(
                keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            // CSRF is not disabled; demo has GETs only.
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain basicApiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
        return http
            // No securityMatcher -> fallback chain.
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/error").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/web/me")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    private static Mono<Void> problem(
            ServerWebExchange exchange,
            HttpStatus status,
            String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().set(
            HttpHeaders.CACHE_CONTROL, "no-store");

        // Only server-chosen internal code values.
        // Never output raw exceptions, keys, passwords, or session IDs.
        String json = """
            {"type":"about:blank","title":"Unauthorized",
             "status":401,"detail":"Authentication required"}
            """;

        if (status == HttpStatus.FORBIDDEN) {
            json = """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"Access denied"}
                """;
        }

        // Never reflect codes from the request. This code may be used
        // in internal metrics, never log credentials.
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Key points to verify when reading the code:**

1. `SecurityWebFiltersOrder.AUTHENTICATION` places the custom key filter in the authentication phase **before** authorization. Never write an arbitrary global `WebFilter` expecting security context/ordering to behave the same.
2. `@Order(0)`, `@Order(1)`, and `@Order(2)` make chain order deterministic. The fallback chain protects URLs outside internal/API.
3. `internalChain` enables **only** the API-key mechanism; Basic/form are disabled on this chain. Basic requests to internal paths will not authenticate via Basic.
4. `keyFilter.setRequiresAuthenticationMatcher` narrows to GET/exact path; the converter runs only on matching requests.
5. The converter returns `Mono.empty()` solely when the **key header is absent**. Present headers that are wrong, blank, duplicated, or paired with `Authorization` are passed as credentials flagged `malformed` so the manager rejects them.
6. `ApiKeyVerifier.authenticate` executes only when the converter emits an authentication; tests verify the attempt count.
7. `NoOpServerSecurityContextRepository` is configured on both the filter and the HTTP security chain so key auth is not persisted into a login session for later requests. The `WebFilter` still populates the reactive `SecurityContext` for the **current request** upon success.
8. `basicApiChain` uses HTTP Basic with a separate in-memory account. There is no custom API-key filter in this chain; an `X-API-Key` header does not log in here.
9. `browserChain` uses form login and disables Basic. Unauthenticated browsers are redirected to the default login page.
10. `csrf` is **not disabled**. Demo GET endpoints need no CSRF token. Before adding unsafe POSTs to internal/API paths, design CSRF/method matchers/credential origins and test first.
11. The JSON writer never outputs raw tokens or detailed causes. You can include a stable error code like `invalid_api_key` / `api_key_required` in the body if required by your client contract, using server-side literals rather than exception messages.
12. The code above uses `@Bean ApiKeyVerifier` instead of `@Bean AuthenticationWebFilter`, separating verification logic from `WebFilter` lifecycle and registration.

### 9.5 Controller

**src/main/java/example/match/DemoController.java**

```java
package example.match;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping(value = "/internal/jobs",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> jobs(Principal principal) {
        return Mono.just(
            "jobs for " + principal.getName());
    }

    @GetMapping(value = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> apiMe(Principal principal) {
        return Mono.just(
            "basic user " + principal.getName());
    }

    @GetMapping(value = "/web/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webMe(Principal principal) {
        return Mono.just(
            "web user " + principal.getName());
    }

    @GetMapping(value = "/web/public",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }
}
```

Do not read raw credentials from the request inside the controller to re-verify. `Principal` arrives after the `SecurityWebFilterChain`, reflecting the authentication accepted by the matching mechanism. For real data, still enforce owner/tenant permissions in services/repositories; route-level authorities are not enough for object-level authorization.

### 9.6 Running with Gradle and curl

```bash
gradle bootRun

# Valid internal API-key:
curl -i -H "X-API-Key: demo-local-api-key" \
  http://localhost:8080/internal/jobs

# Internal missing key:
curl -i http://localhost:8080/internal/jobs

# Internal wrong key:
curl -i -H "X-API-Key: wrong-key" \
  http://localhost:8080/internal/jobs

# Basic API route; curl prompts for password, enter dev-only-password:
curl -i -u alice http://localhost:8080/api/me

# Passing key on Basic route cannot replace Basic:
curl -i -H "X-API-Key: demo-local-api-key" \
  http://localhost:8080/api/me

# Unauthenticated browser route: observe 302 without following:
curl -i -H "Accept: text/html" \
  http://localhost:8080/web/me

# Public:
curl -i http://localhost:8080/web/public
```

If a wrapper exists, use `./gradlew bootRun` or `gradlew.bat bootRun` on Windows. In PowerShell, you may need `curl.exe`. Never put real passwords in URLs or command-line history; keys and passwords in this lesson are strictly local lab data.

**Expected:**

```text
GET /internal/jobs (valid X-API-Key) -> 200, "jobs for internal-service"
GET /internal/jobs (missing key)     -> 401
GET /internal/jobs (wrong key)       -> 401
GET /api/me (Basic alice)            -> 200, "basic user alice"
GET /api/me (only X-API-Key)         -> 401 Basic challenge
GET /web/me (anonymous HTML)         -> 302 Location: /login
GET /web/public                      -> 200 "public"
```

`curl -L` follows redirects automatically; omit `-L` when inspecting the initial 302 response.

## 10. WebTestClient Tests: Proving No Duplicate Authentication

Tests run HTTP WebFlux with the real Security chain, sending valid and invalid credentials to verify which routes invoke `ApiKeyVerifier`.

**src/test/java/example/match/AuthenticationMatcherTest.java**

```java
package example.match;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationMatcherTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApiKeyVerifier verifier;

    @Test
    void internalWithValidApiKeyAuthenticatesExactlyOnce() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("jobs for internal-service");

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void missingApiKeySkipsManagerButCannotAccess() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void invalidApiKeyFailsOnceWithoutBasicFallback() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "incorrect")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void mixedInternalCredentialsAreRejected() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void duplicateApiKeyHeadersAreRejected() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key",
                "demo-local-api-key", "incorrect")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void basicApiDoesNotInvokeApiKeyManager() {
        int before = verifier.attemptCount();

        client.get().uri("/api/me")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("basic user alice");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void keyOnBasicRouteIsNotAValidCredential() {
        int before = verifier.attemptCount();

        client.get().uri("/api/me")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void basicOnInternalRouteDoesNotAuthenticate() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void anonymousWebPageRedirectsInsteadOfKeyAuth() {
        int before = verifier.attemptCount();

        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isFound()
            .expectHeader().valueMatches(
                HttpHeaders.LOCATION, ".*/login");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void publicPageDoesNotInvokeApiKeyVerifier() {
        int before = verifier.attemptCount();

        client.get().uri("/web/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void defaultLoginPageIsHandledByWebChain() {
        int before = verifier.attemptCount();

        client.get().uri("/login")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void matcherForGetDoesNotAcceptUnsafePost() {
        int before = verifier.attemptCount();

        // POST outside the GET authentication filter scope.
        // With CSRF enabled, 403 is the expected outcome for this request.
        client.post().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(before, verifier.attemptCount());
    }
}
```

The **12 test methods** intentionally check three things:

1. **Each valid-key request performs exactly one authentication attempt.** Checking `AtomicInteger` before and after catches duplicate filter registration or double manager invocation.
2. **Requests on other routes never invoke the verifier.** Basic routes, web routes, and the login page must not trigger the API-key manager.
3. **Missing keys, wrong keys, simultaneous credentials, or duplicate headers** never produce an unintended 200.

The `POST /internal/jobs` test simply proves the GET authentication matcher does not "spill over" to POST; default CSRF blocks unsafe POSTs. A real system must add tests for method-specific policies/CSRF whenever write endpoints exist.

Run:

```bash
gradle test
```

**QA scope:** the code has been reviewed against Spring Security 6.x APIs; **there is no executed Gradle build/test log** in this lesson. Verify against your actual dependency lockfile/versions before adopting. If duplicate-header tests are normalized differently by an HTTP stack/proxy than in tests, check your gateway's HTTP header normalization policy rather than prematurely blaming the auth filter.

### 10.1 Measuring Accurately in Real Integration Tests

`attemptCount` only measures **how many times the verifier's `authenticate` method was called**. It does not measure everything else:

- A filter might run twice while its converter returns `Mono.empty()` on one pass, leaving `attemptCount` unchanged; to distinguish that, add **filter-level instrumentation** in tests.
- WebFlux/Netty or a custom client could retry requests if configured; this lesson's `WebTestClient` configures no retries.
- An `AuthenticationManager` could invoke async dependencies multiple times within a single attempt; to ensure DB/IdP queries aren't duplicated, instrument the repository/HTTP client itself.
- If tests run in parallel, a global counter races across tests; run sequentially, use per-request metrics/correlation IDs, or mock strict invocation counts.
- Shared `WebFilter`s like CSRF, headers, and tracing still run; "one attempt" does not mean only one `WebFilter` ran.

In production, never store raw tokens for debugging; use correlation IDs and non-sensitive counters per route and credential type.

## 11. What If One Chain Must Support Multiple Mechanisms?

Some APIs support both OAuth2 Bearer and HTTP Basic in parallel during a migration. Here you cannot simply split by path when **the same path** is called by clients using either scheme.

### 11.1 Two Filters with Disjoint Credential Matchers

- Basic filter accepts only `Authorization: Basic ...`.
- Bearer filter accepts only `Authorization: Bearer ...`.
- API-key filter accepts only `X-API-Key`, while detecting a companion `Authorization` header to reject mixed credentials.
- Matchers must be disjoint or governed by an explicit precedence policy.
- Only **one** source may produce the authoritative `Authentication` for the request.

**Do not assume having two default filters on the same chain is automatically a vulnerability**: Spring Security can support multiple mechanisms simultaneously when done properly. The real issue is custom logic with overly broad matchers, converters fabricating authenticated tokens, or an unpolicied "try anything until one succeeds" fallback rule.

### 11.2 A Dispatching Converter

For custom mechanisms, you can use `DelegatingServerAuthenticationConverter` (where supported by your version) or write a routing `ServerAuthenticationConverter`:

```java
// Pseudocode for credential routing policy:
convert(exchange) {
    if (hasBothApiKeyAndAuthorization(exchange)) {
        return Mono.error(
            new BadCredentialsException("Ambiguous credentials"));
    }

    if (isBearer(exchange)) {
        return bearerConverter.convert(exchange);
    }

    if (isApiKey(exchange)) {
        return apiKeyConverter.convert(exchange);
    }

    return Mono.empty();
}
```

This is **pseudocode**, not compile-ready Java. The corresponding `ReactiveAuthenticationManager`/resolver must accept each converter's token type. When using a `DelegatingReactiveAuthenticationManager`, watch empty vs error semantics: **never turn a wrong credential from provider A into an opportunity for provider B to grant access** without an explicit policy.

### 11.3 AuthenticationManagerResolver for Multiple Issuers/Tenants

Spring Security Reactive provides `AuthenticationWebFilter(ReactiveAuthenticationManagerResolver<ServerWebExchange>)`. It lets you select **which manager** handles a request in legitimate scenarios. However, never trust unvalidated client-supplied `Host`, `tenant`, or `issuer-uri` values to run metadata discovery and create new managers; that invites SSRF, IdP mix-up, and cache poisoning. Enforce an issuer/tenant allowlist, proper JWT key validation, and a consistent authentication policy.

### 11.4 Leverage Built-In JWT Resource Server

When protecting Bearer JWTs, prefer:

```java
@Bean
@Order(0)
SecurityWebFilterChain jwtApiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/jwt/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .build();
}
```

This is a **config fragment** requiring `ReactiveJwtDecoder` and issuer/JWK configuration; do not paste it verbatim into Section 9's demo. If adding it alongside a `/api/**` Basic chain, place the **JWT chain before the Basic chain** so the narrower matcher is not shadowed by the broader one. Enable proper scope/authority/audience policies (not merely `authenticated()`), and test expired/invalid-signature rejections plus 401/403 separation.

## 12. Matchers and Other Security Considerations

### 12.1 URLs Matched by No Security Chain

If a developer declares only:

```java
.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**"))
```

with **no** fallback chain, other routes can go unprotected by Spring Security. The framework does not automatically turn every URL outside `/api/**` into 403. Keep a catch-all chain with `anyExchange().denyAll()` for unexpected routes, and test "unlisted" endpoints with multi-role users.

### 12.2 Shadowed Authorization Rules

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN"))
```

This is an **example of misordered rules**: the broader rule comes first and matches admin routes, never reaching the stricter rule. Put narrower rules before broader ones, with `anyExchange()` last. Likewise, verify `@Order` between narrow and broad chains.

### 12.3 Never Base Permissions on Accept or User-Agent

You may inspect `Accept: text/html` to choose between a 302 HTML redirect and a 401 JSON error **after** authentication fails. However, `Accept`/`User-Agent`/`X-Requested-With` never prove whether a client is a human or a service. Never grant roles or route access because a User-Agent looks like an internal browser.

### 12.4 Same Route, Two Credentials, and an Existing Logged-In Session

Suppose a browser has a valid session yet sends an **invalid** `Authorization: Bearer` header to an API: your policy must define the response clearly. Never silently fall back to the logged-in session to ignore a bad token when the endpoint contract demands Bearer. Separate `/api/**` into a stateless resource-server chain and disable form/session login on API routes where architecture permits.

### 12.5 CSRF and Authentication Matchers

CSRF guards against browsers automatically attaching credentials, typically on unsafe methods. A custom matcher that skips POST **does not solve CSRF**, and `permitAll` does not disable CSRF either. With HTTP Basic where browsers cache credentials, CSRF can still apply; never disable CSRF globally just because a URL starts with `/api`.

### 12.6 CORS Preflight

Browsers may send `OPTIONS` before a Bearer/API-key request. Configure `CorsConfigurationSource` and Spring Security WebFlux CORS integration with explicit origin/method/header allowlists. Do not require an API key on a browser preflight that sends no credentials; equally, never open `permitAll` across all methods/routes just to silence preflight errors. The demo exposes GET only and does not configure cross-origin support.

### 12.7 Registering Custom WebFilters Outside Spring Security

A `@Component WebFilter` running in WebFlux's global chain may run before, after, or outside the expected order of the Spring Security filter chain. Never invent an authenticated principal by calling `exchange.getAttributes().put("user", ...)` expecting Spring Security's authorization to recognize it as an `Authentication`.

When a custom mechanism truly performs authentication, use `AuthenticationWebFilter`/`ReactiveAuthenticationManager`/`ReactiveSecurityContextHolder` at the right order. A global filter used for tracing/metrics must not contain secret authentication logic.

### 12.8 Stateless vs Session Persistence

`NoOpServerSecurityContextRepository` avoids persisting API-key/Basic `SecurityContext` between requests. Yet it **does not automatically make the entire application "completely stateless"**: CSRF, request caches, or other features may still create a `WebSession`. If true statelessness is required, audit all `WebFilter`s, request caches, CSRF repositories, cookies, and business sessions individually rather than merely setting a NoOp repository.

### 12.9 Header Normalization and Duplicate Credentials

HTTP proxies may merge multiple header lines into one comma-separated value or treat `Authorization` specially. Filters must never assume "one header name present" always equals one verified value. For API keys:

- Enforce a single credential per contract.
- Reject whitespace/blank/duplicate values, oversized headers, and unsupported schemes.
- If traffic passes through a proxy, verify how the proxy normalizes duplicate headers **before** validation.
- Rate-limit and authenticate by key ID/trusted identity; never log raw keys.
- Keys/tokens must have high entropy, rotation, and revocation; API keys should not replace user delegation when per-user authorization is needed.

## 13. Diagnosing 401, 403, 302, or Duplicate Filter Execution

| Symptom | Suspect | Check |
|---|---|---|
| Valid key on `/internal/jobs` always returns 401 | Wrong matcher; converter emits no Authentication; manager not called; wrong configured key | Check `@Order`, header name, manager attempt count |
| Basic request to `/internal/jobs` succeeds | Internal chain accidentally enabled Basic or matcher too narrow | Check `securityMatcher`/HTTP Basic spec |
| `/api/me` succeeds with API key | Custom `WebFilter` registered globally or Basic converter didn't block | Check `@Bean WebFilter` and `addFilterAt` |
| One request increments attempt count by 2 | Filter added twice, retry/re-subscription, or multiple converters/managers | Instrument filter entry, manager subscribe, and request ID |
| `/api/**` receives HTML login page | Web chain caught request before API or failed Basic hit form entry point | Check `@Order`/`securityMatcher`/`entryPoint` |
| Wrong key header still returns 200 | Manager returned `Mono.empty()` and another filter granted access; session fallback | Fail closed on wrong credentials, separate schemes |
| Path matches chain yet returns 403 with valid key | Wrong authority, HTTP method mismatch, or CSRF block | Check filter/authorizeExchange/CSRF matchers |
| POST with key returns 403 | CSRF or `anyExchange().denyAll()` | Design CSRF + explicit method rules; never disable everything |
| OPTIONS preflight returns 401 | CORS not processed before auth | Check origin/method/headers and chain CORS policy |
| `/login` returns 404/403 | Missing fallback chain or generated login page disabled | Check `formLogin`, login `permitAll`, chain matchers |
| Undeclared route is accessible | No chain matched, or overly broad `permitAll` | Add fallback `denyAll`, test unknown URLs |
| Invalid-signature Bearer succeeds via session | Multiple schemes allowed on route without clear policy | Split Bearer/stateless chain, fail closed |
| Two Authentication types appear in logs | Two filters both processed, overwriting context | Check converters/matchers and identity precedence |
| Auth manager queries DB/IdP multiple times | Side effects inside `Mono` subscribed/retried; duplicate global filter | Measure subscribe count, eliminate redundant requests |
| Custom filter runs on `/health` | Global `WebFilter` or default any-request requires matcher | Set narrow matcher and chain-scoped filter |
| Client authenticated rightly but wrong tenant | Route-level auth only, missing data-level authorization | Enforce ownership/tenant checks in service/repository |

**Better than logging credentials:** emit an event/counter `auth_attempt{route,mechanism,outcome}` without secrets, attach a correlation ID, and log safe exception mappings.

## 14. Test Suite Needed for Real Systems

| Category | Cases | Must Assert |
|---|---|---|
| Chain selection | `/internal`, `/api`, `/web`, `/login`, unknown URLs | Exactly one matching chain and safe fallback |
| Filter matching | GET target path, POST same path, OPTIONS, similar paths | Custom filter activates strictly within scope |
| Key conversion | Missing, blank, wrong, duplicated key | Never succeeds; never silently falls back |
| Mixed credentials | Basic+key, Bearer+key, Cookie+Bearer | Clear ambiguity policy, no identity override |
| Basic auth | Valid/invalid credentials | Correct 200/401 challenge |
| Browser form login | Missing session, valid login/CSRF, logout | Correct 302/login and session persistence |
| Reactive context | Authenticated request followed by keyless request | Zero cross-request context leakage |
| Filter duplication | Each valid-key request increments manager attempt by 1 | No double registration or retries |
| Authorization | Missing authority, admin route, `denyAll` | Appropriate 403/401, no data leak |
| Resource Server | Expired/bad-sig/wrong-aud JWT | Fails closed before controller |
| HTTP errors | Wrong credential vs missing credential | Failure handler and entry point follow policy |
| CSRF/CORS | Unsafe methods, preflight | Protections never disabled for matchers |
| Multi-chain | Narrow matchers before broad ones | No rule shadowing |
| Multi-instance | Key rotation, revocation, caches, counters | Revoked keys rejected everywhere |
| Observability | Auth attempt events, login failures | Zero plaintext passwords/API keys/access tokens |

## 15. Implementation Checklist

1. Map out a route → credential scheme table before writing Security config.
2. Create separate `SecurityWebFilterChain`s for route groups with different auth models when possible.
3. Assign explicit `@Order` for overlapping matchers; narrower matchers before broader ones.
4. Include a fallback chain so unknown URLs never escape Spring Security.
5. Inside each chain, use `authorizeExchange` for permissions; filter matchers do not replace authorization.
6. On custom `AuthenticationWebFilter`, explicitly set `setRequiresAuthenticationMatcher` and `setServerAuthenticationConverter`.
7. Converter returns `Mono.empty()` only when that mechanism's credential is absent, never when it is invalid.
8. Authentication manager accepts only its intended token type and returns an error on invalid credentials.
9. Reject conflicting credentials transparently rather than using "try until one succeeds".
10. Instantiate custom filters **inside the chain**, never also registering them as global `WebFilter` beans.
11. Scope `SecurityContext` cleanly to the request or session; prevent cross-request authentication leaks.
12. For Basic/JWT, prefer built-in authentication filters over hand-rolling parsing or token validation.
13. Never treat `X-User`/`X-Role` headers as permission proof; derive permissions from verified identity.
14. Protect API keys with TLS, high entropy, hashing, rotation, revocation, and scope/tenant limits.
15. Keep CSRF/CORS policies aligned with your threat model; test both `OPTIONS` and unsafe methods.
16. Assert converter/manager invocation counts alongside 200/401/403/302 responses.
17. Keep audits/traces free of credentials; prevent retry/auth loops and duplicate side effects.
18. After upgrading Spring Security, re-run the matcher/filter-order and HTTP behavior test matrix.

## 16. Practice Exercises

1. Diagram the three matcher layers in the demo, explaining why `/api/me` never invokes the API-key verifier.
2. Swap `@Order(0)` and `@Order(2)` so the web catch-all comes first. How do the outcomes change? Restore immediately after testing.
3. Remove `setRequiresAuthenticationMatcher` from the key filter and observe whether the converter runs on more paths in that chain; why is that unnecessary or suboptimal?
4. Change the converter for bad keys to return `Mono.empty()`. Explain the risk if another authentication filter is added later.
5. Expose the custom `AuthenticationWebFilter` as a `@Bean` **and** call `addFilterAt` to observe the duplication hazard, then revert to chain-only.
6. Add `GET /internal/status` permitting only an API key with `SCOPE_status.read`; write matchers and tests isolating roles/scopes.
7. Send both `X-API-Key` and Basic to `GET /internal/jobs`. Why does the demo return 401 instead of accepting the valid key?
8. Write tests sending an empty API-key header, two API-key headers, or an oversized value; define a fail-closed policy.
9. Add a `/api/jwt/**` JWT chain before the `/api/**` Basic chain and verify a wrong-audience token returns 401.
10. Allow CORS preflight for a specific Origin/Method/Header without requiring a key on `OPTIONS`. Never open every route with `permitAll`.
11. Add a POST endpoint and test missing vs valid CSRF; explain why a GET-only API-key matcher grants no POST protection.
12. Compare `NoOpServerSecurityContextRepository` with `WebSessionServerSecurityContextRepository`. Why do stateless Basic APIs and web form logins have different expectations?
13. Track converter calls and verifier attempts with two separate counters. When does a request increment the converter counter without incrementing the verifier?
14. Design a policy for when a browser has an active session yet an API call carries an invalid Bearer token: reject or fall back? Why?
15. Use `ReactiveAuthenticationManagerResolver<ServerWebExchange>` for an allowlisted multi-tenant setup; explain how to prevent SSRF and issuer mix-up.
16. Inspect test logs to confirm **zero** plaintext API keys, Basic passwords, Bearer tokens, or session cookies appear.

## Summary

Selecting authentication mechanisms in Spring Security Reactive requires distinguishing **three levels**: `securityMatcher` decides **which `SecurityWebFilterChain`** handles the request; `setRequiresAuthenticationMatcher` decides **whether an `AuthenticationWebFilter` attempts authentication**; `ServerAuthenticationConverter` checks whether a matching credential exists to form an attempt; and `authorizeExchange.pathMatchers` enforces **post-authentication access rights**. To avoid duplicate processing, prefer one chain per route group with distinct credential schemes, declare explicit ordering, never register custom `WebFilter`s twice (global bean + `addFilterAt`), never turn invalid credentials into `Mono.empty()`, and preserve boundaries across authentication, authorization, and sessions. When multiple mechanisms must share a route, enforce explicit ambiguity/failure policies rather than trying each until one succeeds. Verify with `WebTestClient` and count **manager attempts per request**, while keeping CSRF/CORS, JWT validation, and object-level authorization intact.

## Official Resources

1. Spring Security 6.5 — WebFlux Security, Multiple SecurityWebFilterChains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
2. Spring Security 6.5 — AuthenticationWebFilter Javadoc (matcher, converter, failure/success, NoOp context): https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
3. Spring Security 6.3 — ServerAuthenticationConverter Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
4. Spring Security 6.5 — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
5. Spring Security 6.3 — WebFlux authentication components: https://docs.spring.io/spring-security/reference/6.3/reactive/authentication/index.html
6. Spring Security 6.5 — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
7. Spring Security 6.5 — WebFlux CSRF security: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
8. Spring Framework — WebFlux WebFilter and reactive request processing: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
