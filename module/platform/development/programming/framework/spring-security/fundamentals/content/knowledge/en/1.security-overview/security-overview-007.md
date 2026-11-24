# Application Protection Scope and Responsibilities That Remain With the Developer

> **Context:** Spring Security is a security framework for Spring applications, focusing on **authentication**, **authorization**, and several HTTP-layer attack-mitigation mechanisms. Having the `spring-boot-starter-security` dependency present does not mean the application is safe from every type of attack. This lesson focuses on Spring MVC/Servlet web applications; for WebFlux, the principles are similar, though the APIs and processing chain differ.

## 1. Learning Objectives

After this lesson, you should be able to answer:

1. Which questions does Spring Security handle at the HTTP boundary and at the method level?
2. Which parts are provided out of the box by the framework, which parts **only take effect when configured**, and which parts must always be handled by business logic or infrastructure?
3. Why can an endpoint that already requires login still leak another user's documents?
4. At which layers must you test so you do not confuse "enabled Spring Security" with "protected application"?

## 2. Security Is Multiple Layers, Not a Single Filter

A real request can travel through the following flow:

```text
Client / Browser
    |
    v
TLS, reverse proxy, WAF/rate limiter (infrastructure, if deployed)
    |
    v
Servlet Filter Chain
    |
    v
Spring Security FilterChainProxy -> matching SecurityFilterChain
    |  Authentication: who is calling?
    |  CSRF/headers/session: configured HTTP protections
    |  Authorization: may this request proceed?
    v
Spring MVC Controller
    |
    v
Service -> object/tenant permission checks, business rules
    |
    v
Repository / SQL / external API / file storage
    |
    v
Data filtered and returned (output encoding, privacy, logging...)
```

With Servlet, Spring Security integrates into the filter chain before the request reaches the controller; `SecurityFilterChain` defines the security filters applied. `Authentication` describes the principal and `GrantedAuthority` instances; `SecurityContext` provides the security context for current processing. The authorization component can make decisions for URLs/methods/HTTP methods, but **does not automatically know** "who owns order 42", "whether this customer may view another tenant", or "whether this data field may be exported".

Distinguish four questions:

| Question | Example | Where Usually Decided |
| --- | --- | --- |
| **Authentication**: Who? | Valid token? Which account? | Spring Security and configured identity system |
| **Entry-point Authorization**: May the operation be called? | `/admin/**` requires `ADMIN` | `SecurityFilterChain`, method security |
| **Data/Business Authorization**: May **this specific object** be accessed? | Is Alice allowed to read invoice #42? | Service/repository with application policy |
| **System-wide Safety**: Is the processing safe? | SQL Injection, XSS, SSRF, secret leaks, DoS? | Developers, relevant frameworks, operations/infrastructure |

**Core principle:** "Authenticated" only proves identity under the active mechanism; it does not automatically grant permission to every resource.

## 3. What Does Spring Security Provide?

### 3.1. Authentication and Maintaining Identity Context

- Built-in authentication mechanisms: form login, HTTP Basic, `AuthenticationProvider`/`AuthenticationManager`, username/password authentication; extensible with identity providers.
- `PasswordEncoder` infrastructure for storing and verifying **hashed passwords**, such as BCrypt/Argon2 with appropriate configuration. The framework does not create password reset policies, account takeover defenses, or identity lifecycle controls on behalf of the application.
- Support for security context management, sessions, and measures like session fixation protection in appropriate configurations. The application must choose the right session/stateless strategy, timeouts, logout/revocation, and session storage.
- Integration for OAuth2 Login/OIDC Client and OAuth2 Resource Server when the right dependencies/configuration are supplied. With JWT, **verifying signature, issuer, audience, scope, and expiration** must be appropriately configured and verified; merely having `spring-security` does not turn an API into a secure Resource Server.

Common pitfall: having an `Authentication` object in `SecurityContextHolder.getContext().getAuthentication()` does not mean every access request is valid; anonymous state and how `SecurityContext` is stored must be understood in the current request's context. Do not trust usernames or roles sent arbitrarily by the client via JSON or headers.

### 3.2. Authorization at Requests and Methods

- `authorizeHttpRequests` can place rules by path, HTTP method, authority/role, or custom `AuthorizationManager`.
- `@EnableMethodSecurity` enables method-level control; `@PreAuthorize`/`@PostAuthorize` only take effect when method security is enabled and the call passes through a suitable proxy/interception point. **Methods without an attached policy are not automatically protected.**
- `hasRole("ADMIN")` typically checks the `ROLE_ADMIN` authority; `hasAuthority("ADMIN")` checks the exact string `ADMIN`. Keep permission-granting conventions consistent.
- `requestMatchers(...)` only checks requests matching rules; `securityMatcher(...)` selects which filter chain applies. When creating multiple chains, ensure no endpoints are left exposed outside the chains' scope.
- Use a clear terminating rule, such as `anyRequest().denyAll()` if you only want to expose a defined set of public endpoints, or `authenticated()` when all remaining paths require login.

URL authorization blocks coarse actions like "ordinary user calls the admin page". It is **not sufficient** for BOLA/IDOR (Broken Object Level Authorization / Insecure Direct Object Reference): a logged-in user changing `/documents/1` to `/documents/2` to fetch someone else's document. Policy must check **principal + action + resource + tenant + business state** against trustworthy data.

### 3.3. Conditional HTTP-Layer Protections

- **CSRF:** In Servlet applications, CSRF protection is enabled in common default configurations; state-changing requests have tokens checked when within scope. The token must genuinely be sent by the form/client. Do not disable `csrf` just because an API returns JSON: if the browser automatically attaches cookies/sessions or Basic credentials, CSRF still needs evaluation.
- **Security headers:** Spring Security can write common protective headers (such as iframe embedding protection, cache control, HSTS when conditions apply). **Content-Security-Policy is not inferred and added automatically by the framework**; application authors must design an appropriate policy. Headers reduce certain risks; they do not replace escaping/validation.
- **CORS:** Spring Security can integrate CORS policies with Spring MVC/`CorsConfigurationSource`. Allowed origins, credentials, methods, and headers are **application decisions**. CORS is a browser policy, not an authentication or authorization mechanism, and does not block requests from curl or server-to-server calls.
- **Session/login/logout:** supporting hooks exist, yet the application must still define token revocation, account lockout, login rate limits, device management, and incident response per its own requirements.
- **Test integration:** supports simulating users, roles, and CSRF in Spring Security Test; tests must still be written by the development team based on actual policies.

**Be careful with defaults:** Defaults can vary across versions, dependencies, application types (Servlet/WebFlux), and whether you define your own `SecurityFilterChain`. Read the running configuration and verify with integration tests.

## 4. Responsibilities That Remain With Developers and Infrastructure

| Risk / Responsibility | How Spring Security Helps | Mandatory Work Outside the Framework |
| --- | --- | --- |
| Strangers entering private APIs | Authentication and HTTP/method rules | Choose login mechanism, protect all entry points, and design proper policies |
| Users viewing others' data (IDOR/BOLA) | Supplies principal/authority, authorization hooks | Check owner, tenant, state, and permissions on **each resource**; put policy in service/queries |
| Privilege escalation via field updates | Blocks operation if rules match | Never let clients write `role`, `ownerId`, `tenantId` arbitrarily; whitelist DTOs and validate state transitions |
| SQL/NoSQL injection | Does not automatically fix queries | Use parameter binding/ORM properly; avoid concatenating query strings |
| XSS/content injection | Supports headers, allows configuring CSP | Escape output **by context**, sanitize allowed HTML, avoid putting raw data into the DOM |
| CSRF | Supports tokens/filters | Choose credential strategy, send tokens properly from clients; test state-changing endpoints |
| SSRF | Does not automatically sanitize outbound URLs | Validate outbound targets, restrict internal DNS/IPs, network egress, timeouts, and redirects |
| Upload/path traversal | Does not inspect user files automatically | Limit size/type, inspect content, generate safe storage names, isolate files, enforce download permissions |
| Broken authentication/session | Has auth/session mechanisms | MFA when needed, lockout/rate limit, reset flows, token revocation, cookie flags, HTTPS, rotation |
| Sensitive data exposure | Does not know which fields are secrets | Data minimization, DTOs, masking, access reviews, encrypting data and backups |
| Secure communication | Certain headers and integrations | TLS at proxy/ingress, trust proxy headers, proper HTTPS/HSTS config, and internal traffic protection |
| Resource exhaustion attacks | Not a complete DoS solution | Rate limiting, quotas, payload limits, timeouts, queues, circuit breakers, capacity |
| Vulnerable dependencies | Does not remove outdated libraries automatically | Track CVEs, update dependencies/base images, inspect SBOMs and configuration |
| Monitoring/compliance | Has authentication and authorization events/hooks | Audit with sufficient context, avoid logging passwords/tokens/PII, restrict log access, alerting and incident response |
| Multi-tenancy | Can propagate identity/claims | Enforce tenant constraints on every query/cache/job/event, isolate data, prevent cross-tenant access |

One easily missed point: requests that do not enter via HTTP (scheduled jobs, message consumers, batch jobs, internal method calls) may **not be subject** to URL authorization. Do not rely solely on filters to protect logic shared across multiple entry points. Domain boundaries must be enforced where data is used.

## 5. End-to-End Example: Locking the Path Still Does Not Protect the Document

The small example below uses **Java 17+, Spring Boot 3.3.13/Spring Security 6.x** to reproduce the behavior; versions are pinned so the lesson remains reproducible. When creating a new production project, choose a currently supported Spring Boot branch and apply patches. Using in-memory accounts and sample passwords is **strictly for learning environments**.

### 5.1. Structure and Dependencies

```text
security-scope-demo/
├── pom.xml
└── src/main/java/demo/security/SecurityScopeApplication.java
```

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-scope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

### 5.2. Complete Java Code

```java
// src/main/java/demo/security/SecurityScopeApplication.java
package demo.security;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityScopeApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/documents/**").authenticated()
                .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo123")).roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("demo123")).roles("USER").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo123")).roles("ADMIN").build()
        );
    }
}

@RestController
class DemoController {
    private final DocumentService documents;

    DemoController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }

    @GetMapping("/documents/{id}")
    String document(@PathVariable long id, Authentication authentication) {
        return documents.read(id, authentication.getName());
    }
}

@Service
class DocumentService {
    private final Map<Long, String> ownerById =
        Map.of(1L, "alice", 2L, "bob");

    @PreAuthorize("hasRole('USER')")
    String read(long id, String requester) {
        String owner = ownerById.get(id);

        // Resource-level policy: USER role alone is not enough.
        if (owner == null || !owner.equals(requester)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "document-" + id;
    }
}
```

There are **three decision layers**:

1. `/admin` requires `ROLE_ADMIN`; this is URL-level authorization in `SecurityFilterChain`.
2. `DocumentService.read` requires `ROLE_USER` via `@PreAuthorize`. Because `@EnableMethodSecurity` is present and the call goes from the controller to the service bean, the method check is applied. `@PreAuthorize` does not apply automatically on internal calls within the same bean via `this`.
3. The comparison `owner.equals(requester)` checks **permission on the specific data**. If you only used `authenticated()` for `/documents/**` or only `hasRole('USER')`, Alice could view Bob's document by guessing the ID.

The example returns `404` when a document does not exist **or** does not belong to the requester to limit existence inference; in a real system, clearly define when to return `403`/`404` per the API contract. In multi-tenant systems, checks must rely on the tenant derived from a trustworthy identity, not solely a client-sent `tenantId`. In practice, enforcing policy in services/repositories with queries like `findByIdAndOwnerId`/`findByIdAndTenantId` prevents accidentally loading unauthorized data.

### 5.3. Run and Verify

Requires JDK 17+ and Maven 3.9+ in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In another terminal, test:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u alice:demo123 http://localhost:8080/documents/1
curl -i -u alice:demo123 http://localhost:8080/documents/2
curl -i -u alice:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/documents/1
```

| Request | Expected HTTP status | Success body / reason |
| --- | --- | --- |
| `GET /public`, anonymous | `200` | `public` |
| `GET /admin`, anonymous | `401` | Requires Basic authentication |
| `GET /documents/1`, Alice | `200` | `document-1` |
| `GET /documents/2`, Alice | `404` | Denied by owner check |
| `GET /admin`, Alice | `403` | Lacks ADMIN role |
| `GET /admin`, Admin | `200` | `admin` |
| `GET /documents/1`, Admin | `403` | Method requires USER role |

Status codes are the behavior to verify; detailed error headers/bodies depend on server configuration. The sample only uses GET, so no CSRF token is needed in the commands above. If adding POST/PUT/DELETE with sessions/cookies, CSRF tokens must be designed and tested. `httpBasic` must run over HTTPS in real environments because Basic only Base64-encodes credentials and does not encrypt transport.

## 6. Common Failure Scenarios and Fixes

### Scenario A — "Already logged in, so any document can be read"

```java
// WRONG in a system with private documents:
@GetMapping("/documents/{id}")
Document get(@PathVariable Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

HTTP filters may enforce login, yet this query does not constrain the owner. Fix: derive principal/tenant on the server, check permission before the operation, and query using conditions matching **both** the document and owner/tenant. Never use an `ownerId` taken from the request body as proof of ownership.

### Scenario B — "Security is enabled, so XSS/SQLi cannot happen"

```java
// WRONG: concatenating untrusted data into a query:
String sql = "SELECT * FROM orders WHERE code = '" + input + "'";
```

Spring Security does not automatically turn that SQL string into a safe query. Fix: `PreparedStatement`/parameterized queries or ORM parameter binding; escape output for HTML/attribute/URL/JavaScript contexts and sanitize HTML if rich text input is permitted. CSP is an extra layer, **not** a replacement for escaping.

### Scenario C — "Stateless APIs can always disable CSRF"

Being "stateless" on the server is **not enough** to conclude that. The deciding question is whether the browser automatically attaches credentials on cross-site requests. An API that only accepts Bearer tokens via a client-set `Authorization` header has a different risk model from cookie auth; examine the concrete threat model. Strict CORS does not replace CSRF tokens when CSRF is still possible.

### Scenario D — "`permitAll()` leaves an endpoint completely unprotected"

`permitAll` removes the authorization requirement for matching requests, yet if the request still passes through the security filter chain, mechanisms such as writing security headers can continue operating. `web.ignoring()` excludes paths from the Spring Security filter chain and has broader impact; avoid using it as a default for static resources.

### Scenario E — "Roles are enough for a multi-tenant system"

Roles only answer what category of action is allowed, such as `REPORT_VIEWER`; **data scope** still requires tenant and actual permissions. Enforcement is required across lists/details/exports, background jobs, cache keys, and queries. When changing from `GET` to `POST` or adding new endpoints, re-verify every policy layer.

## 7. Design, Operations, and Testing Process

### 7.1. Designing From Assets to Protect

1. List data/actions: profiles, invoices, documents, file exports, admin, webhooks, health endpoints.
2. Identify subjects: anonymous, user, admin, service account, tenant; separate identity claims from server-trusted roles/permissions.
3. Write a **principal x action x resource x condition** matrix. For example: only owner can view a document; admin has management permission within their tenant; staff can only export permitted fields.
4. Place checks at both **entry points** (HTTP/method) and **domain/data**. Domain rules must not depend solely on controllers.
5. Choose session cookies, JWT bearer, or OAuth2/OIDC according to trust boundaries; configure TLS, CSRF, CORS, and token storage/revocation accordingly. Avoid disabling filters without understanding why.
6. Implement supporting controls: validation, parameter binding, output escaping, secret management, rate limits, quotas, patching, audit logs, backups.

### 7.2. Minimum Test Matrix

| Check | Expected |
| --- | --- |
| Anonymous calls private endpoint | `401` or redirect to login depending on mechanism |
| Ordinary user calls admin | `403` |
| Alice reads/updates/deletes Bob's resource | Denied or hidden, no data leaked |
| User sends forged `tenantId`/`ownerId` | Does not bypass server-side policy check |
| Revoked permission, expired session/token | Can no longer be used per revocation/expiry design |
| POST with cookie auth but missing/invalid CSRF token | Blocked when CSRF protection applies |
| New URL not on allowlist | Blocked by `denyAll`; test HTTP methods too |
| Input containing special SQL/HTML characters | Queries remain parameterized, output does not execute code |
| Oversized or too-rapid requests | Enforced by designed payload/rate/quota limits |
| Error logs with passwords/tokens/PII | No sensitive data leaked in logs |

In Spring Boot, use `MockMvc`/`spring-security-test` to test `@WithMockUser`, `user()`, `csrf()`, alongside integration tests using real repositories or multi-owner test data to catch IDOR bugs. Test both filter chain configuration and method security, not only service logic. If multiple security chains exist, write tests for endpoints matching and **not matching** each chain.

### 7.3. Pre-Release Self-Review Questions

- Which endpoints use `permitAll`? Why are they public, and is any returned data sensitive?
- Can a user alter IDs, tenants, roles, query/filters, filenames, or URLs in a request to escalate privileges?
- At the point data is read/written, does policy use the real server-side identity and verify ownership?
- Do calls from events/jobs/services or internal invocations bypass HTTP policies?
- Are defenses against SQLi, XSS, SSRF, malicious uploads, secret leaks, and DoS appropriate for the attack surface?
- Are there negative tests for anonymous access, wrong roles, cross-owner objects, and misconfiguration?
- Who is responsible for upgrading libraries, periodic security reviews, monitoring events, and incident response?

## 8. Key Takeaways

1. **Spring Security is a platform for enforcing authentication/authorization policies**, together with HTTP mechanisms when enabled and properly configured; the framework cannot guess business policies.
2. **Authentication != authorization != data ownership.** A valid login and valid role can still mean no access to a specific document.
3. **Defaults do not replace a threat model.** Configuration, dependencies, sessions/tokens, frontends, reverse proxies, and versions determine actual behavior.
4. **Defense in depth:** filters + service/repository policies + secure code + infrastructure + testing + operations.
5. Define a secure system by **verifiable rules and negative (denied-case) tests**, not by having declared a dependency.

## References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
