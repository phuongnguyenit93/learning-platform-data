# Process ID, hostname, and replica identity after restore

When a Java application is restored from a CRaC image, objects in the heap return to the saved state. Environment-identifying values at checkpoint time can also remain in memory: PID, read hostname, container metadata, IP address, node name, or a UUID generated when the application started.

These values do not have the same lifecycle. A PID is the identifier of a process within an operating system scope; a hostname describes the machine name or network environment; a replica ID describes a logical replica of a service; and a process incarnation ID identifies a specific run. If a temporary value is mistakenly used as a persistent identifier, logs, metrics, locks, and service discovery may point to the wrong process after restore.

The design should clearly distinguish:

- **Service identity**: the service or application name, usually stable across multiple runs.
- **Replica identity**: the logical replica identifier assigned or configured by the deployment platform.
- **Process identity**: the current PID within the operating system namespace.
- **Process incarnation identity**: a new UUID for each fresh JVM startup or restore.
- **Host identity**: the hostname or node/container identifier in the running environment.
- **Checkpoint identity**: the identifier of the checkpoint image or artifact version that produced the state.
- **Restore attempt identity**: the identifier of a specific restore attempt, useful when retrying restore multiple times.

These concepts should not be combined into a single string such as pid@hostname. They answer different questions and can change at different times.

## 1. What is a PID and why can't it be used as a long-lived identifier?

A PID (Process ID) is the number that the operating system assigns to a process. On Linux, a PID is scoped by a PID namespace. Inside a container, the PID that the application sees may differ from the PID of that process on the host.

Java 9 and later provides ProcessHandle.current().pid() to obtain the PID of the current JVM:

~~~java
long pid = ProcessHandle.current().pid();
System.out.println("Current process PID: " + pid);
~~~

A PID is useful for:

- Finding the process when viewing logs and operating system monitoring tools.
- Associating a CPU/RSS measurement with a specific process.
- Supporting administrative or diagnostic operations within the same environment.
- Identifying the process holding a socket or file within a namespace.

A PID is not a global or persistent identifier:

- A PID can be reused after a process terminates.
- The PID seen inside a container may differ from the PID on the host.
- Upon restore, the PID may be preserved or assigned differently depending on how the runtime, CRIU, and namespaces are configured.
- Moving an image to another environment does not guarantee that the process will have the same PID.
- A PID does not uniquely identify an application version or a logical replica.

Therefore, do not store the PID in a database as a long-term key, do not use the PID as an idempotency key, and do not assume the PID before checkpoint is still the PID after restore.

### Reading the PID at the time it is needed

If logs need the PID, obtain the current PID when logging or create a runtime snapshot after restore. Avoid reading the PID once at startup and keeping it in static final long PID, because that value is kept in the checkpoint heap and may be stale after restore.

~~~java
public final class ProcessInfo {

    private ProcessInfo() {
    }

    public static long currentPid() {
        return ProcessHandle.current().pid();
    }
}
~~~

Call ProcessInfo.currentPid() when it is necessary to record the current process. If it is necessary to correlate the PID with the host PID, information from the platform/container runtime must be used; the PID returned by Java does not itself provide the PID outside the namespace.

## 2. Hostname describes the environment, not a unique identifier

Hostname is the machine name or host name used by the operating system and the name resolution system. In Java, the hostname can be obtained in a simple way:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

public final class HostInfo {

    private HostInfo() {
    }

    public static String currentHostName() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException failure) {
            return "unknown";
        }
    }
}
~~~

This call depends on the hostname configuration and name service of the environment. It may not return the name that the operations team expects, may be slow when DNS or network configuration has issues, and is not always the canonical name.

A hostname can:

- Stay the same when a container or process is restored in the same environment.
- Change when an instance is created on a different node.
- Be shared by multiple processes on one machine.
- Collide or change according to the naming rules of the platform.
- Not accurately reflect the IP address that clients can reach.

Therefore, the hostname is suitable for assisting diagnostics and grouping logs, but should not be the unique key for a process or a replica.

### Do not infer network addresses from hostname

Hostname and IP address are two different pieces of data. One hostname can resolve to multiple addresses, DNS can change after failover, and a container can receive a new IP. If the application needs an address to bind a socket or publish an endpoint, obtain it from appropriate network configuration/service discovery, and verify that the listener has bound successfully.

Do not call InetAddress.getLocalHost() as a database or network readiness check. It only reflects host information according to resolver configuration; it does not prove an external dependency is reachable.

## 3. Distinguishing service, replica, and process incarnation

In multi-replica deployments, a service usually has multiple instances serving concurrently. Identity is needed at multiple layers.

| Identifier | Example | Lifecycle | Used for |
|---|---|---|---|
| Service ID | orders-api | Stable across deployments | Grouping logs, metrics, and configuration |
| Replica ID | orders-api-2 or ID assigned by orchestrator | Follows the logical replica lifecycle | Distinguishing replicas of the same service |
| Process incarnation ID | New UUID on each run/restore | A specific run | Distinguishing incarnations in logs and tracing |
| PID | 4217 | Per process within the namespace | Operating system diagnostics |
| Hostname | node-a or pod name | Follows the host environment | Diagnostics and deployment partitioning |
| Checkpoint ID | release-2026-11-13-01 | Follows the checkpoint artifact | Tracing the origin of the image |
| Restore attempt ID | UUID for each restore | A single restore attempt | Error analysis and retries |

### Replica ID is not necessarily process ID

A logical replica can go through multiple process incarnations:

1. Replica orders-api-2 starts for the first time with PID 120 and incarnation A.
2. The application creates a checkpoint.
3. The JVM is restored with PID 120 or a different PID, depending on the environment; the new incarnation is B.
4. The logical replica can still be orders-api-2, if the platform restores that exact replica.

If the image is restored into a new pod, the replica ID may change according to the new pod or instance. If the system uses a StatefulSet ordinal or a logical replica key, it can remain unchanged across pod recreation. This policy belongs to the deployment platform, not decided automatically by CRaC.

### Process incarnation ID

An incarnation ID is a UUID newly generated each time the application starts fresh or is restored. It helps distinguish:

- Pre-checkpoint logs and post-restore logs.
- Two processes running concurrently on one host.
- A replica that has undergone multiple restores.
- One successful restore from another restore from the same image.

If a UUID is generated before checkpoint and stored in the heap, after restore that UUID is still restored. When it is necessary to identify the new run, a new UUID must be generated in afterRestore().

## 4. Why can identifiers in the heap become stale?

A checkpoint saves the object graph at a point in time. A final or static field containing a PID, hostname, or container ID can be restored with its old value.

For example:

~~~java
public final class RuntimeIdentity {
    public static final long PID = ProcessHandle.current().pid();
    public static final String HOST =
            HostInfo.currentHostName();
}
~~~

The values above are computed when the class is initialized. If the class was already initialized before checkpoint, they may continue to exist after restore. They should not be used as current runtime information.

Common cases:

- An old PID kept in an object or static field.
- A hostname read once and then cached.
- A process UUID generated at startup and kept in the heap.
- A container ID or pod name read from an environment variable before checkpoint.
- An IP address or endpoint resolved and then cached in a client.
- A thread-local or singleton holding old node information.

Not every value is guaranteed to change after restore. The problem is that the application cannot assume by default that they are still valid. It is necessary to classify which fields are stable configuration, which must be refreshed, and which are only used for recording history.

### System.getenv and system properties

System.getenv() returns the environment variables of the process. Java does not provide a portable API to modify an existing environment map or request it to re-read a new environment from outside. If a value is restored from the image, do not assume it updates automatically just because the container or orchestrator changed external configuration.

System.getProperty() returns the current system properties in the JVM. Values stored in the heap or configured at launch time may also fail to reflect the new configuration of a different environment.

If dynamic identity from the platform is needed, query a supported source after restore or receive information through a provider updated in a controlled manner. Do not use an environment variable stored in the heap as proof that the process is currently on the same host or pod.

## 5. Designing an identity provider for CRaC

Instead of letting multiple services independently read PID, hostname, and UUID, create a unified identity management component. This component:

1. Generates an incarnation ID when the JVM starts fresh.
2. Registers as a CRaC Resource.
3. After restore, reads the current PID and hostname as needed.
4. Obtains the replica identity from a configuration or platform provider.
5. Generates a new incarnation ID for the restore.
6. Publishes an immutable snapshot for other components to read.

The following example uses Java records (Java 16 and later). ReplicaIdProvider is an application abstraction; it can read a configured logical ID or obtain the current ID from the deployment platform.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

public final class RuntimeIdentityResource implements Resource {

    @FunctionalInterface
    public interface ReplicaIdProvider {
        String currentReplicaId() throws Exception;
    }

    public record IdentitySnapshot(
            String serviceId,
            String replicaId,
            String incarnationId,
            long pid,
            String hostName,
            Instant observedAt,
            String phase) {
    }

    private final String serviceId;
    private final ReplicaIdProvider replicaIdProvider;
    private final AtomicReference<IdentitySnapshot> current =
            new AtomicReference<>();

    public RuntimeIdentityResource(
            String serviceId,
            ReplicaIdProvider replicaIdProvider) throws Exception {
        this.serviceId = serviceId;
        this.replicaIdProvider = replicaIdProvider;
        current.set(capture("startup"));
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        // Keep the old snapshot to trace the origin of the checkpoint.
        // Do not create a new incarnation at checkpoint time.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // This is a new process incarnation.
        current.set(capture("restore"));
    }

    public IdentitySnapshot current() {
        IdentitySnapshot snapshot = current.get();
        if (snapshot == null) {
            throw new IllegalStateException("Runtime identity is not initialized");
        }
        return snapshot;
    }

    private IdentitySnapshot capture(String phase) throws Exception {
        String replicaId = replicaIdProvider.currentReplicaId();
        if (replicaId == null || replicaId.isBlank()) {
            throw new IllegalStateException("Replica ID is unavailable");
        }

        return new IdentitySnapshot(
                serviceId,
                replicaId,
                UUID.randomUUID().toString(),
                ProcessHandle.current().pid(),
                resolveHostName(),
                Instant.now(),
                phase
        );
    }

    private static String resolveHostName() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException failure) {
            return "unknown";
        }
    }
}
~~~

In the example:

- serviceId is the stable identifier of the application.
- replicaIdProvider determines the logical replica identifier according to the environment.
- incarnationId is newly generated in the constructor and renewed in afterRestore().
- PID is read at the time the snapshot is created.
- Hostname is obtained from the environment at capture time; if it cannot be determined, the diagnostic value unknown is used.
- AtomicReference publishes an immutable snapshot for other threads to read consistently.

The example uses InetAddress.getLocalHost() for illustration. In systems with strict hostname requirements or where hostname queries can block, replace it with a platform-appropriate HostIdentityProvider and set a timeout. Hostname is not a mandatory dependency of the application; hostname resolution failure usually should not prevent the database or server from recovering.

If the replica ID is mandatory for routing or ensuring uniqueness, failure to obtain the ID must keep the application unready. If the ID is only used to enrich logs, an intentional fallback value can be used and it should be recorded that the metadata is incomplete.

### Fresh startup and restore

The constructor runs when the JVM starts fresh and creates the first incarnation. On restore, the resource object is restored from the heap so it is not recreated by the constructor; CRaC calls afterRestore() on the registered resource. Therefore, generating a new UUID in afterRestore() is necessary to mark the new run.

Do not register the same resource again in afterRestore(). The resource was already registered before checkpoint and the registration state belongs to the lifecycle managed by CRaC.

## 6. Obtaining identity from containers and orchestrators

In container environments, hostname, container ID, pod name, and pod UID are different concepts.

| Value | Meaning | Notes on restore |
|---|---|---|
| Container hostname | Hostname seen inside the container | Can be configured; uniqueness is not guaranteed |
| Container ID | Container ID assigned by the runtime | No portable Java API; may change when a new container is created |
| Pod name | Pod name in Kubernetes | Can be preserved under StatefulSet rules or change when replacing a pod |
| Pod UID | Unique ID of a pod incarnation | A new pod has a new UID even if the name may be the same |
| Node name | Name of the node running the pod | May change when the pod is scheduled to another node |
| Host PID | PID on the host, outside the PID namespace | Differs from the PID seen by the JVM inside the container |

If the application needs the Pod UID, that value can be injected into the container using the Kubernetes Downward API. If the node name or pod name is needed, they can also be provided through a similar mechanism. However, values injected into the environment at container startup will not automatically change inside a checkpointed process when the pod or external environment changes.

For information that needs to be updated after restore, use a dynamic source supported by the platform, such as an internal API or a file mounted and updated via an explicit mechanism. Distinguish static configuration files from projected volumes that can be updated; mount method and update timing depend on the platform.

### Restore in the same pod and restore into a new pod

**Restore in the same pod/container**: pod UID, container ID, or hostname usually still belong to the same environment. PID still must be re-read because it depends on the restore mechanism and namespace.

**Restore into a new pod/container**: the new pod UID and container ID may differ. The image may contain environment variables, paths, and system state from the checkpoint-creating environment. Image portability depends on CRIU, kernel, namespaces, mounts, and runtime; do not assume by default that an image can be moved arbitrarily to another pod.

If the platform supports restoring into a new replica, the application needs to obtain the new identity from the platform after restore and update service discovery. Do not take the old Pod UID from a field in the heap as the ID of the new pod.

## 7. Host ID and machine ID

On some Linux systems, /etc/machine-id provides a system identifier. This is not a portable Java API and should not be treated as an application identifier.

In container environments:

- The file may not exist or may be mounted from the host.
- Multiple containers may see the same machine ID.
- Images/containers may be configured differently.
- The value may be sensitive regarding privacy and infrastructure information.

Do not use machine ID as a public instance ID, do not send it to clients, and do not include it in external telemetry without a valid reason and appropriate policy. If node identity is needed, use the node identifier assigned by the platform and only publish it within the necessary scope.

## 8. RuntimeMXBean and JVM identification APIs

The runtime name can be obtained via:

~~~java
import java.lang.management.ManagementFactory;

String runtimeName =
        ManagementFactory.getRuntimeMXBean().getName();
~~~

Some JVMs return a string in the form pid@hostname. However, this format is an implementation detail, not a standard format for applications to parse. Do not split the string on the @ character and use the two parts as an official identity.

Points to remember:

- RuntimeMXBean.getName() is the runtime name provided by the JVM; the format is not guaranteed to be the same across all implementations.
- The value may reflect information generated when the runtime started and is not an API for refreshing identity after CRaC restore.
- RuntimeMXBean.getStartTime() and getUptime() describe time according to the runtime; do not use them instead of a restore attempt ID.
- ProcessHandle.current().pid() is more appropriate for reading the current PID.
- Hostname should be obtained through a separate environment-specific provider if refresh is needed.

Example of logging diagnostic information:

~~~java
import java.lang.management.ManagementFactory;

public final class RuntimeDiagnostics {

    private RuntimeDiagnostics() {
    }

    public static void print() {
        long pid = ProcessHandle.current().pid();
        String runtimeName =
                ManagementFactory.getRuntimeMXBean().getName();

        System.out.println("pid=" + pid);
        System.out.println("runtimeName=" + runtimeName);
    }
}
~~~

Treat runtimeName as a log field supporting investigation. Do not use it as a database key, cache key, or resource name that needs to persist across multiple restores.

## 9. Which identifiers should be kept and which need to be regenerated?

A practical rule is to classify by lifecycle:

| Data | Keep across restore? | How to handle |
|---|---|---|
| Service ID | Yes | Read from stable deployment configuration |
| Logical replica ID | Depends on platform policy | Keep if same replica; refresh if restoring into a new replica |
| Process incarnation ID | No | Generate a new UUID in afterRestore() |
| PID | No | Read with ProcessHandle.current().pid() |
| Hostname | Not by default | Refresh via provider if needed |
| Container ID / Pod UID | Depends on environment | Obtain from platform; do not infer from PID or hostname |
| Checkpoint ID | Yes | Keep to trace the created image |
| Restore attempt ID | No | Generate a new ID for each restore |
| Request ID | Per request | Generate or propagate per request, do not use as process identity |
| Idempotency key | Per business operation | Keep per transaction; do not regenerate just because the process restores |

### Checkpoint ID and incarnation ID are different

Checkpoint ID identifies the created image. If the same image is restored multiple times, the checkpoint ID may be the same.

Incarnation ID identifies a specific run. Each restore from the same image should generate a new incarnation ID. When logging two restores, the pair checkpointId + incarnationId helps identify both the image source and the current run.

Restore attempt ID can be generated by the orchestrator or the application. If the application needs to track restore attempts that failed before the process could run, an ID assigned by the orchestrator is usually more suitable because callbacks might not yet be invoked when a restore fails very early.

## 10. Using identity in logs and tracing

Identifiers should be attached to logs in a structured manner to correlate events:

~~~text
service=orders-api
replica=orders-api-2
incarnation=9d2a...
pid=4217
host=node-a
checkpoint=release-2026-11-13-01
phase=afterRestore
event=database_ready
~~~

In systems with structured logging, each field should be a separate attribute rather than concatenated into a string that is hard to query.

Some notes:

- PID and hostname assist diagnostics, but do not replace incarnation ID.
- Incarnation ID helps group logs of a single run.
- Replica ID helps track a logical replica across multiple incarnations.
- Checkpoint ID helps correlate incidents with the artifact that created the state.
- Request ID and trace ID must continue to be propagated according to the tracing protocol, not replaced by process identity.

Do not put PID, hostname, or incarnation ID into high-cardinality metric labels if the metrics system is not designed for that. With Prometheus or similar systems, each new incarnation can create additional time series; limit retention time, use appropriate metrics, or keep detailed identity only in logs/tracing.

## 11. Using identity in caches, locks, and service discovery

### Cache key

Do not use PID or hostname as a cache key for business data that needs to persist across restore. PIDs can change or be reused; hostnames can be shared. If a cache is local to the process, incarnation ID can be used to isolate data valid only within a single run.

If a cache stores data that needs to be kept across restore, the key must be based on an appropriate business or service/tenant identifier, independent of process identity.

### Distributed lock and lease

Do not use a standalone PID as the owner ID for a distributed lock. A PID can be reused and cannot distinguish two runs. Use a random owner token or incarnation ID, accompanied by a time-limited lease and a fencing token mechanism if the system requires protection against stale owners.

After restore, do not assume a lease granted before checkpoint is still valid. Verify or acquire a new lease. A process may restore heap state while an external lease has already expired and been granted to another process.

### Service discovery

Service discovery usually requires a reachable address, port, health status, and replica identity. After restore:

1. Read the current listener address/port.
2. Verify that the listener is active.
3. Obtain the replica identity appropriate for the platform.
4. Register or refresh the endpoint in service discovery.
5. Only transition the endpoint to the healthy state after readiness succeeds.

Do not publish an old hostname or old IP just because they still remain in a restored object.

## 12. Be careful with static fields, singletons, and cached identity

Some ways of writing easily produce stale data:

~~~java
public final class NodeMetadata {
    public static final long PID =
            ProcessHandle.current().pid();
    public static final String HOST =
            HostInfo.currentHostName();
    public static final String INSTANCE_ID =
            java.util.UUID.randomUUID().toString();
}
~~~

After checkpoint, the values above may be restored as-is. If current metadata is needed, use a refreshable provider:

~~~java
public interface RuntimeIdentityProvider {
    RuntimeIdentityResource.IdentitySnapshot current();
}
~~~

Services should access the provider when runtime information is needed instead of copying PID or hostname into their own fields. If a snapshot must be stored in a log or event, clearly record the observation timestamp and the accompanying incarnation ID.

Not every static field needs to be refreshed. Constants such as service name, protocol version, or module name can remain stable. What must be avoided is caching a process/host-dependent value and using it as current data after restore.

## 13. Testing identity after restore

A useful test should compare the snapshot before checkpoint with the snapshot after restore.

### Basic scenario

1. Start a fresh application.
2. Record service ID, replica ID, incarnation ID, PID, and hostname.
3. Create a checkpoint.
4. Restore the image in the target environment.
5. In afterRestore(), create a new snapshot.
6. Confirm that the new incarnation ID differs from the pre-checkpoint ID.
7. Confirm that the PID is re-read from ProcessHandle.current().
8. Verify the replica ID according to environment policy: kept unchanged if same replica, changed if restored to a new replica.
9. Verify that the hostname reflects the current environment or is recorded as unknown if unresolvable.
10. Check that logs, tracing, and service discovery use the new snapshot.

Do not set an expectation that the PID must be different or must be the same. The result depends on the restore method and namespace. Check the important thing: that the application reads the current PID instead of trusting a value stored in the heap.

### Additional cases

| Scenario | What to verify |
|---|---|
| Restore in the same container | Replica/host metadata may stay unchanged; incarnation ID must be new |
| Restore in a new pod | Pod UID/replica identity is obtained from the target environment |
| PID namespace | PID inside the container is distinguished from PID on the host |
| Unresolvable hostname | Application still recovers if hostname is only diagnostic metadata |
| Replica ID provider unreachable | Keep readiness false if the ID is mandatory for routing |
| Multiple restores from the same image | Each run has a new incarnation ID, checkpoint ID may stay the same |
| Logs after restore | Do not use PID/hostname cached before checkpoint |
| Distributed lock | Old lease is verified or newly acquired; owner token is not reused |

Testing must run through an actual checkpoint/restore. Calling a method that generates a new UUID directly only tests Java code; it does not prove that CRaC restored the resource and invoked callbacks in the proper lifecycle.

## 14. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| PID is the unique identifier of an application. | PID only identifies a process within a namespace scope and can be reused. |
| PID after restore is guaranteed to stay the same. | PID depends on runtime, CRIU, and namespace; it must be re-read. |
| Hostname is always unique. | Multiple processes can share a hostname; hostname can change or be unresolvable. |
| RuntimeMXBean.getName() always has the form pid@hostname. | The format is an implementation detail and should not be parsed as identity. |
| A UUID generated before checkpoint is the ID of the process after restore. | That UUID is kept in the heap; a new incarnation ID must be generated in afterRestore(). |
| Pod name is the Pod UID. | Pod name and UID are two different values; a new pod has a new UID. |
| System.getenv() updates automatically after restore. | Process environment does not automatically re-read new values from the orchestrator. |
| Hostname can be used as distributed lock owner. | Use an appropriate owner token/incarnation ID and lease/fencing. |
| Checkpoint ID and restore ID are the same. | Checkpoint ID identifies the image; restore/incarnation ID identifies a run created from the image. |

## 15. Implementation checklist

### Identity classification

- [ ] Service ID is stable and does not depend on PID.
- [ ] Replica ID has a clear source from configuration or the orchestrator.
- [ ] Process incarnation ID is newly generated for each startup/restore.
- [ ] PID is read using ProcessHandle.current().pid() when needed.
- [ ] Hostname is used only as diagnostic metadata, not as a unique key.
- [ ] Checkpoint ID and restore attempt ID are distinguished.

### CRaC lifecycle

- [ ] The identity provider is registered as a Resource before checkpoint.
- [ ] afterRestore() creates a new runtime snapshot.
- [ ] PID/hostname are not held in static final as current data.
- [ ] Resource is not registered repeatedly in afterRestore().
- [ ] Mandatory identity is verified before opening readiness.

### Platform and operations

- [ ] Distinguish PID inside the container from PID on the host.
- [ ] Distinguish container ID, pod name, pod UID, and node name.
- [ ] Do not assume environment variables are refreshed automatically.
- [ ] Service discovery uses the current address and replica identity.
- [ ] Distributed locks do not rely on a standalone PID or hostname.
- [ ] Logs include appropriate service, replica, incarnation, and checkpoint IDs.
- [ ] Metrics do not create unnecessary high cardinality.
- [ ] Tested restore in the same container and expected target environment.

In CRaC, memory restored from an image may contain identifiers created before checkpoint. PID and hostname need to be treated as runtime information that can change; replica ID must follow platform policy; process incarnation ID needs to be regenerated in afterRestore(). When separating these lifecycles, the application can log accurately, manage locks safely, and register the right endpoints after restore.