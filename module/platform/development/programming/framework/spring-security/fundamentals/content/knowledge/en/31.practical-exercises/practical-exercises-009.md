# Auditing a Sample Configuration for Over-Broad Permissions or Disabled Protections

## 1. Objectives of the Capstone Exercise

The learner's task is to **read a Spring Security configuration like a security reviewer**, spot overly broad permissions, inspect disabled protective layers, explain exploitable consequences, propose a safer configuration, and write automated tests proving that the fix enforces the policy.

The focus is **Spring Security for Servlet/Spring MVC**, Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x. Initialization and filter chain APIs may change when moving to Spring Boot 4/Spring Security 7; when targeting another version, consult its API docs and migration guide. The deliberately flawed configuration in the first part is **for analysis only** and must never be deployed. The final practical section provides a minimal secure application buildable with Maven and verifiable with MockMvc.

After this exercise, you will be able to:

- Distinguish **the scope of a `SecurityFilterChain`** from **authorization rules inside that chain**.
- Spot overly broad `permitAll` or matchers, wrong rule ordering, missing deny-by-default rules, and unintentionally exposed new endpoints.
- Evaluate context accurately when encountering `csrf.disable()`, `headers.disable()`, `sessionFixation().none()`, `web.ignoring()`, or a `securityMatcher` covering only part of the app.
- Avoid confusing CORS, CSRF, authentication, authorization, method security, and data ownership checks.
- Write negative tests: anonymous, wrong role, disallowed HTTP method, missing CSRF, unlisted resource, and unmatched filter chains.
- Report findings based on **evidence → risk → conditions → remediation → tests**, avoiding sweeping claims from a single config line taken out of context.

### Hypothetical application policy

An internal system named **Report Desk** has these URLs:

| URL / operation | Who is allowed? | Notes |
|---|---|---|
| `GET /` | Everyone | Landing page |
| `GET /login` and `POST /login` | Everyone | Browser form login; POST is CSRF-protected |
| `GET /api/public/info` | Everyone | Public information, no sensitive data |
| `GET /api/reports/summary` | `VIEWER` or `ADMIN` | View report summary |
| `POST /api/reports/export` | `ADMIN` | Request report export, with CSRF token when using cookies/sessions |
| `GET /api/admin/users` | `ADMIN` | User administration |
| `GET /api/account/me` | Anyone **authenticated** | View own account info |
| Any other route, including unreviewed new routes | Deny | Deny-all by default; open only via explicit rule |

This is the **authorization contract** for the exercise. If a similar contract is missing in a real project, consult the product/security owner before deciding between `permitAll` and `hasRole`. A sound audit cannot infer business intent from endpoint names alone.

## 2. Reading Spring Security Accurately Before Hunting Bugs

In Spring Security Servlet, `FilterChainProxy` selects the **first matching `SecurityFilterChain`** for a request. Each chain has a **chain-level matcher**; by default a chain built from `HttpSecurity` matches all requests, whereas calling `securityMatcher(...)` narrows that scope. **If no chain matches, the request bypasses Spring Security protection.** When multiple chains exist, you must analyze `@Order` and the fallback—you cannot inspect a single bean in isolation and draw conclusions.

**Inside the selected chain**, `authorizeHttpRequests` checks `requestMatchers` in declaration order; **the first matching rule decides access**. `anyRequest()` applies only to requests that entered that chain, not as an application-wide fallback if the chain is scoped by `securityMatcher`.

```text
HTTP Request
   |
   v
FilterChainProxy
   |
   +-- SecurityFilterChain @Order(1), securityMatcher("/api/**") ?
   |      | yes
   |      v
   |    CSRF/Auth filters -> authorizeHttpRequests (first matching rule)
   |
   +-- SecurityFilterChain @Order(2), catch-all ?
   |      | yes
   |      v
   |    CSRF/Auth filters -> authorizeHttpRequests
   |
   +-- No chain matches
          |
          v
      BYPASSES Spring Security protection
```

Distinguish keywords that are frequently misunderstood:

| Configuration | Actual meaning | Review question |
|---|---|---|
| `requestMatchers("/x/**").permitAll()` | Allows matching requests without authorization | Is this genuinely public? Could the pattern capture sensitive routes too? |
| `requestMatchers("/x/**").authenticated()` | Requires an authenticated identity | Are roles, permissions, or tenant/owner checks also needed? |
| `requestMatchers("/x/**").hasRole("ADMIN")` | Requires `ROLE_ADMIN` authority (by default) | Is the rule shadowed by an earlier one? Are authority sources trusted? |
| `anyRequest().permitAll()` | Opens every remaining route **within the chain** | Are internal paths or future routes exposed? |
| `anyRequest().authenticated()` | Lets any logged-in user through | Is that tight enough for admin actions, or should it be deny-by-default? |
| `anyRequest().denyAll()` | Denies any request not matched earlier | Does it help catch newly added undeclared endpoints? |
| `securityMatcher("/api/**")` | Sets the scope for the **entire chain** | Do routes outside `/api/**` have a catch-all chain? |
| `web.ignoring().requestMatchers(...)` | Skips Spring Security filters for those paths | Does it unintentionally drop headers, SecurityContext/CSRF, or security logging? |
| `csrf.disable()` | Disables CSRF in the chain | Does the chain receive browser requests with auto-attached cookies/Basic creds? |
| `headers.disable()` | Disables Spring Security's default response header writers | Does an edge/proxy replace them completely? Verified on real HTTP responses? |

**Do not apply a blanket rule that "every `permitAll` is a bug."** Minimal health endpoints and static assets may legitimately be public. What matters is **matcher breadth, ordering, and the authorization contract of the actual data**.

## 3. Deliberately Insecure Sample: Find the Issues Before Reading the Solution

Assume this is the **only `SecurityFilterChain`** in the application. The illustrative code compiles inside a Spring Security 6.5 project; it was written for an audit exercise and **must never run with real data**.

```java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class VulnerableSecurityConfiguration {

    @Bean
    SecurityFilterChain unsafeChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")                  // A
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").permitAll() // B
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")                   // C
                .anyRequest().authenticated()          // D
            )
            .csrf(AbstractHttpConfigurer::disable)     // E
            .headers(AbstractHttpConfigurer::disable)  // F
            .sessionManagement(sessions -> sessions
                .sessionFixation(fixation -> fixation.none()) // G
            )
            .formLogin(withDefaults())                 // H
            .httpBasic(withDefaults())
            .build();
    }
}
```

**Questions before checking the answers:**

1. Which chain handles an anonymous `GET /api/admin/users` request? Does rule B or rule C decide permission?
2. Do `GET /dashboard` or `GET /admin` outside `/api/**` pass through any `SecurityFilterChain`?
3. Does `anyRequest().authenticated()` at D "rescue" rule B? Does it protect paths outside `/api/**`?
4. Is disabling CSRF at E guaranteed to be a vulnerability in every API? What more must you know about credentials and browser usage?
5. Which protective headers are lost by disabling headers at F? Does Spring Security add CSP by default?
6. What does G do if the app uses sessions? Does H actually serve the `POST /login` endpoint inside a chain that matches only `/api/**`?
7. If a patch merely swaps B and C while keeping A and E/F/G, does it satisfy the section 1 policy?
8. Which **negative tests** would you write to prove the attack paths are closed?

## 4. Audit Answers: Evidence, Impact, and Fixes

### R1. `requestMatchers("/api/**").permitAll()` grants overly broad access

Inside the selected chain, rule B matches **every URL under `/api/**`**, including `/api/admin/users`, `/api/reports/export`, and `/api/account/me`. Once rule B returns permit, rules C and D are never evaluated. `hasRole("ADMIN")` on the next line looks strict yet is completely shadowed by rule B.

**Impact:** anonymous requests pass HTTP authorization into sensitive handlers. An endpoint might still enforce service-layer checks, so inspect controllers, services, and other chains before declaring data leaked; nonetheless, the HTTP policy layer clearly violates the contract.

**Fix:** permit strictly `GET /api/public/info`, place admin and report rules before the fallback, and avoid `/api/**.permitAll()`. **Test:** anonymous reading `/api/admin/users` must be blocked; a VIEWER user GETting admin must receive 403; only ADMIN succeeds.

### R2. Misordered matchers shadow stricter rules

In Spring Security, authorization matchers are ordered; a path matching both `/api/**` and `/api/admin/**` obeys whichever rule comes first. Putting specific rules before broad rules fixes part of the issue, yet an overly broad `permitAll` lower down still exposes other endpoints.

**Fix:** build a matrix by method + path + role; permit only the approved public endpoints; end with `anyRequest().denyAll()` when the product model requires a strict allowlist. **Test:** a newly added route lacking an explicit rule must be denied, even for an ADMIN user.

### R3. `securityMatcher("/api/**")` leaves all other paths unprotected

This is the **only chain** in the example. Consequently `GET /dashboard`, `GET /internal/maintenance`, and `GET /admin` do not match the chain's matcher and **bypass Spring Security completely**. If a real app defines a second catch-all chain afterward, the conclusion changes; you must audit every `SecurityFilterChain` and `@Order` together.

**Fix:** for small apps, use a single catch-all chain **without calling `securityMatcher`**. With multiple independent API/web chains, place specific chains first and a catch-all chain last; write tests for each group and out-of-scope paths. **Test:** calling an unexpected path like `/internal/maintenance` must be blocked per the contract.

### R4. `csrf.disable()` removes a context-dependent defense

For web apps using **session cookies** or browser-attached ambient credentials, disabling CSRF on POST/PUT/PATCH/DELETE allows unintended state-changing requests. In the example, `formLogin` is enabled (even if outside the chain's scope) and report endpoints have POST operations—a clear sign that CSRF must be seriously reviewed.

**Do not jump to the conclusion** that every stateless bearer-token API needs CSRF tokens: an API accepting only `Authorization: Bearer ...` headers explicitly set by non-cookie clients has a different CSRF threat model. Mixed APIs can split filter chains or use narrow CSRF matchers, verified by actual testing. **Fix in this cookie/form-login lab:** keep CSRF enabled. **Test:** ADMIN POST `/api/reports/export` without a token must return 403; with a valid token it returns 200.

### R5. `headers.disable()` turns off defensive response headers

Spring Security Servlet writes useful default headers such as `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and cache-control headers; `Strict-Transport-Security` is normally added for HTTPS responses. Disabling `headers` turns off Spring Security's default header writers. Even for public static files, `web.ignoring()` skips security filters altogether and is generally less safe than `permitAll`.

**Do not claim** CSP or Referrer-Policy is enabled out of the box: CSP is **not a default Spring Security header** and must be designed specifically for the app. Proxies/CDNs may add headers too, so base conclusions on the **final HTTP response**. **Fix:** keep default headers enabled and add policies like CSP after evaluating UX/browser impact. **Test:** assert `nosniff`, frame options, and cache-control on responses; verify HSTS over HTTPS rather than expecting it on localhost HTTP.

### R6. `sessionFixation().none()` disables session ID rotation at login

With **HTTP-session-based login**, rotating the session ID on successful authentication defends against session fixation. Modern Servlet Spring Security uses an appropriate strategy by default; setting `none()` is a red flag. If a chain were truly stateless without session logins, this item would not represent a live vulnerability.

**Fix:** remove the weak setting or configure `sessionFixation(f -> f.changeSessionId())` when using session login. **Test:** create an anonymous session ID A, log in, verify new ID B differs from A; after logout, neither A nor B can access protected data. Never claim rotating the ID mitigates XSS or post-login cookie theft.

### R7. `formLogin` fails to serve login endpoints due to chain scope

In the sample, the chain selects only `/api/**`, yet `formLogin(withDefaults())` defaults its login page and login processing URL to `/login`. Because `/login` **never enters the chain**, the filters rendering the form and handling `POST /login` never run for those requests; the config looks like it has form login while its endpoints sit outside the chain. This usually breaks functionality, and combined with unprotected routes elsewhere makes things worse.

**Fix:** place form login in a catch-all web chain, or widen the matcher to cover auth endpoints alongside a fallback chain. **Test:** `GET /login` renders the form and `POST /login` succeeds with a CSRF token, while unauthenticated users cannot read protected data.

### R8. `anyRequest().authenticated()` requires only being logged in

Even after removing rule B, `authenticated()` is insufficient for admin actions, data exports, order approvals, permission edits, or accessing another tenant's resources. Any valid low-privilege user could still call a path missing a stricter rule.

**Fix:** enforce `hasRole`/`hasAuthority` for sensitive route groups and **method-level/ownership checks** in services. For `/api/reports/{id}`, general permission to view reports **does not prove** that report ID belongs to the caller's tenant. **Test:** a tenant A user reading an `id` owned by tenant B must be denied even with the same role.

### R9. Missing `@EnableMethodSecurity` and service-layer rules

`@PreAuthorize` on methods runs only when method security is enabled and calls go through a Spring proxy. Not seeing `@EnableMethodSecurity` in one file does not alone prove it is missing everywhere (it might live in another config class). Still, when policy requires enforcing rules on service use cases, verify annotations actually run at runtime.

**Fix:** enable `@EnableMethodSecurity` when using `@PreAuthorize`, invoke services via Spring beans, and test both controllers **and** services. **Test:** a VIEWER user cannot invoke the ADMIN export service method via an alternate entry point.

### Remediation priority summary

| ID | Evidence in sample | Assumed priority | Verification condition |
|---|---|---|---|
| R1/R2 | B before C: `/api/**` public | Very high | Sensitive endpoints have handlers and no secondary guard |
| R3 | Only `/api/**` chain exists | Very high | No catch-all chain exists |
| R4 | `csrf.disable()` | High in web sessions | Browsers auto-send cookies/creds to state-changing endpoints |
| R5 | `headers.disable()` | High/Medium | Headers are not fully supplied by a proxy |
| R6 | `sessionFixation().none()` | High if session login | Login uses HTTP sessions and keeps the same ID |
| R7 | Login filter outside chain | Medium/High | No other chain serves `/login` |
| R8 | Fallback only `authenticated()` | High | Unlisted sensitive routes exist |
| R9 | Method security unverified | Business-dependent | Service requires checks and annotations aren't active |

Priorities in this table reflect **scenario-based review priority**; real severity depends on data sensitivity, exploitability, compensating controls, and public vs. intranet exposure. Avoid rating every `csrf.disable` as critical before checking how authentication works.

## 5. Fixed Version: Testable Java 17 Application

To focus on **policy verification**, this lab uses Spring MVC with default form login **and HTTP Basic for API tests**. Production usually selects the authentication model matching each client type; enabling both here is strictly for clear observation and testing. Since the app supports session/cookie login, CSRF remains enabled on POST.

Structure:

```text
security-audit-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/audit/
    │   ├── SecurityAuditApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── DemoController.java
    │   └── ReportService.java
    └── test/java/com/example/audit/
        └── SecurityPolicyTest.java
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-audit-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

### 5.2. `SecurityAuditApplication.java`

```java
package com.example.audit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityAuditApplication.class, args);
    }
}
```

### 5.3. `SecurityConfiguration.java`: explicit rules and deny-by-default

```java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        return http
            // No securityMatcher: the default chain covers the whole app.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/info")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyRole("VIEWER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/account/**")
                    .authenticated()
                // New paths/unexpected methods must be approved before opening.
                .anyRequest().denyAll()
            )
            .formLogin(withDefaults())
            .httpBasic(withDefaults())
            .csrf(withDefaults())
            .headers(withDefaults())
            .sessionManagement(sessions -> sessions
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-123"))
            .roles("VIEWER")
            .build();
        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-123"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }
}
```

**Why this is an improvement:**

1. One default `SecurityFilterChain` captures every request; there is no gap from `securityMatcher("/api/**")`.
2. `GET /api/public/info` is public **for that exact method and path**; a `POST` to the same path is not permitted.
3. `/api/admin/**` is guarded by `ROLE_ADMIN` right at request authorization; reports allow only their designated roles.
4. The `denyAll` fallback is intentionally strict: adding a business route forces updating the policy and tests, preventing "accidentally exposed new endpoints."
5. CSRF and security headers remain active; form login on `/login` sits inside the chain. Session fixation protection is explicitly configured for web sessions.
6. `@EnableMethodSecurity` ensures service-layer policies run when invoked through Spring-managed beans.

**Why include `/login` before `denyAll`?** Default form login requires the login endpoints for unauthenticated callers; if the `denyAll` fallback blocked them, login itself would break. Permitting login endpoints does not weaken CSRF: a POST without a token is still rejected by `CsrfFilter`. When using a custom login page, ensure its static assets and endpoints are properly permitted.

**Production warning:** Demo passwords in source code are strictly for learning. In real systems, use a trusted account store (DB/LDAP/OIDC), adaptive password hashing, reset/MFA/rate-limit controls, secret management, and dedicated account/tenant policies. Never copy demo users to production.

### 5.4. `DemoController.java`: handlers with testable outcomes

```java
package com.example.audit;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final ReportService reports;

    public DemoController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/")
    public String index() {
        return "REPORT_DESK_PUBLIC";
    }

    @GetMapping("/api/public/info")
    public String publicInfo() {
        return "PUBLIC_INFO";
    }

    @GetMapping("/api/reports/summary")
    public String reportSummary() {
        return "REPORT_SUMMARY";
    }

    @PostMapping("/api/reports/export")
    public String exportReport() {
        return reports.export();
    }

    @GetMapping("/api/admin/users")
    public String listUsers() {
        return "ADMIN_USERS";
    }

    @GetMapping("/api/account/me")
    public String profile(Authentication authentication) {
        return "HELLO_" + authentication.getName();
    }

    @GetMapping("/api/unlisted")
    public String unlisted() {
        return "SHOULD_NOT_BE_VISIBLE";
    }
}
```

`/api/unlisted` **deliberately has a controller method without an allow rule**. It acts as a "canary route": if someone changes `anyRequest().denyAll()` to `permitAll()`, the test immediately catches that the policy was opened. In real applications, use full route coverage and authorization tests rather than relying on a single canary.

### 5.5. `ReportService.java`: adding use-case protection

```java
package com.example.audit;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String export() {
        // Returns demo string; no actual data export performed.
        return "EXPORT_REQUESTED";
    }
}
```

`@PreAuthorize` checks before entering the method **when invoked through a Spring-managed proxy**. HTTP rules and method rules complement each other: a service method may be called by a message handler, scheduler, another controller, or service orchestration; URL protection alone may not suffice. Never rely solely on annotations for internal `this.export()` calls inside the same object because self-invocation can bypass the proxy. For **ownership/tenant** rules, add checks against real data rather than assuming equal roles mean shared access.

### 5.6. `SecurityPolicyTest.java`: proving policy with real requests through filters

```java
package com.example.audit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPolicyTest {

    @Autowired MockMvc mvc;
    @Autowired ReportService reports;

    @Test
    void publicRouteIsReadableAndSecurityHeadersRemain() throws Exception {
        mvc.perform(get("/api/public/info"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_INFO"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"));
    }

    @Test
    void aViewerCannotUseAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(httpBasic("viewer", "viewer-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anAdminCanUseAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_USERS"));
    }

    @Test
    void aViewerCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("viewer", "viewer-demo-123")))
            .andExpect(status().isOk());
    }

    @Test
    void postExportRequiresCsrfAndAdminRole() throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isForbidden()); // missing CSRF token

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("viewer", "viewer-demo-123"))
                .with(csrf()))
            .andExpect(status().isForbidden()); // valid CSRF, missing role

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin-demo-123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("EXPORT_REQUESTED"));
    }

    @Test
    void anUnlistedEndpointStaysForbiddenEvenForAdmin() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "admin-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void serviceGuardAlsoRejectsViewer() {
        assertThrows(AccessDeniedException.class, () -> reports.export());
    }
}
```

Each test above verifies **observable behavior**, not merely grepping source for `hasRole`. `httpBasic` supplies credentials through the real filter; `csrf()` generates a valid CSRF token to pass `CsrfFilter`; `@WithMockUser` is used specifically for the **method security** test and **does not replace** real password authentication tests.

When an app enables default form login alongside HTTP Basic, the response to an **anonymous request** may be a login redirect (302) or 401 depending on entry points and the `Accept` header. Therefore the required tests above focus on **403 for authenticated users lacking roles**, **403 for missing CSRF**, and **200 for authorized access**. If you want to assert 401 for anonymous APIs, configure and test the specific `AuthenticationEntryPoint`; never assume every app returns the same status.

**Running the code** once all 5 Java files and `pom.xml` are in place:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

After the server starts on `http://localhost:8080`, quick checks:

```bash
curl -i http://localhost:8080/api/public/info
curl -i -u viewer:viewer-demo-123 http://localhost:8080/api/admin/users
curl -i -u admin:admin-demo-123 http://localhost:8080/api/admin/users
curl -i -u viewer:viewer-demo-123 http://localhost:8080/api/reports/summary
```

Expected responses respectively: **200 PUBLIC_INFO**; **403** because VIEWER lacks admin permission; **200 ADMIN_USERS**; **200 REPORT_SUMMARY**. Do not use these curl commands to prove CSRF: a valid POST requires a CSRF token paired with its session state, so use MockMvc's `.with(csrf())` or obtain a token from the form/browser session.

**Limits of the fixture:** this code is a learning fixture. Learners can copy it into a Maven project and run the tests; this article does not claim to have executed Maven or proved identical APIs across out-of-scope versions.

## 6. Auditing Any Configuration Step by Step

### Step 1 — Write down the permission contract from the product's perspective

Do not start by blindly replacing `permitAll` with `authenticated`. For each endpoint, document at least:

- Method, path, auth mechanism (session, Basic, bearer token, OIDC), public vs. private.
- Principal type, authority/role, owner/tenant rules, account status requirements.
- Does it mutate data, log out, alter permissions, or accept sensitive inputs?
- Is it called directly by browsers with cookies, or strictly by machine-to-machine clients?
- Are equivalent endpoints exposed via Actuator, management ports, other servlets, or proxy routes?
- Are there static assets, login pages, error dispatches, CORS preflights, or webhooks needing special handling?

The output is a **method × path × persona × expected decision** table serving as the test oracle. Clearly distinguish `permitAll` for public resources from `authenticated` for personal pages, and `hasRole`/`hasAuthority`/custom authorization for sensitive data.

### Step 2 — List every filter chain and its scope

Inspect **all** `@Bean SecurityFilterChain` definitions, `@Order` values, `securityMatcher`s, `WebSecurityCustomizer`s, servlet paths, context paths, management/actuator configurations, and reverse proxies. A `/api/**` matcher can be safe when backed by a catch-all chain; without a catch-all, routes fall outside what developers assumed "Spring blocks by default."

Note: `anyRequest().denyAll()` inside a narrow chain **cannot compensate** for paths outside that chain. When multiple `DispatcherServlet`s, servlet paths, or URL rewrites exist, verify which **normalized request path** matchers actually evaluate on your exact stack/framework version. Never guess that a wildcard matches identically across all servlet contexts.

### Step 3 — Hunt for overly broad permissions and shadowed rules

Scan rules top to bottom:

- `"/**".permitAll()`, `"/api/**".permitAll()`, `anyRequest().permitAll()`.
- `authenticated()` on admin/write/approval/finance routes—does it need an explicit authority?
- Is `"/admin/**".hasRole("ADMIN")` placed **after** a broader matching rule?
- Are rules scoped by `HttpMethod`, or does permitting GET inadvertently permit POST/DELETE?
- Do matchers align with real endpoints, servlet paths, trailing slashes, and URL-encoded paths?
- Is there an explicit fallback policy for newly added unreviewed URLs?

Never treat finding the text `permitAll` alone as proof of a bug. Compute **which matcher actually wins** and test concrete requests.

### Step 4 — Inspect disabled or reconfigured defenses

| Signal | What to investigate | Guidance |
|---|---|---|
| `csrf(AbstractHttpConfigurer::disable)` | Browser cookies/sessions? Basic credentials? State-changing endpoints? | Keep CSRF for web sessions; allow narrow exceptions only with evidence |
| `headers(AbstractHttpConfigurer::disable)` | Which final response headers are sent by app/proxy? | Keep default headers; add app-specific CSP/Referrer-Policy |
| `sessionFixation(...none())` | Is session-based form login used? | Keep `changeSessionId`/`migrateSession` as appropriate |
| `securityMatcher(...)` missing fallback | Are other routes covered by a chain? | Add a catch-all chain or drop `securityMatcher` if single-chain |
| `web.ignoring().requestMatchers(...)` | Do requests bypass header writers/filters? | Prefer `permitAll` inside the filter chain |
| `httpBasic(withDefaults())` | Is Basic exposed to internet endpoints unnecessarily? | Enable only approved schemes and enforce TLS |
| `cors(...)` opening origins | Cookie credentials combined with untrusted origins? | Restrict origins/methods/headers and verify real CORS responses |
| `sessionCreationPolicy(STATELESS)` | Does the app expect form login/sessions? | Match session model or clearly separate stateless bearer APIs |
| `@EnableMethodSecurity` missing | Is `@PreAuthorize` expected to enforce rules? | Enable it and test services via Spring beans |
| `/actuator/**` `permitAll` | Which management endpoints are exposed? | Expose only required liveness probes; isolate management security config |

**CSRF and CORS are two separate problems**. CORS restricts cross-origin browser reads per server policy; CORS never provides authorization and never replaces CSRF tokens. Conversely, disabling CSRF on a stateless bearer-token API can be sound once verified that no browser-auto-attached credentials are accepted.

### Step 5 — Verify defense in depth beyond URLs

HTTP rules do not replace:

- **Object-level authorization:** a tenant A user requesting `/api/reports/42` belonging to tenant B. Enforce checks against the target record, owner/tenant/ACL—not merely the role to view reports.
- **Field-level authorization:** a user may view a report but not salary/PII fields; serializers/queries must not leak restricted fields.
- **Method security:** `@PreAuthorize`/`@PostAuthorize` or service authorization components must execute along real call paths.
- **Authentication trust:** roles/scopes must come from trusted sources—never trust `role`/`tenantId` fields sent unverified by the client.
- **Token validation:** in JWT resource servers, validate signatures, issuer, expiry, and audience; never equate "decodable JWT" with "valid authentication."
- **Operational controls:** TLS, cookie protections, lockout/rate limits, session expiry/revocation, and safe audit logging.

An API returning 403 on one route might still expose the data via another route, GraphQL endpoint, or export pathway. Audits must trace **data flows**, not a single regex.

### Step 6 — Write matching positive and negative tests

Use a minimal persona set:

| Persona | Test objective |
|---|---|
| Anonymous | Public GET allowed; private/admin blocked |
| VIEWER | Reads summary; cannot export or administer |
| ADMIN | Allowed administration and export on matching HTTP methods |
| Authenticated without right role | Does not inherit permission through fallbacks |
| Cross-tenant user | Cross-tenant data is rejected |
| Request missing CSRF | Cookie/session POST is blocked |
| Request to unlisted URL | Fails closed, even for admin users |

Verify both **status** and **response body**. If a denial happened because no controller matched the method rather than security policy, a `404`/`405` does not prove authorization works; create a real handler and prove filters block before reaching it. Likewise, `403` from missing CSRF does not prove admin role rules work—always test a **request with a valid CSRF token and insufficient role**.

### Step 7 — Document findings and re-verify

A concise review finding can follow this structure:

```text
ID: SEC-01
Path/method: GET /api/admin/users
Contract: ROLE_ADMIN only
Evidence: /api/**.permitAll() precedes /api/admin/**.hasRole("ADMIN")
Risk: HTTP authorization lets anonymous through; actual impact
      also depends on service policies and handler response data
Severity: High assuming no compensating guard
Fix: specific rules and deny-by-default; avoid wildcard permits
Tests:
  - anonymous is blocked
  - VIEWER receives 403
  - ADMIN receives 200
  - /api/unlisted remains blocked
Post-fix result: MockMvc and HTTP trace evidence attached
```

Never include real passwords, cookies, access tokens, session IDs, or real user records in issues/logs. For production, plan rollout and impact checks: a new `denyAll` can break a legitimate endpoint if the contract was incomplete. That is why building the matrix and running integration tests **before** deploying matters.

## 7. Distinguishing False Positives from Real Bugs

### Case A — `permitAll` can be legitimate

`GET /actuator/health/liveness` for a load balancer may legitimately be public per infrastructure policy, whereas `/actuator/env`, `/actuator/heapdump`, or admin endpoints must stay closed. The bug is `"/actuator/**".permitAll()` without per-endpoint evaluation—not having a public liveness probe.

### Case B — Disabling CSRF can be legitimate on a bearer API chain

A chain accepting only tokens in `Authorization` explicitly attached by non-browser clients, strictly stateless with no cookie/Basic auth, has a different threat model from web sessions. Disabling CSRF **strictly on that API chain** can be valid once verified. If an SPA uses cookies to call that API, re-evaluate. **Base the decision on how credentials actually travel**, not on whether the URL path contains `api`.

### Case C — `authenticated()` is not always overly broad

`GET /api/account/me` returning data for **only the current principal** without accepting an arbitrary ID can be reasonable with `authenticated()`. By contrast, `GET /api/account/{id}` letting the client pick an ID needs ownership/role policies; conclusions depend on the use case.

### Case D — `headers.disable()` might be compensated at the gateway, but must be proven

If an ingress/gateway enforces equivalent headers and final-response tests confirm them, app-only risk differs from a public app with no proxy. Even then, disabling them in the app shifts enforcement onto deployment infrastructure; establish ownership and drift tests. Remember Spring Security **does not add CSP automatically** even with default headers enabled.

### Case E — Multiple filter chains are not inherently a bug

An `@Order(1)` chain for `/api/**` followed by a catch-all chain is a valid architecture. The mistake is reviewing only the API chain or only the fallback without checking chain selection; putting `anyRequest().denyAll()` in a wrongly scoped chain leaves everything outside it unprotected.

## 8. Post-Audit Acceptance Checklist

- [ ] Reviewed every `SecurityFilterChain` and their order, confirming no paths fall outside all chains.
- [ ] Verified method + path + role + owner/tenant policies for every sensitive endpoint.
- [ ] `permitAll` applies strictly to approved public endpoints and no broad matcher shadows stricter rules.
- [ ] Remaining routes hit `denyAll` when operations require an allowlist; new routes fail safely.
- [ ] CSRF remains enabled for web cookies/sessions; any exception is proven by the client/credential model.
- [ ] Security headers are verified on live responses, without assuming CSP is included by default.
- [ ] Form login/logout/session fixation/timeouts suit browser-based authentication if used.
- [ ] Method security and data-layer authorization are tested through real invocations.
- [ ] Tests cover anonymous, wrong role, with/without CSRF, disallowed methods, unlisted routes, and tenant/owner boundaries.
- [ ] Distinguished 302/401/403 by entry point; never mistook 404/405 or CSRF 403 for role tests.
- [ ] No demo credentials, debug/actuator endpoints, or policy bypasses left in real environments.
- [ ] Test execution evidence plus rollout, rollback, and redacted audit logs are ready.

**End-of-exercise check questions:**

1. Why is `anyRequest().denyAll()` **inside** a `securityMatcher("/api/**")` chain not enough to protect `/internal`?
2. If `"/api/**".permitAll()` appears before `"/api/admin/**".hasRole("ADMIN")`, which rule wins and why?
3. Does a POST test returning 403 prove role authorization works? What additional test is required?
4. If every request carries a bearer token in a header, is `csrf.disable()` automatically dangerous? What condition flips the answer?
5. Why might `@PreAuthorize` have no effect even though the annotation appears on the method?
6. Why must you inspect the actual response headers received by browsers instead of only reading source config?
7. Add a new endpoint and forget its policy: how do `denyAll` and `authenticated` behave differently?
8. With multiple chains, how do you ensure the login endpoint and every route land in an appropriate chain?

## 9. Reference Documentation for the Exercise

- [Spring Security 6.5 — Authorize HTTP Requests (matcher order, permitAll, denyAll)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Java Configuration, securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — MockMvc integration & testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)

The outcome of a strong security review is **clear policies, rules that actually execute, protective layers aligned with the authentication model, and tests that catch any future change that accidentally opens access**.
