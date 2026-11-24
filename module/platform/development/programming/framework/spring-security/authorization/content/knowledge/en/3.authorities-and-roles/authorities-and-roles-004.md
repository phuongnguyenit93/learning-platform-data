# hasAnyAuthority, hasAnyRole, and Checking One of Multiple Permissions in Spring Security

## Goal

After this lesson, you will be able to distinguish `hasAnyAuthority` from `hasAnyRole`, accurately interpret the condition **"having at least one of the listed permissions"**, use both APIs in HTTP configuration and `@PreAuthorize`, handle the `ROLE_` prefix, combine OR/AND conditions per business policy, and test authorized/unauthorized cases in Spring Security on the Servlet stack.

## 1. What does "one of multiple permissions" mean?

In Spring Security, `Authentication` represents the currently authenticated principal. Its `GrantedAuthority` list contains **granted permission strings**, for example:

```text
report:read
report:export
ROLE_EDITOR
ROLE_ADMIN
SCOPE_profile
```

A policy may allow reading reports when the caller possesses **read permission** `report:read` **or** **export permission** `report:export`. This is an **OR** operation: only **one condition needs to be true**. Given the actual permission set `G` and the accepted permission set `R`, the general condition is:

```text
allow = there exists r in R such that r is in G

Example:
G = {"report:read", "ROLE_SUPPORT"}
R = {"report:read", "report:export"}

G ∩ R = {"report:read"}  =>  ALLOW
```

**You do not need all permissions** in `R`. If the user has none of the matching permissions, the condition fails. This is only **one authorization condition**: the request may still be denied by another rule, lack of authentication, resource ownership checks, or CSRF.

### Decision table

Suppose the application uses the exact authorities in the first column and has no role hierarchy configured:

| User's GrantedAuthority | `hasAnyAuthority("report:read", "report:export")` | `hasAnyRole("EDITOR", "ADMIN")` |
| --- | --- | --- |
| `report:read` | **true** | **false** |
| `report:export` | **true** | **false** |
| `report:read`, `report:export` | **true** | **false** |
| `ROLE_EDITOR` | **false** | **true** |
| `ROLE_ADMIN`, `report:read` | **true** | **true** |
| `ROLE_SUPPORT` | **false** | **false** |
| No authorities | **false** | **false** |

From the table, functional permissions like `report:read` and roles like `ROLE_EDITOR` are not automatically equivalent. Spring Security does not infer that "someone with `ROLE_ADMIN` automatically has `report:read`" unless the application **grants both authorities** or explicitly configures a mechanism like a role hierarchy.

## 2. hasAnyAuthority: matching one of multiple authorities

`hasAnyAuthority("a", "b", ...)` returns allow if `Authentication` has **at least one** `GrantedAuthority` matching one of the passed strings, as evaluated by the authorization checker in use.

Example:

```java
// Inside authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("report:read", "report:export")
```

Meaning: every `GET` request matching this path must have **`report:read` OR `report:export`**. Someone with only `report:read` suffices; someone with only `report:export` also suffices. If the actual authority is named `SCOPE_report.read` while the policy checks `report:read`, the two strings **do not match**, even if a human considers their meaning similar.

### Comparison with hasAuthority

| Expression | Condition |
| --- | --- |
| `hasAuthority("report:read")` | Must have exact `report:read` |
| `hasAnyAuthority("report:read", "report:export")` | Has `report:read` **or** `report:export` (or both) |
| `hasAuthority("report:read") and hasAuthority("report:export")` | Must have **both** |
| `hasAuthority("report:read") or hasAuthority("report:export")` | Conceptually equivalent to `hasAnyAuthority` in the two-authority example |

When you want "**just one of these permissions is enough**", use `hasAnyAuthority` because it is concise and conveys the exact intent. When the policy requires **both permissions simultaneously**, use `and` in SpEL or an appropriate AND-combining `AuthorizationManager`; **do not use `hasAnyAuthority`**.

**Security note:** choose alternative permissions that have the **same acceptable access level for that operation**. For example, letting `report:export` substitute for `report:read` is an intentional business decision. If `report:export` must be more strictly protected, do not assume it substitutes for read access on every endpoint.

## 3. hasAnyRole: matching one of multiple roles

`hasAnyRole("EDITOR", "ADMIN")` is the syntax tailored for roles. Under default configuration, Spring Security interprets this as requiring at least one of the authorities:

```text
ROLE_EDITOR
ROLE_ADMIN
```

The default prefix is **`ROLE_`**. Therefore:

```java
.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyRole("EDITOR", "ADMIN")
```

Has the same default intent as:

```java
.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyAuthority("ROLE_EDITOR", "ROLE_ADMIN")
```

### Distinguishing passed strings

| Actual data in `Authentication.getAuthorities()` | Expression | Default result |
| --- | --- | --- |
| `ROLE_EDITOR` | `hasAnyRole("EDITOR", "ADMIN")` | Allow |
| `ROLE_EDITOR` | `hasAnyAuthority("ROLE_EDITOR", "ROLE_ADMIN")` | Allow |
| `ROLE_EDITOR` | `hasAnyAuthority("EDITOR", "ADMIN")` | Deny |
| `EDITOR` | `hasAnyRole("EDITOR", "ADMIN")` | Deny |
| `report:read` | `hasAnyRole("EDITOR", "ADMIN")` | Deny |

**Easy rule to remember:** with the default `ROLE_` convention, pass `"EDITOR"`, `"ADMIN"` to `hasAnyRole`; use the **exact prefixed string** when calling `hasAnyAuthority`. Do not pass `"ROLE_EDITOR"` into `hasAnyRole` "just to be safe": this is not the recommended call style and some API variants check/reject an already-present prefix.

The role prefix can be customized via Spring Security configuration; if so, ensure **where permissions are granted, where they are checked, and tests** all share the same convention. If using **RoleHierarchy** (e.g., admins inherit editor authorities), the outcome may depend on effective authorities after hierarchy expansion; the table above assumes no hierarchy.

### Is "Role" a separate data type in Spring Security?

At the basic decision layer, a role is typically represented as a `GrantedAuthority` starting with `ROLE_`. `hasAnyRole` provides **convenient syntax** and the prefix convention. Assigning `ROLE_ADMIN` to a user **does not automatically turn into every other permission**. The application must grant business authorities, define mappings from groups/roles, or configure a hierarchy.

## 4. Applying both options at the HTTP layer

In a Spring Boot application using Spring Security Servlet, rules are placed in `SecurityFilterChain`. The complete authorization configuration example below uses Spring Security 6.x syntax:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Public endpoint
            .requestMatchers("/actuator/health").permitAll()

            // Has at least one of the two accepted authorities
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAnyAuthority("report:read", "report:export")

            // Has at least one of the two accepted roles
            .requestMatchers(HttpMethod.POST, "/api/reports/**")
                .hasAnyRole("EDITOR", "ADMIN")

            // Do not expose endpoints without an explicit policy
            .anyRequest().denyAll()
        );
        // Illustrates one authentication mechanism only:
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

To run in a real project, you need Spring Security dependencies, a mechanism to supply `Authentication`/authorities, and proper session/token/CSRF configuration. The example above **does not automatically create** users, roles, data sources, or REST controllers. `httpBasic` only puts the example into an easy-to-follow authentication frame; production may use form login, sessions, or OAuth2 Resource Server.

Per-request analysis:

| Request | Caller's GrantedAuthority | HTTP-layer decision |
| --- | --- | --- |
| `GET /api/reports/8` | `report:read` | Passes GET rule |
| `GET /api/reports/8` | `report:export` | Passes GET rule |
| `GET /api/reports/8` | `ROLE_ADMIN` | Denied: GET requires authority `report:read` or `report:export` |
| `POST /api/reports` | `ROLE_EDITOR` | Passes POST rule |
| `POST /api/reports` | `ROLE_ADMIN` | Passes POST rule |
| `POST /api/reports` | `report:read` | Denied: POST requires role EDITOR or ADMIN |
| `DELETE /api/reports/8` | Any | `denyAll` under this configuration |

**"Passing the rule" does not guarantee HTTP 2xx.** The request still depends on login, controllers, validation, business rules, data, CSRF, and other protective layers. For example, a `POST` with Basic authentication can get `403` due to a missing CSRF token in a CSRF-enabled configuration, even with `ROLE_EDITOR`.

### Matcher ordering and intentional OR

In `authorizeHttpRequests`, rules are evaluated **in order** and the request uses the first matching rule. Do not write two identical matchers expecting permissions to combine:

```java
// WRONG if you want "report:read OR report:export":
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:export")
```

Once the first matcher matches, the second matcher does not act as a fallback. Write it as **one rule**:

```java
// RIGHT for an OR policy:
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("report:read", "report:export")
```

Place specific paths before `/api/**` or `/**` to keep broad rules from shadowing narrow ones. `anyRequest().denyAll()` ensures new endpoints are not silently granted access simply because they lack a matcher.

## 5. Applying in method security

Not every service call comes through an HTTP controller: there are background jobs, message consumers, scheduled tasks, or other services. Therefore, permissions can be checked right **before calling a business method** using `@PreAuthorize`.

### 5.1. Two basic examples

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportPermissionService {

    @PreAuthorize("hasAnyAuthority('report:read', 'report:export')")
    public String viewSummary() {
        return "Report summary";
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
    public String createDraft() {
        return "Draft created";
    }
}
```

The application must enable `@EnableMethodSecurity` in configuration. When a Spring-managed proxy receives a call to `viewSummary()`, the caller needs `report:read` **or** `report:export`. For `createDraft()`, the caller needs `ROLE_EDITOR` **or** `ROLE_ADMIN` under the default convention.

These two checks belong to **two separate methods**; there is no meaning of "the user needs both a role and an authority". Only when writing a combined expression or adding other guard layers do you get additional conditions.

### 5.2. Combining "one of multiple permissions" with mandatory constraints

An operation reading a private report may allow two alternative authorities **yet still require matching tenant and ownership**:

```java
@PreAuthorize(
    "hasAnyAuthority('report:read', 'report:export') and " +
    "@reportAccess.canRead(authentication, #reportId)"
)
public Report read(@P("reportId") long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

This is **illustrative integration code** in a Spring service: `Report`, `repository`, and the `reportAccess` bean are application-defined. `@P` comes from `org.springframework.security.access.method.P` to provide the `#reportId` variable name to SpEL, avoiding reliance on the compiler preserving parameter names. The `reportAccess` bean must verify tenant/owner/share based on the server-side record, not merely check that the user knows an ID.

The logic of the expression is:

```text
ALLOW =
    (report:read OR report:export)
    AND policy.canRead(currentUser, reportId)
```

Unlike:

```java
// Only appropriate if business rules ALLOW bypassing the object check
// when holding the ADMIN role:
@PreAuthorize(
    "hasAnyAuthority('report:read', 'report:export') or hasRole('ADMIN')"
)
```

The expression `or hasRole('ADMIN')` makes admins skip the other check branch if you place the policy in the wrong OR branch. In a multi-tenant system, explicitly decide whether admins are allowed cross-tenant access. If everyone must respect tenant boundaries, place `sameTenant` in the shared `AND` branch, even for admins.

### 5.3. Limitations to know

- `@EnableMethodSecurity` must be enabled explicitly. Having `@PreAuthorize` in source code does not guarantee the system actually checks it if method security is not enabled.
- Standard interceptors use Spring AOP proxies; `this.viewSummary()` within the **same bean** usually bypasses the proxy, and objects created with `new` outside the container are not protected by Spring.
- `@PreAuthorize` is checked **before** the method. `@PostAuthorize` is checked **after** the method returns and must not be used as the sole gate for operations with side effects.
- If multiple annotations of different types apply together, each checker can add another requirement that must be met; do not assume they combine with OR. Do not stack multiple `@PreAuthorize` annotations on the same method hoping "any matching permission passes".
- If calling a service outside an HTTP request, assigning `Authentication` for workers/jobs must be explicitly designed; a missing security context typically results in denial, not automatic allowance.

## 6. Standalone Java 17 code simulating the check

The following example uses `Set<String>` to simulate a list of GrantedAuthorities. It illustrates the **logical meaning** of `hasAnyAuthority` and the default role prefix convention, **without replacing** Spring Security's implementation; it ignores role hierarchies, custom prefix configs, or authentication state.

Save with exact name **`AnyRightsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Set;

public class AnyRightsDemo {

    static boolean hasAnyAuthority(Set<String> granted, String... required) {
        return Arrays.stream(required).anyMatch(granted::contains);
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        return Arrays.stream(roles)
            .map(role -> "ROLE_" + role)
            .anyMatch(granted::contains);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
            "report:read",
            "ROLE_SUPPORT",
            "SCOPE_profile"
        );

        System.out.println("Read or export: "
            + hasAnyAuthority(granted, "report:read", "report:export"));

        System.out.println("Edit or delete: "
            + hasAnyAuthority(granted, "report:edit", "report:delete"));

        System.out.println("Support or admin role: "
            + hasAnyRole(granted, "SUPPORT", "ADMIN"));

        System.out.println("Editor or admin role: "
            + hasAnyRole(granted, "EDITOR", "ADMIN"));

        System.out.println("Authority without ROLE_ prefix: "
            + hasAnyAuthority(granted, "SUPPORT", "ADMIN"));

        System.out.println("OAuth scope authority exact match: "
            + hasAnyAuthority(granted, "SCOPE_profile", "SCOPE_email"));

        System.out.println("Empty granted authorities: "
            + hasAnyAuthority(Set.of(), "report:read", "report:export"));
    }
}
```

Run with **JDK 17 or higher**:

```bash
javac AnyRightsDemo.java
java AnyRightsDemo
```

**Exact stdout**:

```text
Read or export: true
Edit or delete: false
Support or admin role: true
Editor or admin role: false
Authority without ROLE_ prefix: false
OAuth scope authority exact match: true
Empty granted authorities: false
```

Explanation: `granted` only has `report:read`, so the first policy returns `true` without needing `report:export`. It has `ROLE_SUPPORT`, so `hasAnyRole("SUPPORT", "ADMIN")` is `true`. However, the string `"SUPPORT"` is not in `GrantedAuthority`: `hasAnyAuthority("SUPPORT", "ADMIN")` must be `false`. `SCOPE_profile` is recognized because we check the **exact string**, with no automatic conversion into a role.

## 7. Where do authority strings come from?

### 7.1. In-memory users and UserDetails

When using `UserDetails`, you can grant authorities directly:

```java
UserDetails reader = User.withUsername("reader")
    .password("{noop}demo-password")
    .authorities("report:read", "ROLE_SUPPORT")
    .build();
```

This snippet illustrates assigning permissions to a learning user; it requires importing `UserDetails` and `User` from `org.springframework.security.core.userdetails`. `{noop}` is only for representing test data; never use sample passwords or the NoOp encoder for production accounts. Calling `.roles("SUPPORT")` in the default builder creates authority `ROLE_SUPPORT`; if you want control over exact prefixed strings or business permission names, use `.authorities(...)` accordingly.

### 7.2. JWT/OAuth2 Resource Server

In many OAuth2 Resource Server configurations, Spring Security maps token scopes into authorities prefixed with `SCOPE_`; for example, scope `report.read` can become `SCOPE_report.read`. Therefore:

```java
.hasAnyAuthority("SCOPE_report.read", "SCOPE_report.export")
```

only works properly when the converter actually generates these strings. If the system wants to use `report:read` or `ROLE_EDITOR` from a custom claim, you must define a consistent mapping/converter from claim to `GrantedAuthority`. Do not assume "having claim role=EDITOR" equals "having authority ROLE_EDITOR"; mapping depends on authentication configuration.

**Proper way to diagnose:** inspect the `GrantedAuthority` set authenticated and mapped by the server, comparing **verbatim** with the strings in the rule; use safe logging in development, without logging access tokens or sensitive details. Avoid adding roles based solely on fields sent by the client.

### 7.3. Role prefix and hierarchy

By default, role methods check the `ROLE_` prefix. If the application customizes the role prefix, evaluation may differ from standard conventions. Role hierarchy can expand effective authorities, for example `ROLE_ADMIN` declared to inherit `ROLE_EDITOR`; in that case a policy requiring EDITOR can pass ADMIN even if the initial list did not directly contain `ROLE_EDITOR`. This requires a **hierarchy configuration** integrated with the corresponding evaluator, and must never be assumed merely because two roles look parent–child.

## 8. When to use OR, when to use AND?

**Use OR** when the permissions are **genuine alternatives** for the same action:

```text
View summary report:
    report:read OR report:export

Access support page:
    ROLE_SUPPORT OR ROLE_ADMIN
```

**Use AND** when business rules require **simultaneous** conditions:

```text
Approve payment:
    payment:approve
    AND MFA completed
    AND sameTenant
    AND NOT requesterIsApprover
```

`hasAnyAuthority("payment:approve", "mfa:verified")` would be **wrong** in this scenario: someone with only `mfa:verified` would be let through. Instead, use `hasAuthority("payment:approve") and ...` along with verified MFA state and real data; MFA is an authentication/context state that must be verified, not blindly trusted from a client-sent authority string.

### Combining authority and role

In method security you can write:

```java
@PreAuthorize(
    "hasAnyRole('SUPPORT', 'ADMIN') and " +
    "hasAnyAuthority('ticket:read', 'ticket:manage')"
)
```

Meaning **(SUPPORT or ADMIN) AND (ticket:read or ticket:manage)**. A user with only `ROLE_ADMIN` and no matching ticket authority **does not pass** this check unless the system configures inherited/corresponding permissions. If you want **admin role to be an exception** for part of a policy, use parentheses and clearly define which checks admins must still obey.

If access also depends on a record's **tenant, owner, or status**, `hasAnyAuthority` or `hasAnyRole` only solves the authority-set check. Combine custom policies with `@PreAuthorize`/`AuthorizationManager` or scoped queries; do not treat permission to reach a URL as permission to read every ID.

## 9. Testing with case matrices and Spring Security Test

Do not test only the case with both permissions. Test each alternative independently as well as callers with no permissions at all.

| Scenario | GET endpoint requiring `report:read` or `report:export` | POST endpoint requiring role EDITOR or ADMIN |
| --- | --- | --- |
| Only `report:read` | Passes permission check | Denied |
| Only `report:export` | Passes permission check | Denied |
| Both report authorities | Passes permission check | Denied if missing role |
| Only `ROLE_EDITOR` | Denied | Passes permission check |
| Only `ROLE_ADMIN` | Denied | Passes permission check |
| Only `ROLE_SUPPORT` | Denied | Denied |
| Unauthenticated | Denied by authentication mechanism | Denied by authentication mechanism |
| Has baseline permission but accesses another tenant's record | HTTP rule may pass | Business/object policy must still block |

With `spring-security-test` and `MockMvc`, you can create test principals:

```java
@WithMockUser(authorities = {"report:read"})
// Test GET /api/reports/8: passes HTTP permission check.

@WithMockUser(authorities = {"report:export"})
// Also passes HTTP GET permission check.

@WithMockUser(roles = {"EDITOR"})
// Has authority ROLE_EDITOR; passes POST role check.

@WithMockUser(authorities = {"ROLE_ADMIN"})
// Also passes POST role check under the default prefix.
```

These are **annotation configurations for individual tests**, not a standalone Java class to compile as-is. In real tests, place **each** `@WithMockUser` on its own test method. `roles = {"EDITOR"}` adds `ROLE_` by default; `authorities = {"ROLE_ADMIN"}` uses the literal string. `POST` tests must handle CSRF per configuration (e.g., `with(csrf())` if CSRF is enabled), otherwise you may get `403` for a missing token even when the role is right.

Beyond HTTP status, verify the service is invoked when allowed, **not invoked when denied**, and data remains unchanged in denied cases. For method security, invoke the **real Spring bean through its proxy**, rather than calling a method on an object created with `new` and claiming the annotation worked.

### Distinguishing causes of denial

- **401** usually indicates missing valid authentication credentials for an entry point requiring login.
- **403** usually indicates authenticated but lacking authority/role; it can also result from CSRF or authorization checks at another layer.
- Passing the HTTP rule while the service throws `AccessDeniedException` means **two layers of checks** are working, not that `hasAnyAuthority` is broken.
- A controller returning **404** because the record does not exist or due to a policy hiding data existence is a separate API handling decision.

Exact HTTP outcomes depend on authentication mechanisms, exception handling, CSRF, and other policies; tests must establish proper context rather than treating every `403` as a role error.

## 10. Common mistakes and how to avoid them

1. **Confusing "any" with "all":** `hasAnyAuthority("a", "b")` allows when only `a` is present. If both are required, use an explicit AND condition.
2. **Forgetting the role prefix:** `hasAnyRole("ADMIN", "EDITOR")` checks `ROLE_ADMIN`/`ROLE_EDITOR` by default; `hasAnyAuthority("ADMIN", "EDITOR")` checks two completely different strings.
3. **Passing `ROLE_ADMIN` into `hasAnyRole`:** pass unprefixed role names under default configuration to avoid errors or inconsistent interpretation.
4. **Assuming a role automatically holds every business authority:** `ROLE_ADMIN` does not turn into `report:read` unless permissions are granted or a hierarchy is configured.
5. **Assuming a JWT scope has the same name as a required authority:** inspect `SCOPE_`/claim converter mappings and the actual strings in `Authentication`.
6. **Splitting two identical matchers to build OR:** the first matching rule decides; use a single `hasAnyAuthority(...)` or `hasAnyRole(...)`.
7. **Using OR as a backdoor skipping owner/tenant:** mandatory constraints must sit outside the OR branch and apply to everyone, including admins if policy dictates.
8. **Protecting only controllers:** service calls from other paths can bypass HTTP. Use method security and protect data by ID.
9. **Not enabling `@EnableMethodSecurity` or self-invocation:** annotations may not execute. Test through Spring-managed beans.
10. **Misattributing 403 sources in tests:** CSRF, authentication, proxies, or business constraints can reject requests after authority rules pass.
11. **Leaving new endpoints open by default:** set `anyRequest().denyAll()`; only grant access after defining business requirements.
12. **Granting overly broad alternative permissions:** do not add roles or authorities to an OR list just to "let users through"; every alternative must be policy-approved and tested.

## 11. Workflow for choosing the right API

1. List **all** actual authorities/roles of `Authentication` after mapping.
2. Ask "is **one of these permissions** enough, or are **all** required?"; write down the OR/AND condition before coding.
3. If matching **any arbitrary GrantedAuthority strings**, use `hasAnyAuthority("a", "b")`. If matching **roles** under the prefix convention, use `hasAnyRole("EDITOR", "ADMIN")`.
4. Place HTTP rules for early blocking and service rules if business logic has multiple entry points; configure a deny fallback.
5. Add invariant checks such as tenant, owner, and document status in methods/objects/queries; do not let OR bypass them.
6. Test each alternative permission individually, zero-permission cases, role prefixes, JWT mapping, CSRF, method proxies, and out-of-scope data.

**Self-check:** Alice has exactly `report:export` and `ROLE_SUPPORT`, without `report:read` or `ROLE_ADMIN`. Does Alice pass `hasAnyAuthority("report:read", "report:export")`? **Yes**, because at least one authority matches. Does Alice pass `hasAnyRole("ADMIN", "EDITOR")`? **No**, because she lacks `ROLE_ADMIN` or `ROLE_EDITOR`. If the endpoint requires **both** report permission and admin role, the overall result remains **deny**.

## References

- Spring Security, *Authorize HttpServletRequests*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, *Method Security*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, *Authorization Architecture*: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security, *Testing Method Security*: https://docs.spring.io/spring-security/reference/servlet/test/method.html
