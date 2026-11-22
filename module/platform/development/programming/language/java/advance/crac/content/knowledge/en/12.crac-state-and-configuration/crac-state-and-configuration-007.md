# Recreating per-replica identities, resources, and credentials

CRaC enables taking a checkpoint of an initialized Java process and restoring that process to reduce startup time. In deployments with multiple replicas, the same checkpoint image can be used to spawn multiple application instances. This is an effective way to replicate shared initialization, yet it introduces a critical problem: every replica starts from the exact same heap state.

If a checkpoint image contains an instance ID, hostname, consumer ID, local sequence number, leader status, session, private key, or token created before the checkpoint, those values can appear identically across multiple replicas. Some identical values are intentional, such as service name or consumer group. Other values must be unique per replica, such as a process identity, session key, temporary file, socket, lease, or instance-scoped credential.

Therefore, the application must distinguish three categories of data:

1. **Shareable configuration and state:** service name, protocol configuration, schemas, immutable metadata, or shareable initialization data.
2. **Per-replica identities and resources:** instance ID, member ID, temporary directories, sockets, connection pools, workers, leases, and local state.
3. **Credentials with independent lifecycles:** short-lived tokens, certificates, private keys, sessions, and credentials that must be newly acquired or re-verified after restore.

Each replica must complete its own per-replica initialization before accepting traffic or processing work. CRaC preserves reusable initialization state; post-restore callbacks must refresh values that depend on the current replica's identity and environment.

## 1. Why can multiple replicas from the same checkpoint conflict?

Suppose an application starts once, creates identity objects, opens a consumer, acquires a lease, and stores all those objects on the heap. Then the application is checkpointed. When the system spawns three replicas from the same image, each new process can start with a copy of the Java objects that existed at checkpoint time.

For example, the heap at checkpoint time might contain:

~~~java
static final String INSTANCE_ID = UUID.randomUUID().toString();
static final String CONSUMER_MEMBER_ID = "worker-17";
static volatile boolean leader = true;
static long localSequence = 10_500;
~~~

If these fields remain unchanged when restoring from the same checkpoint, multiple replicas can all identify themselves as worker-17, all believe they are the leader, and all continue from the same sequence number. When replicas operate concurrently, the system can encounter:

- Duplicate instance IDs in the service registry, logs, metrics, or traces.
- Multiple consumers using the same member ID and colliding when joining the group.
- Multiple replicas believing they hold a distributed lock or leadership.
- Colliding temporary file names, socket paths, PID files, or working directories.
- Sharing a token or private key already stored on the heap.
- Generating duplicate business IDs if a random generator or counter is cloned without uniqueness guarantees.
- Overwriting one another's state when updating the same external resource.

A checkpoint does not know which values have service-wide meaning and which have per-process meaning. Classification must be built into application design.

### 1.1. Which state is retained?

A checkpoint image can retain Java state such as:

- Static and instance fields.
- Singletons, caches, loaded configuration, and initialized objects.
- Referenced client, session, token, or credential objects.
- Counters, random generator seeds, and scheduler state on the heap.
- References to OS or native resources depending on runtime and platform support.

When multiple processes restore from the same image, each process has its own memory space, yet initial field values are copied from the same snapshot. The fact that replicas do not share the same memory addresses does not make the identity values inside them automatically differ.

Some external resources may not be restored or may have expired. Even so, the Java object representing the resource may still reside on the heap. The application must close, discard, or recreate resources according to library APIs and CRaC callbacks.

### 1.2. Not every value must differ

Do not generate new IDs for everything. Replicas may need to share:

- Logical service name such as orders-api.
- Consumer group that all replicas join together.
- Topic or queue names.
- Schemas, protocol versions, and immutable business configuration.
- Root CAs or shared service trust policies.
- Feature flag configuration if dictated by the config source.

Meanwhile, the following values usually must differ or be reissued per replica:

- Instance ID or process incarnation ID.
- Consumer member ID if the broker requires each member to have a distinct identity.
- Hostname, pod UID, or replica endpoint address.
- Socket names, temporary directories, lock files, and local resources.
- Lease tokens, fencing tokens, or leadership status.
- Instance-, session-, or connection-scoped credentials.
- Trace/process metadata and instance-identifying metric labels.

What matters is determining the ownership scope and uniqueness scope of each value, not merely its name.

## 2. Distinguishing service identity, replica identity, and business identity

A distributed system typically has multiple kinds of IDs coexisting. Using one ID for every purpose easily leads to accidental cloning or unstable IDs.

| Identity kind | Scope | Examples | Handling upon restore |
|---|---|---|---|
| Service identity | Represents a logical service | orders-api, billing-worker | Usually preserved from configuration |
| Workload identity | Represents an authorized workload | Service account, SPIFFE ID | Verify or re-fetch from platform |
| Replica/instance identity | One replica or one process instance | Pod UID, instance UUID | Fetch fresh or query current replica metadata |
| Process incarnation ID | One specific startup/restore run | UUID generated after restore | Generate newly per restore if incarnations must be distinguished |
| Consumer member ID | One member inside a consumer group | Broker-assigned or client-generated member ID | Re-register and receive a distinct member ID |
| Business entity ID | One business entity | Order ID, payment ID, account ID | Read or generate from an authoritative source; never reset per replica |
| Operation/idempotency ID | A retryable business request | Idempotency key | Keep stable across retries of the same operation |
| Fencing token | Resource ownership ordering | Monotonically increasing generation number | Acquire a fresh token from coordinator or storage |

For example, orders-api can be the shared service identity for all replicas. Each pod has its own pod UID. Each time the process restores inside a pod, it can generate a new process incarnation ID. When a request creates an order, the order ID must be issued by a durable business mechanism; it must never be generated from an instance ID or a snapshotted counter.

### 2.1. Stable service identity

Service identity is commonly used in configuration, routing, authorization policies, or service names. This value can be shared across replicas because it represents the same logical service.

Do not use the shared service identity as an instance ID. If logs or metrics record only orders-api, operations will struggle to tell which replica caused an error. Attach service identity alongside replica ID and process incarnation ID for diagnostics.

### 2.2. Replica identity

Replica identity distinguishes concurrently running replicas. The ID source can be:

- Metadata supplied by the orchestration platform, such as a pod or task UID.
- A UUID generated with a cryptographically secure random generator when the process restores.
- An ID issued by a coordinator and registered with a service registry.
- An identifier combining workload identity with system-managed incarnation information.

If using platform metadata, query the running replica's metadata after restore. Do not rely on a hostname or pod name recorded on the heap before checkpointing if the image may be deployed onto another replica.

### 2.3. Process incarnation ID

A replica may undergo multiple restores or restarts. When each process creation needs to be distinguished, use a process incarnation ID. This value is newly generated when the process enters a new incarnation.

An incarnation ID is useful for:

- Logs and distributed tracing.
- Per-process metrics.
- Correlating startup events.
- Detecting messages or heartbeats coming from an old process.
- Diagnosing transient overlap when an old replica and a new replica coexist.

Do not use an incarnation ID as a business ID that must stay stable across retries. A request retried after restore must still retain its original idempotency key.

## 3. Generating unique IDs per replica

### 3.1. Regenerating after restore

If the application needs a distinct random ID per incarnation, generate the ID during post-restore recovery, or during bootstrap of a new process before it is permitted to serve.

Simple example:

~~~java
import java.util.UUID;

public final class InstanceIdentity {
    private volatile String instanceId;

    public void initializeForCurrentProcess() {
        instanceId = UUID.randomUUID().toString();
    }

    public String getInstanceId() {
        String current = instanceId;
        if (current == null) {
            throw new IllegalStateException(
                    "Instance identity is not initialized");
        }
        return current;
    }
}
~~~

Do not initialize a unique ID once and freeze it into the checkpoint if the image may be restored into multiple replicas. Each replica must run initializeForCurrentProcess() within its own lifecycle.

UUID v4 offers very low collision probability when generated by a proper implementation. However, if the system requires strict uniqueness, ordering, or confirmation by a coordinator, use an authoritative ID issuer such as a database sequence, registry, or ID service. UUIDs do not replace unique constraints in databases.

### 3.2. Using platform metadata

In Kubernetes, pod name and pod UID have different scopes. A pod name can be reused after a pod is deleted; UID distinguishes a specific pod object. If replica identity is needed, use platform-issued metadata and query it from the running replica's environment.

Other platforms may provide a task ARN, machine ID, container ID, or workload identity. Determine:

- Is that value stable across the replica's lifecycle or does it change when the container is recreated?
- Is the value issued uniquely per replica or is it merely a service name?
- Is the metadata endpoint reachable after restore?
- Is the value updated if the replica is rescheduled onto another node?
- Can it be used in logs/metrics without exposing sensitive information?

If metadata cannot be queried immediately inside a callback, perform asynchronous bootstrap with explicit readiness gating. Do not use a stale value as though current identity had been verified.

### 3.3. Do not rely on heap counters to issue global IDs

A long variable on the heap can be snapshotted with the checkpoint. When multiple replicas restore, they can resume from the same value and issue duplicate IDs.

Risky example:

~~~java
private static long nextId = 1000;

public static synchronized long allocateId() {
    return ++nextId;
}
~~~

The synchronized modifier applies only within one JVM. It does not coordinate across different replicas. If each replica starts from nextId = 1000, both can issue 1001.

For business IDs, use:

- Database sequences or identity columns.
- UUID or ULID generated by an appropriate implementation.
- A distributed ID generation service.
- Partitioned ID ranges backed by a durable lease or allocation record.
- Unique constraints in storage to detect collisions.

Do not use a snapshotted local counter as the sole source of global IDs.

### 3.4. Refreshing random number generators

A checkpoint can preserve the state of random-number generator objects on the heap. If an ordinary PRNG has its internal state cloned, replicas may produce identical value sequences after restore. For security-sensitive data, never use a custom PRNG or fixed seed.

For security values, use SecureRandom and providers supported on your deployed JDK/platform. Check the CRaC documentation of your JDK and provider regarding entropy state handling across checkpoint/restore. If the application maintains its own generator or seed on the heap, implement regeneration or reseeding after restore per provider guidance.

Do not simply call setSeed() with the current time to achieve uniqueness. Timestamps can match across replicas and are not a source of cryptographic entropy. When strong uniqueness is required, combine random IDs with registration or unique constraints in an authoritative system.

## 4. Recreating local resources per replica

Local resources are objects or OS resources belonging exclusively to one process, container, or replica. If retained intact from a checkpoint, multiple replicas may contend for the same name or use stale state.

### 4.1. Temporary directories and local files

An application can create a temporary directory keyed by instance ID:

~~~java
Path workDirectory = Path.of(
        System.getProperty("java.io.tmpdir"),
        "orders",
        instanceId
);
Files.createDirectories(workDirectory);
~~~

After restore, create or re-verify the current replica's directory. Do not use a fixed path saved in the checkpoint if multiple replicas mount the same volume and write to it concurrently.

Lock files, PID files, Unix domain socket paths, spool files, and local caches must also be classified. If they are per-process resources, generate unique names or reopen them according to ownership rules after restore. Avoid deleting another replica's files merely because a filename matches an old checkpoint value.

### 4.2. Sockets and network ports

Do not assume a socket opened before checkpointing remains valid after restore. Close old sockets before checkpointing per library APIs. After restore, re-bind or reconnect so the OS allocates fresh network state.

If the application needs to listen on a dynamic port, bind port 0 and read the actual port after binding. If fixed ports are required, the orchestration platform must ensure each replica has its own endpoint or sits behind a proxy/load balancer. Never clone a local port or socket descriptor from a checkpoint image across multiple replicas.

### 4.3. Connection pools and clients

HTTP clients, JDBC pools, broker clients, and SDKs can hold connections, threads, executors, DNS caches, or sessions. Each replica must create its own owned clients/pools after restore. Never share a pool or client object by cloning heap state and assuming those connections are independent.

Before checkpoint:

- Stop accepting new requests or messages through the client.
- Drain in-flight operations.
- Commit or roll back transactions.
- Close pools/clients via official APIs.

After restore:

- Create new pools/clients.
- Load current endpoint configuration.
- Establish new connections and authenticate.
- Run health/readiness checks before accepting work.

### 4.4. Consumers and schedulers

A consumer group is usually a shared logical identity across replicas, whereas member ID is the individual identity of each member. After restore, rejoin the group so the broker assigns or confirms a fresh member identity. Do not continue using a snapshotted member ID if the broker requires each member to have a distinct ID.

Similarly, a scheduler may hold next-run state on the heap. Multiple replicas restored from the same snapshot might execute the same task simultaneously. For distributed tasks, use a distributed scheduler, fenced locks, or durable task-claiming mechanisms. If a task can run repeatedly, design it to be idempotent.

## 5. Distributed ownership: leases, locks, and leadership

One of the most severe risks is cloning ownership state. For instance, at checkpoint time, a process held a distributed lock and had field leader = true. When two replicas restore, both copies of that field can be true.

State on the heap is not proof that external systems still recognize ownership. A lease may have expired while the process was stopped and been granted to another replica. An old restored leader might operate concurrently with a new leader.

### 5.1. Do not restore leadership from a boolean

Do not use a checkpointed boolean variable to conclude a replica is the leader. After restore, re-register with the coordinator or election system and wait for confirmation.

For example, instead of:

~~~java
if (wasLeaderBeforeCheckpoint) {
    startLeaderTasks();
}
~~~

do:

~~~java
LeadershipLease lease = coordinator.acquireLeadership(instanceId);
if (lease.isGranted()) {
    startLeaderTasks(lease.fencingToken());
}
~~~

The second snippet illustrates the concept. Exact coordinator APIs depend on the distributed system in use. Acquisition must verify current ownership and return a fresh token/generation if supported.

### 5.2. Leases and fencing tokens

A lease is time-bounded ownership. If a process stops and fails to renew the lease, ownership can expire. After restore, the process must acquire a fresh lease.

A fencing token is a sequence number or generation issued by the coordinator that increases with each ownership grant. The storage system validates the token before accepting write operations. When an old replica wakes up with a stale token, storage rejects the write because that token is lower than the current token.

This is a vital safeguard because releasing a lock in a callback is insufficient if the process is killed abruptly or partitioned on the network. Fencing must be checked where side effects happen, not solely in heap variables.

### 5.3. Consumer groups and message processing

When multiple replicas restore together, they may simultaneously join a consumer group. This can be desirable if the broker distributes partitions to the new members. However, each member must be uniquely identified and message handling must have deduplication.

Do the following:

- Stop consumers and complete or return in-flight messages before checkpointing.
- Acknowledge messages only after business outcomes are durably persisted.
- Rejoin the group after restore and receive fresh member assignments.
- Never use a snapshotted consumer member ID as a fixed ID for all replicas.
- Use message IDs, idempotency keys, or an inbox table to prevent duplicate processing.
- Let the broker manage offsets and group membership via its official protocol.

### 5.4. Distributed sequences and counters

If a replica keeps a local counter to allocate sequences, the same checkpoint can clone that value across multiple replicas. The safe approach is requesting dedicated sequence ranges from an authoritative source or using database/broker-managed sequences. If pre-allocated ID ranges are used, each replica must receive non-overlapping allocation ranges with durable ownership tracking.

## 6. Credentials that must be reissued or re-verified

Credentials can reside on the heap: access tokens, refresh tokens, session cookies, API keys, client certificates, private keys, cloud credentials, or database credentials. When a checkpoint is cloned, replicas can inherit the same copy of credentials.

That can introduce risks:

- A token meant for a single session or client used concurrently by multiple replicas.
- Tokens expiring while the JVM is stopped.
- Revoked tokens whose heap copy persists.
- Credentials bound to one workload or instance used from another replica.
- Multiple replicas refreshing a single-use rotating refresh token, causing refresh races.
- A private key cloned across many instances, widening blast radius if one replica is compromised.

Not all credentials must differ. A workload identity may be shared under platform policy, yet tokens and private keys proving that identity must have appropriate lifecycles and scopes.

### 6.1. Workload identity and instance identity

Workload identity represents an authorized workload, such as a service account or SPIFFE ID. Multiple replicas of the same workload may be allowed to share the same logical identity.

Instance identity distinguishes each specific replica. It can come from a pod UID, task identity, or an ID generated when the process restores.

A design can combine:

- Shared service identity to determine application permissions.
- Distinct replica identity for logs, metrics, and member distinction.
- Short-lived credentials issued for the current replica's workload identity.
- Private keys generated or loaded per replica according to mTLS policy.

Do not use a static API key packaged inside a checkpoint image as the sole means of authenticating all replicas.

### 6.2. Access tokens and refresh tokens

Access tokens usually have short lifetimes. Refresh tokens may rotate or be bound to a client/session. If a token is snapshotted, after restore it may be expired or rejected by the authentication service.

After restore:

1. Determine the current workload identity.
2. Fetch a fresh token from the identity provider or secret/token service.
3. Validate audience, scope, issuer, and expiration.
4. Update clients to use the new token.
5. Open readiness only once authentication with required services succeeds.

If a refresh token is single-use or rotates on every refresh, never let multiple replicas share the same copy of the refresh token. Each replica needs its own credential issuance flow or a token broker with proper concurrency control.

### 6.3. Certificates and private keys

In mTLS, a client may require a certificate and private key. If the private key resides on the heap or in a file packaged into the checkpoint, every restored replica can hold the same key. That may violate policies requiring per-instance keys.

Options:

- Generate a dedicated key pair per replica after restore and request a certificate from the CA.
- Obtain keys from an HSM or secret manager based on current identity.
- Use short-lived workload certificates with automated rotation.
- Use a shared workload identity if policy permits, while tightly scoping permissions and certificate lifetimes.

Do not log private keys or bake them into images unnecessarily. If a checkpoint must contain secrets, protect the image like a credential store: encrypt at rest and in transit, restrict access permissions, enforce retention limits, and support revocation.

### 6.4. Database and broker credentials

A JDBC pool or broker client may store credentials inside configuration objects, sessions, or connections. After restore, do not merely reopen sockets; verify credentials remain valid and create fresh clients/pools from current configuration.

If the database password rotated while the JVM was stopped, the new pool must read the new password. If a broker uses OAuth or mTLS, the client must obtain fresh tokens/certificates and rejoin per broker protocol.

### 6.5. Secret managers and metadata services

In cloud environments or Kubernetes, credentials are commonly supplied via workload identity, projected service account tokens, metadata services, or secret managers. These sources can furnish fresh credentials for the current replica after restore.

Do not assume a token read from a file or environment before checkpointing remains the current token. Check:

- Was the token file rotated or its symlink updated?
- Is the metadata endpoint reachable in the restore environment?
- Does the replica's identity match the current workload?
- Can the secret manager issue distinct, time-bounded credentials?
- Must clients be recreated after secrets change?

Process environment variables are typically part of process state. If multiple replicas are spawned from the same process image, do not assume snapshotted env values will differ on their own. When per-replica information is needed, fetch it from platform-supported metadata/identity sources after restore.

## 7. Recreating resources and credentials with a CRaC Resource

A resource managing replica bootstrap can coordinate closing old resources prior to checkpoint and recreating per-replica state after restore.

General sequence:

### beforeCheckpoint()

1. Transition the replica to a quiescing state.
2. Stop accepting new requests and new work.
3. Drain workers, consumers, and transactions.
4. Close connection pools, clients, sockets, and local resources.
5. Release leases or locks if required by protocol.
6. Clear or invalidate references to sessions/credentials that cannot safely remain in use.

### afterRestore()

1. Read metadata for the current replica.
2. Generate a new replica ID and process incarnation ID if needed.
3. Create per-replica directories, socket paths, caches, and local resources.
4. Authenticate workload identity and obtain fresh credentials.
5. Build new SSLContext, clients, connection pools, or consumers.
6. Reacquire leases, locks, or member assignments.
7. Verify dependencies and enable readiness.

Do not start workers or accept traffic before identity and credential creation completes. If a recovery callback fails, the replica must stay not ready and apply a bounded retry policy.

### 7.1. Example Resource coordinating per-replica bootstrap

The following example illustrates a class managing resources that depend on replica identity. Providers are abstracted so the application can plug in Kubernetes metadata, cloud identity services, secret managers, or specific coordinators.

~~~java
import java.util.UUID;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ReplicaBootstrapResource implements Resource {
    private final ReplicaMetadataProvider metadataProvider;
    private final CredentialProvider credentialProvider;
    private final ReplicaResourceFactory resourceFactory;

    private volatile ReplicaResources resources;
    private volatile ReplicaIdentity identity;

    public ReplicaBootstrapResource(
            ReplicaMetadataProvider metadataProvider,
            CredentialProvider credentialProvider,
            ReplicaResourceFactory resourceFactory) throws Exception {
        this.metadataProvider = metadataProvider;
        this.credentialProvider = credentialProvider;
        this.resourceFactory = resourceFactory;

        initializeForCurrentReplica();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        closeReplicaResources();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        initializeForCurrentReplica();
    }

    private void initializeForCurrentReplica() throws Exception {
        ReplicaMetadata metadata = metadataProvider.currentMetadata();

        String processIncarnationId = UUID.randomUUID().toString();
        ReplicaIdentity newIdentity = new ReplicaIdentity(
                metadata.serviceName(),
                metadata.replicaId(),
                processIncarnationId
        );

        ReplicaCredential credential =
                credentialProvider.obtainFor(newIdentity);

        ReplicaResources newResources =
                resourceFactory.create(newIdentity, credential);

        // Publish identity/resources only after initialization succeeds.
        this.identity = newIdentity;
        this.resources = newResources;
    }

    private void closeReplicaResources() throws Exception {
        ReplicaResources current = resources;
        resources = null;
        identity = null;

        if (current != null) {
            current.close();
        }
    }

    public ReplicaIdentity identity() {
        ReplicaIdentity current = identity;
        if (current == null) {
            throw new IllegalStateException(
                    "Replica identity is not ready");
        }
        return current;
    }
}
~~~

Types ReplicaMetadataProvider, CredentialProvider, ReplicaResourceFactory, ReplicaMetadata, ReplicaIdentity, ReplicaCredential, and ReplicaResources are application-defined interfaces/models; they are not built-in JDK or CRaC classes. The example focuses on sequence: retrieve current metadata, generate incarnation ID, fetch credentials for that identity, build per-replica resources, and only then publish ready state.

In a real application, resource creation can fail at any step. Clean up partially created resources if a subsequent step fails, never publish identity before credentials are valid, and do not open readiness until mandatory dependencies are ready.

If metadataProvider or credentialProvider also has its own resource requiring callbacks, design an appropriate registration order. Underlying providers must be ready before ReplicaBootstrapResource. If the bootstrap resource depends on a secret manager client, that client must be created first and restored first.

### 7.2. Example provider interfaces

A simple contract might look like:

~~~java
public interface ReplicaMetadataProvider {
    ReplicaMetadata currentMetadata() throws Exception;
}

public interface CredentialProvider {
    ReplicaCredential obtainFor(ReplicaIdentity identity)
            throws Exception;
}

public interface ReplicaResourceFactory {
    ReplicaResources create(
            ReplicaIdentity identity,
            ReplicaCredential credential
    ) throws Exception;
}

public interface ReplicaResources extends AutoCloseable {
    @Override
    void close() throws Exception;
}
~~~

An application can implement the metadata provider using the Kubernetes Downward API or platform metadata APIs; the credential provider can use workload identity to obtain short-lived tokens or certificates. Do not hard-code a single provider into the lifecycle if the application must run across multiple environments.

## 8. Initialization order and readiness

A replica must not accept traffic the instant JVM restore finishes. Restore only recovers the process; it does not ensure the replica has valid per-replica identity, credentials, and resources.

A common sequence:

1. Initialize immutable, shareable configuration.
2. Query current replica metadata.
3. Generate instance/incarnation identity.
4. Fetch fresh credentials and validate expiration, scope, and audience.
5. Create local resources and clients.
6. Join service registry, broker group, or coordinator.
7. Acquire new leases/locks if required.
8. Verify dependency health.
9. Signal readiness and accept traffic.

Diagram:

~~~mermaid
flowchart TD
    A[Restore JVM] --> B[Read current replica metadata]
    B --> C[Generate replica/incarnation ID]
    C --> D[Obtain new credentials]
    D --> E[Create per-replica resources]
    E --> F[Register with broker/registry/coordinator]
    F --> G[Acquire lease and verify ownership]
    G --> H[Health check]
    H --> I{All required dependencies ready?}
    I -->|Yes| J[Readiness: accept traffic]
    I -->|No| K[Remain not ready and retry with limits]
    K --> H
~~~

Readiness must reflect actual serving capability. Liveness only tells whether the process is alive; it does not replace readiness. If credentials have not been issued or the replica has not joined the broker group, do not let the load balancer route business requests to the replica.

If some components can initialize asynchronously, separate mandatory dependencies from optional dependencies. Do not let an optional service make the entire application unready if architecture allows serving remaining features; equally, never signal ready while a critical business flow cannot yet operate.

## 9. Error handling and retries when establishing identity/credentials

After restore, services issuing metadata, credentials, or leases may not yet be ready. Common errors:

| Situation | Possible cause | Resolution |
|---|---|---|
| Metadata returns old replica ID | Application uses snapshotted or cached value | Query current metadata source after restore |
| Two replicas share the same instance ID | ID was generated before checkpoint and cloned | Generate new ID or use platform-issued ID |
| Expired token | Credential was snapshotted earlier | Fetch new token and verify expiry/audience |
| Refresh token rejected | Multiple replicas share a rotated refresh token | Issue per-replica credentials or use a concurrency-controlled token broker |
| Client certificate rejected | Stale key/certificate or wrong identity | Generate/load fresh key material and request cert for current identity |
| Lease not granted | Another replica holds it or coordinator unavailable | Retry with backoff; never reuse old leader state |
| Consumer rejected member ID | Member ID collides across replicas | Rejoin group with distinct member identity |
| Temp directory creation fails | Read-only volume or unsuitable permissions | Check mount/permissions; keep readiness closed |
| Resource partially initializes then fails | Later step fails while earlier resources stay open | Clean up in reverse order and retry safely |
| Two replicas write the same resource | Ownership stored solely on the heap | Use coordinator, lease, and storage-level fencing tokens |

Retries need timeouts, backoff, and jitter so multiple replicas do not stampede the identity provider or secret manager right after restore. If the credential service is failing, keep the replica not ready and emit clear operational signals.

Never log secrets, private keys, or tokens while diagnosing. You can log credential type, issuer, truncated expiration, request correlation ID, and error code without logging secret values.

## 10. Protecting checkpoint images containing sensitive data

A checkpoint can contain many heap objects, including tokens, passwords, private keys, session cookies, personal data, and request payloads. If the same image is cloned across multiple replicas, each replica can receive a copy of those values.

Treat a checkpoint image as a sensitive artifact:

- Encrypt images at rest and in transit per environment policy.
- Restrict read, write, download, and restore permissions on images.
- Allow only authorized workloads or pipelines to use images.
- Enforce retention periods and delete old images via secure procedures.
- Exclude long-lived credentials from images whenever fresh credentials can be obtained after restore.
- Rotate or revoke credentials that may have appeared in an image upon incident.
- Never log secrets in callbacks or during image creation.
- Track image versions and provenance to avoid restoring an old artifact with stale config or credentials.

If an image must contain secrets, assess the blast radius if the image is leaked or misused. A shared private key inside a checkpoint causes all replicas to share one secret; encrypting the image protects data at rest but does not make the key unique per replica after restore.

## 11. Common design mistakes

| Design | Risk | Adjustment |
|---|---|---|
| Generating static INSTANCE_ID before checkpoint | All replicas may share the same ID | Regenerate in post-restore lifecycle or fetch from replica metadata |
| Using snapshotted hostname as replica identity | Hostname may belong to the image-builder replica | Query current metadata |
| Keeping leader=true on the heap | Multiple replicas think they are leader | Acquire fresh lease/election and use fencing tokens |
| Sharing one refresh token across all replicas | Rotation or single-use semantics cause conflicts | Per-replica credentials or token broker |
| Keeping client private key in checkpoint | Multiple replicas share the same private key | Generate separate keys or use identity service/HSM |
| Using static counter to generate global IDs | Replicas continue from the same counter | Database sequence or ID service |
| Creating temp files with fixed names | Replicas overwrite or delete each other's files | Per-replica directory/filename |
| Restoring old sockets/connection pools | Peer may have closed or credentials expired | Close before checkpoint, create new client/pool |
| Using fixed consumer member ID | Broker rejects or replicas contend | Rejoin group and receive distinct member identity |
| Opening readiness immediately after JVM restore | Replica lacks credentials or dependencies | Signal readiness after bootstrap and health checks |
| Using a new idempotency key per retry | One operation may execute multiple times | Keep key stable for the same operation |
| Using timestamp as sole ID source | Multiple replicas can generate simultaneously | Use UUID, ID service, or unique constraint |

## 12. Testing multiple replicas from the same checkpoint

Testing a single restored process does not catch cloning bugs. Use the same checkpoint to launch multiple replicas in a test environment and observe concurrent behavior.

A general test scenario:

1. Start the application, create a checkpoint once shared configurations are loaded.
2. Use the same checkpoint image to restore at least two replicas.
3. Collect service identity, replica identity, and process incarnation ID from each replica.
4. Confirm replica identity/incarnation ID differ as required.
5. Confirm shared configuration and service identity remain consistent.
6. Confirm each replica creates its own local resources and connection pools.
7. Verify credentials are issued per policy, tokens have valid expirations, and private keys are not unintentionally shared.
8. Confirm consumer groups have distinct members and the broker distributes work properly.
9. Let a replica's lease expire and restore again; confirm it does not reuse old leadership.
10. Have multiple replicas execute business operations concurrently; confirm business IDs and idempotency do not collide or mis-duplicate.
11. Make the identity provider or secret manager temporarily unavailable; confirm readiness stays closed and retries are bounded.
12. Verify logs, metrics, and traces distinguish replicas.

### 12.1. Test matrix

| Item | Test condition | Expected result |
|---|---|---|
| Replica identity | Restore two replicas from the same image | Distinct IDs |
| Service identity | Restore multiple replicas of the same workload | Same service identity per config |
| Process incarnation | Restore the same replica again | New incarnation if required by policy |
| Temporary directory | Two replicas mount the same volume | Separate paths, no overwriting |
| Socket/port | Two replicas run concurrently | Fresh sockets created, no old descriptors; ports allocated distinctly |
| Credential | Concurrent restore of multiple replicas | Valid scoped credentials without conflicts |
| Certificate rotation | CA/certificate changes while JVM stopped | Client loads fresh key/trust material per policy |
| Lease/leader | Old lease expires before restore | Replica must reacquire; stale token cannot write |
| Consumer group | Multiple replicas join together | Proper member identities and assignments |
| Business ID | Multiple replicas insert records concurrently | No duplicates thanks to ID issuer/constraints |
| Readiness | Secret manager fails | Replica stays unready with bounded retries |
| Observability | Requests pass through multiple replicas | Logs/traces distinguish instances |

### 12.2. What to record

In a test environment, you can log:

- Service identity.
- Replica ID and process incarnation ID.
- Restore timestamp and readiness-open timestamp.
- Credential type, issuer, and expiry (never log the token).
- Certificate version or public fingerprint if appropriate.
- Lease generation/fencing token.
- Broker-assigned consumer member ID.
- Health check results and bootstrap errors.

Never write private keys, secrets, passwords, or access tokens into logs or test reports.

## 13. Recommended deployment workflow

A workflow can be divided into three phases.

### When preparing the checkpoint

1. Identify which fields and resources may be shared across replicas.
2. Stop accepting new work and drain workers.
3. Commit or roll back transactions.
4. Close connections, sockets, consumers, and clients via supported APIs.
5. Release leases/locks if required by protocol.
6. Clear or invalidate references to credentials/sessions that should not be reused.
7. Create the checkpoint only after resources reach a safe state.

### When restoring each replica

1. Query current replica metadata.
2. Generate a new replica/incarnation identity or verify the platform-issued identity.
3. Create per-replica local resources and endpoints.
4. Obtain short-lived credentials matching the workload/replica identity.
5. Recreate SSLContext, clients, connection pools, consumers, and schedulers.
6. Re-register service, join groups, and acquire leases.
7. Verify ownership, health, and readiness.

### While the replica is running

1. Renew or refresh credentials according to lifecycle.
2. Monitor leases and fencing tokens.
3. Obtain business IDs from authoritative sources.
4. Include replica identity in logs, metrics, and traces.
5. At the next checkpoint, repeat the drain and resource-release sequence.

## 14. Design principles

- The same checkpoint can spawn multiple replicas with identical initial heap values.
- Distinguish service identity, workload identity, replica identity, process incarnation ID, and business ID.
- Retain only values genuinely meant to be shared by design.
- Regenerate per-replica IDs after restore or fetch IDs from platform metadata.
- Do not use local heap counters as a source of global IDs.
- Check PRNG/SecureRandom state per JDK and provider; do not use fixed seeds or custom PRNGs for security.
- Recreate directories, sockets, connection pools, consumers, and schedulers belonging to each replica.
- Do not restore leadership or leases from a heap boolean; reacquire and use fencing tokens.
- Obtain tokens/certificates from the identity provider or secret manager per policy after restore.
- Minimize long-lived credentials and private keys in checkpoints.
- Open readiness only after the replica's identity, credentials, and dependencies are ready.
- Test multiple concurrent replicas from the same checkpoint image.

CRaC can reuse shared JVM initialization, yet it cannot automatically differentiate identities of replicas spawned from the same snapshot. The application must proactively generate or verify per-replica identity, recreate local resources, obtain policy-compliant credentials, and reacquire distributed ownership after restore. Once those steps finish before readiness, multiple replicas can share checkpoint benefits while operating as independent instances.