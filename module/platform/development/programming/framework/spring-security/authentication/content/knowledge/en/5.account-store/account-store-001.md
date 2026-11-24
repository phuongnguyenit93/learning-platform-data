# JdbcUserDetailsManager and the Users and Authorities Schema

When a Spring Security application authenticates a username/password, the authentication machinery needs to read a trusted account from a store: username, **one-way encoded password verifier**, login-enabled status, and server-granted **authorities**. For data in a relational database, Spring Security provides `JdbcDaoImpl` to read `UserDetails` via JDBC and `JdbcUserDetailsManager` to **both read and manage** users under the `UserDetailsManager` contract.

The core focus of this lesson is **the two linked tables `users` and `authorities`, the default SQL queries Spring Security uses, how data is managed, and the limits of the built-in schema**. Having a `JdbcUserDetailsManager` bean does not mean an account is already authenticated: a filter receives the username/password, `DaoAuthenticationProvider` calls the user store and `PasswordEncoder` verifies the credential, and then authorization decides access to resources.

This lesson belongs to the **Account Store** section in the *Spring Security - authentication* topic. The example runs on **Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Spring JDBC, and H2** to show exactly how data in the tables affects HTTP authentication.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish the roles of `JdbcDaoImpl`, `JdbcUserDetailsManager`, `UserDetailsService`, `UserDetailsManager`, `DaoAuthenticationProvider`, `PasswordEncoder`, and `DataSource`.
2. Create the two tables `users` and `authorities` along with primary key, foreign key, and unique constraints matching the default SQL queries.
3. Explain the meaning of `users.username`, `users.password`, `users.enabled`, `authorities.username`, and `authorities.authority`, and how they map to `UserDetails`.
4. Use `JdbcUserDetailsManager` to create, update, delete, check existence of, and load users under authorized management mechanisms.
5. Run a Spring Boot program using an H2 database; observe successful login, wrong password, disabled account, and insufficient authority.
6. Diagnose errors such as "user not found", "no authority", SQL schema mismatch, hash/encoder mismatch, wrong role prefix, and the difference between login and authorization.
7. Understand when you need to customize SQL, add group-based authorities, or implement a custom store for tenants, account lock, password expiration, and complex business policies.

## 2. What Do the Classes Do and How Do They Connect?

| Component | Specific responsibility | What it does not do on its own |
| --- | --- | --- |
| `DataSource` | Provides JDBC connections to the right database/schema. | Does not know whether a user's password is valid. |
| `JdbcDaoImpl` | Executes SQL queries to return `UserDetails` with username, password hash, enabled, and authorities. | Does not manage account CRUD. |
| `JdbcUserDetailsManager` | Extends `JdbcDaoImpl` and implements `UserDetailsManager` for user/authority CRUD and supported management operations. | Does not become an HTTP login filter merely by being registered as a bean. |
| `UserDetailsService` | Contract for reading a user via `loadUserByUsername(String)`. | Does not verify the raw password from the request. |
| `UserDetailsManager` | Extends `UserDetailsService` for certain user management operations such as `createUser`, `updateUser`, `deleteUser`, and `userExists`. | Does not replace the entire registration workflow, email verification, MFA, or business administration. |
| `DaoAuthenticationProvider` | Uses the user store and `PasswordEncoder` to verify username/password credentials and account status. | Does not create database tables or grant authorities based on request parameters. |
| `PasswordEncoder` | Stores/verifies the password verifier using `encode` and `matches`. | Does not encrypt TLS or execute JDBC queries. |
| `Authentication` / `SecurityContext` | Carries the authenticated principal and granted authorities to request handling. | Does not guarantee that a user has permission for every data object. |

Typical flow in Spring Security Servlet:

```text
HTTP Basic or form login
     |
     v
Authentication filter creates UsernamePasswordAuthenticationToken
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     |
     +--> JdbcUserDetailsManager.loadUserByUsername(username)
     |        |
     |        +--> DataSource/JDBC
     |                | users: username, password, enabled
     |                + authorities: username, authority (multiple rows)
     |        |
     |        +--> UserDetails (security view)
     |
     +--> account status + PasswordEncoder.matches(raw, storedHash)
     |
     v
Authenticated Authentication: principal + authorities
     |
     v
SecurityContext -> Authorization -> Controller/Service
```

**Security boundary:** `users.password` is an **encoded password verifier** stored in the server-side database, not the raw password received from the request. `authorities.authority` is a server-granted value; never take it from an `X-Role` header, a JSON `isAdmin` field, or a URL parameter. Finding an account record in the database is **not enough** to produce a successful `Authentication`.

## 3. Default Schema: The Two Tables users and authorities

Spring Security provides default DDL for the username/password store in the resource:

```text
org/springframework/security/core/userdetails/jdbc/users.ddl
```

The sample in Spring Security documentation uses `varchar_ignorecase` to describe some string types; this is a **database dialect-dependent** type and is not available in every RDBMS. Logical schema idea:

```text
users
  username  PK
  password  encoded verifier
  enabled   boolean

authorities
  username  FK -> users.username
  authority string
  UNIQUE(username, authority)
```

One user can have **multiple authorities**, so this is a 1–N relationship from `users` to `authorities`; the composite unique key prevents granting the same authority twice to one user. The `authorities` table usually does not need an extra `roles` table if the application only needs to store `GrantedAuthority` strings. A role is still a type of authority by prefix convention, for example `ROLE_READER`.

### 3.1 Portable SQL for the H2 Example and Databases Supporting VARCHAR/BOOLEAN

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE users (
    username VARCHAR(100) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(100) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_auth_user
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_auth_username
        UNIQUE (username, authority)
);
```

This DDL fits the default JDBC queries and runs with **H2** in the example. In PostgreSQL, MySQL, Oracle, or SQL Server, adjust types, collation, length limits, identity/sequence, and migrations accordingly; in particular, do not copy `varchar_ignorecase` from the documentation onto every RDBMS.

**Explanation of each column and constraint:**

| Column/constraint | Purpose | What to remember |
| --- | --- | --- |
| `users.username` | Login identifier key in the simple schema. | Case-sensitivity, Unicode, normalization, and uniqueness policies must be clear. |
| `users.password` | Verifier encoded with `PasswordEncoder.encode(...)`. | Use a column long enough for both the `{id}` prefix and the encoded password; **never store plaintext**. |
| `users.enabled` | Active condition of the account. | `false` is interpreted as disabled in `UserDetails`. |
| `authorities.username` | Foreign key pointing to the account. | Authorities must belong to a real user, avoiding orphan records. |
| `authorities.authority` | An authority string, such as `ROLE_READER` or `orders:read`. | Not a "permit everything" boolean; authorization still checks the endpoint/object. |
| `PRIMARY KEY(users.username)` | Only one record per username in the current namespace. | Multi-tenant systems may need a composite key `(tenant_id, username)`. |
| `UNIQUE(username, authority)` | Prevents storing duplicate authorities for the same user. | Avoids duplicate data and supports CRUD operations and integrity. |
| `FOREIGN KEY` | Prevents an authority from referencing a non-existent user. | When deleting a user, handle authorities first or design explicit cascading. |

**The simple default schema has intentional limitations:** `users` does not include `id` UUID, `tenant_id`, `locked_until`, `account_expired_at`, `password_changed_at`, `credentials_expired`, MFA fields, or status history. By default `JdbcDaoImpl` mainly loads **username, password, enabled, and authorities**; do not assume it checks account lock and credential expiration just because the `UserDetails` interface has those getters.

### 3.2 Why Is the authorities Table Also Needed?

Using a single `role` column directly in `users` only represents one value and does not match the default authorities query. When a user has `ROLE_READER` and `orders:read`, the table stores them as two rows. Example illustrating the data after creating users:

```text
users
+----------+---------------------+---------+
| username | password            | enabled |
+----------+---------------------+---------+
| alice    | {bcrypt}<hash...>    | true    |
| disabled | {bcrypt}<hash...>    | false   |
+----------+---------------------+---------+

authorities
+----------+-------------+
| username | authority   |
+----------+-------------+
| alice    | ROLE_READER |
| alice    | orders:read |
| disabled | ROLE_READER |
+----------+-------------+
```

**This is an illustrative table, not real hashes for logging in.** Bcrypt hash data has a random salt so each generation can differ. The `{bcrypt}` string is a prefix for `DelegatingPasswordEncoder`, not part of the password the user enters.

In the `UserDetailsService` Javadoc, `loadUserByUsername` may throw `UsernameNotFoundException` **when the user is not found or the user has no `GrantedAuthority`**. Therefore, a user that exists in `users` but has no authority in `authorities` may surface as "not found". When debugging, check **both tables**, not just `SELECT * FROM users`.

## 4. Default SQL Used by JdbcDaoImpl to Load UserDetails

With the default schema, the lookup mechanism is equivalent to the following SQL queries:

```sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
```

The `?` is a JDBC bind parameter. The system passes the username via prepared statement/binding rather than concatenating the username directly into the SQL string. **Never build `"... WHERE username='" + input + "'"` yourself** because it can create SQL injection.

### 4.1 Two Queries Serving Two Types of Data

- The `usersByUsernameQuery` query loads **one user** with username, encoded password, and enabled. The data must have the structure/aliases that `JdbcDaoImpl` expects. If the query returns multiple rows for one username, the account namespace is already ambiguous.
- The `authoritiesByUsernameQuery` query loads **multiple authorities** for the same username; it uses them to build the `GrantedAuthority` instances that `Authentication` receives upon success.
- `JdbcDaoImpl` has a separate mechanism for fetching group authorities when enabled; see section 9. You do not have to create group tables if the application does not use group mode.
- Column names, column return order, and the type of `enabled` must match the default mapper. Using an `enabled` alias from an arbitrary expression can turn every account into enabled, causing a policy bug.

### 4.2 Distinguishing the User-Lookup Query from Password Verification

This is a misconception:

```sql
-- Wrong responsibility if treating this SQL as completing authentication:
SELECT * FROM users WHERE username = ?;
```

SQL finding the record only provides `UserDetails` containing the verifier; **`PasswordEncoder.matches(rawPassword, storedHash)` is what checks the credential** in the provider. If the user enters a wrong password, the user is still found, but a valid authentication is not produced.

Do not use a query comparing plaintext passwords in SQL such as `WHERE username=? AND password=?` when the column holds a proper password hash. Hashes with salt/cost must be verified through the password encoder in the proper format.

### 4.3 Sensitivity of Authorities

`ROLE_ADMIN`, `ROLE_READER`, and `orders:approve` are meaningful strings defined by the application's policy. `JdbcDaoImpl` loads them; **it does not validate why a user was granted that role**. Granting/managing authorities must live in an authoritative workflow (admin, approved provisioning, identity sync) and be audited.

- `hasRole("ADMIN")` in the default configuration checks the `ROLE_ADMIN` authority.
- `hasAuthority("orders:read")` checks the exact string `orders:read`.
- `User.withUsername(...).roles("READER")` adds the `ROLE_` prefix when creating `UserDetails`.
- If the database already contains `ROLE_READER`, do not add the prefix a second time when loading. `JdbcDaoImpl` has a role prefix option; only use it when the data genuinely needs it and you understand its impact on authorization.

A user having `ROLE_READER` only proves the system granted a general authority; you must still check **object-level permissions** and tenant. Successful authentication must not be equated with permission to read all orders.

## 5. JdbcDaoImpl vs. JdbcUserDetailsManager

`JdbcDaoImpl` is sufficient when the requirement is only to **load accounts for login**, while user registration/administration workflows are owned by a separate service. `JdbcUserDetailsManager` extends it to manage data according to `UserDetailsManager`:

| API/capability | Purpose | What to verify in business logic |
| --- | --- | --- |
| `loadUserByUsername(username)` | Loads the security view for the provider. | Username is in the right namespace and exists; has authorities. |
| `userExists(username)` | Checks whether the username already exists in the store. | Do not rely on a single check as a uniqueness guarantee under concurrent access. |
| `createUser(userDetails)` | Inserts user and authority records according to configured SQL. | Password is encoded, roles come from a trusted source, transaction/constraints are in place. |
| `updateUser(userDetails)` | Updates user/authority data supported by the manager. | Do not overwrite authorities accidentally; check authorization of the caller making the change. |
| `deleteUser(username)` | Deletes account/authorities according to configured SQL queries. | Enforce foreign keys, soft delete, audit, and retention of related business data. |
| `changePassword(old,new)` | Changes password according to the user context and related configuration. | Verify current user, encoder, old-password verification, and session invalidation per policy. |
| `setUsersByUsernameQuery(...)` | Changes the SQL for finding an existing account. | Query returns username/password/enabled matching the mapper. |
| `setAuthoritiesByUsernameQuery(...)` | Changes the SQL for loading existing authorities. | One or more rows with username/authority. |
| `set...Sql(...)` methods for CRUD | Changes insert/update/delete/check SQL queries when the schema differs. | Read the version-specific Javadoc and maintain data consistency when changing them. |

**Do not use `JdbcUserDetailsManager` as a public account administration API**. If a registration endpoint calls `createUser`, the backend must authenticate the caller's permission, validate input, encode the password, assign minimal default authorities, and handle conflicts/idempotency. The client must never send `authorities=["ROLE_ADMIN"]` and have the server copy it verbatim into the DB.

### 5.1 A Single User Operation Often Touches Two Tables

For example, creating a user with two authorities requires at minimum inserting the user and the authority rows. Deletion also needs to ensure authorities are deleted or managed via FK. A failure partway through can leave inconsistent state; in a real account management service, **consider the transaction boundary** or use Spring JDBC/manager mechanisms with appropriate administrative transactions, and verify rollback with integration tests.

`JdbcUserDetailsManager` is a tool; consistency, audit, policy, and transactions at the business level still must be designed. A CRUD method must never be assumed to "automatically cover every multi-system registration workflow".

### 5.2 For Passwords, the Input Is an Encoded Verifier

If using `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, generate a new verifier with `encoder.encode(rawPassword)` and pass it into `UserDetails` before calling `createUser`. `JdbcUserDetailsManager` is not responsible for automatically hashing a plaintext password input. Do not store `{noop}secret` outside of demos. For `updateUser`/`changePassword`, check the encoding contract of your version and service caller to avoid storing raw passwords, double-hashing, or accidentally bypassing current-password verification.

### 5.3 Return Contract of loadUserByUsername

The contract is to return a valid `UserDetails` or throw `UsernameNotFoundException`. Never return `null` to indicate a missing user. In particular, **a user with a record in the `users` table but no valid authority** may be treated as user not found; check the authorities table and group mode.

## 6. Runnable Example: Spring Boot 3.3.13 + JDBC + H2

The example creates an in-memory H2 database, initializes the two tables using `schema.sql`, and uses `JdbcUserDetailsManager` to add two demo accounts:

- `alice` with `ROLE_READER` and `orders:read`, enabled.
- `disabled` with `ROLE_READER` but `enabled=false`.

HTTP Basic invokes `DaoAuthenticationProvider` to check the stored password hash. The controller only returns principal/authorities, never the hash. Both accounts use the **local demo** raw password `local-demo-password`, intended only for learning environments. Spring Boot 3.3.13 is a released version of the 3.3.x branch, not a recommendation to pick an EOL version for new production systems.

### 6.1 Project Structure

```text
jdbc-auth-lesson/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/JdbcAuthLessonApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

File `settings.gradle`:

```groovy
rootProject.name = 'jdbc-auth-lesson'
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

**Why is `spring-boot-starter-jdbc` needed?** `JdbcDaoImpl` and `JdbcUserDetailsManager` require JDBC/DataSource; adding only the web/security starters does not guarantee HikariCP, JDBC support, and the datasource are configured for the user store.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:authlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.sql.init.continue-on-error=false
```

Spring Boot runs `schema.sql` for the embedded datasource via SQL initialization before the runner bean creates users. `DB_CLOSE_DELAY=-1` keeps the in-memory database alive until the process ends (within the current JVM). **An empty password for H2 user `sa` is only for an in-memory learning database**, not a production setting. Disable the public H2 console; never commit real DB passwords into source control.

File `src/main/resources/schema.sql` is the two `CREATE TABLE` statements from section 3.1. The example does **not** need `data.sql`, because the `ApplicationRunner` below uses the management API to create accounts with valid hashes.

### 6.2 Complete Java Code

File `src/main/java/demo/JdbcAuthLessonApplication.java`:

```java
package demo;

import java.util.Map;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.jdbc.JdbcDaoImpl;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JdbcAuthLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcAuthLessonApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager userDetailsManager(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    ApplicationRunner seedDemoAccounts(
            JdbcUserDetailsManager users,
            PasswordEncoder encoder) {

        return args -> {
            if (!users.userExists("alice")) {
                UserDetails alice = User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .authorities("ROLE_READER", "orders:read")
                        .build();
                users.createUser(alice);
            }

            if (!users.userExists("disabled")) {
                UserDetails disabled = User.withUsername("disabled")
                        .password(encoder.encode("local-demo-password"))
                        .roles("READER")
                        .disabled(true)
                        .build();
                users.createUser(disabled);
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/orders").hasAuthority("orders:read")
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class JdbcDemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> currentUser(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders-readable";
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
```

The `JdbcDaoImpl` import line is not used directly in the Java class above; you can remove that import without changing the program. It only serves as a reminder of the base class that `JdbcUserDetailsManager` extends. The remaining imports serve the beans/filter/controller directly.

**Why is the manager bean enough for authentication in this example?** `JdbcUserDetailsManager` implements `UserDetailsService`; when it is the active user service and a `PasswordEncoder` is present, Spring Security's standard username/password configuration can use `DaoAuthenticationProvider`. `httpBasic()` provides the mechanism for receiving raw passwords. In projects with a custom `AuthenticationManager` or multiple `SecurityFilterChain` beans, you must verify that the manager/filter is actually wired to the user store; adding a bean does not automatically attach it to every chain.

### 6.3 Running and Observing

Use the project's Gradle wrapper if present:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you do not have the wrapper but have a compatible Gradle installed, you can run `gradle bootRun`. **You cannot run `javac JdbcAuthLessonApplication.java` standalone** because the class requires Spring Boot, Spring Security, and JDBC dependencies; Gradle resolves the classpath.

In another terminal, send requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/orders
curl -i -u alice:local-demo-password http://localhost:8080/api/admin
curl -i -u disabled:local-demo-password http://localhost:8080/api/me
```

In PowerShell, if `curl` is an alias for something else, use `curl.exe`. Exact HTTP output may contain different headers depending on version/container; the **reliable test outcomes** are:

| Request | Expected HTTP | Meaning |
| --- | --- | --- |
| `/public` without credentials | `200`, body `public` | URL is permitted by `permitAll()`. |
| `/api/me` without credentials | `401` (HTTP Basic challenge) | No authenticated principal yet. |
| `alice:wrong` to `/api/me` | `401` | User is found, but password match fails. |
| `alice:local-demo-password` to `/api/me` | `200` | Password verifier matches; authorities from JDBC are granted. |
| Alice to `/api/orders` | `200`, body `orders-readable` | Has the `orders:read` authority. |
| Alice to `/api/admin` | `403` | Authentication succeeds, but lacks `ROLE_ADMIN`. |
| `disabled` to `/api/me` | `401` | `enabled=false` causes login to be rejected. |

The `GET /api/me` body for Alice is equivalent to (JSON key order is not fixed):

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER", "orders:read"]
}
```

Even though the JSON from the endpoint includes username and authorities, **it must never contain `password` or the password hash**. The code outputs only the necessary metadata. Bcrypt generates a random salt, so you must not compare raw hash text across runs.

### 6.4 What Was Verified Through the Example?

1. Spring Boot creates the H2 `DataSource` and runs `schema.sql` on startup.
2. `ApplicationRunner` creates users/authorities using `JdbcUserDetailsManager`, with passwords encoded beforehand.
3. `BasicAuthenticationFilter` turns HTTP Basic credentials into an authentication request.
4. `DaoAuthenticationProvider`/`JdbcDaoImpl` loads username/hash/enabled/authority rows and verifies the password.
5. On success, `Authentication` contains the corresponding principal and authorities.
6. Authorization decides `/api/orders` by `orders:read` and `/api/admin` by `ROLE_ADMIN`, returning 200 or 403 depending on policy.
7. If `enabled=false` or the raw password is incorrect, the request does not yield a successful authentication.

Important point: the `userExists()` method in the runner is helpful when running code repeatedly against the same database, but **it cannot replace a unique constraint or transaction in a system with concurrency**. The example does not use a distributed mechanism or multiple instances seeding into a long-lived database concurrently.

## 7. Customizing the Schema When Account Tables Already Exist

In a real application, existing tables might look like:

```text
account
  id, tenant_id, login_name, password_hash,
  active, locked_at, ...
account_permission
  account_id, permission_code, ...
```

If you want to reuse `JdbcDaoImpl`, you can configure two **read** SQL queries that return the exact data the default mapper expects:

```java
@Bean
JdbcUserDetailsManager userDetailsManager(DataSource dataSource) {
    JdbcUserDetailsManager manager =
            new JdbcUserDetailsManager(dataSource);

    manager.setUsersByUsernameQuery("""
        SELECT login_name, password_hash, active
        FROM account
        WHERE login_name = ?
        """);

    manager.setAuthoritiesByUsernameQuery("""
        SELECT a.login_name, ap.permission_code
        FROM account a
        JOIN account_permission ap ON ap.account_id = a.id
        WHERE a.login_name = ?
        """);

    return manager;
}
```

**This is a read SQL configuration example for a hypothetical schema**, not drop-in code for the default demo: to use this schema, you must create the corresponding tables and handle multi-tenancy. Both queries still take one username bind parameter and return columns in the order **username/password/enabled** and **username/authority**. If the schema has multiple tenants sharing the same `login_name`, filtering only by username as above is **unsafe**: you must design a subject key/tenant boundary from a trusted source before querying, or use a `UserDetailsService` suited to a multi-tenant architecture.

More importantly, **changing only the two read queries does not make `JdbcUserDetailsManager` CRUD valid for the new tables**. The methods `createUser`, `updateUser`, `deleteUser`, and `userExists` still have their own default SQL; to manage accounts on a custom schema, you must align all related SQL per the API version or separate out a dedicated user management service. Do not configure the manager with custom read queries and expect `createUser` to write into the `account` table on its own.

### 7.1 Username, ID, and Tenant Are Not Interchangeable

The default schema treats username as the primary key. In a multi-tenant system, `alice` in organization A and `alice` in organization B may be two separate accounts:

```text
(tenant=A, username=alice) -> account #101
(tenant=B, username=alice) -> account #205
```

A query like `WHERE username = ?` cannot select the right account by tenant. Reasonable design approaches include:

- A server-assigned global identity key, such as `tenant:accountId`, with clear mapping and canonicalization rules.
- An `AuthenticationManagerResolver` or user service partitioned by a **verified/authorized** tenant, never trusting an arbitrary client-supplied `X-Tenant` header.
- A custom `UserDetailsService` fetching the account by trusted subject/tenant, keeping a stable account ID as the principal ID, and returning authorities in the right namespace.

Never use a query string or request body to switch tenants and look up another account without trust-boundary checks. Post-login authorizations must still consider the specific tenant and resource.

### 7.2 What Evidence Is Allowed to Determine enabled?

By default `enabled` is a boolean in `users`, sufficient for enabled/disabled. If the application needs to handle `locked_until`, unverified email, password age, account expiry, or pending review, decide accordingly:

- Write a query/mapper or custom `UserDetailsService` that reflects the full state in `UserDetails` and an appropriate provider/checker.
- Avoid cramming every state into a single `enabled` boolean and losing the required reason and lifecycle.
- Separate the condition for **allowing login** from **permission to perform a business action**. An account may be allowed to log in to pay an overdue invoice even when its subscription tier no longer permits running a feature.

Do not claim that default `JdbcDaoImpl` automatically respects `isAccountNonLocked` and `isCredentialsNonExpired` based on columns absent from the schema. When needed, build a custom security adapter and test the flags.

## 8. Groups: When Permissions Are Granted Through Groups Instead of Individual Users

Spring Security JDBC has a mode for managing authorities by **group**. When group authorities are enabled, the data typically uses three additional tables:

| Table | Contents | Relationship |
| --- | --- | --- |
| `groups` | Group ID and group name. | Each group can have many members and authorities. |
| `group_members` | Which username is a member of which group. | Many users link to many groups. |
| `group_authorities` | Authority granted to a group. | One group has many authorities. |

Default group schema in the documentation:

```sql
CREATE TABLE groups (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(50) NOT NULL
);

CREATE TABLE group_members (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    group_id BIGINT NOT NULL,
    CONSTRAINT fk_group_members_group
        FOREIGN KEY (group_id) REFERENCES groups(id)
);

CREATE TABLE group_authorities (
    group_id BIGINT NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_group_auth_group
        FOREIGN KEY (group_id) REFERENCES groups(id)
);
```

Above is **group DDL adapted for H2/common SQL**, not a claim of byte-for-byte identity with the `users.ddl` resource across all versions. Consider unique constraints on memberships and group authorities, a username foreign key if appropriate, and migrations for a real database.

To fetch authorities from groups, configure `JdbcDaoImpl` via `setEnableGroups(true)`; by design you can keep `enableAuthorities=true` to also load direct authorities, or set `setEnableAuthorities(false)` if you only want authorities from groups. You must create the group tables before enabling group queries; otherwise, login can fail with a SQL error even when the `users`/`authorities` tables exist.

Group-based authorities **do not by default imply a role hierarchy system**. Groups are just a way to store/aggregate authorities; whether one role implies another or which ABAC/RBAC policy applies depends on separate authorization configuration.

## 9. Safe User/Authority Management in Production

### 9.1 Password Hashing and Credential Changes

- Use an appropriate `PasswordEncoder` (for example, `DelegatingPasswordEncoder` with bcrypt or a password hashing algorithm approved by your organization).
- When creating/changing a password, encode from the raw password exactly once; `users.password` holds a consistently formatted hash.
- Never store raw passwords in logs, query params, audit events, database migrations, or public samples.
- For password reset, build a time-limited, replay-resistant recovery flow that verifies ownership; after reset, decide whether to invalidate sessions/refresh grants per policy.
- When old hashes need migration, design a controlled upgrade path; do not change the encoder and assume all legacy data will still authenticate.

### 9.2 Managing Authorities at an Authoritative Source

- Only an authorized admin or provisioning service may modify `authorities`.
- Grant least privilege; every change should be audited (who, action, timestamp, tenant, scope).
- Forbid clients from submitting `ROLE_ADMIN` in a form and having a mapper save it directly.
- When an authority is revoked, account for `UserDetails` caches and security sessions still holding the old authority; a database update **does not automatically update every issued session/JWT**.
- Guard against race conditions when granting/removing authorities, especially with concurrent operations by multiple admins or services.

### 9.3 Transactions, Uniqueness, and Concurrency

A user consists of the main record plus authorities, so writing multiple related rows needs an appropriate transaction boundary if the workflow requires atomicity. User creation can happen concurrently with another request: checking `userExists(...)` before `createUser(...)` is useful, but still has a **TOCTOU race**. Use a unique constraint as the final safeguard, handle `DuplicateKeyException` or the appropriate error, and decide on retries at the business level.

Deleting a user must handle FKs; choosing hard-delete vs. soft-delete depends on retention laws, auditing, and domain references. If soft-deleting, ensure login is disabled and security queries do not return deleted accounts.

### 9.4 DataSource and Operability

- Use a bounded connection pool with timeouts and least-privilege DB permissions; if the auth service only needs reads, consider separating SELECT privileges from provisioning write privileges.
- The login path needs proper indexes on username/namespace and authority FKs; avoid N+1 queries in other policies.
- Store DB TLS settings/credentials in a secret manager; do not hardcode production secrets into `application.properties`.
- Database downtime/timeouts must cause authentication to **fail closed** (never automatically grant anonymous requests authenticated status).
- Use a database migration tool (Flyway/Liquibase) to manage versioned production schemas; avoid running both automatic SQL initializers and a migration tool on the same schema unless deliberately planned.
- Limit logging of SQL bind parameters that could contain usernames/PII; do not turn on JDBC database tracing in production to inspect passwords.
- Define cache freshness and revocation mechanisms when an account is disabled or roles change; do not assume the next request automatically reloads `UserDetails` in every mechanism/session.

## 10. Common Errors and How to Diagnose Them

| Symptom | Causes to check | How to fix |
| --- | --- | --- |
| Login fails even though the user is in `users` | Missing `authorities` rows, wrong username/case, wrong DataSource, SQL query. | Check both tables on the **right database/schema**; lookup requires the user to have authorities. |
| `BadCredentialsException` | Raw password does not match the encoded verifier; wrong `{id}` prefix or encoder. | Check hash generation and encoding policy; do not switch to `{noop}` to bypass the error. |
| `DisabledException` / HTTP 401 | `enabled=false` or wrong status mapper. | Check the status source and login policy; do not edit the DB to enabled without approval. |
| SQL syntax / table not found | `schema.sql` did not run, wrong datasource/schema, different dialect, different table/column names. | Check datasource configuration, migrations, and default queries; avoid guessing from DB names. |
| "User not found" when authorities are empty | The loader does not return a user with valid authorities. | Grant authorities per policy or use a custom user store when semantics genuinely require empty authorities. |
| Login succeeds but returns `403` | Missing authority, wrong `ROLE_` prefix, endpoint requires a different permission, or CSRF on state-changing requests. | Check sanitized `Authentication.getAuthorities()` and authorization rules; do not arbitrarily alter the password store. |
| `createUser` SQL error with custom schema | Only read SQL was changed; create/insert SQL still points to default tables. | Align CRUD queries or use a separate provisioning service. |
| Locked account can still log in | Default schema has no lock flag; custom mapping/provider does not check it. | Add the proper security view and status checker. |
| Case "Alice" differs from "alice" | Collation and column type depend on the database; normalization queries are inconsistent. | Establish a canonical username policy and appropriate unique index/collation. |
| Users A and B share a username across two tenants | Query lacks namespace/tenant. | Use a proper multi-tenant identity key and trust boundary; do not rely on self-reported headers. |
| DB status/role changed but old sessions still work | Authentication in the session is a snapshot; cache/JWT not revoked. | Define refresh/revoke/invalidate policies; test existing sessions too. |
| Only half of users/authorities data is written | Multiple SQL statements in create/update/delete lack a transaction or fail under concurrent writes. | Add transaction boundaries, FKs, unique constraints, and integration tests. |

### 10.1 When Encountering 401, Find the Right Failure Layer

Check in order: did the request go through the right `SecurityFilterChain`? Was `httpBasic()` applied? Did the filter create the right authentication? Does the provider use this `JdbcUserDetailsManager` or another bean? Does the SQL lookup fetch the right account and authorities? Does `PasswordEncoder.matches(...)` match? Is `enabled` true? If a 401 happens after finding the right user, do not immediately blame the JDBC query.

### 10.2 When Encountering 403, Check Authorization

If the response is 403, the user may already be **properly authenticated** but missing `ROLE_ADMIN` or `orders:read`, or failing CSRF on a session/cookie request. Inspect the principal's authorities and the policy on the endpoint/object; do not add higher privileges just to make the endpoint return 200.

### 10.3 Observability Boundaries

Never log raw passwords, encoded passwords, `Authorization`, `Cookie`, bearer tokens, or JDBC credentials. Useful fields include request ID, authentication outcome, normalized exception type, component name, sanitized SQL error code, and query duration. Be careful with SQL debug logs because bind params can contain personal identifiers.

## 11. Test Matrix

| Test case | Expected result |
| --- | --- |
| Fresh schema initialized | Both tables and FK/unique constraints exist before seeding users. |
| `createUser` with two authorities | Exactly one `users` row and two `authorities` rows, no duplicates. |
| `loadUserByUsername("alice")` | Returns the right username, encoded password, enabled=true, and two authorities. |
| `userExists("alice")` | True after creation, false after deletion per workflow. |
| Non-existent username | `loadUserByUsername` throws `UsernameNotFoundException`. |
| User with no authority rows | Cannot be loaded as a user with authorities by default; verify actual error. |
| Correct password, enabled=true | HTTP 200 on authenticated endpoint; no hash exposed in response. |
| Wrong password | HTTP 401, no authenticated principal granted. |
| Enabled=false | HTTP 401 even when the raw password is correct. |
| Alice has `orders:read` | `GET /api/orders` returns 200. |
| Alice lacks `ROLE_ADMIN` | `GET /api/admin` returns 403. |
| Duplicate authority record | Unique constraint rejects duplicate insert. |
| Authority username does not exist | Foreign key blocks orphan insert. |
| Role changed in database | New request result reflects the designed freshness/session policy. |
| Custom read queries with default CRUD | Must verify create/update/delete compatibility, not just login. |
| Multi-tenant login | Does not mistakenly fetch an account with the same username from another tenant. |
| Concurrent user creation | Unique constraint and transaction prevent duplicates/partial records. |
| DB disconnected | Does not treat authentication as successful; error is handled safely. |
| Group mode enabled | Group tables exist, authorities are correct, and roles are not unintentionally duplicated. |

For integration tests, use a datasource/migration close to production and test both authentication and query behavior. Unit tests on a mock repository are not enough to prove that columns, constraints, and default SQL are compatible with the actual database.

## 12. Self-Check Exercises

**Question 1.** An account `alice` is in `users` with `enabled=true` and a valid password hash, but has no rows in `authorities`. Why might login fail as if the user were not found?

**Answer:** Default `JdbcDaoImpl`/`UserDetailsService` requires at least one `GrantedAuthority`; with no authorities, the loader may throw `UsernameNotFoundException`. Check the authorities table or choose a different architecture if the system intentionally allows accounts with zero authorities.

**Question 2.** The database stores `ROLE_EDITOR`, while the code uses `hasRole("EDITOR")`. Should you add the `ROLE_` prefix again when loading?

**Answer:** No. `hasRole("EDITOR")` matches `ROLE_EDITOR` by default. If loading authorities from a database that already includes the prefix, do not add `ROLE_` twice.

**Question 3.** A user has a valid password hash but `enabled=false`. Will the JDBC manager allow login?

**Answer:** The standard username/password provider rejects it because `isEnabled=false`, even if the password is correct. The enabled field is an account status condition, separate from the password.

**Question 4.** You want to use a table `app_accounts(login,hash,active)` instead of `users`. Is changing only `usersByUsernameQuery` enough for `createUser`?

**Answer:** No. You also need to change the authorities query and all CRUD SQL statements if you want the manager to write/delete on the new schema, or separate a read-only `UserDetailsService` from a custom provisioning service.

**Question 5.** In a multi-tenant system, two organizations both have username `sam`. Should you use `WHERE login = ?` as the entire identity decision?

**Answer:** No. You need a namespace/tenant from a trusted source, a valid key, and a properly scoped query to prevent cross-tenant access; never trust just a client-supplied header.

**Question 6.** Why is `JdbcUserDetailsManager` not enough out of the box to lock an account for 15 minutes after 5 wrong passwords?

**Answer:** The default schema only stores `enabled` and has no `lock_until`, failure counter, or status policy logic. You need a state store, a mechanism to update failure counts and lock duration, and an appropriate checker; also test concurrency/recovery.

**Question 7.** Can `{noop}password` be used for a demo DB? Should it be used in production?

**Answer:** `{noop}` can be used to demonstrate the flow in a constrained lesson, but it does not protect passwords. Production must use an approved password hashing algorithm with appropriate cost configuration and secret policies.

**Question 8.** Alice logs in successfully, calls `/api/admin`, and receives 403. Does that mean the password hash in `users` is wrong?

**Answer:** No. Authentication succeeded; Alice lacks the authority that authorization requires. Check the authorities table and policy—do not modify the password to fix an authorization error.

## 13. Official Sources and Further Reading

- Spring Security — [JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html): `JdbcDaoImpl`, `JdbcUserDetailsManager`, default `users/authorities` schema, and group tables.
- Spring Security — [JdbcDaoImpl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/jdbc/JdbcDaoImpl.html): SQL lookups, UserDetails mapping, enableAuthorities, enableGroups, and schema support/caveats.
- Spring Security — [JdbcUserDetailsManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html): user management APIs and CRUD SQL configuration.
- Spring Security — [UserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): missing user or user with no GrantedAuthority.
- Spring Security — [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): provider that checks password and status from `UserDetails`.
- Spring Security — [Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, verifier format, and hash upgrades.
- Spring Boot — [Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`/`data.sql`, embedded datasources, and migration mechanisms.

**Key takeaway:** `JdbcUserDetailsManager` manages a *clearly structured account store*, where `users` provides **username + encoded password + enabled** and `authorities` provides **authorities granted per username**. The SQL must match the schema and namespace, data must come from trusted sources, and `DaoAuthenticationProvider` together with `PasswordEncoder` determines credential validity. After authentication, authorization still decides what the user is allowed to do.