# Integrating a Custom User Store via UserDetailsService

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson walks through integrating custom application account tables into the username/password authentication flow via the `UserDetailsService` interface—from the data model, lookup adapter, and account/authority mapping to configuration, testing, and security. The Spring examples below belong to **a Spring Boot project** with the corresponding dependencies; only the Java SE example at the end can be compiled standalone with JDK 17.

## 1. Problem: User Data Does Not Live in the Default Schema

Many projects already have their own account store, for example:

- An `app_account` table containing username, password hash, account status, and login lock flag.
- An `app_account_role` table storing roles/permissions for each account.
- Registration, password change, disable/lock, auditing, and permission management workflows owned by business logic.

Spring Security **does not require** migrating all data into the library's default schema. Instead, a `UserDetailsService` can serve as a **read adapter** between the internal account model and Spring Security's authentication contract.

~~~text
POST /login  (username + password)
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     |                                     
     +--> UserDetailsService.loadUserByUsername(username)
     |       |
     |       v
     |   AccountRepository -> app_account + app_account_role
     |       |
     |       v
     |   UserDetails {username, passwordHash, enabled, locked, authorities}
     |
     +--> PasswordEncoder.matches(rawPassword, encodedPassword)
     +--> check account status
     |
     v
Authenticated Authentication (or AuthenticationException)
     |
     v
SecurityContext and persistence/response steps depending on login mechanism
~~~

Key takeaway: **`UserDetailsService` does not authenticate passwords itself**. It only **loads user data**. `DaoAuthenticationProvider` is what combines that data with `PasswordEncoder` and status checks to decide whether login is permitted.

## 2. Four Responsibility Boundaries to Keep Clear

| Component | Must Do | Should Not Do |
| --- | --- | --- |
| `AccountRepository` / DAO | Read account records, roles, and metadata from the application's data store. | Directly create HTTP sessions, responses, or login redirects. |
| `UserDetailsService` | Turn a username into a `UserDetails` conforming to Spring Security's contract or throw `UsernameNotFoundException`. | Read raw passwords from HTTP requests, compare passwords itself, or set authenticated flags. |
| `DaoAuthenticationProvider` | Use `UserDetailsService`, `PasswordEncoder`, and account status to verify username/password. | Decide the application's entire per-URL access control strategy. |
| `SecurityFilterChain`, authentication filter, and context | Define endpoints, login mechanism, authorization, success/failure handlers, and `SecurityContext` scope. | Query SQL directly in every controller just to reimplement login logic. |

Thanks to this separation, you can swap JDBC for JPA, an LDAP adapter, or an internal service without rewriting `UsernamePasswordAuthenticationFilter`. Conversely, changing the password encoder does not force table changes if the hash column supports the corresponding format.

### Central Interface

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

This is an **abbreviated signature of the Spring Security API**, not a custom interface to redefine in your project. Related types:

- `org.springframework.security.core.userdetails.UserDetailsService`
- `org.springframework.security.core.userdetails.UserDetails`
- `org.springframework.security.core.userdetails.UsernameNotFoundException`

The method takes a **username for lookup**; there is no raw password parameter. If the user does not exist, it must throw `UsernameNotFoundException`. If the database loses connection, that is an **infrastructure error** and should not be unconditionally converted into "account does not exist".

## 3. The `UserDetails` Contract: What Data Needs Mapping?

`UserDetails` represents the data Spring Security needs for the username/password mechanism. It has key methods:

| API | Meaning |
| --- | --- |
| `getUsername()` | Login username or identity key used during authentication. |
| `getPassword()` | Stored **hashed/encoded password**, not the raw password sent by the client. |
| `getAuthorities()` | `GrantedAuthority` instances granted from a trusted source. |
| `isEnabled()` | Whether the account is permitted to be used by policy. |
| `isAccountNonLocked()` | `false` if the account has been locked. |
| `isAccountNonExpired()` | `false` if the account has expired. |
| `isCredentialsNonExpired()` | `false` if credentials need rotation/have expired. |

You can **implement `UserDetails` yourself** to carry extra domain fields, but in most cases you should **use `org.springframework.security.core.userdetails.User`** for mapping. That reduces boilerplate code and avoids bugs in `isAccountNonLocked()` and `isCredentialsNonExpired()`.

Example mapping rules:

~~~text
Domain record                        Spring Security UserDetails
username = "learner"       ------->  username = "learner"
password_hash = "{bcrypt}..." ---->  password = "{bcrypt}..."
enabled = true             ------->  enabled = true
locked = false             ------->  accountNonLocked = true
roles = ["ROLE_LEARNER"]   ------->  authorities = ["ROLE_LEARNER"]
~~~

**Especially error-prone:** a domain field `locked=true` must be expressed as `isAccountNonLocked()=false`—inverted logic. With the `User.withUsername(...)` builder, you can call `.accountLocked(account.locked())` to avoid miscalculating it manually.

### `role` and `authority` Permissions

Spring Security ultimately evaluates `GrantedAuthority` values. By common convention:

- `.roles("LEARNER")` creates the `ROLE_LEARNER` authority.
- `.authorities("ROLE_LEARNER")` supplies the exact `ROLE_LEARNER` value.
- `.hasRole("LEARNER")` typically checks for `ROLE_LEARNER`.
- `.hasAuthority("ROLE_LEARNER")` checks the full authority name.

If the database already stores `ROLE_LEARNER`, use `authorities(...)` and **do not** pass `ROLE_LEARNER` to `roles(...)` because that risks duplicating or misapplying the prefix. If the system has fine-grained permissions like `orders:read`, they can be separate authorities without requiring the `ROLE_` prefix.

## 4. Integration Example: Custom Account Store with JDBC

The example is a Spring Boot 3.x application using **in-memory H2** so learners can run it quickly. A similar repository/adapter design can be switched to PostgreSQL or MySQL by changing the datasource and adjusting SQL syntax accordingly. H2 is for demo only; never use an in-memory database or test accounts as a production user store.

Required dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-jdbc`
- `com.h2database:h2` (runtime/demo)
- `spring-boot-starter-test` and `spring-security-test` (test)

Create the Java files in package `com.example.securitydemo` (or a package scanned by `@SpringBootApplication`). The examples below use `JdbcTemplate` so the adapter stays explicit, without depending on Hibernate/JPA.

### 4.1. SQL Schema — `src/main/resources/schema.sql`

~~~sql
CREATE TABLE app_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE app_account_role (
    account_id BIGINT NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (account_id, role_code),
    CONSTRAINT fk_account_role_account
        FOREIGN KEY (account_id) REFERENCES app_account(id)
);
~~~

Intentional details in the schema:

1. `password_hash` is long enough to hold hashes with an algorithm prefix such as `{bcrypt}...`; never store raw passwords.
2. `username` has a `UNIQUE` constraint. When using case-insensitive usernames, define normalization/collation rules and a matching unique index **consistently** between registration and login.
3. `enabled` and `locked` are separate; account/credential expiration rules can add new columns if business rules require them.
4. `role_code` stores normalized authority names like `ROLE_LEARNER`, **never** accepting raw permission lists from clients during login.
5. The foreign key prevents orphan roles; production migrations should be managed via Flyway/Liquibase or a unified migration mechanism rather than re-running `CREATE TABLE` on every deploy.

### 4.2. Datasource Configuration — `src/main/resources/application.properties`

~~~properties
spring.datasource.url=jdbc:h2:mem:securitydemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.h2.console.enabled=false
~~~

This configuration is **strictly for learning environments**. Boot runs `schema.sql` for the datasource in the demo; do not infer that a production app should recreate the schema on every startup. Never commit production database usernames/passwords into source control.

### 4.3. Domain Record — `AppAccount.java`

~~~java
package com.example.securitydemo;

public record AppAccount(
        long id,
        String username,
        String passwordHash,
        boolean enabled,
        boolean locked
) {}
~~~

A Java 17 record keeps the data model simple and immutable. It is a **domain read model**, not `UserDetails` and not the request's servlet principal. Operations like password changes, account locking, or role assignments should go through controlled application services, rather than mutating a `UserDetails` object used for authentication.

### 4.4. Repository — `JdbcAccountRepository.java`

~~~java
package com.example.securitydemo;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcAccountRepository {
    private final JdbcTemplate jdbc;

    public JdbcAccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<AppAccount> findByUsername(String username) {
        List<AppAccount> rows = jdbc.query(
                """
                SELECT id, username, password_hash, enabled, locked
                FROM app_account
                WHERE username = ?
                """,
                (rs, rowNum) -> new AppAccount(
                        rs.getLong("id"),
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled"),
                        rs.getBoolean("locked")
                ),
                username
        );
        return rows.stream().findFirst();
    }

    public List<String> findRoleCodes(long accountId) {
        return jdbc.query(
                """
                SELECT role_code
                FROM app_account_role
                WHERE account_id = ?
                ORDER BY role_code
                """,
                (rs, rowNum) -> rs.getString("role_code"),
                accountId
        );
    }
}
~~~

**Explanation:**

- The `?` placeholder is bound via `JdbcTemplate`, avoiding concatenating usernames directly into SQL and reducing SQL injection risk.
- The first query fetches only **one username**; the unique index ensures at most one matching account.
- The role query uses the account ID from the retrieved record, **never trusting** an ID sent by the client.
- If multiple authorities/tenants/permissions are computed by business rules, the repository and mapper must have a clear contract on which authorities are actually used for authorization.
- Reading the account and roles with **two queries** is simple for a demo. For large systems with high latency, consider consistent transactions, appropriate JOINs, or a cache with invalidation; do not assume two queries are always fast enough.

A DB connection failure will throw a data access error; **do not** catch all exceptions and return `Optional.empty()`. Doing so causes infrastructure failures to be mistaken for nonexistent usernames, making outages hard to detect and skewing monitoring strategies.

### 4.5. `UserDetailsService` Adapter — `AccountUserDetailsService.java`

~~~java
package com.example.securitydemo;

import java.util.List;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class AccountUserDetailsService implements UserDetailsService {
    private final JdbcAccountRepository accounts;

    public AccountUserDetailsService(JdbcAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AppAccount account = accounts.findByUsername(username)
                .orElseThrow(() ->
                    new UsernameNotFoundException("Invalid username or password"));

        List<String> authorities = accounts.findRoleCodes(account.id());

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .authorities(authorities.toArray(String[]::new))
                .build();
    }
}
~~~

**This is the most important integration point of the lesson.**

1. `@Service` registers the adapter as a Spring bean. When the application has a matching `UserDetailsService` and no other authentication mechanism overrides it, Spring Security can configure `DaoAuthenticationProvider` to use this bean in the username/password authentication flow.
2. If the account does not exist, throw `UsernameNotFoundException` per the contract instead of returning `null`.
3. `.password(account.passwordHash())` must receive the **encoded password fetched from the database**, not the password the client is submitting; the adapter **does not call `matches(...)`**.
4. `.disabled(!account.enabled())` and `.accountLocked(account.locked())` accurately reflect the status rules. For account expiration or credential expiration, extend the domain model and mapping accordingly.
5. `.authorities(...)` uses permissions read from server-controlled storage. Never take `role=ADMIN` from a login form and assign it as the user's authority.
6. If the data store has no roles for a user yet, it may return an empty list depending on policy; the user may pass authentication yet still be denied access to endpoints requiring roles. Define clear business rules on default roles and permission grants.

**Do not confuse "user does not exist" errors with wrong-password errors:** `DaoAuthenticationProvider` typically masks `UsernameNotFoundException` as a generic credentials error on the authentication side to limit user enumeration. HTTP responses should likewise return a generic login failure message. This does not mean omitting operational logging; simply do not expose sensitive details to clients.

## 5. Configuring SecurityFilterChain and PasswordEncoder

Create `SecurityConfig.java`:

~~~java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Why use `DelegatingPasswordEncoder`?**

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates an encoder that recognizes algorithms by hash prefix, such as `{bcrypt}$2a$...`. When calling `encode(...)` under the default configuration, passwords are hashed with BCrypt plus the `{bcrypt}` prefix; at login, `matches(raw, storedEncoded)` uses the prefix to pick the right encoder. This helps when upgrading hash algorithms in the future while still supporting existing stored hashes.

Never store `"training-only"` directly in `password_hash`, and never hash passwords with plain `SHA-256(password)`. Passwords require dedicated password-hashing algorithms with appropriate work factors such as BCrypt, Argon2, or PBKDF2 per current policy.

**A note on bean auto-configuration:** With one `UserDetailsService` and one `PasswordEncoder` bean, many Spring Security username/password setups automatically wire them into `DaoAuthenticationProvider`. However, if a project defines a custom `AuthenticationManager`, `AuthenticationProvider`, has **multiple** `UserDetailsService` beans, or multiple `SecurityFilterChain` beans with custom mechanisms, do not assume a new bean will be picked up automatically. Inspect the authentication manager/provider applied to the right chain; when needed, explicitly configure the provider in a way compatible with your version.

### Controller for Testing Login — `DemoController.java`

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
~~~

`/public` is a public endpoint, `/me` requires login, and `/admin` requires `ROLE_ADMIN`. Being able to log in successfully does **not** automatically allow a user to access `/admin`.

### Main Class — `SecurityDemoApplication.java`

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

Place all classes in the same `com.example.securitydemo` package or subpackages of the main package so Spring Boot component scanning discovers `@Service`, `@Repository`, `@Configuration`, and `@RestController`.

## 6. Creating a Demo Account Properly: Run Only When Profile `demo` Is Active

To give integration tests data, you can seed a `learner` user with role `ROLE_LEARNER`. Never hardcode fixed demo passwords into production application code. The example below uses the **`DEMO_SEED_PASSWORD` environment variable**, creating data only when the `demo` profile is active.

Create `DemoUserInitializer.java`:

~~~java
package com.example.securitydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
@Profile("demo")
public class DemoUserInitializer {

    @Bean
    ApplicationRunner seedDemoAccount(
            JdbcTemplate jdbc,
            PasswordEncoder encoder,
            @Value("${DEMO_SEED_PASSWORD}") String password) {

        return args -> {
            if (password == null || password.isBlank()) {
                throw new IllegalStateException("Demo password is missing");
            }

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM app_account WHERE username = ?",
                    Integer.class,
                    "learner"
            );
            if (count != null && count > 0) {
                return;
            }

            jdbc.update(
                    """
                    INSERT INTO app_account(username, password_hash, enabled, locked)
                    VALUES (?, ?, ?, ?)
                    """,
                    "learner", encoder.encode(password), true, false
            );

            Long id = jdbc.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class,
                    "learner"
            );
            jdbc.update(
                    """
                    INSERT INTO app_account_role(account_id, role_code)
                    VALUES (?, ?)
                    """,
                    id, "ROLE_LEARNER"
            );
        };
    }
}
~~~

**Limitations:** `@Profile("demo")` ensures the seed bean exists only when this profile is active. This is still a demo, not a production provisioning system: it does not fully handle race conditions across two instances, rotation, migrations, or auditing. In production, manage users through registration/password-change/administration workflows with transactions and access controls.

Note when placing Java placeholders in annotations: in the actual Java file, the content is `@Value("${DEMO_SEED_PASSWORD}")` **without backslashes**. Any backslash in this Markdown document was only for escaping while authoring; the final annotation should be written `@Value("$"+"{DEMO_SEED_PASSWORD}")` in the sense of a complete Spring placeholder string.

### Running the Demo

In a Unix/macOS terminal, with the Maven Wrapper and Boot application created:

~~~bash
SPRING_PROFILES_ACTIVE=demo DEMO_SEED_PASSWORD=training-only ./mvnw spring-boot:run
~~~

On Windows PowerShell, equivalently:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "demo"
$env:DEMO_SEED_PASSWORD = "training-only"
.\mvnw.cmd spring-boot:run
~~~

`training-only` is only an illustrative password for local environments; never use it to protect real accounts. In in-memory H2, data is recreated whenever the process starts fresh. For production JDBC databases, data must live in persistent DBs with strict migrations and permission-granting processes.

### Progression of a Login Flow

~~~text
GET /me when unauthenticated
  -> security chain requires authenticated user
  -> browser is redirected to form login

POST /login (username=learner, password=training-only, valid CSRF)
  -> UsernamePasswordAuthenticationFilter creates unauthenticated token
  -> AuthenticationManager -> DaoAuthenticationProvider
  -> AccountUserDetailsService.loadUserByUsername("learner")
       -> JDBC looks up account id, password_hash, enabled, locked
       -> JDBC fetches ROLE_LEARNER
       -> Spring UserDetails holds {bcrypt}... and account flags
  -> PasswordEncoder.matches("training-only", hash) == true
  -> Provider returns authenticated Authentication
  -> authentication filter places result into SecurityContext
  -> saves context/session and runs success handler per configuration
  -> response redirects per active login flow

GET /me when browser sends back valid session
  -> SecurityContext is reloaded from repository
  -> Authentication.getName() == "learner"
  -> HTTP 200, body "learner"

GET /admin in the same session
  -> user only has ROLE_LEARNER, lacks ROLE_ADMIN
  -> typically HTTP 403 Forbidden
~~~

With default form login, CSRF protection is usually enabled for POST; use a browser form or a test helper with a valid CSRF token. **Do not** disable CSRF just to make a `curl -d "username=...&password=..."` sample work.

## 7. Integration Testing: Does It Actually Go Through UserDetailsService?

`MockMvc` + `spring-security-test` tests requests through the servlet security chain, instead of merely mocking `UserDetailsService` and asserting "authenticated".

Create `src/test/java/com/example/securitydemo/AccountLoginIntegrationTest.java`:

~~~java
package com.example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest(properties = "DEMO_SEED_PASSWORD=training-only")
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class AccountLoginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validPasswordLogsInAndSessionRetainsUser() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("learner").password("training-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("learner"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(formLogin().user("learner").password("wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());
    }
}
~~~

Because `@ActiveProfiles("demo")` creates the H2 user when starting the test context and `@SpringBootTest(properties=...)` supplies the demo password, the test has concrete input data. `formLogin()` is a **request builder from spring-security-test**, not `http.formLogin(...)`; it sends a valid login request for the default configuration and handles CSRF. The test demonstrates three behaviors:

1. Valid username/password leads to an authenticated result.
2. After login, reusing the session can read `/me` with principal `learner`.
3. `ROLE_LEARNER` is not permitted to access an endpoint requiring `ROLE_ADMIN`.

The wrong-password test confirms no new authenticated principal is created. Maven/Gradle log output depends on the environment, so exact stdout is not asserted. In a project with a Maven Wrapper, run:

~~~bash
./mvnw test
~~~

**Do not generalize this test to every configuration:** if the application uses stateless bearer tokens, changes login URLs, uses custom success/failure handlers, multiple chains, or custom session management, session/redirect assertions must change accordingly. In production, add tests verifying the real database and migrations, not just H2.

### Testing Account States

Add test cases runnable against an isolated test database:

| Data in DB | Behavior to Observe |
| --- | --- |
| Username absent | `loadUserByUsername` throws `UsernameNotFoundException`; login ultimately fails to authenticate. |
| Username exists, wrong password | `PasswordEncoder.matches(...)` rejects; no new authentication granted. |
| `enabled=false` | Account rejected even with right password. |
| `locked=true` | Account rejected per policy even with right password. |
| `ROLE_LEARNER` | Logs in successfully but rejected at endpoints requiring `ROLE_ADMIN`. |
| Validly granted `ROLE_ADMIN` | Can pass `hasRole("ADMIN")` check when other conditions are valid. |
| No roles | Login may succeed but does not automatically grant admin privileges. |
| Database unavailable | System reports/records infrastructure error, not silently treating it as a nonexistent username. |

Avoid writing sequential tests directly on shared data without resetting, because modifying account state in one test can make other tests flaky. You can use a separate DB, properly transacted fixtures, or a controlled cleanup strategy.

## 8. Standalone Java 17 Example: Converting a Domain Account to a Principal

The Spring examples above require Spring Boot/classpath and cannot be run by compiling a single file with `javac`. To see the mapping step firsthand **without pretending to authenticate passwords**, the following Java SE example simulates a repository and view equivalent to `UserDetails` input data.

Create `AccountMappingDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

public class AccountMappingDemo {

    record StoredAccount(
            String username, String encodedPassword,
            boolean enabled, boolean locked, List<String> roles) {}

    record PrincipalView(
            String username, boolean enabled,
            boolean accountNonLocked, List<String> authorities) {}

    static PrincipalView load(
            Map<String, StoredAccount> database, String username) {
        StoredAccount account = database.get(username);
        if (account == null) {
            throw new NoSuchElementException("No matching account");
        }
        return new PrincipalView(
                account.username(),
                account.enabled(),
                !account.locked(),
                List.copyOf(account.roles())
        );
    }

    public static void main(String[] args) {
        Map<String, StoredAccount> database = Map.of(
                "learner", new StoredAccount(
                        "learner", "encoded-value-for-demo",
                        true, false, List.of("ROLE_LEARNER"))
        );

        PrincipalView user = load(database, "learner");
        System.out.println("username=" + user.username());
        System.out.println("enabled=" + user.enabled());
        System.out.println("accountNonLocked=" + user.accountNonLocked());
        System.out.println("authorities=" + user.authorities());

        try {
            load(database, "missing");
        } catch (NoSuchElementException ex) {
            System.out.println("missing user rejected");
        }
    }
}
~~~

Run on JDK 17 or newer:

~~~bash
javac AccountMappingDemo.java
java AccountMappingDemo
~~~

Exact stdout:

~~~text
username=learner
enabled=true
accountNonLocked=true
authorities=[ROLE_LEARNER]
missing user rejected
~~~

This is a **data simulation**, not a login system: `encoded-value-for-demo` is not a valid BCrypt hash, `PasswordEncoder.matches(...)` is not called, and no real `Authentication` is issued. The goal is to recognize how the adapter fetches data from the domain (not trusting the client), inverts `locked` to `accountNonLocked`, and turns roles into the authority list. Password verification must reside in Spring Security's provider mechanism.

## 9. Using JPA or Internal APIs Instead of JDBC

`UserDetailsService` only requires the `loadUserByUsername(...)` method. The backing user store can be:

- **Spring Data JPA:** `JpaRepository<AccountEntity, Long>` with a method to find accounts by username and map role relationships. Watch out for `LAZY` role collections, `LazyInitializationException`, query counts, and read-only transactions. Use `@EntityGraph`, fetch joins, or appropriate DTO projections when roles must be fetched in the same access unit.
- **JDBC as in the example:** explicit SQL control, simple, easy to inspect queries and mapping.
- **Internal account service:** an adapter calling the service via a client with timeouts/circuit-breakers, identifying the authority source, handling infrastructure errors; never send raw passwords over insecure networks.
- **LDAP or centralized directory:** standard corresponding providers/adapters can be used instead of writing SQL inside a custom `UserDetailsService`.
- **Built-in `JdbcUserDetailsManager`:** fits if table structure and simple queries satisfy its contracts; you can configure custom queries within the API's scope, though a dedicated adapter makes complex domain and status mapping more transparent.

### Why Does JPA Easily Hit Lazy-Load Errors?

Suppose entity `AccountEntity` has `@OneToMany(fetch=LAZY)` or `@ManyToMany(fetch=LAZY)` for roles. If the service fetches the account, the transaction/persistence context closes, and only then `account.getRoles()` is called, it can throw `LazyInitializationException`. Fetch all data needed for `UserDetails` inside a read transaction or a dedicated query. Do not blindly enable `EAGER` on every relationship because that easily causes heavy queries or N+1 problems.

If role and account status changes must take effect nearly immediately upon revocation, consider caching policies. A `UserDetailsService` with custom caching may return stale data, and already logged-in sessions may still hold authorities from the prior authentication. **Locking an account in the database does not automatically guarantee all open sessions are invalidated immediately**; that requirement needs session/token/cache revocation or per-request permission checks appropriate to the model.

## 10. Multi-Tenant, Email/Username, and Identity Mapping Cases

### Username Is Not Always Globally Unique Across the System

A multi-tenant application may only have a unique constraint on `(tenant_id, username)`. Calling only `findByUsername(username)` could fetch another tenant's account by mistake. Ensure the tenant is determined by a **trusted** context and included in the DB query. Conceptual example:

~~~sql
SELECT id, username, password_hash, enabled, locked
FROM app_account
WHERE tenant_id = ? AND username = ?
~~~

This is **illustrative SQL** for a multi-tenant schema, not directly usable against the demo table in Section 4 (which does not yet have `tenant_id`). Never blindly trust a `tenantId` taken from an unauthenticated form to grant cross-tenant access. Complex architectures may require a specialized authentication provider, a principal carrying explicit tenant identity, and authorization rules always bound to the tenant.

### Email Used as Username

You can pass an email into the `loadUserByUsername` parameter; the interface's fixed method name does not require the system to have a field literally named `username`. However, if you want case-insensitivity or whitespace trimming, normalize **consistently** at account creation and lookup, with a matching uniqueness constraint.

Never "try every account" or fall back to another username when not found, as that easily causes ambiguity, account takeover, or identity leakage. A user identifier must have stable lookup semantics.

### Which Principal Should Be Returned?

In many projects, `org.springframework.security.core.userdetails.User` is enough. If a domain ID is needed in the principal, you can create an immutable custom `UserDetails` or use a dedicated principal class. Avoid stuffing an entire JPA entity, raw password, service access token, mutable permissions, or objects with unloaded lazy relationships into the principal. Principals can be kept in sessions, serialized, or logged in unexpected layers.

## 11. Security: What the Adapter Must and Must Not Do

1. **Hash passwords properly:** at registration/password change, call `PasswordEncoder.encode(raw)` to store; at login `DaoAuthenticationProvider` uses `matches(raw, encoded)`. With `DelegatingPasswordEncoder`, legacy data missing the `{id}` prefix needs migration or controlled compatibility config; never skip verification by accepting plaintext.
2. **Never log secrets:** never log raw passwords, the `password_hash` column, access tokens, session cookies, or full `UserDetails`. Logging usernames also requires considering privacy and data-exposure rules.
3. **Prevent user enumeration:** failure messages sent to clients must not reveal whether an account exists. Never create an unrestricted `/user-exists` API just to assist login checks.
4. **Prevent brute-force/credential stuffing:** apply rate limiting, risk-aware lockout/backoff, MFA, and anomaly monitoring at the appropriate authentication layer. Integrating `UserDetailsService` alone does not supply these mechanisms.
5. **Account status:** map `enabled`, `locked`, and expiration accurately. Additional business logic may need to be enforced before or alongside the provider.
6. **Trusted authorization:** authorities come from server-managed sources; never trust role fields submitted by the client in a login form.
7. **Consistent lookup:** username normalization and unique constraints must match; if multi-tenant, scope queries by a trusted tenant.
8. **Distinguish data errors from system errors:** a DB timeout is not a wrong password. Do not catch every `Exception` and throw `UsernameNotFoundException`; emit appropriate alerts/metrics.
9. **Session and CSRF:** in cookie-based form login, retain CSRF protection per threat model, HTTPS, proper cookie flags, session fixation protection, and logout/session revocation. `UserDetailsService` does not replace them.
10. **Do not overuse caches:** password changes, account locks, or role revocations must have matching refresh/invalidation policies; do not expect old sessions to refresh roles automatically.
11. **Information present in context:** a `UserDetails` read from the DB is only data; it does not automatically become an authenticated `Authentication`. Only the responsible authentication provider supplies a trusted result.
12. **Limit data fetched from the DB:** avoid loading full relationships/PII just to return `UserDetails`; fetch only data strictly needed for login/authorization.

## 12. Common Errors When Implementing `UserDetailsService`

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Spring still uses the default user instead of DB users | `UserDetailsService` bean not scanned, multiple beans exist, or another custom provider/manager takes precedence. | Check package scanning, security config, and actual provider. |
| `UsernameNotFoundException` even though DB has the row | Query uses wrong column name, different case/trimming rules, or wrong datasource/tenant. | Check query parameter binding and consistent lookup keys. |
| `BadCredentialsException` despite "correct" password | Hash stored in wrong format, raw password in DB, encoder mismatch, or unintended password normalization. | Check prefix and `PasswordEncoder.matches(...)` via test fixtures, without logging passwords. |
| Login succeeds yet always returns `403` | Wrong role/authority mapping, missing `ROLE_`, or policy requires a different authority. | Inspect returned `GrantedAuthority` instances and `hasRole/hasAuthority` rules. |
| Locked user can still log in | Custom principal mapping inverted `locked` wrong or custom provider skips state checks. | Test `locked=true` and `isAccountNonLocked()==false`. |
| Account disabled yet old session still has access | Roles/status were checked at login, while session still holds old authentication. | Define session revocation requirements and implement invalidation/re-check policies. |
| `LazyInitializationException` | JPA role association is lazy and transaction already closed. | Use queries loading sufficient data or read-only transactions. |
| Every request executes too many SQL queries | Per-request authentication, N+1 roles, missing cache, or misconfigured chain. | Profile queries, optimize fetching, and assess stale-cache risk. |
| First request login works, next request loses login | `SecurityContextRepository`/session policy, explicit-save, or cookie not persisted. | Separate authentication mechanism from context/session persistence. |
| Bearer token API does not call `UserDetailsService` | Flow uses `JwtAuthenticationProvider` or opaque token provider, not DAO provider. | Check filter chain and authentication mechanism. |
| `403` error right on POST /login | Missing/invalid CSRF token in cookie/form login app. | Submit a valid token; do not rush to disable CSRF. |

## 13. Self-Check Questions

**1. Where does `UserDetailsService` receive the user's password from the form?** It does not receive it. It only receives the username and loads `UserDetails`. Client-supplied passwords are handled separately by the authentication filter/manager/provider to compare against the encoded password from `getPassword()`.

**2. If the user is not in the database, should it return `null`?** No. The `loadUserByUsername(...)` contract requires throwing `UsernameNotFoundException` when not found. Real database errors must be distinguished from nonexistent users.

**3. Why must `locked=true` not be mapped directly to `isAccountNonLocked()==true`?** Because the method name means **not locked**; `locked=true` corresponds to `accountNonLocked=false`.

**4. Why does the database store `ROLE_LEARNER` while the code uses `.authorities(...)`?** Because `authorities` takes the exact authority name. `roles("LEARNER")` is what automatically prepends `ROLE_` by convention.

**5. To switch from MySQL to PostgreSQL, do you need to rewrite `UsernamePasswordAuthenticationFilter`?** No. Keep the `UserDetailsService` contract; only change the datasource/repository/migrations for the target DBMS.

**6. If an account is disabled in the DB, do existing active sessions expire immediately?** Not necessarily. An `Authentication` already saved in a session may remain valid until an appropriate re-check or session/token revocation policy acts on it.

**7. Is `UserDetailsService` the right mechanism for every JWT bearer request?** No. JWT resource servers typically use dedicated decoders/providers and do not necessarily call `UserDetailsService`. Choose the adapter matching the authentication type.

**8. When needing to add multiple login methods, should all of them be crammed into `loadUserByUsername(...)`?** No. This service only handles user lookup for compatible authentication providers. OAuth2/OIDC, JWT, or asynchronous login have their own contracts/providers.

**Takeaway:** `Custom account store → Repository/DAO → UserDetailsService → Server-trusted UserDetails → DaoAuthenticationProvider + PasswordEncoder → Authenticated Authentication`. Keep **user lookup**, **credential verification**, **session/context management**, and **authorization checks** in their proper layers. That is the key to integrating a custom user store without weakening Spring Security's security model.
