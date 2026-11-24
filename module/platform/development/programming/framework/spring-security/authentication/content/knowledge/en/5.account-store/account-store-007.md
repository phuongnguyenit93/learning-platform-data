# Multi-Tenancy: Looking Up the Right Account Within Tenant Scope

In a multi-tenant system, the same `username` or email string can represent **different accounts**. For example, `sam` in organization `acme` and `sam` in organization `boreal` are two distinct subjects with their own passwords, statuses, authorities, and data. If the authentication machinery only queries `WHERE username = 'sam'`, the application can pick the wrong account, authenticate against the wrong identity source, apply the wrong permissions, or open a cross-tenant access path.

This lesson solves **"how to find the right account in the account store by tenant, and then bind the authenticated tenant to subsequent requests"** in Spring Security. The focus is not merely adding a `tenant_id` column to a table. You must distinguish which tenant is a *pre-authentication lookup hint*, which tenant is the *verified identity*, and whether every downstream query and authorization check preserves that boundary.

> Foundational rule: **Account lookup keys must include the proper tenant namespace; passwords must be verified against that exact selected account; after authentication, only use the tenant/account bound inside the trusted principal for authorization and resource queries.** Unverified tenant IDs, subdomains, headers, or claims do not grant permissions on their own.

This content belongs to the **Account Store** group of *Spring Security - authentication*. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and H2 to illustrate a username/password login design with a `tenant|username` qualified login key. OAuth2/OIDC/JWT strategies are clearly distinguished and not conflated with password flows.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish **tenant**, **membership**, **account ID**, **login identifier**, **principal**, **issuer**, and **authority**.
2. Explain why `findByUsername(username)` is unsafe when usernames are only unique *within each tenant*; design composite keys, indexes, unique constraints, and query parameters.
3. Separate three moments: **select candidate tenant → verify credential belonging to that account → bind authenticated tenant in the principal**.
4. Build a `UserDetailsService` that loads accounts by `(tenant_id, login_name)` and avoids relying on `ThreadLocal` or arbitrary headers as trusted context.
5. Construct a principal holding a stable account ID and tenant ID; use them to scope resources and prevent *cross-tenant IDOR/BOLA*.
6. Identify risks from cache keys, username normalization, role synchronization, multiple datasources, and JWT issuers.
7. Run a Spring Boot example with the same username `sam` in two tenants and test successful login, wrong-tenant login, cross-tenant resource access, and insufficient authority.

## 2. Concepts: One Login String Is Not Necessarily One Identity

| Term | Meaning | Example |
| --- | --- | --- |
| **Tenant** | Unit of identity/permission/data isolation per application contract: organization, workspace, or customer. | `acme`, `boreal`. |
| **Login identifier** | Value supplied by the user to look up an account in a namespace. | `sam`, work email. |
| **Account** | An identity record with status, credential verifier, and stable ID. | Acme's account `101`, Boreal's account `202`. |
| **Membership** | Relationship of a subject participating in a tenant with corresponding roles; one user may belong to multiple tenants. | Global user #7 is a member of Acme as `READER`, Boreal as `AUDITOR`. |
| **Qualified login key** | Login key explicitly combining namespace + login identifier, used in a specific authentication strategy. | `acme|sam`, `boreal|sam`. |
| **Authenticated principal** | Identity verified by the provider and attached to `Authentication`. | `accountId=101, tenantId=acme`. |
| **Authority/role** | Permission granted within a defined scope. | Acme's `orders:read`. |
| **Issuer (`iss`)** | Token issuer in OIDC/OAuth2; not synonymous with application tenant ID. | `https://idp.example.test/acme`. |

**Two data models to distinguish:**

- **Per-tenant account:** the same person may hold multiple independent accounts; the primary key may be a global `account_id`, with unique key `(tenant_id, login_name)`. Credentials and statuses can differ.
- **Global identity + per-tenant membership:** there is one global user identity, while roles and permissions vary by `tenant_id`. On login, the app may authenticate the global identity first, then verify membership to select the active tenant. Never pick a membership merely because the client sent a tenant ID.

No single model fits every system. **The task of "looking up the right account within tenant scope"** requires pinpointing the exact namespace where the account was created and is verified. If the database enforces globally unique usernames, the lookup SQL can be simpler; however, permissions and resources still require tenant scoping.

### Example of an Ambiguity Bug

```text
Tenant ACME                          Tenant BOREAL
  username: sam                       username: sam
  accountId: 101                      accountId: 202
  passwordHash: hash(A)               passwordHash: hash(B)
  enabled: true                       enabled: true
  roles: READER                       roles: AUDITOR

Wrong: SELECT * FROM accounts WHERE login_name = 'sam'
Right: SELECT * FROM accounts
       WHERE tenant_id = :tenant AND login_name = :login
```

With the wrong query, the outcome can depend on record/mapper order or throw a multi-row error. Both indicate that **the lookup model fails to identify a single identity**. Never "fix" it with `LIMIT 1`, because that only hides the bug and makes account selection arbitrary.

## 3. Three Tenant Trust Boundaries in Authentication

In a per-tenant username/password login model, distinguish:

1. **Candidate tenant:** value used to locate the verification domain. It may be sent alongside username via a form, URL/subdomain, or qualified login key. At this point, **the client is not yet authenticated**; the value is merely untrusted input subject to format validation, allowlisting, and valid routing.
2. **Authenticated tenant:** after selecting the exact account via the composite key and verifying password/status, the provider returns a principal containing `tenantId` and `accountId` from the trusted record. **This is server-verified data.**
3. **Effective tenant for authorization/data access:** on subsequent requests, services use the authenticated tenant and verified membership/authorities to constrain queries. If a user wants to switch organizations, verify membership/switch context via a trusted mechanism—never trust `X-Tenant: other`.

```text
Before authentication
    Client: tenantHint + loginName + password
                      |
                      v
    Validate syntax/namespace of tenantHint
    Select permitted verifier/user store
                      |
                      v
    Query: WHERE tenant_id=? AND login_name=?
                      |
                      v
    AccountRecord from DB + passwordHash + enabled
                      |
                      v
    PasswordEncoder.matches(password, passwordHash)
                      |
                 (success?)
                 /         \
               No           Yes
               |             |
          Generic 401        v
                      TenantPrincipal:
                       tenantId from DB
                       accountId from DB
                       granted authorities
                             |
                             v
                       SecurityContext
                             |
                             v
                  API/service reads tenant from
                  principal, not from header
                             |
                             v
                  WHERE tenant_id=? AND ...
```

**A tenant hint may be chosen by the client, but must never be treated as proof of belonging to that tenant.** Someone can try both `acme|sam` and `boreal|sam`. The system must verify the **password of the exact account for the selected tenant**, never accepting `acme|sam`'s password and switching the principal to `boreal|sam`.

### 3.1 Common Tenant Sources and Trust Levels

| Source | What can it be used for? | What is it not enough for? |
| --- | --- | --- |
| Subdomain `acme.example.test` | Identifying a candidate tenant and branding/routing if domains are strictly controlled. | Proving the user is a member of Acme. |
| Path `/t/acme/login` | Receiving the candidate tenant before login. | Granting Acme permissions after login without checking account/membership. |
| Form field `tenantId=acme` | Selecting an account within a namespace, with validation. | Deciding the principal's tenant or authorities on its own. |
| Header `X-Tenant: acme` | Tenant selection hint for a trusted client, subject to verification. | Acting as an authority source for arbitrary Internet requests. |
| Authenticated `Authentication` | Authoritative source of `tenantId`, `accountId`, and authorities in the application layer. | Allowing object-level authorization checks to be skipped. |
| Verified JWT `iss`/tenant claim | Indicating issuer/tenant under a trusted contract with signature/audience validation. | Trusting any unverified self-declared `iss`/`tenant` in a payload. |

Behind a proxy, `Host`/`X-Forwarded-Host` can only be trusted routing input if ingress normalizes and validates the path; never let an attacker spoof forwarded headers to hijack tenant selection. If using a tenant hint to route across multiple IdPs, **only select issuers from a trusted registry/allowlist**, never fetching metadata from arbitrary client-supplied URLs.

## 4. Designing Account Keys and Database Constraints

### 4.1 Primary and Unique Keys Should Serve Different Questions

A clean schema:

```sql
CREATE TABLE tenant_accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    login_name VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,

    CONSTRAINT uq_tenant_login UNIQUE (tenant_id, login_name),
    CONSTRAINT uq_tenant_account UNIQUE (tenant_id, account_id)
);

CREATE TABLE account_authorities (
    tenant_id VARCHAR(32) NOT NULL,
    account_id BIGINT NOT NULL,
    authority VARCHAR(96) NOT NULL,

    CONSTRAINT pk_tenant_authority
        PRIMARY KEY (tenant_id, account_id, authority),
    CONSTRAINT fk_tenant_authority
        FOREIGN KEY (tenant_id, account_id)
        REFERENCES tenant_accounts(tenant_id, account_id)
);

CREATE TABLE tenant_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_account_id BIGINT NOT NULL,
    title VARCHAR(160) NOT NULL,

    CONSTRAINT fk_tenant_order_owner
        FOREIGN KEY (tenant_id, owner_account_id)
        REFERENCES tenant_accounts(tenant_id, account_id)
);
```

This example uses a **system-wide unique** `account_id`. If IDs are only unique per tenant, adjust the primary key—for example `PRIMARY KEY(tenant_id, account_id)`—and update every FK to use the matching key. Never assume all numeric IDs are global.

**Purpose of each constraint:**

- `UNIQUE(tenant_id, login_name)` allows `sam` to exist in two tenants while forbidding duplicates within the same tenant. This is guaranteed by the database even under concurrent account creation requests.
- `UNIQUE(tenant_id, account_id)` enables composite FKs that protect tenant/account consistency, preventing inserting an authority or order whose `tenant_id` differs from the owner's tenant.
- `account_authorities` scopes permissions within the **tenant namespace**, rather than storing bare `username` values that collide across organizations.
- `tenant_orders` carries both `tenant_id` and `owner_account_id`, letting queries verify tenant and owner simultaneously; unique/FK constraints guard data invariants.
- `enabled` is a basic account flag. Timed locks, MFA, account expiry, and membership status may require separate columns and checks; they do not appear automatically just by using `UserDetails`.

### 4.2 An Account Lookup SQL Query Must Include Tenant

```sql
-- Right: prepared statement with both parameters
SELECT account_id, tenant_id, login_name, password_hash, enabled
FROM tenant_accounts
WHERE tenant_id = ? AND login_name = ?;
```

Both `?` placeholders must be JDBC-bound using the **validated candidate tenant** and **login identifier**. Never concatenate input directly into SQL. Having `WHERE tenant_id = ?` is the critical data boundary—do not rely only on checking tenant in the controller after loading the wrong account.

Similarly, fetch authorities by account ID **and tenant ID**:

```sql
SELECT authority
FROM account_authorities
WHERE tenant_id = ? AND account_id = ?
ORDER BY authority;
```

If an implementation only filters `WHERE account_id=?` and IDs are not globally unique or records are mis-mapped, permissions can bleed across accounts. Both parameters must come from **the account just queried and verified**.

### 4.3 Indexes, Collation, and Canonicalization

A unique constraint alone does not fix all username bugs:

- Should `sam` and `Sam` be treated as the same login? That depends on policy and DB collation; define one canonicalization rule and apply it consistently across registration and login.
- Emails can change; if using email as the login key, keep the account ID immutable. Never use a display email as the primary key across business relations.
- Unicode normalization, whitespace, and lookalike characters are easy to abuse; define allowed characters and normalization rules explicitly before lookup and at account creation. Never lowercase case-sensitive identifiers automatically if policy forbids it.
- In systems with many tenants and varying naming rules, use a registered stable tenant ID rather than a free-form company name as an internal key.
- Index `(tenant_id, login_name)` for login lookups; permission and data indexes should also include `tenant_id` according to actual query patterns.

**Never use `SELECT ... WHERE login_name=? LIMIT 1`**, and never fall back to `tenant_id IS NULL` to "try a shared user" unless there is an explicit, thoroughly tested design boundary. A shared-account fallback can easily become a tenant bypass.

## 5. Passing Tenant into UserDetailsService: Which Strategy Fits?

Standard `UserDetailsService` only defines:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

It **does not accept a separate `tenantId` parameter**. Therefore, if login keys are not globally unique, you need an explicit way to pass or route tenant context before the loader queries. Common strategies:

| Strategy | Mechanism | What to watch out for |
| --- | --- | --- |
| **Qualified login key** | Username passed to loader is `tenant|username`; loader parses, validates, then queries `(tenant, username)`. | Easy to use with `DaoAuthenticationProvider`, but define a safe delimiter/canonicalization and never treat pre-login strings as an authenticated principal. |
| **Custom authentication token + provider** | Filter builds `TenantUsernamePasswordAuthenticationToken` carrying candidate tenant, username, and credential; provider loads account by composite key. | Verify credentials/status properly and return a trusted principal; wire filters, handlers, and context lifecycle properly. |
| **AuthenticationManagerResolver** | Selects manager/provider per permitted tenant/issuer; each manager uses its own account store. | Selection source needs an allowlist/trust model; avoid open redirects, SSRF, or dynamic manager creation from arbitrary issuers. |
| **Global identity + membership** | Authenticate global identity, then check membership and select active tenant via server-side source. | Authorities must be scoped by membership; tenant switching must verify membership; users don't necessarily supply tenant during password login. |
| **SAML/OIDC identity federation** | Accept token/assertion from a trusted IdP and map subject/issuer to an account/membership in the tenant. | Verify token/assertion, issuer, and audience; never trust only a colliding `email` claim. |

This hands-on lesson chooses a **qualified login key `tenant|username`** because it works with the standard username/password provider without rewriting authentication filters. This is **one pattern with a clear contract**, not a rule that every multi-tenant system must use `|`.

### 5.1 Qualified Key Formatting Rules

- Tenant ID in demo: regex `[a-z0-9-]{1,32}`; login name: `[a-z0-9._-]{1,64}`. The `|` character is excluded from both sets so parsing is unambiguous.
- `acme|sam` splits into exactly **two parts**; reject `acme|sam|other` or empty parts.
- In production, never identify a tenant by taking a substring "up to the first dot" in an email or domain; enforce explicit registration and domain verification rules.
- Return a generic authentication error when the login key is malformed or the user does not exist, limiting account enumeration; write safe audit logs per policy.
- If other services need tenant/account info, pass a **structured principal** (`tenantId`, `accountId`) instead of forcing every service to re-parse a delimited string.

**Simple walkthrough:** Input `boreal|sam` → query `tenant_id='boreal' AND login_name='sam'` → if the password matches Boreal's account, the principal carries `tenantId='boreal', accountId=202`. When a request asks for `/api/orders/1001` (an Acme order), the service queries with `tenantId='boreal'` and **does not see** Acme's order.

## 6. Spring Boot Example: Two Tenants Sharing a Username Without Mixing Accounts

The demo application uses **Java 17+ / Spring Boot 3.3.13 / Spring Security 6.x**, in-memory H2, `JdbcTemplate`, `UserDetailsService`, and HTTP Basic. Two accounts:

| Tenant | Local username | Account ID | Demo password | Authorities |
| --- | --- | --- | --- | --- |
| `acme` | `sam` | `101` | `acme-password` | `orders:read` |
| `boreal` | `sam` | `202` | `boreal-password` | `orders:read`, `reports:read` |

Both accounts share **the same login name `sam` with different passwords and permission scopes**. When sending HTTP Basic, the full username is `acme|sam` or `boreal|sam`. The loader checks the composite key and returns a `TenantPrincipal` (a subclass of standard `User`) holding the DB-verified tenant and account.

### 6.1 Project Structure

```text
tenant-lookup-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/TenantLookupApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

File `settings.gradle`:

```groovy
rootProject.name = 'tenant-lookup-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Versions are pinned for reproducibility in this learning example, **not as a recommendation to use an end-of-support branch for new production systems**. In real projects, choose a currently supported Spring Boot/Spring Security branch and verify compatibility against official docs.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:tenantlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.sql.init.continue-on-error=false
```

H2 here runs in-process solely for learning and disappears when the app stops; DB user `sa` with an empty password is **only for a local demo environment**. Never deploy this configuration to production or expose a public H2 console.

File `src/main/resources/schema.sql` is the full DDL from section 4.1, keeping all three tables and their constraints intact. If porting to another database, adjust dialect/migrations accordingly. In particular, never remove `UNIQUE (tenant_id, login_name)` or the tenant/account FK just to make running easier.

### 6.2 Complete Java Code

File `src/main/java/demo/TenantLookupApplication.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TenantLookupApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantLookupApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    private record AccountRecord(
            long accountId,
            String tenantId,
            String loginName,
            String passwordHash,
            boolean enabled) {
    }

    @Bean
    UserDetailsService userDetailsService(JdbcTemplate jdbc) {
        return qualifiedLogin -> {
            // Only parse candidate tenant; do not treat request as authenticated yet.
            String[] parts = qualifiedLogin.split("\\|", -1);
            if (parts.length != 2
                    || !parts[0].matches("[a-z0-9-]{1,32}")
                    || !parts[1].matches("[a-z0-9._-]{1,64}")) {
                throw new UsernameNotFoundException("Invalid login");
            }

            AccountRecord account;
            try {
                account = jdbc.queryForObject("""
                        SELECT account_id, tenant_id, login_name,
                               password_hash, enabled
                        FROM tenant_accounts
                        WHERE tenant_id = ? AND login_name = ?
                        """,
                        (rs, rowNum) -> new AccountRecord(
                                rs.getLong("account_id"),
                                rs.getString("tenant_id"),
                                rs.getString("login_name"),
                                rs.getString("password_hash"),
                                rs.getBoolean("enabled")),
                        parts[0], parts[1]);
            } catch (EmptyResultDataAccessException ex) {
                throw new UsernameNotFoundException("Invalid login", ex);
            }

            // Scope authorities by tenant + account returned by the DB.
            List<GrantedAuthority> authorities = jdbc.query("""
                    SELECT authority
                    FROM account_authorities
                    WHERE tenant_id = ? AND account_id = ?
                    ORDER BY authority
                    """,
                    (rs, rowNum) -> new SimpleGrantedAuthority(
                            rs.getString("authority")),
                    account.tenantId(), account.accountId());

            if (authorities.isEmpty()) {
                throw new UsernameNotFoundException("No assigned authorities");
            }

            // Only the DB account determines tenant, accountId, and authorities.
            return new TenantPrincipal(
                    qualifiedLogin,
                    account.passwordHash(),
                    account.enabled(),
                    authorities,
                    account.accountId(),
                    account.tenantId(),
                    account.loginName());
        };
    }

    static final class TenantPrincipal extends User {
        private static final long serialVersionUID = 1L;

        private final long accountId;
        private final String tenantId;
        private final String localUsername;

        TenantPrincipal(
                String qualifiedUsername,
                String encodedPassword,
                boolean enabled,
                Collection<? extends GrantedAuthority> authorities,
                long accountId,
                String tenantId,
                String localUsername) {
            super(qualifiedUsername, encodedPassword,
                    enabled, true, true, true, authorities);
            this.accountId = accountId;
            this.tenantId = tenantId;
            this.localUsername = localUsername;
        }

        public long getAccountId() {
            return accountId;
        }

        public String getTenantId() {
            return tenantId;
        }

        public String getLocalUsername() {
            return localUsername;
        }
    }

    @Bean
    ApplicationRunner seedDemo(
            JdbcTemplate jdbc,
            PasswordEncoder encoder) {

        return args -> {
            jdbc.update("""
                    INSERT INTO tenant_accounts
                    (account_id, tenant_id, login_name, password_hash, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    101L, "acme", "sam",
                    encoder.encode("acme-password"), true);

            jdbc.update("""
                    INSERT INTO tenant_accounts
                    (account_id, tenant_id, login_name, password_hash, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    202L, "boreal", "sam",
                    encoder.encode("boreal-password"), true);

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "acme", 101L, "orders:read");

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "boreal", 202L, "orders:read");

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "boreal", 202L, "reports:read");

            jdbc.update("""
                    INSERT INTO tenant_orders
                    (order_id, tenant_id, owner_account_id, title)
                    VALUES (?, ?, ?, ?)
                    """, 1001L, "acme", 101L, "acme-order");

            jdbc.update("""
                    INSERT INTO tenant_orders
                    (order_id, tenant_id, owner_account_id, title)
                    VALUES (?, ?, ?, ?)
                    """, 2001L, "boreal", 202L, "boreal-order");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/*")
                    .hasAuthority("orders:read")
                .requestMatchers("/api/reports")
                    .hasAuthority("reports:read")
                .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class TenantDemoController {

    private final JdbcTemplate jdbc;

    TenantDemoController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal) {

        return Map.of(
                "tenantId", principal.getTenantId(),
                "accountId", principal.getAccountId(),
                "username", principal.getLocalUsername(),
                "authorities", principal.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/orders/{orderId}")
    ResponseEntity<String> order(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal,
            @PathVariable long orderId) {

        List<String> titles = jdbc.query("""
                SELECT title
                FROM tenant_orders
                WHERE order_id = ?
                  AND tenant_id = ?
                  AND owner_account_id = ?
                """,
                (rs, rowNum) -> rs.getString("title"),
                orderId,
                principal.getTenantId(),
                principal.getAccountId());

        if (titles.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(titles.get(0));
    }

    @GetMapping("/api/reports")
    String reports(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal) {

        return "reports-for-" + principal.getTenantId();
    }
}
```

Security highlights in the code:

- `UserDetailsService` parses the candidate from the qualified login, validates the format, and queries `WHERE tenant_id = ? AND login_name = ?`; there is no global user fallback.
- The returned DB record supplies the authoritative `tenant_id`/`account_id`. The principal keeps **IDs from the DB**, never using client-declared values to query resources.
- `PasswordEncoder` generates hashes for each account during seeding. `DaoAuthenticationProvider` verifies the password of **the exact account queried for that tenant**, so `acme-password` cannot log into `boreal|sam`.
- `TenantPrincipal` extends Spring Security's `User`, which provides `getPassword()` and `CredentialsContainer`. Instances are loaded fresh from the DB rather than reusing a cached object whose hash was erased.
- Authorities are fetched from `account_authorities` using both tenant and account ID. No authorities are ever accepted from request bodies or headers.
- `/api/orders/{orderId}` checks **tenant + owner account + order ID** in the query; knowing an `orderId` alone is never enough to access someone else's order.
- `/api/reports` requires `reports:read`; Acme cannot view Boreal's reports even though both have username `sam`.
- The API returns only identity metadata to authenticated clients; it never returns raw passwords, password hashes, JDBC secrets, or full `UserDetails` objects.

### 6.3 Running

Create the files per the structure in section 6.1 and `schema.sql` from section 4.1. If the project has a Gradle wrapper, run:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you have no Gradle wrapper but have a compatible Gradle installed, run `gradle bootRun`. The application requires Spring libraries, so **a standalone `javac TenantLookupApplication.java` command will not work**. JDK 17 or higher is required for this demo, along with Maven Central access on first dependency resolution.

Open another terminal and use `curl`; on PowerShell you may need `curl.exe`. The commands below use illustrative passwords for local H2 (localhost HTTP); never use plaintext HTTP with real credentials:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/me
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/me

curl -i -u 'acme|sam:boreal-password' http://localhost:8080/api/me
curl -i -u 'boreal|sam:acme-password' http://localhost:8080/api/me

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/orders/1001
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/orders/1001

curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/orders/2001
curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/orders/2001

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/reports
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/reports
```

Expected results, focusing on status codes and primary body rather than container-specific headers:

| Case | Expected | Explanation |
| --- | --- | --- |
| `GET /public` | `200`, body `public` | Public endpoint. |
| `GET /api/me` without credentials | `401` | Unauthenticated. |
| `acme|sam` + `acme-password` | `200`, tenant `acme`, accountId `101` | Right account, right password. |
| `boreal|sam` + `boreal-password` | `200`, tenant `boreal`, accountId `202` | Same local username, different subject. |
| `acme|sam` + `boreal-password` | `401` | Boreal's password cannot log into Acme. |
| `boreal|sam` + `acme-password` | `401` | Acme's password cannot log into Boreal. |
| Acme requests order `1001` | `200`, body `acme-order` | Matching tenant and owner. |
| Boreal requests order `1001` | `404` | Acme's order is invisible to Boreal's tenant-scoped query. |
| Boreal requests order `2001` | `200`, body `boreal-order` | Matching tenant Boreal. |
| Acme requests order `2001` | `404` | No cross-tenant order leak. |
| Acme requests `/api/reports` | `403` | Authenticated, yet missing `reports:read`. |
| Boreal requests `/api/reports` | `200`, body `reports-for-boreal` | Has matching authority. |

Example `GET /api/me` response for Acme has content equivalent to:

```json
{
  "tenantId": "acme",
  "accountId": 101,
  "username": "sam",
  "authorities": ["orders:read"]
}
```

Boreal's response has `tenantId="boreal"`, `accountId=202`, and authorities `orders:read` and `reports:read`. JSON property ordering is not guaranteed; assert parsed values rather than comparing raw bytes.

### 6.4 Why Does the Example Not Rely on the X-Tenant Header?

If a client logs in as `acme|sam` and sends `X-Tenant: boreal` on a subsequent request, the controller **does not read** that header to switch identity. The tenant inside the principal remains `acme` because it was server-verified and bound at login. Supporting active tenant switching in a membership-based system requires a dedicated workflow that verifies the user actually has a Boreal membership and then establishes/switches a trusted effective context.

Order queries also do not run `WHERE order_id=?` and check tenant only after loading sensitive data; the query filters both tenant and owner **at the point of access**. If an admin needs to read orders across users within the same tenant, the owner predicate can be replaced by role/action authorization, yet **the tenant boundary must still be enforced**.

## 7. Comparing Wrong vs. Right Approaches

### 7.1 Filtering Only by Username, Then Assigning Tenant from Request

```java
// WRONG: anti-pattern example, not a standalone class.
Account account = repository.findByUsername(username);

// Compounded error: trust client's tenant and treat logged-in account as belonging to it.
String tenant = request.getHeader("X-Tenant");
TenantPrincipal principal = makeTrustedPrincipal(
        account, tenant, account.getAuthorities());
```

Two-layer flaw: lookup omits tenant, and then the result switches namespaces based on unverified input.

**Right:** query `findByTenantIdAndLoginName(tenantCandidate, loginName)`; provider verifies password and status on the returned account; result sets `principal.tenantId = account.tenantId` from the trusted source. Headers/routes never grant authority on their own.

### 7.2 Picking the Right Account, Yet Loading Roles from Another Tenant

```sql
-- WRONG if usernames overlap across tenants:
SELECT authority
FROM account_authorities_by_username
WHERE username = ?;

-- RIGHT when authorities are tied to the composite identity:
SELECT authority
FROM account_authorities
WHERE tenant_id = ? AND account_id = ?;
```

Account lookup and authority lookup must share the exact same boundary. Checking the password for the right tenant but loading authorities by unscoped username lets a user inherit permissions from a namesake in another tenant.

### 7.3 Checking Tenant Only in the Controller, Not in Service/SQL

```java
// WRONG: fetch object by ID across the entire DB before checking scope.
Order order = orderRepository.findById(orderId).orElseThrow();

// If data has already passed through logger/cache/serializer, checking later is too late.
if (!order.getTenantId().equals(principal.getTenantId())) {
    throw new AccessDeniedException("Forbidden");
}
```

Post-load object policies are sometimes necessary, yet they should not replace **scoping queries at retrieval time** for isolated data. With Spring Data/JPA, prefer `findByIdAndTenantId(...)` or a specification/query with a tenant predicate; add `ownerAccountId` when owner-scoped. Ensure JPQL/SQL projections, joins, and lazy loading also never pull in another tenant's data accidentally.

### 7.4 Using loginName as a Global Cache Key

```text
WRONG: cache["sam"] = Account(acme, #101)
       next, boreal|sam mistakenly gets Acme's record.

RIGHT: cache[(tenantId, canonicalLogin)] = AccountInTenant(...)
       or cache[globallyUniqueAccountId] = ...
```

Cache keys must match the namespace of the data store. When an account is disabled, changes passwords, changes roles, or switches tenants, invalidate the exact keys and issued sessions/tokens per policy; TTL alone does not guarantee immediate revocation.

### 7.5 Using a Global JWT Subject While Ignoring Issuer/Tenant

A `sub` like `sam` or `123` is not inherently unique across multiple IdPs. In JWT/OIDC, durable identity usually requires **issuer + subject**, or a verified mapping from a trusted IdP to an internal account followed by a tenant membership check. Never use bare `sub` as a global key when multiple issuers can emit overlapping subjects.

## 8. Spring Security Multi-Tenancy with OAuth2/JWT: How It Differs from Password Flows

Spring Security Resource Server supports **multiple bearer token verification strategies** and allows an `AuthenticationManagerResolver` to select a manager at request time. For JWTs from multiple issuers, Spring Security documentation guides building a resolver from **trusted issuers** rather than creating decoders for arbitrary attacker-supplied issuers.

Two independent steps are required:

1. **Resolve tenant/issuer to select a verifier** from a trusted registry and fixed contract.
2. **Validate the token**: signature, issuer, audience, lifetime (`exp`/`nbf`), and relevant claims; then map the verified identity to a permitted tenant/membership.

Do not confuse "reading `iss` from the JWT" with "verifying the issuer". Payloads can be decoded without checking signatures. A resolver can inspect claims to select a verifier, but **must only choose from an allowlist of issuers**; the decoder/provider must then fully validate and reject invalid tokens. Allowing any URL from a token as an issuer opens the door to spoofing or SSRF/metadata fetching depending on configuration.

**Illustrative** configuration for Spring Security 6.x with two fixed issuers, not a standalone application:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://login.example.test/issuer-acme",
                "https://login.example.test/issuer-boreal");

http
    .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver));
```

Using this requires `spring-boot-starter-oauth2-resource-server`, real issuers with valid metadata/keys, audience/claims validation configuration, and corresponding account/tenant mapping. This snippet is not a one-line "turn on multi-tenancy and you're done" solution; never ship illustrative domains to production.

**Federation identity:** `(issuer, subject)` locates a verified external identity; a mapping table can record `issuer`, `subject`, `tenant_id`, and `account_id`. If one external identity belongs to multiple tenants, membership/policy determines the active tenant—holding a valid JWT never automatically grants access across every tenant.

### 8.1 When a JWT Carries a Tenant Claim

- Only trust claims after full signature/issuer/audience validation.
- Specify which issuers are authorized to assert which tenant claims; a valid JWT from issuer X must not arbitrarily assert `tenant_id=Y` if the contract forbids it.
- If roles/scopes are tenant-bound, map and validate them within the namespace; never grant a global `ROLE_ADMIN` across all tenants when permission belongs to one organization.
- If the URL/header asks for tenant A while the verified token is bound to tenant B, **reject or enforce an authorized membership/switch workflow**, never silently switching the effective tenant.
- A revoked token or user removed from a tenant does not automatically invalidate self-contained access tokens immediately without a freshness/revocation policy; design appropriate TTLs and revalidation.

### 8.2 When One User Belongs to Multiple Organizations

In a *global identity + memberships* model:

```text
identity: user_global_id = 7, issuer = trusted-idp
membership:
  (tenant=acme, user=7, role=READER)
  (tenant=boreal, user=7, role=EDITOR)
```

After authenticating the global identity, the client can submit a **selection request** to pick `boreal`; the server queries membership `WHERE user_id=7 AND tenant_id='boreal' AND active=true`. On success, the effective principal/context carries tenant Boreal with Boreal's membership authorities; otherwise, deny. Being "logged in" must never merge roles from all tenants into a single global permission bag.

## 9. Multiple Datasources or Schemas: Scoping All the Way to the Connection

Besides the *shared database/shared schema* architecture in the demo, other topologies exist:

| Storage model | Advantage | Risk / safeguard |
| --- | --- | --- |
| Shared DB, shared tables with `tenant_id` | Centralized operations/migrations. | Every query and join must be scoped, composite unique/indexes; RLS can add defense-in-depth. |
| Shared DB, separate schema per tenant | Structural and query isolation by schema. | Select schema from verified data, reset connection pool state, run migrations across all schemas. |
| Separate database per tenant | Stronger resource/fault isolation in some models. | Tenant → DataSource mapping needs an allowlist/registry, careful connection, secrets, and trust-boundary routing. |
| Separate identity provider per tenant | Domain trust/SSO per organization. | Issuer/certificate/JWKS validation and subject/tenant mapping; never dynamically trust arbitrary URLs. |

**Common pitfall with routing datasources:** Calling `AbstractRoutingDataSource` and picking `lookupKey` from an arbitrary `X-Tenant` header lets attackers steer the server to another tenant's database. For unauthenticated login, a candidate tenant must only **select a candidate verifier source from an approved registry**, and credentials must be verified within that exact source. After login, business read requests pick the DB from the verified tenant and membership permissions, never from a raw header alone.

Additionally, storing tenant in a custom `ThreadLocal` requires careful lifecycle cleanup, especially with thread pooling, async execution, scheduled jobs, and event processing. A stale tenant context leaking across a reused thread is a critical security bug. Prefer passing an explicit/immutable `TenantContext` from the principal to services/repositories and using official context-propagation mechanisms when needed, rather than assuming request threads are everything.

### RLS Is an Extra Layer, Not a Substitute for Tenant-Aware Login

With PostgreSQL Row-Level Security or similar features, the DB can enforce tenant predicates via session roles/settings. This is valuable defense-in-depth, provided the application sets the tenant session variable/DB role from the **authenticated principal**, never from raw headers; watch connection pool state resets, role bypasses, migration users, and integration tests. Never treat RLS as an excuse to drop `WHERE tenant_id=?` from queries where policy expects it.

## 10. Authorization Must Be Tenant-Scoped, Not Just Role-Scoped

A role like `ROLE_ADMIN` or authority `orders:read` **is not enough** to grant access across every tenant. Authorities carry scoped semantics:

- `(tenant=acme, authority=orders:read)`: read orders in Acme only.
- `(tenant=boreal, authority=orders:read)`: read orders in Boreal only.
- Platform operator authority: may inspect multiple tenants under a separate administrative policy with auditing and least privilege.

Do not flatten every tenant role into a global authority and let `hasRole("ADMIN")` read another organization's data. In the demo app, `TenantPrincipal` establishes the effective tenant and `/api/orders/{orderId}` filters tenant+owner in the DB. These are **two complementary layers**: route-level `orders:read` and object-level tenant/owner checks.

One user may have `READER` and only be permitted to read their own orders. Another with `TENANT_ADMIN` may read all orders within their tenant, yet must never read another tenant's orders. Enforce these rules in services, repositories, and authorization policies—never rely on hiding UI buttons.

### 10.1 Preventing IDOR/BOLA

Suppose Alice in Acme learns order ID `2001` belonging to Boreal. If the endpoint runs:

```sql
SELECT * FROM tenant_orders WHERE order_id = ?;
```

then guessing IDs leaks another tenant's data. Instead, scope by the security context:

```sql
SELECT title
FROM tenant_orders
WHERE order_id = ?
  AND tenant_id = ?
  AND owner_account_id = ?;
```

The second and third parameters come from the verified principal, never from client-supplied `?tenant=...` or `?owner=...`. Whether out-of-scope objects return `404` or `403` depends on your anti-enumeration policy; **never leak object details in uncontrolled errors or logs**.

### 10.2 Switching Tenants Safely

If users are allowed to work across multiple tenants, a safe switch flow works as follows:

1. The user is authenticated via a global identity or stable subject.
2. The client requests switching to tenant T.
3. The server checks active membership/permissions for that subject and T.
4. The server updates context/session or issues a new token **bound to T and T's authorities** per policy.
5. Every subsequent request validates the new token/session; mismatched tenant requests are rejected or routed through the switch flow.
6. When membership is revoked, invalidate/refresh sessions/tokens/caches per freshness requirements.

Never store a browser-editable `activeTenant` in an unsigned/unprotected header or cookie and pass it straight into repositories.

## 11. Registration and Account Management Across Multiple Tenants

**Looking up the right account at login** is only part of the lifecycle. When creating/managing users:

- Only create accounts inside a tenant where the caller has admin authority or through an approved provisioning workflow.
- Database `UNIQUE (tenant_id, canonical_login_name)` must guard against concurrency. Checking `SELECT EXISTS` before inserting does not eliminate race conditions; handle unique constraint failures properly.
- Email may serve as a login identifier or recovery channel, yet one email may participate in multiple tenants. Password resets must explicitly identify **which account/namespace** is being recovered.
- When sending email invitations, bind the invite token to tenant, inviter, user/email, expiry, and one-time semantics; never let an Acme token open a Boreal membership.
- When granting roles, record `tenant_id` alongside `account_id` and the grantor; avoid inserting `ROLE_ADMIN` merely because a request asked for it.
- When deleting/disabling a tenant, handle accounts, memberships, sessions, tokens, secrets, and data under a clear policy; do not merely "hide the tenant prefix in the UI".
- Backup/restore, import/export, and background jobs must also be tenant-aware; jobs running without an HTTP request cannot read tenant from request headers.

**Name collisions:** `sam` in Acme and `sam` in Boreal do not mean the two accounts belong to the same person. Never merge accounts, sync password hashes, or transfer permissions between them based on matching usernames.

## 12. Caching and Sessions: Preserving Namespace Across Requests

### 12.1 Cache Keys

Cache `UserDetails` by **qualified login key** or a truly globally unique account key, never by bare `login_name`:

```text
WRONG:
  userCache["sam"]  -> Account #101/Acme

RIGHT:
  userCache["acme|sam"]   -> Account #101/Acme
  userCache["boreal|sam"] -> Account #202/Boreal

ALSO CHECK:
  authorityCache[(tenantId, accountId)]
  membershipCache[(tenantId, globalUserId)]
```

`org.springframework.security.core.userdetails.User` implements `CredentialsContainer`; on success, `ProviderManager` may erase credentials on the principal. If the exact same `UserDetails` instance from a cache is reused, the password hash may be wiped, breaking the next login. Separate the cached verifier from copied principals properly and test multi-request correctness. Never disable erasure just to mask a caching bug.

### 12.2 Sessions/JWTs After Tenant or Role Changes

An authenticated session typically stores a principal/authorities snapshot. When a user leaves a tenant, changes roles, or has their account disabled, **database updates do not automatically cause every live session/JWT to fail immediately**. Define:

- What is the maximum acceptable revocation latency?
- When must membership/tenant status be revalidated?
- Which sessions must be invalidated, which tokens revoked, and which cache keys refreshed?
- When switching tenants, are sessions/tokens isolated per tenant; how are in-flight old requests prevented from running under the new tenant?
- Do APIs reading sensitive data verify permissions against a fresher source than the cache?

**Never hold a mutable tenant global variable** inside a singleton Spring bean. Multiple requests/tenants execute concurrently; use proper request-scoped context or explicit parameters read from the principal.

### 12.3 Audit Logging Without Leaking Credentials

Logs may include authenticated `tenantId`, `accountId`, request ID, action, outcome, timestamp, and sanitized reason codes. Pre-login tenant hints should be logged in line with anti-enumeration/PII policies; never log passwords, JWTs, bearer tokens, session cookies, or full authentication objects that might contain secrets. In multi-tenant systems, read access to audit logs must also be tenant-scoped.

## 13. Common Errors and How to Fix Them

| Symptom | Possible causes | How to check and fix |
| --- | --- | --- |
| Two tenants share `sam`; login sometimes enters the wrong account | SQL only has `WHERE username=?` or cache keyed by username. | Composite query, unique/index, and cache key including tenant; verify principal after login. |
| Tenant A's password works to enter tenant B's account | Code authenticates global username and takes tenant from header without membership check. | Verify credentials against exact account or use global identity + dedicated membership workflow. |
| Login succeeds but returns roles from another tenant | Authority query lacks tenant/account scoping. | Filter authorities by tenant and account ID from the verified account. |
| User with `ROLE_ADMIN` in A can read B | Global role unscoped in authorization. | Enforce tenant predicates/object policies; separate platform-admin from tenant-admin. |
| Changing `X-Tenant` header alters returned data | API trusts client header as authenticated tenant. | Treat header only as hint; authorization uses verified principal/membership. |
| Spoofed subdomain affects account lookup | Unchecked `Host`/proxy forwarded headers/tenant registry. | Lock down trusted hosts and ingress rules; validate candidate tenant before lookup. |
| `JwtIssuerAuthenticationManagerResolver` accepts any `iss` | Unallowlisted issuers. | Use a trusted issuer registry and full JWT verification; avoid arbitrary metadata URLs. |
| `getPrincipal()` lacks tenant/accountId | Stores bare username only, missing binding. | Custom principal/adapter carrying DB `accountId` and `tenantId`; avoid wrong casts with JWTs. |
| One person in two tenants gets mixed session permissions | Global role bag or mutable active tenant without membership check. | Tenant-scoped context, switch workflow + reissue/refresh auth state. |
| User disabled yet old session still works | Session/JWT still valid, stale cache. | Define freshness/revocation, invalidate by tenant/account, and test. |
| SQL has tenant predicate yet JOIN pulls another tenant's data | JOIN on non-global ID alone is insufficient. | JOIN on composite keys, verify FK/PK, and enforce tenant predicates throughout the query. |
| Admin importing duplicate names creates inconsistency | Missing `UNIQUE (tenant_id, login_name)`, race on user creation. | DB constraint + transaction + conflict handling. |
| Multi-tenant datasource reuses the wrong schema | Connection pool fails to reset tenant/schema. | Set/reset session context per transaction/connection lifecycle; integration test it. |
| API returns unexpected 404 | Tenant+owner filter hides out-of-scope objects. | Distinguish intentional 404 from missing query data; never drop tenant predicates just to return 200. |
| HTTP 403 after login | Missing authority for authenticated tenant or object policy denies access. | Inspect sanitized authenticated tenant/account/authorities and query scope. |

### Safe Debugging Sequence

1. **Right chain/filter?** Did the request enter the intended authentication mechanism?
2. **Where did the candidate tenant come from?** Was the pre-login value checked against format, allowlist, and namespace?
3. **Right lookup?** Does the SQL include **both `tenant_id` and `login_name`**; are parameters bound; right datasource/schema?
4. **Right verifier?** Was the hash fetched from the selected tenant's record; did `PasswordEncoder.matches` verify the raw password?
5. **Right result?** Does the post-login principal contain server-assigned tenant/account IDs rather than self-declared input?
6. **Right authorities?** Were roles/memberships loaded for the verified tenant/account?
7. **Right data queries?** Do all object reads/writes enforce tenant + owner/permission scope?
8. **Right lifecycle?** Do sessions/JWTs/caches enforce proper freshness and revocation?
9. **No data leaks?** Are logs, traces, and error responses free of passwords, tokens, full account records, and excess PII?

Never log passwords or raw tokens to debug. Use request IDs, permitted internal account IDs, provider class names, result codes, and verified tenant IDs as appropriate.

## 14. Required Test Matrix

| Test case | Expected result |
| --- | --- |
| Two accounts with `login_name=sam` in two tenants | Schema permits storing both; unique constraint reports no conflict. |
| Creating a second `sam` inside the same tenant Acme | `UNIQUE (tenant_id, login_name)` rejects it. |
| `acme|sam` + Acme password | Authentication succeeds with `tenantId=acme`, `accountId=101`. |
| `boreal|sam` + Boreal password | Authentication succeeds with `tenantId=boreal`, `accountId=202`. |
| `acme|sam` + Boreal password | HTTP 401; never falls back to Boreal's account. |
| `boreal|sam` + Acme password | HTTP 401; never falls back to Acme's account. |
| Malformed qualified key or unknown tenant | Generic authentication failure, no account-existence leak. |
| Acme reads its own Acme order | 200 if `orders:read` and matching owner. |
| Acme reads Boreal order `2001` | 404/403 per policy, no data leaked. |
| Boreal reads Acme order `1001` | 404/403 per policy, no data leaked. |
| Acme reads report requiring `reports:read` | 403 due to missing authority. |
| Boreal reads report | 200 if `reports:read` is present. |
| Client sends `X-Tenant: boreal` with Acme auth | Effective principal stays Acme; no account/role switching. |
| JWT token with unallowlisted issuer | Rejected; never builds a decoder trusting arbitrary issuers. |
| Valid JWT for issuer A while request demands tenant B | Allowed only with verified mapping/membership for B; never auto-switches. |
| Cache loads `sam` from tenant A then B | No cache collision; hashes, statuses, and authorities never mix. |
| After membership/role revocation | Sessions/caches/tokens reflect revocation policy on time. |
| Ambiguous SQL JOIN on account ID | Schema/query enforces composite tenant + account; never returns wrong-tenant records. |
| JDBC connection pool switches tenants | No schema/session context leaks from prior requests. |
| Background job without an HTTP request | Still passes explicit verified/system-authorized tenant context and scopes data. |

**Good testing goes beyond checking 200/401/403.** Assert account ID and tenant after authentication, verify exact authority rows, inspect SQL for tenant predicates, and attempt direct access using another tenant's IDs. With multiple datasources, run integration tests against databases and connection settings close to production.

## 15. Reasoning Exercises with Solutions

### Question 1: Why is `UNIQUE(username)` alone insufficient?

The system allows both Acme and Boreal to have an account `sam`. A global `UNIQUE(login_name)` would block the second account. The right constraint is uniqueness scoped to the **actual login namespace**, such as `UNIQUE(tenant_id, login_name)`, combined with proper canonicalization and indexing.

### Question 2: Can a tenant from an unauthenticated login form be trusted?

**It cannot be trusted as membership or authority.** A form field can act as a *candidate* tenant to route lookup, subject to validation/allowlisting. Only after password/credentials are verified against the exact account and valid status does the server issue a principal with a trusted tenant ID from the account record.

### Question 3: A user logs into Acme successfully, then edits `X-Tenant: boreal` to read Boreal data. What must the API do?

**Never switch the effective tenant** based on the header alone. With an Acme session/token, the API must use Acme from the verified principal in its queries. If the user truly holds a Boreal membership, a tenant-switch request must be verified separately and establish a proper context.

### Question 4: Tenant is already filtered during user lookup; must orders also filter by tenant?

**Yes.** Accurate account lookup ensures the right principal; object authorization and data isolation are a separate step. An Acme user could guess a Boreal order ID. Repositories must enforce tenant/owner scope or equivalent policies so objects never leak.

### Question 5: Global user #7 is a member of Acme and Boreal. Why not merge both tenants' roles into one global list?

Because Acme's `ROLE_ADMIN` could be used to access Boreal if roles are not bound to tenants. Check membership and authorities for **the active tenant**, or use a clearly scoped authority representation evaluated against that scope.

### Question 6: A JWT has `iss=https://evil.example`, and the server fetches JWKS from it and treats it as valid. What is wrong?

The issuer was never registered as a trusted party. An attacker can mint a token signed with their own key and tell the server to fetch that key. The resolver must only choose issuers from a trusted registry, and the decoder must verify issuer/audience/signature/lifetime and map tenants per contract.

### Question 7: The `UserDetails` cache uses key `sam`; what bug occurs?

`acme|sam` and `boreal|sam` overwrite or fetch each other's cache entry, causing wrong password hashes, account statuses, and authorities to be used. Keys must include tenant + canonical username, or a genuinely globally unique account ID.

### Question 8: An account has `tenant_id=acme`, yet an order row inserts `tenant_id=boreal` and `owner_account_id=101`. How can the DB block this immediately?

Use a composite FK `(tenant_id, owner_account_id) REFERENCES tenant_accounts(tenant_id, account_id)` backed by a matching unique constraint on the account table. Then an order cannot reference an owner from another tenant even if application code has an insert bug.

### Question 9: Two tenants use two different IdPs, yet both JWT `sub` values equal `123`. Can `sub` be used as a global account key?

No. Bind verified issuer and subject together, or use a unique internal account mapping followed by a tenant membership check. `sub` must never be assumed unique across issuers.

### Question 10: Why is 404 when Boreal requests `/api/orders/1001` in the demo an intentional result?

Because the SQL scopes by Boreal's principal tenant+owner and finds no Acme order. Returning 404 avoids revealing the existence of out-of-scope objects under the demo policy. It does not mean the order was deleted from the DB.

## 16. Further Reading

- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService`, `PasswordEncoder`, and `AuthenticationManager` flow for username/password.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): controlled issuer/token verifier selection, `AuthenticationManagerResolver`, and trusted issuers.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `AuthenticationProvider`, and `SecurityContextHolder`.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): contract of the security view.
- [Spring Security — User class API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): constructors, authorities, status flags, `CredentialsContainer`, and caching caveats.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, authorizing every request, and preventing IDOR/BOLA.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): data isolation, scoping, identity, and caching in multi-tenant environments.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): initializing H2 with `schema.sql` in demo environments.

**Conclusion:** Multi-tenancy is an **identity and data boundary**, not a `tenantId` string for UI display. To look up the right account, queries must be scoped by tenant + login identifier; credentials verified against that exact account; principals hold tenant/account from an authoritative source; and all subsequent authorities and resource queries enforce the verified scope. A mistake at any single step can turn "two organizations sharing a username" into a cross-tenant access breach.