# Enabling HTTP Basic in SecurityWebFilterChain

> **Scope:** Configuring HTTP Basic for **Spring Security reactive / Spring WebFlux**, using Spring Boot 3.x, Spring Security 6.x, and Java 17+. The goal is to properly declare `SecurityWebFilterChain` with `ServerHttpSecurity.httpBasic(...)`, authenticate username/password using a reactive user service, enforce access permissions, and verify HTTP behavior. Hard-coded passwords appearing below are strictly for localhost practice exercises.

## Learning objectives

After this lesson, you can:

1. Explain `Authorization: Basic <credentials>`, the `401 Unauthorized` response, and the `WWW-Authenticate` header.
2. Enable HTTP Basic with `http.httpBasic(Customizer.withDefaults())` in `SecurityWebFilterChain`, distinguishing this API from Spring MVC's `HttpSecurity`/`SecurityFilterChain`.
3. Configure `MapReactiveUserDetailsService`, `PasswordEncoder`, and `authorizeExchange` rules.
4. Test **200 (authorized), 401 (unauthenticated or invalid credentials), and 403 (authenticated but missing permissions)** statuses using curl and `WebTestClient`.
5. Understand session scope, CSRF, HTTPS, error handling, multiple filter chains, how to disable HTTP Basic, and scenarios where Basic should not be used in production.

## 1. How does HTTP Basic work?

HTTP Basic is an HTTP **authentication scheme**. The client sends username/password on each request in the `Authorization` header:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic cmVhZGVyOnJlYWRlci1wYXNz
```

The example header above contains the Base64 of `reader:reader-pass`, purely to illustrate syntax. **Base64 is representational encoding, not security encryption:** anyone who obtains the header can decode the username/password back. Therefore, when connecting over real networks, you must use **HTTPS/TLS**, and protect credentials from unnecessary logs, proxies, and monitoring tools.

The client usually receives a challenge first:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The `realm` value is an **illustrative example**; do not write tests that hard-depend on the default realm name. The `WWW-Authenticate` header informs the client of the authentication method the server accepts. Once it has credentials, the client retries the request with `Authorization: Basic ...`. Some clients know the credentials ahead of time and send them immediately without waiting for 401.

### 1.1 Authentication vs. Authorization

| Concept | Meaning | Example |
| --- | --- | --- |
| **Authentication** | Server verifies who the caller is | Valid username/password → `Authentication` object |
| **Authorization** | Server decides what that person can do | `ROLE_READER` can access `/api/me`; missing `ROLE_ADMIN` cannot access `/api/admin` |
| **HTTP Basic** | How an HTTP request transports credentials | `Authorization: Basic ...` |
| **ReactiveAuthenticationManager** | Credential verification API in WebFlux | Returns `Mono<Authentication>` or appropriate error/empty |
| **SecurityWebFilterChain** | HTTP security filter set of Spring WebFlux | Basic authentication, security context, authorization, CSRF, headers |
| **ReactiveSecurityContextHolder** | Reads the reactive request/subscription context | Retrieves username/authorities after authentication |

Enabling Basic **does not automatically grant access** to any endpoint. `httpBasic(...)` sets up the **authentication method**; `authorizeExchange(...)` decides the **access rules**.

### 1.2 HTTP Basic is not a login page

- With HTTP Basic, the client sends credentials in `Authorization`; the server does not need to serve an HTML form to collect a password.
- Browsers may automatically display a prompt dialog upon receiving a Basic challenge, depending on the browser and request context.
- Typical form login handles form/cookie/session and redirects when unauthenticated; that is a **different mechanism**.
- Spring Security can configure **both Basic and form login** if the use case requires it, but for APIs using only Basic we usually disable form login so clients receive **401** instead of unexpectedly redirecting to a login page.

## 2. Where does SecurityWebFilterChain sit in WebFlux?

`SecurityWebFilterChain` is a set of `WebFilter`s applied to matching `ServerWebExchange` requests. Spring Security reactive uses `WebFilterChainProxy` and WebFilters to handle security before Spring WebFlux invokes an annotated controller or functional route handler.

Simplified logical flow:

```text
Client (HTTP Basic request)
    |
    v
WebFlux HttpHandler / WebFilter pipeline
    |
    v
Spring Security WebFilterChainProxy
    |
    +-- selects SecurityWebFilterChain by securityMatcher
    |
    +-- HTTP Basic authentication filter
    |     |
    |     +-- reads Authorization: Basic ...
    |     +-- creates unauthenticated UsernamePasswordAuthenticationToken
    |     +-- invokes ReactiveAuthenticationManager
    |     +-- authenticates successfully or reports error
    |
    +-- SecurityContext in Reactor Context
    |
    +-- authorizeExchange (path/method/role)
    |
    +-- may return 401 or 403 and short-circuit request
    |
    v
DispatcherHandler
    |
    +-- @RestController / @GetMapping
    +-- RouterFunction / HandlerFunction
    |
    v
HTTP response
```

The diagram only illustrates **conceptual stages** and does not guarantee that every physical `WebFilter` has the exact order or names shown. Specific components also vary by configuration/version.

**Key takeaway:** Basic credentials are processed by Spring Security **inside the WebFilter pipeline**, not by a controller manually Base64-decoding the password. The controller only receives the request after security policies are satisfied. If both Controllers and RouterFunctions exist on one WebFlux server, `SecurityWebFilterChain` protects them uniformly by URL/method.

## 3. Distinguishing Reactive Security from Servlet Security

Do not confuse the two configuration APIs:

| Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| Servlet `Filter` | Reactive `WebFilter` |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityContextHolder` typically ThreadLocal-bound | `ReactiveSecurityContextHolder` uses Reactor Context |

If Spring Boot has **both** `spring-boot-starter-web` (MVC) and `spring-boot-starter-webflux`, Boot usually **prefers Spring MVC** under default auto-detection. Having `WebClient` or `Mono` classes does not prove the server is WebFlux. To follow this lesson properly, use **only `spring-boot-starter-webflux`** for the HTTP server, unless you explicitly force `WebApplicationType.REACTIVE` and test at runtime.

## 4. Setting up the practice project

Use Spring Initializr to create a Spring Boot 3.x app, **Java 17+**, Gradle Groovy, adding dependencies:

- Spring Reactive Web (`spring-boot-starter-webflux`)
- Spring Security (`spring-boot-starter-security`)
- Spring Boot Test (`spring-boot-starter-test`)

Equivalent dependency block in `build.gradle` for a project that already has the Boot plugin and dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The sample project consists of four files under the same package:

```text
src/
  main/java/com/example/basicwebflux/
    BasicWebfluxApplication.java
    SecurityConfig.java
    ApiController.java
  test/java/com/example/basicwebflux/
    HttpBasicIntegrationTest.java
```

Package names across all files must match; if you use a different package, update `package` declarations and directory paths consistently. The Java code below requires Spring Boot/Spring Security/Reactor dependencies. **Do not compile standalone with `javac` without the framework classpath**; use the project's Gradle wrapper.

### 4.1 Main class — BasicWebfluxApplication.java

`src/main/java/com/example/basicwebflux/BasicWebfluxApplication.java`:

```java
package com.example.basicwebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicWebfluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicWebfluxApplication.class, args);
    }
}
```

Because `@SpringBootApplication` component-scans the current package and subpackages, `SecurityConfig` and `ApiController` are also registered as beans in the same application context.

## 5. Enabling HTTP Basic in SecurityWebFilterChain

### 5.1 SecurityConfig.java — complete code

`src/main/java/com/example/basicwebflux/SecurityConfig.java`:

```java
package com.example.basicwebflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

This is a **fully working configuration in the Boot project above**, without needing to manually create `AuthenticationWebFilter` or decode Base64 yourself. Spring Security WebFlux registers the necessary components when `@EnableWebFluxSecurity` and `SecurityWebFilterChain` are properly declared.

### 5.2 Explaining each key line

**`@EnableWebFluxSecurity`**

Enables security support for WebFlux. This is not the `@EnableWebSecurity` annotation for Servlets. It also **does not change** the web stack type if Spring Boot already chose MVC due to dependencies; ensure the app actually runs on WebFlux.

**`SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http)`**

Declares the web security bean for the reactive server; `ServerHttpSecurity` is the WebFlux DSL. `http.build()` builds the chain after you define rules and authentication. Do not return a Servlet `SecurityFilterChain`.

**`authorizeExchange(...)`**

Rules are evaluated in order:

1. `GET /public/**` — public.
2. `GET /api/admin` — requires admin role.
3. `GET /api/**` — authenticated users can call.
4. `anyExchange().denyAll()` — remaining requests are denied per authorization policy.

Place `/api/admin` **before** `/api/**`, because a broad matcher placed first would shadow the admin requirement. With `hasRole("ADMIN")`, Spring Security checks for authority `ROLE_ADMIN`. `User.roles("ADMIN")` automatically adds the `ROLE_` prefix; do not pass `roles("ROLE_ADMIN")`.

**`httpBasic(Customizer.withDefaults())`**

Enables HTTP Basic with Spring Security WebFlux's default settings. `Customizer.withDefaults()` tells the DSL to use defaults; it **does not create users**, **does not grant roles**, and **does not replace** `authorizeExchange`.

**`formLogin(ServerHttpSecurity.FormLoginSpec::disable)`**

Disables form login in the demo chain so the API focuses on HTTP Basic, returning a 401/challenge when requests lack credentials instead of form-login behavior. Disabling form login does not disable CSRF or security headers.

**`MapReactiveUserDetailsService`**

Creates an in-memory reactive user store for the practice exercise. It implements `ReactiveUserDetailsService` and can be automatically used by Spring Security to construct the password authentication manager for Basic when no other custom manager overrides it. Production should replace it with a properly managed user store/IdP mechanism.

**`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**

Creates a `DelegatingPasswordEncoder`; by default, calling `encode` typically produces a string with the `{bcrypt}` prefix and a salted hash. Do not store raw passwords or use `{noop}` in production. The resulting hashes are salted, so do not expect identical values across runs.

### 5.3 CSRF is not disabled in the example

Spring Security WebFlux enables CSRF protection by default. The demo endpoints are **GET**, so no CSRF token is needed to call them. For POST/PUT/PATCH/DELETE, requests may be rejected by the CSRF filter **before** the handler runs if no token is present, even when Basic authentication succeeds.

Do not preemptively add `.csrf(ServerHttpSecurity.CsrfSpec::disable)` to the lesson just so any POST request works. For **browsers** capable of automatically sending HTTP Basic credentials after authentication, CSRF can still be an issue for state-changing requests. Only consider changing CSRF policy once you clearly understand the client types, credential auto-sending behavior, browser origins, and threat model.

## 6. Creating three endpoints to test policies

`src/main/java/com/example/basicwebflux/ApiController.java`:

```java
package com.example.basicwebflux;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> me() {
        return currentUsername().map(name -> "Hello " + name);
    }

    @GetMapping(
        value = "/api/admin",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> admin() {
        return currentUsername().map(name -> "Admin " + name);
    }

    private Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

**Analysis:** The controller does not check passwords directly. When Basic credentials are valid, the authentication filter handles authentication first; Spring Security puts the details into the request's Reactor Context. `ReactiveSecurityContextHolder` reads the username from that context.

Do not call Servlet's ThreadLocal-based `SecurityContextHolder.getContext()` inside a reactive handler. Do not call `block()` to retrieve the principal on a WebFlux event-loop thread; keep logic inside `Mono` / `Flux`.

### 6.1 Expected results per user

| Request | Credentials | Expected HTTP | Body on success |
| --- | --- | --- | --- |
| GET `/public/ping` | None | **200 OK** | `pong` |
| GET `/api/me` | None | **401 Unauthorized** | No application body |
| GET `/api/me` | `reader` + correct password | **200 OK** | `Hello reader` |
| GET `/api/me` | `reader` + wrong password | **401 Unauthorized** | No application body |
| GET `/api/admin` | `reader` + correct password | **403 Forbidden** | No application body |
| GET `/api/admin` | `admin` + correct password | **200 OK** | `Admin admin` |
| GET `/api/admin` | None | **401 Unauthorized** | No application body |
| POST `/api/me` | Any | Not handled by GET handler; may be blocked by CSRF/authorization | N/A |

**Note:** `/api/admin` is placed before `/api/**` in the authorization rules. If reversed, `reader` could be allowed through because the authenticated rule matches first, causing an authorization bug even when Basic authenticates properly.

## 7. Testing with curl

From the Gradle project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

By default, the application usually runs at `http://localhost:8080` if the port has not been changed and no other app occupies it. Use **HTTP on localhost only for the demo**; never send real credentials over unencrypted public networks.

### 7.1 Public and unauthenticated requests

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/admin
```

Expected:

```text
GET /public/ping  -> 200, body pong
GET /api/me       -> 401 when missing Basic header
GET /api/admin    -> 401 when missing Basic header
```

The 401 response typically includes `WWW-Authenticate: Basic ...`. Specific realm values, security headers, and HTTP protocol versions may differ across environments. Do not test by matching the entire raw HTTP response string.

### 7.2 Valid Basic username/password

Use curl with `-u` so **curl prompts for the password interactively** instead of placing it directly in the command line:

```bash
curl -i -u reader http://localhost:8080/api/me
curl -i -u reader http://localhost:8080/api/admin
curl -i -u admin http://localhost:8080/api/admin
```

When curl prompts, enter the corresponding demo password:

- `reader`: `reader-demo-password`;
- `admin`: `admin-demo-password`.

Calling `/api/me` as `reader` expects 200, body `Hello reader`. Calling `/api/admin` as `reader` expects 403 due to missing ADMIN role. Calling `/api/admin` as `admin` expects 200, body `Admin admin`.

**Do not write** `curl -u reader:your-real-password` in shell history in real environments. Do not copy raw `Authorization` headers containing real passwords into tickets/logs. If debugging is needed, mask the header or log only the request path and HTTP status.

### 7.3 Explaining Base64 yourself to understand the protocol

For the string `reader:reader-demo-password`, the client computes Base64 for the entire `username:password` and attaches:

```http
Authorization: Basic <BASE64_OF_USERNAME_COLON_PASSWORD>
```

This is a **protocol placeholder**, not a valid header to paste and run. Use curl or an HTTP client to generate a proper header. Base64 may have trailing `=` characters (padding) depending on byte count; international characters in usernames/passwords must be handled by client/server according to compatible HTTP Basic charsets/standards.

The core principle remains unchanged: **HTTPS/TLS protects the wire transport**, not Base64. If a client sends tokens/credentials over an unencrypted connection, an intermediary can capture the secret.

## 8. Testing HTTP Basic with WebTestClient

The most important test is sending requests **actually through Spring Security's WebFilterChain** using Basic headers, rather than placing a principal directly into the context and assuming HTTP Basic works.

Create `src/test/java/com/example/basicwebflux/HttpBasicIntegrationTest.java`:

```java
package com.example.basicwebflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpBasicIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }

    @Test
    void anonymousRequestIsChallenged() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void correctBasicCredentialsAreAccepted() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello reader");
    }

    @Test
    void incorrectPasswordReturns401() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "not-the-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderIsForbiddenOnAdminRoute() {
        client.get()
            .uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.get()
            .uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Admin admin");
    }

    @Test
    void credentialsAreRequiredOnEachIndependentRequest() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk();

        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
./gradlew test --tests '*HttpBasicIntegrationTest'
```

Or on Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*HttpBasicIntegrationTest'
```

These assertions thoroughly verify:

- Public endpoints remain accessible without credentials.
- Without Basic credentials, protected requests receive 401/challenge.
- Correct passwords authenticate, and SecurityContext contains the username.
- Wrong passwords do not result in an authenticated request.
- Authenticated users lacking the ADMIN role receive 403.
- Admins with sufficient permissions receive 200.
- After a request with a Basic header, a **subsequent request does not automatically inherit** the previous request's authentication in the demo setup.

**Note:** These tests use in-memory demo passwords and a random-port HTTP server in the test process. Results are **expected from the sample configuration**, not stdout captured from an actual build run here. If a project adds other security configurations, different profiles, custom repositories, proxies, or MVC dependencies, inspect the active configuration before diagnosing 401/403 errors.

### 8.1 Why not just use mockUser?

`spring-security-test` provides `mockUser()` and `@WithMockUser` to help test authorization. They are very useful, but **do not prove that the Basic header is parsed or that the password is verified**. A `mockUser` test can pass even when HTTP Basic is disabled.

To accurately test this lesson, use `headers.setBasicAuth(...)` on `WebTestClient` and run full-context tests like above. You can add mock-user tests to isolate authorization; the two test levels serve different purposes.

### 8.2 Checking rule order: a regression exercise

Try swapping:

```java
.pathMatchers(HttpMethod.GET, "/api/**").authenticated()
.pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
```

in place of the two lines in that order in `SecurityConfig`. Then the `/api/**` rule coming first can let `reader` into `/api/admin`, causing the `validReaderIsForbiddenOnAdminRoute` test to fail.

**Fix:** place the more specific `/api/admin` rule before `/api/**`, and maintain 403 tests to catch mistakes when adding new endpoints.

## 9. Customizing HTTP Basic to fit your needs

The most basic configuration only needs:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is an **alternative bean** when you want to protect all requests; it requires imports and a suitable `ReactiveAuthenticationManager`/`ReactiveUserDetailsService`. Calling `httpBasic` does not supply passwords itself. If you already use the full bean in section 5, do not declare this minimal bean alongside it unless intentionally configuring multiple chains with ordering/matchers.

### 9.1 Specifying a custom ReactiveAuthenticationManager

When you want to verify passwords via a custom mechanism, `HttpBasicSpec` lets you configure a `ReactiveAuthenticationManager`:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        ReactiveAuthenticationManager manager) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(basic -> basic.authenticationManager(manager))
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
```

This is an **alternative** to the `securityWebFilterChain` bean in section 5; it requires a valid `ReactiveAuthenticationManager` bean configured elsewhere. Import `ReactiveAuthenticationManager` from `org.springframework.security.authentication`. The manager must verify credentials before returning an authenticated `Authentication`—never return `Mono.just(...)` with roles taken from unverified input.

Besides the manager, `ServerHttpSecurity.HttpBasicSpec` also lets you customize `authenticationEntryPoint`, `authenticationFailureHandler`, and `securityContextRepository`. Customize these only when policy requirements and corresponding tests demand it; defaults are a good starting point.

### 9.2 When should HTTP Basic be disabled?

If the application switches completely to OAuth2 Bearer JWT or form login only, do not leave Basic accidentally enabled.

```java
http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        Customizer.withDefaults()
    ));
```

This is a **configuration snippet**, not a complete file; it requires the Resource Server dependency, `ReactiveJwtDecoder`, and proper issuer/audience configuration. Do not call `http.build()` twice or combine this snippet with `httpBasic(withDefaults())` in the same chain if the goal is to disable Basic. An OIDC/browser app might use `oauth2Login(...)` or another session mechanism instead of Basic.

**Distinction:** `httpBasic(...disable)` disables the **HTTP Basic** mechanism; it does not disable all authentication mechanisms or make endpoints public. `authorizeExchange` still governs route decisions.

### 9.3 Multiple SecurityWebFilterChains: Basic for one area only

A system might want:

- `/internal/**`: HTTP Basic with automation accounts.
- `/api/**`: JWT Resource Server.
- `/web/**`: OAuth2 Login/session.

This design typically requires **multiple `SecurityWebFilterChain` beans**, each with a `securityMatcher` and `@Order`; Spring Security selects **the first matching chain**, rather than stacking every chain onto the same request.

Conceptual diagram:

```text
@Order(1) chainInternal  -> securityMatcher("/internal/**") -> httpBasic()
@Order(2) chainApi       -> securityMatcher("/api/**")      -> jwt()
@Order(3) chainWeb       -> catch-all                       -> oauth2Login()
```

This is **architectural pseudocode**, not standalone Java. In real applications, choose matchers, authentication providers, and fallback chains carefully; if you only create a Basic chain matching `/internal/**` and omit other chains, URLs outside that matcher **are not protected by that chain**. Do not rely on `anyExchange().authenticated()` in a narrow-matcher chain to protect all URLs.

### 9.4 Enforce HTTPS/TLS, do not confuse with Base64

In production, protect the HTTP channel with TLS, configure proxies/ingress and certificates properly, and accept credentials only over HTTPS. HTTPS enforcement can be configured at the reverse proxy or in Spring Security depending on the environment. Basic typically resends username/password on **every request**, increasing the sensitivity of access logs and transport paths.

Do not treat `Authorization: Basic ...` like a JWT with expiry/scope/audience. Basic carries long-lived credentials as long as the account/password has not changed; lifecycle management, authentication protection, and system-level brute-force defenses are needed.

## 10. HTTP Basic and sessions, CSRF, CORS

### 10.1 Basic does not inherently require session cookies

In WebFlux HTTP Basic configuration, the Basic filter authenticates **each request carrying a matching header**; by default, `HttpBasicSpec` uses `NoOpServerSecurityContextRepository` for Basic context storage. Thus the example does not use Basic as a "log in once and rely on a session" mechanism.

However, **do not conclude the entire app is strictly stateless** solely because Basic is enabled. Other features such as form login, OAuth2, CSRF token repositories, WebSession, and custom components may use sessions. Audit the full configuration before claiming statelessness or setting cookie policies.

### 10.2 Keep CSRF when browsers auto-send credentials

If clients always use `Authorization` headers explicitly added by code and **never auto-sent by browsers** across cross-origin requests, the threat model can differ from cookie/session apps. However, HTTP Basic remembered by a browser can be sent automatically by that browser for the same protection space. **Do not treat "Basic" as sufficient justification to disable CSRF**.

In Spring Security WebFlux, CSRF is typically enabled by default. Data-reading GET/HEAD requests should not have side effects. For POST/PUT/PATCH/DELETE, determine how clients obtain and send CSRF tokens if forged browser requests are a risk. If an API is strictly well-defined machine-to-machine, you can design a separate security chain/matcher and disable CSRF **for the appropriate scope** after evaluation, rather than mechanically disabling it app-wide.

### 10.3 CORS does not replace authentication

CORS restricts which web pages a browser permits to read responses and controls preflight; it does not prove identity. Browsers using JavaScript with `Authorization` usually trigger a CORS preflight when cross-origin. Allow the needed headers/methods for the **exact origins** via CORS policy—never casually set `Access-Control-Allow-Origin: *` alongside credentials.

CORS preflight requests can be blocked by `SecurityWebFilterChain` if not configured properly. Test this scenario explicitly; do not solve it by making all of `/api/**` public.

## 11. Diagnosing 401, 403, and 404 errors

### 11.1 Common causes table

| Symptom | Likely assessment | What to check |
| --- | --- | --- |
| No `Authorization` sent → 401 | Expected when calling a protected route | Check route/rules and `WWW-Authenticate` header |
| Basic sent but still 401 | Wrong password, unknown username, encoder mismatch, malformed header | Check user store/encoder; do not log raw passwords |
| Authenticated user gets 403 | Missing authority/role, or CSRF on unsafe method | Check `hasRole`/`hasAuthority`, CSRF token, and HTTP method |
| Public GET returns 401 | `permitAll` rule didn't match, or another chain was selected | Check path/method matchers, `securityMatcher`, and `@Order` |
| Reader succeeds on admin route | `/api/**` rule placed before admin rule | Order matchers from specific to general |
| 302 redirect to `/login` instead of 401 | Form login / another entry point still active | Disable form login in the API chain or inspect selected chain |
| 404 on expected route | Controller not scanned, wrong path, missing handler | Check mappings; security does not create routes |
| Authenticated POST gets 403 | Missing/invalid CSRF token, or authorization denial | Do not blindly disable CSRF; trace the handling path |
| User works in unit tests but real HTTP returns 401 | Test bypasses filter or Basic header wasn't sent | Use full-context `WebTestClient` and Basic headers |
| 401 after sending updated correct password | Password hash/user store changed, cache/account policy | Check user source and active version/config |
| 401 when sending Bearer token | Basic filter does not authenticate Bearer credentials | Enable OAuth2 Resource Server if API uses Bearer |
| Basic works in MVC but not in WebFlux | Wrongly used Servlet DSL or Boot picked MVC | Check `ApplicationContext` and security chain type |

An HTTP status has no single source: **401** usually relates to authentication challenge/failure; **403** can come from authorization denial or CSRF; **404** relates to handler mapping after passing filters. Inspect security logs and integration tests to distinguish them rather than looking at the status code alone.

### 11.2 Why must UserDetailsService be reactive?

This lesson uses `MapReactiveUserDetailsService`. In real systems, you can implement `ReactiveUserDetailsService.findByUsername(String)` returning `Mono<UserDetails>` from a reactive database/repository. The authenticator checks the password using `PasswordEncoder.matches(...)` and builds the appropriate authenticated principal.

Do not write blocking database code on the event loop wrapped in `Mono.just(blockingCall())`: `blockingCall()` still executes synchronously before the Mono is even created. If integrating legacy blocking code is unavoidable, offload it to an appropriate executor/scheduler, apply load limits, and measure latency.

### 11.3 PasswordEncoder and hash prefixes

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` uses encoding IDs such as `{bcrypt}...`. The error `There is no PasswordEncoder mapped for the id "null"` commonly occurs when a plain-text password without a prefix is improperly passed into `DelegatingPasswordEncoder`.

In the demo, `encoder.encode(...)` is called before creating the user, avoiding this issue. Production should store **hashed passwords** using an appropriate password hashing algorithm (bcrypt/Argon2/PBKDF2 per policy), rather than storing raw passwords in databases or property files. Do not hardcode `{noop}` to work around errors.

## 12. Comparing HTTP Basic with Bearer/JWT and form login

| Criterion | HTTP Basic | Bearer/JWT Resource Server | Form login / session |
| --- | --- | --- | --- |
| Header/credential | Username/password in Base64 | `Authorization: Bearer <token>` | Form submit, typically sets a session cookie |
| Verification | Password authentication manager/user store | JWT decoder/opaque introspection; issuer/audience/scope | Login flow, session/security context |
| Credential transmission | Typically every HTTP request | Access token on every request | Cookie/session automatically sent by client |
| Best fit | Internal admin APIs, demos, simple clients with TLS | Standardized REST APIs and service-to-service | Traditional browser web applications |
| Expiration/revocation | Depends on account/password policy | Token expiry, revocation/introspection, and IdP design | Session expiry, logout/invalidation |
| Key risks | Password leaks in logs/HTTP; brute-force | Leaked bearer token; wrong issuer/audience/algorithm | CSRF/session fixation/cookie security |

Do not say HTTP Basic is "always insecure" in every context: with TLS, secret management, least privilege, rate limiting, and operational controls, it can fit simple clients. However, for large-scale APIs and systems needing scoped access, token expiry, or delegated identity, OAuth2/OIDC or workload identities are generally more appropriate than transmitting a user's primary password on every request.

## 13. Configuration mistakes to avoid

1. **Confusing `SecurityFilterChain` with `SecurityWebFilterChain`:** the Servlet type is not what the WebFlux request pipeline uses. Pick `ServerHttpSecurity` and the reactive runtime.
2. **Enabling Basic without configuring authorization:** can leave unexpected default policies. Explicitly declare `authorizeExchange` and test every sensitive endpoint.
3. **Creating users without calling `httpBasic(...)`:** Spring Security has contextual defaults, but a custom chain should not rely on implicit defaults. Enable Basic explicitly in the bean.
4. **Placing broad matchers before narrow matchers:** `/api/**` could let `reader` access `/api/admin`. Test rule precedence.
5. **Using `{noop}` or plaintext in production:** protect passwords with a proper encoder and credential store.
6. **Sending Basic over real HTTP:** Base64 is trivial to decode. Test HTTP only on localhost with dummy data; mandate HTTPS/TLS in deployment.
7. **Logging the `Authorization` header or passwords:** scrub logs at gateways/reverse proxies/applications, and avoid curl commands with real passwords.
8. **Mechanically disabling CSRF:** especially dangerous with browsers that auto-send credentials; evaluate the threat model.
9. **Putting self-asserted usernames into `Authentication`:** bypasses password verification. Let the manager/provider validate credentials.
10. **Using `@WithMockUser` as proof that HTTP Basic works:** mockUser bypasses Basic header parsing; write integration tests with headers.
11. **Not checking multiple chains:** the Basic config may sit in a chain that does not match the intended URL; use `securityMatcher` and `@Order` properly.
12. **Confusing 401 and 403:** missing/wrong credentials differ from authenticated but unauthorized. Distinguish them in tests and client handling.
13. **Allowing state-changing requests via GET:** CSRF defenses may assume GET is safe; use proper HTTP methods and add CSRF protection.
14. **Assuming Basic is always completely stateless:** other security components may use WebSession; audit the entire configuration.
15. **Ignoring rate limiting and brute-force protection:** Basic can be targeted with password guessing; protect at ingress/IdP/account controls.

## 14. Self-check quiz

**Question 1.** In WebFlux, what enables HTTP Basic properly when writing `SecurityWebFilterChain`?

**Answer:** `.httpBasic(Customizer.withDefaults())` on `ServerHttpSecurity`, or `.httpBasic(basic -> ...)` when customization is needed. Do not use Servlet `HttpSecurity` for a reactive pipeline.

**Question 2.** Is `Authorization: Basic ...` securely encrypted?

**Answer:** No. The part after Basic is Base64 of `username:password`, which can be decoded. HTTPS/TLS protects credentials in transit.

**Question 3.** Why does an unauthenticated request get 401 while `reader` accessing `/api/admin` gets 403?

**Answer:** 401 requests authentication, whereas `reader` has a valid principal but lacks `ROLE_ADMIN`, so authorization denies it.

**Question 4.** What happens if `.pathMatchers("/api/**").authenticated()` is declared before `.pathMatchers("/api/admin").hasRole("ADMIN")`?

**Answer:** The broader rule can match first, bypassing the admin restriction. Put the specific rule first.

**Question 5.** Must username/password be stored in a session cookie to use Basic?

**Answer:** No. Clients can send the Basic header on every request. However, other application components may still use sessions, so do not equate enabling Basic with everything being stateless.

**Question 6.** Do you have to disable CSRF to enable HTTP Basic?

**Answer:** No. The GET endpoints in this lesson work with CSRF enabled. For state-changing methods, decide CSRF handling based on browser/client/credential behavior and forgery risk rather than unconditionally disabling it globally.

**Question 7.** Why do `@WithMockUser` tests pass while curl Basic still returns 401?

**Answer:** MockUser only injects a test authentication and can bypass Basic credential parsing/verification. Check username/password, encoder, `httpBasic(...)`, active chain, and use `WebTestClient.headers(setBasicAuth)` for real tests.

**Question 8.** If an API uses Bearer JWT, should `httpBasic` be used to read the JWT?

**Answer:** No. Bearer JWT uses OAuth2 Resource Server with a JWT decoder and proper validation. Basic uses username/password. The two schemes have different converters and managers.

## 15. Pre-completion checklist

- [ ] Boot is running **WebFlux reactive**, not accidentally using Servlet due to MVC dependencies.
- [ ] A `SecurityWebFilterChain` exists with `ServerHttpSecurity` and `.httpBasic(Customizer.withDefaults())`.
- [ ] Form login is intentionally kept or disabled per chain's clients.
- [ ] A valid `ReactiveUserDetailsService` or `ReactiveAuthenticationManager` and secure password encoder are configured.
- [ ] `authorizeExchange` is clearly configured, specific matchers precede general ones, and a safe fallback rule exists.
- [ ] Public endpoints return 200 without credentials; protected endpoints return 401 when Basic credentials are missing or invalid.
- [ ] Valid username/password returns 200; user lacking role gets 403; admin with role gets 200.
- [ ] Browser/API CSRF, CORS, HTTP methods, and session semantics are evaluated.
- [ ] Production enforces HTTPS/TLS, protects password/`Authorization` logs, rate limiting, and credential rotation.
- [ ] Real HTTP Basic integration tests were run, not just `mockUser` tests.
- [ ] If multiple `SecurityWebFilterChain` beans exist, `securityMatcher`, `@Order`, and the actually selected chain are verified.

**Conclusion:** To enable HTTP Basic in Spring Security reactive, declare a `SecurityWebFilterChain` using `ServerHttpSecurity.httpBasic(Customizer.withDefaults())`, provide a user service/manager that verifies passwords, and set `authorizeExchange` for endpoints. HTTP Basic authenticates the caller; authorization decides permissions. Test 200/401/403 with `WebTestClient` to prove the system behaves properly; always use TLS when transmitting real credentials.

### Official references

- [Spring Security 6.5 — WebFlux Security and httpBasic configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — WebFlux testing authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Framework — WebFlux Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [RFC 7617 — The "Basic" HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617)
