# hasAuthority and hasRole: The ROLE_ Prefix Rule

> **Spring Security – authorization** · **Group:** Authorities and roles  
> Focus: the meaning of `GrantedAuthority`, exact matching in `hasAuthority`, how `hasRole` handles the `ROLE_` prefix, and important differences across HTTP authorization, method security, and user data.

## 1. Opening scenario: same ADMIN text, different outcomes

Suppose a logged-in user has the following list of authorities:

~~~text
username = "an"
authorities = ["ROLE_ADMIN", "invoice:read"]
~~~

In a common Spring Security configuration, the following three conditions **are not the same**:

~~~java
.hasRole("ADMIN")                 // Checks authority ROLE_ADMIN
.hasAuthority("ROLE_ADMIN")       // Checks exact string ROLE_ADMIN
.hasAuthority("ADMIN")            // Checks exact string ADMIN
~~~

The first two conditions let user An through; the last one denies access because the authority list **does not contain the string `ADMIN`**.

Confusion often stems from treating "business role", "authority string stored in `Authentication`", and "argument passed to the check function" as the same thing. Keep three layers clear:

1. **Business role**: permission group name, such as `ADMIN`, `EDITOR`.
2. **GrantedAuthority**: the actual data attached to an `Authentication`, such as `ROLE_ADMIN`.
3. **Authorization rule**: how Spring Security decides whether the available authorities satisfy the condition.

The `ROLE_` prefix is a **convention in role checks**; it does not modify already-granted permission strings, create roles automatically, or map business permissions.

## 2. `Authentication` and `GrantedAuthority`: what gets matched

After authentication, Spring Security represents the principal with an `Authentication` object. Besides principal, credentials, and authentication state, this object holds a collection of `GrantedAuthority` instances. A common string-based authority is represented via `SimpleGrantedAuthority`.

Example of an authority set:

~~~text
Authentication
  principal: an
  authenticated: true
  authorities:
    - ROLE_ADMIN
    - invoice:read
    - SCOPE_invoices.read
~~~

Key points:

- `ROLE_ADMIN` may be used by the application as an **authority representing the ADMIN role**.
- `invoice:read` may be used by the application as a **permission to read invoices**.
- `SCOPE_invoices.read` may come from an **OAuth 2.0 scope** mapped from an access token.
- Despite different business meanings, all three can reside in the same `GrantedAuthority` collection.
- `getAuthority()` on a string-based `GrantedAuthority` usually returns the string to match against. Some complex implementations may not be representable by a single string; in that case a specialized checker is needed.

Java example inside an application that already has the Spring Security dependency:

~~~java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "an",
                null,
                List.of(
                        new SimpleGrantedAuthority("ROLE_ADMIN"),
                        new SimpleGrantedAuthority("invoice:read"),
                        new SimpleGrantedAuthority("SCOPE_invoices.read")
                )
        );

// authentication.getAuthorities() contains the three authorities passed in.
~~~

This is an **illustrative snippet inside a Spring application**, not a standalone program. The constructor taking a collection of authorities creates an authentication token marked as authenticated; in a real application only trusted security-layer code should construct an authentication this way. Do not accept self-declared roles or authorities from an HTTP request and mark the token authenticated.

**Why inspect the actual authorities?** When a rule denies access, the bug may be in the authority source or converter rather than in the matcher. A string `ADMIN` from the database does not turn into `ROLE_ADMIN` inside `Authentication` if the application has not mapped it.

## 3. `hasAuthority`: verbatim string matching

`hasAuthority("X")` asks whether the granted authorities collection contains an authority **equal to `X`** under standard string matching. It does not prepend `ROLE_`, normalize uppercase/lowercase, interpret dots/colons, or infer permission hierarchy.

Example with authorities:

~~~text
["ROLE_ADMIN", "invoice:read", "SCOPE_invoices.read"]
~~~

| Rule | Required authority | Result |
|---|---|---|
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | **true** |
| `hasAuthority("ADMIN")` | `ADMIN` | **false** |
| `hasAuthority("invoice:read")` | `invoice:read` | **true** |
| `hasAuthority("INVOICE:READ")` | `INVOICE:READ` | **false** |
| `hasAuthority("SCOPE_invoices.read")` | `SCOPE_invoices.read` | **true** |
| `hasAuthority("invoices.read")` | `invoices.read` | **false** |
| `hasAuthority("ROLE_USER")` | `ROLE_USER` | **false** |

Distinguish `ADMIN` from `ROLE_ADMIN`, `invoice:read` from `Invoice:Read`, and `SCOPE_invoices.read` from `invoices.read`. Build a centralized naming convention that stays consistent between where authorities are issued and where they are checked.

`hasAnyAuthority("A", "B")` typically requires **at least one** matching authority. Do not misread "any" as "must have all". When requiring multiple conditions simultaneously, write out the combined policy explicitly (e.g. expression `hasAuthority('invoice:read') and hasAuthority('SCOPE_invoices.read')`).

## 4. `hasRole`: role check with prefix convention

Under the default `ROLE_` convention, `hasRole("ADMIN")` checks whether `Authentication` has authority `ROLE_ADMIN`.

~~~text
hasRole("ADMIN")
    |
    v
Apply default role prefix "ROLE_"
    |
    v
Require GrantedAuthority "ROLE_ADMIN"
~~~

Under this convention:

| Rule | Required authority | Interpretation |
|---|---|---|
| `hasRole("ADMIN")` | `ROLE_ADMIN` | ADMIN role |
| `hasRole("USER")` | `ROLE_USER` | USER role |
| `hasRole("ACCOUNTANT")` | `ROLE_ACCOUNTANT` | ACCOUNTANT role |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Explicit match on the role string |
| `hasAuthority("ADMIN")` | `ADMIN` | Match on unprefixed authority |
| `hasAuthority("invoice:read")` | `invoice:read` | Check business permission if granted |

**Important equivalence in default configuration:**

~~~text
hasRole("ADMIN")
         ≈
hasAuthority("ROLE_ADMIN")
~~~

The `≈` symbol describes the **required authority condition** in typical scenarios; it does not claim the two APIs share the same implementation or remain equivalent when customizing prefixes, role hierarchies, or authorization managers.

`hasAnyRole("ADMIN", "SUPPORT")` requires the caller to have at least one of `ROLE_ADMIN` or `ROLE_SUPPORT` (under the default convention). Having `ROLE_ADMIN` does not implicitly grant `ROLE_USER`; inherited permissions only apply if a role hierarchy configuration or authority-granting rule actually produces that result.

### A confusing exception when passing a string that already has `ROLE_`

**The style to use everywhere is `hasRole("ADMIN")`, never `hasRole("ROLE_ADMIN")`.** However, behavior when passing `ROLE_ADMIN` depends on the **specific API**:

- With the Java API `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")` in Spring Security 6.x, the Javadoc specifies the argument must **not have the `ROLE_` prefix**; the implementation may throw `IllegalArgumentException` because the argument already starts with `ROLE_`.
- With `SecurityExpressionRoot.hasRole('ROLE_ADMIN')` in some Spring Security expression mechanisms, the expression handler recognizes an already-prefixed string and can match `ROLE_ADMIN` without doubling the prefix. This differs from the Java API above.
- Do not rely on this difference as a coding convention. For readability and portability across APIs, always pass the **logical role name**, e.g. `"ADMIN"`, into `hasRole`, and pass the **full** authority string into `hasAuthority`.

It is important to avoid claiming "every `hasRole("ROLE_ADMIN")` doubles the prefix" or "everywhere accepts it" – neither is accurate across all APIs/versions.

## 5. Check matrix: inspect the authority set before guessing the outcome

Assume the system **has no role hierarchy configured** and uses the default prefix.

| Current authorities | `hasRole("ADMIN")` | `hasAuthority("ADMIN")` | `hasAuthority("ROLE_ADMIN")` |
|---|---|---|---|
| `[]` | false | false | false |
| `["ADMIN"]` | false | true | false |
| `["ROLE_ADMIN"]` | true | false | true |
| `["ROLE_USER"]` | false | false | false |
| `["ADMIN", "ROLE_USER"]` | false | true | false |
| `["ROLE_ADMIN", "ADMIN"]` | true | true | true |
| `["SCOPE_admin"]` | false | false | false |

These conditions check **the granted authority data**, without directly querying a `role` column in the database on every evaluation.

The critical question when hitting `403 Forbidden` is: "Which authority **was required**, and which authorities **were present**?". Only then check why the input data and configuration did not match.

## 6. Authority sources: `roles(...)` and `authorities(...)` differ

Another source of confusion lies in **how users are built**.

### 6.1. `UserDetails` in Spring Security

The following illustrative snippet belongs inside a Java method with Spring Security dependencies and proper imports:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

UserDetails fromRoles = User.withUsername("an")
        .password("{noop}demo-only")
        .roles("ADMIN")
        .build();

UserDetails fromAuthorities = User.withUsername("binh")
        .password("{noop}demo-only")
        .authorities("ROLE_ADMIN")
        .build();
~~~

With standard construction:

- `.roles("ADMIN")` creates granted authority `ROLE_ADMIN`; the builder handles the role prefix.
- `.authorities("ROLE_ADMIN")` grants the **exact specified authority**.
- `.authorities("ADMIN")` grants `ADMIN` and **does not** prepend `ROLE_`.
- Do not pass `"ROLE_ADMIN"` to `.roles(...)` when the builder expects an unprefixed role name.
- The string `{noop}demo-only` is only for documentation/test illustration; do not use clear-text passwords or NoOp encoders in production.

If users are loaded from a database, code mapping a business role to `SimpleGrantedAuthority("ROLE_" + roleName)` must align with the rules. Validate role names, avoid blindly concatenating strings from untrusted input, and do not double the prefix if stored data already contains `ROLE_`.

### 6.2. Test helper `@WithMockUser`

Spring Security Test has different ways to build authorities:

~~~java
@WithMockUser(roles = "ADMIN")
// Creates authority ROLE_ADMIN for the mock user.

@WithMockUser(authorities = "ROLE_ADMIN")
// Creates exact authority ROLE_ADMIN.

@WithMockUser(authorities = "ADMIN")
// Creates exact authority ADMIN; does not satisfy default hasRole("ADMIN").
~~~

These are **illustrative annotations**, meant to be placed on a test method or test class. The `roles` and `authorities` attributes should not be specified simultaneously in the same `@WithMockUser`. Creating a mock user with `roles` does not prove the application maps JWT/database/IdP correctly; separate tests are needed for the real authentication flow.

## 7. Usage in HTTP authorization (Servlet)

With Spring Boot 3.x / Spring Security 6.x on the servlet stack, HTTP configuration can use `SecurityFilterChain` and `authorizeHttpRequests`.

The following example is **a configuration class inside a Spring application**, not a standalone Java program. It assumes login and authorities are properly supplied by the system:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")
                .requestMatchers("/api/support/**")
                    .hasAnyRole("ADMIN", "SUPPORT")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Interpretation:

1. `/api/admin/**` requires `ROLE_ADMIN` if using the default prefix.
2. `GET /api/invoices/**` requires **exact** `invoice:read`; having only `ROLE_ADMIN` **is not automatically enough** if that permission has not been granted via mapping/hierarchy.
3. `/api/support/**` permits access if at least one authority in `ROLE_ADMIN`, `ROLE_SUPPORT` is present.
4. Remaining paths are blocked by `denyAll()`. Deliberately add public rules, health endpoints, and other actual endpoints when building a complete system.
5. Matcher rules are evaluated in declaration order; specific paths must be placed before broader paths.

`httpBasic` here only illustrates an authentication mechanism; in production there must be proper user/password configuration and HTTPS. The example does not dictate the application's CSRF design. If the application relies on sessions/cookies and has state-changing operations, protect CSRF according to the actual usage model.

**Key takeaway:** `hasRole` **does not look up role names in the users table**. It only matches authorities on `Authentication`. If the database has field `role="ADMIN"` yet user mapping produces authority `ADMIN`, the `/api/admin/**` route will be denied by default.

### When to choose `hasRole`, when to choose `hasAuthority`?

- Choose `hasRole("ADMIN")` when the policy is expressed in terms of **roles** and the application consistently follows the `ROLE_` convention.
- Choose `hasAuthority("invoice:approve")` when the policy targets a **specific permission**.
- Choose `hasAuthority("ROLE_ADMIN")` if you want to match the exact role authority string and intentionally use the full prefix.
- Choose `hasAuthority("SCOPE_invoices.read")` when checking **mapped token scopes**, if the resource server uses the corresponding default configuration.
- Do not casually swap `hasRole("ADMIN")` to `hasAuthority("ADMIN")` thinking they "both check admin".

## 8. Usage in method security

Enable method security with `@EnableMethodSecurity` in Spring configuration. You can use `@PreAuthorize` on Spring-managed methods:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('ADMIN')")
public void resetApplicationSettings() {
    // Administrative operation.
}

@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    // Also check invoice/tenant/status in business policy.
}

@PreAuthorize(
        "hasRole('ADMIN') or hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long invoiceId) {
    // invoiceDto and policy belong to the actual application.
}
~~~

These are **detached methods illustrating annotations**, not an immediately runnable standalone class. Methods must belong to a Spring-managed bean, method security must be enabled, and calls must go through the appropriate interception/proxy mechanism. One method on the same instance internally calling another method can bypass AOP advice, so do not assume annotations always protect self-invocation.

Expressions can use `and`, `or`, but policies should be analyzed before combining: `or` means **only one condition needs to be true**. If business rules require both a token scope and an internal permission, use `and` or a policy bean evaluating all constraints.

Example with permission and object check:

~~~java
@PreAuthorize(
    "hasAuthority('invoice:read') " +
    "and @invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceDto findInvoice(long invoiceId) {
    return invoiceQueryService.findInvoice(invoiceId);
}
~~~

The snippet above only works when the application provides the `invoicePolicy` bean, `invoiceQueryService`, and the corresponding `InvoiceDto` type; the `#invoiceId` parameter must be properly resolved via parameter metadata or compiler configuration. Neither `hasAuthority` nor `hasRole` **automatically checks** that a resource belongs to the right tenant/owner.

### `@Secured` and `@RolesAllowed` should not have their conventions mixed

Some applications also use `@Secured` or `@RolesAllowed` (JSR-250) after enabling their respective support. They have their own syntax and role-handling rules. Do not copy strings verbatim from `@PreAuthorize` to another annotation without checking the documentation for the version in use. For this lesson, prioritize mastering `@PreAuthorize` and the HTTP DSL first.

## 9. The default prefix mechanism can be customized

Spring Security supports configuring the default prefix for role checks in applicable mechanisms. For example, in method security using `GrantedAuthorityDefaults`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Configuration
public class RolePrefixConfig {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }
}
~~~

The idea behind the configuration above: in **expression handlers** that use this `GrantedAuthorityDefaults`, `hasRole('ADMIN')` is evaluated with the `APP_` prefix, meaning it looks for `APP_ADMIN` instead of `ROLE_ADMIN`.

**However, do not infer that every API changes prefix simply because the bean exists.** Some ways of creating `AuthorizationManager` have their own behavior. For instance, the Javadoc of `AuthorityAuthorizationManager.hasRole("ADMIN")` in Spring Security 6.x specifies that the required string has the `ROLE_` prefix; if you explicitly want a custom authority, `hasAuthority("APP_ADMIN")` remains the exact string check. Newer versions may offer different factories/configurations; verify the exact API and test actual behavior for both URL authorization and method security.

Additionally, changing the prefix **does not migrate data automatically**:

~~~text
Before configuration:
  Authentication.authorities = ["ROLE_ADMIN"]
  hasRole("ADMIN") --> looks for "ROLE_ADMIN"

After changing prefix in an applicable mechanism:
  Authentication.authorities = ["ROLE_ADMIN"]   // still old data
  hasRole("ADMIN") --> looks for "APP_ADMIN"    // no match

To match, the Authentication source must also grant "APP_ADMIN".
~~~

When changing the prefix, everything must be aligned: user creation, JWT mappers, role data, test helpers, HTTP rules, method security, custom managers, and role hierarchy. Customizing the prefix just to "avoid typing `ROLE_`" can incur significant operational cost; for typical applications, keeping the default standard is usually easier to read and control.

## 10. How does `ROLE_` differ from `SCOPE_` and business permissions?

Many applications use OAuth 2.0 Resource Server JWT. With the common default converter, scopes from the `scope` or `scp` claim are converted into authorities starting with `SCOPE_`.

Suppose an access token contains:

~~~json
{
  "sub": "user-42",
  "scope": "invoices.read invoices.approve"
}
~~~

Mapped authorities may be:

~~~text
SCOPE_invoices.read
SCOPE_invoices.approve
~~~

Then:

~~~java
.hasAuthority("SCOPE_invoices.read")  // Matches mapped scope
.hasRole("ADMIN")                     // Not automatically true just because token has scope
.hasAuthority("invoice:read")        // Not automatically true just because token has SCOPE_invoices.read
~~~

**Things never to assume automatically:**

- `SCOPE_invoices.read` does not mean `ROLE_ADMIN`.
- `ROLE_ADMIN` does not automatically generate `invoice:read`.
- `invoice:read` does not by itself prove permission to read **all** invoices in another tenant.
- An access token having a scope does not mean the permissions granted to the principal in the database or IAM are identical.
- Spring Security's default JWT converter usually understands **scope**, and does not automatically turn every provider-specific `roles` claim into `ROLE_*`.

If you want to turn roles/permissions from a JWT into authorities, clearly specify which claim is trusted, issuer/audience, and the mapping logic; then test the whole pipeline from token verification → `Authentication` creation → rule evaluation. Never use an unverified token or let clients self-assign claims.

## 11. Role hierarchy does not replace the prefix rule

Spring Security can support a **role hierarchy**, for instance a configuration stating `ROLE_ADMIN` includes the authorities enjoyed by `ROLE_USER`. That only happens if the application **has configured** a hierarchy and the active checker actually uses it.

~~~text
Without hierarchy configured:
  Authorities = ["ROLE_ADMIN"]
  hasRole("USER") --> false

With hierarchy applied and ADMIN > USER declared:
  Authorities = ["ROLE_ADMIN"]
  hasRole("USER") --> can be true per hierarchy
~~~

The `>` symbol in the description represents an application-declared permission relationship, not something inferred from role names. When a hierarchy is present, `hasAuthority` may also be evaluated against reachable authorities depending on the specific authorization mechanism, so equivalence with a simple `Set.contains` operation must be understood in a context **without additional hierarchy**.

Role hierarchy design must prevent unintentionally granting broader permissions than intended. An admin role for tenant T1 does not gain permissions on tenant T2 through hierarchy alone.

## 12. Standalone Java 17 example: observe matching directly

To solidify the meaning of the prefix, the example below simulates the **basic default rule** in plain Java. The program does not use Spring Security and **does not simulate** custom prefix configuration or role hierarchies; it only demonstrates why `hasRole("ADMIN")` typically corresponds to authority `ROLE_ADMIN`.

Save as `RolePrefixDemo.java`:

~~~java
import java.util.Set;

public class RolePrefixDemo {
    static boolean hasAuthority(Set<String> granted, String required) {
        return granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String roleName) {
        return hasAuthority(granted, "ROLE_" + roleName);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN",
                "invoice:read",
                "SCOPE_invoices.read"
        );

        System.out.println(
                "hasAuthority(ROLE_ADMIN): "
                + hasAuthority(granted, "ROLE_ADMIN"));

        System.out.println(
                "hasAuthority(ADMIN): "
                + hasAuthority(granted, "ADMIN"));

        System.out.println(
                "hasRole(ADMIN): "
                + hasRole(granted, "ADMIN"));

        System.out.println(
                "hasRole(USER): "
                + hasRole(granted, "USER"));

        System.out.println(
                "hasAuthority(invoice:read): "
                + hasAuthority(granted, "invoice:read"));

        System.out.println(
                "hasRole(invoice:read): "
                + hasRole(granted, "invoice:read"));

        System.out.println(
                "hasAuthority(SCOPE_invoices.read): "
                + hasAuthority(granted, "SCOPE_invoices.read"));
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac RolePrefixDemo.java
java RolePrefixDemo
~~~

Standard output:

~~~text
hasAuthority(ROLE_ADMIN): true
hasAuthority(ADMIN): false
hasRole(ADMIN): true
hasRole(USER): false
hasAuthority(invoice:read): true
hasRole(invoice:read): false
hasAuthority(SCOPE_invoices.read): true
~~~

Explanation:

- `ROLE_ADMIN` was granted, so the exact match succeeds.
- `ADMIN` was not granted, so `hasAuthority("ADMIN")` fails.
- `hasRole("ADMIN")` prepends the prefix to form `ROLE_ADMIN`, so it succeeds.
- `ROLE_USER` is not in the set, so `hasRole("USER")` fails.
- `invoice:read` is a granted authority, so `hasAuthority("invoice:read")` succeeds.
- `hasRole("invoice:read")` looks for `ROLE_invoice:read`, so it fails.
- `SCOPE_invoices.read` does not need `hasRole`; `hasAuthority` suffices to match verbatim.

In a real application, do not reimplement `hasRole` as a policy replacing Spring Security; the program only lets you observe the rule without loading the framework.

## 13. Testing in Spring Security: catching prefix mistakes

Example HTTP testing with `Spring Security Test`, `MockMvc`, and an endpoint guarded by `hasRole("ADMIN")`. Assume the application defines `GET /api/admin/ping` returning `200 OK` for authorized callers and has the security filter chain enabled.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleIsAccepted() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void exactPrefixedAuthorityIsAccepted() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void RawAuthorityIsNotAnAdminRole() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserIsForbidden() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Conditions for this example:** the test class only runs when the project has the `GET /api/admin/ping` endpoint, the matching role rule, Spring Boot Test/Spring Security Test dependencies, and no other rule altering the decision. If the application does not yet have the endpoint, create a test endpoint or pick an existing admin endpoint; this snippet is a **project test template**, not standalone Java source.

The third test method name is self-explanatory: a raw `ADMIN` authority **does not** satisfy the `ADMIN` role rule under the default convention. Note that Spring Security Test simulates granted authorities and **does not verify** loading roles from a database or mapping JWTs; add separate integration tests for the real authentication flow.

### Minimum test scenario set

| Principal's authority set | Rule | Expected |
|---|---|---|
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Allow |
| `ADMIN` | `hasRole("ADMIN")` | Deny |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Allow |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Deny |
| `invoice:read` | `hasAuthority("invoice:read")` | Allow |
| `ROLE_ADMIN` | `hasAuthority("invoice:read")` | Deny if no mapping/hierarchy |
| `SCOPE_invoices.read` | `hasAuthority("SCOPE_invoices.read")` | Allow |
| `SCOPE_invoices.read` | `hasRole("ADMIN")` | Deny |

Add tests for missing authentication or invalid authentication to verify `401`/`403` flows match the application's entry point and handler. For multi-tenant applications, continue testing resource policies: passing a role rule does not mean reading every record is allowed.

## 14. Debugging "has the role yet still gets 403"

Follow this checklist in order instead of guessing rule changes:

1. **Confirm the HTTP route/method**: which matcher is the request hitting? Is the rule blocked by an earlier matcher? For method security, which method has the annotation and is the interceptor running?
2. **Confirm valid authentication**: is there an actual principal? Do not confuse an authentication error with a missing-permission error.
3. **Inspect the effective authority list**: e.g., does safe observed data show `[ADMIN]` or `[ROLE_ADMIN]`? Do not log credentials, full access tokens, or sensitive data.
4. **Identify what the rule requires**: `hasRole("ADMIN")` requires `ROLE_ADMIN` in default config, whereas `hasAuthority("ADMIN")` requires `ADMIN`.
5. **Check the authority source**: are `UserDetailsService`, `AuthenticationProvider`, database mapper, JWT converter, or IdP adding/omitting/doubling the prefix?
6. **Check custom prefix/hierarchy**: does the application have `GrantedAuthorityDefaults`, a custom authorization manager, or a role hierarchy causing unexpected outcomes?
7. **Check other rules**: a request can pass the HTTP rule and still be denied by `@PreAuthorize`, ACL/object policy, or business conditions.
8. **Lock it down with a negative test**: add a test proving a principal with only `ADMIN` is denied if the rule requires role `ADMIN` with the default prefix; test that the right authority succeeds.

Common error example:

~~~text
Database role: ADMIN
          |
Wrong mapping: new SimpleGrantedAuthority("ADMIN")
          |
Authentication authorities: [ADMIN]
          |
HTTP rule: hasRole("ADMIN")
          |
Required authority: ROLE_ADMIN
          |
Result: denied
~~~

The fix is to **align the authority producer and the rule**. You can map logical role `ADMIN` to `ROLE_ADMIN`, or if the system intentionally uses raw authority `ADMIN` then check with `hasAuthority("ADMIN")` and standardize the convention; do not randomly patch individual endpoints to mask mapping bugs.

## 15. Misconceptions to avoid

| Misconception | Reality |
|---|---|
| "`hasRole` queries the roles table." | `hasRole` checks authorities already attached to `Authentication` using the prefix convention. |
| "`hasAuthority("ADMIN")` is the same as `hasRole("ADMIN")`." | By default, one requires `ADMIN` and the other requires `ROLE_ADMIN`. |
| "`hasAuthority` also prepends `ROLE_`." | `hasAuthority` matches the passed authority verbatim. |
| "Passing `ROLE_ADMIN` to `hasRole` always works / always errors." | Behavior depends on the API and expression mechanism; choose `hasRole("ADMIN")` for consistency. |
| "Having role ADMIN definitely grants every permission." | Only explicitly defined authorities/mappings/hierarchies apply. |
| "Changing the prefix automatically updates data in `Authentication`." | Only matching rules change; the authority producer must be aligned separately. |
| "Mock user roles passing means the JWT converter is also right." | Mock tests bypass many authentication steps; test converters/claims separately. |
| "An OAuth scope is a role." | `SCOPE_*` and `ROLE_*` are normally two distinct conventions and do not imply each other. |
| "Having `ROLE_ADMIN` allows viewing every resource." | Function-level roles do not replace object-level, tenant/owner, and business condition checks. |

## 16. Usage checklist in code review

Before merging an authorization change, verify:

- **Authority contract:** which exact strings are attached to `Authentication`? E.g., `ROLE_ACCOUNTANT`, `invoice:read`, or `SCOPE_invoices.read`.
- **Granting source:** which database/IAM/JWT/LDAP is responsible, and has the data been verified?
- **API called:** `hasRole` receives the logical role name; `hasAuthority` receives the full authority string.
- **Prefix:** default `ROLE_` or a configured prefix? Does the configuration apply to both HTTP and method authorization?
- **Permission vs role:** does the endpoint need a title/role or a specific action permission?
- **Object-level access:** do tenant, owner, resource status, or sharing policies need checking?
- **Tests:** are there both allow and deny cases with missing prefixes, extra prefixes, and wrong names?

If a project needs a simple convention, it can standardize on: **store roles at the business layer like `ADMIN`; when building `Authentication`, map to `ROLE_ADMIN`; call `hasRole("ADMIN")` for roles, call `hasAuthority("invoice:read")` for permissions, and `hasAuthority("SCOPE_invoices.read")` for mapped scopes**. This is a consistent design choice, not a mandatory rule of Spring Security.

## 17. Self-check questions

**Q1.** A user only has authority `ADMIN`. Does `hasRole("ADMIN")` allow them through by default?  
**No**. It requires `ROLE_ADMIN`.

**Q2.** A user only has authority `ROLE_ADMIN`. Does `hasAuthority("ADMIN")` allow them through?  
**No**. `hasAuthority` matches the exact string and adds no prefix.

**Q3.** How do you check the ADMIN role using the default Spring Security HTTP DSL?  
**`hasRole("ADMIN")`**. Another explicit way is `hasAuthority("ROLE_ADMIN")`.

**Q4.** Which authority does `.roles("ADMIN")` in the `UserDetails` builder typically create?  
**`ROLE_ADMIN`**.

**Q5.** Is `@WithMockUser(authorities = "ADMIN")` equivalent to `@WithMockUser(roles = "ADMIN")`?  
**No**: one creates `ADMIN`, while the other creates `ROLE_ADMIN`.

**Q6.** Does having authority `SCOPE_invoices.read` automatically satisfy `hasAuthority("invoice:read")`?  
**No**. The two strings do not match and policies do not infer mappings.

**Q7.** After configuring the prefix to `APP_` in an expression handler, what does `hasRole('ADMIN')` require?  
**`APP_ADMIN`** in the expression handler that actually applies that configuration. Check other authorization managers separately.

**Q8.** Why should you not claim `hasRole("ROLE_ADMIN")` always throws an error?  
Because **there is a difference between Java `AuthorityAuthorizationManager.hasRole` and some SpEL `SecurityExpressionRoot.hasRole` implementations**. The most portable and clear way to write it remains `hasRole("ADMIN")`.

**Q9.** When the authority in authentication is `ROLE_ADMIN` yet the request is still denied, is `hasRole("ADMIN")` definitely wrong?  
**No**. You must check matchers, other rules, custom prefixes, method security, role hierarchies, object policies, and the authentication flow.

### Official documentation

- Spring Security – Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 – `AuthorityAuthorizationManager` JavaDoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 6.5 – `SecurityExpressionRoot` JavaDoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html
