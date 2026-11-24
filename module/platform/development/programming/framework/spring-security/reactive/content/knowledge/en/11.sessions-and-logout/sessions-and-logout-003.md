# Distinguishing Stateful Applications from Stateless Authentication in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Knowledge group:** Sessions and logout  
> **Goal:** Distinguish session-based login persistence from per-request independent authentication; understand the impact of `WebSession`, cookies, `SecurityContext`, Bearer tokens, and logout; practice two separate WebFlux configurations and verify behavior with `WebTestClient`.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain that "**stateful authentication**" means the server or session store retains authentication information across multiple HTTP requests; "**stateless authentication**" means each request carries enough credentials for the server to re-authenticate without reading a prior login session.
2. Distinguish `WebSession`, the `SESSION` cookie, `SecurityContext`, `Reactor Context`, HTTP Basic, Bearer access tokens, and refresh tokens.
3. Configure WebFlux using `WebSessionServerSecurityContextRepository` for form login and `NoOpServerSecurityContextRepository` for per-request authenticated APIs.
4. Predict what happens to the next request when dropping the cookie, dropping the `Authorization` header, when a token expires, or on logout.
5. Explain why **logout can invalidate a server session immediately** yet does not automatically revoke all issued JWTs.
6. Analyze trade-offs between server-side sessions and token-based APIs regarding CSRF, XSS, credential storage, multi-instance scaling, permission revocation, and data-level protection.
7. Verify actual behavior using negative tests, rather than seeing a single 200 response and concluding "logged in".

**Core point:** "Not storing authentication state" means **not relying on a saved authentication session from a previous request**. It does not promise the application has zero state of any kind: databases, caches, rate limiters, audits, CSRF token repositories, refresh-token stores, or request caches can still hold state.

## 2. HTTP Is Inherently Independent; the Authentication Mechanism Determines Statefulness

HTTP requests do not automatically carry Java objects from the previous request. When a user opens `GET /api/me` after logging in, the server needs a way to know why the new request belongs to the same user.

**Stateful session:** after authentication, the server stores `SecurityContext` or related data in a session store. The browser receives a cookie containing a **session ID**; subsequent requests send the cookie, and the server uses the ID to look up the session and restore `Authentication`.

**Stateless per-request:** each request carries credentials verified for that request alone, for example `Authorization: Bearer <access-token>`. The Resource Server validates the token, creates `Authentication` within the request scope, and discards the local result after processing. There is no need to store "user X logged in on a prior request" in an authentication session.

~~~mermaid
flowchart TD
    U["Client sends request #1"] --> S{"Choose authentication style"}
    S -->|"Stateful: POST /login"| A["Verify credentials"]
    A --> B["Save SecurityContext in WebSession"]
    B --> C["Set-Cookie: SESSION=<session-id>"]
    C --> D["Request #2 carries Cookie: SESSION"]
    D --> E["Server looks up WebSession and restores Authentication"]
    S -->|"Stateless: Bearer"| F["Request #1 carries Authorization: Bearer token"]
    F --> G["Verify token -> local Authentication"]
    G --> H["Request #2 must carry its own valid Bearer token"]
    H --> I["Re-verify token for request #2"]
~~~

### Quick Comparison

| Aspect | Stateful Authentication (Session) | Stateless Authentication (Per-Request) |
| --- | --- | --- |
| Typical info sent by client | Cookie containing session ID | Authorization Bearer/JWT; HTTP Basic also verifies per request |
| Server retains "previous login" | Yes, in `WebSession`/session store | No server-side login session needed |
| New request identity | Loaded from server session looked up by ID | Authenticates the new request's credentials |
| When client omits credentials | No cookie -> session not found | No token/header -> not authenticated |
| Invalidation/logout | Invalidate session on server; old cookie becomes unusable | Deleting token client-side **does not revoke** still-valid tokens |
| Centralized revocation | Delete session or change state in store | Offline JWT: needs short expiry/denylist/introspection/token version or suitable strategy |
| Multi-instance scale | Needs session stickiness or shared session store like Redis | Usually needs no shared auth session; still has infra/secrets/keys/validation state |
| CSRF | Especially important when browser auto-sends session cookie | Depends on whether credentials are auto-sent or explicitly attached, **not solely on "JWT"** |
| XSS/token theft | Session cookies still risk hijacking; HttpOnly limits JS reading cookie | Tokens in JS-accessible storage are very vulnerable to XSS; tokens in cookies carry CSRF risk |
| Server-side authorization | Must always check routes, roles, and data permissions | Must always check routes, scopes, roles, and data permissions |

**Do not confuse "stateless" with "using JWT":** HTTP Basic does not persist a login session if configured not to store `SecurityContext`, yet it must send username/password on every request and is not ideal for many production APIs. A JWT can easily be placed in a **cookie** and auto-sent by browsers; that still creates CSRF risk. Conversely, server-side sessions do not imply a system cannot scale: a shared session store enables horizontal scaling.

## 3. Things Commonly Confused in WebFlux

### 3.1. WebSession

`WebSession` is **Spring WebFlux**'s session abstraction. The server may store session data in memory or an external store. The session ID is typically sent to browsers via a cookie named `SESSION`, though the cookie name/mechanism can be configured or replaced by another session resolver. The cookie holds a **reference ID**; in the default session setup, it is **not a JWT** and does not contain the raw `SecurityContext` object.

`WebSession` is a broader concept than authentication: the app can store other session data, CSRF tokens, and saved requests. Therefore, disabling `SecurityContext` persistence is **not enough** to prove there are no `WebSession`s anywhere in the application.

### 3.2. SecurityContext and Reactor Context

`SecurityContext` holds `Authentication` (principal, authorities, and related authentication details). `ReactiveSecurityContextHolder` lets code inside `Mono`/`Flux` read `SecurityContext` from the **Reactor Context of the running subscription**.

- **With sessions:** Spring Security can load a saved `SecurityContext` from `WebSession` into the Reactor Context of a **new request**.
- **With stateless auth:** Spring Security can build a `SecurityContext` from the **current request**'s token, place it into Reactor Context, and skip writing it to `WebSession` for the next request.
- Therefore, **having a `SecurityContext` within a request does not mean the application is stateful**.

Do not use Servlet ThreadLocal `SecurityContextHolder` and assume a WebFlux request always stays on one thread.

### 3.3. ServerSecurityContextRepository

`ServerSecurityContextRepository` defines how to `load(ServerWebExchange)` and `save(ServerWebExchange, SecurityContext)` authentication state across requests.

- `WebSessionServerSecurityContextRepository`: saves/reads `SecurityContext` in `WebSession`. Per the official API, when saving `SecurityContext`, the session ID is rotated to reduce session fixation risk.
- `NoOpServerSecurityContextRepository`: an implementation that does not save/load `SecurityContext`; suitable when re-authenticating from credentials on every request.
- `ReactorContextWebFilter` can use the repository to populate `SecurityContext` for the current request.
- When configuring login/custom authentication mechanisms, inspect the **repository of the corresponding `AuthenticationWebFilter`**, not just the repository at the `ServerHttpSecurity` level. A login mechanism can still save to a session if its individual filter is configured to do so.

**Do not bring Servlet code into WebFlux:** `HttpSessionSecurityContextRepository`, `HttpSecurity`, and `SessionCreationPolicy.STATELESS` are familiar examples from the Servlet branch; this lesson uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerSecurityContextRepository`.

## 4. Stateful Flow: Log In Once, Subsequent Requests Use a Cookie

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as WebFlux App
    participant S as WebSession store
    B->>A: GET /login
    A-->>B: Login page + CSRF token
    B->>A: POST /login + credentials + CSRF
    A->>A: Verify username/password
    A->>S: Save SecurityContext in WebSession
    A-->>B: Set-Cookie SESSION + redirect
    B->>A: GET /api/me + Cookie SESSION
    A->>S: Load SecurityContext by session ID
    S-->>A: Saved Authentication
    A-->>B: 200 user JSON
    B->>A: POST /logout + Cookie + CSRF
    A->>S: Clear context/invalidate session
    A-->>B: Redirect / login
    B->>A: GET /api/me + old cookie
    A-->>B: Prompt to log in again
~~~

**What the browser stores is usually just the session ID.** Server-side data can reside in a single instance's memory or a shared store. With Spring Session + Redis, multiple instances can access the same session. If stored only in-memory per instance, the load balancer needs a sticky-session strategy or users risk losing state when requests hit another instance.

### 4.1. Session lifecycle

1. **Anonymous:** there may be no session yet, or the session only holds data such as CSRF/saved requests; there is no user `Authentication` yet.
2. **Successful login:** Spring Security creates `Authentication` and saves it to the `WebSession`-backed repository; the session ID is rotated upon saving to reduce session fixation.
3. **Subsequent request:** the client sends the session cookie; the server looks up the session and restores identity. If the session has expired/been deleted/has a forged ID, it must require logging in again.
4. **Idle/absolute expiration:** timeouts and renewal policies must be defined per application. `WebSession` supports idle-time timeouts; absolute lifetime or concurrent login limits may require additional mechanisms.
5. **Logout:** clears `SecurityContext` and typically invalidates `WebSession`; deleting the cookie client-side helps UX, but **server invalidation** is what renders the old ID unusable.
6. **Permission changes:** if the session caches old authorities, changing roles or disabling an account may not take effect immediately unless sessions are refreshed/revoked or permissions are checked at the data layer.

### 4.2. Cookie security and CSRF

For browser sessions, configure `Secure` (sent only over HTTPS), `HttpOnly` (reduces script access to cookies), `SameSite`, domain/path, and expiration. Never put session IDs in URLs, logs, or third-party analytics. A stolen cookie can allow session hijacking even without knowing the password.

Because browsers automatically send cookies according to domain/policy, state-changing requests are vulnerable to **Cross-Site Request Forgery (CSRF)**. Spring Security WebFlux enables CSRF protection by default. Form login and logout require a CSRF token; logout is triggered via **POST** by default, not an arbitrary GET link. `HttpOnly` does not replace CSRF tokens, and `SameSite` is not a sufficient barrier for every threat model.

## 5. Stateless Flow: Re-authenticating from Per-Request Credentials

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API client
    participant A as Resource Server A
    C->>A: GET /api/me + Bearer token
    A->>A: Verify signature/issuer/exp/aud/scope
    A->>A: Build Authentication for current request
    A-->>C: 200 user JSON
    C->>A: GET /api/me without token
    A-->>C: 401
    C->>A: GET /api/me + valid token
    A->>A: Authenticate for new request
    A-->>C: 200
~~~

With Bearer JWTs, the resource server typically verifies the signature against public keys/JWKS, `iss`, `exp`, `nbf`, and **audience per policy**. Scopes can map to `SCOPE_...` authorities. The JWT on the second request is not a "session" the server remembered from the first request: the server must validate fresh credentials every time.

With opaque access tokens, the server may call **introspection** against the token management system; authentication still **does not necessarily use a login `WebSession`**, yet there is dependency/state at the authorization server and introspection cache. Thus, "not storing authentication state at the resource server" **does not** mean "zero state across the entire system".

### 5.1. Stateless does not mean lacking a local SecurityContext

Within each request, filters still build `Authentication` and service code still reads it via `ReactiveSecurityContextHolder.getContext()`. This context is needed for authorization within the current request. What is eliminated is **reliance on a saved `SecurityContext` across two HTTP requests**.

### 5.2. Do not self-issue JWTs in a Resource Server

An application acting as a **Resource Server** verifies access tokens issued by an Authorization Server/IdP. Do not build a demo endpoint that signs JWTs with a hardcoded secret and treat it as a production approach. Token issuance, key rotation, revocation, refresh tokens, OIDC login, and user management are responsibilities that must be designed separately.

In the practice section, so the two variants **run standalone without an IdP**, we demonstrate statelessness using HTTP Basic on WebFlux with the NoOp repository. Afterward, section 12 shows a realistic JWT Resource Server configuration. Basic sends the password on every request, so **use it only for localhost labs** and never recommend it as a replacement for JWT/OAuth2.

## 6. Maven Project Running Two Separate Modes

We create **one project** with two Spring profiles:

- `session`: form login and `WebSession`; the `/api/me` endpoint uses the authenticated session cookie.
- `basic`: HTTP Basic checks username/password every time; `NoOpServerSecurityContextRepository` does not retain `SecurityContext` across requests.
- In both: `GET /api/public` is public and `GET /api/me` is restricted to authenticated users.
- On each startup, select **exactly one** profile; these are two alternative configurations, not enabled simultaneously.

The example uses **JDK 17+**, Maven, Spring Boot `3.3.13` corresponding to Spring Security 6.x; the Spring Boot 3.3 branch has reached end of OSS support, so new production systems must choose a currently supported version and verify APIs for that version. Lab account/password values must not be used in real environments.

Structure:

~~~text
webflux-auth-state/
├── pom.xml
└── src/
    ├── main/java/example/state/
    │   ├── StateApplication.java
    │   ├── UserConfig.java
    │   ├── SessionSecurityConfig.java
    │   ├── BasicStatelessSecurityConfig.java
    │   └── ApiController.java
    └── test/java/example/state/
        ├── SessionModeTest.java
        └── BasicStatelessModeTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-auth-state</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

**Why is there no Resource Server dependency?** The first two profiles intentionally require no real issuer/token so they can be tested right away. The JWT configuration in section 12 is an optional variant with its own dependency. Do not add `spring-boot-starter-web` because the lab uses reactive WebFlux, not Servlet MVC.

### 6.2. Startup class

File `src/main/java/example/state/StateApplication.java`:

~~~java
package example.state;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@SpringBootApplication
@EnableWebFluxSecurity
public class StateApplication {
    public static void main(String[] args) {
        SpringApplication.run(StateApplication.class, args);
    }
}
~~~

### 6.3. A shared user store for both profiles

File `src/main/java/example/state/UserConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class UserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
            .password(encoder.encode("demo-pass"))
            .roles("STUDENT")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
~~~

`MapReactiveUserDetailsService` provides a demo user. The password is encoded with `PasswordEncoder` before entering the in-memory user store; however, the plaintext string `demo-pass` appears in the **lab source code**, so do not use this approach for production. Real user stores require a secure database/IdP, password management, and appropriate rotation.

## 7. Stateful Configuration: Form Login + WebSession

File `src/main/java/example/state/SessionSecurityConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@Profile("session")
public class SessionSecurityConfig {

    @Bean
    SecurityWebFilterChain sessionChain(ServerHttpSecurity http) {
        var repository = new WebSessionServerSecurityContextRepository();

        var logoutHandler = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler()
        );

        return http
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public", "/login", "/logout")
                    .permitAll()
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form.securityContextRepository(repository))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .logout(logout -> logout.logoutHandler(logoutHandler))
            .build();
    }
}
~~~

**Key decisions:**

1. `@Profile("session")` ensures this chain bean is active only when starting with the `session` profile.
2. `WebSessionServerSecurityContextRepository` is used to read/save authentication state across HTTP requests. Both HTTP security context loading and form login use the matching repository.
3. `formLogin(...)` provides credential submission and saves context after login; Spring Security supplies a default login page in the sample environment.
4. `httpBasic(...disable)` prevents HTTP Basic from acting as a fallback mechanism, ensuring tests observe only session behavior. This does not mean inherently "stateless" HTTP Basic is always less secure; the two mechanisms serve different purposes.
5. Logout uses `DelegatingServerLogoutHandler`: clearing context via `SecurityContextServerLogoutHandler` and invalidating `WebSession` via `WebSessionServerLogoutHandler`. Note that Spring Security has a default logout setup, yet **to ensure explicit full `WebSession` invalidation**, you should configure the corresponding handler.
6. CSRF **is not disabled**. POST login and POST logout require a CSRF token per Spring Security Reactive policy. Do not turn logout into a GET to bypass CSRF.
7. `anyExchange().denyAll()` at the end prevents unintentionally exposing other URLs. Login/logout endpoints go through Spring Security's dedicated filters.

**Caution when scaling out:** login sessions also involve timeouts, cookie flags, session fixation, concurrency, role changes, and session-store resilience. In WebFlux, the repository stores `SecurityContext` in `WebSession`; actual session persistence may use the default session manager or be replaced by Spring Session/shared stores. `SESSION` is a common default cookie name, not a permanent guarantee across all configurations.

## 8. Simple Stateless Configuration: Per-Request HTTP Basic

File `src/main/java/example/state/BasicStatelessSecurityConfig.java`:

~~~java
package example.state;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@Profile("basic")
public class BasicStatelessSecurityConfig {

    @Bean
    SecurityWebFilterChain basicChain(ServerHttpSecurity http) {
        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.securityContextRepository(noOp))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .build();
    }
}
~~~

**Explanation:**

- `@Profile("basic")` selects the alternative configuration, not running concurrently with the session chain.
- `NoOpServerSecurityContextRepository.getInstance()` makes saving/loading `SecurityContext` across requests a no-op. Configure **both the `ServerHttpSecurity`-level repository and the HTTP Basic filter's repository** so the intent not to persist credentials is explicit.
- `httpBasic(...)` checks `Authorization: Basic ...` on **every request**. If the next request omits the header, the user is no longer authenticated. This is a stateless example in terms of **authentication persistence**.
- Disable `formLogin`, `requestCache`, and the default logout endpoint because browser login sessions are not used. There is no login session to invalidate; calling the API again with valid Basic credentials authenticates the new request anew.
- **Default CSRF is intentionally kept** in the lab, because HTTP Basic **can also be cached by browsers and sent automatically**. Only GETs are tested here, so no CSRF token is needed. Do not infer that `NoOpServerSecurityContextRepository` means CSRF can be disabled for every credential type.
- NoOp only addresses `SecurityContext` persistence; another part of the app can still create a `WebSession` for CSRF, flash data, or custom features. To confirm a "no session cookie" architecture, test the entire flow rather than reading a single config property.
- Basic is unsuitable for many modern web systems because the password is resent on every request (Base64 is not secret encryption), browser logout is unreliable, and revocation is tied to the password. **Use HTTPS outside localhost** and prefer OAuth2/Bearer for real APIs.

If the app needs the authenticated user within a single request, `ReactiveSecurityContextHolder.getContext()` can still hold `Authentication` **for the current request**; NoOp does not prevent creating a local `SecurityContext` after successful authentication.

## 9. Controller Shared by Both Modes

File `src/main/java/example/state/ApiController.java`:

~~~java
package example.state;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }
}
~~~

The same `GET /api/me` endpoint can produce JSON `{"username":"student"}` in **both modes**. **The difference does not lie in the controller**, but in the request's identity proof: stateful uses a previously created session cookie; stateless Basic requires credentials again for that request.

Do not call `block()` manually to retrieve `Authentication`, and do not use Servlet `SecurityContextHolder` to reason about WebFlux security.

## 10. Running and Observing Both Modes

In the directory containing `pom.xml`, run tests:

~~~bash
mvn clean test
~~~

To start session mode:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=session
~~~

Open `http://localhost:8080/login` in a browser; enter username `student` and password `demo-pass`. Spring Security renders the form login; if the browser supports cookies, you are redirected after login and receive a session. Then visit `http://localhost:8080/api/me` in the **same browser**: expect 200 and the student JSON. Use a private window **with no cookie** to call `/api/me`: you will be prompted to log in (usually redirected to `/login` with form login).

Log out in the browser flow via **POST /logout with a CSRF token** (Spring Security's logout page/form handles the request). After logout, the old session cookie no longer references a valid authentication; reloading `/api/me` must require re-authentication. If you only delete the cookie client-side without the server invalidating the session, the session may remain alive until timeout; proper logout must perform **server-side invalidation**.

Stop the server, then start Basic mode:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=basic
~~~

Send requests:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u student http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
~~~

With `curl -u student`, the tool prompts for a password; enter `demo-pass`. Expected sequence: **200, 401, 200, 401**. The third GET succeeds because it carries Basic credentials; the fourth is a **new** request without credentials and does not "inherit login" from the third request.

Locally, the easiest way to observe this is using the browser's Network tab or `curl -i` and inspecting cookies/headers. **Do not pass real passwords in command history**, and never log Authorization headers. The default port 8080 can be changed via configuration if another application occupies it.

### 10.1. Expected behavior matrix

| Action | Session mode | Basic stateless mode |
| --- | --- | --- |
| `GET /api/public` without credentials | 200 | 200 |
| `GET /api/me` without credentials | Usually redirects to login (form flow) | 401 with Basic challenge |
| Successful login | Server saves SecurityContext in WebSession | Authenticates per request carrying Authorization |
| Subsequent request **with only the issued cookie** | Can return 200 if session is still valid | Not authenticated by a session cookie |
| Subsequent request **with no cookie/header** | Not logged in -> log in again | 401 |
| Logout | Clears context/invalidates WebSession | Cannot invalidate a known password merely via "logout" |
| Resending Basic credentials right after client-side "logout" | Basic is disabled in this mode | New request can still return 200 |
| Server restart with in-memory session store | Session can be lost | No authentication session to restore |

**Do not compare only HTTP status codes across the two modes and misjudge the policy.** A form-login site may redirect 302 for anonymous users, whereas a REST API returns 401. What must be proven is that anonymous requests **do not reach protected endpoints** and that authentication state across requests behaves as designed.

## 11. Automated Testing with WebTestClient

We use two test classes, each activating one Spring profile. `spring-security-test` provides the `csrf()` helper in the mock `WebTestClient` environment. In a Spring Boot 3.3 project, `@SpringBootTest` without `RANDOM_PORT` combined with `@AutoConfigureWebTestClient` enables testing WebFlux against the `ApplicationContext`; do not use the CSRF mock helper with a live external HTTP client and assume tokens magically appear on another server.

### 11.1. SessionModeTest.java

File `src/test/java/example/state/SessionModeTest.java`:

~~~java
package example.state;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@ActiveProfiles("session")
@AutoConfigureWebTestClient
class SessionModeTest {

    @Autowired
    WebTestClient client;

    @Test
    void loginPersistsAcrossRequestsAndLogoutInvalidatesSession() {
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "demo-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody()
            .returnResult();

        ResponseCookie session = login.getResponseCookies()
            .getFirst("SESSION");
        assertNotNull(session);

        client.get()
            .uri("/api/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");

        client.mutateWith(csrf())
            .post()
            .uri("/logout")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();

        // Old cookie after WebSession invalidation
        // must not allow viewing the private endpoint.
        client.get()
            .uri("/api/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

In the default form flow, anonymous users are typically redirected to login; the test checks for redirection rather than forcing 401. The real cookie may have a different name if the app changes the cookie resolver, so this test intentionally applies to the **default lab**. `csrf()` is a Spring Security Test mutator and does not imply production clients are exempt from CSRF.

If a project uses a custom login page, success handler, JSON API entry point, or a logout-success handler returning 200, update the assertions to match the chosen protocol. The critical test is that **a request carrying the old cookie cannot view `/api/me` after logout**.

### 11.2. BasicStatelessModeTest.java

File `src/test/java/example/state/BasicStatelessModeTest.java`:

~~~java
package example.state;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("basic")
@AutoConfigureWebTestClient
class BasicStatelessModeTest {

    @Autowired
    WebTestClient client;

    @Test
    void eachRequestMustPresentCredentialsAgain() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");

        // Another request without Basic header: 401.
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();

        // Fake session cookie does not replace Basic credentials.
        client.get().uri("/api/me")
            .cookie("SESSION", "not-a-valid-session-id")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void publicEndpointIsStillAccessible() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }
}
~~~

The Basic test proves that **a request with valid credentials does not log in the next request**. It does not prove the entire application "never issues a session cookie": to verify that, inspect response headers and other flows such as CSRF, request cache, OAuth2 login, or application code using `WebSession` directly.

These are web-security tests for **practice**, not benchmarks. Do not use demo passwords in real environments; never put production passwords into logs or public test fixtures.

## 12. Configuring a Stateless JWT Resource Server in Real Applications

Bearer JWT is a more common example of an API authenticating **per request**. The following code is an **alternative configuration** to the Basic profile—**do not add it simultaneously in the lab project** without clear profile/bean routing.

Add dependency (in `pom.xml`, when converting the project to a Resource Server):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Example bean for a JWT API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Bean
SecurityWebFilterChain jwtApiChain(ServerHttpSecurity http) {
    var noOp = NoOpServerSecurityContextRepository.getInstance();

    return http
        .securityContextRepository(noOp)
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
        // Only for Bearer APIs that do not rely on auto-sent
        // cookies for authentication; evaluate CSRF first.
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
}
~~~

This is an **illustrative bean snippet** that must be placed in `@Configuration`, supplied with a valid issuer/decoder, and have overlapping demo chains removed. The example does not self-sign JWTs, issue refresh tokens, or prove that disabling CSRF is always safe.

Configure the issuer in Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/issuer
~~~

The domain `example.invalid` has no real issuer; replace it with an active IdP providing metadata/JWKS and access tokens issued with the proper audience/scopes for the application. With basic configuration, the Resource Server verifies signature, `iss`, and `exp`/`nbf`. **Do not assume `issuer-uri` automatically validates your API's exact audience**; add audience validation per your security contract. If using opaque tokens, replace the JWT decoder with introspection per the appropriate model.

A JWT request without a token -> usually **401**; a valid token with sufficient permissions -> controller executes; a valid token lacking the endpoint's scope/authority -> **403**. A `JwtAuthenticationToken` is still created in the local Reactor Context **for that request**, even though the server retains no `WebSession` authentication.

### 12.1. Stateless only when credentials **do not rely on auto-sent cookies**

If a JWT access token is stored in a cookie and automatically sent by the browser on every request, a CSRF threat model similar to other cookie mechanisms still applies. **Do not disable CSRF just because you use JWT.** Disabling CSRF in the snippet is only suitable for APIs using an `Authorization: Bearer` header explicitly attached by the client, with no cookies/Basic/sessions used automatically for authentication and after a threat-model review.

### 12.2. Authentication state and token state are different

A service that retains no authentication session may still use:

- JWKS/introspection result caches, connection pools, and databases.
- Refresh token stores at the Authorization Server.
- Denylists/allowlists, token versions, audits, risk engines, and rate limiters.
- Permission/tenant data in a DB or authorization service.
- `WebSession` for another UI portion if the architecture combines sessions + APIs.

Thus, the accurate concept is **stateless authentication at the resource server boundary**, not "100% zero state in any service".

## 13. Logout: The Most Crucial Difference

### 13.1. Logout in a session-based application

A valid POST logout with a CSRF token causes the server to clear `SecurityContext` and/or invalidate `WebSession`. The old cookie resent by the client **no longer references an active authenticated session**. To log out from all devices, you must be able to find/delete all sessions belonging to the user, rather than only invalidating the session on the current device.

The client cookie can be cleared at the same time, yet merely deleting the cookie in the browser is **not enough** to revoke a stolen session — a copy of the session ID elsewhere can remain usable until the server deletes or expires it.

### 13.2. Logout with stateless Bearer JWTs

Removing the access token from secure client memory and stopping refreshes can end the client's "session". However, **a still-valid copy of the self-contained access token can continue to be accepted by the resource server until expiration**, unless revocation/token-version/denylist/introspection mechanisms are applied.

The required revocation level depends on risk:

- **Short-lived access tokens:** limit the exposure window; do not provide instant revocation.
- **Refresh token rotation and revocation:** block issuing **new access tokens**, without necessarily invalidating already issued access tokens immediately.
- **Denylist by `jti` or token fingerprint:** the resource server checks every request; increases state/latency and requires operating a store/TTL.
- **Opaque tokens + introspection:** can be revoked centrally, though introspection caching delays revocation effect if the TTL is misaligned.
- **Token version / session version:** checks current account or server-side session data to reject old tokens; rejecting without any state lookup is hard to make take effect immediately.
- **Signing key rotation:** broad blast radius, not a routine single-user logout mechanism.
- **OIDC front-/back-channel logout:** addresses SSO/RP session contexts per protocol and IdP capabilities; not identical to revoking all OAuth2 access tokens.

**HTTP Basic also has no server-side authentication session "logout"** in NoOp mode: if the client keeps sending a valid username/password, the server will re-authenticate. Clearing credentials from the client or changing the password/disabling the account changes future behavior, yet there is no session cookie to invalidate.

### 13.3. Comparison table of logout operations

| Action | Stateful WebSession | Stateless JWT/Bearer | Stateless HTTP Basic |
| --- | --- | --- | --- |
| Delete credential on client | Browser stops sending session ID, though session may remain on server | Client stops sending token; another copy can still work | Client stops sending Basic; browser cache can be hard to clear reliably |
| Immediate server invalidation of one session | Yes, if store supports it and logout handler matches | Not built in; needs denylist/online validation/session version | No saved session; only checks password on next request |
| Expiration | Server session TTL/timeout | JWT `exp`/TTL/token policy | Depends on password/account validity |
| Log out all devices | Requires registry/store finding all sessions | Requires revocation policy/token family/refresh sessions | Can invalidate credentials (affects entire user) |
| Credential theft | Session ID can be used until invalidated/expired | Bearer token can be used until expired/revoked | Exposed password poses high risk until changed/disabled |

## 14. CSRF, XSS, and Credential Storage Location

There is no rule that "stateful is dangerous and stateless is safer" or vice versa. Risk depends on **how credentials are carried**.

| Credential storage | Does browser auto-send per request? | Primary risks | Countermeasures |
| --- | --- | --- | --- |
| Session ID in cookie | Yes, per cookie policy | CSRF, session hijack | CSRF token, Secure/HttpOnly/SameSite, session timeout/invalidation |
| JWT in cookie | Yes | CSRF **still exists**, token theft | CSRF policy, cookie flags, token expiry/revocation |
| Bearer token in JS memory | Only when JS attaches header | XSS can steal token; lost on reload unless refreshed | CSP/XSS mitigation, short-lived tokens, avoid logging |
| Bearer token in localStorage | JS attaches header | XSS steals long-lived tokens | Avoid storing tokens in JS-readable persistent storage |
| HTTP Basic browser cache | Browser may auto-send after challenge | CSRF/credential exposure depending on client, hard to log out | HTTPS, CSRF per threat model, prefer other mechanisms |

**CORS is not authentication.** Allowing another origin to read responses does not grant permissions, and blocking CORS in browsers does not mean an API is protected from `curl`/server-to-server calls. CSRF relies on browsers automatically attaching credentials to cross-site requests; where the JWT lives and how it is sent is the deciding factor.

An `HttpOnly` session cookie prevents JavaScript from reading the cookie directly, yet XSS can still perform actions through the logged-in browser. Therefore, you must simultaneously have input/output encoding, an appropriate CSP, CSRF protection, and data-level authorization.

## 15. Operations and Scaling: Choosing Architecture by Requirements

### 15.1. Is stateful really hard to scale?

Not necessarily. If the server keeps sessions in one instance's memory, losing a pod/redeploying or load-balancing to another instance can lose logins; the solution is sticky sessions **or** a shared session store such as Spring Session + Redis. A shared store improves continuity across instances while adding network IO, TTLs, consistency, session-store security, and resilience concerns. You must manage session fixation, session hijacking, timeouts, logout, and invalidation when roles change.

### 15.2. Does stateless really require no shared infrastructure?

Offline JWT verification can avoid reading a session store per request; yet the API still needs JWKS/key rotation, clock sync, audience validation, rate limits, and business data. If immediate revocation is needed, you often must query a denylist/introspection endpoint or account state, increasing state dependency. Never trade away revocation security for an "absolute statelessness" slogan.

### 15.3. Decision comparison

| Requirement | Session-based usually fits | Bearer-based usually fits |
| --- | --- | --- |
| Server-rendered website with browser login/logout | Easy to manage via session, cookies, and CSRF | Can use OIDC + backend-for-frontend, without storing tokens in JS |
| Mobile/API with Authorization header | Can use sessions if protocol fits | Usually fits OAuth2/OIDC access tokens |
| Immediate logout on a single device | Invalidate session | Needs revocation mechanism if not waiting for expiry |
| Multi-instance service | Needs shared store or session affinity | Easy to distribute JWT validation, though key/authz state remains |
| Immediate permission policy changes | Revoke/revalidate session | Needs DB/claims version/denylist; avoid trusting stale claims too long |
| Integrating multiple resource servers | App A's session cookie does not work automatically on B | Properly scoped/audience tokens work per contract; never relay wrong-audience tokens |
| Stateless required for latency | Measure actual store latency | Measure JWT verify, introspection, caches; do not assume always faster |

Do not decide based on technology buzzwords. Start from **client type, credential lifetime, logout/revocation requirements, data authorization, scaling, risk, and user experience**.

## 16. Keeping Data Authorization Correct in Both Models

In both stateful and stateless models, `authenticated()` only establishes that the caller has a valid identity. It does **not** mean the user is allowed to read every resource.

Example `GET /api/orders/42`:

- Stateful: the session has user ID A; the service must check whether order 42 belongs to A or an authorized tenant.
- Stateless: the JWT has `sub=A` and scope `orders.read`; the service must still check whether order 42 belongs to A/a valid tenant.
- If roles/tenants change, session authorities and JWT claims may be stale. Alongside expiry/logout, a policy is needed so revoked permissions take effect within the required window.
- If service A calls service B, A's context **does not automatically cross HTTP**. B authenticates outbound credentials independently and enforces resource permissions at B.

Never use a "signed token" as an excuse to skip owner/tenant checks. A signature proves the token was issued by a trusted source and untampered, **not** that the caller owns every object.

## 17. Real-World Misconfigurations and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| After form login, `GET /api/me` still asks to log in | `SESSION` cookie not sent, wrong repo, lost session, or login failed to save context | Inspect `Set-Cookie`/`Cookie` (do not log values), session store, `formLogin` repo |
| Basic stateless returns 200 on request missing header | Another session/auth filter present, test client auto-sends credentials, or wrong matcher | Read the exact security chain, inspect actual outbound requests |
| Replaced `securityContextRepository(NoOp)` yet `SESSION` cookie still appears | CSRF/request cache/other feature creates `WebSession`, or a separate auth filter saves context | Inspect all components holding session state, not just the repo |
| `POST /logout` returns 403 | Missing/invalid CSRF token, expired session | Keep POST and CSRF token; trace login/logout flow |
| After logout, old request still returns 200 | Server did not invalidate session, or browser still sends Basic/Bearer | Distinguish actual credentials on new requests, token revocation vs. session |
| User logs in on node A, loses session when routed to B | In-memory sessions not shared between nodes | Shared session store/affinity/TTL per architecture |
| JWT still works after clicking Logout | Access token is still valid and lacks a revocation check | Design TTL/denylist/introspection/refresh revocation |
| Valid token yet service B returns 401 | Wrong issuer/audience, expired token, or B does not accept token | Check validation on B and outbound headers |
| GET works, POST returns 403 | CSRF protects unsafe methods, or missing authority | Distinguish CSRF from authorization |
| Cookie JWT with CSRF disabled because "stateless" | Browser still auto-sends cookies, creating CSRF risk | Base threat model on credential transport |
| ThreadLocal `SecurityContextHolder` is empty | Running on WebFlux Reactor Context | Use `ReactiveSecurityContextHolder` inside `Mono`/`Flux` |
| Revoked role yet request retains old permission | Stale cached session/token claims | Session invalidation or revalidation/versioning |

**Recommended investigation order:** what cookies/headers the request carries (without logging secrets) -> which security chain is selected -> authentication mechanism -> `SecurityContextRepository` -> CSRF/authorization -> controller -> session/token lifetime/revocation.

## 18. Applied Exercises

### Exercise A — Describe two consecutive requests

Draw a sequence for form login where the server issues a session cookie, followed by two `GET /api/me` calls: the GET with the cookie must have identity; the GET without the cookie must be blocked. Draw a second sequence for Bearer: both GETs must carry an accepted token on their own. Indicate when `Authentication` is created/loaded.

### Exercise B — Swap the repository in the lab

In the Basic profile, read `NoOpServerSecurityContextRepository`'s code and explain why `ReactiveSecurityContextHolder` still contains `Authentication` when a Basic request succeeds. Try omitting the Basic header on the next request and predict the status. Do not swap NoOp for a session repository just to "make tests pass".

### Exercise C — Observe session logout

Run the session test: log in, extract the cookie, `GET /api/me`, `POST /logout` with CSRF, resend the old cookie. Explain why server-side invalidation matters more than just deleting the cookie in the browser.

### Exercise D — Distinguish access and refresh tokens

Assume a JWT access token lives 10 minutes and a refresh token lives 7 days. The user logs out at minute 2: what does revoking the refresh token prevent? Can the already-issued access token still be used when the Resource Server only verifies offline? Propose a revocation mechanism with immediate SLA if the business requires it.

### Exercise E — CSRF with JWT in a cookie

Design an API storing a JWT in an `HttpOnly` cookie. Even though the server stores no authentication session, the browser auto-sends the cookie. Explain why CSRF must be evaluated, and write POST tests with and without a CSRF token per your chosen policy.

### Exercise F — Multi-instance scaling

Assume two WebFlux replicas behind a round-robin load balancer. Diagram what happens if sessions live only in replica A's memory; propose Spring Session/Redis or sticky sessions. Compare against offline JWT verification, factoring in JWKS rotation, revocation, and data authorization.

### Exercise G — Authorization after role changes

A user holds the `ADMIN` role and then has it revoked. With sessions and short-lived JWTs, when can the change take effect? Design a policy meeting a 1-minute revocation requirement without assuming tokens self-update.

### Self-assessment checklist

- [ ] Can explain that "stateful" means persisting authentication across requests, not merely having a cookie.
- [ ] Know how `WebSession` differs from `SecurityContext` and `Reactor Context`.
- [ ] Know that `WebSessionServerSecurityContextRepository` persists `SecurityContext` across requests.
- [ ] Know that `NoOpServerSecurityContextRepository` does not store `SecurityContext`, yet does not eliminate all application state.
- [ ] Distinguish form login/session from per-request Basic and JWT.
- [ ] Can run both Spring profiles and negative tests via `WebTestClient`.
- [ ] Can explain session logout vs. JWT access token revocation.
- [ ] Know that CSRF depends on whether credentials are auto-sent by the browser.
- [ ] Do not confuse Spring WebFlux `ServerHttpSecurity` with Servlet `HttpSecurity`/`SessionCreationPolicy`.
- [ ] Can propose session-store and token-revocation solutions when scaling.
- [ ] Know that successful authentication does not grant permission over every order/tenant.

## 19. Self-Check Questions

1. A new request carries only `Cookie: SESSION=...`: which part of the server restores `Authentication`?
2. Why can `ReactiveSecurityContextHolder.getContext()` still return a context in NoOp mode?
3. Does `NoOpServerSecurityContextRepository` forbid all `WebSession` usage in the app?
4. Why should POST logout in form-based WebFlux include a CSRF token?
5. Why is deleting the client cookie not guaranteed to invalidate a stolen session ID?
6. If HTTP Basic credentials are sent again after a "logout", can the server re-authenticate?
7. Is a JWT in a cookie exempt from CSRF because the server stores no authentication session?
8. When clicking logout on the client before a JWT expires, will an offline-verifying resource server accept it again?
9. Does opaque token introspection mean the resource server uses stateful sessions? Why or why not?
10. If an app has 4 replicas, where is session state stored so users do not lose login?
11. Why is an `authenticated()` user still not automatically allowed to view another user's orders?
12. When roles change immediately, what strategies prevent stale sessions/JWTs from retaining privileges past the acceptable window?

## 20. Official Documentation

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring `SecurityWebFilterChain`, `formLogin`, `httpBasic`.
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html): saving `SecurityContext` into `WebSession`, session-id rotation.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): load/save strategy across requests.
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html): does not save/load context across requests.
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): default logout and `WebSessionServerLogoutHandler`.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF mechanics, form login/logout, cookie token repository.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Bearer JWT validation and authorities.
- [Spring Security — WebTestClient CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): the `csrf()` mutator.
- [Spring Framework — WebFlux WebSession](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattributes.html): using session data in WebFlux; also see `WebSession` API.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, cookie flags, fixation, timeout, and logout.
- [OWASP — JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT storage, logout/revocation, key/claim validation.

**Conclusion:** In a **stateful** application, the server maintains login information in `WebSession` and the client presents a session ID to recover `Authentication`; POST logout can invalidate the session on the server. In **stateless authentication**, every HTTP request must carry credentials verified for itself; a local `SecurityContext` still exists during the request, yet it is not loaded from a saved session. Especially with JWTs, "deleting the token on the client" is not equivalent to "revoking the token on the server"; and "stateless" does not exempt requirements for CSRF, data authorization, rate limiting, or credential management.