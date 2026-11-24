# RBAC: Organizing Permissions by User Role in Spring Security

> **Topic:** Access control models. This lesson covers **Role-Based Access Control — RBAC**: designing roles, assigning permissions to roles, assigning roles to users, and enforcing policies in a Java/Spring Security application.

## 1. What Problem Does RBAC Solve?

Suppose a report management system has 1,000 users and three main operations: **view reports**, **edit reports**, and **manage accounts**. If the application stores a separate permission list for each person, the development team has to update those lists whenever staff are hired, transferred, or change responsibilities. As the number of users and action types grows, permissions easily become misassigned or omitted.

**RBAC** solves this by placing **roles** between users and permissions:

- **User (user/subject):** an account or identity that needs access to resources; one person can have multiple roles.
- **Role:** a set of responsibilities defined in the system, such as `REPORT_VIEWER`, `REPORT_EDITOR`, `ADMIN`.
- **Permission:** a specific capability such as `report:read`, `report:write`, `users:manage`. Each permission typically represents an **action on a resource type**.
- **Role assignment:** the relationship assigning users to roles. **Permission assignment:** the relationship assigning permissions to roles.
- **Policy/enforcement:** server-side code determines the caller's roles/authorities and blocks the operation when required permissions are missing.

~~~text
                      ROLE ASSIGNMENT          PERMISSION ASSIGNMENT
User ────────────────────► Role ──────────────────► Permission
alice ───────────────────► VIEWER ─────────────────► report:read
bob   ───────────────────► EDITOR ─────────────────► report:read
                           EDITOR ─────────────────► report:write
carol ───────────────────► ADMIN ──────────────────► report:read
                           ADMIN ──────────────────► report:write
                           ADMIN ──────────────────► users:manage

Request: (principal, action, resource)
        └─► verify identity
             └─► fetch assigned roles and effective permissions
                  └─► check permission / additional conditions
                       ├─► ALLOW: process request
                       └─► DENY: block on server
~~~

**Key idea:** administrators do not have to assign `report:read` individually to every employee. They assign `VIEWER`; the system maps that role to its defined permissions. When a policy change is needed for the whole group, adjust the **role → permission** mapping through a controlled process.

RBAC is **authorization** (deciding whether to grant access), not the process of verifying passwords/tokens. Spring Security typically authenticates the identity first, then retrieves trusted `GrantedAuthority` instances to evaluate policies.

## 2. Designing the Role–Permission Matrix

For the example reporting system, we can agree on three roles:

| Permission | `VIEWER` | `EDITOR` | `ADMIN` |
| --- | :---: | :---: | :---: |
| `report:read` — view reports | Yes | Yes | Yes |
| `report:write` — edit report content | No | Yes | Yes |
| `users:manage` — manage accounts | No | No | Yes |

Users are assigned roles; **effective permissions** are the union of the permissions granted by those roles (unless the system defines additional deny rules).

Examples:
- Alice has `VIEWER` → can read reports, cannot edit.
- Bob has `EDITOR` → can read and edit reports, cannot manage accounts.
- Carol has `ADMIN` → gets all three listed permissions.
- If a person has both `VIEWER` and `EDITOR`, the permissions combine; do not assume the system automatically understands which role is "higher" than another.

**Do not infer inheritance from role names alone:** `ADMIN` does not implicitly include `EDITOR` in Spring Security. In the matrix above, `ADMIN` has `report:read` and `report:write` because **we explicitly assigned them**. If you want a higher role to inherit a lower role, you need to configure a *role hierarchy* or proactively expand permissions when building the identity.

### Role Design Principles

1. **Start from actions and resources:** identify `report:read`, `report:write`, `users:manage` before creating roles; avoid vague role descriptions like "high privilege".
2. **Tie roles to business responsibilities:** `EDITOR` clearly expresses a duty, whereas arbitrary per-person roles defeat the purpose of RBAC.
3. **Least privilege:** by default, grant only the necessary permissions. Someone who only views reports does not need edit permissions.
4. **Deny by default:** endpoints or operations not explicitly granted access must be denied.
5. **Separation of Duties:** some business domains require that two roles never belong to the same person (for example, payment requester and payment approver). This is an **additional constraint** on the RBAC policy, not something that arises automatically just by having roles.
6. **Stable, UI-independent permission names:** a permission like `report:write` is better than a name like `clickSaveButton` because a business permission may be invoked via web, API, or batch job.
7. **Role lifecycle governance:** each role should have a description, an owner, a permission list, an approval workflow, periodic reviews, and a revocation mechanism.

## 3. Roles, Authorities, and Permissions in Spring Security

Spring Security checks permissions through the set of `GrantedAuthority` instances in the `Authentication` object. The framework does not enforce a single SQL "role–permission" table; applications can provide authorities from `UserDetailsService`, SSO/OIDC, verified tokens, a database, or other trusted sources.

**How Spring Security interprets strings:**

| Expression | What is checked in `Authentication#getAuthorities()` |
| --- | --- |
| `hasRole("ADMIN")` | Authority `ROLE_ADMIN` using the default role prefix |
| `hasAuthority("ROLE_ADMIN")` | Exact match `ROLE_ADMIN` |
| `hasAuthority("report:read")` | Exact match `report:read` |
| `hasAnyRole("EDITOR", "ADMIN")` | Has at least one corresponding role |
| `authenticated()` | Authenticated according to framework rules; does not require a specific permission |
| `permitAll()` / `denyAll()` | Always allow / always deny according to that rule |

A **role** is also represented as an authority, usually with the `ROLE_` prefix. A **permission** such as `report:write` can be stored as a plain authority without a prefix. Therefore:

- `User.withUsername("bob").roles("EDITOR")` creates `ROLE_EDITOR`, and **does not automatically create** `report:read` or `report:write`.
- `User.withUsername("bob").authorities("ROLE_EDITOR", "report:read", "report:write")` provides both the role label and the specific permissions.
- Both `roles(...)` and `authorities(...)` builders set the authority list; do not chain both methods assuming they accumulate. Build **one complete authority list** yourself if you need both.

In application RBAC architectures, a common approach is to load the user's roles and **expand** them into permission authorities; controllers/services can then require `hasAuthority("report:write")` without needing to remember which role owns that permission. Another approach is to check `hasRole(...)` directly on endpoints genuinely meant for a single role. Both approaches are valid when the policy is consistent.

## 4. Java 17+ Spring Boot Example: Mapping Role → Permission in One Place

This example has three accounts and three roles following the matrix in section 2. It shows how to build a **central mapping table** `ROLE_PERMISSIONS`, grant authorities from roles, protect requests, and re-verify at the service layer.

**Setup:** create a Maven project via Spring Initializr with **Java 17+**, **Spring Web**, and **Spring Security** dependencies. The classes below belong to Spring Boot + Spring Security; the example is run using the project's Maven Wrapper, not plain JDK `javac` alone. Create the file:

`src/main/java/com/example/rbac/RbacApplication.java`

~~~java
package com.example.rbac;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class RbacApplication {

    private static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
        "VIEWER", Set.of("report:read"),
        "EDITOR", Set.of("report:read", "report:write"),
        "ADMIN", Set.of("report:read", "report:write", "users:manage")
    );

    public static void main(String[] args) {
        SpringApplication.run(RbacApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/reports/view").hasAuthority("report:read")
                .requestMatchers("/reports/editor").hasAuthority("report:write")
                .requestMatchers("/admin/users").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = account("alice", "demo123", encoder, "VIEWER");
        UserDetails bob = account("bob", "demo456", encoder, "EDITOR");
        UserDetails carol = account("carol", "demo789", encoder, "ADMIN");
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    private static UserDetails account(
            String name, String password, PasswordEncoder encoder, String... roles) {

        Set<String> authorities = new LinkedHashSet<>();

        for (String role : roles) {
            Set<String> permissions = ROLE_PERMISSIONS.get(role);
            if (permissions == null) {
                throw new IllegalArgumentException("Unknown role: " + role);
            }

            authorities.add("ROLE_" + role);
            authorities.addAll(permissions);
        }

        return User.withUsername(name)
            .password(encoder.encode(password))
            .authorities(authorities.toArray(String[]::new))
            .build();
    }

    @RestController
    static class RbacController {
        private final ReportService reports;

        RbacController(ReportService reports) {
            this.reports = reports;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/reports/view")
        String view() {
            return reports.readReport();
        }

        @GetMapping("/reports/editor")
        String editor() {
            return reports.openEditor();
        }

        @GetMapping("/admin/users")
        String users() {
            return "user administration";
        }
    }

    @Service
    static class ReportService {

        @PreAuthorize("hasAuthority('report:read')")
        public String readReport() {
            return "report data";
        }

        @PreAuthorize("hasAuthority('report:write')")
        public String openEditor() {
            return "report editor";
        }
    }
}
~~~

**Notable details in the example:**

1. `ROLE_PERMISSIONS` is the example's **role → permission configuration source**, avoiding repeating the permission table for each account. In production, this source can come from controlled configuration or role/permission tables in a database.
2. `account(...)` adds both the `ROLE_...` authority and the permission authorities. For Bob, the result includes `ROLE_EDITOR`, `report:read`, and `report:write`.
3. `/reports/view` checks `report:read` at HTTP; `/reports/editor` checks `report:write`. `/admin/users` illustrates checking `hasRole("ADMIN")` directly.
4. `@EnableMethodSecurity` enables `@PreAuthorize` on the service. Because the controller calls **another bean `ReportService`** through a Spring proxy, the method-level check runs on invocation. Do not rely on `@PreAuthorize` when one method in the same bean calls another method via `this` under standard proxy mechanics.
5. `GET /reports/editor` only returns the message "report editor" and **does not mutate data**; it is an example of accessing an editor page. For real write operations, protect `POST`/`PUT`/`PATCH` and handle CSRF appropriately for your application's authentication mechanism.
6. `anyRequest().denyAll()` closes undeclared routes. `requestMatchers` are evaluated in order; place specific rules before broad rules.
7. Demo passwords are encoded with BCrypt for Spring Security verification; **do not hardcode sample accounts/passwords in real production systems**. HTTP Basic is only safe over HTTPS in real environments.

### Running and Testing the Output

In the project directory, run:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/reports/view
curl -i -u alice:demo123 http://localhost:8080/reports/view
curl -i -u alice:demo123 http://localhost:8080/reports/editor
curl -i -u bob:demo456 http://localhost:8080/reports/editor
curl -i -u bob:demo456 http://localhost:8080/admin/users
curl -i -u carol:demo789 http://localhost:8080/admin/users
~~~

| Request | Expected HTTP Result | Why |
| --- | --- | --- |
| `GET /public/ping` without credentials | `200`, `pong` | `permitAll()` |
| `GET /reports/view` without credentials | `401` | Unauthenticated for a resource requiring an authority |
| `GET /reports/view` as Alice | `200`, `report data` | `VIEWER` has `report:read` |
| `GET /reports/editor` as Alice | `403` | Missing `report:write` |
| `GET /reports/editor` as Bob | `200`, `report editor` | `EDITOR` has `report:write` |
| `GET /admin/users` as Bob | `403` | Missing `ROLE_ADMIN` |
| `GET /admin/users` as Carol | `200`, `user administration` | Has `ROLE_ADMIN` |

The 401/403 statuses in the table assume **the example's HTTP Basic configuration**: omitting credentials on a protected endpoint usually yields 401; a valid identity lacking the required authority yields 403. With form login, an unauthenticated request may receive a redirect to the login page instead of 401.

**Key takeaway:** any route can receive requests from a client, but **the server** enforces the policy. Hiding an "Edit" button on the frontend only improves UX; users can still call the API directly, so RBAC rules must live in the backend.

## 5. Storing Roles and Permissions in a Database

For organizations with many accounts, the in-memory mapping in section 4 can be replaced by a relational data model. A minimal structure typically includes:

| Table | Role |
| --- | --- |
| `app_users` | List of internal accounts/identities |
| `roles` | Role catalog, unique key by role code |
| `permissions` | Permission catalog, unique key by permission code |
| `user_roles` | Many-to-many join table between user and role |
| `role_permissions` | Many-to-many join table between role and permission |

Example DDL in **PostgreSQL** (illustrating the authorization structure; not yet a complete schema for every business case):

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE roles (
    id BIGINT PRIMARY KEY,
    role_code VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE permissions (
    id BIGINT PRIMARY KEY,
    permission_code VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES app_users(id),
    role_id BIGINT NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id),
    permission_id BIGINT NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);
~~~

To retrieve the permissions **granted via roles** for a user:

~~~sql
SELECT DISTINCT p.permission_code
FROM user_roles ur
JOIN role_permissions rp ON rp.role_id = ur.role_id
JOIN permissions p ON p.id = rp.permission_id
WHERE ur.user_id = :user_id;
~~~

`:user_id` is a query bind parameter passed by the data access layer, not standalone PostgreSQL SQL syntax to run directly in a console. In real applications, use prepared statements/parameter binding.

**When integrating with Spring Security:** the authentication process can read the user's roles, load the corresponding permissions, and build an `Authentication`/`UserDetails` with the appropriate authorities. Spring Security **does not automatically create an RBAC database or sync a `role_permissions` table** just because the application calls `hasRole`.

In multi-tenant systems, role assignments are often also tied to a **tenant** or organizational scope. Never take an `ADMIN` role from tenant A and apply it to tenant B's data if administrative privileges only apply within tenant A. Scopes/keys such as `tenant_id` may be needed in both the relational model and authorization checks.

## 6. Role Hierarchy and How to Avoid Misconceptions

RBAC can span multiple levels:

- **Basic RBAC:** users are assigned roles, roles are assigned permissions, and the system evaluates effective permissions.
- **Hierarchical RBAC:** roles have explicit inheritance relationships, such as `ADMIN > EDITOR > VIEWER`.
- **Constrained RBAC:** restricts role assignment/activation, for example two roles "Create payment order" and "Approve payment order" cannot be assigned to the same user.

In Spring Security, a role hierarchy can be declared like the following snippet (this is a **configuration fragment** that must be placed inside a `@Configuration` class with the appropriate imports, not a standalone Java program):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Bean
static RoleHierarchy roleHierarchy() {
    return RoleHierarchyImpl.fromHierarchy(
        "ROLE_ADMIN > ROLE_EDITOR\nROLE_EDITOR > ROLE_VIEWER");
}
~~~

With this configuration, a higher role can be treated as carrying the authorities of lower roles **in authorization mechanisms configured to use the hierarchy**. Do not confuse this with the raw data in `Authentication#getAuthorities()`: the hierarchy computes reachable authorities at evaluation time and does not necessarily rewrite new authorities onto the user.

When using `@PreAuthorize`/`@PostAuthorize` expressions, configure `MethodSecurityExpressionHandler` to apply the hierarchy, for example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

This snippet is also a **fragment**; official documentation recommends registering the handler so Spring processes it in time for method security initialization (commonly using `static @Bean`). In systems using a hierarchy, you must configure and test consistency between HTTP and method checks. Do not arbitrarily combine a role hierarchy with an explicitly expanded permission list into two conflicting policy sources.

**Practical choice:** the matrix in section 2 works well even without a hierarchy. If `ADMIN` is already assigned the required permissions, there is no need to add a hierarchy just so "ADMIN automatically has all permissions". Conversely, when many senior roles stably inherit junior roles, a hierarchy can reduce duplication.

## 7. Limitations of RBAC and When Other Conditions Are Needed

RBAC answers **"what kinds of actions can this role perform?"** very well. However, many applications need decisions based on a **specific object** or context:

- Bob has `report:read` but may only view reports belonging to Bob's department.
- Alice has `invoice:approve` but cannot approve invoices created by Alice herself.
- A user is `ADMIN` in one tenant, with no administrative rights in another tenant.
- An operation is only allowed in the `DRAFT` state or when the transaction amount is below the approval limit.

This is where RBAC is commonly combined with **ownership** checks, scope/tenant checks, object state, and business attribute conditions (ABAC or dedicated policies).

Illustrative example of a service-layer check:

~~~java
// Illustrative fragment, not a standalone runnable class:
@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long reportId, Authentication auth) {
    Report report = repository.findById(reportId).orElseThrow();
    if (!report.getTenantId().equals(currentTenantId(auth))) {
        throw new AccessDeniedException("No access to this tenant");
    }
    return mapper.toDto(report);
}
~~~

The `report:read` permission is a **necessary condition**; access to the report itself must also be evaluated before returning data. The names `ReportDto`, `repository`, `mapper`, and `currentTenantId` in the fragment are business components needed in a real project. This example cannot compile standalone; its purpose is to show **where object-level conditions are applied**.

For complex systems, place policies in a shared service/policy component or a custom `AuthorizationManager` so you do not duplicate slightly different conditional checks across many controllers.

## 8. Implementation Risks to Control

### Permissions Changing While a Session/Token Is Still Valid

If Bob's role changes from `EDITOR` to `VIEWER`, updating the `user_roles` table **does not guarantee** that every existing session/JWT loses the permission immediately. Depending on the authentication mechanism, the authority list may be cached in a session, token, or cache. Choose an appropriate strategy: session revocation, token refresh, short-lived tokens, server-side permission lookup, or versioning/invalidation mechanisms. For sensitive permissions, define the maximum acceptable revocation delay.

### Never Grant Authorities from Untrusted Input

Roles sent by the frontend, query parameters, or unverified token claims **must never be trusted automatically**. Only convert them into `GrantedAuthority` after the identity source and mapping policy have been verified. With OAuth2/OIDC, distinguish client/realm/resource-server roles from the effective permissions in this application.

### Logging and Testing

- Record changes: **who granted/revoked which role, to whom, when, and why**.
- Write a test matrix covering **role × endpoint × action × tenant/ownership**.
- Include negative tests: a valid account lacking permission must be blocked; a new route without a rule must be blocked; a user from another tenant must not cross boundaries.
- For POST/PUT/DELETE operations, test both authorization and proper CSRF protection. A CSRF 403 must not be confused with a 403 due to a missing role.
- Never log passwords, access tokens, or sensitive credential details.

### Common Pitfalls

1. **Role explosion:** creating a role for every user/resource variant; separate baseline permissions from object conditions instead.
2. **Assuming automatic role inheritance:** assigning `ROLE_ADMIN` does not make Spring imply `ROLE_EDITOR`; an explicit mapping or configured hierarchy is required.
3. **Confusing `hasRole` and `hasAuthority`:** `hasRole("ADMIN")` typically checks `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` requires the exact authority string `ADMIN`.
4. **Blocking only on the frontend:** the UI is not a security enforcement boundary; the backend must verify permissions.
5. **Checking "logged in" instead of a permission:** `authenticated()` is not equivalent to `hasAuthority("report:write")`.
6. **Hardcoding username checks:** `if (name.equals("alice"))` is hard to govern and creates hidden privileges; roles/permissions should be structured.
7. **Granting system-wide `ROLE_ADMIN` to every department admin:** lacks tenant context, organizational scope, and least privilege.
8. **Forgetting method/service checks:** flows calling a service from other endpoints/jobs still need proper enforcement.
9. **Assuming tokens/sessions auto-update:** you must manage permission revocation and the authority source lifecycle.
10. **Adding `anyRequest().permitAll()` as a quick fix for a 403 error:** this can unintentionally expose new endpoints; define the required rules instead of opening by default.

## 9. Design and Self-Check Checklist

Before introducing RBAC into a project, be able to answer these questions:

- What list of **actions/resources** needs protection? Are permission codes clear and consistent?
- What responsibility does each role serve? Which role has which permissions, and who approves changes?
- Can a user hold multiple roles? If so, what is the permission combination rule? Are there conflicting roles that must be blocked?
- How are policies enforced at HTTP, method/service, and record/tenant levels?
- Where are authorities loaded from? When a role is revoked, when do sessions/tokens/caches expire?
- Are new endpoints denied by default? Are there tests for unprivileged users and cross-tenant users?
- Are role management logs sufficient for traceability and auditing?

**Quick questions:**

1. Alice has `VIEWER`, and an API requires `report:write`. **Result:** denied; being authenticated does not substitute for the permission.
2. Bob has `EDITOR`. Can he call an endpoint requiring `hasAuthority("report:read")`? **Yes**, if the role mapping actually grants that permission as in the section 2 matrix.
3. Carol has `ROLE_ADMIN` but **does not** have `report:read`, and the system **has not** enabled a hierarchy or permission expansion. Does `hasAuthority("report:read")` allow it? **No**; a role name does not automatically generate child permissions.
4. Two employees have the same `VIEWER` role; one wants to view the other's private document. Is checking `report:read` alone enough? **No**; object-level/scope permissions must also be checked.
5. A role is revoked in the database while an old access token is still valid. Does the permission disappear immediately? **It depends on the permission loading/refresh mechanism**; you cannot assume yes by default.

**Remember:** **User → Role → Permission** keeps permission management consistent and controllable. Spring Security evaluates `GrantedAuthority`/roles according to declared policies; actual access also depends on the resource and context. Good design means clear role responsibilities, clear action permissions, least privilege, deny by default, and a revocation mechanism.

## Official Documentation for Further Reading

- Spring Security — Authorization Architecture (role hierarchy): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — RoleHierarchyImpl API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
