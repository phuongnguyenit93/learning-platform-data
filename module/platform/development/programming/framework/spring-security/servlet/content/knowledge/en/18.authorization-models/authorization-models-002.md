# The ROLE_ Prefix and GrantedAuthorityDefaults in Spring Security Servlet

> **Topic:** Spring Security - servlet. **Category:** Authorization models. **Examples:** Java 17+, Spring Boot 3.x, Spring Security 6.x. This article explains how `GrantedAuthority` represents privileges, the default meaning of `ROLE_`, the difference between HTTP authorization and method security when using `GrantedAuthorityDefaults`, along with examples and tests to avoid 403 errors caused by prefix mismatches.

## 1. The Typical Problem: Successfully Logged In Yet Still Denied

User `alice` has logged in, but `Authentication.getAuthorities()` contains:

```text
ADMIN
REPORT_READ
```

The application uses:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

In Spring Security 6 with the standard HTTP authorization manager, `hasRole("ADMIN")` requires the authority **`ROLE_ADMIN`**, not `ADMIN`. The user is **authenticated**, yet **lacks the exact authority string**, so the request can receive 403 Forbidden.

There are two proper ways to fix this:

- Change the HTTP rule to `.hasAuthority("ADMIN")` if the identity source intentionally issues the `ADMIN` string.
- Keep `.hasRole("ADMIN")` if the authority data is normalized to `ROLE_ADMIN`.

`GrantedAuthorityDefaults("")` lets you change the default role prefix in **components that support reading the bean**; it does not automatically rewrite all HTTP rules, tokens, users, or authorities.

**Key takeaway:** you must know **which exact string** Spring Security is comparing against, rather than just looking for the word "role" or "admin" in a database column name.

## 2. `GrantedAuthority` and Role Are Two Conceptual Layers

Spring Security uses `Authentication` to represent an authenticated identity. Its `getAuthorities()` property holds the `GrantedAuthority` instances available during authorization.

Condensed contract:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

This is an illustrative API signature, not a standalone Java source file. Common implementations:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("ROLE_EDITOR");
new SimpleGrantedAuthority("REPORT_READ");
new SimpleGrantedAuthority("ORDER_APPROVE");
new SimpleGrantedAuthority("SCOPE_orders.read");
```

Each `SimpleGrantedAuthority` stores a **privilege string**. The interface has no role enum or `isPermission` boolean. The meaning of the string is defined by the application and the authorization managers:

| Example | Possible convention | Automatically understood system-wide? |
| --- | --- | --- |
| `ROLE_ADMIN` | Administrative role | `hasRole` usually expects `ROLE_`, but hierarchy must be configured separately |
| `ROLE_SUPPORT` | Support role | Does not automatically include ADMIN privileges |
| `REPORT_READ` | Report-reading permission | Use `hasAuthority("REPORT_READ")` |
| `SCOPE_orders.read` | Converted OAuth2 scope | Use exact authority, not `hasRole("orders.read")` |
| `TENANT_42_READ` | Example tenant-scoped privilege | Requires clear mapping/trust-boundary design |

Successful authentication does not mean access to every endpoint. Authorization may still require owner/tenant checks, resource type, account state, and business operations.

## 3. `ROLE_` Is a Convention Prefix, Not an Auto-Generated Permission

Spring Security has a long-standing convention: the logical role name is `ADMIN`, while when represented as an authority it is typically `ROLE_ADMIN`.

```text
Logical role:         ADMIN
Authority string:     ROLE_ADMIN

Logical role:         OPS
Authority string:     ROLE_OPS

Permission string:    REPORT_READ
OAuth scope string:   SCOPE_orders.read
```

Important checks:

- `hasAuthority("ADMIN")` looks for exact `ADMIN`.
- `hasAuthority("ROLE_ADMIN")` looks for exact `ROLE_ADMIN`.
- `hasRole("ADMIN")` in Spring Security 6 HTTP `AuthorityAuthorizationManager` checks `ROLE_ADMIN`.
- `hasAnyAuthority("REPORT_READ", "REPORT_WRITE")` matches the exact list passed in.
- `hasAnyRole("ADMIN", "OPS")` uses the role convention and is not equivalent to `hasAnyAuthority("ADMIN", "OPS")`.

### Default Comparison Table

| Principal's authorities | HTTP rule | String match result |
| --- | --- | --- |
| `["ROLE_ADMIN"]` | `hasRole("ADMIN")` | Match |
| `["ADMIN"]` | `hasRole("ADMIN")` | No match |
| `["ROLE_ADMIN"]` | `hasAuthority("ROLE_ADMIN")` | Match |
| `["ROLE_ADMIN"]` | `hasAuthority("ADMIN")` | No match |
| `["ADMIN"]` | `hasAuthority("ADMIN")` | Match |
| `["REPORT_READ"]` | `hasAuthority("REPORT_READ")` | Match |
| `["REPORT_READ"]` | `hasRole("REPORT_READ")` | No match without `ROLE_REPORT_READ` |
| `["SCOPE_orders.read"]` | `hasAuthority("SCOPE_orders.read")` | Match |
| `["SCOPE_orders.read"]` | `hasRole("orders.read")` | No match |

This table covers only authority matching for the APIs listed above, excluding role hierarchies or custom authorization managers.

### Should You Pass `hasRole("ROLE_ADMIN")`?

**No.** The `AuthorityAuthorizationManager.hasRole` API in Spring Security 6 applies `ROLE_` automatically and can reject arguments that already start with the prefix.

```java
// Use the logical role name:
.hasRole("ADMIN")

// Or match the full authority string:
.hasAuthority("ROLE_ADMIN")

// Avoid:
.hasRole("ROLE_ADMIN")
```

Do not pass a value into `hasRole` just because it matches a literal stored in the DB; understand whether the method prepends the prefix automatically.

## 4. `roles()` Differs from `authorities()` When Building `UserDetails`

The User builder has two similar-looking APIs:

```java
UserDetails first = User.withUsername("first")
    .password(encodedPassword)
    .roles("ADMIN")
    .build();

UserDetails second = User.withUsername("second")
    .password(encodedPassword)
    .authorities("ADMIN")
    .build();
```

This is a fragment requiring a valid `encodedPassword`, imports, and surrounding context.

- `roles("ADMIN")` typically creates `SimpleGrantedAuthority("ROLE_ADMIN")`.
- `authorities("ADMIN")` creates the authority with the exact string `ADMIN`.

Resulting `getAuthorities()`:

```text
first  -> [ROLE_ADMIN]
second -> [ADMIN]
```

**Important:** even if you add `GrantedAuthorityDefaults("")`, `User.UserBuilder.roles("ADMIN")` does not automatically switch to `authorities("ADMIN")`. The two APIs have separate contracts.

The same issue often occurs in tests:

- `@WithMockUser(roles = "ADMIN")` or `user("u").roles("ADMIN")` grants `ROLE_ADMIN`.
- `@WithMockUser(authorities = "ADMIN")` or `user("u").authorities(...)` grants `ADMIN`.

If production stores the authority `ADMIN` while the test fixture creates `ROLE_ADMIN`, the test can produce false positives or false negatives compared to real data.

## 5. What Is the `GrantedAuthorityDefaults` Bean?

Spring Security provides `org.springframework.security.config.core.GrantedAuthorityDefaults`. It configures **the default role prefix for components designed to read it**.

Example empty prefix:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("");
}
```

Or if your organization follows a different naming convention:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
```

These two fragments are **alternatives**; do not declare two beans of the same type with conflicting values in one configuration.

An empty prefix can make the method-security expression `hasRole('ADMIN')` check for the `ADMIN` authority instead of `ROLE_ADMIN`, **provided the relevant expression handler uses that bean**.

### What Does This Bean NOT Do?

It does **not**:

- Mutate strings inside `Authentication.getAuthorities()` for the current session.
- Strip prefixes from an existing `SimpleGrantedAuthority("ROLE_ADMIN")`.
- Change the behavior of `User.withUsername(...).roles("ADMIN")`.
- Rewrite roles/authorities inside JWTs or the database.
- Change the `SCOPE_` prefix of OAuth2 converters.
- Automatically create a role hierarchy or grant new privileges to users.
- Guarantee that every `hasRole` API across all Spring Security versions is configured identically.

Distinguishing between **changing how matching works** and **changing the granted data** is the key to avoiding mismatches.

### Why Declare It as a Static Bean?

Some method-security infrastructure beans may be instantiated early during configuration. In Spring Security 6, declaring `static @Bean GrantedAuthorityDefaults` helps ensure the bean is discovered in time when the expression handler needs it. When using a custom handler, verify that the handler actually receives the default role prefix.

## 6. Method Security: `@PreAuthorize` Can Use the Configured Prefix

Example:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("");
    }
}
```

This fragment needs the appropriate Spring imports. In many Spring Security 6 setups, the method-security expression handler picks up the empty prefix. When it does:

```java
@PreAuthorize("hasRole('OPS')")
public void runOperations() {
    // Business logic...
}
```

will require the `OPS` authority instead of `ROLE_OPS`.

Remember:

- `@EnableMethodSecurity` must actually enable method interception.
- The annotation must execute through a **Spring-managed proxy**; self-invocation of a method within the same bean can bypass interception.
- A custom `MethodSecurityExpressionHandler` may configure a different prefix; inspect the application context instead of guessing.
- `@PreAuthorize("hasAuthority('OPS')")` matches exact `OPS` and depends less on prefix configuration.
- Method security does not replace checking resource ownership/tenant membership. A global role does not automatically grant access to every record.

## 7. Spring Security 6 API Warning: HTTP `hasRole` Differs from Method Expressions

In standard HTTP `authorizeHttpRequests`, `hasRole("OPS")` is delegated to `AuthorityAuthorizationManager.hasRole("OPS")`, which uses the `ROLE_` prefix convention.

That can happen even if you have declared:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("");
}
```

**Do not assume** this bean causes every HTTP `hasRole("OPS")` call to check `OPS`. An unambiguous HTTP rule for the `OPS` authority is:

```java
.requestMatchers("/ops/**").hasAuthority("OPS")
```

When the default convention is desired, using the `ROLE_OPS` authority together with `hasRole("OPS")` is also valid.

### Illustrating the Difference

Suppose the principal holds authorities `[OPS]`, and the `GrantedAuthorityDefaults("")` bean is used by the method handler:

```text
HTTP authorizeHttpRequests().hasRole("OPS")
  -> typically checks ROLE_OPS
  -> principal only has OPS -> denied

Method @PreAuthorize("hasRole('OPS')")
  -> method expression handler used the empty prefix
  -> checks OPS -> allowed
```

This is the behavior of the specific engines/configurations described in this article, **not a guarantee for every major version or custom manager**.

| API | Authority checked |
| --- | --- |
| HTTP `hasAuthority("OPS")` | `OPS` |
| HTTP `hasRole("OPS")` via `AuthorityAuthorizationManager` in Security 6 | `ROLE_OPS` |
| Method `hasAuthority('OPS')` | `OPS` |
| Method `hasRole('OPS')` | Per the expression handler's default prefix |
| `User.roles("OPS")` | Grants `ROLE_OPS` |
| `User.authorities("OPS")` | Grants `OPS` |
| Test `user("x").roles("OPS")` | Grants `ROLE_OPS` |
| Test `user("x").authorities(new SimpleGrantedAuthority("OPS"))` | Grants `OPS` |

When a project uses legacy `authorizeRequests`/web expressions or a custom authorization manager, verify the semantics explicitly. Do not carry assumptions from one engine to another without testing.

## 8. Plain Java 17: An Easy-to-Follow Matching Model

The following program is **standalone, compilable with javac**, and models exact vs. prefix-prepended matching. This is purely an educational model, **not Spring Security's actual implementation**.

Create `RolePrefixModel.java`:

```java
import java.util.Set;

public class RolePrefixModel {
    static boolean hasAuthority(Set<String> granted, String exact) {
        return granted.contains(exact);
    }

    static boolean hasRole(
            Set<String> granted, String role, String prefix) {
        return granted.contains(prefix + role);
    }

    public static void main(String[] args) {
        Set<String> prefixed = Set.of("ROLE_ADMIN", "REPORT_READ");
        Set<String> plain = Set.of("ADMIN", "REPORT_READ");

        System.out.println("prefixed.default="
            + hasRole(prefixed, "ADMIN", "ROLE_"));
        System.out.println("plain.default="
            + hasRole(plain, "ADMIN", "ROLE_"));
        System.out.println("plain.custom="
            + hasRole(plain, "ADMIN", ""));
        System.out.println("prefixed.exact="
            + hasAuthority(prefixed, "ROLE_ADMIN"));
        System.out.println("plain.permission="
            + hasAuthority(plain, "REPORT_READ"));
    }
}
```

Run with JDK 17+:

```bash
javac RolePrefixModel.java
java RolePrefixModel
```

Exact stdout from this code:

```text
prefixed.default=true
plain.default=false
plain.custom=true
prefixed.exact=true
plain.permission=true
```

In real Spring Security, the prefix is determined by the **active** authorization manager/expression handler and is not necessarily passed as a parameter like in the demo function.

## 9. Spring Boot 3 / Security 6 App Demonstrating All Three Checks

We write a Servlet MVC app with:

- `GET /http/exact`: HTTP `hasAuthority("OPS")`.
- `GET /http/role`: HTTP `hasRole("OPS")`.
- `GET /method/role`: HTTP only requires `authenticated()`, while the service method is protected with `@PreAuthorize("hasRole('OPS')")` and an empty method prefix.

Demo users:

| User | Authorities | Expected result |
| --- | --- | --- |
| `ops` | `OPS` | Can access `/http/exact`, `/method/role`; denied on `/http/role` |
| `legacy` | `ROLE_OPS` | Can access `/http/role`; denied on `/http/exact`, `/method/role` |
| `viewer` | `REPORT_READ` | Logs in successfully, but lacks privileges for all three endpoints |

Two naming conventions are intentionally included for **comparison**, not as a production design to keep permanently.

### Gradle Dependencies

In a Spring Boot 3.x Java 17 Gradle project that already has plugin/dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### Complete Java File

Create `src/main/java/example/roles/RolePrefixApplication.java`:

```java
package example.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.core.GrantedAuthorityDefaults;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RolePrefixApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolePrefixApplication.class, args);
    }
}

@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/http/exact").hasAuthority("OPS")
                .requestMatchers("/http/role").hasRole("OPS")
                .requestMatchers("/method/role").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails ops = User.withUsername("ops")
            .password(encoder.encode("ops-pass"))
            .authorities("OPS")
            .build();

        UserDetails legacy = User.withUsername("legacy")
            .password(encoder.encode("legacy-pass"))
            .authorities("ROLE_OPS")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .authorities("REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(ops, legacy, viewer);
    }
}

@Service
class ReportService {

    @PreAuthorize("hasRole('OPS')")
    public String methodReport() {
        return "method allowed";
    }
}

@RestController
class DemoController {
    private final ReportService reportService;

    DemoController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/http/exact")
    String exactPage() {
        return "exact allowed";
    }

    @GetMapping("/http/role")
    String rolePage() {
        return "http role allowed";
    }

    @GetMapping("/method/role")
    String methodPage() {
        return reportService.methodReport();
    }
}
```

This snippet uses one top-level public class matching the Java file name and package-private classes for the rest, which is valid in Java 17. `@SpringBootApplication` scans package `example.roles`; `ReportService` is a Spring-managed `@Service`, so calls from the controller go through the method-security proxy.

**Explanation:**

1. `@EnableMethodSecurity` enables interceptors supporting `@PreAuthorize`.
2. `static @Bean GrantedAuthorityDefaults("")` configures the method expression prefix according to the supporting component's contract.
3. HTTP `hasRole("OPS")` and HTTP `hasAuthority("OPS")` are intentionally placed on two separate endpoints to test.
4. Users are created with `authorities(...)` for exact strings, rather than `roles(...)` which would prepend `ROLE_`.
5. `.formLogin(Customizer.withDefaults())` enables form login and the default login page when not customized.
6. Demo passwords are hashed with the delegating encoder; never use demo credentials/keys in production.

### Running the Application

In the Gradle project root containing the wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Visit `http://localhost:8080/public`; expected response body:

```text
public
```

After logging in as `ops` / `ops-pass`:

```text
GET /http/exact  -> HTTP 200, body "exact allowed"
GET /http/role   -> HTTP 403
GET /method/role -> HTTP 200, body "method allowed"
```

With user `legacy` / `legacy-pass`:

```text
GET /http/exact  -> HTTP 403
GET /http/role   -> HTTP 200, body "http role allowed"
GET /method/role -> HTTP 403
```

This is the **expected behavior from the configuration**, not verified by executing the application in this article. Use two independent browser profiles/cookie jars so a previous user's session does not skew results.

## 10. MockMvc Tests for Both HTTP and Method Authorization

Tests should construct authorities **exactly as production does**, without using the `roles(...)` helper when unprefixed authorities are intended.

Create `src/test/java/example/roles/RolePrefixSecurityTest.java`:

```java
package example.roles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RolePrefixSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousProtectedRequestStartsFormLogin() throws Exception {
        mvc.perform(get("/http/exact"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void exactAuthorityOnlyAcceptsOps() throws Exception {
        mvc.perform(get("/http/exact")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("exact allowed"));

        mvc.perform(get("/http/exact")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void httpHasRoleRequiresRoleOpsInSecurity6() throws Exception {
        mvc.perform(get("/http/role")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("http role allowed"));

        mvc.perform(get("/http/role")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodHasRoleUsesConfiguredEmptyPrefix() throws Exception {
        mvc.perform(get("/method/role")
                .with(user("ops").authorities(
                    new SimpleGrantedAuthority("OPS"))))
            .andExpect(status().isOk())
            .andExpect(content().string("method allowed"));

        mvc.perform(get("/method/role")
                .with(user("legacy").authorities(
                    new SimpleGrantedAuthority("ROLE_OPS"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherAuthorityDoesNotGrantOpsRights() throws Exception {
        mvc.perform(get("/http/exact")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isForbidden());

        mvc.perform(get("/method/role")
                .with(user("viewer").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isForbidden());
    }
}
```

Run command:

```bash
./gradlew test
```

These tests are **expected assertions**, not executed while authoring the article. `SecurityMockMvcRequestPostProcessors.user` sets up an already-authenticated principal to test authorization; it does not verify credentials through `UserDetailsService`. To test login end-to-end, POST to `/login` with `csrf()`, valid/invalid passwords, and session handling.

**Do not confuse test principals:** `user("ops").roles("OPS")` produces `ROLE_OPS` and alters what is being tested. To simulate the `OPS` authority, use `authorities(new SimpleGrantedAuthority("OPS"))`.

### If Method Tests Do Not Behave as Expected

Check the application version, `@EnableMethodSecurity`, proxy interception, whether the `GrantedAuthorityDefaults` bean is used by the method expression handler, that no custom bean sets a different prefix, that the service is not calling itself via self-invocation, and that `SecurityContext` in the test holds the expected authorities.

## 11. When Should You Skip Prefix Matching and Use `hasAuthority`?

A clean convention can use exact authorities at **both HTTP and method layers**:

```java
// HTTP rule:
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")

// Method rule:
@PreAuthorize("hasAuthority('ORDER_READ')")
public Order getOrder(long id) {
    // Still need to check ownership/tenant.
    return orderRepository.findById(id).orElseThrow();
}
```

This is a fragment requiring real model/repository types, not a standalone runnable file. `hasAuthority` simplifies the matching contract, though the application must still manage issuer/tenant, account state, and per-record permissions.

Another system may keep `ROLE_ADMIN` for role groups and `ORDER_READ` for permissions. That is equally reasonable when mappings and rules are consistent:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/orders/**").hasAuthority("ORDER_READ")
```

There is no single mandatory prefix choice for every project. The critical requirement is **unambiguous representation**.

## 12. JWT and `JwtGrantedAuthoritiesConverter`: `SCOPE_` Is Not `ROLE_`

When Spring Security Resource Server converts JWT `scope`/`scp` claims into authorities, the standard convention is the `SCOPE_` prefix:

```text
Verified token:
  scope: "orders.read reports.export"

Authorities via standard converter:
  SCOPE_orders.read
  SCOPE_reports.export
```

If an API requires the order-reading scope:

```java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

`GrantedAuthorityDefaults("")` **does not automatically alter** the JWT converter. If you customize `JwtGrantedAuthoritiesConverter.setAuthorityPrefix(...)` to use another prefix, update rules accordingly; never arbitrarily mix a role name `ADMIN` with a `SCOPE_admin` privilege.

In addition, roles from an Identity Provider (such as groups or realm roles) may need a custom converter to emit `ROLE_ADMIN` or `ADMIN`. Only do this from claims whose **signature, issuer/audience, expiration, tenant mapping**, and trusted privilege source have been verified. Never accept a client-supplied role field from a request body and turn it into a `GrantedAuthority`.

## 13. Role Hierarchy and Other Method-Security Annotations

`RoleHierarchy` allows expressing policy-based role/authority relationships, for example:

```text
ROLE_ADMIN
  |
  +--> ROLE_MANAGER
          |
          +--> ROLE_VIEWER
```

However, a hierarchy only takes effect when configured and integrated into the required authorization manager/expression handler. `GrantedAuthorityDefaults("")` **does not** create inheritance relationships. If the hierarchy declares `ROLE_ADMIN` while the user is actually granted `ADMIN`, the relationship may fail to match.

Method security also supports `@Secured` and JSR-250 `@RolesAllowed` when enabled with the corresponding options, such as `securedEnabled=true` or `jsr250Enabled=true` on `@EnableMethodSecurity`. They have their own semantics/managers; do not assume a prefix configuration for `@PreAuthorize` automatically applies identically to every annotation or version.

For applications with multiple authorization mechanisms, testing each annotation style and HTTP filter chain is mandatory. Remember to distinguish `AuthenticationManager` (identity verification), `AuthorizationManager` (access decision), `GrantedAuthoritiesMapper` (authority normalization), and `GrantedAuthorityDefaults` (a default role prefix setting).

## 14. Moving from `ROLE_ADMIN` to `ADMIN` Requires a Full Migration

Setting `new GrantedAuthorityDefaults("")` is not a migration. You must review at least:

1. Data store: role/permission columns, `UserDetailsService`, external groups, and `GrantedAuthoritiesMapper`.
2. HTTP rules: `hasRole`, `hasAnyRole`, `hasAuthority`, multiple `SecurityFilterChain`s, and custom managers.
3. Method rules: `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@RolesAllowed`, expression handlers, and Spring proxies.
4. Test fixtures: `@WithMockUser(roles=...)`, `user().roles(...)`, mocked JWTs/JWT converters.
5. RoleHierarchy: authority names in relationships and where the hierarchy is applied.
6. Sessions/JWTs: already-issued authentications hold old authority snapshots; appropriate TTL/revocation/invalidation policies are required.
7. Rollout/cluster: avoid node A requiring `ROLE_ADMIN` while node B requires `ADMIN`, causing inconsistent authorization behavior.
8. Monitoring: track denials without logging passwords, JWTs, session IDs, or secrets.

| Before | After | Must verify |
| --- | --- | --- |
| User authority `ROLE_MANAGER` | `MANAGER` | DB/SSO/JWT mapping |
| HTTP `hasRole("MANAGER")` | HTTP `hasAuthority("MANAGER")` | Exact authority contract |
| Method `hasRole('MANAGER')` | Method `hasAuthority('MANAGER')` or empty-prefix handler | Method proxy/handler |
| `User.roles("MANAGER")` | `User.authorities("MANAGER")` | User builder |
| `@WithMockUser(roles="MANAGER")` | `@WithMockUser(authorities="MANAGER")` | Test setup |
| `ROLE_MANAGER > ROLE_USER` | Hierarchy following the new convention | Integration with authorization engines |

**Do not "fix" this by indiscriminately granting both `MANAGER` and `ROLE_MANAGER` to all users.** That can unintentionally widen privileges and mask inconsistent policies.

## 15. Diagnosing 401, 403, and Prefix Errors

A user lacking privileges typically receives **403**, but the status code alone does not tell the whole story:

| Outcome | Possible cause |
| --- | --- |
| 302 redirect `/login` | Anonymous request prompted to log in by form-login entry point |
| 401 Unauthorized | Missing/invalid authentication for Basic/Bearer |
| 403 for logged-in user | Insufficient authority, role mismatch, deny policy, resource-level check |
| 403 on POST | Possibly missing CSRF token, not necessarily a role issue |
| 404 | No handler, endpoint not exposed, or policy intentionally hides resource |

When encountering 403, follow these steps:

1. Confirm the request entered the right `SecurityFilterChain` and matched the URL/method rule.
2. Confirm the principal is authenticated and what `Authentication` type `SecurityContext` holds.
3. Inspect the principal's **exact authorities** during the request in a controlled debug environment.
4. Distinguish between `hasRole`, `hasAuthority`, a SpEL expression, or a custom manager.
5. Determine the manager/handler's actual prefix; do not guess from bean names.
6. If it is method security, verify `@EnableMethodSecurity` and invocation through a Spring proxy.
7. Inspect role hierarchy, scopes, object ownership, and tenant boundaries.
8. Check whether old sessions/JWTs carry cached/stale authorities.
9. Write tests for users with `ADMIN`, `ROLE_ADMIN`, no authorities, and other roles.
10. Only then update the mapping, rule, or expression handler.

Enable debug logging only when needed in development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Never write tokens, cookies, passwords, security headers, or private data into logs/metrics. In production use audit/correlation IDs with minimal information and appropriate access controls.

## 16. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| User has `ADMIN`, HTTP rule `hasRole("ADMIN")` | 403 | `hasAuthority("ADMIN")` or grant `ROLE_ADMIN` |
| User has `ROLE_ADMIN`, rule `hasAuthority("ADMIN")` | 403 | Exact `ROLE_ADMIN` |
| Passing `hasRole("ROLE_ADMIN")` | Possible config error | `hasRole("ADMIN")` |
| Assuming `GrantedAuthorityDefaults` changes every HTTP matcher | Method/HTTP produce different results | Test each manager; use exact authority |
| Changing prefix while still using `User.roles()` | Still grants `ROLE_...` | Use `authorities()` when no prefix is desired |
| Using `@WithMockUser(roles=...)` for unprefixed data | Wrong fixture | Use `authorities=...` |
| Using `hasRole` for JWT scope `SCOPE_...` | No match | `hasAuthority("SCOPE_...")` |
| Forgetting `@EnableMethodSecurity` or proxy | Annotation ignored | Enable interception and test |
| Building authorities from user input | Privilege escalation | Map only from trusted identity sources |
| Assuming ADMIN automatically has all permissions | Missing access or over-privilege | Explicit RoleHierarchy and business policy |
| Skipping ownership/tenant checks once a role is present | IDOR, cross-tenant access | Enforce resource-level permissions |
| Granting both prefixed and unprefixed roles to "fix" errors | Excess privileges | Choose one consistent naming convention |
| Changing config while keeping old sessions/JWTs | Stale authorization | Revoke/refresh per SLA |
| Disabling CSRF to work around 403 | Introduces security risk | Distinguish CSRF vs. role errors and fix the right layer |

## 17. Review Questions

**Q1.** User has authority `ADMIN`; does Spring Security 6 default HTTP `hasRole("ADMIN")` allow access?

**Answer:** No, the manager typically checks for `ROLE_ADMIN`. Either use exact `hasAuthority("ADMIN")` or grant `ROLE_ADMIN`.

**Q2.** Does `hasAuthority("ADMIN")` automatically prepend `ROLE_`?

**Answer:** No. It checks exact `ADMIN`.

**Q3.** Does `GrantedAuthorityDefaults("")` modify authorities inside `Authentication`?

**Answer:** No. It configures the default prefix for supporting components; it does not rewrite data.

**Q4.** Are `User.roles("OPS")` and `User.authorities("OPS")` the same?

**Answer:** No. `roles` typically creates `ROLE_OPS`, whereas `authorities` creates `OPS`.

**Q5.** Why can a `@WithMockUser(roles="OPS")` test behave differently from a production user with `OPS`?

**Answer:** The test fixture creates `ROLE_OPS`, so the authority string differs.

**Q6.** Do HTTP `hasRole("OPS")` and method `@PreAuthorize("hasRole('OPS')")` always use the same prefix?

**Answer:** Not guaranteed. In Security 6 the HTTP builder uses a manager with `ROLE_`, while the method expression handler can pick up `GrantedAuthorityDefaults("")`. Test each layer.

**Q7.** If you want to keep the `OPS` authority without depending on prefix configuration, what should you use?

**Answer:** `hasAuthority("OPS")` and `@PreAuthorize("hasAuthority('OPS')")`.

**Q8.** A JWT converter creates `SCOPE_orders.read`; what is the matching rule?

**Answer:** `hasAuthority("SCOPE_orders.read")` if the converter uses that naming.

**Q9.** Does a `ROLE_ADMIN` user automatically have `ROLE_VIEWER`?

**Answer:** No; a role hierarchy must be configured and applied.

**Q10.** Why can changing the role prefix bean still leave users with old privileges?

**Answer:** Sessions, JWTs, and caches can hold authority snapshots. A migration must address those lifecycles.

**Q11.** A method has `@PreAuthorize` yet does not block unauthorized callers; what should you check?

**Answer:** `@EnableMethodSecurity`, Spring proxies, self-invocation, the handler, and test setup—not just the prefix.

**Q12.** Does the ADMIN role grant permission to read another tenant's data?

**Answer:** Not automatically; separate tenant/ownership authorization is required.

## 18. Pre-Release Checklist

- [ ] Define canonical conventions for roles, permissions, and scopes.
- [ ] Inspect actual `GrantedAuthority.getAuthority()` values, not only role labels in the DB.
- [ ] Know which APIs prepend `ROLE_` and which match exact strings.
- [ ] Use `GrantedAuthorityDefaults` only when the target components are configured compatibly.
- [ ] Test `authorizeHttpRequests().hasRole` independently from method `@PreAuthorize` `hasRole`.
- [ ] Do not use `User.roles()` or `@WithMockUser(roles=...)` to grant unprefixed authorities.
- [ ] Use exact `hasAuthority` for permissions to avoid ambiguity.
- [ ] Verify proxies/`@EnableMethodSecurity` so method annotations actually execute.
- [ ] Audit JWT/SSO converters, RoleHierarchy, and authority mappers.
- [ ] Test principals with `ADMIN`, `ROLE_ADMIN`, and no privileges.
- [ ] Test HTTP/method layers, roles/scopes, ownership/tenant checks, and CSRF at the proper layer.
- [ ] Handle stale session/JWT/cache data when changing conventions.
- [ ] Never temporarily broaden permissions just to make tests pass.
- [ ] Keep regression tests for Spring Security version upgrades.
- [ ] Never log passwords, tokens, or sensitive user data during debugging.

## Conclusion

`ROLE_` is a **role prefix convention** in many Spring Security APIs. `GrantedAuthority` instances are the actual privilege strings attached to `Authentication`. `hasAuthority` performs an exact string match, whereas `hasRole` may prepend a prefix depending on the active implementation.

`GrantedAuthorityDefaults` is useful for changing the default role prefix in supporting components, especially method-security expressions, but **it does not convert authorities or guarantee that every HTTP `hasRole` follows the same bean**. To avoid 403 errors, choose a consistent convention, normalize privileges from trusted identity sources, use exact `hasAuthority` where appropriate, and test both HTTP and method authorization against your exact Spring Security version.
