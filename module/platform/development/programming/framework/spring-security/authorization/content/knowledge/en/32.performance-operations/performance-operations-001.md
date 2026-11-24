# Measuring Authorization Check Latency Across HTTP, Method, and Data Layers

## 1. Why Measure Authorization Latency Separately?

In Spring Security, a request can pass through multiple steps: identity authentication, **HTTP-layer authorization checks**, **Java method authorization checks**, and then **data-based permission lookups** such as owner, tenant, ACL, or business state. Each step has a different cost; when users say "the API is slow because of Spring Security", overall HTTP response time alone is not enough to prove which authorization step is the cause.

The goal of this lesson is to know how to **place timers at the right boundaries**, collect metrics without altering allow/deny decisions, compare scenario groups fairly, and find optimization targets while keeping the security policy intact.

After this lesson, you will be able to:

1. Distinguish **total request time** from **authorization decision time**.
2. Measure the three layers separately: **HTTP authorization** (request matcher/AuthorizationManager), **method authorization** (for example @PreAuthorize), and **data-aware authorization** (ACL, owner, tenant, data queries).
3. Use Micrometer Timer, execution counts, denial rates, p50/p95/p99 percentiles, and traces to investigate latency.
4. Write Spring Security + MockMvc tests confirming that timers record at the right layer while verifying that unauthorized users are actually blocked.
5. Design measurements under controlled load without mistaking noise, caching, or whole-application cost for permission evaluation cost.
6. Keep metric tag cardinality under control and avoid exposing sensitive identities or resources.

**Scope:** Spring MVC/Servlet, Java 17+, Spring Boot 3.x with Spring Security 6.x. Some illustrative APIs are pinned to the Spring Security 6.4+ line for readability; when using Spring Security 7 or reactive security, check the actual APIs and execution paths of that version.

## 2. The Three-Layer Model and Measurement Boundaries

~~~text
Client
  │
  │  Total HTTP time: connection + filters + controller + service
  ▼
SecurityFilterChain
  ├── Authentication                            [measure separately if needed]
  ├── HTTP authorization decision               [T_http_auth]
  │      URL + HTTP method + GrantedAuthority
  ▼
Controller
  ▼
Service Spring AOP proxy
  ├── Method authorization decision             [T_method_auth]
  │      @PreAuthorize / AuthorizationManager
  ▼
Service / business logic
  ├── Data-based policy                         [T_data_auth]
  │      ACL, ownership, tenant, query repository
  ▼
Database / cache / application returns response
~~~

| Metric | Where to Place the Timer? | Includes | Excludes |
| --- | --- | --- | --- |
| Full HTTP request | Observe Spring Boot/Actuator HTTP server | Filter chain, controller, business logic, queries, response generation within instrumentation scope | Cannot isolate the authorization decision alone |
| HTTP authorization | Wrap the AuthorizationManager used in authorizeHttpRequests | Delegate evaluation time for HTTP rules; may include obtaining Authentication from Supplier | Controller body, service, downstream business DB |
| Method authorization | Wrap the AuthorizationManager of the @PreAuthorize interceptor | Method condition evaluation time, SpEL, fetching caller information | Method body when using simple pre-authorization |
| Data authorization | Instrument the policy or permission-lookup repository directly | Tenant, owner, ACL comparison; may include DB/cache round-trip if inside the measured region | Does not automatically equal total service time |
| ACL/database query | Instrument the actual repository/DB span | Querying/reading permission data, waiting for a connection if inside the span | Java permission checks after data is fetched, unless the span wraps both |

**Boundaries determine what the numbers mean.** If @PreAuthorize invokes a policy bean via SpEL, for example @PreAuthorize("@policy.canRead(authentication,#p0)"), then **T_method_auth may contain T_data_auth**; the two measurements are nested. If the service performs the data check **after** @PreAuthorize, as in the example in section 5, the two intervals do not overlap. In either case, **do not sum** the timers into "total HTTP" or treat simple subtraction as the absolute cost of one layer: there are other steps, instrumentation overhead, GC, scheduling, and boundary skew.

### 2.1. Distinguishing Allow and Deny Decisions

A denied result can be **faster** because it stops early, or **slower** if it has to query DB/ACL before knowing it should deny. Reporting a single overall p95 across all decisions can hide major differences. You should group by:

- **layer:** http, method, data.
- **result:** allow, deny, abstain (if the manager has an undecided state), error.
- **operation:** a standardized bounded label, for example document-read; add only when genuinely needed.
- **authentication_type/route:** if needed, use bounded groups such as jwt/session/basic and URI templates, never raw tokens or raw URLs.

**Denied** does not mean a Java exception is thrown inside the evaluation function itself: an AuthorizationManager typically returns a non-granted decision; the interceptor or filter handles the corresponding response. **Error** is an execution failure of the evaluator (for example an exception when querying the policy source), which must be separated from deny because the two states have different causes, impacts, and remediation paths.

### 2.2. Quantities You Need to Understand

A Micrometer Timer records **count** and **totalTime**, and can emit distributions/histograms depending on backend configuration. Mean latency is roughly total time divided by count, but it cannot replace p95/p99. High percentiles help detect slow tails, which are often critical in ACL/DB lookups.

| Quantity | Question It Answers |
| --- | --- |
| count / throughput | How many decisions occurred within the time window? |
| p50 | How fast are the majority of typical calls? |
| p95 / p99 | How slow are the slowest 5% / 1% of calls? |
| max (per window) | Are there abnormal latency spikes? |
| allow/deny/error rate | How much is the policy allowing/denying/failing, and did it shift after release? |
| cache hit/miss, query count | Why are data-based decisions fast or slow? |

Do not read p99 from just a handful of calls as a stable property. Percentiles require **enough samples in the window**; always display count alongside charts. If you only need to know how many times a method was called in a test, Timer.count() is useful; if you need to prove an optimization is faster, you must measure repeatedly in a controlled environment.

## 3. Instrumentation and Observation Strategy

### 3.1. Overall Level: HTTP Server Observation

With Spring Boot Actuator and Micrometer configured appropriately, you can use HTTP server observation, typically carrying the **http.server.requests** metric. It shows response times by status, HTTP method, and route template; this is the starting point to locate affected endpoints. However, **http.server.requests does not measure the authorization check in isolation**. A 403 request can also take time because of authentication, exception handling, or other components.

Do not take measurements from @Timed placed around a controller method and call that filter-level authorization cost: by the time the controller executes, HTTP authorization has **already run**. For method security, timing the service body can also miss the interceptor because the interceptor runs before entering the method.

### 3.2. Permission Decision: AuthorizationManager/Observation

Spring Security provides **ObservationAuthorizationManager**, which takes an ObservationRegistry and delegates to an AuthorizationManager to observe permission evaluation. It can help observe managers wrapped in the right place; whether it is currently registered for a specific filter or method interceptor depends on your actual configuration. Do not assume that simply adding Actuator automatically gives you all three separate timers.

In this lesson, we use an explicit **TimedAuthorizationManager** to define clear boundaries and test recording counts. This approach also illustrates how to instrument a system that does not yet use tracing. **Pick one primary instrumentation path** for the same decision to avoid duplicate collection or skewed measurements when combining built-in observation and custom wrappers.

### 3.3. Data: Observing Policy and Queries

For example, a policy checking document read permission must fetch the owner from a repository. Latency here can include connection pool wait, querying, caching, Java processing, and permission comparison. If you need to distinguish each part, create separate spans or timers for **data-policy** and **ACL lookup**.

Do not merely measure Map.get()/String comparison and conclude that a real database system is just as fast. Using a Map in the fixture only serves to **demonstrate wiring and measurement boundaries**; real performance results must be evaluated with appropriate data, connection paths, caches, and load.

## 4. Principles for Accurate and Safe Instrumentation

1. Use **System.nanoTime()** or Micrometer Timer/Sample for elapsed intervals; do not use System.currentTimeMillis() to measure very short segments because it is a wall clock that can be adjusted and lacks suitable resolution.
2. Wrap the exact **authorization evaluation delegate**, without accidentally invoking the delegate twice or altering its result.
3. Record **allow, deny, and error**; if the API allows null/abstain, preserve that state instead of coercing it into allow.
4. Put metric recording in **finally** so error paths are counted too. Use pre-initialized Timers for bounded tags to reduce meter registration overhead on the hot path.
5. Even when instrumenting in detail, keep **authorization denial tests**. An authorization optimization that accidentally bypasses policy is a security bug, no matter how low the latency is.
6. Never use username, email, token, documentId, raw URI containing ids, or SQL parameters as **metric tags**: they explode cardinality, increase storage cost, and risk data exposure.
7. For decisions that hit a DB/cache, measure both **duration** and **query count**; avoid policies that issue N queries for N objects.
8. Be careful with **asynchronous/reactive code**: returning a Mono/CompletionStage is not when the work finishes; place measurement inside the pipeline or a span wrapping completion. The example below uses synchronous execution.

## 5. Complete Example: Spring Security 6.4 + Micrometer + JUnit 5

A hands-on fixture with these steps:

- **HTTP:** GET /api/docs/{id} requires authority document:read. Wrap a dedicated AuthorizationManager for HTTP.
- **Method:** DocumentService.read(id) has @PreAuthorize("hasAuthority('document:read')"), instrumenting the interceptor with an AuthorizationManager for @PreAuthorize.
- **Data:** DocumentAcl looks up the owner from a mock data Map using SecurityContext; instrument the owner/ACL decision.
- **Test:** a user with the right permission and document is allowed, missing permission is blocked at HTTP or method, and reading another user's document is denied at the data layer.
- **Observation:** a single successful request produces three records **http=allow, method=allow, data=allow**; an HTTP-denied path does not execute method/data.

### 5.1. Dependencies

Use a **Spring Boot 3.x** project that manages dependency versions, Java 17+; the test example uses APIs present in Spring Security 6.4.x. Relevant dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'io.micrometer:micrometer-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

In real production systems, **spring-boot-starter-actuator** and a registry such as **micrometer-registry-prometheus** export metrics to an observability stack. The fixture uses **SimpleMeterRegistry** to count in test memory without needing Prometheus or a database and without exposing management endpoints.

### 5.2. A Runnable JUnit File in a Boot 3.x Project

Create **src/test/java/demo/authorization/AuthorizationLatencyTest.java**:

~~~java
package demo.authorization;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Advisor;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.authorization.method.PreAuthorizeAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest(classes = AuthorizationLatencyTest.App.class)
@AutoConfigureMockMvc
class AuthorizationLatencyTest {

    static final String METRIC = "security.authorization.latency";

    /*
     * Wrapper for the Spring Security 6.4.x line.
     * check() is still usable in 6.x; verify against the API when upgrading to 7.x.
     */
    static final class TimedManager<T> implements AuthorizationManager<T> {
        private final AuthorizationManager<T> delegate;
        private final Timer allow;
        private final Timer deny;
        private final Timer abstain;
        private final Timer error;

        TimedManager(AuthorizationManager<T> delegate,
                     MeterRegistry registry, String layer) {
            this.delegate = delegate;
            this.allow = timer(registry, layer, "allow");
            this.deny = timer(registry, layer, "deny");
            this.abstain = timer(registry, layer, "abstain");
            this.error = timer(registry, layer, "error");
        }

        @Override
        @SuppressWarnings("deprecation")
        public AuthorizationDecision check(
                Supplier<Authentication> authentication, T object) {
            long started = System.nanoTime();
            Timer selected = error;
            try {
                AuthorizationDecision result =
                        delegate.check(authentication, object);

                selected = result == null ? abstain :
                        result.isGranted() ? allow : deny;
                return result; // Preserve the decision as-is, including null.
            } finally {
                selected.record(System.nanoTime() - started,
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    static Timer timer(MeterRegistry registry,
                       String layer, String result) {
        return Timer.builder(METRIC)
                .description("Elapsed authorization decision time")
                .tags("layer", layer, "result", result)
                .register(registry);
    }

    /*
     * Mock data policy: Document 42 belongs to alice, 43 belongs to bob.
     * Replace Map with a repository when running real data integration tests.
     */
    static final class DocumentAcl {
        private final Map<Long, String> owners =
                Map.of(42L, "alice", 43L, "bob");
        private final Timer allow;
        private final Timer deny;
        private final Timer error;

        DocumentAcl(MeterRegistry registry) {
            this.allow = timer(registry, "data", "allow");
            this.deny = timer(registry, "data", "deny");
            this.error = timer(registry, "data", "error");
        }

        boolean mayRead(long id) {
            long started = System.nanoTime();
            Timer selected = error;
            try {
                Authentication auth =
                        SecurityContextHolder.getContext()
                                .getAuthentication();
                String owner = owners.get(id);

                boolean permitted = auth != null
                        && auth.isAuthenticated()
                        && owner != null
                        && owner.equals(auth.getName());

                selected = permitted ? allow : deny;
                return permitted;
            } finally {
                selected.record(System.nanoTime() - started,
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    static class DocumentService {
        private final DocumentAcl acl;

        DocumentService(DocumentAcl acl) {
            this.acl = acl;
        }

        @PreAuthorize("hasAuthority('document:read')")
        public String read(long id) {
            if (!acl.mayRead(id)) {
                throw new AccessDeniedException(
                        "Insufficient document permission");
            }
            return "document:" + id;
        }
    }

    @RestController
    @RequestMapping("/api/docs")
    static class DocumentController {
        private final DocumentService service;

        DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/{id}")
        String read(@PathVariable("id") long id) {
            return service.read(id);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity(prePostEnabled = false)
    static class App {

        @Bean
        MeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        DocumentAcl documentAcl(MeterRegistry registry) {
            return new DocumentAcl(registry);
        }

        @Bean
        DocumentService documentService(DocumentAcl acl) {
            return new DocumentService(acl);
        }

        @Bean
        DocumentController documentController(DocumentService service) {
            return new DocumentController(service);
        }

        @Bean
        SecurityFilterChain securityFilterChain(
                HttpSecurity http, MeterRegistry registry)
                throws Exception {

            AuthorizationManager<RequestAuthorizationContext> read =
                    AuthorityAuthorizationManager
                            .hasAuthority("document:read");

            http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/docs/*")
                        .access(new TimedManager<>(read, registry, "http"))
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults());

            return http.build();
        }

        /*
         * prePostEnabled=false disables the default interceptor so we
         * register a single timed @PreAuthorize interceptor.
         * This configuration illustrates one hook point and does not enable @PostAuthorize.
         */
        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor preAuthorizeAdvisor(MeterRegistry registry) {
            AuthorizationManager<MethodInvocation> manager =
                    new PreAuthorizeAuthorizationManager();

            return AuthorizationManagerBeforeMethodInterceptor.preAuthorize(
                    new TimedManager<>(manager, registry, "method"));
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Autowired
    MeterRegistry registry;

    long count(String layer, String result) {
        Timer t = registry.find(METRIC)
                .tags("layer", layer, "result", result)
                .timer();
        return t == null ? 0L : t.count();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void validReaderMeasuresThreeLayers() throws Exception {
        long http = count("http", "allow");
        long method = count("method", "allow");
        long data = count("data", "allow");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("document:42"));

        assertEquals(http + 1, count("http", "allow"));
        assertEquals(method + 1, count("method", "allow"));
        assertEquals(data + 1, count("data", "allow"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void missingHttpPermissionSkipsService() throws Exception {
        long deny = count("http", "deny");
        long method = count("method", "allow")
                + count("method", "deny");
        long data = count("data", "allow")
                + count("data", "deny");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isForbidden());

        assertEquals(deny + 1, count("http", "deny"));
        assertEquals(method, count("method", "allow")
                + count("method", "deny"));
        assertEquals(data, count("data", "allow")
                + count("data", "deny"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void dataPolicyDeniesAnotherOwnersDocument() throws Exception {
        long http = count("http", "allow");
        long method = count("method", "allow");
        long dataDeny = count("data", "deny");

        mvc.perform(get("/api/docs/43"))
                .andExpect(status().isForbidden());

        assertEquals(http + 1, count("http", "allow"));
        assertEquals(method + 1, count("method", "allow"));
        assertEquals(dataDeny + 1, count("data", "deny"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "other")
    void directServiceCallIsDeniedByMethodInterceptor() {
        long methodDeny = count("method", "deny");

        assertThrows(AccessDeniedException.class,
                () -> service.read(42L));

        assertEquals(methodDeny + 1, count("method", "deny"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:read")
    void correctAuthorityDoesNotBypassDataOwnership() throws Exception {
        long dataDeny = count("data", "deny");

        mvc.perform(get("/api/docs/42"))
                .andExpect(status().isForbidden());

        assertEquals(dataDeny + 1, count("data", "deny"));
    }
}
~~~

**Run:** In a Gradle Spring Boot 3.x project using Java 17+ and JUnit Jupiter:

~~~bash
./gradlew test --tests "demo.authorization.AuthorizationLatencyTest"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "demo.authorization.AuthorizationLatencyTest"
~~~

**Expected outcome from the fixture logic:** 5 tests pass when using the versions and dependencies stated above. This is an expected result, not an executed benchmark log. MockMvc verifies 200/403, while Timer.count() verifies **the exact number of recorded decisions**. The fixture does not enforce hard timing thresholds because microsecond/millisecond measurements in CI fluctuate easily.

### 5.3. Why Does the Fixture Record Exactly Three Layers?

**Allow path — Alice reads document 42:**

1. The HTTP AuthorizationManager evaluates document:read and records **http/allow**.
2. The @PreAuthorize interceptor evaluates the authority on the service and records **method/allow**.
3. The service calls DocumentAcl with id=42. The Map contains owner=alice and records **data/allow**.
4. The controller returns the string **document:42** and HTTP 200.

**Missing functional permission — Alice only has another authority:**

1. The HTTP manager returns deny and records **http/deny**.
2. The filter does not invoke the controller, so there are no new method/data records.
3. MockMvc returns 403.

**Right authority but wrong owner — Alice reads document 43:**

1. The HTTP manager allows and records http/allow.
2. The method interceptor allows and records method/allow.
3. DocumentAcl finds owner=bob, returns false, and records data/deny.
4. The service throws AccessDeniedException, and the request is blocked with 403.

**Calling the service directly via the bean:**

- The method interceptor still checks permissions and records method/deny if document:read is missing.
- It does not pass through the HTTP filter, so http is not recorded.
- If the interceptor denies before entering the method body, there is no ACL lookup and data is not recorded.

**Limitations of the example:** A Map is used as mock ACL data; measuring the data layer here is **in-memory lookup + owner comparison**, which does not prove DB or cache performance. Recording all three Timers in one HTTP request does not mean the measurements are statistically independent, because they share the same machine load and the same request. Tests count records; they do not turn authorization decisions into separate "extra measurement" calls.

### 5.4. What to Keep When Changing the Architecture

- **@EnableMethodSecurity(prePostEnabled=false)** in the fixture intentionally disables the default pre/post configuration to register a single timed @PreAuthorize advisor. In an application with @PostAuthorize, @PreFilter, @PostFilter, or other interceptors, you must keep all those rules intact; do not copy a config that disables defaults and forget to re-register the active policies.
- Never attach the same interceptor twice. Duplicating advisors increases cost, inflates record counts, and can alter evaluation behavior.
- If you move data conditions into @PreAuthorize SpEL, the data timer will **nest inside** the method timer; you must adjust how you read dashboards accordingly.
- A call via **new DocumentService(...)** is not protected by a Spring proxy. Tests directly use the injected bean.
- For production testing, verify the mapping from user/role/claim to authorities; @WithMockUser grants authorities directly and only verifies enforcement in the fixture.
- When using policies based on tenant, status, permission expiration, or caching, add tests for both allow and deny at every boundary.

## 6. Measuring and Comparing in Real Systems

### 6.1. Minimal Benchmark Scenarios

Build a test matrix before running so layers are comparable:

| Group | HTTP | Method | Data/ACL | Expected Result | Purpose |
| --- | --- | --- | --- | --- | --- |
| A | valid authority | valid @PreAuthorize | valid owner | allow | Happy path across all 3 layers |
| B | missing authority | not invoked | not invoked | deny at HTTP | Cost of early denial |
| C | valid authority | missing specific authority | not invoked | deny at method | Cost of interceptor/SpEL |
| D | valid authority | valid | wrong tenant/owner | deny at data | Cost of reading ACL before denial |
| E | valid | valid | cache hit | allow | Data policy with warm cache |
| F | valid | valid | cache miss / DB lookup | allow or deny | Cost of real data access |
| G | valid | valid | large ACL / many objects | per permission | Scalability with data size |

The fixture in section 5 demonstrates A, B, D, and the standalone method path; comparing C, E, F, and G requires real data and policies. You cannot measure the method layer by taking total service time and subtracting JDBC time while all other steps still fluctuate.

### 6.2. Controlling Measurement Conditions

1. **Pin versions:** JDK, Spring Security, Spring Boot, JVM flags, CPU/memory, pool sizes, TLS state, database, and cache.
2. **Separate environments:** A MockMvc test is suitable for proving policy and instrumentation; end-to-end latency measurements should run on a real deployed application (with network, DB, thread pools).
3. **Warm-up:** The JVM needs JIT compilation, class loading, AOP initialization, and cache warm-up. Measure after a controlled warm-up phase, while keeping a separate cold-cache scenario if you want to study it.
4. **Allow/deny ratio:** Keep the workload mix fixed. Increasing early-denied requests can lower overall p95 without actually optimizing the policy code.
5. **Data and permissions:** Ensure the same accounts, authorities, resource types, and ACL scale between baseline and candidate; use safe test accounts/configurations.
6. **Load:** Run across multiple concurrency and request rate levels. Latency can grow nonlinearly when connection pools or CPU saturate; low-load p95 does not represent high load.
7. **Repeat:** Run multiple trials, recording count, throughput, p50/p95/p99, error rate, GC, CPU, DB wait time, and cache hit rate; do not cherry-pick one "best" run.
8. **Test permission correctness:** Under the same workload, verify HTTP statuses, per-layer decisions, and data state. An optimization that skips rules can make results fast yet wrong.
9. **Never use sleep to fake benchmarks:** Sleep latency only checks that a Timer wraps a code block; it does not simulate real DB/ACL distributions.

### 6.3. When Should You Use JMH?

When comparing only the tiny pure-Java cost of two policy algorithms (for instance looking up data in a Map versus a Set), JMH handles warm-up, measurement loops, JIT optimizations, and microbenchmark noise. However, JMH **does not represent** the cost of the HTTP filter chain, proxies, network, database, or connection pools. Do not report "reduced API latency by 50%" just because JMH showed a Set check is faster.

Combine approaches: **unit tests** for decision correctness, **JMH** for Java operators when truly needed, **integration/traces** for execution paths, and **load tests** for production p95/p99.

## 7. Micrometer, Histograms, and Operational Dashboards

### 7.1. Metric Design

In the fixture, the custom metric is named **security.authorization.latency**, with two tags **layer** and **result**. Production environments can add **operation** with bounded values such as document-read, invoice-approve. Never add document ids, usernames, email addresses, raw URLs, query strings, or dynamic SpEL strings to tags.

Examples of valid metric series:

~~~text
security.authorization.latency{layer="http",result="allow"}
security.authorization.latency{layer="method",result="deny"}
security.authorization.latency{layer="data",result="allow"}
~~~

These are **illustrative Micrometer names + tags**, not the export format of a specific backend. When exported to Prometheus via micrometer-registry-prometheus, names and units are converted by the registry, typically into a metric family with suffixes **_seconds_count**, **_seconds_sum**, and **_seconds_bucket** (if histograms are configured). Do not treat internal Micrometer names as verbatim PromQL query names.

### 7.2. Why a Plain Timer May Not Provide Server-Side p95?

A basic Timer always has count and total time; **histogram buckets must be enabled** per backend/configuration. With Prometheus, enable percentile histograms or a finite set of SLO buckets for timers whose percentiles you want to inspect. Example configuration where the Timer is registered in a real system:

~~~java
// Illustrative replacement for timer(...) in the fixture when using
// a histogram-capable registry; not needed for counting tests.
return Timer.builder("security.authorization.latency")
        .tags("layer", layer, "result", result)
        .serviceLevelObjectives(
                java.time.Duration.ofMillis(1),
                java.time.Duration.ofMillis(5),
                java.time.Duration.ofMillis(20),
                java.time.Duration.ofMillis(100))
        .publishPercentileHistogram()
        .register(registry);
~~~

For very fast in-memory decisions, sub-1 ms buckets can be added based on real numbers; for DB-backed ACL queries, larger buckets may be useful. Bucket counts and tag combinations affect memory usage and time-series count. Client-computed percentiles cannot be accurately aggregated across multiple instances like server-side histograms; choose the approach that fits your backend.

### 7.3. Illustrative Prometheus Queries

Suppose the metric is exported as **security_authorization_latency_seconds** with buckets; for example, p95 of data/allow decisions across all instances:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(security_authorization_latency_seconds_bucket{
      layer="data",result="allow"
    }[5m])
  )
)
~~~

Counting the rate of denied HTTP decisions:

~~~promql
sum(
  rate(security_authorization_latency_seconds_count{
    layer="http",result="deny"
  }[5m])
)
~~~

The HTTP denial ratio among allowed/denied decisions can be illustrated as:

~~~promql
sum(rate(security_authorization_latency_seconds_count{
  layer="http",result="deny"
}[5m]))
/
clamp_min(
  sum(rate(security_authorization_latency_seconds_count{
    layer="http",result=~"allow|deny"
  }[5m])),
  1e-9
)
~~~

**Interpretation:** This is the ratio **among decisions measured at that HTTP manager**, not the 403 rate across all application requests. Paths blocked before reaching the manager, other matchers, or failed authentication may not be in the denominator. For the full picture, combine with http.server.requests and the corresponding authentication/exception metrics.

### 7.4. What Should Dashboards Display?

- Top row: overall HTTP request p95/p99 by route template and status; error rate; throughput.
- Second row: authorization latency p50/p95/p99 by layer, result, operation; count/rate in the same window to confirm sample size is sufficient.
- Third row: DB/ACL query latency, queries per decision, cache hit/miss, connection pool saturation.
- Include trace exemplars or correlation ids in a separate tracing/logging tool when investigating rare cases. Correlation id is **not** a metric tag.
- Annotate deployment and policy-change timestamps to read regressions accurately; alert only when data volume is sufficient and workload matches.

## 8. Bottleneck Analysis and Optimization Directions

### 8.1. Slow HTTP Authorization

**Symptom:** T_http_auth increases while method/data do not increase correspondingly.

**Check:** number of matchers, matcher ordering, custom AuthorizationManagers, remote policy engine/identity provider calls, and token re-validation/introspection on the evaluation path. Rules that merely compare authorities are very cheap; if an HTTP check takes tens of ms, look for I/O calls or extra processing rather than blaming the concept of roles/permissions.

**Remediation:** reduce I/O inside HTTP policies, configure matchers deliberately, cache permission data with appropriate TTL/invalidation; never cache only by user while ignoring tenant, resource scope, or permission version.

### 8.2. Slow Method Authorization

**Symptom:** T_method_auth is high, especially with complex SpEL expressions or repeated lookups.

**Check:** whether multiple interceptors apply together; whether @PreAuthorize calls a policy bean that performs I/O; whether rules after annotation changes run multiple times; whether self-invocation/proxy call paths behave as expected.

**Remediation:** clarify where policies live, eliminate redundant data calls, reuse defined check logic, and separate queries from expression evaluation where sensible. **Do not** remove @PreAuthorize or replace it with authenticated() just to reduce latency.

### 8.3. Slow Data Authorization

**Symptom:** T_data_auth grows with resource count, cache miss rate, or ACL size; DB spans show expensive queries.

**Check:** N+1 queries, missing indexes on (tenant_id, resource_id, principal_id/action), expensive ACL joins, connection pool saturation, network latency, cache keys/invalidation rules, and repeated queries when one request checks multiple resources.

**Remediation:** index accurately for real queries; push permission checks and result filtering into properly constrained queries; batch lookups instead of one query per record; cache with full permission context and a refresh strategy; avoid loading unauthorized data into memory only to filter it afterward when the database can restrict it upfront.

**Cache security boundary:** a cached allow decision for user A on resource 42 must never be reused for user B or another tenant. When permissions are revoked, stale permissions must not persist beyond the system's accepted window. Cache performance and correctness must be verified together.

### 8.4. P95 Dropped, Yet Users Still See a Slow API

If authorization time drops from 3 ms to 1 ms while request latency is several hundred ms, the overall HTTP gain can be negligible. Determine the **time share** of each component and re-check with traces/load tests; do not spend days optimizing a slice that occupies very little of the latency budget.

Conversely, if a list request for 100 items calls the ACL 100 times at 2 ms each, the total cost can be substantial even if the p95 of **each individual decision** looks low. Therefore you must measure **decision calls per request**, not just per-call latency.

## 9. Common Misinterpretations

| Symptom | Wrong Conclusion | Right Reading |
| --- | --- | --- |
| High HTTP p95, low HTTP auth timer | "Not security related" | Authentication or method/data auth can still be slow; trace end-to-end |
| Very low latency on HTTP 403 | "Policy is perfectly optimized" | It may have been denied before reaching service/DB |
| Data timer drops when cache enabled | "Cache is always safe" | Must test TTL, revocation, tenant, and cache key |
| Method timer contains DB call in SpEL | "Sum method + data for total" | Timers are nested; summing double-counts |
| Low Timer.count after a load run | "Authorization is rarely called" | Wrong path matching, blocked earlier, or missing instrumentation |
| P99 fluctuates wildly with few samples | "Update caused a regression" | Increase sample size, multiple windows, control confidence |
| MockMvc runs fast | "Production timing will match" | MockMvc does not simulate production network, DB, or concurrency |
| Tests only assert duration | "Optimization succeeded" | Rules may have been bypassed; must assert allow/deny |
| CPU spikes after enabling histograms on all tags | "Business service has a bug" | Metrics may create too many time series/buckets |
| Putting userId/resourceId in tags | "Easier to investigate" | Unbounded cardinality and data-exposure risk; use protected traces/logs |

**Define measurement boundaries clearly:** Decisions at request matchers may only evaluate functional permissions; object/tenant policies appear after the controller loads the resource. When refactoring the flow to push data checks into the method interceptor, the method group rises and the data group shifts even though real total time did not change. Dashboards should tag instrumentation and policy versions for fair comparisons.

## 10. Operational Runbook When an Authorization Latency Alert Fires

1. Identify route template, HTTP method, status, timestamp, frequency, and environment; verify sample count is sufficient.
2. Compare HTTP p95/p99 against **http/method/data authorization**, separating allow and deny.
3. Inspect traces of one or more real requests; look for I/O spans, pool waits, ACL queries, or policy engine calls.
4. Check recent changes: code, rules, indexes, cache hit rate, token/role hierarchy versions, ACL scale.
5. Reproduce with matching data and permission ratios, changing one factor at a time.
6. After optimizing, re-run tests for **authorized**, **unauthorized**, **wrong owner/tenant**, and **recently revoked permission**.
7. Compare baseline and candidate on p95/p99, sample count, throughput, resource usage, and allow/deny ratio; note any metric config changes.
8. Monitor post-release: latency improvements must go hand in hand with permission correctness and no abnormal increase in errors/denials.

**Example target selection:** You can set a latency budget per path: static HTTP permission checks should be lower than DB-backed ACL checks. However, concrete thresholds must come from your baseline and application SLOs; do not apply an arbitrary number to every system. For critical permissions, prioritize correctness and data consistency over tiny time savings.

## 11. Practice Exercises and Completion Criteria

**Exercise 1 — Spot the wrong measurement point.** Put System.nanoTime() inside the controller method and compare it with http.server.requests. Explain why controller time excludes HTTP filter authorization that ran beforehand. Fix it with a wrapper placed on the HTTP AuthorizationManager.

**Exercise 2 — Method-layer denial.** Add a method with @PreAuthorize requiring document:delete; call the bean directly as a user who only has document:read. Tests must prove method/deny increments once while data policy does not run.

**Exercise 3 — Real data.** Replace the owners Map with a read-only repository in a test environment; add a span for the permission query. Measure cold/warm cache; test 100, 10,000, and 1,000,000 records with appropriate indexes. Report count, p50/p95/p99, query count, and cache hit rate; do not fabricate numbers.

**Exercise 4 — Permission in SpEL.** Move owner checks into a bean called from @PreAuthorize. Use traces to show the data span lies inside method authorization. Fix the dashboard so it does not sum two nested timers.

**Exercise 5 — Multiple objects.** Write a feature to read a list of 100 documents; compare per-item ACL checks against a batched query. You must compare **query count**, total request time, per-decision latency, and the returned list. Both approaches must return only authorized data.

**Completion criteria:**

- Have a boundary diagram for **HTTP / method / data**; clearly mark potentially nested spans.
- Record **count** and **duration** for allow/deny/error at each active layer without creating unbounded-cardinality tags.
- Tests prove HTTP deny blocks method/data; method deny blocks data; data deny still prevents returning resources.
- Measurements include baseline, warm-up, workload mix, sample count, p95/p99, and described cache/DB conditions.
- After any optimization, the permission matrix remains unchanged outside intentionally approved policy changes.
- Never claim production performance results based on a Map/MockMvc fixture or a single isolated microbenchmark.

## 12. References

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.4/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/6.4/servlet/authorization/method-security.html
- Spring Security — AuthorizationManagerBeforeMethodInterceptor API 6.4: https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html
- Spring Security — ObservationAuthorizationManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ObservationAuthorizationManager.html
- Spring Boot — Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
