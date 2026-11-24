# Implementing a Custom UserDetailsService and Mapping Authorities from Domain Data

## 1. Practice Problem and Responsibility Boundaries

A Java e-commerce application has an `app_user` table, system-wide global roles (for example `USER`, `SUPPORT`), business permissions (for example `REPORT_READ`), and per-organization (tenant) roles/permissions. Users must log in with a username/password stored in the database, and then only access the features and records they are genuinely permitted to view.

**Goal:** implement an application-specific `UserDetailsService` to load accounts and permission sets from business data, delegate password verification to `DaoAuthenticationProvider`, map privileges into `GrantedAuthority` with proper semantics, and enforce **tenant/object-level** authorization right at the service layer. This is a **Capstone Practical Exercise** in the **Spring Security - authentication** module, not merely a tutorial for creating an in-memory user.

Distinguish four responsibilities:

1. **User lookup** — `UserDetailsService.loadUserByUsername(String)` finds the account in the data store, returning `UserDetails` with the password hash, flags, and authorities, or throws `UsernameNotFoundException`. It **does not authenticate the password itself**.
2. **Password authentication** — `DaoAuthenticationProvider` retrieves `UserDetails`, calls `PasswordEncoder.matches(raw, hash)`, and checks account status; it returns an `Authentication` once valid.
3. **Global authorization** — `SecurityFilterChain` and `@PreAuthorize` check the authority/role attached to `Authentication`; for example `ROLE_SUPPORT` or `PERM_REPORT_READ`.
4. **Tenant/object authorization** — business logic verifies that the current `userId` still holds an active membership in that tenant and has permission on the specific resource. **Do not** turn "admin of tenant A" into a global `ROLE_ADMIN`.

### Overall Architecture

~~~text
POST /login (username, password, CSRF token)
             |
             v
UsernamePasswordAuthenticationFilter
             |
             v
AuthenticationManager / ProviderManager
             |
             v
DaoAuthenticationProvider
       |                 |
       |                 +-- PasswordEncoder.matches(raw, storedHash)
       v
DomainUserDetailsService.loadUserByUsername(username)
       |
       +-- Normalize login consistent with signup
       +-- AccountDataPort / JDBC-JPA database adapter
       +-- AccountSnapshot (id, hash, enabled, locked)
       +-- Global roles and global permissions from DB
       +-- Map to ROLE_... / PERM_...
       |
       v
DomainPrincipal implements UserDetails
             |
        success / failure
             |
       SecurityContext for session
             |
       AuthorizationFilter / @PreAuthorize
             |
       TenantPermissionLookup(userId, tenantId, permission)
             |
       Business query constrained by tenant ID
~~~

Even if the provider returns an authenticated `Authentication`, that is still **not enough** to read orders belonging to any tenant. Functional permissions must be combined with **record-level** access checks against live data.

### Outcomes You Must Prove Yourself

- Logging in with the right password hash succeeds; logging in with a wrong password or nonexistent username is rejected without leaking account existence.
- Disabled/locked users cannot log in, even with the right password.
- `hasRole("SUPPORT")` matches `ROLE_SUPPORT`; `hasAuthority("PERM_REPORT_READ")` matches the exact authority string.
- Without a privilege in the DB, the user **does not** obtain that authority just because the frontend sends a claim/role.
- An admin of tenant A cannot view tenant B's data by swapping `tenantId` in the URL.
- When roles/memberships change, the system has a policy to refresh/reject **previously issued sessions or tokens**; do not assume every Principal updates automatically.
- Test the DAO/user service, provider, HTTP filters, and business authorization at their **respective layers**.

## 2. Understanding UserDetailsService Correctly in Spring Security

Spring Security's interface has one primary method:

~~~java
package org.springframework.security.core.userdetails;

public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
~~~

This is a **shortened signature for explanation**. `UserDetailsService` does not receive passwords, OTPs, request bodies, or `tenantId` from the browser. It does not replace `AuthenticationProvider`. During form login via the DAO provider, Spring Security receives a `UsernamePasswordAuthenticationToken` containing the raw password, loads `UserDetails` through the service, and checks it using the encoder.

The `UserDetails` properties must be implemented deliberately:

| Property / method | Value and Meaning |
| --- | --- |
| `getUsername()` | Canonical login or chosen identifier; stable, never arbitrarily based on a display email |
| `getPassword()` | Hashed/encoded password (e.g., `{bcrypt}...`), **never** plaintext |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` containing global roles/permissions per schema |
| `isEnabled()` | Is the user still allowed to sign in? |
| `isAccountNonLocked()` | `false` when the account is locked |
| `isAccountNonExpired()` | Is there an account expiration policy? |
| `isCredentialsNonExpired()` | Are current credentials still valid per policy? |

Per Spring Security 6.5 documentation, `DaoAuthenticationProvider` uses `UserDetailsService` and `PasswordEncoder`, and typically retains `UserDetails` as the resulting principal. If you want to attach a local user ID to the principal, you can create a custom `UserDetails` class. If you only need username and authorities, `org.springframework.security.core.userdetails.User` may suffice.

### Do Not Mix Authentication with Lookup

**Wrong:** inside `loadUserByUsername`, manually fetching the raw password from `SecurityContextHolder`, comparing it with the DB, and returning `UserDetails` if it matches. That breaks provider boundaries, complicates testing, and usually bypasses encoder, lockout, and audit/credential-erasure mechanisms.

**Right:** the service only fetches data and maps it to `UserDetails`. `DaoAuthenticationProvider` performs password verification; `AuthenticationFailureHandler`/entry point handles public errors, and the audit logger records internal reasons.

### Username Normalization and User Enumeration

Choose a consistent canonicalization rule across **registration, username changes, and login**. For example, if a product treats email as username: strip leading/trailing whitespace and lowercase with `Locale.ROOT`, storing `login_norm` with a unique constraint. However, Unicode/IDN rules, case sensitivity, and email aliases must be defined by the product; **never guess that two addresses are equivalent** and merge accounts.

When lookup finds nothing, throw `UsernameNotFoundException`. The default `DaoAuthenticationProvider` typically masks unknown-user errors with `BadCredentialsException`; you still need to check HTTP responses, response timing, rate limiting, and dummy password-hash comparisons if applicable. Never expose `username exists` or `account locked` on anonymous APIs in a way that enables user enumeration.

## 3. Database Structure: How Real Data Maps to GrantedAuthority

Abbreviated PostgreSQL example:

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    login_norm VARCHAR(254) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    security_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE global_user_role (
    user_id UUID NOT NULL REFERENCES app_user(id),
    role_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, role_code)
);

CREATE TABLE global_user_permission (
    user_id UUID NOT NULL REFERENCES app_user(id),
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, permission_code)
);

CREATE TABLE tenant_membership (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE tenant_member_permission (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (tenant_id, user_id, permission_code),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_membership (tenant_id, user_id)
);
~~~

This is a **learning** schema; it omits auditing, soft deletes, tenant FKs, role catalogs, permission catalogs, migrations, and tenant ownership rules. Production requires trusted role/permission catalogs, validation when granting privileges, least privilege, and approver auditing. Above all, **never accept role/permission codes directly from the login request body** to construct authorities.

### Two Privilege Levels

- **Global role**: `SUPPORT` is a system-wide role and maps to `ROLE_SUPPORT`; granted only through trusted administrative workflows, never from tenant membership.
- **Global permission**: `REPORT_READ` maps to `PERM_REPORT_READ`, matched via `hasAuthority("PERM_REPORT_READ")`.
- **Tenant permission**: Alice holds `INVOICE_READ` in tenant T1, but not in T2. This is a **(userId, tenantId, permission)** relationship that must be checked at request/service time, not turned into a global `PERM_INVOICE_READ` without scope enforcement.
- **Object ownership**: beyond membership, data queries must also enforce `invoice.tenantId == requestedTenantId` and owner/workspace policies to prevent IDOR.

Data example:

| user | global role | global permission | tenant | tenant permission |
| --- | --- | --- | --- | --- |
| Alice | `USER` | `REPORT_READ` | T1 | `INVOICE_READ` |
| Alice | `USER` | `REPORT_READ` | T2 | *(none)* |
| Bob | `SUPPORT` | *(none)* | T2 | `INVOICE_READ` |

For Alice, system-wide authorities contain only `ROLE_USER` and `PERM_REPORT_READ`. Alice **does not** get `ROLE_ADMIN` merely because she administers some tenant. To view a T1 invoice, she also needs membership in T1; changing the URL to T2 must be denied.

### Authority Naming Rules

`hasRole("SUPPORT")` checks `ROLE_SUPPORT` by default; **do not** pass `hasRole("ROLE_SUPPORT")` because the DSL already adds the prefix. `hasAuthority("PERM_REPORT_READ")` matches the literal string `PERM_REPORT_READ` without adding any prefix. Pick one convention and test it consistently; avoid mixing styles across different screens.

**Authority is not an automatic security boundary for row-level data.** Even when `ROLE_SUPPORT` grants access to support pages, the service must still restrict which records that person can view, potentially requiring auditing/just-in-time elevation for cross-tenant access.

## 4. Dependencies and Exercise Structure

With Spring Boot 3.x version-managed by its BOM, a minimal MVC/session authentication project looks like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

You do not need `spring-security-oauth2-resource-server` if you are only practicing **username/password with DaoAuthenticationProvider**; JWT/OIDC is a separate flow. Do not add `spring-boot-starter-webflux` and then use Servlet `HttpSecurity` if the actual app is WebFlux — reactive apps use `ReactiveUserDetailsService` and `SecurityWebFilterChain`.

Illustrative structure:

~~~text
src/main/java/example/security/
  AccountDataPort.java
  DomainPrincipal.java
  DomainUserDetailsService.java
  JdbcAccountDataAdapter.java
  DomainSecurityConfig.java
  TenantAccess.java
  TenantPermissionLookup.java
src/main/java/example/billing/
  InvoiceService.java
src/test/java/example/security/
  DomainUserDetailsServiceTest.java

src/main/resources/
  application.yml
  db/migration/V1__account_auth.sql
~~~

Files under the `example` namespace are package-name illustrations; a real deployment requires `@SpringBootApplication` plus datasource/migration configuration. The code snippets below **can compile when placed in the same package with the proper dependencies**, though they do not form a standalone runnable app without real endpoints and data. Section 9 provides a pure JDK 17 program that runs without Spring.

## 5. Implementing a Custom UserDetailsService with AccountDataPort

### 5.1. Data DTO and Account Reading Abstraction

Create `src/main/java/example/security/AccountDataPort.java`:

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public interface AccountDataPort {
    Optional<AccountSnapshot> findByCanonicalLogin(String login);

    record AccountSnapshot(
            UUID userId,
            String canonicalLogin,
            String encodedPassword,
            boolean enabled,
            boolean locked,
            Set<String> globalRoles,
            Set<String> globalPermissions) {
    }
}
~~~

The port only returns data needed to authenticate and build global authorities. `encodedPassword` must be a hash in a format accepted by the encoder; never raw passwords. Never load all tenant memberships into the principal to turn them into global authorities.

### 5.2. Custom Principal with a Stable User ID

Create `src/main/java/example/security/DomainPrincipal.java`:

~~~java
package example.security;

import java.io.Serial;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.userdetails.UserDetails;

public final class DomainPrincipal
        implements UserDetails, CredentialsContainer {

    @Serial
    private static final long serialVersionUID = 1L;

    private final UUID userId;
    private final String login;
    private String encodedPassword;
    private final boolean enabled;
    private final boolean nonLocked;
    private final List<GrantedAuthority> authorities;

    public DomainPrincipal(
            UUID userId,
            String login,
            String encodedPassword,
            boolean enabled,
            boolean nonLocked,
            Collection<? extends GrantedAuthority> authorities) {

        this.userId = Objects.requireNonNull(userId);
        this.login = Objects.requireNonNull(login);
        this.encodedPassword =
            Objects.requireNonNull(encodedPassword);
        this.enabled = enabled;
        this.nonLocked = nonLocked;
        this.authorities = List.copyOf(authorities);
    }

    public UUID userId() {
        return userId;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return encodedPassword;
    }

    @Override
    public String getUsername() {
        return login;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;  // Change if the product has account expiry.
    }

    @Override
    public boolean isAccountNonLocked() {
        return nonLocked;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;  // Change if the product has credential expiry.
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void eraseCredentials() {
        // ProviderManager normally erases credentials after successful
        // authentication; avoid keeping hashes in the session unnecessarily.
        this.encodedPassword = null;
    }

    @Override
    public String toString() {
        // Avoid logging encodedPassword, authorities, or PII.
        return "DomainPrincipal[userId=" + userId + "]";
    }
}
~~~

**Why not use a simple `record DomainPrincipal(..., encodedPassword)`?** A generated `record.toString()` can leak the password hash into logs. The class above explicitly hides fields and implements `CredentialsContainer.eraseCredentials()`. Do not log full `Authentication` objects, and do not keep hashes/authorities in the session beyond what is necessary.

**Caching note:** a principal with `eraseCredentials()` sets `encodedPassword` to null when ProviderManager erases credentials. Do not cache/share **this same instance** as `UserDetails` across multiple authentications; if you enable a custom `UserCache`, design cloning/separate caching so the password hash is not lost for subsequent logins. `NullUserCache` is typically the default for DAO. When needing to avoid storing hashes in sessions, you can separate the session principal from credential-bearing user details.

### 5.3. Translating Global Role/Permission Data into Authorities

Create `src/main/java/example/security/DomainUserDetailsService.java`:

~~~java
package example.security;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class DomainUserDetailsService
        implements UserDetailsService {

    private final AccountDataPort accounts;

    public DomainUserDetailsService(AccountDataPort accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String rawUsername)
            throws UsernameNotFoundException {

        String login = canonicalize(rawUsername);

        AccountDataPort.AccountSnapshot account =
            accounts.findByCanonicalLogin(login)
                .orElseThrow(() ->
                    new UsernameNotFoundException(
                        "Invalid username or password"));

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>();

        for (String role : account.globalRoles()) {
            authorities.add(new SimpleGrantedAuthority(
                "ROLE_" + validCode(role)));
        }
        for (String permission : account.globalPermissions()) {
            authorities.add(new SimpleGrantedAuthority(
                "PERM_" + validCode(permission)));
        }

        return new DomainPrincipal(
            account.userId(),
            account.canonicalLogin(),
            account.encodedPassword(),
            account.enabled(),
            !account.locked(),
            authorities);
    }

    private static String canonicalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new UsernameNotFoundException(
                "Invalid username or password");
        }

        String login = raw.strip().toLowerCase(Locale.ROOT);
        if (login.length() > 254) {
            throw new UsernameNotFoundException(
                "Invalid username or password");
        }
        return login;
    }

    private static String validCode(String value) {
        if (value == null
                || !value.matches("[A-Z][A-Z0-9_]{0,63}")) {
            // Invalid privilege data in DB -> fail closed,
            // never silently grant access on malformed codes.
            throw new IllegalStateException(
                "Invalid configured authority code");
        }
        return value;
    }
}
~~~

The sample code expects `AccountDataPort` to return two non-null sets of ACTIVE **global** roles/permissions filtered from a trusted data store. If your permission catalog allows dots or hyphens, adjust the `validCode` regex to match your approved vocabulary — **never** drop validation simply because the DB is "internal". Login length limits and canonicalization must stay consistent with signup input and the unique index.

**Never accept `AccountDataPort.findByCanonicalLogin` input from frontend role claims.** The sole source of privileges is the server-controlled store. If a request sends `role=ADMIN` or tampers with a `role` cookie, it must not be able to inject authorities into the service result.

### 5.4. Real DB Access: JdbcTemplate

Example adapter reading the three datasets at a relatively consistent point in time; create `src/main/java/example/security/JdbcAccountDataAdapter.java`:

~~~java
package example.security;

import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public final class JdbcAccountDataAdapter
        implements AccountDataPort {

    private final JdbcTemplate jdbc;

    public JdbcAccountDataAdapter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<AccountSnapshot> findByCanonicalLogin(
            String login) {

        List<AccountSnapshot> rows = jdbc.query(
            """
            SELECT id, login_norm, password_hash, enabled, locked
              FROM app_user
             WHERE login_norm = ?
            """,
            (rs, rowNum) -> {
                UUID userId =
                    UUID.fromString(rs.getString("id"));

                Set<String> roles = new HashSet<>(
                    jdbc.queryForList(
                        """
                        SELECT role_code FROM global_user_role
                         WHERE user_id = ?
                        """,
                        String.class, userId));

                Set<String> permissions = new HashSet<>(
                    jdbc.queryForList(
                        """
                        SELECT permission_code
                          FROM global_user_permission
                         WHERE user_id = ?
                        """,
                        String.class, userId));

                return new AccountSnapshot(
                    userId,
                    rs.getString("login_norm"),
                    rs.getString("password_hash"),
                    rs.getBoolean("enabled"),
                    rs.getBoolean("locked"),
                    Set.copyOf(roles),
                    Set.copyOf(permissions));
            },
            login);

        if (rows.size() > 1) {
            // The unique constraint should prevent this.
            throw new IllegalStateException(
                "Duplicate canonical logins");
        }
        return rows.stream().findFirst();
    }
}
~~~

**Important:** this example executes two queries inside `RowMapper` for readability. It works for the **single-account** case, but production style should separate querying the account from querying roles/permissions, loading privileges with an appropriate batch/join; using this pattern over a list of users creates an **N+1** problem. `@Transactional(readOnly=true)` does not automatically guarantee a consistent snapshot without a high isolation level: across multiple SQL statements, role state could change between queries depending on the RDBMS and isolation level; if policy requires strong consistency, use explicitly designed transaction isolation and query strategies.

Use `?` parameter binding to prevent SQL injection; never concatenate `username` into SQL strings. With PostgreSQL `UUID`, `UUID.fromString(rs.getString("id"))` assumes the driver returns a standard UUID string representation. Apply environment-appropriate migrations, indexes, and tenant isolation.

### 5.5. Do Not Over-Query Privileges

When loading UserDetails, you only need **global authorities** and the flags needed to decide login. If a user holds 2,000 tenant memberships, do not cram all of them into the Session Principal and assume that snapshot stays fresh. For tenant memberships, check permissions by `(userId, tenantId, action)` at the service/method boundary with dedicated caching/invalidation and clear policies.

## 6. PasswordEncoder and DaoAuthenticationProvider Performing Authentication

### 6.1. Configuring Spring Security Servlet 6.5.x

Create `src/main/java/example/security/DomainSecurityConfig.java`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class DomainSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Default encodes new passwords with an id prefix, usually {bcrypt}.
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationProvider domainAuthenticationProvider(
            DomainUserDetailsService users,
            PasswordEncoder passwords) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(passwords);
        return provider;
    }

    @Bean
    SecurityFilterChain appSecurityFilterChain(
            HttpSecurity http,
            AuthenticationProvider domainAuthenticationProvider)
            throws Exception {

        return http
            .authenticationProvider(domainAuthenticationProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error",
                                 "/public/**").permitAll()
                .requestMatchers("/support/**").hasRole("SUPPORT")
                .requestMatchers("/reports/**")
                    .hasAuthority("PERM_REPORT_READ")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Using `new DaoAuthenticationProvider(users)` is the supported constructor in Spring Security 6.5; the no-argument `DaoAuthenticationProvider()` constructor is deprecated. `setPasswordEncoder(...)` is the proper way to configure the encoder. Defining an `AuthenticationProvider` bean and registering it in the chain clarifies wiring intent; **if the app has multiple security chains/providers/AuthenticationManagers**, verify which provider actually handles requests and avoid accidentally creating duplicate providers.

**Security note:** do not use `csrf.disable()` with form login/session cookies just to make tests pass. POST `/login` requires CSRF under the default policy. For a dedicated JSON login API, implement proper filters/converters and failure handlers with matching Content-Type/HTTP status codes rather than treating the form login example as a complete JSON API.

### 6.2. Proper Hashing and Password Migration

Database passwords must be stored in an encoder-supported format, for example:

~~~text
{bcrypt}$2a$10$.....................................................
~~~

This string illustrates structure only and is **not a usable bcrypt hash**. Never store plaintext or raw `SHA-256(password)` without salt/work factor. With `DelegatingPasswordEncoder`, the `{id}` prefix selects the encoder for legacy hashes while encoding new hashes with the current default encoder. Never ship `{noop}` to production; `{noop}` may appear only in **controlled test fixtures**.

Proper flow:

~~~text
registration / password reset:
  raw password -> PasswordEncoder.encode() -> store hash

login:
  raw password in request
  -> DaoAuthenticationProvider
  -> UserDetailsService loads stored hash
  -> PasswordEncoder.matches(raw, storedHash)
  -> status checks + authenticated principal
~~~

Never grant administrator privileges simply because a user supplied a matching password hash. Authentication does not replace authorization.

### 6.3. Account Flags and Logging Out on Privilege Changes

`isEnabled()` and `isAccountNonLocked()` allow `DaoAuthenticationProvider` to block accounts on **new logins**. However, if an account was just locked or a role was just revoked, an `Authentication` already stored in `HttpSession` may continue holding **stale** authorities unless the app re-checks. Choose a strategy:

- Invalidate sessions via Spring Session/an indexed repository while blocking locked accounts from creating new sessions.
- Or store `securityVersion` when issuing a session and compare against the DB/Redis on sensitive requests; changing roles/password/lock status increments the version and forces re-auth.
- With already-issued JWT Access Tokens, offline verifiers do not automatically refresh role/lock status; use short TTLs, revocation/denylists, or status checks at every Resource Server per your risk budget.
- For tenant-scoped permissions, check live DB state at the service layer instead of caching all memberships on the principal; still account for cache TTL/consistency.
- Never delete a role in the DB and assume old requests are immediately blocked with 403 while that role remains cached in the session.

## 7. Business Authorization by Tenant, Preventing IDOR

A global `PERM_INVOICE_READ` privilege can be dangerous: a user who is an accountant in tenant A might succeed against `/tenants/B/invoices/123` if the service only checks `hasAuthority("PERM_INVOICE_READ")`. Actual authorization must check **(localUserId, tenantId, permission, resource scope)**.

### 7.1. Tenant Permission Lookup Port

Create `src/main/java/example/security/TenantPermissionLookup.java`:

~~~java
package example.security;

import java.util.UUID;

public interface TenantPermissionLookup {
    boolean hasActivePermission(
        UUID userId, UUID tenantId, String permission);
}
~~~

A PostgreSQL implementation using the tables from Section 3:

~~~java
package example.security;

import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcTenantPermissionLookup
        implements TenantPermissionLookup {

    private final JdbcTemplate jdbc;

    public JdbcTenantPermissionLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean hasActivePermission(
            UUID userId, UUID tenantId, String permission) {

        Boolean found = jdbc.queryForObject(
            """
            SELECT EXISTS (
                SELECT 1
                  FROM tenant_membership m
                  JOIN tenant_member_permission p
                    ON p.tenant_id = m.tenant_id
                   AND p.user_id = m.user_id
                 WHERE m.tenant_id = ?
                   AND m.user_id = ?
                   AND m.status = 'ACTIVE'
                   AND p.permission_code = ?
            )
            """,
            Boolean.class, tenantId, userId, permission);

        return Boolean.TRUE.equals(found);
    }
}
~~~

**Additional checks needed:** verify the account is not LOCKED/DISABLED per policy, the tenant is ACTIVE, grant history, owner/collaborator relationships, permission catalog, and DB unavailability. The SQL example fails closed as a boolean by returning false, but exceptions/timeouts will propagate; error handlers must distinguish outages from missing permissions for operations rather than silently returning "allow".

### 7.2. Service-Side Authorization Bean

Create `src/main/java/example/security/TenantAccess.java`:

~~~java
package example.security;

import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public final class TenantAccess {

    private final TenantPermissionLookup permissions;

    public TenantAccess(TenantPermissionLookup permissions) {
        this.permissions = permissions;
    }

    public boolean canReadInvoice(
            Authentication authentication, UUID tenantId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal()
                     instanceof DomainPrincipal principal)) {
            return false;
        }

        return permissions.hasActivePermission(
            principal.userId(), tenantId, "INVOICE_READ");
    }
}
~~~

Because `TenantAccess` extracts `userId` from the authenticated `DomainPrincipal`, a browser cannot claim Bob's privileges simply by sending `userId=bob`. However, this bean assumes `Authentication` holds a local `DomainPrincipal`; when integrating OIDC/JWT principals, perform a verified mapping to the local user ID **before** applying the rule rather than casting blindly.

### 7.3. Guard Both the Endpoint and the Query

In a service with a matching `InvoiceRepository`, an example **snippet** (not a standalone runnable file) is:

~~~java
@PreAuthorize(
    "@tenantAccess.canReadInvoice(authentication, #tenantId)")
public Invoice readInvoice(UUID tenantId, UUID invoiceId) {
    return invoices.findByIdAndTenantId(invoiceId, tenantId)
        .orElseThrow(NotFoundException::new);
}
~~~

This snippet requires the method to reside on a Spring-managed service bean alongside application-defined `Invoice`, `NotFoundException`, and repository types; add `@P("tenantId")` or compile with `-parameters` so Spring method security resolves `#tenantId`. `@EnableMethodSecurity` was already enabled in Section 6's config. **Never** rely solely on `@PreAuthorize("hasRole('USER')")` and then call `findById(invoiceId)` when invoices belong to different tenants.

If fine-grained permissions are needed per **invoice** (owner, project, sensitivity), queries/rules must factor in `invoiceId` and ownership relations, not just tenant membership. For cross-tenant documents, `findByIdAndTenantId` constrains data scope, though the service must still verify business permissions.

### 7.4. Object Authorization Must Not Live Permanently in the Principal

A user's role in tenant A may change while they remain logged in. If an authority like `TENANT_A_ADMIN` is baked into the session and never invalidated, stale permissions persist. For frequently changing tenant/order permissions, re-verify against the trusted source (and caches with policy-defined versioning/TTL/invalidation), and bound transactions tightly to avoid TOCTOU in financial operations.

**Time-of-check/time-of-use risk:** a user still holds membership when `canReadInvoice` executes, but is revoked before the service updates data. For sensitive writes, re-check/lock permissions inside the mutating transaction, or enforce versioned permissions and DB constraints. Never treat a single annotation as an atomic transaction-wide guard.

## 8. Component Testing: From DB Snapshot to UserDetails and DaoAuthenticationProvider

### 8.1. Unit Testing UserDetailsService Without a Spring Context

File `src/test/java/example/security/DomainUserDetailsServiceTest.java` with JUnit 5 (placed in the same package as Section 5 classes):

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DomainUserDetailsServiceTest {

    private static final UUID ALICE_ID =
        UUID.fromString("00000000-0000-0000-0000-000000000001");

    private static AccountDataPort fakePort() {
        return login -> {
            if (!"alice@example.test".equals(login)) {
                return Optional.empty();
            }
            return Optional.of(
                new AccountDataPort.AccountSnapshot(
                    ALICE_ID,
                    "alice@example.test",
                    "{noop}demo-password",
                    true,
                    false,
                    Set.of("USER", "SUPPORT"),
                    Set.of("REPORT_READ")));
        };
    }

    @Test
    void loadsCanonicalUserAndMapsAuthorities() {
        var service = new DomainUserDetailsService(fakePort());
        UserDetails user =
            service.loadUserByUsername(" ALICE@EXAMPLE.TEST ");

        assertEquals("alice@example.test", user.getUsername());
        assertTrue(user.isEnabled());
        assertTrue(user.isAccountNonLocked());

        var names = user.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .collect(java.util.stream.Collectors.toSet());

        assertEquals(
            Set.of("ROLE_USER", "ROLE_SUPPORT",
                   "PERM_REPORT_READ"),
            names);
    }

    @Test
    void missingUserDoesNotCreatePrincipal() {
        var service = new DomainUserDetailsService(fakePort());
        assertThrows(UsernameNotFoundException.class,
            () -> service.loadUserByUsername("unknown@example.test"));
    }

    @Test
    void lockedUserProducesNonLockedFalse() {
        AccountDataPort port = login -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                ALICE_ID, login, "{noop}demo-password",
                true, true,
                Set.of("USER"), Set.of()));

        var service = new DomainUserDetailsService(port);
        assertFalse(service.loadUserByUsername(
            "alice@example.test").isAccountNonLocked());
    }

    @Test
    void invalidPrivilegeCodeFailsClosed() {
        AccountDataPort port = login -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                ALICE_ID, login, "{noop}demo-password",
                true, false,
                Set.of("ROLE_ADMIN/unsafe"), Set.of()));

        var service = new DomainUserDetailsService(port);
        assertThrows(IllegalStateException.class,
            () -> service.loadUserByUsername("alice@example.test"));
    }
}
~~~

**Interpreting results accurately:** these tests prove the custom `UserDetailsService`'s mapping and account flags, **not** `PasswordEncoder` or HTTP login, because `fakePort` returns snapshots with fixture hashes. `{noop}` appears strictly in tests; never use it in production. Tests compile and run only when Section 5 classes share the package and test dependencies include JUnit 5 + Spring Security.

### 8.2. Lightweight Integration with DaoAuthenticationProvider

The following snippet can be placed in `DomainDaoProviderTest.java` in the same package; it uses a real encoder and hashes generated inside the test:

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DomainDaoProviderTest {

    private DaoAuthenticationProvider provider(
            boolean enabled, boolean locked) {

        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String encoded = encoder.encode("safe-demo-password");

        AccountDataPort port = username -> Optional.of(
            new AccountDataPort.AccountSnapshot(
                UUID.fromString(
                    "00000000-0000-0000-0000-000000000001"),
                username, encoded, enabled, locked,
                Set.of("USER"), Set.of("REPORT_READ")));

        var provider = new DaoAuthenticationProvider(
            new DomainUserDetailsService(port));
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Test
    void correctPasswordIsAuthenticated() {
        var result = provider(true, false).authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice@example.test", "safe-demo-password"));

        assertTrue(result.isAuthenticated());
        assertEquals("alice@example.test", result.getName());
    }

    @Test
    void wrongPasswordFails() {
        assertThrows(BadCredentialsException.class,
            () -> provider(true, false).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "wrong-password")));
    }

    @Test
    void disabledAccountFailsEvenWithCorrectPassword() {
        assertThrows(DisabledException.class,
            () -> provider(false, false).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "safe-demo-password")));
    }

    @Test
    void lockedAccountFailsEvenWithCorrectPassword() {
        assertThrows(LockedException.class,
            () -> provider(true, true).authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice@example.test", "safe-demo-password")));
    }
}
~~~

These tests invoke the provider **directly**, so they do not test `ProviderManager` erasure, SecurityContext persistence, CSRF, the filter chain, redirects, or error contracts. Do not hardcode HTTP status codes based on exception classes when the app uses form-login redirects. If you need to verify credentials are erased from the principal after successful login, instantiate a real `ProviderManager` with the provider and inspect the authentication returned through the manager; ProviderManager supports `eraseCredentialsAfterAuthentication` per configuration.

**Fixture limitation:** `provider(true,false)` returns a snapshot for any login name because this test only exercises password/status; the unknown-username case is tested separately in `DomainUserDetailsServiceTest`. In production, repositories always query the real canonical username backed by a unique index; never copy this `fakePort` into application code.

## 9. Standalone Java 17: Mapping Business Privileges and Tenant Isolation

The following example uses **pure JDK 17** with no Spring, DB, or test-framework dependencies. It illustrates independent domain rules: global roles/permissions map to authorities, whereas per-tenant privileges **are checked against `tenantId`**, never promoted to global roles.

Create `AuthorityMappingDemo.java`:

~~~java
import java.util.List;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public class AuthorityMappingDemo {

    record Membership(
            String tenantId,
            Set<String> permissions) {
    }

    record Account(
            String userId,
            Set<String> globalRoles,
            Set<String> globalPermissions,
            List<Membership> memberships) {
    }

    static SortedSet<String> globalAuthorities(Account account) {
        SortedSet<String> result = new TreeSet<>();

        for (String role : account.globalRoles()) {
            result.add("ROLE_" + role);
        }
        for (String permission : account.globalPermissions()) {
            result.add("PERM_" + permission);
        }
        return java.util.Collections.unmodifiableSortedSet(result);
    }

    static boolean canReadInvoice(
            Account account, String tenantId) {

        return account.memberships().stream().anyMatch(
            membership ->
                membership.tenantId().equals(tenantId)
                    && membership.permissions()
                        .contains("INVOICE_READ"));
    }

    public static void main(String[] args) {
        Account alice = new Account(
            "alice",
            Set.of("USER"),
            Set.of("REPORT_READ"),
            List.of(
                new Membership("tenant-A",
                    Set.of("INVOICE_READ")),
                new Membership("tenant-B",
                    Set.of("INVOICE_WRITE"))));

        SortedSet<String> authorities =
            globalAuthorities(alice);

        System.out.println("authorities=" + authorities);
        System.out.println("tenantARead="
            + canReadInvoice(alice, "tenant-A"));
        System.out.println("tenantBRead="
            + canReadInvoice(alice, "tenant-B"));
        System.out.println("globalAdmin="
            + authorities.contains("ROLE_ADMIN"));
    }
}
~~~

Compile/run:

~~~bash
javac AuthorityMappingDemo.java
java AuthorityMappingDemo
~~~

**Exact stdout** (using `TreeSet` so ordering is deterministic):

~~~text
authorities=[PERM_REPORT_READ, ROLE_USER]
tenantARead=true
tenantBRead=false
globalAdmin=false
~~~

Look at the two checks `tenantARead=true` and `tenantBRead=false`: Alice holds invoice read permission in A but only write permission in B. **Never interpret "has at least one tenant with INVOICE_READ" as "may read invoices across all tenants".** `globalAdmin=false` proves the user is not escalated to system-wide privileges.

**Limitations:** this example lacks a real authenticated principal, does not enforce an allowed permission vocabulary, and does not check ACTIVE membership, invoice ownership, revocation, or consistency. Sections 5–7 show how to integrate it with Spring Security and a trusted database.

## 10. HTTP and Object Authorization Testing: Where Unit Tests Fall Short

### 10.1. From Mock Principals to Real Logins

| Purpose | Test Level | Right Tool | What Remains **Unproven** |
| --- | --- | --- | --- |
| Role/permission mapping from snapshot | Unit `DomainUserDetailsServiceTest` | Fake AccountDataPort | Real DB queries, password validation |
| Password hash, disabled/locked | Provider test | `DaoAuthenticationProvider` + real encoder | Filter chain, CSRF, session |
| Route /support requires ROLE_SUPPORT | MockMvc test | `@WithMockUser` or `user(...)` | That custom UserDetailsService was invoked |
| POST /login with real password in test DB | Integration | MockMvc + SecurityFilterChain + JdbcAccountDataAdapter | External SSO/JWT, multi-node |
| Tenant ID protection | Service/HTTP integration | `@PreAuthorize` + scoped repository query | Coverage of all other endpoints |
| Privilege revoked while logged in | Session/token integration | Two requests, DB update, fresh authorization check | Guarantees without multi-node tests |
| Loading accounts from JDBC | Database integration | Testcontainers/Postgres or real test DB | Security of default filters |
| OAuth/JWT login sharing user ID | Separate integration | OIDC test IdP, JWT decoder | Password DAO path |

### 10.2. What Should MockMvc Form Login Tests Verify?

This is a **snippet placed inside a test class with `MockMvc mvc`, real datasource/fixtures, and a security filter chain**; it is not a standalone Java file:

~~~java
// alice@example.test prepared with a hash created by PasswordEncoder,
// global role USER and permission REPORT_READ.

// Valid login: status is typically a 302 redirect under formLogin().
mvc.perform(formLogin()
        .user("alice@example.test")
        .password("correct-password"))
   .andExpect(authenticated()
       .withUsername("alice@example.test"));

// Invalid login: must still fail without granting an authenticated session.
mvc.perform(formLogin()
        .user("alice@example.test")
        .password("wrong-password"))
   .andExpect(unauthenticated());
~~~

These methods belong to `spring-security-test` and require static imports for `formLogin` from `SecurityMockMvcRequestBuilders` and `authenticated`/`unauthenticated` from `SecurityMockMvcResultMatchers`, applying Spring Security Test integration to MockMvc. `formLogin()` simulates posting to `/login` with a valid CSRF token via the test helper. Assert specific redirects/responses if UX requires them, and ensure tests do not replace `UserDetailsService` with a mock bean. Never use `@WithMockUser` for tests meant to prove the JDBC password flow; that annotation **bypasses real login**.

### 10.3. IDOR / Cross-Tenant Tests

Test at least:

1. Alice has `INVOICE_READ` in tenant A; `GET /tenants/A/invoices/1` succeeds if the invoice actually belongs to A.
2. Alice swaps the URI to tenant B with the same invoice ID: must be denied or return not found without leaking data.
3. Alice has global `ROLE_USER` but no membership in B: `ROLE_USER` must not grant read access in B.
4. Bob is authorized in B but requests an invoice belonging to A: repository queries must constrain by tenant.
5. Alice's session retains stale rights after A membership is revoked: per policy, subsequent requests must be denied or adhere to a documented cache TTL; tests must reproduce this.
6. Locked user: new logins are rejected, and if immediate lockout is required, **existing sessions** must also be rejected via guards/session revocation.
7. DB permission lookup failure: exceptions must never turn into `allow=true`.
8. Direct service call bypassing HTTP controllers: method security/transactions still enforce policy; never place all checks solely in controllers.

**Avoid authority syntax mistakes:** `@WithMockUser(roles="ADMIN")` builds `ROLE_ADMIN`, whereas `@WithMockUser(authorities="PERM_REPORT_READ")` builds the literal authority. Never mix the two accidentally and cause tests to pass with overly broad privileges.

### 10.4. 401 vs. 403

- Unauthenticated request to a protected endpoint: APIs typically return 401; browser form login may redirect to `/login`.
- Authenticated user missing `PERM_REPORT_READ` or tenant permission: typically 403 (or 404 to limit resource disclosure per policy), **never** 401 causing clients to keep retrying login.
- Nonexistent username / wrong password: form login may redirect to `/login?error`; REST JSON login depends on the failure handler.
- Disabled/locked account: Spring's provider throws `DisabledException`/`LockedException` by status; public error messages should guard against user enumeration rather than exposing distinct codes on anonymous login.

## 11. Operational Risks After Deployment

### 11.1. Database Privilege Changes Do Not Automatically Update Every Session

An `Authentication` stored inside `HttpSession` typically captures authorities from login time. If an admin removes `REPORT_READ` in the database afterward, `loadUserByUsername` **is not guaranteed to re-run on requests using an existing session**. To meet privilege revocation SLAs:

- Include an account/authority version on the principal and server-side state store, checking it on critical requests;
- invalidate sessions via Spring Session or an appropriate session registry; across multiple nodes, use a shared store/consistency mechanism;
- check tenant permissions live (or via a TTL/invalidated cache) instead of trusting unbounded privilege snapshots;
- if APIs use self-contained JWTs, resource servers must check denylists/versions/status or accept an explicit residual TTL;
- when memberships/roles change, emit invalidation events and test with an already-logged-in browser B.

### 11.2. Performance and N+1

- Loading DB account + roles + permissions via a few queries for a single login is usually acceptable with proper indexes. Never fire 1 query per authority and introduce N+1.
- If a user belongs to thousands of tenants, never pack every membership into the principal/session, causing bloat, stale caches, and serialization issues.
- UserDetails caches must invalidate on lock, password change, and privilege updates; pay special attention to principals erased by `CredentialsContainer.eraseCredentials()`.
- Index `tenant_member_permission` on `(tenant_id, user_id, permission_code)` and membership status.
- Never use `SecurityContextHolder` or blocking JDBC on a WebFlux event-loop pipeline; WebFlux requires reactive authentication designs and R2DBC/offloading per policy.
- When the DB is unavailable, never silently return a fake user or default role; classify infrastructure failures, apply availability policies, and alert.

### 11.3. Auditing, Least Privilege, and Boundaries

- Who granted the role/permission? Record audit events with actor, target user, tenant, privilege code, approval source, timestamp, and reason.
- Who may modify `global_user_role`? Such endpoints need step-up auth and dedicated permissions, never trusting roles from input.
- Separate `ROLE_SUPPORT` from customer data access; support workflows may require just-in-time elevation, read-only views, masking, and case IDs.
- Never log passwords, encoded hashes, session cookies, OTPs, access/refresh tokens, or full `UserDetails` objects.
- When support looks up users, public error responses must not disclose account existence or locked status via distinct error codes.
- Test tenant mismatches, time-of-check/time-of-use races, and stale sessions after revocation—not just happy paths.

## 12. Common Mistakes and How to Avoid Them

1. **Calling `password.equals(rawPassword)` inside UserDetailsService**: wrong boundary. Provider + PasswordEncoder own verification.
2. **Storing plaintext passwords in the DB**: replace with password hashes encoded via an approved algorithm and migration strategy.
3. **Omitting the `{id}` prefix with DelegatingPasswordEncoder** yet expecting `matches` to detect legacy hashes automatically: migrate or configure properly.
4. **Confusing roles with authorities**: `hasRole("SUPPORT")` needs `ROLE_SUPPORT`; `hasAuthority("PERM_REPORT_READ")` needs the exact string.
5. **Mapping a tenant role to global `ROLE_ADMIN`**: causes cross-tenant privilege escalation.
6. **Letting the frontend send roles and copying them into Authentication**: allows any user to escalate their own privileges.
7. **Building UserDetails from non-canonical email/displayName**: duplicate accounts, broken lookups, and identity-mapping risks.
8. **Missing unique constraint on `login_norm`**: non-deterministic lookups or colliding accounts.
9. **Ignoring locked/disabled flags**: blocked users in the DB can still sign in.
10. **Abusing `@WithMockUser` for DB login tests**: tests bypass real UserDetailsService and PasswordEncoder.
11. **Checking only `ROLE_USER` and returning invoices via `findById`**: IDOR / cross-tenant exposure.
12. **Using `@PreAuthorize` while forgetting `@EnableMethodSecurity` or calling methods internally bypassing Spring proxies**: checks silently fail to run.
13. **Including password hashes in a principal record's `toString()`**: leaks hashes into logs/traces.
14. **Caching a principal whose password hash gets nulled by `eraseCredentials()`**: breaks subsequent logins from cache.
15. **Relying on login-time DB role snapshots forever**: revoked roles survive inside active sessions.
16. **Letting `ROLE_SUPPORT` view all tenants' data by default**: lacks least-privilege policies and object-level authorization.
17. **Changing roles without bumping versions / invalidating caches and sessions**: stale permissions remain active on other nodes.
18. **Using string-concatenated SQL for usernames**: SQL injection; use parameterized queries and constraints.
19. **Turning DB outages into anonymous users**: masks operational failures and can open unsafe fallback paths.
20. **Applying servlet SecurityFilterChain to a WebFlux app**: WebFlux requires ReactiveUserDetailsService/ReactiveAuthenticationManager.
21. **Using custom UserDetails to attach emails, tokens, and private info**: principals land in sessions/caches/logs, so minimize stored data.
22. **Failing to test empty permissions / unknown role codes**: mappers must fail closed rather than assigning default privileges.

## 13. Exercise Completion Checklist

- [ ] Designed `app_user` with a unique canonical login, password hash, enabled/locked flags, and stable account ID.
- [ ] Separated global roles/permissions from tenant memberships/permissions and resource ownership.
- [ ] `UserDetailsService.loadUserByUsername` only looks up/assembles `UserDetails` without comparing raw passwords.
- [ ] `DaoAuthenticationProvider` is wired with the right service and `PasswordEncoder`; no other provider silently bypasses it.
- [ ] Roles/permissions are loaded from a trusted DB, mapped with `ROLE_`/`PERM_` properly, and never taken from request bodies.
- [ ] Custom `DomainPrincipal` never logs password hashes, supports credential erasure, and carries the local user ID.
- [ ] Global pages/routes use `hasRole`/`hasAuthority`; tenant invoices use `@PreAuthorize` and tenant-scoped repository queries.
- [ ] Locked/disabled accounts and wrong passwords cannot log in; UI avoids user enumeration.
- [ ] DB privilege changes are backed by a session/token invalidation strategy or version/current-state checks.
- [ ] Unit tests cover canonicalization, role mapping, and status; provider tests use a real encoder.
- [ ] MockMvc integration uses `formLogin` properly with negative tests for 401/403/IDOR and CSRF.
- [ ] Grant/revoke auditing, least privilege, safe logging, and fail-closed behavior on security DB outages are in place.

**Summary:** `UserDetailsService` is the **bridge from domain data to UserDetails**; `DaoAuthenticationProvider` is where passwords are verified; `GrantedAuthority` should reflect only **trusted global privileges** and never replace point-of-use tenant/object authorization. A complete implementation covers source code, database constraints, scoped permissions, provider/HTTP tests, and privilege-refresh mechanisms when accounts or memberships change.

## 14. Official Documentation

- Spring Security 6.5 — `UserDetailsService`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html
- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 API — `DaoAuthenticationProvider` constructor and `setPasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — Authorize HTTP Requests, `hasRole` and `hasAuthority`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Password Storage and DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — Testing Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- OWASP — Authorization Cheat Sheet (deny-by-default, object checks): https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
