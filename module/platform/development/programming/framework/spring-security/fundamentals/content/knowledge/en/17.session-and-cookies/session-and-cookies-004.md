# Stateful and Stateless Are Choices About Where Authentication State Is Kept

## 1. Lesson Objectives

After this lesson, you will be able to:

1. Explain **stateful** and **stateless** in the context of *HTTP authentication* using the question: **after authentication, where is user identity state kept so the next request is recognized?**
2. Describe the login flow using `HttpSession` + session cookie and the per-request re-authentication flow using HTTP Basic or a bearer access token.
3. Distinguish **cookie, session ID, SecurityContext, Authentication, access token, refresh token**, and the concept that HTTP is inherently stateless.
4. Understand Spring Security's `SessionCreationPolicy`, especially the differences among `IF_REQUIRED`, `NEVER`, and `STATELESS`; and know that choosing stateless **does not automatically enable JWT**.
5. See how one application can use **stateful for the browser UI** and **stateless for the API**, with two clearly ordered `SecurityFilterChain` beans.
6. Verify with Java 17+/Spring Boot, `MockMvc`, and `curl` that the login session is reused while the API requires credentials on every request.
7. Evaluate trade-offs in scaling, revocation/logout, CSRF, XSS, token lifecycle, system load, and user experience.

**Scope:** Spring Security fundamentals and HTTP sessions/cookies. The primary examples use **Servlet/MVC** (`HttpSecurity`, `HttpSession`, `SecurityFilterChain`). WebFlux manages sessions/security contexts differently; do not use Servlet APIs directly in reactive handlers.

## 2. Main Idea: Where Does Authentication State Live Between Requests?

HTTP is a *stateless* protocol in the sense that each request is independent and does not automatically retain "who logged in on the previous request." However, an **application** can build a login session using sessions or require proof of authentication every time.

Two models:

**Stateful authentication (server-side session-based):**

```text
Browser                                  Server
  │ POST /login + credentials + CSRF       │
  ├───────────────────────────────────────>│ verify credentials
  │                                        │ create/save SecurityContext
  │                                        │ in HttpSession
  │<────────────── Set-Cookie: JSESSIONID=... ─┤
  │                                        │
  │ GET /account                          │
  │ Cookie: JSESSIONID=...                │
  ├───────────────────────────────────────>│ look up session by session ID
  │                                        │ read saved Authentication
  │<────────────── 200 OK ────────────────┤
```

**Stateless authentication (does not rely on a security session across requests):**

```text
Client                                     Resource Server
  │ GET /api/account                         │
  │ Authorization: Bearer <access-token>     │
  ├─────────────────────────────────────────>│ validate token for request
  │                                          │ create Authentication for request
  │<──────────────── 200 OK ─────────────────┤
  │                                          │ do not persist SecurityContext
  │ GET /api/account                         │ via HttpSession for next time
  │ Authorization: Bearer <access-token>     │
  ├─────────────────────────────────────────>│ verify proof again
  │<──────────────── 200 OK ─────────────────┤
```

In the stateless diagram, `<access-token>` is only a placeholder illustrating the flow, not a real token. There are many credential mechanisms, such as HTTP Basic or mTLS, and it does not have to be JWT.

**Careful definitions:**

- **Stateful:** the server or a server-side state store keeps login session information across multiple requests; the client usually holds a **session identifier** pointing to that state.
- **Stateless (for security context):** the server processes a request based on the proof carried in that request, without needing to retrieve a prior authenticated session for the same user from an earlier request. It still creates `Authentication`/`SecurityContext` **for the current request**.
- **Zero state anywhere in the entire system** is not the goal or promise of "stateless." The server still has configuration, a user store, signing keys, caches, rate limits, audit logs, and sometimes must query an external system to validate tokens.

The difference **does not lie in whether the frontend is an SPA or a traditional web app**. An SPA can use cookie sessions; a web server can also use bearer tokens; what matters is **who holds and looks up authentication state between requests**.

## 3. Stateful: Session ID Lives on the Client, SecurityContext Usually on the Server

With Spring Security Servlet, a typical form login flow:

1. The client sends username/password over HTTPS along with a CSRF token when CSRF protection applies.
2. The server authenticates and creates an `Authentication` containing principal, authorities, and necessary details.
3. The security context persistence mechanism saves `SecurityContext` so it can be restored on subsequent requests, usually into `HttpSession`.
4. The server sends a session cookie (commonly named `JSESSIONID` in Servlet containers) containing the **session ID**, not usually the entire `Authentication`/password.
5. The browser automatically sends the cookie matching domain/path/cookie attributes on subsequent requests.
6. The server uses the ID to look up the session, restores `SecurityContext`, and proceeds to check authorization.
7. Logout/session expiration/session invalidation causes the server to stop recognizing the corresponding ID.

### Distinguishing the objects

| Concept | Typical location / lifetime | What does it hold? |
| --- | --- | --- |
| `HttpSession` | Server-side session store, possibly in RAM or Redis | Session data across multiple requests; can include Spring Security context |
| `JSESSIONID` cookie | Browser; sent along with matching requests | Usually just an opaque session identifier, not a JWT token |
| `SecurityContext` | Security context on the request and may be persisted in the session | `Authentication` and related security state |
| `Authentication` | Created upon authentication or restored from context | Principal, credentials/authorities, authentication status |
| CSRF token | A value protecting state-changing requests | Helps prevent request forgery; not a session ID |
| Access token | Carried by client to the resource server | Proof of access rights; may be self-contained claims or an opaque string |

**A cookie does not imply stateful.** A cookie can carry a session ID, or it can carry a signed token; conversely, the server can receive a session ID through another mechanism. When comparing models, examine **what the cookie value represents** and whether the server has to look up a session on its side.

### When there are multiple instances

If server A keeps sessions in its own RAM and the next request hits server B, B may not find that session. Ways to handle this include:

- Using a **shared session store** (e.g., Spring Session + Redis) so multiple instances access the same state.
- Using sticky sessions at the load balancer if you accept coupling to an instance and failover limitations.
- Designing logout, expiration, session serialization/consistency, securing the session store, and handling Redis/database unavailability.

**A session store using Redis is still stateful.** It only moves storage from individual instance memory to a shared store; it does not automatically make the application stateless.

### Pros and limitations

- Easy to achieve **near-instant logout/revocation** by invalidating the corresponding session (provided instances check the same session store).
- Centralized management of concurrent sessions and timeouts is possible.
- Convenient browser UX because cookies are sent automatically without application code attaching an Authorization header on every call.
- Requires protecting the session store, session IDs, session fixation, CSRF, and cookie configuration.
- Infrastructure may need a distributed store when scaling; each request may require a lookup to the store or cache.

## 4. Stateless: Proof of Authentication Arrives with Each Request

In a stateless API model, the client brings credentials/proof on every request; the server constructs a security context to process that request without relying on an `HttpSession` holding security context from a previous request.

Examples:

**HTTP Basic:** every request sends an `Authorization: Basic ...` header containing a Base64-encoded username/password, **not encrypted**. The server verifies credentials on every request. This is a simple way to illustrate statelessness, though not the right UX/security choice for most public APIs; it requires HTTPS and an appropriate credential strategy.

**Bearer token (e.g., JWT):** every request sends `Authorization: Bearer ...`. The resource server verifies the token per configuration: signature/algorithm/keys, issuer, expiration, audience, and required claims/authorities. No login session needs to be stored on the resource server itself if the token and policies are verified from the request.

**Opaque reference token:** the resource server can call the authorization server via introspection to learn whether the token is still valid, its scopes/permissions, and which user it represents. The resource server can still **keep no user session**, yet the overall system still depends on state at the authorization server and may add an introspection cache.

Thus, "stateless" is usually a statement **about a specific service/resource server** and security context persistence mechanism, not a claim that no component needs state.

### JWT is not a mandatory requirement for stateless

You can build a stateless API with HTTP Basic, mTLS, or bearer access tokens. Conversely, a system using JWT still has state if it stores tokens/sessions on the server, uses a denylist, a refresh-token store, or queries permissions from a database. Do not conclude "has JWT = completely stateless" or "has cookie = definitely stateful."

**JWT is only a token format**, not a login protocol; it does not automatically protect against XSS/CSRF or grant refresh/revocation capabilities. Choosing JWT vs. opaque tokens follows architectural decisions about identity, trust, and lifecycle.

### Revocation and logout with stateless tokens

If a resource server trusts an unexpired self-contained JWT, clicking "Logout" on the client may only delete the token on the device; a stolen copy of the token can still be used until it expires. Ways to mitigate this risk:

- Short-lived access tokens; refresh tokens with explicit verification/rotation/revocation flows.
- Introspection or a denylist/revocation state for use cases requiring immediate revocation.
- Restricting scopes/audience, verifying issuer, signature, expiry, clock skew, and key rotation.
- Replay monitoring, protecting tokens on the client, and TLS.

**Trade-off:** wanting immediate revocation usually requires adding a state/lookup source; at that point the resource server may no longer be purely self-contained even though the API still uses no HttpSession.

## 5. Comparison by Architectural Criteria

| Criterion | Stateful session | Stateless security context |
| --- | --- | --- |
| Proof carried by client | Usually a cookie containing an opaque session ID | Credentials/token attached to each request (Basic/Bearer/mTLS...) |
| Auth info across requests | Server/session store holds session state | Does not rely on a prior login session on the resource server |
| Verifying subsequent requests | Look up session and restore context | Validate the proof attached to the request |
| Changing permissions / revocation | Can invalidate session on the server | Depends on token type; self-contained JWT may need expiry/denylist/introspection |
| Scaling across instances | Needs shared/sticky sessions if state is local | Easier to scale stateless resource servers, though dependencies remain |
| Per-request cost | May need to query session/store | May need signature/token verification or introspection/identity calls |
| CSRF | Critical when cookies auto-send for auth | Still critical if cookies or browsers auto-send credentials; bearer headers behave differently |
| XSS | `HttpOnly` cookies reduce the chance of JS reading the session ID | Tokens stored in JS-accessible storage risk theft via XSS |
| Logout | Invalidating the session can block subsequent requests | Deleting client-side does not necessarily invalidate issued tokens |
| Session fixation | Needs session ID rotation/protection | Does not rely on session IDs for APIs; still must guard against token replay |
| Typical clients | Browser/server-rendered apps, admin UIs | Service-to-service, mobile/SPA/API with an IdP as required |
| Core distinction | **Where state is kept across requests** | **Not restoring login from a server session across requests** |

Neither model is "universally faster" or "universally safer." Depending on request volume, token verification, session store latency, revocation requirements, and client/browser behavior, actual outcomes can vary.

## 6. Spring Security: What Does SessionCreationPolicy Control?

In Spring Security Servlet, `SessionCreationPolicy` has the following common values:

| Policy | Meaning |
| --- | --- |
| `ALWAYS` | Spring Security always creates an `HttpSession` under this policy |
| `IF_REQUIRED` | Creates a session only when Spring Security needs one |
| `NEVER` | Spring Security does not create a session itself, but **may use an existing one** |
| `STATELESS` | Spring Security does not create a session and **does not use a session to obtain `SecurityContext`** |

The single most important point of the lesson:

```java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

This is a **configuration fragment**, not a standalone program; you must import `org.springframework.security.config.http.SessionCreationPolicy` and place it inside a `SecurityFilterChain`.

According to documented Spring Security behavior, using `STATELESS` causes `SecurityContextRepository` to use `NullSecurityContextRepository` in appropriate stateless flows and avoids saving requests for login into `HttpSession`. It **does not mean no component anywhere in the entire application can create an HttpSession**; application code, servlets/other frameworks, or CSRF/session mechanisms depending on configuration must still be examined.

### STATELESS does not authenticate requests automatically

Simply configuring `STATELESS` without enabling `httpBasic`, JWT resource server, OAuth2, mTLS, or an appropriate `AuthenticationFilter` leaves the server with no way to infer who the caller is. Session policy governs persistence, **not** credential verification.

Nor should `NEVER` be used as a synonym for stateless: `NEVER` can still read an existing session and restore the security context.

### SecurityContext still exists during a stateless request

Even without persisting across sessions, Spring Security still handles `Authentication`/`SecurityContext` **within the scope of the current request** to enforce authorization. "Stateless" here does not mean the framework lacks an in-memory `Authentication`.

In Spring Security 6, classes such as `SecurityContextHolderFilter`/`SecurityContextRepository` are responsible for loading/saving context according to the configured strategy. If you implement a custom authentication filter, you must follow the exact API and semantics of the version in use, including whether the context must be saved explicitly to the repository. Do not copy old Spring Security 5 examples verbatim into Spring Security 6 without checking.

## 7. Runnable Java 17 Example: One Application with Both Stateful and Stateless

We build a Spring Boot **3.3.13**, Java 17+, Gradle 8.x application. The application intentionally has **two `SecurityFilterChain` beans**:

- **API:** all `/api/**` routes use HTTP Basic on every request and `SessionCreationPolicy.STATELESS`; they do not read login state from the browser session.
- **Browser:** `/browser/**` uses default form login and `HttpSession` to keep login across requests; `/public` is open.
- The API chain at `@Order(1)` is evaluated **before** the catch-all chain at `@Order(2)` so the browser chain does not shadow the API chain.

This is one application with **two policies for two groups of requests**; there is no contradiction in a single backend using both.

### 7.1. Structure and build

```text
session-state-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/sessionstate/
    │   ├── SessionStateApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/sessionstate/
        └── SessionStateTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'session-state-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 7.2. Main class

**`src/main/java/com/example/sessionstate/SessionStateApplication.java`**

```java
package com.example.sessionstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionStateApplication.class, args);
    }
}
```

### 7.3. SecurityConfiguration: two chains, two places holding authentication state

**`src/main/java/com/example/sessionstate/SecurityConfiguration.java`**

```java
package com.example.sessionstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain statelessApiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSessionChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

Explanation of each decision:

1. `@Order(1)` and `securityMatcher("/api/**")` place the API chain first, applying only to the API routes.
2. `SessionCreationPolicy.STATELESS` instructs Spring Security not to rely on `HttpSession` to store login for API authentication. HTTP Basic sends credentials on **every request**.
3. `httpBasic(withDefaults())` enables `Authorization: Basic ...` header processing; `formLogin(...disable())` avoids redirecting to a login form on API endpoints. An API request without Basic credentials will normally receive 401.
4. `@Order(2)` is the catch-all chain for the remainder. `formLogin(withDefaults())` generates/renders the login page and uses sessions to maintain browser login. `/public` requires no login.
5. The user store uses `{noop}` only for local demonstration. Do not use plaintext passwords, non-TLS HTTP, or hardcoded accounts in production.
6. CSRF protection **stays at its default on both chains**. The demo endpoints use GET; browser form login POST uses the CSRF token supported by the form and test helpers. Do not mechanically disable CSRF just because an API carries the stateless label, especially when a browser may auto-send Basic/cookie credentials.

**Production note:** because the API chain uses HTTP Basic, browsers may automatically resend Basic credentials in certain situations. Evaluate CSRF based on how credentials are actually sent by browsers; if switching to bearer tokens sent explicitly in an Authorization header without ambient cookies, the CSRF threat model changes. In this example, default protection for unsafe HTTP methods is kept enabled.

### 7.4. Shared controller

**`src/main/java/com/example/sessionstate/DemoController.java`**

```java
package com.example.sessionstate;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/browser/me")
    public String browserMe(Principal principal) {
        return "browser " + principal.getName();
    }

    @GetMapping("/api/me")
    public String apiMe(Principal principal) {
        return "api " + principal.getName();
    }
}
```

`Principal` is provided once the request has authenticated successfully through the matching chain. This example only reads the current name; never use a principal name alone as proof of ownership of another resource.

### 7.5. Running and observing

Install JDK 17+ and a compatible Gradle 8.x, then in the `session-state-demo` directory run:

```bash
gradle test
gradle bootRun
```

If you have the matching Gradle Wrapper version, you can use `./gradlew test`, `./gradlew bootRun` (Linux/macOS) or `gradlew.bat test`, `gradlew.bat bootRun` (Windows). The classes require Spring dependencies, so standalone `javac`/`java` commands are insufficient without the classpath.

**Observing the stateful browser flow:**

1. Open `http://localhost:8080/browser/me` in a browser.
2. When there is no logged-in session, Spring Security typically redirects to `/login`.
3. Enter `alice` / `alice123` in the demo login form.
4. After logging in, reopen `/browser/me`. The server restores Authentication from `HttpSession` via the session ID cookie, so the response body is `browser alice`.
5. Opening a new tab in the same browser profile with the same cookie can still use the session; after logout/session expiration, requests require logging in again.

**Observing the stateless API with curl:**

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
```

Expected in order:

1. `401 Unauthorized`, because no credentials were sent.
2. `200 OK`, body `api alice`, because valid HTTP Basic credentials were included in the request.
3. `401 Unauthorized` again, because the previous call **did not create a login session for the API** and the final curl omits Basic credentials.

**Observing the boundary between the two chains:** after logging in via the browser, sending only the session cookie to `/api/me` (without Basic credentials) does not make the API chain recognize the login; the API chain is configured stateless and requires its own authentication. In practice, browsers may send other headers/cookies, so use `MockMvc` below to test the boundary in a controlled way.

Summary table of results:

| Scenario | Endpoint | Proof sent | Expected |
| --- | --- | --- | --- |
| Unauthenticated | `GET /public` | None | 200, `public` |
| Unauthenticated browser | `GET /browser/me` | None | 302 redirect to login (with default form login) |
| Logged-in browser | `GET /browser/me` | Valid session cookie | 200, `browser alice` |
| API missing Basic | `GET /api/me` | None | 401 |
| API with Basic | `GET /api/me` | Correct username/password | 200, `api alice` |
| API after a successful request | `GET /api/me` | Without Basic | 401 |
| API receives browser session without Basic | `GET /api/me` | Session cookie only | 401 |

Statuses may change if you add custom entry points, change the login path, or enable another identity mechanism; this table accurately reflects the demo configuration.

### 7.6. Testing the difference with MockMvc

**`src/test/java/com/example/sessionstate/SessionStateTests.java`**

```java
package com.example.sessionstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStateTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void browserEndpointRedirectsBeforeLogin() throws Exception {
        mvc.perform(get("/browser/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void browserLoginCreatesReusableSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/browser/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("browser alice"));
    }

    @Test
    void apiRequiresCredentialsOnEveryRequest() throws Exception {
        MvcResult success = mvc.perform(
                get("/api/me").with(httpBasic("alice", "alice123"))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("api alice"))
            .andReturn();

        assertNull(success.getRequest().getSession(false));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void browserSessionDoesNotAuthenticateStatelessApi() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }
}
```

In Spring Security Test, the `formLogin()` helper constructs a POST login request with a valid CSRF token; thus we can keep CSRF protection enabled and still test login.

Key takeaways from the test suite:

- The browser test proves a successful login produces an `HttpSession` and the same session is reused to access the next request.
- The API test proves only requests carrying valid `Authorization: Basic` succeed; without proof on the next request, it is not recognized.
- The cross-chain test proves having a browser session **is not an authentication source for the stateless API chain**.
- `MockHttpSession` in tests stands in for the servlet environment's session/cookie transport, **not** an actual measurement of `Set-Cookie` over the network or TLS/browser flags. Test a real browser and infrastructure separately before deployment.

## 8. Cookie/Session Security: What Protections Does Stateful Need?

When a browser holds a session ID, someone else who obtains that ID may attempt to use the session. Therefore:

1. **HTTPS and `Secure` cookies:** browsers only send cookies over secure connections when configured properly; production must not transmit session IDs over unencrypted HTTP.
2. **`HttpOnly`:** reduces the risk of JavaScript reading session cookies during XSS (does not block all impacts of XSS).
3. **`SameSite`:** reduces certain cross-site cookie-sending scenarios, yet does not replace CSRF protection design.
4. **Path/Domain:** limits where cookies are sent, avoiding unnecessarily broad scopes.
5. **Session fixation protection:** rotates the session identifier upon login/privilege elevation. Spring Security includes session fixation protection; verify per version/config.
6. **Timeouts, logout, and invalidation:** limits session lifetime, invalidates sessions when users log out, and tracks revoked permissions.
7. **CSRF tokens:** protects state-changing requests when browsers auto-send cookies; login/logout requests themselves can also need CSRF protection.
8. **XSS, CSP, and auditing:** never allow arbitrary user content to execute scripts; protect application data even when cookies are HttpOnly.

**One point to remember:** clicking logout should invalidate the session on the server. Deleting the cookie on the client alone is no substitute for invalidating the server session. In Spring Security, logout typically processes POST with a CSRF token by default; allowing arbitrary GET logout easily opens logout CSRF risks.

### What about CSRF when using JWT/Bearer?

If a bearer token is explicitly attached by JavaScript to an `Authorization` header and the browser does not automatically attach equivalent credentials on cross-site requests, the CSRF threat model differs from cookie sessions. However, if the token is placed in a cookie and auto-sent, **CSRF risk returns even though the token is a JWT**.

Do not apply a blanket rule "if stateless, disable CSRF." Determine whether the browser can **automatically send authentication proof** on requests initiated by another site, which endpoints mutate state, and what protections are in place. The runnable example keeps CSRF enabled by default.

### XSS and token storage

Storing access tokens in `localStorage` makes them readable by JavaScript, so if XSS occurs, the token can be stolen. `HttpOnly` cookies reduce the ability of scripts to read cookies, though the browser can still send them on requests during XSS/CSRF if defenses are insufficient. Choosing how to store tokens requires weighing XSS, CSRF, token lifetime, refresh flows, SameSite, CORS, and client architecture.

## 9. When Using a Real OAuth2 Resource Server / JWT

HTTP Basic in the demo is used solely to **observe stateless requests** because it runs immediately without needing an Identity Provider. A production API typically chooses OAuth2 Resource Server with access tokens issued by an Authorization Server/IdP.

Example **conceptual configuration fragment**:

```java
@Bean
@Order(1)
SecurityFilterChain jwtApiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
```

This is a **fragment, not a standalone runnable program**; it requires the `spring-boot-starter-oauth2-resource-server` dependency, imports, and real issuer/JWK source configuration from a trusted IdP. Do not add this bean into the demo app in section 7 without removing/replacing the old API chain. With real JWTs:

- Validate token signature, algorithm, issuer, expiration, and audience per policy; Spring Security provides some default validators, though audience usually requires explicit verification setup.
- Mapping claims such as scopes, roles, and groups into authorities must be explicit; never assume every `roles` claim means `ROLE_ADMIN`.
- Restrict scopes/audience; access tokens should grant only the appropriate resources and actions.
- Design refresh, revocation, key rotation, expired-token handling, and clock skew.
- Protect tokens in transit/storage and prevent leaking them in logs.

With **opaque tokens**, token introspection can be used instead of JWT self-validation; an API can maintain no session while still calling the authorization server or caching introspection results. Where state is kept and looked up **still must be described at the system level**, rather than looking solely at the token type.

## 10. Choosing a Model by Requirements Instead of Trends

### Case A: Browser admin application

Users log in via forms, want immediate logout, perform sensitive actions, need session timeouts, and can use a shared session store. Stateful sessions are easy to administer when cookies and CSRF are implemented properly. Account for session fixation, session hijacking, concurrent session management, session store availability, and re-authentication policies for sensitive actions.

### Case B: API serving mobile/services

Clients send bearer access tokens on each request, and the resource server validates tokens without keeping login sessions; instances scale easily with clean API boundaries, but you must solve lifetimes, refresh/revocation, scopes/audience, key rotation, and token protection. If immediate revocation is needed or permissions change constantly, long-lived self-contained tokens create friction.

### Case C: One backend serving browsers and APIs

Two chains can be applied like in the demo:

```text
Request /api/**         → SecurityFilterChain #1 → STATELESS + Basic/Bearer
Request /browser/**     → SecurityFilterChain #2 → FormLogin + HttpSession
Request /public         → SecurityFilterChain #2 → permitAll
```

**Chain ordering matters greatly.** If the catch-all chain comes first, the API chain might never be selected. `securityMatcher` picks the matching chain; `requestMatchers` inside a chain only selects authorization rules. Having a final catch-all chain helps avoid requests falling outside every Spring Security chain.

### Case D: Scaling stateful with Redis

Need multiple servers while preserving the traditional login/session experience? Using Spring Session with Redis lets instances share access to sessions, reducing reliance on sticky sessions. However, Redis/clustering, TTL, failover, and store security become part of the architecture. This is still **stateful**, because requests must look up login state stored on the server side.

## 11. Evaluating Common Claims Accurately

| Claim | Accurate assessment |
| --- | --- |
| "HTTP is stateless so sessions cannot be used" | False: applications build sessions on top of HTTP |
| "Having a cookie means stateful" | False: a cookie can carry a session ID or a self-contained token |
| "Stateless means there is no SecurityContext" | False: each request can still create Authentication/SecurityContext |
| "`STATELESS` automatically enables JWT auth" | False: a separate JWT/OAuth2 Resource Server mechanism must be configured |
| "`NEVER` and `STATELESS` are the same" | False: `NEVER` can still use an already existing session |
| "With JWT, logout immediately invalidates the token" | False: depends on expiry/revocation/introspection |
| "Stateless means disable CSRF" | False: depends on whether the browser auto-sends credentials |
| "Using Redis for sessions makes it stateless" | False: state merely moved location, still looked up by ID |
| "With HTTP Basic, the next request stays logged in automatically" | False under STATELESS config: Basic credentials must be sent each time |
| "The server keeps no session so there is zero stateful data" | False: keys, user stores, policies, caches, audits, and token/refresh state still exist |
| "JWT is always better than sessions" | No universal rule: choose based on clients, operations, revocation, scale, and threats |
| "Using form login is enough, no CSRF needed" | False: form login/cookie flows require serious CSRF evaluation |

### How to diagnose an unexpected 401 request

1. Did the client send the `JSESSIONID` cookie or `Authorization` header expected by the selected chain?
2. Which `SecurityFilterChain` did the request match? Are `@Order` and `securityMatcher` as intended?
3. Does that chain use `STATELESS`, `NEVER`, or `IF_REQUIRED`? Does it use `HttpSessionSecurityContextRepository` or `NullSecurityContextRepository`?
4. Does the session ID exist, or has it expired, been invalidated, been lost on instance switching, or gone missing from the session store?
5. Has the token expired, failed issuer/audience/signature checks, been revoked, or failed to map authorities?
6. If using browser cookies, was the request blocked by CSRF and returning **403** instead of 401?
7. Did a proxy/load balancer alter domain/path/scheme, preventing the browser from sending the cookie within scope?

Never log full session IDs, Authorization headers, passwords, refresh tokens, or JWTs in production logs. Only store sanitized or properly hashed details needed for investigation.

## 12. Self-Check Exercises

**1. If a browser holds a `JSESSIONID` cookie, how can a logged-in user reuse the session?**

The server receives the session ID from the cookie, looks up the `HttpSession` storing `SecurityContext`, restores `Authentication`, and evaluates authorization. The browser only keeps the ID and does not need to resend the password on every request.

**2. If the server uses Redis as a session store, does the system become stateless?**

No. Redis holds server-side state for subsequent requests. It enables sharing state across multiple instances, yet the model remains stateful.

**3. Why is `SessionCreationPolicy.NEVER` not enough to promise no sessions are used?**

Because it avoids creating an `HttpSession` for Spring Security, yet can still use an already existing session. `STATELESS` is what expresses the policy of not using `HttpSession` to obtain the security context.

**4. Must an API using JWTs in the `Authorization` header store zero state anywhere?**

No. A resource server can verify self-contained JWTs without sessions, yet the system still has keys, permissions, refresh token stores, revocation/denylists, caches, or introspection depending on design.

**5. Why did the stateless API in the demo return 401 right after a successful Basic request?**

Because the subsequent request did not send Basic credentials and Spring Security does not retrieve a login session from the previous request. The previous request's Authentication is not persisted to authorize the next request.

**6. Why can a cookie introduce CSRF risk?**

Browsers can automatically send cookies on requests matching cookie attributes, including requests triggered from untrusted origins. CSRF tokens and appropriate SameSite/Origin policies mitigate this risk; do not rely solely on the word "stateful/stateless."

**7. Can a JWT still be used after a user clicks logout?**

Yes, if the token is still within its validity window and the resource server continues accepting it. Short expirations, revocation/introspection, or other mechanisms are needed if immediate blocking is required.

**8. In the demo, why doesn't logging in at `/browser/me` automatically authorize `/api/me`?**

Because `/api/**` requests are handled by the separate `@Order(1)` chain configured with `STATELESS` and HTTP Basic. The security context in the browser's `HttpSession` is not used by the API chain as an authentication source.

**9. Should you disable CSRF whenever `STATELESS` is configured?**

No. Check whether authentication proof is automatically sent by the browser on cross-site requests. Basic authentication or bearer tokens stored in cookies may still require CSRF mitigation.

**10. Is a long-lived self-contained JWT a good fit for a system requiring near-instant permission revocation on every API request?**

Usually inconvenient: an unexpired self-contained JWT may still be accepted. Consider short-lived access tokens, introspection, or revocation/denylist mechanisms suited to your requirements.

## 13. Key Takeaways

- **Stateful / stateless is a decision about where authentication state is kept between requests**, not a label for "has/lacks cookies" or "JWT/no JWT."
- **Stateful:** the client usually keeps a session ID, the server keeps the session and Authentication; subsequent requests look up state via the ID.
- **Stateless:** each request carries proof of authentication, the server verifies it within that request, and does not need to restore security context from a prior login session.
- `SessionCreationPolicy.STATELESS` does not automatically enable JWT, does not mean the entire application never creates an `HttpSession`, and does not unilaterally define the CSRF threat model.
- HTTP Basic is a simple stateless illustration but resends credentials on every request; production APIs typically favor tokens/mTLS.
- **Cookie sessions require properly configured CSRF, XSS, session fixation protections, and cookie flags.** Self-contained tokens also require expiry, scopes, issuer/audience validation, and a revocation strategy.
- Stateful sessions shared via Redis are **still stateful**. Stateless resource servers relying on introspection/denylists still depend on state in another component.
- One application can use **stateful for browsers and stateless for APIs** if security chains, scopes, and ordering are clearly defined.
- The final decision rests on client requirements, UX, session control, operations, scaling, logout, security, and cost.

### Official Documentation

- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Session Management and HttpSession Configuration: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Java Configuration, multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing Form Based Authentication with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Session — Spring Session and session sharing: https://docs.spring.io/spring-session/reference/
