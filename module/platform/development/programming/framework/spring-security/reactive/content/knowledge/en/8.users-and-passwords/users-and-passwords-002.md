# Creating In-Memory Users with MapReactiveUserDetailsService in Spring Security Reactive

## 1. Learning Objectives

In a Spring WebFlux application, the first task when learning authentication is creating a few accounts with usernames, passwords, and permissions, then letting Spring Security use them to authenticate requests. **MapReactiveUserDetailsService** helps do that without needing a database yet: it holds **UserDetails** in memory and looks up accounts by username via the **ReactiveUserDetailsService** contract.

After this lesson, you will:

1. Understand the relationship between UserDetails, ReactiveUserDetailsService, MapReactiveUserDetailsService, PasswordEncoder, ReactiveAuthenticationManager, and SecurityWebFilterChain.
2. Create users with usernames, hashed passwords, roles/authorities, and account status flags.
3. Declare MapReactiveUserDetailsService as a Spring bean for WebFlux.
4. Test lookups with StepVerifier and try real HTTP Basic calls with curl/WebTestClient.
5. Distinguish the three steps: **user lookup**, **password verification**, and **permission checking**.
6. Recognize the limitations of in-memory storage when moving toward production.

**Scope:** this lesson covers creating in-memory users for Spring Security **reactive**, not a servlet implementation and not a production registration/account management system.

## 2. MapReactiveUserDetailsService in the WebFlux Architecture

Each component has a distinct responsibility:

| Component | Job | Example |
| --- | --- | --- |
| **UserDetails** | Describes username, password hash, GrantedAuthority, and status | reader, ROLE_USER |
| **ReactiveUserDetailsService** | Looks up a user by username | Mono<UserDetails> findByUsername(String) |
| **MapReactiveUserDetailsService** | Implements the service above using an in-memory Map | new MapReactiveUserDetailsService(reader, admin) |
| **PasswordEncoder** | Encodes new passwords and calls matches during verification | BCryptPasswordEncoder |
| **ReactiveAuthenticationManager** | Receives credentials, uses user data and password check to authenticate | Login success or failure |
| **SecurityWebFilterChain** | Connects HTTP authentication and authorization | httpBasic, authorizeExchange |
| **Authentication** | Trusted identity after successful authentication | Principal reader, ROLE_USER |

Roughly how Spring Security processes an HTTP Basic flow:

~~~text
Client -> Authorization: Basic <base64(username:password)>
         |
         v
SecurityWebFilterChain (WebFlux)
         |
         v
Username/password authentication component
         |
         +--> ReactiveUserDetailsService.findByUsername(username)
         |       |
         |       +--> Mono<UserDetails> or Mono.empty()
         |
         +--> PasswordEncoder.matches(rawPassword, storedHash)
         |
         +--> UserDetails status checks
         |
         +--> Success: trusted Authentication
         +--> Failure: no valid login created
         |
         v
Authorization: authenticated, hasRole, hasAuthority
         |
         v
Controller and service
~~~

The diagram explains responsibilities, not the exact ordering of every WebFilter in every configuration. **MapReactiveUserDetailsService does not directly verify the raw password**; it only supplies the user record to the authentication mechanism. Likewise, finding a user does not mean the request sender is that user.

### 2.1. Comparison with Servlet

| Spring Security servlet | Spring Security reactive |
| --- | --- |
| UserDetailsService.loadUserByUsername returns UserDetails synchronously | ReactiveUserDetailsService.findByUsername returns Mono<UserDetails> |
| InMemoryUserDetailsManager | MapReactiveUserDetailsService |
| HttpSecurity, SecurityFilterChain | ServerHttpSecurity, SecurityWebFilterChain |
| Servlet Filter and servlet-style context management | WebFilter and Reactor Context |

Avoid confusing MapReactiveUserDetailsService with **InMemoryUserDetailsManager** just because both names suggest RAM. They serve different contracts and application models. Never call block() inside a WebFlux handler to force a Mono into a synchronous object.

## 3. Building UserDetails Properly

UserDetails is the contract describing an identity record, consisting of name, stored password, authorities, and flags such as enabled, accountNonLocked, accountNonExpired, and credentialsNonExpired.

Spring Security provides the **User.withUsername(...)** builder. Example:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails reader = User.withUsername("reader")
        .password(encoder.encode("reader-pass"))
        .roles("USER")
        .build();

UserDetails admin = User.withUsername("admin")
        .password(encoder.encode("admin-pass"))
        .roles("USER", "ADMIN")
        .build();

MapReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(reader, admin);
~~~

This snippet is meant to be placed inside a Java method with appropriate imports; the complete program is in Section 7.

- **username** is the key for looking up the user. Two users should not share the same username under system policy.
- **password** must be a string encoded with a PasswordEncoder compatible with the authentication mechanism.
- **roles("USER")** generates the **ROLE_USER** authority under Spring Security's default convention.
- **roles("USER", "ADMIN")** gives admin both ROLE_USER and ROLE_ADMIN, so it can also access endpoints requiring the USER role.
- **build()** creates the UserDetails from the configured values.

Distinction:

~~~java
.roles("ADMIN")                  // authority ROLE_ADMIN
.authorities("orders:read")      // authority orders:read
~~~

**hasRole("ADMIN")** checks for ROLE_ADMIN under the standard convention; **hasAuthority("orders:read")** compares the exact authority string. Do not pass ROLE_ADMIN into roles() and expect it to work properly in every case; roles() typically expects role names without the ROLE_ prefix.

### 3.1. Locked or Disabled Accounts

UserDetails holds account status flags. You can create a locked fixture:

~~~java
UserDetails locked = User.withUsername("locked")
        .password(encoder.encode("locked-pass"))
        .roles("USER")
        .accountLocked(true)
        .build();
~~~

This is an additional example, not part of the demo's two-user list. A user present in the Map but locked should not authenticate successfully. The authentication mechanism checks status and password, not merely whether the Map contains the username.

## 4. PasswordEncoder and Secure Password Storage

**BCryptPasswordEncoder** creates salted password hashes with an adjustable computational cost:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("reader-pass");

boolean ok = encoder.matches("reader-pass", storedHash);  // true
boolean bad = encoder.matches("wrong-pass", storedHash);  // false
~~~

Because of salting, two calls to encode with the same raw password can produce two different hashes. Never compare with encoder.encode(raw).equals(storedHash); always use **matches(raw, storedHash)**.

| Stage | Action |
| --- | --- |
| User creation | Hash password once, store hash in UserDetails |
| HTTP login | Receive raw password through the authentication mechanism |
| Lookup | MapReactiveUserDetailsService returns record containing hash |
| Verification | PasswordEncoder compares raw password against stored hash |
| Success | Framework creates Authentication with principal and authorities |
| Authorization | URL/method/object rules decide which resources can be accessed |

Do not write:

~~~java
// Incorrect with BCryptPasswordEncoder:
User.withUsername("reader")
        .password("reader-pass")
        .roles("USER")
        .build();
~~~

Also do not use **NoOpPasswordEncoder**, the **{noop}** prefix, or **User.withDefaultPasswordEncoder()** as a production solution. Simple mechanisms may appear in learning demos, but hardcoded passwords in source/binaries can still be read. The examples in this lesson use literals solely so learners can test with curl; never copy those credentials into a real system.

**HTTP Basic** encodes the username:password representation using Base64, which does not encrypt or secure the transport. Real deployments must run over **HTTPS/TLS** and avoid logging the Authorization header, passwords, or tokens. Never pass passwords in URL query strings.

BCrypt is CPU-intensive, so applications still need login rate limiting, load monitoring, and appropriate concurrency limits. Mono helps compose reactive pipelines, but it does not turn password hashing into a zero-CPU operation.

## 5. Instantiating MapReactiveUserDetailsService

Three constructors worth knowing:

~~~java
new MapReactiveUserDetailsService(reader, admin);
new MapReactiveUserDetailsService(List.of(reader, admin));

Map<String, UserDetails> byUsername = Map.of(
        reader.getUsername(), reader,
        admin.getUsername(), admin);
new MapReactiveUserDetailsService(byUsername);
~~~

The Map constructor requires non-blocking Map access. Do not place a synchronous I/O operation inside Map.get() and assume the outer wrapper makes it reactive. For small, static data, the varargs constructor is easiest to read.

MapReactiveUserDetailsService implements **ReactiveUserDetailsService** and **ReactiveUserDetailsPasswordService**; key public APIs:

~~~java
Mono<UserDetails> findByUsername(String username);
Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
~~~

**findByUsername** looks up a user by name; if present, it emits one UserDetails and completes; if absent, the Mono typically completes empty. It does not check raw passwords or create Authentication.

**updatePassword** allows updating a user's password in the running Map. With PasswordEncoder, the newPassword parameter must contain the **encoded** value matching the authentication configuration. This update is not persisted across restarts or automatically synced to other instances.

Example illustrating changing a password on a test service:

~~~java
Mono<UserDetails> changed =
        users.findByUsername("reader")
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("User missing")))
                .flatMap(user -> users.updatePassword(
                        user, encoder.encode("new-demo-pass")));
~~~

This code must be placed in a context where the users and encoder variables exist, not as a standalone Java file. When changing passwords in a real product, you need caller verification, rate limiting, auditing, session/token invalidation when needed, durable storage, and a password policy.

**Do not confuse APIs:** MapReactiveUserDetailsService does not provide administrative methods like createUser/deleteUser/updateUser as servlet's InMemoryUserDetailsManager does. You can supply the initial list when building the bean; if you need production account registration/deletion/updates, use an administrative service and an appropriate repository/Identity Provider.

### 5.1. Testing Lookups with Mono

~~~java
Mono<UserDetails> publisher = users.findByUsername("reader");

Mono<String> names = users.findByUsername("reader")
        .map(UserDetails::getUsername)
        .switchIfEmpty(Mono.just("not found"));
~~~

When run with the example data, publisher emits reader's UserDetails; names emits the string reader. However, a client could send a username via a query parameter to find an existing record. Such a lookup **does not prove client identity**. To protect APIs, use the Authentication provided by Spring Security after successful authentication.

### 5.2. Remember the Difference Between Configuration and Runtime

The bean is initialized when ApplicationContext creates its dependencies. BCrypt hashes can differ on each startup due to salting, yet matches(raw, storedHash) still succeeds. If the process restarts, the user list is recreated from configuration code, and runtime changes to the Map are not automatically restored. Multiple application instances do not share the same Map.

## 6. How Authentication and Authorization Share the User List

Spring Security looks at users from three distinct angles:

1. **Does the username exist?** ReactiveUserDetailsService.findByUsername returns UserDetails or Mono.empty.
2. **Are the credentials valid?** The manager and PasswordEncoder check the password, account status, and authentication conditions.
3. **Does the request have sufficient permissions?** SecurityWebFilterChain/authorization checks Authentication against roles, authorities, and resource policies.

Example with two requests:

~~~text
Request A: reader/reader-pass -> look up reader -> correct password
          -> Authentication ROLE_USER -> /api/me: 200

Request B: reader/reader-pass -> look up reader -> correct password
          -> Authentication ROLE_USER -> /admin/report: 403
~~~

Request B authenticated successfully but lacks admin permissions. Conversely, a nonexistent username or wrong password typically receives 401 with an HTTP Basic entry point.

**Do not return overly detailed, differing HTTP messages for nonexistent usernames vs. wrong passwords**, as that can aid user enumeration. Never log raw passwords; if metrics are needed, record failure categories server-side with sanitized data.

**Roles alone are not enough to protect specific records.** Someone with ROLE_USER still should not automatically read another user's orders. Enforce owner/tenant checks in the business layer or query data strictly within the permitted scope.

## 7. Runnable Java 17+ Project: Spring Boot WebFlux + HTTP Basic + MapReactiveUserDetailsService

The demo uses Java 17+, Gradle 8.x, and Spring Boot **3.3.5**. Two accounts for learning only:

| Username | Demo Password | Authority |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

Structure:

~~~text
memory-reactive-users/
├── settings.gradle
├── build.gradle
├── src/main/java/example/memory/MemoryUsersApplication.java
├── src/main/java/example/memory/DemoController.java
└── src/test/java/example/memory/MemoryUsersApplicationTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'memory-reactive-users'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. MemoryUsersApplication.java

~~~java
package example.memory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class MemoryUsersApplication {

    public static void main(String[] args) {
        SpringApplication.run(MemoryUsersApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

Here:
- The **PasswordEncoder** bean ensures passwords are encoded with BCrypt.
- The **MapReactiveUserDetailsService** bean provides users to Spring Security's username/password mechanism.
- **httpBasic** reads credentials from headers; controllers do not verify passwords themselves.
- **authorizeExchange** places the specific /admin/** rule before /api/** and finishes with denyAll.
- **formLogin.disable()** keeps the demo focused on HTTP Basic and 401/403 status codes.

### 7.4. DemoController.java

~~~java
package example.memory;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(p -> "hello " + p.getName());
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }
}
~~~

The controller receives a Mono<Principal> established by WebFlux HTTP security processing. It does not call users.findByUsername directly to "log in on behalf of" the client, nor does it return UserDetails (which could contain a hash) in HTTP responses.

### 7.5. Running and Observing

In the project directory, with JDK 17+ and Gradle 8.x:

~~~bash
gradle bootRun
~~~

In another Bash terminal:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u reader:reader-pass http://localhost:8080/api/me
# hello reader

curl -s -u admin:admin-pass http://localhost:8080/api/me
# hello admin

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:wrong-pass http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u unknown:any-pass http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/admin/report
# admin-report
~~~

Lines starting with # are only **expected stdout or status codes**, not commands. On Windows PowerShell, use **curl.exe** on a single line instead of Bash line-continuation syntax.

| HTTP request | Authentication | Authorization | Expected Result |
| --- | --- | --- | --- |
| /public/ping without credentials | Not required | permitAll | 200 pong |
| /api/me without credentials | Unauthenticated | authenticated | 401 |
| /api/me reader correct password | Succeeded with ROLE_USER | authenticated | 200 hello reader |
| /api/me admin correct password | Succeeded with ROLE_USER, ROLE_ADMIN | authenticated | 200 hello admin |
| /api/me reader wrong password | Failed | No valid identity created | 401 |
| /api/me nonexistent username | Failed | No valid identity created | 401 |
| /admin/report valid reader | Succeeded | Lacks ROLE_ADMIN | 403 |
| /admin/report valid admin | Succeeded | Has ROLE_ADMIN | 200 admin-report |

These are results of this specific HTTP Basic configuration; form login applications may use redirects instead of HTTP 401. The demo only uses GET so it does not demonstrate write operations/CSRF. If adding POST/PUT/DELETE, design CSRF according to the credential type browsers use and check resource limits.

## 8. Testing with StepVerifier and WebTestClient

You must test **user data** and **HTTP behavior** independently. A passing lookup test does not guarantee password verification or URL authorization is correct.

### 8.1. MemoryUsersApplicationTest.java

~~~java
package example.memory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MemoryUsersApplicationTest {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void findsStoredUserWithEncodedPassword() {
        StepVerifier.create(users.findByUsername("reader"))
                .assertNext(reader -> {
                    assertEquals("reader", reader.getUsername());
                    assertFalse("reader-pass".equals(reader.getPassword()));
                    assertTrue(encoder.matches(
                            "reader-pass", reader.getPassword()));
                    assertTrue(reader.getAuthorities().stream()
                            .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
                })
                .verifyComplete();
    }

    @Test
    void unknownUsernameIsEmpty() {
        StepVerifier.create(users.findByUsername("unknown"))
                .verifyComplete();
    }

    @Test
    void publicEndpointDoesNotNeedLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanOpenMeButCannotOpenAdmin() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello reader");

        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanOpenAdmin() {
        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-report");
    }
}
~~~

Run in the project directory:

~~~bash
gradle test
~~~

**Expected result:** six tests PASS, and Gradle finishes with **BUILD SUCCESSFUL** when dependencies are downloaded and the environment is valid.

- StepVerifier checks that findByUsername emits UserDetails, the hash is not the raw password, and an unknown username returns empty.
- WebTestClient checks WebFilter, HTTP Basic, and authorizeExchange, distinguishing invalid credentials (401) from missing admin permissions (403).

The test suite uses a random port, so no separate demo server needs to be running on port 8080. If you want to test protecting APIs with real data, add owner/tenant tests, brute-force rate limiting, CSRF, and realistic authentication mechanisms.

### 8.2. Testing updatePassword in Isolation

You should not change passwords on a shared bean across HTTP tests because test execution order could make results depend on each other. You can create a dedicated instance:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
UserDetails original = User.withUsername("temporary")
        .password(encoder.encode("old-pass"))
        .roles("USER")
        .build();

MapReactiveUserDetailsService temporary =
        new MapReactiveUserDetailsService(original);

StepVerifier.create(temporary.findByUsername("temporary")
        .flatMap(user -> temporary.updatePassword(
                user, encoder.encode("new-pass"))))
        .assertNext(updated -> {
            assertTrue(encoder.matches("new-pass", updated.getPassword()));
            assertFalse(encoder.matches("old-pass", updated.getPassword()));
        })
        .verifyComplete();
~~~

This snippet is used **inside a test method** with imports User, UserDetails, MapReactiveUserDetailsService, BCryptPasswordEncoder, PasswordEncoder, and assertTrue/assertFalse; it is not a standalone class file. It only modifies the temporary Map in RAM.

## 9. When Should You Use MapReactiveUserDetailsService?

**Good fit:** Spring Security learning demos, HTTP Basic API examples, integration tests, proofs of concept, or a small fixed set of users in a controlled environment.

**Not a production default** if you need sign-up, password change/reset, credential rotation, multiple replicas, multi-tenancy, auditing, policy-based account locking, MFA, or immediate permission updates.

| Limitation | Impact | Solution |
| --- | --- | --- |
| Non-persistent | Restarts lose runtime changes | Persistent repository or IdP |
| Not shared across instances | Each replica holds its own users | Centralized identity store |
| No full management API | Cannot build full signup/password reset with Map | Admin service, authorization, audit |
| Hardcoded credentials | Source/binary may expose demo passwords | Secret manager, issuance, and rotation |
| No built-in anti-abuse login policy | Brute force / credential stuffing | Rate limiting, monitoring, MFA |
| Password verification is CPU-intensive | Login floods affect availability | Load limiting, sizing, and latency tracking |
| UserDetails lacks object-level permissions | IDOR/BOLA can occur | Owner/tenant checks in service/repository |

For production, you can build a custom **ReactiveUserDetailsService** calling a non-blocking repository:

~~~java
// Integration example; userRepository, record, and data types are application-defined.
public Mono<UserDetails> findByUsername(String username) {
    return userRepository.findByUsername(username)
            .map(record -> User.withUsername(record.username())
                    .password(record.encodedPassword())
                    .authorities(record.authorities())
                    .disabled(!record.enabled())
                    .accountLocked(record.locked())
                    .build());
}
~~~

The snippet above **is not a standalone Java program**; you must design the schema, indexes/uniqueness, transactions, authority mapping, auditing, and status policies. Using OAuth2/OIDC or a Resource Server may be more suitable when an external Identity Provider already exists. When an API only accepts JWT bearer tokens from an issuer, you do not need MapReactiveUserDetailsService to validate those tokens.

## 10. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Having a user in the Map means the request is logged in" | findByUsername only finds the record; password/token verification is required |
| "Reactive means no CPU is used" | Mono is an async contract; BCrypt still consumes CPU |
| "PasswordEncoder.encode(raw) always outputs the same string" | BCrypt uses salt; verify with matches |
| "Calling roles("ADMIN") automatically protects all admin URLs" | You must configure hasRole/hasAuthority |
| "ROLE_ADMIN is a direct argument to roles()" | Typically use roles("ADMIN") or authorities("ROLE_ADMIN") |
| "MapReactiveUserDetailsService is InMemoryUserDetailsManager by another name" | One is reactive, the other is servlet/synchronous |
| "HTTP Basic Base64 is secure enough" | Must use TLS |
| "Mono.empty() from findByUsername means anonymous is allowed" | It means no UserDetails; authorization still decides |
| "The user list can be stored permanently in RAM" | Restarts and multiple replicas lose/diverge changes |
| "updatePassword(raw) will hash raw automatically" | In a PasswordEncoder model, you must supply an encoded value |
| "UserDetails can be returned directly to clients" | Can leak hashes and sensitive metadata |
| "authenticated() replaces object-level permissions" | Roles plus owner/tenant checks are required |

## 11. Self-Check Exercises

1. Which lookup interface does MapReactiveUserDetailsService implement, and what return type does findByUsername use?
2. When a username exists but the password is wrong, which step rejects it?
3. Why shouldn't you compare two BCrypt hashes generated from the same raw password using equals?
4. How do roles("ADMIN") and authorities("ROLE_ADMIN") differ in representation?
5. Why does user reader log in successfully yet receive 403 at /admin/report?
6. If a controller accepts a client-supplied username and calls users.findByUsername(username), has it authenticated the sender?
7. What happens when the application restarts after calling updatePassword on the Map?
8. Why does HTTP Basic still require TLS despite using Base64?
9. Should you use StepVerifier or WebTestClient to test findByUsername directly?
10. When should you move to a reactive repository or an Identity Provider?
11. What must be configured so new endpoints are not public by default?
12. Why shouldn't UserDetails be returned directly as an API response?

**Suggested answers:** (1) ReactiveUserDetailsService and Mono<UserDetails>; (2) the manager/PasswordEncoder checks credentials; (3) salt; use matches; (4) roles adds the ROLE_ prefix by convention; (5) missing ROLE_ADMIN; (6) no, clients can claim any username; (7) runtime changes are lost because the bean is recreated; (8) Base64 does not protect transport; (9) StepVerifier, while WebTestClient tests HTTP end-to-end; (10) when needing persistence, management, multi-instance support, or MFA/SSO; (11) authorizeExchange rules with secure defaults; (12) it can expose password hashes or internal status.

## 12. Reference Documentation

- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security Javadoc — MapReactiveUserDetailsService: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html
- Spring Security Javadoc — ReactiveUserDetailsService: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html

**Conclusion:** create UserDetails with BCrypt-encoded passwords and explicit authorities, place the users in a **MapReactiveUserDetailsService** bean, and use **SecurityWebFilterChain** to enable authentication and authorization. Username lookup, credential verification, and permission checking are three distinct steps; the in-memory store helps you learn the reactive mechanics, but it does not replace a production identity store.