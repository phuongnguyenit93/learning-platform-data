# Bounding Timeouts, Connections, and Pending Tasks at External Boundaries — Spring Security Reactive

## 1. Objectives and Context

After this lesson, you will be able to configure stage-by-stage timeouts, cap active connections and queued acquire requests, enforce an in-flight bulkhead for the entire external operation, handle timeouts, overload, and cancellation reactively, test slow/failing provider scenarios, and monitor metrics to tune limits without weakening authentication or authorization.

In Spring WebFlux + Spring Security, a single request may need to call an Identity Provider, OAuth2 token introspection endpoint, JWK endpoint, authorization API (PDP), profile/entitlement service, Redis, a database, or LDAP. Using Reactor/Netty avoids holding a thread while waiting for each HTTP response; **being reactive does not mean requests, connections, queues, and memory are automatically bounded**.

~~~text
Incoming request
   -> Spring Security WebFilterChain (authentication/authorization)
   -> Controller / service
   -> [Cap on external calls in flight]
   -> [Wait to acquire connection from pool]
   -> [TCP/TLS connection]
   -> [Send request, await response, decode body]
   -> clear response or mapped error
~~~

To prevent saturation, you must enforce limits along **three separate dimensions**:

- **Time:** requests must complete or cancel before a deadline; distinguish pool wait, TCP connect, TLS, response, and total business duration.
- **Connections:** downstream systems must not be flooded with too many open sockets/HTTP connections.
- **Pending tasks:** both the connection-acquire queue and waiting business operations must have ceilings or rejection policies.

If a remote call informs a security decision, timeout/connection errors **must never turn into an access-granting decision**.

## 2. Where Do Limits Actually Take Effect?

| Mechanism | Protection Scope | What It Does Not Protect |
| --- | --- | --- |
| `ConnectionProvider.maxConnections(N)` | Active connections per connection pool/remote endpoint | Total application requests; pending operations |
| `pendingAcquireMaxCount(N)` | Number of requests *waiting to acquire a connection* | Work before the acquire step; scheduler queues |
| `pendingAcquireTimeout(Duration)` | How long a single acquire may wait | DNS/TCP/TLS, response, and business processing |
| `ChannelOption.CONNECT_TIMEOUT_MILLIS` | TCP connect | DNS, TLS handshake, body |
| `HttpClient.responseTimeout(Duration)` | Network response/read timeout | Pool queue time and overall deadline |
| `Mono.timeout(Duration)` | Deadline from subscription until `Mono` emits/completes | Does not undo external side effects already triggered |
| `Semaphore.tryAcquire()` | In-flight calls holding a permit; can fail fast | Does not directly cap sockets opened by third-party libraries |
| `Flux.flatMap(mapper, concurrency)` | Concurrent inner publisher subscriptions **within one pipeline** | Total concurrency across thousands of pipelines |
| `Schedulers.newBoundedElastic(...)` | Threads/queued tasks for a blocking bridge | Underlying blocking client sockets/pools and real deadlines |

**Distinguish three queues:** (1) HTTP request queue at ingress/proxy, (2) Reactor Netty's pending-acquire queue, (3) scheduler task queue for blocking clients. They do not substitute for one another.

### Example of a time budget

Suppose an endpoint has roughly a 2-second budget for an outbound profile lookup:

- `pendingAcquireTimeout = 200 ms`: do not wait too long for a socket.
- `CONNECT_TIMEOUT_MILLIS = 300`: do not wait too long for TCP connect.
- `responseTimeout = 1,200 ms`: cut off connections with overly slow network responses.
- `bodyToMono(Profile.class).timeout(1,800 ms)`: deadline wrapping the entire profile-fetch pipeline.

These numbers are illustrative only; they are **not** a standard configuration template. DNS, TLS, retries, and overhead also consume time; an outer timeout may trip earlier. For a `Flux` continuously emitting elements, `timeout(Duration)` bounds the idle gap between signals, not necessarily total stream duration. Choose deadlines from SLAs and actual p95/p99 latencies.

Reactor Netty pooling is typically scoped per remote host:port; HTTP/2 can multiplex multiple streams over a single connection, so do not strictly equate `maxConnections` with request count. With multiple replicas, total connections to a provider can approach the sum of each replica's limit.

## 3. Runnable Java 17+ Example: Spring Security and an External Profile API

The example uses a Gradle Spring Boot 3.x project with the Java plugin and Spring Boot dependency management. Required dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
tasks.register('runMockProfileProvider', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.boundary.MockProfileProvider'
}
~~~

All Java sources live in package `com.example.boundary`. HTTP Basic and hardcoded accounts here are **for localhost testing only**; production must use real authentication and credential-management systems.

### 3.1. Bootstrap and security chain

File `src/main/java/com/example/boundary/BoundaryDemoApplication.java`:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/boundary/DemoSecurityConfig.java`:

~~~java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class DemoSecurityConfig {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/current-profile").authenticated()
                        .anyExchange().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Fixture FOR LOCAL DEMO ONLY. Do not use {noop} in production.
    @Bean
    MapReactiveUserDetailsService demoUsers() {
        UserDetails fast = User.withUsername("demo")
                .password("{noop}demo123").roles("USER").build();
        UserDetails slow = User.withUsername("slow")
                .password("{noop}slow123").roles("USER").build();
        return new MapReactiveUserDetailsService(fast, slow);
    }
}
~~~

An anonymous request to the endpoint receives **401** from Spring Security before touching the outbound client. If already authenticated and the profile provider fails, that is an availability failure for an authenticated request: do not turn it into 401 or synthesize an identity.

### 3.2. Dedicated WebClient: pool, pending queue, connect and response timeouts

File `src/main/java/com/example/boundary/ExternalClientConfig.java`:

~~~java
package com.example.boundary;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class ExternalClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider profileConnectionProvider() {
        return ConnectionProvider.builder("profile-pool")
                .maxConnections(8)
                .pendingAcquireMaxCount(8)
                .pendingAcquireTimeout(Duration.ofMillis(200))
                .maxIdleTime(Duration.ofSeconds(20))
                .metrics(true)
                .build();
    }

    @Bean("profileWebClient")
    WebClient profileWebClient(
            WebClient.Builder builder,
            ConnectionProvider profileConnectionProvider,
            @Value("${external.profile.base-url:http://127.0.0.1:9011}")
                    String baseUrl) {

        HttpClient httpClient = HttpClient.create(profileConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
                .responseTimeout(Duration.ofMillis(1200));

        return builder.baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(c -> c.defaultCodecs().maxInMemorySize(128 * 1024))
                .build();
    }
}
~~~

Exact meaning: at most 8 connections per pool key, at most 8 pending-acquire slots (not 8 business requests), each waiting at most 200 ms to acquire a connection. `maxIdleTime` does not replace business timeouts. `maxInMemorySize` caps response decoding buffers, preventing huge upstream bodies from spiking memory. `WebClient.Builder` from Spring Boot preserves existing customizers/observations in the context. `metrics(true)` emits Reactor Netty metrics when a Micrometer registry is present.

For HTTPS, DNS, TLS handshake, and proxies also matter. `CONNECT_TIMEOUT_MILLIS` measures TCP connect and does not automatically cover those stages. When tuning clients, target the actual client in use: configuring `profileWebClient` **does not automatically apply** to internal HTTP clients used by OIDC/JWK/introspection or other SDKs.

### 3.3. Non-blocking bulkhead and request-wide deadline

File `src/main/java/com/example/boundary/ExternalProfileClient.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class ExternalProfileClient {
    private final WebClient webClient;
    private final Semaphore permits;
    private final Duration deadline;

    @Autowired
    public ExternalProfileClient(
            @Qualifier("profileWebClient") WebClient webClient) {
        this(webClient, 12, Duration.ofMillis(1800));
    }

    // Allows testing small capacity and deadline.
    ExternalProfileClient(WebClient webClient,
                          int maxInFlight, Duration deadline) {
        this.webClient = webClient;
        this.permits = new Semaphore(maxInFlight);
        this.deadline = deadline;
    }

    public Mono<Profile> fetch(String subject) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Profile boundary is busy"));
            }

            return webClient.get()
                    .uri(uri -> uri.path("/profiles/{subject}")
                            .build(subject))
                    .retrieve()
                    .onStatus(
                            status -> status.value() == 404,
                            response -> Mono.just(new ResponseStatusException(
                                    HttpStatus.NOT_FOUND, "Profile not found")))
                    .onStatus(
                            HttpStatusCode::isError,
                            response -> Mono.just(new ResponseStatusException(
                                    HttpStatus.SERVICE_UNAVAILABLE,
                                    "Profile provider rejected the request")))
                    .bodyToMono(Profile.class)
                    .switchIfEmpty(Mono.error(new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Empty profile response")))
                    .timeout(deadline)
                    .onErrorMap(
                            ex -> !(ex instanceof ResponseStatusException),
                            ex -> new ResponseStatusException(
                                    HttpStatus.SERVICE_UNAVAILABLE,
                                    "Profile provider unavailable", ex))
                    .doFinally(signal -> permits.release());
        });
    }

    public record Profile(String id, String displayName) {}
}
~~~

Why place `tryAcquire()` inside `Mono.defer`? Constructing a `Mono` does not execute the network call; the permit is acquired only upon subscription. `tryAcquire()` does not block the event loop: once 12 requests hold slots, new requests fail fast instead of waiting in an unbounded queue. `doFinally` executes on completion, error, or **cancel**, preventing permit leaks when clients time out/cancel requests. Never call `Semaphore.acquire()`, `Thread.sleep()`, or `.block()` on the event loop.

This is a **per-JVM/service-instance** bulkhead. The 12 in-flight calls include those waiting for connections, connecting, and reading responses. The limits of 8 connections, 8 pending acquires, and 12 in-flight are **independent** caps, not a guarantee that “12 = 8 + 4” at every instant.

In this example, any error not already mapped as a `ResponseStatusException` becomes 503 for easy observation; in real deployments, **classify separately** connect timeouts, acquire timeouts, pool pending overflow, HTTP 5xx, decode errors, and code bugs so programming errors are not masked.

### 3.4. Controller receiving the authenticated principal

File `src/main/java/com/example/boundary/ProfileController.java`:

~~~java
package com.example.boundary;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {
    private final ExternalProfileClient profiles;

    ProfileController(ExternalProfileClient profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/current-profile")
    Mono<ExternalProfileClient.Profile> currentProfile(
            Mono<Principal> principal) {
        return principal.flatMap(p -> profiles.fetch(p.getName()));
    }
}
~~~

In real OIDC applications, use a trusted identifier key (typically combining issuer and subject) rather than assuming `Principal.getName()`/email/displayName is always immutable. In this example, Basic Auth provides fixed usernames for simple simulation.

### 3.5. Mock provider to observe timeouts

File `src/main/java/com/example/boundary/MockProfileProvider.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.netty.http.server.HttpServer;

public class MockProfileProvider {
    public static void main(String[] args) {
        var server = HttpServer.create()
                .host("127.0.0.1")
                .port(9011)
                .route(routes -> routes
                        .get("/profiles/demo", (req, res) ->
                                res.header("Content-Type", "application/json")
                                        .sendString(Mono.just(
                                                "{\"id\":\"demo\","
                                                + "\"displayName\":\"Demo User\"}")))
                        .get("/profiles/slow", (req, res) ->
                                res.header("Content-Type", "application/json")
                                        .sendString(
                                                Mono.delay(Duration.ofSeconds(3))
                                                        .map(tick ->
                                                                "{\"id\":\"slow\","
                                                                + "\"displayName\":\"Slow User\"}"))))
                .bindNow();

        System.out.println("Mock provider: http://127.0.0.1:9011");
        server.onDispose().block();
    }
}
~~~

In two separate terminals:

~~~bash
# Terminal 1
./gradlew runMockProfileProvider

# Terminal 2
./gradlew bootRun
~~~

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`, then call:

~~~bash
curl -i http://localhost:8080/api/current-profile
curl -i -u demo:demo123 http://localhost:8080/api/current-profile
curl -i -u slow:slow123 http://localhost:8080/api/current-profile
~~~

| Scenario | Expectation |
| --- | --- |
| No authentication | **401** from Spring Security, provider not called |
| Account `demo`, fast provider | **200** and JSON `{"id":"demo","displayName":"Demo User"}` |
| Account `slow`, provider responds after 3 seconds | **503** due to response timeout/deadline |

Never use demo user/password pairs, `{noop}`, or localhost HTTP as a production configuration template.

## 4. Testing Deadlines, Overload, and Permit Release on Cancellation

Test with a fake `ExchangeFunction` returning a response after a delay: it accurately verifies service permit/deadline logic, but **does not** create physical connections, so it does not replace pool integration tests.

File `src/test/java/com/example/boundary/ExternalProfileClientTest.java`:

~~~java
package com.example.boundary;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ExternalProfileClientTest {
    private WebClient fakeServer(Duration delay) {
        return WebClient.builder()
                .exchangeFunction(request ->
                        Mono.delay(delay).map(ignored ->
                                ClientResponse.create(HttpStatus.OK)
                                        .header(HttpHeaders.CONTENT_TYPE,
                                                MediaType.APPLICATION_JSON_VALUE)
                                        .body("{\"id\":\"demo\","
                                                + "\"displayName\":\"Demo User\"}")
                                        .build()))
                .build();
    }

    private void expect503(Throwable ex) {
        assertThat(ex).isInstanceOf(ResponseStatusException.class);
        assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    }

    @Test
    void slowProviderExceedsOverallDeadline() {
        var client = new ExternalProfileClient(
                fakeServer(Duration.ofMillis(250)),
                1, Duration.ofMillis(50));

        StepVerifier.create(client.fetch("demo"))
                .expectErrorSatisfies(this::expect503)
                .verify();
    }

    @Test
    void fullBulkheadRejectsFastAndCancelReturnsPermit() {
        var client = new ExternalProfileClient(
                fakeServer(Duration.ofMillis(250)),
                1, Duration.ofSeconds(1));

        Disposable first = client.fetch("demo").subscribe();
        try {
            StepVerifier.create(client.fetch("demo"))
                    .expectErrorSatisfies(this::expect503)
                    .verify();
        } finally {
            first.dispose();
        }

        StepVerifier.create(client.fetch("demo"))
                .assertNext(profile ->
                        assertThat(profile.id()).isEqualTo("demo"))
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests 'com.example.boundary.ExternalProfileClientTest'
~~~

When fully configured, expect **2 tests PASS**. The second test proves a call after cancelling a prior request can still proceed through the bulkhead. These tests **do not measure `maxConnections`**; verifying the pool requires a real Reactor Netty `HttpServer` on a random port, sending enough concurrent requests, and checking active/pending/acquire failures.

## 5. Bounding Fan-Out and Blocking Boundaries

### 5.1. Fan-out of multiple calls within one pipeline

~~~java
Flux<Entitlement> permissions =
        Flux.fromIterable(entitlementIds)
                .flatMap(id -> entitlementClient.fetch(id), 8);
~~~

This is an **illustrative snippet** assuming the application already defines `Entitlement`, `entitlementIds`, and `entitlementClient`. `flatMap(..., 8)` keeps at most 8 inner publishers subscribed concurrently within this pipeline; it **does not** limit the total across pipelines from many user requests. Combine with client/service limits like the example above. When result order must be preserved, consider `flatMapSequential` or an appropriate model.

### 5.2. Bridging to blocking APIs

For LDAP/JDBC/SDK libraries that only expose blocking interfaces, isolate dedicated threads:

~~~java
Scheduler blockingScheduler =
        Schedulers.newBoundedElastic(4, 20, "directory-io");

Mono<DirectoryUser> user =
        Mono.fromCallable(() -> blockingDirectory.findById(userId))
                .subscribeOn(blockingScheduler)
                .timeout(Duration.ofSeconds(2));
~~~

This illustrative snippet requires existing `blockingDirectory`, `DirectoryUser`, and `userId` types/variables plus imports for `reactor.core.scheduler.Scheduler`, `Schedulers`, and `reactor.core.publisher.Mono`. `newBoundedElastic(4, 20, ...)` allows at most 4 backing threads and caps queued tasks **per backing thread** per the Reactor API; when full, it can throw `RejectedExecutionException`. Manage scheduler `dispose()`. `timeout()` cancels the subscription, but **does not guarantee** immediately stopping a blocking I/O call that ignores interrupts. You must also configure driver/SDK timeouts and separate connection limits.

## 6. Direct Connection to Spring Security Reactive

Two decision branches must be distinguished:

**Calling an external service after authentication.** A profile lookup failure should surface as an availability error such as 503. Never alter usernames, synthesize roles, or treat an upstream timeout as an unauthenticated account.

**External service is the source of authentication or authorization decisions.** Examples include opaque-token introspection, JWK key refresh, OIDC UserInfo, or a PDP. If the provider fails or authentication evidence cannot be obtained, **never grant access by default**. This is a wrong pattern:

~~~java
// WRONG: Grants access when PDP cannot be reached!
return remoteDecision.onErrorReturn(new AuthorizationDecision(true));
~~~

The snippet above is solely to recognize an anti-pattern, not code to use. Always fail closed, distinguish genuine denials from unavailability, and preserve accurate HTTP contracts:

| Status | Meaning |
| --- | --- |
| **401 Unauthorized** | Request is unauthenticated or credentials are invalid |
| **403 Forbidden** | Authenticated, but policy forbids access |
| **503 Service Unavailable** (if exception mapping supports it) | Unable to complete an external dependency; request must not pass |

A custom reactive authorization manager may emit exceptions that must be mapped at the appropriate filter/exception-handler layer; do not assume every error automatically turns into 503. Never use `onErrorResume(error -> Mono.just(true))` or `onErrorReturn(AuthorizationDecision(true))` on permission verification paths. If tokens/permissions are cached, define TTL, key rotation, and revocation requirements rather than “caching forever” to avoid calling the IdP.

**Configure the right client.** `profileWebClient` applies only to the example service. When using `oauth2ResourceServer().jwt()`, `oauth2ResourceServer().opaqueToken()`, or `oauth2Login()`, Spring Security may create its own decoder, introspector, or metadata/JWK HTTP clients. Identify the exact component making the outbound call and configure it via the hook supported in your version (such as a custom `ReactiveOpaqueTokenIntrospector` or `ReactiveJwtDecoder`). Changing settings on an unrelated `WebClient` does not protect introspection/JWK calls.

## 7. Retries, Cancellation, and Cascading Load

- Use small bounded retries with backoff/jitter **only** for transient errors and safely repeatable operations; retries must stay within the total deadline.
- Do not retry bulkhead/queue-full rejections only to pile on more load. Never retry side-effecting POSTs without an idempotency key.
- When `Mono.timeout` cancels a subscription, upstream may already have processed the change; cancel **does not roll back** transactions at the provider.
- Per-instance limits are not system-wide limits. For instance, 5 replicas each with an 8-connection pool can open roughly 40 connections to the same provider (depending on remote host and protocol).
- For critical token introspection/PDP calls, never attempt “fail open” merely to preserve availability.
- Never log Bearer/refresh tokens, cookies, client secrets, raw principal claims, or sensitive data. Use trace/correlation IDs and finite downstream names.

## 8. Observing and Tuning Limits with Metrics

Once Reactor Netty metrics, Actuator, and a Micrometer registry are enabled, measure:

| Metric/Observation Group | Meaning |
| --- | --- |
| `reactor.netty.connection.provider.active.connections` | Whether active sockets stay near pool max for long periods |
| `reactor.netty.connection.provider.idle.connections` | Sockets available for reuse |
| `reactor.netty.connection.provider.pending.connections` | Whether pending acquisitions grow without draining |
| Pool acquire duration and timeout/rejection count | Whether bottlenecks occur before calling the provider |
| HTTP client response time p50/p95/p99; 4xx/5xx | Slow provider vs. functional errors |
| 503s at boundary; in-flight/cancel counts | Whether fail-fast and permit release work properly |
| Server request latency p95/p99, error ratio | End-user impact |
| Queue depth and active threads on blocking scheduler | Whether tasks wait too long |

Emitted series names depend on Reactor Netty/Micrometer/version/registry and tags. Confirm metrics contain real data; do not assume adding Actuator alone automatically enables a Prometheus endpoint. Tag by `downstream=profile`, outcome, timeout stage, or status class; **never** tag per username/token/URL with IDs because of high cardinality.

How to choose numbers:

1. Measure throughput to each upstream and mean, p95, and p99 latency under normal load and degradation.
2. Apply **Little's Law** as a steady-state estimate: `L ≈ λ × W`. At an average of 40 calls/s and a mean duration of 0.2 seconds, about 8 calls are in flight on average. The formula uses the **mean**—do not blindly substitute p95 to feel safe.
3. Size pools and bulkheads from actual load, burst headroom, and upstream capacity; small pending queues enable fail-fast instead of holding doomed requests.
4. Load test with the provider intentionally slow, dropping connections, returning 5xx, or stalling body reads; observe memory, queues, sockets, latency, throughput, and recovery.
5. Test multiple replicas and confirm total connections/rates stay within provider quotas.

## 9. Real Integration Test Matrix

| Scenario | Expected Behavior | Additional Checks |
| --- | --- | --- |
| Unauthenticated request | 401 | Zero outbound calls |
| Authenticated, fast upstream | 200 | Accurate data, connections reused |
| Upstream slower than deadline | 503 | Permit released, no indefinite wait |
| Cannot connect | 503 | TCP deadline enforced |
| Bulkhead permits exhausted | Fast 503 | Event loop unblocked |
| Connections full, pending slots free | Waits up to acquire timeout | Pending metric rises then falls |
| Pending acquisition full | Fast failure | Queue remains bounded |
| Client cancels | Permit released | No in-flight leak |
| PDP/introspection fails | Access denied | Error/deny clearly attributed |
| Many concurrent requests | Stable memory, bounded tail latency | No retry storm |
| Multiple instances | Total sockets/rate within budget | Check shared quotas |

## 10. Common Mistakes

1. **Configuring only `responseTimeout`:** requests can still wait too long in the connection-acquire queue. Add `pendingAcquireTimeout` and an outer deadline.
2. **Only increasing `maxConnections`:** shifts saturation downstream and opens excessive sockets. Measure provider capacity first.
3. **Unbounded pending queues:** during slowdowns, memory and latency keep climbing. Set a finite `pendingAcquireMaxCount` and add admission control.
4. **Acquiring permits before subscription:** creating an unused Publisher already consumes a slot. Use `Mono.defer`.
5. **Forgetting to release permits on cancel:** leads to self-lockout after repeated timeouts. Use `doFinally` and test cancellation.
6. **Running blocking SDKs on the event loop:** isolate on a bounded scheduler with driver timeouts.
7. **Treating 401/403/503 identically:** masks infrastructure failures or misleads clients.
8. **Failing open when authorization checks fail:** creates critical authorization bypasses; always fail closed.
9. **Ignoring pending metrics:** active connections near the cap do not tell the whole story; measure pending counts, acquire latency, and 503s.
10. **Applying pools/timeouts to the wrong `WebClient`:** introspectors/JWK decoders may use separate clients.
11. **Unbudgeted retries:** amplify load right when a provider degrades, stretching p99.
12. **Assuming cancel stops blocking I/O or rolls back external work:** requires real SDK timeouts and idempotency.

## Official References

- [Reactor Netty — HTTP Client: Connection Pool and Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Reactor Core — Schedulers API (boundedElastic)](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)

When designing an external boundary for a reactive security application, you must simultaneously answer: **how long to wait at most, how many connections to open at most, how many tasks to accept at most, how to reject when full, and which metrics verify it**.