# Limits of Synchronous JDBC, JPA, and LDAP and Integration Patterns at Blocking Boundaries

> **Context:** Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux, Project Reactor, and Java 17+. This lesson focuses on **user lookup, password verification, and directory access** when a reactive system still has to interact with synchronous JDBC, Spring Data JPA, or LDAP/JNDI. The goal is defining explicit blocking boundaries rather than pretending a synchronous API becomes non-blocking simply by wrapping it in `Mono`.

## 1. The Problem: One Blocking Call Can Stall Many Requests

WebFlux is built around asynchronous, non-blocking I/O. A small number of event-loop threads can handle many connections because they **do not wait** for one SQL or LDAP request to finish before doing other work. By contrast:

- `JdbcTemplate`, JDBC `Connection`, and `ResultSet`: wait synchronously for the driver to execute SQL and return rows.
- JPA `EntityManager`, Spring Data JPA `JpaRepository`, classic Hibernate ORM: perform queries, flushes, lazy loading, and transactions in an imperative model; DB I/O remains blocking.
- Spring LDAP/JNDI `LdapTemplate` and synchronous LDAP clients: can wait on connects, binds, searches, and directory server responses.
- `PasswordEncoder.matches(...)` with BCrypt/Argon2/PBKDF2: significant CPU work; it does not necessarily *wait on I/O*, yet still should not occupy the event loop for long.

Anti-pattern example:

```java
@GetMapping("/api/users/{name}")
Mono<String> user(@PathVariable String name) {
    UserRecord record = jdbcUserDao.findBlocking(name); // BLOCKING immediately
    return Mono.just(record.displayName());
}
```

This is only an **illustrative snippet** (incomplete imports/classes). `findBlocking` runs **before the `Mono` is returned**, on the thread invoking the handler—typically a reactive processing thread. If the DB slows down, that thread is held; other requests can slow down too.

A second mistake pattern:

```java
Mono<UserRecord> user = Mono.just(jdbcUserDao.findBlocking(name));
```

`Mono.just(...)` does not defer the argument call: Java evaluates `findBlocking(name)` **first**, then puts the result into the publisher. The `Mono` type does not make the inner operation non-blocking.

**Correct mindset:** to use a blocking library, push **the blocking operation itself** into a bounded zone with suitable threads, concurrency/queue caps, and timeouts; keep authorization checks and Reactor composition outside that zone.

## 2. Distinguishing Three Resource Types in Reactive Security

| Component | Common APIs | Inherently Non-Blocking? | What Must Be Managed |
|---|---|---|---|
| JDBC | `DataSource`, `JdbcTemplate`, JDBC drivers | **No** | Blocked threads, connection pool, query/statement timeouts |
| Spring Data JPA | `JpaRepository`, `EntityManager`, Hibernate | **No** | Threads, thread-bound transactions, EntityManager, lazy loading |
| Synchronous LDAP | `LdapTemplate`, JNDI, LDAP bind/search APIs | **No** | Connect/socket timeouts, pools, TLS, filter injection |
| Spring Security reactive | `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` | **Reactive interfaces** | Implementations can still block if written improperly |
| R2DBC | `ConnectionFactory` / reactive DB drivers | **Non-blocking by design** | Drivers, reactive pools, query limits, and reactive transactions |
| Password hashing | `PasswordEncoder.matches` | Usually **CPU-bound** | CPU budget, password hash cost, appropriate scheduler |

Never assume: "WebFlux + JPA = reactive database". JPA/JDBC do not become non-blocking just because Spring Boot selects the WebFlux HTTP stack.

### A Service's Return Type Does Not Determine the Operation's Nature

A method returning `Mono<User>` can be merely a **wrapper** around JDBC. What matters is whether synchronous calls run on the event loop, whether work is dispatched to an appropriate scheduler, and whether queued work is bounded.

Conversely, **using JDBC/JPA in a WebFlux application is not strictly forbidden**. It can be a sensible transition strategy while a database driver or repository layer cannot yet be replaced; it carries clear costs, throughput limits, and operational requirements.

## 3. Blocking-Boundary Pattern in Project Reactor

Standard pattern when *a synchronous operation may block*:

```java
Mono<UserRecord> result =
    Mono.fromCallable(() -> legacyUserDao.load(username))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a **code fragment**; it requires the corresponding DAO, model, and imports. Three key points:

1. `Mono.fromCallable(...)` defers executing the `Callable` until subscription. Creating the publisher does not invoke the DAO.
2. `subscribeOn(Schedulers.boundedElastic())` moves source subscription onto a scheduler designed for blocking I/O, keeping the `Callable` off the event loop.
3. If the DAO throws an exception, `Mono` emits `onError`; if the `Callable` returns `null`, `Mono.fromCallable` completes empty. For user lookups, deliberately distinguish "not found" via an explicit exception or `Mono.empty()`.

Same pattern with a void-returning `Runnable`:

```java
Mono<Void> operation =
    Mono.fromRunnable(() -> blockingAuditStore.write(entry))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
```

`Mono.fromCallable` fits when returning `UserDetails`, DTOs, or lookup results. Never call `block()` or manual `subscribe()` to "force a result" inside WebFlux controllers or services.

### Why `subscribeOn` Instead of Only `publishOn`?

Placing `publishOn` **after** a source that already called a blocking method eagerly cannot undo that earlier block. `subscribeOn` attaches to a lazy source so subscription and the `Callable` run on the chosen scheduler. Illustrative comparison:

```java
// RIGHT: JDBC is inside Callable and runs on the blocking scheduler
Mono.fromCallable(() -> jdbcUserDao.load(username))
    .subscribeOn(Schedulers.boundedElastic())
    .map(UserRecord::displayName);

// WRONG: JDBC runs immediately when creating the Mono
Mono.just(jdbcUserDao.load(username))
    .publishOn(Schedulers.boundedElastic());
```

**`subscribeOn` does not make database I/O asynchronous:** it simply uses another thread to **wait** for the synchronous call to finish. Thread counts, connections, and queues remain real limits.

## 4. Configuring Schedulers, Connection Pools, and Load Limits

`Schedulers.boundedElastic()` is Reactor's shared scheduler for potentially blocking tasks. Its thread count and queued tasks are **bounded**; it is not an infinite thread pool. For authentication paths needing isolation from other blocking tasks, you can provide a dedicated scheduler:

```java
@Bean(destroyMethod = "dispose")
Scheduler jdbcAuthScheduler() {
    return Schedulers.newBoundedElastic(
        4,        // max 4 worker threads for this scheduler
        100,      // queued task cap per scheduler configuration
        "jdbc-auth");
}
```

This is a configuration method and **will not run standalone** outside a `@Configuration` class with `Bean`, `Scheduler`, and `Schedulers` imported. `destroyMethod="dispose"` releases the scheduler when the application context closes. The numbers 4 and 100 are **illustrative values**; size them to query latency, DB pool size, and system limits rather than copying them as production settings.

There is no one-size-fits-all formula. For instance, if a JDBC pool has only 4 connections while hundreds of logins arrive concurrently, raising threads from 4 to 100 merely creates more threads waiting on the pool; it does not make the DB 25× faster.

### Limits That Should Work Together

- **Connection pool:** HikariCP maximum pool size, connection timeout, broken-connection validation.
- **Thread pool/scheduler:** worker count, queue cap, overload policy. A dedicated auth scheduler keeps JDBC logins from exhausting the shared scheduler used by other tasks.
- **Bulkhead/semaphore:** if concurrent requests to LDAP/DB must be capped, enforce it at the adapter with bounded queues and explicit overload responses.
- **Statement/query timeouts and LDAP connect/read timeouts:** set them at the driver/client level, not solely as an outer reactive timeout.
- **Monitoring:** lookup p50/p95/p99 latency, active/pending pool connections, thread queues, timeouts, failed authentications, LDAP errors.
- **Login limits:** rate limiting / brute-force defenses, backoff, MFA, or risk-appropriate lockout policies; never rely solely on thread counts.

When a blocking task holds 1 thread for its entire wait duration, concurrency capacity is tied to runnable threads and available connections. **Reactor backpressure neither expands a JDBC pool automatically nor rejects all HTTP request bursts by itself.**

### Timeout and Cancellation Do Not Automatically Stop JDBC Immediately

`Mono.timeout(Duration.ofSeconds(3))` makes the caller stop waiting and emits a timeout signal, yet a synchronous JDBC/LDAP operation waiting on a socket or driver **is not guaranteed to stop immediately**. Some drivers respond to interrupts/cancellations; others do not. Always configure connection, statement, and socket timeouts to prevent thread/connection leaks after clients disconnect. Never attach unbounded `retry()` to user-store or LDAP errors: it can amplify load against a struggling backend.

## 5. Integration Boundary into Spring Security Reactive

Spring Security WebFlux consumes reactive interfaces:

```java
public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
```

The snippet omits package/imports for readability. **The `ReactiveUserDetailsService` interface does not promise every implementation is non-blocking**. When the backend is synchronous JDBC/JPA/LDAP, selecting an appropriate scheduler is the implementation/adapter's responsibility.

A standard integration pattern:

```text
HTTP Basic / form login
           |
           v
SecurityWebFilterChain
           |
           v
ReactiveAuthenticationManager
           |
           v
ReactiveUserDetailsService.findByUsername()
           |
           +--> Mono.fromCallable(...)
                    .subscribeOn(boundedElastic / dedicated blocking Scheduler)
                           |
                           v
                   Synchronous JDBC / JPA / LDAP
                           |
                           v
                   UserDetails (hash + authorities)
           |
           v
PasswordEncoder.matches(...) -> authentication result
           |
           v
Authorization -> controller/service
```

**Do not wrap the whole flow merely by putting `@Async` on a DAO** and letting Spring Security guess the result. `@Async` typically returns `Future`/`CompletableFuture` with a separate executor system; if used, convert properly into a Publisher with bounds and error propagation. In Spring Security reactive, `ReactiveUserDetailsService` is the direct, testable integration point.

### Password Hashing Has a Different Cost Type Than I/O

- **Reading a user hash** from synchronous JDBC/JPA/LDAP is potentially **I/O-blocking**; offload it to `boundedElastic`.
- **Verifying BCrypt/Argon2** is **CPU-intensive** work; enforce concurrency caps and keep it off the event loop.
- Spring Security's `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` to find the user, then verifies password and account status. It supports `setPasswordEncoder(...)` and `setScheduler(...)` to tune the scheduler for password-related work; the implementation's default targets CPU work. The password-matching scheduler **does not replace the scheduler used for JDBC I/O**.

Never use `NoOpPasswordEncoder` or store plaintext passwords to "speed up" production. Choose an appropriate salted, cost-configured hashing algorithm with a policy-driven hash upgrade workflow.

## 6. Runnable Demo: WebFlux + Spring Security + JDBC/H2 at the Blocking Boundary

This demo intentionally uses **synchronous JDBC**, without pretending it is non-blocking. To avoid external MySQL/PostgreSQL setup on a learning machine, the backend is in-memory H2 via `JdbcTemplate`. The app seeds a demo user and an endpoint protected by HTTP Basic. Every JDBC lookup triggered by the authentication flow runs on the resource-bounded `jdbc-auth` scheduler. Passwords use BCrypt hashes.

Illustrative versions: **Spring Boot 3.3.13**, Java 17+, Gradle compatible with Spring Boot 3.3.

### 6.1 Structure

```text
jdbc-boundary-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/boundary/BlockingBoundaryApplication.java
  src/main/java/demo/boundary/BlockingUserLookup.java
  src/main/java/demo/boundary/SecurityConfiguration.java
  src/main/java/demo/boundary/ApiController.java
  src/test/java/demo/boundary/BlockingBoundaryTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'jdbc-boundary-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.boundary'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` provides the reactive web server; `spring-boot-starter-jdbc` provides `JdbcTemplate` and HikariCP. Adding the JDBC starter **does not make JDBC reactive**. `spring-boot-starter-web` is omitted to avoid mixing web stacks while learning.

### 6.2 Starting the App and Seeding Users in H2

**src/main/java/demo/boundary/BlockingBoundaryApplication.java**

```java
package demo.boundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class BlockingBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingBoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner seedUser(JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    username VARCHAR(80) PRIMARY KEY,
                    password_hash VARCHAR(100) NOT NULL,
                    enabled BOOLEAN NOT NULL
                )
                """);

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM app_users WHERE username = ?",
                Integer.class, "reader");

            if (count != null && count == 0) {
                jdbc.update("""
                    INSERT INTO app_users(username, password_hash, enabled)
                    VALUES (?, ?, ?)
                    """, "reader", encoder.encode("dev-only-password"), true);
            }
        };
    }
}
```

Notes:

- `ApplicationRunner` runs at **startup** (not during request processing); synchronous JDBC here does not block the request-handling event loop like the Section 1 anti-pattern.
- In-memory H2 is not a production user store.
- `"dev-only-password"` is a fixed credential **for localhost demo only**; production must load secrets from a proper secret manager, never hardcode them in source.
- Passwords are stored as BCrypt hashes in `password_hash`; never store plaintext in the DB.

### 6.3 Synchronous-Only JDBC DAO

**src/main/java/demo/boundary/BlockingUserLookup.java**

```java
package demo.boundary;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Repository;

@Repository
public class BlockingUserLookup {

    private final JdbcTemplate jdbc;

    public BlockingUserLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public UserDetails loadByUsername(String username) {
        List<UserDetails> users = jdbc.query(
            """
            SELECT username, password_hash, enabled
            FROM app_users
            WHERE username = ?
            """,
            (rs, rowNum) -> User.withUsername(rs.getString("username"))
                .password(rs.getString("password_hash"))
                .disabled(!rs.getBoolean("enabled"))
                .roles("READER")
                .build(),
            username);

        if (users.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }
        return users.get(0);
    }
}
```

This DAO is **intentionally imperative**: `loadByUsername` returns `UserDetails`, without creating a `Mono` or picking threads itself. Separating it makes the adapter's blocking boundary visible. The SQL uses `?` parameters bound via `JdbcTemplate`, never concatenating request usernames into the query, preventing SQL injection.

`UsernameNotFoundException` signals an authentication failure; never turn every database error, timeout, or LDAP outage into "user not found", as that masks infrastructure incidents. Never return SQL details or user-enumeration hints to clients.

### 6.4 ReactiveUserDetailsService Adapter and Authentication Manager

**src/main/java/demo/boundary/SecurityConfiguration.java**

```java
package demo.boundary;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean(destroyMethod = "dispose")
    Scheduler jdbcAuthScheduler() {
        return Schedulers.newBoundedElastic(4, 100, "jdbc-auth");
    }

    @Bean
    ReactiveUserDetailsService users(
            BlockingUserLookup lookup,
            @Qualifier("jdbcAuthScheduler") Scheduler scheduler) {

        return username -> Mono
            .fromCallable(() -> lookup.loadByUsername(username))
            .subscribeOn(scheduler);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private")
                    .hasRole("READER")
                .anyExchange().authenticated())
            .httpBasic(basic ->
                basic.authenticationManager(authenticationManager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Important details:

1. `lookup.loadByUsername(username)` **is inside `Mono.fromCallable`**, so it does not run when constructing the publisher.
2. `subscribeOn(scheduler)` sits directly after the source, ensuring JDBC lookups run on the `jdbc-auth` pool upon subscription instead of tying up the Netty event loop.
3. The scheduler is bounded to avoid spawning unlimited blocking workers. `@Qualifier` guarantees the right scheduler is injected.
4. `ReactiveUserDetailsService` is an application-supplied bean, so Spring Boot does not generate a random `user` account. The demo user is created by `ApplicationRunner`.
5. `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` to fetch the hash and `PasswordEncoder` to compare passwords. It does not magically turn the DAO non-blocking.
6. `httpBasic(basic -> basic.authenticationManager(...))` wires the manager into Basic authentication **explicitly**, without relying on auto-config guesses once a custom chain is defined.
7. `hasRole("READER")` checks the `ROLE_READER` authority built by the DAO; `anyExchange().authenticated()` requires login for remaining requests.
8. `formLogin(...disable())` is solely so the API demo cleanly shows HTTP 401; UI apps using cookies/sessions need proper form and CSRF policies.
9. Password hash matching incurs CPU cost and is handled by the manager's own scheduler per implementation; not every operator after `subscribeOn` is forced to stay on the JDBC scheduler.
10. To tighten login request/capacity caps further, add queues/concurrency limits/rate limits aligned with backend budgets; the scheduler is **one control layer**, not the whole solution.

If you implement `ReactiveUserDetailsService` yet **accidentally write**:

```java
return username -> Mono.just(lookup.loadByUsername(username));
```

then the query still runs immediately when `findByUsername` is called on the current thread. That is a very common legacy-integration bug.

### 6.5 Controller and Authenticated Requests

**src/main/java/demo/boundary/ApiController.java**

```java
package demo.boundary;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint(Principal principal) {
        return Mono.just("hello " + principal.getName());
    }
}
```

There is no need to call JDBC again inside the controller just to get the name: the authentication manager already built the principal when HTTP Basic succeeded. Querying per-user data still requires object/tenant authorization checks, not merely reading `principal.getName()`.

### 6.6 Running and Verifying with curl

In the project directory (JDK 17+ and compatible Gradle):

```bash
gradle bootRun
```

If a Gradle wrapper is present, use `./gradlew bootRun`; Windows: `gradlew.bat bootRun`. From another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i -H "Accept: application/json" \
    http://localhost:8080/api/private

# curl CLI will prompt for password; enter dev-only-password
curl -i -u reader http://localhost:8080/api/private

# Enter a wrong password to test the negative case
curl -i -u reader http://localhost:8080/api/private
```

The last two commands have identical syntax; **results depend on the password entered** at the prompt. On PowerShell, if `curl` is an alias, use `curl.exe`.

| Request | Expected HTTP | Explanation |
|---|---|---|
| `GET /api/public` without credentials | 200, body `public` | Intentionally public URL |
| `GET /api/private` without credentials | 401 | Unauthenticated |
| `GET /api/private` with `reader` / `dev-only-password` | 200, body `hello reader` | JDBC finds user, BCrypt matches, has `ROLE_READER` |
| `GET /api/private` with wrong password | 401 | Authentication failed |
| `GET /api/private` with nonexistent user | 401 | Does not disclose specific authentication details |

Do not predict exact Gradle stdout because it varies by environment, JDK version, plugins, and logs; what matters is HTTP status/body. If the database failed to initialize, H2 failed to connect, or the app is down, inspect logs rather than assuming every error is a 401.

## 7. Automated Testing at the Security + JDBC Boundary

**src/test/java/demo/boundary/BlockingBoundaryTest.java**

```java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BlockingBoundaryTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsPublic() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateRouteNeedsAuthentication() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void jdbcBackedUserCanAuthenticate() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello reader");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIsRejected() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("missing", "anything"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

The complete project has **5 test methods**, expected to pass when dependencies download and the runtime matches. The tests verify integration wiring, not empirical proof that the event loop is never blocked. Dedicated scheduler/latency/thread-contention tests and production load monitoring are needed to evaluate limits.

### Checking the Thread in an Additional Experiment

Temporarily instrument the DAO locally:

```java
String currentThread = Thread.currentThread().getName();
System.out.println("JDBC lookup thread = " + currentThread);
```

This snippet is purely for checking the scheduler; never log usernames/passwords, credentials, or sensitive SQL parameters. Thread names normally contain `jdbc-auth` as named by `Schedulers.newBoundedElastic`. **Never rely on thread names as a security condition**: they are a diagnostic tool, not a public API contract. Do not keep `System.out.println` in a production DAO.

## 8. Integrating Spring Data JPA at Proper Transaction Boundaries

JPA/`EntityManager` remains blocking. With ORM comes an extra wrinkle: **imperative JDBC/JPA transactions and persistence contexts are typically bound to the current thread**. Spring `@Transactional` with `PlatformTransactionManager` also uses thread-bound state. Therefore, never start a transaction on the event loop, hop a query to another worker thread, and assume the transaction automatically follows.

### 8.1 Right Pattern: Transactional Imperative Service Called from an Adapter

Suppose the app already has `JpaRepository<AccountEntity, Long>`:

```java
@Service
public class BlockingAccountService {
    private final AccountRepository repository;

    public BlockingAccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AccountView load(long accountId) {
        var entity = repository.findById(accountId)
            .orElseThrow(() -> new AccountNotFoundException(accountId));

        // Map needed data inside the transaction,
        // including lazy associations if needed and permitted.
        return new AccountView(entity.getId(), entity.getDisplayName());
    }
}
```

This is an **architectural illustration snippet** requiring application entity, repository, `AccountView`, and `AccountNotFoundException` types. Crucially, `load(...)` returns a **plain DTO**, not a `Mono`; `PlatformTransactionManager` wraps all JPA work inside the method invoked via Spring's proxy.

Reactive adapter in a **separate bean**:

```java
@Service
public class ReactiveAccountGateway {
    private final BlockingAccountService legacy;
    private final Scheduler blockingScheduler;

    public ReactiveAccountGateway(
            BlockingAccountService legacy,
            @Qualifier("jdbcAuthScheduler") Scheduler blockingScheduler) {
        this.legacy = legacy;
        this.blockingScheduler = blockingScheduler;
    }

    public Mono<AccountView> load(long accountId) {
        return Mono.fromCallable(() -> legacy.load(accountId))
            .subscribeOn(blockingScheduler);
    }
}
```

This snippet is also illustrative and needs imports. The right flow is: scheduler worker **invokes through the Spring proxy bean** → transaction opens on the worker thread → repository queries, lazy mapping, and commit/rollback complete in the same call → only a DTO returns to Reactor. Never pass an entity with uninitialized lazy associations out of the transaction to be read on another thread.

**Self-invocation warning:** calling a `@Transactional` method via `this.load(...)` inside the same bean can bypass the Spring AOP proxy, causing transactions not to apply as expected. Use a separate bean or `TransactionTemplate` when boundaries must be guaranteed.

### 8.2 Wrong Pattern

```java
// Anti-pattern: imperative transaction does not automatically follow
// a Mono chain created and executed on another thread.
@Transactional
public Mono<AccountView> load(long accountId) {
    return Mono.fromCallable(() ->
        repository.findById(accountId)
            .map(e -> new AccountView(e.getId(), e.getDisplayName()))
            .orElseThrow())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Problem: the JPA code executes **at subscription time**, potentially on another thread, while proxies/transaction managers and `Mono`-returning methods follow separate rules. With JDBC/JPA `PlatformTransactionManager`, do not rely on `@Transactional` on a reactive-publisher-returning method to maintain transactions; define an **imperative DTO-returning method** as in Section 8.1.

### 8.3 When Should You Choose R2DBC Over JPA/JDBC?

If request flows are primarily database I/O, require high concurrency, and drivers/databases support R2DBC, Spring Data R2DBC with `R2dbcEntityTemplate`/`ReactiveCrudRepository` may fit better. However:

- R2DBC **is not an adapter that "automatically turns JPA reactive"**; entity mapping, cascades, lazy loading, query models, and transactions differ from JPA.
- If existing JPA/ORM mappings are needed, weigh migration cost against real gains; keeping a blocking boundary can be a well-managed transitional step.
- Reactive transactions normally use `ReactiveTransactionManager` and Reactor Context, **differing** from `PlatformTransactionManager` + thread-local. Never mix transaction managers and expect them to span the same unit of work.
- Small queries still need indexes, timeouts, pooling, and authorization checks. Switching drivers never fixes poor schemas or queries.

## 9. Synchronous LDAP: Search, Bind, and Identity Verification

LDAP typically participates in two operations: searching users/groups in a directory and verifying credentials. Synchronous LDAP/JNDI implementations can block when opening connections, binding, searching, reading group memberships, or when the server drops connections.

### 9.1 Adapter at the Blocking Boundary

If the application already has a properly built `BlockingLdapIdentityService` using `LdapTemplate`/JNDI:

```java
public Mono<UserDetails> findByUsername(String username) {
    return Mono.fromCallable(() -> ldapIdentityService.lookup(username))
        .subscribeOn(ldapScheduler);
}
```

This is an **integration snippet**, not a complete LDAP application: you must define `ldapIdentityService`, configure the context source/LDAP server, construct `UserDetails` from results, and supply a bounded scheduler. When a flow involves both LDAP bind and group lookup, treat them as **one synchronous operation** with timeouts, sessions, and resource cleanup inside the adapter. Never call `LdapTemplate.search(...)` directly from the event loop and merely wrap the result in `Mono.just(...)`.

### 9.2 LDAP Requires Dedicated Safeguards

- **Network timeouts:** connect timeout, read timeout, search time limits, max returned entries, and referral policies per client/server.
- **TLS:** LDAP over TLS (LDAPS or properly configured/supported StartTLS) with certificate/hostname verification; never send passwords over unprotected connections.
- **Filter injection:** never concatenate unescaped input into `"(uid=" + username + ")"` in an LDAP search filter. Use library-provided builders/escaping such as an LDAP query builder.
- **Access privileges:** bind/search accounts use least privilege; never log passwords, sensitive full DNs, tokens, or private attributes.
- **Pooling and concurrency:** blocking threads, directory connection pools, bounded retries/circuit breakers.
- **Failure modes:** an unresponsive directory is an infrastructure incident, not a wrong password; distinguish internal logs from safe client-facing messages.

Mapping LDAP groups to Spring Security authorities must follow explicit policy—for example, granting `ROLE_STAFF` only when a trusted group genuinely matches. Never take group values from client-supplied headers or payloads.

### 9.3 Use a Truly Asynchronous LDAP Client When Available

If your organization has an appropriate asynchronous LDAP library, a dedicated identity gateway, or another protocol with a non-blocking client, you can design a **truly** reactive adapter. Still verify that the library uses real async I/O rather than merely returning `CompletableFuture` backed by a blocking thread pool. Changing the return type alone does not prove non-blocking execution.

## 10. Timeouts, Cancellation, Errors, and Access Safety

### 10.1 Never Turn Infrastructure Errors into Misleading 401s

In the auth flow:

| Condition | Interpretation | What to Do |
|---|---|---|
| User does not exist | Identity lookup returned nothing | Reject authentication without revealing username existence |
| Password mismatch | Wrong credentials | Reject authentication; rate-limit password guessing |
| User disabled/locked | Account not permitted to log in | Manager checks account flags |
| JDBC pool exhausted | Infrastructure cannot keep up | Record controlled metrics/logs, fail closed, recover resources |
| LDAP timeout/unavailable | Directory network/server failure | Never allow anonymous access to private data; alert on incident |
| Publisher timed out | Request waited too long | Cancel subscription and bound lingering blocking work; do not assume JDBC stopped |

**Fail closed** means never granting access when identity cannot be verified. Yet never lump all backend failures into "wrong password" in internal logs/metrics; that hides outages and can trigger spurious lockouts or wrong operational responses.

### 10.2 Timeouts Have Two Layers

Suppose a lookup needs a deadline:

```java
Mono<UserDetails> user = Mono.fromCallable(() -> dao.loadByUsername(username))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
```

This is an **illustrative code snippet**; import `Duration` and pick values matching real SLOs. Reactor's timeout bounds how long the subscriber waits; it does not replace JDBC statement timeouts, connection acquisition timeouts, or LDAP connect/read timeouts. Never attach infinite retries to login failures caused by a slow DB.

### 10.3 Cancellation Must Not Break Transaction Boundaries

When a client closes a connection, the subscription may cancel, yet a synchronous JDBC/JPA/LDAP call already in flight can still hold a thread/connection. Operations need real timeouts and clean resource release at the JDBC/JPA/Spring-managed boundary. For mutating transactions, HTTP cancellation is not a guaranteed "remote rollback" protocol; define commit/rollback behavior, idempotency, and auditing in the service.

### 10.4 Security Context and Transaction Context Differ

Spring Security reactive typically passes `SecurityContext` via **Reactor Context**. Meanwhile, JDBC/JPA `@Transactional` with `PlatformTransactionManager` uses **ThreadLocal** binding connections/EntityManagers to the active transaction thread. Never assume:

- "Because Reactor Context flows across `publishOn`, JDBC transactions flow across too."
- "Because `@Transactional` is declared, a `Mono.fromCallable` created inside the method belongs to the same imperative transaction."
- "Because the username is in the security context, the repository automatically enforces per-record permissions."

Keep transaction boundaries distinct, and enforce resource permissions using the verified identity.

## 11. Choosing a Strategy by System Profile

| Situation | Recommendation |
|---|---|
| Project has stable JDBC/JPA and moves HTTP to WebFlux | Keep DAO/service imperative; add a `Mono.fromCallable + subscribeOn` adapter with pools/timeouts/metrics |
| App is primarily SQL queries with a suitable R2DBC driver | Evaluate migrating data access to R2DBC; avoid wrapping JDBC long-term under high load |
| Auth backed by legacy LDAP/JNDI | Offload synchronous search/bind to a dedicated scheduler with secure timeouts and pools; consider an external IdP |
| Must keep multi-step JPA transactions | Enclose the entire unit of work inside one imperative `@Transactional` method invoked from a worker thread |
| Need JWT/Identity Provider support | Prefer proper resource server/JWT validation, while still enforcing token checks, network policies, and authorization |
| High auth load, CPU-heavy password hashing | Separate CPU budgets for hashing from I/O budgets for DB/directory; apply rate limits, bulkheads, latency tracking |
| Unsure where current users come from | Inspect `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` and the active filter chain; never guess from dependencies |

A system can combine reactive HTTP and blocking repositories in a controlled way. However, if most requests wait on blocking I/O, WebFlux's concurrency advantage shrinks; if there is no hard requirement for the reactive stack, an MVC/Servlet application with proper threading is also worth comparing. Architecture choices depend on I/O profiles, operational resources, and whole-system needs—not the "reactive" or "non-reactive" label alone.

## 12. Common Mistakes and Fixes

| Anti-pattern | Why It Is Dangerous | Fix |
|---|---|---|
| `Mono.just(jdbc.query(...))` | JDBC already ran blocking before creating Mono | `Mono.fromCallable(...).subscribeOn(blockingScheduler)` |
| Calling sync JPA/LDAP inside `map` on event loop | Can hold the event loop while waiting | Offload the operation onto a worker |
| Using `Schedulers.parallel()` for network-waiting JDBC/LDAP | Scheduler is meant for CPU work, not long I/O waits | `boundedElastic` or dedicated blocking scheduler |
| Using `boundedElastic` with unmonitored queues | Growing wait queues raise latency and overload | Add bounds, metrics, rate limits/bulkheads |
| Adding threads to cure a small DB pool | Only creates more threads waiting on connections | Tune queries, pools, and concurrency to budgets |
| Assuming `Mono.timeout` always aborts SQL | Sync JDBC can keep running after timeout | Set driver/statement/socket timeouts |
| `@Transactional` method returning `Mono` wrapping JPA | Imperative transactions do not span subscriptions/threads | Wrap JPA in an imperative `@Transactional` service, call via proxy on worker |
| Returning JPA entities with lazy fields to reactive chains | Post-transaction lazy loading can fail or add blocking I/O | Map fully to DTOs inside the transaction |
| Using `ReactiveSecurityContextHolder` instead of tx manager | Security context is distinct from resource/transactions | Manage transactions using the backend's proper manager |
| Putting hand-coded BCrypt on the event loop | CPU-intensive hashing spikes latency for other requests | Use proper managers/schedulers/CPU bounds |
| Storing plaintext passwords or using NoOp encoder | Credential exposure risk | Use salted, appropriately costed hashes |
| Concatenating user input into LDAP filters | LDAP injection | Use builders/escaping, input validation, least privilege |
| Using `permitAll()` on private routes when backend auth fails | Loses security during outages | Fail closed with clear policies and observability |
| Calling `subscribe()` manually for lookup in controllers | Detaches error/cancel/context flows; responses race auth | Return publishers and let the framework subscribe |
| Logging passwords, Basic Authorization, or JDBC secrets | Exposes credentials | Mask/redact logs and restrict log access |
| Testing only successful logins | Misses open endpoints, timeouts, brute-force flaws | Test anonymous, wrong passwords, overload, outages, and data authorization |

## 13. Implementation Checklist and Exercises

### 13.1 Checklist

1. Audit every I/O library: which JDBC, JPA, or LDAP clients actually block? Never equate `Mono` with async I/O.
2. Locate any `Mono.just(dao.call())`, `map(x -> dao.call())`, or queries called from controllers or the event loop.
3. Place **the entire synchronous call** inside `fromCallable/fromRunnable` with `subscribeOn` onto a clearly budgeted scheduler.
4. Size DB/LDAP pools alongside schedulers; set queue/concurrency caps and test under login bursts.
5. For JPA/transactions, call an imperative `@Transactional` bean via proxy on a worker thread and return a DTO.
6. Configure BCrypt/Argon2/PBKDF2 with proper hashing and CPU budgets; never use plaintext passwords.
7. Set timeouts at HTTP/publisher **and** driver/statement/socket levels, understanding cancellation limits.
8. Separate bad credentials from DB/directory failures in internal metrics/logs without leaking details to clients.
9. Write negative tests: missing credentials, wrong password, nonexistent user, disabled user, wrong role/tenant.
10. Monitor event-loop blocking, blocking scheduler utilization, JDBC pool pending counts, LDAP latency, and auth error rates.
11. If capacity limits are exceeded, evaluate R2DBC, an async IdP, or architectural changes backed by data.

### 13.2 Exercises

1. Run the demo and explain why `JdbcTemplate` still blocks even though HTTP endpoints return `Mono`.
2. Switch the adapter from `fromCallable` to `Mono.just(lookup.loadByUsername(...))`, point out when the DB query executes, and restore the right version.
3. Log the thread name inside the DAO (without logging credentials), verify it contains `jdbc-auth`, and re-measure when using `Schedulers.boundedElastic()`.
4. Add two new tests: a user with `enabled = false` and a user lacking `ROLE_READER`; verify the private endpoint denies both.
5. Suppose the Hikari pool shrinks to 2 connections while 20 logins arrive concurrently. Describe where queues form and why merely adding threads cannot fix a DB bottleneck.
6. With JPA, compare an imperative `@Transactional public AccountView load()` running completely on a worker against a deferred `@Transactional Mono<AccountView> load()`; explain transaction/lazy-loading risks.
7. For LDAP, list connect/read/search timeouts, TLS settings, filter escaping, and how to fail closed when the directory disconnects.
8. Write an outage test scenario: shut down the DB mid-login, verify clients cannot reach private resources, and ensure metrics distinguish backend errors from wrong passwords.
9. Name three scenarios where migrating to R2DBC or an IdP makes more sense than continuing to wrap a blocking backend; explain migration costs.

## Summary

**Synchronous JDBC, Spring Data JPA, and LDAP/JNDI can all hold threads while waiting on I/O**. In WebFlux, use `Mono.fromCallable(...)` or `Mono.fromRunnable(...)` with `subscribeOn(Schedulers.boundedElastic())` or a dedicated blocking scheduler to draw clear boundaries; wrapping **does not turn sync libraries non-blocking**. In Spring Security, place JDBC/JPA/LDAP lookups inside a `ReactiveUserDetailsService` adapter, let `ReactiveAuthenticationManager` verify password hashes, and protect routes with `SecurityWebFilterChain`. For JPA, keep imperative transactions inside a synchronous call running on a worker thread. Combine driver timeouts, connection pools, queue caps, rate limiting, monitoring, and negative tests so this boundary operates safely.

## Official Documentation

- Project Reactor — FAQ: How Do I Wrap a Synchronous, Blocking Call?: https://projectreactor.io/docs/core/3.6.0/reference/faq.html
- Spring Security 6.3 — ReactiveUserDetailsService API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — UserDetailsRepositoryReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Boot 3.3 — WebFlux Security Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Framework — Declarative transaction implementation, ThreadLocal, and ReactiveTransactionManager: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — JDBC connections and thread-bound connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
