# hasRole, hasAnyRole, hasAuthority, and hasAnyAuthority in Spring Security Servlet

> **Context:** Spring Security **Servlet**, Java 17+, Spring Boot 3.x / Spring Security 6.x. This lesson focuses on **HTTP authorization** with `authorizeHttpRequests`: which **`GrantedAuthority`** grants or denies an authenticated request access, the difference between **prefixed roles** and **exact-match authorities**, the meaning of `hasAny...` methods, and how to test them. It includes a Spring Boot example with configuration, controller, demo users, `MockMvc` tests through the filter chain, and a directly runnable Java 17 program. Do not confuse authorization with the password authentication step.

## 1. Two Questions That Must Be Separated

**Authentication** answers: *which identity does this request belong to, and is the authentication proof valid?*  
**Authorization** answers: *is the current identity allowed to perform the action on the resource?*

A successfully logged-in user does **not** automatically get access to `/admin`. Spring Security checks the actual permissions attached to `Authentication.getAuthorities()` and the policy of the URL/method being called.

~~~text
HTTP request
   |
   v
FilterChainProxy -> Matching SecurityFilterChain
   |
   +-- Authentication mechanism
   |       session / form login / Basic / bearer token ...
   |       -> Authenticated Authentication
   |       -> authorities issued by a trusted source
   |
   v
AuthorizationFilter
   |
   v
RequestMatcher (e.g., GET /api/reports/**)
   |
   v
AuthorizationManager declared by authorizeHttpRequests
   |
   +-- Matching permission -> proceed to DispatcherServlet/controller
   |
   +-- Insufficient permission -> AccessDenied / typically 403
   |
   +-- Unauthenticated -> AuthenticationEntryPoint,
                          may redirect to login or return 401
~~~

**Minimal definition:** a `GrantedAuthority` is an object with `String getAuthority()`, such as `ROLE_ADMIN`, `ROLE_USER`, `SCOPE_reports.read`, or `DOCUMENT_READ`. This is **not** a password, username, or HTTP endpoint name; it is a string the system matches against rules.

A principal can hold multiple authorities:

~~~text
Authentication.getName()         = "alice"
Authentication.isAuthenticated() = true

Authentication.getAuthorities() = [
  ROLE_ADMIN,
  DOCUMENT_READ,
  BILLING_WRITE,
  SCOPE_reports.read,
  SCOPE_reports.write
]
~~~

When authorization checks, the framework does not ask "is alice's name admin?". It compares permissions **verified by the server** against the conditions declared by the developer.

## 2. Quick Comparison of the Four Methods

| Rule in `authorizeHttpRequests` | Meaning with Default `ROLE_` Naming | Example Required Authorities |
| --- | --- | --- |
| `hasRole("ADMIN")` | Requires **one role**, interpreted as authority `ROLE_ADMIN`. | `ROLE_ADMIN` |
| `hasAnyRole("ADMIN", "OPS")` | Has **at least one** of the listed roles. | `ROLE_ADMIN` **or** `ROLE_OPS` |
| `hasAuthority("DOCUMENT_READ")` | Requires **one exact authority string**. | `DOCUMENT_READ` |
| `hasAnyAuthority("BILLING_READ", "BILLING_WRITE")` | Has **at least one** exact authority string. | `BILLING_READ` **or** `BILLING_WRITE` |

With Spring Security's standard authority assignment:

~~~text
hasRole("ADMIN")                   ≈ hasAuthority("ROLE_ADMIN")
hasAnyRole("ADMIN", "OPS")         ≈ hasAnyAuthority("ROLE_ADMIN", "ROLE_OPS")
hasAuthority("ADMIN")             DIFFERS FROM hasAuthority("ROLE_ADMIN")
hasAuthority("SCOPE_reports.read") does not equal hasRole("reports.read")
~~~

The `≈` symbol only expresses matching equivalence **with the default role prefix and no special configuration**; not every version or every method/expression security integration shares the same custom prefix mechanism.

**Remember immediately:** `hasAny...` is **OR**, not AND. If you need a user to hold **both permissions simultaneously**, do not use `hasAnyAuthority("A","B")` because either A *or* B will pass; you need a supported combined condition, a custom `AuthorizationManager`, or an appropriate policy.

## 3. hasRole: How Is a Role Name Converted to a GrantedAuthority String?

Example:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

In common configurations, the condition searches for the `ROLE_ADMIN` authority in `Authentication.getAuthorities()`. A user carrying `ROLE_ADMIN` passes; a user carrying only `ADMIN` **does not** pass under this policy. The **`ROLE_` prefix** mechanism creates this distinction.

**Pass `"ADMIN"`, not `"ROLE_ADMIN"`, to `hasRole`.** In the `authorizeHttpRequests` DSL backed by `AuthorityAuthorizationManager`, `hasRole` in Spring Security 6 versions typically checks that the input does not contain the standard `ROLE_` prefix and may throw `IllegalArgumentException` if you call `hasRole("ROLE_ADMIN")`. When you want to check the exact string `ROLE_ADMIN`, use `hasAuthority("ROLE_ADMIN")`.

### Granting Authorities from UserDetails

`User.withUsername(...)` has two DSL styles that are easy to confuse:

~~~java
// Excerpt from a method returning UserDetails in an app with
// a declared PasswordEncoder encoder.
UserDetails byRole = User.withUsername("an")
    .password(encoder.encode("demo-only"))
    .roles("ADMIN")
    .build();

// Equivalent in authority string: ROLE_ADMIN.
UserDetails byExactAuthority = User.withUsername("binh")
    .password(encoder.encode("demo-only"))
    .authorities("ROLE_ADMIN")
    .build();
~~~

The examples above are **code snippets**, requiring imports for `User`, `UserDetails`, and a properly typed `encoder` variable. With the standard builder, `roles("ADMIN")` prepends `ROLE_` when building authorities; `authorities("ROLE_ADMIN")` keeps the exact string supplied by the caller.

**Critical mistake:** do not call `.roles("ADMIN").authorities("DOCUMENT_READ")` and assume the result definitely contains both groups. `User.UserBuilder` methods can overwrite the authorities field on the later call; build the **complete list** with `.authorities("ROLE_ADMIN", "DOCUMENT_READ")`, or use an explicit roles -> authorities mapping component that you manage.

### ROLE_ Is a Convention, Not a Separate "Role Data Type"

In `Authentication.getAuthorities()`, there are typically only `GrantedAuthority` objects holding strings. The `ROLE_` prefix gives the framework/application a naming convention to distinguish high-level roles from functional permissions. Java has no mechanism that automatically infers roles from a username string or a `roles` table if you do not map data properly when building `Authentication`.

For example, a database table stores the role `ADMIN`. If a service maps it to `new SimpleGrantedAuthority("ADMIN")` while the HTTP config uses `hasRole("ADMIN")`, the check fails due to missing `ROLE_`. Decide consistently: normalize roles to `ROLE_ADMIN`, or use `hasAuthority("ADMIN")` matching the policy format (and align other security components consistently).

## 4. hasAnyRole: At Least One Role, Not All Roles

~~~java
.requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
~~~

This rule permits requests when the authorities list contains **ROLE_ADMIN or ROLE_OPS**. It does not require the user to hold both at once.

| User's Authorities | hasAnyRole("ADMIN","OPS") | Reason |
| --- | --- | --- |
| `[ROLE_ADMIN]` | Allow | Has ROLE_ADMIN. |
| `[ROLE_OPS]` | Allow | Has ROLE_OPS. |
| `[ROLE_ADMIN, ROLE_OPS]` | Allow | Has both, though only one is needed. |
| `[ROLE_USER]` | Deny | Lacks required authority. |
| `[ADMIN]` | Deny | String lacks `ROLE_` per default convention. |
| `[]` | Deny | Has no matching permission. |

Suppose a business rule requires a user to be both **finance staff** and an **approved order signer**. Using `hasAnyRole("FINANCE", "APPROVED_SIGNER")` has the **wrong semantics** because it lets someone with only one role through. You must express **AND** in an `AuthorizationManager` or supported conditional mechanism.

An admin **does not automatically inherit all other roles** unless a **role hierarchy** is configured. For instance, a user with `ROLE_ADMIN` but without `ROLE_USER` normally does not satisfy `hasRole("USER")`. If admins should inherit user permissions, assign both or configure a role hierarchy used by the framework and the right authorization manager type. Never rely on "ADMIN is bigger than USER so it will definitely be allowed" without tests proving it.

## 5. hasAuthority: Exact Match, Without Adding ROLE_

~~~java
.requestMatchers("/docs/**").hasAuthority("DOCUMENT_READ")
~~~

The rule requires the **exact** authority string `DOCUMENT_READ`, without turning it into `ROLE_DOCUMENT_READ`. If the permission source contains:

~~~text
[DOCUMENT_READ, ROLE_USER, SCOPE_reports.read]
~~~

then `hasAuthority("DOCUMENT_READ")` can grant access, whereas `hasAuthority("ROLE_DOCUMENT_READ")` will not given only that set.

### OAuth2/JWT Scopes

A common pattern in resource servers is mapping a bearer token's scopes into authorities prefixed with `SCOPE_`. For example, the claim `scope: "reports.read reports.write"` can produce `SCOPE_reports.read` and `SCOPE_reports.write` through the appropriate default converter.

Then:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("SCOPE_reports.read")

.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("SCOPE_reports.write")
~~~

These are **exact scope authorities**, not roles. Do not write `hasRole("SCOPE_reports.read")`. That condition would look for `ROLE_SCOPE_reports.read` under the default role convention, completely different from the scopes issued by the resource server.

**Caution:** JWT converters may be customized, and actual claims/authorities may carry different names. Inspect `Authentication.getAuthorities()` **in a development environment with sensitive data redacted** and write unit/integration tests for the converter; do not assume every JWT maps identically.

### Business Permissions

An application can use action-descriptive authorities:

~~~text
INVOICE_VIEW
INVOICE_APPROVE
INVOICE_REFUND
DOCUMENT_READ
DOCUMENT_WRITE
CUSTOMER_EXPORT
~~~

These are strings issued by the **server** and matched directly with `hasAuthority`. Naming permissions clearly keeps policies less coupled to roles: both a manager and an accountant can be granted `INVOICE_VIEW` if business rules allow it.

A role can represent a **broad group of permissions**, while an authority can represent a **specific permission**. However, Spring Security does not force a fixed permission-management schema on you; it matches whatever authority strings the authentication carries. Any role -> permission mapping is a decision of the application or identity provider.

## 6. hasAnyAuthority: One of Multiple Specific Permissions

~~~java
.requestMatchers("/billing/**")
    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
~~~

Under this policy, someone with **BILLING_READ or BILLING_WRITE** can enter. This can be a reasonable design for a shared overview page, yet **unsuitable** for protecting endpoints that **write/modify** billing data if a `BILLING_READ` user would also be accepted.

A better example with distinct HTTP methods:

~~~java
.requestMatchers(HttpMethod.GET, "/billing/invoices/**")
    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
.requestMatchers(HttpMethod.POST, "/billing/invoices/**")
    .hasAuthority("BILLING_WRITE")
.requestMatchers("/billing/invoices/**")
    .denyAll()
~~~

Authorization should follow the **action on the endpoint**, not just the URL group name. A policy for `GET` is not automatically safe for `POST`, `PUT`, `PATCH`, or `DELETE`.

### OR Does Not Mean Inheritance and Does Not Mean AND

Given authorities `[BILLING_READ]`:

~~~text
hasAnyAuthority("BILLING_READ", "BILLING_WRITE") -> true
hasAuthority("BILLING_WRITE")                    -> false
~~~

Given authorities `[ROLE_ADMIN]`:

~~~text
hasAnyAuthority("BILLING_READ", "BILLING_WRITE") -> false
hasAnyRole("ADMIN", "OPS")                        -> true
~~~

There is no implicit link between a general role and every application permission. If an admin should have `BILLING_WRITE`, you must grant that permission when mapping the principal or configure an appropriate role hierarchy/authorization manager and test it. Conditions using the role prefix and scope prefix do not share one namespace.

## 7. An Important Lookup Table

Suppose the actual permission list is:

~~~text
ROLE_ADMIN
ROLE_USER
DOCUMENT_READ
SCOPE_reports.read
~~~

| Rule | Result | Explanation |
| --- | --- | --- |
| `hasRole("ADMIN")` | True | Has `ROLE_ADMIN`. |
| `hasRole("USER")` | True | Has `ROLE_USER`. |
| `hasRole("OPS")` | False | Lacks `ROLE_OPS`. |
| `hasAnyRole("OPS","ADMIN")` | True | Has `ADMIN`, only one needed. |
| `hasAuthority("ADMIN")` | False | Lacks exact string `ADMIN`. |
| `hasAuthority("ROLE_ADMIN")` | True | Has exact string `ROLE_ADMIN`. |
| `hasAnyAuthority("DOCUMENT_WRITE","DOCUMENT_READ")` | True | Has `DOCUMENT_READ`. |
| `hasAuthority("SCOPE_reports.read")` | True | Has matching scope. |
| `hasRole("reports.read")` | False | Condition looks for `ROLE_reports.read`. |
| `hasAnyAuthority("SCOPE_reports.write","ROLE_OPS")` | False | Lacks both listed strings. |

This style of test question is more useful than memorizing API names: **write down the exact list of `GrantedAuthority`s**, turn each rule into a membership/OR check, and determine the result. However, testing with a self-constructed list only proves matching logic; you also need tests verifying that login/JWT converters actually grant the real authorities.

## 8. Applying the Four Methods in authorizeHttpRequests

In Spring Security 6, a Servlet application typically declares:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
    .requestMatchers("/docs/**").hasAuthority("DOCUMENT_READ")
    .requestMatchers("/billing/**")
        .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
    .anyRequest().authenticated());
~~~

This is a **configuration snippet**, requiring a `@Configuration` class, `HttpSecurity`, and `SecurityFilterChain`. Rule declaration order matters: with the standard matcher-based registry, the first rule matching the request picks the `AuthorizationManager` to apply. An overly broad condition placed first can prevent specific rules after it from ever being evaluated.

### Dangerous Ordering Example

~~~java
// ANTI-PATTERN: every URL passes authenticated first,
// and the /admin/** rule below never gets a chance to apply.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    .requestMatchers("/admin/**").hasRole("ADMIN"));
~~~

In some versions, the DSL even prevents configuring matchers after `anyRequest` with a build-time error. Whether it manifests as an exception or an unintended policy, the rule remains **specific rules first, broad rules later**. Do not try to "work around" it by placing `permitAll` at the top of the chain.

### HTTP Method Is Part of the Permission

~~~java
.requestMatchers(HttpMethod.GET, "/api/items/**")
    .hasAuthority("ITEM_READ")
.requestMatchers(HttpMethod.POST, "/api/items/**")
    .hasAuthority("ITEM_WRITE")
.requestMatchers("/api/items/**").denyAll()
~~~

In this configuration, someone with `ITEM_READ` cannot modify via POST; unlisted methods are denied instead of accidentally inheriting read access. **CSRF** is a separate check: in a cookie-session browser chain, POST may be rejected by the CSRF filter **even before** reaching authorization. To test POST permissions, provide a valid CSRF token; otherwise a `403` may merely indicate a missing token rather than verifying `hasAuthority`.

### Distinguishing 401, 403, and Redirect

Do not write a rigid rule saying "wrong role always returns 401". In a web browser:

- Unauthenticated user: may be redirected to form login (`302`) or receive `401` depending on `AuthenticationEntryPoint` and the request.
- Authenticated user missing authority: typically receives `403 Forbidden`.
- Authenticated user with sufficient permission: request proceeds to the controller, though the controller may still reject because the resource does not exist or due to deeper business policies.

Test responses from the **right security chain** and verify authentication state; do not infer role issues from HTTP status alone.

## 9. Complete Spring Boot 3 / Java 17 Example

We will build an application with endpoints demonstrating **all four methods** and real HTTP testing via `MockMvc`. Use Spring Initializr to create a Boot 3.x project with JDK 17+ and dependencies:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test   (test scope)
spring-security-test      (test scope)
~~~

The Java files below live in package `com.example.roleauthority`. A Maven/Gradle project with properly configured dependencies is required; Spring code is not a standalone Java SE program compilable via bare `javac`.

### 9.1. SecurityConfig.java

~~~java
package com.example.roleauthority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-alice-only"))
                .authorities(
                    "ROLE_ADMIN",
                    "DOCUMENT_READ",
                    "BILLING_WRITE",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demo-bob-only"))
                .authorities("ROLE_OPS", "BILLING_READ")
                .build();

        UserDetails cara = User.withUsername("cara")
                .password(encoder.encode("demo-cara-only"))
                .authorities("DOCUMENT_READ", "SCOPE_reports.read")
                .build();

        UserDetails dave = User.withUsername("dave")
                .password(encoder.encode("demo-dave-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, cara, dave);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()

                // Specific HTTP methods must come before general rules.
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports/**").denyAll()

                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
                .requestMatchers("/docs/**")
                    .hasAuthority("DOCUMENT_READ")
                .requestMatchers("/billing/**")
                    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
                .requestMatchers("/user/**").hasRole("USER")

                .requestMatchers("/profile").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());

        // Default CSRF remains enabled for unsafe methods.
        return http.build();
    }
}
~~~

**Reading the configuration accurately:**

1. `GET /api/reports/{id}` requires `SCOPE_reports.read`.
2. `POST /api/reports/{id}` requires `SCOPE_reports.write` **and**, in a CSRF-enabled chain, must pass the CSRF filter.
3. Other methods on `/api/reports/**` hit `denyAll`. Do not infer DELETE is permitted because POST is permitted.
4. `/admin/**` requires `ROLE_ADMIN` (via `hasRole("ADMIN")`).
5. `/ops/**` accepts `ROLE_ADMIN` or `ROLE_OPS` (via `hasAnyRole`).
6. `/docs/**` requires exact `DOCUMENT_READ`.
7. `/billing/**` accepts `BILLING_READ` or `BILLING_WRITE`. This is a read-only demo page; update endpoints need a dedicated rule for WRITE as in section 6.
8. `/user/**` requires `ROLE_USER`; **alice** cannot enter even with `ROLE_ADMIN`, because the demo configures no role hierarchy and Alice lacks `ROLE_USER`.
9. `.anyRequest().denyAll()` denies unlisted routes by default; great for authorization exercises because every new API must have a reviewed policy.
10. `formLogin` provides browser sessions; `httpBasic` adds an easy authentication mechanism for HTTP tests. Never use demo passwords in production; use a real user store/secret policy.

**Never mint authorities from client data:** the Alice/Bob/Cara/Dave list is fixed server-side in the demo's `UserDetailsService`. In production, it must be queried from an access-controlled permission store or mapped from a JWT whose signature/issuer/audience are verified, never from a client-supplied `X-Role` header or JSON `roles`.

### 9.2. AccessController.java

~~~java
package com.example.roleauthority;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccessController {

    @GetMapping("/")
    public String root() {
        return "public-home";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin/panel")
    public String admin() {
        return "admin";
    }

    @GetMapping("/ops/panel")
    public String ops() {
        return "ops";
    }

    @GetMapping("/docs/file")
    public String document() {
        return "document";
    }

    @GetMapping("/billing/invoices")
    public String billing() {
        return "billing";
    }

    @GetMapping("/user/home")
    public String userHome() {
        return "user-home";
    }

    @GetMapping("/profile")
    public String profile(Authentication auth) {
        return auth.getName();
    }

    @GetMapping("/api/reports/{id}")
    public String readReport(@PathVariable String id) {
        return "report:" + id;
    }

    @PostMapping("/api/reports/{id}")
    public String updateReport(@PathVariable String id) {
        // Lesson only returns a string to illustrate security,
        // without actually modifying any report.
        return "updated:" + id;
    }
}
~~~

**Note:** even though the `POST /api/reports/{id}` response does not mutate a DB in this demo, tests still demonstrate **authorization and CSRF at the HTTP boundary**. In production, the controller/service must also check permissions on the **specific resource** (owner, tenant, order/report status...), not just general URLs and roles.

### 9.3. RoleAuthorityApplication.java

~~~java
package com.example.roleauthority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleAuthorityApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleAuthorityApplication.class, args);
    }
}
~~~

The classes above must share package `com.example.roleauthority` or sit inside the main class's component scan. A Spring Boot project that already has its own main class does not need a second main; use a consistent package structure.

### 9.4. Running the Sample Application

In a project with the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Demo requests (on localhost only):

~~~bash
# Public, no login needed:
curl -i http://localhost:8080/public

# Alice has ROLE_ADMIN:
curl -i -u alice:demo-alice-only \
  http://localhost:8080/admin/panel

# Bob has ROLE_OPS but not ROLE_ADMIN:
curl -i -u bob:demo-bob-only \
  http://localhost:8080/ops/panel

# Cara has DOCUMENT_READ:
curl -i -u cara:demo-cara-only \
  http://localhost:8080/docs/file

# Cara can read reports via scope:
curl -i -u cara:demo-cara-only \
  http://localhost:8080/api/reports/42
~~~

With the demo config and credentials, these requests can return `200` with bodies `public`, `admin`, `ops`, `document`, or `report:42` respectively. Do not assert exact fixed `curl -i` headers/stdout since HTTP/container versions can differ. **Never pass real passwords on the command line**: `curl -u` here only illustrates with fake accounts on localhost; command lines/history and process inspection can leak credentials.

With protected POSTs and default CSRF enabled, you cannot simply run `curl -X POST -u ...` and conclude whether an authority works when seeing 403; CSRF may have blocked the request first. Use `MockMvc` with `csrf()` as shown next, or an integrated client that fetches tokens properly.

## 10. Integration Test Suite: Verifying Each Method Properly

Create `src/test/java/com/example/roleauthority/HttpAuthorizationIntegrationTest.java` in the same project with `spring-boot-starter-test` and `spring-security-test`:

~~~java
package com.example.roleauthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void adminRoleAndOpsRoleAreDifferent() throws Exception {
        mvc.perform(get("/admin/panel")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/admin/panel")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/ops/panel")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/ops/panel")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk());
    }

    @Test
    void roleAdminDoesNotAutomaticallyImplyRoleUser()
            throws Exception {
        mvc.perform(get("/user/home")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/user/home")
                    .with(httpBasic("dave", "demo-dave-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("user-home"));
    }

    @Test
    void exactAuthoritiesControlDocumentsAndBilling()
            throws Exception {
        mvc.perform(get("/docs/file")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/docs/file")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/billing/invoices")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/billing/invoices")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void scopeReadDoesNotGrantScopeWrite() throws Exception {
        mvc.perform(get("/api/reports/42")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:42"));

        // Include csrf() to ensure 403 comes from the policy
        // missing SCOPE_reports.write, not from missing CSRF.
        mvc.perform(post("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("updated:42"));
    }

    @Test
    void unsafeRequestStillRequiresCsrf() throws Exception {
        // Alice has write scope but the POST carries no CSRF token.
        mvc.perform(post("/api/reports/42")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedHttpMethodIsDeniedEvenForAdmin()
            throws Exception {
        mvc.perform(delete("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

This is an **integration test through the servlet filter chain**, not a direct call to `AuthorizationManager`. `httpBasic(...)` sends fake Basic credentials to Spring Security; `UserDetailsService` returns authorities; then `AuthorizationFilter` applies each rule. These assertions are more meaningful than constructing a mock `Authentication` object and checking one method's result.

Scenarios proven:

- `hasRole("ADMIN")` accepts Alice with `ROLE_ADMIN`, denies Bob with `ROLE_OPS`.
- `hasAnyRole("ADMIN","OPS")` lets either Alice or Bob pass `/ops/**`.
- `hasAuthority("DOCUMENT_READ")` lets Cara pass `/docs/**` but not Bob.
- `hasAnyAuthority("BILLING_READ","BILLING_WRITE")` accepts Bob with `BILLING_READ`; rejects Cara.
- Alice has `ROLE_ADMIN` but **not** `ROLE_USER`; `/user/**` still returns 403 because no hierarchy is configured.
- Cara only has `SCOPE_reports.read`; allowed to GET but not POST after sending a valid CSRF token. Alice with `SCOPE_reports.write` is allowed to POST.
- `DELETE /api/reports/42` hits deny-all because there is no method rule for DELETE, even for an admin user.
- On a CSRF-enabled web chain, a POST missing a token still gets 403 even when the write authority is present; never attribute every 403 to a missing role.

Run the test suite via Maven Wrapper:

~~~bash
./mvnw test
~~~

Do not cite fixed stdout for Maven/Test because it depends on environment, JDK setup, library versions, and other tests. An advanced practice is verifying the **cause** of a 403 by ensuring the request has valid CSRF and an authenticated user.

### Mock Users vs. Real Authentication

`spring-security-test` also offers `user("test").roles("ADMIN")` or `@WithMockUser(roles="ADMIN")`. They are convenient for **unit-testing authorization**, yet can skip **authority assignment from the user store** or real login. If database role-mapping code is broken, a test using only a mock user with `ROLE_ADMIN` will still stay green.

Therefore, you should have all three:

1. Authority-mapping tests at `UserDetailsService`/JWT converter.
2. HTTP integration tests like above with real fixture credentials (or proper login flow) to prove mapped results reach `AuthorizationManager`.
3. Resource-level/tenant-level permission tests in the service, since URL permissions alone are insufficient to protect individual records.

## 11. Standalone Java 17: Simulating the Four Conditions Exactly

Let's run an experiment without Spring Security dependencies to understand the matching operations. Create `RoleAuthorityDemo.java`:

~~~java
import java.util.Set;

public final class RoleAuthorityDemo {

    static boolean hasAuthority(Set<String> granted, String wanted) {
        return granted.contains(wanted);
    }

    static boolean hasAnyAuthority(
            Set<String> granted, String... wanted) {
        for (String authority : wanted) {
            if (hasAuthority(granted, authority)) {
                return true;
            }
        }
        return false;
    }

    static boolean hasRole(Set<String> granted, String role) {
        if (role.startsWith("ROLE_")) {
            throw new IllegalArgumentException(
                    "Pass role name without ROLE_ prefix");
        }
        return hasAuthority(granted, "ROLE_" + role);
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        for (String role : roles) {
            if (hasRole(granted, role)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN",
                "BILLING_READ",
                "SCOPE_reports.read");

        System.out.println("hasRole(ADMIN)="
                + hasRole(granted, "ADMIN"));
        System.out.println("hasRole(USER)="
                + hasRole(granted, "USER"));
        System.out.println("hasAuthority(ADMIN)="
                + hasAuthority(granted, "ADMIN"));
        System.out.println("hasAuthority(ROLE_ADMIN)="
                + hasAuthority(granted, "ROLE_ADMIN"));
        System.out.println("hasAnyRole(USER,ADMIN)="
                + hasAnyRole(granted, "USER", "ADMIN"));
        System.out.println("hasAnyAuthority(WRITE,READ)="
                + hasAnyAuthority(
                    granted, "BILLING_WRITE", "BILLING_READ"));
        System.out.println("hasAuthority(SCOPE_reports.write)="
                + hasAuthority(granted, "SCOPE_reports.write"));
    }
}
~~~

Compile and run directly with JDK 17+:

~~~bash
javac RoleAuthorityDemo.java
java RoleAuthorityDemo
~~~

**Exact** stdout:

~~~text
hasRole(ADMIN)=true
hasRole(USER)=false
hasAuthority(ADMIN)=false
hasAuthority(ROLE_ADMIN)=true
hasAnyRole(USER,ADMIN)=true
hasAnyAuthority(WRITE,READ)=true
hasAuthority(SCOPE_reports.write)=false
~~~

This program does **not** create a `SecurityFilterChain`, verify passwords, handle HTTP, or execute a real `AuthorizationManager`. It intentionally simulates only the **membership rules** with the default `ROLE_` prefix. The goal is seeing that an authorities entry `ROLE_ADMIN` satisfies `hasRole("ADMIN")` but does **not** satisfy `hasAuthority("ADMIN")`.

Do not confuse this Java SE role check with complete security assurance: in a real system, authorities must come from a trusted server source, policies must live in the proper Spring Security chain, and data-writing endpoints must enforce CSRF or tokens/permissions per design.

## 12. Safely Mapping Roles from a Database

A system often stores roles as `ADMIN`, `OPS`, `USER`. `UserDetailsService` or a server-side adapter should convert them into prefixed authorities matching the active policy:

~~~java
// SNIPPET: roles is a String collection from a trusted server source.
List<GrantedAuthority> mapped = roles.stream()
    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
    .toList();
~~~

This snippet requires importing `java.util.List`, `GrantedAuthority`, and `SimpleGrantedAuthority`, plus a `roles` variable from a trusted data store. It must **never** be used with `roles` read from client-sent JSON/headers. Before prepending the prefix, verify stored data does not already contain `ROLE_` to avoid creating `ROLE_ROLE_ADMIN`.

If data has a `role_name` column and a `permission_code` column, separate the mappings clearly:

~~~text
role_name="ADMIN" -> "ROLE_ADMIN"
permission_code="DOCUMENT_READ" -> "DOCUMENT_READ"
oauth_scope="reports.read" -> "SCOPE_reports.read"
~~~

In a multi-tenant model, `ROLE_ADMIN` in tenant A **does not by default** allow accessing tenant B's data. A general authority only describes a *permission group*; resource/tenant access control must also verify the trusted tenant ID in the service or policy. Never rely solely on a role name to confirm ownership.

### Never Accept Permissions from the Client

Patterns like the following are **wrong**:

~~~java
// ANTI-PATTERN: NEVER grant roles from HTTP input.
String role = request.getHeader("X-Role");
return User.withUsername(username)
    .password(passwordHash)
    .authorities(role)
    .build();
~~~

If a user can set `X-Role: ROLE_ADMIN` themselves, they can escalate their own privileges. The proper trust chain is: server verifies identity using checked credentials -> queries/assigns authorities from an access-controlled source -> Spring Security authorization matches against them.

With JWTs, only trust scopes/roles from a token after verifying **signature, algorithm, issuer, audience, expiration**, and relevant claims. A converter may be needed to name `SCOPE_` or `ROLE_` per policy; never copy unverified claims into `Authentication`.

## 13. Role Hierarchy, ROLE_ Prefix, and Custom Configuration

### Role Hierarchy Does Not Exist Automatically

If an organization defines ADMIN as "including" USER, Spring Security only knows this when:

- You actually grant both `ROLE_ADMIN` and `ROLE_USER` to the user; **or**
- You configure a **`RoleHierarchy`** and ensure the HTTP `AuthorizationManager` and related policies actually use that hierarchy.

Example describing the relationship:

~~~text
ROLE_ADMIN > ROLE_OPS
ROLE_OPS   > ROLE_USER
~~~

This is a **configurable business rule**, not a default. Several APIs/hooks for wiring `RoleHierarchy` into Spring Security have evolved across versions; therefore test real requests rather than defining a bean and assuming every checker—including method security—automatically uses it.

For specialized permissions, you can **grant specific permissions to roles** when constructing `Authentication` instead of relying on hierarchy. That keeps `hasAuthority("DOCUMENT_READ")` consistent between authorization and security audits. Never "add `ROLE_ADMIN` to every account" to fix a 403 error.

### Customizing the ROLE_ Prefix

Spring Security has the `GrantedAuthorityDefaults` concept to adjust the default role prefix in **supporting components**, such as certain expression/method authorization mechanisms. However, do not assume declaring a prefix-changing bean immediately makes **every** `hasRole` call in `authorizeHttpRequests` switch to the new prefix: the `AuthorityAuthorizationManager`-based DSL has specific behavior depending on API/version.

A simple, easy-to-test approach when using a non-standard authority prefix system is **using `hasAuthority("EXACT_STRING")`** in HTTP rules, and documenting the exact format emitted by the provider. If the system uses the default `ROLE_`, `hasRole("ADMIN")` expresses intent cleanly without inventing custom prefixes.

### Use hasAuthority or hasRole Across Multiple Systems?

- App-internal roles only: `hasRole("ADMIN")` with consistent `ROLE_ADMIN` mapping.
- Permissions from a policy server: `hasAuthority("INVOICE_APPROVE")`.
- OAuth2/JWT scopes: typically `hasAuthority("SCOPE_invoice.approve")`, depending on converter.
- Roles/authorities from SSO/LDAP: verify actual format before picking an API. Do not assume every directory group is automatically translated to `ROLE_...`.

## 14. What Are the Limits of Path-Based Authorization?

A single `/orders/**.hasRole("ADMIN")` rule is not enough to protect all data types. HTTP authorization generally governs **access to an endpoint category**, whereas specific object authorization requires deeper conditions:

- **IDOR/BOLA:** a user with `ORDER_READ` does not automatically gain rights to read **every** order by swapping IDs.
- **Tenant isolation:** an admin of tenant A is not a system-wide admin; tenant and resource ownership must be checked from a trusted source.
- **HTTP method override:** test `POST`, `PUT`, `PATCH`, `DELETE`, and handler mappings so write routes do not slip through a read rule.
- **Forward/include/error dispatch:** applications have different dispatcher types; verify authorization when using internal forwards, error pages, and custom servlet filters. Do not set overly broad `permitAll` just to let error messages render.
- **Multiple SecurityFilterChains:** the first matching chain handles the request; the same URL can face different policies depending on `securityMatcher` and `@Order`. Looking at only one `authorizeHttpRequests` snippet is not enough if requests hit another chain.
- **Static resources and health:** explicitly decide which routes are public; `permitAll()` on public resources differs from skipping the security filter chain entirely.
- **Custom AuthenticationProvider:** if a provider produces an authenticated result with missing/wrong authorities, the role checker behaves correctly on **wrong data**. You must also test the authority-assignment step.

### Separating Role Permissions from Feature Flags

A feature flag showing an "Edit" button is purely a UI control; the API must still check `ITEM_WRITE`. Conversely, a `403` does not mean the frontend must always completely hide a resource; the app can display an "insufficient permissions" state and a controlled access-request workflow.

### hasAnyAuthority Can Cause Overgranting

Many developers write:

~~~java
.requestMatchers("/payments/**")
    .hasAnyAuthority("PAYMENTS_VIEW", "PAYMENTS_REFUND")
~~~

If `/payments/refund` is covered by this rule and has no specific earlier rule, a user with only `PAYMENTS_VIEW` can enter the refund handler — a serious authorization flaw. Split it instead:

~~~java
.requestMatchers(HttpMethod.POST, "/payments/refund")
    .hasAuthority("PAYMENTS_REFUND")
.requestMatchers(HttpMethod.GET, "/payments/**")
    .hasAnyAuthority("PAYMENTS_VIEW", "PAYMENTS_REFUND")
.requestMatchers("/payments/**").denyAll()
~~~

This configuration is an **illustrative snippet**, omitting beans/imports/controller methods. Note that POST also needs CSRF in a cookie-based browser chain. The pattern "specific write rules first, broader read rules later, deny other methods" is easier to verify than an overly broad wildcard grant.

## 15. Step-by-Step 403 Diagnosis

When rules are already in place yet a user gets 403, verify in order:

1. **Right security chain?** Which chain does `FilterChainProxy` select for the URL and method? Are there other `securityMatcher`s or `@Order`s?
2. **Is the user really authenticated?** Does `Authentication` come from form/session, HTTP Basic, bearer JWT, or mock? Is it `AnonymousAuthenticationToken`?
3. **What are the exact authorities?** Count/contents from the server-side principal after authentication; never print passwords/tokens to logs.
4. **Which rule matched first?** Is there a `/**`, `permitAll`, `authenticated`, or `deny` wildcard before your intended rule?
5. **Does the role string have the prefix?** `hasRole("ADMIN")` looks for `ROLE_ADMIN` in the default configuration; `hasAuthority("ADMIN")` looks for `ADMIN`.
6. **Does `hasAny...` use OR as expected?** Missing both A and B fails; if you wanted both, does the current policy have the wrong semantics?
7. **Does the HTTP method match?** GET works, POST might not; verify the specific `HttpMethod` rule.
8. **Did CSRF block first?** For POST/PUT/PATCH/DELETE in a cookie-based web chain, send a valid token to test authorization.
9. **Did a service-level rule block?** Is there `@PreAuthorize`, `@PostAuthorize`, or a service-side tenant/ownership check?
10. **Do URL variants match differently?** Context paths, trailing slashes, casing, encoded paths, reverse proxies, and Servlet dispatch types must be tested against actual deployment.

Never fix a 403 by changing `hasRole("ADMIN")` to `permitAll()` just to make the request "work". That destroys the security boundary instead of fixing the mapping/policy bug.

## 16. Testing Both "Unauthorized" and "Authorized"

A reliable authorization test suite usually has a matrix:

| User (Server-Issued) | GET /admin/panel | GET /ops/panel | GET /docs/file | GET /billing/invoices | GET /api/reports/42 | POST /api/reports/42 with CSRF |
| --- | --- | --- | --- | --- | --- | --- |
| Alice: ROLE_ADMIN, DOCUMENT_READ, BILLING_WRITE, scope read/write | 200 | 200 | 200 | 200 | 200 | 200 |
| Bob: ROLE_OPS, BILLING_READ | 403 | 200 | 403 | 200 | 403 | 403 |
| Cara: DOCUMENT_READ, scope read | 403 | 403 | 200 | 403 | 200 | 403 |
| Dave: ROLE_USER | 403 | 403 | 403 | 403 | 403 | 403 |

The `200` and `403` values are shown for the demo controller/configuration above, when **the user is authenticated with the right fixture** and unsafe requests carry a valid CSRF token. If the request is unauthenticated, the HTTP status may differ due to the entry point.

In practice, also add:

- Positive and negative tests for **each rule**.
- Tests verifying **unlisted methods** are not granted overly broad access by a fallback.
- **Anonymous** tests confirming unauthenticated users cannot reach protected resources.
- Tests for role -> `GrantedAuthority` mappers, JWT authority converters, and `RoleHierarchy` configuration if present.
- Tests across multiple chains (JWT API / session UI) if the application combines them.
- Resource-level tests: user A cannot read/write tenant B's resources even with the same role.
- Error policy tests (403/401/redirect) ensuring no sensitive data leakage or username enumeration.

### Why Should You Not Assert Status Alone?

An endpoint can return `403` due to missing CSRF, not role. An endpoint can return `404` because the controller route does not exist, failing to prove the authorization rule works. A `200` can come from `permitAll` on a broader matcher rather than the intended authority check.

Therefore verify authentication state, exact request path/method, CSRF, matched rule, and response content. For production security regression, instrument authorization decisions/metrics at a level that exposes no sensitive data.

## 17. Common Mistakes in Code Review

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `hasRole("ROLE_ADMIN")` | May fail configuration due to passing prefix into role API. | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`. |
| `hasAuthority("ADMIN")` when user only has `ROLE_ADMIN` | 403 due to string mismatch. | Align mapper or use the role API. |
| `roles("ROLE_ADMIN")` on `UserBuilder` | May throw error because input already has prefix. | Use `roles("ADMIN")` or `authorities("ROLE_ADMIN")`. |
| `hasAnyAuthority("READ","WRITE")` protecting a WRITE endpoint | Users with only READ can enter. | Use `hasAuthority("WRITE")` for writes. |
| `hasAnyRole("A","B")` to require both A and B | Only one role is enough to pass. | Use AND / custom manager. |
| Assuming `ROLE_ADMIN` automatically includes `ROLE_USER` | Admin may get 403 on user paths. | Grant both or configure a hierarchy. |
| Granting permissions from client headers/body | Attackers escalate privileges themselves. | Load authorities from store/trusted claims after authentication. |
| Placing `anyRequest().authenticated()` before sensitive rules | Broad matcher can drop role policies. | Specific rules first, fallback last. |
| Ignoring `HttpMethod` | Read-only users can hit write endpoints. | Constrain methods and default-deny. |
| POST test without CSRF | 403 does not prove missing authority. | Use `csrf()` in MockMvc. |
| Testing only with `@WithMockUser` | Misses user store/JWT converter mapping bugs. | Include end-to-end credential -> authorities tests. |
| Checking only URL, ignoring ownership | IDOR/BOLA and cross-tenant access. | Enforce resource-level authorization. |
| Relying on role prefix config in one place | Other checkers may use different semantics. | Verify exact Java DSL, method/security API of target version. |
| No deny fallback for new routes | New URLs can be accessed unintentionally. | Use `anyRequest().denyAll()` when appropriate, test coverage. |

## 18. Self-Check Exercises

**Exercise 1.** A user has `ROLE_STAFF` and `DOCUMENT_READ`, without `ROLE_MANAGER`. Does `hasAnyRole("MANAGER","STAFF")` allow them?  
**Answer:** Yes, because `ROLE_STAFF` is granted and `hasAnyRole` uses OR.

**Exercise 2.** A user has `ROLE_ADMIN` but not `ADMIN`. Does `hasAuthority("ADMIN")` match?  
**Answer:** No. Authority checking is an **exact string** match.

**Exercise 3.** When is `hasRole("ADMIN")` equivalent to `hasAuthority("ROLE_ADMIN")`?  
**Answer:** When the standard `ROLE_` prefix convention is used and no custom rule semantics alter how checks work. This is the common case in `authorizeHttpRequests`.

**Exercise 4.** To require both `INVOICE_VIEW` **and** `INVOICE_APPROVE`, is `hasAnyAuthority("INVOICE_VIEW","INVOICE_APPROVE")` right?  
**Answer:** Wrong. That method uses OR; you need AND per an appropriate policy.

**Exercise 5.** A user has `SCOPE_reports.read` but not `SCOPE_reports.write`. With method-specific rules, what happens on report GET and POST?  
**Answer:** GET is allowed, POST is denied (once POST passes valid CSRF to reach authorization).

**Exercise 6.** Why does `ROLE_ADMIN` not automatically satisfy `hasRole("USER")`?  
**Answer:** Because `ROLE_USER` is not in the `GrantedAuthority` list unless the application granted that role or configured an active hierarchy.

**Exercise 7.** A POST test returns `403` due to missing CSRF. Can you conclude `hasAuthority("WRITE")` works properly?  
**Answer:** No. The request may be blocked by `CsrfFilter` before authorization. Use a valid token and test users with and without `WRITE`.

**Exercise 8.** With multiple `SecurityFilterChain`s, why might a correct rule in chain A still fail to protect a URL?  
**Answer:** The request may match chain B first; check each chain's `securityMatcher` and `@Order`.

**Exercise 9.** If the frontend hides the "Refund" button for users lacking permission, can the backend omit `hasAuthority("PAYMENTS_REFUND")`?  
**Answer:** No. Client/UI can be modified or HTTP called directly; enforcement must happen on the server with ownership checks when needed.

**Exercise 10.** Should you choose `hasRole` or `hasAuthority` for a scope converted to `SCOPE_orders.read`?  
**Answer:** `hasAuthority("SCOPE_orders.read")`, because it looks for the exact server-issued scope string without prepending `ROLE_`.

## 19. Closing Checklist

- [ ] Distinguished authentication, HTTP authorization, and resource-level permission.
- [ ] Know the exact strings contained in `Authentication.getAuthorities()`.
- [ ] `hasRole("X")` is understood as `ROLE_X` under the default prefix, without passing `ROLE_` explicitly.
- [ ] Both `hasAnyRole` and `hasAnyAuthority` use **OR**.
- [ ] `hasAuthority` does not prepend `ROLE_` and suits exact-string permissions/scopes.
- [ ] Roles/permissions are issued from a trusted server source, never client input.
- [ ] URL-specific and method-specific matchers precede broad fallbacks.
- [ ] Write endpoints are protected by WRITE, not READ OR WRITE.
- [ ] Default deny exists for unapproved methods/URLs when appropriate for the architecture.
- [ ] CSRF/session/token policies are tested according to the threat model.
- [ ] Positive/negative integration tests exist with `MockMvc` plus mapper/claims tests.
- [ ] If using role hierarchy or a custom prefix, real behavior is tested on the running Spring Security version.
- [ ] Tenant, ownership, or per-record authorization is checked for APIs that require it.

**Key takeaway:** `hasRole` and `hasAnyRole` are convenient syntax for **roles with the `ROLE_` prefix**; `hasAuthority` and `hasAnyAuthority` perform **exact `GrantedAuthority` string matching**. Both `hasAny...` methods use **OR**, not AND. In HTTP authorization, the final decision also depends on **the right `SecurityFilterChain`, the right path/method, the right matcher order, and server-verified authorities**.
