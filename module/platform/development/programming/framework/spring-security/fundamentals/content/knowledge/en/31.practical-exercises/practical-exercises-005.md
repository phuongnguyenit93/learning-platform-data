# Replacing Sample Account Storage with a Custom Data Source in Spring Security

> **Capstone practical exercise — Spring Security Fundamentals (Servlet / Spring MVC).** The goal is to replace the illustrative `InMemoryUserDetailsManager` or Spring Boot default user with application-managed data, while still letting Spring Security verify passwords, enforce account status, and apply access rules. The complete example uses **Java 17, Spring Boot 3.3.0, Spring Security 6.x, Spring Data JPA, and H2**. H2 in this example is a **learning-only** database whose data is lost on shutdown; real deployments require a persistent database, schema migrations, and proper account administration.

## 1. Target Outcomes and Scope

After this exercise, you should be able to:

1. Explain the login flow from HTTP Basic/form login through `AuthenticationManager`, `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, and `SecurityContext`.
2. Identify the exact **sample user store** in use and replace it with a `UserDetailsService` querying a repository/database.
3. Map application user data (`username`, password hash, enabled, authorities) to `UserDetails` without manually comparing raw passwords in the repository.
4. Keep the `SecurityFilterChain` and authorization policy intact: existing user, valid password, active account, matching authority.
5. Verify the success path **200**, unauthenticated **401**, insufficient permission **403**, disabled account, and a newly inserted database account.
6. Distinguish demo shortcuts from production operations: hashed passwords, account locking, roles, migrations, unique indexes, transactions, caching, and regression tests.

This exercise only replaces the **data source for username/password authentication**. It does not build registration screens, password resets, MFA, refresh tokens, an OAuth2 Authorization Server, or a complete IAM system. Those capabilities can leverage additional Spring Security modules or external systems, but require separate design.

## 2. Understanding the Core Idea: Swap the Data Source, Keep the Auth Mechanism

In sample configurations, you typically encounter one of two cases:

**Case A — Spring Boot auto-generated dev user:** `spring-boot-starter-security` is present with no custom `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager`. Boot can create a `user` account and log a generated password at startup. This is strictly a development convenience.

**Case B — Project-defined in-memory users:**

```java
@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    UserDetails demo = User.withUsername("demo")
        .password(encoder.encode("demo-pass"))
        .roles("USER")
        .build();
    return new InMemoryUserDetailsManager(demo);
}
```

This is a **sample configuration fragment** and must not remain when switching to a database source. Users are defined in code and cannot be managed independently via application data; changing passwords or roles requires changing code or mutating the running instance.

**Target architecture:**

```text
Client (username + raw password)
    │
    ▼
SecurityFilterChain / filter receiving HTTP Basic or form login
    │
    ▼
AuthenticationManager → DaoAuthenticationProvider
                          ├─ calls UserDetailsService.loadUserByUsername(username)
                          │      │
                          │      ▼
                          │   AccountRepository → Database
                          │      │
                          │      ▼
                          │   UserDetails (username, password HASH, enabled, authorities)
                          │
                          └─ uses PasswordEncoder.matches(raw, storedHash)
    │
    ├─ Bad credentials / disabled / not found → authentication failure
    ▼
Valid Authentication containing authorities
    │
    ▼
AuthorizationFilter → requestMatchers / hasRole / authenticated
    │
    ▼
Controller / Service
```

Layer responsibilities:

| Component | Responsibility | What not to do |
| --- | --- | --- |
| `AccountRepository` | Read/write accounts and authorities from the database | Do not compare raw passwords in SQL; never send hashes out in API responses. |
| `UserDetailsService` | Look up user by username, map data to `UserDetails`, throw `UsernameNotFoundException` if missing | Do not compare passwords, touch `SecurityContextHolder` directly, or grant default roles when DB data is missing. |
| `PasswordEncoder` | `encode(raw)` on creation/password change, `matches(raw, encoded)` during login | Do not encode the raw password to compare two BCrypt hashes; never store `{noop}` in production. |
| `DaoAuthenticationProvider` | Uses `UserDetailsService` + `PasswordEncoder` to verify credentials and user status | No need to reimplement if requirements are standard username/password login. |
| `SecurityFilterChain` | Configures authentication methods and HTTP rules, e.g. USER/ADMIN | Do not write SQL account lookups inside `requestMatchers`. |
| Business Service | Checks permissions against real data: owner/tenant/resource | Never trust `userId` or `role` supplied by the client. |

**A custom `UserDetailsService` bean** causes Spring Boot's default user configuration to back off, provided no conflicting `AuthenticationProvider`/`AuthenticationManager` beans intervene. If an application already defines custom providers, LDAP, OAuth2, or multiple chains, inspect the actual authentication path before assuming the custom service is active.

## 3. The `UserDetailsService` Contract: Input, Output, and Errors

Key signature:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

`loadUserByUsername` **takes only the username**. The raw password stays in the authentication pipeline so `DaoAuthenticationProvider` can match it against the hash returned by the service. At minimum, a `UserDetails` supplies `username`, the **encoded** `password`, the collection of `GrantedAuthority`, and account status flags.

Mapping data:

| Application column | `UserDetails` property | Rule |
| --- | --- | --- |
| `username` | `getUsername()` | Unique, canonicalized per policy, no duplicate users. |
| `password_hash` | `getPassword()` | Holds the encoded hash, never plaintext. |
| `enabled` | `isEnabled()` | If false, standard provider authentication must fail. |
| `authorities` | `getAuthorities()` | Explicit authority strings, e.g., `ROLE_USER`, `ROLE_ADMIN`. |
| `locked`, `expired`, `credentialsExpired` (if present) | `isAccountNonLocked()`, `isAccountNonExpired()`, `isCredentialsNonExpired()` | Use true defaults only when the product **does not yet have** those states; if present, map them accurately. |

In the example below, the table only has `enabled`, so the other flags use defaults from `User.withUsername(...)`. Never turn a "locked account" rule in the database into blindly returning `enabled=true`.

### Roles vs. authorities naming

`User.withUsername(...).roles("ADMIN")` generates the `ROLE_ADMIN` authority. When stored data already looks like `ROLE_ADMIN`, call `.authorities("ROLE_ADMIN")` or `.authorities(Collection...)`, **not** `.roles("ROLE_ADMIN")`: that would violate the prefix convention. `hasRole("ADMIN")` typically checks `ROLE_ADMIN`; `hasAuthority("invoice:approve")` matches the exact authority string. Never trust roles taken directly from request JSON.

## 4. Preparing a Runnable Project

This example uses Maven; do not copy an older config from another exercise. Create the project directory:

```text
custom-account-store/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/accounts/
    │   │   ├── AccountsApplication.java
    │   │   ├── Account.java
    │   │   ├── AccountRepository.java
    │   │   ├── DatabaseUserDetailsService.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoAccounts.java
    │   │   └── AccountController.java
    │   └── resources/application.yml
    └── test/java/example/accounts/
        └── AccountSecurityTest.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>custom-account-store</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

Using **pinned** versions keeps the example consistent with Spring Boot 3 / Spring Security 6 and `jakarta.persistence`. This is a baseline for learning the API, not guidance to deploy older versions to production. In real projects, pick a supported release with current patches and re-run tests against that version's docs.

### 4.2. `src/main/resources/application.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:accounts_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
  h2:
    console:
      enabled: false
```

In-memory H2 lets us practice with a repository without installing PostgreSQL. `create-drop` tells Hibernate to create the schema for the demo and drop it when closing `EntityManagerFactory`. **Never put `ddl-auto: create-drop` into production**, as it is not a safe schema migration mechanism. Keeping the H2 console disabled also avoids exposing an unnecessary attack surface.

### 4.3. `src/main/java/example/accounts/AccountsApplication.java`

```java
package example.accounts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountsApplication.class, args);
    }
}
```

Placing `@SpringBootApplication` in package `example.accounts` scans `@Entity`, repositories, services, and configs across this package and subpackages. No extra `@ComponentScan` is needed for this layout.

## 5. Creating the Account Data Model

This is the **application's source-of-truth data**; `UserDetails` is merely the object Spring Security uses during authentication. Do not force JPA entities to implement `UserDetails`: separating them decouples persistence models from Spring Security and avoids accidentally serializing hashes in HTTP responses.

Create `src/main/java/example/accounts/Account.java`:

```java
package example.accounts;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
        name = "app_account_authorities",
        joinColumns = @JoinColumn(name = "account_id")
    )
    @Column(name = "authority", nullable = false, length = 100)
    private Set<String> authorities = new HashSet<>();

    protected Account() {
        // JPA constructor.
    }

    public Account(String username, String passwordHash,
                   boolean enabled, Set<String> authorities) {
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.enabled = enabled;
        this.authorities = new HashSet<>(Objects.requireNonNull(authorities));
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public Set<String> getAuthorities() {
        return Set.copyOf(authorities);
    }
}
```

Key takeaways:

- `username` must be unique in the **database**, not only in Java. Case sensitivity and canonicalization policies must align with DB collation. For usernames/emails, lowercasing and normalization rules must be decided **before** loading real data.
- `password_hash` must be long enough for the chosen hash format, including `DelegatingPasswordEncoder` prefixes such as `{bcrypt}`. Never store raw passwords or reversible encryption masquerading as a "hash."
- `enabled` is an attribute `DaoAuthenticationProvider` can check through `UserDetails`.
- `authorities` stores strings like `ROLE_USER`. EAGER fetching is used here so the example loads authorities cleanly when fetching a username. In larger systems, pick an appropriate fetch strategy/DTO/query to avoid N+1 queries, excess data, or huge authority sets on every login.
- `getAuthorities()` returns an immutable copy, yet this entity is still **not** meant to be returned directly from HTTP APIs. Restrict HTTP payloads to DTOs and never expose hashes or internal flags.

Create `src/main/java/example/accounts/AccountRepository.java`:

```java
package example.accounts;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByUsername(String username);
}
```

Spring Data JPA derives the query from `findByUsername` based on the entity's `username` field. The repository's sole purpose is **reading an account**, not generating `Authentication` or deciding whether a password matches.

## 6. Replacing `InMemoryUserDetailsManager` with a Custom `UserDetailsService`

Create `src/main/java/example/accounts/DatabaseUserDetailsService.java`:

```java
package example.accounts;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        Account account = accounts.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .authorities(account.getAuthorities().toArray(String[]::new))
            .build();
    }
}
```

**Why is this the primary replacement point?**

- `@Service` registers a `UserDetailsService` bean with the Spring container. When no custom provider/manager conflicts, `DaoAuthenticationProvider` in standard username/password authentication uses this bean to look up accounts.
- `loadUserByUsername()` fetches the account matching `username`. If missing, it **throws `UsernameNotFoundException`**; it never auto-provisions a new user or returns a default fallback account.
- `.password(account.getPasswordHash())` returns the **stored hash**—never call `PasswordEncoder.encode(raw)` during login lookup.
- `.authorities(...)` preserves the authority strings from the database. If the DB stores `ROLE_ADMIN`, `hasRole("ADMIN")` will match.
- `.disabled(!account.isEnabled())` maps the `enabled` flag. Returning `isEnabled() == false` causes the standard provider to reject authentication.
- `@Transactional(readOnly=true)` wraps the query and collection read inside one transaction; this is a JPA choice and does not alter authentication semantics.

**Do not also declare an `InMemoryUserDetailsManager` bean** in another config class: with multiple `UserDetailsService`/provider beans, Spring Security may not pick the one you expect. If a real system needs multiple sources, wire an explicit `AuthenticationProvider`/routing chain and test every login path.

## 7. Keeping Password Encoding and HTTP Rules

Create `src/main/java/example/accounts/SecurityConfig.java`:

```java
package example.accounts;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

In this example, **there is no need to manually declare a `DaoAuthenticationProvider` or `AuthenticationManager` bean**: having one `UserDetailsService` and one `PasswordEncoder` is sufficient for standard username/password authentication. If your project already defines custom `AuthenticationProvider` or `AuthenticationManager` beans, do not blindly rely on this autoconfiguration assumption; wire injection explicitly and test which provider gets invoked.

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` in this baseline defaults to creating new hashes with the `{bcrypt}` prefix. General format:

```text
{id}encodedPassword
{bcrypt}$2a$...              # illustrative value, not a hash for login
```

`encode("alice-pass")` generates a salted hash; the same raw password normally yields **different** hashes each time. To verify a login, use `passwordEncoder.matches("alice-pass", storedHash)`; **never** compare `encode(raw).equals(storedHash)`. When migrating legacy hashes, see the migration section rather than adding `{noop}` for all passwords.

The `SecurityFilterChain` above uses HTTP Basic so statuses are easy to observe. In a browser app using sessions/form login, you can choose `.formLogin(Customizer.withDefaults())` and test CSRF/redirects/UX accordingly. These GET examples do not require disabling CSRF; **never** disable CSRF to make a 403 disappear without knowing whether browsers automatically send cookies/sessions.

## 8. Seeding Demo Data in the Database Without Putting Accounts in SecurityConfig

An empty H2 database at startup has no accounts to test. Create `src/main/java/example/accounts/DemoAccounts.java`:

```java
package example.accounts;

import java.util.Set;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class DemoAccounts {

    @Bean
    CommandLineRunner insertDemoAccounts(
            AccountRepository accounts,
            PasswordEncoder passwordEncoder) {

        return args -> {
            if (accounts.count() > 0) {
                return;
            }

            accounts.save(new Account(
                "alice",
                passwordEncoder.encode("alice-pass"),
                true,
                Set.of("ROLE_USER")
            ));

            accounts.save(new Account(
                "admin",
                passwordEncoder.encode("admin-pass"),
                true,
                Set.of("ROLE_ADMIN")
            ));

            accounts.save(new Account(
                "blocked",
                passwordEncoder.encode("blocked-pass"),
                false,
                Set.of("ROLE_USER")
            ));
        };
    }
}
```

This is **seed data for learning**, not a production pattern. With a real database, never seed hardcoded usernames/passwords; provision accounts through secure workflows, migrations/provisioning, and secret management. Restrict demo seeding to demo environments or tightly locked profiles. The `accounts.count()>0` check is strictly for the H2 demo; never use it instead of proper migrations or partial account provisioning in real systems.

The crucial point here is that `alice`, `admin`, and `blocked` **live in JPA tables**, no longer as hardcoded `UserDetails` inside `InMemoryUserDetailsManager`. Future status or permission updates happen via data changes in proper use cases and transactions.

## 9. Creating an API to Observe Authentication and Authorization

Create `src/main/java/example/accounts/AccountController.java`:

```java
package example.accounts;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-ok";
    }
}
```

`Authentication` is injected by Spring MVC from the security context of the authenticated request. The app can read `authentication.getName()` and authorities to perform work; never take a username from a query parameter as a trusted identity. The demo endpoint returns only the username—**never return the full entity**, password hash, or stack traces.

### 9.1. Running the project

Requires **JDK 17+**, Maven 3.9+ (or a Maven version compatible with Spring Boot 3.3), and network access to download dependencies on first run:

```bash
java -version
mvn test
mvn spring-boot:run
```

`mvn test` runs the integration tests in section 10. `mvn spring-boot:run` starts Tomcat on default port 8080 unless configured otherwise.

In a second terminal (macOS/Linux), try:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:wrong http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u blocked:blocked-pass http://localhost:8080/profile
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/admin/report
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/admin/report
```

**Expected** output with this exact exercise configuration:

```text
200
401
200
401
401
403
200
```

Explanation:

- `/public/ping` is open via `permitAll()`, so **200**.
- `/profile` lacks an Authorization header so HTTP Basic challenges for credentials, **401**.
- `alice` has a matching hash and an enabled account, so `/profile` returns **200** with body `hello:alice`.
- Wrong password: `PasswordEncoder.matches()` fails, so **401**.
- `blocked` has the right password but `enabled=false`, so **401**.
- Alice only has `ROLE_USER`, while `/admin/**` requires `ROLE_ADMIN`, so **403**.
- Admin has `ROLE_ADMIN`, so **200**.

On Windows PowerShell, use `curl.exe` instead of `curl` to avoid the alias; replace `/dev/null` with `NUL` when running directly on Windows. Statuses can differ in apps with form login enabled (e.g., 302 redirects), so test against your actual auth configuration.

## 10. Integration Tests Proving Real Data Is Used

Create `src/test/java/example/accounts/AccountSecurityTest.java`:

```java
package example.accounts;

import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountRepository accounts;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotViewProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanAuthenticateUsingDatabaseHash() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:alice"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("unknown", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void disabledAccountIsRejected() throws Exception {
        mvc.perform(get("/profile").with(httpBasic("blocked", "blocked-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userCannotAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report").with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void passwordIsStoredAsHash() {
        Account alice = accounts.findByUsername("alice").orElseThrow();

        assertThat(alice.getPasswordHash()).startsWith("{bcrypt}");
        assertThat(alice.getPasswordHash()).isNotEqualTo("alice-pass");
        assertThat(encoder.matches("alice-pass", alice.getPasswordHash())).isTrue();
        assertThat(encoder.matches("wrong", alice.getPasswordHash())).isFalse();
    }

    @Test
    void newlyCreatedDatabaseAccountCanAuthenticate() throws Exception {
        String username = "fresh-" + UUID.randomUUID();
        Account created = accounts.save(new Account(
            username,
            encoder.encode("fresh-pass"),
            true,
            Set.of("ROLE_USER")
        ));

        try {
            mvc.perform(get("/profile")
                    .with(httpBasic(username, "fresh-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello:" + username));
        } finally {
            accounts.deleteById(created.getId());
        }
    }
}
```

**Expected:** when running `mvn test` with the exact source, **10 tests pass**. This is the expected logical outcome, not a report of a build run in the current workspace.

The last test is especially valuable: it **inserts a new account into the repository** and immediately authenticates with it over HTTP Basic. If the application were still authenticating against a hardcoded user list, this test would fail. A random username is used and the record is deleted in `finally` to avoid polluting test state. In parallel test suites, use isolated databases or stronger test isolation.

### 10.1. Which test catches which bug?

| Behavior | Correct signal | Bug it catches |
| --- | --- | --- |
| Public endpoint | 200 | Accidentally locking down the entire API when editing `SecurityFilterChain`. |
| Anonymous to protected endpoint | 401 | Endpoint accidentally exposed or filter chain missing. |
| Alice valid password | 200 | `UserDetailsService` not wired up, hash stored in wrong format. |
| Alice wrong password | 401 | Custom broken password check or password check skipped. |
| Nonexistent username | 401 | Service returning an unsafe fallback user. |
| Disabled account | 401 | Ignoring `enabled` or inverting its boolean mapping. |
| USER to admin | 403 | Wrong role prefix or broken route matcher. |
| ADMIN to admin | 200 | Roles not loaded from DB or overly strict policy. |
| Hash inspection | `{bcrypt}` and `matches()` valid | Storing plaintext password or encoding at the wrong step. |
| New DB user logs in | 200 | App still reading from `InMemoryUserDetailsManager` instead of DB. |

**Distinguishing 401 and 403:** 401 typically indicates missing/failed authentication; 403 indicates an authenticated principal lacking authority. With form login, failure may redirect to the login page; test actual behavior rather than assuming HTTP Basic status codes apply to every app.

## 11. Migrating Real Data from Legacy Stores to the Database

In real projects, "replacing the sample store" usually takes two steps: switching the **login account lookup path** and **loading/migrating existing production account data**. Switching only the service without migrating data can leave every user getting 401.

### 11.1. Inventorying input data

Before switching, build a detailed mapping:

| Existing source | Target column | What to verify |
| --- | --- | --- |
| Login username/email | `username` | Case sensitivity, Unicode, uniqueness, duplicate accounts. |
| Password | `password_hash` | Current hashing algorithm, salt, work factor, prefix ID, any incompatible hashes. |
| Account status | `enabled`, `locked`, ... | Whether locked/expired accounts might accidentally become active during migration. |
| Role/group/scope | `app_account_authorities` or standard role mapping | `ROLE_` prefix, many-to-many relations, tenant permissions. |
| User ID | `id` and related foreign keys | Avoid breaking references from orders, audits, file owners, or other data. |
| Operational metadata | createdAt, updatedAt, version, lastPasswordChange | Needed for administration, auditing, sync, and permission changes. |

If the old source is an `InMemoryUserDetailsManager` with a few test users, **never carry test accounts over into production**. For existing stores with millions of users, design a measured backfill and cutover plan with rollback—never migrate records lazily in a loop inside login requests unless intentionally designed as a controlled upgrade.

### 11.2. Schema migration for a real database

Replace demo H2 with PostgreSQL/MySQL suited to the app. An **illustrative PostgreSQL DDL** to visualize the schema (do not run alongside Hibernate `create-drop`):

```sql
CREATE TABLE app_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE app_account_authorities (
    account_id BIGINT NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, authority)
);
```

Put DDL in Flyway/Liquibase migrations, switch production to schema validation (`spring.jpa.hibernate.ddl-auto=validate`), and verify backfills and indexes before cutover. Database unique constraints protect against duplicate username registrations across multiple instances. Real schemas may need extra columns (locks, tenant, version, reset token metadata) driven by application policy; do not add fields arbitrarily to a sample and treat it as universally complete.

### 11.3. Legacy passwords: do not "re-encode" stored hashes

- If the source already stores BCrypt, PBKDF2, scrypt, or Argon2, you do not know the original passwords. You **cannot** convert an old hash to a new hash via `encode(oldHash)` and expect users to log in.
- `DelegatingPasswordEncoder` uses prefixes like `{bcrypt}`, `{pbkdf2}`, etc. to pick the matching decoder. When importing legacy **already-hashed passwords lacking prefixes**, build a verified encoder mapping or prepend the prefix **matching the exact algorithm**—never slap `{bcrypt}` onto a hash from another algorithm.
- A standard migration path is to verify with a temporarily accepted legacy encoder and **rehash from the raw password received on the next successful login** via an authorized hash-upgrade component (such as `UserDetailsPasswordService` when properly configured). Prerequisite: the legacy algorithm must still be safe enough to verify during the transition window.
- If the legacy source stored plaintext passwords (a severe security issue), prioritize risk mitigation, migrate to strong hashing or controlled password resets, and never log or transmit passwords over unprotected channels.
- To change work factors, plan performance benchmarks and gradual upgrades; BCrypt is intentionally salted and compute-heavy, not a fast general-purpose hash.

### 11.4. Cutover and rollback

A practical workflow:

1. Lock down the current login path, providers, and actual user source, recording baseline 200/401/403 tests.
2. Design the schema and normalize username/authority/password-hash data; inspect special accounts.
3. Deploy schema migrations in staging and verify backfill: row counts, unique collisions, null/missing roles, disabled accounts.
4. Implement the new `UserDetailsService` and test both the repository and authentication in a production-like environment.
5. Test logins across cohorts (old/new users, special roles, locked accounts) and measure error rates and query latency.
6. Cut over per the approved plan, monitoring authentication failures and connection-pool health; keep a **non-destructive** schema/code rollback plan.
7. Once stable, remove the sample store from production config and stop accepting demo credentials.

Never add a fallback "if the database fails, log in with a demo user." When the real identity store is down, authentication must fail safely alongside proper monitoring and incident response.

## 12. Alternative Approaches: Choose Based on Existing Data Structure

**A. Custom schema with JPA (primary example).** Fits systems that already have user/entity tables and integrate with services/repositories. Requires careful modeling, migrations, queries, and transactions.

**B. Standard Spring Security JDBC.** `JdbcUserDetailsManager` is a built-in implementation for Spring Security's default `users` and `authorities` schema. Example **standalone replacement—do not register alongside the `DatabaseUserDetailsService` bean above**:

```java
@Bean
UserDetailsService jdbcUserDetailsService(DataSource dataSource) {
    return new JdbcUserDetailsManager(dataSource);
}
```

This fragment requires imports for `DataSource`, `UserDetailsService`, `JdbcUserDetailsManager`, and a `@Configuration` class. The default configuration expects matching table and column names; against this example's `app_accounts` table it will not run without customizing queries/mappings. JDBC can also run custom SQL queries against a custom schema while still returning password hashes, statuses, and authorities in the expected types.

**C. LDAP/Active Directory or Identity Provider.** If your organization owns users in LDAP/IdP, integrate the matching provider rather than copying passwords into the app database. With OAuth2/OIDC login or Resource Servers, authentication mechanics differ and **not every request** goes through `UserDetailsService`. Pick modules matching the authentication architecture instead of forcing every identity flow through `DaoAuthenticationProvider`.

**D. Multiple account sources.** When separating internal/external users or migrating incrementally, design explicit provider ordering, username namespacing, authority sources, duplicate-account handling, and source-outage behavior. Never let a fallback downgrade authentication strength.

## 13. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Login with new user always returns 401 | `DatabaseUserDetailsService` is not the bean used by the provider, or username is missing in DB | Test creating an account via repository then logging in; inspect provider/manager wiring. |
| Log `There is no PasswordEncoder mapped for id "null"` | Legacy hash lacks a prefix while using `DelegatingPasswordEncoder` | Identify the legacy algorithm and configure compatible mapping without disabling encoding. |
| 401 despite typing right password | Hash was double-encoded, stored raw, or user is disabled/locked | Check `encoder.matches(raw, storedHash)` and status flags. |
| 403 when user visits `/admin/**` | DB stores `ADMIN` while `hasRole("ADMIN")` expects `ROLE_ADMIN` | Inspect actual `GrantedAuthority` values on `UserDetails`. |
| 500 or `LazyInitializationException` reading authorities | Lazy JPA collection accessed outside a transaction | Fetch eagerly/explicitly or map to a DTO inside the transaction. |
| Two or more `UserDetailsService` beans | Leftover `InMemoryUserDetailsManager` or another auth config | Remove the sample bean or configure explicit provider routing and test. |
| No users after restart | Still using in-memory H2 or `ddl-auto=create-drop` | Use a persistent DB, migrations, and environment-appropriate backups. |
| Disabled account still uses existing session | User status is checked at login; sessions/tokens have separate lifecycles | Build session invalidation, token lifetime/revocation, or access-time checks as needed. |
| DB queries suddenly become slow | N+1 authorities, undersized connection pool, missing username index | Analyze query plans, fetch strategies, metrics, and caching. |
| Cross-tenant access still returns 200 | Checked only broad role without checking resource owner/tenant | Add authorization in service/repository; write cross-tenant tests. |
| Unauthenticated Basic returns 302 instead of 401 | Form login or another entry point is active | Read `SecurityFilterChain` configuration and test per actual auth mechanism. |
| Logins fail during DB downtime | DB is the identity source and is currently unavailable | Monitor/retry per design; never fall back to sample passwords. |

### Layer-by-layer debugging tips

On a 401, check in order: does the request carry credentials → did the security filter chain match → which provider is actually running → did the repository return an account → do the hash and encoder match → what are `enabled/locked/expired`? On a 403, separate authenticated-but-lacking-authority from CSRF rejection; never jump to conclusions from the status code alone.

You can enable Spring Security `DEBUG` logging **in test environments** to observe the filter chain and authentication path, while never logging raw passwords, tokens, hashes, or sensitive data. Especially in client error responses, avoid distinguishing "user does not exist" from "wrong password" if doing so enables account enumeration.

## 14. Pre-Production Security Checklist

- [ ] Removed `InMemoryUserDetailsManager` and default dev accounts from production auth paths; if multiple providers exist, documented ordering and routing.
- [ ] DB enforces unique usernames, normalizes values per policy, and is managed via verifiable migrations.
- [ ] Passwords are encoded by an appropriate `PasswordEncoder` with valid prefixes/legacy migration; zero plaintext storage.
- [ ] `enabled`, `locked`, `expired`, and authorities from the DB map faithfully to `UserDetails`.
- [ ] Authorities are granted through trusted business logic, never accepted arbitrarily from clients.
- [ ] Tests cover success, wrong password, missing user, disabled user, missing role, valid role, and newly created DB accounts.
- [ ] Strategy exists for permission changes during active sessions/JWTs, caches, and in-flight requests; consistency limits are documented.
- [ ] DB connections use TLS and externally managed secrets; schema migrations, backups, and audits work.
- [ ] Entities containing hashes are never exposed via controllers/JSON; auth errors leak neither credentials nor internals.
- [ ] Rate limiting, lockout, and abuse prevention are configured alongside security and privacy-safe audit logging.
- [ ] Production CSRF/session/CORS/HTTPS are verified against client types and threat models; CSRF is not disabled by habit.
- [ ] Regression tests re-run after Spring Boot/Spring Security upgrades with actual dependency versions verified.

## 15. Official Documentation for Further Self-Study

- Spring Security — `UserDetailsService`: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Username/Password Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/
- Spring Security — Password Storage / `DelegatingPasswordEncoder`: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — JDBC Authentication / default schema: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/jdbc.html
- Spring Boot 3.3 — Spring Security auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Data JPA — Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html

**Exercise outcome:** the account source moves from sample configuration to a repository holding application data; `UserDetailsService` returns accurate hashes, statuses, and authorities from the database; `DaoAuthenticationProvider` continues to handle password verification; and `SecurityFilterChain` continues to handle HTTP authorization. When a test inserts a new account into the database and logs in successfully without touching security code, you have proven the replacement at the right boundary.
