# Customizing JDBC Queries to Fit Existing Data

## Objectives

Many systems already have an account database before integrating Spring Security: the table is not named `users`, the password lives in a `pwd_digest` column, status is `active`, and roles are stored across relational tables. **You do not need to redesign the entire schema just to use JDBC authentication.** You can configure the SQL queries that Spring Security uses to load `UserDetails` and `GrantedAuthority`.

This lesson belongs to the **Account Store** group in the *Spring Security - authentication* module. It focuses on **customizing account/authority read queries in Spring Security Servlet** using `JdbcDaoImpl`, distinguishing when `JdbcUserDetailsManager` is needed for writing data, and the conditions for configuring it safely. Java snippets use Spring Boot 3.x, Spring Security 6.x, Java 17+; test SQL uses H2. When applying to PostgreSQL, MySQL, SQL Server, or Oracle, adapt syntax to the corresponding dialect.

Upon completing this lesson, you will know:

1. Which columns the two default queries of `JdbcDaoImpl` require, in what **order**, and which parameters.
2. How to use `setUsersByUsernameQuery(...)` and `setAuthoritiesByUsernameQuery(...)` to map an existing schema without faking a `users`/`authorities` schema.
3. How to build and run a Spring Boot example: accounts, password hashes, roles via join tables, HTTP Basic, and testing `200`/`401`/`403`.
4. How to handle schemas that use an ID instead of username, non-boolean status, roles with or without the `ROLE_` prefix, or permissions stored by group.
5. How to distinguish **reading login data** from **writing accounts**; choosing `JdbcDaoImpl`, `JdbcUserDetailsManager`, or a custom `UserDetailsService` to fit the need.
6. How to diagnose errors involving SQL column order, hash mismatches, missing authorities, duplicate users, SQL injection, tenant mismatches, and DataSource configuration.

## 1. Where Does JDBC Authentication Sit in the Authentication Flow?

When an application uses username/password, the typical chain of responsibility is:

~~~text
HTTP Basic / form login filter
          |
          v
AuthenticationManager (usually ProviderManager)
          |
          v
DaoAuthenticationProvider
          |
          +---> UserDetailsService.loadUserByUsername(username)
          |          |
          |          +---> JdbcDaoImpl
          |                  |-- usersByUsernameQuery
          |                  +-- authoritiesByUsernameQuery
          |                            |
          |                            v
          |                          DataSource / JDBC / database
          |
          +---> PasswordEncoder.matches(raw, storedHash)
          +---> checks account status and credentials
          |
          v
   Successful Authentication or AuthenticationException
          |
          v
  SecurityContext + authorization filter
~~~

`JdbcDaoImpl` is an implementation of `UserDetailsService`: it **loads the account and its list of authorities**. A `SELECT` query succeeding by itself **does not mean** the password is correct. `DaoAuthenticationProvider` is what verifies the password and account status, and then `AuthenticationManager` returns the result. The filter handles the request and places the trusted authentication into the security context.

Never put the raw password in the SQL lookup, such as `WHERE username = ? AND password = ?`: with passwords stored as hashes, checking that way is both bad design and risky. Lookup uses only the username; the password is checked by `PasswordEncoder` using the algorithm matching the stored data.

Common options:

| Need | Suitable component | Notes |
| --- | --- | --- |
| Only **reading** account and authority info from JDBC | `JdbcDaoImpl` | Usually sufficient when using an existing account system |
| Reading **and** creating/updating/deleting users, changing passwords via admin API | `JdbcUserDetailsManager` | Extends `JdbcDaoImpl`, but write queries must also be mapped |
| Complex domain (tenants, flags, statuses, custom policies) | Custom `UserDetailsService` + repository/JdbcTemplate | Flexible, must map `UserDetails` accurately yourself |
| Only authenticating bearer JWT/OIDC via valid tokens | Resource server/OAuth2 machinery | Does not necessarily call `UserDetailsService` |

## 2. The Query Contract of JdbcDaoImpl

The default tables in Spring Security examples look roughly like:

~~~sql
-- Minimal description of the default schema, DO NOT run
-- this snippet alongside the legacy schema in the example section.
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(50) NOT NULL
);
~~~

Correspondingly, the two default queries that read accounts and authorities are:

~~~sql
SELECT username, password, enabled
FROM users
WHERE username = ?;

SELECT username, authority
FROM authorities
WHERE username = ?;
~~~

These are **two independent SELECT statements**. Each uses **one `?` parameter**, bound by Spring JDBC from the username being searched. The two SQL queries are not joined in app code; `JdbcDaoImpl.loadUserByUsername(...)` runs the account lookup and then collects authorities.

### 2.1. usersByUsernameQuery: Three Columns in Exact Order

This query must produce a result set with columns in positional order:

| Column | Value needed by JdbcDaoImpl | Legacy example |
| --- | --- | --- |
| 1 | `username` (or key used under special configuration) | `login_name AS username` |
| 2 | stored `password` (hash) | `pwd_digest AS password` |
| 3 | `enabled` boolean/status readable via `ResultSet.getBoolean(3)` | `active_flag AS enabled` |

Mapping example:

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE a.login_name = ?;
~~~

**Order matters.** Changing aliases while keeping the wrong column order is not enough. `JdbcDaoImpl` reads the three columns by position in the traditional mapping path; returning `password, username, enabled` or `id, username, enabled` can cause authentication failures or mapping errors. Using both the right order **and** meaningful aliases makes it easier for SQL readers, drivers, and test tools to verify.

### 2.2. authoritiesByUsernameQuery: Two Columns in Exact Order

The authorities query must return:

| Column | Meaning | Example |
| --- | --- | --- |
| 1 | username/key value matching the lookup | `a.login_name AS username` |
| 2 | authority string | `p.code AS authority` |

~~~sql
SELECT a.login_name AS username, p.code AS authority
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
JOIN app_permissions p ON p.id = ap.permission_id
WHERE a.login_name = ?;
~~~

Each authority row corresponds to one `GrantedAuthority`, such as `ROLE_READER` or `SCOPE_reports.read`. Do not return a comma-joined string like `ROLE_USER,ROLE_ADMIN` as a single value unless you write a corresponding mapper: standard `JdbcDaoImpl` will treat it as **one** malformed authority.

By default, `JdbcDaoImpl` enables loading individual authorities (`enableAuthorities=true`) and does not automatically enable group authorities (`enableGroups=false`). If a user has zero authorities loaded, standard `JdbcDaoImpl` may throw `UsernameNotFoundException` even when the account row exists. Verify your policy for users without assigned permissions instead of "fixing" it by granting `ROLE_ADMIN` or an overly broad default role.

### 2.3. Why Is There a `?` Character in the SQL?

Spring JDBC uses a prepared statement and binds the username to the placeholder rather than concatenating the username directly into the SQL string. Correct:

~~~sql
SELECT login_name, pwd_digest, active_flag
FROM app_accounts
WHERE login_name = ?;
~~~

Wrong and vulnerable to SQL injection:

~~~java
// WRONG. Do not build a query from an untrusted username.
String sql = "SELECT * FROM app_accounts WHERE login_name = '"
    + usernameFromRequest + "'";
~~~

`JdbcDaoImpl` binds the parameter itself, so keep **one `?` placeholder** for the lookup query. Table or column names cannot be bound with `?`, so configure a fixed, server-controlled schema. If routing by tenant is needed, never concatenate a client-supplied schema/table name directly; use an allowlist mapping or a datasource/connection routed from a verified tenant identity.

## 3. Real-World Case: An Existing Account Schema

Suppose a business system uses:

~~~text
app_accounts
    id               BIGINT
    login_name       VARCHAR
    pwd_digest       VARCHAR  (BCrypt hash)
    active_flag      BOOLEAN

app_permissions
    id               BIGINT
    code             VARCHAR  ("ROLE_READER", "ROLE_ADMIN")

app_account_permissions
    account_id       BIGINT -> app_accounts.id
    permission_id    BIGINT -> app_permissions.id
~~~

These names **do not match** the default `users`, `password`, `enabled`, `authorities`. We will keep the naming as a legacy schema and map it using the two read queries in `JdbcDaoImpl`.

Intentional relationships:

- `app_accounts.id` is the internal key; `login_name` is the username used for login.
- `pwd_digest` holds a hash generated by `BCryptPasswordEncoder`; no plaintext password is stored.
- `active_flag=false` means the account is disabled.
- The list of roles comes from joining account → join table → permissions table.
- `p.code` already includes the `ROLE_` prefix; do not configure automatic prefixing a second time.

A valid account is found via `usersByUsernameQuery`, while permissions are loaded from one or more rows of `authoritiesByUsernameQuery`. These are two distinct data concerns.

## 4. End-to-End Runnable Spring Boot 3.x / Java 17+ Example

The example uses H2 **for learning environments only**, JDBC, Spring MVC, and HTTP Basic. It can run immediately after creating a Maven project with the listed dependencies. No external database installation is required. In production, do not use in-memory H2, do not seed demo passwords, enforce HTTPS, and configure datasources/secrets securely.

### 4.1. Create the Project

Create a project from Spring Initializr with:

- Spring Boot **3.x**, Java **17+**, Maven.
- Group `com.example`, artifact `legacy-auth`, package `com.example.demo`.
- Dependencies: **Spring Web**, **Spring Security**, **JDBC API / Spring JDBC** (Maven starter name `spring-boot-starter-jdbc`), **H2 Database**.
- The corresponding Maven dependencies are `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc`, and `com.h2database:h2` in runtime scope.

Required file tree:

~~~text
legacy-auth/
├── pom.xml                         (generated by Spring Initializr)
└── src/main/
    ├── java/com/example/demo/
    │   └── LegacyJdbcAuthApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.2. Create the Legacy Schema in H2

Contents of **`src/main/resources/schema.sql`**:

~~~sql
CREATE TABLE app_accounts (
    id BIGINT PRIMARY KEY,
    login_name VARCHAR(80) NOT NULL UNIQUE,
    pwd_digest VARCHAR(100) NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE app_permissions (
    id BIGINT PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE app_account_permissions (
    account_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    PRIMARY KEY (account_id, permission_id),
    FOREIGN KEY (account_id) REFERENCES app_accounts(id),
    FOREIGN KEY (permission_id) REFERENCES app_permissions(id)
);
~~~

This is a **demo** schema sufficient to run. In a real legacy application, keep your existing DDL and only adapt the read SQL to match. Do not import Spring Security's default `users.ddl` and run it on top of an existing schema: it creates mismatched tables and can trick developers into thinking authentication is using the legacy DB when it is actually reading from demo tables.

### 4.3. Configure the DataSource

Contents of **`src/main/resources/application.properties`**:

~~~properties
spring.datasource.url=jdbc:h2:mem:legacy_auth;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=embedded
~~~

Spring Boot loads `schema.sql` for the embedded database under this configuration before running the `CommandLineRunner` that seeds data. `DB_CLOSE_DELAY=-1` is only appropriate for an in-memory H2 example. In production, use Flyway/Liquibase or a managed migration process rather than initializing account tables on every startup.

### 4.4. Define the JDBC UserDetailsService and AuthenticationProvider

Full contents of **`src/main/java/com/example/demo/LegacyJdbcAuthApplication.java`**:

~~~java
package com.example.demo;

import java.util.List;
import java.util.stream.Collectors;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.jdbc.JdbcDaoImpl;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class LegacyJdbcAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(LegacyJdbcAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(DataSource dataSource) {
        JdbcDaoImpl jdbc = new JdbcDaoImpl();
        jdbc.setDataSource(dataSource);

        jdbc.setUsersByUsernameQuery("""
            SELECT
                a.login_name AS username,
                a.pwd_digest AS password,
                a.active_flag AS enabled
            FROM app_accounts a
            WHERE a.login_name = ?
            """);

        jdbc.setAuthoritiesByUsernameQuery("""
            SELECT
                a.login_name AS username,
                p.code AS authority
            FROM app_accounts a
            JOIN app_account_permissions ap
              ON ap.account_id = a.id
            JOIN app_permissions p
              ON p.id = ap.permission_id
            WHERE a.login_name = ?
            """);

        return jdbc;
    }

    @Bean
    AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        AuthenticationManager authenticationManager
    ) throws Exception {
        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    CommandLineRunner seed(JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                101L, "alice", encoder.encode("demo-pass"), true
            );
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                102L, "bob", encoder.encode("demo-pass"), true
            );
            jdbc.update(
                "INSERT INTO app_accounts "
                    + "(id, login_name, pwd_digest, active_flag) "
                    + "VALUES (?, ?, ?, ?)",
                103L, "disabled", encoder.encode("demo-pass"), false
            );

            jdbc.update(
                "INSERT INTO app_permissions (id, code) VALUES (?, ?)",
                1L, "ROLE_READER"
            );
            jdbc.update(
                "INSERT INTO app_permissions (id, code) VALUES (?, ?)",
                2L, "ROLE_ADMIN"
            );

            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                101L, 1L
            );
            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                102L, 2L
            );
            jdbc.update(
                "INSERT INTO app_account_permissions "
                    + "(account_id, permission_id) VALUES (?, ?)",
                103L, 1L
            );
        };
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            String roles = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

            return "user=" + authentication.getName()
                + "; authorities=" + roles;
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

#### Why Is This Configuration Valid?

1. `userDetailsService(DataSource)` creates `JdbcDaoImpl`, attaches the right `DataSource`, and replaces the two default SQL queries. It does not write users to the database upon creation.
2. `DaoAuthenticationProvider` uses the JDBC service to look up the hash and authorities, then `PasswordEncoder` to compare passwords.
3. `ProviderManager` holds that provider. `HttpSecurity.authenticationManager(...)` explicitly binds the manager to the HTTP filter chain, avoiding reliance on auto-wiring guesses when multiple providers exist.
4. `httpBasic(withDefaults())` allows sending credentials via HTTP Basic. `authorizeHttpRequests(...)` protects `/me`, requires role ADMIN for `/admin`, and permits access to `/public`.
5. `CommandLineRunner` only seeds H2 after Spring Boot has initialized the schema. Passwords in the DB are **hashed with BCrypt at runtime**; no plaintext password is used in `pwd_digest`.
6. `DemoController` receives the authenticated `Authentication`; it only displays the username and authorities, never returning hashes or credentials.

**Example limitations:** the `demo-pass` password and in-memory H2 are only for local learning. Seeding via `CommandLineRunner` writes data on every startup; do not copy the seed bean into an environment using a real database. All demo endpoints use GET, so CSRF does not need to be disabled to run; do not add `csrf.disable()` just because you are using HTTP Basic.

### 4.5. Run and Test with curl

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell on Windows uses `.\mvnw.cmd spring-boot:run`. Open another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u bob:demo-pass http://localhost:8080/admin
curl -i -u alice:demo-pass http://localhost:8080/admin
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u nobody:demo-pass http://localhost:8080/me
~~~

If `curl` is a PowerShell alias, use `curl.exe` instead. When running the code and H2 seed properly:

| Request | Expected Status | Observed data |
| --- | --- | --- |
| `GET /public`, no credentials | `200` | Body `public` |
| `GET /me`, no credentials | `401` | HTTP Basic challenge |
| `GET /me` with `alice:demo-pass` | `200` | Body **exact** `user=alice; authorities=ROLE_READER` |
| `GET /me` with `alice:wrong` | `401` | Password does not match hash |
| `GET /admin` with `bob:demo-pass` | `200` | Body `admin` |
| `GET /admin` with `alice:demo-pass` | `403` | Alice is authenticated but lacks `ROLE_ADMIN` |
| `GET /me` with `disabled:demo-pass` | `401` | Account has valid data and hash, but `enabled=false` |
| `GET /me` with `nobody:demo-pass` | `401` | Username not found |

Error headers and response bodies depend on version/filter/servlet container; the focus is on statuses and successful response bodies. If you change the configured port, update the URL accordingly.

You can observe what was loaded by placing breakpoints at `JdbcDaoImpl.loadUserByUsername(...)`, `JdbcDaoImpl.loadUserAuthorities(...)`, `DaoAuthenticationProvider.retrieveUser(...)`, and the `PasswordEncoder.matches(...)` step. Never log raw passwords, Authorization headers, or full hashes.

### 4.6. Verify the Two SELECT Queries Directly in the Database

In a SQL client for the test environment, run the two queries below after seeding (in the SQL console you use literal values just to cross-check; in the application keep using `?`):

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE a.login_name = 'alice';

SELECT
    a.login_name AS username,
    p.code AS authority
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
JOIN app_permissions p ON p.id = ap.permission_id
WHERE a.login_name = 'alice';
~~~

Query 1 must return exactly **one row** with the three columns `username=alice`, `password=<BCrypt hash>`, `enabled=true`. The hash value differs across runs because BCrypt generates a random salt — that is normal behavior. Query 2 must return the row `username=alice`, `authority=ROLE_READER`. If Query 1 returns a row but Query 2 returns zero rows, Spring Security may report `UserDetails` not found / no authority rather than automatically granting empty permissions.

## 5. Real-World Schema Variants and How to Write Queries

### 5.1. Non-BOOLEAN Status Column

Some systems use `status_code` such as `ACTIVE`, `DISABLED` instead of `active_flag`. If the SQL dialect supports `CASE`, you can return a boolean value:

~~~sql
SELECT
    a.login_name AS username,
    a.password_hash AS password,
    CASE WHEN a.status_code = 'ACTIVE'
         THEN TRUE ELSE FALSE END AS enabled
FROM app_accounts a
WHERE a.login_name = ?;
~~~

This is an **adaptation pattern**, not for verbatim use against the H2 schema run above (in that example the column is `active_flag`). If the database uses a `CHAR(1)` type like `Y/N` or `1/0`, use a conversion suitable for your dialect; verify that the JDBC driver reads column 3 via `ResultSet.getBoolean(3)` as expected.

Do not use a constant `TRUE AS enabled` just because the table lacks this column if the business domain actually has lock/disable states: doing so can bypass account controls. If the domain genuinely does not manage enabled state, you may use an intentionally chosen boolean constant, accompanied by tests and policy documentation.

### 5.2. Authorities Stored Across Multi-Level Join Tables

If a role is `role_id` and the roles table uses business codes `ADMIN`/`READER`, the query can normalize it on the fly:

~~~sql
SELECT a.login_name AS username,
       CONCAT('ROLE_', r.role_code) AS authority
FROM app_accounts a
JOIN app_account_roles ar ON ar.account_id = a.id
JOIN app_roles r ON r.id = ar.role_id
WHERE a.login_name = ?;
~~~

This pattern is illustrative: change table names and the concat function to match your database. **Do not use both** `CONCAT('ROLE_', ...)` and `JdbcDaoImpl.setRolePrefix("ROLE_")` at the same time; the result would become `ROLE_ROLE_ADMIN`, causing `hasRole("ADMIN")` to fail. Conversely, if the DB already stores `ROLE_ADMIN` as in the runnable example, do not add the prefix.

Note the distinction between role and authority:

- `hasRole("ADMIN")` normally checks the `ROLE_ADMIN` authority under the default prefix.
- `hasAuthority("reports.read")` checks the exact authority string `reports.read`, without automatically adding `ROLE_`.
- When using a system-wide custom prefix, keep configuration and tests consistent; do not change the string in only one of the SQL queries.

### 5.3. DB Uses a Numeric Key Instead of Username

Suppose `app_accounts.id` is the primary key while the username is `login_name`. The least-surprising approach is for **the user query to still return `login_name` in column 1**, and then JOIN authority tables via ID inside the same SQL; the demo in section 4 does this.

`JdbcDaoImpl` also has `setUsernameBasedPrimaryKey(false)` for designs where the first column of the lookup result is not the username, and the authorities query runs using the corresponding key. However, when choosing this path you must thoroughly test how the user lookup, the key passed to the authorities query, and the returned username behave, because type or configuration mismatches can cause subtle bugs across identity stores. Do not toggle the flag merely because the database has an ID column: the demo schema uses ID for joins and **does not need** the flag enabled.

If usernames are allowed to change, consider the impact on sessions, caches, audits, and query mechanisms using a stable key; do not turn username into ID or vice versa if the domain has no clear mapping policy.

### 5.4. Case-Sensitive DB and Username Normalization

`WHERE login_name = ?` may compare case-sensitively or case-insensitively depending on collation and database. For example, `Alice` and `alice` can be two distinct records in one environment yet equal in another.

You can enforce a normalized **case-insensitive** policy with matching indexing:

~~~sql
SELECT
    a.login_name AS username,
    a.pwd_digest AS password,
    a.active_flag AS enabled
FROM app_accounts a
WHERE LOWER(a.login_name) = LOWER(?);
~~~

This is a standalone pattern and should not be blindly applied to every DB: an expression like `LOWER(column)` can prevent regular indexes from being used, requiring a function-based index or a normalized column; furthermore, Unicode/email normalization is not as simple as `LOWER`. UNIQUE constraints and account creation rules must follow the exact same rule. **The lookup query must return a single deterministic identity**, never allowing multiple duplicate accounts after normalization.

### 5.5. Authorities Assigned via Groups

`JdbcDaoImpl` supports loading group authorities via:

~~~java
jdbc.setEnableGroups(true);
jdbc.setGroupAuthoritiesByUsernameQuery("""
    SELECT
        g.id,
        g.group_name,
        p.code
    FROM app_groups g
    JOIN app_group_members gm ON gm.group_id = g.id
    JOIN app_group_permissions gp ON gp.group_id = g.id
    JOIN app_permissions p ON p.id = gp.permission_id
    WHERE gm.login_name = ?
    """);
~~~

**This is only an illustrative snippet** placed in the `JdbcDaoImpl jdbc` configuration if the real schema also has `app_groups`, `app_group_members`, and `app_group_permissions`. **Do not** paste it directly into the demo app, because the example `schema.sql` does not create those tables. The standard group query has three columns in order: **group ID, group name, authority**. Group mode is off by default; `setEnableGroups(true)` is required. You can use direct authorities and group authorities together, or explicitly call `setEnableAuthorities(false)` when using groups only; in the latter case, ensure the group query loads the required authorities.

### 5.6. Do Not Use a JOIN That Duplicates the Account Row in usersByUsernameQuery

A common design mistake:

~~~sql
-- WRONG FOR ACCOUNT LOOKUP WHEN USER HAS MULTIPLE ROLES.
SELECT a.login_name, a.pwd_digest, a.active_flag
FROM app_accounts a
JOIN app_account_permissions ap ON ap.account_id = a.id
WHERE a.login_name = ?;
~~~

If Alice has three roles, this query can produce **three rows for the same account**. `JdbcDaoImpl` expects the identity lookup to yield one deterministic record; never rely on "take the first row" behavior to legitimize duplicate data. Return exactly one account row in `usersByUsernameQuery`, and read multiple permissions in `authoritiesByUsernameQuery`. Enforce `UNIQUE` on the username per policy and test accounts with multiple roles.

## 6. When Using JdbcUserDetailsManager, Write Queries Must Also Be Customized

`JdbcUserDetailsManager` extends `JdbcDaoImpl` and implements `UserDetailsManager`: it provides APIs such as `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists`, and authority/group management. This is useful **if the application is actually permitted to write accounts**.

However, replacing the two SELECTs does not automatically make the default INSERT/UPDATE/DELETE statements match a legacy schema. In addition to `setUsersByUsernameQuery` and `setAuthoritiesByUsernameQuery`, the implementation supports methods such as:

- `setCreateUserSql(...)`, `setUpdateUserSql(...)`, `setDeleteUserSql(...)`.
- `setCreateAuthoritySql(...)`, `setDeleteUserAuthoritiesSql(...)`.
- `setUserExistsSql(...)`, `setChangePasswordSql(...)`.
- Dedicated group SQL methods if managing groups through the manager.

**Do not call `createUser(...)` on a `JdbcUserDetailsManager` that only changed the two SELECT queries and expect it to save into `app_accounts`.** You must adapt each DML statement, placeholder order, transaction boundaries, foreign keys, hashing, auditing, and operation permissions.

Example **showing shape only and not run in the app above**:

~~~java
JdbcUserDetailsManager manager = new JdbcUserDetailsManager(dataSource);

manager.setUsersByUsernameQuery(
    "SELECT login_name, pwd_digest, active_flag "
        + "FROM app_accounts WHERE login_name = ?"
);
manager.setAuthoritiesByUsernameQuery(
    "SELECT a.login_name, p.code FROM app_accounts a "
        + "JOIN app_account_permissions ap ON ap.account_id = a.id "
        + "JOIN app_permissions p ON p.id = ap.permission_id "
        + "WHERE a.login_name = ?"
);

// If actually using createUser/updateUser/deleteUser,
// you must design complete DML for a schema with numeric PK and join tables.
// Do not assume the two SELECTs above are enough for CRUD.
~~~

`JdbcUserDetailsManager` has a constructor taking `DataSource` in Spring Security 6.5. Because this snippet provides no DML, it **should only be used for reading as a `UserDetailsService`** if there is no write implementation; in read-only practice, use `JdbcDaoImpl` as in the complete example.

If the schema uses auto-generated IDs, multiple join tables, audit columns, and multi-step transactional logic, a domain service with `@Transactional`/repositories is usually clearer than forcing every operation through preconfigured SQL strings. Never let users gain account administration privileges just because the application contains a `JdbcUserDetailsManager` bean; endpoints invoking CRUD must still be protected by proper authorization.

### 6.1. Custom RowMapper When SELECT Alone Is Not Enough

Some modern Spring Security versions (for example `JdbcUserDetailsManager` from 6.5) add configuration methods `setUserDetailsMapper(RowMapper<UserDetails>)` and `setGrantedAuthorityMapper(RowMapper<GrantedAuthority>)`. These are advanced options when SQL results require custom mapping. With traditional `JdbcDaoImpl`, the two positional SELECT setters remain the more stable path.

If the domain needs to preserve locked/expired flags or a principal containing an account ID and extra fields, do not assume default `JdbcDaoImpl` will automatically map every extra column onto `UserDetails`. It mainly loads username, password, enabled, and authorities. Consider writing a custom `UserDetailsService`:

~~~java
// ILLUSTRATIVE EXAMPLE: not a standalone runnable file.
@Override
public UserDetails loadUserByUsername(String username) {
    AccountRecord a = accountRepository.findByLogin(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("Unknown account"));

    return User.withUsername(a.loginName())
        .password(a.passwordHash())
        .authorities(a.authorities())
        .disabled(!a.active())
        .accountLocked(a.locked())
        .build();
}
~~~

This snippet assumes `AccountRecord`/`accountRepository` are domain types and methods defined by the application; do not copy it into the demo file without providing the repository. When security data changes, issued caches/sessions/tokens also need an appropriate update or revocation policy.

## 7. Testing Queries Independently and Integration Testing Authentication

With legacy data, it is very easy to get "SELECT runs fine" yet "login fails". Split tests into three layers.

### 7.1. Direct SQL Verification

For each test username:

| Input data | usersByUsernameQuery | authoritiesByUsernameQuery | Expected outcome |
| --- | --- | --- | --- |
| Existing username, active=true, 1 authority | 1 row | 1 authority row | Can authenticate if password is correct |
| Existing username, multiple authorities | 1 row | N rows | Authorities aggregated accurately |
| Non-existent username | 0 rows | 0 rows | `UsernameNotFoundException` on lookup |
| Existing username, no authorities | 1 row | 0 rows | Verify `JdbcDaoImpl` policy/behavior before deploying |
| Disabled account | 1 row enabled=false | May have authorities | Provider rejects even if password matches |
| Duplicate username by collation/normalization | Risk of >1 row | Risk of mixed authorities | **Data bug** requiring constraint/policy fix |

You can run SQL tests using a database client or a `JdbcTemplate.query(...)` integration test. With the H2 demo, Alice/Bob/disabled cover three representative branches.

### 7.2. Testing UserDetailsService

A Spring context test can inject the service and assert the data (illustrative snippet, requires test starter):

~~~java
// In a @SpringBootTest test class with UserDetailsService injected:
UserDetails alice = userDetailsService.loadUserByUsername("alice");
assertEquals("alice", alice.getUsername());
assertTrue(alice.isEnabled());
assertTrue(alice.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
~~~

This lookup result **does not** prove the raw password was verified. To verify login, you must test through `AuthenticationManager`/HTTP Basic or form login.

### 7.3. End-to-End HTTP Testing

The `curl` commands in section 4 prove three distinct layers:

1. **Lookup:** Alice is loaded from `app_accounts` via the custom query.
2. **Authentication:** matching BCrypt password and enabled account → `200`; wrong password/disabled/unknown → `401`.
3. **Authorization:** Bob with `ROLE_ADMIN` accesses `/admin`; Alice with `ROLE_READER` receives `403`.

When putting real SQL into an existing project, prioritize regression tests for at least: non-existent user, active/disabled, multiple authorities, accented/Unicode names, username case policy, old and new password hashes, admin role, user lacking permission, database errors, and tenant boundary.

## 8. Diagnosing Common Errors

### Error 1. `BadSqlGrammarException` or "table/column not found"

**Cause:** SQL uses the default `users` table even though the database only has `app_accounts`; different schema name; wrong alias; different SQL dialect; DataSource pointing to the wrong database.

**How to resolve:** verify connection, schema name, SELECT privileges, and actual column names; run each SQL query with a sample value and then restore `?`. Check safe query logs and active flag mapping. Never modify a production database directly just to make sample SQL work.

### Error 2. Username Loads Properly, but `BadCredentialsException`

**Common causes:** column 2 is not a hash, query returns columns in the wrong order, hash uses a different algorithm than the encoder, or wrong password was entered. The real password cannot be reconstructed by inspecting the hash string.

**How to resolve:** confirm result set column 2 is the actual hash string; check the matching encoder format, such as BCrypt. For legacy algorithms, build a hash migration strategy and use `DelegatingPasswordEncoder` where appropriate; never enable `NoOpPasswordEncoder` in production.

### Error 3. User Exists in app_accounts, Yet "Not Found"

**Cause:** the authority query returns 0 rows, wrong JOIN condition, username differs in case, or input data/driver collation mismatch. `JdbcDaoImpl` may throw `UsernameNotFoundException` when the user has no authorities.

**How to resolve:** run both queries separately with the exact username; check foreign keys and authority mappings. Do not "fix" it by granting admin privileges or disabling account status checks.

### Error 4. `hasRole("ADMIN")` Always Returns 403 Despite Account Having the Role

**Cause:** the DB returns `ADMIN` while policy expects `ROLE_ADMIN`, or the prefix was accidentally added twice. A single string `ADMIN,READER` is also not equivalent to two authorities.

**How to resolve:** decide on one consistent convention and inspect `Authentication.getAuthorities()` after login in dev, without logging other sensitive details. If using a custom role prefix, synchronize it across the entire authorization configuration.

### Error 5. User Has Multiple Roles, but Loads Incorrectly

**Cause:** putting the roles JOIN into `usersByUsernameQuery` so it returns multiple account rows, or the authority query only takes the first row/wrong column.

**How to resolve:** the user query must return exactly one row; the authority query returns N rows, one permission name per row. Check `DISTINCT`/UNIQUE on many-to-many relationships if duplicates exist.

### Error 6. `enabled=true`, Yet Account Is Locked in the Domain

**Cause:** default `JdbcDaoImpl` does not know about all business flags (lock, expiry, soft-delete, MFA). The query only returns three columns, where `enabled` might be mapped to the wrong policy.

**How to resolve:** clearly identify which states must deny login, project them into `enabled=false` when appropriate, or write a custom `UserDetailsService`/provider to handle other flags. Do not reduce every domain state into a single boolean.

### Error 7. Account Authenticates in Test Environment, Production Fails with JDBC Error

**Cause:** syntax for `TRUE/FALSE`/`CONCAT`/identifier quoting differs by dialect, schema name differs, missing permissions, insufficient connection pool, different DB SSL/certificates, or migrations not run.

**How to resolve:** run integration tests against the same database engine/dialect or a production-equivalent environment, verifying read permissions and migrations. H2 may accept SQL that PostgreSQL/Oracle does not accept identically.

### Error 8. Lookup Picks the Wrong User from Another Tenant

**Cause:** usernames are only unique within a tenant, yet `WHERE login_name = ?` ignores tenant; or tenant ID comes from an unverified HTTP header.

**How to resolve:** design the lookup with a tenant-aware identity key and a trustworthy tenant signal. This may require a custom authentication token/provider/`UserDetailsService` or policy-based DataSource routing. **Do not** patch around it by adding an extra `?` parameter to `JdbcDaoImpl`'s query: the standard query contract only auto-binds **username**. If a second parameter is truly required, build a proper custom integration.

### Error 9. No SQL Calls Observed on Subsequent Requests

**Cause:** `SecurityContext` is already stored in the session, a caching provider is active, or the request goes through a different authentication mechanism. Do not conclude the query is broken just because not every request calls the service.

**How to resolve:** identify the filter chain/authentication mechanism, test with a fresh session, and trace `UserDetailsService.loadUserByUsername(...)`. Do not reconfigure caches/sessions solely to force every request to hit the DB if that does not fit the architecture.

### Error 10. After Updating SELECTs, Calling `JdbcUserDetailsManager.createUser` Fails

**Cause:** default write statements still expect the default tables. **How to resolve:** use read-only `JdbcDaoImpl` when CRUD is unnecessary; if CRUD is required, configure complete DML and ensure transaction/ID handling, or use a proper domain service.

## 9. Security and Operational Notes for Legacy Data

1. **Password hashes:** never store raw passwords in the DB or logs, and never compare strings directly. Verify existing hashes are compatible with the encoder, and use a migration policy when needed. The H2 demo uses BCrypt; real data may require algorithm upgrades.
2. **Prepared statements:** keep `?` for username and let Spring JDBC bind the parameter. Never concatenate client strings into SQL, including authority queries.
3. **Principle of least privilege:** a DataSource serving read-only authentication only needs SELECT privileges on the required tables/views. If the same DataSource writes accounts, separate permissions by role and endpoint.
4. **Least privilege for accounts:** map granted permissions accurately; never auto-add broad roles when a user lacks authorities. Test low-privilege users and disabled accounts.
5. **Tenant boundaries:** if a username can exist in multiple tenants, the lookup key must carry full context and the tenant source must be trusted. A bad join in the authorities query can cause severe privilege escalation.
6. **Read consistency:** two consecutive SELECTs can observe different DB changes in a concurrent/multi-node system. For strong consistency or immediate revocation, design transaction/cache/session/token policies rather than relying blindly on two separate queries.
7. **Performance:** index usernames, foreign keys, and JOIN columns; check query plans with realistic data volumes, not just a three-user H2 dataset. Never let N+1 queries or heavy role queries bottleneck login.
8. **Fail closed:** connection errors, timeouts, or missing tables/columns must never result in an authenticated user. Ensure monitoring distinguishes infrastructure errors from wrong passwords while public responses leak no account details.
9. **Avoid accidental schema changes:** keep migrations separate from application code; never run demo `schema.sql` against a real database. Coordinate schema/query rollout and rollback under one version.
10. **Connections and secrets:** keep DB passwords in a secret manager/deployment config, use TLS to the DB if required, restrict logging of JDBC parameters, and audit sensitive access.

## 10. Reasoning Exercises

**Exercise A — Wrong column order.** A query returns `SELECT pwd_digest AS password, login_name AS username, active_flag AS enabled ...`. Even though the aliases are accurate, is this fine?

**Answer:** no. Standard `JdbcDaoImpl` relies on **column position** (1=username, 2=password, 3=enabled). You must reorder the SELECT or use a custom mapper if genuinely necessary.

**Exercise B — Missing authorities.** The account query returns Alice with active=true, while the role query returns 0 rows because the join table wasn't seeded. Is `loadUserByUsername` guaranteed to still return the account with an empty authority array?

**Answer:** do not assume that. Standard `JdbcDaoImpl` may throw `UsernameNotFoundException` when no `GrantedAuthority` is loaded; check the exact contract and enforce least-privilege role assignment per business rules.

**Exercise C — ROLE prefix.** The database already returns `ROLE_ADMIN`, yet you call `jdbc.setRolePrefix("ROLE_")`. What happens to `hasRole("ADMIN")`?

**Answer:** it risks failing because the authority name becomes `ROLE_ROLE_ADMIN`. Use a single prefixing strategy.

**Exercise D — User with four permissions.** You put the role JOIN in the user query and get four rows. Is that a valid design?

**Answer:** no. The account query must return a single row; the authorities query is what returns multiple authority rows.

**Exercise E — Database has deletedAt instead of enabled.** Can you return a constant `TRUE AS enabled` for every account?

**Answer:** not if soft-delete/disabled has security significance. Map the active condition to a boolean according to your SQL dialect or use a domain service with an explicit policy.

**Exercise F — Schema uses account ID.** When logging in by username, do you have to enable `setUsernameBasedPrimaryKey(false)` just because the table has an `id` column?

**Answer:** no. If the user query still returns `login_name` at position 1 and the role query joins by ID while filtering by username as in the demo, you do not need to flip that flag.

**Exercise G — Two tenants share login_name.** Should you change `WHERE login_name = ?` to `WHERE login_name = ? AND tenant_id = ?` and simply call `setUsersByUsernameQuery(...)`?

**Answer:** not enough. Standard `JdbcDaoImpl` only binds username for this SQL. You must adjust the lookup/identity mapping mechanism to obtain a verified tenant and pass the second parameter safely.

## 11. Checklist Before Integrating into an Existing System

- [ ] Accurately identified the account table, username/password hash/enabled columns, and authority tables in the real schema.
- [ ] `usersByUsernameQuery` returns **one** record with the exact order username, password, enabled and **one** username placeholder.
- [ ] `authoritiesByUsernameQuery` returns the exact order username, authority; can return multiple rows; tested a user with zero authorities.
- [ ] Verified consistent `ROLE_` or authority naming rules between DB and authorization.
- [ ] Verified hash format against the real `PasswordEncoder`; no raw passwords used in SQL.
- [ ] `DataSource` points to the right DB/schema; app user has proper SELECT permissions and a secure connection.
- [ ] Tested non-existent username, wrong password, disabled/locked, user with multiple roles, user with no roles, and infrastructure errors.
- [ ] No accidental cross-tenant user mixing or queries exposing accounts from another identity domain.
- [ ] If using `JdbcUserDetailsManager` for writes, designed all required DML, transactions, and authorization; did not only change SELECTs.
- [ ] Tested on a production-like dialect, checked performance/indexes, and verified session/cache recovery when account info changes.

**Conclusion:** to integrate JDBC authentication with a legacy schema, keep your existing account store and **map the two SELECT queries to the data contract** of `JdbcDaoImpl`. The user query returns `username, password, enabled` by position; the authority query returns `username, authority`. `DaoAuthenticationProvider` together with `PasswordEncoder` performs password verification, while `SecurityFilterChain` controls HTTP and authorization. When requirements go beyond two SELECTs — complex domain statuses, multi-tenancy, multi-table user management — choose the appropriate mapping layer or custom service rather than breaking the standard SQL contract.

## Official References

- [Spring Security 6.5 — JDBC Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — JdbcDaoImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/jdbc/JdbcDaoImpl.html)
- [Spring Security 6.5 — JdbcUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/JdbcUserDetailsManager.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
