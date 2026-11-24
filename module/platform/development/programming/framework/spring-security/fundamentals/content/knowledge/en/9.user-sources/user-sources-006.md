# Mapping Roles, Permissions, and Statuses from a Database

Suppose an application has two accounts in its database: `mai` and `admin`. Mai has the `STAFF` role, allowed to read documents but not edit them. Admin has the `ADMIN` role, allowed to read and edit documents and open the admin area. The database also records that Mai is active, a colleague is disabled, and another account is locked until the next day.

When a user logs in, Spring Security needs to know **which password hash format is stored, whether the account is still usable, which roles it holds, and which specific permissions it has**. If the application only returns username/password from a repository and ignores role, permission, or status tables, authentication may succeed yet authorize incorrectly, or locked accounts may still be able to log in.

This topic explains how to turn relational data into `UserDetails` and `GrantedAuthority` for Spring Security: **roles**, **permissions/authorities**, **account status (enabled/locked/expired)**, along with harder topics such as multi-tenancy, revoked permissions, concurrent queries, caching, and testing.

The main example is a **Java 17+**, **Spring Boot 4.1.2**, **Spring Security managed by the Boot BOM**, **Spring JDBC + in-memory H2** application. The example demonstrates with a real database and HTTP Basic without requiring an external PostgreSQL/MySQL instance. The passwords in this lesson are dummy data strictly for local runs.

## 1. From Database Tables to Authentication Objects

Three core layers of responsibility:

| Layer | Data it manages | Question it answers |
| --- | --- | --- |
| **Repository/Database** | Account, password hash, role, permission, assignment relations, and current status | What business data is **currently stored**? |
| **`UserDetailsService` and `UserDetails`** | User representation for authentication, including name, password hash, status flags, and authorities | What data does Spring Security need to **check login**? |
| **`Authentication` and authorization** | Principal, authorities received from provider, and request/resource policy | Is the verified subject **allowed to perform this operation**? |

Typical flow with username/password:

~~~text
HTTP Basic / form login
        |
        v
UsernamePasswordAuthenticationToken (unauthenticated)
        |
        v
AuthenticationManager / DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername(username)
                    |
                    v
              Database (app_accounts)
                    |
               +----+------------------------------+
               |                                   |
       password hash + flags               roles -> permissions
               |                                   |
               +----------> UserDetails <----------+
                                |
                                v
           isEnabled / isAccountNonLocked / expiry checks
                       + PasswordEncoder.matches
                                |
                     +----------+----------+
                     |                     |
                    FAIL                  SUCCESS
                     |                     |
          AuthenticationException         v
                                Authentication with authorities
                                             |
                                             v
                                HttpSecurity authorizeHttpRequests
                                             |
                                             v
                                 Controller + domain authorization
~~~

**`UserDetailsService` does not itself verify passwords.** The `loadUserByUsername` method only loads trusted data from the configured source; `DaoAuthenticationProvider` uses `PasswordEncoder` to compare the user-submitted raw password against the hash stored in `UserDetails`. Afterwards, Spring Security checks permissions based on the supplied authorities, depending on policy.

## 2. Distinguishing Role, Permission, Authority, and Status

In many projects, four terms get mixed up:

| Concept | Database example | Representation in Spring Security | Used for |
| --- | --- | --- | --- |
| Role | `STAFF`, `ADMIN` | `ROLE_STAFF`, `ROLE_ADMIN` | Coarse permission group, organizational role |
| Permission | `DOC_READ`, `DOC_WRITE`, `USER_MANAGE` | `DOC_READ`, `DOC_WRITE`, `USER_MANAGE` | Permission on a specific action/feature |
| `GrantedAuthority` | Created from role or permission | `new SimpleGrantedAuthority("DOC_READ")` | Data type consumed by Spring Security's authorization |
| Account status | `enabled`, `locked_until`, `account_expires_at` | Four flags in `UserDetails` | Denies or allows **new authentication** by status |

**Both roles and permissions can become `GrantedAuthority`.** Under default configuration, `hasRole("ADMIN")` looks for the authority `ROLE_ADMIN`, whereas `hasAuthority("DOC_WRITE")` looks for the **exact string** `DOC_WRITE`. Spring Security does not inspect `roles` or `permissions` tables directly; it only sees the authorities mapped by the application or produced by the `AuthenticationProvider`.

Example:

~~~text
Database:
  account mai -> role STAFF
  role STAFF -> permission DOC_READ

UserDetails.getAuthorities() for Mai:
  ROLE_STAFF
  DOC_READ

Checks:
  hasRole("STAFF")          -> true
  hasRole("ADMIN")          -> false
  hasAuthority("DOC_READ")  -> true
  hasAuthority("DOC_WRITE") -> false
~~~

This is the **RBAC with role-permission mapping** model. There is no rule forcing every system to store roles and permissions in two tables; small systems can store authorities directly. Splitting tables helps when one role is assigned to many people and one permission is shared across multiple roles.

### What does the ROLE_ prefix mean?

Assigning via the builder:

~~~java
User.withUsername("mai")
    .password(encodedPassword)
    .roles("STAFF")
    .build();
~~~

Writing `.roles("STAFF")` creates the `ROLE_STAFF` authority. Do not pass `"ROLE_STAFF"` into `.roles(...)`, because the builder automatically adds the prefix and forbids values already starting with `ROLE_`.

However, when fetching data from a `roles` table, you can add the prefix yourself:

~~~java
String roleCodeFromDatabase = "ADMIN";
GrantedAuthority authority =
        new SimpleGrantedAuthority("ROLE_" + roleCodeFromDatabase);
~~~

Then the `hasRole("ADMIN")` rule can match. If the database already stores the full string `ROLE_ADMIN`, **do not** add the prefix again; pick one stable convention right from schema and migration time.

**Common pitfall:** calling both `.roles("STAFF")` and then `.authorities("DOC_READ")` on the same builder can cause the later call to **replace** the authority list rather than automatically merging the two sets. The transparent approach is to **collect roles and permissions into one collection first**, then call `.authorities(allAuthorities)` once.

## 3. Minimal Relational Schema Design

To illustrate the entire topic, we use five tables:

~~~text
app_accounts
  account_id (PK)
  username (UNIQUE)
  password_hash
  enabled
  locked_until_ms
  account_expires_ms
  credentials_expires_ms
        |
        | 1:N
        v
account_roles (account_id, role_code)
        |
        | N:1
        v
roles (role_code PK)
        |
        | 1:N
        v
role_permissions (role_code, permission_code)
        |
        | N:1
        v
permissions (permission_code PK)
~~~

**Function of each table:**

- `app_accounts`: user and credential hash source for username/password login; the stable internal identifier is `account_id`.
- `roles`: role catalog controlled by administrators/system; e.g., `STAFF` or `ADMIN`.
- `permissions`: action catalog; e.g., `DOC_READ`, `DOC_WRITE`.
- `account_roles`: assigns roles to accounts, many-to-many.
- `role_permissions`: assigns specific permissions to roles, many-to-many.

**Key constraints:** use foreign keys, uniqueness, and primary keys to prevent orphan records or duplicate assignments. Roles and permissions must never be taken from client-claimed data; only an authorized administrative workflow may modify these tables.

Never store raw passwords in `password_hash`. The system must use a `PasswordEncoder` configured compatibly with the hash format and have a policy for upgrading work factor when needed. The example uses bcrypt.

### Status and time

The example stores timestamps in `*_ms` columns as epoch milliseconds solely to keep demo SQL simple and avoid DB timestamp syntax differences. With real PostgreSQL/MySQL, you can use `TIMESTAMP WITH TIME ZONE` or an appropriate type with a clear UTC convention.

| Column | Example | Mapping rule |
| --- | --- | --- |
| `enabled` | `true` | `isEnabled()` taken directly from trusted data |
| `locked_until_ms` | Future timestamp | If `now < locked_until`, the account is locked |
| `account_expires_ms` | Past timestamp | If `now >= expiresAt`, the account has expired |
| `credentials_expires_ms` | Past timestamp | If `now >= credentialsExpiresAt`, credentials have expired |
| Time value `NULL` | No expiration set | Corresponding expiration condition does not apply |

The choice "exactly at the expiration timestamp, it is no longer valid" must be consistent across application, DB, and tests. In a multi-node architecture, use reliable clocks/UTC, control clock skew, and never use browser-sent timestamps to decide status.

## 4. A Complete Policy Needs Both Status and Permissions

Suppose Mai's account has `ROLE_STAFF` and `DOC_READ`, yet `enabled=false` because she left the company. You cannot say "Mai has `DOC_READ`, so she can read documents" and ignore status.

For new logins, `DaoAuthenticationProvider` checks the `UserDetails` status flags alongside the password. A disabled or locked account typically **cannot complete authentication**, even with the right password and authorities.

One way to distinguish:

~~~text
Authentication:
  Right password?
  Account enabled/non-locked/non-expired?
  Credentials not expired?
       |
       +--> fail -> do not issue trusted Authentication

Authorization:
  Valid Authentication present?
  Appropriate authority present?
  Allowed on specific record/tenant?
       |
       +--> fail -> deny operation
~~~

**Authentication differs from authorization.** An active account may still lack `DOC_WRITE` and receive 403 when editing documents. A disabled account may receive 401 right at HTTP Basic login. These two codes come from two different decision layers.

### Do not confuse account expired with subscription expired

If a company's service plan expires, you may still want users to log in to renew billing or export data. Do not turn `subscription_expires_at` into `UserDetails.isAccountNonExpired=false` if you only need to block a plan's features. Likewise, an expired membership in tenant A does not mean the user should lose the ability to log into tenant B.

`UserDetails` status is suited for deciding whether to permit **identity authentication**. Plan, organization, or individual resource permissions must be checked at the business authorization layer.

## 5. Hands-On Project: Java 17 + Spring Boot 4.1.2 + H2 + JDBC

This is a Servlet/HTTP Basic application you can study and run locally. Its purpose is to verify **how to load accounts, roles, permissions, and statuses from a database**, not to build a production user system.

Project components:

~~~text
db-security-lab/
  pom.xml
  src/main/resources/
    application.properties
    schema.sql
  src/main/java/com/example/dbsecurity/
    DbSecurityLabApplication.java
    DatabaseUserDetailsService.java
    SecurityConfiguration.java
    DemoController.java
~~~

APIs used:

- `JdbcTemplate` to read the database using parameterized `?` queries.
- `UserDetailsService` to convert account data into `UserDetails`.
- `SimpleGrantedAuthority` to convert roles/permissions into authorities.
- `DaoAuthenticationProvider` with `PasswordEncoder` to verify passwords.
- `SecurityFilterChain` to demonstrate `hasRole` and `hasAuthority`.
- H2 in-memory database so no DB server installation is needed.

### 5.1. pom.xml

Create file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>db-security-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

The Spring Boot parent manages versions of Spring Security, Spring JDBC, H2, and other components via its BOM. Do not add a separate `spring-security-core` version just because you saw a newer version number on Maven Central. `spring-boot-starter-webmvc` is the starter for Spring MVC applications in Boot 4; `spring-boot-starter-web` appeared in many earlier Boot 3 lessons.

### 5.2. Local database configuration

Create `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:securitylab;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql

server.port=8080
~~~

Here H2 runs **in memory**: when the app stops, data is lost. The `sa` account and blank password are local settings for an embedded database, **not a production recommendation**. In a real system using a managed database, secrets live in a secret manager/environment config, connections are secured, database roles have least privilege, and migrations are run via Flyway/Liquibase or an organization-approved tool.

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked_until_ms BIGINT,
    account_expires_ms BIGINT,
    credentials_expires_ms BIGINT
);

CREATE TABLE roles (
    role_code VARCHAR(60) PRIMARY KEY
);

CREATE TABLE permissions (
    permission_code VARCHAR(80) PRIMARY KEY
);

CREATE TABLE account_roles (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(60) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    FOREIGN KEY (account_id) REFERENCES app_accounts(account_id),
    FOREIGN KEY (role_code) REFERENCES roles(role_code)
);

CREATE TABLE role_permissions (
    role_code VARCHAR(60) NOT NULL,
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (role_code, permission_code),
    FOREIGN KEY (role_code) REFERENCES roles(role_code),
    FOREIGN KEY (permission_code) REFERENCES permissions(permission_code)
);
~~~

Composite primary keys prevent assigning the same role/permission twice. Despite SQL constraints, the application must still avoid granting permissions from untrusted input and verify the authority of whoever updates these tables.

### 5.3. Main class and demo data

Create `src/main/java/com/example/dbsecurity/DbSecurityLabApplication.java`:

~~~java
package com.example.dbsecurity;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class DbSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(DbSecurityLabApplication.class, args);
    }

    @Bean
    CommandLineRunner seedData(
            JdbcTemplate jdbc, PasswordEncoder encoder, Clock clock) {
        return args -> {
            jdbc.update("INSERT INTO roles(role_code) VALUES (?)", "STAFF");
            jdbc.update("INSERT INTO roles(role_code) VALUES (?)", "ADMIN");

            for (String code : new String[] {
                    "DOC_READ", "DOC_WRITE", "USER_MANAGE"}) {
                jdbc.update(
                    "INSERT INTO permissions(permission_code) VALUES (?)",
                    code);
            }

            grantPermission(jdbc, "STAFF", "DOC_READ");
            grantPermission(jdbc, "ADMIN", "DOC_READ");
            grantPermission(jdbc, "ADMIN", "DOC_WRITE");
            grantPermission(jdbc, "ADMIN", "USER_MANAGE");

            long now = clock.instant().toEpochMilli();
            long tomorrow = clock.instant()
                    .plus(Duration.ofDays(1)).toEpochMilli();
            long yesterday = clock.instant()
                    .minus(Duration.ofDays(1)).toEpochMilli();

            saveUser(jdbc, encoder, 101L, "mai", true,
                    null, null, null);
            saveUser(jdbc, encoder, 102L, "admin", true,
                    null, null, null);
            saveUser(jdbc, encoder, 103L, "linh", false,
                    null, null, null);
            saveUser(jdbc, encoder, 104L, "khoa", true,
                    tomorrow, null, null);
            saveUser(jdbc, encoder, 105L, "an", true,
                    null, yesterday, null);
            saveUser(jdbc, encoder, 106L, "tue", true,
                    null, null, yesterday);

            grantRole(jdbc, 101L, "STAFF");
            grantRole(jdbc, 102L, "ADMIN");
            grantRole(jdbc, 103L, "STAFF");
            grantRole(jdbc, 104L, "STAFF");
            grantRole(jdbc, 105L, "STAFF");
            grantRole(jdbc, 106L, "STAFF");
        };
    }

    private static void saveUser(
            JdbcTemplate jdbc,
            PasswordEncoder encoder,
            long id,
            String username,
            boolean enabled,
            Long lockedUntil,
            Long accountExpires,
            Long credentialsExpires) {
        jdbc.update(
            "INSERT INTO app_accounts " +
            "(account_id, username, password_hash, enabled, " +
            "locked_until_ms, account_expires_ms, credentials_expires_ms) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            id, username, encoder.encode("demo-password"),
            enabled, lockedUntil, accountExpires, credentialsExpires);
    }

    private static void grantRole(
            JdbcTemplate jdbc, long id, String role) {
        jdbc.update(
            "INSERT INTO account_roles(account_id, role_code) " +
            "VALUES (?, ?)", id, role);
    }

    private static void grantPermission(
            JdbcTemplate jdbc, String role, String permission) {
        jdbc.update(
            "INSERT INTO role_permissions(role_code, permission_code) " +
            "VALUES (?, ?)", role, permission);
    }
}
~~~

This is a **local demo seed** executed at startup, not a production account creation mechanism. The shared password is `demo-password`, bcrypt-hashed by `PasswordEncoder` before writing to the DB. Bcrypt hashes use random salts so hash strings in the DB are **not fixed across runs**, yet login checks still work.

Accounts:

| Username | Demo password | Status | Role |
| --- | --- | --- | --- |
| `mai` | `demo-password` | Active | STAFF |
| `admin` | `demo-password` | Active | ADMIN |
| `linh` | `demo-password` | Disabled | STAFF |
| `khoa` | `demo-password` | Temporarily locked until next day | STAFF |
| `an` | `demo-password` | Account expired since previous day | STAFF |
| `tue` | `demo-password` | Credentials expired since previous day | STAFF |

The `now` variable in the demo illustrates the reference instant, while timestamps are computed from `Clock` and do not need printing. In production, never hardcode passwords, never seed default admin accounts, and never grant `ADMIN` privileges via a runner like this.

### 5.4. UserDetailsService reading data from JDBC

Create `src/main/java/com/example/dbsecurity/DatabaseUserDetailsService.java`:

~~~java
package com.example.dbsecurity;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public DatabaseUserDetailsService(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    private record AccountRow(
            long id,
            String username,
            String passwordHash,
            boolean enabled,
            Long lockedUntilMs,
            Long accountExpiresMs,
            Long credentialsExpiresMs) {
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        List<AccountRow> rows = jdbc.query(
            "SELECT account_id, username, password_hash, enabled, " +
            "locked_until_ms, account_expires_ms, credentials_expires_ms " +
            "FROM app_accounts WHERE username = ?",
            (rs, rowNum) -> new AccountRow(
                rs.getLong("account_id"),
                rs.getString("username"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled"),
                nullableLong(rs, "locked_until_ms"),
                nullableLong(rs, "account_expires_ms"),
                nullableLong(rs, "credentials_expires_ms")),
            username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("Unknown user");
        }

        AccountRow account = rows.get(0);

        List<String> roles = jdbc.queryForList(
            "SELECT role_code FROM account_roles WHERE account_id = ?",
            String.class, account.id());

        List<String> permissions = jdbc.queryForList(
            "SELECT DISTINCT rp.permission_code " +
            "FROM role_permissions rp " +
            "JOIN account_roles ar ON ar.role_code = rp.role_code " +
            "WHERE ar.account_id = ?",
            String.class, account.id());

        Set<String> codes = new TreeSet<>();
        for (String role : roles) {
            codes.add("ROLE_" + role);
        }
        codes.addAll(permissions);

        List<GrantedAuthority> granted = codes.stream()
            .map(SimpleGrantedAuthority::new)
            .map(authority -> (GrantedAuthority) authority)
            .toList();

        long now = clock.millis();
        boolean locked = account.lockedUntilMs() != null
                && now < account.lockedUntilMs();
        boolean accountExpired = account.accountExpiresMs() != null
                && now >= account.accountExpiresMs();
        boolean credentialsExpired =
                account.credentialsExpiresMs() != null
                && now >= account.credentialsExpiresMs();

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(locked)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .authorities(granted)
                .build();
    }

    private static Long nullableLong(ResultSet rs, String column)
            throws SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }
}
~~~

This is the **most important part** of the lesson. Reading top to bottom:

1. `loadUserByUsername` receives the username being processed by authentication and uses JDBC **parameter binding (`?`)**; it never concatenates the username into SQL.
2. If no record exists, it throws `UsernameNotFoundException`, **never returning `null`** and never inventing a fake privileged account.
3. Queries `account_roles` to fetch role codes by the **stable `account_id`**.
4. Joins `account_roles` with `role_permissions` to fetch permissions granted to the account via its roles.
5. Converts roles to `ROLE_...`, while keeping permission codes as-is. Uses `TreeSet` to deduplicate and maintain deterministic order for observation.
6. Computes `locked`, `accountExpired`, and `credentialsExpired` against the current timestamp.
7. Returns Spring Security's `UserDetails` with the **password hash**, status flags, and the aggregated authorities list.

`TreeSet` here is only for in-memory list handling; it does not validate trustworthiness of roles/permissions. Only server-managed roles/permissions in the DB may enter `GrantedAuthority`.

**Do not rewrite this as `.roles(roles).authorities(permissions)` expecting both calls to concatenate lists.** We assemble `granted` first and call `.authorities(granted)` once.

### 5.5. Configuring SecurityFilterChain and PasswordEncoder

Create `src/main/java/com/example/dbsecurity/SecurityConfiguration.java`:

~~~java
package com.example.dbsecurity;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            DatabaseUserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/docs/edit")
                    .hasAuthority("DOC_WRITE")
                .requestMatchers("/docs")
                    .hasAuthority("DOC_READ")
                .requestMatchers("/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

By calling `authenticationProvider(provider)`, this chain uses an explicitly configured `DaoAuthenticationProvider` with `DatabaseUserDetailsService` and `BCryptPasswordEncoder`. The goal is an easy-to-follow learning flow; a normal Boot project can also rely on default authentication configuration when matching beans are declared.

Three illustrative rules:

- `GET /docs` requires the `DOC_READ` authority.
- `GET /docs/edit` requires the `DOC_WRITE` authority.
- `GET /admin` requires the `ADMIN` role, corresponding to the `ROLE_ADMIN` authority.

`anyRequest().authenticated()` is a fallback to prevent undeclared endpoints in the example from being exposed unintentionally. It **does not replace per-record permission checks** in a real system.

There is no `formLogin` in this example. HTTP Basic lets us use `curl` to demonstrate mapping; production must use **HTTPS**, appropriate credential/secret policies, and a suitable login mechanism. Spring Security's default CSRF still needs evaluation if adding state-mutating endpoints, especially in browser/cookie apps; the demo only has non-mutating GETs.

### 5.6. Controller demonstrating authorization

Create `src/main/java/com/example/dbsecurity/DemoController.java`:

~~~java
package com.example.dbsecurity;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/docs")
    public String docs() {
        return "docs-readable";
    }

    @GetMapping("/docs/edit")
    public String edit() {
        return "docs-editable";
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-area";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello-" + authentication.getName();
    }
}
~~~

The controller does not check roles with `if` itself. Spring Security enforces rules before the request reaches the controller. In a real application, write operations should use proper HTTP methods (`POST`, `PATCH`, `PUT`, `DELETE`), enforce CSRF where appropriate, and add record/tenant authorization in the service layer.

### 5.7. Build and run

Requires JDK 17+ and a compatible Maven installation; first run needs access to the dependency repository:

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

If port 8080 is occupied by another program, change `server.port` and update URLs in the test commands. Because H2 is in-memory, stopping and restarting the project recreates the schema and the runner seeds fresh data. The example writes no data to external systems.

In a second terminal, test (the `demo-password` password is for **local demo only**; never pass real passwords on the command line):

~~~bash
curl -s -o /dev/null -w 'mai-docs=%{http_code}\n' \
  -u mai:demo-password http://localhost:8080/docs

curl -s -o /dev/null -w 'mai-edit=%{http_code}\n' \
  -u mai:demo-password http://localhost:8080/docs/edit

curl -s -o /dev/null -w 'admin-edit=%{http_code}\n' \
  -u admin:demo-password http://localhost:8080/docs/edit

curl -s -o /dev/null -w 'admin-area=%{http_code}\n' \
  -u admin:demo-password http://localhost:8080/admin

curl -s -o /dev/null -w 'linh-disabled=%{http_code}\n' \
  -u linh:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'khoa-locked=%{http_code}\n' \
  -u khoa:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'an-expired=%{http_code}\n' \
  -u an:demo-password http://localhost:8080/profile

curl -s -o /dev/null -w 'tue-expired-password=%{http_code}\n' \
  -u tue:demo-password http://localhost:8080/profile
~~~

Expected status results per the project's policies and data:

~~~text
mai-docs=200
mai-edit=403
admin-edit=200
admin-area=200
linh-disabled=401
khoa-locked=401
an-expired=401
tue-expired-password=401
~~~

On Windows PowerShell, call `curl.exe` instead of `curl` if `curl` is aliased; the `\` line continuation belongs to Bash, so on Windows put each command on one line or use PowerShell syntax.

Try one more:

~~~bash
curl -s -u mai:demo-password http://localhost:8080/profile
~~~

Expected body:

~~~text
hello-mai
~~~

Status explanation:

- Mai has `ROLE_STAFF` and `DOC_READ`: allowed to read `/docs` yet lacks `DOC_WRITE`, so `/docs/edit` returns 403.
- Admin has `ROLE_ADMIN`, `DOC_READ`, `DOC_WRITE`, `USER_MANAGE`: allowed into `/admin` and `/docs/edit`.
- Linh disabled, Khoa locked, An account expired, Tue credentials expired: even though the demo password is right, the provider checks status and rejects new authentication; HTTP Basic typically responds with 401.
- An unauthenticated caller hitting `/profile` also gets 401 under HTTP Basic, **which does not mean a wrong password was entered**.

HTTP statuses are analyzed per the demo chain; if form login, custom entry points, proxies, or other configs are added, responses may redirect or change format. **Never publicly disclose "username exists but is locked"** to unauthenticated callers, to reduce account enumeration.

## 6. Note: UserDetails Builder Takes "Bad State" Flags, Interface Takes "Good State" Flags

This is a common mistake when a mapper reads status:

| Domain data | Builder method | Corresponding `UserDetails` method |
| --- | --- | --- |
| `enabled=true` | `.disabled(false)` | `isEnabled()==true` |
| Account currently locked | `.accountLocked(true)` | `isAccountNonLocked()==false` |
| Account expired | `.accountExpired(true)` | `isAccountNonExpired()==false` |
| Credentials expired | `.credentialsExpired(true)` | `isCredentialsNonExpired()==false` |

This syntax is error-prone because the builder is phrased around **error states**, whereas most interface methods contain `Non`.

Wrong example:

~~~java
// WRONG if enabled means the account is active.
.disabled(account.enabled())
~~~

Right example:

~~~java
.disabled(!account.enabled())
~~~

In the lab, all three time conditions are computed from `Clock` rather than reading the system clock inside controllers. You can inject `Clock.fixed(...)` in unit tests to precisely test instants just before, right at, and after expiration. When time equals `account_expires_ms`, `accountExpired` is `true` per the example's convention.

**Note:** if the database has both a `manually_locked` flag and a temporary lock deadline, compute `locked = manuallyLocked || now < lockedUntil` so you do not automatically unlock an administrator-banned account. The demo schema uses only time-based locks to keep the topic focused.

## 7. When to Use JdbcUserDetailsManager Instead of Writing a Custom UserDetailsService?

Spring Security includes `JdbcDaoImpl` implementing `UserDetailsService` and `JdbcUserDetailsManager` extending it to manage users via JDBC. They are useful when your data fits the **default schema** or you adjust the supported queries.

The default JDBC authentication schema consists of `users` and `authorities` tables, typically having username, password, enabled, and authority columns. Spring Security provides separate documentation and sample scripts.

Conceptual example:

~~~java
@Bean
UserDetailsManager users(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
~~~

This is a **configuration fragment** suitable only when you have created the schema matching the default queries or configured custom queries. It has no seed users, no web/security chain, and is not a standalone runnable program.

Comparison:

| Option | Best suited for | Limitations to recognize |
| --- | --- | --- |
| `JdbcUserDetailsManager` with default schema | Small apps wanting standard-structure users/authorities management | Does not automatically know complex domain `role_permissions`/status tables |
| `JdbcDaoImpl` with custom queries | Partially different schema where mapping remains fairly simple | Must understand return column structure and implementation requirements |
| Custom `UserDetailsService` as in demo | Multi-table joins, explicit account status, permissions, auditing, or tenants | You own queries, mapping, performance, fail-closed handling, and tests |
| Custom `AuthenticationProvider` | Authentication mechanism other than JDBC username/password or special requirements | Must ensure verification logic and exceptions are sound; never mark authenticated from unverified data |

Do not assume `JdbcUserDetailsManager` automatically reads `locked_until`, `account_expires_at`, and `credential_expires_at` from an arbitrary business schema. If you need those states, check whether the implementation supports corresponding configuration or whether a custom `UserDetailsService` like in this lesson is required.

## 8. Multi-Level Role-Permission Relations and Overlapping Permissions

An account may have two roles:

~~~text
Role STAFF -> DOC_READ, REPORT_READ
Role REVIEWER -> DOC_READ, DOC_APPROVE
Account mai -> STAFF + REVIEWER
~~~

When merged:

~~~text
ROLE_STAFF
ROLE_REVIEWER
DOC_READ
REPORT_READ
DOC_APPROVE
~~~

The `DOC_READ` permission appears in both roles, yet `UserDetails` only needs one `DOC_READ` authority. You can use `Set` and `DISTINCT` in queries, as in the demo, to avoid duplicates.

### Do not assume ROLE_ADMIN implies every permission

In Spring Security, `hasRole("ADMIN")` only checks for `ROLE_ADMIN` by convention. It **does not automatically grant** `DOC_READ`, `DOC_WRITE`, or `USER_MANAGE`. If the system wants the `ADMIN` role to hold those permissions, they must be mapped from the DB or configured via an explicit `RoleHierarchy`/policy.

A role hierarchy can express `ADMIN > STAFF` per custom rules, yet you should never assume a hierarchy exists if none is configured. Resource-specific permissions still need appropriate policies, even with the `ADMIN` role.

### "Deny" permissions and database records

If there are both `allow` and `deny` tables, a plain `GrantedAuthority` list does not itself resolve deny-overrides/allow-overrides precedence. That is an authorization design decision: it may require a custom `AuthorizationManager`, policy engine, or service logic. Never grant an allow-equivalent authority simply because a permission row with status `DENIED` was found.

**Default rule:** if a trusted permission cannot be determined, never grant broader access. At the same time, do not treat a database failure as "user lacks permission" when the system actually lost verification capability; preserve the real cause in logs and return a safe response.

## 9. Multi-Tenancy: A Role Is Not Necessarily System-Wide

In a SaaS application, Mai may be `ADMIN` in company A yet only `VIEWER` in company B:

~~~text
account_id = 101

memberships:
  (account=101, tenant=A, role=ADMIN)
  (account=101, tenant=B, role=VIEWER)
~~~

If `UserDetailsService` unconditionally flattens all roles into `ROLE_ADMIN`, a `hasRole("ADMIN")` rule could accidentally grant admin privileges **in B as well**. Therefore the demo schema only illustrates **global roles** and **global permissions**.

For multi-tenant apps, define **scope**:

- System-wide roles differ from per-tenant roles.
- Memberships must bind to server-verified account IDs and tenant IDs.
- If a client sends `X-Tenant-Id` or a tenant in the URL, that is a **tenant selection request**, not proof of membership.
- Policy must verify the current account still belongs to the tenant and is permitted the operation and resource.
- In many cases, use permission checks in the service/repository scoped by `tenant_id` instead of stuffing every role from every tenant into shared authorities.

A typical policy:

~~~text
allow(account, action, resource, tenant)
  = authenticated(account)
    AND currentAccountEnabled(account)
    AND isMember(account, tenant)
    AND resource.tenantId == tenant
    AND hasTenantPermission(account, tenant, action, resource)
~~~

This is a business model, not a built-in Spring Security API. Permissions can be enforced via an `AuthorizationManager`, `@PreAuthorize` calling a policy service, or a tenant-scoped data access layer.

**Never rely on a role named `ADMIN` to allow reading arbitrary records.** Guard against IDOR/BOLA: if `/documents/102` receives a client-tampered ID changed from 101 to 102, the server must check ownership/sharing and tenant, not merely the logged-in username.

## 10. DB Data Can Change After Authentication

Suppose at 09:00, Mai logs in and an `Authentication` is created with `DOC_WRITE`. At 09:05, an administrator revokes `DOC_WRITE` from the `role_permissions` table. Mai still holds an HTTP session containing the earlier `Authentication`.

~~~text
09:00 DB: STAFF -> DOC_READ, DOC_WRITE
      login creates Authentication with 2 permissions

09:05 DB: STAFF -> DOC_READ
      role_permissions changed

09:06 Old session:
      Authentication.getAuthorities() may STILL contain DOC_WRITE
      if the application does not refresh/revoke context

09:10 New login:
      UserDetailsService reads DB -> only DOC_READ remains
~~~

**DB changes do not by default immediately strip permissions from every existing session/JWT.** `UserDetailsService` normally participates in **new authentication**; a request reusing an old session may not invoke `loadUserByUsername` again.

Strategies used depending on requirements:

| Case | Applicable strategy | Tradeoff |
| --- | --- | --- |
| Stateless app checking DB per request | Query current status/permissions | Latency and DB load |
| HTTP session storing authorities | Revoke session on role/status change, or refresh by TTL/version | Managing sessions across multiple nodes |
| JWT carrying roles/permissions | Short TTL tokens, refresh, and revocation/version/introspection | Token info may be stale until expiration |
| Sensitive actions | Check current owner/tenant/permission directly in service | Extra per-action check |
| `UserDetails`/permission cache | TTL, event-driven cache invalidation, and versioned grants | Needs race condition and latency control |

There is no single answer. For sensitive actions such as granting admin rights, transferring money, or exporting data, define an **acceptable revocation latency** and test explicitly.

### Be careful when caching UserDetails

Spring Security has a `CredentialsContainer.eraseCredentials()` mechanism to clear sensitive info on authentication results. If a mutable `UserDetails` carrying a password hash is cached and that same object is shared as the principal, credential erasure can mutate the object inside the cache. Do not optimize performance by sharing uncontrolled mutable principals.

Typical solutions are copying `UserDetails` for the authentication flow, limiting cache lifetimes, or separating password hash data from long-lived identity/principals. **Do not casually disable `eraseCredentialsAfterAuthentication`** just to make a cache work.

## 11. Security Requirements When Loading Roles and Permissions from DB

### 11.1. Never accept roles/authorities from the request

Example request body:

~~~json
{
  "username": "mai",
  "role": "ADMIN",
  "permissions": ["DOC_WRITE"]
}
~~~

This is **client-claimed** data. Never use it to build an authenticated `Authentication` or `SimpleGrantedAuthority` for Mai. Roles, permissions, and account status must come from a **trusted source** after identity is verified, managed by a separate administrative workflow.

A classic vulnerability is allowing `POST /register` to accept and save `role=ADMIN` directly into `account_roles`. That is privilege escalation. On self-registration, the server must assign a safe default role and verify authorization for any privileged grants.

### 11.2. Restrict write permissions on security tables

The `account_roles` and `role_permissions` tables hold security policy. Insert/update/delete operations require authorization, transactions, auditing, tenant checks, and sometimes multi-person approval.

Never let an account alter its own `enabled`, `locked_until_ms`, `role_code`, or `permission_code` freely just because it has profile-edit permissions. An "edit profile" API should use a DTO allowlisting editable fields.

### 11.3. Fail closed when the DB cannot be read

If `JdbcTemplate` reports a connection failure, `UserDetailsService` must never fabricate a fake user with `ROLE_USER` and let login proceed. A storage failure means **unable to verify**, which is different from "username does not exist".

Spring Security has `AuthenticationException` subtypes to distinguish `BadCredentialsException` from `AuthenticationServiceException`. Keep the true error cause observable internally, while never returning stack traces, SQL, or DB hostnames to unauthenticated callers.

### 11.4. Use parameter binding and read-only queries

Right example:

~~~java
jdbc.queryForList(
    "SELECT role_code FROM account_roles WHERE account_id = ?",
    String.class, accountId);
~~~

Never concatenate request usernames/tenants directly into SQL. With JPA or Hibernate, also use bound parameters and understand fetch/join behavior to avoid SQL injection and N+1 queries.

The database can grant a **read-only** DB user for authentication queries (unless the app must update lockout counters/status elsewhere). Separate administrative writes to roles/permissions under the principle of least privilege whenever feasible.

### 11.5. Authority naming conventions must be clear

Pick conventions such as:

~~~text
roles.role_code:
  STAFF
  ADMIN

permissions.permission_code:
  DOC_READ
  DOC_WRITE
  USER_MANAGE

Runtime authorities:
  ROLE_STAFF
  ROLE_ADMIN
  DOC_READ
  DOC_WRITE
  USER_MANAGE
~~~

If admins are allowed to create custom role names, validate length, characters, uniqueness, and avoid collisions with key naming conventions. Never let a permission code match a role authority in a confusing way. Migrate existing data before changing conventions.

## 12. Performance and Consistency Under Concurrent Logins

The demo example uses three queries per login: account, roles, permissions. For small systems this is clear enough. As load grows, examine:

1. **Indexes:** unique index on `username` for lookup; PK on `account_roles(account_id, role_code)` helps role lookups; `role_permissions(role_code, permission_code)` helps joins.
2. **N+1 queries:** looping over each role and issuing a separate query for permissions scales queries with role count; in the demo we join once to fetch all permissions.
3. **Data consistency:** if a role changes between the three queries, a request could observe an inconsistent snapshot. High-accuracy systems need appropriate transaction isolation or versioning, not just caching.
4. **Caching:** reduces DB round-trips yet requires managing TTL, invalidation, principal mutation, and post-login locks.
5. **Connection pool:** database outages or connection exhaustion impact logins; configure timeouts and monitoring rather than retrying endlessly on the same request.
6. **Query projection:** select only columns needed for authentication rather than loading entire entity graphs or sensitive profile fields.
7. **Case sensitivity:** decide whether usernames/emails are case-sensitive; DB collation, normalization, and unique indexes must align.
8. **Resource authorization:** per-tenant/per-record permissions may need dedicated queries rather than cramming all record attributes into tokens.

You can design an `AuthSnapshot` holding ID, version, authorities, and status loaded consistently within a single transaction, yet you still need a refresh strategy when permissions change. Never assume a DB snapshot remains up-to-date indefinitely across a session.

### Database outages and authorization

An **unsafe** pattern is: when permission queries fail, add `ROLE_ADMIN` by default "to avoid downtime". Another pattern that hinders operations is pretending every DB outage is a wrong password. Deny access when unable to verify, preserve accurate system errors for metrics/auditing, and return an appropriate external response.

## 13. Multi-Layer Mapping Tests

You can test at three layers:

- **Data layer:** SQL joins return the right roles and permissions for an account without inflating permissions through duplicate relations.
- **Authentication layer:** `UserDetailsService` supplies the right hash, flags, and authorities; `DaoAuthenticationProvider` rejects disabled/locked/expired accounts and wrong passwords.
- **HTTP authorization layer:** `/docs`, `/docs/edit`, and `/admin` actually return the expected statuses through the filter chain.

Minimum test matrix:

| Case | Expectation |
| --- | --- |
| Mai has STAFF -> DOC_READ | `hasRole("STAFF")` and `hasAuthority("DOC_READ")` true |
| Mai lacks DOC_WRITE | `GET /docs/edit` returns 403 on valid login |
| Admin has ADMIN -> DOC_WRITE | `GET /admin` and `GET /docs/edit` return 200 |
| Mai's password wrong | Authentication fails, HTTP Basic usually 401 |
| Non-existent username | Authentication fails; response does not enumerate accounts |
| Linh disabled | Cannot create new login even with right password |
| Khoa locked until future time | Cannot log in before `locked_until_ms` |
| Clock exactly at `locked_until_ms` | Time lock clears per the example's convention |
| An account expired | Cannot create new login despite having STAFF role |
| Tue credentials expired | Cannot create new login despite matching password hash |
| Multiple roles sharing DOC_READ | `UserDetails` does not contain duplicate DOC_READ |
| DOC_WRITE revoked right after login | Test stale session/token per refresh/revocation policy |
| Admin role in tenant A, request to tenant B | Blocked if lacking membership/permission in B |
| Temporary DB roles/permissions error | Does not grant fallback roles; logs system error |
| Concurrent status change and login | Controlled transactions, races, and revocation latency |

Do not rely solely on `@WithMockUser(roles="ADMIN")` to conclude **database mapping works**: that annotation builds a pre-authenticated `Authentication`, usually bypassing `UserDetailsService` and `DaoAuthenticationProvider`. It is fine for testing policies, yet verifying the data pipeline requires sending credentials through a real login or calling the configured `AuthenticationManager`.

### Inspecting actual authorities

In a test environment, you can inspect:

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

for (GrantedAuthority authority : auth.getAuthorities()) {
    System.out.println(authority.getAuthority());
}
~~~

This is a fragment requiring imports and an authenticated security context; not a standalone program. **Do not expose this code as a public production endpoint.** Starting in Spring Security 7, providers may add factor-related authorities (such as `FACTOR_PASSWORD`), so in tests assert that **expected business permissions are present in the set** rather than always asserting exact collection size equal to DB role/permission count.

## 14. Common Mistakes When Writing Mappers

1. **"Storing role ADMIN in the DB lets Spring Security find it automatically."** No: the app must load and map it into an authority.
2. **"`hasRole("ADMIN")` checks for unprefixed `ADMIN`."** By default it checks for `ROLE_ADMIN`.
3. **"Calling `.roles(...)` then `.authorities(...)` appends both sets."** Never assume that; merge first and call once.
4. **"Role ADMIN automatically includes all permissions."** No: permissions must be granted or backed by an explicit hierarchy/policy.
5. **"Permission DOC_WRITE and ROLE_DOC_WRITE are the same thing."** No; they are two distinct authority strings.
6. **"Having `enabled=true` guarantees login succeeds."** Locked, account expiry, credential expiry, and password verification also apply.
7. **"`.disabled(account.enabled())` keeps the account active."** Wrong: inverted logic.
8. **"`locked_until` passed yet flag stays false forever."** Likely the mapper/cached `UserDetails` did not recompute or the cache was not invalidated.
9. **"Using email as the join key for roles is always fine."** Emails can change; an immutable internal ID is usually safer.
10. **"Assigning roles from registration JSON is convenient."** Privilege escalation vulnerability.
11. **"An account with ADMIN role in tenant A is admin across the whole system."** Wrong when permissions are tenant-scoped.
12. **"Changing roles in the database takes effect immediately in all sessions/JWTs."** Not by default.
13. **"When a DB query fails, just give the user ROLE_USER to keep things running."** Never grant permissions when verification fails.
14. **"Multiple rows in a role-permission join mean distinct permissions."** Use `DISTINCT`/`Set` to deduplicate.
15. **"UserDetailsService compares passwords itself."** Wrong: the provider uses `PasswordEncoder`.
16. **"A DB password hash is safe to return in a DTO because it's not plaintext."** No; hashes are still sensitive.
17. **"UserDetailsService returns `null` when an account is missing."** Violates the contract; throw `UsernameNotFoundException`.
18. **"If there are no authorities, auto-add ADMIN to avoid errors."** No; missing permissions mean grant nothing.
19. **"`@PreAuthorize` works without enabling method security."** Typical setups require `@EnableMethodSecurity`; the main example uses web URL rules.
20. **"A single `hasAuthority("DOC_READ")` protects viewing all documents."** No; owner/tenant/object-level authorization is still required.
21. **"Cached roles always stay in sync with the DB."** No; cache TTL and invalidation must be designed.
22. **"Adding an account to the DB is enough to log in."** You also need a compatible hash, valid status, roles/permissions, and `SecurityFilterChain`/provider.
23. **"Concatenating username in SQL is fine because the user is logging in."** Login input is untrusted; always bind parameters.
24. **"A 403 means wrong password."** No: 403 typically means missing permission/CSRF; Basic authentication failures typically return 401.

## 15. Self-Practice Exercises

**Exercise 1 — Add a new role.** Add `REVIEWER` to the `roles` table, granting `DOC_READ` and `DOC_APPROVE` to that role. Assign the role to Mai. Verify `UserDetails.getAuthorities()` contains `ROLE_STAFF`, `ROLE_REVIEWER`, `DOC_READ`, `DOC_APPROVE` and does not contain `DOC_READ` twice.

**Exercise 2 — Time-based status checks.** Set `locked_until_ms` just before and just after a timestamp supplied by `Clock.fixed`, and verify `UserDetails.isAccountNonLocked()`. Define the boundary precisely with `now < lockedUntil`.

**Exercise 3 — Grant permissions without a role.** Consider an `account_permissions(account_id, permission_code)` schema to support direct exceptions. If added, define allow/deny precedence, authorized grantors, and update the mapper without dropping role-derived permissions.

**Exercise 4 — Revoke permission after login.** Grant Mai `DOC_WRITE`, log in using a stateful session, revoke `DOC_WRITE` in the DB, and call the API again. Observe whether the old permission persists; propose an invalidation/refresh policy matching the system's latency requirements.

**Exercise 5 — Multi-tenancy.** Add `tenant_id` to memberships, making Mai ADMIN in tenant A and VIEWER in tenant B. Verify requests to tenant B resources do not inherit ADMIN privileges from A.

**Exercise 6 — Database failure.** Simulate a temporary DB outage during login. Ensure the system does not construct a fake `UserDetails`, does not auto-grant authorities, and classifies service errors for operations to handle.

## 16. Self-Check Questions

**Q1.** The database stores `STAFF`, `ADMIN`. When using `hasRole("ADMIN")` with the default convention, which authority is required?

*Answer:* `ROLE_ADMIN`. The mapper must prepend `ROLE_` if the database stores unprefixed role codes.

**Q2.** Does `hasAuthority("DOC_WRITE")` automatically recognize `ROLE_ADMIN`?

*Answer:* No. It checks for the exact authority string `DOC_WRITE`; that permission must be granted via the DB or a corresponding policy.

**Q3.** Does `UserDetailsService` need to call `PasswordEncoder.matches` when reading a user?

*Answer:* Not in the standard `DaoAuthenticationProvider` flow. The service loads username/hash/flags/authorities; the provider compares credentials.

**Q4.** If `.disabled(account.enabled())` is used when `enabled=true`, what happens?

*Answer:* Marks the user disabled, inverting the data's meaning. It should be `.disabled(!account.enabled())`.

**Q5.** A user has two roles that both grant `DOC_READ`. Do you need two `SimpleGrantedAuthority("DOC_READ")` entries?

*Answer:* No. Use `DISTINCT` in SQL or a `Set` in the mapper to deduplicate.

**Q6.** Why should you not take a role from `POST /register` and create an `Authentication` with `ROLE_ADMIN`?

*Answer:* Clients could grant themselves administrative privileges. Only role data managed by a trusted source and authorized workflow may be used to build authorities.

**Q7.** After an admin changes roles in the DB, do all `Authentication` objects currently in sessions update automatically?

*Answer:* Not by default. You must design session/JWT revocation/refresh, cache invalidation, or live authorization checks.

**Q8.** Why should a `ROLE_ADMIN` from tenant A not automatically apply in tenant B?

*Answer:* It lacks tenant scope; authorization must bind roles/memberships to the right tenant and resource.

**Q9.** Does default `JdbcUserDetailsManager` automatically read `locked_until_ms` and `role_permissions` in a custom schema?

*Answer:* No; its default queries target the standard JDBC `users`/`authorities` schema. Complex mapping requires customizing queries or implementing a custom `UserDetailsService`.

**Q10.** A DB role query throws a connection error. Should you grant a default `ROLE_USER` so the app keeps working?

*Answer:* No. Being unable to verify permissions means access must be denied, while classifying the infrastructure failure appropriately for monitoring.

**Q11.** If the account status has expired while the `DOC_READ` permission remains in the DB, can the user log in?

*Answer:* With `DaoAuthenticationProvider` enforcing standard `UserDetails` checks, an expired account cannot establish a new authentication even if roles/permissions still exist.

**Q12.** What else must be checked beyond `hasAuthority("DOC_READ")` when reading a specific document?

*Answer:* Owner, tenant, membership, data status, and sharing policy of that record. A coarse authority does not itself perform object-level authorization.

## 17. Checklist Before Applying to a Real System

- [ ] Clear schema for accounts, roles, permissions, and assignment relations; appropriate foreign keys and unique/indexes.
- [ ] **Stable account ID**, never using mutable display names or emails as long-term permission keys.
- [ ] Passwords stored with secure hashes, `PasswordEncoder` properly managed, and hashes never returned to clients.
- [ ] `UserDetailsService` reads real data from a trusted source, uses parameter binding, and never returns `null`.
- [ ] Roles mapped properly to `ROLE_...`, permissions to exact authority codes; no double prefixing.
- [ ] Merge roles and permissions before assigning to `UserDetails`, deduplicating intentionally.
- [ ] Enabled, locked, account expired, and credentials expired converted in the right sign direction into `UserDetails` flags.
- [ ] Timezone/UTC rules and expiry boundaries agreed upon and tested using `Clock`.
- [ ] `DaoAuthenticationProvider` has the right `UserDetailsService` and `PasswordEncoder`; `SecurityFilterChain` has appropriate rules.
- [ ] Never accept permissions from client-claimed requests; APIs creating/editing permissions enforce authorization, tenant checks, auditing, and transactions.
- [ ] Owner/tenant/object-level permission checks exist beyond functional authorities.
- [ ] Strategy exists when DB roles/statuses change post-login: session/JWT revocation, refresh, versioning, or policy lookup.
- [ ] User cache does not share mutable `UserDetails` whose credential erasure breaks subsequent logins.
- [ ] On DB errors, never grant fallback permissions; logs/metrics preserve real causes for recovery.
- [ ] Optimize queries with proper indexes/joins, avoiding N+1 and controlling snapshots/transactions when needed.
- [ ] Tests cover sufficient/missing permissions, non-existent users, wrong passwords, locked, disabled, expired, and multiple roles.
- [ ] Test revoked permissions on existing sessions/tokens per the security SLA.
- [ ] Production uses migrations, backups, secrets/TLS, auditing, Security patches, and a least-privilege DB user.

**A useful mental formula:** the database states which roles, permissions, and statuses an account currently holds; `UserDetailsService` converts them into **password hash + flags + GrantedAuthority**; `DaoAuthenticationProvider` decides whether the login attempt is trustworthy; `SecurityFilterChain` and service policies decide **which actions that subject may perform, on which data**. Keeping responsibilities cleanly separated avoids both over-granting permissions and ineffective locks/expirations.

### Official Documentation

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — JDBC Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html)
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User Builder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
