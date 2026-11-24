# UserDetailsRepositoryReactiveAuthenticationManager and PasswordEncoder

**Topic:** Spring Security – reactive (Spring WebFlux)  
**Context:** Users and passwords  
**Prerequisites:** Java 17+, understanding of `Mono`, HTTP Basic, and `@Configuration` beans in Spring Boot.

These two components address **two distinct yet tightly connected responsibilities** when authenticating username/password credentials in a WebFlux application:

- `UserDetailsRepositoryReactiveAuthenticationManager` is a `ReactiveAuthenticationManager`: it receives an authentication request, retrieves the account via `ReactiveUserDetailsService`, performs user- and password-related checks, and returns a `Mono<Authentication>` when valid or emits an authentication error on failure.
- `PasswordEncoder` determines **how passwords are transformed for storage** (`encode`) and **whether a user-entered password matches the stored hash** (`matches`). It **does not** load users, grant roles, issue sessions, or check endpoint access permissions.

**Practical takeaway:** Store **one-way hashes**, use the same `PasswordEncoder` policy when creating accounts and when authenticating, pass `ReactiveUserDetailsService` into the manager, and wire the manager into the right `SecurityWebFilterChain`. After authentication, Spring Security uses the `Authentication` in the reactive security context to enforce `authorizeExchange` rules and serve business code.

## 1. The Three Interfaces/Classes Involved in Password Authentication

| Component | Input | Output / Role | What It Does Not Do |
| --- | --- | --- | --- |
| `ReactiveUserDetailsService` | Username, via `findByUsername(String)` | `Mono<UserDetails>` containing username, **password hash**, authorities, and account status; or empty if no user exists | Does not verify the password the user just entered |
| `PasswordEncoder` | `encode(rawPassword)`, `matches(raw, encoded)` | Generates hashes during registration/password change; verifies passwords at login | Does not know which tenant the user belongs to or whether they can read a resource |
| `UserDetailsRepositoryReactiveAuthenticationManager` | Unauthenticated `Authentication` (typically `UsernamePasswordAuthenticationToken`) | Authenticated `Mono<Authentication>` or `AuthenticationException` error | Does not create HTTP responses, cookies, or endpoint mappings itself |
| `SecurityWebFilterChain` / authentication web filter | HTTP request + credentials | Converts credentials into a token, calls the manager, establishes the security context, handles errors and authorization | Does not save passwords to the database for you directly |

Avoid confusing similarly named types:

- **Reactive/WebFlux:** `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `UserDetailsRepositoryReactiveAuthenticationManager`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`.
- **Servlet/MVC:** `UserDetailsService`, `AuthenticationManager`, `DaoAuthenticationProvider`, `HttpSecurity`, `SecurityFilterChain`, thread-local `SecurityContextHolder`. Servlet examples cannot be copied verbatim to WebFlux.

`MapReactiveUserDetailsService` is an in-memory implementation suited for learning or testing. With a real database, implement a custom `ReactiveUserDetailsService` returning results from a **reactive** repository; do not turn blocking JDBC calls into "reactive" merely by wrapping them in `Mono.just(...)`.

## 2. End-to-End HTTP Basic Authentication Flow

In a WebFlux application configured with HTTP Basic:

```text
Client GET /api/me
Authorization: Basic <encoded-user-and-password>
       |
       v
Spring Security AuthenticationWebFilter for HTTP Basic
       | extracts username/password from header
       v
Unauthenticated UsernamePasswordAuthenticationToken
       |
       v
ReactiveAuthenticationManager.authenticate(token)
       |
       v
UserDetailsRepositoryReactiveAuthenticationManager
       |-- ReactiveUserDetailsService.findByUsername(username)
       |       └── UserDetails: username, passwordHash, authorities, status
       |-- PasswordEncoder.matches(rawPassword, passwordHash)
       |-- user status checks / additional policies
       |
       +-- WRONG: Mono emits AuthenticationException
       |           └── HTTP Basic usually returns 401 + WWW-Authenticate
       |
       +-- RIGHT: Authenticated Mono<Authentication>
                 └── SecurityContext of the request/subscriber
                           |
                           v
                 authorizeExchange: permission check
                           |
                  +--------+---------+
                  |                  |
               allowed         missing permission
                  |                  |
                  v                  v
             controller          403 (typical)
                  |
                  v
         Mono/Flux -> HTTP response
```

Processing occurs inside the reactive pipeline: creating a `Mono` and actually subscribing are two different things. `findByUsername` must feed the **matching username's** data into the stream; the manager compares passwords using the chosen encoder. Spring Security handles filter selection and combining authentication with authorization; business services **should not manually call** `manager.authenticate(...).subscribe()` just to "force a login".

**An often-overlooked point:** `Authentication.getAuthorities()` represents authenticated permissions; `hasRole("ADMIN")` typically looks for the `ROLE_ADMIN` authority (default prefix). Logging in successfully does not grant access to every endpoint, and `PasswordEncoder.matches(...) == true` alone does not prove the account is enabled or has enough roles.

## 3. How PasswordEncoder Works

Core interface (signature description):

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Meaning:

1. **Registration or password change:** obtain the raw password from the request over a secure channel, validate/enforce appropriate policies, call `passwordEncoder.encode(raw)` **once** before saving; the database stores `encodedPassword`, never `rawPassword`.
2. **Login:** take the **raw password** sent by the client (held only transiently during verification), load `encodedPassword` from the user store, and call `passwordEncoder.matches(raw, encoded)`. Do not decrypt hashes; do not "re-encode and compare two newly encoded strings".
3. **Hash upgrade:** `upgradeEncoding(encoded)` can signal that a stored hash is outdated/weak compared to the new configuration. To automatically upgrade and persist on valid login, integrate a password update service; managers/repositories do not automatically rewrite your database just because you swapped encoders.

Example of correct behavior (illustrative Java snippet, not a standalone program):

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String hash = encoder.encode("correct horse battery staple");

boolean ok = encoder.matches("correct horse battery staple", hash);
boolean wrong = encoder.matches("incorrect", hash);

System.out.println(ok);
System.out.println(wrong);
```

Exact stdout of the **two println statements**:

```text
true
false
```

The `hash` value is not printed because BCrypt uses a random salt, so running it twice for the same password typically produces **two different hashes**. That is expected behavior. Never compare `encoder.encode(input).equals(hashFromDatabase)`; always use `matches`.

### 3.1. Why Use a Slow Salted Hash?

Passwords are guessable secrets that may be exposed if a database is copied. Purpose-built password hashing increases the cost of offline attacks. BCrypt is a built-in, practical choice in Spring Security; Argon2 or PBKDF2 are also dedicated password algorithms when properly configured and supported.

- **Salt:** a random value attached to each password/hash, preventing two users with the same password from producing the same fixed hash and hindering precomputed table lookups. BCrypt embeds the salt and work factor inside the hash string.
- **Work factor / cost:** hashing is intentionally more compute-heavy than plain SHA-256, slowing down bulk password guessing. Benchmark on real infrastructure to choose an appropriate balance between security and login latency.
- **Not decryptable encryption:** a one-way hash is for matching, and cannot be "decrypted" to return the old password. Forgotten passwords must go through a **reset** workflow with single-use, expiring tokens and proper verification.

Using raw `MessageDigest` SHA-256, MD5, Base64, or reversible encryption as a password storage mechanism is inappropriate. Password hashing also does not replace TLS; passwords still travel from client to server during login and require HTTPS outside localhost.

## 4. DelegatingPasswordEncoder and the {id} Prefix

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates a `DelegatingPasswordEncoder`. When encoding a new password, the default configuration typically picks BCrypt and produces the format:

```text
{bcrypt}$2a$10$...salt-and-hash-part...
```

**This is an illustrative format**, not a valid hash to copy into a database. Components:

- `{bcrypt}` is the **algorithm id** used by `DelegatingPasswordEncoder` to select the implementation during `matches`.
- The `$2a$10$...` part is the BCrypt string containing version, cost, salt, and hash output.
- For older passwords, other prefixes like `{pbkdf2}` or `{noop}` may exist if the system previously used them. Just because an encoder can read a format **does not mean** that format should continue to be used for new data.

When calling `matches(raw, "{bcrypt}...")`, the delegating encoder reads the id `bcrypt` and delegates the remainder to `BCryptPasswordEncoder`. If a stored hash **has no prefix** or has an unsupported id, the default configuration may throw `IllegalArgumentException` such as "There is no PasswordEncoder mapped for the id ...". Do not treat this as a normal wrong-password failure or "fix" it by disabling hashing.

**Common mistake:**

```java
// Generates a raw BCrypt hash, typically WITHOUT {bcrypt}:
String withoutId = new BCryptPasswordEncoder().encode("secret");

// Yet matches using DelegatingPasswordEncoder:
PasswordEncoder delegating =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

// Can fail due to missing id, even though the inner BCrypt part is valid.
delegating.matches("secret", withoutId);
```

This is an intentional fragment illustrating a configuration bug and should not be copied into real login flows. You can either consistently use a single `BCryptPasswordEncoder` for both encode/matches in a legacy system or **migrate the data** to the `{id}` format. Never blindly prepend `{bcrypt}` to every record without verifying all existing data is actually valid BCrypt. Do not set `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder.getInstance())` as a blanket patch: it can silently accept plaintext passwords unintentionally.

### 4.1. The {noop} Prefix: Fine for Learning, Never for Production

Online examples sometimes use:

```java
User.withUsername("demo")
    .password("{noop}password")
    .roles("USER")
    .build();
```

`{noop}` means **no password hashing**, acceptable at most for short-lived demonstrations but unsuitable for storing real users. In the runnable example below, we use `PasswordEncoderFactories.createDelegatingPasswordEncoder()` to encode with BCrypt right when creating the in-memory users.

### 4.2. Should You Change the Work Factor and Algorithm?

- If using BCrypt directly: `new BCryptPasswordEncoder(strength)` (cost within the API-supported range). Store hashes consistently with that encoder.
- If using Delegating: define an explicit map of algorithms/ids and `idForEncode` when switching algorithms for new passwords, while still allowing verification of existing hashes during migration. Never alter prefixes with arbitrary string manipulation.
- Changing the cost does not invalidate old hashes; `matches` still relies on the stored parameters, while rehashing depends on your integration.
- Evaluate CPU/latency budgets, valid login speed, brute-force resistance, memory requirements, and cost over time. Never lower the work factor just because tests feel slow without measuring.

## 5. Complete Java 17+ WebFlux Application Example

We will implement three endpoints:

- `GET /public/ping`: public, returns `pong`.
- `GET /api/me`: requires login; reads the Authentication's username from Reactor Context.
- `GET /api/admin`: requires `ROLE_ADMIN`; regular readers cannot access it.

There are two demo accounts: `alice / alice123` with role `USER`, and `admin / admin123` with role `ADMIN`. Passwords are encoded **before being placed into the in-memory user store**; the manager uses the same encoder to verify them. Example passwords are only for **localhost** and must not be reused in real systems.

### 5.1. Project Files and Dependencies

```text
reactive-password-auth/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/password/
    │   │   ├── PasswordAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/demo/password/
        └── PasswordAuthTests.java
```

The example uses Spring Boot `3.5.7`, released and available on Maven Central, for consistent dependencies. When moving to production, upgrade to a supported/patched version per project policy; do not treat the example version number as a permanent recommendation.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-password-auth</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-password-auth
server.port=8080
```

Do not add `spring-boot-starter-web` for a WebFlux lesson: if both MVC and WebFlux are present, Spring Boot may choose Servlet/MVC by default priority, breaking expectations about reactive filters.

### 5.2. Entry Point

`src/main/java/demo/password/PasswordAuthApplication.java`:

```java
package demo.password;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordAuthApplication.class, args);
    }
}
```

The three main Java classes reside in the same `demo.password` package and are discovered by component scanning.

### 5.3. Configuring PasswordEncoder, ReactiveUserDetailsService, and Manager

`src/main/java/demo/password/SecurityConfig.java`:

```java
package demo.password;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    UserDetailsRepositoryReactiveAuthenticationManager passwordManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            UserDetailsRepositoryReactiveAuthenticationManager passwordManager) {

        return http
            .authenticationManager(passwordManager)
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Key points **bean by bean**:

1. `passwordEncoder()` returns a single encoder policy used consistently throughout. With Spring Security's default factory in the example version, new passwords have the `{bcrypt}` prefix.
2. `users(encoder)` creates `UserDetails` carrying **hashes**. Each time the application starts, hashes are regenerated with new salts, yet the same raw passwords still log in. This is an in-memory demo, not a persistent database.
3. `passwordManager(users, encoder)` explicitly constructs the `UserDetailsRepositoryReactiveAuthenticationManager` being studied; the constructor takes `ReactiveUserDetailsService`, and `setPasswordEncoder` configures hash verification. By default the manager also has a delegating encoder, but declaring it explicitly prevents policy drift between password creation and authentication.
4. `security(..., passwordManager)` passes the manager into `ServerHttpSecurity.authenticationManager` and configures the HTTP Basic filter to accept credentials; only necessary endpoints are permitted. `formLogin` is disabled so tests do not get redirected to a login form.
5. `hasRole("ADMIN")` is **authorization** after authentication succeeds. A valid Alice without the ADMIN role still gets 403. Logging in as admin does not open every route because `anyExchange().denyAll()` blocks undeclared paths.

**Mind the Spring bean lifecycle:** The `users` method depends on the Spring-injected `PasswordEncoder` bean; do not instantiate a different encoder in a controller or a different encoder when comparing passwords. With a real database, users must not be re-encoded on every `findByUsername`: the repository must return the **stored hash as-is**.

### 5.4. Controller Reading the Principal from Reactor Context

`src/main/java/demo/password/ProbeController.java`:

```java
package demo.password;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProbeController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

Once Spring Security authenticates HTTP Basic successfully, the `/api/me` controller reads the current subscription's `Authentication` via `ReactiveSecurityContextHolder`, never reading the username from a query parameter or an untrusted `X-User` HTTP header. The controller returns a `Mono` for the framework to subscribe to; never call `subscribe()` manually.

## 6. Running the Application and Verifying HTTP Statuses

Inside `reactive-password-auth`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Use JDK 17+, Maven 3.9+, and an available port 8080. Once the Reactor Netty server starts successfully, in another terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user unknown:whatever http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
```

Expected in order:

| Request | Status | Body / Meaning |
| --- | --- | --- |
| `/public/ping` without credentials | 200 | `pong`; public URL |
| `/api/me` without credentials | 401 | HTTP Basic challenge, usually includes `WWW-Authenticate: Basic ...` |
| `/api/me` with Alice's correct password | 200 | `alice` |
| `/api/me` with Alice's wrong password | 401 | `matches` fails; no identity granted |
| `/api/me` with nonexistent user | 401 | Does not disclose whether the user exists in public response |
| `/api/admin` with Alice's correct password | 403 | Authenticated, but lacks `ROLE_ADMIN` |
| `/api/admin` with admin's correct password | 200 | `admin-ok` |

`401` and `403` are expectations for this HTTP Basic example and common default error configuration; apps with form login, OAuth2, custom entry points, or access-denied handlers may differ. A `401` response **does not identify** precisely whether the user doesn't exist, the hash format is invalid, or the password is wrong: inspect the system server-side while keeping client messages generic enough to prevent username enumeration.

On Windows PowerShell, if `curl` is an alias for `Invoke-WebRequest`, use `curl.exe`. Basic sends credentials via a Base64 header, **without encrypting the transport**; use localhost only in examples and HTTPS in real systems. Avoid putting real credentials into scripts, shell history, or logs.

## 7. Testing with WebTestClient and StepVerifier

The test suite below checks two separate layers:

- **Encoder/manager layer:** hash carries the prefix, right/wrong passwords, manager produces `Authentication` and authorities, and never comparing two fresh hashes via string equality.
- **HTTP layer:** filter uses the manager, and endpoints requiring authentication and authorization return 200/401/403 as expected.

`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real server on a random port. Spring Boot 3.5 supports injecting `WebTestClient` for WebFlux apps with this setup; tests do not require `mvn spring-boot:run` running in another terminal. `StepVerifier` verifies signals of standalone `Mono`s.

`src/test/java/demo/password/PasswordAuthTests.java`:

```java
package demo.password;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PasswordAuthTests {

    @Autowired
    WebTestClient client;

    @Autowired
    PasswordEncoder passwordEncoder;

    @Autowired
    ReactiveUserDetailsService users;

    @Autowired
    UserDetailsRepositoryReactiveAuthenticationManager manager;

    @Test
    void storedPasswordIsEncodedAndMatchesOnlyCorrectRawPassword() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertTrue(user.getPassword().startsWith("{bcrypt}"));
                assertFalse(user.getPassword().equals("alice123"));
                assertTrue(passwordEncoder.matches(
                    "alice123", user.getPassword()));
                assertFalse(passwordEncoder.matches(
                    "wrong", user.getPassword()));
            })
            .verifyComplete();
    }

    @Test
    void saltedHashesOfSameRawPasswordCanDiffer() {
        String first = passwordEncoder.encode("somePassword");
        String second = passwordEncoder.encode("somePassword");

        assertNotEquals(first, second);
        assertTrue(passwordEncoder.matches("somePassword", first));
        assertTrue(passwordEncoder.matches("somePassword", second));
    }

    @Test
    void managerAuthenticatesAndSuppliesAuthorities() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "alice123");

        StepVerifier.create(manager.authenticate(request))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream().anyMatch(
                    authority -> authority.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsIncorrectPassword() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "incorrect");

        StepVerifier.create(manager.authenticate(request))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void publicEndpointDoesNotRequirePassword() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousUserGetsHttpBasicChallenge() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctCredentialsReachProtectedEndpoint() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void wrongPasswordReturns401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserReturns401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("unknown", "guess"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectPasswordCanAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Run:

```bash
mvn test
```

With only `PasswordAuthTests`, **11 tests are expected to pass**. Do not try to predict exact Maven logs, BCrypt hash timings, or test execution order as they vary by environment. This is sample code for the reader to create and run the project; run it with the proper JDK/Maven versions before treating it as real test output.

### 7.1. Reading Results and Test Limitations

- `storedPasswordIsEncodedAndMatchesOnlyCorrectRawPassword` confirms the in-memory user store holds hashes, not raw passwords. Hashes are generated at startup, not fixed byte sequences.
- `saltedHashesOfSameRawPasswordCanDiffer` proves two hashes should not be compared by equality; to keep tests stable long-term across encoder changes, focus on `matches` and the chosen algorithm policy. With BCrypt, random salts make the probability of two identical hashes minuscule.
- `managerAuthenticatesAndSuppliesAuthorities` proves calling the **real manager** produces an `Authentication` and loads Alice's authorities.
- `managerRejectsIncorrectPassword` tests `BadCredentialsException` at the manager level for **an existing username with a wrong password**; it does not assert every kind of authentication failure uses this class.
- The HTTP tests verify the filter reads the Basic header, invokes the manager, and enforces authorization; direct manager tests alone do not prove the WebFilter is wired properly.
- Testing that `admin` is allowed and Alice is denied on the same URL clarifies **authentication vs. authorization**: a correct password does not imply sufficient roles.

Do not turn tests into checking internal hashes against a hardcoded BCrypt string; hashes use random salts. To test upgrade policies, build a valid legacy hash fixture, configure the password service, and assert the update is actually saved after successful authentication.

## 8. Execution Timing, Performance, and Schedulers in Reactive

`ReactiveUserDetailsService.findByUsername` returns `Mono<UserDetails>`, typically subscribed inside the authentication pipeline. Notes:

1. If the user source comes from R2DBC/a reactive driver, calling the repository to return a Publisher usually does not perform I/O immediately; I/O runs upon subscription. **Do not wrap** blocking calls in `Mono.just(blockingRepository.findUser(...))` because Java evaluates arguments eagerly.
2. BCrypt password verification is intentionally **CPU-intensive**. Spring Security's `AbstractUserDetailsReactiveAuthenticationManager` can offload password verification onto a scheduler; do not assume every callback runs on the Netty event loop. Do not blindly spawn `Schedulers.parallel()` per request yourself.
3. Composing reactive user lookup, hash verification, and authorization must preserve the request's **Reactor Context**. Never store principals in static/singleton variables across concurrent requests.
4. Never call `block()` on the WebFlux event loop to query users or await the manager. For a temporarily unavoidable blocking data source, isolating it with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` can serve as a bridge, while still planning migration to a reactive driver, load limits, and latency monitoring.
5. Consider rate limiting, backoff, credential-stuffing defenses, and concurrency limits so the login endpoint cannot be abused as a BCrypt CPU-exhaustion vector. Never lower cost or disable hashing to "fix" timeouts without measuring accurately first.

The manager exposes `setScheduler(...)` for advanced tuning; keep the default until benchmarks provide a measurable reason to change it. A scheduler does not replace protecting database/CPU pools under heavy load.

## 9. Moving ReactiveUserDetailsService from In-Memory to a Database

In-memory stores are for demos, tests, or small configurations. Real applications need persistent user tables and hashes. You can use R2DBC and query by a normalized, unique username.

**Suggested data schema:**

| Field | Meaning |
| --- | --- |
| `id` | Internal ID, not necessarily identical to username |
| `username` | Unique value per policy; sanitize/normalize input carefully |
| `password_hash` | Complete encoded string, including `{id}` prefix if using delegating |
| `enabled`, `locked` | Account status; checked by the manager via `UserDetails` |
| `authorities` or separate role table | Current permissions, which may require reactive resolution |
| `password_changed_at`, `updated_at` | For lifecycle/alerting/updates; never store raw passwords |

**Design fragment** example, not a standalone Java file:

```java
@Service
class DatabaseUserDetailsService implements ReactiveUserDetailsService {
    private final AccountRepository accounts;

    DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash()) // Do NOT re-encode
                .authorities(account.authorities().toArray(String[]::new))
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .build());
    }
}
```

This snippet assumes an `AccountRepository` with `Mono<Account> findByUsername(String)` and a record/account model with corresponding accessors; import `@Service`, `Mono`, `User`, `ReactiveUserDetailsService`, `UserDetails`, and domain types. If the user does not exist, the repository should return `Mono.empty()` per the service contract. Never turn "user not found" into a default user or use an empty password.

When **creating accounts** via a dedicated API, persistence code may look like:

```java
Mono<Account> register(RegisterRequest request) {
    return Mono.fromSupplier(() ->
            passwordEncoder.encode(request.password()))
        .flatMap(hash -> accounts.insert(
            request.username(), hash, /* other verified fields */));
}
```

This is **pseudocode/a fragment** illustrating where encoding occurs; `Account`, `RegisterRequest`, and `accounts.insert` are project-defined. Note that hashing is CPU-intensive; `Mono.fromSupplier` defers execution here, but **does not automatically switch threads**. Real systems must place encoding on an appropriate scheduler or use an account management mechanism with explicit resource controls, plus handle duplicate usernames, email verification, rate limiting, and dedicated password requirements. Do not copy this fragment as finished controller code.

## 10. Upgrading Hashes Without Forcing Everyone to Change Passwords

An organization may upgrade algorithms/cost over time, such as moving from `{bcrypt}` with an old work factor to a newer policy. A sound plan:

1. Use `DelegatingPasswordEncoder` to **keep verifying** accepted legacy hashes via trusted ids. Only allow the algorithms needed during the migration window.
2. When a user logs in successfully, if `passwordEncoder.upgradeEncoding(storedHash)` indicates an upgrade is needed, generate a new hash with the active encoder and save it via `ReactiveUserDetailsPasswordService`.
3. `UserDetailsRepositoryReactiveAuthenticationManager` inherits `setUserDetailsPasswordService(...)`; automatic upgrades require configuring an implementation that actually updates storage and testing that path.
4. Ensure password hash updates do not overwrite concurrent user changes, respect datastore transactions/concurrency, and preserve account permissions/flags.
5. Track the proportion of legacy hashes and infrequently logging-in accounts, and maintain a separate password change/reset process for accounts that cannot migrate via login.

**Example interface to implement**:

```java
public interface ReactiveUserDetailsPasswordService {
    Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
}
```

This is an abbreviated signature for learning; the real method uses Spring Security's corresponding types. The `newPassword` parameter in the upgrade mechanism is the **new hash string** to persist, not a request to grab the user's plaintext password out-of-band. Implementations must update the database and return the updated `UserDetails` per contract. Avoid logging hash strings or raw credentials during migration.

**Do not do this:** when switching to delegating, replace every old password hash with `encoder.encode(oldHash)`. That hashes the **hash string**, making it impossible for users to log in with their original passwords. Only encode raw passwords during registration/password change or after **a successfully authenticated login** while the raw password is in scope as needed.

## 11. Checking User Status and Safe Error Handling

`UserDetails` also carries flags such as `enabled`, `accountNonLocked`, `accountNonExpired`, and `credentialsNonExpired`. The manager and its associated check strategies use them to gate login. A disabled/locked account must not receive a valid `Authentication` merely because the password matches. For custom policies, configure the right check strategy instead of ignoring status flags.

Errors to distinguish **internally** without leaking too much **externally**:

| Case | Investigation Point | Typically Appropriate Public Response |
| --- | --- | --- |
| User missing | `findByUsername` empty / manager strategy | HTTP Basic 401, generic message |
| Wrong password | `PasswordEncoder.matches` false | 401, do not reveal user existence |
| Hash missing prefix or invalid id | Legacy data mismatched with `DelegatingPasswordEncoder` | Investigate config and migration; never disable hashing |
| User disabled/locked/expired | `UserDetails` and check strategy | Reject login per policy; safe public message |
| Right password but missing permission | `authorizeExchange`, role/authority, domain policy | Usually 403 |
| Slow user store / connection error | Reactive database, timeouts, retries, circuit breaker | System error, never fall back to granting access |
| BCrypt taking too long under heavy load | CPU capacity, scheduler, cost, rate limiting | Optimize with measurements while keeping password hashing secure |

**Never log passwords, Basic headers, bearer tokens, or full password hashes.** Log login events with permitted request IDs/user IDs and appropriate error categories, preventing information leakage and complying with data controls. Never send stack traces or password hashes to clients. Avoid differing public responses between "username does not exist" and "wrong password" that allow attackers to enumerate accounts; for timing risks, evaluate separately rather than assuming an identical message alone prevents differentiation.

## 12. Common Configuration Mistakes and Fixes

### 12.1. Storing Plaintext with a Strong Encoder

`PasswordEncoder` only helps if **`encode` is actually called before saving**. Storing `"alice123"` in the database and then using a delegating encoder for `matches` will fail; never slap `{noop}` onto everything just to make tests pass. Run a controlled migration or reset passwords per policy.

### 12.2. Double-Encoding When Reading Users

`findByUsername` must never do:

```java
return repository.findByUsername(username)
    .map(user -> User.withUsername(user.username())
        .password(passwordEncoder.encode(user.passwordHash())) // WRONG!
        .roles("USER")
        .build());
```

This is an intentionally wrong fragment (repo/model types are application-defined). This bug turns the database hash string into **input for a new hash**, so valid passwords will never match. Return the raw stored hash from the database.

### 12.3. Using BCryptPasswordEncoder on One Side and DelegatingPasswordEncoder on the Other

Plain BCrypt normally outputs `$2a$...` without a prefix; default delegating expects `{id}`. Choose a consistent encode/decode configuration, or migrate formats properly. Do not blindly prepend `{bcrypt}` to unverified values.

### 12.4. Picking Servlet APIs by Mistake

`DaoAuthenticationProvider`, `UserDetailsService`, `HttpSecurity`, and `SecurityFilterChain` belong to the Servlet stack. For WebFlux, use `UserDetailsRepositoryReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ServerHttpSecurity`, and `SecurityWebFilterChain`. Do not expect `@EnableWebSecurity` to set up the right reactive filters for your project.

### 12.5. Blocking the Event Loop with BCrypt/SQL

Calling blocking JDBC directly inside a controller or during assembly stalls WebFlux even if the method returns `Mono`. For databases, use R2DBC or isolate blocking on an appropriate scheduler. For password hashing, rely on the manager's scheduler/measured configuration rather than creating a new executor per request.

### 12.6. Setting Default permitAll While Debugging Login

When seeing 401, many developers change to `anyExchange().permitAll()` and think they "fixed" authentication. That leaves endpoints wide open. Inspect the Basic header, user store, password hash id, and encoder first, then review authorization. Never fix a policy by removing security.

### 12.7. Authorizing Based on Username in the URL

`/api/users/alice` is not automatically safe for user Alice if the endpoint only uses `authenticated()`; you must compare the resource owner against `Authentication` or enforce permissions in the service layer. Password managers solve **identity authentication**, not per-record ownership.

### 12.8. Holding Authentication in a Singleton or ThreadLocal

One successful login is not a reason to store `Authentication` in a `static currentUser` field or global cache. Reactive requests interleave, and context lives in the subscription; use `ReactiveSecurityContextHolder`, never leftover state from a previous request. Passwords/hashes must not sit in shared mutable state.

## 13. Applying to Production Environments

**Account management:** Username uniqueness and normalization must be clearly defined; never arbitrarily lowercase or Unicode-normalize accounts after they have already been created. Enforce strong passwords and handle resets/email verification/password changes per policy. Store hashes intact (do not truncate database columns due to prefixes or algorithm length), and never log secrets.

**Protecting the login endpoint:** HTTPS, multi-dimensional rate limiting (IP/account/risk), credential-stuffing monitoring, appropriate conditional lockouts/delays, and MFA when needed. Slow hashing is a defense layer after a database breach, not a substitute for online attack protection.

**User permissions and status:** Obtain authorities from trusted sources, accounting for permission changes, account lock/disable states, and per-resource data rules. Never put raw passwords or full `UserDetails` objects in JSON responses.

**Performance:** Benchmark the encoder against actual CPU/cost targets. Never hash in a loop or recreate encoders repeatedly to "try" each login. Separate user lookup (I/O) from password matching (CPU); monitor latency, queues, and login load, and enforce concurrency controls.

**Extensibility:** With multiple `SecurityWebFilterChain`s, the manager must be wired into the exact chain handling the request; two chains with different authentication mechanisms may need different managers. With OAuth2/JWT, bearer tokens are not verified with `PasswordEncoder`, and username/password managers should not be misapplied to resource servers.

**Hash migration:** Use algorithm ids and the upgrade service, with a plan for legacy/noop entries and reset policies. Never reverse hashes and never automatically fall back to plaintext comparison on id errors.

**Testing:** Beyond valid/invalid login tests, test locked/disabled users, missing permissions, prefixless hash values, password changes, hash upgrades, and latency under realistic load. All tests must go through the security filters rather than calling controllers directly and assuming login is secure.

## 14. Self-Assessment Questions

**Question 1.** Calling `encode` twice on the same raw password produces two different strings. Is this a bug?  
**No.** With BCrypt's random salt, this is expected behavior; use `matches(raw, storedHash)`.

**Question 2.** Should `ReactiveUserDetailsService.findByUsername` return the raw password or the hash?  
**The stored hash** in `UserDetails.getPassword()`. The manager uses `PasswordEncoder` to compare it with the raw credential from the current login attempt.

**Question 3.** Why does a user who enters the right password receive 403 at `/api/admin`?  
Authentication succeeded, but the account lacks `ROLE_ADMIN`; this is **authorization**, not an encoder error.

**Question 4.** A BCrypt hash from another library has no `{bcrypt}` prefix. Can the default `DelegatingPasswordEncoder` always read it?  
**Not guaranteed.** It requires a supported id; you must choose/migrate to a consistent configuration rather than enabling `noop`.

**Question 5.** Can `Mono.just(jdbcRepository.findByUsername(...))` serve as a reactive source?  
**Incorrect.** The JDBC call executes before the `Mono` is created and can block the thread; use R2DBC or proper blocking isolation.

**Question 6.** Does simply defining a `PasswordEncoder` bean automatically upgrade every hash in the database?  
**No.** You need a configured `ReactiveUserDetailsPasswordService`/logic to persist the new hash, upgrade criteria, and data-integrity tests.

**Question 7.** What is the main difference between `UserDetailsRepositoryReactiveAuthenticationManager` and `DaoAuthenticationProvider`?  
Both handle username/password authentication, but the manager discussed here belongs to **reactive/WebFlux** and uses `ReactiveUserDetailsService`, whereas the provider is a **Servlet** component typically used with synchronous `UserDetailsService` and `AuthenticationManager`.

**Question 8.** If a client sends an `X-Role: ADMIN` header with Alice's correct password, does her role automatically change to ADMIN?  
**No.** Authorities come from `UserDetails`/a trusted system. Self-asserted headers are not a source of permissions.

**Question 9.** Do you need to call `subscribe()` in a controller to trigger authentication?  
**No.** Spring Security/WebFlux orchestrates the request pipeline and subscription. Calling `subscribe()` manually can detach work from the lifecycle and context.

### Official Documentation

- Spring Security, `UserDetailsRepositoryReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security, `AbstractUserDetailsReactiveAuthenticationManager` (encoder, scheduler, password upgrade): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security, *Password Storage / DelegatingPasswordEncoder*: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security, *Spring Security Crypto Module*: https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html
- Spring Security, `ServerHttpSecurity` API (ReactiveAuthenticationManager): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Key takeaway:** `ReactiveUserDetailsService` **looks up the right user and hash**, `PasswordEncoder` **performs one-way password encoding and matching**, `UserDetailsRepositoryReactiveAuthenticationManager` **combines both to authenticate**, and `SecurityWebFilterChain` **wires authentication into HTTP and enforces permissions**. Configure all four consistently, store properly formatted hashes, and test both success and rejection paths to avoid confusion or accidental privilege escalation.