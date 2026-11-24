# RoleHierarchy and Inherited Privileges Between Roles in Spring Security Servlet

## 1. Why Is RoleHierarchy Needed?

Suppose an administrative system has three roles:

- **USER**: allowed to view their own profile.
- **MANAGER**: allowed to perform USER actions plus management functions.
- **ADMIN**: allowed to perform MANAGER actions plus administrative functions.

Without an inheritance model, you might have to assign every administrator `ROLE_ADMIN`, `ROLE_MANAGER`, and `ROLE_USER`; or on every new endpoint write combinations like `hasAnyRole("USER", "MANAGER", "ADMIN")`. Both approaches duplicate logic, are hard to maintain, and risk missing rules when new roles are introduced.

**`RoleHierarchy`** in Spring Security solves *deriving inherited privileges* from relationships between roles/authorities:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER
~~~

With this relationship:

- Someone **directly assigned** `ROLE_ADMIN` can be **treated as having** `ROLE_MANAGER` and `ROLE_USER` when an authorization mechanism **is integrated with RoleHierarchy**.
- Someone who only has `ROLE_MANAGER` can be treated as having `ROLE_USER`, but does **not** become ADMIN.
- Someone who only has `ROLE_USER` does **not** get higher roles.
- The relationship is **transitive**: ADMIN → MANAGER and MANAGER → USER implies ADMIN → USER.
- **Assigned** privileges and **derived** privileges are two distinct concepts.

The last point is essential: **declaring a RoleHierarchy bean does not mean every `AuthorizationManager`, expression handler, or authorization library in the application automatically uses it**. Each integration point must be verified per API/version. The runnable example in Section 9 **explicitly wires the hierarchy** into the `authorizeHttpRequests` managers to avoid relying on auto-configuration assumptions.

This article targets **Spring Boot 3.x / Spring Security 6.x, Java 17+, Servlet stack**; the focus is managing role relationships and applying them in the right places. It does not replace object-level permissions, owner/tenant checks, or credential verification.

## 2. From GrantedAuthority to Role Hierarchy

### 2.1. Spring Security Evaluates Authority Strings

After a user logs in, `Authentication` typically holds a list of `GrantedAuthority` instances. An example:

~~~text
Authentication
  principal   = "alice"
  authenticated = true
  authorities = ["ROLE_MANAGER"]
~~~

In Spring Security, roles are fundamentally represented as **authority strings** with the `ROLE_` prefix by default convention:

| Check style | Default required authority | Meaning |
| --- | --- | --- |
| `hasRole("USER")` | `ROLE_USER` | Typically used to check the USER role |
| `hasRole("MANAGER")` | `ROLE_MANAGER` | Checks the MANAGER role |
| `hasAuthority("ROLE_USER")` | `ROLE_USER` | Exact match on full authority |
| `hasAuthority("report:read")` | `report:read` | Specific string permission/scope |
| `authenticated()` | Not a role | Checks authentication status |

**Do not call `hasRole("ROLE_ADMIN")` when using the default prefix rule.** Normally use `hasRole("ADMIN")`; if you want to check the already-prefixed string, use `hasAuthority("ROLE_ADMIN")`. A system can customize the prefix, but once changed it must stay consistent across the entire hierarchy configuration, role managers, expression handlers, and identity provider mappings.

### 2.2. Directly Assigned Authorities vs. Effective Authorities

Suppose the database assigns only `ROLE_ADMIN` to bob. The initial privileges after authentication might be:

~~~text
Direct authorities:    [ROLE_ADMIN]
Reachable authorities: [ROLE_ADMIN, ROLE_MANAGER, ROLE_USER]
~~~

`Reachable authorities` are the **result derived from the hierarchy**, not necessarily the list actually stored inside `Authentication.getAuthorities()`. If you inspect the raw Authentication object, you may still see only `ROLE_ADMIN`. That is normal.

Components such as `AuthorityAuthorizationManager` or the method-security expression handler can call `RoleHierarchy#getReachableGrantedAuthorities(...)` when configured. **If an authorization check is not integrated with the hierarchy, it may not see inherited roles**.

Therefore, do not write:

~~~java
authentication.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_USER"));
~~~

and conclude ADMIN definitely lacks USER access. That snippet only checks **direct authorities**. It is appropriate if you genuinely want to verify a direct assignment, but it is **not** equivalent to a check that considers role hierarchy. For effective-privilege checks, use a hierarchy-aware manager/expression handler or invoke the hierarchy explicitly.

### 2.3. Role Hierarchy Does Not Create Accounts

`RoleHierarchy` does not replace `AuthenticationManager`, `UserDetailsService`, `PasswordEncoder`, or JWT signature verification. Nor does it modify database role tables, write new privileges into tokens, create sessions, or "promote" users over time.

The typical flow is:

~~~text
Credentials/token verified
            |
            v
Trusted Authentication containing direct authorities
            |
            v
AuthorizationManager / expression handler
            |
            +-- RoleHierarchy computes reachable authorities
            |
            v
Allow/deny decision based on required role/permission
~~~

If an incoming token contains unverified client-claimed roles, a hierarchy merely **amplifies the privilege-granting flaw**. The foundation is always secure authentication and claim mapping.

## 3. Directed Inheritance Model and Transitivity

### 3.1. Relationship Syntax

One way to declare relationships in `RoleHierarchyImpl` is a sequence of lines:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

The `>` symbol means **the role on the left includes the privileges of the role on the right**. Never reverse the direction:

~~~text
ROLE_MANAGER > ROLE_ADMIN
~~~

that line would mean MANAGER inherits ADMIN — very dangerous if you define MANAGER as the lower role.

Visualized as sets:

| Direct role | Effective roles in the example |
| --- | --- |
| `ROLE_ADMIN` | `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER` |
| `ROLE_MANAGER` | `ROLE_MANAGER`, `ROLE_USER` |
| `ROLE_USER` | `ROLE_USER` |
| No role in the tree above | Receives no extra roles from the tree |

Transitivity allows extending across multiple levels, but **do not create unnecessarily deep hierarchies**. A role graph with too many edges makes derived privileges hard to review and easily violates least privilege.

### 3.2. RoleHierarchy Also Handles Multiple Branches

Example:

~~~text
ROLE_ADMIN > ROLE_OPERATIONS
ROLE_ADMIN > ROLE_FINANCE
ROLE_OPERATIONS > ROLE_USER
ROLE_FINANCE > ROLE_USER
~~~

ADMIN implies OPERATIONS, FINANCE, and USER; OPERATIONS and FINANCE each include USER without implying each other. This is a directed graph model, not necessarily a single linear chain.

Name roles after **actual responsibilities**, not under the assumption that every role fits on a single ladder. In particular, do not invent a "SUPER_ROLE" spanning every domain just to simplify tests if separation-of-duties policies forbid combining those privileges.

### 3.3. Avoid Cycles and Hard-to-Audit Graphs

A cyclic relationship can make two roles equivalent in inherited privileges:

~~~text
ROLE_A > ROLE_B
ROLE_B > ROLE_A
~~~

Do not intentionally or accidentally introduce cycles when A is meant to outrank B. Depending on the implementation/version, role hierarchy may handle or warn about cycles differently; the key is **never relying on implicit behavior when a cycle exists**.

It is best to maintain a **directed acyclic graph (DAG)** when roles represent distinct tiers and responsibilities. Test both intended inclusions and the absence of unintended privileges.

### 3.4. A Higher Role Does Not Necessarily Get Every Permission

If an endpoint's specific policy is `hasAuthority("billing:refund")`, an ADMIN assigned `ROLE_ADMIN` does not necessarily have the `billing:refund` string. RoleHierarchy only expands authorities that have **declared relationships** and at checkpoints that use the hierarchy.

For example:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

does **not** automatically imply:

~~~text
ROLE_ADMIN > billing:refund
ROLE_ADMIN > deploy:production
~~~

unless you explicitly declared that relationship/mapping or granted permissions another way. This is an advantage: isolating special privileges like issuing refunds or deploying to production from general roles.

## 4. Core Spring Security APIs

Key types:

- `org.springframework.security.access.hierarchicalroles.RoleHierarchy`: abstraction for expanding authorities.
- `org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl`: common implementation.
- `org.springframework.security.core.GrantedAuthority`: an assigned or derived privilege.
- `org.springframework.security.core.authority.SimpleGrantedAuthority`: simple implementation holding an authority string.
- `org.springframework.security.authorization.AuthorityAuthorizationManager`: manager checking roles/authorities; can be wired with a `RoleHierarchy`.
- `org.springframework.security.web.access.intercept.RequestAuthorizationContext`: HTTP authorization context from `authorizeHttpRequests`.
- `org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler`: one way to configure expressions for method security.

### 4.1. Creating RoleHierarchyImpl

Example that runs on the common Spring Security 6 branch:

~~~java
@Bean
RoleHierarchy roleHierarchy() {
    RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
    hierarchy.setHierarchy("""
        ROLE_ADMIN > ROLE_MANAGER
        ROLE_MANAGER > ROLE_USER
        """);
    return hierarchy;
}
~~~

Place this in a `@Configuration` class with appropriate imports. `setHierarchy(String)` is a familiar Spring Security 6 API; in some newer versions it is marked **deprecated** in favor of factories/builders. For production, check your pinned version and migrate to the recommended initialization style in that version; do not copy a newer version's API into an older project without verifying.

Java text blocks `"""..."""` require Java 15+, so a **Java 17** project works cleanly.

### 4.2. getReachableGrantedAuthorities

You can inspect the result with an illustrative snippet:

~~~java
RoleHierarchy hierarchy = /* configured RoleHierarchy bean */;
var direct = List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
var reachable = hierarchy.getReachableGrantedAuthorities(direct);
~~~

This is a **snippet**, not a standalone class. `reachable` contains the authorities reachable along hierarchy edges, including the direct authorities. Do not rely on collection iteration order as a business requirement; when printing stable output, use `map(GrantedAuthority::getAuthority).sorted().toList()`.

### 4.3. RoleHierarchy Is an Authorization Rule, Not a User Repository

When user `admin` logs in, `UserDetailsService` may supply only `ROLE_ADMIN`. RoleHierarchy maps privileges at check time — there is no need to "duplicate" all three roles in the database just to simulate inheritance.

However, if part of the system does not use RoleHierarchy (for instance, a custom service reading `authentication.getAuthorities()` and comparing strings directly), results across layers can diverge. **Keep policy sources consistent and test every protected entry point.**

## 5. Integrating Properly with authorizeHttpRequests on Servlet

### 5.1. Do Not Assume Declaring a Bean Alone Is Enough

This example may look right, yet should not be treated as proof the hierarchy applies across all versions/configurations:

~~~java
@Bean
RoleHierarchy roleHierarchy() {
    RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
    hierarchy.setHierarchy("ROLE_ADMIN > ROLE_USER");
    return hierarchy;
}

// Elsewhere:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/user/**").hasRole("USER")
);
~~~

Different versions/extension points have different auto-discovery behavior. If the manager is constructed **without receiving RoleHierarchy**, a user holding only `ROLE_ADMIN` can be denied on `hasRole("USER")`. Test actual behavior rather than inferring from the bean's existence.

### 5.2. Explicit Configuration via AuthorityAuthorizationManager

You can build a dedicated manager per role and attach the hierarchy:

~~~java
AuthorityAuthorizationManager<RequestAuthorizationContext> userRule =
    AuthorityAuthorizationManager.hasRole("USER");
userRule.setRoleHierarchy(roleHierarchy);

AuthorityAuthorizationManager<RequestAuthorizationContext> adminRule =
    AuthorityAuthorizationManager.hasRole("ADMIN");
adminRule.setRoleHierarchy(roleHierarchy);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").access(adminRule)
    .requestMatchers("/user/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

This is a **configuration snippet** assuming an existing `roleHierarchy` bean; a complete example is provided in Section 9. `AuthorityAuthorizationManager` checks privileges using the `RoleHierarchy` attached to that manager instance. Using `.access(...)` ensures the DSL uses that exact manager.

Benefits:

- Does not depend on assuming "Spring Security automatically discovers the RoleHierarchy bean everywhere".
- Inheritance can be tested clearly per endpoint.
- Reading the config immediately shows which managers use the hierarchy.
- Easy to separate role-hierarchy rules from policies requiring standalone authorities.

### 5.3. Rule Order Still Matters

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").access(adminRule)
    .requestMatchers("/user/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

These are two distinct URLs so they do not overlap. For nested URLs, place more specific matchers before broader ones:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").access(adminRule)
    .requestMatchers("/api/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

`RequestMatcherDelegatingAuthorizationManager` selects **the first rule whose matcher matches**, and applies that rule's manager. It does not fall through to `userRule` later if `adminRule` denies access.

Hierarchy only affects a manager's **effective privileges**; it does not change `RequestMatcher` selection or `SecurityFilterChain` ordering.

### 5.4. AuthenticationEntryPoint and AccessDeniedHandler

If a request without credentials hits `/user/**`, the application may return **401** (HTTP Basic) or redirect to the login page (formLogin). If already authenticated without sufficient role, it typically returns **403**. That is the behavior of `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler` in the chain.

**RoleHierarchy does not choose the HTTP status code.** It determines which authorities are considered when the manager evaluates access; the HTTP response mechanism depends on authentication type and exception handling.

### 5.5. Should hasAuthority Use Inheritance?

`AuthorityAuthorizationManager.hasAuthority("report:read")` can be wired with a RoleHierarchy if the system defines edges to that authority, such as `ROLE_MANAGER > report:read`. However, using role hierarchy to inherit **permission strings** requires care: `report:read` is not a role by naming convention, and other components might not interpret it as you expect.

**Separating role hierarchy from permission mapping is easier to audit in many large systems.** Roles describe functions/responsibilities, permissions describe actions; a policy service can map roles→permissions per business rules. If role→permission edges exist in a hierarchy, document the contract clearly and test all entry points.

## 6. Integrating with Method Security: Verify Separately

HTTP authorization protects URLs. For sensitive business logic, Spring Security also provides method security:

~~~java
@PreAuthorize("hasRole('USER')")
public Profile loadProfile() {
    // ...
}
~~~

This snippet is **not** standalone-compilable; method security must be enabled and the method must belong to a Spring bean behind an appropriate AOP proxy.

For the hierarchy to take effect in expression-based method security, you can configure the handler explicitly (inside a configuration with `@EnableMethodSecurity`):

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {

    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();

    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

Required imports:

~~~java
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.context.annotation.Bean;
~~~

Depending on the **Spring Security version**, a `RoleHierarchy` bean may be supported by another auto-configuration mechanism. The snippet above expresses the intent of **explicitly wiring the hierarchy into the expression handler** for predictability. If the project already defines a custom `MethodSecurityExpressionHandler`, do not add a competing bean—configure the active handler instead. Test method-level authorization in a real context.

**Important AOP note:** method security may not run when a method in the same object directly calls another protected method on itself (**self-invocation**) because the call bypasses the proxy. Hierarchy does not solve proxy bypass; design service boundaries carefully and test methods through Spring proxies.

### 6.1. HTTP Rules and Method Rules Can Apply Together

Example:

~~~text
HTTP: GET /api/reports/42
  |
  +-- HTTP manager requires ROLE_USER -> allowed via ROLE_ADMIN > ROLE_USER
  |
  +-- Service method requires report:read and matching tenant
        |
        +-- user lacks permission/wrong tenant -> denied
~~~

Role hierarchy expands hierarchical roles; **it does not eliminate** fine-grained permission policies, ownership, or tenant isolation.

## 7. Cases Where You Should NOT Inherit Roles

### 7.1. Separation of Duties

An organization has two roles:

- `ROLE_PAYMENT_CREATOR`: creates payout requests.
- `ROLE_PAYMENT_APPROVER`: approves payout requests.

Do not define `ROLE_PAYMENT_APPROVER > ROLE_PAYMENT_CREATOR` just because "approver" sounds higher-ranking. Policy may **intentionally require the creator and approver to be two separate principals**. Wrong inheritance breaks the four-eyes principle.

Similarly, `ROLE_SUPPORT`, `ROLE_SECURITY_AUDITOR`, and `ROLE_DB_OPERATOR` may represent responsibility groups that **do not include one another**. Never treat hierarchy as a total ordering over every role.

### 7.2. Object/Tenant-Scoped Privileges

In a multi-tenant system, a user with `ROLE_ADMIN` in tenant A is **not** automatically an ADMIN in tenant B. A global hierarchy:

~~~text
ROLE_ADMIN > ROLE_USER
~~~

only describes inclusion **by role name**, carrying no tenant context. Without encoding scope into `Authentication`/policy or checking tenancy in the service, a global ADMIN role can cause overauthorization.

The usual solution is binding roles to tenants and real policies, such as a `TenantMembership(userId, tenantId, role)` check in the service or a custom `AuthorizationManager` reading a trusted source. Never treat a client-supplied `?tenantId=A` as proof of membership.

### 7.3. Roles Are Not Equivalent to Permissions

A business unit might want:

- USER to view their own profile.
- MANAGER to view profiles of staff in their team.
- ADMIN to view system reports.

That does not mean ADMIN may view **every** personal profile. A linear RoleHierarchy `ADMIN > MANAGER > USER` is only appropriate when **aggregate privileges genuinely** subsume lower tiers. Do not build a hierarchy first and force privacy policies to bend around it.

### 7.4. Scope/Token-Based Authorities

In an OAuth2 resource server, authorities can come from scopes like `SCOPE_read` or verified role claims. Do not assume scopes automatically inherit like `ROLE_` without a trusted mapping. JWTs require signature/issuer/audience/expiration verification; role mapping must come from a trusted IdP, and claims can remain stale until token expiry/revocation.

### 7.5. Special Permissions with Their Own Lifecycle

Certain privileges like `deploy:production`, `refund:high_value`, or `export:pii` typically require MFA/step-up, approval, time bounds, or auditing. Do not tuck these permissions under ADMIN just to simplify a hierarchy. When a privilege has dynamic conditions, use a policy service or dedicated `AuthorizationManager`.

## 8. Technical Notes: Authorities Are Not Automatically "Transformed" in Tokens/Sessions

### 8.1. Authentication.getAuthorities() May Remain Unchanged

Suppose Spring Security authenticates user `admin` and returns:

~~~text
authentication.getAuthorities() = [ROLE_ADMIN]
~~~

After attaching RoleHierarchy to a manager, `hasRole("USER")` can allow this user, while calling `authentication.getAuthorities()` still returns only `ROLE_ADMIN`. Do not compare the direct list with the reachable list and conclude Spring Security "dropped roles".

In an admin UI, if you need to display **actually assigned** roles, show direct roles; if you need to explain **effective privileges**, show reachable roles with a clear note that they are derived. The demo's `GET /roles` is only for learning; production should not expose authority lists arbitrarily to every client.

### 8.2. Sessions and Tokens Can Hold Stale Data

If you change a hierarchy from:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

to:

~~~text
ROLE_ADMIN > ROLE_MANAGER
~~~

managers using the new bean can change reachable authorities immediately after deployment; however:
- Some server instances may still run the old configuration during a rolling deployment.
- Sessions/JWTs may hold **old direct authorities** or stale claims.
- Cached authorization decisions may not have refreshed yet.
- Custom code not using the hierarchy may behave differently.

Plan rollout/versioning, invalidation/re-authentication when sensitive privileges change, and multi-instance testing. **RoleHierarchy does not automatically revoke JWTs or sessions**.

### 8.3. Computing Reachable Authorities and Performance

Role hierarchy can typically precompute/cache relationships so privilege lookup stays efficient; the more roles/edges in your configuration, the more you should measure startup time and complexity. Do not treat it as a database policy engine or build arbitrary privilege graphs from unauthenticated user input.

For dynamic per-object business rules, put optimized, data-controlled checks in services/policies rather than rebuilding a hierarchy on every HTTP request.

## 9. Complete Example: Spring Boot 3.3.13, Java 17, HTTP Basic, and MockMvc

The project below constructs **one `RoleHierarchyImpl`** and wires it **explicitly** into three `AuthorityAuthorizationManager` instances. The app has four demo users:

| Username | Direct role | Reachable roles | Accessible endpoints |
| --- | --- | --- | --- |
| `user` | `ROLE_USER` | USER | `/user` |
| `manager` | `ROLE_MANAGER` | MANAGER, USER | `/manager`, `/user` |
| `admin` | `ROLE_ADMIN` | ADMIN, MANAGER, USER | `/admin`, `/manager`, `/user` |
| `auditor` | `ROLE_AUDITOR` | AUDITOR | None of the three role endpoints above |

All use the learning password `demo-pass`; this is **not** a production configuration. The demo uses `httpBasic` to test 401/403 without form login/CSRF tokens for GET endpoints. When exposing HTTP Basic over the Internet, HTTPS is mandatory, and an appropriate authentication/threat model should be applied.

### 9.1. Directory Structure

~~~text
role-hierarchy-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/roles/
    │       ├── RoleHierarchyApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/com/example/roles/
            └── RoleHierarchyTests.java
~~~

**`pom.xml`**

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>role-hierarchy-demo</artifactId>
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
~~~

**`src/main/java/com/example/roles/RoleHierarchyApplication.java`**

~~~java
package com.example.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleHierarchyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleHierarchyApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig.java: Explicit Hierarchy + Managers

**`src/main/java/com/example/roles/SecurityConfig.java`**

~~~java
package com.example.roles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    RoleHierarchy roleHierarchy() {
        RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
        hierarchy.setHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_USER
            """);
        return hierarchy;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RoleHierarchy roleHierarchy) throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext> adminRule =
            AuthorityAuthorizationManager.hasRole("ADMIN");
        adminRule.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> managerRule =
            AuthorityAuthorizationManager.hasRole("MANAGER");
        managerRule.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> userRule =
            AuthorityAuthorizationManager.hasRole("USER");
        userRule.setRoleHierarchy(roleHierarchy);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").access(adminRule)
                .requestMatchers("/manager").access(managerRule)
                .requestMatchers("/user").access(userRule)
                .requestMatchers("/roles").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("user")
                .password(encoded)
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(encoded)
                .roles("MANAGER")
                .build(),
            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build(),
            User.withUsername("auditor")
                .password(encoded)
                .roles("AUDITOR")
                .build()
        );
    }
}
~~~

**Design analysis:**

1. `RoleHierarchyImpl` declares two edges. From those, ADMIN implies MANAGER and USER by transitivity.
2. Each `AuthorityAuthorizationManager<RequestAuthorizationContext>` is created via `hasRole(...)`, then **explicitly wired with the exact same RoleHierarchy bean**.
3. `.access(adminRule/managerRule/userRule)` states explicitly which HTTP rules use the hierarchy-enabled managers. We do not rely on a RoleHierarchy bean being auto-wired into the matcher DSL.
4. `.anyRequest().denyAll()` denies unlisted URLs; the example needs no controller for arbitrary paths.
5. The `auditor` account has no inheritance path to USER and therefore cannot access `/user`.
6. `HttpBasic` does not derive roles from URLs/queries. Authentication verifies BCrypt passwords against the demo `UserDetailsService`.
7. `setHierarchy(...)` may be deprecated in newer versions; it is still used in Spring Security 6 examples that have this API. When upgrading, switch to the factory/builder confirmed by your target version without guessing behavior.

**Never add a "global hasRole bypass" for ADMIN.** Even as ADMIN, the user still passes through the chosen manager; the hierarchy lets ADMIN pass the USER/MANAGER managers because of **declared relationships**, not because Spring Security treats the word "ADMIN" as special.

### 9.3. Controller: Inspecting Direct and Reachable Roles

**`src/main/java/com/example/roles/DemoController.java`**

~~~java
package com.example.roles;

import java.util.List;
import java.util.Map;

import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final RoleHierarchy roleHierarchy;

    public DemoController(RoleHierarchy roleHierarchy) {
        this.roleHierarchy = roleHierarchy;
    }

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/user")
    public Map<String, String> userPage() {
        return Map.of("status", "user-ok");
    }

    @GetMapping("/manager")
    public Map<String, String> managerPage() {
        return Map.of("status", "manager-ok");
    }

    @GetMapping("/admin")
    public Map<String, String> adminPage() {
        return Map.of("status", "admin-ok");
    }

    public record RolesView(
        String username,
        List<String> direct,
        List<String> reachable
    ) {
    }

    @GetMapping("/roles")
    public RolesView roles(Authentication authentication) {
        List<String> direct = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        List<String> reachable = roleHierarchy
            .getReachableGrantedAuthorities(authentication.getAuthorities())
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new RolesView(authentication.getName(), direct, reachable);
    }
}
~~~

The `GET /roles` endpoint intentionally exposes the authority list **for local demo purposes**. In production, do not arbitrarily return internal privilege lists in responses without appropriate authorization checks.

**Key observation:** user `admin` returns `direct = ["ROLE_ADMIN"]` while `reachable` contains ADMIN, MANAGER, and USER. RoleHierarchy enables effective-privilege checks **without needing to mutate the original Authentication object**.

### 9.4. Testing Authorization and Inheritance with MockMvc

**`src/test/java/com/example/roles/RoleHierarchyTests.java`**

~~~java
package com.example.roles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleHierarchyTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void anonymousRequestNeedsCredentials() throws Exception {
        mvc.perform(get("/user"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userDoesNotInheritHigherRoles() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void managerInheritsUserButNotAdmin() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminInheritsManagerAndUserTransitively() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void unrelatedRoleDoesNotInherit() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("auditor", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reachableRolesAreDifferentFromDirectRoles() throws Exception {
        mvc.perform(get("/roles")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("admin"))
            .andExpect(jsonPath("$.direct[0]").value("ROLE_ADMIN"))
            .andExpect(jsonPath("$.direct.length()").value(1))
            .andExpect(jsonPath("$.reachable",
                hasItems("ROLE_ADMIN", "ROLE_MANAGER", "ROLE_USER")));
    }

    @Test
    void fallbackDeniesEvenAdmin() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

These tests verify **behavior through the real Spring Security filter chain in MockMvc**, not merely calling `getReachableGrantedAuthorities` in isolation. They prove:

- Unauthenticated anonymous requests → **401** with HTTP Basic.
- USER accesses only `/user`, not `/manager` or `/admin`.
- MANAGER inherits USER but not ADMIN.
- ADMIN inherits MANAGER and USER; this demonstrates transitivity.
- AUDITOR does not implicitly get USER.
- Direct roles differ from reachable roles.
- Fallback `denyAll` still blocks even ADMIN if a URL is not permitted.

If a developer later removes `setRoleHierarchy(...)` on the USER manager, the test where ADMIN accesses `/user` catches the regression. This is why you should test **both inherited grants and inherited denials**, not just the admin endpoint.

### 9.5. Running the Project and Observing Output

The machine needs **JDK 17+ and Maven**, and may download dependencies on the first build:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Expected result** is that all tests pass and Maven reports `BUILD SUCCESS` when the files are created properly. These are **run instructions and expected results**; **Maven was not executed in this document**.

Once the server is running:

~~~bash
curl -i http://localhost:8080/public
# Expected HTTP 200, {"status":"public-ok"}

curl -i http://localhost:8080/user
# Expected HTTP 401 with Basic challenge

curl -i -u user:demo-pass http://localhost:8080/user
# Expected HTTP 200

curl -i -u user:demo-pass http://localhost:8080/manager
# Expected HTTP 403

curl -i -u manager:demo-pass http://localhost:8080/user
# Expected HTTP 200 via inherited ROLE_USER

curl -i -u admin:demo-pass http://localhost:8080/manager
# Expected HTTP 200 via inherited ROLE_MANAGER

curl -i -u admin:demo-pass http://localhost:8080/roles
# Expected HTTP 200; direct=[ROLE_ADMIN],
# reachable=[ROLE_ADMIN,ROLE_MANAGER,ROLE_USER] in sorted order

curl -i -u auditor:demo-pass http://localhost:8080/user
# Expected HTTP 403

curl -i -u admin:demo-pass http://localhost:8080/unlisted
# Expected HTTP 403
~~~

Note: HTTP Basic sends credentials in the Authorization header (Base64 **is not encryption**). Use plain HTTP only on localhost for learning; production must use TLS/HTTPS and proper credential storage policies.

## 10. Extended Testing: Modifying the Hierarchy and Regression Checks

### 10.1. Direct Privileges Only

If you **remove both hierarchy edges** while keeping user `admin` with direct `ROLE_ADMIN`, requests to `/manager` and `/user` will **no longer be allowed** by the managers requiring MANAGER/USER. If they still return 200, a broader rule, another RoleHierarchy, or a custom mapping may be present.

### 10.2. Single-Level Inheritance Only

If you declare:

~~~text
ROLE_ADMIN > ROLE_MANAGER
~~~

ADMIN inherits MANAGER, but does **not** automatically inherit USER. Manager likewise does not get USER without the corresponding edge. This verifies whether tests actually check transitivity.

### 10.3. Adding an Unrelated Role

~~~text
ROLE_AUDITOR > ROLE_AUDIT_READER
~~~

If AUDITOR has no path to USER, it cannot access endpoints requiring USER. This negative test helps prevent a bug where "every role is treated as a common role" due to a faulty custom manager.

### 10.4. Tenant-Dependent Hierarchies

Suppose tenant A wants MANAGER > USER while tenant B forbids it. A single global `RoleHierarchyImpl` bean **cannot adequately represent dynamic per-tenant conditions**. Attempting to mutate a global hierarchy per request for each tenant creates **race conditions and cross-tenant privilege leaks**. Use a policy/`AuthorizationManager` with trusted tenant context, or a tenant-scoped role model, instead of mutating a singleton bean per request.

### 10.5. Conditional Permissions

For high-value refunds, the rule "ADMIN has ROLE_USER" does not prove the caller completed MFA or received approval. Use an authorization policy that checks dynamic conditions:

~~~text
Authenticated user
    |
    +-- Has refund:create permission?
    +-- Correct tenant?
    +-- Valid MFA/step-up?
    +-- Not approving a request they created?
    |
    +--> all satisfied: allow
~~~

A hierarchy can be **one** signal in the decision, never the entire decision.

## 11. Common Mistakes When Applying RoleHierarchy

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reversing `ROLE_USER > ROLE_ADMIN` | USER inherits ADMIN, risking privilege escalation | Sketch the graph before declaring, add negative tests |
| Assuming hierarchy means "every role includes lower roles" without config | Privileges inferred incorrectly | Infer only via explicit edges and transitivity |
| Declaring a RoleHierarchy bean without wiring it to active managers | `hasRole` may miss inherited roles | Use `setRoleHierarchy`/integrated handler, test HTTP & method |
| Inspecting `Authentication.getAuthorities()` directly and expecting `ROLE_USER` for admin | Confuses direct vs. reachable | Separate assigned vs. effective; use hierarchy where needed |
| Using `hasRole("ROLE_ADMIN")` with the default prefix | Risk of misconfiguration/exception | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Assuming ADMIN has `report:read` without declaring it | Access fails or leaks via bypass | Design explicit permission mappings |
| Creating cycles between roles | Unintended privilege equivalence | Avoid cycles, test the graph |
| Mutating a singleton hierarchy per request/tenant | Race conditions, cross-tenant leaks | Policy scoped by trusted context |
| Letting payment approver inherit payment creator | Breaks separation of duties | Keep roles independent with controlled policies |
| Treating role hierarchy as an ownership check | User A can read user B's data | Check owner/tenant in service/method |
| Changing policy without revoking old sessions/tokens | Stale privileges in sessions/claims | Implement versioning/revocation/re-authentication |
| Adding `anyRequest().permitAll()` to "fix" 403 | Unintentionally exposes endpoints | Inspect managers, authorities, and fallbacks |
| Testing only whether admin can access `/admin` | Misses inheritance and privilege leaks | Test USER, MANAGER, AUDITOR, anonymous, and fallback |
| Forgetting differences between HTTP and method security | Inconsistent policy between endpoint and service | Test both layers, configure handlers properly |
| Calling a new bean/API name absent in the pinned dependency version | Build fails when upgrading/downgrading | Pin versions, verify actual API and migration notes |

## 12. Process for Introducing RoleHierarchy in a Real Project

### Step 1: Analyze Business Privileges

List direct roles and the actions each role is allowed to perform. For every edge `A > B`, ask:

> “Should every member of A, in every applicable context, always be permitted to do everything B can do?”

If the answer is "no" or "only within one tenant/order", do not create a global edge. Design a permission/ownership policy instead.

### Step 2: Sketch and Review the Graph

Draw the DAG, ensure no reversed edges, no cycles, and no over-grants, and review it with security/business owners. A new role edge can expand reachable authorities for thousands of accounts; treat this change as a **security policy change**.

### Step 3: Create the RoleHierarchy Bean According to Your Version

Use the API available in your current Spring Security version; if using `RoleHierarchyImpl.setHierarchy(...)`, note its deprecation in newer versions. Do not share a string built dynamically from user input. Role hierarchies are controlled configuration, not request data.

### Step 4: Integrate All Required Checkpoints

Check:

- Are `authorizeHttpRequests` + `AuthorityAuthorizationManager` actually wired with the hierarchy?
- Does the method-security expression handler use the hierarchy?
- Does custom policy code compare direct authorities instead of reachable ones?
- Do gateways/resource servers share the same role mapping and trust boundaries?
- Do sensitive endpoints enforce additional permission, owner/tenant, and MFA checks?

### Step 5: Test the Authorization Matrix

| User/role | /public | /user | /manager | /admin |
| --- | --- | --- | --- | --- |
| Anonymous | 200 | 401 (Basic) | 401 | 401 |
| USER | 200 | 200 | 403 | 403 |
| MANAGER | 200 | 200 | 200 | 403 |
| ADMIN | 200 | 200 | 200 | 200 |
| AUDITOR | 200 | 403 | 403 | 403 |

HTTP codes in this table assume the **HTTP Basic** configuration in the example; with form login, anonymous requests can receive a 302 redirect. Test negative cases too, not just the happy path.

### Step 6: Controlled Rollout and Observability

Monitor 403/401 rates, policy paths, and unusual changes, without logging raw passwords, session cookies, Bearer tokens, or unnecessary personal data. When changing the hierarchy, account for stale sessions/JWTs, multi-version deployments, and backward compatibility.

### Step 7: Document the Inheritance

Each relationship should have an owner, a business rationale, and tests demonstrating expectations. Do not allow each module to invent a different hierarchy without a shared design; that makes the same role enforce different access across endpoints.

## 13. Self-Check Questions

**1. What does `ROLE_ADMIN > ROLE_MANAGER` mean?**

ADMIN is treated as including the privileges of MANAGER in authorization components configured with that RoleHierarchy. It does not mean MANAGER gets ADMIN.

**2. If ADMIN > MANAGER and MANAGER > USER, does ADMIN have USER?**

Yes, by transitivity. This is a key case to test.

**3. Does a user with only ROLE_USER have ROLE_MANAGER?**

No. The relationship is directed; lower roles do not imply higher ones.

**4. Once a RoleHierarchy bean exists, does every `hasRole` automatically inherit?**

Do not assume so. Verify that the manager/expression handler uses RoleHierarchy per version and config; for instance, HTTP wired via `AuthorityAuthorizationManager#setRoleHierarchy`.

**5. Why might `Authentication.getAuthorities()` for ADMIN contain only ROLE_ADMIN?**

Because that is the list of **directly assigned** authorities. Reachable roles are computed by the hierarchy when needed, without necessarily mutating `Authentication`.

**6. What does `hasRole("ADMIN")` check by default?**

It typically checks `ROLE_ADMIN`. With the default prefix, do not pass `ROLE_ADMIN` directly into `hasRole`.

**7. Does ADMIN automatically get every `hasAuthority("...")`?**

No. A separate permission such as `refund:approve` only applies if granted/mapped by the corresponding policy. The ADMIN role does not automatically include every permission string.

**8. Does RoleHierarchy solve an admin of tenant A viewing data of tenant B?**

No. You need an owner/tenant policy backed by trusted data. A global role does not encode tenant scope.

**9. Should payment approver inherit payment creator?**

Only if the business truly allows it and it does not violate separation of duties; many systems require those two roles to stay separate.

**10. After changing RoleHierarchy, are old JWTs/sessions automatically revoked?**

No. You need appropriate expiration, revocation, policy versioning, or re-authentication mechanisms.

**11. Why does the fallback `anyRequest().denyAll()` still block ADMIN?**

Because hierarchy does not override deny rules; unlisted requests are still denied per policy.

**12. Why test method security separately if HTTP already uses RoleHierarchy?**

Because they can use different expression handlers/authorization managers; method-level policies also protect business logic invoked from multiple entry points.

**13. When should you avoid a linear hierarchy ADMIN > MANAGER > USER?**

When roles do not genuinely subsume one another, when separation of duties applies, when permissions are object-scoped, or when dynamic/tenant constraints exist; use a branched graph or independent policies instead.

**Key takeaway:** **RoleHierarchy describes directed inheritance relationships between roles/authorities. Reachable results can be larger than direct authorities, but only take effect when properly integrated into authorization managers/expressions. Inheritance must be business-driven, avoid over-granting, and never replace ownership, tenancy, MFA, or session/token revocation.**