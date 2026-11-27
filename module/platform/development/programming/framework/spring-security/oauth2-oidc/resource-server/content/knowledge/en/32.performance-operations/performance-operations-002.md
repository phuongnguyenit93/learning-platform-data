# Latency, Throughput, and Authentication Processing Time in a Request

## 1. Why Measure Authentication Time Separately?

A request to an API protected by a Spring Security Resource Server passes through many steps: accepting the connection, HTTP processing, running security filters or web filters, reading the access token, verifying the token, creating Authentication, checking permissions, running the controller, and accessing data. When an API is slow, you cannot assume the cause is JWT or Spring Security by default.

User-perceived response time is the total time of the entire path. Authentication time is only one part of that path, yet it can become the bottleneck when every request must introspect a token from the Authorization Server, fetch JWKS keys, query permissions from a database, or wait on a remote service.

Three concepts must be distinguished:

- **Latency:** the elapsed time from when a request begins until the measured outcome is produced. It can be measured for the entire request or for a specific authentication step.
- **Throughput:** the number of requests processed per unit of time, usually expressed as requests per second (RPS).
- **Authentication processing time:** the duration from when the security component begins verifying credentials until Authentication is successfully created or fails.

Latency and throughput are related, but not synonymous. A system might handle 2,000 RPS when requests are lightweight, yet reach only 400 RPS when each request must call an introspection endpoint. A single request may have low latency while the system is idle, then spike sharply when connection pools, CPU, or downstream services saturate.

In the Performance and Operations chapter, the goal is to measure the right segment of the path, understand what drives cost, find the saturation point, and optimize without weakening security policy.

### Learning Objectives

After this lesson, you will be able to:

1. Describe the path of a request through a Spring Security Resource Server.
2. Distinguish end-to-end request latency from authentication latency.
3. Compare the processing costs of JWTs and opaque tokens.
4. Understand the impact of JWK caching, introspection, authority mapping, and permission queries.
5. Measure p50, p95, p99, throughput, error rate, and saturation.
6. Design load tests with warm-up, ramp-up, steady state, and soak phases.
7. Detect blocking calls in WebFlux and bottlenecks in Servlet stacks.
8. Properly tune caches, connection pools, concurrency, and timeouts.
9. Monitor performance without leaking tokens or sensitive data into metrics or logs.
10. Evaluate trade-offs between performance, token state freshness, and revocation capability.

---

## 2. What Steps Does a Request Pass Through?

### 2.1. High-Level Request Path

With a JWT access token, a request typically traverses these steps:

~~~mermaid
flowchart TD
    A[HTTP request arrives at API] --> B[Servlet Filter Chain or WebFilter Chain]
    B --> C[Extract Authorization header]
    C --> D[Authentication Manager]
    D --> E[ReactiveJwtDecoder or JwtDecoder]
    E --> F[Parse JWT and verify signature]
    F --> G[Validate issuer, audience, timestamps, claims]
    G --> H[Authentication Converter]
    H --> I[SecurityContext]
    I --> J[Authorization rules]
    J --> K[Controller and business logic]
    K --> L[Repository or downstream service]
    L --> M[HTTP response]
~~~

With an opaque token, the decoder is typically replaced by an introspector:

~~~mermaid
sequenceDiagram
    participant Client
    participant RS as Resource Server
    participant AS as Authorization Server
    participant API as Application

    Client->>RS: Request + Bearer token
    RS->>RS: Read token and start authentication
    RS->>AS: Introspection request
    AS-->>RS: active, subject, scope, claims
    RS->>RS: Build Authentication
    RS->>RS: Check authorization
    RS->>API: Run controller
    API-->>Client: Response
~~~

These diagrams show logical steps only. Some steps are combined inside a filter, provider, or manager; exact ordering and components vary by Servlet/WebFlux and JWT/opaque token configuration.

### 2.2. Intervals That Should Be Separated

To pinpoint bottlenecks, separate at least the following intervals:

| Measured Interval | Start | End | Meaning |
|---|---|---|---|
| HTTP server duration | Server receives request | Server writes response | Server-side experience |
| Security chain duration | Security filter/web filter starts | Security chain finishes | Cost of the security pipeline |
| Authentication duration | Authentication starts | Authentication produced or fails | Token verification time |
| JWT decode duration | Decoder invoked | Decoder emits Jwt or error | Parse, signature, validators, and key lookup on cache miss |
| Introspection duration | Introspection request sent | Response received/read | Network and AS cost |
| Converter duration | Jwt/principal received | Authentication created | Subject, scope, and authority mapping |
| Authorization duration | Permission check starts | Decision reached | Scope, role, policy, or tenant lookup |
| Application duration | Enters controller/service | Business processing completes | Business logic and data access |

Do not sum all measurements if they are nested. For example, HTTP server duration already contains security, controller, and repository time. Adding HTTP duration to security duration counts security twice.

### 2.3. Request Latency Is Not a Simple Sum of Every Timer

A sequential request can be approximated as:

\[
T_{request} = T_{network-in} + T_{security} + T_{application} + T_{network-out}
\]

Where:

\[
T_{security} = T_{extract} + T_{authenticate} + T_{authorize}
\]

And for JWT:

\[
T_{authenticate} \approx T_{decode} + T_{validate} + T_{convert}
\]

For opaque tokens:

\[
T_{authenticate} \approx T_{introspection} + T_{convert}
\]

This is a conceptual decomposition model, not an exact additive formula in every system. Some tasks may run in parallel, some timers include scheduler or connection pool wait times, and some instrumentation overlaps the same interval.

---

## 3. Factors That Determine Authentication Time

### 3.1. Parsing and Verifying JWTs

A JWT typically consists of three Base64URL parts: JOSE header, payload, and signature. The Resource Server must parse the token, verify the algorithm, verify the signature, and run validators.

Signature verification cost depends on:

- Signing algorithm, such as RSA or ECDSA.
- Key size and cryptographic provider implementation.
- CPU architecture and CPU load.
- Token size and number of claims.
- Number of validators and additional mapping logic.
- Caching of keys fetched from the JWKS endpoint.

Do not conclude that ECDSA is always faster than RSA or vice versa. Benchmark the exact algorithm, key size, JDK, crypto provider, and hardware of your deployment environment.

JWT parsing and claims validation are typically in-process operations. With a standard JWT Resource Server configuration, the server does not need to call the Authorization Server per token solely to verify signatures. However, when a new signing key must be fetched, a network request to the JWKS endpoint may occur.

### 3.2. JWK Set and Key Caching

The Resource Server obtains public keys from a JWK Set URI or issuer discovery metadata. Once keys are fetched and cached, subsequent requests can verify signatures locally.

Typical path:

~~~text
First request or cache miss
  -> Decoder needs key by kid
  -> JWK source searches cache for key
  -> If no matching key is present, fetch JWK Set
  -> Select key and verify signature
  -> Cache key/JWK per policy

Subsequent requests with cached key
  -> Retrieve key from cache
  -> Verify signature locally
~~~

This creates a distinction between the **cold path** and the **warm path**:

- Cold path may include DNS, TLS handshake, HTTP connection setup, JWKS download, and JWK parsing.
- Warm path usually only requires cache lookup and signature verification.
- When the Authorization Server rotates keys, the Resource Server may need to refresh the JWK Set to find the new key.
- When the cache expires or is evicted, a request may trigger a fetch again.

Never benchmark with only the first request and treat it as steady-state latency. Conversely, do not measure only the warm path if production frequently starts multiple new instances simultaneously or the AS rotates keys often.

### 3.3. Issuer Discovery and JWKS Retrieval

If configured with an issuer URI, the framework may need to fetch Authorization Server metadata to locate the JWKS endpoint. Decoder configuration and lifecycle determine whether metadata is fetched at startup or on demand.

To minimize traffic impact:

- Initialize the decoder and verify metadata during startup/warm-up if architecture permits.
- Use a stable JWKS endpoint capable of handling load.
- Configure reasonable timeouts for metadata/JWKS connections.
- Keep old signing keys during an appropriate overlap window during rotation.
- Monitor key fetch errors, cache misses, and JWKS download latency.
- Avoid creating a new decoder per request; the decoder should be a shared bean.

Do not cache keys indefinitely on your own. Key rotation is part of the trust lifecycle. Caching for too long can delay picking up new keys or continue trusting keys retired by policy.

### 3.4. Opaque Token Introspection

With opaque tokens, the Resource Server typically sends the token to the introspection endpoint to check whether it is active and retrieve subject, scope, and attributes.

Key performance differences:

- JWTs can be verified locally once keys are available.
- Opaque tokens generally require a network round trip to the AS for each introspection, unless the application caches results or uses another optimization.
- Introspection duration depends on network, TLS, connection pool, AS capacity, the AS database/token store, and response payload.
- When the AS slows down, authentication latency and queued requests rise accordingly.

An introspection call might take a few milliseconds on an internal network or much longer under load, so never rely on a fixed number to predict production behavior. Measure on your actual topology and load.

### 3.5. Authority Mapping and Authentication Conversion

After verifying the token, the Resource Server still needs to build an Authentication:

- Read the subject/principal name.
- Map scopes to authorities, such as SCOPE_orders.read.
- Map roles/groups claims if the application enforces that policy.
- Normalize custom claims.
- Construct the principal or authentication object.
- Optionally query a role directory or entitlement service if required by design.

In-memory claim mapping is generally much cheaper than a network call. If a converter queries a database or HTTP endpoint on every request, that cost can exceed JWT signature verification itself.

If dynamic permissions are required, explicitly decide whether permission data is fetched at authentication time, authorization time, or from a cache. Loading a user's full permission set on every request can add unnecessary latency and downstream load.

### 3.6. Authorization After Authentication

Authentication answers "who is this token/principal and is it valid?". Authorization answers "is this principal allowed to perform this action on this resource?".

A request may authenticate quickly yet stall while checking:

- Roles or groups from a database.
- Tenant membership.
- Object ownership.
- Policy engine evaluation.
- Permission service calls.
- Method security or ACLs.
- Data queries needed for authorization checks.

When a dashboard reports only a single "security duration" metric, separate authentication from authorization so you do not optimize the wrong stage.

---

## 4. Comparing JWT and Opaque Tokens from a Performance Perspective

| Criterion | JWT access token | Opaque access token |
|---|---|---|
| Per-request verification | Usually local once keys are cached | Usually calls introspection endpoint |
| Network dependency on hot path | Usually none | Usually present |
| Primary costs | Parse, signature verify, validators, mapping | Network, AS processing, response parsing, mapping |
| Resource Server scaling | Scales with CPU and request rate | Also depends on AS capacity and connection pool |
| Immediate token revocation | Difficult with local JWT verification alone | AS can return inactive on the next introspection |
| Caching | JWKS/key cache; optional policy-bounded result cache | Introspection result cache with bounded TTL |
| During transient AS failure | Tokens with cached keys can still be verified | New introspections typically fail |
| Request size | Token is usually larger | Token is usually shorter |
| Token state freshness | Depends on expiry and supplemental mechanisms | Depends on each introspection or cache TTL |

JWT is not automatically faster in every system. If the JWT is huge, signature verification is heavy, the converter queries a database, or the decoder keeps fetching JWKS, the advantage shrinks. Opaque tokens can achieve good latency if the AS is nearby, connection pooling is solid, and caching matches policy.

Choosing a token format requires balancing:

- How urgently early token revocation is needed.
- Number of Resource Servers.
- Authorization Server capacity.
- Latency between RS and AS.
- Audit and token state requirements.
- Operational maturity for key rotation.
- Cache policy and maximum acceptable staleness window.

Do not switch from opaque tokens to JWT based on a single isolated benchmark. Measure the hot path, cold path, key rotation, AS outage behavior, and revocation requirements.

---

## 5. Where Can Caching Improve Performance?

### 5.1. JWK and Metadata Caching

JWK caching reduces how often the Resource Server must call the JWKS endpoint. Consider:

- Cache lifetime and refresh policy.
- Behavior when encountering an unknown kid.
- Refresh synchronization across multiple instances.
- Overlap between old and new keys during rotation.
- Timeouts/retries when the JWKS endpoint is unavailable.

When many instances start simultaneously or encounter an unknown kid together, concurrent JWKS fetches can occur. Where needed, use startup warm-up, appropriate caching, and concurrency limits at the key-retrieval layer.

### 5.2. Introspection Result Caching

An introspection cache can cut round trips to the AS. However, caching reduces token state freshness.

For example, if a token is revoked right after the cache stores active=true:

~~~text
t0: RS introspects -> active=true, cache TTL 30s
t1: AS revokes token
t2: RS reads cache -> still sees active=true
t3: cache expires
t4: RS introspects again -> active=false
~~~

In this example, the maximum staleness window is close to the remaining cache TTL, plus propagation delays and implementation details.

Choose TTLs according to security requirements:

- Low-privilege, short-lived access tokens can tolerate longer cache TTLs.
- Administrative tokens or sensitive transactions require higher freshness.
- If near-instant revocation is required, active=true caching must be very short or backed by active invalidation.
- Never cache error/timeout responses as active tokens.
- Never use cache keys containing raw tokens in logs or metrics.

### 5.3. Authority and Tenant Data Caching

Authority mapping may come from token claims or a permission service. When caching permission results:

- Define keys with subject, tenant, resource/action, and the required data version.
- Align TTL with permission update timelines.
- Explicitly design invalidation when roles or tenant memberships change.
- Never serve one user's cached permissions to another user.
- Never let a cache hit skip per-record resource ownership checks.

A scope claim in an access token is usually a permission snapshot from issuance time. If the application needs near real-time permission updates, a mechanism beyond the scope snapshot is needed, and its cost must be measured.

### 5.4. Caching Is Not a Silver Bullet for Every Bottleneck

Caching reduces network calls, but also introduces:

- Memory footprint.
- Serialization/deserialization overhead.
- Eviction and contention.
- Invalidation complexity.
- Stale authorization.
- Cache stampedes.
- Blind spots when hits/misses are unmeasured.

Measure cache hit ratio, hit/miss latency, evictions, cache size, and staleness windows. If the hit ratio is low or data changes constantly, caching may help little.

---

## 6. Connection Pools, Timeouts, and Concurrency

### 6.1. Introspection WebClient

With opaque tokens, the Resource Server needs an HTTP client with a properly sized connection pool. If the pool is too small, requests wait for connections even when the AS responds fast. If the pool is too large, the system may open too many connections and overload the AS.

Monitor:

- Active connections.
- Idle connections.
- Pending acquire count and connection wait time.
- Connect timeout.
- Response timeout.
- TLS handshake frequency.
- Request failures due to pool exhaustion.
- Connection reuse and keep-alive.

Never create a new WebClient per request. Use a shared client with explicit pool and timeout configuration.

### 6.2. Timeouts Must Reflect the Request Budget

Suppose an API has a p95 target of 300 ms. If the introspection timeout is set to 5 seconds, some requests can hold resources long after they have blown past the latency budget.

Timeouts should be layered:

- Connection acquisition timeout.
- Connect timeout.
- TLS handshake timeout if the client supports configuring it separately.
- Response/read timeout.
- Overall request deadline.
- Timeouts for permission services or databases.

A lower-layer timeout should not exceed the total deadline the caller is still willing to wait for. Conversely, overly aggressive timeouts trigger false failures during bursts or network jitter.

### 6.3. Concurrency and Backpressure in WebFlux

WebFlux uses a reactive pipeline to avoid tying up a thread per request waiting on I/O. That does not give downstream services infinite capacity.

If 5,000 requests simultaneously call an introspection endpoint, the Resource Server still places corresponding load on the connection pool and AS. Bound concurrency or use bulkheads at dependency boundaries to protect the system.

Never call blocking JDBC, a blocking Redis client, or RestTemplate directly on the event loop. A blocking call can stall an event-loop thread from serving other requests, degrading latency across the application.

If calling a blocking API is unavoidable, offloading it to an appropriate scheduler is a transitional workaround; long term, use a reactive client/driver instead. Schedulers also have finite thread and queue limits, not infinite capacity for blocking work.

### 6.4. Concurrency and Thread Pools in Servlet Stacks

Servlet stacks typically use request threads. While a request waits on introspection or a database, its thread remains occupied. If a downstream slows down:

- Active request threads climb.
- Request queues grow.
- The thread pool exhausts.
- New requests wait longer or are rejected.
- Tail latency spikes rapidly.

Monitor active threads, queue length, rejected tasks, request concurrency, and downstream wait times. Never raise max threads unboundedly; more threads increase context switching and can overwhelm downstream services.

---

## 7. Measuring Latency Properly

### 7.1. Do Not Look Only at Averages

An average can hide a very slow tail of requests. For example, if 99 requests take 20 ms and 1 request takes 2 seconds, the average is 39.8 ms, yet one user still waited 2 seconds.

Track percentiles:

- **p50:** half of requests are faster than or equal to this value.
- **p90:** 90% of requests are faster than or equal to this value.
- **p95:** 95% of requests are faster than or equal to this value.
- **p99:** 99% of requests are faster than or equal to this value.
- **max:** the slowest request in the measurement window; sensitive to outliers and sample size.

p95/p99 are essential for observing tail latency. However, percentiles require enough samples and an appropriate time window; p99 over a few dozen requests is statistically noisy.

### 7.2. Throughput and Error Rate

Monitor at least:

- Requests per second.
- Successful requests per second.
- 401 and 403 rates.
- 5xx rate.
- Timeout rate.
- Authentication failures by reason category.
- Introspection/JWKS dependency error rate.
- CPU, memory, GC, and connection pool saturation.

A system achieving high RPS by returning 401 or 503 to most requests does not deliver high useful throughput. Always read throughput alongside success and error rates.

### 7.3. Histograms and Metric Cardinality

Use histograms when computing percentiles from latency distributions. Metric labels must have bounded cardinality.

Suitable labels typically include:

- operation: jwt_decode, opaque_introspection, authentication, authorization.
- outcome: success, invalid, error, timeout, cancelled.
- token_type: jwt or opaque if this dimension is controlled.
- Normalized application/route group, not raw paths containing IDs.

Never use the following values as metric labels:

- Access token or refresh token.
- Subject/user ID.
- Email.
- Session ID.
- Request ID.
- Raw URLs with path variables.
- Arbitrary exception messages.

High cardinality can exhaust metrics backend memory and CPU. Identifying data needed for traces or logs must follow privacy policy and never include secret tokens.

### 7.4. Avoid Logging Tokens

Never log the Authorization header, compact JWTs, introspection request bodies, client secrets, or DPoP proofs. When correlating errors, use a trace ID or a safely designed identifier, never raw credentials.

Exception logs also warrant scrutiny because some HTTP clients include request details in error messages. Scrub credentials before logging.

---

## 8. Instrumentation with Micrometer

### 8.1. Timing a Reactive Component

Example wrapper timing `ReactiveJwtDecoder`. The timer starts when the Publisher is subscribed to and stops on the terminal signal:

~~~java
public final class TimedReactiveJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final MeterRegistry registry;

    public TimedReactiveJwtDecoder(
            ReactiveJwtDecoder delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return delegate.decode(token)
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "complete";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancelled";
                        default -> "other";
                    };

                    sample.stop(
                        registry.timer(
                            "security.jwt.decode",
                            "outcome", outcome
                        )
                    );
                });
        });
    }
}
~~~

This snippet uses a Java switch expression; if the project targets an older Java version, replace it with a standard switch statement. The metric attaches only an outcome label with a finite set of values. Never add tokens or subjects as tags.

The wrapper must be registered as the decoder the Resource Server actually uses. Timing a bean outside the security chain will not reflect production requests.

### 8.2. Timing the Introspector

The same pattern applies to `ReactiveOpaqueTokenIntrospector`:

~~~java
public final class TimedOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final MeterRegistry registry;

    public TimedOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return delegate.introspect(token)
                .doFinally(signal -> {
                    String outcome = signal == SignalType.ON_ERROR
                        ? "error"
                        : signal == SignalType.CANCEL
                            ? "cancelled"
                            : "complete";

                    sample.stop(registry.timer(
                        "security.opaque.introspection",
                        "outcome", outcome
                    ));
                });
        });
    }
}
~~~

In production, distinguish inactive tokens from AS/network errors by classifying exceptions safely. Never put exception messages into metric tags. If recording extra metrics for timeouts, classify using exception type or a stable error code.

### 8.3. Timing Converters and Authorization

Converters can be wrapped similarly, but avoid instrumenting tiny operations whose overhead outweighs the insight gained. Start with meaningful boundaries:

- JWT decode.
- Opaque introspection.
- Authority lookup.
- Tenant/permission check.
- Total authentication.
- Total authorization.
- Total HTTP request.

If a single request performs multiple authorization checks, metric names and units must clearly distinguish "per check" from "per request".

### 8.4. Measuring with Observation

Spring/Micrometer Observation records an operation with both timers and tracing handlers. When a project already uses Observation conventions, prefer following the shared convention over creating a separate metric system for the same operation.

A useful observation can carry operation name and outcome. Never add sensitive data or unbounded labels to low-cardinality key values. Use high-cardinality tracing data only when backend capacity and privacy policy allow, and never place access tokens in trace baggage.

---

## 9. Diagnosing Bottlenecks from Operational Signals

| Signal | Possible Cause | How to Confirm |
|---|---|---|
| p95 JWT decode rises with CPU | CPU-heavy signature verification, parsing, or validators | CPU profile, benchmark decoder |
| p99 spikes on unknown kid | JWKS fetch, retries, or key rotation | Measure JWKS cache misses and fetch latency |
| Slow opaque introspection with low RS CPU | AS, network, or pool wait | Measure outbound HTTP timing and pool pending count |
| Latency rises above an RPS threshold | CPU, thread, pool, or AS saturation | Ramp load test and monitor queues |
| App-wide WebFlux latency rises with busy event loop | Blocking call on event loop | BlockHound, thread dumps, profiler |
| Servlet active threads near max | Requests waiting on downstream | Thread pool metrics and dependency latency |
| Fast authentication but slow request overall | Authorization, business logic, or data access | Split timers per stage |
| 401s rise during key rotation | JWKS propagation/cache or key overlap | Check kid and JWKS responses |
| High cache hit rate but stale authorization | Misconfigured TTL or invalidation | Compare revocation/change time with cache expiry |
| High p99 while introspection pool pending grows | Undersized connection pool or slow AS | Pool acquire time, active connections |
| Low CPU but high latency | I/O wait, queueing, or lock contention | Distributed traces and queue metrics |
| Error rate rises when timeouts are tightened | Timeout budget does not match downstream | Compare downstream latency distribution |

A good dashboard lets you compare over the same time window: request latency, authentication latency, downstream dependency latency, RPS, error rate, and saturation.

---

## 10. Designing Load Tests for a Resource Server

### 10.1. Test Objectives

Load testing is not just about finding peak RPS. It should answer:

- What are p95/p99 at expected traffic levels?
- When does throughput stop scaling even as concurrency increases?
- Does CPU or a downstream dependency saturate first?
- How do 401/403/5xx rates behave?
- Do cold starts and JWKS refreshes create latency spikes?
- How much AS load does introspection caching save, and how large is the staleness window?
- How does the system behave during a long soak test?
- When the AS or JWKS endpoint fails, does the Resource Server enforce policy properly?

### 10.2. Test Phases

A test plan should include:

1. **Warm-up:** warm up JVM/JIT, connection pools, DNS/TLS, and the JWK cache.
2. **Ramp-up:** gradually increase traffic to observe the onset of saturation.
3. **Steady state:** hold stable load long enough to capture reliable percentiles.
4. **Burst:** brief traffic spikes to verify queueing and autoscaling.
5. **Soak:** sustained load to detect memory leaks, unbounded cache growth, pool leaks, and GC pressure.
6. **Recovery:** drop load and observe how quickly the system returns to normal.

### 10.3. Separate Workloads

Do not mix all request types into one bucket and infer token performance:

| Workload | What to Measure |
|---|---|
| JWT warm key, valid token | Hot-path cost |
| JWT cold key/JWKS miss | Key fetch and refresh cost |
| JWT invalid signature/claims | Failure-path cost |
| Opaque introspection active | Network and AS capacity |
| Opaque introspection inactive | Failure path |
| Cache hit/miss | Cache benefit and overhead |
| Tokens with few vs. many claims | Parsing and mapping |
| Local vs. remote authority lookup | Converter/policy cost |
| Missing scope | Authorization failure |
| Heavy business requests | Separate security cost from application cost |

Use pre-generated valid and invalid token fixtures. Avoid generating key pairs or signing tokens inside the load-test script itself when measuring the Resource Server; doing so makes the load generator the bottleneck and skews server measurements.

### 10.4. k6 Example for the JWT Hot Path

Simple example sending a pre-signed test access token:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL;
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN;

export const options = {
  scenarios: {
    resource_server: {
      executor: 'constant-arrival-rate',
      rate: 500,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<700'],
  },
};

export default function () {
  const response = http.get(BASE_URL + '/api/orders/42', {
    headers: {
      Authorization: 'Bearer ' + ACCESS_TOKEN,
    },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
~~~

This is a workload template, not a universal performance threshold. Scenario settings must match your target RPS and load generator capacity. With constant-arrival-rate, k6 tries to maintain the iteration start rate; monitor dropped iterations and active VU counts.

Never pass production tokens through shell history, CI logs, or source repositories. Use secret injection for test environments and least-privilege tokens.

### 10.5. Test Opaque Introspection Separately

An opaque token scenario should send valid test tokens to a Resource Server endpoint backed by a real or stub introspector. Measure concurrently:

- HTTP duration on the Resource Server.
- Introspection timer.
- AS request rate.
- Active/pending pool connections.
- AS latency and error rate.
- Cache hit ratio if caching is enabled.

If the Resource Server hits 500 RPS while the AS only processes 200 introspection RPS, the difference may come from caching or failing requests. Cross-check the success rate and actual introspection call count.

### 10.6. Ensure the Load Generator Is Not the Bottleneck

A load generator machine can run out of CPU, sockets, or ephemeral ports before the Resource Server does. Warning signs include high generator CPU, dropped iterations, and rising client-side latency while the server shows no matching load.

Run multiple load generators on sufficient network capacity and compare server-side request rates against client-side iteration rates. Never draw server conclusions from a single generator's metrics alone.

---

## 11. Throughput, Concurrency, and Little's Law

Little's Law describes the relationship between average requests in the system, throughput, and time spent in the system:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests currently being processed or waiting.
- \(\lambda\): average throughput (requests/second).
- \(W\): average time spent in the system (seconds).

For example, if the system processes 400 RPS with an average duration of 0.1 seconds:

\[
L = 400 \times 0.1 = 40
\]

On average, roughly 40 requests are in flight. If latency rises to 0.5 seconds while throughput remains 400 RPS:

\[
L = 400 \times 0.5 = 200
\]

Average concurrent requests climb to 200. That drives up demand for request slots, connection pools, memory, and queues.

Little's Law applies to stable systems and averages measured across the same boundary. Never multiply p99 by RPS and treat the result as exact concurrency.

### 11.1. Higher Concurrency Does Not Always Increase Throughput

Initially, increasing concurrency can improve CPU and I/O utilization. Once capacity is reached:

- CPU run queues grow.
- Connection pool pending counts rise.
- Thread pool queues back up.
- GC pauses and context switching increase.
- The AS or database becomes overloaded.
- p95/p99 latency climbs steeply.
- Useful throughput plateaus or drops.

This is the saturation point. Operational targets typically keep traffic below the knee where latency begins climbing steeply, leaving headroom for bursts and node failures.

### 11.2. Distinguish Service Latency from End-to-End Latency

Client-measured end-to-end latency may include DNS, TCP, TLS, gateways, network transit, and the server. Server timers measure only from when the request crosses a specific boundary.

When comparing numbers, state the exact boundary:

- Client-side request duration.
- Gateway upstream duration.
- Resource Server HTTP duration.
- Authentication component duration.
- AS introspection duration.

If boundaries differ, measurements cannot be compared directly.

---

## 12. Optimizing Performance in a Sensible Order

### 12.1. Measure Before Optimizing

Start by establishing a baseline:

- RPS and concurrency.
- Request p50/p95/p99.
- Authentication p50/p95/p99.
- CPU, heap, and GC.
- Connection pool and thread/event-loop metrics.
- JWKS fetch and introspection latency.
- Error rate and status code distribution.

Record application version, JDK, CPU/memory limits, token type, signing algorithm, cache settings, and workload. Without holding these fixed, before/after benchmarks are hard to interpret.

### 12.2. Reduce Network Calls on the Hot Path

If every request calls an introspection or permission service:

- Evaluate whether local JWT validation fits your threat model and revocation policy.
- Use connection reuse and properly sized pools.
- Co-locate services in the same network/region.
- Use caches with TTLs aligned to freshness requirements.
- Batch permission lookups where possible without creating oversized queries.
- Eliminate unnecessary extra calls inside converters.

### 12.3. Keep Decoders and Clients Shared

Never instantiate a `JwtDecoder`, `WebClient`, HTTP client, or connection pool per request. These components should have managed lifecycles and be reused.

Creating a new client per request forfeits connection reuse and adds TLS handshakes, DNS lookups, and allocations. Recreating decoders repeatedly can also discard the JWK cache.

### 12.4. Keep Token Claims Intentionally Minimal

Oversized JWTs increase:

- Request header size.
- Transmission and parsing cost.
- Memory allocation.
- Amount of claim mapping required.
- Risk of exceeding proxy or server header limits.

Include only the claims the Resource Server actually needs. Never turn a JWT into a replica of an entire user profile or permission database.

Do not strip claims required by security policy just to save a few bytes. Optimization must retain issuer, audience, expiry, scopes, and required bindings.

### 12.5. Keep Converters Lightweight

Converters should primarily map verified claims to Authentication/GrantedAuthority objects. If a remote service call is required, measure it separately and consider caching or moving the lookup to the authorization boundary.

Avoid heavy work such as sequential service calls, loading full user profiles, or fetching entire ACLs when an endpoint does not need them.

### 12.6. Avoid Blocking in WebFlux

Blocking calls can tie up event-loop threads. Use reactive drivers/clients and verify with a profiler or BlockHound in appropriate tests.

If a blocking call is unavoidable, isolate it on a properly bounded scheduler with explicit concurrency/queue limits and timeouts. Never treat the default scheduler as an unbounded sink for blocking work.

### 12.7. Optimize Cryptography Only With Evidence

If CPU profiling shows signature verification is the bottleneck:

- Benchmark algorithms/key sizes supported by the AS.
- Check the JDK and cryptographic provider.
- Check CPU instruction support.
- Avoid redundant token parsing or conversion.
- Maintain proper key/JWK cache lifecycles.
- Scale the Resource Server horizontally by CPU when the workload is genuinely CPU-bound.

Never shrink key sizes or weaken the algorithm allowlist just to boost RPS. Every cryptographic change must satisfy the security baseline.

---

## 13. Performance Across Mixed Request and Token Types

### 13.1. Valid and Invalid Tokens Have Different Costs

Malformed tokens may be rejected early during parsing. Well-formed tokens with invalid signatures still incur part of cryptographic verification. Valid tokens continue through validators, converters, and authorization.

Therefore, do not benchmark solely with one type of invalid token and extrapolate throughput for valid traffic.

### 13.2. 401 and 403 Follow Different Paths

- **401 Unauthorized:** typically unauthenticated, such as missing token, expired token, invalid signature, or inactive introspection.
- **403 Forbidden:** Authentication succeeded, but authorities or policy are insufficient.

If a 403 request also runs tenant lookups or object-level authorization, its cost can exceed an early-rejected 401. Break down metrics by outcome to understand the distribution.

### 13.3. Method Security Can Add Overhead

Method security annotations can run additional checks on service method calls. If the same permission is checked in the filter chain and again across multiple layers, clarify the purpose of each layer.

Do not remove method security solely to shave latency if it provides critical defense-in-depth. Instead, eliminate duplicate queries, cache permission data appropriately, and define clear policy boundaries.

### 13.4. Requests With Multiple Service Calls

A request may call a permission service, tenant service, repository, and downstream API. If called sequentially, total latency approaches the sum of round trips. If independent and run in parallel, latency approaches the slowest step while downstream concurrency and load increase.

Do not parallelize checks that have data dependencies or where parallelism creates traffic spikes. Use traces to identify the critical path.

---

## 14. Resilience When the Authorization Server or JWKS Endpoint Slows Down

### 14.1. JWTs With Cached Keys During a JWKS Endpoint Outage

If the Resource Server already holds the valid public key in cache, it can usually continue verifying tokens with that key during a temporary JWKS endpoint outage. However, when a token uses a new key not yet in cache, the decoder will not be able to verify it.

Test these scenarios:

- Key already cached, JWKS endpoint down.
- New token uses unknown kid, JWKS endpoint down.
- Slow JWKS responses.
- Key rotation under heavy incoming traffic.
- Cache refresh and retry behavior.

Never retain old keys indefinitely just to preserve availability; compromised keys must be retired through emergency procedures.

### 14.2. Opaque Introspection Endpoint Failures

If the AS fails to respond, the RS does not know whether the token is still active. Never turn a timeout into active=true or grant a default Authentication.

Operational options:

- Fail closed whenever the token cannot be verified.
- Cache active responses within a short policy-approved TTL.
- Use a circuit breaker to stop flooding a failing AS.
- Bound concurrency and timeouts.
- Alert when AS error rate or latency crosses thresholds.
- Distinguish inactive tokens from AS unavailability.

A circuit breaker must never turn a dependency failure into granted access. Fallbacks must follow security policy; for unverified tokens, the fallback is typically rejection.

### 14.3. Stale Caches and Revocation

Caching improves availability but delays recognition of revoked tokens. Document clearly:

- Maximum TTL.
- Invalidation mechanism.
- Propagation time across nodes.
- Behavior when the cache backend fails.
- Policy for high-privilege tokens.
- Remaining access token lifetime.

This is a security/performance trade-off that must be approved at the policy level, not merely tuned as an engineering parameter.

---

## 15. Example: Reading a Benchmark Result

Suppose a test run yields these numbers:

| Scenario | Successful RPS | p50 request | p95 request | p99 request | p95 authentication |
|---|---:|---:|---:|---:|---:|
| JWT, warm JWK cache | 1,200 | 28 ms | 75 ms | 140 ms | 4 ms |
| JWT, frequent JWKS misses | 700 | 45 ms | 210 ms | 900 ms | 90 ms |
| Opaque, direct introspection | 350 | 85 ms | 260 ms | 700 ms | 65 ms |
| Opaque, 20-second cache TTL | 900 | 35 ms | 100 ms | 230 ms | 8 ms |

These figures are hypothetical to illustrate how to read the table, not an official Spring Security benchmark.

Questions to investigate from this table:

- JWT warm path has low authentication p95; the rest of the request time likely sits in application logic or network.
- Frequent JWKS misses push JWT p99 sharply higher; inspect key caching/rotation and the JWKS dependency.
- Direct opaque introspection shows high authentication p95; inspect the AS, pool wait time, and network.
- Opaque caching improves latency, but the post-revocation staleness window must be evaluated.
- Higher RPS alone does not mean better if error rates, stale authorization, or memory costs rise.

Never use an illustrative table to set production SLAs. Real benchmarks must be repeated on identical hardware, software versions, and workloads.

---

## 16. Operations Checklist

### 16.1. Before Deployment

- [ ] Define latency SLOs for overall requests and authentication.
- [ ] Decide between JWT and opaque tokens and document revocation policy.
- [ ] Verify JWK caching, refresh, and key rotation behavior.
- [ ] Set timeouts for JWKS, introspection, and permission services.
- [ ] Configure shared connection pools.
- [ ] Verify there is no blocking I/O on the WebFlux event loop.
- [ ] Cap cache TTLs per freshness requirements.
- [ ] Define failure policy when the AS or cache backend fails.
- [ ] Ensure metric labels contain no tokens or user IDs.
- [ ] Prepare workloads for valid, invalid, and cold/warm paths.

### 16.2. In Production

- [ ] Monitor HTTP and authentication p50/p95/p99.
- [ ] Monitor successful RPS, 401/403/5xx, and timeouts.
- [ ] Monitor CPU, heap, GC, threads, and event-loop utilization.
- [ ] Monitor JWK cache misses and JWKS fetch latency.
- [ ] Monitor introspection latency, errors, and pool pending counts.
- [ ] Monitor converter/permission lookup duration.
- [ ] Monitor cache hit ratio, evictions, and staleness window.
- [ ] Alert when tail latency spikes or throughput drops.
- [ ] Never log access tokens, refresh tokens, client secrets, or DPoP proofs.

### 16.3. When Latency Spikes Suddenly

1. Identify when the spike started and which routes or token types are affected.
2. Compare HTTP latency with authentication latency.
3. Check RPS, error rates, and saturation over the same window.
4. If JWT: inspect CPU, JWK cache misses, key rotation, and signature failures.
5. If opaque: inspect AS latency, connection pools, timeouts, and introspection rate.
6. If converter/authorization: inspect role/tenant services and query latency.
7. If WebFlux: look for blocking calls, event-loop saturation, and scheduler queues.
8. If only p99 rises: inspect queueing, retries, GC pauses, lock contention, and cold paths.
9. Make one controlled change at a time and re-measure on the same workload.
10. Verify the change has not weakened token validation or revocation policy.

---

## 17. Self-Check Questions

**Question 1.** How does latency differ from throughput?

**Answer:** Latency is the time a single request takes across a measured boundary; throughput is the number of requests processed per second. A system can increase RPS while degrading p95/p99 if it is nearing saturation.

**Question 2.** Why do JWTs usually not require calling the AS on every request?

**Answer:** The Resource Server can verify signatures locally using public keys fetched from JWKS and cached. The AS/JWKS only needs to be called when metadata/keys are needed or refreshed per policy.

**Question 3.** What is the impact of a JWKS cache miss?

**Answer:** The decoder may have to make a network call to fetch the JWK Set, creating higher cold-path latency than the warm path. If many requests miss together, they can create a spike against the AS.

**Question 4.** What extra costs does opaque introspection introduce?

**Answer:** Typically a network round trip, connection acquisition, TLS/HTTP processing, and processing time on the Authorization Server.

**Question 5.** What is the risk of caching introspection active=true results?

**Answer:** A token revoked after a cache hit can still be treated as active until the cache entry expires or is invalidated. TTL is part of revocation policy.

**Question 6.** Why is measuring p95 and p99 necessary?

**Answer:** Averages can conceal a subset of very slow requests. Percentiles reveal the tail latency actually experienced by users.

**Question 7.** Why should you not sum every timer?

**Answer:** Timers can be nested. HTTP duration already includes security and application durations; adding them together double-counts time.

**Question 8.** Does WebFlux guarantee infinite throughput?

**Answer:** No. Reactive pipelines manage asynchronous I/O efficiently, but CPU, connection pools, downstream capacity, and concurrency remain finite. Blocking calls can also stall the event loop.

**Question 9.** What does Little's Law express?

**Answer:** The average number of requests in the system equals average throughput multiplied by average time spent in the system, assuming a stable system and consistent measurement boundaries.

**Question 10.** Why should subject never be used as a metric tag?

**Answer:** Subject creates very high cardinality and can be identifying data. Metric labels should be bounded dimensions like operation or outcome.

**Question 11.** Can a converter calling a role service be slower than JWT verification?

**Answer:** Yes. A network or database round trip often takes longer than in-memory parsing and signature verification. Measure converters and lookups separately.

**Question 12.** When introspection times out, should the Resource Server issue Authentication from an arbitrary cache?

**Answer:** Only when a designed and approved cache policy with explicit TTL/freshness limits applies. Never turn a timeout into active=true or a default principal by default.

**Question 13.** Why benchmark both cold paths and warm paths?

**Answer:** Cold paths may involve fetching JWKS, establishing connections, or warming up the JIT; warm paths use ready caches and connections. Production experiences both.

**Question 14.** Does increasing thread pools or connection pools always increase throughput?

**Answer:** No. Too many threads or connections can increase context switching, memory usage, contention, and downstream overload. Determine true capacity via load testing.

**Question 15.** How do you tell whether the bottleneck is in authentication or business logic?

**Answer:** Time decoder/introspection, converter, authorization, controller/repository, and the full HTTP request separately, then compare them across the same trace or time window.

---

## 18. References

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive JWT decoder, validation, and authentication converters.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque tokens and introspection.
- [Spring Security — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): ReactiveOpaqueTokenIntrospector and WebFlux integration.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, JWK Set, JWT validation, and key retrieval.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics and application instrumentation.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, histogram, and percentile concepts.
- [Reactor Reference — Testing and instrumentation](https://projectreactor.io/docs/core/release/reference/): reactive pipelines, schedulers, and instrumentation.
- [k6 — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): load testing models and arrival-rate executors.
- [Little's Law](https://en.wikipedia.org/wiki/Little%27s_law): relationship between throughput, time in system, and concurrency.

Verify the exact documentation for the Spring Security, Spring Boot, Micrometer, and Reactor versions your project uses. Default metric names and instrumentation behavior can vary by version, configuration, and observation conventions.

## 19. Takeaways

Authentication time is one slice of request latency. To optimize a Resource Server, separately measure JWT decoding, JWKS lookups, opaque introspection, Authentication conversion, authorization, and business logic.

- **JWT:** the hot path usually verifies signatures locally using cached JWKs; cold paths or key rotations may trigger fetches.
- **Opaque tokens:** introspection usually adds a network dependency; caching lowers latency but widens the revocation visibility window.
- **WebFlux/Servlet:** reactive does not remove CPU, pool, or downstream limits; blocking calls on the event loop can degrade latency across the entire app.
- **Measurement:** use p50/p95/p99, successful RPS, error rates, saturation, and per-boundary timers.
- **Optimization:** measure first, reuse shared decoders/clients, cut unnecessary network calls, set sensible timeouts/concurrency limits, and never relax security validation.
- **Operations:** watch cold/warm paths, key rotation, AS outages, cache freshness, and tail latency; never put credentials in logs or metric labels.

A fast Resource Server processes tokens efficiently while still enforcing issuer, audience, signature, expiry, scopes, resource-level permissions, and revocation policy.
