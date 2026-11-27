# Avoiding Simultaneous Re-Registrations or Re-Queries After an Outage

When a registry just recovers from a connectivity outage, many providers may re-register simultaneously while many consumers reload their instance lists at once. The registry, having barely escaped overload, gets hit by a massive wave of requests and slows down or disconnects again. This phenomenon is commonly known as a thundering herd.

In Spring Cloud Service Discovery, two flows need to be controlled:

- **Registration storm:** many provider instances create or update registrations together after startup, reconnect, or session restoration.
- **Discovery query storm:** many consumers simultaneously call getServices, getInstances, refresh caches, or rebuild endpoint lists right after the registry recovers.

The solution is not merely raising timeouts. You must spread retry timing, limit request rates and concurrency, use caching sensibly, coalesce duplicate queries, and maintain explicit readiness and retry budgets. The goal is for the system to recover gradually within the registry's capacity rather than dumping the entire load at one instant.

## 1. Why Do Clients Act in Lockstep?

Clients typically share the same configuration and the same trigger event. Without randomized delays, they can fire requests almost simultaneously.

Common causes include:

- A container cluster deploys at once and all providers start within the same few seconds.
- Networking to Eureka, Consul, or ZooKeeper drops and recovers; every client reconnects together.
- Many ZooKeeper sessions expire within the same window and applications create new sessions simultaneously.
- Discovery caches across many consumers expire at the same timestamp.
- Many applications share identical refresh schedules, such as every 30 seconds from startup.
- A deployment or scale-out spawns hundreds of new instances registering together.
- A registry just recovers, and every consumer immediately retries previously failed requests.
- Health checkers, load balancers, and applications query the service list on identical cycles.

For example, 600 consumers refresh the registry together after the network recovers. If each consumer loads multiple service lists and retries three times on failure, the registry can receive thousands of requests in a short burst. If providers also re-register concurrently, both read and write load spike together.

This creates an amplification loop:

~~~mermaid
flowchart TD
    A["Registry or network experiences outage"] --> B["Many clients lose connection"]
    B --> C["Registry recovers"]
    C --> D["Clients reconnect / retry simultaneously"]
    D --> E["Registrations and queries spike"]
    E --> F{"Can registry handle the load?"}
    F -->|"No"| G["New timeouts and errors"]
    G --> D
    F -->|"Yes"| H["Clients recover gradually"]
~~~

Retrying immediately after every failure increases load precisely when the system is least able to handle it. Subsequent attempts must be spaced apart and distributed over a time window.

## 2. Distinguishing Retry, Reconnect, Refresh, and Registration

These actions serve different purposes; never lump them all into one shared retry loop.

| Action | Purpose | Risk when synchronized |
|---|---|---|
| Reconnect | Restore client connection to the registry | Many new TCP connections/sessions opened at once |
| Register | Create or update an instance record | Heavy write burst; risk of duplicate IDs |
| Renew/heartbeat | Maintain a lease or session | Periodic load spikes if schedules align |
| Refresh discovery | Reload instance/service lists | Many read requests and large response parsing |
| Health check | Verify registry or service status | Probe storm, especially with fan-out checks |
| Retry business request | Retry downstream call after error | Load amplification across service tiers |

A provider may have reconnected without yet registering successfully. A consumer may read the registry successfully while a cache still holds old instances. Track connection state, registration state, discovery refresh, and business readiness separately.

## 3. Using Exponential Backoff with Jitter

Exponential backoff increases the wait after each failure. Jitter adds randomness so clients do not retry at the exact same moment.

Without jitter, 600 clients failing at second 0 wait 1 second and all retry together; failing again, they all wait 2 seconds, 4 seconds, and keep generating synchronized load waves.

A common full-jitter formula:

\[
cap_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

\[
wait_n \sim Uniform(0,\ cap_n)
\]

Where n is the number of retries performed so far. Each client independently picks a random wait time between 0 and cap. Once cap reaches maxDelay, the wait stops growing.

Other variants:

| Strategy | How wait time is chosen | Characteristics |
|---|---|---|
| Exponential without jitter | Always wait cap | Prone to synchronized retries |
| Full jitter | Random from 0 to cap | Spreads attempts effectively |
| Equal jitter | Wait half of cap plus random portion of the remaining half | Reduces overly early retries |
| Decorrelated jitter | New wait derived from previous wait and bounds | Avoids fixed retry cadence |

Full jitter is usually straightforward to adopt. A maxDelay cap is required so attempts are not delayed indefinitely. For operations with business time limits, an overall deadline is also needed to stop retrying once useful time runs out.

## 4. Example of Generating Full-Jitter Wait Times in Java

The helper below computes the growing cap and selects a random wait duration. attempt starts at 0 on the first retry.

~~~java
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelay {

    private RetryDelay() {
    }

    public static long fullJitterMillis(
            int attempt,
            long baseDelayMillis,
            long maxDelayMillis) {

        if (attempt < 0) {
            throw new IllegalArgumentException("attempt must be >= 0");
        }
        if (baseDelayMillis <= 0 || maxDelayMillis < baseDelayMillis
                || maxDelayMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid delay range");
        }

        long cap = baseDelayMillis;

        for (int i = 0; i < attempt && cap < maxDelayMillis; i++) {
            cap = cap > maxDelayMillis / 2
                    ? maxDelayMillis
                    : Math.min(maxDelayMillis, cap * 2);
        }

        return ThreadLocalRandom.current().nextLong(cap + 1);
    }
}
~~~

Example configuration with a 500 ms base delay and 30-second max delay:

| Retry attempt | Maximum cap | Full-jitter wait range |
|---:|---:|---:|
| 0 | 500 ms | 0–500 ms |
| 1 | 1,000 ms | 0–1,000 ms |
| 2 | 2,000 ms | 0–2,000 ms |
| 3 | 4,000 ms | 0–4,000 ms |
| 4 | 8,000 ms | 0–8,000 ms |
| 5 | 16,000 ms | 0–16,000 ms |
| 6 onward | 30,000 ms | 0–30,000 ms |

These values illustrate a single retry operation. Never reuse the exact same parameter set for all requests, heartbeats, session timeouts, and health checks. Each operation type has its own deadline, cost, and fault tolerance.

When receiving Retry-After from a backend or gateway, honor that duration and consider adding small jitter past the requested timestamp. Never retry earlier than the backend's stated limit.

## 5. Classifying Errors Before Retrying

Not every error can be solved by retrying. If an error stems from misconfiguration, expired credentials, or a nonexistent serviceId, relentless retries only add load.

| Error category | Examples | Action |
|---|---|---|
| Transient error | Connection reset, timeout, registry leader election | Backoff and bounded retry |
| Overload | HTTP 429, 503, server overload | Throttle back, honor Retry-After, enforce retry budget |
| Auth/authorization error | 401, 403, ACL denied | Do not retry continuously; fix credentials/permissions |
| Misconfiguration | Wrong hostname, port, scheme, or path | Report configuration error and stop retrying |
| Invalid data | Schema-invalid metadata, duplicate instance ID | Do not retry blindly; fix the data |
| Service does not exist yet | No provider registered yet | Use a deadline or bounded waiting policy |

Retry only operations that can be repeated safely. Registrations need a stable instance ID and idempotent semantics so retries do not create multiple records. For writes that may produce side effects, verify state before retrying or use an idempotency key.

## 6. Bounding Retry Budgets and Attempt Counts

Backoff spreads out timing; a retry budget caps the total volume of retries the system permits.

For example, cap maximum retries to a small fraction of original requests over a time window. When original requests rise, permitted retries scale within the bound; when original requests drop, retries cannot keep generating standalone load.

Measures:

- Cap attempt counts per operation.
- Enforce an overall deadline instead of infinite retries.
- Cap the retry-to-total-request ratio.
- When the budget is exhausted, return a controlled error or serve still-valid cached data.
- Reset backoff state only after connectivity stays stable long enough, not immediately after a single flaky success.
- Track retry rate separately from original request rate.

Do not stack retries across every layer. For instance, HTTP client retrying 3 times, LoadBalancer retrying 3 times, and the service retrying the whole operation 3 times can produce up to 27 attempts for a single original request. Designate one primary retry layer and propagate remaining deadlines downward.

## 7. Staggering Startup and Registration Timing

When scaling a deployment from 0 to many replicas, instances often boot close together. If every instance registers the instant its ApplicationContext is ready, the registry absorbs a heavy write spike.

Peak load can be dampened via:

- Random initial delay before the first registration or attempt.
- Rolling deployments adding replicas in staged batches.
- Limiting maxSurge or concurrent newly created instances in the orchestrator.
- Limiting concurrency of registration operations.
- Retrying registration with backoff and jitter when the registry is not ready yet.
- Flipping readiness UP only after registration succeeds if the app relies on discovery to receive traffic.

For example, with 300 new providers spreading registration across a 30-second window, theoretical average write load is around 10 registrations per second instead of 300 almost at once. Real-world load still depends on random distribution, retries, and registry throughput; measure peak load rather than looking solely at averages.

Do not add the same fixed delay to every instance. If every container sleeps 10 seconds, they still wake up together. Use a per-instance random value or controlled rollout mechanics.

## 8. Registration Must Be Idempotent with Stable Identifiers

When reconnecting after an outage, a provider needs to know whether its old registration still exists or was lost. If every retry generates a new instance ID, the registry can accumulate multiple records for the same process.

Rules to apply:

- Generate an instance ID that remains stable across an instance's lifecycle.
- Never generate a new UUID on each registration retry.
- If the registry supports upsert or ID-based registration, rely on those exact semantics.
- After session expiration, create a new registration bound to the new session while keeping an appropriate logical identifier.
- When a process replaces an old instance, ensure the new ID does not collide and old records are cleaned up.
- Mark readiness UP only after registration state meets the application's verification rules.

With ZooKeeper ephemeral znodes, a new session must recreate the node after the old session goes LOST. Node creation logic must handle cases where the node already exists from an earlier retry or another process still holding the same path. Never delete another instance's node to "fix" a conflict.

With Eureka and Consul, check registration status before minting a new ID. Avoid repeating full metadata writes if only one field needs updating and the backend offers a suitable API.

## 9. Avoiding Query Storms with Caching and Single-Flight

Consumers should not call the registry on every business request when the instance list can be safely cached. Spring Cloud DiscoveryClient implementations may already maintain internal caches, though behavior depends on the registry client and configuration. Inspect the implementation before adding another cache layer.

Principles:

- Cache instance lists with an appropriate TTL.
- Add jitter to refresh timestamps so replica caches do not expire simultaneously.
- When the cache expires, allow only one request to execute the refresh; concurrent requests either use existing results or wait on the same future.
- Use stale-while-revalidate if older data remains safe for a brief window.
- Never retain known-unhealthy instances too long merely to save queries.
- Partition caches by serviceId if the consumer only needs a subset of services.
- Do not call getServices() across the whole registry when only getInstances() for a specific service is needed.

Single-flight coalesces multiple concurrent refresh requests for the same key into a single operation. For instance, 100 requests needing the inventory-service list while the cache expires share one refresh instead of launching 100 queries.

Conceptual flow:

~~~mermaid
flowchart TD
    A["Many requests need instance list"] --> B["Check cache by serviceId"]
    B --> C{"Cache still usable?"}
    C -->|"Yes"| D["Return cache"]
    C -->|"No"| E["Check in-flight refresh"]
    E --> F{"Refresh already running for key?"}
    F -->|"Yes"| G["Wait / share result"]
    F -->|"No"| H["Start one refresh"]
    H --> I["Call DiscoveryClient"]
    I --> J["Update cache and release waiters"]
    J --> G
~~~

Never use stale data indefinitely. Enforce a max stale age and explicit fallback policy. If an endpoint was removed for security reasons or readdressed, using an overly stale cache can keep routing consumer traffic to an unauthorized instance.

## 10. Jitter for Cache TTLs and Refresh Schedules

If every consumer uses a 30-second TTL starting from the same deploy moment, they can all refresh at second 30. Add randomness to the TTL or refresh schedule:

\[
TTL_{\text{effective}} = TTL_{\text{base}} + Uniform(-jitter,\ +jitter)
\]

For example, a 30-second base TTL with ±5-second jitter spreads expirations across 25–35 seconds. Never pick jitter so large that stale data exceeds acceptable bounds.

Jitter must be smaller than the base TTL so effective lifetime stays strictly positive. Where TTL carries security implications or strict staleness bounds, evaluate both lower and upper edges rather than only the mean.

Another approach is periodic refresh with a random initial delay per process, followed by a fixed delay measured from completion of the prior refresh. Fixed delay avoids overlapping runs when operations turn slow; still enforce at most one in-flight refresh at a time.

Never add jitter to business request deadlines or timeouts in a way that violates SLAs. Jitter here spreads background task timing, not arbitrarily delaying responses.

## 11. Limiting Registry Concurrency and Access Rate

Even with jittered retries, many clients can still query the registry in a short window. Bound concurrent operations and request emission rates.

Available controls:

- Semaphores or bulkheads capping active discovery queries.
- Token buckets / rate limiters capping requests per second.
- Bounded queues for refresh or re-registration work.
- Capping concurrent registrations processed inside a worker.
- Per-operation timeouts and overall deadlines.
- Circuit breakers pausing backend calls during continuous errors, then probing cautiously in half-open state.

Example semaphore limiting concurrent operations within one process:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class DiscoveryConcurrencyLimiter {

    private final Semaphore permits = new Semaphore(4);

    public <T> T execute(
            java.util.concurrent.Callable<T> operation,
            long timeoutMillis) throws Exception {

        if (!permits.tryAcquire(timeoutMillis, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Discovery concurrency limit reached");
        }

        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
~~~

This semaphore limits concurrency only within a single JVM. With 100 replicas each allowing 4 concurrent requests, the registry can still receive 400 simultaneous requests. Cluster-wide limits require rate limiting or quotas at the gateway, registry, service mesh, or appropriate orchestration tier.

In the example, timeoutMillis governs only waiting for a permit. The operation itself still needs connect/read timeouts and an overall deadline; if an operation hangs forever, the permit stays held and starves process concurrency.

Never use unbounded queues. When the registry slows down, unbounded queues swell, hold expired tasks past their deadlines, and dump delayed load when the backend recovers. Cap queue size, drop expired tasks, and apply backpressure.

## 12. Circuit Breakers and Controlled Recovery

Circuit breakers prevent clients from continually sending requests to a failing backend. A typical model:

- **Closed:** requests flow through; failures are tracked.
- **Open:** backend calls pause for a cooldown duration.
- **Half-open:** only a small number of probes are allowed to retry.
- If probes succeed, transition back to closed; if they fail, return to open.

For a discovery registry, circuit breakers need tight probe limits and jitter when many replicas transition to half-open together. If 500 clients open their circuits for 30 seconds and all flip half-open together, the registry still takes a large probe wave.

A circuit breaker does not replace caching and does not self-heal registrations. It only throttles calls to a failing dependency. While open, the application must decide whether to use stale cache, keep serving current flows, or return a service-dependent error.

For registration operations, never pretend registration succeeded while the circuit is open. Providers should maintain appropriate readiness and continue retrying on a bounded schedule.

## 13. Registry-Specific Notes

### Eureka

Eureka Client runs periodic heartbeat and registry fetch tasks. When many clients start or reconnect together, observe renewal/fetch timing and avoid adding custom polling loops duplicating the built-in client.

Points to watch:

- Choose lease renewal and expiration intervals suited to the network; do not shrink them aggressively just to force faster detection.
- Keep registry fetch intervals aligned with list freshness needs.
- Check self-preservation behavior before interpreting lingering instances in the registry.
- Use client/LoadBalancer local caching intentionally and measure staleness.
- Avoid having every consumer health check call getServices() continuously if the full catalog is not needed.

### Consul

Consul agents perform health checks and synchronize service status. When many services are recreated together, agents and servers can receive heavy bursts of registrations and check updates.

Points to watch:

- Stagger startup and registration times.
- Choose sensible check intervals/timeouts; never set ultra-short intervals across thousands of services.
- Have consumers query passing instances only when filtering for healthy instances.
- Use consumer-side caching and cap refresh frequency.
- Monitor agent, node, and service states separately; avoid having all consumers poll the Catalog API simultaneously after a leader election.

### ZooKeeper

ZooKeeper clients use sessions and ephemeral znodes. After an ensemble recovers or many sessions expire, many clients may create sessions and re-register nodes simultaneously.

Points to watch:

- While SUSPENDED, do not rush to open a new session if the existing session may still be valid.
- When LOST, re-register with a new session and stable ID.
- Stagger reconnects and registration retries at the application layer if the library exposes suitable hooks.
- Use watchers for change notifications instead of continuous polling, while still resyncing after reconnect.
- After reconnect, stagger full resyncs; do not let all consumers read the full service tree at once.

Client libraries have their own reconnect mechanisms. Do not wrap an external retry loop around internal retries without understanding them, as nested layers multiply attempts and spike load.

## 14. Spring Cloud: Avoiding Stacked Retry Mechanisms

An application can simultaneously host retries across many layers:

- Registry client automatic reconnects.
- Discovery adapter retrying registry requests.
- Spring Cloud LoadBalancer retrying on instance selection or failed calls.
- HTTP client connection retries.
- Resilience4j retries or circuit breakers.
- Business code looping on caught errors.

Without assigning clear ownership, attempts multiply. For example, three layers each retrying up to 3 times can generate 27 attempts for one original operation.

Map ownership explicitly:

| Layer | Responsibility | Bounds |
|---|---|---|
| Registry client | Maintain session/connection and refresh registry | Rely on library mechanisms; avoid duplicate loops |
| Discovery cache | Hold instance list and refresh | TTL, jitter, single-flight |
| LoadBalancer/HTTP client | Pick instances and handle connection errors | Small retry count with timeouts |
| Business service | Decide fallbacks and idempotency | Overall deadline and retry budget |

Inspect your Spring Cloud version and specific implementation before modifying properties. There is no universal property enabling jitter across all of Eureka, Consul, ZooKeeper, and LoadBalancer. Where libraries lack configuration hooks, you may need an application-level adapter, scheduler, or orchestration; do not patch library internals without clear justification.

## 15. Observability to Detect Thundering Herds

Measure both request volume and request timing. A normal one-minute total can still conceal an intense multi-second spike.

Useful metrics:

| Metric | Meaning |
|---|---|
| registration_attempt_total | Total provider registration attempts |
| registration_success_total | Successful registrations |
| registration_retry_total | Registration retry attempts |
| discovery_query_total | Total discovery queries |
| discovery_query_duration | Latency of getServices/getInstances/probes |
| discovery_refresh_inflight | Concurrent active refreshes |
| discovery_cache_hit_ratio | Ratio served from cache |
| registry_connection_state | Client connection state |
| retry_delay_seconds | Chosen backoff delay |
| registry_error_rate | Error rate from the backend |

Track p50, p95, p99, and max latency; add per-operation histograms, and avoid putting unbounded serviceId or instanceId values into labels if doing so creates high cardinality.

Logs should record operation, attempt, delay, serviceId where needed, redacted registry endpoint, and connection state. Never arbitrarily log credentials, tokens, or full metadata blobs.

A classic thundering herd signature is a sharp spike in requests/connections right after a reconnect or deployment, followed by rising timeouts and climbing retry rates. Set alerts on retry rate, queue depth, registration conflicts, and recovery duration.

## 16. Testing Recovery Scenarios

Run a controlled load-recovery test:

1. Start the registry and a fleet of providers/consumers.
2. Record baselines for registrations, discovery queries, and latency.
3. Temporarily block registry connectivity in a lab environment.
4. Restart the registry or restore networking.
5. Observe per-second reconnects, registrations, and queries.
6. Compare runs without jitter against runs with backoff, jitter, caching, and concurrency limits.
7. Verify whether the registry gets overloaded a second time.
8. Check whether providers created duplicate registrations or consumers clung to stale instances too long.
9. Measure time until most clients recover.
10. Repeat with larger client counts and varied outage durations.

Never test network cuts or quorum loss in production. Tests must bound client scope, remain reversible, and avoid real business data.

Comparison criteria:

- Peak requests per second hitting the registry.
- Concurrent connection count.
- Registration success rate.
- Time for 95% of clients to recover.
- Average and maximum retry counts.
- Business request failure rate during recovery.
- Maximum discovery cache staleness.

A good configuration does not necessarily recover the very first client fastest. The objective is stable recovery of the entire system without triggering a secondary overload while staying within accepted staleness limits.

## 17. Common Pitfalls

| Symptom | Cause | Remedy |
|---|---|---|
| Registry disconnects again right after recovering | Clients reconnect simultaneously | Backoff with full jitter and concurrency limits |
| Duplicate registrations appear | Each retry mints a new instance ID | Use stable IDs and idempotent registration |
| Consumers fetch service lists together | Synchronized cache expirations or aligned polling | TTL jitter, single-flight, and targeted queries |
| Retries grow exponentially in volume | Stacked retries across multiple layers | Designate one primary retry layer and cap total budget |
| Registry queried constantly despite zero traffic | Aggressive scheduled refresh or health checks | Tune intervals, caching, and lightweight probes |
| Consumers keep calling dead instances after reconnect | Stale cache or unrefreshed watcher | Bounded resync, max stale age, and faulty endpoint eviction |
| Refresh queue grows unbounded | Backend slow while work keeps queuing | Bounded queues, deadlines, and backpressure |
| Circuit breakers flip half-open together | Synchronized recovery windows | Jitter cooldown timing and limit probes |
| Provider readiness UP before registering | Startup lifecycle skips registration wait | Tie readiness to registration state when discovery is required |
| Registry overloaded after rolling deploy | Too many new replicas created at once | Staged rollouts, surge limits, and random startup delays |

## 18. Design Checklist

Before shipping recovery mechanisms to production, confirm:

1. Registration and queries separate transient failures from config/permanent failures.
2. Retries use exponential backoff with jitter and a max delay cap.
3. Every operation enforces attempt limits and an overall deadline.
4. A retry budget caps aggregate retry load.
5. Instance IDs remain stable and registrations can be retried safely.
6. Startups and rollouts do not unleash simultaneous registration waves.
7. Discovery caches configure sensible TTLs and jitter.
8. Concurrent refreshes for the same serviceId coalesce via single-flight or equivalent.
9. Concurrency limits, rate limits, and bounded queues are enforced.
10. Circuit breakers cap half-open probes and avoid synchronized transitions.
11. Retries are not stacked across registry client, LoadBalancer, HTTP client, and business service.
12. Readiness stays down while mandatory registration prerequisites are incomplete.
13. Watcher reconnects trigger staggered resyncs rather than synchronized full reads.
14. Metrics track retries, registrations, queries, caching, and recovery times.
15. Outage/recovery scenarios have been tested in a lab environment.

The core principle is: **after an outage, never let every client retry immediately at once.** Spread attempts with jitter, bound attempt counts and rates, coalesce duplicate queries, leverage safe caches, and monitor recovery progress. The registry needs traffic to ramp up within its capacity so the system stabilizes without causing a secondary outage.
