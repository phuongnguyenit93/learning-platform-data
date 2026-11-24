# Integrating JPA or a Business Account Store via UserDetailsService

> **Context:** Spring Security – authentication, **Account Store** knowledge group. This lesson focuses on bringing account data from Spring Data JPA or an existing business service into Spring Security's username/password authentication mechanism. Examples use **Java 17+**, **Spring Boot 4**, **Spring Security 7**, Spring Data JPA, and H2; explaining responsibility boundaries, query design, `UserDetails` mapping, testing, and real-world risks.

## 1. Why Do We Need a Custom UserDetailsService?

Applications often already have a user system before adding Spring Security:

- An `app_accounts` table managing usernames, password hashes, and account status.
- Related tables storing roles, permissions, or account–organization relationships.
- A business service or identity service with an API for looking up accounts.
- Workflows for registration, password changes, account locking, and granting/revoking permissions.

Spring Security needs to verify credentials, yet **does not know** the application's custom schema. Putting JPA entities directly into every security component couples code to persistence, lazy loading, and business structures. Rewriting password comparison logic inside a controller easily misses account status checks, error handling, or built-in security mechanisms.

`UserDetailsService` solves this problem with a **read-data contract**: Spring Security asks to "load the authentication record by username", while the application decides where to find the account and how to map it to `UserDetails`.

```text
HTTP Basic / Form Login: username, password sent by client
                          |
                          v
                 Authentication Filter
                          |
                          v
                AuthenticationManager
                          |
                          v
               DaoAuthenticationProvider
                    |              |
                    |              +--> PasswordEncoder
                    |                   verifies password against hash
                    v
             UserDetailsService
                    |
                    +--> Spring Data JPA Repository
                    |         |
                    |         +--> Database account + authorities
                    |
                    +--> Or a trusted domain account service
                    |
                    v
               UserDetails adapter
               username, hash, flags, authorities
                    |
                    v
          Authenticated Authentication (if valid)
                    |
                    v
          SecurityContext + authorization
```

**Key point:** `UserDetailsService` **loads the account record**, while `DaoAuthenticationProvider`/**`PasswordEncoder`** **verifies** the credential. Finding a username in the database does not prove that the sender of the request owns that account.

## 2. The Exact Contract of UserDetailsService

The `org.springframework.security.core.userdetails.UserDetailsService` interface has one core method:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

This is a **condensed API signature**, not a standalone Java file. Points in the contract:

1. `username` is the lookup identifier from the authentication request; it is **not yet a proven identity**.
2. The result must be a `UserDetails` populated with the fields needed for subsequent checks.
3. **Never return `null`** when the account cannot be found. Throw `UsernameNotFoundException`.
4. The contract also treats a user with zero `GrantedAuthority` instances as not found; when business policy permits an account with no permissions, clearly define how to represent a minimal authority or an alternative policy rather than silently assigning sensitive authorities.
5. `UserDetailsService` is a **read-only contract**; it is not responsible for creating users, changing passwords, or performing login. Administrative operations belong in a dedicated service/repository or `UserDetailsManager` if the application adopts that contract.
6. Do not build a successful `Authentication`, attach `SecurityContextHolder`, or issue tokens/cookies inside `loadUserByUsername`.
7. The `UserDetails` username may differ in letter case from the requested string when the application supports case-insensitive lookup. A compatible normalization/uniqueness policy must exist in the database.

### What Does UserDetails Contain?

A `UserDetails` implementation typically provides:

| Method | Value source | Purpose |
| --- | --- | --- |
| `getUsername()` | Server-managed username | Account name after lookup |
| `getPassword()` | **Password hash**, not plaintext | Passed by the provider to `PasswordEncoder.matches(...)` |
| `getAuthorities()` | Roles/permissions mapped from a trusted source | Authorization after authentication |
| `isEnabled()` | Account activation flag | May lead to `DisabledException` |
| `isAccountNonLocked()` | `true` when unlocked | `false` may lead to `LockedException` |
| `isAccountNonExpired()` | `true` when account is still valid | `false` may lead to `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` when credentials are still valid | `false` may lead to `CredentialsExpiredException` |

Spring Security provides the `org.springframework.security.core.userdetails.User` implementation and the `User.withUsername(...)` builder to avoid manually implementing the whole interface in demos. For an application principal that needs a **stable internal ID**, you can create a custom `UserDetails` or a dedicated converter, but you should not put a JPA entity rich in sensitive data directly into the principal.

### What UserDetailsService Does Not Do

- **Does not compare raw password against hash**: this belongs to `PasswordEncoder` and the provider.
- **Does not decide per-resource permissions**: `report:read` is only a general authority; viewing a report belonging to another tenant must still be checked by domain authorization.
- **Does not replace OAuth2 Resource Server**: JWT/bearer tokens normally go through decoders/converters and do not implicitly call `UserDetailsService`.
- **Does not guarantee authorities are refreshed on every request**: sessions, tokens, and caches have their own lifecycles.

## 3. Separating Responsibilities Between Persistence, Adapter, and Security

A clean structure has three layers:

```text
                    ┌──────────────────────────────┐
                    │ Security Filter / Provider   │
                    │ credential + account status  │
                    └─────────────┬────────────────┘
                                  │
                                  v
                    ┌──────────────────────────────┐
                    │ JpaUserDetailsService        │
                    │ implements UserDetailsService│
                    │ maps DomainAccount -> User   │
                    └─────────────┬────────────────┘
                                  │
                                  v
                    ┌──────────────────────────────┐
                    │ AccountRepository            │
                    │ @EntityGraph(authorities)    │
                    └─────────────┬────────────────┘
                                  │
                                  v
                    ┌──────────────────────────────┐
                    │ Database: accounts + grants  │
                    └──────────────────────────────┘
```

**Repository** is responsible for JPA queries. **Service/adapter** enforces the identity contract, verifies that source data is usable, and maps statuses and authorities. **Provider** verifies credentials and issues a trusted authentication result. **SecurityFilterChain** chooses how credentials are received and HTTP access policies.

Avoid putting all SQL logic, password checking, authority conversion, and HTTP response creation inside a `/login` controller. Also do not pass `HttpServletRequest` into a domain account service just to extract username/tenant: establish a trusted information-passing boundary and clear policies.

### What Is Special About a JPA Data Source?

- JPA-managed entities may contain `LAZY` relationships. After the transaction closes, reading roles/authorities can easily trigger `LazyInitializationException`.
- Many small queries can cause N+1 queries.
- Entities can be mutated inside a transaction; never use a mutable entity as a long-lived user principal across multiple requests.
- Username queries need an explicit uniqueness policy and must account for concurrency and renames.
- The database can fail transiently. Never "fail open" by granting a fallback default user.
- An account can exist while disabled, locked, or credential-expired; these are still real records whose status must be mapped.

In the example below, we use `@Transactional(readOnly = true)` to perform the read inside a transaction and `@EntityGraph` to load the authorities collection during the lookup.

## 4. Minimal Account Table Design for Authentication

The example uses two tables:

```text
app_accounts
  id                  UUID PRIMARY KEY
  username            VARCHAR UNIQUE NOT NULL
  password_hash       VARCHAR NOT NULL
  enabled             BOOLEAN NOT NULL
  locked              BOOLEAN NOT NULL
  account_expired     BOOLEAN NOT NULL
  credentials_expired BOOLEAN NOT NULL

app_account_authorities
  account_id          UUID REFERENCES app_accounts(id)
  authority           VARCHAR NOT NULL
```

The second table stores **authority names already shaped by the business contract**, such as `ROLE_USER` and `report:read`. This is an **illustrative model** to focus on JPA/`UserDetailsService`. In a larger application, the domain might store `users`, `roles`, `permissions`, `user_roles`, and `role_permissions` and map them into the corresponding strings.

### Why Store a Hash Instead of Plaintext?

When a user registers or changes their password, the server receives the password **only at creation/change time** and uses `PasswordEncoder.encode(raw)` to store an appropriate hash. On login, `DaoAuthenticationProvider` uses `PasswordEncoder.matches(raw, encoded)` to verify, rather than reading plaintext from the DB or hashing raw input and naively comparing hash strings (BCrypt uses salt, so encoding the same input twice produces different outputs).

### Status Flags Must Be Consistent

In the domain schema we store `locked`, `accountExpired`, and `credentialsExpired` as "bad-state" flags. When building `UserDetails`, the builder uses `accountLocked(true)`, `accountExpired(true)`, and `credentialsExpired(true)`. If implementing `UserDetails` directly, `isAccountNonLocked()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()` have **negated** semantics, so invert the values properly.

Note: "subscription expired" is not always "account expired". Many systems still let users log in to view invoices or renew; that is a different business rule.

## 5. Runnable Example: Spring Boot 4 + Spring Data JPA + H2

The following example provides **complete files** runnable with Java 17+. Create a new Maven project with the structure:

```text
jpa-auth-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jpaauth/
    │   ├── JpaAuthDemoApplication.java
    │   ├── AccountEntity.java
    │   ├── AccountRepository.java
    │   ├── JpaAccountUserDetailsService.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── resources/application.properties
```

The model has three accounts:

| Username | Demo password | Status | Authorities |
| --- | --- | --- | --- |
| `an` | `demo-pass` | Active | `ROLE_USER`, `report:read` |
| `binh` | `demo-pass` | Active | `ROLE_ADMIN` |
| `khoa` | `demo-pass` | Locked | `ROLE_USER` |

This data is for learning only and is not secure credentials for a real environment.

### 5.1. `pom.xml`

Spring Boot 4 uses the `spring-boot-starter-webmvc` starter for Spring MVC. The Maven parent manages the versions of the remaining dependencies.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jpa-auth-demo</artifactId>
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
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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
```

You can use Spring Initializr to generate the Maven wrapper and a stable release on the Spring Boot 4.x branch; if choosing another branch, check starter names and API compatibility. The example pins `4.0.0` so learners have a reproducible setup, not as a requirement for every production project to use this exact version.

### 5.2. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:authdemo;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` drops/creates the schema for the **in-memory H2 demo** and must not be used in production because it can destroy data. `spring.jpa.open-in-view=false` helps catch accidental LAZY relationship access outside transactions, while encouraging the adapter to load all needed data inside the transaction boundary. The in-memory database disappears when the application stops.

### 5.3. `AccountEntity.java` — JPA entity, not the principal

```java
package com.example.jpaauth;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

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
public class AccountEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 100)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @Column(nullable = false)
    private boolean locked;

    @Column(name = "account_expired", nullable = false)
    private boolean accountExpired;

    @Column(name = "credentials_expired", nullable = false)
    private boolean credentialsExpired;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "app_account_authorities",
            joinColumns = @JoinColumn(name = "account_id"))
    @Column(name = "authority", nullable = false, length = 120)
    private Set<String> authorities = new HashSet<>();

    protected AccountEntity() {
        // JPA requires a no-arg constructor.
    }

    public AccountEntity(String username,
                         String passwordHash,
                         boolean enabled,
                         boolean locked,
                         boolean accountExpired,
                         boolean credentialsExpired,
                         Set<String> authorities) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.enabled = enabled;
        this.locked = locked;
        this.accountExpired = accountExpired;
        this.credentialsExpired = credentialsExpired;
        this.authorities = new HashSet<>(authorities);
    }

    public UUID getId() {
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

    public boolean isLocked() {
        return locked;
    }

    public boolean isAccountExpired() {
        return accountExpired;
    }

    public boolean isCredentialsExpired() {
        return credentialsExpired;
    }

    public Set<String> getAuthorities() {
        return Set.copyOf(authorities);
    }
}
```

Things to notice:

- `id` is a persistence-generated UUID and can serve as a **stable internal user ID**, even if the username changes. This example does not put the ID into the principal yet; if business services need the ID, design a dedicated custom principal rather than using username as an ownership key.
- `passwordHash` is for password verification and must never be returned directly in APIs or written to logs.
- `authorities` is `LAZY`. `@EntityGraph` on the repository instructs JPA to load the collection during the authentication lookup.
- `AccountEntity` **does not implement UserDetails**. Separating the entity from Security APIs helps control what data enters `Authentication`.
- `getAuthorities()` returns an unmodifiable copy, preventing external code from accidentally mutating the authority set stored on the entity.
- The entity has a `protected` no-arg constructor for JPA instantiation; avoid adding unnecessary setters merely for the security adapter's convenience.

### 5.4. `AccountRepository.java` — querying account and authorities

```java
package com.example.jpaauth;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<AccountEntity, UUID> {

    @EntityGraph(attributePaths = "authorities")
    Optional<AccountEntity> findByUsername(String username);

    boolean existsByUsername(String username);
}
```

`@EntityGraph(attributePaths = "authorities")` instructs JPA to load the authority set alongside the account in this lookup. For a small collection like this demo, it is easy to follow. When there are multiple complex collections/roles/permissions, measure the actual queries; multiple fetch joins can cause a Cartesian product or memory pressure. Never set `EAGER` on all entity relationships just because `UserDetailsService` needs authorities.

`Optional<AccountEntity>` represents the case where no record is found. The adapter converts it into `UsernameNotFoundException` per the contract. Never call `Optional.get()` without checking for presence.

### 5.5. `JpaAccountUserDetailsService.java` — authentication adapter

```java
package com.example.jpaauth;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaAccountUserDetailsService
        implements UserDetailsService {

    private final AccountRepository accounts;

    public JpaAccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = accounts.findByUsername(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Unknown user"));

        String[] authorityNames =
                account.getAuthorities().toArray(String[]::new);

        if (authorityNames.length == 0) {
            // The demo chooses to reject accounts without authorities.
            throw new UsernameNotFoundException(
                    "Account has no authorities");
        }

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(authorityNames)
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .accountExpired(account.isAccountExpired())
                .credentialsExpired(account.isCredentialsExpired())
                .build();
    }
}
```

**This is the central boundary of the lesson:**

1. `AccountRepository` looks up the data by username.
2. The adapter reads the password hash, status flags, and authorities inside a read-only transaction.
3. If no user exists, it throws `UsernameNotFoundException`; **never return null, and never return a fake user with elevated permissions**.
4. The normalized source authority set is passed into `UserDetails` as authority strings. `User.UserBuilder` converts them into `GrantedAuthority` instances.
5. The adapter **does not** call `PasswordEncoder.matches(...)` and **does not** build an authenticated token itself.
6. Builder mapping uses "bad-state" flags: `disabled(!enabled)`, `accountLocked(locked)`, `accountExpired(accountExpired)`, `credentialsExpired(credentialsExpired)`.
7. Once the method finishes, `UserDetails` is an object detached from the JPA entity; the provider does not depend on the JPA transaction remaining open.

For data with zero authorities, the demo chooses to reject. Depending on business needs, you might assign a minimal `ROLE_USER` authority for profile-only accounts, but only when **that is an explicitly defined policy**—never add `ROLE_ADMIN` or `report:read` automatically due to missing data.

### 5.6. `SecurityConfiguration.java` — provider, encoder, and rules

```java
package com.example.jpaauth;

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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JpaAccountUserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder)
            throws Exception {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);

        return http
                .authenticationProvider(provider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/reports")
                            .hasAuthority("report:read")
                        .requestMatchers("/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

`DaoAuthenticationProvider` fetches `UserDetails` from the adapter and uses BCrypt to verify the password. If username/password/status are valid, Spring Security issues the request's `Authentication`. If credentials are wrong or the account is locked or disabled, the mechanism produces the appropriate authentication failure.

The `hasAuthority("report:read")` rule requires the exact string `report:read`. The `hasRole("ADMIN")` rule looks for `ROLE_ADMIN` by default. These are **authorization rules**, independent of looking up the account in the database.

The example only uses **GET** and HTTP Basic for illustration. In applications using browsers, sessions/cookies, and state-changing operations, preserve or design proper CSRF protection; never disable CSRF globally just to make a login demo run.

### 5.7. `JpaAuthDemoApplication.java` — seeding demo data

```java
package com.example.jpaauth;

import java.util.Set;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class JpaAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaAuthDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner seedAccounts(
            AccountRepository repository,
            PasswordEncoder encoder) {

        return args -> {
            if (!repository.existsByUsername("an")) {
                repository.save(new AccountEntity(
                        "an", encoder.encode("demo-pass"),
                        true, false, false, false,
                        Set.of("ROLE_USER", "report:read")));
            }

            if (!repository.existsByUsername("binh")) {
                repository.save(new AccountEntity(
                        "binh", encoder.encode("demo-pass"),
                        true, false, false, false,
                        Set.of("ROLE_ADMIN")));
            }

            if (!repository.existsByUsername("khoa")) {
                repository.save(new AccountEntity(
                        "khoa", encoder.encode("demo-pass"),
                        true, true, false, false,
                        Set.of("ROLE_USER")));
            }
        };
    }
}
```

`CommandLineRunner` seeds data after JPA/H2 initializes. `repository.save(...)` performs writes so H2 has accounts for testing. Passwords are stored as BCrypt hashes; using the same demo password for all three users is solely to simplify observation.

In production, account creation must be a workflow with input validation, password policy checks, unique usernames, transactions, and race-condition handling; never create admin accounts via `CommandLineRunner` or hardcode passwords.

### 5.8. `DemoController.java` — observing Authentication

```java
package com.example.jpaauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }

    @GetMapping("/reports")
    String reports() {
        return "reports ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

The controller does not accept a password, does not call the repository to "re-check the user", and does not read `?role=...` from the client to grant permissions. It reads the principal name placed into `Authentication` by the authentication mechanism. `/me` is intended to illustrate the flow; real applications should consider returning only the required ID/profile and never serializing raw `Authentication` to JSON.

## 6. Running the Example and Checking Output

Requires JDK 17+, Maven 3.9+ or a compatible wrapper, and permission to download Maven dependencies. From the `jpa-auth-demo` directory:

```bash
mvn spring-boot:run
```

If the project was generated via Spring Initializr with a wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell can run `.\mvnw.cmd spring-boot:run`. In-memory H2 starts empty, the schema is created, and the three accounts are seeded on startup. Do not invoke `javac` directly on individual files because they require Spring Boot/JPA/Security dependencies.

Open another terminal and run:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-pass http://localhost:8080/me
curl -s -u an:demo-pass http://localhost:8080/reports
curl -s -u binh:demo-pass http://localhost:8080/admin
```

**Expected body in order for the four commands:**

```text
pong
principal=an
reports ok
admin ok
```

Test rejection cases:

```bash
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u khoa:demo-pass http://localhost:8080/me
curl -i -u an:demo-pass http://localhost:8080/admin
curl -i -u binh:demo-pass http://localhost:8080/reports
```

With the demo's HTTP Basic configuration, **the first three requests** normally return **401 Unauthorized** (no credentials, wrong password, locked account). **The last two requests** return **403 Forbidden** because the caller is authenticated but lacks the required authority. Error bodies/headers depend on version/configuration; the Basic challenge usually includes `WWW-Authenticate` on 401.

If using PowerShell and `curl` is aliased to another cmdlet, substitute `curl.exe`. HTTP Basic only encodes credentials with Base64, **not secure encryption**. The demo uses localhost; real applications must deploy HTTPS and manage passwords/secrets properly.

### Analyzing a Successful Request

When running `curl -u an:demo-pass /reports`:

1. The Basic authentication filter reads the header containing username/password.
2. The provider calls `JpaAccountUserDetailsService.loadUserByUsername("an")`.
3. The repository fetches the account and authorities `ROLE_USER`, `report:read` from H2; `@EntityGraph`/transaction ensures the data is available during mapping.
4. The adapter returns `UserDetails` with the BCrypt hash, flags, and authorities.
5. `DaoAuthenticationProvider` checks the raw password against the hash; only on success does it return an authenticated `Authentication`.
6. The `hasAuthority("report:read")` rule is satisfied, so the controller returns `reports ok`.

When running `curl -u binh:demo-pass /reports`, the provider still authenticates Binh, but `Authentication` only has `ROLE_ADMIN` per the demo policy. The rule requiring `report:read` **is not met**, so the request is blocked. `ROLE_ADMIN` does not implicitly grant every permission unless the system configures a different mapping or role hierarchy.

### How Do You Know the App Is Actually Using the Database?

Try modifying an account in the managed data source and restarting/re-authenticating per your workflow, then verify the authorities update per policy; with H2 `create-drop`, data disappears between restarts. In real environments, use a persistent database, schema migrations, and repository/SQL tests rather than relying on an auto-generated default Spring Security account.

## 7. Using Another Business Store Instead of JPA

`UserDetailsService` does not mandate Spring Data JPA. The backing store could be:

- `JdbcTemplate`/direct SQL with parameterized queries.
- An existing account/domain service inside the same application.
- An internal user service providing results over a trusted API.
- A directory or LDAP suited to the organization's model.
- An adapter to another data store with clear read, status-checking, and permission semantics.

A skeleton for a business store:

```java
@Service
class DomainUserDetailsService implements UserDetailsService {

    private final AccountQueryService accountQueries;

    DomainUserDetailsService(AccountQueryService accountQueries) {
        this.accountQueries = accountQueries;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        DomainAccount account = accountQueries.findByLogin(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Unknown user"));

        return User.withUsername(account.login())
                .password(account.encodedPassword())
                .authorities(account.authorityNames().toArray(String[]::new))
                .disabled(!account.enabled())
                .build();
    }
}
```

This is a **design snippet** and requires Spring Security imports plus your application's `AccountQueryService` and `DomainAccount` to compile. Never register two `UserDetailsService` beans side-by-side for the same purpose without specifying which provider uses which. Authentication mechanisms should be explicitly configured when multiple stores exist.

**The contract stays unchanged:** look up user -> obtain hash/flags/authorities from a trusted source -> map to `UserDetails` -> let the provider verify credentials. If an external service **already authenticates using its own protocol** without returning a valid password hash, do not try to fake `UserDetails.getPassword()` to use a DAO provider; use an appropriate `AuthenticationProvider` or an OIDC/OAuth2/LDAP solution.

### When the Account Service Is Remote

A remote call is not trustworthy merely because it is "on the internal network". You must define service-to-service authentication, timeouts, retries, circuit breakers, authority provenance, auditing, and behavior when the service is unavailable. If identity cannot be verified or required authorities cannot be retrieved, normally **deny authentication/authorization** rather than falling back to `ROLE_USER` or `ROLE_ADMIN` arbitrarily.

Never log raw passwords, raw bearer tokens, or session cookies in request logs/traces; limit personal data and credentials stored in caches/messages. A dedicated IDP may be a better fit for multi-service systems needing SSO.

## 8. Efficient JPA Queries and Avoiding LazyInitializationException

### Why Does LAZY Break Easily?

Suppose `AccountEntity` has `@OneToMany(fetch = LAZY)` or `@ManyToMany(fetch = LAZY)` for roles. If the adapter returns the JPA entity as the principal and code reads roles after the transaction closes, Hibernate may fail to load the collection. To prevent this:

- Fetch all fields needed for authentication within the transaction.
- Use `@EntityGraph(attributePaths = ...)` or a tailored query/projection.
- Map the entity **immediately** to a `UserDetails` object detached from the JPA session.
- Never enable `spring.jpa.open-in-view=true` just to mask controller errors; that keeps the persistence context open longer and can cause hidden queries in the web layer.

### `@EntityGraph` and N+1

The demo only has one `authorities` collection, so `@EntityGraph` makes authorities available in a single lookup. However, in complex domains (roles, permissions, groups, tenants), fetching multiple collections in the same query can multiply joined rows, consume memory, or hit ORM limits. Measure the SQL:

| Issue | Symptom | Remediation |
| --- | --- | --- |
| Lazy access after transaction | `LazyInitializationException` | Map inside the transaction and fetch the right associations |
| N+1 | One account query triggers many role/permission queries | Dedicated projection/query, batch fetch, or suitable entity graph |
| Cartesian product | One query returns huge row counts from joining multiple collections | Split queries, avoid fetching multiple collections simultaneously |
| Unindexed query | Slow username lookup | Unique index/normalization matching requirements |
| Duplicate username | Ambiguous which user to select | DB uniqueness, handle case sensitivity |
| Account missing authorities | Error or inconsistent rules | Predefined empty-authority policy |

Adding `@Transactional(readOnly = true)` to the method **does not replace** good query design; it marks the operation as read-only and keeps the transaction open during mapping. For non-JPA external stores, transaction/read-only semantics differ.

### Query Projections Can Be Better Than Full Entities

If the user entity is very large or roles span many tables, you can write a query returning only `username`, `passwordHash`, status flags, and authority names, and then build `UserDetails`. This reduces the risk of accidentally loading PII/profile fields. Still, you must handle uniqueness, multiplicity, and consistency when assembling results.

## 9. PasswordEncoder, Account Status, and Authentication Errors

### PasswordEncoder

`PasswordEncoder` is the component that verifies credentials:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String encoded = encoder.encode("demo-pass");
boolean valid = encoder.matches("demo-pass", encoded);
System.out.println(valid); // true
```

This is an **illustrative Java snippet** requiring Spring Security imports inside a method or classpath-configured JShell. BCrypt hashes include a salt, so calling `encode` multiple times typically yields different strings. Never use `encoded.equals(encoder.encode(raw))` to match.

For stores that have accumulated multiple hash algorithms over time, use `DelegatingPasswordEncoder` with the `{id}` prefix format and a managed migration strategy. Never pick `{noop}` or plaintext as a production solution just to "get login working".

### Account Flags

Translate flags accurately:

| Entity field | Builder call | Meaning |
| --- | --- | --- |
| `enabled=true` | `disabled(false)` | Not disabled |
| `locked=true` | `accountLocked(true)` | Account is locked |
| `accountExpired=true` | `accountExpired(true)` | Account has expired |
| `credentialsExpired=true` | `credentialsExpired(true)` | Credentials have expired |

In the DAO provider, account statuses can trigger `DisabledException`, `LockedException`, `AccountExpiredException`, or `CredentialsExpiredException`. If the username is absent, `UserDetailsService` throws `UsernameNotFoundException`; the default provider usually masks this so clients cannot easily enumerate accounts. Never expose raw exception messages or SQL errors in public HTTP responses.

An account may be locked after it **already has an active login session**. Updating a flag in the database does not automatically invalidate all existing sessions/tokens; you need policies for invalidation, token expiry, revocation, or checking current status on sensitive actions.

### DB Errors Are Different from Password Errors

If the database times out, a connection fails, or schema migrations are incomplete, the adapter must let the system record an **infrastructure error** rather than returning a fake user or skipping authentication. The framework's exception handler may produce an HTTP response depending on the mechanism, but telemetry must distinguish wrong passwords from datasource failures. Never log JDBC URLs containing credentials, passwords, or sensitive data in error responses.

## 10. Protecting Username Lookup and Avoiding Case-Sensitivity Bugs

Username/email is a **lookup key**, not necessarily a stable ID key. When an application allows changing username/email, use an internal account ID (such as a UUID) in foreign keys, ownership, and audits. Standard DAO `UserDetails` `Authentication.getName()` returns the username, not automatically the database UUID.

### Normalization Rules

Common options:

- Case-sensitive username: `An` and `an` may be two different accounts if the DB/schema permits it.
- Case-insensitive username: define a canonical form and supporting unique constraint so two usernames cannot differ only by letter case.
- Login by email: emails can change and require verification per policy; do not use email as an immutable ownership key.
- Multi-tenant: you may need a unique key `(tenant_id, normalized_username)` instead of a global username.

Do not apply `trim()` or `toLowerCase()` inconsistently across registration, login, and lookup; normalization needs an explicit contract, Unicode handling, and a matching unique index. In multi-tenant systems, any caller-supplied tenant ID must also be verified via a trusted context/protocol; never accept a self-declared header as a security boundary.

### Account Enumeration

Do not return "username does not exist" for one public request and "wrong password" for a real username. To curb user enumeration, the DAO provider has a policy to mask username-not-found, but the application must also manage timing, rate limiting, monitoring, and secure account recovery flows. Do not infer that encountering `BadCredentialsException` guarantees the account exists.

## 11. Mapping Business Permissions to GrantedAuthority

In the demo, `app_account_authorities` stores strings ready for Spring Security: `ROLE_USER`, `ROLE_ADMIN`, `report:read`. In a real domain, the source might store:

```text
users(id, username, password_hash, enabled)
roles(id, role_code)
permissions(id, permission_code)
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id)
```

The adapter or domain permission service must decide:

1. Role code `ADMIN` is converted to `ROLE_ADMIN` (following the default prefix).
2. Permission code `report:read` is kept as `report:read` and checked via `hasAuthority("report:read")`.
3. Permissions from multiple roles/direct grants are merged and deduplicated.
4. Unknown roles/permissions never become arbitrary elevated privileges; handle them according to a defined policy.
5. Authorities do not automatically imply owner/tenant checks. `report:read` only satisfies the general authority condition and does not decide which reports a user may read.

If a user has the `ADMIN` role, that **does not automatically** satisfy `hasAuthority("report:read")` unless the mapping grants that permission; never implicitly grant full access merely because a name says "ADMIN".

**Never accept a list of roles/permissions sent by the client at login** and convert it into `SimpleGrantedAuthority`. Permissions must come from a trusted server/issuer source after verifying all required conditions.

## 12. Caching and the UserDetails Lifecycle

Caching can reduce queries under heavy login load, but bad caching keeps stale authorities/statuses alive:

- `UserDetails` may contain the password hash, so cache storage must be protected and have an appropriate TTL.
- When passwords, roles, account locks, or enabled status change, an invalidation/refresh policy is needed.
- `ProviderManager` may erase credentials from `Authentication`/principal after success per contract; if a cache shares the same `UserDetails` instance, understand the impact of credential erasure so the cache does not break.
- Session-based login may keep `Authentication` in the session rather than calling `UserDetailsService` on every request.
- JWT bearer tokens have their own verification/claim-mapping flow; do not assume every JWT request queries JPA to load authorities unless you design it that way.

If up-to-date permissions are required for sensitive transactions, check them in a policy service instead of trusting the login-time snapshot completely. TTL/revocation rules must be tested in scenarios where a user is disabled or loses a role while their session/token is still active.

## 13. Testing: Targeted Checks for Repository, Adapter, and HTTP

Test along responsibility boundaries rather than only checking that a controller returns 200:

| Layer | Case | Expected outcome |
| --- | --- | --- |
| Repository | Find existing username | Returns the right account with authorities loaded |
| Repository | Non-existent username | `Optional.empty()` |
| Adapter | Existing account | `UserDetails` has accurate username, hash, flags, authorities |
| Adapter | Missing account | Throws `UsernameNotFoundException`, never returns `null` |
| Adapter | Account without authorities | Handled per fail-closed policy, grants no unexpected authorities |
| Provider | Correct password + active account | Authentication succeeds |
| Provider | Wrong password | Authentication fails |
| Provider | Locked account | Authentication fails even with correct password |
| HTTP | `/reports` as `an` | Succeeds due to `report:read` |
| HTTP | `/reports` as `binh` | 403 because `report:read` is missing |
| HTTP | `/admin` as `binh` | Succeeds due to `ROLE_ADMIN` |
| HTTP | Wrong/missing credentials | 401 in the Basic demo |
| Lifecycle | Revoke permission after login | Takes effect per defined refresh/revocation mechanism |
| Database | H2 down / missing table | Fails closed safely, emits telemetry |

For integration tests, you can use H2/a test database and `@DataJpaTest` or `@SpringBootTest` with the appropriate test dependencies. In Spring Boot 4, test starters are split by module; select the test dependency matching your stack. You do not need to write tests for every entity getter; focus on account loading, authority mapping, and access decisions.

### An Account-Change Test

Try simulating: account An currently has `report:read`; an administrator revokes the permission. Check both a new authentication and an existing session/token. The two results may differ because sessions/caches store snapshots; a sound design defines and enforces when revocation takes effect.

### Inspecting Actual SQL

Use dev/test query-monitoring tools to check whether `findByUsername` triggers N extra queries for authorities; inspect username query plans/indexes, and never log passwords/tokens while debugging. In production, avoid enabling unrestrained SQL logging that prints secret values.

## 14. Common Mistakes and How to Handle Them

| Mistake | Problem | Better approach |
| --- | --- | --- |
| `UserDetailsService` compares password to hash itself | Duplicates responsibility wrongly, easily misses policy | Let provider use `PasswordEncoder.matches` |
| Returning `null` when user is not found | Violates contract | Throw `UsernameNotFoundException` |
| Returning JPA entity as a long-lived principal | Lazy loading, mutation, data leaks | Map to a minimal `UserDetails`/principal |
| Storing raw passwords in DB | Exposes credentials | Store password hashes using a proper encoder |
| Using `{noop}` for demo and shipping to production | Passwords are unhashed | BCrypt/Argon2/`DelegatingPasswordEncoder` per policy |
| Calling `getAuthorities()` on a LAZY relation after transaction | `LazyInitializationException` | Transaction + fetch/projection, map in adapter |
| Enabling EAGER on all relationships | N+1 or massive queries | Query specifically for the authentication lookup |
| Defaulting unknown roles to ADMIN | Privilege escalation | Validate / fail closed |
| Using username/email as owner ID | Renames/reuse misattribute data | Use an immutable internal ID |
| Not enforcing username uniqueness | May ambiguously match multiple accounts | Unique index + canonicalization |
| Running Basic over public HTTP | Exposes credentials easily | HTTPS, TLS, protect logs |
| Using `?role=ADMIN` as authority | Caller self-elevates privileges | Read authorities only from trusted sources |
| Treating auth success as full resource permission | IDOR, cross-tenant | Resource/tenant authorization |
| Disabling user without handling old sessions | Permissions persist in old sessions | Session/token revocation/refresh |
| Returning a "fallback" user on DB error | Fail open | Deny authentication, alert operations |
| Returning raw `Authentication` as JSON to client | Can leak hash/PII/claims | DTO limited to needed fields |

## 15. Self-Check Questions

**Question 1.** `loadUserByUsername("an")` returns a `UserDetails`. Has An logged in successfully yet?  
**Answer:** No. That is only the record-loading step; `DaoAuthenticationProvider` still has to verify credentials and account status.

**Question 2.** Does putting `@Transactional(readOnly = true)` on the adapter replace `@EntityGraph`?  
**Answer:** No. The transaction keeps the persistence scope open while reading; the entity graph/projection determines what data is loaded. The two solve different problems.

**Question 3.** The repository returns `Optional.empty()`. May the adapter return `null`?  
**Answer:** No. Throw `UsernameNotFoundException` per the `UserDetailsService` contract.

**Question 4.** Why should `AccountEntity` not implement `UserDetails` directly in every case?  
**Answer:** It couples persistence to security and risks exposing lazy collections, mutable state, hashes, and unnecessary fields inside a long-lived principal. An adapter separates responsibilities and data.

**Question 5.** The database stores authority `ROLE_ADMIN`. Does the rule `hasAuthority("report:read")` automatically allow it?  
**Answer:** No. The authority string must match the rule or a properly configured policy/role hierarchy.

**Question 6.** Why must the password hash from the repository be placed into `UserDetails.getPassword()`?  
**Answer:** Because `DaoAuthenticationProvider` needs the hash and `PasswordEncoder` to verify the raw password from the request. Never store or compare plaintext in the repository.

**Question 7.** If an account is locked after a session already exists, will `UserDetailsService` be called again on the next request?  
**Answer:** Not guaranteed. The session may hold the old authentication; you need policies for revocation, refresh, or checking account state.

**Question 8.** Another API authenticates via signed JWTs. Must it call the JPA `UserDetailsService` on every request?  
**Answer:** No. Resource servers typically use a decoder/converter. If mapping to an internal account is needed, design a separate step with an explicit contract and caching/validation.

**Question 9.** Why does `findByUsername` need uniqueness in the database even if the service checks for it?  
**Answer:** To ensure an authentication lookup maps to a single account, preventing race conditions and duplicates during creates/updates. A unique constraint is the bottom-line safeguard.

**Question 10.** When should you use an adapter to a business store instead of JPA?  
**Answer:** When the source of truth for accounts is already managed by another domain/identity service, or the application requires a non-JPA storage mechanism. `UserDetailsService` only needs to fulfill the contract and trust the data source.

## Conclusion

`UserDetailsService` is **the read-data bridge between a business account store and Spring Security's username/password authentication mechanism**. The right integration pattern loads user/hash/status/authorities from a trusted repository or service, converts them into a complete `UserDetails` **inside an appropriate read transaction**, and lets `DaoAuthenticationProvider` and `PasswordEncoder` perform authentication. Only on success is the result placed into `Authentication`/`SecurityContext` and used for authorization checks.

A sound design keeps persistence separate from the principal, uses efficient queries, handles missing users via contract-compliant exceptions, protects password hashes/PII, keeps authorities aligned, and enforces session/token policies when accounts change.

**Remember:** *The repository knows the account data; `UserDetailsService` knows how to represent it for Spring Security; `AuthenticationProvider` knows how to verify credentials; authorization decides what an authenticated request is allowed to do.*

### Official References

- [Spring Security 7 — UserDetailsService](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 7 — UserDetails](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/user-details.html)
- [Spring Security 7 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 7 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/index.html)
- [Spring Boot 4 — Developing Your First Application (WebMVC starter)](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html)
- [Spring Boot 4 — SQL Databases and JPA](https://docs.spring.io/spring-boot/4.0/reference/data/sql.html)
- [Spring Data JPA — Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/)
