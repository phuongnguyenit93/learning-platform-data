# Testing Restore After Expired Tokens, TTLs, and Connections

A CRaC checkpoint saves the state of a Java process at a point in time, while external systems continue operating while the process is paused. Upon restore, an access token may have expired, a refresh token may have been revoked, caches may have exceeded their TTL, the database may have closed idle connections, and the broker may have changed the session. The corresponding Java objects may still exist in the restored heap, but the external state they represent is no longer valid.

Therefore, restore testing needs to create an actual time gap between checkpoint and restore, while actively changing dependency state during that interval. Simply testing restore immediately after checkpoint is not enough to catch expiration bugs. Nor should you only check that Java fields are still non-`null`; you need to prove that the application re-authenticates, refreshes caches, creates new connections, and enables readiness only when required dependencies work.

Tests should combine two layers. Unit tests use a controllable `Clock` to verify deadline and TTL logic deterministically. Integration tests run with a CRaC JDK and a compatible environment to verify that callbacks, pause duration, token servers, caches, databases, and network connections actually work properly after restore.

## 1. States That Can Expire While the Process Is Paused

Before writing tests, list which state is managed by the process and which state is managed by external systems.

| State | What can happen during checkpoint | Behavior to verify after restore |
|---|---|---|
| Access token | Expired, revoked, or no longer matches audience/scope | Refresh or re-authenticate before calling APIs |
| Refresh token | Expired, rotated, or revoked | Obtain new credentials via the provisioned flow; if impossible, readiness/operation must fail clearly |
| Signing key/JWKS | Old key rotated or removed from the trusted key set | Load current metadata/keys and verify tokens per policy |
| TTL cache | TTL elapsed; data source changed | Do not return expired data; reload or invalidate |
| Negative cache | A transient error was cached too long or error state changed | Once TTL expires, retry according to policy |
| JDBC connection | Database, proxy, or firewall closed idle connection | Create new pool/connections and run validation query |
| HTTP keep-alive | Server or load balancer closed the socket | Client creates a new connection and handles safe retries |
| WebSocket/gRPC stream | Peer timed out or terminated the session | Reconnect and resume according to the application protocol |
| Kafka/RabbitMQ client | Heartbeat timeout, rebalance, channel closed | Create new client/session, rejoin group or re-register consumer |
| Lease/distributed lock | Lease expired and another instance took ownership | Re-acquire/renew; do not continue exclusive operations with stale state |
| DNS/service discovery | Backend address changed | Resolve current endpoint and create a new client if needed |

A good test must verify both directions: the application recovers successfully when it can refresh/reconnect, and the application refuses service when credentials or dependencies cannot be recovered.

## 2. Building a Multi-Layered Testing Strategy

Not every case needs to launch a real CRaC runtime. Separate logic that can be tested quickly from behaviors that can only be verified in a checkpoint/restore environment.

| Test layer | Objective | Tools/approach |
|---|---|---|
| Unit test | Verify expiration comparison, TTL, refresh window, and retry policy | Mocked `Clock`, fake token provider, in-memory cache |
| Component test | Verify coordination among token manager, cache, and connection manager | Mock HTTP server, test database instance, fake secret provider |
| Integration test | Verify `beforeCheckpoint`/`afterRestore` callbacks and client lifecycle | Compatible CRaC JDK, test database/broker/container |
| End-to-end restore test | Verify the entire application after a pause interval and dependency changes | Real checkpoint, wait outside the process, change dependency state, restore |
| Multi-replica test | Detect refresh stampede, connection storm, and lease contention | Restore multiple replicas from the same image, observe issuer/database/broker |

Unit tests verify application logic but do not prove that sockets or the runtime are recovered properly. Conversely, a single successful integration test on one machine does not replace unit tests for time boundaries. Combining both keeps tests fast and stable while still providing evidence of real CRaC behavior.

## 3. Using `Clock` to Test Tokens and TTLs Deterministically

Do not use `Thread.sleep()` in unit tests to wait for tokens to expire or caches to exceed TTL. That makes tests slow and prone to flakiness due to thread scheduling, machine load, or timer precision.

Inject `java.time.Clock` into components that need to read time. In production, use `Clock.systemUTC()`. In tests, use `Clock.fixed()` or a shiftable clock.

Example of a token provider checking expiration time:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

record AccessToken(String value, Instant expiresAt) { }

interface TokenClient {
    AccessToken refresh() throws Exception;
}

public final class AccessTokenProvider {

    private final Clock clock;
    private final Duration refreshSkew;
    private final TokenClient tokenClient;
    private final AtomicReference<AccessToken> current =
            new AtomicReference<>();

    public AccessTokenProvider(Clock clock,
                               Duration refreshSkew,
                               TokenClient tokenClient) {
        this.clock = clock;
        this.refreshSkew = refreshSkew;
        this.tokenClient = tokenClient;
    }

    public synchronized AccessToken current() throws Exception {
        AccessToken token = current.get();
        Instant refreshAt = token == null
                ? Instant.MIN
                : token.expiresAt().minus(refreshSkew);

        if (token == null || !clock.instant().isBefore(refreshAt)) {
            token = tokenClient.refresh();
            current.set(token);
        }
        return token;
    }

    public synchronized void refreshAfterRestore() throws Exception {
        current.set(tokenClient.refresh());
    }
}
```

This is a simple example of refreshing by a `refreshSkew` duration before expiration. In a real application, you need to handle synchronization bounds when multiple threads need a token concurrently, refresh errors, timeouts, retries with backoff, and refresh token rotation. Do not log `token.value()`; log only safe metadata such as issuer, expiry, and refresh result.

Tests can use `Clock.fixed()` to verify whether a token is valid, inside the refresh window, or expired without waiting:

```java
Instant issuedAt = Instant.parse("2026-11-13T08:00:00Z");
Clock beforeExpiry = Clock.fixed(issuedAt, ZoneOffset.UTC);

AccessToken token = new AccessToken(
        "test-token",
        issuedAt.plus(Duration.ofMinutes(10)));

assertTrue(beforeExpiry.instant().isBefore(token.expiresAt()));
```

This test snippet only illustrates how to fix time. You should test the behavior of `AccessTokenProvider` with a fake `TokenClient` that counts refresh calls and returns tokens with controlled expiry.

### When the Clock Needs to Advance Within the Same Test

A small `MutableClock` can be used to advance time without waiting in real time:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;

    public MutableClock(Instant initial) {
        this.current = new AtomicReference<>(initial);
    }

    public void advance(Duration duration) {
        current.updateAndGet(value -> value.plus(duration));
    }

    @Override
    public ZoneId getZone() {
        return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        throw new UnsupportedOperationException("UTC test clock only");
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

Tests can create a token expiring in 5 minutes, call `clock.advance(Duration.ofMinutes(6))`, and then verify that the provider refreshes before returning a token. Because the clock only controls logic inside the test process, it does not cause a token in a real identity provider or database to expire on its own. To test external systems, you must control the clock/test fixture in that system itself or use short-TTL tokens and wait in real time in integration tests.

## 4. Testing Access Tokens and Refresh Tokens

Tokens can expire by `exp`, be revoked, be rotated, or become invalid due to changes in issuer, audience, scope, or signing key. Tests that only create a JWT with an `exp` in the past will not cover these cases.

### Test Matrix for Tokens

| Scenario | Pre-checkpoint preparation | Change during pause | Expected result after restore |
|---|---|---|---|
| Valid access token | Token has sufficiently long remaining lifetime | Restore before `exp` | Token can be used if policy allows; no unnecessary refresh |
| Expired access token | Token has near-term expiry | Wait past `exp` | Provider refreshes before API call or before readiness per design |
| Valid refresh token | Valid access token and refresh token exist | Access token expires | Refresh succeeds, client uses new token |
| Expired refresh token | Short-TTL refresh token | Wait past both expiries | Re-authenticate or report error; do not use old token |
| Revoked refresh token | Initially valid token | Revoke on issuer before restore | Refresh fails clearly; readiness/operation per policy |
| Secret rotation | Old credential in use | Rotate secret or certificate | Fetch new value and recreate dependent clients |
| Signing key rotation | Token signed with old key | Update JWKS/key set | Verify against current keys and overlap policy |
| Issuer/audience changed | Client uses old configuration | Change policy at identity provider | Client loads new config or fails safely |
| Multiple replicas restoring together | Same checkpoint contains old token state | Simultaneously need refresh | Refresh is bounded/coalesced; no stampede or invalid session reuse |

### Testing Tokens Expiring During the Pause Interval

An integration test should follow this sequence:

1. Start the application with a test token having a short TTL, such as 30–60 seconds.
2. Call a protected API to verify the token is valid before checkpoint.
3. Record the expiry and token state without writing the token value to logs.
4. Request a checkpoint.
5. From a test controller or test harness outside the JVM, wait past the expiry.
6. Restore the process.
7. Call an authenticated API or check readiness depending on the architecture.
8. Verify that the client obtains a new token, the API call succeeds, and the old token is not resent.

The key point is that the waiting time must occur outside the checkpointed process. If a test calls `Thread.sleep()` inside the application before checkpoint, it only tests waiting while the JVM is running, not CRaC pause duration.

### Testing Refresh Failures

Do not test only the success path. Revoke the refresh token or make the token endpoint return `invalid_grant`, `401`, `429`, or `5xx` as appropriate. Verify:

- The application does not resend the expired access token as if it were still valid.
- Permanent authentication errors are not retried indefinitely.
- Transient errors are retried with bounded backoff.
- Secrets/tokens do not appear in logs or exception messages.
- Readiness remains false if the token is a required dependency.
- If the application supports degraded mode, only capabilities that do not require the token are enabled.

### Coordinating Refreshes When Multiple Replicas Restore

If 20 replicas restore together from a checkpoint containing an access token near expiration, all of them may call the token endpoint at once. Tests need to observe refresh counts, call timing, and how the application handles rotation. Single-flight refresh within each process, jitter across replicas, or a centralized token cache may be needed if the issuer and security model allow it. Do not share rotating/one-time refresh tokens across multiple replicas if the issuer does not support that model.

## 5. Testing Cache TTLs and Expired Data

TTL is the duration for which a value is considered fresh. If a cache only stores `remainingSeconds` at checkpoint time, that value can remain frozen in the heap while the process is paused. After restore, the application risks serving expired data as though the TTL had not elapsed.

Prefer storing an absolute expiration timestamp or enough metadata to determine freshness:

```java
record CacheEntry<T>(T value, Instant expiresAt, String version) { }

public final class TtlCache<T> {

    private final Clock clock;
    private final Map<String, CacheEntry<T>> entries = new ConcurrentHashMap<>();

    public TtlCache(Clock clock) {
        this.clock = clock;
    }

    public Optional<T> get(String key) {
        CacheEntry<T> entry = entries.get(key);
        if (entry == null) {
            return Optional.empty();
        }

        if (!clock.instant().isBefore(entry.expiresAt())) {
            entries.remove(key, entry);
            return Optional.empty();
        }
        return Optional.of(entry.value());
    }
}
```

The snippet illustrates expiration by `Instant`. A real cache needs to handle reloading on miss, concurrency, invalidation, and data sources. If values are sensitive or affect access control, fail closed when freshness cannot be verified.

### TTL Test Matrix

| Scenario | Restore time | Expected result |
|---|---|---|
| Cache within TTL | Before `expiresAt` | Cache may be returned if version/source is still valid |
| Cache just expired | Slightly after `expiresAt` | Cache miss and reload; do not return stale entry |
| Cache long expired | Multiple TTLs later | Invalidate; do not run unbounded concurrent reloads |
| Externally invalidated cache | Source emits invalidation event while app is paused | Detect version mismatch or reload after restore |
| Expired negative cache | Previously cached “not found” result | Retry data source after TTL |
| Cache containing permissions/roles | Role revoked during checkpoint | Do not continue authorizing based on stale entry |
| Multiple replicas missing together | All restore after TTL | Apply load limiting, single-flight, or appropriate jitter |

Tests must verify return values, source loader invocation counts, invalidation counts, and latency. Checking only that the `expiresAt` field still exists does not prove the cache behaves correctly.

### Distinguishing In-Heap Caches from External Caches

In-heap caches may be saved with the checkpoint, but their TTL and freshness need evaluation. Redis, distributed caches, database buffer caches, or CDN caches live outside the process; they have their own lifecycles. A pre-checkpoint warm-up request does not prove an external cache still remains after restore. Tests need to verify each cache layer and identify the ultimate source of truth.

## 6. Testing Expired Database Connections and Connection Pools

A database, proxy, firewall, or pooler may close idle connections while the application is paused. After restore, Java fields may still hold a `DataSource` or connection wrapper, while the underlying socket has been closed by the peer.

Do not rely solely on `Connection.isClosed()` to prove a connection is usable. Some drivers do not know the peer has closed the socket until I/O is performed. Check using a validation query or the pool's validation API, and design so failed connections are evicted from the pool and recreated.

### Database Integration Test Scenario

1. Start a test database with an idle timeout or a proxy capable of closing connections.
2. Create the pool and borrow a connection to verify queries succeed.
3. Bring the application to a state with no in-flight transactions or queries.
4. Create a checkpoint using the pool/driver's CRaC integration, or close the pool before checkpoint if managed by the application.
5. While the process is paused, wait past the idle timeout or actively restart the database/proxy.
6. Restore the application.
7. Verify that the pool creates new connections and the validation query succeeds.
8. Send a safe read/write business request to prove the real path works.
9. Check that old connections are not reused and the number of new connections stays within limits.

If the test environment does not support forcing a database timeout, you can close connections from the database/proxy side or restart the dependency container during the pause interval. Record the exact action taken to distinguish CRaC issues from unavailable-dependency issues.

### Testing Pool Recreation After Restore

If the pool must be closed before checkpoint, verify that after restore the application does not retain references to the closed pool. A facade can point to the current pool:

```java
public final class SwappableDataSource {

    private final AtomicReference<DataSource> current = new AtomicReference<>();

    public void replace(DataSource replacement) {
        current.set(Objects.requireNonNull(replacement));
    }

    public Connection getConnection() throws SQLException {
        DataSource dataSource = current.get();
        if (dataSource == null) {
            throw new SQLException("DataSource is not ready");
        }
        return dataSource.getConnection();
    }
}
```

This is an illustrative structure. When replacing the pool, you need to stop new requests, drain borrowed connections, create the new pool, run validation, atomically swap the reference, and close the old pool. In `afterRestore()`, do not enable readiness before the new pool is valid.

### When the Database Is Not Ready After Restore

Have the test database delay accepting connections or return transient errors for the first few attempts. Verify that the application:

- Retries with backoff and jitter.
- Does not open hundreds of connections concurrently.
- Does not hold requests indefinitely in queues.
- Keeps readiness false while unable to connect.
- Switches readiness to true after validation succeeds.
- Does not require restarting the entire process for transient dependency errors if the design supports reconnecting.

## 7. Testing HTTP, TLS, WebSocket, and gRPC Connections

HTTP keep-alive sockets may be closed by the server or load balancer during the pause interval. TLS certificates or client credentials may expire. WebSocket/gRPC streams may be timed out or terminated by the peer. Tests need to verify that the client can establish new connections and recover application state.

Scenarios should include:

- Server closes keep-alive connections while the process is paused.
- DNS returns a new backend address after restore.
- TLS certificate is rotated or expired.
- Token used by the HTTP client expires.
- WebSocket server closes the session and requires re-subscribing.
- gRPC server ends the stream; the client must open a new RPC and resume from the cursor.
- The first request after restore receives a transient network error and then retries successfully.

Do not test simply by calling `connect()` or checking that the client object is non-`null`. Call an actual test endpoint and verify the new peer, TLS hostname, authentication, and response. For streams, verify sequences/cursors to prove no items are dropped or duplicated outside policy.

## 8. Testing Kafka and RabbitMQ After Connection/Lease Expiration

For Kafka, the process may be evicted from the consumer group during the pause interval. After restore, the consumer must establish connections, rejoin the group, and receive new partition assignments. Tests need to verify that uncommitted records can be redelivered and handlers are idempotent.

For RabbitMQ, the broker may close connections/channels on heartbeat timeout. Unacknowledged deliveries may be requeued and redelivered. Tests need to verify that the consumer creates a new channel, re-registers on the queue, and handles duplicate messages safely.

| Broker | Action while process is paused | Assertion after restore |
|---|---|---|
| Kafka | Wait for session timeout or change group membership | New consumer joins group, receives assignment, and resumes from valid offset |
| Kafka | Send record without clear commit/confirm outcome | Outbox/retry handles per semantics, no confirmed records lost |
| RabbitMQ | Wait for heartbeat timeout or restart broker | New connection/channel created and consumer re-registers |
| RabbitMQ | Leave message unacked and close channel | Message is redelivered and consumer creates no duplicate side effects |
| Both | Restore multiple replicas concurrently | Connection/consumer limits not exceeded; identity and membership are correct |

Do not assume a single reconnect callback restores all broker semantics. Inspect offsets, acknowledgements, publisher confirms, transactions, and assignments using broker APIs/metrics.

## 9. Integrating Tests with CRaC Resource Callbacks

A Resource can coordinate token refresh and dependency reconnection after restore. Separate steps by responsibility so tests can substitute a fake provider or fake connection factory.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExternalStateResource implements Resource {

    private final TokenProvider tokenProvider;
    private final ConnectionManager connectionManager;
    private final ReadinessGate readiness;

    public ExternalStateResource(TokenProvider tokenProvider,
                                 ConnectionManager connectionManager,
                                 ReadinessGate readiness) {
        this.tokenProvider = tokenProvider;
        this.connectionManager = connectionManager;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.markNotReady();
        connectionManager.stopNewWorkAndDrain();
        connectionManager.closeForCheckpoint();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.markNotReady();
        tokenProvider.refreshAfterRestore();
        connectionManager.reconnectWithCurrentCredentials();
        connectionManager.verifyConnections();
        readiness.markReady();
    }
}
```

`TokenProvider`, `ConnectionManager`, and `ReadinessGate` are illustrative abstractions. If a library already provides CRaC integration, do not register a second callback to close/open the same resource. If multiple resources depend on each other, define callback ordering or group them into a lifecycle coordinator so tokens are refreshed before clients establish connections.

In real code, readiness is enabled only after all required dependencies are verified. If token refresh fails, do not proceed to create clients with old credentials. If database reconnection fails, keep readiness false and let bounded retry mechanisms operate per policy.

### Unit Testing Callbacks Without a Real Process Restore

Coordinator logic can be tested by calling lifecycle methods in tests with fake dependencies, or by using a separate abstraction detached from the `Resource` interface. However, manually calling `afterRestore()` is not equivalent to a real restore; it does not test the runtime, threads, sockets, file descriptors, or callback ordering performed by CRaC.

## 10. End-to-End Scenario: Checkpoint, Expire Dependencies, Restore

A valuable integration test should have a harness controlling the process from the outside. The harness launches the application, waits for readiness, requests a checkpoint, changes dependencies while the process is stopped, and then initiates restore.

```text
Test harness
   |
   +--> Start application with CRaC JDK
   |
   +--> Wait for pre-checkpoint readiness
   |
   +--> Create token/cache/DB fixtures with short TTLs
   |
   +--> Verify one successful request
   |
   +--> Request checkpoint
   |
   +--> Wait until checkpoint process has completed
   |
   +--> Outside the stopped process:
   |      - wait beyond token expiry
   |      - expire cache TTL
   |      - close DB/proxy connections
   |      - optionally rotate credentials or DNS
   |
   +--> Restore from the checkpoint
   |
   +--> Wait for afterRestore lifecycle and readiness
   |
   +--> Assert fresh token, fresh connection, cache reload
   |
   +--> Send representative business request
   |
   +--> Assert no stale credential or connection was reused
```

Specific checkpoint/restore commands depend on the CRaC JDK and container/VM environment. The harness should use tools verified in the project and inspect exit codes/logs to know that checkpoint completed before modifying dependencies. Do not assume that merely sending a signal or seeing an arbitrary log line means the checkpoint has finished writing.

### Keeping Tests Repeatable

- Create a separate namespace/database/queue for each test run.
- Attach a run ID to fixtures and logs so data does not mix across tests.
- Use a short token TTL that still leaves enough time to complete the checkpoint step.
- Wait for expiry using the actual timestamp issued by the issuer, rather than relying on the application's mock clock if the issuer uses a separate clock.
- Clean up fixtures after the test completes.
- Set an overall timeout so tests do not hang if restore or a dependency fails to respond.
- Pin the image/JDK/kernel within the same test suite.

## 11. Comprehensive Test Matrix

Maintain a matrix combining pause duration and dependency health. Not every combination needs to run on every commit; fast unit tests can run frequently, while heavy scenarios run in CI integration/nightly.

| Scenario | Token | Cache TTL | Database/network | Outcome to verify |
|---|---|---|---|---|
| Fast restore | Valid | Valid | Connection still active | Restore does not perform redundant refresh/reconnect if policy does not require it |
| Short pause | Near expiry | Valid TTL | Idle connection | Token refreshes per skew; connection validation succeeds |
| Medium pause | Expired | Just past TTL | Peer closed idle connection | New token, cache reload, new pool/client |
| Long pause | Access and refresh tokens expired | Long past TTL | Database/proxy restarted | Re-auth or fail closed; cache reload; reconnect with retry |
| Credential revoked | Revoked | Any | Dependency still active | Old token not used; readiness per policy |
| Secret rotated | Old credential no longer valid | Cache may still be within TTL | Database requires new credential | Fetch new secret and create new pool |
| DNS/backend changed | Valid or refreshable | Valid | Old endpoint closed | Resolve new endpoint and create new client |
| Dependency unavailable | Refresh endpoint or DB temporarily failing | TTL expired | Cannot connect immediately | Readiness false, bounded retry, no crash loop |
| Multi-replica restore | Same old token state | Many cache misses | Many new connections | No unbounded refresh/connection stampede |
| Clock anomaly | Expiry near boundary | TTL near boundary | Normal connection | Handle clock skew per policy; no erroneous negative duration |

## 12. Verifying Readiness and Fail-Closed Behavior

One of the most important assertions is that the application does not accept traffic too early. After restore, the JVM may already be running while tokens have not refreshed, the database has not reconnected, or consumers have not rejoined the group.

Tests need to verify:

1. Readiness starts at false during the restore phase.
2. Expired tokens are not used for requests to protected dependencies.
3. Expired cache entries are not returned as fresh data.
4. Old connections are not treated as healthy merely because the wrapper object still exists.
5. Dependency retries have timeouts/backoff and do not hold requests indefinitely.
6. Readiness turns true only after mandatory steps complete.
7. If credentials are permanently revoked, the application does not report ready and does not enter an infinite retry loop.

If some features can function when a dependency is unavailable, readiness can be based on individual capabilities or endpoints. However, you must clearly specify which capabilities are disabled; do not mark the entire service ready when core business flows cannot operate.

## 13. Testing Multiple Replicas and Anti-Stampede Behavior

A single checkpoint image can be restored into multiple replicas. All of them may contain the same saved tokens, cache entries, deadlines, and client state. When restored concurrently, they may all refresh tokens, reload caches, or open connections at the same time.

Check:

- Number of calls to the token endpoint within a time window.
- New connections/second and total connections per database user.
- Concurrent cache reloads for the same key.
- Time from restore to readiness for each replica.
- Whether jitter/backoff spreads out retries.
- Whether instance identity and leases are issued independently.
- Whether a refresh failure on one replica affects other replicas.

Do not use an `AtomicBoolean` in the heap as a cluster-wide lock. It only coordinates threads within a single process and will be cloned along with the checkpoint. For cluster-level throttling, use a coordinator, distributed lock/lease, or rollout limits in the deployment platform.

## 14. Observability and Logging in Tests

To distinguish token, TTL, and connection failures, log lifecycle milestones with clear identifiers:

- `beforeCheckpoint-start` and `beforeCheckpoint-complete`.
- `checkpoint-created` with checkpoint ID/build ID.
- `afterRestore-start`.
- `token-refresh-start`, `token-refresh-success`, or `token-refresh-failure`.
- `cache-entry-expired`, `cache-reload-start`, and `cache-reload-complete`.
- `connection-validation-failed`, `connection-recreated`, and `dependency-ready`.
- `readiness-ready`.

Useful metrics:

| Metric | What to know |
|---|---|
| Restore pause duration | Time elapsed from checkpoint mark to restore according to the chosen measurement method |
| Token refresh count/latency | Number of refreshes and issuer call duration |
| Token refresh failure by class | Distinguish expiration, revocation, configuration, and transient errors |
| Cache expired/reload count | Number of expired entries and reloads |
| Connection validation failures | Old connections that are no longer usable |
| New connection rate | Rate of opening connections after restore |
| Pool acquisition latency/timeouts | How long requests must wait for a connection |
| Reconnect attempts | Number of retries before dependency is ready |
| Restore-to-readiness duration | Actual time for the application to become able to serve |

Do not log access tokens, refresh tokens, cookies, passwords, or connection strings containing secrets. Use a safely designed token ID/hash if event correlation is needed, and avoid placing high-cardinality IDs in metric labels.

## 15. Common Testing Mistakes

### Restoring Immediately After Checkpoint Only

Tokens and connections may still be valid, so the test never exercises the refresh/reconnect path. Create a sufficiently long pause or actively revoke/close dependencies externally.

### Using `Thread.sleep()` in Unit Tests

Tests become slow and schedule-dependent. Inject `Clock` to test deadlines/TTLs deterministically; use real time only in integration tests that need to verify external systems.

### Using the Application's Mock Clock to Conclude the Token Server Expired

The issuer has its own clock. Shifting `Clock` inside the JVM does not change the token server's time. Use short-TTL tokens or a controllable test issuer.

### Checking Only `isClosed()` or Non-Null Objects

The wrapper may not yet know the peer closed the socket. Execute a validation query or real request after restore.

### Not Testing Revoked Refresh Tokens

A passing test when the refresh token is valid does not prove the application handles `invalid_grant` or rotation. Failure cases must also be tested.

### Not Testing Expired Caches

The cache object may still reside in the heap. Assertions must prove stale data is not returned and the loader is called when TTL expires.

### Enabling Readiness Before Reconnect Finishes

The health endpoint may report healthy even though the first business request fails. Check readiness and exercise a real business path.

### Sharing Fixtures or Credentials Across Tests

Parallel tests may revoke another test's token or clear its cache. Create separate namespaces, users, keys, and resources per test run.

### Testing Only a Single Replica

Fails to catch refresh stampedes, connection storms, or lease conflicts. Also run scenarios restoring multiple instances from the same image.

## 16. Implementing the Test Suite in CI

A pipeline can split tests into groups:

```text
Pull request
  - Unit tests with mocked Clock
  - Token expiry/refresh policy
  - Cache TTL/invalidation
  - Connection manager state transitions

Integration job
  - Start database, broker, and test identity provider
  - Start application with a compatible CRaC JDK
  - Real checkpoint
  - Wait for expiry/close connections/rotate credentials
  - Real restore
  - Verify token, cache, connection, and readiness

Nightly / release gate
  - Long pause and dependency restart
  - Token revoked/refresh token expired
  - DNS/TLS rotation
  - Multiple replicas restored concurrently
  - Load/connection rate and failure recovery
```

CI must pin verified CRaC JDK, kernel/runtime, and container image versions. If CI runners do not support checkpoint/restore requirements, run the integration suite on a dedicated node pool or VM; unit tests still run on every pull request.

Do not put production secrets into tests. Use mock issuers, staging credentials, and synthetic data. Checkpoint test artifacts should have short retention and restricted access because they may also contain data in the heap.

## 17. Checklist for a Complete Restore Test

- [ ] Identify which tokens, TTLs, leases, and connections can expire during the pause interval.
- [ ] Unit tests use `Clock` to verify expiration before, at, and after the expiration boundary.
- [ ] Test an expired access token while the refresh token is still valid.
- [ ] Test an expired or revoked refresh token, or a temporarily unavailable issuer.
- [ ] Test cache TTL expiration and invalidation occurring while the process is paused.
- [ ] Test the database/proxy closing idle connections and the pool creating new connections.
- [ ] Test HTTP/WebSocket/gRPC or broker reconnection according to the protocol the application uses.
- [ ] Integration tests create a real checkpoint and let time elapse outside the process.
- [ ] Restore tests run on a compatible JDK/kernel/runtime.
- [ ] Readiness is false during refresh/reconnect and turns true only after dependencies are ready.
- [ ] Test that permanent errors and transient errors follow different policies.
- [ ] Test multiple replicas to detect refresh stampedes and connection storms.
- [ ] Logs/metrics do not leak tokens, secrets, or personal data.
- [ ] Tests clean up fixtures, checkpoints, and resources after completion.

## 18. Conclusion

Testing restore after tokens, TTLs, and connections expire must verify external state outside the process that changed during the checkpoint. Use a mocked `Clock` for unit tests to check expiration and deadlines deterministically. Use integration tests with a real CRaC JDK to checkpoint, wait outside the process, expire or revoke tokens, let TTLs elapse, close connections, or change backends, and then restore.

After restore, the application needs to refresh credentials, evict expired cache entries, recreate connections, and verify dependencies with real operations. Test both successful recovery paths and refresh/reconnect failure cases; readiness must remain false when required dependencies are not yet ready. Finally, test restoring multiple replicas together to catch refresh stampedes, cache reload bursts, and connection storms. When these scenarios are automated, checkpoint images can be verified against the real lifecycle rather than merely proving that the JVM can restore memory.
