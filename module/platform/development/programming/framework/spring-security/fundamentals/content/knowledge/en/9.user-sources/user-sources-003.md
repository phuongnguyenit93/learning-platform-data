# InMemoryUserDetailsManager for Learning and Testing

> **Focus:** `InMemoryUserDetailsManager` is a way to create and manage `UserDetails` directly in the memory of a Java process. It is very useful for learning **username/password authentication**, trying `roles`/`authorities`, building database-independent tests, and quickly reproducing cases of successful login, wrong password, insufficient permissions, or locked accounts. It is **not a persistent user store**: when the application restarts, runtime changes are not preserved, deployment instances/nodes do not synchronize automatically, and hard-coding real passwords into code is dangerous.

This lesson belongs to the **User Sources** section of the **Spring Security – fundamentals** module. The main examples use **Java 17+, Spring Boot 3.5.16, Spring Security 6.5.x, Spring MVC/Servlet**, HTTP Basic, and JUnit/MockMvc. There are two independent test layers: HTTP testing through the filter chain and direct testing of the user management API. The final part clarifies how to restrict sample users to a test profile, how to avoid state leakage between tests, and when to migrate to a production user store.

## 1. Learning Objectives

After this lesson, you can:

1. Accurately diagram the relationship `UserDetailsService` → `InMemoryUserDetailsManager` → `DaoAuthenticationProvider` → `PasswordEncoder` → `AuthenticationManager`.
2. Create multiple accounts with BCrypt-hashed passwords, `ROLE_USER`/`ROLE_ADMIN` roles, and custom authorities like `TASK_WRITE`.
3. Distinguish **authenticating** a user with username/password from **authorizing** HTTP methods, endpoints, and resources.
4. Understand `UserDetails`, account state flags (`enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired`), and the errors commonly received over HTTP.
5. Use `loadUserByUsername`, `userExists`, `createUser`, `updateUser`, `deleteUser`, and `updatePassword` in tests with isolated state.
6. Write integration tests using `httpBasic(...)` to go through **real password validation** and distinguish them from `@WithMockUser` or `user(...)`.
7. Build a `200 / 401 / 403` test matrix, method-based permissions, CSRF, and locked accounts without running a database or external identity system.
8. Recognize limitations around persistence, multi-instance deployment, permission management, password lifecycle, revocation, and test fixture security.
9. Know when to use `@TestConfiguration` or a test profile to separate sample identities from the production environment.

## 2. Where Does InMemoryUserDetailsManager Sit in Spring Security?

Let us start from the HTTP Basic flow:

```text
GET /me
Authorization: Basic <Base64-encoded username:password>
           |
           v
Servlet SecurityFilterChain
           |
           v
BasicAuthenticationFilter
           |
           v
UsernamePasswordAuthenticationToken (unauthenticated)
           |
           v
AuthenticationManager (usually ProviderManager)
           |
           v
DaoAuthenticationProvider
     |                         |
     v                         v
UserDetailsService        PasswordEncoder
     |                    matches(raw, hash)
     v                         ^
InMemoryUserDetailsManager     |
     |                         |
     +---- UserDetails --------+
             |
      username, hash,
      authorities,
      account flags
             |
             v
Authentication succeeds or AuthenticationException
             |
             v
SecurityContext (current request)
             |
             v
AuthorizationFilter -> Controller -> Service
```

`InMemoryUserDetailsManager` is an implementation of `UserDetailsService` and `UserDetailsManager`, and also supports the password update mechanism for `UserDetails`. It **supplies user data** to the provider. This manager itself **is not an HTTP filter**, **does not receive REST login requests**, **does not verify record ownership**, and **does not replace `SecurityFilterChain`**.

When `DaoAuthenticationProvider` receives a username/password request, it calls `UserDetailsService.loadUserByUsername(username)` and compares the raw password against the hash using `PasswordEncoder.matches(...)`. If all conditions are valid, the provider returns an authenticated `Authentication` with trusted authorities from `UserDetails`.

### Role Assignment Table

| Component | Responsibility | Avoid confusing with |
| --- | --- | --- |
| `UserDetails` | A user description: username, password hash, authorities, account status | Not a mandatory JPA `@Entity` |
| `UserDetailsService` | User reading contract: `loadUserByUsername(String)` | Does not itself decide which URLs are open |
| `UserDetailsManager` | Extends UserDetailsService with APIs to add, update, delete users | Does not mean the data store is persisted |
| `InMemoryUserDetailsManager` | Stores `UserDetails` in the memory of a single Java process | Not a database or distributed user store |
| `DaoAuthenticationProvider` | Verifies credentials/account state for username/password | Not the place to declare route policies |
| `PasswordEncoder` | Hashes and matches passwords | Does not encrypt network traffic; HTTP needs TLS |
| `AuthenticationManager` | Coordinates providers, returns authentication result or exception | Does not create users or write HTTP responses itself |
| `SecurityFilterChain` | Selects HTTP filters and URL/method/authority rules | Does not automatically infer owner/tenant permissions |
| `@WithMockUser`/`user(...)` in tests | Injects a fake principal to test authorization | Does not check passwords against the real user store |

### Why is it called "UserDetailsManager" instead of just "UserDetailsService"?

`UserDetailsService` has one primary method:

```java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
```

`UserDetailsManager` additionally provides `createUser`, `updateUser`, `deleteUser`, `userExists`, and `changePassword`. `InMemoryUserDetailsManager` implements these methods on in-RAM data. The name "manager" refers to the ability to mutate users **in this store**, not that it centrally manages every user in the system or guarantees ACID/durability like a database.

## 3. When Is InMemoryUserDetailsManager Useful?

It is especially suited for four scenarios:

- **Spring Security labs:** setting up Alice, Bob, admin, and a locked user to understand how authentication differs from authorization.
- **API integration tests:** verifying valid Basic credentials and testing 200/401/403 without depending on a database/migration/seed/Identity Provider.
- **Testing logic around UserDetailsManager:** trying create/update/delete, authorities, and account status with a fresh manager in each test.
- **Short-lived PoCs/local demos:** quickly standing up features to learn filter chains, form login/Basic auth, or method security.

Its limitations must be recognized:

1. **Not persisted:** Data created/modified/deleted at runtime is lost when the JVM restarts; users declared via a bean may be recreated from code on each start.
2. **Not shared across instances:** Two replicas run two separate memories; updating permissions/users on replica A does not appear on B.
3. **No full account business workflows:** MFA, self-service reset, verification email, historical lockout, auditing, key management, and federated auth all require dedicated design.
4. **Does not auto-revoke sessions/tokens:** Changing permissions in the manager does not guarantee that `Authentication` stored in sessions or self-contained claim tokens are updated immediately.
5. **Not a production credential store:** Even though passwords are BCrypt-hashed when entering RAM, hard-coding plaintext before hashing in source still exposes secrets if the repository is read.
6. **Does not protect domain resources:** `ROLE_USER` does not decide whether Alice can read Bob's orders.
7. **Not the same as a reactive user store:** WebFlux uses `MapReactiveUserDetailsService` and `ReactiveUserDetailsService` to fit the reactive pipeline.

**Selection criteria:** If an exercise needs authentication/authorization tests without persistence yet, InMemoryUserDetailsManager keeps the setup simple. If there are real accounts, frequently changing permissions, multiple replicas, or audit/lifecycle requirements, design an appropriate user store/IdP.

## 4. Initializing UserDetails Properly

### 4.1. Simple account

Snippet example in Spring configuration:

```java
@Bean
InMemoryUserDetailsManager users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("demo-pass"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(alice);
}
```

`User.withUsername(...)` is a builder provided by Spring Security. `.roles("USER")` adds the `ROLE_USER` authority per the default prefix convention. The password is hashed before being placed in `UserDetails`. The `users(...)` method returns a bean that Spring Security can use as the user source when authentication is appropriately configured.

**Do not write:**

```java
// Anti-pattern: storing plaintext in UserDetails instead of an appropriate hash.
User.withUsername("alice")
    .password("demo-pass")
    .roles("USER")
    .build();
```

With `BCryptPasswordEncoder`, an unhashed password like this does not match the verification rules and can cause login failures. In all cases, putting real passwords into source code is an unacceptable risk in production.

### 4.2. Roles and authorities

```java
UserDetails reader = User.withUsername("reader")
    .password(encoder.encode("demo-pass"))
    .roles("USER")
    .build();

UserDetails writer = User.withUsername("writer")
    .password(encoder.encode("demo-pass"))
    .authorities("ROLE_USER", "TASK_WRITE")
    .build();

UserDetails admin = User.withUsername("admin")
    .password(encoder.encode("demo-pass"))
    .roles("ADMIN")
    .build();
```

| Creation call | Granted authority | Corresponding rule |
| --- | --- | --- |
| `roles("USER")` | `ROLE_USER` | `hasRole("USER")` |
| `roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` |
| `authorities("TASK_WRITE")` | `TASK_WRITE` | `hasAuthority("TASK_WRITE")` |
| `authorities("ROLE_USER", "TASK_WRITE")` | Both values | `hasRole("USER")` and `hasAuthority("TASK_WRITE")` can be used |
| `roles("USER", "ADMIN")` | `ROLE_USER`, `ROLE_ADMIN` | User has both roles |

**Mind the prefix:** `hasRole("ADMIN")` usually looks for `ROLE_ADMIN`. Do not use `roles("ROLE_ADMIN")` in the builder because `roles` already adds the prefix; when you need to assign an exact authority string, use `authorities("ROLE_ADMIN")`.

A user with `TASK_WRITE` does not automatically have `ROLE_ADMIN`. Never grant broad administrative authorities just to test a write endpoint.

### 4.3. Account status

Spring Security `UserDetails` provides these checks:

| Property | Meaning when true | Builder call to create blocked state |
| --- | --- | --- |
| `isEnabled()` | Account is allowed to authenticate | `disabled(true)` |
| `isAccountNonLocked()` | Account is not locked | `accountLocked(true)` |
| `isAccountNonExpired()` | Account has not expired | `accountExpired(true)` |
| `isCredentialsNonExpired()` | Credentials have not expired | `credentialsExpired(true)` |

Example:

```java
UserDetails locked = User.withUsername("locked")
    .password(encoder.encode("demo-pass"))
    .roles("USER")
    .accountLocked(true)
    .build();
```

Even with the right password, `DaoAuthenticationProvider` typically rejects login if the account is locked. With HTTP Basic, the client may only see `401`. To verify the technical cause, use provider-level tests and `LockedException`, rather than designing overly detailed responses that let outsiders probe account status.

### 4.4. PasswordEncoder is essential

`BCryptPasswordEncoder` creates salted password hashes:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
```

When testing:

```java
String encoded = passwordEncoder.encode("demo-pass");
boolean valid = passwordEncoder.matches("demo-pass", encoded);
```

`valid` must be true. **Do not compare two `encode(...)` results using `equals`**: bcrypt uses salting, so the same plaintext usually produces different hashes. Use `matches(rawPassword, storedHash)`. With modern password policies, beyond the hashing algorithm you need secret management, reset flows, reasonable complexity rules, and brute-force limits.

Spring Security also has `DelegatingPasswordEncoder`, which uses prefixes like `{bcrypt}` to pick the algorithm. Two different cases:

```text
BCryptPasswordEncoder directly:
    password is stored as "$2a$..." (no {bcrypt} prefix needed)

DelegatingPasswordEncoder:
    password is usually stored as "{bcrypt}$2a$..."
```

Do not directly mix BCryptPasswordEncoder with a stored value carrying `{bcrypt}` and expect it to always match; the encoder configuration must match the stored hash format.

### 4.5. withDefaultPasswordEncoder, {noop}, and sample passwords

Spring Security documentation includes examples with `User.withDefaultPasswordEncoder()` or the `{noop}` prefix for quick learning, however:

- `User.withDefaultPasswordEncoder()` is only suitable for demos/getting started and is marked unsuitable for production. Plaintext passwords in source are still exposed via Git/decompilation, even though the builder hashes them before storing.
- `{noop}` allows unencrypted/unhashed passwords suitable only for special examples; it should not be chosen as a real password configuration.
- For a test with fixed passwords, you can use BCrypt and sample test fixtures containing no personal information. Never let fixtures become production configuration.
- When you do not want the project to contain secrets in source, supply them via test configuration/appropriate secret injection; passwords exist only within the test process and must not be logged.

## 5. Relationship Between Spring Boot Default User and Your Own Manager

In Spring Boot MVC with `spring-boot-starter-security`, if the application does not yet have a suitable identity configuration, Boot may create a default in-memory user named `user` with a random password logged to console for development. Part of this is handled by `UserDetailsServiceAutoConfiguration`.

When you create your own `InMemoryUserDetailsManager` bean (which is a `UserDetailsService`), **the auto-configuration that creates the generated user can step back** based on the condition that a user source already exists. Thus:

```text
Initially:
  spring-boot-starter-security
  -> Boot may create default user: username=user, random password

After adding bean:
  @Bean InMemoryUserDetailsManager users(...)
  -> App uses your declared sample users, e.g. alice/writer/admin
  -> Do not assume the default user "user" still exists

However:
  Creating a UserDetailsService does not mean URL authorization changed.
  Creating a SecurityFilterChain does not guarantee the generated user disappeared.
```

These are two separate responsibilities:

- **Authentication source:** `InMemoryUserDetailsManager`/`UserDetailsService` provides users, hashes, and authorities.
- **HTTP authorization:** `SecurityFilterChain`/`authorizeHttpRequests` decides which endpoints are public and which users are allowed in.

A common mistake is creating only a user bean and assuming `GET /public` becomes public automatically, or adding `requestMatchers("/admin").hasRole("ADMIN")` without any user possessing `ROLE_ADMIN`.

If the project adds OAuth2 Resource Server/OIDC/SAML or a custom authentication provider, Boot's auto-configuration conditions may differ. Inspect actual beans and test over HTTP; do not rely on a generated password in logs once you actively manage the source.

## 6. Complete Demo: Spring Boot + InMemoryUserDetailsManager

**Demo goals:**

- `GET /public` requires no login.
- `GET /me` requires authentication.
- `GET /admin` requires `ROLE_ADMIN`.
- `POST /tasks` requires `TASK_WRITE`, and is still checked by CSRF protection.
- A `locked` user is rejected despite having the right password.
- Test requests with HTTP Basic through the real `SecurityFilterChain` and test reading manager data.

**Pinned versions to reproduce the lesson:** Java 17+, Spring Boot `3.5.16`, Spring Security 6.5.x managed by the Boot BOM. Spring Boot 3.5.16 was released on 2026-06-25 and is the final OSS release of the 3.5 line. For new production deployments, choose a still-supported Boot line (such as Boot 4.x) and check Security 7 changes. Demo users are not for production.

### 6.1. File structure

```text
inmemory-users-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/inmemory/InMemoryDemoApplication.java
    └── test/
        └── java/demo/inmemory/
            ├── InMemoryHttpSecurityTests.java
            └── InMemoryManagerUnitTests.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>inmemory-users-demo</artifactId>
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

### 6.3. Complete Java application

Create `src/main/java/demo/inmemory/InMemoryDemoApplication.java`:

```java
package demo.inmemory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class InMemoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InMemoryDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("demo-pass"))
            .authorities("ROLE_USER", "TASK_WRITE")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-pass"))
            .roles("ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .accountLocked(true)
            .build();

        return new InMemoryUserDetailsManager(
            alice, writer, admin, locked);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/tasks")
                    .hasAuthority("TASK_WRITE")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(Customizer.withDefaults())
            // Keep CSRF enabled to separate CSRF checks from authority.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

@RestController
class DemoRoutes {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/tasks")
    String createTask(Authentication authentication) {
        // Only simulates creation, no database.
        return "created:" + authentication.getName();
    }
}
```

**Reading the code with proper responsibility layers:**

1. `users(...)` is an `InMemoryUserDetailsManager` bean; Spring Security uses it as the user source. Passwords are hashed using a shared `PasswordEncoder` bean.
2. Alice has only `ROLE_USER`. Writer has both `ROLE_USER` and `TASK_WRITE`. Admin has only `ROLE_ADMIN`. Locked has the right password yet cannot authenticate due to account status.
3. `securityFilterChain(...)` defines HTTP permissions. `/public` is public because of `permitAll()`, not because of any path name or username. `anyRequest().denyAll()` closes undeclared routes within the chain's scope.
4. HTTP Basic extracts credentials from headers and passes them to the authentication provider. The in-memory manager supplies the user record and hash for the provider to check.
5. `SessionCreationPolicy.STATELESS` chooses the "each request carries credentials" demo; no login session is used to reuse Alice on subsequent requests. This makes tests clearly prove independent requests.
6. CSRF protection remains enabled: `POST /tasks` can return `403` even when the user has `TASK_WRITE` if the token is missing. In browser apps using auto-sent Basic/cookie credentials, CSRF has its own purpose; do not disable it just to make a curl POST succeed.
7. Endpoints return minimal strings rather than returning `UserDetails` or hashes to clients. For real apps, DTOs must be designed not to leak credentials.
8. These are **sample identities for learning**. Never use the `demo-pass` password or these in-memory users as real configuration on a public server.

### 6.4. Checking with curl (localhost connection)

In the project directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

After the server starts on `localhost:8080`:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u writer http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
curl -i -u locked http://localhost:8080/me
```

`curl -u alice` (without putting the password in the command) will prompt for the password. Enter `demo-pass` on your local machine. On older PowerShell, `curl.exe` may be needed instead of the `curl` alias.

| Test | Expected Status | Reason |
| --- | --- | --- |
| `GET /public` anonymous | 200 | `permitAll` |
| `GET /me` anonymous | 401 | HTTP Basic requires authentication |
| `GET /me` with Alice right password | 200, body `me:alice` | User exists, BCrypt matches |
| `GET /me` with writer right | 200, body `me:writer` | User exists, authenticated |
| `GET /admin` with Alice right | 403 | Lacks `ROLE_ADMIN` |
| `GET /admin` with admin right | 200, body `admin` | Has `ROLE_ADMIN` |
| `GET /me` with locked right | 401 | Provider rejects locked account |

If using the wrong password, `GET /me` also typically returns `401`. Do not disclose detailed "username exists/is locked" information in public responses; HTTP responses should avoid username enumeration.

**HTTP Basic does not encrypt passwords on the wire**; Base64 is only an encoding of `username:password`. All these HTTP commands are for `localhost` only. For real systems, HTTPS and an appropriate identity method are mandatory. To test POST with a valid CSRF token, use MockMvc in the next section.

## 7. Integration Test: Using In-Memory Users Through Real Authentication

Create `src/test/java/demo/inmemory/InMemoryHttpSecurityTests.java`:

```java
package demo.inmemory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InMemoryHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryUserDetailsManager users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void userStoreContainsEncodedPasswordsAndExpectedRoles() {
        assertTrue(users.userExists("alice"));
        assertTrue(users.userExists("writer"));
        assertTrue(users.userExists("admin"));
        assertTrue(users.userExists("locked"));
        assertFalse(users.userExists("nobody"));

        UserDetails alice = users.loadUserByUsername("alice");
        assertEquals("alice", alice.getUsername());
        assertFalse(alice.getPassword().equals("demo-pass"));
        assertTrue(encoder.matches("demo-pass", alice.getPassword()));
        assertTrue(alice.isEnabled());
        assertTrue(alice.isAccountNonLocked());

        UserDetails locked = users.loadUserByUsername("locked");
        assertFalse(locked.isAccountNonLocked());
    }

    @Test
    void checksRealPasswordViaHttpBasic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("nobody", "demo-pass")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("locked", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rolesAndFineGrainedAuthoritiesHaveDifferentEffects()
            throws Exception {

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        // ROLE_ADMIN does not automatically include TASK_WRITE.
        mvc.perform(post("/tasks")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Alice also does not have TASK_WRITE.
        mvc.perform(post("/tasks")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfAndPermissionMustBothPass() throws Exception {
        // Writer has TASK_WRITE but lacks CSRF token.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Has token, yet invalid token is also rejected.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // Has both permission and valid CSRF, so controller runs.
        mvc.perform(post("/tasks")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:writer"));
    }

    @Test
    void statelessRequestsDoNotInheritPreviousAuthentication()
            throws Exception {

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        // Subsequent request without Authorization header remains anonymous.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        // Undeclared route is denied.
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Why is this test meaningful?**

- `@SpringBootTest` loads the real application context/beans; `@AutoConfigureMockMvc` attaches Spring MVC and the filter chain to test requests.
- `httpBasic("alice", "demo-pass")` adds the `Authorization: Basic ...` header. Spring Security genuinely uses `DaoAuthenticationProvider` + `InMemoryUserDetailsManager` + `PasswordEncoder` to verify the password.
- `users.loadUserByUsername` lets you verify fixtures and hashes; that is a direct test of the user source, not a substitute for HTTP integration tests.
- Users with different permissions prove that a successful login does not mean access to every endpoint.
- `csrf()` and `csrf().useInvalidToken()` independently test exploit protection and authorities. Missing CSRF can result in 403 before the authentication filter finishes, so **do not infer from a single 403 code alone that the password was accepted**.
- Testing a subsequent request without credentials proves that authenticated principals are not automatically reused in the stateless demo.
- `users` is only read in integration tests without mutating the shared bean; tests that modify users are moved to unit tests with a fresh instance.

If built/tested in the right environment, assertions are expected to pass. This is runnable code provided for you; `BUILD SUCCESS` is an **expectation**, not an executed result in this article.

## 8. Standalone Unit Tests: Add, Edit, Delete Users Without Polluting Other Tests

`InMemoryUserDetailsManager` is an object with **mutable state**. If in one `@SpringBootTest` you call `deleteUser("alice")` on the shared bean, other HTTP tests may start failing depending on execution order, test context caching, or parallel execution. Therefore, create a **fresh manager in each mutating test** rather than modifying the application bean serving other tests.

Create `src/test/java/demo/inmemory/InMemoryManagerUnitTests.java`:

```java
package demo.inmemory;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InMemoryManagerUnitTests {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();

    @Test
    void createUpdateChangeAndDeleteUserInOneIsolatedManager() {
        InMemoryUserDetailsManager users =
            new InMemoryUserDetailsManager();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("first-pass"))
            .authorities("ROLE_USER", "TASK_WRITE")
            .build();

        users.createUser(editor);
        assertTrue(users.userExists("editor"));
        assertTrue(encoder.matches("first-pass",
            users.loadUserByUsername("editor").getPassword()));

        // Duplicate usernames cannot be created in the same manager.
        assertThrows(IllegalArgumentException.class,
            () -> users.createUser(editor));

        // Replace permissions and password using a new UserDetails.
        UserDetails updated = User.withUserDetails(editor)
            .password(encoder.encode("second-pass"))
            .authorities("ROLE_USER")
            .build();

        users.updateUser(updated);

        UserDetails loaded = users.loadUserByUsername("editor");
        assertTrue(encoder.matches("second-pass", loaded.getPassword()));
        assertFalse(loaded.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("TASK_WRITE"::equals));

        // The updatePassword API expects an already-encoded password.
        users.updatePassword(updated, encoder.encode("third-pass"));

        UserDetails withNewPassword =
            users.loadUserByUsername("editor");
        assertTrue(encoder.matches("third-pass",
            withNewPassword.getPassword()));

        users.deleteUser("editor");
        assertFalse(users.userExists("editor"));
        assertThrows(UsernameNotFoundException.class,
            () -> users.loadUserByUsername("editor"));
    }

    @Test
    void daoProviderChecksPasswordAndAccountLock() {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("correct-pass"))
            .roles("USER")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("correct-pass"))
            .roles("USER")
            .accountLocked(true)
            .build();

        InMemoryUserDetailsManager users =
            new InMemoryUserDetailsManager(alice, locked);

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager authenticationManager =
            new ProviderManager(provider);

        Authentication verified = authenticationManager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-pass"));

        assertTrue(verified.isAuthenticated());
        assertEquals("alice", verified.getName());
        assertTrue(verified.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("ROLE_USER"::equals));

        assertThrows(BadCredentialsException.class,
            () -> authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "wrong-pass")));

        assertThrows(LockedException.class,
            () -> authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "locked", "correct-pass")));
    }
}
```

**Explanation:**

- Each test creates its own `new InMemoryUserDetailsManager(...)`, so create/delete/update do not change the data used by the Spring Boot application context in `InMemoryHttpSecurityTests`.
- `createUser` rejects a username that already exists in the same manager. `updateUser` replaces the user record with the new `UserDetails`; the test verifies that `TASK_WRITE` is gone and the new hash works.
- `updatePassword` accepts an **encoded password** in this example. Do not send plaintext to the manager assuming it automatically BCrypt-hashes it. This is a contract API for credential updates, not a REST endpoint for anyone to change passwords.
- `DaoAuthenticationProvider` and `ProviderManager` are constructed directly to test authentication results with a real source. Wrong password throws `BadCredentialsException`; locked account throws `LockedException`. In production HTTP, both situations may return `401` to limit account enumeration.
- Tests generate BCrypt hashes right inside the process rather than copying fixed hashes from another environment. Hashes are compared using `matches`.

### 8.1. Be careful with changePassword(old, new)

`UserDetailsManager.changePassword(oldPassword, newPassword)` is a specialized API meaning "change the password of the **current authenticated user**". `InMemoryUserDetailsManager` can use `SecurityContextHolder` to find the current user and **only verifies the old password if an appropriate `AuthenticationManager` has been attached to the manager**. Therefore, never expose this method directly as a self-service user endpoint assuming all checks are already built in.

When designing real password changes, you need:

1. Verify the current user from a trusted context, never taking an arbitrary client-sent username.
2. Require appropriate re-authentication or step-up policy.
3. Hash the new password per encoder/password policy; never accept a client-supplied "newHash" that could violate format or policy.
4. Check CSRF for web cookie auth and rate-limit requests.
5. Update the persistent user store, revoke sessions/tokens when needed, and write safe audit logs.
6. Test the entire flow; do not just assert `userExists`.

In **this lesson**, calling `updateUser`/`updatePassword` directly on a new instance suffices to illustrate the technique. Production should use a user repository or IdP managing the full lifecycle.

## 9. How Does @WithMockUser Differ from HTTP Basic with InMemoryUserDetailsManager?

This is the most important distinction when **testing security**.

### 9.1. Using a mock user

```java
@Test
@WithMockUser(username = "ghost-admin", roles = "ADMIN")
void anAdminRoleCanOpenAdminEndpoint() throws Exception {
    mvc.perform(get("/admin"))
        .andExpect(status().isOk());
}
```

This is a snippet placed in a test class with `MockMvc mvc`, JUnit imports, and `WithMockUser`. The user `ghost-admin` **does not need to exist in `InMemoryUserDetailsManager`**; the annotation supplies a simulated authentication in the test. This is great for checking **authorization rules** without depending on a database or passwords.

However, a green test **does not prove**:

- A real `ghost-admin` account exists.
- Password hashing/encoder works.
- `DaoAuthenticationProvider` picks the right source.
- The login form or Basic filter successfully verifies credentials.
- Locked/disabled/expired accounts are properly rejected.

### 9.2. Using Basic header with a real manager

```java
mvc.perform(get("/admin")
        .with(httpBasic("admin", "demo-pass")))
    .andExpect(status().isOk());
```

Once the Spring Security filter chain is configured in MockMvc, the request sends Basic credentials to the filter, and the provider loads the user from the in-memory manager and compares the password against the hash. It tests both **authentication and authorization** simultaneously within the application context.

### 9.3. Selection table

| Need to prove | `@WithMockUser` / `user()` | `httpBasic(...)` + InMemory manager |
| --- | --- | --- |
| URL requires ROLE_ADMIN | Suitable | Suitable |
| Rule `hasAuthority("TASK_WRITE")` | Suitable | Suitable |
| PasswordEncoder.matches works | **No** | **Yes** |
| Whether user exists in source | **No** | **Yes** |
| Whether locked/disabled account is rejected | No, unless simulated by policy | Yes, if provider executes account checks |
| BasicAuthenticationFilter integration with provider | No | Yes |
| Real session/form login testing | No | Basic test does not replace form-login test |
| No external test identity provider dependency | Yes | Yes, because source is in-memory |
| Unit speed when testing policy only | Usually very convenient | Needs Spring/context or appropriate provider |

Depending on your goal, use both kinds of tests. Controller/service tests may use mock users to focus on policy. Authentication configuration tests must have at least one **real credential** path through the provider/filter.

## 10. Where Should Test Data Live?

### 10.1. Avoid placing test users in production configuration

The demo above puts test users in `src/main` only so learners can run it immediately on localhost. In a real product, doing so could package "demo-pass" accounts into the release artifact. Separate them:

- Production: managed identity provider, database, or user service, with clear secret policies and auditing.
- Integration tests: `InMemoryUserDetailsManager` with dummy passwords, a test-only profile, or `@TestConfiguration`.
- Unit tests: create a fresh InMemory instance per method or `@BeforeEach`, independent of the singleton application context.

Example using an intentional **profile**:

```java
@Configuration(proxyBeanMethods = false)
@Profile("test")
class TestUsersConfiguration {

    @Bean
    InMemoryUserDetailsManager testUsers(PasswordEncoder encoder) {
        UserDetails tester = User.withUsername("tester")
            .password(encoder.encode("test-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(tester);
    }
}
```

This snippet needs the corresponding Spring/Security imports and should live in the test module or configuration excluded from production builds. If placed in `src/test/java`, the class is absent from production artifacts. With other profiles, ensure the app has a real user source; **never** let a test profile leak into public deployments.

Activating the profile properly in a test:

```java
@SpringBootTest
@ActiveProfiles("test")
@AutoConfigureMockMvc
class ProfileBasedSecurityTests {
    // Tests will see beans matching the active "test" profile.
}
```

Avoid declaring two indistinguishable `UserDetailsService` beans and leaving the provider unsure which bean to use. In projects using `@Primary` or `@TestConfiguration` to override the source, define clear conditions and a single choice. When testing production configuration, test the production security chain independently of fake users.

### 10.2. Why should each mutating test have a fresh manager?

Spring Test caches `ApplicationContext` to save time. `InMemoryUserDetailsManager` is a bean holding **state**; calling `updateUser`/`deleteUser` in one test can change the data seen by another test sharing the context. When tests run in parallel, outcomes become even less stable.

Reasonable approaches:

- Use `new InMemoryUserDetailsManager()` in unit tests needing create/update/delete.
- Use a fixture factory creating a dedicated manager per test.
- For integration tests that do not need to modify users, only read the bean and send HTTP requests.
- If you truly must mutate a bean in context, recreate/reset state via an explicitly controlled strategy (possibly `@DirtiesContext`, though slow), avoiding it as a default for all tests.
- Do not use `@TestMethodOrder` as a band-aid for leaked state; good tests should not depend on a previous test succeeding.

### 10.3. Do not put fixture secrets in logs or snapshots

Even though `test-pass` is sample data, logging raw Basic headers or full `Authentication` objects builds bad habits. With real user data, follow redaction/secret management and avoid pushing sensitive details into issues/CI artifacts. In tests, assert only status, authorities, and account name; never snapshot cookie/password values.

## 11. InMemoryUserDetailsManager CRUD API: Boundaries to Remember

### 11.1. createUser

`createUser(UserDetails user)` adds an account to the current store. If the username already exists, the implementation throws an error rather than silently overwriting permissions on the old account. Validate inputs and use a policy-compliant user registration API in real products.

### 11.2. updateUser

`updateUser(UserDetails user)` replaces an existing user's info. When changing only one authority, build a new `UserDetails` explicitly preserving the remaining attributes; `User.withUserDetails(existing)` helps copy the user's base data. Re-check account flags and password hash after updating to avoid accidentally locking/unlocking an account.

### 11.3. deleteUser

`deleteUser(username)` removes the user from the running manager. It **does not automatically revoke** issued JWTs or authenticated sessions in another filter chain. In a real system, deprovisioning also requires session invalidation, token/refresh-token revocation, events/auditing, and data protection.

### 11.4. userExists and loadUserByUsername

`userExists(username)` checks existence in the store. `loadUserByUsername(username)` returns `UserDetails` or throws `UsernameNotFoundException`. **Do not expose these methods directly** as public APIs allowing strangers to probe usernames; return generic login messages and apply rate limiting when needed.

### 11.5. updatePassword and changePassword

`updatePassword(UserDetails user, String newPassword)` accepts an encoded password to update the specified user; typically used by hash upgrade mechanisms via `UserDetailsPasswordService`. `changePassword(oldPassword, newPassword)` is tied to the current user and re-authentication conditions if the manager is configured. These two methods differ in intent; never expose them on uncontrolled REST endpoints.

### 11.6. Guarantees when multiple requests modify concurrently

The in-memory implementation provides user management operations within a single process, yet never design a production account lifecycle assuming "all permission updates are transactional and immediately consistent across a cluster". For role changes concurrent with login, session caching, revocation, or multiple replicas, you need a persistent store and consistency policies matching your application.

## 12. Easily Misunderstood Cases

### Case A: User exists yet still gets 403

Alice has the right username/password and the provider authenticated her; `GET /admin` returns `403` because she lacks `ROLE_ADMIN`. Creating a user in the manager **does not** automatically grant every URL permission. Test role-specific paths separately.

### Case B: POST returns 403 even though writer has TASK_WRITE

The CSRF filter can block POST before the authorization step. When testing, send `csrf()` and re-check. Do not disable CSRF globally just to make POST return 200; consider auto-attached browser credentials and the actual threat model.

### Case C: Hash stored yet login returns 401

You may be using `DelegatingPasswordEncoder` requiring the `{bcrypt}` prefix while the stored value lacks it, or using BCryptPasswordEncoder with a stored value that has the prefix. Check the **encoder bean** and stored hash format before blaming InMemoryUserDetailsManager.

### Case D: Created user bean yet Boot's "user" account still appears

You may be running a different profile/context, have multiple user stores, or the custom bean was not seen by component scan/auto-configuration. Check the runtime context, active profiles, and conditional configuration. Do not rely on the presence of username "user" from an older run.

### Case E: Changing password in test A makes test B fail

Test A mutates a singleton manager belonging to the cached `ApplicationContext`. Isolate mutating tests with a new manager; do not try to order tests to make them "stable".

### Case F: @WithMockUser logs in ghost-admin successfully

This is expected behavior of the mock security context. That test only proves the `hasRole("ADMIN")` rule works. To test the user store/BCrypt, use `httpBasic(...)` or call the real provider.

### Case G: Newly created user disappears after restart

The in-memory user store has no persistence. If you need users to survive restarts, use a database, LDAP, or an IdP. Manually serializing a `HashMap` to save demo accounts is not a proper production identity management approach.

### Case H: One replica has the user, another does not

Two JVMs have independent memory; copying code does not create shared storage. For multi-replica production, use a shared source and appropriate session/token/revocation policies.

### Case I: User deleted yet old session still gets in

If requests rely on an authentication stored in a session, they do not necessarily reload the user from the store on every request. Deleting from the manager does not automatically destroy all of that person's sessions. Design session invalidation/reauth and domain-level permission checks as separate steps.

### Case J: Letting the client send roles in JSON

`InMemoryUserDetailsManager` is a server-controlled user source; never take `roles` from the request body and create an admin account without policy. Role assignment requires administrative authority, actor verification, and auditing.

## 13. Deeper Dive: In-Memory Users, Sessions, and Permission Changes

A stateless HTTP Basic request can pass through the provider on **every request**. If Alice is granted/revoked `TASK_WRITE` in the in-memory store, a newly re-authenticated request can see the updated permissions. However, with session-based form login, an authenticated user may have an `Authentication` holding old authorities in the session and not automatically reload the user on each request.

```text
First request: Alice logs in
 -> UserDetails gets authorities [ROLE_USER, TASK_WRITE]
 -> Authentication is saved into session

Admin modifies user store:
 -> Alice now has only [ROLE_USER]

Subsequent request with the same session:
 -> If the old context is restored intact, authorities may still include TASK_WRITE
 -> Never assume updating the user store = instant revocation of all sessions
```

For permission changes to take effect immediately, the application needs a dedicated strategy: session invalidation/revocation, principal refresh, resource-level permission checks, or grant versioning. This goes beyond local memory and becomes critical across multiple instances.

**Resource access permissions:** Even when Alice has `TASK_WRITE`, you must still verify whether she is allowed to create tasks in tenant X; never rely on a route permission to let Alice modify tenant Y's data.

## 14. Test Matrix Needed for a Complete Lesson

| Group | Scenario | Expectation |
| --- | --- | --- |
| Source | `userExists("alice")` | true |
| Source | `loadUserByUsername("nobody")` | UsernameNotFoundException |
| Hash | `encoder.matches(raw, storedHash)` | true with right password |
| Hash | Compare two separate BCrypt hashes | Do not need to be equal |
| HTTP | `GET /public` anonymous | 200 |
| HTTP | `GET /me` anonymous | 401 with Basic entry point |
| HTTP | `GET /me` right password | 200 |
| HTTP | `GET /me` wrong password | 401 |
| HTTP | `GET /me` locked user | 401; provider-level test confirms LockedException |
| Authz | `GET /admin` Alice | 403 |
| Authz | `GET /admin` admin | 200 |
| CSRF | `POST /tasks` writer missing token | 403 |
| CSRF | `POST /tasks` writer wrong token | 403 |
| Authz | `POST /tasks` Alice with CSRF | 403 due to missing TASK_WRITE |
| Authz | `POST /tasks` writer with CSRF | 200 |
| Isolation | CRUD in fresh manager | Does not affect other HTTP tests |
| Isolation | New request without credentials in stateless demo | 401 |
| Safety | User deleted from manager | No longer exists in that manager; does not imply all sessions revoked |
| Domain | User from tenant A accesses tenant B object | Denied by service/resource policy |

HTTP outcomes also depend on `AuthenticationEntryPoint`, filter chain, CSRF, and framework version; the matrix above is the contract **of this lesson's demo**, not every Spring Security app if using form login or OAuth2.

## 15. When and How to Scale Beyond In-Memory?

When the goal is **learning and testing**, continue using InMemoryUserDetailsManager with clear fixtures. When real users are needed, choose a source by context:

| Option | Best fit | Additional design needed |
| --- | --- | --- |
| `InMemoryUserDetailsManager` | Demos, unit/integration tests, short PoCs | Separating from production, test isolation |
| `JdbcUserDetailsManager` | Default JDBC schema lessons or simple apps | Database, schema, migrations, transactions, password reset |
| Custom `UserDetailsService` with JPA/repository | Apps with custom user domain | Entity → UserDetails mapping, caching, transactions, lockout, role policy |
| LDAP/Active Directory | Organizations with a directory service | Secure connectivity, group mapping, lifecycle |
| OIDC/OAuth2 Identity Provider | SSO, multi-app, MFA | Issuer/audience trust, sessions/tokens, grant mapping |
| Reactive `MapReactiveUserDetailsService` | WebFlux demos and tests | Reactor Context, WebFilterChain, reactive authentication |
| JWT Resource Server | Bearer token APIs from a trusted issuer | Decoder, signatures, expiry, issuer/audience, scope/authority mapping |

**You do not always need to build your own users table** if the organization already has an IdP. Choose the identity source based on the authentication mechanism the app actually uses. `UserDetailsService` is specifically relevant to username/password checked by `DaoAuthenticationProvider`; JWTs do not automatically flow through this in-memory manager.

### When migrating from in-memory to a database

Keep the HTTP policy and test behavior at the contract level, intentionally swapping the **user source**:

```text
Before:
  DaoAuthenticationProvider
       |
       v
  InMemoryUserDetailsManager

After:
  DaoAuthenticationProvider
       |
       v
  Custom UserDetailsService -> UserRepository -> database
```

Tests can continue checking `401`, `403`, `200`, roles/methods, CSRF, and owner/tenant. Only swap the appropriate fixtures/setup. Separating the authentication provider, authorization rules, and domain policies makes migrations easier to review.

## 16. Self-Assessment Questions

**Question 1.** With `InMemoryUserDetailsManager` configured, has Spring Security automatically granted `ROLE_ADMIN` to every account?

**Answer:** No. The manager only holds the users/authorities you declare. `roles("ADMIN")` creates `ROLE_ADMIN` for that specific user, and the filter chain needs a `hasRole("ADMIN")` rule to protect the route.

**Question 2.** Why can `encoder.encode("x").equals(encoder.encode("x"))` be false with BCrypt even when the password is the same?

**Answer:** BCrypt uses salting; each encode call can generate a different hash. Use `encoder.matches("x", encodedHash)`.

**Question 3.** `@WithMockUser(username="admin", roles="ADMIN")` passes GET /admin. Does that prove admin's password is right?

**Answer:** No. Mock user creates a test SecurityContext without loading/comparing passwords against the store. Use `httpBasic(...)` through the filter chain or a provider-level test to check real credentials.

**Question 4.** You call `users.deleteUser("alice")` in one test. Another test `GET /me` with Alice suddenly returns 401. Why?

**Answer:** Both tests likely share the same InMemory bean and Spring cached context, so the earlier test deleted Alice. CRUD tests should create a dedicated manager.

**Question 5.** Why does writer with `TASK_WRITE` still get 403 on POST /tasks using curl?

**Answer:** A CSRF token may be missing/invalid, or another HTTP policy rejected it. Both authority and CSRF must be checked; never blindly disable CSRF.

**Question 6.** Created a new user at runtime then restarted the app—why did the user disappear?

**Answer:** The in-memory store does not persist. The bean is recreated, containing only the initially configured data.

**Question 7.** Alice has `ROLE_USER` and logs in properly; can she read Bob's invoices?

**Answer:** Cannot be inferred from the role. The service must check object permissions, owner/tenant, and business context.

**Question 8.** Why should a password-change API not call `changePassword` casually without configuring a manager to verify the old password?

**Answer:** The contract and implementation allow behavior to depend on the attached AuthenticationManager; without proper re-authentication, code may skip critical checks. Designing a password-change endpoint requires clear re-auth/step-up, hashing, CSRF, and auditing.

**Question 9.** Two Spring Boot replicas both have InMemoryUserDetailsManager. If an admin updates a user on replica A, does B automatically change?

**Answer:** No. Each process has its own memory, with no shared persistence/synchronization.

**Question 10.** Which test verifies real authentication, and which verifies only authorization?

**Answer:** `httpBasic(...)` with a real application context/provider tests credentials and URL policies; `@WithMockUser`/`user(...)` primarily tests policies with a mock principal.

## 17. Practice Checklist

- [ ] Understand that the manager is a **user store** in RAM, not an authentication filter?
- [ ] Created a `PasswordEncoder` bean and stored password hashes in the right format?
- [ ] Avoided `{noop}` or `withDefaultPasswordEncoder` for real users?
- [ ] Distinguished `roles("USER")` from `authorities("TASK_WRITE")` and the `ROLE_` prefix?
- [ ] Tested success, wrong password, non-existent username, locked account, and insufficient authority?
- [ ] Integration tests use HTTP Basic headers to pass through the real provider, in addition to mock principal tests?
- [ ] POST has CSRF protection tested independently from permissions?
- [ ] Tested that a subsequent request does not inherit the previous request's context when stateless?
- [ ] CRUD tests create fresh managers and do not mutate singleton state of the suite?
- [ ] Test fixtures live under `src/test` or a safe profile in production projects?
- [ ] No demo accounts/passwords included in production sources or public containers?
- [ ] If an account is changed/locked/deleted, considered old sessions/tokens and multi-instance effects?
- [ ] Actor permissions on objects/tenants are checked in the service, not just the HTTP path?
- [ ] Java, Boot, Security versions and APIs match; Maven tests run in a real environment?

## 18. Key Takeaways

1. **`InMemoryUserDetailsManager` stores `UserDetails` in RAM and implements `UserDetailsService`/`UserDetailsManager`** for quick learning or testing.
2. **`DaoAuthenticationProvider` is what verifies credentials** alongside `PasswordEncoder`; the manager supplies users, password hashes, authorities, and account states.
3. **`roles("ADMIN")` creates `ROLE_ADMIN`**; `authorities("TASK_WRITE")` is a separate permission. `SecurityFilterChain` is required to enforce them on routes.
4. **BCrypt compares using `matches`**, never comparing two hashes directly and never storing plaintext in production.
5. **Mock users differ from real password authentication.** Use `@WithMockUser` to test permissions, and `httpBasic(...)`/providers to test the credential path.
6. **CRUD on an in-memory store is stateful.** Create a separate manager for mutating tests; runtime changes do not persist across restarts or synchronize across JVMs.
7. **Do not use it as a production user store.** For real users, you need persistence/IdP, auditing, session revocation, secret handling, and resource policies.

## Official References

- [Spring Security 6.5 — In-Memory Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/in-memory.html)
- [Spring Security 6.5 — InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html)
- [Spring Security 6.5 — UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html)
- [Spring Security 6.5 — UserDetails / User Builder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage / PasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Testing HTTP Basic with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 Release and OSS Support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
