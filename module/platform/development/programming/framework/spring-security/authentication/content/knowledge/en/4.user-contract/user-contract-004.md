# InMemoryUserDetailsManager for Examples and Testing

## 1. Why Does Spring Security Have an In-Memory User Store?

`InMemoryUserDetailsManager` is a **non-persistent** implementation of `UserDetailsManager` in Spring Security. Instead of reading accounts from SQL tables, LDAP, or an external identity system, it keeps user information in the memory of the application process. This tool is particularly well-suited for **learning examples, sample apps, local prototypes, and tests needing a controllable account store**.

The important thing is understanding responsibilities accurately:

- `InMemoryUserDetailsManager` **stores, finds, and manages `UserDetails`**: username, one-way encoded password, account status, and list of authorities.
- `DaoAuthenticationProvider` **authenticates username/password**: loads `UserDetails` through the manager, calls `PasswordEncoder.matches(...)`, and checks account flags.
- `AuthenticationManager` (usually `ProviderManager`) **coordinates** provider calls and returns an authenticated `Authentication` or signals failure.
- `SecurityFilterChain`/security filters in web applications **receive requests, establish `SecurityContext`, and enforce access policies**.

Therefore, adding an `InMemoryUserDetailsManager` does not automatically give you a login controller, registration API, or HTTP session. It is **a concrete account source** that participates in the authentication flow when the application configures the appropriate components.

The goal of this lesson is to use that manager properly for **reproducible examples and tests**, distinguish testing the user store from testing the real authentication process, and know when not to use it.

## 2. Related Contracts

Type relationships:

```text
UserDetailsService
  └── UserDetailsManager extends UserDetailsService
        ├── InMemoryUserDetailsManager
        ├── JdbcUserDetailsManager
        └── other implementations

InMemoryUserDetailsManager
  ├── loadUserByUsername(username)
  ├── userExists(username)
  ├── createUser(user)
  ├── updateUser(user)
  ├── deleteUser(username)
  ├── changePassword(oldPassword, newPassword)
  └── updatePassword(user, encodedNewPassword)
       (per UserDetailsPasswordService contract)
```

In Spring Security 6.5.11, `InMemoryUserDetailsManager` implements both `UserDetailsManager` and `UserDetailsPasswordService`. It supports initialization via **a `UserDetails` array**, `Collection<UserDetails>`, `Properties`, or an empty constructor.

Key operations:

| API | Role | What to Know in Tests |
| --- | --- | --- |
| `new InMemoryUserDetailsManager(users...)` | Loads sample accounts when creating the object. | Creates concise fixtures with controlled initial data. |
| `loadUserByUsername("lan")` | Gets `UserDetails` by username; throws `UsernameNotFoundException` if not found. | Only tests data loading, **does not authenticate passwords itself**. |
| `userExists("lan")` | Checks whether the manager currently has the user. | Cannot deduce whether the user can log in. |
| `createUser(user)` | Adds a user in current memory. | Use only prepared test data. |
| `updateUser(user)` | Replaces user info (permissions, enabled flag, hash…). | Can simulate a locked/disabled account. |
| `deleteUser("lan")` | Removes user from the store. | Confirms the user is no longer found by the manager. |
| `updatePassword(user, encodedPassword)` | Replaces the **encoded** password string for a specific user. | Do not pass raw passwords to this parameter. |
| `changePassword(old, new)` | Password change API for the current subject per configuration. | Involves context/manager and auth conditions; avoid using casually in isolated tests. |

**Three distinct contracts:** `UserDetailsService` only **reads** users; `UserDetailsManager` adds **create/update/delete**; `UserDetailsPasswordService` supports updating password hashes. `InMemoryUserDetailsManager` supports all three roles, yet all of them operate on **the memory of the current instance**.

### What Does `UserDetails` Contain?

A typical account is built with the builder:

```java
UserDetails lan = User.withUsername("lan")
    .password(encoder.encode("DemoPass123!"))
    .roles("READER")
    .disabled(false)
    .build();
```

This record provides:

- `getUsername()` and `getPassword()` (an **encoded** password value; do not store plaintext).
- `getAuthorities()`: the `roles("READER")` builder generates the `ROLE_READER` authority.
- Flags `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()` for account checks during authentication.

Spring Security's `User` is a common `UserDetails` implementation. It does not replace business `Customer`/`Employee` entities, nor does it require the application to use Spring Data JPA.

## 3. Why Is This Manager Suitable for Lessons and Testing?

A good test needs **clear inputs, predictable results, and no external system dependencies**. Using an in-memory store helps:

1. Create users with specific names, roles, and statuses right in the fixture; no need for SQL schemas or LDAP.
2. Verify `loadUserByUsername`, `userExists`, `createUser`, `updateUser`, and `deleteUser` without touching real data.
3. Combine `DaoAuthenticationProvider` + `PasswordEncoder` to **test the real username/password authentication path**, including wrong passwords or disabled accounts.
4. Create a **fresh `InMemoryUserDetailsManager` for each test**, avoiding situations where a prior test deleted/modified permissions and broke the next test.
5. Use in Spring Boot demos when the goal is explaining filters, roles, and 401/403 without building a database yet.

On the flip side, whenever the application restarts and creates a new manager, dynamic in-memory data is lost; separate application instances do not sync with one another automatically. Therefore, **do not use it as a persistent account source for multi-instance runtime environments**.

## 4. Standalone Runnable Java 17+ Example: Create, Authenticate, Update, and Delete Users

This example uses **Java 17+, Gradle, and Spring Security 6.5.11**. It is a complete console program requiring no Spring Boot or web server. It performs both kinds of work to clarify the difference:

- **Account management** via `InMemoryUserDetailsManager`.
- **Real authentication** via `DaoAuthenticationProvider` and `ProviderManager`, using BCrypt to verify passwords.

Project structure:

```text
memory-users-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/MemoryUsersDemo.java
    └── test/java/demo/InMemoryUsersTest.java
```

### 4.1. Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'memory-users-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.MemoryUsersDemo'
}

test {
    useJUnitPlatform()
}
```

In a real project with Spring Boot dependency management, let Boot manage compatible Security versions rather than manually pinning differing versions of Security modules. The specific versions here simply ensure the console example has an explicit combination.

### 4.2. The `MemoryUsersDemo.java` Program

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class MemoryUsersDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        // Sample data is hashed before loading into the store.
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();

        InMemoryUserDetailsManager store =
                new InMemoryUserDetailsManager(lan);

        System.out.println("lan.exists=" + store.userExists("lan"));
        System.out.println("missing.exists=" + store.userExists("missing"));

        UserDetails loaded = store.loadUserByUsername("lan");
        System.out.println("lan.name=" + loaded.getUsername());
        System.out.println("lan.hashMatches=" + encoder.matches(
                "DemoPass123!", loaded.getPassword()));
        System.out.println("lan.hashRejectsWrong=" + !encoder.matches(
                "wrong-password", loaded.getPassword()));

        // Only when the manager/provider authenticates do we get a trusted Authentication.
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(store);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager authenticationManager =
                new ProviderManager(provider);

        Authentication result = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        System.out.println("login.authenticated=" + result.isAuthenticated());
        System.out.println("login.name=" + result.getName());
        System.out.println("login.reader=" + result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_READER"::equals));

        try {
            authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }

        // Create a new user in the same store.
        store.createUser(User.withUsername("mai")
                .password(encoder.encode("MaiPass123!"))
                .roles("EDITOR")
                .build());
        System.out.println("mai.exists=" + store.userExists("mai"));

        // Simulate a disabled account; preserve existing hash/roles.
        UserDetails mai = store.loadUserByUsername("mai");
        store.updateUser(User.withUserDetails(mai)
                .disabled(true)
                .build());

        System.out.println("mai.enabled="
                + store.loadUserByUsername("mai").isEnabled());

        try {
            authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "MaiPass123!"));
        } catch (DisabledException ex) {
            System.out.println("disabledUser=DisabledException");
        }

        store.deleteUser("mai");
        System.out.println("mai.existsAfterDelete="
                + store.userExists("mai"));
    }
}
```

In a terminal in the `memory-users-demo` directory, use JDK 17+ and a compatible Gradle/Gradle Wrapper:

```bash
gradle run --quiet
```

Lines printed by the program in order (excluding logs from Gradle or libraries if any):

```text
lan.exists=true
missing.exists=false
lan.name=lan
lan.hashMatches=true
lan.hashRejectsWrong=true
login.authenticated=true
login.name=lan
login.reader=true
wrongPassword=BadCredentialsException
mai.exists=true
mai.enabled=false
disabledUser=DisabledException
mai.existsAfterDelete=false
```

### 4.3. Explaining Why Those Results Are Correct

**`lan.exists` and `missing.exists`:** `userExists` only checks whether a record exists in the manager. It neither compares passwords nor creates an `Authentication`.

**`loadUserByUsername`:** returns `UserDetails` with the password hash. `encoder.matches("DemoPass123!", storedHash)` returns true because the hash matches; a wrong string does not match. Do not print hashes/raw passwords to logs.

**`login.authenticated=true`:** the result comes from `ProviderManager`/`DaoAuthenticationProvider`. The provider actually compares the raw password against the hash and builds an authenticated token, including authorities from `UserDetails`. `ROLE_READER` is generated from `roles("READER")`.

**`wrongPassword`:** a wrong password causes the provider to throw `BadCredentialsException` instead of returning an authenticated token.

**`createUser`, `updateUser`, `deleteUser`:** modify records **inside the store instance**. When `mai` is disabled, `DaoAuthenticationProvider` rejects her even with the right password; after deletion, `userExists("mai")` is false.

**A warning about `Authentication` objects:** the authenticated token `result` was created **before** modifying another account. Existing authentication results or sessions do not necessarily auto-update for every subsequent change in the user store. When testing account locking/deletion, clarify whether the test checks a **new login** or the **effect on an already logged-in session**, as those are two different behaviors.

### 4.4. Why Not Use `User.withDefaultPasswordEncoder()`?

Spring Security has a convenient builder for simple examples, but `User.withDefaultPasswordEncoder()` is marked unsafe for production and is deprecated in current APIs. In this lesson, we explicitly create a `PasswordEncoder` bean/object, use `encoder.encode(...)` to store hashes, and use the **same encoder** for the provider. That exposes responsibility boundaries and avoids forming poor password storage habits.

## 5. JUnit 5 Testing: A Fresh Store for Every Test

The important part of this topic is not just a one-off runnable demo, but also knowing how to **build safe fixtures for automated testing**. The next file can run with the Gradle setup above.

`src/test/java/demo/InMemoryUsersTest.java`:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

final class InMemoryUsersTest {

    private PasswordEncoder encoder;
    private InMemoryUserDetailsManager users;
    private AuthenticationManager authenticationManager;

    @BeforeEach
    void setUp() {
        // Do not share a static store across @Test methods.
        encoder = new BCryptPasswordEncoder();
        users = new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("DemoPass123!"))
                        .roles("READER")
                        .build()
        );

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        authenticationManager = new ProviderManager(dao);
    }

    @Test
    void loadsTheExpectedUserAndEncodedPassword() {
        UserDetails found = users.loadUserByUsername("lan");

        assertEquals("lan", found.getUsername());
        assertTrue(encoder.matches("DemoPass123!", found.getPassword()));
        assertFalse(encoder.matches("wrong", found.getPassword()));
        assertEquals("ROLE_READER",
                found.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void realProviderAcceptsCorrectCredentials() {
        Authentication verified = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!"));

        assertTrue(verified.isAuthenticated());
        assertEquals("lan", verified.getName());
    }

    @Test
    void realProviderRejectsWrongPassword() {
        assertThrows(BadCredentialsException.class, () ->
                authenticationManager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "wrong-password")));
    }

    @Test
    void disabledAccountCannotAuthenticate() {
        UserDetails before = users.loadUserByUsername("lan");
        users.updateUser(User.withUserDetails(before)
                .disabled(true)
                .build());

        assertFalse(users.loadUserByUsername("lan").isEnabled());

        assertThrows(DisabledException.class, () ->
                authenticationManager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "lan", "DemoPass123!")));
    }

    @Test
    void createUpdateAndDeleteChangeOnlyThisFixture() {
        users.createUser(User.withUsername("mai")
                .password(encoder.encode("MaiPass123!"))
                .roles("EDITOR")
                .build());

        assertTrue(users.userExists("mai"));

        UserDetails before = users.loadUserByUsername("mai");
        users.updateUser(User.withUserDetails(before)
                .authorities("catalog:write")
                .build());

        assertEquals("catalog:write",
                users.loadUserByUsername("mai").getAuthorities()
                        .iterator().next().getAuthority());

        users.deleteUser("mai");
        assertFalse(users.userExists("mai"));
        assertThrows(UsernameNotFoundException.class,
                () -> users.loadUserByUsername("mai"));
    }
}
```

Run the tests:

```bash
gradle test
```

**Expected result:** all five `@Test` methods pass and Gradle finishes the `test` task successfully; log line counts, runtime, and report formatting depend on the environment. No DB connection or HTTP server is needed. The second and third tests **actually call the provider to verify passwords**, so they test a clearer authentication path than calling `loadUserByUsername` alone.

### Why Create Fixtures in `@BeforeEach`?

- Each test gets **its own manager and `PasswordEncoder`**.
- A test deleting `mai` does not affect a test loading `lan`.
- An account disabled in one test does not cause another test to fail randomly.
- Independent of the order in which JUnit runs tests.
- No need to restore a database, roll back transactions, or flush Redis.

In multi-threaded or parallel tests, you still must watch out for shared state if you deliberately share **one manager**. `@BeforeEach` isolates fixtures per test instance, but does not fix a test design that uses a static/global/shared Spring context with competing mutations.

## 6. Using in a Spring Boot App: Configuring Beans for a Demo Environment

In a Spring Boot Servlet application with `spring-boot-starter-web` and `spring-boot-starter-security`, `InMemoryUserDetailsManager` can be configured as a `UserDetailsService` bean or a bean of its specific implementation type:

```java
// @Configuration snippet in a Spring Boot app with dependencies already present;
// requires imports for @Bean, @Configuration, @Profile, User,
// PasswordEncoder, BCryptPasswordEncoder, InMemoryUserDetailsManager.
@Configuration
class DemoUsersConfig {

    @Bean
    @Profile("demo")
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    @Profile("demo")
    InMemoryUserDetailsManager demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("DemoOnly123!"))
                        .roles("READER")
                        .build(),
                User.withUsername("mentor")
                        .password(encoder.encode("DemoAdmin123!"))
                        .roles("MENTOR")
                        .build()
        );
    }
}
```

This is a **bean snippet, not a standalone application**. You need a `@SpringBootApplication` class, an appropriate `SecurityFilterChain`, and controllers to serve web requests. The example uses `@Profile("demo")` to explicitly mark a demo environment; in practice you must also manage profiles, secrets, and release configs. Never enable a demo profile on a public system just because the app is hitting an authentication error.

In standard username/password configurations, Spring Security can use this `UserDetailsService` with `DaoAuthenticationProvider`; however, how the application builds `AuthenticationManager` and HTTP policies must be verified in the project configuration. **Creating an `InMemoryUserDetailsManager` does not automatically create a form login or REST endpoint.**

### Comparing Two States

**No custom user-source bean:** in certain Spring Boot web configurations with Spring Security, Boot creates a default user for quick testing if auto-configuration conditions are met.

**With an `InMemoryUserDetailsManager` bean:** the application supplies its own account source; this case usually causes Boot's default user configuration to back off per auto-configuration conditions. However, the user-source bean and `SecurityFilterChain` bean are two separate configuration parts; do not deduce solely from declaring a filter chain that Boot stopped creating a default user.

If the application has multiple authentication sources (DB + test users, LDAP + local, OAuth2/OIDC + password), explicitly manage which beans/providers are active per profile, qualifier, and `AuthenticationManager` selection. Avoid creating default usernames that accidentally collide with real users.

## 7. Three Easily Confused Testing Styles: Mock User, Real Store, and Real HTTP

A green test is valuable when you know **the execution path the test actually traversed**.

| Testing Approach | Principal Source | Does It Actually Verify Password via `DaoAuthenticationProvider`? | Best Suited When |
| --- | --- | --- | --- |
| `@WithMockUser` or `MockMvc.with(user(...))` | Spring Security Test creates a mocked principal/`Authentication`. | **No.** Does not require the user to exist in the store. | Testing authorization, controller/method security needing a specific user/role. |
| `@WithUserDetails("lan")` | Spring Security Test loads `UserDetails` via a `UserDetailsService` bean with matching name/qualifier. | **Does not automatically verify raw password** through login flow. | Testing code that depends on custom `UserDetails`, checking loaded authorities/principal. |
| JUnit test calling `AuthenticationManager.authenticate(...)` | Real store and real provider, such as `InMemoryUsersTest`. | **Yes.** | Testing username/password config, encoder, account flags. |
| `MockMvc` sending HTTP Basic or form-login against real filter chain | Real request processed through Spring Security filters + configured provider. | **Can be yes**, when the test wires real filters/manager/user source. | Testing full HTTP authentication, 401/403, success/failure, and endpoint permissions. |

### `@WithMockUser` Does Not Depend on `InMemoryUserDetailsManager`

Illustrative example inside a Spring test class with Spring Security Test integration:

```java
@Test
@WithMockUser(username = "lan", roles = "READER")
void canOpenReaderEndpointAsMockedUser() throws Exception {
    mockMvc.perform(get("/documents"))
            .andExpect(status().isOk());
}
```

This is a **snippet** requiring `mockMvc` configured with Spring Security and an existing `/documents` controller. It **does not** verify that `lan` is in `InMemoryUserDetailsManager`, that the password stores a proper hash, or that the provider rejects wrong passwords. `@WithMockUser` creates a principal for the test rather than running the login workflow.

### `@WithUserDetails` Calls the `UserDetailsService` Bean

```java
@Test
@WithUserDetails("lan")
void knowsThePrincipalFromTheConfiguredUserStore() {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("lan", current.getName());
}
```

This snippet requires Spring Security Test integration, a `UserDetailsService` bean containing user `lan`, and corresponding imports. It loads `UserDetails` and populates `SecurityContext` for the test. It **does not require the client to enter a password**. For custom principal classes, `@WithUserDetails` is more useful than `@WithMockUser` because the principal comes from the application's service.

### When You Need to Test HTTP Login

In a Spring MVC application with a Spring Security FilterChain integrated into `MockMvc`, send authentication info on the request:

```java
// Snippet inside a MockMvc test with @Autowired MockMvc,
// @SpringBootTest/@AutoConfigureMockMvc or equivalent configuration.
// Requires static imports: get, httpBasic, status.
mockMvc.perform(get("/documents")
        .with(httpBasic("lan", "DemoPass123!")))
        .andExpect(status().isOk());

mockMvc.perform(get("/documents")
        .with(httpBasic("lan", "wrong-password")))
        .andExpect(status().isUnauthorized());
```

Results depend on **HTTP Basic being enabled**, users/roles being loaded, and matching endpoints and rules. Only when those conditions hold does the test genuinely prove the web authentication path. With `MockMvc` using `formLogin()`, pay attention to the login URL, CSRF, and session; on a real running server, ensure credentials travel over HTTPS.

**Remember:** a request with `.with(user("lan"))` does not go through password verification like `.with(httpBasic("lan", "..."))` in an HTTP Basic filter chain. Both are useful, yet they **answer different testing questions**.

## 8. Test Scenarios to Include to Avoid Misconceptions

### Testing the Data Source

- Created users have the right username, password hash, authorities, and status.
- Loading a non-existent username throws `UsernameNotFoundException`.
- `userExists` changes properly after `createUser`/`deleteUser`.
- `updateUser` updates authorities/disabled per fixture.
- If using `updatePassword`, pass the **newly encoded hash** and verify via `encoder.matches(...)`.

### Testing Real Authentication

- Right password produces an authenticated token and expected principal.
- Wrong password is rejected with `BadCredentialsException`.
- Disabled/locked/expired users are not allowed to log in by the provider.
- Post-authentication permissions come from `UserDetails`, not from client-supplied roles.
- No successful `Authentication` when the user does not exist; by default the provider typically masks it as `BadCredentialsException`.

### Testing Authorization

- Guests cannot access URLs requiring `authenticated()`.
- Users with `ROLE_READER` can access permitted reader resources.
- Users lacking permissions are blocked by policy.
- Resource ownership is still enforced at the business layer.
- Mock-user tests only verify authorization checks in the test, not the user store or password encoder.

The cases above are **a suggested checklist**, not mandatory additions to the small example in section 5. Pick tests based on the behavior you need to prove rather than writing tests that merely mirror the implementation.

## 9. Passwords, Roles, and Status: Safety Rules Even in Demos

### Demo Passwords Can Be Fake, but the Verification Mechanism Should Be Real

Do not store plaintext passwords in `UserDetails.password` in demos that use a real `DaoAuthenticationProvider`. A good pattern:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("DemoOnly123!");
UserDetails demoUser = User.withUsername("student")
    .password(storedHash)
    .roles("READER")
    .build();
```

BCrypt hashes normally differ after every `encode` call due to salting; proper tests must use `matches(raw, hash)`, **not** compare two hashes with `equals`. Never place sample passwords in production code or request logs.

If using `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, generated hashes usually carry the `{bcrypt}` prefix; if using `BCryptPasswordEncoder` directly, hashes lack that prefix. Do not mix hash formats and encoders without checking format compatibility.

### `roles` vs. `authorities`

```java
User.withUsername("lan")
    .password(encodedPassword)
    .roles("READER")
    .build();
// authority: ROLE_READER

User.withUsername("mai")
    .password(encodedPassword)
    .authorities("document:write")
    .build();
// authority: document:write
```

This snippet only illustrates the builder; `encodedPassword` must be a valid value. `hasRole("READER")` checks `ROLE_READER` by default convention, while `hasAuthority("document:write")` checks the exact string provided. Do not assign `ROLE_ADMIN` to every test account just to make all tests pass.

### Account Status Must Be Tested Through the Provider When Needed

Calling `users.loadUserByUsername("lan").isEnabled()` tells you the fixture data is right. However, to conclude "a disabled user cannot log in", test `AuthenticationManager.authenticate(...)` and verify the attempt is rejected. Do not confuse checking object data with checking security decisions.

### Test Lifecycle Management

- Prefer fixtures created in `@BeforeEach` that live only for the test.
- Do not share a single mutable manager across parallel tests unintentionally.
- Do not hold demo passwords in global variables outliving the test.
- If tests use a cached Spring `ApplicationContext`, mutating an `InMemoryUserDetailsManager` bean can leak into another test sharing the context; isolate, recreate, or reset fixtures by design.
- Avoid relying on JUnit execution order or on data created by another test.

## 10. When Should You Move Away from InMemoryUserDetailsManager?

`InMemoryUserDetailsManager` is described in Spring Security documentation as a **non-persistent** store meant primarily for **testing and demonstration**. Consider switching to a database/directory/IdP if requirements include:

- Account data must survive restarts or scaling across multiple instances.
- Registration workflows, password recovery, account locking/unlocking, and change history.
- Auditing, migrations, long-term permission management, or centralized identity management.
- Syncing with business systems/LDAP/OIDC/SSO.
- User changes remaining consistent across sessions, servers, and deployments.

You can keep the `UserDetailsService` interface and swap the implementation for a DB/LDAP adapter in username/password cases. The authentication/provider layer can continue being used if the mechanism stays the same; however, JWT/OIDC architectures may need a different authentication flow. Never treat `InMemoryUserDetailsManager` as a "good enough for few users" production database: it lacks durability guarantees and proper identity administration workflows.

## 11. Common Mistakes

1. **"InMemoryUserDetailsManager checks passwords itself."** No. It loads users, while the provider/encoder verifies credentials.
2. **"`loadUserByUsername` finding a user means logged in."** No. That is only data for authentication.
3. **"`@WithMockUser` proves the user is in the store."** No. That test can pass even if the manager is empty.
4. **"`@WithUserDetails` authenticates the user's password."** No; it loads the principal and sets context for the test.
5. **"Testing `userExists` is enough to conclude the account can log in."** No; the user could be disabled, locked, or have a mismatched password.
6. **"Store plaintext for speed since it's just a test."** That leads to unrealistic configs and errors with BCrypt/Delegating encoders; hash in real-authentication examples.
7. **"Share one mutable store for the whole test suite."** Leads to ordering dependencies and parallel-run failures; create separate fixtures.
8. **"Disable security checks to make tests pass."** Never change `hasRole` to `permitAll` or strip filters from MockMvc if the goal is testing security.
9. **"Changing a user in the store automatically revokes old sessions."** Not guaranteed; sessions/contexts can retain identity/authorities from prior authentication.
10. **"Adding an `InMemoryUserDetailsManager` bean auto-generates a login REST API."** No. It supplies the account source; login/filters/controllers are separate parts.
11. **"Every Boot app with spring-security gets a demo user forever."** Boot auto-config conditions differ when the app supplies auth beans or uses OAuth2/Resource Server modules.
12. **"`changePassword` and `updatePassword` accept equivalent inputs."** Those two APIs have different contracts/contexts; `updatePassword` expects an **encoded** password.
13. **"`roles("ADMIN")` and `authorities("ADMIN")` are the same."** `roles` prepends `ROLE_` by convention; `authorities` uses the exact string.
14. **"Losing users on restart is a bug."** That is an in-memory characteristic: data has no durable storage.
15. **"Demo profile config can be deployed publicly."** A profile with sample accounts/credentials must be strictly controlled and never accidentally enabled in production.

## 12. Self-Check Questions

**Question 1.** An `InMemoryUserDetailsManager` contains user `lan` and a password hash. Why is sending a wrong password still blocked?

**Answer:** The manager only provides `UserDetails`. `DaoAuthenticationProvider` uses `PasswordEncoder.matches(...)` to compare the raw password against the hash; if they do not match, authentication fails.

**Question 2.** A test with `@WithMockUser(username="lan")` passes, yet `users.userExists("lan")` is false. Is that a contradiction?

**Answer:** No. `@WithMockUser` builds a mocked principal/`SecurityContext`; the test does not require the user to exist in the store.

**Question 3.** How should you test that `DaoAuthenticationProvider` rejects a disabled account?

**Answer:** Create the user in the manager, update `disabled(true)`, and call `AuthenticationManager.authenticate(...)` with the right password; verify `DisabledException` is thrown.

**Question 4.** One test modifies `lan`'s role to `ROLE_ADMIN`, causing another test to falsely pass. Why?

**Answer:** The tests share a mutable store or a cached Spring context. Create a fresh fixture for each test or explicitly control isolation/resetting.

**Question 5.** Once `deleteUser("lan")` has run, is a user with an open session logged out immediately?

**Answer:** Do not assume so. `deleteUser` only removes the record from the store; session/revocation behavior depends on the context mechanism and the application's session policy.

**Question 6.** Why do tests use `encoder.matches(...)` instead of generating a new hash and comparing strings?

**Answer:** BCrypt uses a random salt; two `encode` calls for the same password can yield two different hashes. `matches` is the proper verification API.

**Question 7.** How does the purpose of `userExists` differ from `loadUserByUsername`?

**Answer:** `userExists` returns a boolean answering whether the user exists; `loadUserByUsername` returns `UserDetails` or throws `UsernameNotFoundException`. Neither evaluates passwords on its own.

**Question 8.** When should you use MockMvc with `httpBasic(...)` instead of `@WithMockUser`?

**Answer:** When you need to test the HTTP request path through the filter chain and real username/password verification, rather than only testing authorization logic with a mocked identity.

## 13. Official Documentation

- [Spring Security 6.5.11 – InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): constructors, `UserDetailsManager`, `UserDetailsPasswordService`, and user management operations.
- [Spring Security – Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): in-memory user configuration and how it connects to authentication.
- [Spring Security – UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): role as user information provider for `DaoAuthenticationProvider`.
- [Spring Security 6.5.11 – DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `UserDetailsService` and `PasswordEncoder` in real authentication.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` and `@WithUserDetails`.
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): integrating MockMvc with security filters and request post-processors.
- [Spring Security 6.5.11 – UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): building accounts and status attributes.

**Conclusion:** `InMemoryUserDetailsManager` helps build clear, flexible, and isolated sample account stores for tests. To test real passwords, combine it with `DaoAuthenticationProvider` and `PasswordEncoder`; to test access permissions alone, use mock tests for their intended purpose. In real applications, always distinguish an in-memory user source from a persistent identity management system, and distinguish user data from an authenticated login session.