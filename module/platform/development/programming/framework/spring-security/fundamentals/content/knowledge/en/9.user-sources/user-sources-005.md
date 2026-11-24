# JDBC User Store and Business Domain Store via Custom UserDetailsService

## 1. Why Must You Choose a User Source?

In the first lessons of Spring Security, you can create a few users with **InMemoryUserDetailsManager** to test HTTP Basic or form login. When building a real application, accounts need to survive restarts, have administrable permissions, get locked or revoked, change passwords, and link to business data. At that point, authentication info and permissions usually live in a database or identity management system.

Spring Security provides two common paths when using a relational database:

- **JdbcDaoImpl and JdbcUserDetailsManager:** built-in ways to read accounts and permissions via JDBC, typically corresponding to `users`/`authorities` tables following Spring Security's schema.
- **Custom UserDetailsService:** reads your application's existing account/role tables and translates them into `UserDetails` matching the Spring Security contract.

Both sources can share the same **DaoAuthenticationProvider**, **PasswordEncoder**, and **SecurityFilterChain**. The difference lies in where accounts are stored, the SQL queries, and the logic converting status/roles into objects for authentication.

This lesson uses **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, and Spring MVC/Servlet**; the demo runs with **Spring JDBC and in-memory H2**. Versions are chosen to explain APIs; production must choose a still-supported release and apply security patches, a persistent database, and proper operational procedures.

### Learning Objectives

After this lesson, you can:

1. Distinguish UserDetailsService, UserDetails, UserDetailsManager, JdbcDaoImpl, JdbcUserDetailsManager, and DaoAuthenticationProvider.
2. Understand the `users`/`authorities` schema and default JDBC SQL queries.
3. Build a UserDetailsService reading business domain tables `app_users`/`app_user_roles`.
4. Correctly map BCrypt password hashes, enabled, locked, and authorities.
5. Run the same application under the **jdbc** and **domain** profiles to compare.
6. Test the 200, 401, and 403 branches with curl and MockMvc.
7. Know when to customize JDBC manager queries and when a separate service is needed.
8. Avoid bugs around SQL injection, `ROLE_` prefix, user duplication, stale caches, schema migrations, and per-resource permissions.

## 2. Where Does the User Source Sit in the Authentication Flow?

For HTTP Basic or form login, a filter extracts username/password, creates an unauthenticated Authentication, and passes it to AuthenticationManager. The appropriate provider, usually **DaoAuthenticationProvider**, uses UserDetailsService to find the account and PasswordEncoder to verify the credential.

~~~text
HTTP Basic / Form login
         |
         v
AuthenticationFilter
         |
         v
UsernamePasswordAuthenticationToken (unauthenticated)
         |
         v
AuthenticationManager / ProviderManager
         |
         v
DaoAuthenticationProvider
         |-- loadUserByUsername(username)
         |          |
         |          v
         |      UserDetailsService
         |       /          \
         |      /            \
         | JdbcDaoImpl     Custom Service
         | users/roles     app_users/app_roles
         |      \            /
         |       \          /
         |        UserDetails
         |-- PasswordEncoder.matches(raw, encoded)
         |-- Check enabled, locked, expired
         |
         +-- SUCCESS -> Authentication authenticated
         |                  |
         |                  v
         |             SecurityContext
         |                  |
         |                  v
         |              Authorization
         |
         +-- FAILURE -> AuthenticationException
~~~

The diagram omits other filters to focus on the user source. **UserDetailsService only looks up the account**; it does not itself mark the caller authenticated and does not itself return HTTP 401. The provider/manager decides authentication; the filter/entry point handles the HTTP response.

### 2.1. Responsibility Table

| Component | Role |
| --- | --- |
| **UserDetailsService** | loadUserByUsername(String), returns UserDetails or throws UsernameNotFoundException |
| **UserDetails** | Username, encoded password, granted authorities, enabled/nonLocked/nonExpired status |
| **UserDetailsManager** | Adds user management operations: create/update/delete/changePassword/userExists... |
| **JdbcDaoImpl** | UserDetailsService using JDBC queries to read `users` and `authorities` |
| **JdbcUserDetailsManager** | Extends JdbcDaoImpl, implements UserDetailsManager to manage users via SQL |
| **DaoAuthenticationProvider** | Verifies username/password using UserDetailsService and PasswordEncoder |
| **PasswordEncoder** | Generates hashes and runs matches(rawPassword, hash) |
| **DataSource** | DB connection source used by JDBC manager and JdbcTemplate |
| **SecurityFilterChain** | URL rules, httpBasic/formLogin, and security filters |
| **Authentication** | Verified identity/authorities result |

### 2.2. Finding a username does not prove the password is correct

Suppose the user table has a row for alice. UserDetailsService loading that row successfully only proves the system **has the record**. The caller must still present valid credentials. DaoAuthenticationProvider uses PasswordEncoder.matches to verify.

Do not follow dangerous logic like: "If SELECT finds a user, return an authenticated UsernamePasswordAuthenticationToken." That allows an attacker to impersonate any existing username.

### 2.3. Do not return UserDetails in HTTP JSON

UserDetails holds the encoded password for the provider to check. A BCrypt hash is still a sensitive credential and must never be sent to the frontend or written to logs. Controllers should return a DTO containing only allowed fields instead of returning raw UserDetails, Authentication, or JPA entities.

## 3. Approach A — JdbcDaoImpl and JdbcUserDetailsManager

### 3.1. What tables does JdbcDaoImpl understand?

**JdbcDaoImpl** is a UserDetailsService implementation supporting default queries that read:

- Table **users**: username, password hash, enabled.
- Table **authorities**: username, authority.

An H2 schema example compatible with default queries:

~~~sql
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_authorities UNIQUE (username, authority)
);
~~~

Spring Security provides different schema scripts by database dialect. The example above uses H2 data types, not a mandatory copy-paste schema for PostgreSQL/Oracle/MySQL. In a real product, collation, case sensitivity, indexes, and constraints must match the username policy.

JdbcDaoImpl loads an account by querying username, then fetches authorities. It knows the **enabled** flag, yet the default schema does not automatically model all business states such as lock reason, tenant, subscription, or password reset workflow.

### 3.2. How does JdbcUserDetailsManager differ from JdbcDaoImpl?

**JdbcUserDetailsManager** extends JdbcDaoImpl and implements UserDetailsManager. In addition to reading accounts and authorities for authentication, it has user management methods such as createUser, updateUser, deleteUser, userExists, and changePassword.

This is useful when an app uses a Spring Security-compatible schema and needs simple account administration. However, it **does not replace full enterprise user management**: registration/email verification, MFA, auditing, role management, logging out all devices, brute-force defense, and password reset workflows still need to be designed.

### 3.3. Authorities and the ROLE_ prefix

Values stored in the authorities table are explicit permission strings, for example:

~~~text
username=learner, authority=ROLE_LEARNER
username=admin,   authority=ROLE_ADMIN
~~~

In standard configuration, **hasRole("ADMIN")** checks for the **ROLE_ADMIN** authority. If the database stores only ADMIN, the app may return 403 even after successful login.

You can design permissions without `ROLE_` such as ORDER_READ and use hasAuthority("ORDER_READ"). What matters is that role/authority conventions stay consistent from the database to Authentication and SecurityFilterChain.

### 3.4. When should you choose the JDBC manager?

When the app has fairly simple accounts, can use the standard schema or a compatible variant, wants minimal query code, and needs basic user CRUD. Do not force a complex domain schema into this pattern if significant mapping or tenant logic is required.

If you only need to read from a different schema, you can customize the SELECT queries; however, write operations in JdbcUserDetailsManager also have their own SQL. Changing two SELECTs does not mean createUser/updateUser/deleteUser will automatically understand business tables.

## 4. Approach B — Custom UserDetailsService for a Business Domain Store

Suppose the existing database has:

~~~text
app_users
    id                  BIGINT PRIMARY KEY
    login_name          VARCHAR UNIQUE
    password_hash       VARCHAR
    enabled_flag        BOOLEAN
    locked_flag         BOOLEAN

app_user_roles
    user_id             FK -> app_users.id
    authority           VARCHAR
~~~

Real tables may add email, profile, tenant, verification status, failed attempts, password history, or employee/customer relationships. They do not have to match the JDBC manager's users/authorities tables.

A **custom UserDetailsService** translates those tables into UserDetails understood by DaoAuthenticationProvider. Because the provider does not need to know the schema, security config does not have to change when swapping stores.

### 4.1. Service contract

The method to implement:

~~~java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    // Read account and authorities from trusted source;
    // return UserDetails; if username is missing, throw exception.
}
~~~

This is a **method snippet inside a class implementing UserDetailsService**, not a standalone Java file. The service should:

1. Look up the username normalized per system policy.
2. If no account exists, throw **UsernameNotFoundException** rather than returning null.
3. Never verify raw passwords in the service.
4. Return the encoded password in the PasswordEncoder's expected format.
5. Map enabled/locked/expired status from a trusted source.
6. Map authorities from the database, not from client-claimed roles.
7. Never return an entire complex JPA entity as the principal.
8. Use prepared statements/JdbcTemplate parameters, never concatenating username directly into SQL.
9. Distinguish user-not-found errors from DB connection failures.
10. Enforce username uniqueness per tenant/collation policy.

### 4.2. Account status

UserDetails has the flags enabled, accountNonLocked, accountNonExpired, and credentialsNonExpired. Even a single disabled or locked flag can cause authentication to fail at the provider. If business logic has multiple statuses (pending, suspended, expired), map them explicitly rather than marking everything active=true just to allow login.

In the demo, the custom service maps enabled_flag to disabled and locked_flag to accountLocked. The standard JDBC schema only represents enabled, so the JDBC demo creates a disabled user for comparison.

### 4.3. Querying roles

An account can carry multiple GrantedAuthorities. If the database stores the string ROLE_ADMIN, the service can create **SimpleGrantedAuthority("ROLE_ADMIN")**. If using User.withUsername(...).roles("ADMIN"), the builder also generates ROLE_ADMIN. Do not pass "ROLE_ADMIN" into roles(...) if the builder adds the prefix automatically; when reading already-prefixed strings, use **authorities(...)**.

## 5. Demo: One Project with Both jdbc and domain Profiles

We will create a single Spring Boot project with two authentication sources:

| Profile | Created UserDetailsService bean | Tables |
| --- | --- | --- |
| **jdbc** | JdbcUserDetailsManager | users, authorities |
| **domain** | DomainUserDetailsService | app_users, app_user_roles |

They are not active at the same time. Endpoints and role rules are identical so **the same set of requests** tests both approaches. Data is seeded at startup for learning; production must not seed demo passwords or use in-memory H2.

### 5.1. Dependencies

Create a Spring Initializr project with Spring Boot 3.3.x, Java 17+, Gradle Groovy DSL, and Gradle Wrapper. In the **dependencies** block of build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the dependencies block of a project that already has Boot plugin/BOM configured, not a complete standalone build.gradle. The JDBC starter provides JdbcTemplate/DataSource integration; the H2 driver is for the demo only.

### 5.2. application.properties

Create file **src/main/resources/application.properties**:

~~~properties
spring.datasource.url=jdbc:h2:mem:userstore;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.sql.init.mode=always
spring.profiles.default=jdbc
~~~

When no active profile is passed, the default is **jdbc**. When running with **--spring.profiles.active=domain**, Spring activates the domain profile instead.

In-memory H2 does not preserve data across JVM restarts. DB_CLOSE_DELAY=-1 only keeps the database in the JVM after the last connection closes without creating a persistent file. spring.sql.init.mode=always runs schema.sql on demo startup; with a production DB, use Flyway/Liquibase and manage migrations explicitly.

### 5.3. schema.sql

Create file **src/main/resources/schema.sql**:

~~~sql
-- Standard read/write schema of Spring Security JDBC.
CREATE TABLE users (
    username VARCHAR(50) NOT NULL PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_authorities UNIQUE (username, authority)
);

-- Custom business domain schema.
CREATE TABLE app_users (
    id BIGINT NOT NULL PRIMARY KEY,
    login_name VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled_flag BOOLEAN NOT NULL,
    locked_flag BOOLEAN NOT NULL
);

CREATE TABLE app_user_roles (
    user_id BIGINT NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_app_roles
        FOREIGN KEY (user_id) REFERENCES app_users(id),
    CONSTRAINT pk_app_roles PRIMARY KEY (user_id, authority)
);
~~~

Both sets of tables are created in the demo H2 database, yet only the user source for the **active profile** is used by Spring Security.

### 5.4. Complete Java source

Create file **src/main/java/com/example/userstore/UserStoreApplication.java**:

~~~java
package com.example.userstore;

import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserStoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserStoreApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/lesson")
                    .hasRole("LEARNER")
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Profile("jdbc")
    JdbcUserDetailsManager jdbcUsers(DataSource ds) {
        return new JdbcUserDetailsManager(ds);
    }

    @Bean
    @Profile("jdbc")
    CommandLineRunner seedJdbc(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("learner")) {
                users.createUser(User.withUsername("learner")
                    .password(encoder.encode("learn123"))
                    .roles("LEARNER")
                    .build());
            }
            if (!users.userExists("admin")) {
                users.createUser(User.withUsername("admin")
                    .password(encoder.encode("admin123"))
                    .roles("ADMIN")
                    .build());
            }
            if (!users.userExists("suspended")) {
                users.createUser(User.withUsername("suspended")
                    .password(encoder.encode("suspend123"))
                    .roles("LEARNER")
                    .disabled(true)
                    .build());
            }
        };
    }

    @Bean
    @Profile("domain")
    UserDetailsService domainUsers(JdbcTemplate jdbc) {
        return new DomainUserDetailsService(jdbc);
    }

    @Bean
    @Profile("domain")
    CommandLineRunner seedDomain(
            JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1001L, "learner", encoder.encode("learn123"),
                true, false
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1001L, "ROLE_LEARNER"
            );

            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1002L, "admin", encoder.encode("admin123"),
                true, false
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1002L, "ROLE_ADMIN"
            );

            jdbc.update(
                "INSERT INTO app_users " +
                "(id, login_name, password_hash, enabled_flag, " +
                "locked_flag) VALUES (?, ?, ?, ?, ?)",
                1003L, "suspended",
                encoder.encode("suspend123"), false, true
            );
            jdbc.update(
                "INSERT INTO app_user_roles (user_id, authority) " +
                "VALUES (?, ?)",
                1003L, "ROLE_LEARNER"
            );
        };
    }
}

record AccountRow(
    long id,
    String loginName,
    String passwordHash,
    boolean enabled,
    boolean locked
) {}

final class DomainUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;

    DomainUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<AccountRow> rows = jdbc.query(
            "SELECT id, login_name, password_hash, " +
            "enabled_flag, locked_flag " +
            "FROM app_users WHERE login_name = ?",
            (rs, rowNum) -> new AccountRow(
                rs.getLong("id"),
                rs.getString("login_name"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled_flag"),
                rs.getBoolean("locked_flag")
            ),
            username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }
        if (rows.size() != 1) {
            throw new IllegalStateException(
                "Duplicate login name in account store");
        }

        AccountRow account = rows.get(0);

        List<SimpleGrantedAuthority> authorities = jdbc.query(
            "SELECT authority FROM app_user_roles WHERE user_id = ?",
            (rs, rowNum) ->
                new SimpleGrantedAuthority(rs.getString("authority")),
            account.id()
        );

        return User.withUsername(account.loginName())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .accountLocked(account.locked())
            .authorities(authorities)
            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        var authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", authorities
        );
    }

    @GetMapping("/lesson")
    String lessonEndpoint() {
        return "lesson OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is **a complete Java file inside the Boot project**, paired with the listed application.properties and schema.sql. The public class matches the filename, with the record and helper classes in the same package; Spring Boot detects DemoEndpoints via component scan. Java 17 provides records, var, and Stream.toList.

### 5.5. Analyzing wiring by profile

**In jdbc mode:**

- The JdbcUserDetailsManager bean belongs to the jdbc profile and implements UserDetailsService.
- The seedJdbc runner creates three users using createUser and encoded passwords. The jdbc manager writes to users/authorities.
- DaoAuthenticationProvider can use the UserDetailsService and PasswordEncoder beans to verify login credentials.
- The hasRole rules do not depend on how users were queried from H2.

**In domain mode:**

- The DomainUserDetailsService bean belongs to the domain profile.
- The seedDomain runner inserts into app_users/app_user_roles.
- loadUserByUsername reads the account using parameterized SQL, reads authorities via user_id, and builds UserDetails.
- DaoAuthenticationProvider uses PasswordEncoder to verify the hash returned by the service.

**Do not activate both profiles simultaneously in this lesson.** If multiple UserDetailsService/AuthenticationProvider beans exist at once, Spring Security's selection of provider/manager is no longer trivial; you must explicitly configure user sources, authentication mechanisms, and priority order.

### 5.6. Why is there a shared PasswordEncoder bean?

UserDetailsService **does not compare passwords**. Both JdbcUserDetailsManager and the custom service only return the **stored hash**. BCryptPasswordEncoder compares the raw password from HTTP Basic against the hash. If you change the encoder while the DB contains hashes from another mechanism, authentication may fail across the board.

In products with multiple hash types, use **DelegatingPasswordEncoder** with appropriate algorithm prefixes, a hash upgrade process, and thorough tests. Never enable NoOpPasswordEncoder in production.

### 5.7. Why does the query use a question mark?

In DomainUserDetailsService:

~~~java
List<AccountRow> rows = jdbc.query(
    "SELECT id, login_name, password_hash, " +
    "enabled_flag, locked_flag " +
    "FROM app_users WHERE login_name = ?",
    (rs, rowNum) -> new AccountRow(
        rs.getLong("id"),
        rs.getString("login_name"),
        rs.getString("password_hash"),
        rs.getBoolean("enabled_flag"),
        rs.getBoolean("locked_flag")
    ),
    username
);
~~~

**The ? is a placeholder** bound by JdbcTemplate to username, preventing SQL injection and escaping bugs. Never concatenate client-supplied usernames directly into SQL strings.

Real applications also need policies for case sensitivity/Unicode normalization, username length limits, and unique indexes. Do not silently trim or lowercase without aligning policy and existing data.

### 5.8. Why does UserDetailsService not handle HTTP 401?

When a username is missing, the service throws UsernameNotFoundException; DaoAuthenticationProvider/AuthenticationManager handles the AuthenticationException, and the filter and AuthenticationEntryPoint decide the HTTP response. The service does not access HttpServletResponse or return error JSON itself.

If the database times out or has a schema error, report the infrastructure error properly to monitoring; do not catch every DataAccessException and turn it into UsernameNotFoundException. Public responses should hide SQL details and stack traces.

## 6. Running Both Profiles and Comparing Results

### 6.1. Running JDBC

Per application.properties, the default profile is jdbc:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. Boot creates in-memory H2, runs schema.sql, and seeds users via JdbcUserDetailsManager.

### 6.2. Running the business domain store

Stop the process in jdbc mode, then run:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=domain'
~~~

PowerShell: **.\gradlew.bat bootRun --args='--spring.profiles.active=domain'**.

Domain mode seeds data into app_users/app_user_roles and uses DomainUserDetailsService. Neither Controller nor SecurityFilterChain changes when switching profiles. If the previous process is still running on port 8080, stop it first.

### 6.3. Calling the same set of HTTP requests

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/lesson
curl -i -u learner:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/lesson
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u suspended:suspend123 http://localhost:8080/me
curl -i -u unknown:wrong http://localhost:8080/me
~~~

On PowerShell you may need **curl.exe** because curl is an alias. Hardcoded passwords are only for localhost demos. To avoid passwords appearing in shell history, you can run **curl -i -u learner URL**, then enter the password at the prompt. HTTP Basic transmits credentials in Base64, so HTTPS is required over a network.

### 6.4. Expected result matrix

| Request | Profile jdbc | Profile domain | Explanation |
| --- | --- | --- | --- |
| GET /public anonymous | **200** | **200** | permitAll |
| GET /me anonymous | **401** | **401** | Basic requires authentication |
| GET /me learner right password | **200** | **200** | Hash matches |
| GET /lesson learner | **200** | **200** | ROLE_LEARNER |
| GET /admin learner | **403** | **403** | Missing ROLE_ADMIN |
| GET /lesson admin | **403** | **403** | Missing ROLE_LEARNER |
| GET /admin admin | **200** | **200** | ROLE_ADMIN |
| GET /me suspended | **401** | **401** | Account disabled |
| GET /me unknown | **401** | **401** | Missing username |

These are **expected results based on the demo configuration**, not logs measured from a running server in this article. Proxy configuration, extra filters, entry points, or different session handling may alter responses.

When learner calls /me, expected JSON:

~~~json
{
  "username": "learner",
  "authorities": ["ROLE_LEARNER"]
}
~~~

Key order is not guaranteed. The controller returns only necessary fields rather than serializing UserDetails/Authentication/password hash.

### 6.5. Significance of the results

Both profiles produce the same authentication/authorization behavior because UserDetails is built consistently in terms of username, encoded password, account status, and authorities. **Changing the user source does not require changing URL policies**.

What differs is how users are managed in the database: the JDBC manager knows the default schema and provides createUser; the custom service reads domain tables with arbitrary IDs and flags.

## 7. MockMvc Integration Test for the Business Store

In a project with spring-boot-starter-test, create file **src/test/java/com/example/userstore/DomainStoreHttpTest.java**:

~~~java
package com.example.userstore;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("domain")
class DomainStoreHttpTest {

    @Autowired
    MockMvc mvc;

    private String basic(String user, String password) {
        String pair = user + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
            pair.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void businessStoreLoadsUserAndAuthorities() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_LEARNER"));
    }

    @Test
    void invalidAndDisabledUsersAreRejected() throws Exception {
        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("suspended", "suspend123")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("unknown", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizationUsesRolesLoadedFromDatabase()
            throws Exception {
        mvc.perform(get("/lesson")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("learner", "learn123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin123")))
            .andExpect(status().isOk());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

PowerShell uses **.\gradlew.bat test**. The test file pins the domain profile to test the business schema. You can create an equivalent test with @ActiveProfiles("jdbc") to test the JDBC manager. If running multiple Spring application contexts using H2 in the same JVM, configure distinct database names per context or use generate-unique-name so they do not share one in-memory H2 database and collide on table creation.

**MockMvc tests the HTTP contract; it does not prove scalability or every security edge case.** Production requires testing schema migrations, stale caches, concurrent logins, DB unavailability, SQL injection, and permission updates/revocations.

## 8. Can You Just Change the Default SQL Instead of Writing a Custom Service?

If the business schema is close to the JDBC contract, JdbcDaoImpl/JdbcUserDetailsManager lets you customize user/authority loading queries. Snippet:

~~~java
JdbcUserDetailsManager manager = new JdbcUserDetailsManager(dataSource);
manager.setUsersByUsernameQuery(
    "SELECT login_name AS username, password_hash AS password, " +
    "enabled_flag AS enabled " +
    "FROM app_users WHERE login_name = ?"
);
manager.setAuthoritiesByUsernameQuery(
    "SELECT u.login_name AS username, r.authority " +
    "FROM app_users u JOIN app_user_roles r ON r.user_id = u.id " +
    "WHERE u.login_name = ?"
);
~~~

This is an illustrative configuration snippet inside a method that has a `dataSource` variable, **not a standalone runnable Java file**. Queries must match the column contract expected by the JdbcDaoImpl version in use; verify with integration tests.

**Warning:** changing only the two SELECTs **does not automatically fix JdbcUserDetailsManager's INSERT/UPDATE/DELETE/changePassword statements**. If you use the manager to write accounts, you must configure or replace all related SQL and ensure consistent transactions and auditing. For complex business stores, a dedicated custom UserDetailsService can be clearer and safer.

If you only want to read and not manage users through the manager, consider JdbcDaoImpl or an appropriate custom service. Do not turn the object serving authentication into a dumping ground for all user administration operations.

## 9. What If the Application Uses Spring Data JPA?

Instead of JdbcTemplate, a service can inject AccountRepository and RoleRepository to read entities/DTOs. The fundamental logic remains **username -> account -> encoded password + account flags + authorities -> UserDetails**.

Illustrative method snippet in a service that already has a repository and mapper:

~~~java
@Override
public UserDetails loadUserByUsername(String username) {
    AccountEntity account = repository.findByLoginName(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("User not found"));

    return User.withUsername(account.getLoginName())
        .password(account.getPasswordHash())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .authorities(roleMapper.toGrantedAuthorities(account.getRoles()))
        .build();
}
~~~

This is not a standalone example because AccountEntity, repository, and roleMapper are application-specific components. When applying in practice:

- Ensure the transaction/lookup loads all roles to avoid LazyInitializationException.
- Never return the raw entity containing password hash, email, phone number, or JPA relationships as the principal or response.
- Use sensible projections/queries, indexes, and unique constraints.
- Never enable Open Session in View just to mask role mapping bugs.
- Verify that account status mappings do not conflict with business rules.

## 10. Data and Credential Lifecycle

### 10.1. Hashes are sensitive data

A BCrypt hash is not plaintext, yet it can still be used for offline brute-force attacks if leaked. Control DB permissions, backups, logs, tracing, and API responses.

In the demo, PasswordEncoder.encode runs during seeding to create hashes. With a production database, registration/password-change flows must generate hashes in a controlled service and never write raw passwords to the database.

### 10.2. DelegatingPasswordEncoder and migration

A system may contain multiple generations of hashes: BCrypt, PBKDF2, or Argon2 with different parameters. DelegatingPasswordEncoder supports storing values with an algorithm prefix such as {bcrypt} to route to the right encoder. If switching from direct BCryptPasswordEncoder to DelegatingPasswordEncoder, inspect the format of existing password_hash values. Never swap beans in production assuming legacy data is automatically compatible.

### 10.3. Credential erasure and caching

ProviderManager usually attempts to erase credentials on a successful Authentication if the object supports CredentialsContainer. If cached UserDetails and the principal share the same mutable object, erasure may wipe the password in the cache, breaking subsequent authentications.

When caching UserDetails, consider object copying, TTL, invalidation after password/role changes, credential lifecycle, and disabled accounts. Do not disable credential erasure just to avoid errors without analyzing the risk.

### 10.4. Stale tokens/sessions after changing user sources

If roles or account status change in the DB, a previously issued session or JWT may still hold old authorities. Changing UserDetailsService does not automatically destroy all sessions/tokens. You need expiration, revocation, refresh strategies, or permission checks on sensitive requests.

## 11. Common Mistakes

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Right password still returns 401 | Encoder does not match hash format | Check stored hash, PasswordEncoder, prefix |
| JDBC reports table users not found | schema.sql did not run, wrong DB/profile | Check DataSource, initialization, migrations |
| Custom store returns 401 for real user | SQL query wrong field, case sensitivity, or flag | Inspect resulting UserDetails and account state |
| Login succeeds yet /admin returns 403 | Authority lacks ROLE_ADMIN | Check DB authority mapping and hasRole |
| Two UserDetailsServices cause ambiguous config | Both profiles active or extra bean | Explicitly pick source or configure manager/provider |
| Password hash leaked in JSON/logs | Returned raw UserDetails/entity/Auth | DTO allowlist, redaction, limit logging |
| Locked user still logs in | Service skipped accountLocked mapping | Map status and test locked/disabled branches |
| Lookup looks fine yet DB outage causes 401 | Caught DataAccessException and turned into user not found | Distinguish operational errors from not-found |
| Role changed yet session keeps old permission | Stale cache/Authentication | Invalidation/re-auth/re-check |
| Duplicate username | Missing unique constraint or canonicalization | Unique index, data migration |
| SQL injection | Concatenated username into query string | Use parameterized queries |
| Domain user checked against wrong tenant | Query only by username while tenant-scoped | Design identity key and tenant verification |
| H2 loses data on restart | In-memory database | Use persistent DB and migrations in production |
| Seed runs repeatedly on real DB | CommandLineRunner unconditionally creates test users | Seed locally only; use dedicated data migrations |

### 11.1. Why not register beans for both the JDBC manager and custom service at once?

If both JdbcUserDetailsManager and DomainUserDetailsService are created simultaneously, Spring may not automatically decide which UserDetailsService is the authentication source. Auto-configuration may step back or a different provider than expected may be wired.

In the demo, @Profile resolves this cleanly. Real applications combining multiple identity sources may need dedicated AuthenticationProviders or AuthenticationManagers per mechanism, yet must design user resolution, issuer/tenant, and permissions consistently rather than relying on bean registration order.

### 11.2. Why not build login yourself inside the service?

UserDetailsService is not a complete authentication API. If a Controller simply loads a user and builds an Authentication with authenticated=true, clients can spoof identity. Let the Security filters + AuthenticationManager/DaoAuthenticationProvider execute the flow.

### 11.3. Why doesn't the admin account automatically get learner permissions?

In the demo, admin has ROLE_ADMIN and learner has ROLE_LEARNER. hasRole("LEARNER") does not automatically treat ROLE_ADMIN as a higher privilege unless you design a role hierarchy or grant appropriate authorities. Therefore GET /lesson by admin may receive 403 even though admin logged in successfully.

## 12. Moving from Demo to Production

1. **Choose a single account source:** JDBC manager, domain DB, or IdP; define how username/subject/tenant are stably identified.
2. **Manage schemas via migrations:** Flyway/Liquibase, constraints, indexes, rollbacks, and backups. Do not use schema.sql to create tables on every startup on a real DB.
3. **Store only appropriate password hashes:** pick encoder, cost, migration, and never log credentials in logs/traces.
4. **Protect the database:** restrict DB account privileges, TLS for connections if needed, secret management, and rotation.
5. **Verify status/roles:** disabled, locked, expired, password lifecycle, authority mapping, and token/session revocation.
6. **Design data-level authorization:** user A cannot read B's records, tenant boundaries, and business permissions.
7. **Decouple the HTTP contract from the data source:** never return UserDetails, entities, password hashes, or SQL errors in responses.
8. **Limit brute force:** rate limiting, monitoring, password-spraying/credential-stuffing defenses, and anti-account-enumeration.
9. **Test both success and failure:** wrong password, non-existent user, locked account, DB down, duplicate username, and missing roles.
10. **Operate caching safely:** TTL, invalidation after role/password changes, disabled accounts, avoiding shared mutable objects holding hashes.
11. **Monitor performance:** index on login_name lookup, authorities query, connection pool size, query time, concurrency.
12. **Test during version upgrades:** Spring Boot, Spring Security, JDBC driver, H2/production database dialect, SQL migrations.

### 12.1. Multi-tenant note

A username may not be unique across tenants. The UserDetailsService.loadUserByUsername contract takes only one username parameter; do not concatenate a client-claimed tenant into queries without checking authorization. Design explicit identity keys, map verified tenants, and enforce permissions on every resource.

### 12.2. User identity and business authorization

Having an existing user and right password is only **authentication**. Whether that user may edit lesson progress, view orders, or change organization settings is **authorization**, requiring separate ownership/role/permission data. Do not cram all policies into the user lookup query.

## 13. Self-Check Knowledge Quiz

**Q1.** How do JdbcDaoImpl and JdbcUserDetailsManager differ?  
**A:** JdbcDaoImpl uses JDBC to read UserDetails; JdbcUserDetailsManager extends it to manage users via UserDetailsManager.

**Q2.** Is UserDetailsService responsible for checking raw passwords?  
**A:** No. DaoAuthenticationProvider and PasswordEncoder check credentials.

**Q3.** What main columns does the default JDBC schema require?  
**A:** `users(username, password, enabled)` and `authorities(username, authority)`.

**Q4.** Why must ROLE_ADMIN be stored if SecurityFilterChain uses hasRole("ADMIN")?  
**A:** hasRole typically checks for the authority with the `ROLE_` prefix.

**Q5.** Does switching profiles from jdbc to domain require changing SecurityFilterChain?  
**A:** No, as long as both sources supply consistent UserDetails/authorities.

**Q6.** If a username is missing, should a custom service return null or throw something?  
**A:** Throw UsernameNotFoundException per the UserDetailsService contract.

**Q7.** On a database outage, should you throw UsernameNotFoundException to hide the error?  
**A:** No. Preserve the real operational error and hide details at the response boundary.

**Q8.** Why avoid SQL string concatenation when looking up a username?  
**A:** Risk of SQL injection; use query parameters.

**Q9.** If app_users has locked_flag, where does it map?  
**A:** UserDetails.accountNonLocked via accountLocked in the User builder.

**Q10.** Why is changing only the two SELECTs of JdbcUserDetailsManager insufficient for CRUD on business tables?  
**A:** Management statements (INSERT/UPDATE/DELETE/changePassword) have their own SQL.

**Q11.** Why does an authenticated admin still get 403 at /lesson?  
**A:** ROLE_ADMIN does not automatically imply ROLE_LEARNER in the demo.

**Q12.** Is a password hash safe to return to the frontend?  
**A:** No. Hashes are still sensitive credential data.

**Q13.** When a role is revoked, do old sessions/JWTs update automatically?  
**A:** No. Refresh, invalidation, revocation, or business re-checks are needed.

**Q14.** Why is a unique index needed on login_name?  
**A:** Guarantees each login name identifies one account per policy and prevents ambiguous lookup results.

**Q15.** Must an app already using JPA fall back to JdbcTemplate to implement UserDetailsService?  
**A:** No. You can use a JPA repository, provided UserDetails mapping is accurate and transactions/lazy loading are controlled.

## 14. Official Documentation

- Spring Security — JDBC Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html
- Spring Security — Security Database Schema: https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — UserDetails: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.3 — Database Initialization: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
