# ReactiveUserDetailsService and MapReactiveUserDetailsService in Spring Security WebFlux

> **Goal:** Understand the role of **ReactiveUserDetailsService** when authenticating username/password in **reactive** Spring Security, know how to use **MapReactiveUserDetailsService** to build a runnable/testable WebFlux application, and know when to replace an in-memory user store with **truly non-blocking** queries. Focus: Java 17+, Spring Boot 3.x, Spring Security 6.x, and Reactor.

## 1. Why Does WebFlux Authentication Need a Different UserDetailsService?

In Spring MVC/Servlet, many username/password login mechanisms use the synchronous **UserDetailsService**:

~~~java
// Servlet contract, not WebFlux reactive:
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

This call immediately returns **UserDetails** or throws an exception. If the database query blocks the thread, a request can hold that thread until I/O finishes.

In Spring WebFlux, the authentication pipeline works with Project Reactor **Publishers**. The corresponding interface is **ReactiveUserDetailsService**:

~~~java
package org.springframework.security.core.userdetails;

import reactor.core.publisher.Mono;

public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
~~~

**Mono<UserDetails>** represents at most one asynchronously emitted user; it does not mean the password has been verified. This is the contract for **loading user data**, not the entire login process. **ReactiveAuthenticationManager** is responsible for checking credentials and creating an **Authentication** upon success.

**MapReactiveUserDetailsService** is a built-in implementation of ReactiveUserDetailsService that holds users in an in-memory Map and returns **Mono<UserDetails>**. It is convenient for examples, tests, proofs of concept, and very small services with fixed users, but it does not replace a real user management system.

### Comparing Servlet and Reactive

| Aspect | Spring Security Servlet | Spring Security WebFlux |
| --- | --- | --- |
| User lookup component | **UserDetailsService** | **ReactiveUserDetailsService** |
| Method | **loadUserByUsername(String)** | **findByUsername(String)** |
| Return value | Synchronous **UserDetails** | **Mono<UserDetails>** |
| Sample in-memory user store | **InMemoryUserDetailsManager** | **MapReactiveUserDetailsService** |
| Common username/password authenticator | **DaoAuthenticationProvider** in AuthenticationManager/ProviderManager | **UserDetailsRepositoryReactiveAuthenticationManager** in ReactiveAuthenticationManager |
| HTTP security chain | **SecurityFilterChain**, HttpSecurity, Servlet Filter | **SecurityWebFilterChain**, ServerHttpSecurity, WebFilter |
| Security context | SecurityContextHolder/ThreadLocal per Servlet model | **ReactiveSecurityContextHolder** in Reactor Context |
| Web testing | MockMvc | **WebTestClient** |
| Appropriate data access | JDBC/JPA or synchronous services | R2DBC, reactive drivers, or non-blocking clients |
| Common mistake | Threads blocked by slow DB | Calling **block()**, JDBC/JPA on the Netty event-loop |

**Note:** having the word *Reactive* in an interface name does not make a JDBC driver non-blocking. You must design an appropriate I/O chain. Conversely, MapReactiveUserDetailsService is a very fast in-memory lookup; there is no network I/O to wait on.

## 2. The ReactiveUserDetailsService Contract

Just one method:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

The input is the username extracted by the filter/manager from the login request. The output is a publisher. In a proper design:

- **Mono.just(user)** or equivalent publisher: a UserDetails record exists; the rest of the pipeline checks account status, password, and authorities.
- **Mono.empty()**: user not found. The manager turns the absence of a user into an appropriate authentication failure; never emit a fake UserDetails with granted authorities.
- **Mono.error(exception)**: real errors such as DB timeout, connection loss, or data processing errors. Must fail closed; do not turn an error into a user with a default password.
- **Never return Java null** instead of a Mono. Null does not represent “no user” in Reactor.
- **Do not perform heavy/thread-blocking work** directly inside the method before returning the publisher.

**UserDetails** describes user data used for authentication: username, password hash, list of **GrantedAuthority**, and enabled, accountNonLocked, accountNonExpired, and credentialsNonExpired flags. It is not an HTTP response object and generally **should not be serialized to the client**, especially the password hash.

A simple example showing the meaning:

~~~java
ReactiveUserDetailsService users = username -> {
    if ("alice".equals(username)) {
        UserDetails user = User.withUsername("alice")
                .password("{noop}training-only")
                .roles("READER")
                .build();
        return Mono.just(user);
    }
    return Mono.empty();
};
~~~

This is a **contract-illustration snippet**, not a production configuration: **{noop}** does not hash passwords and is suitable only for explaining semantics; the runnable example below uses **BCryptPasswordEncoder**. **UserDetails**/**User** live in package **org.springframework.security.core.userdetails** and Mono lives in **reactor.core.publisher**.

### UserDetailsService Does Not Check Passwords Itself

Visualize a request:

~~~text
GET /api/me
Authorization: Basic <base64(username:password)>
                  |
                  v
       SecurityWebFilterChain
                  |
                  v
       AuthenticationWebFilter
             (HTTP Basic)
                  |
                  v
       ReactiveAuthenticationManager
                  |
                  v
UserDetailsRepositoryReactiveAuthenticationManager
                  |
                  +--> ReactiveUserDetailsService.findByUsername("alice")
                  |       |
                  |       +--> Mono<UserDetails>
                  |
                  +--> PasswordEncoder.matches(raw, storedHash)
                  +--> check account flags
                  +--> build trusted Authentication
                  |
                  v
      ReactiveSecurityContextHolder / Reactor Context
                  |
                  v
          AuthorizationWebFilter
                  |
                  v
              Controller
~~~

**Never set isAuthenticated=true merely because a user was found.** If the client supplies a username and the manager has not verified the password, identity has not been proved. Authorities must come from a server-managed source, not from a **role** field in the request.

## 3. What Is MapReactiveUserDetailsService and What Can It Do?

Spring Security provides:

~~~java
package org.springframework.security.core.userdetails;

public class MapReactiveUserDetailsService
        implements ReactiveUserDetailsService,
                   ReactiveUserDetailsPasswordService {
    // Spring Security library implementation.
}
~~~

Useful constructors:

~~~java
new MapReactiveUserDetailsService(user1, user2);
new MapReactiveUserDetailsService(collectionOfUsers);
new MapReactiveUserDetailsService(mapOfUsernameToUserDetails);
~~~

A Map can be used in examples, though for the constructor taking a Map, the Javadoc requires a **non-blocking Map**. Use standard in-memory structures or an appropriate concurrent map—do not pass an adapter whose **get** hits a blocking database each time.

| Expectation | Behavior / Notes |
| --- | --- |
| Finding a user loaded into the Map | Returns a Mono emitting the matching UserDetails |
| Finding a nonexistent username | Completes with no items |
| Creating roles | Using **User.withUsername(...).roles("READER")** produces **ROLE_READER** |
| Using exact authorities | Use **authorities("SCOPE_read")**; do not assume every string is a role |
| Password | Store encoded hash produced by PasswordEncoder; raw passwords should not be stored in the Map |
| Mutating users | The Map is not a management database and does not sync across nodes/restarts |
| Password change | The class implements **ReactiveUserDetailsPasswordService.updatePassword(...)**, though this is not a full password-change workflow |
| Restarts | Data is recreated from config/beans; runtime changes are not automatically persisted |
| Multiple distributed instances | Each instance has its own Map; must share configuration or a common data source |

**ReactiveUserDetailsPasswordService** is separate from ReactiveUserDetailsService. It describes **updating the encoded password hash** in the user store, usable for hash upgrades on login. It does not include old-password verification, user confirmation, auditing, MFA, or email notification. If you implement a password change feature, design it separately.

### When to Use MapReactiveUserDetailsService?

Suitable for:

- Spring Security WebFlux learning examples needing real HTTP Basic/form login.
- Automated tests with a few static users and roles.
- PoCs or very small internal apps whose user list is managed via config/secret manager (still requiring rotation and deployment handling).
- Directly comparing the **findByUsername** contract with Servlet's UserDetailsService.

Unsuitable when you need API user registration/password changes, lockout, tenant management, per-device revocation, long-term auditing, millions of accounts, or a database as the source of truth. In those cases, create a **custom ReactiveUserDetailsService** querying via a reactive repository and enforcing user state.

## 4. Runnable Example: Spring Boot WebFlux + MapReactiveUserDetailsService

We build a Java 17+, Spring Boot 3.x, and Spring Security 6.x app with **two accounts**: **alice** has ROLE_READER, and **admin** has ROLE_READER + ROLE_ADMIN. Clients log in with HTTP Basic and test public/reader/admin endpoints.

### 4.1. Choosing the Right Dependencies

Create a Maven project with **Spring Initializr**: Java 17+, Spring Boot 3.x, and dependencies **Spring Reactive Web (spring-boot-starter-webflux)**, **Spring Security (spring-boot-starter-security)**, and **Spring Boot Starter Test**. For WebTestClient you need the test libraries provided by starter-test/webflux; if your project customizes dependencies, ensure **spring-test**, **reactor-test**, and the proper reactive HTTP test client are included.

The dependencies section in **pom.xml** of a project with the Spring Boot parent/BOM:

~~~xml
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
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is an **excerpt**, not the full pom.xml. Use Spring Boot dependency management to keep versions compatible. **Do not** add **spring-boot-starter-web** to this project just to get controllers: when both Spring MVC and WebFlux starters are present, Spring Boot may auto-select a Servlet application, preventing the demo from illustrating the reactive pipeline. If a real project intentionally runs a hybrid setup, configure **spring.main.web-application-type** explicitly and understand why.

Place the Java files under **src/main/java/com/example/reactiveusers/**. The Spring Boot main class also lives in this package so component scanning covers the remaining classes.

### 4.2. Startup Class

File **ReactiveUsersApplication.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUsersApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUsersApplication.class, args);
    }
}
~~~

### 4.3. Reactive Spring Security Configuration

File **SecurityConfig.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder encoder,
            @Value("${demo.alice.password}") String alicePassword,
            @Value("${demo.admin.password}") String adminPassword) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode(alicePassword))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode(adminPassword))
                .roles("READER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

**Each part has its own role:**

1. **@EnableWebFluxSecurity** activates WebFlux security configuration. The bean produced is **SecurityWebFilterChain**, not Servlet's **SecurityFilterChain**.
2. **PasswordEncoder** encodes raw passwords into BCrypt hashes when building UserDetails. **roles("READER")** generates **ROLE_READER**, and similarly ADMIN → ROLE_ADMIN.
3. **MapReactiveUserDetailsService** holds the two server-managed users. Passwords come from environment variables for the demo; in production, accounts/credentials require protected storage and rotation processes.
4. **UserDetailsRepositoryReactiveAuthenticationManager** takes ReactiveUserDetailsService and PasswordEncoder; it handles username/password credentials. **findByUsername** does not verify passwords by itself.
5. **http.authenticationManager(manager)** uses the explicitly configured manager instead of relying on guessing which bean gets auto-configured.
6. **authorizeExchange** sets rules for reactive requests. Endpoint **/api/admin** requires ROLE_ADMIN; all remaining requests must be authenticated except **/public**.
7. **httpBasic(...)** reads username/password from the HTTP Authorization header. **formLogin(...disable())** disables form login so API clients do not get unexpected HTML redirects; there is no custom REST token-issuing endpoint here.
8. **CSRF is not disabled** because the demo uses GET only. For POST/PUT/PATCH/DELETE using cookies/sessions or browser HTTP Basic, evaluate and configure CSRF according to the client model; never disable it just to make tests pass.

**Key learning point:** MapReactiveUserDetailsService and UserDetailsRepositoryReactiveAuthenticationManager are purely **reactive** components. Never create a Servlet **DaoAuthenticationProvider** for this SecurityWebFilterChain.

### 4.4. Controller Reading Authentication from Reactor Context

File **ApiController.java**:

~~~java
package com.example.reactiveusers;

import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        "me " + context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin");
    }
}
~~~

**ReactiveSecurityContextHolder** uses the **Reactor Context** to access the verified SecurityContext. Unlike ThreadLocal **SecurityContextHolder** in many Servlet examples, the Reactor Context travels with the publisher chain and does not depend on the request staying on one fixed thread.

Never stash Authentication into an arbitrary **static ThreadLocal** during reactive processing. When the pipeline switches schedulers/threads, ThreadLocal data may not follow the request. To access the context, use reactive security utilities or Spring WebFlux-supported handler arguments.

### 4.5. Configuring Demo Passwords

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.alice.password=${DEMO_ALICE_PASSWORD}
demo.admin.password=${DEMO_ADMIN_PASSWORD}
~~~

On Linux/macOS:

~~~bash
export DEMO_ALICE_PASSWORD=alice-demo-pass
export DEMO_ADMIN_PASSWORD=admin-demo-pass
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:DEMO_ALICE_PASSWORD = "alice-demo-pass"
$env:DEMO_ADMIN_PASSWORD = "admin-demo-pass"
.\mvnw.cmd spring-boot:run
~~~

These passwords are **localhost practice data only**. Never use HTTP Basic over the Internet without TLS: Base64 does not protect passwords from observers. Production must use HTTPS, protect secrets, and apply retry limits/rate limiting.

### 4.6. Sending Requests with curl

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-demo-pass http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:alice-demo-pass http://localhost:8080/api/admin
curl -i -u admin:admin-demo-pass http://localhost:8080/api/admin
~~~

Expectations:

| Request | HTTP status | Body / meaning |
| --- | --- | --- |
| GET /public | **200** | **public** |
| GET /api/me without credentials | **401** | Authentication required; may include WWW-Authenticate |
| Alice + valid password → /api/me | **200** | **me alice** |
| Alice + wrong password → /api/me | **401** | Password rejected |
| Alice + valid password → /api/admin | **403** | Authenticated, but lacks ROLE_ADMIN |
| Admin + valid password → /api/admin | **200** | **admin** |

Do not assume a request can log in merely by sending a username and role. Authorities reside in server-side UserDetails and PasswordEncoder must verify the password. If a browser/client caches an old Authorization header, inspect the actual headers when testing uncredentialed scenarios.

### 4.7. Sample Directory Tree

~~~text
reactive-users-demo/
  pom.xml
  src/
    main/
      java/com/example/reactiveusers/
        ReactiveUsersApplication.java
        SecurityConfig.java
        ApiController.java
      resources/
        application.properties
    test/
      java/com/example/reactiveusers/
        MapReactiveUsersTest.java
        WebFluxAuthenticationTest.java
~~~

Java files use **package com.example.reactiveusers**. Do not put multiple public classes in one file. Maven wrapper **mvnw/mvnw.cmd** is typically generated by Spring Initializr.

## 5. Testing ReactiveUserDetailsService and WebFlux Authentication

We need two levels of testing: **direct Mono<UserDetails> lookup** and **HTTP requests through the WebFilter chain**. If you only mock the SecurityContext, tests may skip actual password matching.

### 5.1. Unit/Context Test with StepVerifier

File **src/test/java/com/example/reactiveusers/MapReactiveUsersTest.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
        "demo.alice.password=alice-test-pass",
        "demo.admin.password=admin-test-pass"
})
class MapReactiveUsersTest {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Test
    void knownUserHasServerControlledDetails() {
        StepVerifier.create(users.findByUsername("alice"))
                .assertNext(user -> {
                    assertEquals("alice", user.getUsername());
                    assertTrue(user.isEnabled());
                    assertTrue(encoder.matches(
                            "alice-test-pass", user.getPassword()));
                    assertTrue(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("ROLE_READER")));
                    assertFalse(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("ROLE_ADMIN")));
                })
                .verifyComplete();
    }

    @Test
    void missingUserYieldsNoDetails() {
        StepVerifier.create(users.findByUsername("nobody"))
                .verifyComplete();
    }
}
~~~

**StepVerifier** subscribes and checks the Mono's emitted signals and completion/error. **Never** call **users.findByUsername("alice")** and immediately read data as if Mono executed synchronously; publishers can be lazy and run only upon subscription.

The test does not compare BCrypt hashes with string equality because BCrypt uses a salt and encoding the same raw password twice does not necessarily produce the same string. Verify with **PasswordEncoder.matches(raw, encoded)**.

### 5.2. Integration Test with WebTestClient

File **src/test/java/com/example/reactiveusers/WebFluxAuthenticationTest.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "demo.alice.password=alice-test-pass",
                "demo.admin.password=admin-test-pass"
        })
@AutoConfigureWebTestClient
class WebFluxAuthenticationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteNeedsNoAuthentication() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validPasswordAuthenticatesAlice() {
        client.get().uri("/api/me")
                .headers(h ->
                        h.setBasicAuth("alice", "alice-test-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("me alice");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIsRejected() {
        client.get().uri("/api/me")
                .headers(h ->
                        h.setBasicAuth("unknown", "alice-test-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/api/admin")
                .headers(h ->
                        h.setBasicAuth("alice", "alice-test-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin")
                .headers(h ->
                        h.setBasicAuth("admin", "admin-test-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin");
    }
}
~~~

This tests HTTP requests against an embedded server on a random port (**RANDOM_PORT**) with **WebTestClient**, traversing the application's real WebFlux/Spring Security chain. If a test using wrong credentials still gets 200, inspect manager wiring, encoder, matchers, and whether the endpoint was accidentally permitted with permitAll.

Run:

~~~bash
./mvnw test
./mvnw -Dtest=WebFluxAuthenticationTest test
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=WebFluxAuthenticationTest' test
~~~

If the tests fail to run, check JDK 17+, the Maven wrapper, Boot 3.x, the WebFlux starter, and the test password properties first. These commands are practical instructions, **not a report claiming the test suite was executed**.

### 5.3. Limitations of Testing with a Mock Security Context

Spring Security Test lets you attach a mock user to the reactive test client or use **@WithMockUser**. That is useful for testing **authorization** or controller logic, but it **does not test the data** in MapReactiveUserDetailsService and **does not test passwords**. To verify the login path, send real Basic credentials as in the integration test above.

Unit tests calling **ReactiveAuthenticationManager.authenticate(...)** directly are also valuable: they check BadCredentialsException, disabled accounts, and returned authorities; however, they do not replace HTTP WebFilter testing.

## 6. From MapReactiveUserDetailsService to a Real Reactive User Source

When users live in PostgreSQL, MySQL, MongoDB, or an internal service, **do not** maintain an unbounded Map or use JDBC that blocks the event-loop. Design a **ReactiveUserDetailsService** backed by a non-blocking repository.

### 6.1. Decoupling the Record Contract from Spring Security

The next example is an **alternative integration pattern**—do not register it alongside MapReactiveUserDetailsService from Section 4, or you will have **two beans** of ReactiveUserDetailsService. This pattern assumes you have a reactive repository storing account data from a trusted source. It separates DB concerns and maps records into UserDetails:

File **AccountRecord.java**:

~~~java
package com.example.reactiveusers;

import java.util.List;

public record AccountRecord(
        String username,
        String passwordHash,
        boolean active,
        List<String> grantedAuthorities) {
}
~~~

File **AccountStore.java**:

~~~java
package com.example.reactiveusers;

import reactor.core.publisher.Mono;

public interface AccountStore {
    Mono<AccountRecord> findByUsername(String username);
}
~~~

**AccountStore** is an application-defined contract, not an auto-generated Spring repository. An **R2DBC**, **ReactiveMongoRepository**, or non-blocking **WebClient** adapter must provide the concrete implementation.

File **DatabaseReactiveUserDetailsService.java**:

~~~java
package com.example.reactiveusers;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import reactor.core.publisher.Mono;

public final class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountStore accounts;

    public DatabaseReactiveUserDetailsService(AccountStore accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        if (username == null || username.isBlank()
                || username.length() > 128) {
            return Mono.empty();
        }

        return accounts.findByUsername(username)
                .map(account -> User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities(
                                account.grantedAuthorities().toArray(
                                        String[]::new))
                        .disabled(!account.active())
                        .build());
    }
}
~~~

**Explanation:**

- The service **does not execute DB queries directly**. It asks AccountStore for a Mono, then uses **map** to convert to UserDetails.
- **account.passwordHash()** must be a server-stored password hash compatible with the authentication manager's PasswordEncoder. Never store raw passwords in SQL and compare strings inside the service.
- **grantedAuthorities** must come from an authoritative source. For instance, the data may contain **ROLE_USER**, **ROLE_ADMIN**, **SCOPE_read** by design; never take roles sent by the client in body/headers.
- **disabled(!account.active())** lets the manager know the account is not allowed to log in. A real application may also have lock/expired flags, tenancy, MFA, ban status, and custom checks.
- When AccountStore returns Mono.empty(), the service also completes empty. When the DB emits Mono.error, the error propagates via Reactor rather than turning into a default UserDetails.
- Bounding username length before lookup helps reject unreasonable inputs; it must align with the app's username policy. If usernames need normalization, apply consistent normalization to avoid unexpected identity shifts due to casing.

In a real project, register **one** bean:

~~~java
@Bean
ReactiveUserDetailsService userDetailsService(AccountStore accountStore) {
    return new DatabaseReactiveUserDetailsService(accountStore);
}
~~~

This is a **supplementary configuration snippet**, not standalone. Update the manager bean in Section 4 to accept **ReactiveUserDetailsService** instead of **MapReactiveUserDetailsService**, or use a separate config with only the DB implementation. Keeping both service beans without `@Qualifier` can cause ambiguous dependency injection.

### 6.2. Connecting to R2DBC — Architecture Map

~~~text
WebFlux Basic Authentication
        |
        v
UserDetailsRepositoryReactiveAuthenticationManager
        |
        v
DatabaseReactiveUserDetailsService
        |
        v
AccountStore (reactive adapter)
        |
        +--> DatabaseClient / R2dbcEntityTemplate / R2dbcRepository
        |
        v
R2DBC Driver (non-blocking)
        |
        v
User table: username UNIQUE, password_hash, active, authorities
~~~

A Spring Data R2DBC repository example when using a dedicated entity:

~~~java
// Snippet for a module with Spring Data R2DBC:
// AccountEntity must have @Table/@Id mapping matching the DB schema.
// This is not a complete standalone runnable file/entity.
public interface AccountRepository
        extends ReactiveCrudRepository<AccountEntity, Long> {

    Mono<AccountEntity> findByUsername(String username);
}
~~~

You need the **spring-boot-starter-data-r2dbc** dependency, the appropriate R2DBC driver, schema, and migrations. **ReactiveCrudRepository** belongs to Spring Data, not Spring Security's ReactiveUserDetailsService; the two serve different purposes.

If roles are stored across multiple tables, design queries so they do not trigger **N+1 blocking calls**, have proper indexes, and map authorities reliably. When an account + authorities query is needed, consider a join/aggregate or a well-defined reactive pipeline.

### 6.3. Do Not Call block() in the HTTP Pipeline

**Wrong:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    AccountRecord record = jdbcRepository.findByUsername(username);
    // This JDBC call blocks the thread, even when wrapped with Mono.just.
    return Mono.just(mapToUserDetails(record));
}
~~~

**Also wrong:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return Mono.just(
            reactiveRepository.findByUsername(username).block());
}
~~~

Calling **block()** waits for the result by blocking the thread, breaking the reactive model's benefits and potentially being rejected by Reactor on non-blocking schedulers. Wrapping with **Mono.just** after a blocking operation changes nothing: the I/O already happened before the publisher was returned.

**Right with a reactive repo:**

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return reactiveRepository.findByUsername(username)
            .map(this::mapToUserDetails);
}
~~~

Here **reactiveRepository** and **mapToUserDetails** are components you supply; the snippet explains the pipeline and is not a complete class. Do not add arbitrary **subscribe()** calls inside the service: Spring Security is the subscriber and manages lifecycle. Subscribing yourself easily breaks error handling, context, and timeouts, creating uncontrolled fire-and-forget work.

### 6.4. If You Must Integrate Blocking JDBC/LDAP

During migration, you can isolate blocking calls away from the event-loop using **Schedulers.boundedElastic()**:

~~~java
Mono<UserDetails> lookup =
        Mono.fromCallable(() -> blockingUserDetailsService
                .loadUserByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
~~~

This is a **temporary boundary pattern** given an existing **blockingUserDetailsService** and Mono/Schedulers imports. It does not turn JDBC into a true reactive driver, nor does it guarantee infinite scaling: boundedElastic has a bounded pool and queue. You need timeouts, concurrency bounds, connection pooling, monitoring, and a plan to migrate to a non-blocking driver under heavy load. Never call **block()** back on the request thread.

If using LDAP/AD or another identity provider, consider official providers/adapters that support the protocol properly. Never assume a **Mono** API automatically makes LDAP authentication non-blocking end to end.

## 7. PasswordEncoder in Reactive Authentication

**UserDetailsService only loads the hash; the manager uses PasswordEncoder to compare.** In real applications:

- Use BCrypt, Argon2id, PBKDF2, or an encoder matching your security policy and runtime environment.
- Never store plaintext passwords in UserDetails or the database.
- Never use **NoOpPasswordEncoder** in production; **User.withDefaultPasswordEncoder()** shown in some Spring Security tutorials is a quick learning shortcut, not a production deployment choice.
- Match the encoder used at hash creation and at verification. With **DelegatingPasswordEncoder**, hashes carry a prefix like **{bcrypt}**; when using **BCryptPasswordEncoder** directly, BCrypt hashes do not require a Delegating prefix.
- Never rehash the raw password with a new salt and compare two hashes using String.equals: BCrypt is salted. Use **encoder.matches(raw, storedHash)**.
- If supporting password hash upgrades, use a mechanism compatible with **ReactiveUserDetailsPasswordService** and update the DB safely without exposing old passwords in logs.

To test the encoder directly:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode("alice-demo-pass");
boolean valid = encoder.matches("alice-demo-pass", hash);
boolean invalid = encoder.matches("wrong", hash);

System.out.println(valid);
System.out.println(invalid);
~~~

When placed inside a method/class with appropriate imports, the **exact stdout** for those two lines is:

~~~text
true
false
~~~

Never print real hashes or passwords to application logs.

**BCrypt cost is CPU-bound.** Even when user lookup is non-blocking, password matching consumes CPU and requires bounding concurrent requests. **AbstractUserDetailsReactiveAuthenticationManager** includes scheduler support for password verification; do not block the event-loop or create unbounded schedulers yourself. Apply rate limiting, latency observability, and credential-stuffing defenses.

## 8. Failure Modes, Security, and Reliability

### 8.1. User Not Found

**findByUsername** may return Mono.empty(). In a typical username/password authentication flow, the manager rejects the attempt—for example, HTTP Basic returns **401**. Do not publicly differentiate “username does not exist” from “wrong password” if that enables account enumeration.

Inspect **timing differences**: looking up a nonexistent user can be faster than running BCrypt against an existing user. Consider mitigations appropriate to load/risk, combined with rate limiting and monitoring.

### 8.2. Locked, Disabled, or Expired Accounts

**UserDetails** provides accountNonExpired, accountNonLocked, credentialsNonExpired, and enabled flags. When implementing a custom service, map all statuses faithfully from the trusted server source. Never ignore status flags merely because the password matches. Enforce policies such as revocation and tenant suspension, and never fabricate authorities when the DB source is down.

### 8.3. Data Source Failures

If a remote DB times out, never convert the failure into a fresh UserDetails or return a successful Authentication. Let **Mono.error** propagate to the proper handler, emit telemetry distinguishing “invalid credentials” from “identity service unavailable”, and choose 401/503 responses per the API contract. Avoid logging raw passwords and tokens. Never log SQL strings containing credentials.

Be careful with:

~~~java
return accounts.findByUsername(username)
        .onErrorResume(error -> Mono.empty());
~~~

This pattern **masks system errors as user-not-found**, hurting operations and potentially triggering false lockouts for users. Even though it does not automatically grant access, it blurs the line between identity source outages and bad credentials; use it only under a thoroughly analyzed error policy.

### 8.4. Where Do Authorities Come From?

When a client sends **role=ADMIN** in JSON or a header, that is not proof for granting privileges. **UserDetails.getAuthorities()** must be built from an authoritative source. With MapReactiveUserDetailsService, data is initialized in a server-side bean. With a DB-backed service, read only roles/scopes bound to the verified subject.

Distinguish: **roles("ADMIN")** produces **ROLE_ADMIN**; **authorities("SCOPE_read")** keeps the exact string. Verify **hasRole("ADMIN")** against actual authority prefixes to avoid 403 errors from mismatched configuration.

### 8.5. Demo Passwords from Environment Variables Still Need Management

Environment variables are convenient for practice, but production should use a secret manager or credential management system. Do not log environment variables, do not hardcode demo passwords into release artifacts, and do not leave H2/test users enabled as default production accounts. Accounts in a Map are recreated on each service restart; generating a new BCrypt hash on each startup is normal BCrypt behavior, not a reason to skip password encoding.

## 9. Distinguishing from Other Reactive Authentication Mechanisms

| Product requirement | Use ReactiveUserDetailsService? | Appropriate components |
| --- | --- | --- |
| HTTP Basic username/password with DB users | Usually **yes** | UserDetailsRepositoryReactiveAuthenticationManager + custom ReactiveUserDetailsService |
| Reactive form login with username/password | Usually **yes** | SecurityWebFilterChain formLogin + reactive manager/service |
| Static users in tests | **Yes** | MapReactiveUserDetailsService |
| JWT Bearer tokens from an IdP | **Not required** | oauth2ResourceServer().jwt(), ReactiveJwtDecoder, JWT authority converter |
| Opaque bearer tokens | **Not required** | ReactiveOpaqueTokenIntrospector |
| OAuth2/OIDC login via external provider | **Not necessarily** | OAuth2Login authentication components, client registration |
| Custom API key | **Not automatically** | Custom AuthenticationWebFilter + ReactiveAuthenticationManager or resolver |
| Storing user password credentials | Not directly | Database account repository + PasswordEncoder + password-change controls |
| Method-level authorization | Can be combined | @EnableReactiveMethodSecurity + @PreAuthorize, Reactor Context |

**ReactiveUserDetailsService is not a universal API for verifying every token type.** Resource servers using JWT/opaque tokens typically do not look up users by username/password on every request; they validate tokens via issuer/decoder/introspection. Never force JWTs into MapReactiveUserDetailsService or construct users from unverified JWT claims.

## 10. Common Implementation Mistakes

**Mistake 1 — Using Servlet UserDetailsService in WebFlux and expecting non-blocking behavior.** The Servlet interface returns UserDetails directly. **Fix:** use ReactiveUserDetailsService and a proper driver/adapter.

**Mistake 2 — Creating only MapReactiveUserDetailsService without configuring the filter or manager properly.** The Map holds user data but does not expose login endpoints by itself. **Fix:** configure HTTP Basic/form login in SecurityWebFilterChain and the matching ReactiveAuthenticationManager.

**Mistake 3 — Assuming findByUsername checks passwords.** It only looks up the user. **Fix:** let the manager + PasswordEncoder perform verification and account flag checks.

**Mistake 4 — Returning null when a user does not exist.** Reactor does not use null as a publisher result. **Fix:** use Mono.empty() or the appropriate error contract.

**Mistake 5 — Putting block() inside findByUsername.** The event-loop gets blocked. **Fix:** use reactive data access or clearly isolate blocking adapters.

**Mistake 6 — Using Mono.just(blockingDatabaseCall()).** The blocking call executes before the Mono is even created. **Fix:** eliminate blocking I/O; during migration use Mono.fromCallable + boundedElastic with concurrency limits.

**Mistake 7 — Using {noop} passwords in real environments.** Raw passwords are not hashed. **Fix:** use BCrypt/Argon2id/DelegatingPasswordEncoder per policy.

**Mistake 8 — Assuming roles("ADMIN") equals authorities("ADMIN").** In fact **roles** adds the ROLE_ prefix. **Fix:** align GrantedAuthority configuration with hasRole/hasAuthority.

**Mistake 9 — Serializing the entire UserDetails as JSON.** UserDetails often contains the password hash, account metadata, and authorities. **Fix:** expose a minimal DTO after authentication.

**Mistake 10 — Mixing starter-web and starter-webflux without checking application type.** The app may boot as MVC/Servlet instead of WebFlux, bypassing the reactive chain. **Fix:** pick the right starter and verify which stack the app runs on.

**Mistake 11 — Testing only with @WithMockUser.** Skips credential verification. **Fix:** send real Basic auth via WebTestClient and test 401/403/200.

**Mistake 12 — Relying on the Map as a production database.** User state is neither persistent nor cluster-synchronized. **Fix:** build a reactive repository with uniqueness, account flags, designed caching/TTL, and revocation.

## 11. Checklist for Moving a Reactive App to Production

- [ ] The application genuinely runs **Spring WebFlux** and **SecurityWebFilterChain**, not Servlet by accident.
- [ ] ReactiveUserDetailsService is a **single unambiguous implementation** used by the manager, with no bean ambiguity.
- [ ] findByUsername always returns **Mono<UserDetails>**, Mono.empty, or Mono.error; never null.
- [ ] Data access is truly non-blocking; no block()/JDBC/JPA directly on the event-loop.
- [ ] UserDetails holds encoded passwords and valid account flags, never raw secrets.
- [ ] PasswordEncoder matches existing hashes, with an upgrade/migration plan.
- [ ] Roles/authorities come from a trusted server source; request-supplied role data is never trusted.
- [ ] UserDetails containing password hashes is never exposed via controllers or logs.
- [ ] Retry limits/rate limiting, timeout telemetry, and protections against credential stuffing and user enumeration are in place.
- [ ] DB/identity source outage → fail closed, with no fallback creating automatic users.
- [ ] WebTestClient tests valid credentials, wrong credentials, missing credentials, locked/disabled accounts, and insufficient roles.
- [ ] StepVerifier tests Mono emitting a valid user, Mono.empty, and Mono.error in the service/adapter.
- [ ] Real HTTPS/TLS is used when transmitting Basic credentials; Base64 is not mistaken for encryption.
- [ ] When using OAuth2/JWT, choose dedicated reactive resource-server components instead of shoehorning into user lookup.
- [ ] Session/CSRF policies match browser/cookie usage; protections are never disabled without cause.
- [ ] In clusters, datasources and account states are consistent; Map-only is used only if its limits are acceptable.

## 12. Self-Check Questions

**1. What does ReactiveUserDetailsService return?** A **Mono<UserDetails>**. It does not return an authenticated Authentication and does not verify passwords itself.

**2. When should you use MapReactiveUserDetailsService?** When you need an in-memory user store for demos, tests, or explicitly managed static configs; it should not be the default for production user systems that mutate and require sync/persistence.

**3. If a username does not exist, can you return Mono.just(null)?** No. Reactor forbids null items; use Mono.empty() or the appropriate error contract.

**4. Why is Mono.just(jdbcRepository.findByUsername(name)) not reactive?** The JDBC call executes synchronously before the Mono is created; it still blocks the thread.

**5. If a user is found, but the password is wrong, can they log in?** No. The manager must run PasswordEncoder.matches, check account state, and emit a successful Authentication only when all checks pass.

**6. Why does /api/admin return 403 for alice even though /api/me returns 200?** Alice authenticated with a valid password, but she only has ROLE_READER and lacks ROLE_ADMIN.

**7. In WebFlux, how is SecurityContext accessed?** Via **ReactiveSecurityContextHolder/Reactor Context** or Spring Security's reactive utilities; do not assume a ThreadLocal stays accurate across schedulers.

**8. Can MapReactiveUserDetailsService handle JWT bearer tokens on its own?** No. JWTs require a token decoder/verifier and matching authentication manager/filter; username/password user lookup is a different mechanism.

## 13. Official Documentation

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): @EnableWebFluxSecurity, SecurityWebFilterChain, MapReactiveUserDetailsService, and DSL.
- [ReactiveUserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): findByUsername contract and Mono<UserDetails>.
- [MapReactiveUserDetailsService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructors taking Map/Collection/varargs, findByUsername, and updatePassword.
- [UserDetailsRepositoryReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): reactive password authentication manager.
- [AbstractUserDetailsReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html): PasswordEncoder, scheduler, account checks, and password upgrades.
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): @EnableReactiveMethodSecurity, Reactor Context, and MapReactiveUserDetailsService examples.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest(RANDOM_PORT), WebTestClient.
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): Mono.just, Mono.empty, Mono.error, map, and subscribeOn.
