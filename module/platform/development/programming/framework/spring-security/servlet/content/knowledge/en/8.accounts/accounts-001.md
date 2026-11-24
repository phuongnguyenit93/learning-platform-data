# UserDetails, UserDetailsService, and UserDetailsManager: Distinct Roles

## 1. Three Concepts, Three Responsibilities in Spring Security Servlet

When building username/password login in a Spring Security Servlet application, we commonly encounter three similarly named types:

- **`UserDetails`** describes **an account used for authentication and authorization**: username, encoded password, authorities, and account status flags.
- **`UserDetailsService`** is the contract for **looking up** `UserDetails` by username. It does not verify passwords itself and does not define APIs to create, update, or delete accounts.
- **`UserDetailsManager`** extends `UserDetailsService`, adding **account management operations** such as creating, updating, deleting, changing passwords, and checking whether a username exists.

The type names are written exactly as in Spring Security:

```java
org.springframework.security.core.userdetails.UserDetails
org.springframework.security.core.userdetails.UserDetailsService
org.springframework.security.provisioning.UserDetailsManager
```

These three lines are type names for locating packages, **not a standalone Java program**.

The key point: **`UserDetails` is data / principal; `UserDetailsService` is the read contract; `UserDetailsManager` is the read + write contract**. Authentication classes such as `DaoAuthenticationProvider` use them through the appropriate API, while account management controllers are the application's responsibility.

### Quick Comparison

| Criterion | `UserDetails` | `UserDetailsService` | `UserDetailsManager` |
| --- | --- | --- | --- |
| Nature | Interface describing an account | Account lookup interface | Account management interface, extends `UserDetailsService` |
| Core methods | `getUsername`, `getPassword`, `getAuthorities`, account status flags | `loadUserByUsername` | `createUser`, `updateUser`, `deleteUser`, `changePassword`, `userExists`, and inherited `loadUserByUsername` |
| Return value | A `UserDetails` implementation is itself the data | `UserDetails` or throws `UsernameNotFoundException` | Varies by operation; `loadUserByUsername` also returns `UserDetails` |
| Checks user-entered password? | No | No | Not the primary responsibility of the interface |
| Creates/updates/deletes users? | No | No | Has corresponding operations |
| Built-in implementations | `org.springframework.security.core.userdetails.User` | Custom service, or a concrete manager | `InMemoryUserDetailsManager`, `JdbcUserDetailsManager` |

## 2. Position in the Username/Password Authentication Flow

For HTTP Basic or form login using `DaoAuthenticationProvider` and a typical account store, the flow can be pictured as follows:

```text
HTTP request with username/password
      |
      v
Authentication Filter (Basic / Form Login)
      |
      v
AuthenticationManager (typically ProviderManager)
      |
      v
DaoAuthenticationProvider
      |
      +---- UserDetailsService.loadUserByUsername(username)
      |                |
      |                v
      |           UserDetails
      |        username/password-hash/
      |        authorities/account flags
      |
      +---- PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +---- Check account flags, perform related authentication steps
      |
      +---- Success: authenticated Authentication
      |                  (with principal, authorities)
      |
      +---- Failure: appropriate AuthenticationException
      |
      v
SecurityContext / response management mechanisms
      |
      v
Authorization filters and controller if permitted
```

This is a **typical flow**, not an exhaustive list or immutable order of every provider. Spring Security supports many login mechanisms: JWT, OAuth2, SAML, pre-authentication, or custom providers may **not call `UserDetailsService`**.

Specifically:

1. `UserDetailsService` **does not receive the candidate password**; it only takes the username parameter.
2. `DaoAuthenticationProvider` is what uses `PasswordEncoder` to compare the user-entered password against the **encoded password** in `UserDetails`.
3. After authentication, the information used in `SecurityContext` is represented by `Authentication`. `UserDetails` may be the `principal` of `Authentication`, but **`Authentication` and `UserDetails` are not synonymous**.
4. `UserDetailsManager` is **not a required component** in authentication. A read-only `UserDetailsService` is sufficient if account management is handled by another system.

## 3. UserDetails: How Is an Account Represented?

`UserDetails` is an interface in `org.springframework.security.core.userdetails`. It tells the framework the data needed to check identity, password, and account status, as well as the granted authorities.

A summary of the relevant methods:

```java
// Abbreviated signature for explanation, not the full interface source code.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isAccountNonExpired();
boolean isAccountNonLocked();
boolean isCredentialsNonExpired();
boolean isEnabled();
```

Here `GrantedAuthority` belongs to `org.springframework.security.core`. The `is...` methods express conditions for **being allowed to operate**, so `isAccountNonLocked() == true` means the account is **not locked**.

### 3.1. Three Groups of Data

**Identity:** `getUsername()` is the name used for lookup. It does not necessarily have to be an email or database primary key, but the username normalization policy must be consistent between registration and login.

**Authentication verification info:** `getPassword()` typically returns a **password hash string** in a format understood by the corresponding `PasswordEncoder`. Do not store plaintext passwords. Some non-password-based authentication mechanisms may use `UserDetails` differently; do not assume every principal has a password.

**Authorization info:** `getAuthorities()` returns `GrantedAuthority` instances such as `ROLE_READER`, `ROLE_ADMIN`, or `order:read`. An authority is the string unit of permission; a role is a naming convention for an authority, typically prefixed with `ROLE_`.

### 3.2. Account Status

| Method | Meaning when returning `true` | Example |
| --- | --- | --- |
| `isEnabled()` | Account is enabled | Account is verified / not disabled |
| `isAccountNonLocked()` | Account is not locked | Not locked due to security policy |
| `isAccountNonExpired()` | Account is still valid | Has not passed expiration time |
| `isCredentialsNonExpired()` | Credentials are still valid | Password has not reached mandatory rotation |

`DaoAuthenticationProvider` checks these conditions during authentication and can throw the corresponding exception for an invalid account. Enabling/disabling these flags must come from business and security rules; do not unconditionally set all of them to `true` if the application requires locking/expiration.

### 3.3. Use the Built-In User or Create a Custom UserDetails Class?

Spring Security provides the `User` class implementing `UserDetails`:

```java
UserDetails reader = User.withUsername("reader")
    .password(encodedPassword)
    .roles("READER")
    .disabled(false)
    .build();
```

This is a **snippet inside code that already has `encodedPassword`**; it requires importing `org.springframework.security.core.userdetails.User` and `UserDetails`. `roles("READER")` creates the `ROLE_READER` authority according to the default convention. If using `authorities("ROLE_READER")`, you supply the exact authority without automatically adding a prefix.

When the application has an id, tenant, display name, or custom attributes truly needed at authentication time, you can create a class implementing `UserDetails`, or map the entity to `User`/a custom principal. **Do not use a JPA entity directly as the principal if doing so exposes sensitive data, triggers lazy-loading outside a transaction, or couples the security layer too tightly to the persistence layer.**

## 4. UserDetailsService: Specifying How to Find a User by Username

Minimal interface:

```java
@FunctionalInterface
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
}
```

This is an **abbreviated excerpt of the contract**. The key point is that a username is provided and the return value is a `UserDetails`. If the account is not found, the contract requires signaling the error with `UsernameNotFoundException`; do not return `null` to indicate "not found".

### 4.1. UserDetailsService Does Not Authenticate Passwords Itself

Do not write logic like the following in the service:

```java
// Wrong separation of responsibilities:
if (rawPassword.equals(account.getPasswordHash())) {
    return account;
}
```

Besides comparing hashes incorrectly, `loadUserByUsername` is not designed to receive `rawPassword`. Let `DaoAuthenticationProvider` and `PasswordEncoder` handle password verification.

### 4.2. Mapping a Domain Account to UserDetails

An example **illustrating persistence integration**, intentionally using two application-defined abstractions `AccountRepository` / `AccountRecord`, so it is **not a standalone runnable program**:

```java
@Service
public class AccountLookupService implements UserDetailsService {
    private final AccountRepository repository;

    public AccountLookupService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord record = repository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return User.withUsername(record.username())
            .password(record.passwordHash()) // Stored hash, do not re-encode.
            .authorities(record.authorities().toArray(String[]::new))
            .disabled(!record.enabled())
            .accountLocked(record.locked())
            .build();
    }
}
```

The `AccountRepository`/`AccountRecord` types are illustrative placeholders for the example. The code needs imports for `@Service`, `UserDetails`, `UserDetailsService`, `User`, `UsernameNotFoundException`, and the appropriate domain classes. In a real application, the repository can use JDBC, JPA, LDAP, or another service API; there is no mandatory requirement to use JPA.

Workflow:

- Look up the record by username with a consistent normalization policy.
- Not found -> `UsernameNotFoundException`.
- Found -> convert to `UserDetails`, pass the existing hash into `password`, and map authorities and status flags accurately.
- The authentication provider retrieves `UserDetails` to perform authentication; the service is only responsible for lookup.

**Note on account information leakage:** messages returned to HTTP clients should not allow probing whether a username exists. The framework/provider has certain mechanisms to mask differences, but messages, timing, logs, and application-specific endpoints still need review.

### 4.3. Why Is It Named "Service" When It Only Has One Method?

Here "Service" describes a retrieval contract for authentication, **not a general-purpose CRUD application service**. An application can have an `AccountApplicationService` with business operations for creating users, sending emails, changing passwords, verifying identity, and auditing; there is no need to force all of those operations into `UserDetailsService`.

## 5. UserDetailsManager: Extending Lookup to Modify Users

`UserDetailsManager` extends `UserDetailsService`, adding user administration operations:

```java
// Core signatures, not the full interface source code.
void createUser(UserDetails user);
void updateUser(UserDetails user);
void deleteUser(String username);
void changePassword(String oldPassword, String newPassword);
boolean userExists(String username);

// loadUserByUsername(String username) is inherited from UserDetailsService.
```

This leads to a very concrete type relationship:

```java
UserDetailsManager manager = obtainUserDetailsManager();
UserDetailsService lookup = manager; // Valid because Manager extends Service.
UserDetails account = lookup.loadUserByUsername("reader");
```

The snippet above is an **illustration with a hypothetical `obtainUserDetailsManager()` function**, not a standalone program.

### 5.1. Common Implementations

**`InMemoryUserDetailsManager`:** keeps accounts in the process's memory. Suitable for examples, tests, prototypes, or a simple fixed list of accounts. Not a durable storage choice for production accounts: a restart normally loses runtime changes.

**`JdbcUserDetailsManager`:** manages accounts via JDBC with a corresponding schema or queries. Requires a `DataSource` and appropriate tables/configuration; you cannot just swap the class in the application and ignore the database/schema. It fits when you want to use the default data model or customize queries within the contract's scope.

**Custom manager:** you can implement the interface yourself if you need CRUD over a custom system, but you must additionally handle transactions, authorization checks for modifying accounts, concurrency, username uniqueness, passwords, auditing, and domain constraints.

### 5.2. Not Every Application Needs UserDetailsManager

If users are provisioned by an external system, the application may only need `UserDetailsService` to read data for authentication. If using JWTs issued by an identity provider, none of these three types may even participate in the request authentication path.

Conversely, when you want to create/delete accounts through a Spring Security interface, `UserDetailsManager` is a useful abstraction. However, `createUser`/`deleteUser` are **server-side APIs**; they do not automatically create HTTP endpoints and do not automatically check whether the caller is an admin. Authorization, validation, and auditing for account management endpoints remain the application's responsibility.

### 5.3. Be Careful with changePassword

`changePassword(oldPassword, newPassword)` represents password-change behavior under the manager contract. Depending on the implementation, this operation may require the current `Authentication` in `SecurityContextHolder` and have a mechanism to verify the old password. Do not call it as an administrative "reset any account's password" API without understanding the implementation.

Do not confuse a password change performed by the account owner with password reset via verification token, login session management, and session revocation. Those workflows require separate design.

## 6. Complete Spring Boot 3 + Java 17 Example

This example can run with Spring Boot 3.3.5, Java 17, Maven, and the Servlet stack. It uses `InMemoryUserDetailsManager` as **both `UserDetailsManager` and `UserDetailsService`**, the corresponding authentication configuration's `DaoAuthenticationProvider` to check passwords, and HTTP Basic to observe responses.

The accounts are **learning** data in memory. Real applications need proper secret provisioning, storage, and auditing mechanisms.

### 6.1. Project Structure

```text
account-interfaces-demo/
  pom.xml
  src/
    main/java/demo/accounts/
      AccountsApplication.java
      SecurityConfig.java
      AccountController.java
    test/java/demo/accounts/
      AccountInterfacesTest.java
```

### 6.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>account-interfaces-demo</artifactId>
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

### 6.3. Startup Class

`src/main/java/demo/accounts/AccountsApplication.java`:

```java
package demo.accounts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountsApplication.class, args);
    }
}
```

### 6.4. SecurityConfig: UserDetailsManager as the Account Provider Bean

`src/main/java/demo/accounts/SecurityConfig.java`:

```java
package demo.accounts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.provisioning.UserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsManager userDetailsManager(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("locked-pass"))
            .roles("READER")
            .accountLocked(true)
            .build();

        return new InMemoryUserDetailsManager(reader, admin, locked);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Observations:

1. The `UserDetailsManager` bean is actually an `InMemoryUserDetailsManager`, which also satisfies the `UserDetailsService` contract for the provider to load accounts.
2. Each raw password only appears to create test data; `PasswordEncoder` generates a BCrypt hash before `UserDetails` is stored.
3. `roles("ADMIN")` creates `ROLE_ADMIN`; therefore `hasRole("ADMIN")` is satisfied.
4. User `locked` can still **be looked up** from the service, but authentication must be rejected because `isAccountNonLocked()` is `false`.
5. `httpBasic(...)` enables HTTP Basic; usernames/passwords should not be transmitted over unencrypted HTTP in real environments. Use HTTPS.
6. `UserDetailsManager` does not create administrative endpoints. The configuration only has the routes declared in the controller.

In a typical configuration, when a suitable `UserDetailsService`/`UserDetailsManager` bean and `PasswordEncoder` are present, Spring Security sets up the corresponding DAO authentication path for HTTP Basic to use. If the application also defines its own `AuthenticationProvider` or `AuthenticationManager`, you must check the actual configuration because provider selection may differ.

### 6.5. Controller Uses the Principal, Not Calling loadUserByUsername Manually

`src/main/java/demo/accounts/AccountController.java`:

```java
package demo.accounts;

import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(@AuthenticationPrincipal UserDetails principal) {
        String role = principal.getAuthorities()
            .iterator().next().getAuthority();
        return principal.getUsername() + " | " + role;
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }
}
```

With this test user set, each account has exactly one authority so `iterator().next()` is valid. In a real application, do not assume every principal has exactly one authority or always implements `UserDetails`: some authentication mechanisms have principals of type `Jwt`, `OAuth2User`, or a custom type. The controller in the example receives principal data **after framework authentication**, rather than calling `loadUserByUsername` itself to "re-authenticate".

### 6.6. Tests Actually Go Through Lookup and PasswordEncoder

`src/test/java/demo/accounts/AccountInterfacesTest.java`:

```java
package demo.accounts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.UserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountInterfacesTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UserDetailsManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsLoadReader() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader | ROLE_READER"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "bad-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lockedAccountCannotAuthenticate() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("locked", "locked-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void managerCanCreateUpdateAndDeleteUser() {
        String username = "temporary-learner";
        UserDetails temporary = User.withUsername(username)
            .password(encoder.encode("temporary-pass"))
            .roles("READER")
            .build();

        try {
            manager.createUser(temporary);
            assertTrue(manager.userExists(username));

            UserDetails changed = User.withUserDetails(temporary)
                .roles("ADMIN")
                .build();
            manager.updateUser(changed);

            UserDetails stored = manager.loadUserByUsername(username);
            assertTrue(stored.getAuthorities().contains(
                new SimpleGrantedAuthority("ROLE_ADMIN")));
        } finally {
            if (manager.userExists(username)) {
                manager.deleteUser(username);
            }
        }

        assertFalse(manager.userExists(username));
    }
}
```

The `httpBasic(username, password)` test sends HTTP Basic credentials through the filter chain instead of presetting a principal with `user(...)`. Therefore, the valid/wrong-password and locked-account tests actually observe the **username/password authentication path**, unlike `.with(user(...))`, which constructs an already-authenticated user in tests without verifying the password through `UserDetailsService`.

The final CRUD test directly calls `UserDetailsManager` and cleans up the `temporary-learner` account in `finally` to minimize impact on other tests. This is an in-memory test account; it is not automatically exposed as a public REST API.

### 6.7. Run Commands and Expected Results

In the project directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` runs eight test cases; given an appropriate configuration and environment, all pass. Maven/Spring Boot stdout depends on the machine and version so there is no fixed exact string. The verifiable HTTP results are:

| Operation | Result |
| --- | --- |
| `GET /public` without credentials | 200, body `public` |
| `GET /me` without credentials | 401 |
| `GET /me` with `reader/reader-pass` | 200, body `reader \| ROLE_READER` |
| `GET /me` with wrong password | 401 |
| `GET /me` with `locked/locked-pass` | 401 |
| `GET /admin` with `reader/reader-pass` | 403 |
| `GET /admin` with `admin/admin-pass` | 200, body `admin` |

Note: the table above describes the **specific HTTP Basic** configuration. If using form login, an anonymous request may receive a 302 redirect; do not generalize that every authentication failure is 401.

To test manually after the server starts, use HTTPS in a real environment; on localhost for learning only:

```bash
curl -i http://localhost:8080/public
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

The credentials above are learning accounts and must not be copied to production.

## 7. Standalone Java 17 Run: Illustrating Read and Management Contracts

The snippet below simulates the very split between **user record**, **lookup contract**, and **management contract**. The `Lookup` and `Manager` interfaces are written separately, **are not Spring Security APIs**, and have no password authentication. The purpose is to observe the read flow and CRUD operations with a single standalone Java file.

Create `AccountContractsDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class AccountContractsDemo {
    record Account(String username, String authority) {}

    interface Lookup {
        Account load(String username);
    }

    interface Manager extends Lookup {
        void create(Account account);
        void update(Account account);
        void delete(String username);
        boolean exists(String username);
    }

    static class MemoryManager implements Manager {
        private final Map<String, Account> accounts = new LinkedHashMap<>();

        public Account load(String username) {
            Account account = accounts.get(username);
            if (account == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return account;
        }

        public void create(Account account) {
            if (exists(account.username())) {
                throw new IllegalArgumentException("Already exists");
            }
            accounts.put(account.username(), account);
        }

        public void update(Account account) {
            if (!exists(account.username())) {
                throw new IllegalArgumentException("Unknown account");
            }
            accounts.put(account.username(), account);
        }

        public void delete(String username) {
            accounts.remove(username);
        }

        public boolean exists(String username) {
            return accounts.containsKey(username);
        }
    }

    public static void main(String[] args) {
        MemoryManager manager = new MemoryManager();
        manager.create(new Account("mai", "ROLE_READER"));

        Lookup lookup = manager; // Manager also provides the read contract.
        System.out.println("lookup: " + lookup.load("mai").authority());

        manager.update(new Account("mai", "ROLE_ADMIN"));
        System.out.println("updated: " + lookup.load("mai").authority());

        manager.delete("mai");
        System.out.println("exists: " + manager.exists("mai"));
    }
}
```

Compile and run:

```bash
javac AccountContractsDemo.java
java AccountContractsDemo
```

**Exact** stdout:

```text
lookup: ROLE_READER
updated: ROLE_ADMIN
exists: false
```

This model does not hash passwords, does not create a `SecurityContext`, and does not execute `DaoAuthenticationProvider`; those parts are in the real Spring Boot example. Both examples reinforce one idea: **the manager supports lookup because it extends the service; the data record does not become a service or manager.**

## 8. Designing with a Real Database

For enterprise account data, classes can be organized along these boundaries:

```text
Domain/Persistence:
  AccountEntity + AccountRepository
          |
          +--> read by username
          |
          v
Security integration:
  AccountUserDetailsService
          |
          +--> map AccountEntity to UserDetails/principal
          |
          v
DaoAuthenticationProvider + PasswordEncoder
          |
          v
Authentication / SecurityContext

Application management:
  AccountManagementService
          |
          +--> authorization checks, validation, transaction, audit
          |
          +--> create user, grant authorities, change password, lock/delete account
          |
          v
AccountRepository
```

It is **not mandatory** for every application to implement a custom `UserDetailsManager`. If this interface is needed, an application service/adapter can implement it while keeping business logic in the proper layer. Clearly separate **lookup for authentication** from **account lifecycle management**, avoiding letting a REST endpoint call `deleteUser` directly without authorization verification and auditing.

Some practical decisions:

- **Username uniqueness:** enforce at the database level as well; pre-checking with `userExists` is only a convenience check and does not replace a unique constraint and race-condition handling.
- **Password storage:** hash with `PasswordEncoder` at creation/change time; when loading from the database, return the stored hash **without re-encoding**. Have a policy to upgrade hash algorithms/cost factors when needed.
- **Role mapping:** distinguish between `roles("ADMIN")` and `authorities("ROLE_ADMIN")`. Do not confuse domain role names with actual `GrantedAuthority` strings.
- **Account state:** map locked/disabled/expired flags accurately to business rules; avoid defaulting flags to enabled in a way that invalidates account locking.
- **Transactions and auditing:** authority changes, locks, or deletions need to be recorded and executed in consistent transactions, especially when spanning multiple tables.
- **Caching:** if caching `UserDetails`, have an invalidation/refresh strategy after password, role, or account status changes.
- **Existing sessions/tokens:** changing roles or disabling an account does not necessarily automatically update all existing `Authentication` instances in sessions/JWTs. An appropriate session invalidation or token revocation/revalidation policy is needed per system.
- **Multi-tenant:** determine whether usernames are globally unique or per-tenant. Taking only a username in a simple contract does not automatically solve tenant isolation.
- **Registration and verification:** `UserDetailsManager.createUser` does not replace email verification, consent, anti-abuse, rate limiting, or other business rules.
- **User enumeration:** avoid returning different messages for "user does not exist" vs "wrong password" in a way that allows outsiders to enumerate the account list.

## 9. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Treating `UserDetailsService` as the place to check passwords | Mixes responsibilities, easily leads to comparing plaintext with hash | Service only loads the user; provider + encoder verify credentials |
| `loadUserByUsername` returning `null` when not found | Violates contract, can lead to confusing errors | Throw `UsernameNotFoundException` |
| Calling `encoder.encode` on a hash retrieved from the database | Correct passwords still fail to match | Encode when saving a new password; return the stored hash intact when loading |
| Using `roles("ROLE_ADMIN")` | Role prefix may be misapplied or rejected by the builder | Use `roles("ADMIN")` or `authorities("ROLE_ADMIN")` |
| Assuming `getAuthorities` is a list of usernames/tenants | Wrong authorization or data leakage | Map to actual authorities and enforce policy checks |
| Treating `isAccountNonLocked()==false` as allowed to log in | Misunderstands flag semantics | `false` means currently locked |
| Hard-casting every `Authentication.getPrincipal()` to `UserDetails` | Runtime error with JWT/OAuth2/custom principals | Check principal type and the active authentication mechanism |
| Using `.with(user(...))` in tests to prove password verification | Test bypasses credential verification | Use `httpBasic(...)` or real login requests through filters |
| Using `InMemoryUserDetailsManager` for long-term production users | Changes lost on restart; no independent persistence | Use proper persistence with clear schema and transactions |
| Exposing `UserDetailsManager` as CRUD APIs without authorization | Allows unauthorized privilege grants or account deletion | Build an application layer with authorization, validation, and auditing |
| Assuming DB role changes immediately update all sessions/JWTs | Old authorities may persist | Implement revalidation/revocation/session management policies |
| Creating multiple `UserDetailsService`/`AuthenticationProvider` beans without understanding selection order | May use the wrong user source or provider | Inspect the actual `AuthenticationManager` configuration |
| Logging `getPassword()` or submitted credentials | Exposes security secrets | Never log hashes, passwords, tokens, or sensitive credentials |

## 10. How to Debug Failed Logins or Wrong Access Permissions

When the same username fails to log in or gets wrong permissions, check in order:

1. **Which SecurityFilterChain matches the request?** Is it really using the expected HTTP Basic/form login and DAO provider?
2. **Which provider is being invoked?** If it is JWT/OAuth2, `UserDetailsService` might not be used for that request.
3. **Which lookup bean is injected?** Do multiple `UserDetailsService` or `UserDetailsManager` beans coexist? Which data source does each bean use?
4. **Username lookup:** are case-sensitivity, normalization, and tenant handled properly? Is "not found" translated to `UsernameNotFoundException`?
5. **PasswordEncoder:** does the stored hash use the right format/algorithm? Is anything encoding the hash a second time or storing plaintext?
6. **Account flags:** do `isEnabled`, `isAccountNonLocked`, `isAccountNonExpired`, and `isCredentialsNonExpired` match the user's state?
7. **Authorities:** what does `getAuthorities()` actually contain, how is the `ROLE_` prefix handled, and what do `hasRole`/`hasAuthority` rules require?
8. **After authentication:** are `SecurityContext` and authentication saved/restored properly if the app is session-based? If stateless, does the next request carry the required credentials/token?
9. **HTTP response:** distinguish authentication failures (typically 401 for Basic) and authorization failures (typically 403 for an authenticated user). Method security or other filters can also affect this.

In development environments, diagnostic logging can be enabled:

```properties
logging.level.org.springframework.security=DEBUG
```

Avoid enabling sensitive logging in production without controls. Never log raw passwords, password hashes, session IDs, or access tokens.

## 11. Self-Check Questions

**Question 1.** `UserDetailsService.loadUserByUsername("lan")` returns account `lan` with its password hash. The user enters the wrong password. Which interface is responsible for comparing them?

**Answer:** `UserDetailsService` only performs lookup. In the standard DAO flow, `DaoAuthenticationProvider` calls `PasswordEncoder.matches(...)` to verify the password, and authentication fails if it does not match.

**Question 2.** An account has `isAccountNonLocked() == false` and the password is correct. Will authentication succeed?

**Answer:** No under `DaoAuthenticationProvider`'s status checks, because the account is locked.

**Question 3.** Why can a `UserDetailsManager` be injected into a variable of type `UserDetailsService`?

**Answer:** Because `UserDetailsManager extends UserDetailsService`. It has all the lookup capabilities of the service plus management operations.

**Question 4.** What do `roles("ADMIN")` and `authorities("ROLE_ADMIN")` have in common?

**Answer:** Under the default prefix convention, both produce the `ROLE_ADMIN` authority. `roles("ROLE_ADMIN")` is not the appropriate way to pass a role name.

**Question 5.** You need user registration, email verification, audit logging, account locking when needed, and token-based password reset. Is `UserDetailsManager` alone enough?

**Answer:** Not yet. The manager interface provides some basic user operations; verification, authorization, tokens, auditing, and transactions belong in the application/domain layer.

**Question 6.** Does a test using `.with(user("reader"))` prove that `reader`'s password is verified through `PasswordEncoder`?

**Answer:** No. It supplies a pre-authenticated test principal. To prove credential lookup and password verification, use a real login path such as HTTP Basic in `MockMvc`.

**Question 7.** After granting an additional `ROLE_ADMIN` in the database, will an existing session automatically pick up the new role?

**Answer:** Not guaranteed. The `Authentication` already created in the session/token may retain old authorities. You need an appropriate policy to refresh or revoke the session/token context.

## 12. Key Takeaways

- `UserDetails`: **account descriptor** containing username, password hash, authorities, and status flags.
- `UserDetailsService`: **read-only contract**, `loadUserByUsername` returns `UserDetails` or throws `UsernameNotFoundException`.
- `UserDetailsManager`: **extends service for management**, with CRUD and password change; `InMemoryUserDetailsManager` and `JdbcUserDetailsManager` are examples.
- `DaoAuthenticationProvider` together with `PasswordEncoder` handles password verification; do not push this into `UserDetailsService`.
- `Authentication` is the authentication result/context; the principal may be `UserDetails`, though not required in every mechanism.
- Account management roles require dedicated policies, authorization, and auditing. Spring Security interfaces provide the foundation, not an automatically secure application API.
