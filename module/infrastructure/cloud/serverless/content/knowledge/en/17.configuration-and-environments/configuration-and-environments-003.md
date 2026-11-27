# Environment Variables, Dynamic Configuration, and Configuration Caching

A Java serverless function can run across multiple environments such as development, staging, and production, while scaling out into many execution environments as traffic increases. Each instance needs service endpoints, processing limits, feature flags, and operational parameters. Hardcoding these values in source code ties every configuration change to a build and deployment, while easily introducing differences across environments.

A sound design separates **deployment-bound configuration**, **configuration that can change while the application is running**, and **secrets**. Environment variables fit values tied to a deployment or revision. Dynamic configuration fits feature flags, thresholds, and policies that must change without redeploying. Secrets must be managed by a dedicated system with access control and rotation processes. Because functions can scale out to many instances, configuration caches must define TTLs, staleness limits, and behavior when the configuration source is unavailable.

This lesson focuses on organizing configuration for Java serverless, reading and validating environment variables, loading dynamic configuration, caching safely across invocations, and operating configuration changes without losing control of the system.

## 1. Three types of configuration data

Not every value an application reads at startup has the same lifecycle. Classify values before choosing where to store them.

| Type | Examples | Appropriate management place | How it changes |
|---|---|---|---|
| Deployment configuration | Region, queue name, service URL, port, expected concurrency level | Environment variables or revision/deployment configuration | Usually changed via deploy/configuration update |
| Dynamic configuration | Feature flags, business thresholds, per-tenant limits, rollout percentages | Dynamic configuration service or database with controlled access | Can be updated while the function is running |
| Secret | API key, database password, signing key, access token | Secret manager or platform built-in secret mechanism | Rotated per security process |

For example:

- `PAYMENT_API_BASE_URL` is deployment configuration because the endpoint usually differs between staging and production.
- `ENABLE_NEW_CHECKOUT` is a feature flag that may need to be toggled without deploying.
- `MAX_CART_ITEMS` can be dynamic configuration if operators need to adjust the limit frequently.
- `PAYMENT_API_SECRET` is a secret and must be protected and rotated.

A given value may fall into a different category depending on requirements. For example, a request limit fixed per revision can be an environment variable; a limit that must adjust immediately under load can be dynamic config. Base the decision on change frequency, criticality, consistency needs, and tolerance for update lag.

## 2. Environment variables in serverless

Environment variables are name/value pairs injected into the process by the platform when initializing the runtime. Java reads them via `System.getenv()`.

For example:

```text
APP_ENV=production
PAYMENT_API_BASE_URL=https://payments.internal
HTTP_CONNECT_TIMEOUT_MS=1500
HTTP_REQUEST_TIMEOUT_MS=4000
MAX_BATCH_SIZE=100
ENABLE_VERBOSE_LOGGING=false
```

In Java:

```java
String environment = System.getenv("APP_ENV");
String paymentUrl = System.getenv("PAYMENT_API_BASE_URL");
```

Environment variables fit configuration that does not change continuously. On many platforms, changing environment variables creates a new revision or configuration version; existing running instances may keep using the old configuration until replaced. Never assume editing an environment variable in the console immediately updates already-running processes.

### Key characteristics to remember

- Values are typically set at the function, service, deployment, or revision level.
- Each environment can have its own set of values.
- Environment variables can be read at init time and stored in an immutable configuration object.
- Each execution environment has its own copy; environment variables are not a shared, synchronized config store.
- Do not use environment variables to pass large payloads or continuously changing lists.
- Never log all environment variables, as they may contain secrets or internal details.

### Naming conventions

Use clear, consistent names with units:

- `HTTP_CONNECT_TIMEOUT_MS` instead of `TIMEOUT`.
- `MAX_RECORDS_PER_BATCH` instead of `LIMIT`.
- `FEATURE_CHECKOUT_V2` instead of `NEW_FEATURE`.
- `PAYMENT_API_BASE_URL` instead of `URL`.

If the same parameter is used across modules, standardize its naming and definition. Numeric values should include units in the name or documentation to avoid confusing seconds with milliseconds.

## 3. Creating typed configuration in Java

Avoid scattering `System.getenv()` calls across many classes. Read configuration in one place, convert it into appropriate data types, and validate it immediately at initialization.

Example using a Java record:

```java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record AppConfig(
        String environment,
        URI paymentApiBaseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        int maxBatchSize,
        boolean verboseLogging) {

    public static AppConfig fromEnvironment(
            Map<String, String> env) {

        String environment = required(env, "APP_ENV");
        URI paymentUrl = URI.create(
                required(env, "PAYMENT_API_BASE_URL"));

        int connectMs = integer(
                env, "HTTP_CONNECT_TIMEOUT_MS", 1500);
        int requestMs = integer(
                env, "HTTP_REQUEST_TIMEOUT_MS", 4000);
        int batchSize = integer(
                env, "MAX_BATCH_SIZE", 100);
        boolean verbose = bool(
                env, "ENABLE_VERBOSE_LOGGING", false);

        if (connectMs <= 0 || requestMs <= 0) {
            throw new IllegalArgumentException(
                    "HTTP timeouts must be positive");
        }
        if (requestMs < connectMs) {
            throw new IllegalArgumentException(
                    "Request timeout must not be shorter than connect timeout");
        }
        if (batchSize < 1 || batchSize > 500) {
            throw new IllegalArgumentException(
                    "MAX_BATCH_SIZE must be between 1 and 500");
        }
        if (!"https".equalsIgnoreCase(paymentUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "Payment API must use HTTPS");
        }

        return new AppConfig(
                environment,
                paymentUrl,
                Duration.ofMillis(connectMs),
                Duration.ofMillis(requestMs),
                batchSize,
                verbose);
    }

    private static String required(
            Map<String, String> env,
            String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }
        return value.trim();
    }

    private static int integer(
            Map<String, String> env,
            String key,
            int defaultValue) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Invalid integer configuration: " + key, ex);
        }
    }

    private static boolean bool(
            Map<String, String> env,
            String key,
            boolean defaultValue) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return defaultValue;
        }
        if ("true".equalsIgnoreCase(value.trim())) {
            return true;
        }
        if ("false".equalsIgnoreCase(value.trim())) {
            return false;
        }
        throw new IllegalArgumentException(
                "Invalid boolean configuration: " + key);
    }
}
```

Initialize once during the init phase:

```java
private static final AppConfig CONFIG =
        AppConfig.fromEnvironment(System.getenv());
```

This lets classes receive configuration through constructors instead of reading environment variables themselves. If a required setting is missing or invalid, the application fails early with a clear message instead of running for a while and failing on a random request.

Never include secret values in exception messages. In the example, errors only state the configuration key name without printing the value.

### Intentional default values

Defaults are suitable for parameters with safe, well-understood values, such as toggling verbose logging or a small default batch size. Do not assign defaults to essential configuration such as payment endpoints, data buckets, or regions if omitting them could route data to the wrong place.

For security parameters, defaults must fail closed. For example, if authentication mode cannot be determined, never default to allowing public access.

## 4. Separating configuration by environment

Development, staging, and production usually differ in endpoints, quotas, secrets, and operational policies. Maintain configuration sets that can be compared and reviewed.

Example configuration table:

| Key | Development | Staging | Production |
|---|---|---|---|
| APP_ENV | development | staging | production |
| PAYMENT_API_BASE_URL | sandbox endpoint | staging endpoint | production endpoint |
| HTTP_REQUEST_TIMEOUT_MS | 5000 | 4000 | 3000 |
| MAX_BATCH_SIZE | 20 | 50 | 100 |
| ENABLE_CHECKOUT_V2 | true | true | false |
| LOG_LEVEL | DEBUG | INFO | INFO |

Do not copy the production secret set into staging or development. Use separate secrets for each environment and restrict read permissions.

Configuration should be managed as reviewed code or deployment manifests. However, manifests must only hold non-sensitive values or secret references—never plaintext secrets. Avoid manual out-of-band edits in production, as they create configuration drift between the environment and the source of truth.

## 5. What is dynamic configuration?

Dynamic configuration is configuration data that the application loads from an external source while the process is running. This allows operators to adjust certain behaviors without rebuilding and redeploying the function.

Examples:

- Enabling a feature flag for a group of users.
- Changing the maximum number of items in a request.
- Adjusting the rollout percentage of a feature.
- Disabling an integration experiencing an outage.
- Adjusting alert thresholds or retry policies.
- Tuning processing levels per tenant.

Dynamic config sources can include:

- The cloud provider's configuration management service.
- A feature flag service.
- A database or key-value store with explicit schema and update permissions.
- An internal API serving versioned configuration snapshots.

Dynamic configuration should not replace every environment variable. Values that determine where the function runs, identity, access permissions, networking, or resource bindings should generally stay bound to the deployment so they can be reviewed and rolled out under control.

### Distinguishing dynamic config from secrets

Dynamic config typically holds operational parameters, not credentials. Secrets need dedicated lifecycle management, encryption, auditing, rotation, and authorization.

Do not put passwords, private keys, or access tokens into a feature flag table just because the application already has a client reading that table. Use a secret manager or the platform's built-in secret mechanism.

## 6. Designing schemas for dynamic configuration

Dynamic config should have an explicit schema and version. Avoid storing arbitrary JSON that each service interprets differently.

Example configuration snapshot:

```json
{
  "version": 42,
  "updatedAt": "2026-11-17T10:15:00Z",
  "features": {
    "checkoutV2": true,
    "asyncReceipt": false
  },
  "limits": {
    "maxCartItems": 50,
    "maxRequestsPerMinute": 120
  }
}
```

A solid schema should define:

- The name and data type of each field.
- Required vs. optional fields.
- Whether default values are safe.
- Valid ranges for numbers and durations.
- Schema version and backward-compatibility rules.
- Who is authorized to modify each configuration group.
- Effective timing and rollback procedures.
- How to handle fields unrecognized by an older application version.

Use immutable objects after parsing and validation. Never let multiple threads mutate a configuration `Map` being read by invocations. On each refresh, create a new snapshot and swap the reference atomically.

### Versioning and rollback

Every update should have a monotonically increasing version or revision ID. During an incident, operators can revert to a prior version and verify which instances received which version.

Do not rely solely on timestamps to compare update order, as system clocks can drift. Monotonic versions or immutable IDs issued by the config service are usually easier to control.

## 7. Caching configuration in serverless

If every invocation calls the config service to fetch dynamic config, the system generates excessive network requests, increases latency, and depends tightly on the config service's availability. Caching reduces load and improves speed.

However, an in-memory function cache is local in scope:

- Each execution environment has its own cache.
- During scale-out, multiple instances may hold different versions for a period of time.
- When an instance stops, its cache is lost.
- When snapshot/restore is used, cached data in the heap may be cloned or already expired.
- A refresh in instance A does not automatically update the cache in instance B.

Therefore, the cache is not the source of truth. It is a time-bounded copy of the config service.

### TTL and staleness limits

TTL defines how long a snapshot is considered fresh. For example, a 30-second TTL means an instance can continue using loaded configuration for up to 30 seconds before needing a refresh.

Distinguish between:

- **Fresh TTL:** how long a snapshot can be used without refreshing.
- **Maximum stale age:** the maximum duration an old snapshot may still be used when the configuration source fails.
- **Refresh timeout:** the maximum wait time when calling the config service.
- **Refresh interval:** the interval between refreshes if an active polling mechanism is used.

Never allow unbounded stale fallback. If stale configuration can create security risks or business errors, fail closed once the staleness limit is exceeded.

## 8. Example dynamic config cache in Java

The following example uses an abstract provider to load configuration. The provider can be implemented via a cloud config service SDK, an internal HTTP API, or a database.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class DynamicConfigCache {

    public interface Provider {
        DynamicSettings fetch(Duration timeout) throws Exception;
    }

    public record DynamicSettings(
            long version,
            boolean checkoutV2Enabled,
            int maxCartItems) {

        public DynamicSettings {
            if (version < 1) {
                throw new IllegalArgumentException("Invalid config version");
            }
            if (maxCartItems < 1 || maxCartItems > 500) {
                throw new IllegalArgumentException("Invalid maxCartItems");
            }
        }
    }

    private record Snapshot(
            DynamicSettings settings,
            Instant loadedAt,
            Instant expiresAt,
            Instant staleUntil) {
    }

    private final Provider provider;
    private final Clock clock;
    private final Duration ttl;
    private final Duration maxStale;
    private final Duration refreshTimeout;

    private volatile Snapshot current;

    public DynamicConfigCache(
            Provider provider,
            Clock clock,
            Duration ttl,
            Duration maxStale,
            Duration refreshTimeout) {
        this.provider = Objects.requireNonNull(provider);
        this.clock = Objects.requireNonNull(clock);
        this.ttl = Objects.requireNonNull(ttl);
        this.maxStale = Objects.requireNonNull(maxStale);
        this.refreshTimeout = Objects.requireNonNull(refreshTimeout);

        if (ttl.isNegative() || ttl.isZero()
                || maxStale.isNegative()
                || refreshTimeout.isNegative()
                || refreshTimeout.isZero()) {
            throw new IllegalArgumentException("Invalid cache durations");
        }
    }

    public DynamicSettings get() {
        Instant now = clock.instant();
        Snapshot snapshot = current;

        if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
            return snapshot.settings();
        }

        synchronized (this) {
            now = clock.instant();
            snapshot = current;

            if (snapshot != null && now.isBefore(snapshot.expiresAt())) {
                return snapshot.settings();
            }

            try {
                // Provider must enforce network timeout <= refreshTimeout.
                DynamicSettings fresh = provider.fetch(refreshTimeout);
                Instant loadedAt = clock.instant();

                Snapshot replacement = new Snapshot(
                        fresh,
                        loadedAt,
                        loadedAt.plus(ttl),
                        loadedAt.plus(ttl).plus(maxStale));

                current = replacement;
                return fresh;
            } catch (Exception refreshError) {
                if (snapshot != null
                        && clock.instant().isBefore(snapshot.staleUntil())) {
                    return snapshot.settings();
                }
                throw new IllegalStateException(
                        "Dynamic configuration is unavailable",
                        refreshError);
            }
        }
    }
}
```

This example illustrates synchronous, single-flight caching within a single process: threads on the same instance do not simultaneously fetch multiple copies when the TTL expires. The provider must configure its own connect/request timeouts within the `refreshTimeout` budget; in a production implementation, pass this timeout into the provider rather than merely storing it in the cache.

Key points:

- `Snapshot` is an immutable record; refreshing replaces the entire reference with a new snapshot.
- `volatile` ensures other threads observe the replaced snapshot.
- Double-checking inside `synchronized` prevents multiple threads from refreshing concurrently.
- Stale fallback is permitted only until `staleUntil`.
- If configuration has never been loaded and the provider fails, the cache has no fallback data.
- Never log configuration contents or secrets when a refresh fails.

This snippet does not spawn background threads. In serverless, background threads may not run continuously between invocations or before an instance is reclaimed. On-demand refresh with an explicit timeout is usually more predictable; if using background refresh, verify lifecycle behavior and ensure requests still have a valid execution path if a refresh has not completed.

## 9. Preventing refresh stampedes and managing latency

When a TTL expires, many requests may arrive at once. If every thread calls the config service, a single instance can create a request burst. When many execution environments expire their TTLs around the same time, the aggregate burst is even larger.

Mitigations include:

- Single-flight: only one thread per process performs the refresh, while other threads use the old snapshot or wait per policy.
- TTL jitter: add a small random offset to expiration times so instances do not all refresh simultaneously.
- Refresh timeout: bound how long to wait on the configuration source.
- Backoff: when a refresh fails, do not retry on every single request.
- Stale-while-revalidate: continue serving the old snapshot within allowed limits while a refresh is in progress.
- Controlled pre-warming: load configuration during init if the function needs config before the first invocation.

The synchronous cache above makes the first request after TTL expiration wait for the refresh. If that latency is unacceptable, implement stale-while-revalidate with a lifecycle-managed refresh task. Do not use unsupported background executors or assume the instance will stay alive long enough for a background refresh to finish.

Jitter only reduces the chance that many instances refresh at the exact same moment; it does not provide global consistency. If changes must take effect nearly immediately, use an appropriate push/invalidation mechanism or version check, while accounting for instances that may briefly lag behind.

## 10. Policies when the config service is unavailable

The config service is itself a dependency. It can time out, return errors, hit quota limits, or become unreachable over the network.

Define behavior according to the criticality of each setting:

| Config type | Behavior when refresh fails |
|---|---|
| Non-sensitive feature flag | Can use the stale snapshot within max stale age |
| Load limits or quotas | Use stale values briefly if safe; otherwise apply conservative defaults or reject |
| Security/authorization policies | Do not use stale config indefinitely; fail closed once max stale age is exceeded |
| Endpoints or resource bindings | Usually require valid deployment config; do not guess fallback endpoints |
| Secrets or credentials | Refresh via secret manager/provider; never use expired or revoked secrets |

Do not apply a single fallback across every key. For each field, decide:

- How long can an old value be used at most?
- Is a default safe?
- When no valid value exists, which requests should be rejected?
- Should an alert fire immediately when refresh fails?
- Who is authorized to roll back or modify the config?

If the cache has never held a valid snapshot, it cannot fabricate data. Fail clearly or use an approved, tested default.

## 11. Secrets and rotation

Secrets must be managed separately from regular configuration. Cloud platforms typically offer a secret manager or deployment-time secret references.

Principles:

- Never commit secrets to Git or package them in JARs/container images.
- Never place secrets into a dynamic config store merely because the application already has a refresh mechanism for it.
- Grant secret read permissions to the runtime service account scoped to specific secrets.
- Never log secret values, tokens, Authorization headers, or connection strings containing passwords.
- Separate secrets across development, staging, and production.
- Monitor audit logs and rotation history.
- Handle rotation with an overlap window if providers need to accept both old and new keys concurrently.

### Inject at deploy time or read at runtime?

Both approaches involve trade-offs:

**Injecting via secret reference/environment or volume:** simple and reduces calls to the secret manager. However, values may be tied to a revision or updated per platform-specific semantics. Know when instances receive the new secret and whether a redeployment is needed.

**Reading from Secret Manager at runtime:** supports refreshing by version or rotation, but adds network dependencies, IAM permissions, latency, and cost. Cache secrets with an appropriate TTL, strict staleness limits, and explicit rotation handling.

Never cache secrets indefinitely. When a credential is revoked during a security incident, overly long caching extends the window during which an instance keeps using the revoked credential.

## 12. Dynamic configuration and safe feature flags

Feature flags let you toggle behavior without deploying, but they can also create hard-to-test state combinations. For instance, enabling checkout V2 while the new payment integration is not yet configured.

Design flags with:

- A name and description of purpose.
- An accountable owner.
- Creation date and planned removal deadline.
- A safe default value.
- Scope of application: global, environment, tenant, or user percentage.
- Compatibility constraints with application versions.
- Metrics to measure impact when toggled.

Never use feature flags as a substitute for authorization. A flag enabling a feature does not mean a user is authorized to perform an action. The backend must still enforce roles, ownership, and tenant boundaries.

For percentage rollouts, use deterministic bucketing so the same user does not flip back and forth between variants. Do not generate a fresh random number on every request if a consistent experience is required; hash an appropriate identifier or use a feature flag provider. Do not log PII just to track cohorts.

### Kill switches

A kill switch lets you quickly disable a failing integration or feature. Design it so the flag read path still works when the primary dependency is failing. If the kill switch lives inside the same unreachable service, it cannot help recovery.

For risky operations, prefer defaulting to off and requiring explicit configuration to enable. Test toggling procedures in staging and record who makes changes.

## 13. Configuration compatibility across versions

During serverless rollouts, old and new revisions may run concurrently. New dynamic configuration must remain compatible with both during the transition period.

For example, a new revision understands `checkoutV2`, while an older revision does not. If the config service alters the schema without versioning, older revisions may fail to parse it or fall back to unsafe defaults.

A safe workflow:

1. Deploy an application version capable of reading both old and new schemas.
2. Add the new configuration field with a safe default.
3. Update the config service.
4. Monitor both old and new revisions.
5. Shift traffic or enable the feature flag in stages.
6. Remove legacy fields only after no old revisions remain.

Never change the meaning of an existing key without a version bump or migration plan. For instance, do not change `timeout=5` from seconds to milliseconds while keeping the same key name and schema.

## 14. Configuration in snapshot/restore environments

Some serverless runtimes support snapshot/restore to reduce cold starts. When a snapshot is restored, static variables and heap caches may be cloned from the state captured at snapshot time.

For dynamic configuration, this means:

- A snapshot may contain configuration whose TTL has already expired upon restore.
- Multiple execution environments may start with the exact same cached version.
- Refresh timing across instances may drift.
- Secrets or tokens loaded before the snapshot may have expired.
- Deadlines or timestamps captured before the checkpoint do not reflect the current wall-clock time.

Never treat heap caches as the source of truth. Upon restore, verify expiration times and versions; refresh if needed before using critical configuration. If the runtime provides a post-restore hook, mark caches for refresh or renew environment-dependent resources. Do not execute business logic inside the hook.

Also avoid synchronized refresh spikes immediately after restore. Use jitter or per-instance single-flight mechanisms and bound load on the config service.

## 15. Observing and auditing configuration changes

When a request behaves unexpectedly, operators need to know which configuration version the instance used. You do not need to log the entire configuration; log only the version, source, and relevant non-sensitive keys.

Useful metrics and logs:

- Current config version by service/revision.
- Snapshot load timestamp and snapshot age.
- Refresh success/failure counts.
- Refresh latency and timeout counts.
- Count of stale config usages.
- Count of fallbacks to defaults.
- Validation or schema mismatch errors.
- Secret refresh failures (without logging secret values).
- Aggregated feature flag evaluations, avoiding high-cardinality labels.

Every configuration update should have an audit trail: who changed it, which keys changed, before/after versions, reason, and timestamp. Critical changes require review or approval per organizational policy.

Avoid logging entire dynamic configuration payloads if they may contain sensitive data or incur high log costs. Log the version and an allow-listed subset of metadata.

## 16. Testing configuration

Configuration is an application input and must be tested like code.

Recommended test cases:

| Test | What to verify |
|---|---|
| Missing required key | Application fails fast naming the key, without printing secrets |
| Wrong data type | Parser rejects invalid value instead of silently falling back to a default |
| Out of range | Negative timeouts, oversized batch sizes, or invalid URLs are rejected |
| Environment isolation | Staging does not point to production endpoints or secrets |
| Dynamic schema | App parses the expected version and handles optional fields |
| Concurrent refresh | A single instance does not issue redundant refresh requests |
| Config service timeout | Stale fallback or fail-closed behaves per policy |
| TTL expiry | Expired snapshots are refreshed |
| Max stale exceeded | Stale configuration is not used indefinitely |
| Rollback | Reverting to a known version works and behavior is verified |
| Snapshot restore | Stale caches and expired secrets are detected |
| Feature flag | Toggling does not bypass business authorization |

Use an injectable `Clock` in the cache to test TTLs and staleness ages without waiting in real time. For providers, use fake implementations to simulate timeouts, 5xx errors, and new versions.

## 17. Common implementation mistakes

- **Reading environment variables everywhere:** configuration becomes scattered and hard to test; centralize into a typed configuration object.
- **Skipping startup validation:** functions run with wrong endpoints or timeouts and fail later in production; fail fast on required keys.
- **Setting defaults on essential configuration:** can route data to the wrong place or inadvertently open access; assign defaults only to genuinely safe fields.
- **Logging secrets:** leaks credentials; log only key names or refresh status.
- **Using env vars for flags needing instant toggles:** updates may require a new revision; use dynamic config for keys with that lifecycle.
- **Calling the config service on every invocation:** increases latency, request volume, and cost; use a TTL cache.
- **Caching indefinitely:** instances may enforce revoked policies; enforce a max stale age.
- **Letting all instances refresh simultaneously:** causes a thundering herd; use single-flight, jitter, and backoff.
- **Treating static caches as the source of truth:** each instance has its own copy and versions may diverge; keep the source of truth in an external service.
- **Using one fallback for every key:** security configuration can go stale; classify fallback behavior by criticality.
- **Making incompatible schema changes:** older revisions can break during rollout; version schemas and roll out in phases.
- **Relying on feature flags instead of authorization:** users can access unauthorized resources; always enforce business permissions on the backend.

## 18. Practical implementation workflow

When building configuration for Java serverless, follow this sequence:

1. List all keys and classify each as deployment config, dynamic config, or secret.
2. Give keys meaningful names, explicit units, and valid value specifications.
3. Manage environment variables per revision/environment and prevent configuration drift.
4. Create a typed configuration object, parse once, and validate at init time.
5. Choose a config service and schema version for keys that must change at runtime.
6. Define TTL, max stale age, refresh timeout, and fallback behavior per key group.
7. Build immutable snapshots and swap references atomically on refresh.
8. Prevent refresh stampedes with single-flight, jitter, and backoff.
9. Read secrets from a secret manager/provider with least privilege and clear rotation.
10. Design feature flags that never replace authorization and include owners and expiry dates.
11. Ensure old and new revisions stay compatible during rollouts.
12. Handle expired caches/credentials after snapshot/restore if supported by the runtime.
13. Monitor config versions, refresh failures, stale usage, and audit trails.
14. Test missing keys, invalid schemas, timeouts, rollbacks, and concurrent refreshes across instances.

## 19. Takeaways

Environment variables fit configuration tied to a deployment or revision; dynamic configuration fits parameters that must change while the application is running; secrets must be managed separately with dedicated security mechanisms.

In Java serverless, consolidate environment variables into a typed configuration and validate early. Dynamic config should have a schema/version, immutable snapshots, and caching with clear TTL and staleness bounds. Each execution environment maintains its own cache, so never assume an update in one instance takes effect globally at once.

Design refreshes with timeouts, single-flight, jitter, and per-key-criticality fallbacks. Monitor configuration versions, refresh failures, and stale data usage; test rollouts, rollbacks, and snapshot/restore behavior. This structure enables flexible behavior changes while keeping consistency, security, latency, and cost under control.
