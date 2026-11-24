# Choosing Servlet vs. Reactive Across the Full Application Architecture

> **Context:** Spring Security fundamentals → Reactive architecture. This lesson helps you make architectural decisions for a secured Spring application, from incoming HTTP through data access, external services, transactions, operations, and testing.

## 1. Questions to Answer Before Picking a Stack

Both Servlet (typically **Spring MVC**) and reactive (typically **Spring WebFlux**) can build secure web applications. The main difference lies in **how I/O is handled, how concurrency is managed, and how execution context is propagated**; your HTTP framework choice also impacts Security, persistence, transactions, HTTP clients, integrated libraries, monitoring, and team readiness.

Do not decide based solely on whether a controller returns `Mono`/`Flux`, and never assume “reactive is faster.” Answer three questions:

1. **Is the request path genuinely non-blocking end to end?** If most business logic calls JPA/JDBC or thread-blocking SDKs, WebFlux will not magically make those calls non-blocking.
2. **Does the real workload benefit from serving many I/O-waiting requests with fewer OS threads?** Distinguish traffic volume, concurrency, I/O wait ratio, CPU cost, p95/p99 latency, and downstream limits.
3. **Is the whole ecosystem ready?** This includes Spring Security mechanisms, transactions, context, testing, library integrations, tracing, resource limits, and debugging capabilities.

**Starting principle:** For an existing application running well on MVC + JPA/JDBC, usually keep Servlet; migrate to WebFlux only with evidence and a plan to convert the entire critical path. For a new service doing predominantly non-blocking I/O such as streaming or fanning out many HTTP calls, reactive is worth considering from the start.

## 2. Where Do the Two Execution Models Actually Differ?

### 2.1. Servlet / Spring MVC

Simplified flow:

```text
HTTP request
  → Servlet container (e.g., Tomcat)
  → Servlet Filter / Spring Security FilterChainProxy
  → DispatcherServlet → Controller → Service
  → JDBC/JPA or other API → HTTP response
```

In typical synchronous processing, a request-handling thread may **wait** when calling a database or network service. The container uses a thread pool to serve multiple requests; Servlet async techniques also exist and Spring MVC can handle several async styles, so “Servlet = synchronous only” is false. The main strength of the imperative path is readable linear code, direct access to a massive blocking ecosystem, thread-bound transactions, and familiar debugging tools.

### 2.2. Reactive / Spring WebFlux

Simplified flow:

```text
HTTP request
  → WebFilter / SecurityWebFilterChain
  → DispatcherHandler → Controller/Handler
  → Mono/Flux pipeline → non-blocking HTTP/DB client
  → data / error / completion signals → HTTP response
```

Instead of holding a thread idle per I/O call, reactive code declares a pipeline; when I/O is not yet ready, the thread can serve other work. WebFlux commonly runs on an event loop with a relatively small number of threads; therefore **you must never block the event loop** with `Thread.sleep`, `Future.get`, `block()`, JDBC, or blocking network operations.

`Mono<T>` represents at most one value or completion/error, and `Flux<T>` represents a sequence of 0..N values. A pipeline executes only when subscribed; in WebFlux, the framework normally handles subscribing to controller return values. Reactor supports backpressure between Reactive Streams–compliant components, yet this **does not automatically guarantee** that every database, queue, HTTP client, or end client has proper load-control mechanisms.

**Distinction:** Reactive is not synonymous with Netty. WebFlux runs on other compatible supported servers; Netty is simply the common choice of the WebFlux starter. Conversely, using `WebClient` or returning `Mono` from an MVC controller **does not automatically turn the whole application into WebFlux**.

### 2.3. Latency, Throughput, and Resources

Non-blocking typically shines when many operations **wait on I/O** (slow APIs, streaming, long-lived connections). It does not make SQL run faster by itself, does not eliminate connection-pool limits, and can add programming, scheduler, memory, or signal-handling overhead. CPU-heavy workloads still compete for finite CPU cores; calling CPU-bound computations “reactive” does not make them more parallel.

Concurrency can be estimated with **Little's Law**: the number of requests in the system is roughly the arrival rate times average processing time, `L ≈ λ × W`. For instance, 200 requests/second at 250 ms average corresponds to roughly 50 concurrent requests in steady state. That figure is **in-flight requests**, not the number of WebFlux threads needed and not the number of JDBC connections needed. The point is to guide measurement questions, not to declare an architectural winner by arithmetic alone.

## 3. Auditing the *Entire* Data Path

A system benefits from reactive when the segments with long wait times all support non-blocking, while any blocking segments are isolated, measured, and bounded. Use the checklist table below to audit every critical request path:

| Component | Typical Servlet/MVC | Typical WebFlux/reactive | What to Verify |
|---|---|---|---|
| HTTP server/controller | `DispatcherServlet`, `@RestController` | `DispatcherHandler`, `Mono`/`Flux`, or functional routes | Which framework does Boot actually start? |
| Outbound REST client | `RestClient`, `RestTemplate`, or `WebClient` | Non-blocking `WebClient` | Any `block()`, sync SDKs, or load-amplifying retries? |
| SQL access | JPA/Hibernate, JDBC, `JdbcTemplate` | R2DBC when driver and use case support it | Are required drivers, ORM features, transactions, and SQL semantics available? |
| Transactions | `PlatformTransactionManager`, typically thread-bound | `ReactiveTransactionManager`, Reactor Context | Which path owns the transaction; are threads/contexts mixed? |
| HTTP Security | `SecurityFilterChain` + `HttpSecurity` | `SecurityWebFilterChain` + `ServerHttpSecurity` | Is the right stack configured with complete rules? |
| Security context | `SecurityContextHolder`, commonly thread-bound | `ReactiveSecurityContextHolder` via Reactor Context | Does identity survive async/scheduler/pipeline boundaries? |
| Filter / exchange | Servlet `Filter`, `HttpServletRequest` | `WebFilter`, `ServerWebExchange` | Do any libraries require Servlet APIs? |
| Session, CSRF, login | Servlet session / CSRF filter | Web session / reactive CSRF filter | Cookie/browser or bearer token? |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Are return types and context compatible? |
| HTTP testing | `MockMvc`, Servlet tests | `WebTestClient`, reactive security tests | Are 401, 403, CSRF, and context propagation tested? |
| Operations | Thread pool, JDBC pool, servlet metrics | Event loop, schedulers, connection pool, backpressure | Can you measure queues, timeouts, memory, and p95/p99? |

**The weakest bottleneck determines effectiveness:** if a WebFlux request passes through three non-blocking layers only to wait on JDBC on the event loop, it can stall many other requests. Conversely, if an MVC service uses `WebClient` to call two independent downstreams concurrently and returns the result asynchronously where appropriate, it can still cut wait times without switching web stacks.

### 3.1. Classifying Dependencies Before Designing

- **Mandatory blocking:** JPA, JDBC, synchronous drivers/SDKs, blocking file operations, libraries with no async API. These usually fit MVC better, or need tightly managed bridges in reactive.
- **Truly non-blocking:** properly used `WebClient`, R2DBC/compatible reactive drivers, certain messaging drivers/stream APIs with backpressure protocols.
- **CPU-bound:** encryption, compression, image processing, heavy math, some signature verification. Both stacks still need CPU and concurrency limits.
- **Shared resources:** DB pools, upstream rate limits, caches, message brokers, API quotas, threads/schedulers. A non-blocking pipeline can still overwhelm them if fan-out is unbounded.

Do not ask only “is there a reactive repository?” Also ask “does the system strictly need JPA entity lifecycle, lazy loading, complex relationships, existing transactions, or specialized drivers?” Migrating JPA to R2DBC is not a drop-in import swap: persistence models and transaction guarantees must be redesigned and retested.

## 4. Spring Security Must Match the Web Stack

Whichever model you choose, security requirements stay the same: identity authentication, authorization, deny-by-default on protected paths, 401/403 handling, CSRF protection when cookies pose a risk, session/token protection, cryptography, safe logging, and negative tests. **Only Spring Security's execution API differs.**

### 4.1. Servlet Security

In MVC, Spring Security integrates via the Servlet filter chain. Configuration uses `HttpSecurity` to create a `SecurityFilterChain` bean; requests are authenticated/authorized through filters before reaching the controller. `SecurityContextHolder` is the standard thread-bound context access in synchronous code, though when hopping to another executor/thread you must use supported context-propagation mechanisms rather than assuming `ThreadLocal` follows automatically.

### 4.2. Reactive Security

In WebFlux, Spring Security integrates via `WebFilter` and `SecurityWebFilterChain`; configuration uses `ServerHttpSecurity`, such as `authorizeExchange` and `pathMatchers`. Authentication/security context travels via **Reactor Context** bound to the subscription/pipeline; calling `SecurityContextHolder.getContext()` on an arbitrary event-loop thread cannot be treated as a reliable way to obtain the current user.

An illustrative snippet **placed inside a method returning `Mono<String>`** in a reactive component integrated with Spring Security:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Corresponding imports: `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext`, and `org.springframework.security.core.Authentication`. The snippet is not a standalone Java class; on an endpoint requiring authentication, it provides the current principal's name.

Manually calling `subscribe()`, `block()`, or spawning threads outside the Reactor chain without control easily breaks context, error, cancellation, transaction, and observability semantics. Keep **a single pipeline subscribed by the framework**, use proper operators, and verify with tests using real identities.

### 4.3. CSRF, Sessions, and Tokens

- For web applications using **session cookies that browsers send automatically as credentials**, analyze CSRF and normally keep CSRF protection for state-changing operations. Do not disable it just to make `POST` tests easier.
- For REST APIs using bearer tokens in headers without relying on automatic cookie credentials, there may be reasons for a different CSRF configuration; analyze the **actual authentication mechanism**. “Using JWT” is not enough to conclude all endpoints are CSRF-exempt if cookies/sessions are still active.
- Applications may require form login, OAuth2 login/OIDC, or JWT/opaque-token resource servers on either stack, yet beans, filters, entry points, context persistence, and integrations must be chosen for the matching stack.
- Authentication/authorization policies can preserve **equivalent semantics** across stacks; you cannot copy `HttpSecurity` verbatim into `ServerHttpSecurity`.
- Distinguish **401** (unauthenticated or invalid credentials) from **403** (authenticated but lacking permissions, or blocked by another check like CSRF). Actual entry points may return a redirect for form login; test against your concrete configuration.

### 4.4. Method-Level Security, Transactions, and Errors

`@EnableMethodSecurity` targets imperative methods; for reactive pipelines use `@EnableReactiveMethodSecurity` with compatible methods/return types. Enforce permissions both at controllers and on sensitive services to avoid gaps when a service is called from another path.

Imperative transactions are managed by `PlatformTransactionManager` and are usually thread-bound; reactive transactions are managed by `ReactiveTransactionManager` based on Reactor Context. Therefore, calling a JPA-style `@Transactional` service via an arbitrary thread/scheduler does not mean you have made transactions reactive. Publisher retry/cancel/error branches must also be considered when guaranteeing rollback and idempotency.

## 5. Two Minimal Runnable Examples Showing the Difference

The two examples below are **two independent Spring Boot applications**, not placed in the same project. Create a Spring Boot 3.x + Java 17+ project from Spring Initializr (or a Boot project already configured with the Gradle plugin/BOM), selecting the matching starters. The illustrative `build.gradle` shows only the `dependencies` block of an existing Boot project, not a complete build file. Both share the same policy: `/public/**` is public, and all other URLs require HTTP Basic authentication. The demo user `learner / demo123` uses `{noop}` **for local learning only**; production uses a secure identity store and password encoder.

### 5.1. Servlet/MVC Option

In the first project, add these dependencies to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/mvc/MvcApplication.java`:

```java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "mvc public";
    }

    @GetMapping("/api/ping")
    public String privatePing() {
        return "mvc protected";
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

The code uses Servlet/MVC + `SecurityFilterChain`, without creating publishers to complete endpoints. Run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows from the right project. Default HTTP port is 8080 unless configured otherwise.

### 5.2. WebFlux/Reactive Option

In the **second project**, use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/reactive/ReactiveApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> publicPing() {
        return Mono.just("reactive public");
    }

    @GetMapping("/api/ping")
    public Mono<String> privatePing() {
        return Mono.just("reactive protected");
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(ex -> ex
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

Here the HTTP flow passes through `SecurityWebFilterChain` and endpoints return publishers. `Mono.just` in the demo only illustrates **return types and security integration**; there is no non-blocking I/O, so it is not proof of higher WebFlux performance.

### 5.3. Running and Observing

Run only **one of the two applications on port 8080** at a time. With the created project, use these commands:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/ping
curl -i -u learner:demo123 http://localhost:8080/api/ping
```

| Request | Expected Status | Typical Body |
|---|---:|---|
| GET `/public/ping` without credentials | 200 | `mvc public` or `reactive public` |
| GET `/api/ping` without credentials | 401 | Do not rely on a fixed error body |
| GET `/api/ping` with valid credentials | 200 | `mvc protected` or `reactive protected` |

Headers depend on server/Spring Security/config; do not compare the entire `curl -i` output verbatim. Also test wrong credentials → 401. Because both demos only have GET endpoints, they do not test CSRF for POST, nor do they illustrate ADMIN roles, sessions, databases, or transactions.

**Starter selection trap:** When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot defaults to **MVC** auto-configuration, because MVC apps often include WebFlux to use `WebClient`. Never infer which web stack is running merely by seeing `spring-webflux` in the dependency tree. Verify `WebApplicationType`, startup logs, active contexts/beans, and actual endpoint/integration tests. Do not force `REACTIVE` onto an existing MVC app without checking dependencies and security beans.

## 6. Bridging: What If Blocking APIs Still Exist?

Sometimes you must call a blocking library from WebFlux during a transition phase. An **illustrative service snippet, not a standalone program**, can offload the blocking operation to a bounded scheduler:

```java
public Mono<Customer> findCustomer(String id) {
    return Mono.fromCallable(() -> legacyRepository.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Assuming `legacyRepository.findById` is a blocking method returning `Customer` or `null`; `Mono.fromCallable` completes empty when the callable returns `null`. `Customer` and `legacyRepository` are provided by the project; `Mono` and `Schedulers` must be imported from Reactor. This bridge **does not make the repository non-blocking**; it uses another thread to avoid stalling the event loop. You still must monitor queued tasks, threads, connection pools, timeouts, concurrency limits, and context/transactions. If the entire request path has to wrap JDBC in `boundedElastic`, MVC is very likely the simpler and easier-to-operate choice.

Operations to avoid inside a WebFlux pipeline:

```java
// Wrong example when running on the event loop:
User user = userClient.getUser(id).block();
Thread.sleep(500);
```

This is an anti-pattern example, **not a runnable class**. `block()` forces the thread to wait for a result and can throw runtime errors on many Reactor non-blocking paths; `Thread.sleep` keeps the event loop idle. For long CPU-bound tasks, consider a dedicated executor/scheduler or moving work to background workers rather than dumping everything onto `boundedElastic`.

On the other hand, if you use Servlet MVC and need to call multiple HTTP endpoints, you can use non-blocking `WebClient` within the async models already supported by MVC. Avoid sprinkling `.block()` carelessly in controllers and concluding “WebClient didn't help”; this choice still needs measurement and consistent error/timeout handling.

## 7. Common Decision Scenarios

### Scenario A — JPA CRUD Business Application

An admin system has many relational tables, JPA/Hibernate, imperative transactions, a few synchronous external APIs, and moderate load. **Starting recommendation: Servlet/MVC + Spring Security Servlet.** The data and transaction paths are blocking; the cost of migrating to WebFlux/R2DBC likely outweighs the benefits. Focus on optimizing SQL/indexes, JDBC pools, caching, downstream latency, timeouts, pagination, and authorization.

### Scenario B — API Aggregation/Gateway Calling Many HTTP Services

An endpoint needs to query multiple high-latency downstreams in parallel, has no JPA transactions, and already uses non-blocking clients. **WebFlux + reactive Security can be a strong fit**, especially when many requests are waiting on I/O. Still, bound fan-out, connections, retries, timeouts, and backpressure at each stage; do not treat any gateway as automatic proof that WebFlux is required. A stable MVC service can also try `WebClient` first.

### Scenario C — SSE/Streaming and Long-Lived Connections

An application streams events continuously or holds many long-lived connections, and upstream supports non-blocking data streams. **WebFlux is worth trying** when you need to model streams, cancellation, and per-pipeline resource control. Servlet also supports streaming/async; base the decision on concurrency, event delivery mechanics, load balancing, reconnects, and deployment infrastructure. Security must still handle login/tokens, expiration, stream authorization, disconnects, and rate limiting.

### Scenario D — Heavy CPU Work or Mandatory Blocking SDKs

Image analysis, high-volume digital signing, or file processing via thread-blocking libraries. **Reactive does not solve CPU/SDK bottlenecks by itself.** Consider Servlet + virtual threads on Java 21+, proper pools, task queues, background workers, or splitting into a separate service. Evaluate JVM limits, virtual-thread pinning, and downstream pressure independently.

### Scenario E — Multiple Microservices with Different Needs

Not all services have to use the same web stack. For example, a JPA admin service uses MVC while a streaming service uses WebFlux, communicating via stable HTTP/event contracts. Each service configures **Security matching its own stack**; you still need consistent identity standards, issuer/audience, authorization semantics, trace-context propagation, timeouts, and key management. Mixing stacks raises skill, library, and operational costs: do so only when concrete benefits justify it.

## 8. A Practical Decision Process for Real Projects

### Step 1: Map the Request Path and Identify Hard Constraints

For each core business flow, map ingress → security filters → controller → service → database/cache/upstream/message broker → response. Note whether each driver/SDK is **blocking** or **non-blocking**, plus transaction style, authentication, sessions, timeouts, and retries. One critical library that only supports Servlet APIs or JPA can be a hard constraint.

### Step 2: Classify the Workload

Measure RPS, concurrent requests, database/API wait times, p50/p95/p99, request sizes, stream durations, CPU, memory, connection/thread pools, and error counts. Identify whether bottlenecks come from **I/O waiting**, CPU, database, contention, upstream limits, or algorithms. A service holding 10,000 concurrent connections waiting on events is completely different from 10,000 concurrent CPU computations.

### Step 3: Pick a Minimal Candidate

- If most of the existing stack is blocking, JPA transactions are central, and Servlet Security is stable: prefer MVC. On Java 21+, you may evaluate monitored virtual threads if appropriate, while still measuring pinning and downstream pools.
- If critical flows are genuinely non-blocking end to end, involve heavy I/O streaming/fan-out, and the team masters Reactor and reactive testing/security: evaluate WebFlux.
- If evidence is lacking: keep the stable architecture and run a small experiment under realistic load. Never switch just for “new tech.”

### Step 4: Build a Fair Experiment

Keep the same business logic, auth, DB and data, SLOs, payloads, GET/POST ratios, downstream latencies, hardware, and concurrency limits. Record thread/event-loop settings, connection pools, client timeouts, retries, heap, GC, and queued requests. Measure both **steady state and slow/failing upstreams**; a “Hello World” benchmark mainly measures framework overhead and does not decide enterprise architecture.

### Step 5: Evaluate Security and Transaction Correctness Too

Are 401/403 enforced on every endpoint? Do cookie/session flows have CSRF? Are user/roles intact across async/schedulers? Does `@PreAuthorize` work with Reactor Context? Do transactions, rollbacks, cancellation, retries, and idempotency align? Do audits, traces, and logs record the right request/user without leaking secrets/tokens? Hitting latency SLOs while breaking security/transactions is **not** an acceptable option.

### Step 6: Decide and Record the Rationale

Write a short ADR (Architecture Decision Record):

```text
Decision: MVC / WebFlux for service X
Workload: RPS, concurrency, p95/p99, I/O wait ratio
Constraints: JPA/JDBC/SDK, security, transaction, team, operations
Alternatives: current MVC, MVC + WebClient, MVC + virtual threads,
              end-to-end non-blocking WebFlux, split service
Evidence: load test results, errors, CPU/heap, pools, failure modes
Security: chain/context/method security, CSRF/session/token, 401/403 tests
Trade-offs: migration cost, debugging, library support, observability
Revisit when: workload/driver/critical dependency changes
```

A good decision includes conditions to **revisit** when workloads or libraries change, rather than turning one stack into a rigid rule for every module.

## 9. Safe Migration Plan If You Choose Reactive

Moving from MVC/JPA to WebFlux is far more than changing `@RestController` methods to return `Mono`:

1. **Define service scope and SLOs:** pick request paths with clear I/O gains rather than migrating everything because of one endpoint.
2. **Inventory dependencies:** JPA/JDBC, transactions, Servlet libraries, filters, auth providers, SDKs, HTTP clients, caches, metrics, tests.
3. **Decouple business logic from framework APIs:** define interfaces/domain logic independent of `HttpServletRequest`/`ServerWebExchange` where possible.
4. **Define persistence:** does an R2DBC driver support the business requirements; do queries, transactions, and lazy loading need redesign?
5. **Translate security with exact semantics:** from `SecurityFilterChain`/`HttpSecurity` to `SecurityWebFilterChain`/`ServerHttpSecurity`; verify rules, session/CSRF, OAuth2, context, and method security.
6. **Replace I/O clients:** build genuinely non-blocking pipelines, managing retries with backoff, timeouts, concurrency, and propagation.
7. **Isolate remaining blocking calls:** keep them bounded, on the right scheduler, with monitored queues/pools; avoid hiding blocking behind “async” method names.
8. **Test edge cases:** anonymous, forbidden, invalid/expired tokens, race/cancel, retry, timeout, rollback, overload, client disconnect, shutdown.
9. **Roll out with observability:** canary or traffic splitting per service when appropriate; compare SLOs, GC, resources, errors, and security.
10. **Keep a rollback plan:** allow configuration and data paths to revert to a stable version if issues arise; avoid simultaneous breaking schema/protocol changes unless necessary.

If the goal is solely to raise concurrency for a few blocking integrations, consider optimizing MVC first or splitting out the streaming part into a dedicated service; do not turn a stack switch into an unmeasured full-system rewrite.

## 10. Security and Performance Testing to Avoid Wrong Choices

### 10.1. Functional and Authorization Testing

In MVC, use `MockMvc`/Spring Security test support per test tier; in WebFlux, use `WebTestClient` and reactive security test utilities. Regardless of framework, verify:

- Public endpoints are accessible; private endpoints return appropriate responses when anonymous; invalid credentials are rejected.
- Users with insufficient roles receive 403; specific rules are not accidentally widened by `anyRequest` or another filter chain.
- Browser sessions/cookies and POST/PUT/DELETE handle CSRF as designed; token-based APIs enforce the exact intended policy.
- Security context and method authorization preserve identity across pipelines/async steps, valid thread switches, and outbound calls.
- Logs/traces never expose passwords, access tokens, cookies, or sensitive headers; audits record trustworthy user IDs.
- Timeouts, cancellations, retries, or client disconnects do not turn failed requests into authorization bypasses or replay side effects.

### 10.2. Load and Resilience

Run scenarios with warm-up, sufficient steady-state duration, and **realistic downstream latency**. Measure successful throughput, p50/p95/p99, error/timeout rates, CPU, RSS/heap/GC, pool wait times, and cost per request. For MVC watch thread pools/connection pools; for WebFlux also monitor event-loop/scheduler saturation, pending tasks, Reactor Netty connections, and backpressure behavior. When upstream slows down or the DB pool is exhausted, require graceful degradation rather than unbounded queue growth.

Never treat a low thread count as the sole KPI: a WebFlux app with 8 event-loop threads choked on JDBC over boundedElastic can still consume many threads and miss SLAs. Conversely, an MVC app with virtual threads and a well-bounded database pool may hit targets cleanly. **Real-load results decide.**

## 11. Common Misconceptions and Design Mistakes

| Claim / Practice | Problem | Correction |
|---|---|---|
| “WebFlux is always faster than MVC.” | Non-blocking optimizes resource efficiency on fitting workloads; it does not guarantee lower latency everywhere. | Measure actual workloads and limits. |
| “Returning `Mono` means the whole system is reactive.” | A publisher can wrap blocking APIs; MVC also supports some reactive return types. | Inspect the runtime web type and every driver/client. |
| “Adding the WebFlux starter to MVC automatically switches the server.” | Spring Boot defaults to MVC when both starters are present. | Check auto-configuration and dependency tree. |
| “Calling JDBC directly on the event loop is fine.” | Can stall the few event-loop threads, blocking other requests. | Stay on MVC, switch to a suitable driver, or use a bounded scheduler bridge. |
| “`.block()` makes reactive code easier to read.” | Destroys non-blocking benefits and can fail on the event loop. | Keep pipelines reactive or use an explicit imperative stack. |
| “SecurityContextHolder gets the right user on every thread.” | Reactor context differs from ThreadLocal; thread hops or manual subscribe easily lose context. | Use stack-appropriate security/context APIs and test propagation. |
| “Copy SecurityFilterChain from MVC to WebFlux.” | Filters, request matchers, and DSLs differ. | Write the corresponding `SecurityWebFilterChain` and verify rule semantics. |
| “If we use JWT, always disable CSRF.” | Depends on cookie credentials, how clients send tokens, and the threat model. | Analyze actual authentication per endpoint. |
| “Use reactive transactions together with JPA @Transactional.” | Managers and context propagation have different contracts. | Pick the transaction manager matching the I/O model. |
| “Unbounded `flatMap`/retries for speed.” | Can pile pressure onto upstreams/DBs and amplify outages. | Bound concurrency, connections, timeouts, backoff, and retry budgets. |
| “If you have SSE, you must use WebFlux.” | Servlet also supports async/streaming; trade-offs depend on load. | Measure long-lived connection counts and operational needs. |
| “Virtual threads completely replace reactive.” | Virtual threads help blocking concurrency; they do not make libraries non-blocking or add backpressure. | Compare via benchmarks and semantic requirements. |

## 12. Final Decision Checklist

Before approving an architecture, reviewers should have concrete answers for these items:

- [ ] Request flows and critical blocking/non-blocking dependencies have been inventoried.
- [ ] I/O wait volume, CPU, concurrent connections, and p95/p99 targets have been measured.
- [ ] Database drivers, transaction semantics, and external libraries fit the choice.
- [ ] Actual security stack is confirmed; HTTP/method security configurations use the right APIs.
- [ ] Sessions, cookies, CSRF, authentication, authorization, and 401/403 have negative tests.
- [ ] Identity/trace/transaction context propagation has been verified across async or Reactor pipelines.
- [ ] Schedulers, event loops, database connection pools, rate limits, and retries are bounded.
- [ ] Load tests cover slow upstreams, timeouts, cancellation, shutdown, and recovery.
- [ ] Migration, operational, learning, and rollback costs are documented in an ADR.
- [ ] The decision is based on the specific service's results, not a blanket label for every service.

**Practical conclusion:** Choose **Servlet/MVC** when most business flows are imperative/blocking—especially with JPA/JDBC and existing transactions—or when simplicity and operability outweigh unproven non-blocking gains. Choose **WebFlux/reactive** when concurrent I/O load is high, a substantial end-to-end non-blocking path exists, streaming/fan-out fits well, and the team can handle Reactor, reactive Spring Security, transactions, and observability. Both service styles can coexist in a distributed architecture, provided security contracts and operational quality stay consistent.

## 13. Official References for Deeper Study

- Spring Framework — [WebFlux Overview / MVC or WebFlux?](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): stack-selection basis, I/O model differences, concurrency, and blocking-library impact.
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): starters and default rules when both Web MVC and WebFlux are present.
- Spring Security — [Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): Servlet request authorization.
- Spring Security — [Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context and method-level security.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): contrasting thread-bound transactions with Reactor Context.
- Spring Boot — [Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads): complementary option on Java 21+, limits, and operations.

Official documentation can evolve across releases; when applying to a project, always cross-check the exact Spring Boot / Spring Security versions in use and replace sample configurations with your system's security policies.
