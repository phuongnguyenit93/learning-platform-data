# Testing Slow, Disconnected, or Unavailable Dependencies

Java applications typically depend on databases, message brokers, HTTP APIs, DNS/service discovery, secret managers, filesystems, or other internal services. When using CRaC, an application may be checkpointed and then restored after a period of time. During that interval, external services continue operating and changing independently: a service may start slowly, endpoints may change, connections may be closed, credentials may expire, or a dependency may become temporarily unreachable.

A successful restore at the JVM level therefore does not prove that the application can serve requests. You need to test scenarios where dependencies respond slowly, connections are dropped, and dependencies are not yet ready; verify that CRaC callbacks have time bounds; check that the application transitions readiness properly; and ensure requests do not pass through stale resources or invalid data.

## 1. Distinguishing Dependency Failure Modes

Do not lump every incident under “service down”. Different failure modes require different fault creation methods and test criteria.

| Scenario | Manifestation | Example | What to verify |
| --- | --- | --- | --- |
| Slow response | Connection succeeds, but response takes a long time | Slow HTTP API processing, locked database query | Request timeouts and callback deadlines are enforced properly. |
| Connection refused | Cannot establish TCP connection | Service not listening yet or wrong port | Client classifies connect errors and retries with bounds. |
| Connection reset/closed | In-use socket closed by peer or network | Pod replaced, database failover, broker channel closed | Pool evicts broken connections and creates new ones. |
| Packet loss or network disruption | Connection may hang or time out instead of failing immediately | Network partition, route change | Client has timeouts at each layer and does not wait indefinitely. |
| DNS/service discovery failure | Hostname fails to resolve or returns stale endpoint | DNS record changed, resolver temporarily unreachable | Cache and endpoints refresh according to policy. |
| Dependency not ready | Process is running, but service is not accepting requests yet | Database in recovery, broker has not elected leader | Readiness keeps refusing traffic until probes succeed. |
| Authentication failure | Server responds unauthorized/forbidden | Credential expired or rotated | Refresh credentials properly; do not retry indefinitely with old secrets. |
| Overload or resource limit | 429, 503, connection pool exhausted, queue full | Rate limiting or service saturation | Backoff, bulkhead, and load shedding operate properly. |
| Invalid response | Connected, but payload/schema is incorrect | API returns format error or incompatible version | Do not classify permanent data errors as network errors for infinite retry. |

Distinguish transient errors from non-self-recovering errors. Timeouts, resets, and 503 may be transient; 401 may require a token refresh; 403 is usually a permissions issue; schema mismatches or invalid input data typically require configuration/code fixes. Retries are only useful when the cause is likely to change within the retry window.

## 2. Why Does CRaC Require Dedicated Testing?

At checkpoint time, heap state may contain clients, connection pools, caches, DNS results, tokens, schedulers, and circuit breaker state. These objects may still exist after restore, yet external dependencies may have changed.

For example, a connection pool created before checkpoint may hold:

- Sockets closed by the server while the process was paused.
- Connections to old IPs after DNS or service discovery changed.
- Database sessions that timed out or underwent failover.
- TLS session/certificate state that is no longer valid.
- Old credentials used to open new connections.

Similarly, a scheduler may hold overdue refresh schedules; a circuit breaker may stay `OPEN` even after the dependency recovered, or `CLOSED` even though the service is now failing. An in-heap cache may still serve stale data even though the source changed.

Therefore, CRaC tests need to verify all three layers:

1. **Process:** Does the JVM restore and execute callbacks successfully?
2. **Resource:** Are clients, pools, sockets, schedulers, and credentials refreshed or validated properly?
3. **Service behavior:** Do readiness, requests, message processing, and business data behave properly when dependencies are slow or failing?

## 3. Defining Application Policy Before Writing Tests

Not all dependencies need to be handled the same way. Before fault injection, determine which dependencies are mandatory for application readiness and which dependencies can operate in degraded mode.

| Dependency type | Common policy | Readiness after restore |
| --- | --- | --- |
| Database containing required business data | Must connect and validate before serving DB-dependent operations | `NOT_READY` if connections cannot be opened or the health query fails. |
| Message broker for required consumers | Create new consumer/session, subscribe, and verify group/queue state | `NOT_READY` if the application cannot receive or process messages as required. |
| HTTP service required for every request | Check connectivity or use an appropriate probe | May be `NOT_READY` if there is no fallback mode. |
| HTTP service used only for an optional feature | Use timeouts, circuit breakers, and bounded fallbacks | May be `READY` if the remaining capabilities still meet SLOs. |
| Secret manager | Fresh credentials required to create clients or connect to database | `NOT_READY` if valid secrets have not yet been retrieved. |
| Telemetry/metrics exporter | Can buffer or drop telemetry briefly | Usually should not block readiness for core business flows. |
| Reloadable cache | Invalidate or refresh per policy | Depends on data type; permission/credential caches need verification before use. |

Specify explicitly which degraded modes are permitted, for how long, and under what limits. Do not mark the application `READY` merely because the process is alive if mandatory dependencies are not yet operational.

## 4. Designing Tests by Timing in the Checkpoint–Restore Cycle

Test dependencies at multiple points in time, because failures before checkpoint differ from failures occurring while the process is stopped or after restore.

| Fault timing | Scenario | Outcome to verify |
| --- | --- | --- |
| Before checkpoint | Dependency is slow or disconnected while requests/transactions are running | Application drains work within deadline; does not checkpoint while transactions are in an unsafe state. |
| Inside `beforeCheckpoint` | Connection pool fails to close or workers do not finish | Callback times out/fails properly; does not falsely report preparation succeeded. |
| After checkpoint, before restore | Dependency restarted, DNS changed, credentials rotated, network policy changed | Restore does not assume external state remained intact. |
| Inside `afterRestore` | Dependency not listening yet or secret manager unavailable | Bounded retry; callback/readiness reflects not-ready state. |
| Right after readiness opens | Dependency drops again as traffic begins | Requests have timeouts, safe retries, and active circuit breakers/bulkheads. |
| While application is steady | Dependency failover or network partition | Application recovers connections without unnecessary process restarts. |
| Aborted checkpoint | Some resources already stopped, but checkpoint did not complete | Coordinator rolls back/resumes or stays `NOT_READY` per policy; does not wait for `afterRestore` to roll back. |

Each test should record the checkpoint attempt id, restore attempt id, dependency state, and the timestamps when faults are enabled/disabled. This helps distinguish failures caused by CRaC callbacks from failures caused by unavailable dependencies.

## 5. Injecting Controlled Faults in the Test Environment

Fault injection needs to be reproducible and affect only the test environment. You can combine fake dependencies, mock servers, network proxies, and real containers.

| Tool/technique | Suitable for testing | Limitations |
| --- | --- | --- |
| Fake/stub in unit tests | Timeout logic, retries, state transitions, readiness, and deterministic errors | Does not fully simulate TCP, TLS, DNS, or real driver behavior. |
| WireMock or mock HTTP server | HTTP 5xx, 429, response delays, malformed responses, unavailable endpoints | Does not replace real protocol/database testing. |
| Toxiproxy | TCP latency, connection resets, timeouts, bandwidth limits, and network partitions between client and service | Proxy must be placed accurately in the connection path and its lifecycle managed. |
| Testcontainers | Real databases, brokers, and dependencies in containers | Starting containers alone does not simulate every failure; combine with proxies or service control operations. |
| Docker Compose test environment | Testing dependency startup order, service restarts, and network topology | Results depend on Docker/network setup and do not fully represent Kubernetes. |
| Kubernetes staging/chaos tooling | Pod restarts, readiness delays, network policies, node disruptions | Run only in a test namespace with strictly bounded scope. |

Example WireMock configuration that can make an HTTP API respond slowly or fail:

```java
stubFor(get(urlEqualTo("/catalog"))
    .willReturn(aResponse()
        .withStatus(503)
        .withFixedDelay(3000)
        .withBody("temporarily unavailable")));
```

The example illustrates a 3-second slow response returning 503. Import/helper syntax depends on the WireMock version in use. Status, delay, or body can be varied to test each error classification branch.

Toxiproxy is suitable when testing connection resets or latency at the TCP layer. Configure the proxy between the application and the dependency, then enable/disable toxics per test. To test DNS, you need a controllable resolver or dedicated test hostnames; adding TCP latency does not simulate name resolution failures.

Do not use a single test with all faults active at once. Start with one reproducible failure, verify the application reacts properly, and only then combine multiple faults to simulate complex incidents.

## 6. Testing Slow-Starting or Unavailable Dependencies

A dependency may take seconds or minutes to recover after a deploy/failover. Tests need to simulate cases where the JVM finishes restoring before the dependency is listening or accepting requests.

Basic scenario:

1. Start the application and create a valid checkpoint.
2. Stop the dependency or configure it to wait before listening.
3. Restore the application.
4. Verify that the application does not open readiness immediately when the JVM resumes.
5. Verify that reconnect has a deadline and retry/backoff.
6. Start the dependency after a delay within the retry window.
7. Verify that the application connects successfully, health checks pass, and readiness switches to accepting traffic.
8. Repeat with a delay longer than the retry window to verify the application fails according to policy and does not wait indefinitely.

Do not test by simply sleeping for a fixed duration and hoping the service is ready. Wait for a specific condition such as a listening port, a health endpoint reporting healthy, or a read-only query succeeding; still keep a wait timeout.

### Readiness, Liveness, and Startup Probes

The three probe types answer different questions:

- **Readiness:** Should the instance receive traffic right now?
- **Liveness:** Is the process still alive and capable of recovering on its own, or does it need a restart?
- **Startup probe:** Has the application finished a long initialization/restore phase?

A temporarily unavailable dependency should usually cause readiness to fail, not necessarily liveness. If liveness directly depends on the database or broker, an external outage can cause Kubernetes to continuously restart every instance, worsening the incident. Choose a policy based on the application's self-healing ability and operational requirements.

In Spring Boot, the Availability API can be used to keep traffic refused while reconnecting:

```java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC);

// Refresh credentials, reconnect dependencies, validate clients...

AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.ACCEPTING_TRAFFIC);
```

This is an illustrative example; publish `ACCEPTING_TRAFFIC` only after all mandatory dependencies have met health criteria. For applications not using Spring Boot, implement an equivalent readiness gate in the HTTP health endpoint or service registry.

## 7. Testing Slow Responses and Timeouts at Each Layer

A request to a dependency can wait in multiple places:

1. Acquiring a connection from the pool.
2. Resolving DNS.
3. Establishing the TCP connection.
4. TLS handshake.
5. Sending the request and waiting for the response.
6. Executing the query or server-side processing.
7. Reading the body/response.
8. Retrying after errors.

Configuring only a `readTimeout` does not mean the entire request is time-bounded. For example, a connection pool might wait indefinitely to borrow a connection; DNS may be slow; retries may extend total duration far beyond the per-call timeout.

There should be an overall deadline and timeouts at each corresponding layer:

| Layer | Timeouts to consider |
| --- | --- |
| Connection pool | Maximum time waiting to acquire a connection. |
| DNS | Resolver timeout or lookup time limit if supported by the client. |
| TCP | Connect timeout. |
| TLS | Handshake timeout or overall timeout wrapping the connection if the library has no dedicated one. |
| HTTP | Response/read timeout and overall call timeout. |
| JDBC | Connection timeout, query timeout, socket/network timeout per driver. |
| Broker | Timeouts for connect, poll, publish, ack/commit, and heartbeat/session policy. |
| Retry | Total retry budget stays within the request/callback deadline. |

For example, a callback with a 20-second budget should not call three dependencies sequentially with up to 20 seconds of retries each. Sub-operations must use the remaining portion of the overall deadline.

## 8. Testing Retries, Backoff, and Jitter

Retries help recover from transient errors, but retrying too quickly or all at once can overload a recovering dependency. Tests need to verify:

- Only potentially transient error types are retried.
- There is a retry count limit or an overall deadline.
- Wait intervals grow with exponential backoff and have a maximum cap.
- Jitter is included so multiple instances do not retry at the exact same moment.
- Locks are not held while sleeping/waiting to retry.
- Non-idempotent operations are not retried without an idempotency key or deduplication mechanism.
- Once the budget is exhausted, the component stays `NOT_READY` or returns a clear error.

Example of a simple retry helper with a deadline:

```java
public void connectWithRetry(Duration totalBudget) throws Exception {
    long deadline = System.nanoTime() + totalBudget.toNanos();
    long delayMillis = 100;
    Exception lastFailure = null;

    while (System.nanoTime() - deadline < 0) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Reconnect interrupted");
        }

        try {
            dependency.connectAndValidate();
            return;
        } catch (TransientDependencyException e) {
            lastFailure = e;
        }

        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            break;
        }

        long jitteredMillis = addJitter(delayMillis);
        long sleepNanos = Math.min(
                TimeUnit.MILLISECONDS.toNanos(jitteredMillis),
                remainingNanos);
        TimeUnit.NANOSECONDS.sleep(sleepNanos);
        delayMillis = Math.min(delayMillis * 2, 2000);
    }

    throw new DependencyUnavailableException(
            "Dependency did not become ready before deadline", lastFailure);
}
```

`dependency`, `TransientDependencyException`, `DependencyUnavailableException`, and `addJitter()` are illustrative application components. In production, classify exceptions per specific client, avoid retrying authentication/permission/schema errors as transient failures, handle duration overflow, and reserve part of the deadline for the final health check. If the callback is interrupted, do not swallow the interruption.

In unit tests, inject a clock/sleeper or retry policy to verify attempt counts and wait intervals without real sleeping. Integration tests are what verify actual timeouts of network clients.

## 9. Testing Circuit Breakers and Bulkheads

A circuit breaker stops calling a dependency when the error rate exceeds a threshold; after a wait period, it allows a few trial requests in the half-open state. A bulkhead limits concurrent requests so a slow dependency cannot exhaust all application threads or connections.

With CRaC, verify whether the restored breaker state is still appropriate:

- A breaker `OPEN` before checkpoint may remain open after restore even though the dependency has recovered.
- A breaker `CLOSED` in the image may not reflect an outage that began while the process was paused.
- In-flight half-open probes from before checkpoint should not be treated as still running after restore.
- Semaphores/permits in the heap may retain stale in-use counts if requests were interrupted at checkpoint time.

After restore, depending on the library and policy, you can reset the breaker, transition it to a probe-needed state, or let the breaker re-evaluate itself. Do not reset blindly if the breaker is protecting an overloaded dependency; bounded probes and jitter are needed to prevent all instances from opening traffic simultaneously.

Tests should create an outage long enough for the breaker to open, checkpoint, restore the dependency, and restore the application; verify the system does not trigger a burst of requests. Also test the case where the dependency is still failing after restore to ensure the breaker continues protecting the application.

## 10. Testing Connection Pools and Stale Connections

Connection pools are one of the resources most prone to failures after restore. Connections may be closed by the server, hit firewall idle timeouts, fail over, or undergo credential rotation while the application is paused.

Scenarios to test:

- Server closes all connections while the process is checkpointed.
- Pool contains idle connections that were already stale before checkpoint.
- Connections are currently borrowed when `beforeCheckpoint` starts.
- Pool closes successfully, but the checkpoint is aborted.
- New pool is created after restore, but the database is not ready yet.
- Database is ready, but old credentials are rejected.
- Pool validation query is slow or times out.

Verify that:

- The application stops accepting new database work before draining.
- Borrowed connections are returned or transactions rolled back within the deadline.
- Old pools/clients are closed via the appropriate API.
- After restore, the new pool uses the current endpoint and credentials.
- If validation fails, the pool is not published as ready.
- The old pool is not used concurrently after the new pool is published.

Do not call `DataSource.getConnection()` just once to prove the pool is healthy. Run an appropriate read-only query and verify the connection actually works. For business tests, use transactions/test data that can be cleanly rolled back or cleaned up.

## 11. Testing DNS, Service Discovery, and Endpoint Changes

Dependencies may change IPs or instances after checkpoint. Tests need to separate DNS failures from TCP failures:

1. Configure a test hostname pointing to server A.
2. Run the application, verify the client connects to A, and create a checkpoint.
3. Update the DNS record/service registry so the hostname points to server B.
4. Stop or block A.
5. Restore the application.
6. Verify that the client re-resolves the hostname according to cache policy and establishes new connections to B.
7. Verify an actual request reaches B, not just that a lookup returned the new IP.

Add cases for temporary NXDOMAIN DNS failures, multiple returned IPs, negative caching, slow resolvers, and endpoint B not yet healthy. If the client maintains its own DNS cache, inspect that cache rather than relying solely on `dig` from the shell.

## 12. Testing Message Brokers and Consumers

Consumers may lose sessions/group membership during the checkpoint interval. The broker continues managing messages, offsets, acknowledgements, and visibility timeouts.

Scenarios to include:

- Broker is not ready when `afterRestore` runs.
- Old connections/channels/sessions were closed during checkpoint.
- Kafka consumer must rejoin the group and receive new partition assignments.
- Unacknowledged RabbitMQ deliveries are redelivered after the channel closes.
- SQS visibility timeout expires and the message is redelivered.
- Handler is interrupted after database commit but before ack.
- Ack/offset commit already completed before the process checkpointed.

Verify that the application stops accepting new messages, drains handlers, and acks/commits only after business side effects are durable. Use inbox/idempotency so message redelivery does not duplicate business actions. After restore, create new consumers/sessions/channels; do not reuse old delivery tags, receipt handles, or assignments.

## 13. Testing Secret Managers and Credential Refresh

A secret manager may be slow or unavailable right when `afterRestore` needs fresh credentials. Tokens in the heap may have expired during checkpoint.

Tests should include:

- Secret manager responds slower than connect/read timeout.
- Secret manager returns 503 and then recovers within the retry window.
- IAM/workload identity is rejected.
- Secret version changed; old credentials are revoked.
- New token is fetched but is near expiration.
- Secret provider caches an old version.
- TLS certificate/trust store of the secret endpoint changed.

The application creates/publishes a new pool only after obtaining valid credentials and passing connection validation. If secrets cannot be fetched within the deadline, keep readiness at `NOT_READY`; do not fall back to revoked credentials. Do not log secret values in logs or test output.

## 14. Testing Failures in `beforeCheckpoint` and `afterRestore` Callbacks

The two callbacks have different responsibilities:

| Callback | Objective | Failures to simulate |
| --- | --- | --- |
| `beforeCheckpoint` | Quiesce, drain, and bring resources to a checkpointable state | Worker fails to stop, transaction does not finish, pool fails to close, dependency is slow during flush. |
| `afterRestore` | Recreate/verify resources and resume operations | DNS/secret/database/broker not ready, connect timeout, TLS/authentication failure. |

`beforeCheckpoint` needs to report an error if it cannot bring resources to a safe state within the deadline. Do not proceed with checkpointing while transactions or resources are in an indeterminate state just to save time.

`afterRestore` needs to handle unavailable dependencies according to policy. It may retry within the allowed window; if it still fails, report a callback failure or keep the application `NOT_READY` for orchestration to handle. Do not publish successful readiness before required resources operate.

If a checkpoint is aborted after callbacks already stopped resources, the original process may continue without running `afterRestore`. Test rollback/resume separately for the checkpoint failure path. Do not use `afterRestore` as a rollback callback.

## 15. Example Resource Validating Dependencies After Restore

The example below uses abstractions to illustrate a readiness gate, bounded retry, and health validation:

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Duration;

public final class DependencyResource implements Resource {
    private final DependencyClient client;
    private final ReadinessGate readiness;

    public DependencyResource(
            DependencyClient client,
            ReadinessGate readiness) {
        this.client = client;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        client.stopAcceptingWork();
        client.awaitInFlightWithTimeout(Duration.ofSeconds(15));
        client.closeConnections();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        client.reconnectWithRetry(Duration.ofSeconds(30));
        client.validateHealth();
        readiness.acceptTraffic();
    }
}
```

`DependencyClient` and `ReadinessGate` are application abstractions. Drain, reconnect, and health check methods must have timeouts; retries need error classification and an overall deadline. If this dependency serves only an optional feature, readiness policy may allow degraded mode instead of blocking the entire instance.

In production, have a coordinator manage multiple dependencies in sequence: refresh DNS/secrets, create network/database clients, connect brokers, start consumers/schedulers, and finally open traffic. Do not hold application locks while making network calls or waiting for retries.

## 16. Unit Tests for Retry and Readiness

Unit tests can use fake dependencies to verify state without real networking:

```java
class FakeDependency implements DependencyClient {
    private int attempts;
    private final int failAttempts;

    FakeDependency(int failAttempts) {
        this.failAttempts = failAttempts;
    }

    @Override
    public void connectAndValidate() throws TransientDependencyException {
        attempts++;
        if (attempts <= failAttempts) {
            throw new TransientDependencyException("not ready yet");
        }
    }

    int attempts() {
        return attempts;
    }
}
```

Conceptual JUnit 5 example:

```java
@Test
void becomesReadyWhenDependencyRecoversWithinBudget() {
    FakeDependency dependency = new FakeDependency(2);
    FakeReadinessGate readiness = new FakeReadinessGate();

    DependencyRecovery recovery = new DependencyRecovery(
            dependency,
            readiness,
            testRetryPolicy());

    recovery.reconnect();

    assertEquals(3, dependency.attempts());
    assertTrue(readiness.isAcceptingTraffic());
}

@Test
void remainsNotReadyWhenDependencyNeverRecovers() {
    FakeDependency dependency = new FakeDependency(Integer.MAX_VALUE);
    FakeReadinessGate readiness = new FakeReadinessGate();

    assertThrows(DependencyUnavailableException.class,
            () -> new DependencyRecovery(
                    dependency, readiness, shortTestRetryPolicy())
                    .reconnect());

    assertFalse(readiness.isAcceptingTraffic());
}
```

Class and helper names in the example are illustrative test components. Inject `Clock`, retry policy, and sleeper so unit tests do not wait in real time. Unit tests verify logic; they do not replace tests with real sockets, drivers, brokers, or the CRaC runtime.

## 17. Component Tests Using Mock Servers and Proxies

For HTTP clients, use WireMock or a mock server to produce:

- Fast 200 responses.
- 503/429 responses.
- Response delays greater than read timeout.
- Connection close before response completes.
- Malformed schema bodies or invalid content types.
- Endpoints that begin returning 200 only after a waiting period.

For TCP dependencies such as databases/brokers, use Toxiproxy to:

- Add latency and jitter.
- Cut open connections.
- Induce timeouts or low bandwidth.
- Re-enable the network path after an interval.

Tests should control faults via signals rather than arbitrary sleeps. For example, a test enables a proxy toxic, verifies that requests fail within the deadline, removes the toxic, and then verifies that the client reconnects successfully. With connection pools, verify that the pool evicts broken connections and does not continue returning stale connections.

## 18. Integration Tests with Real Dependencies

Testcontainers can run real databases and brokers to verify drivers, pools, and protocols. An integration test can:

1. Start database/broker containers.
2. Start the application with a CRaC-compatible JDK and dedicated checkpoint configuration.
3. Run a health check and a test business operation.
4. Create a checkpoint according to the runtime's procedure.
5. Restart the dependency or block connections while the application is checkpointed.
6. Restore the application.
7. Verify reconnect callbacks and readiness behavior.
8. Bring the dependency back up and verify the application self-recovers within the retry window.
9. Verify business data, transactions, and messages are neither duplicated nor lost.

If Testcontainers manages the dependency lifecycle, tests can stop/start containers via the library version's API. When simulating a network partition without stopping the server, place Toxiproxy between the application and the container. Do not share a single database container across multiple parallel tests if tests can mutate each other's state or data.

## 19. End-to-End Testing with Real CRaC

Unit tests calling `beforeCheckpoint()` and `afterRestore()` directly are useful for testing callback logic, but do not verify whether CRIU/JVM can dump or restore a process image. At least one integration test suite is needed using the target CRaC JDK, kernel, container runtime, and filesystem.

Overall workflow:

1. Start dependencies in a healthy state.
2. Start the application and verify readiness.
3. Send a representative workload, then request a checkpoint.
4. Verify that `beforeCheckpoint` drained and closed resources.
5. While the process is checkpointed, make dependencies slow, stop/restart them, change endpoints, or rotate credentials.
6. Restore the application from the checkpoint.
7. Verify process restore, post-restore callbacks, and resource reconnection.
8. Measure duration from restore to readiness.
9. Send requests/messages and verify business outcomes.
10. Verify logs/metrics show timeouts, retries, dependency recovery, and readiness transitions.

Run each failure scenario independently first. Only afterward combine them, such as DNS changing simultaneously with a slow database and a temporarily unavailable secret manager. If a combined test fails, sufficient telemetry is needed to tell which dependency failed first.

## 20. Reference Test Matrix

| ID | Dependency/fault | Timing | Expected outcome |
| --- | --- | --- | --- |
| DEP-01 | HTTP response slower than read timeout | After restore | Request times out within budget; readiness follows policy. |
| DEP-02 | HTTP 503 followed by recovery | `afterRestore` | Retries with backoff; readiness opens when health check succeeds. |
| DEP-03 | TCP reset while connection is open | During checkpoint | Pool/client does not use old socket; creates new connection after restore. |
| DEP-04 | Database not listening yet | After restore | Callback/recovery waits with a bound; instance does not accept traffic early. |
| DEP-05 | Database failover and endpoint change | During checkpoint | DNS/service discovery refreshes; new pool connects to current endpoint. |
| DEP-06 | Broker not ready | After restore | Consumer does not start/receive messages until broker and group/queue are ready. |
| DEP-07 | Message handler does not drain | `beforeCheckpoint` | Checkpoint is rejected/timed out per policy; unfinished messages are not acked. |
| DEP-08 | Secret manager timeout | `afterRestore` | Bounded retry; expired old credentials are not used. |
| DEP-09 | Credentials revoked | During checkpoint | New pool uses current secret version; readiness opens only after validation. |
| DEP-10 | Temporary NXDOMAIN DNS failure | After restore | Negative cache policy does not retain error too long; retries within deadline. |
| DEP-11 | Connection pool exhausted | Before checkpoint and after restore | Pool acquisition times out; bulkhead prevents thread exhaustion. |
| DEP-12 | Circuit breaker still OPEN | After restore | Probes/half-open per policy; no request storm. |
| DEP-13 | Dependency never recovers | After restore | Retry budget exhausted; instance stays `NOT_READY` or fails per policy. |
| DEP-14 | Checkpoint aborted after resources stopped | During checkpoint | Coordinator rolls back/resumes or stays `NOT_READY`; does not wait for `afterRestore`. |
| DEP-15 | Dependency fails again right after readiness | After restore | Circuit breaker, timeouts, and readiness reflect degradation accurately. |

The matrix should be tailored to actual dependencies. Not all tests need to run on every commit; unit/component tests can run frequently while CRaC end-to-end tests run on compatible pipelines/runtimes.

## 21. Measuring Test Results

To determine whether the application reacts properly, collect timestamps and metrics:

- Duration from restore request until `afterRestore` callbacks start/finish.
- Duration of secret fetching, DNS resolution, connection opening, and health checks.
- Retry counts, exception types, backoff, and wait times.
- Connection pool active/idle/pending, evicted connections, and acquisition errors.
- Consumer state, partition assignments, queue depth, and in-flight message counts.
- Circuit breaker state, bulkhead saturation, and rejected request counts.
- Readiness/liveness/startup probe results and state transition timestamps.
- Latency p50/p95/p99, error rate, and throughput after traffic opens.
- Timestamp when the dependency was brought back up and timestamp when the application recovered.

Tag logs with checkpoint attempt id and restore attempt id. Do not log passwords, tokens, private keys, or sensitive payloads. For metrics, use low-cardinality labels; message id, user id, and request id belong in traces/logs rather than metric labels.

## 22. Pass/Fail Criteria

A dependency fault test should pass only when behavior matches the predefined policy. For example:

**Pass** when:

- No unbounded waits exist; timeouts stay within budget.
- Readiness does not open when mandatory dependencies are not yet healthy.
- When dependencies recover within the retry window, the application reconnects and serves requests.
- When dependencies do not recover, the application stays `NOT_READY` or fails per policy without causing a restart/retry storm.
- No stale sockets, credentials, DNS endpoints, or invalid sessions are used.
- No business operations/messages are lost or duplicated in the tested commit/ack windows.
- Resources and schedulers are not erroneously started/stopped repeatedly during checkpoint/restore or checkpoint abort.

**Fail** when:

- Callbacks hang past deadlines or thread pools are exhausted due to blocking.
- Readiness opens before mandatory dependencies operate.
- The application reports healthy merely because the process is alive.
- Unbounded retries or synchronized retries cause overload.
- Data/side effects are lost or duplicated due to out-of-order transaction/ack handling.
- Restore continues using old clients/sessions/credentials without validation.
- An aborted checkpoint leaves the application partially stopped while still accepting traffic.

Specific timing criteria must be based on SLOs and environment. Do not use one single number for every database, broker, or API.

## 23. Common Testing Mistakes

| Issue in tests | Why results are unreliable | How to improve |
| --- | --- | --- |
| Using fixed `Thread.sleep()` to wait for dependencies | Tests depend on machine speed and become flaky | Wait on conditions/health checks with a deadline. |
| Mocking only exceptions in unit tests | Does not test sockets, DNS, TLS, drivers, or pool behavior | Add proxy and integration tests. |
| Testing only JVM restore | Does not prove dependency reconnection or proper readiness | Send real requests/messages after restore and check side effects. |
| Checking only that readiness endpoint returns 200 | Endpoint may not check mandatory dependencies | Design health indicators per dependency policy. |
| Making liveness directly depend on the database | Database outage can trigger a restart storm | Distinguish liveness from readiness and startup probes. |
| Unbounded retries in callbacks | Restore can hang indefinitely | Explicit overall deadline, retry cap, and failure behavior. |
| Sharing the same test database across parallel tests | Test state and data interfere with each other | Isolate containers/schemas/test data. |
| Not testing failures after business commit before ack | Fails to detect duplicates on broker redelivery | Test inbox/idempotency and broker state. |
| Disabling proxy without verifying dependency health | Test may pass due to timing or client using old cache | Verify real connections and the endpoint/instance receiving requests. |
| Not testing checkpoint abort | Resources may have stopped while the process does not restore | Inject faults during preparation/dump and test rollback. |

## 24. Testing Checklist

- [ ] List mandatory dependencies and dependencies that can operate degraded.
- [ ] Classify slow, refused, reset, timeout, DNS, authentication, and overload failures.
- [ ] Include tests before checkpoint, during preparation, during the checkpoint window, and after restore.
- [ ] Have fakes/stubs for unit tests and fault injection at the network layer.
- [ ] Use WireMock/mock servers for HTTP delays, 5xx, and malformed responses.
- [ ] Use Toxiproxy or equivalent tooling for TCP latency/reset/partition.
- [ ] Use Testcontainers or an equivalent environment for real databases/brokers.
- [ ] Test connection pools, stale sockets, credentials, and endpoint refresh.
- [ ] Test retry/backoff/jitter, overall deadlines, and cancellation.
- [ ] Test circuit breakers, bulkheads, and connection pool exhaustion.
- [ ] Readiness fails when mandatory dependencies are not ready; liveness does not cause restart storms.
- [ ] Test consumer drain, ack/offsets, and idempotency if a message broker is present.
- [ ] Test checkpoint abort and resource rollback/resume.
- [ ] Run at least one CRaC integration test on the target runtime/container/kernel.
- [ ] Measure restore-to-ready time, retries, latency, and error rates.
- [ ] Do not log secrets or sensitive data in logs/test output.

## 25. Conclusion

Slow, disconnected, or unavailable dependencies are normal occurrences in distributed systems, especially when an application is restored from an older process image. CRaC does not guarantee that databases, brokers, DNS, secret managers, or HTTP services keep the same state during the checkpoint interval. Therefore, testing must cover callbacks, resources, and business behavior after restore.

Create controlled faults using fakes, mock servers, network proxies, and real dependencies; verify timeouts at every layer, deadlined retries, circuit breakers, pool/client recreation, and readiness. Drain work before checkpoint, do not open traffic before mandatory dependencies are healthy, and test both dependency recovery and non-recovery cases. Combining unit, component, integration, and CRaC end-to-end tests shows that the application can recover safely when dependent services are slow or disrupted.
