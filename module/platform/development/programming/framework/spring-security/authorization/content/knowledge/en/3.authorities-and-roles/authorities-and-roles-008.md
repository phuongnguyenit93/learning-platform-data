# Consistent Permission Naming Conventions Between HTTP Config and Method Security

## 1. Why must a permission have the same meaning across every layer?

In a Spring Security application, a request may pass through at least two authorization gates: **HTTP configuration** in `SecurityFilterChain` and **method security** when invoking a Spring bean method. Both layers read `GrantedAuthority` instances from `Authentication`, yet they can use different expressions:

```java
// HTTP gate
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")

// Method gate, on the service
@PreAuthorize("hasRole('READER')")
```

These two conditions **are not equivalent** by default. `hasAuthority("document:read")` looks for the exact authority string `document:read`, whereas `hasRole("READER")` usually looks for `ROLE_READER`. A user might pass one layer and be blocked at the other even though the development team thought both meant "document read permission".

The reverse scenario is also dangerous: HTTP config requires `ROLE_ADMIN` while the method only checks `authenticated()`, or two endpoints call the same service yet define conflicting permissions. That can let tests pass on one path while internal jobs, other endpoints, or service call chains behave unexpectedly.

**Lesson goal:** establish consistent role/permission naming; understand `hasAuthority`, `hasRole`, and the default prefix precisely; organize a permission catalog usable by HTTP, methods, and tests; catch mismatches from JWT/login/role mappings; and preserve object-level authorization layers required by business rules.

## 2. The actual authority string is what gets matched

An `Authentication` object holds a collection of `GrantedAuthority` instances. With `SimpleGrantedAuthority`, each element holds a string. Authorization expressions match against those granted strings—not by inferring from business role names or UI screens.

For example, after authentication, user Alice has authorities:

```text
ROLE_EDITOR
document:read
document:edit
```

Then:

| Expression | Required string by default | Result for Alice |
| --- | --- | --- |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` | **true** |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | **true** |
| `hasAuthority("EDITOR")` | `EDITOR` | **false** |
| `hasAuthority("document:read")` | `document:read` | **true** |
| `hasAuthority("document:edit")` | `document:edit` | **true** |
| `hasRole("READER")` | `ROLE_READER` | **false** |
| `hasAuthority("DOCUMENT:READ")` | `DOCUMENT:READ` | **false** |
| `hasAuthority("SCOPE_document:read")` | `SCOPE_document:read` | **false** |

The strings `document:read`, `DOCUMENT:READ`, `ROLE_READER`, and `SCOPE_document:read` **are not equivalent by default**. Casing, delimiters, prefixes, and namespaces are all part of the contract.

### 2.1. `hasAuthority` matches the full string

In HTTP:

```java
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasAuthority("document:read")
```

In method security:

```java
@PreAuthorize("hasAuthority('document:read')")
```

When both are configured with the exact same string, the same `Authentication` having `document:read` passes the permission check at **both layers**. `hasAuthority` does not prepend `ROLE_`, `SCOPE_`, or rename `document_read` to `document:read`.

For multiple permissions, you can use `hasAnyAuthority(...)` when **at least one** permission suffices; use `and` logic or an equivalent mechanism when **all** permissions are mandatory. Never replace `and` with `or` just to work around a naming bug.

### 2.2. `hasRole` is a prefix-aware shorthand

Under the **default convention** `ROLE_`:

```text
hasRole("ADMIN")      ≈ hasAuthority("ROLE_ADMIN")
hasRole("EDITOR")     ≈ hasAuthority("ROLE_EDITOR")
hasAnyRole("A","B")  ≈ hasAnyAuthority("ROLE_A","ROLE_B")
```

Method security also supports `hasRole('ADMIN')` and `hasAuthority('ROLE_ADMIN')`. `hasRole` accepts the **unprefixed business role name** in standard usage. Do not pass `hasRole("ROLE_ADMIN")` out of habit, because APIs may reject already-prefixed roles or handle prefixes unexpectedly; pass `"ADMIN"` and standardize prefixes in configuration.

Spring Security allows customizing the role prefix, e.g., via `GrantedAuthorityDefaults`, and different authorization versions/configs have different extension points. **If you changed the prefix**, do not assume every HTTP matcher, method expression, role hierarchy, test, and converter follows the same convention automatically. Verify behavior in your project's Spring Security version and write integration tests for both layers. For many projects, keeping the default `ROLE_` reduces risk.

### 2.3. `Role` differs from `permission` even though both are `GrantedAuthority`

A clear naming scheme looks like:

```text
Role:
  ROLE_DOCUMENT_EDITOR
  ROLE_DOCUMENT_REVIEWER
  ROLE_TENANT_ADMIN

Permission:
  document:read
  document:edit
  document:approve
  user:invite
```

A role describes a responsibility or permission group, whereas a permission describes a business action. One role can grant multiple permissions, for example:

```text
ROLE_DOCUMENT_EDITOR
    ├─ document:read
    └─ document:edit

ROLE_DOCUMENT_REVIEWER
    ├─ document:read
    └─ document:approve
```

Spring Security does not automatically know that `ROLE_DOCUMENT_EDITOR` implies `document:edit`. To check by permission, the application must **grant that exact authority** (for example when loading the user) or configure an intentional role hierarchy/mapping mechanism. Do not scatter mapping logic across individual endpoints.

## 3. Choose one shared convention across the project

Example convention for a document management application:

| Category | Syntax | Example | Meaning |
| --- | --- | --- | --- |
| Role | `ROLE_<BUSINESS_ROLE>` | `ROLE_DOCUMENT_EDITOR` | Stable responsibility group; pass `DOCUMENT_EDITOR` to `hasRole` |
| Permission | `<resource>:<action>` | `document:read` | Capability to perform a business action |
| OAuth 2.0 scope as authority | `SCOPE_<scope>` via default converter | `SCOPE_documents.read` | Scope/permission from access token, **only when** token is verified |
| Object-level authorization | Rules on server-side data | `document.ownerId == currentUserId` | Additional constraint, not a new role per ID |
| Tenant/membership | Scoped data | `tenant=alpha; role=EDITOR` | Role/permission effective within the matching scope |

The convention above is an **applicable example**, not mandatory Spring Security syntax. A project could use `permission:document:read` or `DOCUMENT_READ`, provided the issuer/producer and all consumers stay consistent.

### Naming principles to codify as conventions

1. **Separate namespaces:** `ROLE_` is for roles, `document:read` is for permissions; do not use `ADMIN` as a role in one place and a permission in another.
2. **Maintain exact casing:** e.g., uppercase roles, lowercase permissions with `:`; avoid relying on "readers understand they mean the same thing".
3. **Tie permission names to business actions:** `invoice:approve` differs from `invoice:edit`; do not use HTTP `POST` as a blanket permission for every write command.
4. **Avoid encoding dynamic data in roles:** `ROLE_EDITOR_TENANT_ALPHA_DOCUMENT_42` usually signals role explosion; use role + scope + resource policy.
5. **Define permissions in one clearly owned place:** maintain a permission catalog, contract-change owners, and review rules.
6. **Never rename silently:** changing `document:read` to `documents:read` is a contract change requiring simultaneous updates to authority producers, HTTP, methods, and tests.
7. **Grant no default access for unknown/missing names:** apply deny-by-default.

A "clean" name that only exists in source code is useless if `Authentication.getAuthorities()` actually contains a different string.

## 4. Common mismatch patterns

### 4.1. HTTP checks role, method checks permission

```java
// HTTP
.requestMatchers(HttpMethod.GET, "/api/documents/*")
    .hasRole("DOCUMENT_EDITOR")

// Method
@PreAuthorize("hasAuthority('document:read')")
```

These are **two different conditions**: one demands `ROLE_DOCUMENT_EDITOR`, the other demands `document:read`. If business rules intentionally require **both role and permission**, this is valid, provided it is documented and tested. If both layers are trying to express *the same read permission*, the style is inconsistent and can deny users who only hold `ROLE_DOCUMENT_VIEWER` even when they have `document:read`.

### 4.2. HTTP checks `hasAuthority("ROLE_ADMIN")`, method checks `hasAuthority("ADMIN")`

```text
Authentication authorities: [ROLE_ADMIN]

HTTP required:     ROLE_ADMIN  → ALLOW
Method required:   ADMIN       → DENY
```

It fails because the method lacks the prefix, not because method security is "stricter" than HTTP. The two equivalent forms for a default role are `hasRole('ADMIN')` or `hasAuthority('ROLE_ADMIN')`.

### 4.3. One layer uses role, the other uses JWT scope

An OAuth 2.0 Resource Server using JWT typically maps scopes into `SCOPE_`-prefixed authorities. For example, an access token with scope `documents.read` can yield:

```text
SCOPE_documents.read
```

This **does not automatically produce** `ROLE_DOCUMENT_VIEWER` or `document:read`. Therefore:

```java
// Can be right if enforcing an OAuth scope:
.hasAuthority("SCOPE_documents.read")

// Only right if the business permission was explicitly granted/mapped:
.hasAuthority("document:read")
```

Decide on a strategy:

- **Use token scopes directly:** both HTTP and method require `SCOPE_documents.read`, plus resource-level policy if needed.
- **Translate trusted claims/scopes to internal permissions:** use a verified converter or authorization service to grant `document:read`; then **both layers** check `document:read`.

Never treat arbitrary claims or client-sent values as authorities. Tokens must have signature, issuer, audience (per app requirements), validity period, and related constraints verified before trusting any permissions.

### 4.4. Both layers use the same string with different meanings

Suppose `report:read` in HTTP means "view summary reports", whereas in the method it means "read every report record including confidential data". This is a **semantic mismatch** despite identical names. Define clearly scoped permissions and add policies by object, data classification, or distinct actions like `report:export`.

### 4.5. Enabling HTTP security only, forgetting method security

`@PreAuthorize` on a service is not guaranteed to run if method security is not enabled. In modern configurations, put `@EnableMethodSecurity` on a `@Configuration` class. Spring Boot Starter Security does not enable all method authorization annotations by default.

Direct calls between methods in the same bean (*self-invocation*) can also bypass the Spring AOP proxy. Verify actual enforcement points and call paths through controllers, schedulers, and consumers.

## 5. Granting flow: align from where Authentication is built

A clean architecture diagram:

```text
UserDetailsService / AuthenticationProvider / JWT converter
                          │
                          ▼
          Authentication + GrantedAuthority[]
                          │
          ┌───────────────┴─────────────────┐
          ▼                                 ▼
SecurityFilterChain                 Method security
hasAuthority("document:read")       @PreAuthorize("hasAuthority('document:read')")
          │                                 │
          └─────────────┬───────────────────┘
                        ▼
                Business policy
          tenant / owner / state / MFA
                        │
                        ▼
                  ALLOW / DENY
```

**Operational evaluation order** is normally HTTP security before the controller is invoked, followed by the interceptor at the method call boundary. Yet the diagram does not imply request matchers cover every way a method is invoked: jobs, event consumers, or other services can invoke methods without going through HTTP. Choose enforcement points matching all real entry paths.

### Common authority sources

- **Username/password login:** `UserDetails`/`AuthenticationProvider` grants authorities. A `UserDetailsService` can attach `ROLE_DOCUMENT_EDITOR` and mapped permissions.
- **JWT/OAuth 2.0:** decoder and converter build `Authentication`. By default scopes may appear as `SCOPE_...`, while application roles/permissions must be intentionally mapped.
- **Role hierarchy:** can make higher roles imply other roles/authorities; configure and test consistently across HTTP and methods. Do not assume a hierarchy applies automatically across every expression type and config version.
- **Object-level policy:** relies on current server-verified resource/membership data. Avoid turning thousands of per-ID permissions into bloated authorities inside tokens.

**Note on revocation:** authorities inside a long-lived JWT can remain valid after a role is revoked in the database. Choose token lifetimes, membership checks, and invalidation strategies matching business risk.

## 6. Organizing shared permission constants for HTTP and methods

One way to prevent typos is to define an authority catalog in Java. For example `src/main/java/com/example/security/SecurityAuthorities.java`:

```java
package com.example.security;

public final class SecurityAuthorities {
    private SecurityAuthorities() {}

    public static final String ROLE_DOCUMENT_EDITOR = "ROLE_DOCUMENT_EDITOR";
    public static final String DOCUMENT_READ = "document:read";
    public static final String DOCUMENT_EDIT = "document:edit";
    public static final String DOCUMENT_APPROVE = "document:approve";
}
```

These constants only solve **naming**. They do not grant permissions to users by themselves; whatever builds `Authentication` must supply the exact matching strings. Match class/package naming to the actual codebase, avoiding conflicting copies across modules.

### 6.1. Using the same permissions in HTTP

Servlet Spring Security configuration example, an **integration snippet** placed inside a `@Configuration` class with matching imports and dependencies:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .hasAuthority(SecurityAuthorities.DOCUMENT_READ)
            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority(SecurityAuthorities.DOCUMENT_EDIT)
            .requestMatchers(HttpMethod.POST, "/api/documents/*/approve")
                .hasAuthority(SecurityAuthorities.DOCUMENT_APPROVE)
            .anyRequest().denyAll()
    ).build();
}
```

`SecurityAuthorities` must be imported from `com.example.security`. This snippet only illustrates the listed routes; list, download/export, batch, and delete endpoints need their own exact rules. `anyRequest().denyAll()` denies undeclared routes, a safe default while building an allowlist of endpoints. Route matching also depends on specific Spring MVC/Servlet settings and requires integration testing.

If the application uses CSRF with sessions/cookies, `PATCH`/`POST` operations may be blocked for missing CSRF tokens even with the right authority. In tests, distinguish CSRF errors from authorization errors; never disable CSRF globally just to make tests pass.

### 6.2. Reusing the same permission in `@PreAuthorize`

Annotation strings must be SpEL expressions. You can access `public static final` constants via the `T(...)` operator using the **fully qualified class name**:

```java
@PreAuthorize(
    "hasAuthority(T(com.example.security.SecurityAuthorities).DOCUMENT_READ)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

This is an **illustrative code snippet inside a Spring-managed service**: `Document`, `documentRepository`, imports, and security config must exist in the project. Because SpEL reads the constant from `com.example.security.SecurityAuthorities`, HTTP and method share the exact **single source of truth**. If `DOCUMENT_READ` changes to another permission string, you only update one constant along with authority producers and tests.

The shorter literal form is also valid:

```java
@PreAuthorize("hasAuthority('document:read')")
```

However, with many check points or likely renames, constants/composed annotations and contract tests prevent drifting strings. Keep the structure proportional—no need to invent a custom policy framework for a handful of authorities.

### 6.3. Combining consistent permissions with object checks

Permission `document:read` **does not** mean permission to view every document. You can combine an application policy bean:

```java
@PreAuthorize(
    "hasAuthority(T(com.example.security.SecurityAuthorities).DOCUMENT_READ) " +
    "and @documentAccess.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

The `documentAccess` bean must load the actual resource and verify tenant, owner/share permissions/status; `#documentId` requires parameter name metadata (e.g., compiling with `-parameters` or explicit SpEL parameter naming). Object checking is an **intentional additional constraint**, not a contradiction between two permission names.

For operations with side effects, policies and data writes should sit inside proper transaction/update-condition boundaries so resource state cannot change after checking. Do not default to `@PostAuthorize` for mutating operations: evaluating after execution may be too late to prevent side effects.

### 6.4. If you prefer roles instead of permissions

A small project might consistently use roles in both places:

```java
// HTTP:
.requestMatchers("/admin/**").hasRole("ADMIN")

// Method:
@PreAuthorize("hasRole('ADMIN')")
```

This condition expects `ROLE_ADMIN` by default. If you later want finer-grained permission checks, align both layers to `hasAuthority("user:invite")` or other authorities **after** the authority producer maps them accordingly.

**Do not conclude every API needs two identical check layers.** HTTP usually guards the request surface; methods can guard sensitive use cases and resource policies. Each layer's requirement must be an explicit design choice: either the same permission, or two complementary conditions that are documented and tested.

## 7. Standalone Java 17+ example: checking permission names

This program has no Spring dependency and reproduces the default matching conventions of `hasAuthority` and `hasRole` to make prefix effects visible. Inside Spring, expressions also depend on `Authentication`, role prefix/config, and authorization enforcement points; this demo focuses on **string-matching rules**.

Create `AuthorityNamingDemo.java`:

```java
import java.util.Set;

public class AuthorityNamingDemo {
    private static final String ROLE_PREFIX = "ROLE_";
    private static final String DOCUMENT_READ = "document:read";
    private static final String DOCUMENT_EDIT = "document:edit";

    static boolean hasAuthority(Set<String> authorities, String required) {
        return authorities != null && authorities.contains(required);
    }

    static boolean hasRole(Set<String> authorities, String role) {
        return hasAuthority(authorities, ROLE_PREFIX + role);
    }

    static String decision(Set<String> authorities, String required) {
        return hasAuthority(authorities, required) ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> alice = Set.of("ROLE_EDITOR", DOCUMENT_READ);

        System.out.println("role-EDITOR=" + hasRole(alice, "EDITOR"));
        System.out.println("raw-EDITOR=" + hasAuthority(alice, "EDITOR"));
        System.out.println("raw-ROLE_EDITOR="
                + hasAuthority(alice, "ROLE_EDITOR"));
        System.out.println("read-lowercase="
                + hasAuthority(alice, DOCUMENT_READ));
        System.out.println("read-uppercase="
                + hasAuthority(alice, "DOCUMENT:READ"));

        // Both layers check the same permission in the authority set.
        System.out.println("http-read=" + decision(alice, DOCUMENT_READ));
        System.out.println("method-read=" + decision(alice, DOCUMENT_READ));
        System.out.println("http-edit=" + decision(alice, DOCUMENT_EDIT));
        System.out.println("method-edit=" + decision(alice, DOCUMENT_EDIT));

        // OAuth scope is a different authority without intentional mapping.
        Set<String> tokenAuthorities = Set.of("SCOPE_document:read");
        System.out.println("scope-without-mapping="
                + decision(tokenAuthorities, DOCUMENT_READ));
        System.out.println("scope-with-explicit-check="
                + decision(tokenAuthorities, "SCOPE_document:read"));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac AuthorityNamingDemo.java
java AuthorityNamingDemo
```

Exact stdout:

```text
role-EDITOR=true
raw-EDITOR=false
raw-ROLE_EDITOR=true
read-lowercase=true
read-uppercase=false
http-read=ALLOW
method-read=ALLOW
http-edit=DENY
method-edit=DENY
scope-without-mapping=DENY
scope-with-explicit-check=ALLOW
```

Key takeaways:

- `hasRole("EDITOR")` checks `ROLE_EDITOR` in the default model; `hasAuthority("EDITOR")` requires **exact** `EDITOR` and therefore fails.
- When HTTP and method both require `document:read`, they are consistent: Alice passes both. Without `document:edit`, both deny.
- `SCOPE_document:read` does not automatically equal `document:read`. Choose one convention or map from scope to permission **intentionally**.

In a real system, never let clients pass an `authorities` list as a parameter and apply it directly. The authentication/authorization layer is responsible for building a trusted `Authentication`.

## 8. Testing HTTP and methods as a single shared contract

A permission change is only safe when both the granting side and the consuming side are tested. Do not just test successful login or check whether the UI hides a button.

### 8.1. Most important test matrix

Suppose endpoint `GET /api/documents/d42` and service `readDocument("d42")` both require `document:read`:

| Actual Authentication authorities | HTTP requires `document:read` | Method requires `document:read` | Meaning |
| --- | --- | --- | --- |
| `document:read` | ALLOW | ALLOW | Matches convention |
| `ROLE_DOCUMENT_VIEWER` | DENY | DENY | Role not yet mapped to permission |
| `ROLE_DOCUMENT_VIEWER`, `document:read` | ALLOW | ALLOW | Role + permission granted explicitly |
| `document:edit` | DENY | DENY | Edit does not imply read without an extra granting rule |
| `SCOPE_documents.read` | DENY | DENY | Scope not mapped to internal permission |
| `DOCUMENT:READ` | DENY | DENY | Wrong casing |
| No authorities | DENY | DENY | Deny by default |

If policy requires `read` to also be granted via `edit`, express that via mapping/role hierarchy or an intentional policy. **Do not guess that edit permission always includes read**.

### 8.2. Difference between `@WithMockUser.roles` and `@WithMockUser.authorities`

In Spring Security tests:

```java
@WithMockUser(roles = "DOCUMENT_VIEWER")
```

usually creates an `Authentication` with authority `ROLE_DOCUMENT_VIEWER`.

Meanwhile:

```java
@WithMockUser(authorities = "document:read")
```

creates the exact string authority `document:read`. These two annotations do not automatically create the same permission set.

A test using `@WithMockUser(roles="DOCUMENT_VIEWER")` may pass with `hasRole('DOCUMENT_VIEWER')` yet fail with `hasAuthority('document:read')`. If production actually maps role → permission at login, testing solely with mock roles **does not simulate that mapping**. Add integration tests against the production Authentication/converter flow or test the mapping separately.

### 8.3. Test coverage checklist

1. **HTTP layer:** exact method and path routes; with/without authority; unmatched routes; `denyAll` fallback.
2. **Method layer:** is `@PreAuthorize` actually intercepted in a Spring-managed bean; proxied calls; internal/self-invocation calls.
3. **Authority granting:** username/password, JWT converters, role hierarchy/membership produce exact character-for-character authorities; do not merely assume from database roles.
4. **Shared permission:** when `document:read` is granted, both layers pass; when missing, both block. If intentionally using two distinct conditions, document and test the **AND** outcome.
5. **Object policy:** even with `document:read`, different tenants or unrelated documents cannot be read.
6. **Request security:** if the app uses CSRF, test write operations with a valid CSRF token to avoid confusing CSRF `403`s with authority errors.
7. **Non-HTTP paths:** jobs/consumers/services must still enforce sensitive business invariants.
8. **Renames:** after refactoring permissions, verify no stale literals remain in config, annotations, token mappings, tests, or assignment data.

### 8.4. Small logic test example for comparison

This is an **illustrative test snippet**, working only when the project has the controller, service, mock data, Spring Security Test dependencies, and security config as described:

```java
@Test
@WithMockUser(authorities = "document:read")
void readerCanCallHttpReadFunction() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
           .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "document:edit")
void editOnlyCannotCallHttpReadFunction() throws Exception {
    mockMvc.perform(get("/api/documents/d42"))
           .andExpect(status().isForbidden());
}
```

The `200 OK` test here is only valid if `d42` data exists, the test user satisfies object policy, the controller returns `200`, and no other rule blocks it. Real tests must prepare fixtures and also include service-call tests to verify method security, rather than assuming "passing authority" always equals HTTP `200`.

For **unauthenticated** callers, an endpoint requiring login typically returns `401` in appropriate APIs or redirects to login in form-login apps. For authenticated callers lacking authority, it is usually `403`. Exact values depend on the project's authentication entry point and exception handling.

## 9. Safe design when two check layers exist

### 9.1. Two layers can complement each other, but must be explicit

Three common patterns:

| Design | HTTP | Method | Best fit when |
| --- | --- | --- | --- |
| **Same functional permission** | `document:read` | `document:read` | Want to lock the same capability at both boundaries |
| **Broader HTTP, stricter method** | `authenticated()` | `document:read` + object policy | Multiple business paths call one shared service; enforce at service |
| **HTTP by API group, method by specialized action** | `ROLE_SUPPORT` or gateway rule | `ticket:close` + policy | Two layers express two intentional complementary conditions |

A request passing through both must **satisfy all applied checks**. There is no default rule that "if HTTP allows, skip `@PreAuthorize`". Also avoid unintended contradictions, such as HTTP demanding a role that valid users do not receive while the method demands a different permission.

### 9.2. Do not mix authority naming with object authorization

The name `document:read` is only access to the function. Resource decisions can still require:

```text
ALLOW READ(document) =
    hasAuthority("document:read")
    AND sameTenant(authentication, document)
    AND (isOwner(authentication, document)
         OR isAssignedReviewer(authentication, document))
```

Creating authorities named `document:d42:read` for every record can make tokens huge and permissions hard to revoke. Usually use server-side relationships/scopes/policies, especially when object counts are large.

### 9.3. Default policies must be strict

In `SecurityFilterChain`, order matchers from specific to general and guard sensitive endpoints with concrete rules. A broad `/api/**` matcher with `permitAll()` placed early can keep later role-requiring matchers from ever running on already-matched requests.

For method security, review annotations on classes, methods/interfaces, and precedence rules in your framework version. Avoid assuming `@PreAuthorize` automatically puts every call through a proxy. When multiple layers are used, real route tests and service-boundary tests must serve as proof.

## 10. Workflow for fixing a project with inconsistent permission names

Suppose a codebase contains `ADMIN`, `ROLE_ADMIN`, `ROLE_DOCUMENT_EDITOR`, `document.read`, `document:read`, and `SCOPE_documents.read`.

**Step 1 — Inventory where permissions are matched.** Find `hasRole`, `hasAuthority`, `hasAnyRole`, `hasAnyAuthority`, `@PreAuthorize`, `@Secured`, `@RolesAllowed`, custom `AuthorizationManager`, role hierarchies, controllers/services, and where `Authentication` is created. Do not assume every annotation is active; e.g., `@Secured` requires enabling per specific usage.

**Step 2 — Read the authorities actually granted.** In dev/test environments, inspect `Authentication.getAuthorities()` in a controlled way. Never print access tokens, sensitive data, or private claims to logs. Actual Authentication data is the ultimate reference point for naming conventions.

**Step 3 — Establish a canonical catalog.** For instance, `ROLE_*` for roles and `document:read` for functional permissions; document sources and meanings of each permission; define conversion from scopes/roles to permissions. Pick one scheme the team can keep consistent.

**Step 4 — Pin mapping at the boundary.** Map roles/claims/memberships to authorities at authentication time or in an owned policy adapter. Avoid having each controller translate roles with its own formula.

**Step 5 — Align HTTP and methods.** Check "same permission meaning?" at every endpoint/service. Use constants, meaningful annotations, or static literal checks when helpful. Keep differing conditions only when they are **intentional complementary rules**.

**Step 6 — Test allow and deny paths.** For every permission, test at least exact authority, role only, scope only, no permission, wrong casing, cross-tenant resource, and each HTTP/service call path. Account for CSRF effects when testing write endpoints.

**Step 7 — Migrate in a controlled way.** If renaming strings already used by tokens/users/DB, plan migrations for permission assignments and active sessions. Never accidentally leave both old and new names accepted forever without a deadline/bound and proper audit.

**Step 8 — Maintain the contract long-term.** When adding actions like `document:export`, update authority producers, HTTP matchers, method guards, object policies, and tests in the same change. Review permission names as part of the security API, not arbitrary naming details.

## 11. Common errors and quick diagnosis

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| Login succeeds yet method returns `403` | `@PreAuthorize` requires an authority different from granted set | Inspect actual authorities and SpEL |
| HTTP passes, method fails | `hasRole('X')` vs `hasAuthority('x:read')` not equivalent | Standardize requirement; if two intentional conditions, grant both |
| Test with `roles="ADMIN"` passes, production JWT fails | Mock creates `ROLE_ADMIN` while converter creates `SCOPE_...` | Test real converter/login; align convention |
| Using `hasAuthority("ADMIN")` when user has `ROLE_ADMIN` | Missing prefix in exact string match | Use `hasRole('ADMIN')` or `hasAuthority('ROLE_ADMIN')` |
| `@PreAuthorize` does not block | Method security not enabled, bean not proxied, or self-invocation | Check `@EnableMethodSecurity` and actual call path |
| User with read permission sees others' documents | Checked only functional permission, missing resource policy | Enforce tenant/owner/ACL at service |
| Editing an endpoint opens another endpoint | Matcher too broad or wrong matcher order | Test all related routes and deny fallback |
| Switching to custom role prefix causes skewed behavior | Prefix config inconsistent across HTTP/method/tests | Check version-specific extension points, integration test |
| Renaming permission locks out existing users | Token/DB/cache still holds old name | Migrate producers, invalidate/refresh tokens-caches as needed |
| Failing to distinguish CSRF and permission errors | Write request rejected by CSRF filter before policy | Test CSRF in separate integration tests |

## 12. Self-check

**Q1.** A user has exact authority `ROLE_ADMIN`. What do `hasRole('ADMIN')` and `hasAuthority('ADMIN')` return under the default prefix?

**Answer:** `hasRole('ADMIN')` passes because it expects `ROLE_ADMIN`. `hasAuthority('ADMIN')` fails because it matches exact `ADMIN`, which differs from the granted string.

**Q2.** API uses `hasAuthority('document:read')`; method uses `hasRole('READER')`. Are these two ways of stating the same permission?

**Answer:** Not by default. They require `document:read` and `ROLE_READER`. They represent the same capability only if the application designed/granted both and tested it; otherwise, align on the same permission.

**Q3.** A verified access token has scope `documents.read`. Does `hasAuthority('document:read')` pass automatically?

**Answer:** No. In a JWT resource server under default conventions, the scope usually becomes `SCOPE_documents.read`. Requiring a different business permission needs an explicit, tested mapping.

**Q4.** The method already has `@PreAuthorize("hasAuthority('document:read')")`. Why can data still leak?

**Answer:** A functional permission does not prove access to a specific document. Object policy (tenant, owner, sharing, status...) must be checked at the right boundary; also the annotation must actually be enforced by Spring method security.

**Q5.** HTTP config uses `hasRole('EDITOR')`, method uses `hasAuthority('ROLE_EDITOR')`. Is this consistent?

**Answer:** Under the default `ROLE_` prefix config, both check `ROLE_EDITOR`. Still, prefer one clear convention and add tests if the prefix has been customized.

**Q6.** When aligning permission names between two layers, should we remove other checks to avoid `403`?

**Answer:** No. Fix only unintended mismatches. Complementary conditions such as tenant, owner, resource state, MFA, action-specific permissions, or CSRF must continue to be enforced per policy.

**Remember:** **One business permission must have one canonical name and one canonical meaning** from `Authentication` creation, through HTTP matchers and method security, to tests. `hasRole` has a prefix rule; `hasAuthority` matches exact strings; OAuth scopes are a separate namespace. Consistent naming is a necessary condition, while object-level authorization and enforcement at the right boundaries remain mandatory.

## References

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — `@WithMockUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html
