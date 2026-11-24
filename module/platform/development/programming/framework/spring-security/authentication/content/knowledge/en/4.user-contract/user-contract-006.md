# Mapping Business Permissions to GrantedAuthority

> **Context:** Spring Security – authentication, **User Contract** section. This lesson explains how to convert roles and permissions from a business model into `GrantedAuthority` so Spring Security can use them in `Authentication` and authorization. The focus is on where permission data originates, conversion rules, integration points with `UserDetailsService`, and verifying results. Java 17+ examples use Spring Boot Servlet with username/password. Principles of trusted sources, least privilege, and permission updates also apply when applications use JWT/OIDC, though integration differs.

## 1. The Problem: The Business System Manages Permissions, Spring Security Needs Authorities

An application managing reports and invoices might have three feature groups:

- Viewing reports with the business permission `report:read`.
- Approving invoices with `invoice:approve`.
- Viewing the admin page when holding the `ADMIN` role.

Business data may store roles as codes `ANALYST`, `APPROVER`, `ADMIN`; each role is configured with corresponding permissions. Meanwhile, Spring Security decides access via `Authentication.getAuthorities()` and rules like `hasAuthority("report:read")` or `hasRole("ADMIN")`.

Both sides need a **mapping contract**:

```text
Server-managed business permission source
    |
    +-- user_roles: USER, ANALYST
    +-- role_permissions: ANALYST -> report:read
    +-- user_permissions: certain directly granted permissions
    |
    v
Controlled account loading and mapping process
    |
    +-- ROLE_USER
    +-- ROLE_ANALYST
    +-- report:read
    |
    v
Collection<GrantedAuthority> on UserDetails
    |
    v
AuthenticationProvider verifies credentials successfully
    |
    v
Authentication.getAuthorities() for the request
    |
    v
AuthorizationManager / method security / business policy
```

**`GrantedAuthority` is not a permission table, does not authenticate users, and does not determine all access rights by itself.** It is a representation of granted permissions that Spring Security can match against policies. The final decision still depends on rules, resources, tenants, and context.

For instance, role `ANALYST` in the database does not automatically become `ROLE_ANALYST` in `Authentication` just because the names look alike. The application or provider must perform the right mapping. Likewise, if `ANALYST` is granted `report:read`, you must explicitly decide whether to expand that permission into its own authority or implement an equivalent role hierarchy/policy.

## 2. Distinguishing Role, Permission, Authority, and Object-Level Rights

| Concept | Typical Management Location | Example | What Is It Used For? |
| --- | --- | --- | --- |
| **Role** | User/RBAC system | `USER`, `ANALYST`, `ADMIN` | Grouping responsibilities or granting permissions to many users |
| **Permission** | Business policy | `report:read`, `invoice:approve` | Specific action capability |
| **GrantedAuthority** | `UserDetails` / `Authentication` after mapping | `ROLE_ANALYST`, `report:read` | Value Spring Security compares against authorization rules |
| **Scope** | Authorization server/token | `orders.read` | Scope granted to a token/client; may map to `SCOPE_orders.read` |
| **Object-level right** | Policy/service/DB query | "Allowed to view reports belonging to tenant A" | Checking a specific record/dataset |

`GrantedAuthority` is an interface with method `String getAuthority()`. The commonly used implementation is `SimpleGrantedAuthority`, holding a non-empty string, for example:

```java
GrantedAuthority authority = new SimpleGrantedAuthority("report:read");
System.out.println(authority.getAuthority()); // report:read
```

This is an **illustrative snippet**, requiring imports for `org.springframework.security.core.GrantedAuthority` and `org.springframework.security.core.authority.SimpleGrantedAuthority` in a project with Spring Security. It is not enough to run standalone.

### `hasAuthority` and `hasRole` Differ

With the default role prefix convention:

| Rule | `GrantedAuthority.getAuthority()` String the Rule Looks For |
| --- | --- |
| `hasAuthority("report:read")` | Exactly `report:read` |
| `hasAuthority("ROLE_ADMIN")` | Exactly `ROLE_ADMIN` |
| `hasRole("ADMIN")` | `ROLE_ADMIN` per default prefix |
| `hasAuthority("ADMIN")` | Exactly `ADMIN`, **distinct from** `ROLE_ADMIN` |

Spring Security allows customizing prefixes/authorization conventions; when doing so, check consistency across web and method security configurations. In this lesson we keep the default `ROLE_` to avoid ambiguity.

**A role does not automatically imply every permission:** `ROLE_ADMIN` does not by default satisfy `hasAuthority("report:read")`; to make that work, you must explicitly grant `report:read`, configure an appropriate role hierarchy, or use a custom policy. Never assume the word "ADMIN" automatically bypasses all authorization rules.

## 3. Designing a Clear Permission-Granting Contract

Suppose the business policy is:

| Internal Role | Resulting Authorities from Role |
| --- | --- |
| `USER` | `ROLE_USER` |
| `ANALYST` | `ROLE_ANALYST`, `report:read` |
| `APPROVER` | `ROLE_APPROVER`, `invoice:approve` |
| `ADMIN` | `ROLE_ADMIN` |

Besides permissions granted by roles, there may be individual permissions granted directly. The system must agree on rules:

1. **Granted roles** produce authorities shaped `ROLE_<CODE>`, e.g., `ANALYST` -> `ROLE_ANALYST`.
2. **Role permissions** expand into specific authorities, e.g., `report:read`.
3. **Direct permissions** are merged with permissions from roles.
4. **Duplicate permissions** are deduplicated, avoiding multiple `report:read` entries if granted via both a role and a direct grant.
5. **Unknown or contract-violating data** must never turn into unexpectedly powerful permissions. Validate roles/permissions and handle them "fail closed".
6. **Authority ordering** should be deterministic for logging or testing; permissions are conceptually a set, and display order carries no hierarchy meaning.
7. **Never use untrusted request fields as a permission source**, including requests carrying `role`, `permissions`, or `X-Role`.
8. **Never auto-add "ADMIN has all permissions"** unless internal policy explicitly defines it.

A conceptual formula:

\[
Authorities(user) =
RoleAuthorities(userRoles)
\;\cup\;
RolePermissions(userRoles)
\;\cup\;
DirectPermissions(user)
\]

The union here is a union of valid authority strings. It **does not automatically determine** permission limits by tenant, data object, account status, validity window, or business conditions; those factors still must be checked in the right places.

### "Deny" and Contextual Conditions

If the system has explicit denies, denies must have proper precedence in policy. Simply unioning allowed permissions into `GrantedAuthority` can **lose prohibition information**. When policies have conflicts/denies, compute effective permissions in a policy service/authorization manager that understands full conditions, or use a mapping contract that handles denies accurately. Never turn a deny into a `DENY_*` string expecting `hasAuthority` to automatically know how to reject it.

Similarly, the permission "read reports of one's own department" cannot be fully decided by `report:read` without department/report details. Object-level permission checks should happen after obtaining a trusted principal and the real resource.

## 4. Where Mapping Fits in the Username/Password Flow

With `DaoAuthenticationProvider`, the typical flow:

1. The filter receives client-submitted username/password; credentials are **not yet trusted**.
2. `AuthenticationManager` picks the matching provider.
3. `DaoAuthenticationProvider` uses `UserDetailsService.loadUserByUsername(...)` to fetch user data from a trusted source. The returned `UserDetails` contains the password hash, account status, and authorities collection.
4. `DaoAuthenticationProvider` checks account conditions and password via `PasswordEncoder`. If it fails, **no** successful `Authentication` is produced for the request.
5. If valid, the provider creates an authenticated `Authentication` containing the appropriate principal and authorities. Some Spring Security versions also add internal authorities for framework features like `FACTOR_PASSWORD`; do not arbitrarily assume the raw list contains only business authorities.
6. `SecurityContext` delivers the result to authorization/controllers/services per the request lifecycle and session/token mechanism.

**Subtle point:** Loading/mapping permissions **may happen before the password comparison step**, because it is part of loading `UserDetails`. However, those authorities **only become the current caller's permissions after authentication succeeds**. Never read permissions based on a self-claimed username and immediately use them in a business service.

`UserDetailsService` does not need to call `SecurityContextHolder.setContext(...)` or mark tokens authenticated itself. Leave that responsibility to the authentication mechanism.

### Why Separate the Domain Model from `UserDetails`?

A domain model can hold user IDs, emails, database relationships, multiple roles and permissions, audit timestamps, or other business policies. `UserDetails` only needs parts relevant to the authentication contract, such as username, password hash, account flags, and authorities.

A common design:

```text
DomainUser (persistence/domain)
   username, passwordHash, enabled, roleCodes, directPermissionCodes
                   |
                   v
AuthorityMapper (business rules -> valid authority names)
                   |
                   v
UserDetailsAdapter
   username, passwordHash, enabled, Collection<GrantedAuthority>
                   |
                   v
DaoAuthenticationProvider
                   |
                   v
Authentication + SecurityContext
```

Not every system needs a custom `UserDetails`; `User.withUsername(...)` suffices for many cases. Avoid putting raw JPA entities or raw passwords in the principal, and keep the business layer from depending directly on authentication entities.

## 5. Practical Mapping Algorithm

Inputs the mapper is allowed to process must be loaded and controlled by the server. In real apps this might be tables `user_roles`, `role_permissions`, `user_permissions`; in the example we use an in-memory repository to observe it.

Algorithm:

```text
Input: account.roles, account.directPermissions from trusted source
Output: valid List<GrantedAuthority>

names = an ordered set
FOR each roleCode:
    verify roleCode belongs to current role catalog
    names += "ROLE_" + roleCode
    names += all permissions granted by roleCode

FOR each directPermission:
    verify permission is valid per catalog
    names += directPermission

RETURN deduplicated names, converted to SimpleGrantedAuthority
```

When a role does not exist in the catalog or a permission is invalid, there are two **predefined** policy choices: fail login/flag a data error, or omit the unrecognized permission while still allowing limited login. For our illustrative flow, we **fail closed** with an explicit error so operators catch misconfigurations. Never turn an unknown role into `ADMIN`, never default to granting `report:read`, and never parse unverified strings.

### Be Careful with Permission Name Normalization

Automatic `trim()`, `toUpperCase()`, or swapping `-`/`:` can easily mask bad source data. For example:

- `roleCode = "ADMIN"` and `roleCode = "admin"` should be handled per an explicit contract rather than arbitrarily treated as identical.
- `report:read` differs from `REPORT:READ` when matched by `hasAuthority`.
- `ROLE_ADMIN` is an **already-prefixed authority**, whereas `ADMIN` is an **internal role code** in the illustrative mapping. If the mapper prefixes `ROLE_ADMIN`, it produces `ROLE_ROLE_ADMIN`, which is wrong.
- `SCOPE_orders.read` belongs to token scope mapping conventions; do not convert enterprise roles/permissions into `SCOPE_*` if the application does not follow that convention.

Name permissions according to business intent and maintain a single catalog/contract. For data entered by users in admin UIs, validate before saving and check the permissions of the **granting user**, rather than waiting until login to catch every error.

## 6. Runnable Java 17+ Spring Boot Example

The example creates three accounts:

| User | Source Roles | Source Direct Permissions | Resulting Business Authorities |
| --- | --- | --- | --- |
| `an` | `USER`, `ANALYST` | `report:read` (duplicates role permission) | `ROLE_USER`, `ROLE_ANALYST`, `report:read` |
| `binh` | `USER`, `APPROVER` | `report:read` | `ROLE_USER`, `ROLE_APPROVER`, `invoice:approve`, `report:read` |
| `chi` | `ADMIN` | none | `ROLE_ADMIN` |

An gets `report:read` from both the ANALYST role and a direct grant; the mapper must **deduplicate**. Binh gets `invoice:approve` from the APPROVER role and `report:read` directly. Chi has the ADMIN role, yet **does not have `report:read`/`invoice:approve`** because the demo policy does not define ADMIN as automatically receiving all permissions.

**Preparation:** a Spring Boot Servlet project with Spring Web and Spring Security, Java 17+, Maven or Gradle wrapper. The example illustrates Spring Security 7.x; the classes used here exist in the corresponding API. Create a file `src/main/java/com/example/authoritymap/AuthorityMappingApplication.java`:

```java
package com.example.authoritymap;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityMappingApplication.class, args);
    }
}

// Server-managed internal business data.
// Password is hash only; role codes do not have the ROLE_ prefix yet.
record DomainAccount(
        String username,
        String passwordHash,
        Set<String> roleCodes,
        Set<String> directPermissions,
        boolean enabled) {
}

// Demo repository. In production, replace with a trusted DB/identity service.
final class DomainAccountStore {
    private final Map<String, DomainAccount> accounts;

    DomainAccountStore(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");
        this.accounts = Map.of(
                "an", new DomainAccount(
                        "an", hash,
                        Set.of("USER", "ANALYST"),
                        Set.of("report:read"), true),
                "binh", new DomainAccount(
                        "binh", hash,
                        Set.of("USER", "APPROVER"),
                        Set.of("report:read"), true),
                "chi", new DomainAccount(
                        "chi", hash,
                        Set.of("ADMIN"),
                        Set.of(), true));
    }

    DomainAccount findByUsername(String username) {
        return accounts.get(username);
    }
}

// Authority contract defined and controlled by the application.
final class DomainAuthorityMapper {

    private static final Map<String, Set<String>> ROLE_PERMISSIONS =
            Map.of(
                    "USER", Set.of(),
                    "ANALYST", Set.of("report:read"),
                    "APPROVER", Set.of("invoice:approve"),
                    "ADMIN", Set.of());

    private static final Set<String> ALLOWED_PERMISSIONS =
            Set.of("report:read", "invoice:approve");

    List<GrantedAuthority> toAuthorities(DomainAccount user) {
        TreeSet<String> names = new TreeSet<>();

        for (String role : user.roleCodes()) {
            Set<String> rolePermissions = ROLE_PERMISSIONS.get(role);
            if (rolePermissions == null) {
                throw new IllegalStateException(
                        "Unknown role code in trusted source");
            }

            names.add("ROLE_" + role);
            names.addAll(rolePermissions);
        }

        for (String permission : user.directPermissions()) {
            if (!ALLOWED_PERMISSIONS.contains(permission)) {
                throw new IllegalStateException(
                        "Unknown permission in trusted source");
            }
            names.add(permission);
        }

        return names.stream()
                .map(name -> (GrantedAuthority)
                        new SimpleGrantedAuthority(name))
                .toList();
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DomainAccountStore accounts(PasswordEncoder encoder) {
        return new DomainAccountStore(encoder);
    }

    @Bean
    DomainAuthorityMapper authorityMapper() {
        return new DomainAuthorityMapper();
    }

    @Bean
    UserDetailsService users(
            DomainAccountStore accounts,
            DomainAuthorityMapper authorityMapper) {

        return username -> {
            DomainAccount account = accounts.findByUsername(username);
            if (account == null) {
                throw new UsernameNotFoundException("User not found");
            }

            List<GrantedAuthority> authorities =
                    authorityMapper.toAuthorities(account);

            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .authorities(authorities)
                    .disabled(!account.enabled())
                    .build();
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return http
                .authenticationProvider(provider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/me").authenticated()
                        .requestMatchers("/reports")
                            .hasAuthority("report:read")
                        .requestMatchers("/invoices/approval-check")
                            .hasAuthority("invoice:approve")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        // Select only authorities belonging to the business contract for demo output.
        // Some Spring Security versions may also grant FACTOR_PASSWORD.
        List<String> appAuthorities =
                authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .filter(name -> name != null
                                && (name.startsWith("ROLE_")
                                        || name.contains(":")))
                        .sorted()
                        .toList();
        return authentication.getName()
                + " -> " + String.join(",", appAuthorities);
    }

    @GetMapping("/reports")
    String reports() {
        return "reports visible";
    }

    @GetMapping("/invoices/approval-check")
    String approvalCheck() {
        // Endpoint only checks permission, does not actually approve an invoice.
        return "may approve";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin only";
    }
}
```

### Explaining Each Layer in the Example

**`DomainAccountStore`:** acts as the internal permission source. It returns `roleCodes` and `directPermissions` without reading permissions from request bodies. Role names do not carry `ROLE_` yet; username/password are data for authentication. Using the same BCrypt hash across three accounts is solely for brevity in the demo; real systems must maintain per-user credentials.

**`DomainAuthorityMapper`:** translates role codes to `ROLE_*` authorities, expands them into permissions from the catalog, merges direct permissions, and uses `TreeSet` to deduplicate and sort. Unknown roles or permissions are data errors that **must never grant extra rights**. In production, these errors must be observed and handled through the appropriate authentication mechanism without leaking source details in responses.

**`UserDetailsService`:** serves as the adapter between the domain source and `UserDetails`; returns username, hash, enabled status, and authorities. It **does not check passwords** and does not create authenticated tokens itself.

**`DaoAuthenticationProvider`:** uses `UserDetailsService` and `PasswordEncoder`; when credentials are valid and the account satisfies checks, the framework produces the authentication result. Authorities supplied by the mapper are treated as the caller's permissions **only after verification**.

**`SecurityFilterChain`:** enforces `report:read`, `invoice:approve`, and `ROLE_ADMIN` via independent rules. `anyRequest().denyAll()` ensures undeclared paths are not left open by accident. `/public/ping` is open to anonymous callers; `/me` requires authentication only.

**`DemoController.me`:** filters business authorities for stable example output. Some Spring Security 7 versions include internal authorities like `FACTOR_PASSWORD`; filtering here is strictly for **display**, not authorization logic, nor does it imply they do not exist on `Authentication`.

### Running the Demo

In the root directory of a Gradle project generated by Spring Initializr:

```bash
./gradlew bootRun
```

If the project uses Maven:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell use `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Do not compile the file above with a bare `javac` command without the Spring classpath; dependencies must be loaded properly by the build tool.

Once the application is running on localhost port 8080, open another terminal:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-pass http://localhost:8080/me
curl -s -u binh:demo-pass http://localhost:8080/me
curl -s -u chi:demo-pass http://localhost:8080/me
curl -s -u an:demo-pass http://localhost:8080/reports
curl -s -u binh:demo-pass http://localhost:8080/invoices/approval-check
curl -s -u chi:demo-pass http://localhost:8080/admin
```

On Windows PowerShell, if `curl` is an alias for another cmdlet, use `curl.exe`. The **response bodies** of the valid requests above, in order, are:

```text
pong
an -> ROLE_ANALYST,ROLE_USER,report:read
binh -> ROLE_APPROVER,ROLE_USER,invoice:approve,report:read
chi -> ROLE_ADMIN
reports visible
may approve
admin only
```

To test insufficient permissions or wrong credentials:

```bash
curl -i -u an:demo-pass http://localhost:8080/admin
curl -i -u an:demo-pass http://localhost:8080/invoices/approval-check
curl -i -u chi:demo-pass http://localhost:8080/reports
curl -i -u an:wrong http://localhost:8080/me
curl -i http://localhost:8080/reports
```

In this HTTP Basic demo, the first three commands receive **403 Forbidden** because the caller authenticated but lacks the required permission. The last two commands receive **401 Unauthorized** due to wrong or missing credentials. Error bodies/headers may vary by version/config, so do not rely on fixed error messages. HTTP Basic uses Base64, **not secret encryption**; real environments must use HTTPS and never demo passwords.

**Observation:** Chi's account is ADMIN so she enters `/admin`, yet does not automatically gain `report:read`. An's account has both role ANALYST and direct grant `report:read`, yet `getAuthorities()` holds **only one** `report:read` authority per the mapper's union. Binh gets `invoice:approve` from role APPROVER and `report:read` from a direct grant.

## 7. Bringing This Algorithm into a Real Database

A common relational schema:

```text
users(id, username, password_hash, enabled, tenant_id)
roles(id, code)
permissions(id, code)
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id)
```

Every table/column name is an illustrative design, not a mandatory Spring Security structure. You must define keys, uniqueness, validity, auditing, tenant scope, and grant/revoke management.

Process inside `UserDetailsService`:

1. Find the user by login identifier and appropriate tenant/identity store; do not trust a self-claimed tenant from the caller if unverified.
2. Read password hash and flags from the trusted source; avoid loading unnecessary profile data.
3. Load the user's roles and corresponding permissions; merge with direct grants per policy.
4. Check that roles/permissions are still active, unrevoked, within the right tenant, and meet grant conditions.
5. Canonicalize per catalog convention; return permitted `List<GrantedAuthority>`.
6. Let the provider verify credentials and then issue an authenticated `Authentication`.

With relational DBs, watch out for **N+1 queries** and relationships changing mid-load. You can load permissions via dedicated joins/queries or a domain service; avoid oversized Cartesian products and preserve snapshot consistency when business rules require it. Use unique constraints in grant tables to prevent duplicates, while keeping deduplication in the mapper's output.

### Why Not Map Database Roles Directly to `ROLE_*` and Drop Permissions?

Doing so can fit applications with simple role-based access control (RBAC). However, if policy requires `report:read`, granting only `ROLE_ANALYST` will **not satisfy** `hasAuthority("report:read")` unless the system configures another solution like a structured role hierarchy or an `AuthorizationManager` that understands domain mappings.

Pick a single place responsible for translating roles into permissions to avoid two competing mechanisms. If the mapper already expands permissions, do not add another layer that inconsistently assumes "ADMIN receives every permission".

### Role Prefix Does Not Belong in the Raw Data Source

In the `roles` table you can store code `ADMIN` so the domain stays independent of Spring. The adapter prepends `ROLE_` when building authorities. Do not store both `ADMIN` and `ROLE_ADMIN` in separate columns and let them drift apart. One durable role identifier and a tested conversion function are much easier to manage.

## 8. Mapping Permissions by Tenant and by Resource

A `GrantedAuthority` like `report:read` usually describes a **general capability**. It does not assert that the user may read reports belonging to any tenant or any owner.

Suppose An belongs to tenant A; even with `report:read`, An must not view tenant B's reports. A complete policy could be:

```text
Allow GET /reports/{reportId} if:
    Authentication is authenticated
    AND has authority "report:read"
    AND report.tenant_id falls within the caller's verified tenant scope
    AND policy permits reading the specific reportId
```

In services, the actor ID and tenant must come from a **trusted identity/authorization context**, not from a self-claimed `?userId=...` or `?tenantId=...`. Endpoints returning report lists should apply tenant filters right in the DB query; endpoints viewing a single report should check permission on that exact object.

Never generate hundreds of thousands of `report:123:read` authorities per record if policies can check object/tenant via a domain service. Doing so bloats `Authentication`, complicates caching/revocation, and invites bugs when data permissions change. For small-scoped data, a per-resource authority design can make sense, provided there are clear bounds and revocation strategies.

### If a User Has Both Allow and Deny Rights

Suppose a role grants `report:read` while the user is barred from reading a sensitive report. A list of `GrantedAuthority` shaped as an "allow" set does not natively understand a separate deny. You must apply **blocking policies** in the proper layer: data predicates, tenant isolation, explicit deny rules, or a dedicated authorization manager. Never assume "having the role always permits access" when business conditions exist.

## 9. JWT, OAuth2/OIDC, and Mapping Authorities from Tokens

With username/password, examples use `UserDetailsService`. With an OAuth2 Resource Server, the framework typically extracts principal/authorities from the verified token without calling `UserDetailsService` in the DAO flow shown above.

Example JWT with scopes:

```json
{
  "sub": "user-17",
  "scope": "reports.read invoices.approve"
}
```

This is only an **illustrative payload**, not a valid signed token. In default JWT configuration, scopes are converted into authorities typically prefixed with `SCOPE_`:

```text
SCOPE_reports.read
SCOPE_invoices.approve
```

If the application's API requires `hasAuthority("report:read")`, strings like `SCOPE_reports.read` do **not automatically** equal `report:read`. There are two clear design choices:

- Use rules matching the issued and verified scopes, e.g., `hasAuthority("SCOPE_reports.read")`, when token scopes directly represent API permissions.
- Use a controlled converter/mapping policy to translate trusted claims/scopes into business authorities, when the contract between issuer and application is explicitly defined.

**Never take `roles`, `permissions`, or `scope` from a client JSON body/header to build `SimpleGrantedAuthority` yourself.** With JWTs, verify signature/issuer/expiration and audience per configuration, as well as the claim contract. With opaque tokens, require a trusted introspection source; with OIDC login, distinguish ID tokens, access tokens, and internal permissions.

A claim `"roles": ["ADMIN"]` does not automatically become `ROLE_ADMIN` if the converter does not map it. Explicitly document the issuer, claim namespace, tenant, and principal type (user, service account) before granting permissions; never use email automatically as a cross-account merge key.

## 10. Permissions Changing After Login: The Snapshot and Revocation Problem

`Authentication.getAuthorities()` reflects a permission snapshot at authentication time or when the framework creates/restores the context. If an administrator revokes `invoice:approve` in the database, **you cannot assume** every already-issued session or JWT immediately loses that authority.

| Mechanism | Permission Source per Request | What to Check on Revocation |
| --- | --- | --- |
| HTTP Basic (demo) | Typically re-authenticates credentials, may reload `UserDetails` | Must check user cache and how permissions are loaded |
| Form login + session | May restore `Authentication` from session | Old sessions may retain old authority sets |
| Self-contained-claim JWT | Authorities mapped from verified token | Valid tokens retain claims until revoked/expired |
| Opaque access token | Typically relies on introspection results | Introspection source and how long caches remain valid |
| Custom policy lookup | Policy layer queries current data | Performance, failure behavior, consistency of policy source |

Policies may employ session invalidation, token TTL/revocation, versioned permissions, real-time authorization lookups for sensitive operations, or a combination of measures. Acceptable revocation latency must be an explicit design requirement, especially for financial/administrative permissions.

**Never rely on a stale authorities snapshot to authorize a sensitive transaction when policy demands current permissions.** In that case, re-check against a policy service with a trusted source and sensible failure behavior.

## 11. Common Mistakes When Translating Business Permissions

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Reading `role` from request and creating authority | Caller self-escalates privileges | Take permissions only from verified domain/issuer |
| Getting `UserDetails` and treating login as succeeded | Skips credentials | Let `AuthenticationProvider` verify and emit result |
| Storing `ADMIN` while rule uses `hasRole("ADMIN")` | Rule requires `ROLE_ADMIN` by default | Mapper prepends prefix properly, add tests |
| Mapper adds `ROLE_` to an already-prefixed `ROLE_ADMIN` | Produces `ROLE_ROLE_ADMIN` | Define source role codes without prefix |
| Permission `report.read` while rule requires `report:read` | String mismatch | Use a single permission-naming catalog |
| Auto-granting `ROLE_ADMIN` for unknown roles | Privilege escalation | Validate and fail closed |
| Granting only role, forgetting role-implied permissions | `hasAuthority` rule rejects despite business allowance | Design explicit role → permission mapping |
| Assuming ADMIN role grants all permissions | Bypasses granular policy | Grant specific permissions or configure explicit policy |
| Granting `report:read` and skipping tenant/owner checks | Risks cross-account/tenant data leaks | Combine with resource authorization |
| Caching `UserDetails` indefinitely | Revoked permissions persist | Refresh/TTL/revocation policy |
| Putting a JPA entity with lazy roles in principal | Loading, serialization, mutation errors | Immutable/minimal adapter |
| Logging full tokens, passwords, `Authentication` | Leaks secrets or PII | Log actor ID, decision type, correlation ID |
| Treating `SCOPE_*` as `ROLE_*` without mapping | Broken token/application contract | Proper converter and matching rules |
| Leaving `anyRequest().permitAll()` after missing matchers | Exposes sensitive routes | Prioritize specific rules, deny by default as required |

### Why Should Unknown Role Errors Be Caught Early?

If the database contains role `FINANCE_SUPER` that the mapper does not recognize, silently granting an arbitrary set of permissions can be overly broad. A **fail-closed** policy can throw an internal exception and block authentication/authorization until an administrator fixes the data; avoid leaking database contents in public responses. For systems where users must still log in if missing non-sensitive roles, you may skip unknown roles per an approved policy, yet **never** guess replacement permissions and always emit telemetry for bad data.

## 12. Testing the Mapping: Verify Both Data and HTTP Behavior

A solid test suite should have two layers:

**Test the mapper with known domain data** to isolate conversion bugs, deduplication, prefixes, and unknown roles. **Test Spring Security with authenticated requests** to prove permissions are actually enforced.

Suggested matrix:

| Case | Expected Result |
| --- | --- |
| USER + ANALYST | `ROLE_USER`, `ROLE_ANALYST`, `report:read` |
| APPROVER + direct report:read | Has both `invoice:approve` and `report:read` |
| Same permission from role and direct grant | Only one `report:read` authority |
| ADMIN without report-read permission | `/admin` allowed, `/reports` blocked |
| Unknown role from DB | Fail closed, no arbitrary permissions added |
| Permission not in catalog | Must not turn into an authority outside contract |
| Wrong username/password | No authenticated `Authentication` |
| Missing credentials | Protected endpoint requires authentication |
| Has `report:read` but different tenant | Tenant-scoped policy rejects |
| Permission revoked at source | Permission loses effect per defined refresh/revocation strategy |
| Token with only `SCOPE_orders.read` | Does not automatically satisfy `report:read` |
| User/service accounts use different principals | Do not grant user permissions to services without policy |

### Testing the Mapper in Java 17 (Code Snippet)

The snippet below uses `DomainAuthorityMapper`/`DomainAccount` from the complete example in section 6, and can be placed in a test method or separate `CommandLineRunner`:

```java
DomainAccount demo = new DomainAccount(
        "an",
        "unused-hash-for-mapper-test",
        Set.of("USER", "ANALYST"),
        Set.of("report:read"),
        true);

List<String> names = new DomainAuthorityMapper()
        .toAuthorities(demo)
        .stream()
        .map(GrantedAuthority::getAuthority)
        .toList();

System.out.println(names);
```

Exact output:

```text
[ROLE_ANALYST, ROLE_USER, report:read]
```

This is a **pure mapping test**: the password hash here is unused for authentication and must not be used to log in. To test real `DaoAuthenticationProvider` and HTTP rules, use the `curl` calls in section 6 or the corresponding integration test framework.

### Testing Input Data and Granting Permissions

Do not test only regular users. Test **role/permission assignment**: non-admin users cannot grant themselves `ADMIN`; role lists accepted by admin APIs must still be validated by the backend; grant/revoke mutations must have auditing, idempotency, and proper constraints. The mapper only processes already-granted data and does not replace protection around permission-granting operations.

## 13. Extended Scenarios: Role Hierarchy, Separation of Duties, and Explicit Deny

Some applications have role hierarchies: `MANAGER` implicitly includes `USER`'s capabilities. There are two main ways to represent this:

- **Expand on load:** the mapper grants inherited permissions as well. `Authentication` holds the final flattened permission set.
- **Declare hierarchy in authorization:** a role hierarchy/policy configuration transforms semantics when evaluating rules.

Both ways can achieve the same result for simple cases, yet pick one consistent source to avoid over- or under-granting permissions when the hierarchy changes. Never grant `ROLE_ADMIN` just because a user has many permissions; roles and permissions serve different purposes.

In financial workflows, sometimes one user must not both create and approve the same transaction (separation of duties). Simply granting `invoice:create` and `invoice:approve` and using `hasAuthority` may still fail to prevent a user from approving their own transaction. You must check **actor – resource – workflow relationships** in the service/policy, even when both authorities are present.

With explicit denies, you need a deny-overrides policy. A simple `Collection<GrantedAuthority>` usually only holds granted abilities; it does not interpret prohibition conditions on its own. If moving to a policy engine or custom `AuthorizationManager`, maintain a clear contract for identity, permission source, decision outcome, and failure behavior.

## 14. Pre-Production Checklist

1. Role, permission, and prefix catalogs are standardized, owned, and versioned.
2. Permission sources are trusted; self-granting APIs are protected and audited.
3. Role codes and permission codes are validated both before and during mapping.
4. `UserDetails` holds the exact authority set, no excess permissions, never based on client input.
5. Credentials and account status are verified by the provider; only successful authentication brings authorities into a request.
6. `hasAuthority`, `hasRole`, method security, and domain policies agree on permission names.
7. Multi-tenancy and object ownership are enforced beyond general authorities.
8. Session/token caching and revocation timelines are defined; a plan exists for stale state.
9. Permission-source errors are classified, monitored, and handled safely without failing open.
10. Test least privilege, unknown roles, duplicate grants, role prefixes, missing permissions, revocation, and disabled accounts.
11. Do not log unnecessary secrets/PII; do not output raw `Authentication` to clients.
12. Document explicitly which permissions ADMIN receives per policy; never assume all permissions by default.

## 15. Knowledge Self-Check

**Question 1.** The database stores role `ANALYST`, while the endpoint uses `hasAuthority("report:read")`. Is granting only `ROLE_ANALYST` enough?  
**Answer:** Not yet, unless the application has a special authorization policy understanding that role. With this lesson's mapping, `report:read` must also be loaded from the role.

**Question 2.** A user has `report:read` from both a role and a direct grant. Do we need two `SimpleGrantedAuthority("report:read")` objects?  
**Answer:** No. Collect by permission name and deduplicate before converting into authorities.

**Question 3.** The caller sends `X-Role: ADMIN`. May the server create `ROLE_ADMIN` because of that header?  
**Answer:** No. Client headers are untrusted data; roles must come from a verified source or a trusted proxy/issuer mechanism with clear security boundaries.

**Question 4.** Does a user holding `ROLE_ADMIN` automatically satisfy `hasAuthority("invoice:approve")`?  
**Answer:** No. You must grant `invoice:approve` or configure an equivalent explicit policy/hierarchy.

**Question 5.** Why is it safe for mapping to be called in `UserDetailsService` before password comparison?  
**Answer:** Because the permission data is only account information at that point; the provider must still verify credentials successfully before issuing an authenticated `Authentication` to the caller.

**Question 6.** A user has `report:read`, but the report belongs to another tenant. Should the report be returned?  
**Answer:** No, if policy forbids cross-tenant access. Permissions must be checked against the object/tenant using a trusted context.

**Question 7.** Does changing permissions in the DB immediately alter claims on an already-issued JWT?  
**Answer:** No. You need appropriate TTL, revocation, or current-permission lookup policies.

**Question 8.** Why are `SCOPE_orders.read` and `orders:read` not the same thing?  
**Answer:** They are two distinct authority strings with different grant contracts and creation paths; they are equivalent only if a converter/policy explicitly defines them as such.

## Conclusion

Mapping business permissions to `GrantedAuthority` bridges **the application's permission model** and **Spring Security's authorization mechanism**. Role/permission data must originate from a trusted source; the mapper converts it by clear rules, deduplicates, never expands beyond policy, and returns an authorities collection for `UserDetails` or the corresponding token mechanism. Only after authentication succeeds does Spring Security treat them as the caller's permissions in the request.

**An accurate authority set does not replace writing accurate rules and checking permissions on specific resources.** A complete design needs all three: accurate permission sources, consistent mapping, and context-aware enforcement.

### Official References

- [Spring Security — Authorization Architecture and GrantedAuthority](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — User.UserBuilder API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/resource-server/jwt.html)