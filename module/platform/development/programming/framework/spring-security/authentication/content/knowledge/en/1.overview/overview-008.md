# Prerequisites and Learning Sequence: From Basic Login to External Identity Integration

> **Scope:** Spring Security Authentication in **Servlet/Spring MVC** applications. This lesson is a learning roadmap: what you need to know, in what order to learn, how to practice, and when you have enough foundation to connect external identity systems. Examples run on **Java 17+ and Spring Boot 3.3.x (Spring Security 6.x)**; when using another version, verify against the corresponding version's documentation. Deep dives on authorization, OAuth2/OIDC, federation, and reactive follow these authentication fundamentals.

## 1. Goals and Boundaries

After this lesson, you should be able to explain on your own:

1. Why an unauthenticated request is routed to a login page, and how subsequent requests after login are recognized.
2. The roles of `SecurityFilterChain`, `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, and `SecurityContext`.
3. How to move from in-memory accounts to database-backed accounts without writing custom password-comparison logic.
4. Differences among browser login sessions, HTTP Basic, API bearer tokens, and logging in through an Identity Provider (IdP).
5. How to choose the integration sequence: internal accounts -> real persistence -> session management -> APIs -> IdP/LDAP; while knowing how to test failure cases and trust boundaries.

**Authentication** answers "who is this, and what evidence proves the identity?". **Authorization** answers "what is that identity allowed to do?". Successful login does not imply permission to access every resource. `GrantedAuthority`, roles, and scopes are inputs to authorization decisions; designing detailed authorization policies is outside the scope of this lesson.

## 2. Recommended Prerequisites

| Foundation | What to understand before starting | Self-check |
| --- | --- | --- |
| Java 17+ | Classes, interfaces, exceptions, constructor dependency injection, annotations | Explain why a service can accept an interface instead of an implementation |
| Spring Boot and Spring MVC | `@SpringBootApplication`, `@Configuration`, `@Bean`, `@RestController`, endpoint mapping | Create `GET /hello` returning HTTP 200 |
| HTTP/HTTPS | GET/POST, headers, statuses, 302 redirects, cookies, TLS | Distinguish request/response and why passwords must travel over HTTPS |
| Session state | `JSESSIONID` cookie, server-side sessions, timeouts | Explain why a browser can be recognized on the next request |
| User storage | Identifier keys, querying by username/email, password hash columns, enabled/locked flags | Distinguish raw passwords from hashed values stored in the DB |
| Security concepts | Authentication, authorization, salted hashing, CSRF, XSS, brute force, least privilege | Explain why you must not store plaintext passwords or disable CSRF just to make a form POST work |
| Testing | JUnit, MockMvc, reading logs without secrets | Write tests for unauthenticated requests and wrong passwords |

You can learn HTTP cookies/sessions and password hashing alongside the initial stage; **do not start with JWT, OAuth2, or a custom `AuthenticationProvider`** before understanding the standard login flow.

## 3. Map of a Login Request

```text
Browser: GET /profile (unauthenticated)
    → Servlet Filter Chain / Spring Security
    → no valid Authentication, endpoint requires authenticated
    → AuthenticationEntryPoint redirects to /login
    → Browser GET /login, receives login page
    → Browser POST /login (username, password, CSRF token)
    → UsernamePasswordAuthenticationFilter creates unauthenticated Authentication
    → AuthenticationManager (typically ProviderManager)
    → Appropriate AuthenticationProvider (typically DaoAuthenticationProvider)
    → UserDetailsService fetches user + password hash + status
    → PasswordEncoder.matches(rawPassword, storedHash)
    → success: authenticated Authentication
    → SecurityContextHolder holds SecurityContext for the request
    → session/context repository mechanism persists state when appropriate
    → subsequent request: browser sends cookie, context is restored
    → Controller receives authenticated identity
```

This is a **common path for form login using username/password**, not a fixed diagram for every mechanism. HTTP Basic, bearer tokens, and OAuth2 Login use different filters/providers yet still converge on an authenticated identity in `SecurityContext`.

Read each component by its exact responsibility:

- `SecurityFilterChain` defines the filter layer protecting HTTP requests; login configuration and access conditions live here.
- `Authentication` represents an authentication request (before verification) or a result containing principal, authorities, and authentication status (after verification).
- `AuthenticationManager` receives authentication requests; `ProviderManager` can delegate across multiple `AuthenticationProvider` instances by credential/token type.
- `DaoAuthenticationProvider` uses `UserDetailsService` to fetch account info and `PasswordEncoder` to verify passwords.
- `SecurityContextHolder` allows reading the current `SecurityContext`, normally bound to the request-processing thread. Persisting context across requests depends on repository/session mechanisms; do not assume `ThreadLocal` data survives into the next request by itself.
- `AuthenticationEntryPoint` initiates authentication when needed (login redirect or HTTP challenge); `AuthenticationFailureHandler` and `AuthenticationSuccessHandler` handle login outcomes.
- `SecurityContextRepository` handles saving/restoring context. **If implementing a custom login flow outside standard filters**, consider saving the context explicitly; merely calling `SecurityContextHolder.setContext(...)` is not enough on its own to guarantee login persistence.

## 4. Practice Sequence from Simple to Production-Ready

### Stage 1 — An Application with the Default Login Page

**Goal:** observe before/after authentication with the fewest moving parts.

Create a Gradle Spring Boot **3.3.13** application, Java **17+**, package `dev.demo.auth`. If using Spring Initializr, choose **Spring Web**, **Spring Security**, Gradle, and Java 17 or higher. The minimal `build.gradle` below uses Spring Boot-managed dependencies:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
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

Create `src/main/java/dev/demo/auth/AuthLearningApplication.java`:

```java
package dev.demo.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class AuthLearningApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthLearningApplication.class, args);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

Create `src/main/java/dev/demo/auth/SecurityConfig.java`:

```java
package dev.demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-pass-123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

In the project directory, run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), or use the corresponding Gradle task in your IDE. This example uses default form login **without configuring `loginPage(...)`**, so Spring Security provides the login screen automatically. The password `demo-pass-123` is **learning data**; never copy it into real production accounts.

Experiment in sequence:

1. Open `http://localhost:8080/public` while logged out: receive **HTTP 200**, body **`public`**.
2. Open `http://localhost:8080/profile` in a fresh browser: redirected to `/login`. This shows a request requiring authentication before entering the controller.
3. Log in with `learner` / `demo-pass-123` on the default login page. After returning to `/profile`, the body is **`hello learner`**.
4. Try a wrong password: login fails, and no valid user session is created. By default form login redirects back to the page with an error indicator.
5. Open/watch DevTools Network and observe the **302 redirect**, **POST /login**, cookie/session, and post-login requests. In the browser, the login form includes a CSRF token; do not test a POST without the token and conclude the password was wrong.
6. Log out using Spring Security's logout feature and visit `/profile` again. When CSRF is enabled, logout should use **POST** with a CSRF token rather than assuming GET logout.

**What to understand after Stage 1:** `requestMatchers` decides whether a resource requires an identity; form login is how **credentials are collected**, `UserDetailsService` supplies the user, the encoder verifies the secret, and the context represents the logged-in user. `ROLE_USER` in the example is an authority assigned to the user, not yet a detailed authorization policy.

### Stage 2 — Understanding Passwords and Replacing InMemory with a Database

**Goal:** log in from durable accounts without hardcoding users in configuration.

Follow in order:

1. Design an accounts table with at least `id`, unique `username`, `password_hash`, `enabled`, `locked`, and created/updated timestamps. Distinguish internal accounts from business user profiles.
2. Build a registration/provisioning flow: **encode** passwords once before writing to the DB; at login, read the hash and use `PasswordEncoder.matches(raw, hash)`. BCrypt uses a salt, so encoding the same password twice usually yields two different hashes; **never compare two hash strings with `equals`**.
3. Replace the `InMemoryUserDetailsManager` bean with a `UserDetailsService` that loads accounts via a repository by username. Return `UserDetails` containing username, password hash, enabled/locked flags, and authorities. This is the **data-source extension point**; there is no need to replace the entire authentication pipeline yet.
4. Configure a `PasswordEncoder` bean consistent with the hash format in the DB. In systems supporting multiple algorithms over time, look at `DelegatingPasswordEncoder` and `{id}` prefixes; never mix unformatted hashes and silently "fall back" to plaintext.
5. Test all states: existing user, wrong password, disabled/locked user, nonexistent user, password update, and permission changes.

The snippet below is only a **sketch of the DB wiring point**, requiring `Account` and `AccountRepository` classes in a real system; it is not a standalone runnable Java file:

```java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));

    return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .roles("USER")
            .build();
}
```

Never call `PasswordEncoder.encode(rawPassword)` and compare directly against the DB on each login; also never log passwords, access tokens, or Authorization headers. Error messages shown in the UI should be helpful enough without revealing whether a username exists. Add attempt rate limiting, failed-login monitoring, and account lock/unlock rules per real requirements.

### Stage 3 — Sessions, SecurityContext, CSRF, and Login Lifecycle

**Goal:** master the question "why does the next request still know who I am?".

With **browser + form login**, after successful authentication Spring Security can persist security information via `SecurityContextRepository`/HTTP session. The browser holds a cookie referencing the server-side session; the server restores the context to handle the next request. This is **not** the client resending the password on every request, nor is it `SecurityContextHolder` persisting by itself.

Hands-on exercise: log in -> inspect session cookie -> request `/profile` -> log out -> request again -> timeout -> log in again. Observe session ID rotation at login (session fixation protection), timeout configuration, multi-tab/browser behavior, and session invalidation on logout. If running across multiple nodes, consider a shared session store and logout strategy matching the deployment architecture.

CSRF is a specific risk for requests where the browser attaches cookies automatically. In form login, keep CSRF protection enabled and include the token in POST forms; use a view technology that supports CSRF or pass the server-issued token properly. **Never disable `csrf` globally to fix a 403 error.** For truly stateless bearer-token APIs, CSRF decisions depend on how credentials are transmitted and whether the browser sends them automatically; you cannot conclude from the word "REST" alone.

Read `SecurityContextHolder` for the current request, yet be careful with `@Async`, executors, or other threads: identity does not propagate automatically to every thread. Never store `Authentication` in a static variable or global cache to "keep login alive".

### Stage 4 — From HTML Login to API Authentication

**Goal:** choose the right credential type for the right kind of client.

| Access pattern | Credential and state | Typical unauthenticated behavior | When to learn/use |
| --- | --- | --- | --- |
| Form login + session | Form submits username/password once; browser holds session cookie | Redirects to login page | Web apps with server-side sessions |
| HTTP Basic | Every request sends `Authorization: Basic ...`; Base64 content is **not encryption** | HTTP 401 with Basic challenge | Learning the mechanism, simple integrations over HTTPS; weigh real-world suitability |
| Bearer access token | `Authorization: Bearer <token>`; API validates token | HTTP 401/challenge if token is missing/invalid | SPA/mobile/API where an IdP or authorization server issues tokens |
| OAuth2/OIDC Login | Browser redirects to IdP; app receives code flow result and establishes principal/session per config | Redirects to IdP | SSO/login via organization or external provider |
| LDAP/AD | Directory serves as authentication/identity source | Depends on UI and integration filters | Enterprise systems with a directory |

**HTTP 401** usually means missing/failed authentication; **HTTP 403** means the request was denied despite being authenticated or failed another protective check (e.g., CSRF). Looking at the status code alone is insufficient for diagnosis: inspect the login mechanism, safe logs, and what produced the response.

Mini exercise: switch a learning endpoint to HTTP Basic using `http.httpBasic(Customizer.withDefaults())`, call it from a client with and without the header, and compare with form login redirects. This is an **illustrative configuration snippet added** to `SecurityFilterChain`, not a standalone Java program. Use only over HTTPS; never treat Base64 as password security.

Next, learn **resource servers**: the application receives an access token issued by a trusted issuer, verifies the signature (for JWTs), `iss`, `exp`, and `aud` per the API's requirements, maps claims/scopes to authorities, and establishes the principal. The example configuration below is complete only when the project adds `spring-boot-starter-oauth2-resource-server`, has a valid issuer, and has an appropriate audience validation policy:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/demo
```

`identity.example.org` is only an **illustrative address; there is no real IdP there**. With JWTs, never "Base64-decode" and trust the contents: decoding is not verification. Never use an OIDC **ID token** as an access token to call an API just because it has a JWT shape; each token type has a different intended recipient and purpose.

### Stage 5 — Customize Only When Standard Extension Points Fall Short

**Goal:** identify the right layer to replace when a system uses non-standard authentication sources.

- If only changing where users are stored (DB, JDBC, LDAP): prefer integrating `UserDetailsService` or a Spring Security-supported provider.
- If you must verify a special credential type issued by another system: study `AuthenticationProvider.supports(...)`, `authenticate(...)`, how to return success/failure results, and registering the provider with `AuthenticationManager`.
- If credentials arrive over a new HTTP protocol: an appropriate filter/extractor may be needed, yet never write a manual filter just to receive username/password for form login.
- If calling an external identity service: set timeouts, limit retries, handle outages, never log secrets, clarify who is the source of truth for account locks, and ensure no "fallback" to a weaker mechanism when the external service fails.

Mental check: if an identity-service endpoint returns "account authenticated", the application must check **verifiable evidence** and the trust boundary, not merely trust a JSON field `authenticated=true` from a client. Clearly separate **credential authentication** from **profile/role synchronization** after identity is verified.

### Stage 6 — Logging In via an External IdP: OAuth2 Login and OpenID Connect

**Goal:** integrate SSO without directly handling the provider's passwords.

Learn the roles in order: browser/user -> **OAuth2 Client/Relying Party** application -> **Authorization Server/OpenID Provider** -> **Resource Server** API (if any). **OAuth 2.0** is primarily an access-delegation framework; **OpenID Connect (OIDC)** adds an authentication layer and ID tokens to convey standard identity info. When asked for "Sign in with provider", prioritize understanding the **OIDC Authorization Code Flow** rather than loosely calling OAuth2 a login protocol.

Typical flow:

```text
Browser opens protected page
    → application redirects to IdP (authorization request)
    → IdP authenticates user and obtains consent if needed
    → IdP redirects back to registered redirect URI with authorization code
    → application exchanges code via back channel for tokens
    → library verifies state, token/issuer/nonce per flow and config
    → application builds principal, decides mapping to local account
    → establishes login session or returns response to application
```

Master `client_id`, exact redirect URIs, `state` to prevent request mix-ups/CSRF, `nonce` in OIDC, PKCE where appropriate, issuer/discovery metadata, JWKS, `sub` as the stable identifier within an issuer, session/local logout, and token lifecycle. For external accounts, the durable key is usually **(issuer, subject)**; never automatically equate two people solely by matching emails or unverified emails.

For a Spring MVC app, the integration exercise requires `spring-boot-starter-oauth2-client`, a valid client registration at the IdP, and `spring.security.oauth2.client.registration`/`provider` configuration. In `SecurityFilterChain`, the introductory configuration is:

```java
http.oauth2Login(Customizer.withDefaults());
```

This is only **an illustrative single-line configuration**, not runnable standalone without a client registration/IdP. Spring Security typically uses initiation endpoints like `/oauth2/authorization/{registrationId}` and callbacks like `/login/oauth2/code/{registrationId}`. Verify the exact redirect URI allowed by the IdP and whether the app runs behind HTTP/HTTPS via a reverse proxy.

Questions to answer before implementing: when login succeeds and the local user does not exist yet, do you auto-provision, link under control, or reject? Are roles and groups fetched from the IdP at login or synced periodically? What happens if the IdP is down? When logging out of the IdP, does the local session remain valid? These are design decisions requiring tests, not assumptions that the framework handles them for you.

**Next learning tracks:** LDAP/Active Directory when using a directory; SAML2 when enterprise systems use SAML; MFA/step-up authentication when higher assurance is needed. These are branches to explore after mastering general authentication architecture, not prerequisites for building internal form login.

## 5. Choosing a Learning Path by Problem

| Problem | Right starting point | Next steps to clarify |
| --- | --- | --- |
| Learning website with internal account login | Form login + in-memory user | Password hashing -> DB -> session/logout |
| Enterprise web app with users in DB | `UserDetailsService` + encoder | Account state, rate limiting, password reset, auditing |
| API server receiving tokens from a provider | OAuth2 Resource Server | Issuer/JWKS, audience, scopes, token errors, and clock skew |
| Web app "Login with Company/Google/IdP" | OAuth2 Client + OIDC Login | Redirect URI, subject mapping, account linking, logout |
| Internal portal connecting to AD/LDAP | LDAP authentication integration | Bind mode, group mapping, TLS, directory outage |
| Multi-identity-source system | `AuthenticationManager` + controlled providers | Provider order, fallback policy, trust, security tests |

There is no need to build an authorization server or sign tokens yourself to learn basic authentication. When integrating externally, first clarify whether **the application is a login client, an API validating access tokens, or a token-issuing system**; these three roles do not substitute for one another.

## 6. Minimum Test Matrix at Each Stage

| Case | Expectation to verify |
| --- | --- |
| Public request without a session | Access allowed |
| Protected request while unauthenticated | Redirect to login for browsers, or 401 for the chosen API mechanism |
| Valid username/password, active account | Valid principal created; subsequent request sees the right username |
| Wrong password or nonexistent account | Rejected; no authenticated session created; no passwords/sensitive logs leaked |
| Disabled/locked account | Rejected per policy; status flags not ignored |
| Form POST missing/mismatched CSRF token | Rejected when CSRF protection applies |
| Logout and expired session | Old session cannot be reused to enter protected resources |
| Expired/wrong-issuer/wrong-audience/bad-signature JWT | Token rejected; never accepted merely because payload parses |
| IdP callback with bad state/nonce/redirect | Flow fails safely; does not attach a user from client-supplied data |
| DB/LDAP/IdP source unavailable | Fails closed under control; does not allow login via a weak fallback path |
| Password change or account lock | Verify policy on already-issued sessions/tokens; do not silently assume every session is instantly revoked |

With `spring-security-test` and `MockMvc`, distinguish testing with **mocked identity** (e.g., `@WithMockUser`) from testing the **real authentication flow** via `formLogin()`. `@WithMockUser` is useful when testing resource access, yet it does not prove `UserDetailsService`, the encoder, or the login filter work properly. A test suite should include both, especially negative cases.

**Repeatable practice:** capture Network/browser state before login, run through the matrix cases, record request URLs, statuses, cookies/redirects, and the principal observed at endpoints; never store passwords, session IDs, raw access tokens, or raw ID tokens in docs/log files. For real systems, add refresh/revocation tests and permission-sync tests per operational policy.

## 7. Common Mistakes and How to Spot Them

1. **Confusing authentication with authorization:** login succeeds yet the endpoint returns 403 may be due to an access policy, not a password error.
2. **Writing a manual `POST /login` controller to string-compare passwords:** bypasses framework-provided filters/providers, CSRF, session fixation, and success/failure handling.
3. **Storing plaintext or single-round SHA-256 for passwords:** use password hashing with proper cost/salt; manage hash upgrades and never invent your own algorithm.
4. **Disabling CSRF because of a 403:** examine the client type, cookies, and token mechanism; restrict exceptions only with clear justification.
5. **Setting `anyRequest().permitAll()` to "make login work":** defeats endpoint protection. You must have public requests and authenticated requests to observe the difference.
6. **Assuming having `Authentication` means a session was saved:** distinguish the current request's context from repository/session persistence and custom login APIs.
7. **Confusing an OAuth2 Access Token with an OIDC ID Token:** API-facing tokens and identity-representing tokens have different audiences/purposes.
8. **Trusting JWT claims just because they decoded:** verify issuer, signature, timestamps, and audience at the resource server.
9. **Relying on email as the sole external identity key:** use issuer + subject, a safe account-linking workflow, and check email verification if used.
10. **Calling an external provider without timeout/failure policies:** an outage can turn into a security flaw or hang all logins.
11. **Testing only with `@WithMockUser`:** those tests do not exercise real password or IdP verification flows.
12. **Jumping straight to custom filters/providers:** learn standard features first, replacing only the extension points your requirements truly demand.

## 8. Capstone Exercise to Prove You Learned in the Right Order

Build a small demo application with `/public`, `/profile`, `/admin-demo`, and an internal account. Complete it by milestones, adding only one variable per milestone:

1. **M1 — Standard flow:** in-memory user, default form login, protected requests, observe redirect/cookie/CSRF, logout. Include at least three pass/fail tests.
2. **M2 — Real data source:** replace user store with a DB, store BCrypt/`DelegatingPasswordEncoder` hashes, test disabled/locked accounts without leaking account existence.
3. **M3 — Lifecycle:** session timeout, logout, verify requests after session expiry, log security events without leaking secrets.
4. **M4 — API:** create an API with appropriate authentication (Basic for learning only, or Resource Server with a test issuer); explain HTTP 401, 403, and where credentials are sent accurately.
5. **M5 — External integration:** configure a test IdP for OIDC Login; test login, account mapping, bad callbacks, IdP outage, and logout. Include a trust boundary diagram.

**Completion criteria:** you can draw the authentication flow yourself, point out what each layer does, run the Stage 1 demo, explain DB/session/API/IdP without mixing mechanisms, have tests for failure cases, and state risks at the application <-> IdP boundary. If you cannot yet explain the path of `UsernamePasswordAuthenticationToken` and the roles of `UserDetailsService`/`PasswordEncoder`, reinforce Stages 1–2 before moving to OIDC.

## 9. Official Reference Documentation

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — OAuth2 / OIDC Client and Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html)
- [Spring Boot 3.3 — Java/Gradle requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)

The links above reference the Spring Security 6.5 / Spring Boot 3.3 line for easy alignment with the examples; when your project uses a different Spring Boot/Spring Security version, double-check the APIs, security defaults, and corresponding guides.