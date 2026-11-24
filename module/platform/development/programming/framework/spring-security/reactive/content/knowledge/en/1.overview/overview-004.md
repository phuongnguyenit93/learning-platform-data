# Identifying Users, Credentials, Roles, and Access Permissions

> **Context:** An overview of Spring Security in Spring WebFlux (reactive) applications. This lesson clearly distinguishes *who is calling*, *what proof they provide*, and *what they are allowed to do*, then applies those concepts using `SecurityWebFilterChain`, `Authentication`, and `GrantedAuthority`.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **identity/principal**, **credentials**, **authentication**, and **authorization** without conflating them.
- Distinguish a **role** from an **authority/permission**, and understand the `ROLE_` prefix convention in Spring Security.
- Describe how Spring Security WebFlux processes a request, stores the security context in Reactor `Context`, and decides whether to allow or deny access.
- Write and verify access policies using `ServerHttpSecurity`, `hasRole`, `hasAuthority`, and `authenticated`.
- Recognize places where object/data-level permission checks are required, even when the endpoint itself is already protected.

## 2. Four Concepts That Cannot Substitute for One Another

Suppose a reporting system has an account `lan`. Lan submits a username and password to view a report. The system must answer two independent questions: **Is Lan truly the person logging in?** and **Does Lan have permission to view this specific report?**

| Concept | Question | Examples | Meaning |
| --- | --- | --- | --- |
| Identity / principal | Who is the subject of the request? | User `lan`, service account `billing-service` | The entity identified after the system processes identification proof |
| Credentials | What proof does the subject present? | Password, HTTP Basic credentials, bearer token, OTP code, key/certificate | Data or factor used to prove identity; not synonymous with permissions |
| Authentication | Is the proof valid and bound to the subject? | Checking a hashed password; verifying a JWT's signature, expiration, and issuer | The process and result of verifying the subject |
| Authorization | What actions can the verified subject perform on which resources? | `report:read`, `ROLE_ADMIN`, allowed to read only reports from one's own department | The decision to allow or deny based on policy and context |

**Example:** Correct password → `authentication` succeeds; yet Lan lacks `report:delete` → the delete operation is still denied. Conversely, declaring `role=ADMIN` in a JSON request does not make the caller an administrator: permissions must come from a trusted source verified on the server side.

In real-world applications, identity can also be tied to a tenant, organization, account status, device, or login session. Two people with the same display name are not necessarily the same identity; with JWTs, `sub` should be interpreted in the context of the appropriate issuer (`iss`).

## 3. Spring Security Objects to Recognize

| Component | Practical role in WebFlux |
| --- | --- |
| `Authentication` | Represents the principal, credentials (if still present), `GrantedAuthority` collection, and authentication status; `getName()` typically returns the principal's name |
| `Principal` | Basic Java contract representing an identity; `Authentication` is also a `Principal` |
| `Authentication#getPrincipal()` | The principal object, which may be a `UserDetails`, `Jwt`, a string, or a custom type depending on the authentication mechanism |
| `UserDetails` | Account model commonly used in username/password authentication: username, encoded password, authorities, and account status flags |
| `ReactiveUserDetailsService` | Loads users in a non-blocking manner (`Mono<UserDetails>`); demo examples use the in-memory `MapReactiveUserDetailsService` |
| `ReactiveAuthenticationManager` | Verifies an `Authentication` reactively and returns the authentication result |
| `GrantedAuthority` | A permission represented as a string, such as `ROLE_ADMIN` or `report:read` |
| `SecurityContext` | Holds the current `Authentication` |
| `ReactiveSecurityContextHolder` | Accesses `SecurityContext` via Reactor `Context` in a reactive pipeline |
| `SecurityWebFilterChain` | Declares authentication mechanisms and policies for HTTP requests in WebFlux |

`Authentication#getCredentials()` **is not a place to read back a user's password**. After authentication, sensitive information may be erased from the object; applications should never log credentials, tokens, or the `Authorization` header.

### 3.1. How are roles and permissions represented?

Spring Security uses `GrantedAuthority` to represent permissions visible to the access control engine. **A role is a convention on top of an authority**, not a separate magical kind of permission.

| Granted in `Authentication` | Condition | Result |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Allowed |
| `ADMIN` | `hasRole("ADMIN")` | Does not match under the default `ROLE_` prefix |
| `report:read` | `hasAuthority("report:read")` | Allowed |
| `ROLE_ADMIN` | `hasAuthority("report:read")` | Not automatically allowed |

- `hasRole("ADMIN")` typically checks for the `ROLE_ADMIN` authority; passing `ADMIN` is the proper usage under the default convention.
- `hasAuthority("report:read")` checks for the exact granted string without adding any prefix.
- `User.withUsername(...).roles("ADMIN")` creates the `ROLE_ADMIN` authority; `authorities("report:read")` creates `report:read` verbatim.
- A user can hold multiple authorities. Whether the `ADMIN` role implies `report:read` is **an authorization rule designed by the system**; Spring Security does not automatically infer that implication.
- Role/permission names are an application convention; manage the permission set centrally and choose consistent names, e.g., `invoice:read`, `invoice:approve`.

**Three common policy layers:** check authenticated status (`authenticated`) → check role/action permission (`hasRole`, `hasAuthority`) → check data conditions such as owner, tenant, and record status. The first two layers do not automatically replace the last layer.

## 4. Processing Flow of an HTTP Request in Spring WebFlux

```text
HTTP request + credentials
    |
    v
Spring Security WebFilter chain
    |
    +--> Find and extract proof (Basic, bearer token, session...)
    |        |
    |        v
    |    Authenticate via appropriate mechanism
    |        |
    |        +-- failure / no valid authentication --> handle unauthenticated (typically HTTP 401 for Basic/Bearer APIs)
    |        |
    |        v
    |    Authentication + GrantedAuthority
    |        |
    v        v
SecurityContext in Reactor Context
    |
    v
Evaluate access rules (path/method/permission/conditions)
    |
    +-- deny authenticated subject --> typically HTTP 403
    |
    v
Controller -> Service -> permitted data -> response
```

The depiction above is a conceptual diagram; exact filters and entry points depend on configuration. `SecurityWebFilterChain` applies to WebFlux requests, while `SecurityFilterChain`/`HttpSecurity` are Servlet configuration: **do not mix the two APIs**.

In WebFlux, execution can switch threads. Spring Security binds the security context to Reactor `Context`, so do not rely on a plain `ThreadLocal` to identify the user at every point in the pipeline. Identity can be retrieved from `ServerWebExchange.getPrincipal()` or from `ReactiveSecurityContextHolder`.

### 4.1. How authentication differs from authorization at each step

1. **Extract proof:** e.g., Basic sends username/password or Bearer sends an access token.
2. **Authenticate:** compare encoded passwords via `PasswordEncoder`, or verify the token's signature and constraints; if valid, produce an authenticated `Authentication`.
3. **Attach permissions:** roles/permissions are fetched from an authoritative source (database, identity provider, controlled claim mapping...).
4. **Evaluate policy:** requests to `/api/reports` require `report:read`; requests to `/api/admin` require `ROLE_ADMIN`.
5. **Protect data:** after passing endpoint rules, the service still checks whether the caller is allowed to access **that specific report**.

Do not use `authentication.isAuthenticated()` as the sole check to infer a real user: Spring Security can create an anonymous authentication token. Use `authenticated()` in rules (or an appropriate mechanism that evaluates trust state).

## 5. Runnable Java 17+ Example: WebFlux + HTTP Basic + Authorization

The example uses Spring Boot **3.3.7** (Spring Security 6.x), Maven, and Java 17+. The goal is to clearly see the difference between identity, roles, and permissions. In-memory users and passwords are **for learning only**. All demo endpoints use HTTP GET, so CSRF does not need to be disabled to test.

Project structure:

```text
reactive-identity-demo/
├── pom.xml
└── src/main/java/demo/security/
    ├── ReactiveIdentityApplication.java
    ├── SecurityConfiguration.java
    └── DemoController.java
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-identity-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 5.2. `src/main/java/demo/security/ReactiveIdentityApplication.java`

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveIdentityApplication.class, args);
    }
}
```

### 5.3. `src/main/java/demo/security/SecurityConfiguration.java`

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasAuthority("report:read")
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reporter = User.withUsername("reporter")
            .password("{noop}reporter123")
            .authorities("report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reporter, admin);
    }
}
```

Explanation of each choice:

- `@EnableWebFluxSecurity` enables Spring Security WebFlux configuration. `SecurityWebFilterChain` defines the HTTP policy for this example.
- `permitAll()`: public endpoint, no login required. Security filters still operate on the request.
- `hasAuthority("report:read")`: only callers with the exact report-reading authority can access `/api/reports`.
- `hasRole("ADMIN")`: requires `ROLE_ADMIN`; `roles("ADMIN")` grants this authority to `admin`.
- `anyExchange().authenticated()`: remaining paths must be authenticated; placed last so it does not shadow the specific rules above.
- `httpBasic(...)` enables HTTP Basic; form login is disabled so the API does not redirect to an HTML login page.
- `{noop}` is a non-hashing password encoder: **acceptable only in demos**. Real applications must use a strong password encoder (e.g., BCrypt/Argon2 per policy) and store hashes, never plaintext passwords.
- `reporter` has `report:read` but not `ROLE_ADMIN`; `admin` has `ROLE_ADMIN` but **is not granted** `report:read`. This is an intentional choice to clearly demonstrate that a role does not automatically imply a permission.

### 5.4. `src/main/java/demo/security/DemoController.java`

```java
package demo.security;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public: OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports: OK");
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin: OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "hello, " + auth.getName());
    }
}
```

`/api/me` retrieves the principal's name from the `Authentication` inside the reactive security context, instead of guessing the user from a request parameter or using a custom `ThreadLocal`. `Mono` lets the result participate in the WebFlux pipeline; if the pipeline has no authenticated principal, the `authenticated()` rule already blocks the request before reaching this endpoint.

### 5.5. Run and verify

In the directory containing `pom.xml`, run:

```bash
mvn spring-boot:run
```

In another terminal, run sequentially:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u reporter:reporter123 http://localhost:8080/api/me
curl -i -u reporter:reporter123 http://localhost:8080/api/reports
curl -i -u reporter:reporter123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/reports
curl -i -u reporter:wrong http://localhost:8080/api/reports
```

Expected results (listing only **HTTP status and body**, without fixing headers or error message formats that depend on configuration):

| Request | Expected HTTP status | Body on successful request | Why |
| --- | --- | --- | --- |
| GET `/api/public` without credentials | 200 | `public: OK` | `permitAll` |
| GET `/api/me` without credentials | 401 | — | Unauthenticated, API uses HTTP Basic |
| GET `/api/me` as `reporter` | 200 | `hello, reporter` | Authenticated |
| GET `/api/reports` as `reporter` | 200 | `reports: OK` | Has `report:read` |
| GET `/api/admin` as `reporter` | 403 | — | Missing `ROLE_ADMIN` |
| GET `/api/admin` as `admin` | 200 | `admin: OK` | Has `ROLE_ADMIN` |
| GET `/api/reports` as `admin` | 403 | — | `ROLE_ADMIN` does not grant `report:read` automatically |
| GET `/api/reports` with wrong password | 401 | — | Authentication failed |

**401 and 403:** 401 indicates missing valid authentication (or unauthenticated) under the example policy; 403 indicates the subject was identified but lacks sufficient permissions. An application may customize response handling or hide resource existence; do not infer status codes merely from whether a button appears in the UI.

## 6. Authorization by URL, Method, and Data

### 6.1. HTTP authorization

`authorizeExchange` protects requests by method/path and authority. In a real system, you might add `pathMatchers(HttpMethod.POST, "/api/reports").hasAuthority("report:create")`, followed by rules for GET. Place specific rules before broad rules: if `anyExchange().authenticated()` comes first, subsequent policies no longer take effect as intended.

Do not assume `permitAll()` equals turning off all protections. The request still passes through the appropriate security chain, and other controls (such as headers or CSRF depending on application mechanisms) may still apply.

### 6.2. Method authorization in reactive services

HTTP rules are the outer gate; services can still be called from other flows. Spring Security WebFlux supports `@EnableReactiveMethodSecurity` and `@PreAuthorize` to protect methods on Spring-managed beans. The snippet below **illustrates the additional integration**, not a standalone program; it assumes the application has already configured Spring Security and granted `report:read` to the appropriate users:

```java
// In an application @Configuration:
@EnableReactiveMethodSecurity(useAuthorizationManager = true)

// On a method of a Spring-managed @Service:
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> readReportSummary() {
    return Mono.just("summary");
}
```

In the reactive model, protected methods should return a publisher type like `Mono`/`Flux` so Spring Security can access Reactor `Context`. Method security relies on Spring AOP proxies: internal calls from another method **within the same object** can bypass the interceptor; design calls to go through Spring-managed beans. Do not use Servlet's `@EnableMethodSecurity` instead of `@EnableReactiveMethodSecurity` in a WebFlux application.

### 6.3. Per-object permissions: preventing unauthorized access

Suppose `reporter` has `report:read` and sends `GET /api/reports/42`. Endpoint rules verify the **action type**; they do not prove that report 42 belongs to `reporter`'s tenant or department.

In the service layer, a sound flow is:

1. Retrieve the authenticated user ID/tenant ID from a trusted context (never trust a self-declared `X-User-Id` header from the client).
2. Query the resource by both ID **and** permitted scope, e.g., `findByIdAndTenantId(reportId, currentTenantId)`; or fetch and verify ownership before emitting data.
3. If outside scope, return an appropriate error (403 or 404 per security policy) without leaking content.
4. Re-verify for mutating actions (edit, delete, approve), even when the user is allowed to read.

This protects against **IDOR/BOLA** (unauthorized object access). Checking `ROLE_ADMIN` or `report:read` at the URL level alone will not solve record- or tenant-level authorization.

## 7. Username/Password, Sessions, and JWT: Different Authentication Sources

### Username/password and sessions

The server validates username/password using `ReactiveAuthenticationManager` or an appropriate integration with `ReactiveUserDetailsService` and `PasswordEncoder`. With session-based login, security state is typically tied to the session; cookie policies, session lifetime, logout, and CSRF are critical. With HTTP Basic, the client sends credentials on every request, so use it only over HTTPS and do not treat it as a default modern browser login solution.

### Bearer access token / JWT

With a resource server, the client sends `Authorization: Bearer <token>`. The application must configure appropriate token validation: trusted signature/keys, issuer, required audience, expiration, and other checks per policy. Once the token is valid, Spring Security builds `Authentication` and authorities from mapped claims.

- In Spring Security's common default JWT configuration, scope `report.read` may become authority `SCOPE_report.read`. This **differs** from `report:read` in the demo; to standardize, design a consistent mapping rule.
- A free-form `roles` claim in the token does **not automatically** become `ROLE_ADMIN`; an appropriate converter/mapping is needed, and claims should only be trusted from a verified issuer.
- A JWT with a valid signature does not mean every action is permitted: permissions and data scope must still be checked.
- Access tokens and refresh tokens serve different purposes; never send refresh tokens on regular resource API calls.

The demo in Section 5 uses HTTP Basic and in-memory accounts to clarify concepts; when switching to JWT/OAuth2, **do not simultaneously keep** the Basic configuration as a default unless there is an explicit business requirement.

## 8. Policy Design Process and Common Pitfalls

A testable approach to building policies:

1. **List resources/actions**: e.g., `report:read`, `report:export`, `report:approve`.
2. **Identify trusted identity sources**: identity provider, user store, service identity; verify account status and tenant if applicable.
3. **Define roles as application-granted permission sets**: `ANALYST` might include `report:read`; which permissions `ADMIN` holds must be explicitly decided.
4. **Set HTTP rules to the narrowest scope needed**; re-check in services for critical business operations.
5. **Test both allowed and denied cases**, including cross-tenant / wrong-owner scenarios.
6. **Monitor outcomes safely**: log the subject or correlation ID and high-level decision; never log passwords, raw tokens, session secrets, or unnecessary PII.

| Mistake | Impact | Fix |
| --- | --- | --- |
| Confusing `hasRole("ADMIN")` with authority `ADMIN` | Authorized users get 403, or policy grants wrong access | Check the `ROLE_` prefix and actual mapping |
| Granting `ROLE_ADMIN` expecting `report:read` automatically | Permission logic deviates from design | Map roles → authority sets explicitly |
| Only hiding buttons on the frontend | Clients can still call APIs directly | Enforce authorization on the backend |
| Trusting user ID/role/tenant from query, JSON, or self-declared headers | Privilege escalation | Obtain identity/permissions from verified authentication |
| Checking endpoint permissions only, ignoring record checks | IDOR/BOLA; exposing others' data | Check object ownership, tenant, and business state in service/repository |
| Using Servlet `SecurityFilterChain` or custom `ThreadLocal` for WebFlux | Wrong stack configuration, lost context in reactive pipeline | Use `SecurityWebFilterChain` and Reactor `Context` |
| Using `block()` to look up users in WebFlux handlers/services | Risk of blocking the event loop, degrading throughput | Chain `Mono`/`Flux` using `map`, `flatMap`... |
| Storing plaintext passwords or `{noop}` in production | Risk of credential exposure | Use a strong `PasswordEncoder` and HTTPS |
| Disabling CSRF unconditionally | Increases risk of forged actions under cookie/session auth | Evaluate the specific auth mechanism, browser behavior, and API nature before changing |
| Setting `anyExchange().permitAll()` or overly broad rules | Unintentionally exposing endpoints | Deny by default, open specific public paths intentionally |
| Treating 401 and 403 as the same error | Hard to debug and misleading client messages | Distinguish unauthenticated from authenticated with insufficient permissions |

## 9. Self-Check Scenarios

**Scenario A.** `Authentication` has `ROLE_ADMIN` and `report:read`. Are both `hasRole("ADMIN")` and `hasAuthority("report:read")` true?

**Answer:** Yes, because both required authority strings are present.

**Scenario B.** A user is authenticated and has `report:read`, yet requests a report belonging to another tenant. Should data be returned because `hasAuthority` passed?

**Answer:** No. Tenant or report ownership must be checked at the business/data layer.

**Scenario C.** A client sends `{"role":"ADMIN"}` in the body; the server has not authenticated the user. Can this body grant `ROLE_ADMIN`?

**Answer:** No. Authorities may only be granted from verified information/sources and server-side rules.

**Scenario D.** Why is reading `SecurityContext` via a custom `ThreadLocal` error-prone in a WebFlux application?

**Answer:** A reactive pipeline can switch threads and does not bind a request to a fixed thread; Spring Security reactive uses Reactor `Context`.

## 10. Key Takeaways

- **Identity** answers *who*, **credentials** provide proof, **authentication** verifies proof, and **authorization** decides *what can be done on which resources*.
- Roles in Spring Security are typically authorities prefixed with `ROLE_`; specific permissions can be authorities like `report:read`. There is no automatic implication unless explicitly granted.
- WebFlux uses `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`, and Reactor `Context`. Avoid copying Servlet mechanisms directly into reactive code.
- Endpoint protection is the first step; multi-tenant or ownership-based systems must enforce data-level permissions in services/repositories.
- Always test missing credentials, wrong credentials, sufficient permissions, insufficient permissions, and wrong-owner access.

**Official references:**

- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
