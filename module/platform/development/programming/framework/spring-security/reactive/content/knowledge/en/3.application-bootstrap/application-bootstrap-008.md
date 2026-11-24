# Creating Public Endpoints and Authenticated Endpoints in Spring Security Reactive

> **Topic:** Spring Security - reactive · **Group:** Application Bootstrap  
> **Hands-on outcome:** a Spring Boot WebFlux application with `GET /api/public` accessible without logging in and `GET /api/private` returning data only when the caller is authenticated. Includes source code, run commands, HTTP test commands, and automated tests.

## 1. Requirements and target behavior

In a real application, not every path requires login. Landing pages, public information, or health endpoints are often accessed anonymously; profile pages, orders, or user actions must have an authenticated identity. **The goal of this lesson is to establish that boundary right when bootstrapping a WebFlux application**.

We will create two endpoints:

| Endpoint | Policy | Result when not logged in | Result with valid login |
| --- | --- | --- | --- |
| `GET /api/public` | `permitAll()` | **200 OK**, `{"message":"Public endpoint"}` | **200 OK**, same content |
| `GET /api/private` | `authenticated()` | **401 Unauthorized**, requesting credentials | **200 OK**, `{"username":"student"}` with the demo account |

Both endpoints use HTTP **GET** and do not mutate data. Paths outside this list are configured with `denyAll()` to avoid accidentally exposing new endpoints. The example uses **HTTP Basic** because the authentication lifecycle is easy to observe; this option is **for local learning environments**, with no account creation, user registration, or JWT issuance.

### Distinguish three concepts before writing code

- **Public endpoint:** requires no identity to be granted path access. `permitAll()` does not mean bypassing all security filters or guaranteeing requests carrying invalid credentials are ignored.
- **Authenticated endpoint:** requires a valid `Authentication`, not in an anonymous state; `authenticated()` does not yet check roles, scopes, or permissions on specific data.
- **Authentication vs. authorization:** HTTP Basic + user store determine who is calling; `authorizeExchange` decides which URLs are permitted; for sensitive business data, role, owner, or tenant checks must be added at the appropriate layer.

## 2. Request flow in WebFlux Security

~~~mermaid
flowchart TD
    A["HTTP GET request"] --> B["WebFlux: SecurityWebFilterChain"]
    B --> C{"GET /api/public?"}
    C -->|"Yes"| D["permitAll → controller"]
    C -->|"No"| E{"GET /api/private?"}
    E -->|"No"| F["denyAll → deny access"]
    E -->|"Yes"| G{"Valid Authentication?"}
    G -->|"No"| H["HTTP Basic challenge → 401"]
    G -->|"Yes"| I["authenticated → controller"]
    I --> J["Get username from Reactor SecurityContext"]
    J --> K["200 + JSON username"]
    D --> L["200 + public JSON"]
~~~

In WebFlux, `SecurityWebFilterChain` processes requests through `WebFilter`s; the controller only runs when prior rules allow it. `ServerHttpSecurity` is the security configuration API for **Reactive WebFlux**, differing from `HttpSecurity` for Servlet MVC. `SecurityContext` info in a reactive flow propagates via **Reactor Context**, so do not read it by assuming a `ThreadLocal` fixed to a single request.

**Note on the diagram:** real applications have additional filters, credential verification can occur before the URL permission decision step, and 401/403 errors are also influenced by the login mechanism and exception handling. This diagram helps clarify the main boundaries of the lesson.

## 3. Creating a runnable sample project

Requirements: **JDK 17+**, Maven, port **8080** unused. The example below uses Spring Boot **3.3.13** to illustrate the Spring Boot 3.3 line; open-source support for 3.3 has ended, so new production projects should pick a **currently supported Spring Boot release** and cross-check APIs for that version. The Java APIs in this lesson follow the Spring Security 6 / WebFlux model.

Project structure:

~~~text
reactive-public-private/
├── pom.xml
├── src/
│   ├── main/java/example/reactive/
│   │   ├── ReactiveSecurityApplication.java
│   │   ├── SecurityConfig.java
│   │   └── ApiController.java
│   └── test/java/example/reactive/
│       └── ApiSecurityTest.java
~~~

### 3.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-public-private</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
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

**Dependency roles:** `starter-webflux` provides the reactive web server, controllers, and Reactor; `starter-security` provides Spring Security WebFlux, authentication, and HTTP rules; `starter-test` provides JUnit, Spring Test, and `WebTestClient` for HTTP testing. In this lesson **do not add `spring-boot-starter-web`**, to avoid accidentally running on the Servlet MVC model in the same sample app.

### 3.2. Spring Boot entry point

File `src/main/java/example/reactive/ReactiveSecurityApplication.java`:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables auto-configuration and component scanning in package `example.reactive`, so `SecurityConfig` and `ApiController` in the same package will be discovered.

## 4. Writing the two endpoints in the controller

File `src/main/java/example/reactive/ApiController.java`:

~~~java
package example.reactive;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "Public endpoint"));
    }

    @GetMapping("/api/private")
    public Mono<Map<String, String>> privateEndpoint() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }
}
~~~

**Detailed explanation:**

1. `@RestController` returns JSON directly; `@GetMapping` binds the HTTP GET method to the exact path. Both methods return `Mono<...>`, fitting WebFlux.
2. The public endpoint returns fixed data, without reading an identity or manually triggering a login.
3. The private endpoint obtains `SecurityContext` via `ReactiveSecurityContextHolder.getContext()`, then returns the principal's name from `Authentication`. With the demo account, `getName()` is `student`.
4. The controller does **not** manually decode Basic headers, check passwords, or compare roles. Those tasks belong to Spring Security and the authorization layer.
5. Do not call `block()` to get the user: the method still returns a publisher. When an authenticated request arrives, Spring Security supplies the security context inside the reactive pipeline.

**Important condition:** `privateEndpoint()` is designed to run only through a chain that has checked `authenticated()`. If you call the method directly like an ordinary Java method, bypassing HTTP security, `ReactiveSecurityContext` may be absent and the `Mono` result empty. Do not view that as a method that protects itself when called from anywhere; restricting business actions via services still needs separate controls.

## 5. Declaring public and authenticated policies

File `src/main/java/example/reactive/SecurityConfig.java`:

~~~java
package example.reactive;

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

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private").authenticated()
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
    MapReactiveUserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails student = User.withUsername("student")
            .password(passwordEncoder.encode("demo-pass"))
            .roles("STUDENT")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
~~~

### 5.1. How does this configuration work?

- `@EnableWebFluxSecurity` activates reactive security configuration. The `SecurityWebFilterChain` bean inserts the rules into the request pipeline.
- `.pathMatchers(HttpMethod.GET, "/api/public").permitAll()` opens **specifically GET** to `/api/public`. Do not infer that POST or every path starting with `/api/public` is also open.
- `.pathMatchers(HttpMethod.GET, "/api/private").authenticated()` requires an authenticated `Authentication`. Role `STUDENT` is assigned to the demo user, but **is not an authorization condition** for this endpoint.
- `.anyExchange().denyAll()` denies any request not matching the rules above. Whether a nonexistent endpoint yields 404 or is blocked earlier by security depends on the request, authentication, and configuration, so do not assume a single fixed status for all other paths.
- `.httpBasic(Customizer.withDefaults())` enables Basic authentication: clients send header `Authorization: Basic <base64(username:password)>`. Base64 **does not encrypt secrets**, so HTTPS is mandatory outside local tests.
- `.formLogin(...disable)` disables the form login flow in the API example so unauthenticated requests receive a **401 Basic challenge** instead of redirecting to an HTML login page.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates a password encoder with an algorithm prefix, typically using bcrypt. The demo password is stored encoded in memory, not plaintext in `UserDetails`. However, the string `demo-pass` in source is **only acceptable for local learning**, not for production.
- `MapReactiveUserDetailsService` provides sample accounts for the reactive authentication mechanism. In real systems, replace it with a trusted user store/identity provider and corresponding credential management policy.

### 5.2. Why must `permitAll()` be placed before general rules?

Authorization rules are evaluated in match order. With this configuration:

~~~java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated()
    .pathMatchers("/api/public").permitAll()
)
~~~

Placing `anyExchange()` first can cause the public rule never to apply, or cause the configuration to be rejected because the catch-all matcher already terminated the chain. Declare specific rules first, and the fallback rule last:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/private").authenticated()
    .anyExchange().denyAll()
)
~~~

The example uses only **one** `SecurityWebFilterChain`. If a project has multiple chains, Spring Security selects a chain by `securityMatcher` and `@Order`; `pathMatchers` inside one chain does not replace chain-selection rules.

### 5.3. Differences from Servlet MVC

| Aspect | WebFlux / Reactive (this lesson) | Servlet MVC |
| --- | --- | --- |
| HTTP configuration | `ServerHttpSecurity` | `HttpSecurity` |
| Security filter | `SecurityWebFilterChain` / `WebFilter` | `SecurityFilterChain` / servlet filter |
| User details | `ReactiveUserDetailsService` | `UserDetailsService` |
| Reading security context in pipeline | `ReactiveSecurityContextHolder` | Usually `SecurityContextHolder` |
| Endpoint return value | `Mono<T>`, `Flux<T>` | Direct value, `ResponseEntity<T>`, etc. |

Do not mix `HttpSecurity` into a WebFlux example or place `SecurityContextHolder.getContext()` inside a reactive flow expecting it to remain valid across thread hops.

## 6. Starting the app and testing HTTP requests

In the directory containing `pom.xml`, run:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Use another terminal window to test. The commands below use `curl`; on Windows PowerShell 5.1, use `curl.exe` if `curl` is aliased to `Invoke-WebRequest`.

### 6.1. Public endpoint, no credentials sent

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expected JSON body:

~~~json
{"message":"Public endpoint"}
~~~

Expected HTTP status: **200 OK**. The request has no `Authorization`, yet `permitAll()` lets it reach the controller.

### 6.2. Private endpoint, not logged in

~~~bash
curl -i http://localhost:8080/api/private
~~~

Expected HTTP status: **401 Unauthorized**. With HTTP Basic, the response normally includes a `WWW-Authenticate` header telling the client how to send credentials. Error bodies and headers depend on configuration; no specific JSON format is pinned in this lesson.

### 6.3. Private endpoint, valid credentials

~~~bash
curl -i -u student http://localhost:8080/api/private
~~~

`curl` will prompt for a password. Enter `demo-pass` in the terminal. Expected HTTP status: **200 OK**; JSON:

~~~json
{"username":"student"}
~~~

Putting real passwords directly into commands like `-u student:password` in shell history or shared docs is discouraged. The `-u student` prompt syntax above fits local testing.

### 6.4. Private endpoint, wrong password

~~~bash
curl -i -u student http://localhost:8080/api/private
~~~

This time enter a password **different from** `demo-pass`. Expected HTTP status: **401 Unauthorized**, because the server cannot authenticate the credential pair. If the account does not exist, the outcome also falls into the authentication-failed branch; applications should not reveal which users exist via error messages.

### 6.5. Observation and explanation table

| Request | Authorization header | Applied rule | Expected status |
| --- | --- | --- | --- |
| GET /api/public | None | `permitAll()` | 200 |
| GET /api/private | None | `authenticated()` | 401 |
| GET /api/private | Valid Basic | `authenticated()` | 200 |
| GET /api/private | Invalid Basic | Authentication fails | 401 |
| GET /api/public | Valid Basic | `permitAll()` | 200 |
| POST /api/public | None | Rule only opens GET; security/CSRF may deny | Do not expect 200 |

**Small trap:** a request having an `Authorization` header **does not mean it is logged in**. The header may be wrong, expired (for tokens), or unsupported by the active authentication mechanism. `authenticated()` only passes when Spring Security produces a valid `Authentication`.

## 7. Automated testing with WebTestClient

You should not verify by looking at a single 200 response alone. Tests must prove **both branches**: public and protected.

File `src/test/java/example/reactive/ApiSecurityTest.java`:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ApiSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Public endpoint");
    }

    @Test
    void privateEndpointRejectsAnonymousRequest() {
        client.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsCorrectCredentials() {
        client.get()
            .uri("/api/private")
            .headers(headers ->
                headers.setBasicAuth("student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");
    }

    @Test
    void privateEndpointRejectsWrongPassword() {
        client.get()
            .uri("/api/private")
            .headers(headers ->
                headers.setBasicAuth("student", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

**Four branches proven here:**

1. `permitAll()` genuinely allows anonymous access to the specific URL.
2. `authenticated()` blocks anonymous requests.
3. HTTP Basic + the real user store in the test context accurately checks passwords and builds a principal.
4. Wrong passwords are rejected.

The `RANDOM_PORT` test boots the application to send real HTTP to a random test port. Unlike calling a controller method via `new`, this test goes through WebFlux + the security filter chain.

Because this is a sample app, password and username are fixed in test code. When scaling up, use fixtures or dedicated test identity providers, never production credentials.

## 8. Authentication and authorization: what to know before expanding

**HTTP 401** is when credentials are missing or invalid for a resource requiring an identity. **HTTP 403** usually indicates the caller is authenticated but not permitted to perform the action. The two cases differ:

~~~text
GET /api/private
    ├── unauthenticated           → 401
    └── authenticated             → 200

GET /api/admin (if adding hasRole("ADMIN") policy)
    ├── unauthenticated           → 401
    ├── authenticated, not ADMIN  → 403
    └── authenticated, has ADMIN  → allowed to proceed
~~~

In the lesson's code, `student` has role `STUDENT`, corresponding to authority `ROLE_STUDENT`, yet `/api/private` **does not require this role**. If you change the rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/private")
    .hasRole("STUDENT")
~~~

then the endpoint switches to requiring a specific role permission. The role snippet above is an **illustrative variant**, not to be used alongside the initial config if matching expected test statuses. `hasRole("STUDENT")` checks authority `ROLE_STUDENT`; do not write `hasRole("ROLE_STUDENT")` when the default `ROLE_` prefix applies.

If the endpoint returns orders/profiles belonging to multiple people, being logged in or having `ROLE_STUDENT` still does **not** prove permission to view a given record. The service/repository layer must verify owner, tenant, status, or business rules. This lesson only establishes the initial public/private boundary.

## 9. Choosing the right login mechanism for the context

The sample uses **HTTP Basic + In-memory users** to clarify the difference between anonymous and authenticated requests. When designing real applications, the mechanism can change:

| Mechanism | How identity is sent | When to consider | Notes |
| --- | --- | --- | --- |
| HTTP Basic | `Authorization: Basic ...` on request | Demos, internal tools with TLS, simple cases | Credentials are re-sent on every request; requires HTTPS and secret management |
| Form login + session | Browser sends session cookie | Websites with user sessions | Analyze CSRF, cookie flags, session lifecycle |
| OAuth2 Resource Server / Bearer JWT | `Authorization: Bearer ...` | APIs protected by an issuer/authorization server | Verify signature, issuer, expiry, audience, and claim mapping |
| OIDC login | Authorization Code flow and ID token for login | Websites wanting login via an identity provider | Distinguish ID tokens from access tokens used to call APIs |

**Do not** replace HTTP Basic by inventing an `X-Username` header or trusting a `?user=...` query parameter: those are not authentication mechanisms. If switching to JWT, simply swap in the appropriate authentication config and test with tokens, while the concepts of `permitAll()`, `authenticated()`, and data-level protection remain valid.

## 10. Security hygiene to keep even in small examples

### 10.1. HTTPS and credentials

HTTP Basic encodes data with Base64, **not encryption**. `http://localhost:8080` is only for lab environments. Over real networks HTTPS is required, avoid logging `Authorization` headers, and use secret stores/identity providers instead of fixed accounts in source.

### 10.2. CSRF

The example **does not disable CSRF**: Spring Security protects state-changing requests by default; two read-only GET endpoints do not need CSRF tokens for normal operation. If you add POST/PUT/DELETE, an otherwise validly authenticated request may receive **403** due to a missing CSRF token. Do not fix this by unconditionally disabling CSRF. For APIs using Bearer tokens explicitly attached by clients with no auto-authenticating cookies, disabling CSRF may be considered after evaluating the threat model. With cookie/session logins, CSRF protection is normally needed.

### 10.3. CORS is not authentication

CORS decides whether a browser may read a response from another origin; it does **not** grant access to resources and does not replace `authenticated()`. Do not add `Access-Control-Allow-Origin: *` to "fix" 401/403 errors. If a frontend is on another origin, specify allowed origins, methods, headers, and credential policies explicitly.

### 10.4. `permitAll` does not skip all checks

The `permitAll()` rule only states that matching requests require no access permission. If a client deliberately sends a bad Basic header, the authentication filter can still detect it and return 401. Thus, a true test of a public endpoint must use a request **without credentials**. Conversely, an authenticated client can still hit `denyAll()` on disallowed paths.

### 10.5. Do not overuse public paths

Expose only necessary routes, limit returned data (do not leak emails, secrets, internal resources), and consider rate limiting and separate caching for public content. Do not add `/api/**.permitAll()` just to make every endpoint "work" during development.

## 11. Common errors and how to diagnose them

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `/api/public` returns 401 | Rule shadowed by `anyExchange`, wrong path/method, or client sends invalid Basic header | Check matcher order; test curl without Authorization |
| `/api/private` returns 200 when not logged in | Accidentally opened public too broadly or security chain not activated | Check `@EnableWebFluxSecurity`, active chain, URL match, and negative tests |
| Valid account gets 401 | Wrongly encoded password/mismatched password encoder, wrong username, bad Basic header | Check `MapReactiveUserDetailsService` and password prefix; do not log passwords |
| Public GET returns 200 but POST gets 403 | Rule only opens GET, or missing CSRF token | Distinguish method, route authorization, and CSRF |
| Request redirects to `/login` instead of 401 | Form login is still enabled for that request/chain | Disable form login for APIs or use the appropriate chain/mechanism |
| Cannot retrieve principal in pipeline | Reading context against the wrong reactive model or calling controller directly | Use `ReactiveSecurityContextHolder` inside the publisher and test over HTTP |
| Config fails to compile | Used `HttpSecurity`/Servlet API in a WebFlux project or wrong version | Verify `ServerHttpSecurity`, `SecurityWebFilterChain` imports, and dependencies |
| Request outside the two routes returns an unexpected status | Security denies before routing or a different entry point applies | Check `denyAll` rule, auth state, and HTTP response; do not always assume 404 |

To diagnose, read in order: **method + URL → SecurityWebFilterChain → credentials → Authentication → matcher → controller**. For this lesson, there is no need to write custom filters, custom JWT parsers, or manually manipulate `SecurityContext`.

## 12. Practice exercises

**Exercise A — add a public endpoint:** create `GET /api/version` returning `{"version":"1.0"}`, opening only GET in the security configuration. Prove it is accessible without login and other methods are not automatically permitted.

**Exercise B — role-based protection:** add user `viewer` with `ROLE_VIEWER` and `GET /api/admin` restricted to `ROLE_ADMIN`. Write tests distinguishing: unauthenticated (401), viewer login (403), and admin login (200). Do not use this test to alter `/api/private` behavior unless intended.

**Exercise C — UI integration:** use `WebTestClient` or a cross-origin frontend to observe a CORS issue. Explain why a browser CORS error does not mean the request was unauthenticated, and why adding a CORS rule does not grant access to private endpoints.

**Exercise D — switch to Bearer tokens:** keep the two endpoints/rule groups, replace authentication with OAuth2 Resource Server using a valid test issuer. Verify 401 on missing/invalid tokens, 200 on valid tokens, and add a 403 example when an authority is missing. This is an extension step requiring separate identity provider config and tests.

### Self-assessment checklist

- [ ] Application starts with WebFlux and Spring Security, without mixing Spring MVC.
- [ ] `GET /api/public` returns 200 and the right JSON when **no** Authorization header is sent.
- [ ] `GET /api/private` returns 401 when anonymous or with a wrong password.
- [ ] `GET /api/private` returns 200 and the username when Basic credentials are valid.
- [ ] `anyExchange().denyAll()` is last and does not accidentally expose other paths.
- [ ] `mvn test` verifies all four scenarios above.
- [ ] Can explain the differences between `permitAll()`, `authenticated()`, `hasRole()`, and 401/403.
- [ ] Do not use Basic over HTTP in real environments; do not disable CSRF indiscriminately; do not store production credentials in source.

## 13. Self-check questions

1. Why doesn't the `/api/private` controller need to parse the `Authorization` header itself?
2. Why should `permitAll()` be placed before `anyExchange().denyAll()`?
3. What does `GET /api/private` with a wrong password return, and why does it differ from a user with the right password who lacks role ADMIN?
4. If the controller is changed to return `Mono<UserDto>` from a reactive service, should you call `block()` to get the principal first?
5. If the frontend reports a CORS error when calling `/api/private`, can you conclude the user is not logged in?
6. When adding `POST /api/items` in an application using cookies/sessions, why must CSRF be evaluated even though the route already has `authenticated()`?
7. If a logged-in user can call `/api/orders/42`, which layer ensures order 42 actually belongs to that user or their tenant?

Once you can answer these questions and complete the test matrix, you have the foundation to expand from **HTTP authentication** to **route, method, and business-level authorization**.

## 14. Official documentation

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive user stores.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): HTTP matchers and authorization rules.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html): Basic authentication in Reactive.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): contexts requiring CSRF and how to configure it.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): `@RestController`, reactive return types, and request mapping.
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html): `spring-boot-starter-parent` structure and how to use Maven.

**Core result:** two endpoints can live in the same controller, yet the **access policy** lives in `SecurityWebFilterChain`: one path allows anonymous callers with `permitAll()`, and one path allows only valid `Authentication` with `authenticated()`. Prove both behaviors with HTTP requests and negative tests before adding business permission conditions.