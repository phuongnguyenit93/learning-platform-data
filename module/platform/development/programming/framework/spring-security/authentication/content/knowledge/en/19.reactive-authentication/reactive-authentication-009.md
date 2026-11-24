# Integrating Non-Blocking Data Stores and Controlling CPU-Intensive Work in Reactive Authentication

## 1. Objectives and Context

In Spring Security running on Spring WebFlux, receiving an HTTP request reactively is not enough on its own for an authentication system to perform well. On the login path there are usually two very different kinds of work:

1. **I/O to the identity store**: looking up accounts, lock/disabled flags, authorities, or session info. This work waits on a database, Redis, or a remote service. It requires APIs and drivers that support non-blocking I/O.
2. **CPU-intensive computation**: matching passwords with BCrypt, PBKDF2, or Argon2; verifying cryptographic signatures; or heavy transformations. This work may do zero I/O yet still occupy CPU long enough to stall the event loop if executed there by mistake.

This lesson focuses on **reactive authentication** in the Spring Security module: how to connect `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` to a reactive data store, draw clean boundaries for CPU work, bound concurrency, handle failures, and verify under realistic scenarios. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, and PostgreSQL via Spring Data R2DBC; the concepts apply equally to newer compatible releases.

Target outcome: trace `request → user lookup → password check → build Authentication`, identify which operations can block threads, and design a system that never trades authentication security for throughput.

## 2. Why “Mono” Does Not Automatically Mean Non-Blocking

Spring WebFlux typically serves many connections on a small number of event-loop threads. If an event loop is held for 200 ms by JDBC or heavy hashing, other requests sharing that thread experience latency spikes.

| Operation | Nature | Appropriate handling |
| --- | --- | --- |
| Querying users with Spring Data R2DBC + R2DBC driver | Asynchronous I/O, does not block while waiting for data | Keep inside `Mono`/`Flux` chain, no `block()` |
| Querying Redis with a reactive client | Asynchronous I/O | Use reactive APIs with proper timeouts and pool limits |
| BCrypt `matches`/`encode` | CPU-bound, synchronous API | Run on a CPU-oriented scheduler with bounded capacity |
| JDBC/JPA, `RestTemplate`, synchronous HTTP SDKs | Thread-blocking I/O | Prefer replacing with reactive drivers/clients; if not yet possible, temporarily isolate on `boundedElastic` |
| `Mono.just(repository.findByUsername(name))` if repository is blocking | Executes blocking call **at Mono creation time** | Wrong: wrapping in `Mono` does not turn the call into non-blocking |
| `mono.block()` or `Future.get()` in a WebFlux handler | Synchronous waiting | Never use on reactive execution threads |

`subscribeOn` shifts where the synchronous work wrapped inside a publisher runs; it **does not turn** JDBC into an asynchronous driver. `publishOn` switches threads for downstream operators; do not move the whole pipeline onto a thread pool just for one CPU step. Choose the smallest boundary containing the synchronous computation.

Logical diagram:

```text
HTTP request
  → Spring Security WebFilter (WebFlux)
  → ReactiveAuthenticationManager
  → ReactiveUserDetailsService
  → R2DBC repository ── nonblocking I/O ── PostgreSQL
  → PasswordEncoder.matches(...) ── CPU scheduler
  → Authentication / 401 response if credentials are invalid
```

Never conflate a data store failure with a wrong password: an unavailable database is an infrastructure error, not proof the user mistyped their password.

## 3. Integrating a User Store with Spring Data R2DBC

### 3.1. Prerequisites

A Spring Boot application with dependency management configured can use these dependencies in `build.gradle` (this is a **dependencies snippet**, not the full build script):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Minimal PostgreSQL schema:

```sql
CREATE TABLE app_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    role VARCHAR(64) NOT NULL
);
```

Development configuration in `src/main/resources/application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/security_lab
```

Supply connection credentials via `SPRING_R2DBC_USERNAME` and `SPRING_R2DBC_PASSWORD` environment variables. The database and table must be created beforehand; R2DBC does not guarantee schema creation itself. Run migrations like Flyway/Liquibase via a proper initialization process rather than running blocking JDBC migrations on request paths. Never commit connection passwords or real user passwords into configuration files.

### 3.2. Entity and Reactive Repository

The Java files below live in `src/main/java/com/example/authdemo/` under package `com.example.authdemo`.

**`AppUser.java`**:

```java
package com.example.authdemo;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("app_users")
public record AppUser(
        @Id Long id,
        String username,
        @Column("password_hash") String passwordHash,
        boolean enabled,
        String role) {
}
```

**`AppUserRepository.java`**:

```java
package com.example.authdemo;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface AppUserRepository
        extends ReactiveCrudRepository<AppUser, Long> {

    Mono<AppUser> findByUsername(String username);
}
```

`findByUsername` is a derived query method in Spring Data. `Mono<AppUser>` emits at most one account; completes empty when missing; and emits `onError` on driver or connection failures. The `UNIQUE` constraint on `username` prevents duplicate usernames. Never call `.block()` in repositories, services, or filters.

### 3.3. Mapping Records to Spring Security Objects

**`DatabaseReactiveUserDetailsService.java`**:

```java
package com.example.authdemo;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AppUserRepository repository;

    public DatabaseReactiveUserDetailsService(AppUserRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return repository.findByUsername(username)
                .map(account -> User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities(account.role())
                        .disabled(!account.enabled())
                        .build());
    }
}
```

Explanation:

- `ReactiveUserDetailsService` only loads data used for authentication; it **does not verify** passwords itself and must never build an authenticated `Authentication`.
- `passwordHash` must be an encoded value compatible with `PasswordEncoder` (e.g., `{bcrypt}...` with `DelegatingPasswordEncoder`), never plaintext.
- The example stores one authority `ROLE_USER`. `authorities(...)` uses the string verbatim; `roles("USER")` is what prepends `ROLE_`. For multi-role systems, design join tables/reactive queries or proper mapping.
- The `enabled` flag is mapped onto `UserDetails` so the authentication manager enforces account status checks. Never turn every infrastructure error into `Mono.empty()`.
- When using Redis, a `ReactiveUserDetailsService` can combine a reactive Redis client with R2DBC, provided TTL, invalidation, and cache sensitivity are clearly defined. Avoid caching raw passwords/tokens or stale lock states for too long.

## 4. Offloading Password Verification from the Event Loop

### 4.1. Choosing the Right Spring Security Components

`UserDetailsRepositoryReactiveAuthenticationManager` pairs `ReactiveUserDetailsService` with `PasswordEncoder` to verify username/password. Spring Security supports configuring a scheduler for password encoding/matching because it is CPU-intensive. You can use the framework's default scheduler; the example below creates a dedicated CPU pool to measure and isolate impact across workloads.

**`SecurityConfig.java`**:

```java
package com.example.authdemo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean(destroyMethod = "dispose")
    Scheduler authCpuScheduler() {
        int workers = Math.max(1, Runtime.getRuntime().availableProcessors() / 2);
        return Schedulers.newParallel("auth-password", workers);
    }

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder,
            @Qualifier("authCpuScheduler") Scheduler cpuScheduler) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setScheduler(cpuScheduler);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Key takeaways:

1. R2DBC lookups remain reactive I/O; do not wrap the entire `findByUsername` call in `boundedElastic`.
2. The manager already schedules password verification at the right spot using the configured scheduler; **do not wrap** the entire manager in `subscribeOn` as a blind optimization.
3. `Schedulers.newParallel(name, workers)` allocates a fixed thread pool for CPU tasks. The worker count formula is a starting example, **not** optimal for every machine; tune it based on resources and real measurements.
4. `@Bean(destroyMethod = "dispose")` releases the custom scheduler on shutdown. Never call `dispose()` on Reactor's shared built-in schedulers.
5. `DelegatingPasswordEncoder` recognizes algorithm prefixes like `{bcrypt}`, supporting future algorithm upgrades. Never use `NoOpPasswordEncoder` or store plaintext.

A small controller to verify the flow: **`MeController.java`**.

```java
package com.example.authdemo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(user -> "Authenticated: " + user.getName());
    }
}
```

**`AuthDemoApplication.java`**:

```java
package com.example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }
}
```

The Java snippets above are separate, complete files in the same package; with the dependencies, PostgreSQL/schema, and configuration listed earlier, they wire the HTTP Basic → reactive authentication manager → R2DBC repository → password verification flow. HTTP Basic is only appropriate over HTTPS-protected connections in real deployments. The example intentionally adds no registration endpoint or default accounts.

### 4.2. Hashing During Account Creation or Password Change Is Also CPU-Heavy

When provisioning accounts, compute the hash **before** the reactive save. The sample service shares the dedicated scheduler; production may separate provisioning pools from login verification pools to protect login capacity.

**`AccountProvisioningService.java`**:

```java
package com.example.authdemo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class AccountProvisioningService {

    private final AppUserRepository repository;
    private final PasswordEncoder encoder;
    private final Scheduler cpuScheduler;

    public AccountProvisioningService(
            AppUserRepository repository,
            PasswordEncoder encoder,
            @Qualifier("authCpuScheduler") Scheduler cpuScheduler) {
        this.repository = repository;
        this.encoder = encoder;
        this.cpuScheduler = cpuScheduler;
    }

    public Mono<AppUser> createUser(String username, String rawPassword) {
        return Mono.fromCallable(() -> encoder.encode(rawPassword))
                .subscribeOn(cpuScheduler)
                .flatMap(hash -> repository.save(
                        new AppUser(null, username, hash, true, "ROLE_USER")));
    }
}
```

Here `Mono.fromCallable` defers hashing until subscription, and `subscribeOn(cpuScheduler)` moves only that synchronous computation onto the CPU scheduler. `flatMap` continues with a reactive `save`, without calling `block()`. This illustrates **CPU work plus reactive writes**, not a full signup API: production needs input validation, password policies, provisioning authorization, anti-abuse limits, duplicate-username error handling, and zero logging of passwords/hashes.

## 5. Controlling Concurrency and Resources

**Non-blocking does not mean infinite capacity.** Each login request can consume significant CPU matching BCrypt/Argon2; R2DBC is also bounded by connection pools and database capacity.

| Bottleneck | Symptoms | Mitigation |
| --- | --- | --- |
| Event loop blocked | Even lightweight endpoints spike in latency, throughput drops | Remove `block()`, JDBC, synchronous HTTP calls in WebFlux; move CPU work off the event loop |
| CPU hashing overloaded | Login p95/p99 climbs; high CPU; scheduler queues grow | Bound concurrency / rate limit, benchmark real load, use a dedicated scheduler |
| R2DBC connection pool exhausted | Longer connection wait times or timeouts | Size pool to DB capacity; set timeouts and monitor active/pending connections |
| DB slow or unreachable | Query errors; logins fail to complete | Timeouts, circuit breakers where appropriate, controlled infrastructure error responses |
| Queues grow rapidly under login attacks | Exhausts CPU and memory despite non-blocking I/O | Rate limit per IP/account, brute-force defenses, admission control before hashing |

Distinguish three important scheduler types:

- `Schedulers.parallel()` / `Schedulers.newParallel(...)`: suited for **non-blocking CPU-bound** work. Thread count is fixed, yet tasks can still queue; capping workers **does not automatically cap queued requests**.
- `Schedulers.boundedElastic()`: intended for **genuinely blocking legacy code** needing temporary isolation (JDBC, synchronous file I/O, blocking SDKs), with its own thread and queue bounds. It is not the standard way to speed up pure CPU computation.
- `Schedulers.immediate()`: runs on the current thread; unsuitable for heavy cryptographic work on the event loop.

Example isolating a blocking adapter *solely as a bridge during migration*:

```java
Mono<LegacyAccount> findLegacyAccount(String username) {
    return Mono.fromCallable(() -> legacyJdbcDao.findByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is an illustrative method only, not a standalone program: `LegacyAccount` and `legacyJdbcDao` belong to the legacy system. It avoids blocking the event loop, **yet the database call itself remains blocking**, occupying threads and bounded by pools. Prefer migrating to reactive clients/drivers whenever feasible.

With `Flux.flatMap(mapper, concurrency)`, the `concurrency` parameter helps bound concurrency within one stream; it **does not** enforce a global login limit because each HTTP request has its own pipeline. Global limits require rate limiters, bulkheads, semaphores, or bounded queues at the right layer, with explicit overload rejection policies. Do not wait until hashing has already started before checking quotas.

Timeouts guard waiting time; cancelling a reactive publisher **does not guarantee** that an in-flight CPU operation or already-dispatched database query aborts immediately. Check driver semantics and enforce resource limits at the source.

## 6. Data Flow, Errors, and Security

An authentication request typically moves through these states:

1. The WebFlux security filter reads username/password from HTTP Basic (or a corresponding login mechanism).
2. The reactive authentication manager calls `ReactiveUserDetailsService.findByUsername`.
3. The repository emits the record, completes empty if missing, or emits a DB error.
4. The manager checks account status and compares the password hash with `PasswordEncoder` on the CPU scheduler.
5. If valid, the manager returns an authenticated `Authentication`; Spring Security uses it for authorization and supplies the principal downstream.

| Scenario | Meaning / behavior |
| --- | --- |
| Username not found | Authentication fails; avoid leaking whether the user exists |
| Password mismatch | Authentication fails, typically HTTP 401 with HTTP Basic |
| Account `enabled=false` | Reject authentication; never bypass status checks |
| DB timeout / connection loss | Infrastructure error; do not turn every error into `BadCredentialsException` |
| CPU overloaded | Enforce limits and shed load cleanly; never grow thread pools unboundedly |
| Successful login | Grant authorities solely from verified data; never trust client-sent roles |

Specifically in WebFlux, Spring Security binds security info to the **Reactor Context**. Never rely on traditional `ThreadLocal` or assume a request always stays on one thread. When reading authentication inside a service, use `ReactiveSecurityContextHolder.getContext()` in the reactive chain. Never emit passwords or hashes into logs, metrics, tracing, exception messages, or API responses.

Additional defenses are needed: TLS, rate limiting, failed-login monitoring, reasonable temporary lockout policies, secret management, tuning password encoder cost to CPU capacity, and password/hash rotation workflows. A `{bcrypt}`-prefixed value is a stored hash, not plaintext and not reversible encryption.

## 7. Running and Verifying

### 7.1. Preparing Data

- Start PostgreSQL, create database `security_lab` and table `app_users` as above, and configure connection environment variables.
- Create a test account via a valid provisioning path calling `AccountProvisioningService.createUser("alice", "demo-secret")` or an admin tool using the same `PasswordEncoder`. In the DB, `password_hash` must start with a prefix like `{bcrypt}`. Never insert `"demo-secret"` directly into `password_hash`.
- In a Spring Boot app with the Gradle wrapper and Boot plugin, run `./gradlew bootRun` (PowerShell/Windows: `.\gradlew.bat bootRun`). On Linux/macOS, ensure the wrapper script is executable.
- Use illustrative credentials in development environments only.

Once a user exists, call the endpoint (using HTTPS outside local development):

```bash
curl -i http://localhost:8080/me
curl -i -u 'alice:wrong-password' http://localhost:8080/me
curl -i -u 'alice:demo-secret' http://localhost:8080/me
```

The first two requests should be rejected (typically `401 Unauthorized`). The final request succeeds if the account exists, is enabled, and the hash matches, returning HTTP 200 with body:

```text
Authenticated: alice
```

That is a **conditional expected result**, not stdout captured from a live system in this article.

### 7.2. Unit-Testing the Authenticator Without a Database

`src/test/java/com/example/authdemo/AuthenticationManagerTest.java` tests password-matching logic independently of R2DBC; integration tests with a real database or Testcontainers cover the persistence tier.

```java
package com.example.authdemo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthenticationManagerTest {

    @Test
    void acceptsCorrectPasswordAndRejectsIncorrectPassword() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails user = User.withUsername("alice")
                .password(encoder.encode("demo-secret"))
                .roles("USER")
                .build();

        ReactiveUserDetailsService users = name ->
                "alice".equals(name) ? Mono.just(user) : Mono.empty();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);

        StepVerifier.create(manager.authenticate(
                        new UsernamePasswordAuthenticationToken(
                                "alice", "demo-secret")))
                .assertNext(authentication ->
                        assertTrue(authentication.isAuthenticated()))
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new UsernamePasswordAuthenticationToken(
                                "alice", "wrong-password")))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
```

This test proves the manager accepts or rejects passwords against hashes. It does not prove JDBC/R2DBC non-blocking behavior; integration tests and runtime observation are needed for that.

### 7.3. Load and Operations Checklist

Verify under controlled load by varying concurrent login requests and monitoring:

- **Event loop**: whether lightweight endpoint latency degrades during login bursts; whether any blocking operations are detected on event-loop threads.
- **CPU**: utilization, hash queue/processing latency; sensitivity to cost factor and worker count changes.
- **R2DBC pool**: active/pending connections, wait times, timeouts, connection errors, and DB query latency.
- **Logins**: success/failure rates, p50/p95/p99, rate limits, infrastructure errors vs. bad credentials; zero secrets in telemetry.
- **Failure cases**: nonexistent user, wrong password, disabled account, DB down, slow DB, traffic spikes. Never let DB errors become successful authentications or be masked as wrong passwords.

Use proper instrumentation such as Micrometer/Actuator, safe tracing, and BlockHound where supported in test environments. BlockHound can catch blocking calls on non-blocking threads, but **does not** replace CPU benchmarks or stress testing.

## 8. Common Mistakes and Fixes

| Mistake | Problem | Fix |
| --- | --- | --- |
| `Mono.just(jdbcDao.loadUser(name))` | JDBC executes before the Mono is created, blocking the caller thread | Use R2DBC; if still legacy, isolate with `fromCallable(...).subscribeOn(boundedElastic)` |
| `repository.findByUsername(name).block()` | Breaks the reactive chain and may error on event-loop threads | Return `Mono`, compose with `map`/`flatMap` |
| Calling `passwordEncoder.matches` directly inside `map` on event loop | Hashing can monopolize CPU for too long | Use reactive authentication manager with an appropriate scheduler |
| Sending the entire pipeline onto `boundedElastic` | Does not solve CPU saturation; adds thread/context switching | Isolate CPU work on a CPU scheduler; keep DB reactive |
| Growing workers unboundedly when slow | CPU contention and swelling queues | Measure capacity, bound concurrency/rate, enforce overload policies |
| Using `onErrorResume(e -> Mono.empty())` for all repo errors | Masks DB outages as “user not found” | Classify errors; handle infra failures cleanly without failing open |
| Storing unprefixed passwords or using `{noop}` | Incompatible with encoder or weakens security | Strong hashing via `DelegatingPasswordEncoder`, verify cost and upgrade plan |
| Reading Authentication via `ThreadLocal` after scheduler hops | Context lost or reads stale user | Use `ReactiveSecurityContextHolder`/Reactor Context |
| Bounding only `flatMap(concurrency)` in one stream | Does not bound total independent HTTP requests | Add application-level rate limiters / bulkheads |

## 9. Practice Exercises

1. Replace the example repository with reactive Redis or an identity service supporting asynchronous I/O. Identify where to place timeouts, where to map data to `UserDetails`, and how to distinguish “not found” from upstream errors.
2. Measure latency of `/me` alongside an unauthenticated endpoint under load. Temporarily move password matching onto the event loop in a test environment to observe the degradation, then restore the proper scheduler. Never deploy the blocking variant to production.
3. Design login throttling under heavy wrong-password traffic. Explain why capping CPU threads without capping the queue can still exhaust resources.
4. Add PostgreSQL/Testcontainers integration tests covering existing, disabled, and nonexistent users plus database failures; verify zero `block()` calls on request paths.

## 10. Takeaways

- **Data stores**: pick truly reactive clients/drivers (e.g., R2DBC) and compose with `Mono`/`Flux`; never use `block()`.
- **Passwords and heavy computation**: even without I/O, keep them off the event loop; let the manager use an appropriate CPU scheduler and benchmark capacity.
- **Resource bounds**: DB pools, worker counts, queues, timeouts, rate limits, and admission control are distinct layers of protection.
- **Accurate security semantics**: invalid credentials, locked accounts, and infrastructure failures must stay distinct; never log credentials or grant access when upstreams fail.

References for checking APIs and execution models: Spring Security WebFlux Security (https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html), `UserDetailsRepositoryReactiveAuthenticationManager` Javadoc (https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html), Spring Data R2DBC (https://docs.spring.io/spring-data/relational/reference/r2dbc.html), Reactor Schedulers (https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).