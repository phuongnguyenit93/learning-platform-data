# Measuring Authentication Latency, Password Hashing Cost, and Account Lookups in Spring Security

## 1. Why Can Authentication Be Slow Even When the Endpoint Is Very Simple?

A `POST /login` request may return only a redirect or a short JSON response, yet on the backend it often performs many steps:

- Reading the request, handling cookies/CSRF, selecting the `SecurityFilterChain` and authentication filter.
- Fetching user details from a DB/LDAP/identity service; waiting on the connection pool and network.
- Checking whether the account is enabled/locked/expired.
- Running `PasswordEncoder.matches(...)` with bcrypt/PBKDF2/scrypt/Argon2; work that is **intentionally CPU- or memory-intensive** to resist offline password cracking.
- If the policy changes, potentially running `upgradeEncoding(...)` and `encode(...)` and writing the new password hash.
- Creating the `Authentication`, running extra checks, persisting the session/security context, auditing the login, and redirecting or issuing a token.
- Traversing proxies/networks/browsers; if an IdP/OIDC is involved, additional requests/redirects occur.

If you only read `http.server.requests` and see p95 rising, you do not yet know whether the cause is **password hashing**, **the DB**, **the Hikari pool**, **lockout/rate limiting**, **session persistence**, **the proxy**, or **the IdP**. This lesson presents how to measure each layer, interpret the results, design dashboards, and use findings to optimize **without weakening security**.

Primary context: Spring Boot 3.x + Spring Security 6.5 Servlet (Spring MVC), Java 17+, Micrometer/Actuator, and a relational database. Similar principles apply to WebFlux, LDAP, and SSO, though the hooks and mechanisms differ.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **request latency**, **authentication-manager latency**, **account-lookup latency**, **password verification/encoding latency**, and **session/audit latency**.
2. Record `count`, `total time`, p50/p95/p99, histograms, throughput, and error rates **using low-cardinality tags**.
3. Configure Spring Boot Actuator + Micrometer and recognize Spring Security's default observations.
4. Analyze the latency of `UserDetailsService.loadUserByUsername`, `PasswordEncoder.matches`/`encode`, and the DB pool.
5. Benchmark bcrypt/PBKDF2/Argon2 work factors **on real hardware**, without choosing a weak algorithm merely to hit a fast number.
6. Write tests to verify instrumentation, compare before–after behavior, and avoid leaking raw usernames/passwords/tokens.

## 2. Defining Latency Layers: Do Not Conflate Them

A simplified diagram for password-based login:

```text
Client
 |
 |  T_network + browser + TLS + load balancer
 v
Ingress / Reverse proxy
 |
 |  T_queue + servlet container thread
 v
Spring Security FilterChain
 |
 |--- CSRF / request extraction / basic rate-limit
 |
 |--- AuthenticationManager.authenticate()
 |      |
 |      +--- UserDetailsService.loadUserByUsername()
 |      |      +--- Connection pool wait
 |      |      +--- Network DB / LDAP
 |      |      +--- SQL execution + row mapping
 |      |
 |      +--- account status checks
 |      |
 |      +--- PasswordEncoder.matches(raw, encoded)
 |      |      +--- CPU / memory work factor
 |      |
 |      +--- optional breached password check
 |      +--- optional upgradeEncoding + encode + updatePassword
 |
 |--- session/security context persist, audit, success handler
 |
 v
HTTP response
 |
 v
Client
```

Useful definitions:

| Suggested Metric | Boundary | Includes | Excludes |
| --- | --- | --- | --- |
| `http.server.requests` | Server receives request → returns response per Spring MVC instrumentation | Request-related filter/controller handling per config | Client time, DNS, and network before server |
| `spring.security.authentications` | Observation around authentication attempt | Manager/provider work depending on version/config | Not automatically the full HTTP response |
| `app.auth.manager` | Application wrapper around `AuthenticationManager.authenticate` | Lookup + verify + provider logic | Typically excludes TLS and post-login session writer |
| `app.auth.account.lookup` | `UserDetailsService.loadUserByUsername` or DB repository | Measured lookup call duration | Not always pure SQL execution; may include pool wait/cache |
| `app.auth.password.matches` | `PasswordEncoder.matches` | Credential hashing/comparison (CPU/memory) | Excludes DB lookup when instrumented properly |
| `app.auth.password.encode` | `PasswordEncoder.encode` | New hash during registration/reset/rehash | Not necessarily present on normal logins |
| `app.auth.postlogin` | App success handler / session+audit (define boundaries clearly) | Components after provider success | Do not equate provider success with durable browser session |
| `jdbc.connections.*` / `hikaricp.*` | Pool management gauges/timers | Active/idle/waiting/maximum and pool-specific metrics | Does not by itself identify which SQL query is slow |

An HTTP request might be `GET /api/orders` using a session cookie and **never** call the password encoder. On the other hand, a `POST /login` with a password may genuinely spend hundreds of milliseconds in the hash function. Therefore, never take the average across **all HTTP requests** to represent login latency.

### Defining "Successful Login" Precisely

- `AuthenticationManager.authenticate` returning an `Authentication` may not yet mean the session is persisted or the redirect has completed.
- An `AuthenticationSuccessEvent` reflects an authentication-layer event, which may not correspond to every interactive user login.
- Logins can fail with `BadCredentialsException`, `LockedException`, missing MFA, DB timeouts, or IdP errors; dashboards need **stable, low-cardinality categories**, never exception messages or raw usernames in tags.
- If HTTP Basic is enabled and every request sends credentials, authentication may run **on every request** rather than only at login; measure by authentication mechanism and traffic mix.

## 3. Statistics to Measure and Read Properly

| Statistic | Question Answered | Common Pitfall |
| --- | --- | --- |
| `count` / throughput | How many attempts/s? | Mixing logins and JWT validations into one series |
| `mean` = total/count | Average cost | Hides queueing and long tails |
| `p50` | Typical half of requests | Fails to show slow-request experience |
| `p95` | 95% of requests stay below this threshold | P95 is meaningless with too few samples |
| `p99` | Slowest tail at 99% | Very noisy at low traffic |
| `max` | Peak within the stats window | Micrometer max may reset across time windows |
| `failure rate` | Rate of auth/infrastructure failures | A wrong password is not always a "system error" |
| `CPU / allocation / GC` | Password hashing or hot server? | Low average CPU can still queue on individual cores |
| `pool wait / active / pending` | Waiting for DB connections? | Fast SQL can still bottleneck on the pool |
| `DB query duration` | Is account lookup slow? | Depends on caches, indexes, network, and locks |

### p95/p99 Do Not Simply Add Together

Suppose four logins have lookup times of 8/12/9/30 ms and hash verification times of 120/135/115/150 ms. The p95 of lookup is 30 ms, and the p95 of verification is 150 ms; **the p95 of the total** is not necessarily 180 ms. Percentiles of two distributions cannot simply be summed to obtain the percentile of the sum.

Reason: the slowest runs of the two phases can belong to **two different requests**, alongside queueing, session persistence, instrumentation overhead, and sampling choices. Compute total p95 only from **measured end-to-end totals**, then use tracing/segment timers to locate the cause.

**Nearest-rank:** for N sorted samples, percentile p lies approximately at index `ceil(p*N)-1` (0-based). Metric backends may use different histograms/estimators, so small samples in a Java demo differ from Prometheus `histogram_quantile` interpolation.

### Choosing Aggregation Windows

- 5 minutes usually captures recent fluctuations, but with only a few logins/hour it may lack enough samples.
- Dashboards should display **sample count alongside p95/p99**; suppress p99 alerts when N is too low.
- Separate peak/off-peak hours and deployment revisions to avoid false conclusions when traffic mix shifts.
- Read latency alongside throughput, saturation, error rate, and CPU/memory; higher latency can stem from queueing rather than slower code.

## 4. Default Observations in Spring Security 6.5

Spring Security supports **Observability** when an `ObservationRegistry` is present in the Spring context. The 6.5 documentation describes spans including:

- `spring.security.http.requests`: tracks total filter chain duration.
- `spring.security.http.chains.before` / `.after`: entry/exit activity of security filters.
- `spring.security.http.secured.requests` and `.unsecured.requests`: secured vs. unsecured processing.
- `spring.security.authentications`: `AuthenticationManager` execution.
- `spring.security.authorizations`: authorization decision step.

These observations are very helpful for comparing **authentication vs. authorization vs. request processing**. However:

1. **An observation/trace span does not automatically mean every default span becomes a Prometheus histogram with the exact same name.** That depends on `ObservationHandler`, the meter registry, version config, and exporter.
2. An `ObservationAuthenticationManager` can wrap a manager to create observations; do not assume every `AuthenticationManager` emits metrics automatically in apps with custom wiring.
3. Do not assume the `spring.security.authentications` span name automatically separates `loadUserByUsername` from `matches`; to split those deeply, instrument the specific components.
4. If you add custom Micrometer wrappers around the authentication manager, avoid double-counting metrics/overhead from nested instrumentation. Label custom metrics clearly as **app-defined** rather than claiming they are framework defaults.

Source: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/observability.html

## 5. Enabling Spring Boot Actuator + Micrometer with Proper Scope

In a Spring Boot 3.x project with plugins/dependencies configured, add to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // When using Prometheus as the backend:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Example `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"

  metrics:
    distribution:
      percentiles-histogram:
        "app.auth.manager": true
        "app.auth.account.lookup": true
        "app.auth.password.matches": true
      slo:
        "app.auth.manager": 100ms,250ms,500ms,1s

  observations:
    http:
      server:
        requests:
          name: http.server.requests
```

Explanation:

- `spring-boot-starter-actuator` brings Micrometer/Actuator integration into the application; the Prometheus exporter requires the corresponding registry.
- `/actuator/metrics` lets you discover meter names and drill down; `/actuator/prometheus` is the exporter endpoint when enabled by modules/config.
- `percentiles-histogram` opts into publishing histogram buckets for percentile computation in supported backends; it does not display p95 automatically unless queried properly.
- `slo` configures buckets around target thresholds; 100–1000 ms thresholds are **examples**, not performance guarantees or Spring requirements.
- `http.server.requests` is the meter supported by Spring Boot/Spring MVC observations; **certain filter exceptions** and custom response paths may not be categorized as expected if handled before MVC instrumentation.
- This YAML **does not create** the three `app.auth.*` meters by itself. They only appear after code actively instruments them and **at least one observation has been recorded**.

### Securing Actuator Is Mandatory

By default, Spring Boot exposes only the health endpoint over HTTP; once metrics/prometheus are enabled, **block public Internet access** using network/firewall controls or a dedicated security chain. If the app defines a custom `SecurityFilterChain`, do not assume Spring Boot still blocks all actuator endpoints automatically.

Never open `management.endpoints.web.exposure.include: "*"` to the Internet just so Grafana can scrape metrics. Minimize sensitive metadata, restrict roles/binding/management ports, and monitor requests to actuator.

Local verification when authorized:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/app.auth.manager
curl -s http://localhost:8080/actuator/prometheus
```

These commands are only for localhost or over a trusted admin channel; if endpoints are protected, supply monitoring credentials **without leaving them in shell history or logs**.

## 6. Micrometer Timer: Instrumenting AuthenticationManager

The goal is to measure `AuthenticationManager.authenticate(...)` accurately and **record outcomes even when an exception is thrown**. The following is a Java class for a Spring Security 6.x application, not a standalone Java program.

File `src/main/java/demo/metrics/TimedAuthenticationManager.java`:

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class TimedAuthenticationManager
        implements AuthenticationManager {

    private final AuthenticationManager delegate;
    private final Timer success;
    private final Timer invalidCredentials;
    private final Timer internalError;

    public TimedAuthenticationManager(
            AuthenticationManager delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.success = create(registry, "success");
        this.invalidCredentials = create(registry, "auth_failure");
        this.internalError = create(registry, "server_error");
    }

    private static Timer create(MeterRegistry registry, String result) {
        return Timer.builder("app.auth.manager")
                .description("Time spent in application authentication manager")
                .tag("result", result)
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        long start = System.nanoTime();
        Timer target = internalError;

        try {
            Authentication outcome = delegate.authenticate(request);
            if (outcome != null && outcome.isAuthenticated()) {
                target = success;
            } else {
                // Some AuthenticationManagers may abstain (return null).
                target = internalError;
            }
            return outcome;
        } catch (AuthenticationException ex) {
            target = invalidCredentials;
            throw ex;
        } finally {
            target.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }
}
```

**Measurement scope:** the timer wraps `authenticate`; it includes lookups and KDFs actually executed by the provider, excluding work before/after the manager. The `auth_failure` outcome groups `AuthenticationException`s (bad credentials, locked, disabled…); if finer breakdown is needed, use a small set of **fixed allowlisted labels** rather than exception messages.

**Wiring caution:** make sure to wrap **the actual manager invoked by formLogin/HTTP Basic/custom auth filters**. Merely declaring a bean with the same name does not guarantee every authentication flow passes through the wrapper. In apps with multiple `SecurityFilterChain`s, each chain may use a different manager. Circular wrapping (injecting a manager where the wrapper itself is the manager bean) causes circular dependencies. Design an explicit factory/delegate and run integration tests confirming exact recording counts.

**Never store `Timer.Sample` globally:** each request/call must hold its own sample or its own monotonic start time as above. Use `System.nanoTime()`/the `MeterRegistry` clock for elapsed time; never use `Instant.now()` for durations because wall-clock time can jump.

### Recording Exception Branches Accurately

The `finally` block ensures a sample is recorded when:

- Wrong password/login fails with `AuthenticationException`.
- Account is locked, disabled, or expired.
- Delegate throws an unexpected runtime error/DB failure.
- Provider returns null when abstaining.

If you record the timer only after `return`, most failure attempts **produce no metric**, making dashboards think the system is super fast while under attack or suffering a DB outage.

### Testing with SimpleMeterRegistry

The following test snippet **runs only with JUnit/Mockito and Spring Security**:

```java
@Test
void successShouldIncrementSuccessTimer() {
    var registry = new SimpleMeterRegistry();
    AuthenticationManager fake = request ->
            UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
    AuthenticationManager timed =
            new TimedAuthenticationManager(fake, registry);

    Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "example-test-only");
    Authentication result = timed.authenticate(input);

    assertTrue(result.isAuthenticated());
    assertEquals(1L, registry.get("app.auth.manager")
            .tag("result", "success").timer().count());
    assertEquals(0L, registry.get("app.auth.manager")
            .tag("result", "auth_failure").timer().count());
}
```

Additional imports: `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.core.authority.SimpleGrantedAuthority`, `org.springframework.security.core.Authentication`, `java.util.List`, and JUnit 5. This is a **project test snippet**; it cannot run directly with `java` without the classpath/dependencies.

In production, you can rely on Spring Security's **native observations** instead of a wrapper if those metrics give enough detail; when lookup/hashing breakdown is needed, instrument the exact components and avoid double-counting.

## 7. Measuring UserDetailsService.loadUserByUsername: User Data in DB/LDAP

`DaoAuthenticationProvider` typically calls `UserDetailsService.loadUserByUsername` to fetch `UserDetails` and the hash, unless cached or handled by a custom provider. The method duration consists of:

```text
lookup duration
 = cache lookup / transformation
 + pool acquisition wait
 + network time DB/LDAP
 + query/LDAP operation
 + row mapping / object construction
 + optional retries
```

On a cache hit, the method may take only microseconds/milliseconds. On a cache miss, duration increases. Therefore, measure **two distinct checkpoints** when needed:

1. `app.auth.account.lookup`: wrapper around `UserDetailsService.loadUserByUsername`, reflecting caller-perceived time.
2. `app.auth.db.query`: timer/trace at the repository/`JdbcTemplate`/`DataSource` instrumentation layer, reflecting query cost (optionally splitting pool wait and execution if the driver/proxy supports it).

Example wrapper:

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class TimedUserDetailsService implements UserDetailsService {

    private final UserDetailsService delegate;
    private final Timer lookupTimer;

    public TimedUserDetailsService(
            UserDetailsService delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.lookupTimer = Timer.builder("app.auth.account.lookup")
                .description("Duration of user lookup during authentication")
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        long start = System.nanoTime();
        try {
            return delegate.loadUserByUsername(username);
        } finally {
            lookupTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }
}
```

This is **a decorator**; it must replace the exact `UserDetailsService` used by the provider without circular wiring. To split success/failure, pre-register two timers/outcome tags and choose the target in `catch`/`finally`. Never create a new meter name based on raw username. The example above measures `UsernameNotFoundException` as well, because `finally` always executes.

### Why Observe the Pool?

Spring Boot Actuator provides `jdbc.connections.*` instrumentation for DataSources and `hikaricp.*` for HikariCP when properly integrated. Monitor:

- Are `active` connections approaching `max`?
- Are `idle` connections dropping to 0?
- Are `pending/waiting` threads rising?
- Is `connection acquisition` wait rising during peak hours?
- Are DB CPU, lock waits, network RTT, and query execution rising?

**Connection pool metrics do not replace query profiling.** A full pool can be a symptom of long transactions or slow queries, which means raising `maximumPoolSize` does not always help. If the DB is already saturated, opening more connections can slow it down further.

### Designing the Account Query Properly

A typical application query:

```sql
SELECT user_id, normalized_username, password_hash,
       enabled, account_locked, credentials_expired
FROM app_users
WHERE normalized_username = :username;
```

- Create a **unique index** on the lookup key matching collation/case-normalization and tenant if applicable.
- Read exactly one account; avoid full table scans and joins unnecessary for authentication.
- Use prepared statements/bind parameters; never concatenate raw usernames into SQL.
- Avoid N+1 queries for authorities/roles/tenants. If loading multiple relations, measure every SQL statement or design explicit fetches.
- Never log `password_hash`/raw passwords, tokens, or session cookies; when debugging SQL with parameter logging, redact sensitive params.
- If the account does not exist, do not reveal that to attackers through messages, statuses, or starkly different timing.

### Query Plans and Actual Duration

- `EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL reveals indexes/scans/IO, but **executes** the query; use safely in permitted environments and data.
- Compare application elapsed time against `pg_stat_statements`/DB metrics and pool wait; a 3 ms DB query with an 80 ms pool wait still yields an 83+ ms lookup.
- Tracing spans uncover duplicate account lookups or unexpected calls; correlation IDs must never contain raw credentials.
- With LDAP/AD, latency depends on directory connection pooling, TLS, DN searches, group membership queries, referral chasing, DNS, and failover; do not blame the SQL DB when the user store is not a DB.

## 8. Measuring PasswordEncoder.matches and encode Cost

Password hashing is **intentionally slow**. Spring Security recommends tuning adaptive one-way functions per system; OWASP recommends benchmarking work factors on real servers and balancing brute-force resistance against DoS risk. Consult current guidance for Argon2id, scrypt, bcrypt, PBKDF2, and compliance requirements.

Distinguish:

- `PasswordEncoder.matches(raw, encoded)`: verifies an entered password (especially at login).
- `PasswordEncoder.encode(raw)`: computes a new hash on registration, reset, or **rehash upgrades after successful login**.
- `PasswordEncoder.upgradeEncoding(encoded)`: checks stored hash policy (usually lightweight), **without hashing a new value**.
- `DelegatingPasswordEncoder` picks the algorithm from the stored hash `{id}`; algorithms/costs can vary across accounts.

Measure `matches` and `encode` separately. Combining them into "hash time" causes occasional rehashes to skew the distribution, especially right after deploying a new policy.

### PasswordEncoder Decorator Example

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class TimedPasswordEncoder implements PasswordEncoder {

    private final PasswordEncoder delegate;
    private final Timer matchTimer;
    private final Timer encodeTimer;

    public TimedPasswordEncoder(
            PasswordEncoder delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.matchTimer = Timer.builder("app.auth.password.matches")
                .publishPercentileHistogram()
                .register(registry);
        this.encodeTimer = Timer.builder("app.auth.password.encode")
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public String encode(CharSequence rawPassword) {
        long start = System.nanoTime();
        try {
            return delegate.encode(rawPassword);
        } finally {
            encodeTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }

    @Override
    public boolean matches(
            CharSequence rawPassword, String encodedPassword) {
        long start = System.nanoTime();
        try {
            return delegate.matches(rawPassword, encodedPassword);
        } finally {
            matchTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }

    @Override
    public boolean upgradeEncoding(String encodedPassword) {
        return delegate.upgradeEncoding(encodedPassword);
    }
}
```

**Instrumentation security:** the wrapper **must never** log `rawPassword`, `encodedPassword`, usernames, or stack traces holding sensitive values; metrics record only duration/count. Never put passwords/hashes into tags or trace attributes; they propagate far and have long retention.

**Important detail:** `PasswordEncoder.matches` returning false usually still consumes CPU comparable to a full verify. However, if a user does not exist and a provider skips the KDF, responses become faster, leaking username existence via timing. Spring Security's `DaoAuthenticationProvider` mitigates timing differences for nonexistent users; if writing a custom provider or caching logic, test the negative path instead of trying to make failed requests return as fast as possible.

### Which Tags Should Be Attached?

A **low-cardinality** tag set might include:

| Tag | Example | Notes |
| --- | --- | --- |
| `method` | `password` / `webauthn` / `oidc` | Fixed method name, never raw factor secrets |
| `result` | `success` / `auth_failure` / `server_error` | Never use exception messages |
| `algorithm` | `bcrypt` / `pbkdf2` / `argon2id` | Stable category; omit if unneeded |
| `policy_tier` | `legacy` / `current` | Fixed grouping instead of raw hash |
| `cache` | `hit` / `miss` | Only when cache state is genuinely known |
| `service` | `identity-api` | Placed in appropriate telemetry resource attributes |

Never attach: raw username/email, user ID, IP, token, session ID, parameterized SQL, password strings, arbitrary URIs, per-request UUIDs, traceId, or raw exception messages. A million users create a million time series if tagged by user—causing **high cardinality** and potentially leaking personal data.

## 9. Choosing a Work Factor: Never Trade Security for Pretty Latency Numbers

A slow hash is a **protective feature**, not a bug to delete. Yet an overly high work factor can exhaust server CPU/RAM under concurrent logins, including intentional attacker spam.

### Actual Cost Depends On

- CPU architecture, core/thread scheduling, container CPU quotas, virtualization, and noisy neighbors.
- Algorithm and params: bcrypt cost (scales sharply with cost), PBKDF2 iterations, scrypt N/r/p, Argon2id memory/time/parallelism.
- Concurrent hashes; Argon2id allocates memory per hash, behaving very differently from bcrypt's CPU model.
- JVM warmup, JIT, native/Java implementations, GC, allocators, and in-flight request volume.
- Successful authentication may trigger rehash/encode, while wrong passwords only verify.
- Using `DelegatingPasswordEncoder`: mixed legacy/strong hashes yield different latency distributions; segment them by group.

### How to Benchmark Reliably

1. Choose the algorithm and minimum security policy first, per OWASP/system compliance.
2. On **production-equivalent hardware/containers**, measure cold/warmup separately and especially throughput as concurrency climbs.
3. Benchmark `matches` on hashes generated with **valid salts** matching policy, using synthetic test passwords.
4. Measure `encode` separately; normal logins usually do not call encode unless rehashing.
5. Run **repeated measurements after warmup**; use JMH for reliable JVM microbenchmarking.
6. Run end-to-end load tests with concurrent requests, pool/CPU/RAM/GC; avoid running a single-threaded microbenchmark and extrapolating to the entire system.
7. Pick a security level no weaker than the minimum policy, while enforcing rate limiting, bounded queues, and resource budgets.
8. Document baselines per environment and re-benchmark whenever CPU, Java, or encoder versions change.

**Never use** fast `MessageDigest SHA-256` instead of bcrypt/PBKDF2/scrypt/Argon2 to "cut login latency". Single-pass fast SHA-256 is not a suitable password-hashing algorithm against offline brute force.

### JMH Example — Snippet, Not Standalone Java SE

```java
// Needed: org.openjdk.jmh:jmh-core and matching annotation processor.
// This is a JMH benchmark class; it does not run with plain javac/java.
@State(Scope.Thread)
public class BCryptVerificationBenchmark {

    @Param({"10", "12"})
    public int strength;

    private BCryptPasswordEncoder encoder;
    private String storedHash;

    @Setup(Level.Trial)
    public void prepare() {
        encoder = new BCryptPasswordEncoder(strength);
        storedHash = encoder.encode("benchmark-only-password");
    }

    @Benchmark
    public boolean verify() {
        return encoder.matches(
                "benchmark-only-password", storedHash);
    }
}
```

Requires imports `org.openjdk.jmh.annotations.*` and `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`. JMH provides warmup, measurement, forks, and runner statistics; treat **cost 10/12 purely as benchmark parameters**, not a recommendation to alter defaults. Never benchmark using real production users/passwords.

### Estimating CPU Budget

An illustrative way to reason (not a substitute for benchmarking):

```text
Login rate = 20 requests/second
CPU work per password verify ≈ 250 ms CPU
CPU core-equivalent for verify alone ≈ 20 * 0.250 = 5 cores

+ DB, TLS, authorization, post-login, GC, queue, OS overhead
+ headroom for peak traffic / brute-force throttling
```

**This calculation assumes 250 ms is CPU time per hash**, not wall-clock latency when many requests wait on the scheduler. Never convert wall-clock p95 directly into "CPU cores needed" without measuring CPU time/CPU utilization. For Argon2id, also estimate memory footprint across **in-flight hashes** to prevent OOM.

## 10. Plain Java 17: Breaking Down Latency with a Fake Monotonic Ticker

This JDK 17 example **requires no Spring, DB, or Micrometer**. It simulates fixed durations to verify p50/p95 math, phase boundaries, recording both success/failure, and why both total and component timers are needed.

**This is a simulation, NOT real bcrypt or DB benchmark results.** Never treat the 120–150 ms numbers as real performance targets.

Create `AuthLatencyBreakdownDemo.java`:

```java
import java.util.*;
import java.util.concurrent.TimeUnit;

public class AuthLatencyBreakdownDemo {
    record Point(String metric, String outcome, long elapsedMillis) {}

    static final class FakeTicker {
        private long nanos;
        long read() { return nanos; }

        void advanceMillis(long millis) {
            if (millis < 0) {
                throw new IllegalArgumentException("negative duration");
            }
            nanos += TimeUnit.MILLISECONDS.toNanos(millis);
        }
    }

    static final class Recorder {
        private final FakeTicker ticker;
        private final List<Point> points = new ArrayList<>();

        Recorder(FakeTicker ticker) { this.ticker = ticker; }

        void time(String metric, String outcome, Runnable operation) {
            long start = ticker.read();
            try {
                operation.run();
            } finally {
                points.add(new Point(
                        metric, outcome,
                        TimeUnit.NANOSECONDS.toMillis(
                                ticker.read() - start)));
            }
        }

        void recordTotal(String result, long startNanos) {
            points.add(new Point(
                    "auth_total", result,
                    TimeUnit.NANOSECONDS.toMillis(
                            ticker.read() - startNanos)));
        }

        void summarize(String metric, String outcome) {
            List<Long> values = points.stream()
                    .filter(p -> p.metric().equals(metric)
                            && p.outcome().equals(outcome))
                    .map(Point::elapsedMillis)
                    .sorted()
                    .toList();

            if (values.isEmpty()) return;

            int n = values.size();
            long p50 = values.get((int) Math.ceil(0.50 * n) - 1);
            long p95 = values.get((int) Math.ceil(0.95 * n) - 1);

            System.out.println(metric + "/" + outcome
                    + " count=" + n + " p50=" + p50
                    + "ms p95=" + p95 + "ms");
        }
    }

    static void login(
            Recorder recorder, FakeTicker ticker,
            boolean passwordCorrect,
            long lookupMillis, long hashMillis, long successMillis) {

        long start = ticker.read();
        try {
            recorder.time("account_lookup", "all",
                    () -> ticker.advanceMillis(lookupMillis));

            recorder.time("password_verify", "all",
                    () -> ticker.advanceMillis(hashMillis));

            if (passwordCorrect) {
                recorder.time("after_success", "all",
                        () -> ticker.advanceMillis(successMillis));
            }
        } finally {
            recorder.recordTotal(
                    passwordCorrect ? "success" : "failure", start);
        }
    }

    public static void main(String[] args) {
        var ticker = new FakeTicker();
        var recorder = new Recorder(ticker);

        login(recorder, ticker, true,    8, 120, 5);
        login(recorder, ticker, true,   12, 135, 6);
        login(recorder, ticker, false,   9, 115, 0);
        login(recorder, ticker, true,   30, 150, 5);

        recorder.summarize("auth_total", "success");
        recorder.summarize("auth_total", "failure");
        recorder.summarize("account_lookup", "all");
        recorder.summarize("password_verify", "all");
        recorder.summarize("after_success", "all");
    }
}
```

Run:

```bash
javac AuthLatencyBreakdownDemo.java
java AuthLatencyBreakdownDemo
```

**Exact stdout:**

```text
auth_total/success count=3 p50=153ms p95=185ms
auth_total/failure count=1 p50=124ms p95=124ms
account_lookup/all count=4 p50=9ms p95=30ms
password_verify/all count=4 p50=120ms p95=150ms
after_success/all count=3 p50=5ms p95=6ms
```

### Exact Interpretation

- Success totals: 8+120+5=133 ms, 12+135+6=153 ms, 30+150+5=185 ms. Sorted: 133, 153, 185 → p50=153, p95=185.
- Failure total: 9+115=124 ms; after-success does not run. `count=1` means p95=124 ms is **not statistically meaningful** for alerting.
- Lookups across all requests: 8, 12, 9, 30 ms. Sorted: 8, 9, 12, 30 → p50=9, p95=30.
- Password verify across all requests: 120, 135, 115, 150 ms. Sorted: 115, 120, 135, 150 → p50=120, p95=150.
- After-success: 5, 6, 5 ms → p50=5, p95=6.
- Component timers are **nested inside** the total; never sum their `count`s as the number of login attempts. Each authentication attempt records one total sample.
- `FakeTicker` does not actually wait or burn CPU; it only advances simulated time, making tests deterministic without `Thread.sleep` and without producing real system performance metrics.
- `try/finally` records metrics when logic throws; the demo only illustrates the normal path and logical wrong-password path. Production must tag `server_error` on genuine exceptions rather than labeling everything `failure`.

**Self-directed exercise:** add 10 logins with lookup rising 10→100 ms while holding verify constant, then inspect p95 and count. Write an assertion verifying `auth_total` has exact sample count equal to attempt count. Do not turn the demo code into a Spring Security benchmark merely by renaming the class.

## 11. Prometheus/Grafana: Querying Latency and Saturation

Suppose the app publishes Timer `app.auth.manager` and the Prometheus registry exposes time series such as:

```text
app_auth_manager_seconds_count{result="success"}
app_auth_manager_seconds_sum{result="success"}
app_auth_manager_seconds_bucket{result="success",le="..."}
```

Actual names depend on the exporter/version/naming conventions; **check `/actuator/prometheus` to confirm before copying queries**.

### QPS / Attempts Over 5 Minutes

```promql
sum by (result) (
  rate(app_auth_manager_seconds_count[5m])
)
```

### p95 Authentication Success from Histogram

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_auth_manager_seconds_bucket{result="success"}[5m])
  )
)
```

Results are in **seconds**, not milliseconds. To display ms, multiply by 1000 in the query or set the unit in Grafana. Across multiple service instances, `sum by (le)` aggregates the buckets properly for the filtered group; **never average per-pod p95s** to approximate overall p95.

### p99 Split by Result

```promql
histogram_quantile(
  0.99,
  sum by (le, result) (
    rate(app_auth_manager_seconds_bucket[15m])
  )
)
```

If splitting by `method`/`region`, keep labels to a bounded defined set. When traffic is low, reduce label granularity so each series does not have only a handful of samples.

### Server Errors vs. Auth Failures

```promql
sum(rate(app_auth_manager_seconds_count{result="server_error"}[5m]))
/
clamp_min(sum(rate(app_auth_manager_seconds_count[5m])), 0.001)
```

**Do not treat every `auth_failure` as a system error:** a user mistyping a password and a database outage require different alerts. Brute-force attempts raise failure rates while the service is working per security policy; keep a separate rate-limit/abuse dashboard.

### DB Pool Saturation and Resources

Combine p95/p99 with:

- CPU usage/saturation/container throttling.
- GC pause time, heap/non-heap, thread count/thread-pool queues.
- Hikari `active`/`idle`/`pending`/`max` and connection acquisition latency.
- DB query execution, lock waits, deadlocks, connection timeouts, and slow query counts.
- Network/LDAP/IdP latency if authenticating against external services.
- Rate limiting/retries/login volume and password policy tier distributions.

Custom dashboards may be needed because Hikari/Spring Boot series names vary by exporter; avoid copying metric names that do not exist in your real environment.

## 12. Investigating Bottlenecks: A Pragmatic Decision Tree

```text
Login p95 increased?
    |
    +-- http.server.requests increased,
    |   app.auth.manager DID NOT increase
    |      -> proxy/thread queue/CSRF/filter/session/audit/redirect?
    |
    +-- app.auth.manager increased
           |
           +-- account.lookup increased
           |       |
           |       +-- Hikari pending/connection wait increased?
           |       |      -> pool exhaustion / DB load / long transaction
           |       +-- DB query p95 increased?
           |       |      -> index, plan, IO, lock, network, N+1
           |       +-- LDAP/IdP call increased?
           |              -> directory network/pooling/external dependency
           |
           +-- password.matches increased
           |       |
           |       +-- CPU throttling / saturation?
           |       +-- work factor/encoder mix changed?
           |       +-- GC/memory pressure?
           |       +-- brute-force concurrency surge?
           |
           +-- postlogin/upgrade/encode increased
                   |
                   +-- rehash rollout causing spike?
                   +-- slow session persistence/audit/outbox?
```

### Scenario A — Changing bcrypt Cost

Before deployment, an older cost was used; after deployment, a higher cost is used. If `password.matches` latency increases while account lookup stays flat and CPU rises, **this may be the expected security cost increase**, not a SQL regression. Measure capacity and cap concurrent logins; never roll back to a weaker hash just to make a graph look nicer.

### Scenario B — Connection Pool Exhausted

`account.lookup` p95 rises while DB query execution inside the DB is only a few milliseconds. When pool pending spikes, requests may spend most of their time **waiting to acquire a connection**. Check pool stats, connection hold times, long transactions, and DB load; do not raise pool size blindly.

### Scenario C — Double User Lookup

Tracing shows `loadUserByUsername` runs twice per login: possible causes include a custom provider, user cache miss, post-login reload, or an event listener. Inspect the code path and caching semantics; avoid caching encoded passwords so long that password resets/revocations fail to take effect.

### Scenario D — Many Invalid Credentials After Deployment

The goal is not to make failed logins "abnormally fast" by skipping KDF/lockout checks, as that creates timing enumeration. Identify the traffic source, rate limiters, bot challenges, and CPU abuse while keeping responses/timing consistent enough not to leak user existence.

### Scenario E — Only Clients See Slowness

`app.auth.manager` is 150 ms, yet browsers measure 2 seconds. Check RUM/network waterfalls, ingress/proxy queues, DNS/TLS, redirect chains, OIDC hops, browser resources, session store, and callback ordering. Micrometer server timers do not cover the entire client request path.

## 13. Microbenchmarks and Load Tests Must Go Together

**Microbenchmark:** measures one `matches` function under low simulated load; does not reveal behavior at 100 concurrent logins or when DB pool and CPU saturate together.

**Load test:** measures the full flow under concurrent users with a real DB, pool, container quotas, TLS, and production-like networking. Run:

- Baseline 1→5→20→50 concurrent users at controlled rates.
- Enough traffic for several minutes so JIT/GC/pool metrics stabilize.
- Realistic mix of `success`/`auth_failure` outcomes; never run real brute-force floods against production.
- Separate legacy/current algorithms, first-login rehashes vs. subsequent logins.
- Peak/spike tests to observe queueing and graceful degradation.
- Monitor p95/p99 alongside CPU/memory/DB, not just QPS.
- Test timeout/retry/rate-limiter behavior and check whether high hash concurrency causes DoS.
- Never use real production usernames/passwords in load-test scripts; seed synthetic accounts and dedicated test secrets.

**Warmup vs. benchmark:** `System.nanoTime` measures elapsed time well for request instrumentation, but running one tiny loop from `main` and concluding "bcrypt averages 12 ms" is unreliable. JMH uses warmup/forks to study JVM code; load tests evaluate concurrency, p95, queueing, and end-to-end behavior.

## 14. Designing Meaningful SLOs and Alerts

Service targets can be defined, for **illustration**:

| Target | Example Value | Additional Requirement |
| --- | --- | --- |
| `auth.manager` p95 success | Under 500 ms | Compare only under fixed hardware, security policy, and traffic mix |
| `auth.account.lookup` p95 | Under 100 ms | Include pool wait; separate cache hits/misses |
| `auth.password.matches` p95 | Within KDF policy budget | Never lower cost just to "hit a KPI" |
| 5xx/server error rate | Below a low threshold | Kept separate from bad credentials |
| Hikari connection wait | No sustained growth during peaks | Pair with active/max/pending |
| CPU throttling | Not sustained near saturation | Tune concurrency/resource budgets |

**An SLO is not a security standard:** high-assurance apps may accept slower hash verification; apps serving millions of logins/s use different architectures. Measure with configuration context, tying thresholds to user experience and risk assessment.

Alerts should use at least:

1. P95/p99 exceeding target in a window with sufficient samples.
2. Shifts in throughput and error rates.
3. CPU throttling/DB pool saturation.
4. Comparison against baselines from the same time-of-day/release.
5. Separate security alerts for auth failure rates/rate limiting and brute-force indicators.

Never alert on a single maximum timer sample during low traffic; `max` in Micrometer follows time-window semantics.

## 15. Instrumentation Overhead and Sampling

Measuring performance **also consumes resources**. A timer with 3 fixed tags is far cheaper than generating full stack-trace spans, yet:

- Every metric name + tag combination creates a time series family; high cardinality drives up RAM/CPU/export costs.
- Too many histogram buckets create many time series; publish histograms only for key phases with sensible boundaries.
- Excessively high trace sampling adds overhead, especially if instrumenting DB/LDAP per request.
- Logging timings for every password attempt risks leaking usernames/passwords into JSON log contexts; prefer aggregate metrics and sanitized trace sampling.
- Check whether instrumentation double-records across decorators and framework observations.
- Nanosecond-precision timing bloats footprint if every sample is logged individually; `Timer` aggregation is better.

**Never measure over a raw credential variable and export it as a metric tag.** For traces, never call `authentication.getCredentials().toString()`, and never place session cookies, authorization headers, password hashes, OTPs, or tokens into spans.

## 16. Testing Instrumentation and Data Accuracy

For instrumentation to be trustworthy, test not just HTTP responses but also metric sample counts:

| Scenario | What to Verify |
| --- | --- |
| Valid login | `auth.manager{result=success}` +1, lookup +1 if invoked, matches +1 |
| Wrong password | `auth_failure` +1, matches +1, not counted as success |
| Nonexistent user | Lookup +1, provider preserves timing-enumeration mitigation per policy |
| Disabled account | Auth failure +1; some providers may skip matches — **verify actual behavior**, do not force it |
| DB timeout | `server_error` +1; timer records in `finally`; no fake success |
| Current hash | Verify +1, encode +0 |
| Legacy hash upgraded | Verify +1, encode +1, repository writes per policy |
| Cache hit | Skips DB lookup when cache is valid; caller/provider metrics still record |
| Basic auth per request | Count matches actual attempts, not mistaken for one login session |
| Multiple providers | No double-counting; only the active manager is instrumented |
| Password reset | Encode timer records in reset flow; not confused with login verify |
| Concurrent load | Histograms/counts record completely under 20–100 parallel requests |
| Sampled trace | Tags contain no PII/credentials; trace ID stays in tracing only |
| Metrics exporter unreachable | Auth behavior does not fail-open/fail-closed unexpectedly due to exporter error |
| Unauthorized Actuator | Non-admins/Internet cannot read sensitive metrics |
| No traffic | Do not conclude p99=0 means "fast"; display N=0/no data |
| GC pause | Manager p95 can rise even when SQL/hash CPU stays unchanged in wall time |
| Queue saturation | Server/request p95 rises before auth manager; measure exact boundaries |

### SimpleMeterRegistry Test for Wrong Password

```java
@Test
void invalidCredentialShouldBeCountedAsAuthFailure() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    AuthenticationManager failing = request -> {
        throw new BadCredentialsException("invalid");
    };
    TimedAuthenticationManager wrapped =
            new TimedAuthenticationManager(failing, registry);

    assertThrows(BadCredentialsException.class,
            () -> wrapped.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "test-user", "wrong")));

    assertEquals(1L, registry.get("app.auth.manager")
            .tag("result", "auth_failure").timer().count());
    assertEquals(0L, registry.get("app.auth.manager")
            .tag("result", "success").timer().count());
}
```

Required imports: `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.BadCredentialsException`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.junit.jupiter.api.Test`, and static `org.junit.jupiter.api.Assertions.*`. This is a unit test snippet in a project with required dependencies; it does not run standalone with the JDK.

### Integration Tests to Implement for Real

- Boot the Spring Boot app with `@SpringBootTest`, `@AutoConfigureMockMvc`, and a password user store with test fixtures.
- Submit form login with `csrf()` through the real filter chain; do not use `@WithMockUser` to test password verification (it bypasses the provider).
- Assert actual `MeterRegistry` counts/timers; do not assert only HTTP 302 since both login success and failure can redirect.
- If using JDBC, measure DB query timers/caches/pool waits in the test environment; an in-memory H2 DB does not represent production PostgreSQL.
- Use a fake `Clock`/registry clock for deterministic duration tests; avoid `Thread.sleep` to manufacture desired p95 results.
- Verify the app does not create series per username/email. Inspect `registry.getMeters()` and tags for fixed values.
- For Prometheus, verify actual exported metric names/buckets/units and PromQL dashboards in staging.

## 17. Common Implementation Mistakes

**1. Looking only at the mean.** A 100 ms mean can hide a 2-second p99; examine histograms and tails.

**2. Looking at HTTP duration and blaming bcrypt.** HTTP includes TLS/queues/filters/sessions/proxies; measure `PasswordEncoder.matches`.

**3. Looking at `AuthenticationManager` time and blaming SQL.** The manager includes lookup, verification, and other logic; add lookup and DB timers.

**4. Adding phase p95s to get total p95.** Percentiles are not additive; measure total directly.

**5. Measuring only success.** Missing failed auth/DB errors leaves dashboards blind right during attacks or outages.

**6. Tagging with username/email/IP/sessionId.** Causes high cardinality and personal data leaks; use finite tags.

**7. Using `Instant.now()` for elapsed time.** Wall clocks can jump; use monotonic `System.nanoTime()` or the registry clock.

**8. Assuming `ObservationAuthenticationManager` already provides per-SQL charts.** High-level auth observations do not split repository/KDF costs without deeper instrumentation.

**9. Replacing bcrypt with SHA-256 for speed.** Weakens security and is unfit for password storage; tune work factors and capacity instead.

**10. Picking bcrypt/Argon2 params on a dev laptop.** CPU/RAM differ from production; benchmark both single-request latency and concurrent load.

**11. Allowing unlimited parallel hashes.** Causes CPU saturation/Argon2 OOM; enforce rate limits, concurrency budgets, and resource quotas.

**12. Raising Hikari `maximumPoolSize` when queries are slow.** Can overload the DB further; investigate locks, query plans, and pool wait first.

**13. Caching `UserDetails` indefinitely to "speed things up".** Password resets, account locks, and revoked roles fail to propagate promptly; enforce policy-driven invalidation/TTLs.

**14. Ignoring user-not-found timing.** Attackers can enumerate accounts; test invalid users and dummy-hash behavior.

**15. Measuring `encode` and `matches` as one metric.** Blurs normal logins with rehashes/registrations/resets.

**16. Forgetting `DaoAuthenticationProvider`'s rehash path.** After a policy upgrade, `encode` rises and DB writes happen on success; monitor separately.

**17. Mixing failed credentials and 5xx.** Normal user errors look like outages, causing false alerts.

**18. Multiple metric wrappers recording one attempt.** Counts double and p95 breaks; audit bean wiring and tracing.

**19. Benchmarking once with `System.nanoTime`.** JVM JIT/GC/CPU noise skews results; use JMH and repeated load tests.

**20. Benchmarking with real production data.** Risks credential leaks and polluted logs; use synthetic test data.

**21. Exposing `/actuator/prometheus` publicly.** Leaks topology, labels, and system metrics; restrict to management networks and auth.

**22. Plotting p99 without checking sample count.** Low traffic makes percentiles swing wildly; gate by count and window.

**23. Confusing duration units.** Micrometer timers accept `TimeUnit`, while Prometheus typically exports seconds; match Grafana units.

**24. Optimizing DB queries while ignoring pool acquisition.** Fast SQL still stalls if requests wait for connections; measure pool wait too.

**25. Enabling unlimited TRACE logging on login paths.** Wastes CPU/IO and risks credential leaks; use sampling/redaction.

**26. Weakening security to meet an SLO.** Never turn off throttling, account checks, or MFA; adjust architecture, capacity, and UX per threat model.

## 18. Pre-Production Checklist

- [ ] Identified actual login paths: form login, HTTP Basic, JWT, LDAP, or OIDC?
- [ ] Understood `http.server.requests` and `spring.security.authentications` boundaries without mistaking spans for ready-made histograms?
- [ ] Separate timers for manager, user lookup, password matches, password encode, and post-login where needed?
- [ ] Every timer records in `finally` and classifies success/auth failure/server error with finite tags?
- [ ] Using `System.nanoTime()`/Micrometer timers rather than wall-clock time for durations?
- [ ] `PasswordEncoder` uses an adaptive hash per policy; work factor benchmarked on real hardware?
- [ ] Measured both single-user latency and concurrent throughput, CPU throttling, and Argon2 memory?
- [ ] Distinguished DB pool wait, query execution, network RTT, cache hit/miss, and LDAP?
- [ ] No username/email/IP/sessionID/password/hash/token in metrics or trace tags?
- [ ] Dashboards show count, throughput, p50/p95/p99, errors, and CPU/GC/pool side by side?
- [ ] Prometheus histogram buckets enabled on the right meters, queries use `rate`/`sum by(le)` with matching units?
- [ ] For low-login apps, alerts gated on sufficient sample counts/windows?
- [ ] Changes to encoder cost, deployment, DB indexes, or caches measured before–after under the same traffic mix?
- [ ] Actuator/metrics/prometheus protected by network isolation and authentication/authorization?
- [ ] Tested actual manager/provider/`PasswordEncoder` wiring rather than merely bean existence?
- [ ] Tested negative paths, DB timeouts, wrong passwords, unknown users, legacy rehashes, and parallel logins?
- [ ] Never lowered password hash strength solely for latency targets; rate limiting/capacity planning in place?
- [ ] Runbook exists: p95 rises → isolate hash CPU, DB pool, downstream dependencies, and post-login work?

### References

- Spring Security 6.5 — Observability: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/observability.html
- Spring Security 6.5 — Password Storage / tune work factor: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 API — ObservationAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ObservationAuthenticationManager.html
- Spring Boot 3.5 — Metrics, Spring MVC, JDBC/Hikari: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5 — Actuator endpoints & security: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- JMH — Official OpenJDK microbenchmark harness: https://github.com/openjdk/jmh

**Conclusion:** measuring authentication properly means measuring **every boundary**, not just total HTTP time or CPU. Use safe-tagged metrics/timers to separate lookup, password verification, rehashing, and post-login work; combine p95/p99 histograms, DB pool stats, CPU/RAM, and tracing. Optimize capacity and queries based on evidence, **never weakening hashing algorithms or dropping security controls to lower latency**.
