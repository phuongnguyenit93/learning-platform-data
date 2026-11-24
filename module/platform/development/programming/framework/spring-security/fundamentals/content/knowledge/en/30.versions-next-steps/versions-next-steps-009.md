# Distinguishing Stable Features, Version-Dependent Features, and Custom-Built Parts in Spring Security

> **Scope:** Spring Security for Java/Spring Boot applications, prioritizing **Servlet / Spring MVC**. This lesson shows how to distinguish what the framework already supports, what must be verified by version, and what belongs to application-owned policy and business logic. “Stable” here means **foundational models and capabilities you can rely on when designing**, not a promise that class names, methods, defaults, or detailed behaviors will never change across releases.

## 1. Why Classify Before Writing Code?

In a project, the statement “Spring Security supports login, JWT, authorization, and API protection” bundles several distinct layers of responsibility:

- Spring Security provides standard building blocks to **authenticate** requests, **enforce** authorization rules, and **integrate** several authentication/authorization protocols.
- How a component is enabled, DSL names, matchers, compatible Java/Spring Boot versions, or default values can **change by version**.
- Rules like “only the document owner can view it,” “lock an account after an investigation workflow,” or “one organization cannot view another organization's data” are **business decisions**. The framework only provides extension hooks for the application to enforce those decisions.

Separate three questions whenever you receive a requirement:

1. **Does the capability already exist?** For example, the framework already provides `PasswordEncoder`, HTTP Basic, form login, OAuth2 Resource Server, and method security.
2. **How is that capability used on the currently running versions?** For example, `authorizeRequests` vs. `authorizeHttpRequests`, which matchers are supported, and whether extra modules are needed.
3. **Who defines the data, policy, and workflow?** For example, document ownership, where users are stored, grant/revoke decisions, onboarding, and auditing.

When teams conflate these three questions, they either reinvent framework capabilities or mistakenly assume adding a starter gives them an entire product security workflow out of the box.

## 2. Three Categories to Make Explicit in Design

| Category | Signals | Examples in Spring Security | What to do |
| --- | --- | --- | --- |
| **A — Relatively stable foundation** | Core concepts/extension points documented across releases; applications design around them | `Authentication`, `SecurityContext`, authentication before authorization, Servlet `SecurityFilterChain`, `PasswordEncoder`, `authenticated`/`permitAll`/`hasAuthority` rules | Understand the mechanism, choose the right module, and test the policy rather than replacing well-supported features. |
| **B — Version- / integration-dependent** | API names, defaults, matchers, dependencies, config paths, or exact semantics vary by release/stack | `WebSecurityConfigurerAdapter` vs. `SecurityFilterChain` bean; `antMatchers` vs. `requestMatchers`; Ant/MVC/PathPattern matchers; Lambda DSL; Spring Boot 3 vs. 4 | Pin versions, consult **exact-version** docs, and use migration guides and regression tests. |
| **C — Product-owned custom or integrated parts** | Depends on specific users/tenants/data/workflows; the framework cannot infer the right policy | Account registration, role approval, resolving document owners, org rules, mapping IdP permissions, security notifications, custom audit events | Design models, use cases, storage, approval flows, and business tests; wire into framework extension points. |

**Note:** A single feature can span **multiple categories at once**. “Using JWT for an API” includes Resource Server token decoding/verification (A), configuring `issuer-uri`/`JwtDecoder` per version (B), and deciding token issuance, identity source, scopes/tenants, and revocation (C or an external IdP). Never slap a single label on the whole system.

### Typical Misconceptions

- **“Spring Security has `hasRole`, so it automatically knows who owns an invoice.”** False: the framework compares roles/authorities; it does not know invoice data or ownership relations.
- **“Having Resource Server means the API issues access tokens itself.”** False: a resource server **validates** tokens; an authorization server/IdP issues tokens under the configured flow.
- **“New versions only rename methods.”** False: matchers, filters, persistence, or defaults can change semantics; migrations require behavioral tests.
- **“Having login means having account lifecycle management.”** False: a login screen/flow does not automatically supply registration, email verification, customer support, privilege governance, or anti-fraud controls.

## 3. The Foundation: Core Principles Worth Mastering Thoroughly

### 3.1. Authentication Differs from Authorization

**Authentication** answers: *who does this request represent, and what is the proof?* For web apps, the framework builds `Authentication` after processing Basic, form login, OAuth2/OIDC, or Bearer tokens. `Authentication` carries the principal, authenticated state, and a set of `GrantedAuthority` instances.

**Authorization** answers: *is the authenticated principal allowed to perform this action on this resource?* The condition may be `hasRole("ADMIN")`, `hasAuthority("invoice:read")`, or a policy outcome queried by the application from a database.

Successful login does **not** grant access to all data. HTTP 401 typically indicates missing or unaccepted authentication; HTTP 403 typically indicates a forbidden request despite an established identity (subject to the specific entry point, flow type, and exception mapping).

### 3.2. Framework-Managed Servlet Path

```text
HTTP request
   ↓
Servlet container
   ↓
DelegatingFilterProxy → FilterChainProxy
   ↓  select first SecurityFilterChain matching request
Security filters: SecurityContext, CSRF/headers, authentication, authorization...
   ↓  if permitted
DispatcherServlet → Controller → Service → Repository
```

`SecurityFilterChain` selects which filters apply to a request. Inside the chain, `authorizeHttpRequests` defines HTTP rules. With multiple chains, only **the first matching chain** is selected; if no chain matches, Spring Security may leave that request unprotected. Always define clear chain scopes and an appropriate fallback.

The filter-chain model is foundational, yet **specific filter defaults and bean declarations still need version checks**. In WebFlux, the counterpart extension point is `SecurityWebFilterChain`; do not copy Servlet configuration over to Reactive.

### 3.3. SecurityContext and Request Scope

`SecurityContextHolder` gives Spring Security components access to the current `SecurityContext`. In standard Servlet apps, the default strategy uses `ThreadLocal`. Spring Security manages establishing and clearing the context in the filter chain.

That does **not** guarantee context propagates automatically to every thread, `@Async` call, queue, scheduler, or another service request. When crossing execution boundaries, design explicit identity propagation, validation, and cleanup rather than blindly copying `ThreadLocal`.

### 3.4. The Framework Enforces Rules; the Application Decides Policy

Commonly used rules:

- `permitAll()`: all matching requests proceed; requests still traverse the security filter chain.
- `authenticated()`: requires an authenticated identity.
- `hasRole("ADMIN")`: by default convention, requires authority `ROLE_ADMIN`.
- `hasAuthority("invoice:approve")`: matches an exact authority string.
- `denyAll()`: rejects the request.
- `access(AuthorizationManager)`: allows custom policy logic at the authorization point.

`@EnableMethodSecurity` paired with `@PreAuthorize` can protect logic on Spring bean methods. This is valuable when a service is invoked by multiple controllers or entry points, though remember proxy limitations: direct self-invocation from one method to another on the same bean may **bypass the interceptor**. Controls over sensitive resources must be enforced where data is read or modified, not merely by hiding UI buttons.

### 3.5. Built-In HTTP Protections Are Not “Automatic Absolute Safety”

Spring Security includes mechanisms for CSRF, security headers, session fixation protection, exception translation, and multiple authentication methods. However, enabling, disabling, or configuring each mechanism must fit the application.

For example, apps using session cookies and form login normally need CSRF protection on state-changing methods. A pure Bearer-token API may have a different threat model; CSRF decisions must rest on how browsers attach credentials, **not** merely on the word “REST”. CORS is a browser policy; enabling CORS does not replace authorization. HTTPS/TLS, secret protection, rate limiting, and infrastructure hardening also require clear ownership.

## 4. Things You Must Lock to Your Version Before Copying Code

There are two version layers to check: **Spring Boot → managed Spring Security/Spring Framework versions**, plus additional security dependencies. Do not drop Spring Security 7 documentation snippets into a project still running Spring Security 6 and expect it to compile.

| Topic | Version milestone / risk | How to verify |
| --- | --- | --- |
| Servlet config | `WebSecurityConfigurerAdapter` deprecated in 5.7 and removed in 6.0; `SecurityFilterChain` bean is the modern direction | Check imports and classes on the classpath; compile and run tests. |
| URL authorization | Legacy `authorizeRequests`/`antMatchers` replaced by `authorizeHttpRequests`/`requestMatchers` | Check rule ordering, actual requests, and 401/403/200 statuses. |
| Path matchers | 6.x has Ant/MVC/PathPattern choices depending on config; 7.x moves to `PathPatternRequestMatcher` and drops legacy Ant/MVC matchers | Test `/**`, servlet paths, encoded paths, trailing slashes, and HTTP methods. |
| DSL style | Lambda DSL existed since 5.x, preferred in 6.x, and mandatory in 7.x; legacy `.and()` chaining is no longer a compatible path | Migrate to `http.authorizeHttpRequests(auth -> ...)` and `Customizer.withDefaults()`. |
| Custom DSL | Legacy `HttpSecurity#apply` replaced by `.with(...)` for 7.x compatibility | Check the migration guide before changing custom configurers. |
| Runtime/framework | Spring Security 6.x aligns with Spring Framework 6 / Boot 3; 7.x aligns with Spring Framework 7 / Boot 4 | Inspect BOM/dependency tree, JDK, release notes, and migration guides. |
| OAuth2/OIDC/SAML, testing, method security | Capabilities exist in the framework but require matching artifacts, provider configuration, and versioned APIs | Check the version-pinned reference page for **Servlet or Reactive**. |

### Example of Converting a Rule

**Historical code — illustrates Spring Security 5.x syntax, do not use verbatim in 6/7:**

```java
// Fragment in legacy WebSecurityConfigurerAdapter's configure(HttpSecurity http)
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
    .and()
    .httpBasic();
```

**Modern code for Spring Security 6.x — fragment inside a `SecurityFilterChain` bean:**

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
return http.build();
```

Changing syntax **is not enough** to prove a sound migration: you must preserve the policy and test matcher ordering, authentication, permissions, and side behaviors such as CSRF and login redirects. In 7.x, re-verify every pattern against `PathPattern` semantics. The “specific first, general last” principle remains solid educational knowledge; the **exact matcher syntax** belongs to Category B.

### How to Inspect the Actual Running Dependencies

```bash
# Maven: inspect dependency versions after dependency management and transitive resolution
mvn dependency:tree -Dincludes=org.springframework.security

# Gradle (run inside the corresponding project/module)
./gradlew dependencies --configuration runtimeClasspath
```

In multi-module Gradle builds, inspect the configuration of the module that actually runs; never treat a version in a web snippet as the source of truth. Read release notes for Spring Boot, Spring Security, and related integrations before upgrading.

## 5. What Does Spring Security Support, and What Remains the Product's Job?

| Product requirement | What the framework/standards can provide | What the application/other teams must decide |
| --- | --- | --- |
| Username/password login | Authentication filters, `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, form login | Where users are stored; registration, email verification, password recovery, account lock states, and support workflows. |
| Protecting APIs with Bearer JWT | Resource Server, `JwtDecoder`, signature and claim validation per config, scope-to-authority conversion | Who issues tokens, valid issuer/audience, keys, rotation, lifetimes, revocation, user/tenant mapping, and data permissions. |
| Login via OIDC/OAuth2 | OAuth2 Client/`oauth2Login`, redirects and code exchange per provider config | Registering the app at the IdP, internal user mapping, account linking rules, offboarding, and duplicate-account handling. |
| Role/scope authorization | `hasRole`, `hasAuthority`, `AuthorizationManager`, method security | Lists of roles/permissions, who may grant them, project/tenant scope, and how roles relate to business operations. |
| “Only the owner can view a document” | `@PreAuthorize`/custom `AuthorizationManager` extension points | Schema storing owners, ownership logic, ownership transfer, admin exceptions, and protecting data from cross-access. |
| MFA/OTP/passkeys | Supporting components and flows depending on release/module; can integrate MFA-capable IdPs | Enrollment/recovery policies, which audiences require it, lost-device risk, user communication, and support. |
| Rate limiting/anti-bot | Can combine filters/gateways/IdPs/WAFs or other libraries | Limits per IP/user/tenant, algorithms, distributed state, 429 responses, dashboards, and operations. |
| Auditing and alerting | Security events, logging/integration hooks | Event payload fields, retention, alerts, log security, fraud analysis, and incident response workflows. |
| Multi-tenant authorization | Principal/authority context and extension points | Tenant isolation across repositories, DBs, caches, messages, queries, file storage, and cross-tenant tests. |

Not every Category C capability needs to be **written from scratch**. Prefer **integrating** a trusted Identity Provider, gateway, or library where suitable. Still, responsibility for verifying business policies, configuration, and end-to-end behavior remains with the system.

### Three Easily Confused OAuth2 Roles

```text
User ─► Client (web/mobile/app) ─► Authorization Server / IdP
                                           │ issues access token
                                           ▼
Client ─────── Bearer access token ───────► Resource Server (API)
                                           │ validates token/claims
                                           ▼
                                         Business service
                                           │ checks owner/tenant/policy
                                           ▼
                                          Data
```

- **OAuth2 Client/OIDC login**: handles interactive login and token acquisition per configuration; may rely on an external identity system.
- **OAuth2 Resource Server**: validates JWT/opaque bearer tokens to protect APIs. It does not become a token issuer just by adding a starter.
- **Authorization Server**: the component issuing tokens, either an external IdP service or a system built with appropriate authorization server capabilities. Token issuance, client registration, and lifecycle design still require dedicated decisions.

Even when the resource server verifies a JWT signature cleanly, the API must still check **audience, issuer, scopes/authorities, tenant, and per-record permissions** matching the threat model. A valid JWT does not implicitly grant read access to any customer's data.

## 6. Runnable Example: Framework Verifies Identity; Application Verifies Ownership

The small project below uses **Java 17+, Maven, and Spring Boot 3.3.0 (Spring Security 6.x)** to illustrate all three categories. This is a **fixed version for a learning example**; for real products, pick a supported branch and current security patches. The demo intentionally uses HTTP Basic and in-memory users to spotlight responsibility boundaries; never use demo account credentials in production.

Policy:

1. `GET /public/health` is publicly accessible (**Category A capability, Category B config**).
2. `GET /api/docs/{id}` requires authentication (**A/B**), then only the record owner may view it (**C**).
3. `GET /api/admin/stats` requires the `ADMIN` role (**A/B**); the returned stats payload is demo-only.
4. Demo user `alice` owns document 1, `bob` owns document 2; `admin` holds role `ADMIN` yet cannot automatically view someone else's document because the ownership policy does not permit it.

### 6.1. Structure

```text
spring-security-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/example/boundary/
    │   ├── BoundaryDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── ApiController.java
    └── test/java/example/boundary/
        └── SecurityBoundaryTest.java
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>spring-security-boundary-demo</artifactId>
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
```

`src/main/java/example/boundary/BoundaryDemoApplication.java`:

```java
package example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
```

`src/main/java/example/boundary/SecurityConfig.java`:

```java
package example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Classification:** `SecurityFilterChain`, `UserDetailsService`, `PasswordEncoder`, HTTP Basic, and `@EnableMethodSecurity` are framework-supported capabilities. The Lambda DSL syntax, `requestMatchers`, and bean setup are illustrated **for Spring Security 6.x**. The list of users, roles, and passwords is **demo data supplied by the application**, not users generated automatically by the framework for every product.

`src/main/java/example/boundary/DocumentPolicy.java`:

```java
package example.boundary;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Demo data: the application owns the ownership rule, not Spring Security.
    private final Map<Long, String> owners = Map.of(
        1L, "alice",
        2L, "bob"
    );

    public boolean canRead(String username, Long documentId) {
        return username != null && username.equals(owners.get(documentId));
    }
}
```

In real products, `owners` usually comes from a database and must be constrained by tenant, record state, delegation rights, and relevant transactions. Policy functions must rely on a **trusted identity from `Authentication`**, never on a `userId` parameter that clients can arbitrarily supply.

`src/main/java/example/boundary/DocumentService.java`:

```java
package example.boundary;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    // #p0 is the first parameter (documentId), independent of Java parameter names.
    @PreAuthorize("@documentPolicy.canRead(authentication.name, #p0)")
    public String read(Long documentId) {
        return "doc-" + documentId;
    }
}
```

`@PreAuthorize` is the enforcement hook provided by the framework; `documentPolicy.canRead` is **application-specific logic**. `DocumentService` is called from another controller through a Spring proxy so the method-security interceptor applies. Never move this check solely into UI code or trust a client sending “owner=true”.

`src/main/java/example/boundary/ApiController.java`:

```java
package example.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final DocumentService documents;

    public ApiController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/docs/{id}")
    public String readDocument(@PathVariable Long id) {
        return documents.read(id);
    }

    @GetMapping("/api/admin/stats")
    public String stats() {
        return "stats";
    }
}
```

### 6.2. Automated Testing at the Right Boundaries

`src/test/java/example/boundary/SecurityBoundaryTest.java`:

```java
package example.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void documentRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/docs/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/1").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc-1"));
    }

    @Test
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/docs/2").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/2").with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc-2"));
    }

    @Test
    void aliceCannotReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminStats() throws Exception {
        mvc.perform(get("/api/admin/stats").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("stats"));
    }

    @Test
    void adminStillCannotReadSomeoneElsesDocument() throws Exception {
        mvc.perform(get("/api/docs/1").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Run in the directory containing `pom.xml`:

```bash
java -version
mvn test
mvn spring-boot:run
```

With the exact code and dependencies above, the **expected outcome** of `mvn test` is **8 passing tests**. This is the expected outcome of the example, not a build log run in this environment.

Run the application and send requests from another terminal:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/docs/1
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/docs/1
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/docs/2
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/api/admin/stats
```

Expected output when the server uses default port 8080:

```text
200
401
200
403
200
```

On Windows PowerShell, use `curl.exe` and replace `/dev/null` with `NUL`. These commands illustrate GET only, so default CSRF does not block them. For POST/PUT/DELETE, check CSRF tokens whenever browsers can automatically send sessions/cookies.

### 6.3. Takeaways from the Example

| Observation | Who is responsible? | Test evidence |
| --- | --- | --- |
| Anonymous reaches public endpoint | Framework enforces `permitAll` per versioned configuration | `healthIsPublic`: 200 |
| Anonymous blocked on private API | Framework handles authentication and entry point | `documentRequiresAuthentication`: 401 |
| Lower-role user cannot access admin | Framework checks `ROLE_ADMIN` authority | `aliceCannotReadAdminStats`: 403 |
| Alice reads Alice's document | Application policy and method security work together | `aliceCanReadOwnDocument`: 200 |
| Alice cannot read Bob's document | **Application** defines ownership; framework blocks when policy returns false | `aliceCannotReadBobsDocument`: 403 |
| Admin does not automatically bypass owner | Product rule decides, not inferred from role name | `adminStillCannotReadSomeoneElsesDocument`: 403 |

If the business later allows ADMIN to view any document, the right place to change is the **policy** (plus tests), not changing `authenticated()` to `permitAll()` or writing a custom authentication filter.

## 7. Project-Level Classification Using Five Questions

Suppose the requirement is: **“Only users belonging to the same organization may download contracts, except internal auditors with special permission.”**

**Question 1 — Who is the principal and where does authentication proof come from?** Sessions, OAuth2 login, bearer JWTs, or mTLS? Which framework integration modules exist? If using an IdP, who operates and manages identities? This is **A + integration choice**.

**Question 2 — Which version set is the system running?** Spring Boot/Security/Java, Servlet or Reactive, which modules are included, and which APIs remain supported? This is **B**. Answer using `dependency:tree` or `dependencies`; never write “latest” in a design doc without pinning the version.

**Question 3 — What data does the policy depend on?** The `contract` table, `tenant_id`, `membership` relation, auditor role, contract status, and access expiration. This is **C**; Spring Security has no knowledge of product data.

**Question 4 — Where are enforcement points?** HTTP matchers to require login, method security to block service operations, tenant-scoped repository queries to prevent leaks; for downloads, check permissions **before** generating a presigned URL, streaming, or caching. This is **A + C**, written with **B** syntax.

**Question 5 — What evidence is sufficient for acceptance?** Tests for anonymous, same-tenant user, other-tenant user, auditor, revoked membership, tampered ID in URL, batch download, and background jobs. Include both **allow** and **deny** tests; re-run when upgrading versions or changing policies.

### Technique for Recording Decisions in Design Docs

For each capability, record explicitly:

```text
Requirement: view contract
Framework capability: HTTP authentication + method authorization
Version/stack: Spring Boot 3.3.x, Spring Security 6.3.x, Servlet
Identity source: chosen IdP or local UserDetailsService
Business privilege: same tenant with active membership,
                    or approved auditor role
Policy data source: application database (contract, membership, tenant)
Enforcement point: Service before retrieving/returning file
Evidence: 401, 403, 200 tests and cross-tenant access tests
Operations owner: team owning Identity + team owning Contract
```

The version/identity-source values in this template are **illustrative placeholders** and must be replaced with the real facts of your active project. Any undecided line is an open design gap that needs clarification; never assume the framework handles it automatically.

## 8. Upgrade Boundaries: Preserve Principles, Re-Test Behavior

Before upgrading Spring Security, split the backlog into two parts:

**What does not change in business intent:**

- Admin APIs are only for the ADMIN role.
- Users only view records they are authorized to view.
- Unauthenticated API calls must never return private data.
- Accounts with revoked permissions must stop operating per published policy.

**What must be tested because versions can change execution:**

- Do matchers still recognize URLs, path encoding, servlet prefixes, and HTTP methods properly?
- Do DSL and extension APIs still compile, and do custom filters remain in the right order?
- Do authentication exceptions translate to 401, 403, or redirects as clients expect?
- Do sessions, CSRF, cookies, CORS, and logout preserve required semantics?
- Are JWT validation, claim/authority mapping, OIDC redirect URIs, and provider config still compatible?
- Do method-security tests exercise proxies across every service call path?

### Three Migration Scenarios That Frequently Expose Gaps

1. **Switching `antMatchers` to `requestMatchers` without reviewing wildcards.** An old pattern may not have identical semantics in `PathPattern`; requests slip past rules or get blocked unexpectedly.
2. **Switching `web.ignoring` to `permitAll` or vice versa just to stop a 403.** `web.ignoring` removes requests from the Spring Security filter chain; `permitAll` keeps protective filters active. Evaluate effects on security headers, authentication, CSRF, and monitoring.
3. **Adding multiple chains while forgetting a fallback.** `securityMatcher("/api/**")` selects a chain only for APIs. URLs outside that pattern may have no protecting chain left if no other configuration covers them.

When upgrading 6.x to 7.x, cross-check the exact migration guides for Lambda DSL, `PathPatternRequestMatcher`, extension APIs, and default changes; never run a bulk method-renaming script and call it done.

## 9. Areas Where Responsibility Is Frequently Misattributed

1. **PasswordEncoder vs. password policy:** BCrypt/Argon2 and password matching are technical capabilities. Length rules, breached-password checks, resets, notifications, and account lifecycles belong to the product/IdP.
2. **JWT validation vs. data permissions:** a valid signature and timestamp do not mean the principal has access to document `id=99`. Validate audience, issuer, and policy against real data.
3. **Roles vs. tenants:** `ROLE_ADMIN` may mean administrator of one tenant, not global system admin. Model role scope explicitly and block cross-tenant access on the backend.
4. **CORS vs. authorization:** allowing an origin only controls browser cross-origin behavior under CORS; it is not proof the caller is authorized to read data.
5. **CSRF vs. authentication:** a successful login does not automatically make a POST valid while CSRF protection is enabled; disabling CSRF does not make an API secure.
6. **Logging vs. audit trail:** framework exception or access-denied logs do not automatically satisfy requirements for recording privilege changes, sensitive data access, or retention.
7. **MFA feature vs. MFA program:** a strong authentication factor is only one part of onboarding, recovery, enrollment, user support, and incident response.
8. **Controller protection vs. service protection:** if a service is invoked from batch jobs, queues, or scheduled tasks, HTTP checks on controllers do not guard every entry point. Enforce controls at the service layer and corresponding adapters.
9. **Framework features vs. Spring Boot auto-configuration:** adding a dependency may activate default behavior, yet once you declare custom security beans, the application must explicitly define rules and verify outcomes; do not assume auto-configuration remains intact.
10. **“Stable” vs. “never needs updating”:** Authentication/Authorization principles may be stable, yet unpatched older dependencies still carry risk. Keep tracking security advisories and release support windows.

## 10. Checklist Before Closing a Security Requirement

- [ ] Defined **inputs, principal, resource, action, and allow/deny outcomes**.
- [ ] Verified exact versions of Spring Boot, Spring Security, Java, Servlet/Reactive, and related dependencies.
- [ ] Identified which capabilities come from the framework, which integrate an IdP/gateway, and which require custom business code.
- [ ] Not confusing Resource Server with Authorization Server, or authentication with authorization.
- [ ] Owner/tenant/role/scope policies are enforced **server-side** using trusted data.
- [ ] Proper filter-chain config, fallback, matcher order, and deny-by-default policy where needed.
- [ ] Evaluated CSRF/session/CORS/HTTPS based on how the app actually handles credentials.
- [ ] Tests exist for 200/401/403, cross-resource access, and boundary cases.
- [ ] Re-test plan exists for version upgrades, especially matchers, custom extensions, and login flows.
- [ ] Clear owners recorded for identity data, policies, keys/tokens, auditing, and security operations.

## 11. Official Documentation for Self-Verification

- Spring Security — *Servlet Architecture*: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — *Servlet Authentication Architecture*: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 — *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — *OAuth2 roles: Resource Server, Client, Authorization Server*: https://docs.spring.io/spring-security/reference/servlet/oauth2/
- Spring Security — *OAuth2 Login*: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security — *CSRF*: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — *MockMvc testing*: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security 6.5 — *Migration to 7, Configuration*: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security 6.5 — *Migration to 7, Web*: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security — *Migration index*: https://docs.spring.io/spring-security/reference/migration/

**Expected learning outcome:** given a concrete security requirement, you can clearly articulate **which mechanism the framework enforces**, **which syntax/behavior must be pinned to a release**, and **which policies/data the product team must decide**, and then prove the design with tests for both permitted and denied paths.
