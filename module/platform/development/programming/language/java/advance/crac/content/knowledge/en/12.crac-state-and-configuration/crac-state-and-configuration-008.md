# Reconciling in-image state with current state of external services

CRaC (Coordinated Restore at Checkpoint) saves the state of a Java process at a point in time and restores the process from that image. The heap, objects, in-memory caches, and execution threads can be recovered according to the checkpointed state. Meanwhile, databases, configuration services, secret managers, service registries, message brokers, identity providers, and other external services continue operating.

The time gap between checkpoint creation and restore creates an important problem: **state inside the image may be stale compared to authoritative external state**.

For example, an application checkpoints while a feature flag is enabled. While the image is stored, an administrator disables the feature flag after discovering a bug. Upon restore, the configuration object on the heap still records the feature flag as true. If the application continues using that object without reconciling, the instance can re-enable a disabled feature.

Therefore, a CRaC application needs a post-restore state reconciliation workflow. This workflow determines which data can be kept from the image, which data must be re-read, which data must be verified, and which data must be newly created.

## 1. Two state worlds at checkpoint time and restore time

Two points in time can be modeled:

- **T0 — Checkpoint:** the application is running and creates the image.
- **T1 — Restore:** the process is restored from the image after an interval.

At T0, the application may hold a configuration copy, service discovery state, data caches, tokens, connection pools, or leader status. These values reflect what the application observed at T0.

Between T0 and T1, external services may change:

- Configuration is updated.
- Secrets or certificates are rotated.
- The database advances to a new schema version.
- A service endpoint is replaced.
- Another instance acquires leadership.
- A feature flag or access policy is revoked.
- The message broker changes partition assignments.
- A resource is created, deleted, or transferred to another owner.

The checkpoint image does not automatically update itself for those changes. Upon restore, the application must determine which state remains valid.

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant Image as Checkpoint Image
    participant External as External Services

    App->>External: Read config revision 17
    External-->>App: Config revision 17
    App->>App: Cache state on the heap
    App->>Image: Create checkpoint at T0
    Note over Image,External: Process is stored in the image
    External->>External: Config changes to revision 18
    External->>External: Secret is rotated
    External->>External: Leader lease is granted to another instance
    Image->>App: Restore at T1
    App->>External: Read current state
    External-->>App: Revision 18, new secret, new ownership
    App->>App: Reconcile and update state
    App->>App: Open readiness only when ready
~~~

The key point is that the image saves process state at T0, whereas external services answer the question of current state at T1. These two sources can differ without any checkpoint error having occurred.

## 2. Classifying state retained inside the image

Not all data on the heap needs to be reloaded. Classify by ownership source and mutability.

| State category | Examples | Post-restore policy |
|---|---|---|
| Internally computed state | Parse results, immutable data structures, regenerable caches | Can be kept if inputs and versions remain compatible |
| Configuration snapshots | Feature flags, endpoints, business limits | Check revision or reload per policy |
| Externally authoritative state | Balances, order status, access permissions | Read from the owning system before making decisions |
| Credentials and security state | Tokens, certificates, secrets, sessions | Verify or re-fetch from credential manager |
| OS-lifecycle resources | Sockets, file descriptors, connection pools | Close before checkpoint and recreate after restore |
| Temporary ownership | Leader leases, locks, partition assignments | Revalidate or reacquire |
| Cursors and processing positions | Message offsets, event sequences, change cursors | Sync with broker/store and replay missed items |
| Image metadata | Build ID, config revision, schema compatibility | Verify against target environment before serving |

A Java object existing on the heap proves only that the object's state was saved in the image. It does not prove the data represented by the object is still current or that the application still holds permission to use that resource.

### 2.1 Distinguishing cached copies from authoritative sources

Suppose the application holds:

~~~java
Map<String, FeatureConfig> featureCache;
~~~

The map on the heap is a copy the application loaded from the configuration service. If the configuration service is the authoritative source, the map must never overwrite data on the service merely because the image contains old values.

For critical data, explicitly document:

- Which system owns the data.
- Whether heap data is a cache, snapshot, or authoritative state.
- How long a copy is considered valid.
- How changes are detected.
- Behavior when the authoritative source is unreachable.

This ownership convention prevents a restored instance from writing stale state back onto external systems.

## 3. Choosing a reconciliation policy

Different policies suit different kinds of state. Do not apply one single strategy to every dependency.

### 3.1 Keep the pinned snapshot intact

Some workloads need to reproduce the exact configuration used when creating the image. For example, a batch job must process a dataset or a fixed rule version.

In this case, the image can be bound to an immutable revision. After restore, the application requests that exact revision rather than fetching the latest version.

Suitable when:

- Revisions are stored durably and are not mutated in place.
- Snapshot data remains accessible.
- The goal is reproducibility or preserving consistency within one workflow.
- Security policy permits continuing to use an older revision.

Unsuitable for state that must take effect immediately, such as revoked access permissions, compromised secrets, or security kill switches.

### 3.2 Load the latest state

For dynamic configuration, endpoint discovery, or feature flags, the application usually needs to load the latest version after restore.

The benefit is that the instance quickly converges to current state. In return, instance behavior after restore may differ from behavior when the image was created.

Verify whether the new configuration is compatible with the code and schemas inside the image. Not every newer revision is compatible with an older binary.

### 3.3 Verify before continuing

For high-risk state, the application should ask the external system to confirm that in-image state remains valid.

Examples:

- Check whether a lease still belongs to the instance.
- Verify a session has not been revoked.
- Check that schema version lies within the supported range.
- Confirm certificates or credentials are still trusted.
- Verify endpoints and service generations remain valid.

If verification fails, the application must halt dependent functionality or run an acquire/re-authenticate procedure.

### 3.4 Merge or reconcile

Some systems have local state that must be merged with external state. For example, a workflow has a local checkpoint marker while the event store received additional events.

In that case, the application needs explicit merge rules:

- Use revision or sequence numbers to determine which part is newer.
- Replay events starting from the saved cursor.
- Deduplicate by event ID.
- Use version checks when updating.
- Resolve conflicts according to business rules.

Never merge by overwriting all external state with stale heap objects.

### 3.5 Selection table

| State | Commonly suitable policy | When reconciliation fails |
|---|---|---|
| Version-fixed configuration | Pin revision and verify compatibility | Reject image if revision is no longer supported |
| Dynamic feature flags | Load latest revision or check TTL | Keep readiness false for affected features |
| Secrets/certificates | Fetch or verify current credentials | Do not use old credentials if unverifiable |
| Database schema | Compare version against compatibility range | Do not open traffic if incompatible |
| Leader lease/lock | Revalidate or reacquire | Do not execute operations requiring ownership |
| Service discovery | Resolve current endpoint and rebuild client | Stay not ready until dependency is found |
| Reference data cache | Validate revision or rebuild | Use stale cache only if policy permits |
| Event cursor | Replay from durable cursor and deduplicate | Stop consumer if safe position cannot be determined |

## 4. Storing version and generation instead of only values

A configuration snapshot should carry metadata about the version it represents.

Example:

~~~java
import java.time.Instant;
import java.util.Map;

public record ConfigSnapshot(
        String revision,
        Instant fetchedAt,
        Map<String, String> values) {
}
~~~

At checkpoint time, this object can be saved on the heap. After restore, the application reads the current revision from the configuration service and compares.

If only values are saved without revision, the application struggles to determine:

- When the cached copy was loaded.
- Which environment it belongs to.
- Whether it has changed since the last fetch.
- Which version can be pinned or rolled back to.
- Whether the image is compatible with a new revision.

### 4.1 Revisions must have clear semantics

A version can be:

- A monotonically increasing number, such as 17, 18, 19.
- A hash of configuration contents.
- An ETag provided by an HTTP server.
- A resource's generation ID.
- A commit ID or release ID.
- A version managed by the configuration service.

Do not compare two versions as arbitrary strings if the format does not guarantee ordering. If only equality checks are needed, hashes or opaque ETags work well. If determining which revision is newer is needed, use a version with well-defined ordering.

### 4.2 Associating image metadata with environment state

A system can manage metadata outside the image:

~~~json
{
  "checkpointId": "crac-image-2026-11-13-001",
  "applicationBuild": "2.8.1",
  "environment": "production-eu",
  "configRevision": "cfg-1842",
  "schemaCompatibility": {
    "minimum": 42,
    "maximum": 44
  },
  "createdAt": "2026-11-13T06:00:00Z"
}
~~~

This is an example of deployment-platform-defined metadata, not a mandatory CRaC format.

A controller can inspect metadata before restoring or before opening traffic. If the image belongs to another environment, the config revision has been revoked, or the schema falls outside the compatibility range, the controller can reject the image and start the application conventionally.

Metadata does not replace runtime verification. External state can still change after the controller reads metadata.

## 5. Reconciling dynamic configuration with revisions or ETags

Configuration services often provide revisions or HTTP ETags so clients know whether contents changed.

For example, the initial load receives:

~~~http
HTTP/1.1 200 OK
ETag: "config-r17"
Content-Type: application/json
~~~

After restore, the client sends a conditional request:

~~~http
GET /config/application
If-None-Match: "config-r17"
~~~

If contents have not changed, the server can return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "config-r17"
~~~

If contents changed, the server returns the new contents alongside a new ETag:

~~~http
HTTP/1.1 200 OK
ETag: "config-r18"
Content-Type: application/json
~~~

This reduces transferred payload size and lets the application detect stale caches.

### 5.1 Example client using Java HttpClient

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ConfigClient {

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public ConfigResponse fetch(String etag) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create("https://config.example.internal/app"))
                .timeout(Duration.ofSeconds(5))
                .GET();

        if (etag != null) {
            builder.header("If-None-Match", etag);
        }

        HttpResponse<String> response = client.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 304) {
            return ConfigResponse.notModified(etag);
        }

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Config service returned " + response.statusCode());
        }

        String newEtag = response.headers()
                .firstValue("ETag")
                .orElseThrow(() ->
                        new IllegalStateException("Missing ETag"));

        return ConfigResponse.updated(newEtag, response.body());
    }
}
~~~

ConfigResponse here is an application-defined data type. Validate the response body, schema, signature, or policy before applying configuration.

### 5.2 Applying configuration atomically

Do not update individual fields of shared configuration while other threads are reading. Parse and validate the new version first, then swap the snapshot with an atomic operation:

~~~java
AtomicReference<ConfigSnapshot> current =
        new AtomicReference<>();

void apply(ConfigSnapshot candidate) {
    validate(candidate);
    current.set(candidate);
}
~~~

Threads reading the current snapshot always see a complete version. There is no window where some fields belong to an old revision and others belong to a new revision.

If a new configuration is invalid or incompatible with the current binary, reject application and report an error. Never overwrite a valid snapshot with unvalidated data.

## 6. Do not write stale snapshots back to external services

A dangerous bug is restoring an old object and sending that entire object back to an external service.

For example, the image contains:

~~~json
{
  "revision": 17,
  "maintenanceMode": false,
  "maxWorkers": 20
}
~~~

While the image is stored, an administrator updates revision 18:

~~~json
{
  "revision": 18,
  "maintenanceMode": true,
  "maxWorkers": 5
}
~~~

If the restored instance sends a PUT of the entire revision 17 to the service, it can overwrite the new maintenanceMode and maxWorkers. This is a lost update.

### 6.1 Use conditional updates

If the API supports ETag or versions, send the version precondition that the client read:

~~~http
PUT /config/application
If-Match: "config-r17"
Content-Type: application/json
~~~

If the server is currently at revision 18, the server rejects the update with **412 Precondition Failed**. The client must reload current state and resolve the conflict.

This is optimistic concurrency control. It helps prevent an old snapshot from overwriting newer data.

### 6.2 Update only fields owned by the instance

If an instance manages only its own state such as lastSeen or runtime metrics, use a dedicated endpoint for those fields. Never send the entire global configuration.

Examples:

- Configuration service owns feature flags and business limits.
- Instance registry owns heartbeats and instance status.
- Lease service owns leadership status.
- Database owns order state.
- Application owns only local caches.

Clear ownership boundaries prevent independently restored instances from contending to update the same state document.

## 7. Reconciling secrets, certificates, and identities

Secrets and certificates can change while an image is stored. This category requires strict handling because stale values might still work technically while no longer being permitted.

### 7.1 Secret rotation

Suppose an image contains an old database password. During checkpointing, the secret manager rotates the password and revokes the old credential.

Upon restore, the connection pool is recreated using the password on the heap. Connections will fail.

Proper procedure:

1. Designate the secret manager as the authoritative source.
2. Fetch the current secret version after restore.
3. Validate format and access permissions.
4. Create new connections or clients using the current secret.
5. Replace active credentials only once new clients are working.
6. Never log secrets or embed secret values in image metadata.

If the secret manager is not yet ready, keep readiness false for dependent features. Never use old credentials just to make the application start faster if those credentials may have been revoked.

### 7.2 Certificates and trust stores

Certificates can expire, be revoked, or be replaced. Trust stores can also be updated to remove untrusted CAs.

After restore, verify:

- Client certificates remain within validity periods.
- Corresponding private keys remain available and authorized.
- Certificate chains remain trusted.
- New server certificates are accepted by the trust store.
- Whether old TLS client contexts or connection pools must be recreated.

An SSLContext held on the heap can contain stale trust material. When policy requires immediate updates, build a new SSLContext from the current trust store and replace clients safely.

### 7.3 Workload identity

If the application runs on Kubernetes or cloud platforms, credentials may be issued via service account tokens, metadata services, or workload identity providers.

Tokens in the image may be expired or bound to an old pod/instance. When restored into multiple replicas, do not assume every replica can use the same token.

Obtain new credentials matching each instance's identity after restore. If the environment rotates token files, re-read the file or use an SDK supporting credential refresh.

## 8. Service discovery and changing endpoints

A client object on the heap may retain endpoints, IPs, or connection pools created prior to checkpointing.

While the image is stored:

- Services may scale up or scale down.
- Pods may be replaced.
- IPs may change.
- DNS records may be updated.
- Services may migrate regions or clusters.
- Certificates or routes may rotate.

After restore, do not reuse old endpoints or connections merely because the client object still exists.

### 8.1 Resolving new endpoints

Clients should resolve service names or query the service registry after restore. Then recreate connection pools and run endpoint health checks.

~~~java
public final class ApiClientResource implements Resource {

    private final ServiceDiscovery discovery;
    private final ApiClientFactory factory;
    private ApiClient client;

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        ServiceEndpoint endpoint = discovery.resolve("orders");
        ApiClient replacement = factory.create(endpoint);
        replacement.healthCheck();
        client = replacement;
    }
}
~~~

ServiceDiscovery, ServiceEndpoint, ApiClientFactory, and ApiClient are illustrative abstractions. Production clients need timeouts, TLS configuration, retry policies, and explicit connection shutdown.

### 8.2 DNS caches

The JVM can cache DNS resolution according to security properties and runtime configuration. If the application needs to reach new endpoints after restore, check DNS caching policies of the JDK and networking libraries.

Even after DNS re-resolves, old connection pools can still retain TCP connections to old addresses. Therefore, manage both DNS resolution and socket lifecycles.

Do not merely swap a hostname string in configuration and assume every connection has moved to the new endpoint.

### 8.3 A health check is not a business-state check

An endpoint returning HTTP 200 proves only a certain level of availability. If a client needs specific permissions, test the corresponding capability or permission.

For example, a service may respond to its health endpoint while its database is read-only or its queue consumer has no partitions assigned. Choose validation aligned with the capability the application relies on.

## 9. Database schemas and external data state

Databases are not frozen along with the image. Schemas, data, and permissions can change during checkpointing.

An image created when the application used schema revision 42 might restore after the database migrated to revision 45.

Before serving, the application should verify:

- The current schema version lies within the code's supported range.
- Required tables and columns exist.
- The database user retains required privileges.
- The connection pool has been newly created.
- Old transactions are not treated as still open.
- Caches depending on database data have been validated or rebuilt.

Never automatically run breaking migrations inside afterRestore just to keep an old image running. If the new schema is incompatible, reject the image or deploy using an expand/contract migration strategy.

### 9.1 Data state cannot be inferred from caches

For example, an image retains a cache:

~~~java
Map<Long, OrderStatus> orderStatusCache;
~~~

While the process was inactive, an order may have been paid, canceled, or refunded. The cache inside the image does not reflect those changes.

For strongly consistent business data, query the database or invalidate caches. Stale caches should be used only if business rules tolerate staleness within explicit bounds.

### 9.2 Cache revisions and invalidation

You can attach the data source's revision to the cache:

~~~java
public record CacheSnapshot(
        long sourceRevision,
        Instant loadedAt,
        Map<Long, OrderStatus> values) {
}
~~~

After restore, compare sourceRevision with the current revision. If they differ, reload or invalidate.

If the database does not provide a global revision, use metadata tables, CDC sequences, event offsets, or per-entity versions. Choose a mechanism with well-defined semantics rather than relying solely on local timestamps.

## 10. Message brokers, event cursors, and subscriptions

A consumer may hold on the heap:

- Partition assignments.
- Read or processed offsets.
- Subscription state.
- Connections to the broker.
- In-progress message batches.

Brokers keep running while the process is checkpointed. Meanwhile, partition assignments can change and new messages can be appended to logs.

### 10.1 Do not retain old assignments

After restore, the consumer must reconnect and rejoin group coordination. The broker may assign partitions different from those recorded in the image.

Never assert that the instance still owns old partitions. Let the broker or consumer group coordinator determine new assignments.

### 10.2 Determining safe offsets

Distinguish:

- Fetched offsets.
- Processed offsets.
- Committed offsets.
- Broker-acknowledged offsets.

If a checkpoint saves offsets that were fetched but not finished processing, restoring may skip or duplicate messages depending on commit strategy.

A common policy is committing only after side effects are durably persisted. After restore, start from committed offsets and use idempotent processing to re-handle safely when needed.

### 10.3 Replaying missed events

If the application uses an event stream to maintain a cache, the image may hold a cursor at sequence 100. During checkpointing, the stream advanced to sequence 130.

After restore:

1. Reconnect to the broker.
2. Obtain the durable cursor or current sequence.
3. Replay events from a safe position.
4. Deduplicate by event ID.
5. Apply events in required order.
6. Mark state synchronized only after catching up to an appropriate watermark.

Do not simply reopen a subscription and assume the heap cache is already up to date.

## 11. Leases, leader election, and resource ownership

An image may contain boolean isLeader=true or a lock object acquired prior to checkpoint. Over time, the lease may expire and another instance may acquire leadership.

If multiple replicas restore the same image, all can carry isLeader=true on the heap simultaneously. This is a severe bug if each instance continues writing data or scheduling jobs.

### 11.1 Never checkpoint temporary ownership as ground truth

Leader or lock state on the heap is only an observation at T0. After restore, re-verify with the lease service or database lock.

If the lease expired:

- Halt side effects.
- Acquire a new lease using an atomic operation.
- Obtain a new generation or fencing token.
- Operate only after the target system confirms ownership.

### 11.2 Fencing tokens protect against stale owners

Suppose instance A holds fencing token 105. A checkpoints and its lease expires. Instance B receives token 106. Later, A restores.

If A still sends commands with token 105, the target system must reject them because token 106 is newer. Thus, even if A does not realize it lost the lease, fencing blocks it from writing data.

A local boolean or lock object cannot replace this mechanism.

## 12. Post-restore reconciliation workflow

An application can build a dedicated RECONCILING phase after basic resources have been recreated.

Reference sequence:

1. Keep traffic-serving readiness at false.
2. Recreate connections to external services.
3. Read current revisions/generations from authoritative sources.
4. Verify application build compatibility with current state.
5. Refresh secrets, certificates, and identities.
6. Revalidate leases, locks, and service ownership.
7. Sync event cursors or necessary caches.
8. Apply the new snapshot atomically.
9. Run functional health checks.
10. Transition state to READY.

~~~mermaid
stateDiagram-v2
    [*] --> RESTORING
    RESTORING --> RECONNECTING: JVM and resources begin recovering
    RECONNECTING --> RECONCILING: Dependency connections succeed
    RECONNECTING --> FAILED: Dependency cannot connect
    RECONCILING --> VALIDATING: Current state has been read
    RECONCILING --> FAILED: Conflict or incompatible state
    VALIDATING --> READY: All essential conditions valid
    VALIDATING --> FAILED: Validation fails
    READY --> SERVING: Open readiness
    FAILED --> RECONCILING: Bounded retry
~~~

The RECONCILING state distinguishes a restored JVM from an application genuinely synchronized with its current environment.

### 12.1 Distinguishing mandatory and optional dependencies

Not every service must be operational before the application accepts traffic.

Examples:

- The primary database may be a mandatory dependency.
- A feature flag service may be mandatory if it governs access control.
- A metrics exporter may be optional.
- A cache can rebuild asynchronously if the database can handle the load.
- A search index may be unneeded for certain endpoints.

Specify clearly what each dependency can do:

- Block overall readiness.
- Block a feature group.
- Use an older snapshot for a bounded period.
- Degrade gracefully temporarily.
- Force the instance to stop.

Do not let an optional dependency's failure accidentally take down the entire application's readiness. Conversely, never signal ready while a mandatory dependency remains unverified.

## 13. Java example: reconciling ConfigSnapshot in afterRestore

The example below illustrates a Resource holding a configuration snapshot on the heap and loading the current revision from the service after restore.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConfigResource implements Resource {

    private final ConfigClient client;
    private final ConfigValidator validator;
    private final AtomicReference<ConfigSnapshot> current;

    public ConfigResource(
            ConfigClient client,
            ConfigValidator validator,
            ConfigSnapshot initial) {
        this.client = client;
        this.validator = validator;
        this.current = new AtomicReference<>(initial);

        Core.getGlobalContext().register(this);
    }

    public ConfigSnapshot current() {
        return current.get();
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Watchers or config polling can be paused here.
        // Do not write the old snapshot back to the configuration service.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        ConfigSnapshot restored = current.get();
        ConfigSnapshot latest = client.fetchCurrent();

        validator.validate(latest);

        if (!latest.revision().equals(restored.revision())) {
            current.set(latest);
        }
    }
}

record ConfigSnapshot(
        String revision,
        Instant fetchedAt,
        Map<String, String> values) {
}
~~~

ConfigClient and ConfigValidator are application abstractions. In production, add timeouts, response verification, environment checks, and policies for incompatible new revisions.

Key points:

- The heap snapshot is treated as a cached copy.
- The configuration service is the authoritative source.
- After restore, the client fetches the new state.
- The validator verifies before replacing the snapshot.
- AtomicReference swaps the entire snapshot in a single operation.
- Old data is never pushed back to the external service.

If latest cannot be fetched due to network errors, behavior depends on policy. For security or mandatory configuration, the callback should fail so restoration is not considered complete. For non-critical configuration, the application may keep the older copy briefly while recording STALE status and restricting features.

### 13.1 Not all reconciliation belongs inside the callback

The afterRestore callback can execute synchronous operations required to bring the process back to a consistent state. However, avoid placing massive data loads or infinite retries inside the callback.

You can split into two phases:

- **Required before readiness:** establishing connections, verifying identity, reading revisions, and checking core dependencies.
- **Can run in the background:** rebuilding large caches, loading optional reference data, prefetching, or extra warm-up.

If choosing asynchronous recovery, readiness must accurately reflect which capabilities are ready. Never transition the entire application to READY before mandatory preconditions finish.

## 14. Handling errors and conflicts during reconciliation

Reconciliation can fail due to networking, access permissions, version incompatibility, or data conflicts.

| Error | Handling |
|---|---|
| Timeout reading config | Bounded retry; keep readiness false if config is mandatory |
| New revision incompatible with build | Reject image or trigger rollout of a newer build |
| Secret rotated | Fetch current credential and recreate client |
| ETag changed before conditional update | Reload and resolve conflict |
| Lease lost | Do not perform side effects; reacquire if permitted |
| Schema outside compatibility range | Do not open traffic; run appropriate migration/rollout |
| Broker assignment changed | Accept new assignment and sync cursor |
| Cache revision mismatch | Invalidate or rebuild |
| Optional dependency unavailable | Switch dependent feature to degraded mode if policy permits |

### 14.1 Retries must be bounded

A callback may encounter a temporarily unavailable service. Use timeouts, backoff, and maximum attempt limits.

Do not retry unrecoverable errors such as:

- Revoked credentials.
- Incompatible schema.
- Permanently deleted resources.
- Revoked permissions.
- Image belonging to the wrong environment.

These errors require a deployment or operational decision, not continuous retries.

### 14.2 Never bypass conflicts by overwriting

If a conditional update returns 412 Precondition Failed, the client knows state changed. Reload and resolve according to ownership/version. Never blindly resend the same old payload while stripping the If-Match header.

### 14.3 Distinguishing STALE from INVALID

An old snapshot is not automatically wrong. It may remain valid within a TTL or under a pinned revision.

- **FRESH:** reconciled against current authoritative source.
- **STALE:** not yet refreshed, yet policy permits temporary use.
- **INVALID:** no longer compatible or has been revoked.
- **UNKNOWN:** cannot be verified due to connectivity errors.

UNKNOWN must never automatically convert into FRESH. The application needs an explicit policy for each state.

## 15. Restoring one image into multiple instances

One image can be used to spawn multiple instances for fast scaling. Every instance can start from the same heap snapshot.

This creates risks:

- Holding the same instance ID.
- Sharing the same token or credential.
- All thinking they are leader.
- Holding the same message offset.
- Writing the same sequence number.
- Registering the same scheduled job.
- Re-sending a side effect already executed by another instance.

### 15.1 Creating a distinct identity per instance

If the system needs unique instance identities, obtain or generate a fresh identity after restore from the platform or registry. Do not use a UUID created prior to checkpointing as the identifier for every replica.

Identity can include:

- Pod UID or VM instance ID.
- Process generation.
- Deployment revision.
- Region/zone.
- Checkpoint image ID.

Do not confuse a shared application build ID with an instance ID that must be unique.

### 15.2 Shared state requires external coordination

A static variable inside an image cannot act as a distributed lock. All restored replicas start with the same static value.

Shared resources require external coordination:

- Database unique constraints.
- Distributed locks or lease services.
- Compare-and-set.
- Idempotency keys.
- Fencing tokens.
- Consumer group coordination.

### 15.3 Avoid duplicating side effects

If a checkpoint image was taken after an operation was sent to an external system yet before the application recorded the result on the heap, restoring can resend the operation.

For example, a payment creation request was processed by the payment service, yet the response was not yet saved in local state. Upon restore, code might resend the payment.

Use stable idempotency keys for the same business operation, query state before retrying, and persist business state durably at the authoritative source.

## 16. Observing reconciliation status

To know whether the application synchronized properly after restore, record relevant milestones and versions.

Useful metrics or logs:

- Checkpoint ID and image build ID.
- New instance ID after restore.
- Start timestamps of restore and reconciliation.
- Revision inside the image.
- Current revision from external service.
- Number of reconnected dependencies.
- Number of snapshots refreshed or invalidated.
- Reconciliation duration.
- Count of conditional update conflicts.
- Retry and timeout counts.
- Final status: FRESH, STALE, INVALID, or UNKNOWN.
- Timestamp when readiness becomes true.

Never log raw secrets, access tokens, or session IDs. Use non-sensitive references or controlled hashes to correlate logs.

An example log entry might look like:

~~~json
{
  "event": "external_state_reconciled",
  "checkpointId": "crac-image-2026-11-13-001",
  "instanceId": "pod-7f8b9",
  "configRevisionInImage": "cfg-17",
  "configRevisionCurrent": "cfg-18",
  "result": "UPDATED",
  "durationMs": 142
}
~~~

This log helps explain why the restored instance uses different configuration from when the image was created.

## 17. Testing state changes between checkpoint and restore

A test that merely restores immediately after checkpointing usually misses state drift. Simulate real external service changes.

| Scenario | Change while image is stored | What to verify |
|---|---|---|
| Config update | Revision 17 becomes 18 | Instance loads or pins the right revision per policy |
| Feature flag off | Kill switch turned off | Stale heap flag is not re-enabled |
| Secret rotation | Old password/token revoked | Client uses new secret or keeps readiness false |
| Certificate renewal | Certificate or trust store changed | TLS client recreated with current trust material |
| Database migration | Schema advances to newer version | Image compatibility is verified |
| Service replacement | Endpoint/IP changed | Connection pool recreated with new endpoint |
| Lease expiry | Another instance acquired lease | Restored instance does not resume old ownership |
| Broker rebalance | Partition assignment changed | Consumer rejoins group and handles offsets properly |
| Session revoke | User logged out | Old session is rejected |
| Multi-replica restore | Same image spawns multiple instances | Identities, locks, tokens, and side effects are not improperly shared |
| External service unavailable | Unable to read current state | Fail-closed or degraded policy applied properly |

Also test changes occurring between checks: external state can change right after reconciliation. For critical writes, use conditional updates or leases/fencing at execution time rather than checking only once at startup.

## 18. Common mistakes

### Believing every heap object reflects current state

Objects reflect only a snapshot at checkpoint time. Out-of-process data may have changed.

### Writing old configuration back to the configuration service

Restored instances can overwrite newer updates. Use explicit ownership and revision-based conditional updates.

### Checking only whether an endpoint responds

HTTP 200 does not prove the service has the right version, permissions, schema, or business state the application requires.

### Keeping old connection pools and endpoints

Existing client objects do not prove sockets or endpoints remain valid. Reconnect and re-resolve dependencies.

### Using a checkpointed isLeader boolean

Leadership or leases may have expired. Revalidate with the lease service and use fencing tokens.

### Keeping old tokens or secrets

Credentials may have rotated or been revoked. Fetch current state from the secret manager or identity provider.

### Comparing only local timestamps

Clock skew and revocation can invalidate local timestamps. Prefer revisions, generations, or authoritative state from services.

### Treating UNKNOWN as VALID

If a dependency is unreachable, the application does not know current state. Apply fail-closed behavior for security and high-consistency features.

### Restoring multiple replicas with the same identity

Multiple instances can overwrite state or duplicate side effects. Create fresh identities and use external coordination.

### Transitioning readiness to true too early

A restored JVM does not mean dependencies have been reconciled. Open traffic only after mandatory state is verified valid.

## 19. Implementation workflow

When adopting CRaC for a Java application, apply the following workflow to reconcile in-image state with current external service state:

**Step 1 — Inventory cached state.** Locate config snapshots, feature flags, secrets, tokens, endpoints, schema versions, leases, sessions, caches, and event cursors.

**Step 2 — Identify authoritative sources.** Document which system owns each datum and which fields an instance may read or write.

**Step 3 — Choose policy per state type.** Pin revisions, refresh latest, validate, merge, or recreate according to semantics.

**Step 4 — Record metadata.** Attach revision, generation, application build, and checkpoint ID to identify state inside the image.

**Step 5 — Reconnect and reconcile.** After restore, recreate connections, read current state, verify compatibility, and apply new snapshots atomically.

**Step 6 — Protect write operations.** Use ETag/If-Match, version checks, compare-and-set, idempotency keys, or fencing tokens to avoid overwriting newer state.

**Step 7 — Handle multi-instance restores.** Generate distinct identities, obtain separate credentials, and never inherit temporary ownership from the image.

**Step 8 — Manage readiness.** Keep the application in RECONCILING until mandatory dependencies are verified. Allow degraded mode only when defined by policy.

**Step 9 — Test state drift.** Mutate config, secrets, schemas, endpoints, leases, and sessions while the image is stored; then restore and verify behavior.

**Step 10 — Observe.** Log before/after revisions, reconciliation duration, conflicts, retries, and readiness transitions for traceability.

A reliable CRaC application must treat a checkpoint image as a process snapshot at T0 and proactively reconcile against authoritative state sources at T1. This enables reusing images without accidentally restoring revoked configuration, expired ownership, or stale data.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and coordination between applications and external resources.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): registering Resource and beforeCheckpoint/afterRestore lifecycle callbacks.
- [Java API — AtomicReference](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): replacing configuration snapshots atomically.
- [Java API — HttpClient](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpClient.html): creating HTTP clients and sending requests with timeouts.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ETag, If-Match, If-None-Match, and conditional requests.
- [RFC 7232 — HTTP Conditional Requests](https://www.rfc-editor.org/rfc/rfc7232): HTTP validators and update preconditions (obsoleted/merged into RFC 9110).
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): managing configuration and configuration updates for workloads.
- [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/): service discovery and endpoint access.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): credential management, refresh tokens, and revocation.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS connection authentication and protection.
