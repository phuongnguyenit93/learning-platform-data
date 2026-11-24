# Applying hasRole and hasAuthority to Endpoint Groups in Spring Security

## 1. Objective and scenario

A Java/Spring Boot document management application has several groups of HTTP endpoints:

- `/api/health` is public for application health checks.
- `/api/admin/**` is restricted to administrators.
- `/api/audit/**` is restricted to auditors or administrators.
- `GET /api/documents` and `GET /api/documents/{id}` share the same read permission.
- `POST /api/documents` uses the create permission.
- `PATCH /api/documents/{id}` uses the edit permission.
- `POST /api/documents/{id}/approve` uses the approve permission.
- Other URLs not in the declared catalog must be denied.

If we write a separate condition for each URL without grouping rules, it is easy to leave gaps in protection, create inconsistencies across endpoints, and make testing harder. Spring Security supports **pairing one or more request matchers** with **an authorization rule**. Two commonly used rules are `hasRole` and `hasAuthority`.

After this article, you will be able to:

1. Distinguish role authorities from action/permission authorities in `Authentication.getAuthorities()`.
2. Bind `hasRole`, `hasAnyRole`, `hasAuthority`, and `hasAnyAuthority` to **an endpoint group** in `authorizeHttpRequests`.
3. Order matchers properly, especially when specific and general URLs can both match.
4. Authorize by HTTP method, not just by path.
5. Build a deny-by-default configuration, add object-level checks in services, and write integration tests.
6. Recognize common pitfalls involving the `ROLE_` prefix, claims/scopes, URL wildcards, `securityMatcher`, and CSRF.

**Scope:** the main part of this article uses **Spring Security Servlet/MVC with `SecurityFilterChain` and `authorizeHttpRequests`**. This is not WebFlux syntax (`SecurityWebFilterChain`). Specific configurations and matchers may differ across Spring Security lines, so check against the exact dependency version your project uses.

## 2. Exact meaning of hasRole and hasAuthority

### 2.1. Both rely on GrantedAuthority

After authentication, the `Authentication` object typically holds a list of `GrantedAuthority` instances — the authority names granted to the principal by the application. For example:

```text
ROLE_EDITOR
document:read
document:edit
SCOPE_profile
```

These names are **actual strings to be matched**, and are not automatically synonymous.

| Configuration | Which authority is required by default? | Meaning |
| --- | --- | --- |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | User belongs to the EDITOR role |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` | Exact match of the prefixed authority name |
| `hasAuthority("EDITOR")` | `EDITOR` | **Not equivalent** to `hasRole("EDITOR")` |
| `hasAuthority("document:read")` | `document:read` | Permission to perform document read |
| `hasAnyRole("AUDITOR", "ADMIN")` | `ROLE_AUDITOR` **or** `ROLE_ADMIN` | Has at least one role |
| `hasAnyAuthority("document:edit", "document:approve")` | Either permission | Has at least one action permission |

By **default** convention, `hasRole("EDITOR")` is a shortcut that checks for the `ROLE_EDITOR` authority. When using `hasRole`, pass the name **without** the `ROLE_` prefix. If a project customizes the role prefix, you must verify the actual behavior of HTTP matchers, method security, role hierarchy, and the authority issuer; do not assume one configuration change automatically synchronizes everywhere.

**`hasAuthority` performs an exact check:** `document:read` differs from `DOCUMENT:READ` and differs from `SCOPE_document:read`. Case sensitivity, `:`/`_` characters, and prefixes all matter.

### 2.2. Roles are responsibility groups; permissions are actions

A maintainable convention:

```text
Roles:
  ROLE_ADMIN
  ROLE_AUDITOR
  ROLE_DOCUMENT_EDITOR

Permissions:
  document:read
  document:create
  document:edit
  document:approve
  document:delete
```

A role usually describes a relatively stable group of responsibilities, while a permission describes **a business capability**. For instance, `ROLE_DOCUMENT_EDITOR` may be mapped to `document:read` and `document:edit` where authorities are issued, but **Spring Security does not automatically generate those permissions just because a user has this role**.

Both choices are valid when intentional:

- Small, stable administrative feature set: `/api/admin/**` requires `hasRole("ADMIN")`.
- Distinct read/edit/approve action groups: use `hasAuthority("document:read")`, `hasAuthority("document:edit")`, etc.

Using roles does not replace object-level access control. `document:read` allows **attempting the read action**; it does not yet prove Alice is allowed to read Bob's specific document.

### 2.3. `hasAny...` is OR, not AND

`hasAnyRole("ADMIN", "AUDITOR")` means having **at least one** matching authority. It does not require both. Similarly, `hasAnyAuthority("report:read", "report:export")` only requires one of the two permissions.

If the business logic requires **both** the ADMIN role **and** the export permission simultaneously, express the AND with a custom `AuthorizationManager`/`AuthorizationManagers.allOf(...)` appropriate for your version and enforcement point. Do not use `hasAny...` and think you checked both conditions.

Example Servlet configuration fragment, when the API/version supports the corresponding factories:

```java
import static org.springframework.security.authorization.AuthorizationManagers.allOf;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasAuthority;
import static org.springframework.security.authorization.AuthorityAuthorizationManager.hasRole;

// Inside authorizeHttpRequests:
.requestMatchers(HttpMethod.POST, "/api/admin/reports/export")
    .access(allOf(hasRole("ADMIN"), hasAuthority("report:export")))
```

The snippet above is a **fragment**, not a standalone program; it requires `HttpMethod`, `HttpSecurity`, `SecurityFilterChain`, and appropriate bean configuration. A request passing this branch must satisfy both conditions. Projects on other versions must check the API signatures instead of copying blindly.

## 3. Grouping endpoints with requestMatchers

### 3.1. A group of paths, one condition

If multiple endpoints share the `document:read` permission requirement, combine the paths in one `requestMatchers`:

```java
.requestMatchers(
        HttpMethod.GET,
        "/api/documents",
        "/api/documents/*"
).hasAuthority("document:read")
```

This requires the same permission for:

```http
GET /api/documents
GET /api/documents/d42
GET /api/documents/d99
```

`/api/documents/*` is shown for **a single path segment** directly under `/api/documents`. Do not assume it covers deeply nested endpoints like `/api/documents/d42/versions/3`. Pattern handling depends on the `RequestMatcher` type used — such as `PathPattern`-based matchers in newer configurations — so test actual URLs against the exact Spring Security/Servlet version you run.

### 3.2. A functional group by path prefix

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/audit/**").hasAnyRole("AUDITOR", "ADMIN")
```

- Every request **matching the matcher** `/api/admin/**` requires the ADMIN role.
- Every request **matching the matcher** `/api/audit/**` requires the AUDITOR **or** ADMIN role.

Prefix-based configuration is convenient when a group of routes shares the same sensitivity level. However, `/api/admin/**` may include GET/POST/DELETE, and `hasRole("ADMIN")` alone does not distinguish actions. For sensitive operations like deleting data or exporting secrets, you can add dedicated permissions or stronger policies.

### 3.3. Distinguishing groups with the same path but different HTTP methods

In REST, one path can serve multiple actions:

| HTTP method + path | Action | Appropriate rule |
| --- | --- | --- |
| `GET /api/documents` | List readable documents | `hasAuthority("document:read")` |
| `GET /api/documents/d42` | Read details of one document | `hasAuthority("document:read")` |
| `POST /api/documents` | Create a document | `hasAuthority("document:create")` |
| `PATCH /api/documents/d42` | Edit a document | `hasAuthority("document:edit")` |
| `POST /api/documents/d42/approve` | Approve a document | `hasAuthority("document:approve")` |
| `DELETE /api/documents/d42` | Delete a document | `hasRole("DOCUMENT_ADMIN")` or a dedicated delete permission |
| `GET /api/audit/events` | Read audit logs | `hasAnyRole("AUDITOR", "ADMIN")` |
| `GET /api/admin/users` | Administrative features | `hasRole("ADMIN")` |

Using `requestMatchers(HttpMethod.GET, "...")` ensures a rule protects only a **specific method** instead of unintentionally applying to every operation on the same path. If you need to support `PUT`, `HEAD`, or a new endpoint version, add an intentional rule rather than assuming the framework infers the corresponding permission.

### 3.4. One rule for multiple methods?

If two methods share the exact same **business policy**, you can create multiple `requestMatchers(...)` with the same requirement or a custom matcher grouping methods. However, do not assume `GET`, `POST`, and `DELETE` are equivalent just because they share a path. An auditable approach is usually grouping by action/permission, **not grouping every request just because the URL matches**.

## 4. Matcher ordering: the first matching rule applies

In `authorizeHttpRequests`, matcher/rule pairs are evaluated **in declaration order**. For a given request, the **first matching rule** is used; subsequent rules are not combined automatically.

### 4.1. Wrong example: general matcher shadows specific matcher

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
)
```

Request `GET /api/admin/users` matches `/api/**` first, so it only requires authentication. The ADMIN rule below is **never applied** to that request. This is a vulnerability caused by **ordering**, not by `hasRole` being broken.

### 4.2. Correct example: specific first, general last

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
)
```

In this version, the admin group is guarded first. Still, `/api/**` only requires login for other routes; if the application has sensitive features outside admin, more granular rules are needed. In strict applications, **deny by default** may be preferable to a catch-all `authenticated()`.

### 4.3. Method-based authorization is also affected by ordering

Wrong:

```java
.requestMatchers("/api/documents/**").hasAuthority("document:read")
.requestMatchers(HttpMethod.DELETE, "/api/documents/*")
    .hasAuthority("document:delete")
```

DELETE can be caught by the general matcher first and **require only read permission**. Better:

```java
.requestMatchers(HttpMethod.DELETE, "/api/documents/*")
    .hasAuthority("document:delete")
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")
.requestMatchers("/api/documents/**").denyAll()
```

The trailing general `denyAll()` blocks unlisted method/path combinations in the documents group. This is an **allowlist** strategy, safer than opening all methods and trying to block a few exceptions.

**How to read a long configuration:** go top to bottom, find the **first matcher** applying to the specific request; only then evaluate `hasRole`/`hasAuthority`. Never mentally merge rules together.

## 5. Complete Spring Security configuration by endpoint group

The example below uses **Spring Security Servlet** in a project with `spring-boot-starter-security` and appropriate authentication configuration. It is a real `@Configuration` class that compiles in a compatible Spring Boot project; running the full application also requires controllers, the Spring Web dependency, and an authentication source.

Create `ApiSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth

            // Public endpoint, declared intentionally.
            .requestMatchers("/api/health").permitAll()

            // Specific role groups must come before broad rules.
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/audit/**")
                .hasAnyRole("AUDITOR", "ADMIN")

            // Permission groups by HTTP action.
            .requestMatchers(
                HttpMethod.GET,
                "/api/documents",
                "/api/documents/*"
            ).hasAuthority("document:read")

            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("document:create")

            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority("document:edit")

            .requestMatchers(
                HttpMethod.POST,
                "/api/documents/*/approve"
            ).hasAuthority("document:approve")

            .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                .hasRole("DOCUMENT_ADMIN")

            // Do not allow remaining URLs/methods by default.
            .requestMatchers("/api/documents/**").denyAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

**Explanation of the blocks:**

1. `/api/health` is an **explicitly specified** public exception; other requests do not become public just for sharing the `/api` prefix.
2. `/api/admin/**` requires the ADMIN role, while `/api/audit/**` uses **OR** between AUDITOR and ADMIN.
3. The `document:read` permission protects both GET endpoints performing the same kind of action.
4. POST/PATCH/DELETE methods and the `approve` branch have separate rules; create permission does not mean approve permission.
5. Remaining `/api/documents/**` and `anyRequest().denyAll()` reject undeclared paths/methods.

**This does not mean every request in the system works with just this class.** You must supply authentication (session, JWT, login, etc.), role/permission mapping, and the corresponding controllers; mutating requests may require CSRF tokens per policy. When multiple `SecurityFilterChain`s exist, add appropriate matching/ordering constraints; see section 8.

### 5.1. Why doesn't the example use hasRole for all document operations?

The `DOCUMENT_EDITOR` role may grant multiple permissions, yet an endpoint should check the **exact capability required**. If only `hasRole("EDITOR")` is used for both GET and PATCH, every editor can read and edit via the role, making read-only users harder to express. The `document:read` and `document:edit` permissions keep rules clear and extensible.

Small projects with few actions can certainly use roles for a route group. What matters is a consistent convention and avoiding turning a global role into default access to every record.

### 5.2. Permission name catalog

To avoid typos across multiple places, you can define:

```java
package com.example.security;

public final class Permissions {
    private Permissions() {}

    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_CREATE = "document:create";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_APPROVE = "document:approve";
}
```

Then reference them in HTTP rules:

```java
.requestMatchers(HttpMethod.GET, "/api/documents", "/api/documents/*")
    .hasAuthority(Permissions.DOCUMENT_READ)
```

Creating constants does not automatically grant permissions to users. `Authentication` must be granted the exact same strings where authorities are built. If method security checks the same permission, keep **the same contract**; do not use `hasRole('READER')` on the method if HTTP only requires `document:read`, unless those are **two intentional additive conditions**.

## 6. Authority data must match the rules

### 6.1. Sample user authorities

| Sample user | Actual authorities | Expected outcome |
| --- | --- | --- |
| Anonymous | No valid authentication | Passes only public rules like `/api/health` |
| Viewer | `ROLE_VIEWER`, `document:read` | Reads document list and details |
| Editor | `ROLE_DOCUMENT_EDITOR`, `document:read`, `document:create`, `document:edit` | Reads/creates/edits; does not automatically have approve permission |
| Approver | `ROLE_APPROVER`, `document:read`, `document:approve` | Reads and uses approval endpoint |
| Auditor | `ROLE_AUDITOR` | Enters `/api/audit/**`; does not automatically have `document:read` |
| Admin | `ROLE_ADMIN` | Enters `/api/admin/**` and `/api/audit/**`; **does not automatically have** document permissions unless granted |
| Document admin | `ROLE_DOCUMENT_ADMIN` | Allowed to attempt DELETE on documents; still subject to object policy |

The table only describes outcomes at the **HTTP authorization layer**. If a request targets a specific document ID, the service-layer policy can still deny due to tenant, owner, ACL, or status.

### 6.2. Granting a role and granting a permission are not the same

Example `UserDetails` with a role:

```java
User.withUsername("alice")
    .password("{noop}dev-only-password")
    .roles("DOCUMENT_EDITOR")
    .build();
```

In this DSL, `roles("DOCUMENT_EDITOR")` typically creates the authority `ROLE_DOCUMENT_EDITOR`. It **does not create** `document:edit` for Alice. The `{noop}` password format is only for demonstrating test environments and must never be used in production.

If you want to grant permissions as well, the authentication source must return the corresponding `GrantedAuthority`s or perform role → permission mapping at one clearly responsible place. Illustrative example only:

```java
var authorities = java.util.List.of(
        new SimpleGrantedAuthority("ROLE_DOCUMENT_EDITOR"),
        new SimpleGrantedAuthority("document:read"),
        new SimpleGrantedAuthority("document:edit")
);
```

`SimpleGrantedAuthority` belongs to `org.springframework.security.core.authority`. This snippet only builds an authority list; it does not authenticate the user or populate the security context.

### 6.3. JWT scopes and role prefixes

In OAuth 2.0 Resource Server with JWT, some default converters map scopes to authorities with the `SCOPE_` prefix. For example, a token scope `documents.read` usually becomes `SCOPE_documents.read`, which **does not automatically equal** `document:read`.

There are two consistent approaches:

- Use `hasAuthority("SCOPE_documents.read")` directly on the corresponding HTTP groups.
- Map verified scopes/claims into internal permissions like `document:read` and use those permissions uniformly everywhere.

Never take arbitrary roles/permissions from request bodies/headers to build `Authentication`. With tokens, verify signature, issuer, audience, expiration, and application rules before trusting claims.

## 7. Extended scenario: one request with multiple conditions

### 7.1. Roles and permissions are two combinable dimensions

For example, exporting financial reports requires both ADMIN and `report:export`. Using `hasAnyAuthority("ROLE_ADMIN", "report:export")` turns **AND** into **OR**: someone with only one of the two gets in. That is wrong if the policy requires both.

Common cases:

| Actual policy | How to express it |
| --- | --- |
| Has ADMIN role | `hasRole("ADMIN")` |
| Has ADMIN **or** AUDITOR role | `hasAnyRole("ADMIN", "AUDITOR")` |
| Has `document:read` | `hasAuthority("document:read")` |
| Has `document:edit` **or** `document:approve` | `hasAnyAuthority("document:edit", "document:approve")` |
| Has ADMIN role **and** `report:export` | Combine two authorization managers with **AND** |
| Has read permission **and** access to specific ID | HTTP permission **and** object policy in service |

Additional conditions can be implemented with `AuthorizationManagers.allOf(...)`, a custom `AuthorizationManager<RequestAuthorizationContext>`, or a domain policy depending on version and architecture. Every OR/AND rule must be documented in the permission matrix and tested.

### 7.2. Separately guarding high-risk endpoint groups

If `/api/admin/**` includes GET users and DELETE users, a general ADMIN role may be too broad. One way is placing the specific rule **before** the prefix rule:

```java
.requestMatchers(HttpMethod.DELETE, "/api/admin/users/*")
    .hasAuthority("user:delete")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

However, if DELETE requires `user:delete` **and also mandates the ADMIN role**, the rule above is **not enough** — a matching DELETE request will **not proceed** to the later ADMIN rule. You must combine the AND into **one** rule, or check the extra role at another explicit, tested enforcement point.

**Lesson:** two separate rules with overlapping URLs do not mean Spring Security evaluates both. Only the **first match** is used within the same `authorizeHttpRequests` block.

### 7.3. Having the right HTTP permission is not enough per record

For `GET /api/documents/d42`, HTTP checks `document:read`. In the service:

```java
// Fragment in a Spring-managed @Service.
// Requires @EnableMethodSecurity when using @PreAuthorize.
@PreAuthorize("hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)")
public DocumentView getDocument(String documentId) {
    return documentService.load(documentId);
}
```

`documentPolicy` is an **application-written bean** that reliably loads the document and checks tenant, owner, sharing, or ACL. `DocumentView` and `documentService` are examples; the method above is not a standalone program. `#documentId` requires parameter names to be available at runtime (e.g., compiled with `-parameters`).

If admins are allowed to read across owners/tenants, that policy must also explicitly define its scope; do not automatically grant `ROLE_ADMIN` read access to every tenant. Service-layer protection matters when business operations are also invoked from jobs or other controllers.

## 8. securityMatcher vs requestMatchers; multiple filter chains

Two APIs have similar names but different roles:

- `http.securityMatcher("/api/**")` limits **the request scope to which this entire `SecurityFilterChain` applies**.
- `authorizeHttpRequests(...requestMatchers("/api/admin/**").hasRole("ADMIN"))` selects **an authorization rule inside the already-selected chain**.

`securityMatcher` does not perform `hasRole` itself, and `requestMatchers` does not decide which chain applies. When multiple `SecurityFilterChain`s exist, Spring Security selects the **first matching chain** by chain order; only then does it evaluate authorization matchers inside that chain.

### 8.1. Multi-chain configurations need a fallback

A conceptual example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .build();
}

// Another SecurityFilterChain bean acting as fallback.
// Needs appropriate @Order, authentication config, and
// review of all paths outside /api/**.
```

This is a **fragment**; full imports and configuration depend on the application. If you only define a chain with `securityMatcher("/api/**")` and no other chain matching URLs outside `/api/**`, URLs outside that scope may **not be protected by a Spring Security filter chain**. This is a structural gap, different from a request hitting `anyRequest().denyAll()` inside a chain.

### 8.2. Servlet path, context path, and matcher strategy

In Spring MVC/Servlet, matcher paths can be affected by context path, servlet path, multiple servlet registrations, `MvcRequestMatcher`, or `PathPatternRequestMatcher` depending on the version. For example, an app deployed under context path `/myapp` still has MVC routes like `/api/documents`; do not arbitrarily prepend `/myapp` to patterns without verifying the contract.

With multiple servlets, use a matcher that handles servlet paths properly; do not guess solely from URLs seen in the browser. A reliable practice is writing integration tests with real routes, real HTTP methods, and environment-accurate context/servlet paths.

### 8.3. Method-level HTTP mappings must be protected per use case

A controller may map `@GetMapping("/api/documents/{id}")`, yet the underlying service might also be invoked from batches, scheduled jobs, or message consumers. Those paths may not pass through HTTP filters. For critical use cases, enforce business conditions (object policy, tenant, status) at the service/domain boundary, not only in web config.

## 9. permitAll, authenticated, denyAll, and public access concerns

Three common rules:

| Rule | Meaning |
| --- | --- |
| `permitAll()` | Allows requests past the **authorization rule** step without requiring a specific authority |
| `authenticated()` | Requires authentication; **does not specify business permissions** |
| `denyAll()` | Does not allow requests past that rule |

`permitAll` does not mean "skip all Spring Security filters". If a public route still goes through the filter chain, components like security headers, CORS, or other handlers still operate as configured.

### 9.1. Prefer permitAll over bypassing the filter chain

For public assets, `requestMatchers("/css/**", "/js/**").permitAll()` is usually preferred over `web.ignoring()`. Bypassing the entire filter chain can also skip other protections such as security headers.

### 9.2. authenticated does not equal functional authorization

```java
.requestMatchers("/api/**").authenticated()
```

ensures the user is logged in per framework semantics, but does not distinguish whether they are a viewer, editor, or approver. If every endpoint under `/api/**` is opened with login alone, functional authorization is missing. Design allowlist rules for sensitive actions, then use `denyAll` for the rest.

### 9.3. Status codes are not the sole indicator of a rule

- Unauthenticated: APIs typically return `401`; form-login apps may redirect.
- Authenticated but lacking role/authority: typically returns `403`.
- A route hitting `denyAll` also typically invokes the corresponding access-denied mechanism.
- POST/PATCH/DELETE requests missing a CSRF token can receive `403` **before** authority logic is evaluated.

The HTTP result also depends on `AuthenticationEntryPoint`, `AccessDeniedHandler`, CORS/CSRF, and error handlers. When testing authorization, verify why a request was blocked rather than relying on the `403` number alone.

## 10. CSRF, CORS, and HTTP methods

### 10.1. CSRF is not a permission

In session/cookie-based applications, state-changing operations may require a CSRF token. Passing `hasAuthority("document:edit")` does not make a `PATCH` request bypass the CSRF filter. In MockMvc tests, `.with(csrf())` can be used when CSRF is enabled.

Do not disable CSRF globally just to make `hasRole` tests pass easily. If an API uses Bearer tokens exclusively, does not rely on auto-sent cookies, and has a clear threat model, CSRF may be configured differently; keep that decision separate from rule placement.

### 10.2. CORS preflight and OPTIONS

Browsers may send an `OPTIONS` preflight before a cross-origin request. Preflights typically do not carry the same session/auth info as the main request. Therefore, integrate CORS properly so preflights are handled validly **before/at the right point** in the security chain.

Do not fix preflight errors by blindly opening `OPTIONS /**` and assuming all APIs are safe. If there is a rule for `OPTIONS`, test allowed origins, headers, and methods while ensuring actual requests remain subject to proper authorization/CSRF.

### 10.3. GET, HEAD, and routes supporting other methods

Some controllers/frameworks support HEAD based on GET mappings, yet never assume **every RequestMatcher** and GET security rule always protects HEAD as intended. When a system supports `HEAD`, `OPTIONS`, `PUT`, `DELETE`, or method overrides, test the actual HTTP methods enabled. Protecting only GET while overlooking mutating methods can create severe authorization bugs.

## 11. Standalone Java 17+ example: simulating permission groups

The following plain Java program **does not use Spring Security**. It simulates how an endpoint group is assigned a rule and how default authority/role matching works. The goal is to observe the outcomes of `hasRole`, `hasAuthority`, and `hasAnyRole`. Actual URL matching in Spring Security is handled by `RequestMatcher`, not the simple predicates in this demo.

Create file `HttpGroupAuthorizationDemo.java`:

```java
import java.util.Set;

public class HttpGroupAuthorizationDemo {

    enum Group {
        PUBLIC, ADMIN, AUDIT, DOCUMENT_READ,
        DOCUMENT_CREATE, DOCUMENT_EDIT, DOCUMENT_APPROVE, DENIED
    }

    static boolean hasAuthority(Set<String> granted, String required) {
        return granted != null && granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String role) {
        return hasAuthority(granted, "ROLE_" + role);
    }

    static boolean hasAnyRole(Set<String> granted, String first, String second) {
        return hasRole(granted, first) || hasRole(granted, second);
    }

    static Group group(String method, String path) {
        // Branches evaluated in order, matching the first-match idea.
        if (path.equals("/api/health")) {
            return Group.PUBLIC;
        }
        if (path.equals("/api/admin") || path.startsWith("/api/admin/")) {
            return Group.ADMIN;
        }
        if (path.equals("/api/audit") || path.startsWith("/api/audit/")) {
            return Group.AUDIT;
        }
        if (method.equals("GET")
                && (path.equals("/api/documents")
                    || path.matches("/api/documents/[^/]+"))) {
            return Group.DOCUMENT_READ;
        }
        if (method.equals("POST") && path.equals("/api/documents")) {
            return Group.DOCUMENT_CREATE;
        }
        if (method.equals("PATCH")
                && path.matches("/api/documents/[^/]+")) {
            return Group.DOCUMENT_EDIT;
        }
        if (method.equals("POST")
                && path.matches("/api/documents/[^/]+/approve")) {
            return Group.DOCUMENT_APPROVE;
        }
        return Group.DENIED;
    }

    static String decision(String method, String path, Set<String> authorities) {
        boolean allowed = switch (group(method, path)) {
            case PUBLIC -> true;
            case ADMIN -> hasRole(authorities, "ADMIN");
            case AUDIT -> hasAnyRole(authorities, "AUDITOR", "ADMIN");
            case DOCUMENT_READ ->
                    hasAuthority(authorities, "document:read");
            case DOCUMENT_CREATE ->
                    hasAuthority(authorities, "document:create");
            case DOCUMENT_EDIT ->
                    hasAuthority(authorities, "document:edit");
            case DOCUMENT_APPROVE ->
                    hasAuthority(authorities, "document:approve");
            case DENIED -> false;
        };
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> anonymous = Set.of();
        Set<String> viewer = Set.of("ROLE_VIEWER", "document:read");
        Set<String> editor = Set.of(
                "ROLE_DOCUMENT_EDITOR",
                "document:read", "document:create", "document:edit");
        Set<String> auditor = Set.of("ROLE_AUDITOR");
        Set<String> admin = Set.of("ROLE_ADMIN");

        System.out.println("anonymous-health="
                + decision("GET", "/api/health", anonymous));
        System.out.println("anonymous-documents="
                + decision("GET", "/api/documents", anonymous));
        System.out.println("viewer-list="
                + decision("GET", "/api/documents", viewer));
        System.out.println("viewer-edit="
                + decision("PATCH", "/api/documents/d42", viewer));
        System.out.println("editor-edit="
                + decision("PATCH", "/api/documents/d42", editor));
        System.out.println("editor-approve="
                + decision("POST", "/api/documents/d42/approve", editor));
        System.out.println("auditor-audit="
                + decision("GET", "/api/audit/events", auditor));
        System.out.println("auditor-admin="
                + decision("GET", "/api/admin/users", auditor));
        System.out.println("admin-audit="
                + decision("GET", "/api/audit/events", admin));
        System.out.println("admin-doc-read="
                + decision("GET", "/api/documents/d42", admin));
        System.out.println("unlisted-path="
                + decision("GET", "/api/unknown", admin));
    }
}
```

Compile/run with **JDK 17 or newer**:

```bash
javac HttpGroupAuthorizationDemo.java
java HttpGroupAuthorizationDemo
```

Expected stdout:

```text
anonymous-health=ALLOW
anonymous-documents=DENY
viewer-list=ALLOW
viewer-edit=DENY
editor-edit=ALLOW
editor-approve=DENY
auditor-audit=ALLOW
auditor-admin=DENY
admin-audit=ALLOW
admin-doc-read=DENY
unlisted-path=DENY
```

**Analysis:**

- Viewer has `document:read` so it passes the GET group, but lacks `document:edit` so PATCH is blocked.
- Editor has edit permission but lacks `document:approve`; calling approve must be denied.
- Auditor with AUDITOR role and Admin with ADMIN role both enter the audit group because `hasAnyRole` is OR.
- Admin **is not automatically allowed to read documents** merely via `ROLE_ADMIN`; if business logic requires it, grant the permission or define an explicit policy.
- Undeclared paths fall into `DENIED`, matching the idea of `anyRequest().denyAll()`.

**Simulation boundaries:** this is a custom Java program illustrating logic; it does not perform authentication, CSRF, Spring path matching, filter chain selection, or HTTP status codes. All **per-object** permission decisions must still be checked by the real application's domain policy.

## 12. Testing endpoint groups with Spring Security Test

An HTTP configuration that looks right can still suffer from overly broad matchers, ungranted roles, undeclared new routes, or CSRF/CORS conditions. Therefore, test against a **request and authority matrix**.

### 12.1. Minimum matrix

| Request | Test principal authorities | Expectation at HTTP authorization layer |
| --- | --- | --- |
| `GET /api/health` | Anonymous | Allow past authorization rule |
| `GET /api/documents` | `document:read` | Allow past rule |
| `GET /api/documents/d42` | `ROLE_VIEWER` without `document:read` | Deny |
| `POST /api/documents` | `document:create` | Allow past rule |
| `POST /api/documents` | `document:read` | Deny |
| `PATCH /api/documents/d42` | `document:edit` | Allow past rule |
| `POST /api/documents/d42/approve` | `document:edit` | Deny |
| `GET /api/audit/events` | `ROLE_AUDITOR` | Allow past rule |
| `GET /api/audit/events` | `ROLE_ADMIN` | Allow past rule |
| `GET /api/admin/users` | `ROLE_AUDITOR` | Deny |
| `GET /api/admin/users` | `ROLE_ADMIN` | Allow past rule |
| `GET /api/unknown` | `ROLE_ADMIN` | Deny per fallback |
| `DELETE /api/documents/d42` | `ROLE_DOCUMENT_ADMIN` | Passes HTTP rule; object policy may still deny |

"Allow past rule" **does not equal returning HTTP 200**: the controller may not exist, the resource may not be found, business validation may fail, or method security may have a stricter policy.

### 12.2. @WithMockUser: roles vs authorities

In `spring-security-test`:

```java
@WithMockUser(roles = "ADMIN")
```

normally creates a test principal with the `ROLE_ADMIN` authority.

Whereas:

```java
@WithMockUser(authorities = "document:read")
```

grants `document:read` literally, **without automatically granting** `ROLE_VIEWER`.

Tests using `roles="DOCUMENT_EDITOR"` do not automatically reflect `document:edit` if production only maps roles to permissions at login time. Also test the permission-mapping step at the authority source or run integration tests with real authentication.

### 12.3. MockMvc test fragment

The following example is only a **fragment** in a test class with `MockMvc`, Spring Security Test, appropriate controllers/fixtures, and imports; it is not a standalone `javac` program:

```java
@Test
@WithMockUser(authorities = "document:read")
void readerCanReachDocumentReadEndpoint() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "document:read")
void readerCannotEditDocument() throws Exception {
    mockMvc.perform(patch("/api/documents/d42").with(csrf()))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "AUDITOR")
void auditorCannotCallAdminEndpoints() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
}
```

**Important conditions:** the first test only expects `200` if `d42` exists, the controller returns OK, and the principal also passes object policy. Without a handler, the status can be 404 after passing filters; do not mistake that for a broken rule. The PATCH test uses `with(csrf())` to verify that 403 comes from edit permission (if CSRF is enabled) rather than a missing CSRF token.

### 12.4. Additional test cases to include

1. **Pattern overlap:** a logged-in user without admin role cannot call `/api/admin/**` even when a broad catch-all route exists.
2. **Wrong method:** someone with `document:read` cannot PATCH/DELETE/POST the same path; also test HEAD/OPTIONS/PUT when supported by the app.
3. **Wrong prefix:** `ROLE_ADMIN` passes `hasRole("ADMIN")`; raw `ADMIN` does not pass by default.
4. **Authority-grant mismatch:** `ROLE_DOCUMENT_EDITOR` does not automatically equal `document:edit`; `SCOPE_documents.read` does not automatically equal `document:read`.
5. **No rule:** new endpoints, nested paths, or newly versioned URLs must not open accidentally.
6. **Role OR:** either AUDITOR or ADMIN enters audit; users lacking both are denied.
7. **AND policy:** if export requires both ADMIN role and export permission, missing either one must deny.
8. **Object security:** having `document:read` still cannot view records of another tenant/owner.
9. **Filter chain:** URLs outside `securityMatcher` have an appropriate fallback chain and do not slip outside Spring Security.
10. **CORS/CSRF:** preflights, cookie-bearing requests, and mutating operations behave according to the security configuration.

## 13. Common mistakes in group authorization

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `/api/**.authenticated()` before `/api/admin/**.hasRole("ADMIN")` | Admin group only requires login | Put specific rules first; test first-match |
| Using `hasAuthority("ADMIN")` when the user has `ROLE_ADMIN` | Wrongly denied | Use `hasRole("ADMIN")` or the full prefixed string |
| Habitually passing `hasRole("ROLE_ADMIN")` | Violates default API prefix contract | Pass `ADMIN` to `hasRole` |
| Using `hasAnyRole("ADMIN","AUDITOR")` to require both | Accidentally broadens access | Use AND logic when both are mandatory |
| Using `hasAuthority("document:read")` for all methods on `/api/documents/**` | Read permission may suffice to call DELETE/PATCH | Split by HTTP method + action |
| Leaving a general matcher before a sensitive matcher | Later rule never applies | Specific rules before general ones |
| Assuming `authenticated()` suffices for the whole API | Missing functional authorization | Assign roles/permissions by action |
| Omitting `anyRequest().denyAll()` or an appropriate fallback | New routes may lack intended policies | Use an allowlist and test undeclared endpoints |
| Declaring only `securityMatcher("/api/**")` without another chain | URLs outside `/api/**` may fall outside the filter chain | Define an explicit fallback chain |
| Treating admin role as access to every tenant | Cross-scope over-access | Combine role with scope/object policy |
| Confusing `SCOPE_documents.read` with `document:read` | Wrong denials or bad mapping | Define a consistent converter and convention |
| Enabling `permitAll` and assuming the whole filter chain is skipped | Misunderstanding security headers/CSRF | Distinguish filter bypass from authorization rules |
| Disabling CSRF just because MockMvc returned 403 | Weakens protection for cookie-based mutations | Test with `csrf()`; decide CSRF config by threat model |
| Trusting hard-to-guess paths as authorization | IDOR/BOLA | Check owner, tenant, and ACL in services |

## 14. Process for designing and maintaining endpoint groups

**Step 1 — Build an action table.** From the API contract, list HTTP methods, paths, use cases, sensitive data, and valid users. Never start by writing overly broad wildcards.

**Step 2 — Define canonical authority names.** For example `document:read`, `document:create`, `document:edit`, `document:approve`, `user:delete`; roles `ROLE_ADMIN`/`ROLE_AUDITOR`. Document the meaning and scope of each authority.

**Step 3 — Group by shared policy, not just shared URL.** Document GET endpoints can share a read permission; the approve action must have a distinct permission even though it sits under the same `/api/documents` prefix.

**Step 4 — Design the ordering.** Public endpoints are declared explicitly; sensitive and method-specific rules come before general rules; end with a deny fallback. Cross-check overlapping patterns.

**Step 5 — Verify authority sources.** Runtime `GrantedAuthority` sets must match `hasRole`/`hasAuthority`. For JWTs, verify converters, issuer/audience, and scope/role mapping; for username/password, verify role → permission mapping.

**Step 6 — Object-level authorization.** For routes with `{id}`, add tenant, owner, reviewer, ACL, and status checks at the service/repository layer. For list/search/export, queries must only retrieve authorized records.

**Step 7 — Protect non-HTTP entry points.** Jobs, event consumers, and internal service calls should not rely solely on web rules; enforce business invariants at the appropriate execution boundary.

**Step 8 — Test matrix.** Cover valid permissions, missing permissions, role-prefix mismatches, wrong methods, overlapping routes, fallbacks, CSRF/CORS, and cross-tenant calls. Test with the exact Spring Security/Servlet matcher dependencies used in production.

**Step 9 — Review when APIs change.** Every new endpoint must have an action mapping and tests. For sensitive permissions, review impact before deploying. With multiple chains, review `@Order`, `securityMatcher`, and fallback alongside `requestMatchers`.

**Step 10 — Monitor denial decisions.** Audit subject ID, action, resource ID, rule/policy, outcome, and timestamp at an appropriate level; never log tokens or unnecessary sensitive data. When investigating a spike in 403s, identify whether it came from authz, CSRF, endpoint, method, or object policy instead of broadening permissions wholesale.

## 15. Self-check questions

**Question 1.** A user has `ROLE_ADMIN` and requests `GET /api/admin/users`. Does `.hasRole("ADMIN")` let it through?

**Answer:** Yes, at the default matcher/authority layer, provided the request matches that rule and authentication is valid. Other security layers may still deny it.

**Question 2.** A user has `ROLE_ADMIN` but not `document:read`. `GET /api/documents/d42` uses `hasAuthority("document:read")`. Does it pass?

**Answer:** No, given those authorities. The ADMIN role does not automatically imply read permission; an explicit mapping or permissive policy is needed.

**Question 3.** Configuration has `.requestMatchers("/api/**").authenticated()` before `.requestMatchers("/api/admin/**").hasRole("ADMIN")`. Why can regular users still reach admin?

**Answer:** `AuthorizationFilter` uses **first-match-wins**; `/api/**` matches first so the later ADMIN rule is unused.

**Question 4.** Does `hasAnyRole("AUDITOR", "ADMIN")` require both roles?

**Answer:** No. Only one of the two is required. Requiring both must be expressed as an AND.

**Question 5.** `PATCH /api/documents/d42` has `document:edit` permission, but the document belongs to another tenant. Should the edit succeed?

**Answer:** No. HTTP permission is a functional check; the service must enforce object/tenant policies. Functional permissions do not grant access to every ID.

**Question 6.** You add `GET /api/documents/d42/versions` without writing a matcher for it. Why shouldn't you rely on `/api/documents/*`?

**Answer:** `*` usually matches only a single path segment in many matchers; nested endpoints need their own rule or suitable pattern. A `denyAll` fallback and integration tests help avoid accidental exposure.

**Question 7.** A MockMvc PATCH test returns 403 even though `document:edit` was granted. Next steps?

**Answer:** Check CSRF (if enabled), which matcher matched first, the actual Authentication, method security/object policy, and controller/exception handlers. Do not hastily grant admin or disable CSRF.

**Question 8.** When using multiple `SecurityFilterChain`s, does merely adding `anyRequest().denyAll()` in a chain scoped with `securityMatcher("/api/**")` protect all URLs?

**Answer:** No. `anyRequest()` applies only **inside the selected chain**. A fallback chain must be defined for URLs outside `/api/**`.

**Remember:** Group endpoints with `requestMatchers`, assign exact roles/permissions with `hasRole`/`hasAuthority`, place specific rules **before** general ones, distinguish HTTP methods, use a **deny by default** fallback, and add object-level authorization in services. Security depends on the **actual granted authorities**, the **actually selected request matcher**, and the **policy enforcement point**, not just annotation or endpoint names.

## References

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Testing MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
