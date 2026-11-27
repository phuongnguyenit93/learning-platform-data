# Monitoring Database Load, Connection Pools, and Key Stores

An Authorization Server frequently reads and writes data at critical moments in OAuth 2.0 and OpenID Connect flows. When users log in, grant consent, exchange authorization codes, or refresh tokens, the application may access client, authorization, and consent data. Afterward, the server must sign tokens with the appropriate private key. If the database is slow, the connection pool is exhausted, or the key store is unavailable, latency and error rates across the entire token issuance flow increase.

Monitoring each component separately helps isolate whether the bottleneck lies in the application, connection pool, database, or key service. This lesson focuses on operational signals, collecting them with Spring Boot Actuator and Micrometer, configuring alerts, and following an investigation workflow when incidents occur.

## Objectives

After this lesson, you will be able to:

- Explain the metrics that reflect database load and latency in an Authorization Server.
- Distinguish database overload from connection pool exhaustion on individual application instances.
- Estimate safe connection limits when running multiple Authorization Server replicas.
- Monitor key loading, token signing, key rotation status, and KMS or HSM availability.
- Export metrics with Actuator and Micrometer, and design useful dashboards and alerts.
- Investigate incidents in order—from request, application, pool, and database to key store—without exposing tokens or secrets.

## Observability Landscape of an Authorization Server

A token issuance flow can traverse several components. For example, when handling an authorization code, the server validates the client and stored authorization, verifies required inputs, generates tokens, and signs them with a private key. During a refresh token flow, the server may read and update the authorization record. With JDBC configurations, storage services such as `JdbcRegisteredClientRepository`, `JdbcOAuth2AuthorizationService`, and `JdbcOAuth2AuthorizationConsentService` generate database load. Concrete deployments may differ, so confirm the system's actual storage components before building dashboards.

| Component | Question to Answer | Key Signals |
|---|---|---|
| Authorization Server | Are token issuance requests slow or failing? | Request rate, latency, error codes, traces |
| DataSource and pool | Can the application acquire connections on time? | Active/idle connections, pending, timeouts, acquire time |
| Database | Does the database server have enough resources and execute queries fast? | Connections, CPU, I/O, query latency, lock waits, deadlocks |
| Key store or KMS/HSM | Can the application load keys and sign tokens successfully? | Key load errors, signing latency, KMS/HSM errors, key age, rotation status |

Combine metrics, logs, and traces. Metrics reveal trends and impact scope; logs provide discrete events; traces connect a request's processing time across components. No single signal type replaces the other two.

## 1. Monitoring Database Load

### 1.1. Monitor Both Application and Database Sides

Looking only at database server CPU is not enough. A database with low CPU can still slow down the application due to lock waits, connection limits, I/O spikes, or long-running queries. Conversely, an application pool can become exhausted even when the database still has spare capacity, such as when transactions hold connections too long.

Collect at least the following metric groups:

| Group | Metrics to Watch | Meaning When Spiking Abnormally |
|---|---|---|
| Database connections | Current sessions, max connections, active connections | Multiple apps or replicas sharing the DB; risk of hitting connection limits |
| Queries | Average and p95/p99 latency, slow query count, throughput | Query or index problem; load exceeding processing capacity |
| Transactions | Open transactions, transaction duration, rolled-back transactions | Long transactions holding locks or connections too long |
| Locks | Lock wait time, deadlocks, blocked sessions | Contention updating authorization or consent, or poor transaction design |
| Resources | CPU, memory, I/O, storage capacity, and data growth rate | Database starved of resources or running out of disk |
| Data replication | Replication lag, replica status, failover errors (if applicable) | Reading from replicas may return stale data; failover can disrupt requests |

Metric names and collection methods depend on the database engine. You can use built-in monitoring from your database service, an appropriate exporter, database statistics views, or organization-provided management tools. Verify the unit and meaning of every metric before adding it to a dashboard.

### 1.2. Correlating Database Load with OAuth/OIDC Activity

The following operations typically generate read or write load:

- Looking up client configuration during client authentication or authorization request handling.
- Reading and saving authorizations when issuing authorization codes, access tokens, or refresh tokens.
- Reading and updating consents when users approve or modify granted permissions.
- Revoking authorizations or refresh tokens upon logout, revoke requests, or corresponding admin workflows.
- Background jobs such as expired-data cleanup, synchronization, or migrations if deployed.

When latency rises, correlate the timestamp and flow type with traces or application logs. For example, if refresh token p95 increases at the same time as authorization update query latency, inspect the relevant SQL query, locks, and transactions. If all flows slow down while database queries remain normal, expand the investigation to the pool, network, or key store.

Never log access tokens, refresh tokens, authorization codes, client secrets, verification codes, or sensitive authorization contents in query logs. If you need to identify queries, use query fingerprints or normalized operation names rather than logging parameter values. Restrict access to slow query logs because SQL statements and parameters can occasionally contain personal data.

### 1.3. Monitoring Query and Transaction Quality

A query with a low average duration can still have a very high p99. Monitor latency percentiles, execution counts, and rows/data read and written. When an anomalous query is detected:

1. Identify the corresponding application operation and query fingerprint.
2. Inspect the execution plan using the appropriate tool for your database engine.
3. Verify indexes, filter predicates, rows scanned, and actual rows returned.
4. Check whether transactions hold locks or connections while performing non-database work.
5. Re-measure under representative load after tuning.

Do not add indexes mechanically. Indexes can speed up reads while increasing write overhead, storage usage, and maintenance work. Base decisions on the actual workload of the client, authorization, and consent tables.

## 2. Monitoring and Configuring Connection Pools

### 2.1. What Problem Does a Pool Solve?

Opening a new database connection per request is expensive in time and resources. A connection pool keeps a ready set of connections that requests borrow and return. In many Spring Boot applications, HikariCP is the default pool when present on the classpath and configured appropriately.

Pools have finite capacity. When every connection is in use, new requests must wait. If wait time exceeds `connectionTimeout`, the pool raises a connection acquisition error. This can happen even when the database can still handle more queries, for example because the application holds connections for too long.

Common HikariCP metrics include:

| Metric | How to Read |
|---|---|
| `hikaricp.connections.active` | Connections currently in use by the application |
| `hikaricp.connections.idle` | Idle connections waiting in the pool |
| `hikaricp.connections.max` | Configured maximum pool size |
| `hikaricp.connections.min` | Configured minimum idle connections |
| `hikaricp.connections.pending` | Threads currently waiting to acquire a connection |
| `hikaricp.connections.timeout` | Count of failed connection acquisitions due to timeout |
| `hikaricp.connections.acquire` | Time spent waiting to acquire a connection |
| `hikaricp.connections.usage` | Duration a connection is held before returning to the pool |

Exported names and formats may vary by Micrometer, HikariCP, and registry version. Verify the actual metric names at the metrics endpoint or in your monitoring system before writing dashboard queries.

### 2.2. Reading Signs of Pool Contention

A healthy pool usually shows `active` fluctuating with load while `pending` stays near zero most of the time. Investigate when one or more of the following signs appear:

- `active` frequently approaches `max`.
- `pending` rises and stays elevated across multiple sampling intervals.
- `acquire` time increases alongside request p95/p99 latency.
- Timeout counters increment.
- `usage` duration becomes unusually long, indicating connections are held too long.

A brief spike may simply reflect a traffic burst. Correlate with request rate, query duration, and transaction duration. If `active` is high while the database is idle, look for long-running transactions, synchronous remote calls made while holding a connection, or code paths failing to release connections properly. If `active` is high alongside database CPU, I/O, and query latency, the database may be the true bottleneck.

### 2.3. Sizing the Connection Pool

Do not pick `maximumPoolSize` solely based on application CPU count or keep increasing it whenever `pending` appears. Every additional connection consumes resources the database must maintain. Across multiple replicas, total connections can exceed the database limit even when each instance's pool looks small.

Estimate total application connections using the formula:

\[
C_{app}=N_{replica}\times P_{max}
\]

Where `N_replica` is the maximum number of replicas that can run during scaling or rolling deployments, and `P_max` is `maximumPoolSize` per replica. Then add connections from workers, other services, migrations, administrative tools, and monitoring. The expected total must stay below the database limit while leaving headroom for failover and operational tasks.

You can use Little's Law for a rough initial estimate of required concurrent connections:

\[
L\approx \lambda\times W
\]

Where `λ` is database operations per second and `W` is the average time a single operation holds a connection, in seconds. This is only a starting estimate: long-tail workloads, multi-query transactions, and traffic spikes must be validated through load testing.

For example, a system with up to 6 replicas and a max pool of 12 connections per replica can open up to 72 application connections. If the database allows 100 connections, 72 is not the entire load: other services, migrations, and admin sessions share that same limit. During rolling deployments, old and new replicas can coexist temporarily, so account for temporary replica counts as well.

### 2.4. Illustrative Pool Configuration

Example HikariCP configuration in `application.yml`:

```yaml
spring:
  datasource:
    hikari:
      pool-name: authorization-server
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
```

These numbers only illustrate syntax, not an optimal configuration for every environment. Choose `maximum-pool-size` based on database limits and replica count; set `max-lifetime` lower than the maximum connection lifetime enforced by the database or network infrastructure; and choose timeouts aligned with your request latency budget. `minimum-idle` affects how many connections are kept warm. In some configurations, `idle-timeout` does not behave as expected if the pool is kept at a fixed size.

Do not increase `connection-timeout` to hide pool exhaustion. Long timeouts cause requests to hold threads longer and build larger queues. First determine whether connections are held by slow queries, locks, long transactions, or misconfigured pools.

### 2.5. Detecting Connections Held Too Long

HikariCP provides `leak-detection-threshold` to log a warning when a connection is borrowed longer than the configured threshold. This is a diagnostic tool, not an automatic leak fixer. Enable it only during investigation and set the threshold based on normal processing times; too low a threshold creates noisy logs. When a warning fires, inspect the stack trace where the connection was borrowed and ensure transactions or JDBC resources are released properly.

HTTP calls, KMS/HSM calls, file writes, or heavy computation should stay outside database transactions whenever business rules allow. Keeping a transaction open while waiting on a remote service ties up the connection and increases the risk of pool exhaustion. Design short, explicit transaction boundaries and verify business consistency when splitting operations.

## 3. Monitoring Key Stores and Token Signing

### 3.1. What to Observe

An Authorization Server needs suitable keys to sign tokens and publish public keys for consumers to verify signatures. Keys may be loaded from JKS/PKCS12, protected files, a secret manager, KMS, or HSM. Storage choice dictates how signals are collected, but the core operational questions remain the same:

- Can the application load keys at startup and during configuration refreshes?
- Do active keys have the right purpose, algorithm, and validity state?
- Are signing operations succeeding within the latency budget?
- Is KMS/HSM responsive, or experiencing quota limits or throttling?
- Are keys approaching expiration or scheduled rotation?
- Does the public JWKS contain the keys needed to verify still-valid tokens?

Consider tracking the following metrics or events:

| Group | Signals |
|---|---|
| Key loading | Load successes/failures, load duration, last successful load timestamp |
| Token signing | Signing count, p95/p99 signing latency, signing failures |
| KMS/HSM | Request latency, error rate, timeouts, throttling, quota, and queue depth if supported by provider |
| Key lifecycle | Creation time, activation time, retirement time, and expiration time |
| JWKS | Last updated timestamp, count of published public keys, and presence of currently referenced `kid` values |

Never place private keys, keystore passwords, secrets, tokens, or private JWK material into metrics, logs, traces, or dashboard labels. Never use client ID, subject, token ID, or authorization ID as metric labels because they create high cardinality and risk leaking data. For `kid`, use it as a label only if the key count is bounded and security policy allows it; key status can often be tracked via administrative events or aggregate metrics instead.

### 3.2. Monitoring Remote Key Services

When signing tokens via KMS/HSM, token issuance latency includes the call to the key service. Monitor provider latency, timeouts, and errors separately to distinguish network errors, authentication errors, quotas, throttling, and hardware errors. Use finite timeouts and bounded retry policies; uncontrolled retries can amplify an incident when KMS/HSM is overloaded.

If keys are cached or loaded into memory, observe refresh timestamps and how the application behaves when the key source is temporarily unavailable. Never fail over automatically to an unapproved fallback key. Replacement keys must follow key management procedures and be properly published.

### 3.3. Observing Key Lifecycle and Rotation

Key rotation requires coordination between the token signer and the resource servers or clients verifying tokens. A typical workflow includes:

1. Generate a new key in an access-controlled key store.
2. Publish the public key with a new `kid` on the JWKS endpoint.
3. Confirm JWKS distribution and allow enough time for consumer caches to refresh.
4. Switch the Authorization Server to sign with the new key.
5. Keep publishing the old key for the window required to verify tokens already issued with it.
6. Remove the old key only after related tokens have expired and operational policy permits.

Dashboards should show the active key, next key, expiration dates, last JWKS publish time, and the outcome of each rotation step. Alert far enough ahead of expiration for operations teams to act, rather than waiting until token signing requests start failing.

Do not delete the old key immediately after switching the signing key. Resource servers may still need the old public key to verify unexpired access tokens or ID tokens. Key retention duration must account for the longest token lifetime, JWKS sync delay, consumer caching, and internal policies.

### 3.4. Key Store Health Checks

Health checks should verify that the application can access the key source in a lightweight, safe way. For KMS/HSM, use a status-check API or a provider-recommended check operation. Avoid executing an expensive signing operation on every health endpoint call. Avoid returning configuration details, internal addresses, or secret metadata in health responses.

Distinguish liveness from readiness. Liveness answers whether the process is still alive; readiness answers whether the instance is eligible to receive traffic. If the database or key store is a hard dependency for issuing tokens, readiness can reflect that dependency's state. However, avoid tying a shared database outage to every replica's liveness probe: doing so can cause the orchestrator to continuously restart instances during a database incident, worsening the outage.

## 4. Collecting Metrics with Spring Boot Actuator and Micrometer

### 4.1. Enabling Observability Endpoints

For a Spring Boot application with Actuator and the Prometheus registry, you can use the following illustrative configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  metrics:
    tags:
      application: authorization-server
```

Add Actuator and registry dependencies matching your build system. Example with Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

The `/actuator/metrics` endpoint helps explore metrics exposed by the application; `/actuator/prometheus` exports data in Prometheus format once the corresponding registry is installed. Actual paths may vary based on `management.endpoints.web.base-path` and deployment configuration.

Expose management endpoints only on internal networks or behind appropriate authentication and authorization. Never expose `env`, `configprops`, `heapdump`, `logfile`, or sensitive endpoints publicly. Even `metrics` and `prometheus` can reveal system structure, pool names, or internal labels; restrict access origins accordingly. `show-details: when-authorized` does not replace endpoint access control configuration.

### 4.2. Verifying Actual Metrics

After starting the application in an appropriate environment:

1. Check health and readiness status.
2. Inspect the metric list or query metrics by name to confirm DataSource instrumentation is active.
3. Verify pool metrics change when generating representative read/write load.
4. Confirm the registry exports the histograms or timers needed for p95/p99.
5. Check that labels contain only low-cardinality dimensions such as application, instance, pool, or environment.

Spring Boot and Micrometer may provide JVM, HTTP server, DataSource, and pool metrics automatically depending on dependencies, versions, and configuration. Do not assume every metric exists merely because Actuator was added. If metrics are missing, inspect the registry, binders, DataSource type, export settings, and library versions.

### 4.3. Adding Metrics for Signing Operations

Built-in metrics usually do not fully capture an Authorization Server's signing activity. You can measure duration and failures around the actual signing operation using Micrometer. The example below illustrates a generic helper; place it at the boundary where the application invokes the signer or KMS/HSM:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;
import org.springframework.stereotype.Component;

@Component
public class SigningMetrics {
    private final MeterRegistry registry;
    private final Timer signingTimer;
    private final Counter signingFailures;

    public SigningMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.signingTimer = Timer.builder("oauth2.signing.duration")
                .description("Time spent performing token signing operations")
                .publishPercentileHistogram()
                .register(registry);
        this.signingFailures = Counter.builder("oauth2.signing.failures")
                .description("Number of failed token signing operations")
                .register(registry);
    }

    public <T> T record(Callable<T> operation) throws Exception {
        Timer.Sample sample = Timer.start(registry);
        try {
            return operation.call();
        } catch (Exception exception) {
            signingFailures.increment();
            throw exception;
        } finally {
            sample.stop(signingTimer);
        }
    }
}
```

Usage example:

```java
String signedValue = signingMetrics.record(() -> signer.sign(payload));
```

`signer.sign(payload)` represents your application's signing API, not a fixed Spring Authorization Server API. Adjust the return type and exception handling to match the actual signer. If the application needs to count `Error` throwables as well, consider a dedicated measurement policy; never catch all errors and continue as if signing succeeded.

Do not add per-request variable labels to timers or counters. If you need to distinguish algorithm families or providers, use only a bounded, controlled set of labels. Never log payloads, tokens, or key material while measuring duration.

## 5. Dashboards and Alerts

### 5.1. Dashboard Layout

Operational dashboards should visualize the relationship between requests and dependencies:

| Section | Charts or Tables | Purpose |
|---|---|---|
| OAuth/OIDC flows | Request rate, p95/p99, error rate by endpoint or operation group | Identify when impact starts and its scope |
| Per-instance pool | Active, idle, max, pending, timeouts, acquire latency, usage duration | Detect pool exhaustion and anomalous instances |
| Database | Connections, CPU, I/O, query latency, lock waits, deadlocks, disk capacity | Determine whether the database is the bottleneck |
| Key store | Signing latency, signing failures, KMS/HSM latency and error rate | Detect signing failures or remote dependency issues |
| Key lifecycle | Active key, expiration time, rotation schedule, and JWKS updates | Prevent incidents from expired keys or incomplete distribution |

Align request latency, pool pending, database latency, and signing latency on the same time axis. When curves rise simultaneously, operations teams can quickly narrow down the offending component.

### 5.2. Prometheus Query Examples

Prometheus metric names are typically converted from Micrometer names, though they can vary by version and configuration. The expressions below are templates to adjust after verifying actual metric names in your live environment.

Pool utilization ratio per pool:

```promql
hikaricp_connections_active
  / clamp_min(hikaricp_connections_max, 1)
```

Connection acquisition timeouts per second:

```promql
sum by (application, instance) (
  rate(hikaricp_connections_timeout_total[5m])
)
```

p95 signing latency, if the timer publishes histograms:

```promql
histogram_quantile(
  0.95,
  sum by (le, application) (
    rate(oauth2_signing_duration_seconds_bucket[5m])
  )
)
```

Signing failure rate:

```promql
sum by (application) (
  rate(oauth2_signing_failures_total[5m])
)
```

Verify the units and names exported by the registry before using these expressions. Some metrics are gauges while others are counters or histograms; applying `rate()` to the wrong metric type produces incorrect results.

### 5.3. Designing Alerts

A meaningful pool alert usually combines multiple signals: sustained high active/max ratio, pending greater than zero, and rising acquire latency. Timeout alerts can fire as soon as errors appear, grouped by application and instance to determine scope. Database alerts should combine query latency or lock waits with resource signals. Key store alerts must cover signing failures, KMS/HSM timeouts, and upcoming key expirations.

Do not use a single static threshold for every environment. Establish baselines from normal load, peak hours, high-traffic campaigns, and load tests. Set a sustained evaluation duration to avoid paging on brief spikes; for security errors or signing failures that halt token issuance, faster alerting may be appropriate. Every alert should have an owner, severity, linked dashboard, and first response step.

Example alert conditions:

- Pool pending remains above zero and p95 acquire time exceeds the set budget.
- Connection timeout count rises alongside database-related request errors.
- Query latency or lock waits remain elevated while token issuance/refresh requests slow down.
- KMS/HSM timeouts, throttling, or signing failures exceed operational thresholds.
- Unable to load keys after deployment or configuration refresh.
- Active key approaches expiration without a published and verified next key.
- JWKS has not updated according to the scheduled rotation timeline.

## 6. Incident Investigation Workflow

When users or monitoring systems report token issuance failures, follow this sequence to narrow the scope:

1. **Assess impact.** Check affected endpoints or grant groups, error rate, p95/p99, start time, and number of failing instances. Never include real tokens in incident reports.
2. **Inspect per-instance pools.** Compare active, max, idle, pending, acquire latency, and timeouts. If only one instance is anomalous, check that instance's logs and traces.
3. **Inspect the database.** Compare connections, query latency, lock waits, deadlocks, CPU, and I/O over the same timeframe. Identify involved queries or transactions.
4. **Inspect the key store.** Check key loading errors, signing latency, KMS/HSM timeouts or throttling, active key status, and the most recent JWKS update.
5. **Correlate traces.** Determine whether time is spent in queries, waiting for connections, calling the key service, or executing application logic.
6. **Recover safely.** Apply appropriate remediation such as load shedding, query optimization, transaction tuning, or key service recovery per approved runbooks. Record the impact and verify error rates, latency, and dependency metrics return to normal.

### Example: Rising Refresh Token Latency

Suppose token endpoint p95 jumps from 150 ms to 2 seconds. Dashboards show pool active near max with rising pending; the database shows high lock waits while signing latency remains steady. These signals point the investigation toward transactions and queries updating authorizations. Inspect traces to identify operations holding connections too long, then inspect execution plans and relevant locks. Immediately increasing the pool size may push even more connections onto the database before the lock contention is resolved.

### Example: Token Signing Errors After Deployment

Suppose the database and pool look healthy, yet token issuance error rates spike right after a deployment. Signing failures climb while application logs report that the corresponding key cannot be found. Check key source configuration, secret manager/KMS permissions, selected `kid`, and published JWKS contents. If keys were changed, verify that resource servers can fetch the new public key and that the old key remains retained for the required transition window.

## 7. Pre-Production Verification

Test dashboards and alerts under representative load, and simulate controlled failure scenarios in a staging environment:

- Increase token issuance and refresh token request rates to observe pool active, pending, and query latency.
- Slow down a test query or introduce a controlled lock to verify traces and database alerts.
- Constrain the pool in a test environment to verify timeouts and confirm runbooks identify the cause.
- Simulate slow KMS/HSM, timeouts, or rejected requests to verify signing metrics and error behavior.
- Execute a full key rotation procedure, inspect JWKS, and verify tokens signed by both old and new keys during the overlap window.
- Perform restarts or rolling deployments to verify total connection counts stay below the database limit.

Never artificially overload or deliberately break production databases/KMS/HSM to test alerts. Tests must have explicit load limits, an owner, a schedule window, and a clear rollback procedure.

## 8. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Monitoring only database CPU | Misses locks, slow queries, and pool exhaustion | Combine application, pool, and database metrics |
| Increasing `maximum-pool-size` whenever pending rises | Can overload the database further | Measure connection hold time, query latency, and cap total connections |
| Looking only at average latency | Misses slow tail requests in p95/p99 | Track histograms and percentiles |
| Holding transactions during remote service calls | Ties up connections longer, increasing pool exhaustion risk | Shorten transactions and define explicit operation boundaries |
| Checking keys only at startup | Misses failures during key refresh or KMS/HSM calls | Continuously monitor key loading, signing, and key lifecycle |
| Deleting old keys immediately on rotation | Still-valid tokens may fail verification | Retain old public keys per token lifetime and cache policy |
| Putting tokens or client IDs in metric labels | Cardinality explosion and data leaks | Use small, controlled label value sets |
| Exposing management endpoints publicly | Leaks operational and configuration details | Restrict network access, authentication, and authorization |

## Conclusion

Monitoring database load, connection pools, and key stores gives operations teams visibility into the direct dependencies of token issuance. Measure request latency, pool status, query performance, and signing operations together, then correlate them on a shared timeline. Size pools based on total replica count and database limits, and monitor both signing keys and public key distribution throughout key rotation. When metrics, logs, traces, and runbooks are connected, incident detection and resolution become faster and evidence-based.
