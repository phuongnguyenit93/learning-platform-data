# ReactiveUserDetailsService and MapReactiveUserDetailsService in Spring WebFlux

When a Spring Security application runs on **Spring WebFlux**, account lookup must fit the reactive processing pipeline. Instead of the synchronous **UserDetailsService.loadUserByUsername(String)** contract, Spring Security provides **ReactiveUserDetailsService.findByUsername(String)** returning **Mono<UserDetails>**. To get started quickly, the framework provides **MapReactiveUserDetailsService**, an implementation storing UserDetails in a Map, useful for lessons, demos, and tests. For a real system, you can replace it with a ReactiveUserDetailsService querying data via a nonblocking I/O source such as R2DBC.

This lesson belongs to the **User Sources** section of Spring Security fundamentals. The goal is to understand the contract, its relationship to authentication mechanisms, how to configure WebFlux, Reactor properties, blocking traps, and a complete **Java 17+, Spring Boot 3.3.6, Spring Security 6.x** example. The example uses **HTTP Basic and dummy accounts on localhost** for self-testing with WebTestClient; production must choose appropriate identity sources, HTTPS, secrets, access limits, and security patches.

## 1. Why Does WebFlux Have a Separate User Lookup Contract?

Spring MVC normally handles requests in the Servlet model, using the UserDetailsService API:

~~~java
// Synchronous signature of Servlet-oriented UserDetailsService.
// This is a descriptive fragment, not a standalone Java file.
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

In WebFlux, many I/O steps are represented by Project Reactor publishers. The reactive contract:

~~~java
// Signature of org.springframework.security.core.userdetails.ReactiveUserDetailsService.
// This is a descriptive fragment, not a standalone Java file.
Mono<UserDetails> findByUsername(String username);
~~~

The difference is not in the **UserDetails** object: both contain username, password hash, GrantedAuthority, and account status. The difference is **how the data-fetching process is represented**:

| Criterion | UserDetailsService | ReactiveUserDetailsService |
| --- | --- | --- |
| Method | loadUserByUsername(String) | findByUsername(String) |
| Return value | Direct UserDetails | Mono<UserDetails> |
| Suitable I/O | Synchronous; typically JDBC/JPA or blocking sources | Nonblocking/R2DBC sources or publishers with proper scheduling strategy |
| Typical context | Spring MVC with DaoAuthenticationProvider | Spring WebFlux with UserDetailsRepositoryReactiveAuthenticationManager |
| User not found | Typically throws UsernameNotFoundException | Expressed via Mono signals per implementation and handling manager |
| User data | UserDetails with principal, hash, permissions, account flags | **Same UserDetails interface** |
| Password check | PasswordEncoder in provider/manager | PasswordEncoder in reactive authentication manager |
| HTTP protection | HttpSecurity + SecurityFilterChain | ServerHttpSecurity + SecurityWebFilterChain |

**Mono<UserDetails> does not automatically make a database nonblocking.** If an implementation calls synchronous JDBC or a blocking HTTP client on the event loop and wraps it in Mono.just(...), the event loop is still blocked. Moving to WebFlux requires inspecting the entire I/O call path, not merely changing the method's return type.

A Spring MVC application can use **WebClient** to call other services while remaining a Servlet server. In that case, HTTP security configuration still uses **HttpSecurity/SecurityFilterChain**, rather than switching to ServerHttpSecurity just because WebFlux dependencies are on the classpath.

## 2. UserDetails Remains the Shared Contract

In both stacks, **UserDetails** is a Spring Security Core interface, typically containing:

~~~java
// Condensed contract fragment, not a replacement for the library file.
String getUsername();
String getPassword();
Collection<? extends GrantedAuthority> getAuthorities();
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

In the user store:

- **getUsername()** identifies the name used for authentication lookup.
- **getPassword()** holds stored password info, typically a **hash** compatible with PasswordEncoder. Never store plain text.
- **getAuthorities()** holds trusted authorities such as ROLE_USER, ROLE_ADMIN, or orders:read; never take permissions directly from client headers.
- **isEnabled()** reports whether the account is activated.
- **isAccountNonLocked()**, **isAccountNonExpired()**, and **isCredentialsNonExpired()** are three negated flags: normal state should usually be **true**.

Example of an active user:

~~~text
UserDetails
  username                  = alice
  password                  = BCrypt hash (never put in JSON)
  authorities               = [ROLE_USER, orders:read]
  isEnabled                 = true
  isAccountNonLocked        = true
  isAccountNonExpired       = true
  isCredentialsNonExpired   = true
~~~

**ReactiveUserDetailsService only looks up UserDetails**. It does not itself receive HTTP requests, compare raw passwords, create SecurityContext, or decide whether a role may call an endpoint. Those duties belong to authentication filters, the authentication manager, and the authorization layer.

Note carefully: **isAccountNonLocked=false** means *currently locked*; **isAccountNonExpired=false** means *account expired*. When mapping from an entity with locked=true or expired=true fields, invert the booleans properly.

## 3. Mono<UserDetails>: Understanding Results, Errors, and Lifecycle

A Mono publisher can:

1. **Emit one UserDetails** and complete when found.
2. **Complete empty (no element)** when the source provides no user, if the implementation chooses that representation.
3. **Emit an error** on a failure condition, such as a data-source error or an implementation signaling user-not-found with an exception.

The findByUsername contract returns **Mono<UserDetails>**, meaning the return value itself must never be null. Never write **return null** or **return Mono.just(null)**: Mono does not allow null as a valid element. Missing-user cases must be handled explicitly with Reactor and per the authentication manager's contract.

Illustrative lookup example from a reactive repository:

~~~java
// Illustrative fragment. reactiveAccountRepository and lookup method
// are defined separately in a project using R2DBC or a reactive source.
@Override
public Mono<UserDetails> findByUsername(String username) {
    return reactiveAccountRepository.findByUsername(username)
        .map(row -> User.withUsername(row.username())
            .password(row.passwordHash())
            .authorities(row.authorities())
            .disabled(!row.enabled())
            .accountLocked(row.locked())
            .build());
}
~~~

Here the repository's **findByUsername(...)** must already return a genuine publisher rather than running blocking JDBC. **map(...)** converts AccountRow into UserDetails; when the repository emits no user, map does not run. When the repository emits an error, the error propagates downstream unless intentionally handled.

**Do not use onErrorResume to return a default high-privilege account.** Database errors must cause authentication to fail cleanly, never turning into a fake identity allowed access.

### 3.1. Lazy execution and subscription

Normally, many Reactor publishers are cold: building the pipeline does not necessarily execute the query immediately; the framework subscribes when the request needs the result. Avoid calling **subscribe()** yourself inside ReactiveUserDetailsService, because doing so detaches authentication work from the request lifecycle and loses propagation, error handling, and timeouts.

In controllers/services, return the Mono to the framework or compose with operators like **map**, **flatMap**, **switchIfEmpty**. Never call **block()** inside a WebFilter or Controller running on the event loop.

### 3.2. The Mono.just mistake with blocking sources

~~~java
// Anti-pattern: JDBC runs immediately on the current thread.
return Mono.just(jdbcUserRepository.findUser(username));
~~~

When `jdbcUserRepository.findUser(...)` executes, JDBC has already blocked the thread **before** `Mono.just` is constructed. The safer long-term approach is using a proper reactive database driver and repository; when forced to call a blocking API, isolate it with a scheduler and load bounds:

~~~java
// Illustrative fragment, used when the source is unavoidably blocking.
// May need additional null, exception, timeout, and concurrency handling.
return Mono.fromCallable(() -> jdbcUserRepository.findUser(username))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This example requires importing **reactor.core.scheduler.Schedulers** and **Mono**. `boundedElastic` avoids blocking the event loop while waiting on blocking I/O; it does not make JDBC nonblocking, does not create an infinite pool, and does not guarantee good performance if all queries remain blocking. With CPU-intensive password hashing, monitor schedulers/CPU and concurrency limits per the actual manager in use.

## 4. What Is MapReactiveUserDetailsService?

**org.springframework.security.core.userdetails.MapReactiveUserDetailsService** is a built-in implementation of **ReactiveUserDetailsService**, backed by a Map storing UserDetails. This class also implements **ReactiveUserDetailsPasswordService**, providing `updatePassword(...)` to update passwords per the implementation's contract.

Common ways to construct it:

~~~java
// Code fragment used where MapReactiveUserDetailsService is imported
// and UserDetails variables alice, bob are already created.
MapReactiveUserDetailsService first =
    new MapReactiveUserDetailsService(alice, bob);

MapReactiveUserDetailsService second =
    new MapReactiveUserDetailsService(List.of(alice, bob));

MapReactiveUserDetailsService third =
    new MapReactiveUserDetailsService(
        Map.of(alice.getUsername(), alice, bob.getUsername(), bob)
    );
~~~

**Characteristics:**

- User source resides in the memory of the running process.
- Suitable for small examples, tests, prototypes, or temporary test accounts.
- `findByUsername(...)` returns `Mono<UserDetails>`, sharing the same contract as custom services.
- `updatePassword(...)` can mutate stored user data; use it strictly in isolated tests or a designed password management flow.
- Does not provide persistent databases, replication, MFA, password reset, rotation, auditing, or production account provisioning.
- If the app has multiple instances, instance A's Map **does not automatically sync** to instance B.
- Explicitly check case sensitivity, username uniqueness, data lifetime, and how accounts are recreated on restart.

### 4.1. Do not confuse class names or packages

~~~java
// Spring Security Core:
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
~~~

There is no reason to write a class named **InMemoryReactiveUserDetailsManager** assuming it is a built-in API. For Servlet, the familiar class is **InMemoryUserDetailsManager**; for reactive, use **MapReactiveUserDetailsService**.

### 4.2. When should you not use MapReactiveUserDetailsService?

Do not use it as the primary account store of a real product if the system needs account updates across multiple servers, permission synchronization, auditing, password reset, account lockout, or a centralized identity source. Data sitting in a Map cannot replace an identity service/DB, even if the lookup API is called "reactive".

It also does not make OAuth2/OIDC/JWT appear automatically. A Resource Server decodes/verifies access tokens using its own mechanism; it may not call ReactiveUserDetailsService on every Bearer request.

## 5. Where Does ReactiveUserDetailsService Sit in the Authentication Flow?

With HTTP Basic in WebFlux:

~~~mermaid
flowchart TD
    A["Client GET /api/me + Authorization: Basic ..."] --> B["Spring Security WebFilter chain"]
    B --> C["HTTP Basic authentication filter"]
    C --> D["Unauthenticated UsernamePasswordAuthenticationToken"]
    D --> E["ReactiveAuthenticationManager"]
    E --> F["UserDetailsRepositoryReactiveAuthenticationManager"]
    F --> G["ReactiveUserDetailsService.findByUsername()"]
    G --> H["Mono<UserDetails>"]
    H --> I["PasswordEncoder.matches + account checks"]
    I --> J{"Valid login?"}
    J -- "Yes" --> K["Authenticated Authentication"]
    J -- "No" --> L["401 / response per entry point"]
    K --> M["Reactor SecurityContext"]
    M --> N["authorizeExchange and WebFlux Controller"]
~~~

Steps are simplified for learning; WebFilter and handler placement may depend on configuration. **UserDetailsRepositoryReactiveAuthenticationManager** is the ReactiveAuthenticationManager implementation that uses ReactiveUserDetailsService to load accounts and verify username/password.

Responsibility breakdown:

| Component | Job |
| --- | --- |
| HTTP Basic Authentication WebFilter | Reads HTTP Authorization, creates authentication request, calls appropriate manager. |
| ReactiveAuthenticationManager | Receives Authentication, returns Mono<Authentication> or error/empty signal per contract. |
| UserDetailsRepositoryReactiveAuthenticationManager | Uses ReactiveUserDetailsService, PasswordEncoder, and account checks for username/password authentication. |
| ReactiveUserDetailsService | Looks up UserDetails by username; does not directly verify passwords. |
| MapReactiveUserDetailsService | An implementation looking up users in a Map; useful for demos and tests. |
| PasswordEncoder | Hashes/matches passwords; remains a synchronous interface, so CPU cost must be considered. |
| SecurityWebFilterChain + ServerHttpSecurity | Applies WebFlux authn/authz mechanisms, CSRF, headers, and related filters. |
| ReactiveSecurityContextHolder | Accesses SecurityContext in Reactor Context within appropriate reactive chains. |

**Do not use DaoAuthenticationProvider + HttpSecurity as the main configuration for a WebFlux server.** They belong to the Servlet stack. In WebFlux, the corresponding username/password stack consists of ReactiveAuthenticationManager and ServerHttpSecurity.

### 5.1. Username/password and Bearer tokens are two different mechanisms

For an OAuth2 Resource Server, an access token can be verified using **ReactiveJwtDecoder** or appropriate introspection. Along that path, the framework does not by default call MapReactiveUserDetailsService to load users and check passwords. Do not conclude that disabling a UserDetails in the Map will automatically revoke all still-valid JWTs; token validation/revocation is a separate topic.

## 6. Hands-On Project: Spring Boot WebFlux + MapReactiveUserDetailsService

The sample application has four endpoints:

- **GET /api/public**: requires no authentication.
- **GET /api/me**: requires authentication, returns username from principal.
- **GET /api/orders**: requires authority **orders:read**.
- **GET /api/admin**: requires role **ADMIN** (authority ROLE_ADMIN).

To observe all account states, create these users:

| Username | Test password | Authorities | Status |
| --- | --- | --- | --- |
| alice | demo-password | ROLE_USER, orders:read | Active. |
| viewer | demo-password | ROLE_USER | Active; lacks orders:read. |
| admin | demo-password | ROLE_ADMIN, orders:read | Active; allowed into /api/admin. |
| locked | demo-password | ROLE_USER | Locked, cannot log in. |
| disabled | demo-password | ROLE_USER | Disabled, cannot log in. |
| expired | demo-password | ROLE_USER | Account expired. |
| credentials-expired | demo-password | ROLE_USER | Credentials expired. |

The passwords above are dummy data for localhost. Never ship demo accounts or passwords to production. **PasswordEncoder** hashes the passwords right when creating users at startup.

### 6.1. Requirements and file structure

- **JDK 17+**, Maven 3.9+ or Maven Wrapper.
- Port **8080** free.
- **curl.exe** on PowerShell, or curl on Linux/macOS.

~~~text
webflux-users-demo/
├── pom.xml
└── src
    ├── main/java/com/example/reactiveusers
    │   ├── ReactiveUsersApplication.java
    │   ├── ApiController.java
    │   └── SecurityConfig.java
    └── test/java/com/example/reactiveusers
        └── ReactiveUsersTests.java
~~~

All Java files use package **com.example.reactiveusers**. There is no `spring-boot-starter-web` because the project must run a **WebFlux server**, not silently switch back to Spring MVC.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-users-demo</artifactId>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

**Dependency roles:**

- spring-boot-starter-webflux: Spring WebFlux, Reactor, and reactive HTTP server.
- spring-boot-starter-security: UserDetails contracts, reactive authentication, and security WebFilters.
- spring-boot-starter-test: JUnit 5, Spring Boot Test, WebTestClient, and test utilities.
- spring-security-test: supports mock authentication and Security WebTestClient integration when needed.
- reactor-test: StepVerifier to test Mono/Flux directly.

### 6.3. ReactiveUsersApplication.java

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

Main class in the root package so Spring Boot scans Controller and Configuration in the same package. Never hardcode an "open-everything dev" profile in main.

### 6.4. SecurityConfig.java — creating MapReactiveUserDetailsService

~~~java
package com.example.reactiveusers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_ADMIN", "orders:read")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .accountLocked(true)
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .disabled(true)
            .build();

        UserDetails expired = User.withUsername("expired")
            .password(encoder.encode("demo-password"))
            .authorities("ROLE_USER")
            .accountExpired(true)
            .build();

        UserDetails credentialsExpired =
            User.withUsername("credentials-expired")
                .password(encoder.encode("demo-password"))
                .authorities("ROLE_USER")
                .credentialsExpired(true)
                .build();

        return new MapReactiveUserDetailsService(
            alice, viewer, admin, locked, disabled, expired,
            credentialsExpired
        );
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
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
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("orders:read")
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Configuration explanation:**

1. **MapReactiveUserDetailsService** manages demo UserDetails and supplies `findByUsername(...)` per ReactiveUserDetailsService.
2. **BCryptPasswordEncoder** creates hashes from sample passwords. Never store raw passwords in UserDetails.
3. **UserDetailsRepositoryReactiveAuthenticationManager** looks up the user via the service, matches the password with the encoder, and enforces account status checks.
4. **http.authenticationManager(manager)** plugs the manager into the WebFlux security DSL. Explicit configuration avoids relying on guesswork about which manager Spring Boot picks when multiple providers exist.
5. **ServerHttpSecurity** and **SecurityWebFilterChain** belong to the reactive stack. Never replace them with Servlet's HttpSecurity/SecurityFilterChain.
6. **authorizeExchange** enforces permissions by path and HTTP method. `/api/public` is intentionally public; `/api/me` needs authenticated; `/api/orders` needs authority `orders:read`; `/api/admin` needs `ROLE_ADMIN`.
7. **anyExchange().denyAll()** rejects requests not matching any rule. This covers new methods on existing paths.
8. **httpBasic** lets curl send credentials. This sample uses only GET; **default CSRF is not disabled**.
9. **User.withUsername().accountLocked(true)** builds a UserDetails with `isAccountNonLocked=false`; `disabled(true)`, `accountExpired(true)`, and `credentialsExpired(true)` likewise invert to their corresponding invalid values.
10. HTTP Basic **does not encrypt** username/password on the wire: Base64 can be decoded; real connections must use HTTPS. Never use demo accounts outside localhost.

For Spring Security lines other than 6.3.x, check the constructor and `setPasswordEncoder` APIs in your active dependency version. Do not mix disparate Spring Security versions just to make a snippet compile.

### 6.5. ApiController.java

~~~java
package com.example.reactiveusers;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(
            p -> Map.of("username", p.getName())
        );
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> orders() {
        return Mono.just(Map.of("message", "orders-read"));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin"));
    }
}
~~~

Methods return **Mono** for WebFlux. At `/api/me`, the **Mono<Principal>** parameter is supported by WebFlux; `Principal` represents the security-established identity. Never take a username from a query parameter and treat it as the caller.

**The controller does not check passwords or roles with `if`**: `SecurityWebFilterChain` already enforced URL access before the handler was invoked. A real application still needs Services/domain logic to check **object-level permissions**, such as tenant/owner of each order, because `orders:read` is only an action-level authority.

### 6.6. Launching

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

If the default port is free, the application listens on:

~~~text
http://localhost:8080
~~~

On PowerShell use **curl.exe**, on Linux/macOS use **curl**.

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-password http://localhost:8080/api/me
curl.exe -i -u alice:demo-password http://localhost:8080/api/orders
curl.exe -i -u viewer:demo-password http://localhost:8080/api/orders
curl.exe -i -u alice:demo-password http://localhost:8080/api/admin
curl.exe -i -u admin:demo-password http://localhost:8080/api/admin
curl.exe -i -u locked:demo-password http://localhost:8080/api/me
~~~

**Expected HTTP results:**

| Request | Status | Reason |
| --- | --- | --- |
| GET /api/public, no credentials | 200 | Has permitAll() rule. |
| GET /api/me, no credentials | 401 | Requires authentication via HTTP Basic. |
| GET /api/me, alice right password | 200 | Active account, manager authenticates successfully. |
| GET /api/orders, alice | 200 | Has orders:read. |
| GET /api/orders, viewer | 403 | Has ROLE_USER yet lacks orders:read. |
| GET /api/admin, alice | 403 | Lacks ROLE_ADMIN. |
| GET /api/admin, admin | 200 | Has ROLE_ADMIN. |
| GET /api/me, locked | 401 | Account locked despite right password. |
| GET /api/me, wrong password | 401 | Invalid credentials. |

JSON body on success:

~~~json
{"username":"alice"}
~~~

and:

~~~json
{"message":"orders-read"}
~~~

Headers such as `WWW-Authenticate` or security headers depend on configuration; do not pin the entire response byte-for-byte. If you test a public URL **with a wrong Authorization header**, the authentication filter may reject it even though the authorization rule is `permitAll`; use a credential-free request to truly test public access.

### 6.7. Does MapReactiveUserDetailsService automatically create an HTTP session?

**No.** The service only knows how to look up UserDetails from the Map. HTTP Basic, form login, Bearer tokens, and security context persistence are the job of the filter chain and other authn mechanisms. With HTTP Basic, clients typically send credentials on each request. Do not treat `Mono` or `MapReactiveUserDetailsService` as proof the system is automatically stateless; WebFlux still has `WebSession` and corresponding context repositories when configured.

## 7. Testing ReactiveUserDetailsService with StepVerifier

**StepVerifier** in `reactor-test` lets you test publishers without calling `block()` in business code. Direct check example:

~~~java
StepVerifier.create(users.findByUsername("alice"))
    .assertNext(user -> {
        assertThat(user.getUsername()).isEqualTo("alice");
        assertThat(user.isEnabled()).isTrue();
        assertThat(user.isAccountNonLocked()).isTrue();
        assertThat(user.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_USER", "orders:read");
    })
    .verifyComplete();
~~~

This is a valid test fragment when placed inside a JUnit class with the `users` bean and imports for StepVerifier, AssertJ, and GrantedAuthority. It proves the **Mono<UserDetails>** contract and that basic data is loaded. It does not prove password correctness, because `findByUsername` has no password parameter and performs no authentication.

For a locked account, the data test sees **isAccountNonLocked=false**; to prove the manager rejects a valid password, test **ReactiveAuthenticationManager** or HTTP Basic at the WebTestClient layer.

## 8. Complete Test Suite: Service, Manager, and WebTestClient

Create **src/test/java/com/example/reactiveusers/ReactiveUsersTests.java**:

~~~java
package com.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveUsersTests {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    ReactiveAuthenticationManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void findUserReturnsReactiveUserDetails() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertThat(user.getUsername()).isEqualTo("alice");
                assertThat(user.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("ROLE_USER", "orders:read");
                assertThat(user.isEnabled()).isTrue();
                assertThat(user.isAccountNonLocked()).isTrue();
                assertThat(user.isAccountNonExpired()).isTrue();
                assertThat(user.isCredentialsNonExpired()).isTrue();
            })
            .verifyComplete();
    }

    @Test
    void passwordIsEncodedAndMatchesOnlyCorrectRawPassword() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(user -> {
                assertThat(user.getPassword())
                    .isNotEqualTo("demo-password");
                assertThat(encoder.matches(
                    "demo-password", user.getPassword())).isTrue();
                assertThat(encoder.matches(
                    "wrong-password", user.getPassword())).isFalse();
            })
            .verifyComplete();
    }

    @Test
    void lockedFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("locked"))
            .assertNext(user -> {
                assertThat(user.isEnabled()).isTrue();
                assertThat(user.isAccountNonLocked()).isFalse();
            })
            .verifyComplete();
    }

    @Test
    void disabledFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("disabled"))
            .assertNext(user ->
                assertThat(user.isEnabled()).isFalse())
            .verifyComplete();
    }

    @Test
    void expiredFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("expired"))
            .assertNext(user ->
                assertThat(user.isAccountNonExpired()).isFalse())
            .verifyComplete();
    }

    @Test
    void credentialsExpiredFlagIsReflectedInUserDetails() {
        StepVerifier.create(users.findByUsername("credentials-expired"))
            .assertNext(user ->
                assertThat(user.isCredentialsNonExpired()).isFalse())
            .verifyComplete();
    }

    @Test
    void authenticationManagerAcceptsValidCredentials() {
        var request = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "demo-password");

        StepVerifier.create(manager.authenticate(request))
            .assertNext(authentication -> {
                assertThat(authentication.isAuthenticated()).isTrue();
                assertThat(authentication.getName()).isEqualTo("alice");
                assertThat(authentication.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("ROLE_USER", "orders:read");
            })
            .verifyComplete();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsActiveUser() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void lockedUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "locked", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void disabledUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "disabled", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredUserIsRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "expired", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredCredentialsAreRejectedOverHttpBasic() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "credentials-expired", "demo-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userWithReadAuthorityCanReadOrdersEndpoint() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("orders-read");
    }

    @Test
    void roleUserWithoutPermissionCannotReadOrdersEndpoint() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth(
                "viewer", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void normalUserCannotCallAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanCallAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin");
    }

    @Test
    void unknownRouteIsDeniedEvenForAuthenticatedUser() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void spoofedRoleHeaderDoesNotAuthenticate() {
        client.get().uri("/api/admin")
            .header("X-Role", "ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The **21 tests** above cover UserDetails data, BCrypt hashes, four account flags, direct authentication via ReactiveAuthenticationManager, and WebFlux HTTP outcomes (200/401/403). The tests must be run in a project with the declared dependencies; code in the documentation is a sample for learners to run, not a report claiming Maven was already executed.

### 8.1. What does each test prove?

| Group | What it proves | What it does not prove |
| --- | --- | --- |
| StepVerifier on MapReactiveUserDetailsService | Publisher emits UserDetails and fields/flags/authorities match. | HTTP path authenticated, password checked in filter. |
| StepVerifier on manager.authenticate | Password and account produce a valid Authentication in the reactive pipeline. | HTTP status, CORS, CSRF, TLS, or proxy. |
| WebTestClient | WebFlux/Spring Security enforces rules and returns right status/body in test context. | Production ingress, real OAuth2 IdP, real database, tenant ownership. |
| curl against running server | HTTP behavior of local process and Basic challenge. | Infrastructure/HTTPS security in deployment and secret rotation. |

Do not use MockMvc as the primary tool to test a WebFlux filter chain. **WebTestClient** is the right API, either bound to the application context or connecting to a real HTTP server, depending on configuration.

### 8.2. Why not test updatePassword right here as well?

`MapReactiveUserDetailsService` has `updatePassword(...)`, yet it **mutates data in the Map**. If tests share a Spring ApplicationContext and one test changes Alice's password, subsequent login tests can become order-dependent or fail unpredictably. To test updates, create **an isolated `MapReactiveUserDetailsService` instance inside that test**, use demo passwords, and verify both the hash value and lookup behavior after update. Never mutate the shared user bean of integration tests.

## 9. Custom ReactiveUserDetailsService with a Reactive Database

When the app needs a real account source, replace the Map with an appropriate repository. An R2DBC flow can be designed as:

~~~text
HTTP Basic / form login
        |
        v
ReactiveAuthenticationManager
        |
        v
ReactiveUserDetailsService.findByUsername(username)
        |
        v
R2DBC repository / nonblocking driver
        |
        v
Mono<AccountRow> --> map AccountRow -> UserDetails
        |
        v
Manager checks status + PasswordEncoder.matches
        |
        v
Authentication or error
~~~

An illustrative service fragment; **requires its own AccountRepository, AccountRow, and R2DBC configuration**, so it is not a standalone file inside the demo:

~~~java
@Service
public class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseReactiveUserDetailsService(
            AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(row -> User.withUsername(row.username())
                .password(row.passwordHash())
                .authorities(row.authorities())
                .disabled(!row.enabled())
                .accountLocked(row.locked())
                .accountExpired(row.expired())
                .credentialsExpired(row.credentialsExpired())
                .build());
    }
}
~~~

**AccountRepository.findByUsername(...)** in the illustrative snippet is assumed to return **Mono<AccountRow>**. Ensure data rows contain accurate hashes and authorities granted from a trusted source. If the repository emits an error due to a lost DB connection, the manager must never let callers log in under a default account.

When replacing the Map bean with a database service:

- Keep only **one appropriate ReactiveUserDetailsService source** for this login mechanism, or configure the manager/chain to select explicitly.
- Never ship the demo Map accounts to production; forgotten demo accounts can become a backdoor.
- Ensure username uniqueness within the required scope and never mix data across tenants.
- Password hashes in the database must match the encoder. Never call `encoder.encode(storedHash)` again.
- Read authorities/roles from trusted relations; never read them from an arbitrary client-set `X-Role` header.
- Boolean mapping must be exact: `entity.locked=true` → `builder.accountLocked(true)`, meaning `UserDetails.isAccountNonLocked()` is false.
- Use optimal indexes/queries, timeouts, connection pool limits, and health checks; avoid returning entire sensitive profile records just for authentication.
- If caching users or authorities, enforce TTL/invalidation when roles or passwords change or accounts are locked.
- Place password reset, MFA, auditing, rate limits, and fraud alerts in the appropriate components.

### 9.1. Is R2DBC mandatory?

No. WebFlux can integrate a reactive HTTP source or any storage with a compatible nonblocking driver. Some WebFlux apps must call a blocking dependency; in that case isolate it and measure load. What matters is understanding the **actual call behavior**, backpressure, timeouts, and thread consumption, rather than treating a `Mono`-returning method name as proof.

## 10. PasswordEncoder, Schedulers, and Performance

**PasswordEncoder** has synchronous signatures, namely:

~~~java
// API fragment, not a standalone method outside the interface.
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
~~~

BCrypt intentionally performs CPU work to slow down password-guessing attacks. A `ReactiveAuthenticationManager` may schedule password-handling steps onto an appropriate scheduler; that does not turn hashing into nonblocking I/O.

Under concurrent login traffic, monitor:

- CPU consumed matching BCrypt/Argon2/PBKDF2 per policy.
- Timeouts and concurrency for user lookups from the database/identity store.
- Rate limiting per IP/account/device and credential-stuffing defenses.
- p95/p99 authentication latency and thread counts on event-loop/scheduler pools.
- Error handling when accounts do not exist, DB fails, or credentials are wrong.
- Never write password hashes, raw passwords, Authorization headers, cookies, or tokens to logs.

**Do not recommend dropping BCrypt or using NoOpPasswordEncoder to speed up production.** Optimize configuration, cost, and capacity properly. Across Spring Security versions, scheduling behavior may change; read the Javadoc/implementation of the manager in your active version.

## 11. Reactor Context and SecurityContext: Two Different Things from User Lookup

In WebFlux, Spring Security propagates the security context through **Reactor Context** along the reactive chain. After authentication succeeds, code can read the principal from WebFlux method arguments or via **ReactiveSecurityContextHolder**.

Example fragment in a reactive service:

~~~java
// Code fragment requiring imports for ReactiveSecurityContextHolder,
// SecurityContext, and Mono from Spring Security/Reactor.
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

**This is not ReactiveUserDetailsService.findByUsername(...).** A service calling `ReactiveSecurityContextHolder` is reading the **currently authenticated user**, whereas `ReactiveUserDetailsService` is what **looks up an account by username** during authentication.

When there is no security context, the publisher may emit no username; when the principal is a JWT/OIDC/service identity, the principal type may differ from UserDetails. Never cast every `Authentication.getPrincipal()` to `UserDetails` without checking the authentication mechanism.

Never store `Authentication` in a static variable shared across requests: doing so can mix identities across users. Likewise, do not subscribe outside a request expecting the security context to automatically follow into a scheduled job or message consumer.

### 11.1. WebSession and MapReactiveUserDetailsService

Finding an account in the Map does not automatically create an HTTP session or auto-login. Distinguish:

- **User lookup**: MapReactiveUserDetailsService.
- **Authentication**: ReactiveAuthenticationManager + filter.
- **Request context**: SecurityContext inside Reactor Context.
- **Cross-request persistence**: ServerSecurityContextRepository/WebSession or configured token/credential mechanism.
- **Authorization**: URL, method, and object-level permissions.

WebFlux still supports sessions. `Mono` does not automatically imply "stateless"; stateless vs. stateful is a separate architectural decision.

## 12. Distinguishing 401, 403, and User Lookup Errors

When testing a WebFlux REST API, typical outcomes:

| Scenario | Typical HTTP result | Reason |
| --- | --- | --- |
| GET /api/me without Authorization | 401 | Endpoint requires Authentication; HTTP Basic challenge. |
| Alice sends right password | 200 | Valid account, provider issues Authentication. |
| Alice sends wrong password | 401 | Credentials do not match. |
| Username absent from store | 401 | Cannot build Authentication; does not disclose whether user exists. |
| User locked/disabled/expired/password-expired | 401 | Manager account checks reject despite right password. |
| Viewer hits /api/orders | 403 | Authenticated yet missing orders:read. |
| Alice hits /api/admin | 403 | Missing ROLE_ADMIN. |
| POST to a GET-only path, missing CSRF token | Usually 403 | May be rejected by CsrfWebFilter before authorization. |
| Undeclared endpoint | 403 with denyAll and authenticated user | Fallback denial at the authorization layer. |

**401 does not always mean "wrong password".** It could be missing credentials, wrong username, locked account, or lookup service failure. **403 does not always mean "missing role"**; it could be a permission, CSRF, browser CORS, tenant/owner policy, or another WebFilter. Identify the exact rejecting layer before changing anything.

In production, avoid returning details like "account Alice is currently locked" or "account exists" to unauthenticated callers because it leaks information. Keep full reasons inside protected internal audit/logs with secrets masked.

### 12.1. Must you always return Mono.error when a user does not exist?

Do not apply a mechanical rule across every implementation. The key contract is **never returning null instead of a publisher**, and ensuring the authentication mechanism turns "no user" into a failure. In custom services, you may emit **Mono.empty()** or an appropriate error signal matching the contract/configuration in use; when wired into a real manager, test missing usernames to verify a 401 response and that no fallback identity is created.

Never use `switchIfEmpty(Mono.just(adminUser))` because that fails open. For data-source errors, handle errors intentionally and never masquerade as a valid user.

## 13. updatePassword() on MapReactiveUserDetailsService

Besides `findByUsername`, `MapReactiveUserDetailsService` also supports the **ReactiveUserDetailsPasswordService** contract with `updatePassword(UserDetails, String)` returning `Mono<UserDetails>`.

General semantics:

- Used to update stored passwords per the implementation.
- The new password string is passed per the storage system's contract; never casually pass a raw password into an API expecting an encoded hash.
- Requires authentication/authorization and a dedicated password-change flow (verifying old password or recovery/MFA channel per policy).
- Changes in the demo Map affect only the running process; it does not write to a database or sync across instances.

Illustrative example in a test with an **isolated instance**, without mutating the shared demo bean:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails account = User.withUsername("test-user")
    .password(encoder.encode("old-demo"))
    .roles("USER")
    .build();

MapReactiveUserDetailsService isolated =
    new MapReactiveUserDetailsService(account);

// Reactive test fragment: updatePassword takes the new encoded password.
Mono<UserDetails> updated = isolated.updatePassword(
    account, encoder.encode("new-demo")
);
~~~

Afterwards, subscribe/verify `updated` and look up `test-user` again to confirm the new password took effect. This snippet **is not a password-change endpoint**: it skips many production steps such as verifying the account owner, rate limiting, MFA, session/token invalidation, and auditing.

## 14. Common Mistakes When Moving from MVC to WebFlux

### 14.1. Importing synchronous UserDetailsService in WebFlux

You write a `UserDetailsService` bean expecting the reactive authentication manager to call `loadUserByUsername`. The reactive username/password contract uses **ReactiveUserDetailsService**. Check the actual server stack and manager in your configuration rather than guessing by similar interface names.

### 14.2. Changing return type to Mono while still calling blocking JDBC

`Mono.just(jdbcRepository.findUser(...))` still blocks the current thread. Use R2DBC or a proper blocking isolation strategy, and measure concurrency and timeouts.

### 14.3. Forgetting the matching PasswordEncoder

`UserDetails.getPassword()` holds a BCrypt hash yet the manager uses an incompatible encoder, leading to 401 or encoded-password errors. The demo explicitly calls `setPasswordEncoder(BCryptPasswordEncoder)` and tests both match and mismatch.

### 14.4. Inverting account status

`builder.accountLocked(true)` sets `isAccountNonLocked=false`. If you assign the DB value inverted, locked users can keep logging in. Test both `UserDetails` flags directly and the authentication path.

### 14.5. Assuming ROLE_USER includes orders:read

**hasRole("USER")** checks `ROLE_USER`; **hasAuthority("orders:read")** checks the exact action permission. A user with only a role does not automatically possess permissions. Never grant sensitive read permissions because a username is named "admin".

### 14.6. Demo Map accounts appearing in production

Never operate with hardcoded demo passwords, shared admin accounts, RAM-only user data, or missing auditing/rotation. Replace with proper identity sources and deployment controls.

### 14.7. Using MockMvc instead of WebTestClient

MockMvc is a tool for Spring MVC/Servlet. WebFlux should be tested with **WebTestClient**, using `reactor-test`/`StepVerifier` for direct publisher tests.

### 14.8. Disabling CSRF so POST works

CSRF depends on credential type and browser threat models; never turn it off reflexively when a POST returns 403. The demo uses only GET; when adding write operations, design CSRF explicitly and write appropriate tests.

### 14.9. Login succeeds yet API still returns 403

The manager already produced a valid `Authentication`, yet the authorization policy requires a different role/permission. Inspect **authorizeExchange** rules and authorities before changing user lookup logic.

### 14.10. Deleting/editing an account yet session or JWT still keeps old permissions

A `UserDetails` snapshot loaded at login does not auto-sync with existing sessions or JWTs. Design revocation/TTL/dynamic checks when locking users or revoking permissions.

### 14.11. Looking up usernames without tenant scoping

If multiple tenants share the same username, searching by username alone cannot identify the right account. Tenant routing must rely on a trusted source and designed authentication mechanism, never arbitrary headers.

### 14.12. Returning UserDetails directly from REST

`UserDetails` may contain password hashes and account statuses. Never serialize the raw object; return only the necessary DTO, typically username and suitable public fields.

### 14.13. Forgetting lazy/cancellation semantics of publishers

Calling `subscribe()` yourself and returning `Mono.empty()` can run authentication outside request timing and drop error propagation. Return the publisher for the manager/framework to subscribe, and define timeouts and error propagation.

### 14.14. Believing a JWT Resource Server always uses MapReactiveUserDetailsService

Bearer token validation typically relies on decoders/introspection rather than fetching accounts from a Map to compare passwords. When switching mechanisms, redesign account status checking and authority mapping accordingly.

## 15. From Demo to Production: Required Steps

A sensible progression:

1. **Identify server stack**: Spring MVC or WebFlux. If WebFlux, use `ServerHttpSecurity` and `ReactiveUserDetailsService` for username/password.
2. **Choose data source**: R2DBC database, reactive HTTP client, or LDAP/IdP with proper integration. Never accidentally put blocking JDBC on the event loop.
3. **Design account schema**: unique username/ID/tenant, password hash, authorities, enabled/locked/expiry, and a trusted time source.
4. **Configure PasswordEncoder**: standard hashing, migration, and tests for exact algorithm/version.
5. **Design user lifecycle**: registration, verification, password reset, lockout/rate limits, MFA, disabling, and auditing.
6. **Choose credential transport**: form login/session, Basic only over HTTPS, or OAuth2/OIDC/Bearer per real needs.
7. **Protect URLs and methods**: intentional `permitAll`, proper `hasRole`/`hasAuthority`, `denyAll` fallback, and client-appropriate CSRF/CORS.
8. **Protect object-level access**: users only read/edit data they are permitted; tenant/admin roles do not bypass domain policies by default.
9. **Test reactivity**: test timeouts/cancellations/errors, connection pools, password-hash CPU, and concurrent load.
10. **Test revocation**: when an account is locked/permissions change, do sessions/tokens remain valid, and for how long?
11. **Write negative tests**: missing username, wrong password, locked/disabled/expired, missing authority, cross-tenant, DB errors.
12. **Validate real deployment**: HTTPS, gateways, headers, secret management, Spring Security updates, and monitoring.

A demo account in `MapReactiveUserDetailsService` suffices to understand the API; going to production requires operational policies and data integrity, not just another finder implementation.

## 16. Self-Practice Exercises

**Exercise 1 — Compare contracts.** Write the two signatures **UserDetailsService.loadUserByUsername(String)** and **ReactiveUserDetailsService.findByUsername(String)**. Explain why return types differ while `UserDetails` stays shared.

**Exercise 2 — Build MapReactiveUserDetailsService.** Create two UserDetails `alice` and `admin` using the User builder, using `BCryptPasswordEncoder` to store hashes, then pass them to the varargs constructor. Write a `StepVerifier` checking username and `ROLE_ADMIN`.

**Exercise 3 — Locked status.** Build a UserDetails `locked` with `.accountLocked(true)`. What does `isAccountNonLocked()` return? Why is the right password insufficient to log in?

**Exercise 4 — Permissions.** Viewer has `ROLE_USER` yet lacks `orders:read`. What does `GET /api/orders` return under `hasAuthority("orders:read")`? Why can roles and permissions not be treated as synonyms?

**Exercise 5 — Check hashes.** Why must `getPassword()` be a hash, and how does `PasswordEncoder.matches(raw, hash)` differ from `raw.equals(hash)`? Write a wrong-password test.

**Exercise 6 — Blocking.** Analyze why `Mono.just(jdbcRepository.loadUser(username))` fails to make JDBC nonblocking. Propose an R2DBC solution and a bounded `boundedElastic` approach when forced to call blocking code.

**Exercise 7 — Test WebFlux.** Write `WebTestClient` tests for public 200, anonymous `/api/me` 401, viewer `/api/orders` 403, and admin `/api/admin` 200.

**Exercise 8 — Missing user.** A `ReactiveUserDetailsService` returns null when a username is missing. Fix it per the Reactor contract; test that the authentication manager rejects missing users.

**Exercise 9 — Password update.** Create an isolated `MapReactiveUserDetailsService` instance, update the encoded password in a test, and confirm the old password no longer works. Why should shared accounts not be mutated across integration tests?

**Exercise 10 — Tokens and sessions.** A user was just disabled in the database yet still holds a valid access token. Why might updating `UserDetails` not immediately revoke the token? Propose an appropriate strategy.

**Exercise 11 — SecurityContext.** Distinguish `ReactiveSecurityContextHolder.getContext()` from `ReactiveUserDetailsService.findByUsername(...)`. Which yields the current request's principal, and which looks up user info from the store?

**Exercise 12 — Multi-tenant.** Two tenants both have username `alice`. Design a safe user lookup factoring in a verified tenant, then test cross-tenant access denied.

### Summary Checklist

- **ReactiveUserDetailsService** is the interface for looking up `UserDetails` via **Mono<UserDetails>**.
- **MapReactiveUserDetailsService** is a Map-backed implementation suited for demos/tests; not a production database.
- **UserDetails** still holds username, password hash, authorities, and four account flags.
- **UserDetailsRepositoryReactiveAuthenticationManager** uses the reactive service + `PasswordEncoder` to check username/password.
- **ServerHttpSecurity and SecurityWebFilterChain** protect WebFlux servers; `HttpSecurity`/`SecurityFilterChain` are Servlet APIs.
- **Mono does not automatically turn blocking I/O into nonblocking**. Never call `block()` in WebFilters/Controllers.
- **ReactiveSecurityContextHolder** serves the current security context; it is not a user repository.
- **ROLE_USER differs from orders:read**; successful authentication does not grant access to every endpoint or object.
- **Disabled/locked/expired accounts** can be rejected even when the password is right.
- **StepVerifier tests publishers; WebTestClient tests WebFlux HTTP**. Do not use MockMvc to conclude a WebFlux chain works.
- **WebFlux does not automatically guarantee statelessness**. Sessions, JWT revocation, and data permissions need separate design.
- **Never use demo data or HTTP Basic without HTTPS** in real products.

## References

- [Spring Security — ReactiveUserDetailsService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): `findByUsername` contract returning `Mono<UserDetails>`.
- [Spring Security — MapReactiveUserDetailsService JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructors, `findByUsername`, and `updatePassword`.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `EnableWebFluxSecurity`, `ServerHttpSecurity`, and `SecurityWebFilterChain`.
- [Spring Security — UserDetailsRepositoryReactiveAuthenticationManager JavaDoc](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): `ReactiveAuthenticationManager` using `ReactiveUserDetailsService`.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): testing WebFlux security.
- [Spring Framework — Testing WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): `WebTestClient` and mocking reactive requests/responses.

**Version note:** This lab pins Spring Boot 3.3.6 and Spring Security 6.3.x to keep code and APIs consistent. When creating a new project, choose a currently supported Spring Boot/Spring Security branch and apply corresponding patches; verify packages, constructors, password encoders, and tests against your actual managed dependencies.

## Conclusion

**ReactiveUserDetailsService** provides a `Mono<UserDetails>` account-lookup contract tailored to the WebFlux pipeline, while **MapReactiveUserDetailsService** is a simple Map-backed implementation for quick experiments or testing. Both return `UserDetails` carrying username, password hash, authorities, and account status; yet **authentication** still belongs to `ReactiveAuthenticationManager` and `PasswordEncoder`, and **access permission** belongs to security policies and the domain layer. Understanding each layer's role, verifying genuinely nonblocking I/O sources, protecting credentials, and using `WebTestClient`/`StepVerifier` to test both accepted and rejected cases will help implement reactive user sources accurately and safely.
