# Distinguishing Authentication, Authorization, and Attack Protection in Spring Security Reactive

## 1. The Big Picture

In a Spring WebFlux application, security must answer three distinct questions:

1. **Authentication:** Who is sending the request? Does the system have sufficient proof to trust that identity?
2. **Authorization (access control):** Which actions is the authenticated identity allowed to perform on which resources?
3. **Protection against attacks:** How can requests and data be exploited, even when a user is logged in or an endpoint allows access?

For example: a user logs in successfully and has permission to view orders, yet still must not view someone else's orders; meanwhile, the API must defend against browser-based request forgery, token leakage, XSS, malicious input, and resource abuse. These three layers complement one another and cannot replace each other.

| Perspective | Authentication | Authorization | Attack protection |
| --- | --- | --- | --- |
| Question | "Who are you?" | "What are you allowed to do with this object?" | "How could requests or the system be exploited?" |
| Inputs | Password, session, bearer token, certificate… | Principal, permissions, roles, resource, business context | Request pattern, cookie/token, headers, origin, payload, traffic |
| Outcome | Identity and authentication status | Allow or deny the operation | Block, rate-limit, mitigate threat impact |
| Typical components | ReactiveAuthenticationManager, ReactiveUserDetailsService, Authentication | authorizeExchange, AuthorizationManager, @PreAuthorize | CSRF, CORS, security headers, TLS, password hashing, validation, rate limiting |
| Common mistake | Trusting a client-supplied username | Only checking "is logged in" | Assuming having Spring Security automatically makes you immune to every attack |

**Quick reminder:** authentication proves identity; authorization decides scope of actions; defense controls attack paths across the entire processing flow.

## 2. How Spring Security Works in a Reactive Application

Spring WebFlux runs on Reactor (Mono/Flux) and an asynchronous processing model. In this stack, Spring Security places **WebFilter**s into a **SecurityWebFilterChain** to process requests before invoking handlers:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |-- Check/restore SecurityContext, process credentials
    |-- Authentication: produce an authenticated Authentication
    |-- Authorization: apply URL access rules
    |-- Defense mechanisms: CSRF, headers, exception handling...
    v
WebFlux Controller -> Service (possibly with method security) -> Data
    |
    v
HTTP response
~~~

This is a conceptual diagram; the exact WebFilter order is configured by Spring Security and may differ across HTTP Basic, session, or OAuth2 Resource Server mechanisms.

- **Authentication** holds the principal, the list of GrantedAuthority values, and authentication status. These values must be produced/verified by a trusted security mechanism, not taken directly from self-declared client parameters.
- **SecurityContext** holds the Authentication corresponding to the request. In reactive applications, context lookup/implicit propagation happens primarily via **Reactor Context**; do not rely on ThreadLocal or assume every request runs on a single thread.
- **ReactiveSecurityContextHolder.getContext()** returns a Mono<SecurityContext>, useful when user information is needed inside a reactive pipeline.
- **SecurityWebFilterChain** protects HTTP exchanges; **reactive method security** protects service methods invoked through a Spring proxy. Business rules and per-record permission checks still need to be placed at the appropriate layer.

An endpoint configured with permitAll only means login is not required by that access rule; it does not mean skipping all WebFilters, all HTTP security headers, or input validation.

## 3. Authentication: Identifying the Caller

Common mechanisms:

| Mechanism | Credentials | Typically suited for | What to watch out for |
| --- | --- | --- | --- |
| HTTP Basic | Authorization: Basic… (Base64-encoded username/password, not secure encryption) | Demos, internal integrations protected by HTTPS | Use only over TLS; browsers may automatically resend credentials |
| Form login + session | Initial credentials followed by a session cookie | Browser-facing web applications | Cookies, CSRF, sessions, logout, session timeout |
| OAuth2 Resource Server + JWT | Authorization: Bearer… | APIs receiving access tokens from a trusted issuer | Verify signature, issuer, audience, expiration; map scopes/permissions |
| Opaque bearer token | Token introspected against an authorization server | APIs needing server-side token status/revocation | Introspection connectivity, caching, handling auth server failures |

Successful login does not automatically grant admin privileges. Conversely, a client sending a "role=ADMIN" header is not proof of admin rights either.

**Passwords:** store password hashes using an appropriate algorithm such as bcrypt, Argon2, or PBKDF2 with strong parameters; never store plaintext passwords, and never hash with plain SHA-256 alone. PasswordEncoder handles encode and matches. In-memory test credentials are not an identity management strategy for production.

**Tokens:** JWT is only a format. The API must verify the signature and required claims; decoding a JWT string to read sub without validating it is not authentication. Access tokens should have short lifetimes, be transmitted over HTTPS, and avoid being logged; revocation or exposure-mitigation strategies should also be considered.

## 4. Authorization: Deciding What the User Is Allowed to Do

Three levels of control are commonly combined:

1. **By URL and HTTP method:** e.g., GET /public/ping is open to everyone; GET /admin/report is restricted to ROLE_ADMIN.
2. **By business method:** protect services with @EnableReactiveMethodSecurity and @PreAuthorize so a service cannot bypass policy when called from another path.
3. **By specific object:** when reading order 42, you must still verify ownership/tenant permissions for order 42 itself. Having permission to read orders in general does not inherently allow reading every order.

Distinguishing permission names in Spring Security:

- **hasRole("ADMIN")** checks for the **ROLE_ADMIN** authority by default convention.
- **hasAuthority("orders:read")** checks for the exact authority **orders:read**, without adding any prefix.
- With JWT Resource Server and default mapping, scopes may appear as authorities like **SCOPE_orders.read**. Claims inside a token do not automatically carry the same meaning as application roles; you must understand the authority converter being used.

Place specific matchers before broad matchers, ending with **anyExchange().authenticated()** or **denyAll()** as needed. Having a clear default policy reduces the risk of newly added endpoints being accidentally exposed.

**Object-level authorization bug example (IDOR/BOLA):** user A has permission to call GET /orders/42, but order 42 belongs to user B. Using only authenticated() or hasAuthority("orders:read") at the URL level is insufficient. The service/repository should fetch data scoped to the permitted tenant/owner before returning results; it may return 403 or 404 depending on policies against disclosing resource existence. Never use a client-supplied ID to infer ownership.

## 5. Runnable Demo: Spring Boot WebFlux + HTTP Basic + Role-Based Authorization

The demo uses **Java 17+**, Spring Boot **3.3.5**, Spring Security for WebFlux, and two in-memory accounts. The goal is to clearly observe 200/401/403 responses on HTTP GET endpoints, not to implement real-world login or a data-writing API.

File structure:

~~~text
reactive-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/reactiveauth/ReactiveSecurityDemoApplication.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'reactive-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

**src/main/java/com/example/reactiveauth/ReactiveSecurityDemoApplication.java**

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "hello " + context.getAuthentication().getName());
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Run:** requires JDK 17+ and a Gradle version compatible with Spring Boot 3.3; in the project directory run:

~~~bash
gradle bootRun
~~~

In another terminal, test sequentially:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -u reader:reader-pass http://localhost:8080/me
# hello reader

curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/admin/report
# admin-report
~~~

Result breakdown:

| Request | Authentication | Authorization | Outcome |
| --- | --- | --- | --- |
| GET /public/ping without credentials | Not required | permitAll | 200, pong |
| GET /me without credentials | Unauthenticated | Requires authenticated | 401 |
| GET /me as reader | Valid password | Authenticated | 200, hello reader |
| GET /admin/report as reader | Authenticated | Lacks ROLE_ADMIN | 403 |
| GET /admin/report as admin | Authenticated | Has ROLE_ADMIN | 200, admin-report |

With HTTP Basic, **401** typically includes WWW-Authenticate to prompt for credentials; **403** means the identity was accepted but lacks permission. If an application configures form login, unauthenticated browser requests may be redirected to a login page instead of returning JSON/401: it depends on the entry point.

The code above **keeps the default CSRF configuration** and only provides read-only GET endpoints. Do not assume HTTP Basic automatically eliminates CSRF: browsers may automatically resend cached Basic credentials. Both demo passwords must be replaced with a proper identity store and secrets management when moving to a real environment.

## 6. Method Security and Per-Object Permissions

In a reactive system, you can enable method security and protect a method on a Spring bean:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfig {
}

@Service
class AdminReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readReport() {
        return Mono.just("admin-report");
    }
}
~~~

This is an **independent illustrative snippet** for the service layer; there is no need to add it to the demo to test the five requests above. Calls must go through the Spring bean/proxy for the annotation to take effect; internal calls via this.method() may bypass the proxy mechanism. Methods protected with reactive method security should return an appropriate publisher (Mono/Flux).

@PreAuthorize can check roles/authorities, but when data depends on ownership, also validate the business condition. For example, query the database by both orderId and tenantId obtained from the verified identity. Never trust a tenantId merely because the client sent it in the URL or body.

## 7. Protecting Against Common Attacks

| Threat | Scenario | Primary defense | What Spring Security does not do automatically |
| --- | --- | --- | --- |
| **CSRF** | Another website causes a logged-in browser to send POST/DELETE using cookies or auto-attached credentials | CSRF tokens for state-changing operations; SameSite as an additional layer; design the API around its actual authentication mechanism | Does not decide every case where CSRF can be disabled solely from the word "REST" |
| **XSS** | Untrusted content is injected into HTML/scripts | Context-aware escaping at render time, avoid unsafe HTML/scripts, appropriate CSP | Does not automatically sanitize all data rendered by the application |
| **Credential stuffing / brute force** | Guessing passwords from leaked lists or repeated attempts | Rate limiting, monitoring, controlled soft locks/alerts, MFA, strong password hashing | Does not automatically enforce login attempt limits just because HTTP Basic is enabled |
| **Token/session leakage** | Token read from logs, XSS, storage, or transit | HTTPS, never log secrets, reasonable TTL, HttpOnly/Secure cookies if using cookies, revocation management | Does not automatically revoke a leaked JWT without proper design |
| **IDOR/BOLA** | Changing an ID in the URL to read someone else's data | Check owner/tenant and permissions at the data/business layer | Does not infer ownership from authenticated() |
| **SQL/NoSQL injection** | Input concatenated into query strings | Parameter binding, safe query APIs, input constraints | Does not replace safe query construction |
| **SSRF / path traversal** | User data controls internal URLs or file paths | Destination allowlists, network restrictions, path normalization and validation | Does not automatically protect every HTTP client or file I/O operation |
| **DoS / resource abuse** | Sending massive requests/payloads or CPU-heavy tasks | Gateway rate limits, timeouts, size limits, backpressure, quotas, monitoring | Does not automatically provide full business quota policies |

### 7.1 CSRF: cookies/sessions differ from bearer headers

CSRF exploits the fact that browsers **automatically attach credentials** to requests sent to a target website. If using session cookies or browser-cached HTTP Basic, state-changing endpoints require an appropriate CSRF strategy. Spring Security WebFlux enables CSRF protection by default; for protected POST/PUT/PATCH/DELETE requests, clients must send a valid CSRF token according to the configured mechanism.

For a **truly stateless** API that only accepts bearer tokens manually placed in the Authorization header and does not rely on cookies/auto-sent credentials, disabling CSRF **for that API security chain** can be considered. The decision must be based on the credentials actually sent by browsers and how the application is used; never enable/disable globally out of habit. If cookies are used to store JWTs, CSRF risk may still exist.

### 7.2 CORS: controlling browser cross-origin reads, not granting API permissions

CORS defines which browser origins are allowed to make and read cross-origin responses according to server policy. CORS **does not** replace authentication/authorization: curl, mobile apps, or other servers are not bound by browser CORS enforcement. When using Spring Security with CORS, handle preflight OPTIONS in the right place so preflight requests are not rejected merely for lacking credentials; configure specific origins/methods/headers for trusted frontends. Avoid allowing arbitrary origins together with credentials.

### 7.3 XSS, security headers, and HTTPS

- Encode/escape output according to HTML, attribute, URL, or JavaScript context; do not insert user data into dynamic HTML via unsafe APIs.
- Consider an appropriate Content-Security-Policy for web pages; verify the application's actual security header configuration. Headers help reduce risk but do not replace data validation.
- Use HTTPS for login and APIs; enable HSTS once all access paths are ready for HTTPS.
- For session cookies, consider Secure, HttpOnly, SameSite, session lifetime, logout handling, and session fixation protection. HttpOnly reduces JavaScript access to cookies but does not prevent browsers from sending cookies when exploited; SameSite does not fully replace CSRF tokens.

### 7.4 Specific to reactive programming

Never use block() to obtain SecurityContext in a WebFlux handler or WebFilter; blocking operations can stall the event loop. Keep the Mono/Flux pipeline and access the context via ReactiveSecurityContextHolder. When crossing async boundaries or integrating other libraries, verify how Reactor Context is propagated instead of assuming Servlet-stack ThreadLocal SecurityContextHolder.

Accessing resources requires permission checks at the time of use; do not check once at a gateway and blindly trust all downstream inputs and services. Supporting backpressure, concurrency limits, and timeouts belongs to additional operational design, not default guarantees of authorizeExchange.

## 8. Applying to a Real-World API

Consider GET /api/orders/42:

1. **Transport/protocol:** HTTPS connection; limit request sizes and required headers.
2. **Authentication:** verify the session or bearer token; if invalid/missing and the endpoint requires login, return 401 (or the corresponding login flow).
3. **URL authorization:** require the order-reading scope/permission; if the identity lacks permission, deny, typically with 403.
4. **Object authorization:** look up order 42 within the tenant/owner the identity is allowed to view; block cross-user access.
5. **Data safety:** parameterized queries, return only permitted fields, escape when rendered in UI.
6. **Abuse protection:** rate limit by source/identity, timeouts, telemetry, and anomaly detection.

A system can authenticate properly and enforce URL authorization properly yet still suffer from BOLA. It can also enforce owner checks properly yet still suffer from XSS or token leakage if data/credentials are handled unsafely.

## 9. Misconceptions to Avoid

- **"Once logged in, you can call any API."** False: authenticated() does not replace hasRole, hasAuthority, or per-record permissions.
- **"Roles and authorities are two completely independent lists."** False by default: roles are represented as GrantedAuthority values with the ROLE_ prefix.
- **"CORS blocks all unauthorized clients."** False: it is a browser mechanism; the backend must still enforce permissions.
- **"A decoded JWT is trustworthy."** False: you must verify signature, issuer, audience, expiration, and application conditions.
- **"REST APIs always disable CSRF."** False: evaluate how browsers send credentials, especially cookies and HTTP Basic.
- **"Spring Security automatically blocks SQL injection, XSS, BOLA, and brute force."** False: corresponding controls must be added at the UI, data, business, and infrastructure layers.
- **"WebFlux uses the same ThreadLocal SecurityContext storage as Servlet."** False: prefer Reactor Context and reactive APIs.
- **"Changing a URL to permitAll disables all security controls."** False: many other filters and safety mechanisms can still apply.

## 10. Self-Check Questions

1. User reader calls /admin/report and receives 403 in the demo. Which step did they pass, and which step did they fail?
2. An API lets authenticated users read /orders/{id}, but anyone can change the id to view someone else's order. Is this an authentication bug or an object-level authorization bug?
3. Why cannot CORS replace hasAuthority on the backend?
4. Why is disabling CSRF because "the API uses JSON" an insufficient argument?
5. When switching from HTTP Basic to bearer JWT, what token checks and token leakage protections need to be added?
6. In Mono/Flux, why is ReactiveSecurityContextHolder more appropriate than manually reading the current thread's ThreadLocal?

**Suggested answers:** (1) authentication succeeded, missing ROLE_ADMIN; (2) BOLA/IDOR, owner/tenant checks are needed; (3) non-browser clients are not bound by CORS; (4) risk depends on auto-sent credentials; (5) signature, issuer, audience, exp, scope authorization, HTTPS, and limiting exposure/revocation of tokens; (6) reactive execution can switch threads, whereas Reactor Context carries information along the pipeline.

**Conclusion:** In Spring Security Reactive, design sequentially: **identity authentication → URL/method/object authorization → end-to-end defense across data, browser, and infrastructure**. These three control groups solve different problems and all must be tested directly against the application's request flow.