# Measuring Authentication, Authorization, and Identity Provider Call Latency in Spring Security WebFlux

## 1. Why Measure Each Stage Separately?

In a Spring Security application using WebFlux, an HTTP request may pass through reading a Bearer token or session, authenticating identity (authentication), deciding access permissions (authorization), and only then running business logic. Some mechanisms also communicate with an Identity Provider (IdP). Total endpoint latency does not reveal which stage caused a slowdown; looking only at `http.server.requests` makes it very easy to optimize the wrong place.

The goal of this lesson is to scope each measurement accurately, attach metrics/traces to reactive flows, read p50/p95/p99, and distinguish application-induced slowness from IdP slowness while keeping security behavior intact.

| Metric | Reasonable Start and End Points | Explanation |
| --- | --- | --- |
| HTTP end-to-end | Server starts processing request → response completes | Includes security, handler, I/O, serialization; used as an overall baseline. |
| Authentication (`authentication`) | Subscription to authentication step executes → receives `Authentication`, error, or empty completion | Includes credential/token verification and dependencies of the active mechanism. |
| Authorization (`authorization`) | Executing `ReactiveAuthorizationManager.check(...)` → decision, error, or empty completion | Measures the policy on the instrumented endpoint; does not implicitly cover method security. |
| IdP call | Starting token introspection/token exchange/userinfo/JWK fetch → operation completes | May include network, response handling, retries, and timeouts depending on instrumentation placement. |

For a **Resource Server validating JWTs**, signature verification typically runs locally after public keys have been fetched and cached; do not assume every request calls the IdP. With **opaque token introspection**, requests usually trigger a network call to the IdP unless extra caching is configured. **OAuth2 Login/OIDC** involves authorization code exchange, userinfo retrieval, or token refresh: these are different IdP call points occurring during login/refresh flows rather than necessarily on every API request.

## 2. Choosing Measurement Boundaries to Avoid Inaccurate Metrics

High-level processing flow:

```text
Client request
  -> WebFlux/WebFilter chain
  -> authentication: SecurityContext / Bearer token / ReactiveAuthenticationManager
       -> (if applicable) introspection, JWK retrieval, or IdP call
  -> authorization: ReactiveAuthorizationManager
  -> handler + database + external API
  -> HTTP response
```

These intervals can be **nested**: introspection time sits inside authentication time, and both sit inside the request if executed during that request. Therefore, do not add IdP latency to authentication latency and conclude that is total security latency; adding them double-counts.

For Reactor `Mono`/`Flux`, publishers are usually *lazy*. Creating a pipeline with `Mono.just(...)` or calling a pipeline builder method is not necessarily when the real work executes. Start the clock at **subscription**, and record on complete/error/cancel; avoid starting at assembly time. Use `Mono.defer(...)` and `doFinally(...)` to measure success, error, and cancellation paths. Never use `block()` or `Thread.sleep()` on the event loop to “measure accurately”; they break nonblocking behavior and create artificial latency.

Unit convention: Micrometer `Timer` records durations in appropriate base units and converts at the metrics exporter; with Prometheus you typically see `..._seconds` names and histogram buckets in seconds. Always label units clearly on dashboards.

## 3. Starting with Built-In Metrics

With Spring Boot 3.3 / Spring Security 6.x, you can use Spring Boot Actuator, Micrometer, and Prometheus:

```groovy
// build.gradle — project already uses Spring Boot dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

```yaml
# application.yml — observability section; metrics endpoint must be secured in real environments
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

- Inspect `http.server.requests` first to identify routes, statuses, traffic, and overall latency. Group by URI template and avoid raw routes containing IDs.
- For custom `WebClient`s, use the Spring Boot-injected `WebClient.Builder` to receive `http.client.requests` HTTP client observations; `WebClient.create(...)` bypasses Boot's instrumentation configuration. Do not assume every internal HTTP client created by Spring Security uses the application's `WebClient.Builder`.
- To measure specific **security boundaries**, add a dedicated `Timer` to the component handling authentication/authorization/introspection. HTTP client metrics and component timers answer different questions; the same outbound request can contribute to both.

Example of using a Boot-auto-instrumented HTTP client (for application-managed calls):

```java
@Bean
WebClient idpWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://identity.example.org").build();
}
```

Measuring the HTTP client this way covers only requests actually sent via `idpWebClient`. For token introspection managed by Spring Security, instrument `ReactiveOpaqueTokenIntrospector` as in the next example to measure the duration of that operation itself.

## 4. Java Code Measuring Authorization and IdP Introspection Separately

The following example is **a structurally complete Java file**, using Spring Boot 3.3 + Spring Security 6.x and the dependencies above. `ReactiveSecurityLatencyConfig.java` configures protection for `/reports/**` requiring scope `reports.read`, while measuring authorization decision latency and opaque-token introspection latency. The IdP URI and connection credentials are supplied via application configuration at runtime.

```java
package example.security;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorityReactiveAuthorizationManager;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityLatencyConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, MeterRegistry meters) {

        ReactiveAuthorizationManager<AuthorizationContext> rule =
                AuthorityReactiveAuthorizationManager.hasAuthority(
                        "SCOPE_reports.read");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/reports/**")
                        .access((authentication, context) ->
                                measure(
                                        meters,
                                        "authorization",
                                        decision -> decision.isGranted()
                                                ? "granted" : "denied",
                                        () -> rule.check(authentication, context)))
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            MeterRegistry meters,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                new SpringReactiveOpaqueTokenIntrospector(
                        introspectionUri, clientId, clientSecret);

        return token -> measure(
                meters,
                "idp_introspection",
                principal -> "valid",
                () -> delegate.introspect(token));
    }

    // Use only when the returned manager has been wired into the real authentication flow.
    static ReactiveAuthenticationManager timedAuthenticationManager(
            ReactiveAuthenticationManager delegate, MeterRegistry meters) {
        return authentication -> measure(
                meters,
                "authentication",
                result -> "authenticated",
                () -> delegate.authenticate(authentication));
    }

    private static <T> Mono<T> measure(
            MeterRegistry meters,
            String stage,
            Function<? super T, String> classifyValue,
            Supplier<Mono<T>> operation) {

        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(meters);
            AtomicReference<String> outcome =
                    new AtomicReference<>("empty");

            return Mono.defer(operation)
                    .doOnNext(value ->
                            outcome.set(classifyValue.apply(value)))
                    .doOnError(error -> outcome.set("error"))
                    .doFinally(signal -> {
                        String finalOutcome = signal == SignalType.CANCEL
                                ? "cancel" : outcome.get();

                        sample.stop(Timer.builder("security.stage.duration")
                                .description("Reactive security stage latency")
                                .tag("stage", stage)
                                .tag("outcome", finalOutcome)
                                .publishPercentileHistogram()
                                .register(meters));
                    });
        });
    }
}
```

Key explanations:

1. `Mono.defer(...)` starts `Timer.Sample` at subscription. Each subscription gets its own sample and `AtomicReference`; concurrent requests share no measurement state.
2. `doOnNext` classifies results: `authorization` is `granted`/`denied`; successful introspection is `valid`; successful authentication is `authenticated`. `doOnError` records errors, and `doFinally` includes `cancel`. `empty` means the publisher emitted no value; with `ReactiveAuthenticationManager`, this may mean “unsupported Authentication type” and must **not** be converted into a password error.
3. `delegate` executes the original policy or introspection. Wrapping with a timer must never alter decisions or swallow exceptions. Never put tokens, usernames, `sub`, URLs with sensitive queries, or exception messages into metric tags.
4. `opaqueTokenIntrospector` is the bean Resource Server uses for the opaque token flow. Therefore `idp_introspection` measures the real operation; it is typically part of authentication. The `timedAuthenticationManager` method shows how to wrap a manager **when the application explicitly wires that manager into the authentication filter/flow**; merely declaring an unused method or bean produces no authentication metrics. The runnable example directly wires authorization and introspection measurement.
5. `publishPercentileHistogram()` creates buckets for Prometheus percentile calculation; histograms have memory and time-series costs. With a few fixed `stage`/`outcome` values as above, cost is bounded, but evaluate resources before broad rollout.

To configure introspection for the Java snippet, set `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri`, `client-id`, and `client-secret` (provide secrets via a secret manager/environment variables). Spring uses these properties when creating `ReactiveOpaqueTokenIntrospector`; with the custom bean in the example, the values are constructor/method-injected. The URI must point to a valid IdP introspection endpoint; without a real IdP, the application cannot validate real opaque tokens.

**Observability limitations:** the class above does not measure every authentication mechanism. For JWT, instrument `ReactiveJwtDecoder.decode(...)` or the manager of the corresponding JWT pipeline; for OAuth2 Login, measure the actual token-response client, userinfo client, or token refresh step. When instrumenting `@PreAuthorize`/method security, use a separate boundary to separate it from HTTP authorization. Each instrument must be placed where the component is actually invoked.

## 5. Distinguishing IdP Call Time from Authentication Time

An IdP exposes different endpoints with distinct characteristics:

| Processing Flow | Potential Calls | Where to Measure | Interpretation |
| --- | --- | --- | --- |
| API + opaque Bearer token | Introspection endpoint | `ReactiveOpaqueTokenIntrospector.introspect` | Network token validation latency; network failures differ from rejected tokens. |
| API + JWT | JWKS fetch/refresh on cold cache, miss, or expiration | Decoder and key-fetching client | Most requests verify offline; separate “cache warm” from “cache miss”. |
| OAuth2 Login/OIDC | Authorization-code exchange, userinfo | Actual reactive OAuth2 token client / OIDC user service | Occurs mainly on login callbacks; do not compare directly with normal API requests. |
| Refresh token | Token endpoint | Reactive authorized-client provider/token-response client | Distinguish refresh from subsequent request authentication. |

If you need exact network timing to the IdP, instrument the actual client in use and define where measurement starts/ends (e.g., receiving response headers vs. finishing body consumption). The `introspect` measurement above covers **the entire introspection operation**, including response processing. If retries are configured, measured duration may include multiple attempts and backoff; add counters for attempts/timeouts to pinpoint causes.

With Reactor Netty/WebClient, also inspect the connection pool, DNS/TLS/connect latency, and timeouts. High IdP p95 can stem from pool connection waiting, network issues, rate limiting, retries, or the IdP itself. Do not conclude “the IdP is slow” from a single aggregate timer without checking these segments.

## 6. Viewing Metrics and Computing p95 Properly

After sending representative traffic, inspect `/actuator/prometheus` in an authorized environment. Metric names from the code above typically appear as `security_stage_duration_seconds_count`, `..._sum`, and `..._bucket` with the Prometheus registry; each series has `stage` and `outcome` labels. Example:

```promql
# Introspection call rate, in calls/second
sum(rate(security_stage_duration_seconds_count{
  stage="idp_introspection"
}[5m]))

# Average introspection duration, in seconds
sum(rate(security_stage_duration_seconds_sum{
  stage="idp_introspection"
}[5m]))
/
sum(rate(security_stage_duration_seconds_count{
  stage="idp_introspection"
}[5m]))

# p95 authorization latency, computed from histogram buckets
histogram_quantile(
  0.95,
  sum by (le) (
    rate(security_stage_duration_seconds_bucket{
      stage="authorization"
    }[5m])
  )
)
```

The illustrative PromQL here aggregates all `outcome`s; real dashboards should compare `granted`/`denied` and `error` separately when needed. Histogram percentiles depend on observation windows and buckets and are approximations; p99 over very few samples fluctuates heavily. Avoid averaging per-instance p95 values to get a “cluster-wide p95”; sum buckets by `le` first and then compute `histogram_quantile`.

Minimum recommended metrics: request rate, error/deny rate, p50/p95/p99 by stage, IdP latency, timeout/retry counts, total HTTP latency, in-flight requests, and signs of event-loop/connection-pool saturation. Create only finite dimensions such as `stage`, `outcome`, and `provider` from approved provider names; never create per-user/per-token series.

## 7. Distributed Tracing to Find Slow Requests

Metrics answer “where is the system slow, and at what rate”; tracing answers “which segment made a specific request slow”. With Micrometer Observation and OpenTelemetry/Zipkin/OTLP configured, use traces/spans to stitch together the inbound application path and outbound calls. A useful trace might look like:

```text
http.server GET /reports/{id}           260 ms
  authn/opaque-introspection            185 ms
    outbound POST /oauth2/introspect    179 ms
  authz/check-scope                       2 ms
  handler + downstream                   65 ms
```

**Numbers above are illustrative only**, not output from the Java code above. Execution paths can nest, have gaps, or run in parallel. Do not sum child span durations with parent spans; analyze the critical path and exclusive time when attributing root causes.

In reactive pipelines, trace context propagates via Reactor Context when instrumentation is properly configured. Do not rely on manual `ThreadLocal`/MDC across `publishOn` or `flatMap`; threads can change. Never place Bearer tokens, raw credentials, or personal data in span names or attributes.

## 8. Designing Measurement Test Scenarios

Drive the same route with controlled traffic while simultaneously observing HTTP, security metrics, and traces. Cases to distinguish:

1. **Valid token, sufficient scope:** introspection succeeds; authorization `granted`; handler responds successfully (if the handler behaves properly). Verify each execution produces the right sample count.
2. **Valid token, missing scope:** introspection may succeed; authorization `denied`; endpoint typically returns `403`. Do not mark normal deny decisions as “error”.
3. **Invalid/expired token:** introspection may fail with an authentication error, client typically receives `401`; authorization may not be evaluated because the pipeline stopped before authorization. Distinguish token errors from IdP outages.
4. **Slow, timing-out, or 5xx IdP:** `idp_introspection` shows higher latency or `error`; requests may fail depending on handling policy. Measure timeouts, retries, and the connection pool; never disable security checks to hit latency targets.
5. **Client-cancelled request:** `doFinally(CANCEL)` must record `cancel`. When Reactor `retry`, `timeout`, or `cache` is used, measurement placement determines which waiting times are included.
6. **JWT cold/warm cache (if using JWT):** test initial JWK fetch, cache hit, and refresh/rotation; do not treat every JWT verification as an HTTP call to the IdP.

For load tests, hold constant the valid/invalid token ratio, JWT size, cache hit rate, concurrency level, and connection pool settings when comparing before/after. Warm up the JVM, Reactor Netty, and JWK cache before drawing steady-state conclusions. Test error paths and verify sample counts so you do not capture only successful requests.

## 9. Interpreting and Resolving Bottlenecks

| Symptom | Hypothesis to Verify | Resolution Direction |
| --- | --- | --- |
| High HTTP p95, low authn/authz/IdP | Handler, DB, downstream, serialization | Inspect traces, connections, and thread scheduling. |
| High Authentication p95, high IdP introspection too | Network/IdP wait, timeouts, retries, pool | Check outbound p95, connect/TLS, and service limits; evaluate token strategy against revocation needs. |
| High Authorization p95 | Heavy policy computation, DB/API calls in rules | Measure each lookup, optimize I/O reactively, review caching/data permissions. |
| JWT latency spikes only during JWK rotation | Cache miss, JWKS download, or key rotation | Check cache, network config, timeouts, and rotation procedures. |
| Only p99 spikes at high concurrency | Queueing, pool exhaustion, event-loop blocking, GC | Check event-loop, BlockHound where appropriate, connection pool, and CPU/GC profiles. |

Never put blocking calls such as blocking JDBC, synchronous `RestTemplate`, `Thread.sleep`, or `block()` onto the event loop. If a blocking library is unavoidable, isolate it appropriately (for example `Schedulers.boundedElastic()`), measure waiting overhead separately, and plan migration to nonblocking APIs. Caching authentication/authorization results requires proper TTL, revocation, user-scope, and consistency policies; latency optimization must never weaken access control.

## 10. Common Measurement Mistakes

- **Starting the timer when constructing `Mono`:** captures pre-subscription time or misses retries; measure inside `defer` and understand operator placement before/after `retry`.
- **Measuring only `doOnSuccess`:** misses errors and cancellations; `Mono.doOnSuccess` is also invoked with `null` on empty completion. Use `doFinally` and classify outcomes explicitly.
- **Confusing `401`, `403`, and IdP outages:** 401 usually relates to missing/invalid authentication, 403 is authenticated but unauthorized; IdP infrastructure failures map differently. Do not lump them into a single “authentication failed” metric.
- **Attaching timers to managers unused by the framework:** produces zero samples or misses all requests; verify the real wiring path for JWT, opaque tokens, and OAuth2 login.
- **Using raw URLs, user IDs, tokens, or dynamic scopes as tags:** causes cardinality explosions and data leak risks. Bound labels, redact secrets, and never log Authorization headers.
- **Summing nested timers:** double-counts introspection time. Use traces to view parent–child relationships instead of summing arbitrarily.
- **Interpreting a single sample as an SLO:** percentiles need appropriate windows, sample volumes, and traffic segmentation; also measure throughput, error rate, and concurrency.
- **Exposing observability endpoints publicly:** metrics/traces can leak route names/infrastructure details. Restrict access, retention, sampling, and storage costs.

## 11. Completion Criteria

A measurement setup meets requirements when: each stage has clear boundaries and units; timers start at subscription and stop on success/error/cancel; labels are safe and bounded; aggregate HTTP metrics exist for cross-checking; offline JWT verification is distinguished from introspection and OAuth2 login steps; tests cover grant/deny/invalid token/IdP timeout; and p95 dashboards have sufficient traffic without double-counting spans/timers.

**Official docs for API verification:** [Spring Security — WebFlux authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html), [Spring Security — reactive OAuth2 resource server](https://docs.spring.io/spring-security/reference/reactive/oauth2/), [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html).