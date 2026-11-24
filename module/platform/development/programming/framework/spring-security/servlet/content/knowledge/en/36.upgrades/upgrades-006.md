# From authorizeRequests and AccessDecisionManager to the AuthorizationManager Model

**Scope:** upgrading **Spring Security Servlet/Spring MVC** from the legacy configuration style (`authorizeRequests()`, `FilterSecurityInterceptor`, `AccessDecisionManager`, and `AccessDecisionVoter`s) to the **`authorizeHttpRequests()` + `AuthorizationManager`** model of Spring Security 6.x, Spring Boot 3.x, and Java 17+. This lesson covers architecture, API comparisons, writing request/method rules, migrating custom logic, before-and-after verification, and changes that can cause **unintended privilege widening or broken denials** during an upgrade.

**Version warning:** snippets showing `antMatchers()` and `WebSecurityConfigurerAdapter` are explicitly marked as **historical code for Spring Security 5.x**; do not copy them into Spring Security 6.x. The main examples use `SecurityFilterChain` and Spring Security 6.x Servlet APIs. Some methods were deprecated in later minor releases (such as forms of `AuthorizationManager.check(...)`), yet may still exist in Spring Security 6.x; consult the docs/migration notes for **your exact dependency version** before refactoring APIs further. Do not apply Servlet configs directly to WebFlux, which uses `ServerHttpSecurity.authorizeExchange(...)`.

## 1. Why migrate the model?

### 1.1 Authentication vs Authorization

- **Authentication**: “Who is calling?”. Once login, JWT, or basic authentication completes, Spring Security holds an `Authentication` containing the principal and authorities such as `ROLE_ADMIN` or `REPORT_READ`.
- **Authorization**: “Is that caller allowed to access this request or resource?”. For instance, `GET /api/reports/quarterly` requires `REPORT_READ`, whereas `POST /api/reports` requires `REPORT_WRITE`.
- Both the legacy **AccessDecisionManager** and the modern **AuthorizationManager** serve **authorization** decisions; they **do not replace** `AuthenticationManager` or `AuthenticationProvider` used to verify credentials.

When upgrading, the API names change, while the security objective stays the same: **deny by default**, allow only requests matching rules, protect permissions on services/domain objects, and maintain tests covering 200/401/403.

### 1.2 Two models viewed at the HTTP boundary

```text
BEFORE: authorizeRequests (Spring Security 5.x)
  HTTP request
       │
       ▼
  FilterSecurityInterceptor
       │
       ├── SecurityMetadataSource / ConfigAttributes for URL
       │
       ▼
  AccessDecisionManager
       │
       ├── AccessDecisionVoter A (grant/deny/abstain)
       ├── AccessDecisionVoter B
       └── strategies such as AffirmativeBased / UnanimousBased
       │
       ▼
  Allow or throw AccessDeniedException

AFTER: authorizeHttpRequests (Spring Security 6.x)
  HTTP request
       │
       ▼
  AuthorizationFilter
       │
       ▼
  AuthorizationManager<HttpServletRequest> or manager
  dispatched via RequestMatcherDelegatingAuthorizationManager
       │
       ├── Rule 1: requestMatcher + AuthorizationManager
       ├── Rule 2: requestMatcher + AuthorizationManager
       └── Final rule: anyRequest().denyAll()/authenticated()
       │
       ▼
  Authorization decision / reject request
```

This diagram omits other filters (CSRF, authentication, exception handling, security context). In a real system, **authentication happens along the filter chain**, and a caller may be unauthenticated on the current request. Spring Security passes a `Supplier<Authentication>` to authorization managers to **defer fetching `Authentication`** until needed—a difference from unconditional principal reads in many legacy snippets.

### 1.3 Why is the new model easier to extend?

`AuthorizationManager<T>` encapsulates **allow/deny decisions** under one contract, where `T` is the protected target. For example:

- `AuthorizationManager<RequestAuthorizationContext>` for requests selected by a matcher inside `authorizeHttpRequests`.
- `AuthorizationManager<HttpServletRequest>` at the filter or request-dispatcher level.
- `AuthorizationManager<MethodInvocation>` / method security components for method invocations.
- Built-in managers: `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager`, SpEL/metadata-backed managers, or compositions via `AuthorizationManagers.allOf(...)` and `anyOf(...)`.

Most straightforward rules need no custom classes. Reach for `.access(customManager)` or method security only when specialized business policies demand it.

## 2. Comparing components before and after upgrade

| Legacy approach | Modern approach or review item | Notes |
| --- | --- | --- |
| `http.authorizeRequests(...)` | `http.authorizeHttpRequests(...)` | Replaces the request authorization DSL; do not confuse with `oauth2Login()`. |
| `.antMatchers("/x/**")` | `.requestMatchers("/x/**")` | Not all expressions/matchers keep identical semantics; test MVC/servlet paths. |
| `.mvcMatchers(...)` | `.requestMatchers(...)` or explicit matcher | Depends on MVC matcher/config and version; watch servlet paths and `PathPattern`. |
| `.regexMatchers(...)` | `requestMatchers(RegexRequestMatcher...)` when regex is needed | Do not swap a regex for a wildcard string without verifying. |
| `FilterSecurityInterceptor` | `AuthorizationFilter` when using `authorizeHttpRequests` | Filter behavior, dispatcher types, and context handling differ. |
| `AccessDecisionManager` | `AuthorizationManager` | There is no automatic 1–1 mapping for every voter policy. |
| `AccessDecisionVoter` | Custom/composed manager | Must preserve actual grant/deny/abstain semantics. |
| `ConfigAttribute` / `SecurityMetadataSource` | `RequestMatcher` → `AuthorizationManager` | Separates request matching from authorization logic. |
| `AffirmativeBased`, `UnanimousBased` | `AuthorizationManagers.anyOf/allOf` when equivalent | Watch abstain handling, deny overrides, and short-circuiting. |
| `WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | Adapter removed in Spring Security 6; define filter chains via beans. |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Modern method security uses `AuthorizationManager`-based interceptors. |
| `access("hasAuthority('X')")` | `.hasAuthority("X")` or `.access(manager)` | Prefer the clear DSL for simple expressions. |

**Do not perform a mechanical “find-and-replace” upgrade.** An old `.antMatchers(...)` may match differently from `requestMatchers(...)` due to servlet paths, matcher inference, or dispatcher behavior. Likewise, legacy voters may have complex aggregation policies; verify equivalence with tests before replacing them with `anyOf`/`allOf`.

## 3. Historical configuration pattern: for recognition when reading legacy code

This is **historical code illustrating Spring Security 5.x**; it is incompatible with Spring Security 6.x if copied verbatim:

```java
// LEGACY ONLY — do not use with Spring Security 6.x.
http
    .authorizeRequests()
        .antMatchers("/", "/public/**").permitAll()
        .antMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    .and()
    .formLogin();
```

Before modifying an older project, inventory:

1. All matchers and their **declaration order**.
2. Public URLs, login/logout, error endpoints, static resources, and OAuth2/OIDC callbacks.
3. Rules using `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`.
4. `@PreAuthorize`, `@Secured`, `@RolesAllowed`, URL expression handlers, and custom voters.
5. `AccessDecisionManager`, `RunAsManager`, `PermissionEvaluator`, role hierarchies, and ACL/domain policies if present.
6. Exception handlers/entry points producing 401, 403, or redirects when unauthenticated.
7. How matchers handle HTTP methods, trailing slashes, path variables, servlet paths, and forward/error/async dispatchers.
8. Distinct `SecurityFilterChain`s and `@Order` precedence if the app defines multiple chains.

**Minimum baseline:** before changing the DSL, add positive/negative tests for each sensitive route. An upgrade that compiles cleanly yet silently lets `/admin/**` fall into `anyRequest().authenticated()` is still a security bug.

## 4. New configuration: authorizeHttpRequests on Spring Security 6.x

### 4.1 Simple conversion

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

This is a **method snippet** requiring `@Bean`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer` imports inside a Spring configuration. Do not add `.and()` out of old habit; the Lambda DSL keeps configuration clearer.

### 4.2 How Spring Security selects rules

With `authorizeHttpRequests`, rules are evaluated **in declaration order**. The **first matching rule** applies; later rules are never evaluated to add or subtract permissions for that request.

Wrong:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Bug: `/api/admin/users` matches `/api/**` first and only requires authentication. The `hasRole("ADMIN")` rule below **never gets a chance to apply**.

Right:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

**Deny by default** with `anyRequest().denyAll()` surfaces newly added undeclared endpoints. If you choose `anyRequest().authenticated()`, any unmatched route becomes accessible to any logged-in user, which may violate least privilege in multi-role systems. The choice depends on your architecture, yet must be **deliberate and tested**.

### 4.3 URL patterns and HTTP methods

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("REPORT_WRITE")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Never assume a `GET` rule protects `POST`: if only GET is declared, a POST request may fall through to a weaker catch-all rule. Similarly, review `HEAD`, `OPTIONS`, custom methods, and actuator/health routes per your architecture. For CORS preflight, configure CORS properly rather than opening all methods/endpoints with wildcards.

String-based `requestMatchers(...)` can choose a matcher based on the MVC environment and version; when using a non-`/` servlet mapping, multiple `DispatcherServlet`s, or special regex patterns, supply an explicit `RequestMatcher` and test matching behavior. **Never assume old `antMatchers` and new `requestMatchers` are 100% identical.**

## 5. Role of AuthorizationManager and decision results

Conceptually, a manager returns an `AuthorizationDecision` (or `AuthorizationResult` depending on API/minor version) representing granted/denied. In Spring Security 6.x, the common method signature is:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T secureObject
);
```

Some newer versions introduce or move toward `authorize(Supplier<Authentication>, T)`; when writing long-lived libraries, check the exact interface and deprecation notes of your target version. In standard Spring Security 6.x patterns, `check(...)` is overridden; do not implement both methods without understanding the default contract.

**Why `Supplier<Authentication>`?** When `permitAll` or `denyAll` does not need the caller's identity, Spring Security avoids loading `Authentication` unnecessarily. Custom managers should call `authentication.get()` only when a decision genuinely depends on the principal.

### 5.1 Built-in managers

| Usage | Meaning |
| --- | --- |
| `.permitAll()` | Permits matching requests without requiring login. |
| `.denyAll()` | Denies all matching requests, even for authenticated users. |
| `.authenticated()` | Requires a non-anonymous authenticated user per Spring Security. |
| `.fullyAuthenticated()` | Rejects remember-me authentication as not fully authenticated. |
| `.hasAuthority("REPORT_READ")` | Requires the exact authority string. |
| `.hasAnyAuthority("A", "B")` | Requires at least one listed authority. |
| `.hasRole("ADMIN")` | Typically requires `ROLE_ADMIN`, not bare `ADMIN`. |
| `.access(customAuthorizationManager)` | Uses an application-specific policy manager. |

For example, having `ROLE_ADMIN` does not mean a user automatically holds `REPORT_READ` unless your app's policy or role hierarchy defines it. Never trust JWT or IdP roles blindly just because they contain `admin`; claims-to-authorities mapping must be configured and tested separately.

### 5.2 Composition and “abstain” are not identical

The legacy voter model returned **grant/deny/abstain**, and `AccessDecisionManager` aggregated votes using a strategy (affirmative/unanimous/consensus). In the new model, `AuthorizationManagers.allOf(...)` or `anyOf(...)` can be used when the policy is genuinely equivalent:

- `allOf(A, B)`: generally corresponds to **both must pass**.
- `anyOf(A, B)`: generally corresponds to **at least one must pass**.

However, **do not claim** this is an exact conversion for every legacy voter manager: all-abstain cases, deny-override semantics, exception behavior, rule ordering, and null decisions can differ. Build a truth table from the old code and write tests for grant/deny/abstain combinations before replacing it.

## 6. Complete example: testable Spring Boot Servlet project

Goal: an application enforcing four independent permission types:

- `GET /` and `GET /api/reports/public`: public.
- `GET /api/reports/quarterly`: requires `REPORT_READ` authority.
- `POST /api/reports`: requires `REPORT_WRITE` **and** a CSRF token (with default session/web browser config).
- `GET /api/admin/summary`: requires `ROLE_ADMIN`.
- `GET /api/profiles/{username}`: only a user whose name matches the path variable can view, illustrating custom request authorization.
- `GET /api/service-report`: HTTP requires only authentication, while the service adds `@PreAuthorize` requiring `REPORT_READ`.

Create a Spring Initializr project: **Spring Boot 3.x**, **Java 17+**, **Spring Web**, **Spring Security**, **Spring Boot Starter Test**, plus `spring-security-test`. This example is a **Spring Boot application** run via Gradle/Maven with dependencies, not runnable via plain `javac` alone.

### 6.1 Dependencies configuration

**`build.gradle`**: required dependencies section, keeping plugins/repositories generated by Spring Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2 SecurityConfig.java

**`src/main/java/com/example/authmigration/SecurityConfig.java`**

```java
package com.example.authmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        var reader = User.withUsername("reader")
            .password("{noop}reader-demo")
            .authorities("REPORT_READ")
            .build();

        var writer = User.withUsername("writer")
            .password("{noop}writer-demo")
            .authorities("REPORT_WRITE")
            .build();

        var admin = User.withUsername("admin")
            .password("{noop}admin-demo")
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/public"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("REPORT_READ")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasAuthority("REPORT_WRITE")
                .requestMatchers(
                    HttpMethod.GET, "/api/admin/**"
                ).hasRole("ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/api/profiles/{username}"
                ).access(new OwnProfileAuthorizationManager())
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Explanation and scope:**

1. `@EnableMethodSecurity` enables `@PreAuthorize` checks in services; no legacy `@EnableGlobalMethodSecurity` configuration is needed.
2. Spring Security evaluates HTTP rules in order: public GET before broad GET reports; admin and own-profile have dedicated rules.
3. `{noop}` and demo passwords are **solely** for testing/demonstration, never for production. Production requires secure password hashing (via an appropriate `PasswordEncoder`), a real user store, MFA/passkeys, login throttling, and session management.
4. `.httpBasic(...)` provides an entry point to test 401 when unauthenticated; real browser apps may use `formLogin`/OIDC instead.
5. Default CSRF protection can still affect POST requests depending on session configuration. Never disable CSRF just to make POST tests pass easily.
6. If a stateless API uses bearer JWTs instead of browser cookies, design `oauth2ResourceServer(...)`, sessions, and CSRF for that model. **`AuthorizationManager` does not replace JWT validation.**

### 6.3 Writing a custom request AuthorizationManager

**`src/main/java/com/example/authmigration/OwnProfileAuthorizationManager.java`**

```java
package com.example.authmigration;

import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class OwnProfileAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        String username = context.getVariables().get("username");

        boolean allowed = current != null
            && !(current instanceof AnonymousAuthenticationToken)
            && current.isAuthenticated()
            && username != null
            && username.equals(current.getName());

        return new AuthorizationDecision(allowed);
    }
}
```

**Mechanism:** `RequestAuthorizationContext` holds the `HttpServletRequest` and URI variables extracted by supporting matchers. On `/api/profiles/{username}`, the manager compares the path's `username` against `Authentication.getName()` and returns `AuthorizationDecision(true/false)`.

**Important limitation:** comparing usernames illustrates how to write a manager, yet it is **not a production object-security pattern for every application**. Usernames can change, collide across tenants, or vary in canonicalization; use immutable account IDs and database policies for real ownership rules. Verify path matching extracts variables properly in deployments with custom servlet paths or custom matchers. If a matcher provides no variable, this code **denies** rather than granting access carelessly.

In some newer Spring Security 6.x releases, `check(...)` may be marked deprecated in favor of `authorize(...)`; this snippet uses the common 6.x signature to illustrate the logic. When upgrading dependencies, implement the method matching your actual interface/version and keep behavioral tests intact.

**Avoid common mistakes in custom managers:**

- Calling `authentication.get()` and assuming `isAuthenticated()==true` is enough: an `AnonymousAuthenticationToken` can also return `isAuthenticated()==true`. Use proper semantics (such as Spring Security's trust resolver) rather than a lone boolean.
- Trusting client-supplied role/username headers (`X-User`, `X-Role`) that were not verified by authentication.
- Performing slow network/DB I/O or data-mutating side effects inside the authorization path; this raises latency and introduces retry side effects.
- Returning allow when an account/tenant/path variable is missing or policy fails to load. The safe default is **deny whenever evidence is missing**.

### 6.4 ReportService.java: method security

**`src/main/java/com/example/authmigration/ReportService.java`**

```java
package com.example.authmigration;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String restrictedReport() {
        return "quarterly-report";
    }
}
```

`@PreAuthorize` protects the method even when called from another endpoint, scheduled job, or service. Never rely solely on URL rules when the same business method has multiple callers. **Proxy note:** self-invocation such as `this.restrictedReport()` inside the same bean typically bypasses the AOP proxy and skips the method interceptor. This example invokes it through a Spring-managed bean.

### 6.5 Controller and main

**`src/main/java/com/example/authmigration/ReportController.java`**

```java
package com.example.authmigration;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/api/reports/public")
    public String publicReport() {
        return "public-report";
    }

    @GetMapping("/api/reports/quarterly")
    public String quarterly() {
        return reportService.restrictedReport();
    }

    @PostMapping("/api/reports")
    public String createReport() {
        return "created";
    }

    @GetMapping("/api/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @GetMapping("/api/profiles/{username}")
    public String profile(@PathVariable String username) {
        return "profile:" + username;
    }

    @GetMapping("/api/service-report")
    public String serviceReport() {
        // HTTP rule only requires authenticated; method rule requires REPORT_READ.
        return reportService.restrictedReport();
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

**`src/main/java/com/example/authmigration/AuthorizationMigrationApplication.java`**

```java
package com.example.authmigration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AuthorizationMigrationApplication.class, args
        );
    }
}
```

Name each public class after its file, all in the same package. Start the application with the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Sample requests using HTTP Basic with demo accounts:

```bash
curl -i http://localhost:8080/api/reports/public
curl -i -u reader:reader-demo \
  http://localhost:8080/api/reports/quarterly
curl -i -u reader:reader-demo \
  http://localhost:8080/api/admin/summary
curl -i -u admin:admin-demo \
  http://localhost:8080/api/admin/summary
```

Expected statuses in order: **200, 200, 403, 200** with the demo configuration. HTTP Basic does not encrypt passwords independently of TLS, so **use HTTPS** outside localhost and never use demo credentials in production. The `curl` commands illustrate requests only; no transcript implies a specific environment actually executed them.

## 7. Regression testing: request and method authorization

When upgrading authorization, tests must verify **behavior**, not just that code compiles. With `spring-security-test`, MockMvc can supply test users/authorities to validate HTTP and method security rules.

**`src/test/java/com/example/authmigration/AuthorizationMigrationTest.java`**

```java
package com.example.authmigration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/api/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-report"));
    }

    @Test
    void privateReportNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/reports/quarterly"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayReadReportButNotAdminPage() throws Exception {
        mvc.perform(get("/api/reports/quarterly").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));

        mvc.perform(get("/api/admin/summary").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/quarterly")
            .with(user("visitor").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleAdminCanEnterAdminArea() throws Exception {
        mvc.perform(get("/api/admin/summary")
            .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-summary"));
    }

    @Test
    void ownProfileManagerRejectsOtherUser() throws Exception {
        mvc.perform(get("/api/profiles/alice")
            .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/api/profiles/alice")
            .with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityProtectsServiceDespiteWeakHttpFallback()
            throws Exception {

        mvc.perform(get("/api/service-report")
            .with(user("visitor").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/service-report").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));
    }

    @Test
    void postNeedsBothReportWriteAndCsrf() throws Exception {
        var writer = user("writer").authorities(
            new SimpleGrantedAuthority("REPORT_WRITE")
        );

        mvc.perform(post("/api/reports").with(writer))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports").with(writer).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));

        mvc.perform(post("/api/reports").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("REPORT_READ")
            )
        ).with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

**Reading the results:** these tests use `user(...)` to construct a test `Authentication` for **authorization** checks. They **do not** prove BCrypt, login pages, Basic header parsing, or real JWT/IdP token verification. To test authentication boundaries, add integration tests sending real credentials/tokens through the actual filter chain.

**Expected:** all tests above are **designed to pass** in a complete project/config; this lesson does not claim they were compiled or run in the reader's workspace. Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Compiler and formatter note:** Java allows line breaks after `import static org...request` followed by `.SecurityMockMvcRequestPostProcessors...` as shown, though single-line imports can be used if your IDE prefers. Check Gradle BOM compatibility for Spring Security 6.x/Boot 3.x before copying code.

## 8. Migrating custom AccessDecisionVoter and AccessDecisionManager

This is harder than replacing `antMatchers`. For legacy custom voters, **never translate class names before pinning down the real logic**.

### 8.1 Legacy model

An old `AccessDecisionVoter` could return:

- `ACCESS_GRANTED`: voter agrees to allow.
- `ACCESS_DENIED`: voter objects.
- `ACCESS_ABSTAIN`: voter has no opinion or does not apply.

`AccessDecisionManager` (such as `AffirmativeBased`, `UnanimousBased`, `ConsensusBased`) combined multiple votes. Details such as **all-abstain decisions**, tie-breaking strategies, deny precedence, and exception handling all influence the outcome. Never equate “abstain” with “allow.”

For example, an old policy might read: “Allow if caller has `ROLE_SUPPORT` *or* owns the record, **but** block if the record is under a legal hold.” Converting that simply to `anyOf(role, owner)` while dropping the legal-hold check **severely widens access**.

### 8.2 Expressing policy as explicit conditions

Write the logic in plain words first:

```text
canReadInvoice(actor, invoice):
    require actor is authenticated
    require invoice exists and belongs to correct tenant
    require invoice is not blocked by legal hold
    allow if actor has INVOICE_AUDITOR
             OR actor owns invoice
    otherwise deny
```

This is **pseudocode**, not a Java implementation. To enforce permissions on specific domain objects, place the logic in a domain policy service and method security:

```java
@PreAuthorize("@invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceDto readInvoice(String invoiceId) {
    return invoiceRepository.findAuthorizedDto(invoiceId);
}
```

This is a **method snippet** requiring an `invoicePolicy` bean, `InvoiceDto` type, repository, and implemented authorization policy. In production, verify tenant/ownership from a **trusted backend data source**, never trusting a client-sent `invoice.owner`. If loading the resource prior to authorization, guard against object-existence leaks, TOCTOU, or authorization drift between check and return.

### 8.3 Using a manager on an HTTP route when policy depends only on the request

If the decision relies solely on HTTP path/method and `Authentication`, `.access(new OwnProfileAuthorizationManager())` as in the runnable example suffices. If it needs object existence and ownership checks, prefer a policy service/method security to avoid duplicate DB lookups or bypass via another route.

For clear boolean combinations, `AuthorizationManagers.allOf/anyOf` can replace simple multi-checks; yet before replacing a custom `AccessDecisionManager`, verify the full truth table. Never quietly turn a “deny always wins” rule into `anyOf` where one grant overrides a deny.

### 8.4 AuthenticationManager remains a separate component

Your project may still use:

```java
AuthenticationManager authenticationManager;
AuthenticationProvider customProvider;
```

Those are **authentication components**: handling passwords, tokens, or authentication factors. Replacing `AccessDecisionManager` with `AuthorizationManager` **does not** mean removing `AuthenticationManager`. The names sound similar, yet their responsibilities are distinct.

## 9. Method security: @EnableMethodSecurity and commonly overlooked changes

### 9.1 From @EnableGlobalMethodSecurity

Legacy Spring Security 5.x code often contains:

```java
// LEGACY ONLY:
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

Modern configurations typically use:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` enables `@PreAuthorize` / `@PostAuthorize` with sensible defaults and uses the modern authorization managers/interceptors. Never carry over every flag from legacy config without checking your project's version and defaults. `@Secured` and JSR-250 roles may require `securedEnabled`/`jsr250Enabled` flags if used.

### 9.2 HTTP authorization does not replace method security

Situations requiring method security:

- The same service can be called from an HTTP controller, scheduled job, message consumer, or another endpoint.
- Permissions depend on object ownership, tenant, amount, state, role, and DB-backed policies.
- HTTP matchers only guard a route pattern and lack the context to inspect a specific domain record.
- Logic is shared across callers and needs standalone testing.

Still, method security **does not exempt URL checks**: public and privileged routes need defense-in-depth. Use both where appropriate, testing overlapping policies and path coverage carefully.

### 9.3 @PreAuthorize is not “magic” for internal calls

Spring method security typically works via proxies. Calling `this.protectedMethod()` within the same bean can bypass the proxy and skip the check. Invoke protected methods through Spring-managed beans, avoid self-invocation, and check proxy/aspect modes if customized.

When methods run on another thread via `@Async`, `SecurityContextHolder` normally uses `ThreadLocal`, so context does not propagate automatically. Configure `DelegatingSecurityContextAsyncTaskExecutor` or an appropriate service identity, and test that contexts do not leak across pooled threads. That is an **identity propagation** concern, not an `authorizeHttpRequests` DSL issue.

## 10. Multiple SecurityFilterChains: securityMatcher vs requestMatchers

A system may split `/api/**` and website `/**` across multiple chains. Distinguish:

- **`http.securityMatcher(...)`:** chooses **which requests belong to that `SecurityFilterChain`**, before `authorizeHttpRequests` inside it runs.
- **`authorizeHttpRequests().requestMatchers(...)`:** chooses **authorization rules inside the already selected chain**.
- `SecurityFilterChain` beans are evaluated in `@Order` sequence; the **first matching chain** handles the request rather than running all chains and merging policies.

Condensed config example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

These are **snippets of two beans** requiring `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and a `@Configuration` class. In production, each chain must configure CSRF, sessions, exception handling, auth mechanisms, and request matchers suited to its client type. Never copy this verbatim and assume bearer tokens work: the API chain above uses **HTTP Basic**, not Resource Server.

**Common mistakes:**

- A `/**` chain with `@Order(1)` swallows `/api/**` before the API chain is ever evaluated.
- Lacking a fallback chain for routes outside `securityMatcher` leaves unmatched routes **unprotected by Spring Security**.
- Putting `requestMatchers("/api/**")` in the web chain does not make API requests enter the web chain if the API chain already matched first.
- Failing to inspect paths for `/actuator/**`, error endpoints, static resources, and custom servlet mappings.

Write tests for **each chain, each auth scheme, and unmatched routes**, asserting expected 401/403/302 responses.

## 11. Dispatcher types, ERROR/FORWARD, and differences in AuthorizationFilter

Servlet containers define dispatcher types including `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. One HTTP request can trigger internal forward/error dispatches inside the server. When upgrading to `AuthorizationFilter`, authorization checks on secondary dispatches can differ from legacy `FilterSecurityInterceptor` behavior.

For example, an authorized controller forwarding to a view/template or error handler might hit 403 if rules have not accounted for dispatched URLs or dispatchers. Never “fix” that with `anyRequest().permitAll()`.

If analysis confirms specific dispatcher types must be permitted, the DSL supports:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        jakarta.servlet.DispatcherType.FORWARD,
        jakarta.servlet.DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

This is **illustrative**; blanket `permitAll` on `ERROR`/`FORWARD` may be unsafe for some apps. For real business endpoints, ensure clients cannot trick forwards into privileged resources or leak content via error paths. Test required dispatch flows in a realistic environment.

**For async Servlet:** if a `Callable` or `DeferredResult` executes on another thread, test `SecurityContext` propagation and related dispatches as well. Changing the request authorization DSL does not automatically solve async context issues.

## 12. CSRF, CORS, servlet mappings, and things not to “fix by mistake”

### 12.1 CSRF is not an authorizeHttpRequests rule

A `POST /api/reports` from a browser with a session/cookie can still need a **CSRF token** even if the actor holds `REPORT_WRITE`. Those are two independent checks:

- **Authorization:** does the actor hold `REPORT_WRITE`?
- **CSRF:** does the unsafe browser request carry a valid CSRF token per strategy?

In MockMvc tests focused on authorization, pass `with(csrf())`, and keep a separate test proving missing CSRF returns 403. Never add `csrf.disable()` app-wide to “resolve” 403s after upgrading. Stateless bearer-token APIs that do not rely on browser-auto-sent cookies have a different CSRF model and should be evaluated separately.

### 12.2 CORS is not solved with permitAll

Browsers send `OPTIONS` preflight requests. Configure CORS with exact allowed origins/methods/headers and proper filter ordering instead of opening all endpoints because preflight returned 403. `permitAll` does not emit `Access-Control-Allow-Origin`. When browser credentials are allowed, never combine wildcard origins with `allowCredentials`.

### 12.3 Do not replace permitAll with web.ignoring indiscriminately

`permitAll` still routes requests through the Spring Security filter chain (applying security headers, context, logging, CSRF on unsafe methods, etc.). `web.ignoring()` excludes requests from the Spring Security filter chain entirely. Static assets may have deliberate exceptions, yet **never use `ignoring` on business endpoints** just to dodge misconfigured authorization.

### 12.4 Matchers and URL encoding

Matchers can depend on servlet path, `PathPattern`, encoding, URL normalization, trailing slashes, and the container. Test `/admin`, `/admin/`, `/admin/users`, encoded path segments, and multiple dispatchers. Do not rely on assuming an old pattern behaves identically across every release.

An unmapped controller path may return 404; that does not prove authorization blocked it. For access-control tests, hit **real routes** and assert statuses/bodies per principal.

## 13. Distinguishing 401, 403, redirects, and false positives

| Situation | Typical result | Meaning |
| --- | --- | --- |
| Unauthenticated `GET /api/reports/quarterly` (Basic demo) | 401 | Missing credentials; authentication required. |
| Reader lacking `ROLE_ADMIN` hits admin | 403 | Authenticated, yet insufficient permissions. |
| Authorized POST missing CSRF | 403 | Rejected by CSRF filter, not necessarily missing authority. |
| Unauthenticated web app using `formLogin` | 302 to login page | Web UI entry point, distinct from API 401. |
| Missing route/mapping | 404 | Does not guarantee authorization was tested. |
| No filter chain matches route | May bypass Spring Security | Check `SecurityFilterChain` selection; never infer safety from 200. |
| Custom manager missing context/attribute | Should deny by policy | Never auto-grant simply because principal could not be read. |

For tests to be trustworthy, always verify **which chain ran**, that the route exists, that the principal was built accurately, that authorities are intentional, and that the response body confirms the expected controller ran.

## 14. Step-by-step migration plan

### Step 1: Capture the baseline

Catalog **all protected endpoints**, filter chains, roles/scopes, user journeys, controllers, and method security annotations. Specifically inventory:

- Security-relevant public URLs (login, signup, password reset, actuator health, OAuth2 callbacks).
- Admin/report/tenant/data-export endpoints.
- Custom `AccessDecisionManager`, `AccessDecisionVoter`, `PermissionEvaluator`, and role hierarchies.
- Uses of `web.ignoring`, custom access expressions, and servlet mappings.
- HTTP methods and dispatcher types.
- API clients (browser cookies, Basic, OAuth2/JWT, mTLS) and expected 401/403/302 codes.

### Step 2: Write behavioral tests before modifying code

Run positive and negative tests on the **old version**; record which requests succeed and which are denied. For custom voters, build a truth table across all combinations (grant/deny/abstain), including missing resources, disabled accounts, cross-tenant access, and service calls.

### Step 3: Upgrade dependencies in a controlled way

With Java 17+, Spring Boot 3.x, and Spring Security 6.x, verify all required modules are declared cleanly. Do not “upgrade” by editing code while leaving some Spring Security 5.x JARs on the classpath. Let the Boot BOM manage versions to avoid skew, then consult minor-version migration guides.

### Step 4: Migrate SecurityFilterChain and request DSL

Move from adapter/`authorizeRequests`/`antMatchers` to `SecurityFilterChain` beans/`authorizeHttpRequests`/`requestMatchers`. Preserve “specific before general” ordering, `anyRequest`, and fallback chains. Avoid altering authentication mechanisms unnecessarily.

### Step 5: Migrate custom policies

For simple `hasRole`/`hasAuthority` checks, prefer the built-in DSL. For multi-condition policies, use a custom `AuthorizationManager` or method security/domain policies. Compare **behavior, not just class names**. Preserve deny overrides, roles, scopes, tenant, and ownership checks.

### Step 6: Re-test every boundary

Test:

- anonymous, authenticated, missing role, valid role;
- public/static/admin/unknown paths;
- GET/POST/OPTIONS and CSRF;
- servlet `FORWARD`/`ERROR`/`ASYNC`;
- multiple `SecurityFilterChain`s and `@Order`;
- method security through Spring proxies;
- real OAuth2/JWT/principal mapping where relevant;
- service methods invoked from queues/async/background tasks;
- reverse proxies/servlet paths/case sensitivity/trailing slashes.

### Step 7: Deploy and observe

Monitor 401/403/302 rates, unexpected access grants, route coverage, login failures, CSRF rejections, and `AccessDeniedException` logs. Avoid logging secrets or tokens in debug logs. Keep dependency/config rollback plans and feature flags ready. Never declare a migration successful merely because “403 rates dropped.”

## 15. Regression test matrix to prevent privilege widening

| Rule | User/Request | Before upgrade | Must hold after upgrade |
| --- | --- | --- | --- |
| Public GET | Anonymous GET `/api/reports/public` | 200 | 200 |
| Protected report | Anonymous GET private report | 401/302 per entry point | Preserve matching semantics |
| Protected report | Reader with `REPORT_READ` | 200 | 200 |
| Protected report | Visitor with only `ROLE_USER` | 403 | 403 |
| Admin | Reader without `ROLE_ADMIN` | 403 | 403 |
| Admin | Admin with `ROLE_ADMIN` | 200 | 200 |
| Write | Authorized writer missing CSRF | 403 in session app | 403 |
| Write | Authorized writer + CSRF | 2xx | 2xx |
| Object ownership | Bob views Alice's profile | 403 | 403 |
| Method security | User lacking `REPORT_READ` calls service | Deny | Deny |
| Unknown endpoint | Anonymous and authenticated | Per fallback policy | Must not widen to `permitAll` |
| Multiple chains | API and web routes | Right auth scheme/chain | Not swallowed by another chain |
| Forward/error dispatch | Valid dispatchers | Inventoried behavior | Deliberate, not widened unchecked |
| Custom voter combinations | grant/deny/abstain permutations | Per old policy | Equivalent or approved change |

**Note:** status codes in this table are illustrative; 401 and 302 depend on entry points, while 403 can come from CSRF before authorization. Before/after comparisons must hit **the same flow and corresponding filter chain** to be meaningful.

## 16. Common upgrade errors

| Error | Cause | How to verify/fix |
| --- | --- | --- |
| `antMatchers` no longer compiles | Old API removed in Spring Security 6.x. | Use `requestMatchers` properly; test matcher semantics. |
| `WebSecurityConfigurerAdapter` not found | Adapter config class removed. | Define `SecurityFilterChain` beans and supporting beans. |
| Regular user suddenly accesses admin | Broad `/api/**` rule placed before admin rule. | Put specific before generic; add 403 regression test. |
| Admin gets 403 despite having `"ADMIN"` | `hasRole("ADMIN")` usually expects `ROLE_ADMIN`. | Check actual authorities and map issuer/roles properly. |
| Custom voter “deny” is ignored | Mistakenly converted to `anyOf`/wrong semantics. | Truth table + tests for all grant/deny/abstain cases. |
| Unauthenticated route gets 403 instead of redirect | Entry point/filter chain/CSRF behavior changed. | Distinguish 401/403/302; inspect `ExceptionTranslationFilter` and auth config. |
| POST test fails with 403 | Missing CSRF token, not missing role. | Pass `with(csrf())` for authorization tests; keep negative CSRF tests. |
| Error page/forward gets blocked | Dispatcher authorization behavior changed. | Test `FORWARD`/`ERROR` and configure exact matchers. |
| URL wildcard matches differently than old version | MVC/servlet path/`PathPattern`/trailing slash changes. | Test real requests and explicit matchers if needed. |
| API request has no security | No chain matches after `securityMatcher`. | Add a fallback chain; check `@Order` and paths. |
| REST endpoint returns 302 HTML login | Web chain/`formLogin` captured API path. | Fix chain selection and API entry point. |
| `@PreAuthorize` does not run | Missing `@EnableMethodSecurity` or self-invocation. | Check proxies and write unit/integration service tests. |
| User is authenticated yet accesses others' data | HTTP rule only checks `authenticated`, no owner/tenant check. | Enforce method security/domain authorization on resources. |
| `permitAll` swapped for `web.ignoring` | Bypasses filter chain and strips needed security filters. | Verify headers/CSRF/logs; use `permitAll` where appropriate. |
| WebFlux app copies `HttpSecurity` | Servlet and reactive APIs differ. | Use `ServerHttpSecurity`/`authorizeExchange` for WebFlux. |
| OAuth2 Login works, yet Bearer API fails verification | `AuthorizationManager` is not a token decoder. | Configure OAuth2 Resource Server/decoder properly and test real bearer auth. |

## 17. Quick pre-merge checklist

- [ ] Only compatible Spring Security `authorizeHttpRequests`/`SecurityFilterChain` APIs are used; legacy code remains only in docs.
- [ ] Specific matchers precede broad matchers, and `anyRequest` has an explicit **deny/fallback** meaning.
- [ ] All sensitive URLs and HTTP methods have dedicated rules/tests; no routes are missed across multiple filter chains.
- [ ] `hasRole`/`hasAuthority` are verified against actual authorities, never inferred from untrusted client claims.
- [ ] Custom voters/`AccessDecisionManager` are migrated using a truth table, not just class-name swaps.
- [ ] Custom `AuthorizationManager`s deny when principal/path/object/risk context is missing; never trust unverified headers.
- [ ] `@EnableMethodSecurity` and `@PreAuthorize` are tested through Spring proxies; ownership/tenant checks sit at the right layer.
- [ ] CSRF, CORS, dispatcher types, OAuth2 callbacks, form login, and API entry points remain intact.
- [ ] Tests cover anonymous/reader/admin/writer, 401/403/302, POST+CSRF, object-level denials, and cross-chain routing.
- [ ] Neither `permitAll` nor `web.ignoring` was loosened to bypass build errors or 403s.
- [ ] Metrics/alerts and a post-deployment rollback plan are ready.

**Remember:** `authorizeRequests` + `AccessDecisionManager` is the legacy authorization path built around interceptors, metadata, and voters. `authorizeHttpRequests` + `AuthorizationManager` pairs decision logic directly with request matchers, cleanly supporting built-in managers, custom policies, and method security. **The decisive milestone in an upgrade is not swapping the API, but proving every allow/deny boundary still holds**—especially matcher order, custom voter semantics, multiple filter chains, resource-level permissions, and easily overlooked dispatcher/CSRF flows.
