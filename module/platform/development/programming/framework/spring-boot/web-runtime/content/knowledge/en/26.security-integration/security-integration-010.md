# Boundary Between Web Runtime Configuration and In-Depth Authentication Design in Spring Boot

## 1. Does Configuring Spring Security Mean Authentication Design Is Complete?

**No.** An application can declare a `SecurityFilterChain` to block unauthenticated URLs, verify bearer tokens, and return HTTP 401/403. That only addresses **how HTTP requests are protected at the web runtime**. It does not decide how users register, how passwords/passkeys/MFA work, who issues tokens, how keys are rotated/revoked, how accounts are recovered, or who may access each individual order and tenant.

Two groups of responsibilities must be separated cleanly:

- **Web runtime configuration:** which proxies, Servlet Filters, or WebFlux WebFilters requests pass through; which paths are public; how tokens/cookies enter `SecurityContext`; how URL rules, response semantics, CORS/CSRF, sessions/cookies, HTTPS/forwarded headers, exception handlers, and security headers behave.
- **In-depth authentication/identity design:** choosing identity sources (IdP, user store), verification methods, password hashing, passkeys, MFA, reset/recovery, SSO/OIDC, token issuance/rotation/revocation, brute-force defenses, session lifecycle, audit/risk policies, and domain authorization models.

**Spring Security is the framework that enforces and integrates those policies inside a Spring app, not a complete identity platform turned on by a single property.**

This article belongs to the `Security Integration` group of Spring Boot web-runtime, so it focuses on the **interface between the HTTP layer and identity systems**, how to structure boundaries in code, which decisions belong to the dedicated security/identity workstream, and a runnable, testable Java 17+ Spring Boot 3.x example.

## 2. Concepts That Must Not Be Conflated

| Concept | Core Question | Examples |
| --- | --- | --- |
| **Authentication (AuthN)** | Which verified principal does the current request belong to? | Basic credentials, session, OAuth2 access token |
| **Authorization (AuthZ)** | What is that principal permitted to do on a specific resource? | USER cannot read another user's account; ADMIN has distinct rights |
| **Session management** | How is state retained or reloaded across requests? | `HttpSession`, Spring Session Redis/JDBC, stateless |
| **Credential/token lifecycle** | Who issues, scopes, rotates, revokes, and resets? | IdP, authorization server, token repository |
| **Transport/browser security** | Are the transport channel and browser policies safe? | TLS, Secure cookies, CORS, CSRF, HSTS |
| **Abuse detection/audit** | How are suspicious behaviors detected and investigated? | Rate limits, risk events, login audits, tracing |

A valid principal must not automatically view everyone's resources. When Alice is logged in and calls `GET /api/accounts/bob`, a URL rule `authenticated()` still lets the request through **if there is no owner-level policy**. This is *broken object level authorization* (BOLA/IDOR).

CORS does not prove identity; it is a browser policy for cross-origin responses. HTTPS protects transport, not data permissions. A validly signed JWT does not prove the token was issued for this API or that the user still holds rights.

## 3. Layer Diagram and Processing Boundaries

~~~text
Browser / Mobile / Service Client
        |
        | HTTPS + Cookie / Authorization
        v
CDN / Load balancer / API gateway / Reverse proxy
        | TLS termination, routing, WAF, request limits
        v
Tomcat Servlet container / Reactor Netty HTTP server
        | HTTP parse, connection, headers
        v
Spring Security FilterChainProxy / Security WebFilters
        | CORS/CSRF, SecurityContext, authentication,
        | URL authorization, response handling
        v
DispatcherServlet / WebFlux handler mapping
        | request -> controller, DTO
        v
Application service / Domain authorization
        | object owner, tenant, workflow permission
        v
Repository / Database / downstream services

Identity Provider / Auth Server / Session Store
        | identity, credentials, keys, claims, sessions
        +----------------------------------------------+
~~~

Rejections can happen at multiple layers:

1. The proxy returns 429, 413, or a TLS error **before the request reaches the app**.
2. Spring Security returns 401 for unauthenticated requests or 403 for URL/CSRF denials.
3. The controller returns 400 for invalid input.
4. The domain service returns 403 or 404 per object-access policy.
5. Store/IdP outages cause availability errors; **never bypass authentication to raise uptime**.

Hence status codes alone do not reveal which layer rejected the request. Request IDs, token-redacted security logs, and tracing are essential for investigation.

## 4. Spring Security in the Servlet Web Runtime

Servlet Spring Security attaches to the Servlet Filter Chain via `DelegatingFilterProxy`. Inside, `FilterChainProxy` picks the **first `SecurityFilterChain` matching the request**; security filters then run in framework-managed order.

~~~text
HTTP request
    |
    v
Servlet filters
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |-- choose matching SecurityFilterChain
    |
    +-- security context
    +-- authentication and authorization filters
    +-- CSRF/CORS, exception translation, headers
    |
    v
Spring MVC DispatcherServlet
    |
    v
Controller -> Service
~~~

Exact filters and order may differ across Spring Security versions and configurations. Do not treat an old filter list as fixed.

Distinguish between:

- `http.securityMatcher("/api/**")` determines **which requests enter a specific chain**.
- `authorizeHttpRequests(...requestMatchers(...))` declares **permissions inside the selected chain**.
- `permitAll()` passes that rule's authorization decision; it does not turn off all security filters.
- `denyAll()` actively blocks, making a solid default policy for unlisted routes.
- `@PreAuthorize` protects **method invocations/services**, closer to data/domain logic than URL matchers.
- `WebMvcConfigurer` configures web handling/CORS; it does not replace `SecurityFilterChain`.

**Chain mismatch trap:** if a single chain matches only `/api/**` with no other chain, `/internal/**` endpoints can fall **outside security chain coverage**. With multiple chains, `@Order` and matchers must be tested. Prefer default-deny and make every permitted path explicit.

## 5. What Belongs to Web Runtime Configuration?

### 5.1. HTTP Policy and Status Codes

The web runtime decides:

- Which requests are public, authenticated, or require roles/scopes.
- Which authentication mechanisms plug into filters: form login, HTTP Basic, bearer JWT/opaque tokens, OAuth2 login.
- Whether missing authentication or invalid credentials produce 401, a login redirect, or a specific API error contract.
- Whether insufficient permission returns 403, vs 404/405 depending on routing and data access.
- How CORS preflights pass security, and how CSRF applies per client/credential mode.
- Response headers, session strategy, cookie flags, request timeouts, and webserver/proxy forwarding.

`AuthenticationEntryPoint` and `AccessDeniedHandler` shape responses when authentication is missing vs access is denied. Not all cases behave identically: for an anonymous principal, a permission check failure can be routed to the authentication entry point.

### 5.2. URL Policy Differs from Object-Level Authorization

An HTTP rule `hasRole("USER")` may fit `/api/accounts/**`, yet knows nothing about who owns an account in the DB. `authenticated()` is insufficient if users can swap `accountId` in the URL.

Service/domain policies must evaluate owner, tenant, delegated permissions, and workflow states. DB queries should scope by principal/tenant; cache keys must include permission context. The HTTP and domain layers **complement each other** rather than replacing one another.

### 5.3. TLS, Proxies, and External URLs

In production, browsers may use `https://shop.example.test` while Spring Boot receives only `http://service:8080`. This affects OAuth2 redirects, `Secure` cookies, callbacks, absolute URLs, CORS, and security headers. Enable/trust forwarded headers only from reverse proxies you control.

### 5.4. Sessions, Cookies, and Headers

The web runtime configures idle timeouts, cookie flags, `SecurityContext` persistence, and session repositories. However, **global logout, cross-device revocation, absolute session age, MFA step-up**, and token issuance are not solved just by adjusting session timeout.

## 6. What Belongs to In-Depth Authentication Design?

| Area | Framework/Integration Support | Decisions Design Must Own |
| --- | --- | --- |
| Password authentication | `UserDetailsService`, `PasswordEncoder`, authentication providers | Registration, reset, breach detection, abuse control, hash migration |
| Identity federation | `oauth2Login`, client registrations/OIDC | Trusted IdPs, account linking, callbacks, SSO/logout |
| MFA/passkeys | Authentication flows / external IdP | Enrollment, lost-device recovery, recovery codes, phishing resistance, step-up policy |
| Access tokens | OAuth2 Resource Server validation | Issuer, audience, scopes, grant flows, expiry, key rotation |
| Session/token revocation | Session repositories / adapters | Logout all devices, forced revocation, incident response, persistence |
| Authorization model | URL/method rules, authorities | Role/attribute policies, owner/tenant/data permissions |
| Monitoring | Events, logs, filter hooks | Alerts, retention, forensics, fraud/anomaly detection |
| Recovery and security operations | Extension points | Account lockout, recovery channels, customer support policies |

A custom `POST /login` endpoint that checks a password and mints a JWT **is not automatically** a secure OAuth2/OIDC implementation. Acting as an authorization server requires far more guarantees and contracts: client registration, grants, redirects/PKCE, signing keys, consent, refresh/revocation, metadata, claims, auditing, and threat modeling.

## 7. Choose the Architecture Before Picking Spring Filters

### 7.1. Server-Side Sessions for Browsers

~~~text
Browser -- login --> server/auth service
Browser <-- Set-Cookie: sessionId
Browser -- Cookie: sessionId --> Spring Security session lookup
                                  |
                                  v
                             principal + authorities
~~~

Typically pairs HttpOnly/Secure cookies, CSRF protection, session fixation protection, idle timeouts, and logout invalidation. Across multiple instances, in-memory sessions can be lost when switching nodes; sticky sessions only pin routing, whereas Spring Session Redis/JDBC provides a shared repository.

### 7.2. Bearer Access Tokens for APIs

~~~text
Client -- Authorization: Bearer token --> Resource Server
                                          |
                                          v
                                    signature / issuer /
                                    audience / time
                                          |
                                          v
                                      authorities
                                          |
                                          v
                                   domain authorization
~~~

Spring Security validates JWT/opaque tokens and maps claims/scopes. The token issuer/IdP manages token issuance, MFA, refresh, key rotation, and revocation per contract. A signed JWT **is not automatically encrypted**, so its payload is readable; never store secrets inside claims.

### 7.3. OIDC Login Differs from OAuth2 Resource Server

- `oauth2Login` is the flow where the app acts as an **OAuth2 Client/OIDC Relying Party**, redirecting users to an IdP and receiving login results.
- `oauth2ResourceServer` secures **APIs accepting bearer access tokens**.
- **Authorization Server/IdP** is the component **issuing tokens**, managing identities, and often handling MFA/login UI.
- Service-to-service client credentials or workload identities are distinct from user logins.

**Configuring a Resource Server does not create token-issuing, user registration, or password-reset endpoints.**

## 8. Runnable Java 17+ Example: URL Security vs Owner Security

The example uses Spring Boot 3.3.x, Spring Security 6.x, and **HTTP Basic for a localhost lab**, not a production authentication system. Users `alice` and `bob` hold `ROLE_USER`; `admin` holds `ROLE_ADMIN`. There is no registration, password recovery, MFA, or IdP—precisely those parts sit **outside the web runtime example's scope**.

### 8.1. Structure

~~~text
security-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/boundary/BoundaryApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/boundary/BoundarySecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-boundary'
~~~

`build.gradle` (Spring Boot 3.3.13 illustrative, Java 17):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 8.2. Complete Java Source

File `src/main/java/demo/boundary/BoundaryApplication.java`:

~~~java
package demo.boundary;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class BoundarySecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Example uses GET only; do not disable CSRF arbitrarily.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-password"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-password"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-password"))
                .roles("USER", "ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}

@RestController
class BoundaryController {
    private final AccountService accountService;

    BoundaryController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin/stats")
    Map<String, Integer> adminStats() {
        return Map.of("demoAccounts", 3);
    }

    @GetMapping("/api/accounts/{owner}")
    ResponseEntity<Map<String, String>> account(
            @PathVariable String owner) {
        return ResponseEntity.ok(accountService.readFor(owner));
    }
}

@Service
class AccountService {
    // #p0 references the first method parameter.
    @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
    public Map<String, String> readFor(String owner) {
        return Map.of("owner", owner, "plan", "DEMO");
    }
}
~~~

**This is one valid Java file:** a single public class `BoundaryApplication` and package-private classes in the same package. Spring Boot registers beans for `@Configuration`, `@RestController`, and `@Service`, and the Spring Security method interceptor secures `AccountService.readFor`.

### 8.3. Reading the Example by Boundaries

1. `SecurityFilterChain` keeps `/public/ping` public, restricts `/api/admin/**` to ADMIN, and requires authentication for `/api/**`. This is **web URL policy**.
2. `UserDetailsService` holds in-memory users **so the lab has credentials**. In production, this connects to an IdP/LDAP/DB with proper credential protections. Never commit static passwords into real apps.
3. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` hashes passwords in a format Spring Security understands; hashing is essential yet does not replace reset, lockout, MFA, cost-tuning, or rehashing workflows.
4. `SessionCreationPolicy.STATELESS` instructs security filters not to use `HttpSession` to persist `SecurityContext` in this flow; Basic credentials are resent by clients. Statelessness does not automatically protect against XSS/CSRF.
5. `@EnableMethodSecurity` activates `@PreAuthorize` on the service. Authenticated Alice can pass `/api/accounts/**`, yet `AccountService` denies reading Bob's account. This is **domain/object authorization**.
6. `#p0` avoids relying on runtime parameter names. Method protection is evaluated only when calls go through the method-security interceptor/proxy. Self-invocation inside the same bean can bypass the AOP proxy; place boundaries at service beans and test actual call paths.
7. `admin` has `ROLE_ADMIN` and can read accounts under the demo policy. Multi-tenant systems must still enforce tenant checks for ADMINs; a role name does not automatically authorize cross-tenant access.
8. The lab is GET-only and performs no state changes; CSRF is not disabled globally. When adding POST/PUT/DELETE, design CSRF for your credential mode (especially cookies or HTTP Basic auto-attached by browsers).

### 8.4. Running the Lab

With the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Without a wrapper, install compatible Gradle and generate a wrapper or run `gradle bootRun`. Ensure port 8080 is free.

Public:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expected HTTP **200 OK**, body:

~~~json
{"status":"ok"}
~~~

API missing credentials:

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected HTTP **401 Unauthorized** (usually with `WWW-Authenticate: Basic ...`).

Authenticated Alice:

~~~bash
curl -i -u alice:alice-password http://localhost:8080/api/me
~~~

Expected HTTP 200 and:

~~~json
{"user":"alice"}
~~~

Alice reads her own account:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/accounts/alice
~~~

Expected HTTP 200:

~~~json
{"owner":"alice","plan":"DEMO"}
~~~

Alice tries to read Bob's account:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/accounts/bob
~~~

Expected **403 Forbidden**, because method security in the service blocks it even though the URL matcher allowed the authenticated request through.

Alice tries the admin endpoint:

~~~bash
curl -i -u alice:alice-password \
  http://localhost:8080/api/admin/stats
~~~

Expected 403 at the URL policy layer.

Admin:

~~~bash
curl -i -u admin:admin-password \
  http://localhost:8080/api/admin/stats
~~~

Expected 200:

~~~json
{"demoAccounts":3}
~~~

**Use these passwords only in your localhost lab.** HTTP Basic resends credentials repeatedly and requires HTTPS; values passed to `curl -u` can remain in shell history/process lists, so never use this technique for production passwords.

## 9. MockMvc Tests: URL Rules Do Not Replace Owner Rules

`src/test/java/demo/boundary/BoundarySecurityTest.java`:

~~~java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BoundarySecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPingWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateApiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerAccount() throws Exception {
        mvc.perform(get("/api/accounts/alice")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobAccount() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void regularUserCannotReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(httpBasic("admin", "admin-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.demoAccounts").value(3));
    }

    @Test
    void adminCanReadBobAccountUnderDemoPolicy()
            throws Exception {
        mvc.perform(get("/api/accounts/bob")
                .with(httpBasic("admin", "admin-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.boundary.BoundarySecurityTest
~~~

Two critical verification layers:

- **HTTP boundary:** anonymous → 401; authenticated USER on admin → 403.
- **Domain boundary:** authenticated Alice on Bob's account → 403; authenticated Alice on Alice's account → 200.

`MockMvc` tests verify Spring Security and controller/service integration; they do not replace testing a real identity provider, TLS/proxy, MFA, token expiry, or session failover. Production requires testing those systems at their respective layers.

## 10. HTTP 401, 403, Redirect, 404: Reading the Root Cause Accurately

| Response | Common Meaning | Distinctions Needed |
| --- | --- | --- |
| **401 Unauthorized** | Missing or invalid credentials; includes authentication challenge | Do not assume it means missing role |
| **403 Forbidden** | Authenticated without permission, or blocked by CSRF/CORS in some cases | URL policy, service policy, or CORS/CSRF? |
| **302 Found** | Form login redirect | Unlike bearer-token APIs requiring 401 |
| **404 Not Found** | Missing route/object or intentional existence-hiding policy | Do not assume it is a JWT error |
| **429 Too Many Requests** | Rate limiting at proxy/auth service | Not automatically enabled by Spring Security on all logins |
| **503 Service Unavailable** | Dependency like IdP/session store failing | Do not assume user entered wrong password |

When the browser reports a CORS error while Network shows 401 or 403, inspect **OPTIONS preflight** and the **actual request** separately. Preflight may be blocked by a proxy/Security before authentication runs. Never modify the OAuth2 issuer when the real issue is CORS config, and never disable authorization before diagnosing the status.

## 11. CSRF: Do Not Look Only at the Word “Stateless”

**CSRF** occurs when a browser is induced to send state-changing requests carrying auto-attached credentials, especially session cookies; HTTP Basic after initial login can also be auto-sent by browsers in certain contexts.

- CORS controls **JavaScript permission to read cross-origin responses**, not all CSRF requests from forms/simple requests.
- `SameSite` reduces some cross-site cookie risks, yet does not replace CSRF analysis on sensitive endpoints.
- `SessionCreationPolicy.STATELESS` is solely Spring Security's session policy; it does not prove requests carry no ambient credentials.
- Tokens sent strictly via `Authorization` headers actively attached by JavaScript have a different CSRF threat model, yet still require assessing XSS/token storage, refresh flows, and cookie usage.
- If a browser holds a **JWT in a cookie**, cookie CSRF properties still apply even though the backend uses no `HttpSession`.

Never disable CSRF globally simply because an API uses JSON or due to a slogan like “REST doesn't need it”. For cookie-based apps, use CSRF tokens, `SameSite`, and test state-changing requests; when disabling CSRF for a subset of routes, document clear justification and threat models.

## 12. CORS and FilterChain: Integration, Not a Login Policy

~~~text
Browser
   |
   | OPTIONS /api/resource (preflight)
   | Origin + Access-Control-Request-Method
   v
CORS processing
   | allowed -> browser sends actual request
   | denied  -> browser withholds actual request per preflight flow
   v
Spring Security authentication + authorization
   |
   v
Controller / domain policy
~~~

An allowed origin must never be treated as a trusted user; `curl` and server-to-server clients can spoof `Origin`. Preflight usually carries no session cookie, so Spring Security must handle CORS before authenticating actual requests. With Servlet + Spring MVC CORS config:

~~~java
// Snippet inside SecurityFilterChain configuration.
http.cors(Customizer.withDefaults());
~~~

Never simply permit all `OPTIONS/**` and omit CORS response headers; browsers will still block it. Never pair `allowedOrigins("*")` with credentials. CORS, login, CSRF, and authorization each serve different purposes.

## 13. Forwarded Headers, HTTPS, Cookies, and OAuth Callbacks

Production usually terminates TLS at a proxy:

~~~text
Browser -- https://app.example.test --> Reverse proxy
                                         |
                                         v
                                 http://spring:8080
~~~

Spring Boot may need to know the external scheme/host to construct post-login/OIDC callback redirects, absolute URLs, and `Secure` cookies. Example configuration **only when a trusted proxy is in front**:

~~~properties
server.forward-headers-strategy=framework
~~~

Depending on container/platform, `native` may be better. Never blindly trust `Forwarded`, `X-Forwarded-Proto`, or `X-Forwarded-Host` sent by internet clients: the gateway must strip/overwrite them and the backend must trust only controlled proxies. Otherwise attackers can spoof hosts/schemes or hijack redirects.

When a gateway authenticates and passes `X-User` downstream to a backend, ensure the backend **cannot be reached bypassing the gateway**, headers are produced via a secure trust mechanism, and service-to-service auth is modeled. Trusting raw client `X-User` headers is not authentication.

## 14. Session Cookies: Transport Configuration Differs from Lifecycle

Illustrative Spring Boot Servlet properties:

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

These settings fit **production HTTPS** with a specific cookie policy; localhost HTTP testing can be affected by `Secure` cookies. When using Spring Session, the cookie resolver/`CookieSerializer` may configure a `SESSION` cookie rather than container `JSESSIONID`, so inspect `Set-Cookie` in the actual environment.

Things **not** solved by these properties alone:

- Idle timeout vs absolute session lifetime.
- Session fixation protection and rotating IDs on privilege changes.
- Logout must invalidate the server session, not merely delete the browser cookie.
- “Logout all devices”, concurrent session limits, account deactivation, and forced revocation.
- Cross-node session persistence: sticky sessions do not replicate RAM; Spring Session Redis/JDBC centralizes storage yet introduces TTL/HA/serialization concerns.
- MFA re-authentication or step-up for sensitive actions.
- Cache policies for responses containing personal info, and frontend state after logout.

Cookie `SameSite` is based on **site**, while CORS is based on **origin**; do not treat them as the same concept.

## 15. Spring Security OAuth2 Resource Server: Validator vs Issuer Boundary

A **Resource Server** validates access tokens already issued by an **Authorization Server/IdP**. Enabling Spring OAuth2 Resource Server does not create token-issuing endpoints or build a user registry/MFA.

**Reference** snippet requiring a real IdP and valid tokens; it is not a standalone runnable example like the Basic lab in Section 8:

`build.gradle` needs dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.test/issuer
spring.security.oauth2.resourceserver.jwt.audiences[0]=api://orders
~~~

`SecurityFilterChain` snippet replacing the HTTP Basic flow when real projects use bearer JWTs:

~~~java
@Bean
SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));

    http.sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

    return http.build();
}
~~~

Verify:

1. **Signature and algorithm:** use standard decoders/providers, never merely Base64-decode payloads; never trust arbitrary algorithms/keys specified by the token.
2. **`iss`:** token comes from the trusted issuer; never take `iss` from an untrusted token and fetch arbitrary JWK URIs.
3. **`aud`:** token was issued for this API, not another service's token.
4. **`exp`, `nbf`, and clock skew:** token is valid under time policy and clock sync.
5. **Scopes/roles:** Spring maps scopes to `SCOPE_...` authorities by default; if the domain requires `ROLE_ADMIN`/tenant, configure converters and policies explicitly.
6. **Key rotation/JWK:** the IdP manages signing and rotation; the API must handle JWK caching/fetching and failures cleanly.
7. **Revocation/logout:** self-contained JWTs can remain valid until expiry; logging out a session does not automatically invalidate all access tokens.
8. **Error handling:** invalid/expired tokens usually yield 401; missing scopes/permissions yield 403; never log raw tokens.

These properties **do not** provide a real IdP, login UI, user provisioning, MFA, refresh tokens, or global logout.

### Opaque Tokens

An API can use token introspection instead of local JWT validation. That requires an auth server introspection endpoint, client credentials to call it, timeouts/caching, and fail-closed policies. Opaque tokens, JWTs, and sessions involve different trade-offs in latency, availability, revocation, and sensitive payloads.

## 16. Tenant/Owner Authorization Is What Actually Protects Data

Example request:

~~~http
GET /api/orders/ORD-42
Authorization: Bearer <valid-token>
~~~

A valid signature and `USER` role only confirm **the caller is authenticated**, not that order `ORD-42` belongs to their tenant.

Defense-in-depth flow:

~~~text
SecurityFilterChain:
  /api/** must be authenticated
         |
         v
Controller:
  validate path/query/DTO
         |
         v
Domain service:
  is principal.tenantId == order.tenantId ?
  AND is principal owner/delegate/allowed-role ?
         |
         v
Repository:
  query by (tenantId, orderId), not just orderId
         |
         v
Response:
  data minimization + no-store on sensitive content
~~~

Never treat client-supplied `X-Tenant-Id` or `X-User-Id` headers as proof of ownership. If `@Cacheable` caches data without tenant/identity in the cache key, responses can leak across users **right at the origin** even with HTTP `Cache-Control: no-store`.

`@PreAuthorize` is convenient, yet not every business rule belongs in a hard-to-audit SpEL expression. When permissions depend on DB state and multiple conditions, use an explicit policy service, proper transaction isolation, and tenant-scoped queries.

**Method security proxy pitfall:** calling another method on the same bean via `this` skips the Spring AOP proxy, leaving annotations on the target method unexecuted. Separate bean boundaries, test object-level denials, and never assume an annotation's presence guarantees enforcement.

## 17. Identity Systems: Passwords, MFA, Recovery, and SSO

In-depth workstreams need dedicated owners and security reviews:

### 17.1. Passwords and Account Recovery

- Passwords must be hashed with a maintained password hashing algorithm (BCrypt/Argon2/PBKDF2 per requirements), with calibrated cost and a migration path.
- Never store plaintext or put passwords in URLs, logs, or source configs.
- Password reset tokens must have high entropy, short TTL, single use, and account binding; prevent account enumeration.
- Rate limiting, credential stuffing detection, anti-enumeration, and lockout policies must account for attackers abusing lockouts for DoS.
- Account disabling, password changes, and suspected credential compromise must revoke tokens/sessions per policy.

### 17.2. MFA and Step-Up

- Choose MFA strength carefully: WebAuthn/passkeys/FIDO2 offer stronger phishing resistance than many OTP methods depending on threat model.
- Design flows for enrollment, lost devices, recovery codes, trusted devices, and preventing bypass via password reset.
- An authenticated principal **does not mean** MFA is satisfied for every action. Money transfers, bulk exports, or email changes may require re-authentication/step-up.
- IdPs may issue `amr`/`acr` claims reflecting authentication context; the app must establish a contract and verify them rather than checking roles alone.

### 17.3. Federation and OAuth2/OIDC

- For browsers/mobile, choose Authorization Code + PKCE with proper client security; never invent shortcuts passing tokens in URLs.
- Validate redirect URIs, state/nonce, and issuer/subject; never auto-link accounts solely by unverified email addresses.
- Plan SSO logout, deprovisioning, role/group synchronization, and account lifecycles.
- With multi-tenant IdPs, bind issuer, audience, subject, and tenant claims; prevent a token from one tenant from accessing another.

None of these workflows can be completed with a single `SecurityFilterChain` bean.

## 18. Spring WebFlux: Same Boundaries, Different APIs

WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity` instead of Servlet `SecurityFilterChain`/`HttpSecurity`. `SecurityContext` flows through **Reactor Context** via reactive propagation rather than assuming `ThreadLocal` stays tied to a request across schedulers.

Reactive configuration snippet (placed in a `@Configuration` class with Spring Security WebFlux; **not a standalone class**):

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/**").permitAll()
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Main imports: `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.context.annotation.Bean`, and `org.springframework.security.config.Customizer`.

With WebFlux Resource Server, use a reactive JWT decoder and `oauth2ResourceServer(...jwt())` matching the reactive stack. Never use Servlet `HttpSession` or `OncePerRequestFilter` in pure Netty WebFlux; use `WebSession`, reactive principals, `ReactiveSecurityContextHolder`, or proper framework context propagation.

**The responsibility boundaries remain identical:** reactive web filters enforce HTTP/security policy; the IdP manages tokens/lifecycles; services enforce data/tenant permissions. Using a global `Mono.cache()` for per-user results can leak data across requests; manage caching and reactive contexts separately.

## 19. Observing and Investigating Errors by Layer

| Symptom | Layer to Check First | How to Verify |
| --- | --- | --- |
| Browser preflight returns 401 | CORS/Security chain/proxy | OPTIONS, `http.cors`, ingress |
| API 401 even though JWT “decodes” | Resource Server token validation | `iss`, `aud`, signature, expiry, JWK |
| API 403 with valid principal | URL roles/scopes or method security | selected chain, authorities, service policy |
| Alice reads Bob's data | Data-level authorization | owner/tenant checks, repository/cache |
| Old JWT still works after logout | Token lifecycle | expiry, revocation/introspection strategy |
| Session lost when load balancer switches nodes | Session persistence | local vs Spring Session/shared store |
| OAuth login redirects to HTTP | Proxy forwarded scheme | trusted headers, redirect URI |
| POST gets 403 while GET gets 200 | CSRF or authZ/method security | CSRF token, Cookie, rule order |
| Token from another issuer accepted | Missing trust boundary in JWT validation | decoder issuer/audience configuration |
| `@PreAuthorize` skipped on internal call | AOP proxy/self-invocation | Spring-managed service boundary |
| Right role yet query returns another tenant | Repository/data scoping | `tenantId` from principal and query/cache keys |

### What Should Observability Record?

- Request ID/trace ID, endpoint, status, standardized auth failure reason, chain/node, latency.
- Protect logs: **never log raw Authorization, Cookie, Set-Cookie, passwords, refresh tokens, or session IDs**.
- Distinguish rate limits, CSRF, CORS, expired JWTs, invalid audiences, business unauthorized denials, and dependency outages.
- Business audits should log actor, operation, valid resource identifier, and outcome per policy without dumping raw bodies containing PII.

A 403 from CSRF does not prove a user lacks a role. A 401 from an unavailable IdP/JWK must never be “fixed” by disabling signature verification. **Fail closed** whenever credentials cannot be verified is the default safe rule.

## 20. Testing by Responsibility Boundary

| Scenario | HTTP Web Runtime Test | Identity/Domain Test |
| --- | --- | --- |
| Anonymous hits private API | Security filter returns 401 | No object data leaked in response |
| User A reads account A | URL authenticated | Owner policy allows |
| User A reads account B | URL authenticated | Owner policy denies |
| USER calls admin endpoint | Role matcher returns 403 | Role mapping accurate |
| Expired JWT | Resource Server 401 | IdP TTL/clock policy |
| Wrong-audience JWT | Token validation rejects | Issuer grants right audience |
| Repeated wrong passwords | Authentication failures | Rate limiting/abuse/audit |
| Incomplete MFA login | Flow blocks step-up operations | MFA policy/claims accurate |
| POST with session cookie | Correct CSRF/CORS behavior | Business action authorized |
| Node failure or rolling deploy | No proxy/filter/session bypass | Session/token continuity/revocation |
| User switches tenant | Principal still valid | Data scope/caches follow new tenant |
| Disabled account | Security filter handles failure | Deprovision/revoke and recovery |

**MockMvc/WebTestClient do not replace real proxy/IdP tests.** Service unit tests do not replace filter chain tests either. Splitting tests by boundary clarifies whether a defect belongs to application code, infrastructure, the identity provider, or business authorization.

## 21. Anti-Patterns to Avoid

| Anti-Pattern | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Manually decoding JWT payload and trusting `sub` | Skips signature/issuer/audience verification | Use framework resource server decoders and validators |
| Using `authenticated()` for all domain permissions | Does not protect owner/tenant boundaries | Service/domain authorization |
| Trusting `X-User-Id` from the internet | Clients can forge headers | Verified principal, trusted gateway assertions |
| Disabling CSRF because app is stateless | Browsers may still auto-send cookies/Basic | Threat-model per credential mode |
| Using CORS as a firewall | cURL/server clients ignore browser CORS | Independent AuthN/AuthZ |
| Having `/api/**` chain without a fallback | Unmatched routes can go unprotected | Default deny and test route coverage |
| Minting long-lived JWTs with hardcoded secret | No key/revocation/rotation management | IdP/authorization server, secrets/KMS |
| Logout only deletes the cookie | Server token/session may stay valid | Server-side invalidation/revocation |
| `@PreAuthorize` on self-invoked methods | Proxy/interceptor may not execute | Clear bean boundaries and tests |
| App cache keys missing tenant | Mixes data across users/tenants | Scope cache keys and check auth per access |
| Disabling all security headers to cache CSS | Private routes may be cached/exposed | Allowlist only public assets |
| Swallowing all auth exceptions into HTTP 200 | Breaks semantics, hard to audit | Use 401/403 and proper error contract |
| Letting API trust client Forwarded headers | Redirect/host/proto spoofing | Trusted reverse proxy strips/overwrites |
| “Enabled oauth2Login so we are a token server” | Confuses client with issuer | Distinguish OAuth2 roles |

## 22. Checklist Before Declaring Authentication Integration Complete

1. **Identity owner:** Is someone clearly responsible for the user store, passkeys/passwords, MFA, SSO, and reset/recovery?
2. **Client model:** Web sessions, bearer tokens, OAuth2 login, machine identity, or Basic? Are trade-offs analyzed?
3. **Filter coverage:** Is every URL matched by the right chain in the right order, with nothing accidentally public?
4. **HTTP statuses:** Are 200/401/403/302/404 accurate, leaking no secrets or error details?
5. **Object authorization:** Are owner/tenant/role/attribute checks enforced in services/DBs with IDOR/BOLA regression tests?
6. **CORS/CSRF:** Are browser credential modes, SameSite/Secure cookies, and preflights tested?
7. **Proxy/TLS:** Are forwarded headers trusted properly, and are callback URLs, HSTS, and cookie security accurate from the public endpoint?
8. **Tokens:** For JWTs, are signatures, algorithms, issuers, audiences, expiries, clock skew, scopes, key rotation, and revocation addressed?
9. **Sessions:** Are idle/absolute timeouts, fixation protection, logout, multi-node persistence, and global revocation designed?
10. **Passwords/MFA:** Are hashing, recovery, throttling, enrollment, step-up, and auditing designed?
11. **Caching/logs:** No bearer tokens/sessions/PII in logs; backend caches properly scoped; sensitive responses `no-store`?
12. **Resilience:** Do IdP/session store outages fail closed with incident alerts?
13. **Testing:** Unit/service, MockMvc, staging proxy/IdP, token expiry, and object permission tests?
14. **Governance:** Security review, threat model, incident response, and ownership established?

If you have only finished a `SecurityFilterChain` without those identity and owner-permission decisions, the system **has only finished part of web runtime integration**, not a comprehensive, secure authentication design.

## 23. Self-Check Exercises

**1.** `authenticated()` is enabled on `/api/accounts/**`. Is that enough to stop Alice from viewing Bob's account?

**Answer:** No. That is a URL auth requirement, not object ownership. You need service/DB authorization scoped by owner/tenant.

**2.** Does enabling `oauth2ResourceServer(...jwt())` create an access-token issuer and password-reset system?

**Answer:** No. A Resource Server validates tokens issued by an Authorization Server/IdP; reset/MFA/token issuance belong to the identity platform.

**3.** A JWT has a valid signature yet its `aud` targets a different API. What should the current API do?

**Answer:** Reject it; validate audience, issuer, expiry, algorithm/signature, and related policies.

**4.** A browser stores a JWT inside a cookie; can CSRF be disabled just because the backend is stateless?

**Answer:** No. Browsers can still attach cookies automatically; the CSRF threat model remains.

**5.** Spring Security rejects an OPTIONS preflight with 401. Is that definitely a bad user password?

**Answer:** Not necessarily. Inspect CORS filter integration and the gateway; preflights often carry no user credentials.

**6.** A `@PreAuthorize` on a method invoked via `this` does not run. Where is the bug?

**Answer:** Method security AOP/proxy boundary. Design entry points across proxied beans and test unauthorized paths.

**7.** Ingress terminates TLS and sends forwarded headers, yet the app also trusts headers set directly by clients. What is the risk?

**Answer:** Host/scheme spoofing and broken redirects/callbacks. The gateway must strip/overwrite them and the app must trust only controlled proxies.

**8.** When a JWK cannot be verified due to an IdP outage, can we let requests pass to improve availability?

**Answer:** No. That is fail-open authentication and unsafe. Design resilience while failing closed.

**9.** The Spring Security Basic lab runs cleanly. Is it ready to serve as a production SSO/MFA system?

**Answer:** Not yet. The lab demonstrates only HTTP filters and method security; SSO/MFA/credential lifecycle are separate workstreams.

**10.** Why must you test 401 URL, 403 owner, and 403 admin separately?

**Answer:** They verify **three different decisions**: missing authentication, domain ownership denial, and URL role denial. Passing only one does not prove the others work.

## 24. Official References

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, multi-chain selection.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers and HTTP authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for browser credentials and use cases.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, signature, JWK, claims, scope mapping.
- [Spring Boot — Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.forward-headers-strategy`, trusted proxies, scheme/callbacks.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): HttpSession, fixation protection, session persistence.
- [Spring Security — Reactive Architecture](https://docs.spring.io/spring-security/reference/reactive/architecture.html): `SecurityWebFilterChain` and reactive security.
- [OAuth2 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): authorization flows and security recommendations.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): passwords, MFA, recovery, rate limits.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, default deny, owner/tenant checks.

**Conclusion:** `SecurityFilterChain`, HTTP filters/webfilters, CORS, CSRF, sessions, and proxies are **runtime security integration**. IdPs, MFA, token lifecycles, password recovery, and domain-level access control are **in-depth identity/authentication/authorization design**. Spring Security provides the integration hooks; true protection requires both layers plus thorough testing and operations.