# Refreshing Identity When Restoring Multiple Replicas from One Image

A CRaC checkpoint saves the state of a Java process at the time the image is created. If the same checkpoint is used to restore multiple instances, each instance starts with a copy of the heap and the objects that already existed in the image. This can include `static` fields, singletons, generated UUIDs, hostnames, client IDs, leader flags, counters, lease metadata, and the state of client libraries.

If the application continues to use those values as if they belonged exclusively to the current instance, multiple replicas can claim the same identity. Consequences can include the service registry overwriting endpoints, metrics being merged, message consumers using duplicate client IDs, multiple replicas thinking they are the leader, or instances using the same expired lease.

When restoring multiple replicas from one image, it is necessary to distinguish the **stable identity of the service** from the **unique identity of each instance and each run**. Each restored process must receive a new incarnation ID, re-read current platform information, acquire its own lease/session, and register a new endpoint before accepting traffic.

## 1. Why Can Replicas Have Duplicate Identities?

Suppose an application generates an ID at startup:

```java
public final class InstanceInfo {
    public static final String INSTANCE_ID =
            UUID.randomUUID().toString();

    private InstanceInfo() {
    }
}
```

When the application starts for the first time, the class is initialized and `INSTANCE_ID` receives a value. If a checkpoint is created after that point, this value is in the saved heap state.

When the same checkpoint is restored into three processes, all three replicas can start with the same `INSTANCE_ID` value. `static final` does not cause the value to be regenerated; neither constructors nor static initializers run again just because the process is restored.

```text
Checkpoint generation 42
  INSTANCE_ID = "instance-a7"
          |
          +--------------------+--------------------+
          |                    |                    |
       Restore A            Restore B            Restore C
          |                    |                    |
   INSTANCE_ID=a7       INSTANCE_ID=a7       INSTANCE_ID=a7
```

The same thing can happen with:

- Hostname, IP, or port read before checkpoint.
- `client.id` of a message broker or HTTP client.
- `isLeader` flag, lock token, or lease ID.
- Counters used as sequence numbers or global IDs.
- Random generator/PRNG whose internal state is in the heap.
- Session ID, TLS/session context, or temporary credentials.
- Registration ID and heartbeat metadata in the service registry.

A checkpoint does not know whether it will be restored once or cloned into hundreds of instances. Therefore, any value that is only valid for a single running process must be reconsidered after restore.

## 2. Distinguishing Service Identity, Instance Identity, and Incarnation Identity

Do not lump all types of identities into a single `id` field. Each type has a different lifecycle and scope.

| Identity Type | Examples | Is It the Same Across Replicas? | When Does It Change? |
|---|---|---|---|
| Service identity | `orders-api`, `billing-worker` | Yes | When renaming the logical service |
| Release/checkpoint identity | `orders-2026.11.13`, checkpoint generation 42 | Yes within the same release | On a new build/release/checkpoint |
| Instance identity | Pod UID, VM instance ID, worker ID | No | When the platform creates a new instance |
| Process incarnation ID | UUID for one process run/restore | No | Each time the process is launched or restored |
| Lease/fencing token | Lease epoch 1087 | No; issued by the coordination system | Each time lease ownership is acquired |
| Request/trace identity | Request ID, trace ID | No; per request/trace | Each new request or trace |

For example, three replicas of `orders-api` can share `serviceName` and `releaseId`, but need different `instanceId`s. If a pod restores the process multiple times, the pod's `instanceId` may stay the same, but `incarnationId` should change to distinguish the new process from the old one.

A clear data structure:

```java
import java.time.Instant;

public record RuntimeIdentity(
        String serviceName,
        String releaseId,
        String instanceId,
        String incarnationId,
        Instant createdAt) {
}
```

`serviceName` and `releaseId` can come from the immutable configuration of the release. `instanceId` should come from the running platform or an authoritative identity provider. `incarnationId` is newly generated for each process restore. Do not store a complete `RuntimeIdentity` in the checkpoint and reuse it intact across all replicas.

## 3. Refreshing Identity in `afterRestore`

Each restored process needs to run logic to create a new identity before starting to accept work. CRaC provides the `afterRestore(...)` callback for a registered `Resource`. This is the appropriate place to:

1. Read current instance metadata from the platform or identity provider.
2. Generate a new `incarnationId` for the newly restored process.
3. Update a consistent identity snapshot in the application.
4. Recreate clients/sessions using the new identity.
5. Register the new endpoint and heartbeat.
6. Acquire a lease or participate in leader election if required by the business logic.
7. Open schedulers/consumers and readiness after required steps complete.

Do not wait for the first request to create the identity. A background worker, metrics exporter, or scheduled task can run before the first request and use the old identity. Place a gate so that all identity-dependent components only operate after the new identity has been installed.

## 4. Choosing a Source for Generating a New Identity

There are multiple sources that can issue identities, but they have different levels of guarantees.

| Source | Advantages | Notes |
|---|---|---|
| Random UUID after restore | Simple, no round trip to an external service required | Must use an appropriate entropy source; do not reuse a snapshotted PRNG object |
| Pod UID/container instance ID from platform | Reflects the identity issued by the orchestrator | Must read the current value; environment variables may have been captured into the process before checkpoint |
| VM/cloud instance ID | Instance identity issued by the cloud/platform | Requires accessing the metadata service and authenticating the data source |
| Identity service | Can issue IDs, tokens, or certificates according to policy | Depends on network and availability of the identity-issuing service |
| Database sequence/unique constraint | Issues IDs from a consistent data store | Has database access overhead; must handle retries and connection errors |
| Lease/coordination service | Grants ownership along with a fencing token | Used when ownership/leader is needed, not just for generating ID strings |

For IDs that only require an extremely low collision probability, a newly generated UUID after restore is usually sufficient. For IDs that serve as the basis for protecting write permissions, leader election, or fencing, a consistent coordination system is required; a random UUID does not replace a lease.

### Be Careful with Checkpointed Environment Variables

A process's environment variables are data the process read at startup. If the checkpoint is created in a prepare environment, values such as `HOSTNAME`, `POD_NAME`, or `INSTANCE_ID` may still be the prepare environment's values after restore. The deployment setting different environment variables for the container does not automatically guarantee that the checkpointed process's environment memory is replaced.

If current Kubernetes or cloud metadata is needed:

- Use a source updated for the current instance, such as a metadata endpoint or a platform-supported projected volume.
- If reading from a mounted file, reopen the file after restore; do not rely on an old file descriptor already in the checkpoint.
- If calling the Kubernetes API, refresh the token/service account credential according to the platform's rotation mechanism.
- Verify that the returned metadata belongs to the running pod/VM.
- If a reliable identity cannot be obtained, keep readiness closed and report a restore failure.

With the Kubernetes Downward API, consider how data is exposed. A value injected via environment may be kept in the process snapshot; a projected file may be updated by kubelet, but the application should still reopen the file after restore and verify the behavior on a real cluster/runtime.

## 5. Designing an Atomically Replaceable Identity Holder

Avoid keeping the old identity in multiple separate `static final` fields or singletons. Group runtime identity into an immutable snapshot, then replace the entire snapshot with an atomic operation.

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

final class RuntimeIdentityHolder {
    private final AtomicReference<RuntimeIdentity> current =
            new AtomicReference<>();

    RuntimeIdentity current() {
        RuntimeIdentity identity = current.get();
        if (identity == null) {
            throw new IllegalStateException("Runtime identity is not ready");
        }
        return identity;
    }

    void install(RuntimeIdentity next) {
        current.set(next);
    }

    void clear() {
        current.set(null);
    }
}
```

Services that need the identity should read from the holder at the time of performing an operation. Do not copy the identity into an immutable field of each bean at constructor time if that bean will live across restore. If a library requires passing a client ID in the constructor, recreate the client after restore or use a factory/provider to create the client with the new identity.

An immutable snapshot prevents requests from seeing a half-old, half-new combination, for example a new `instanceId` but an old `advertiseAddress` or `releaseGeneration`. If the identity consists of multiple interrelated fields, replace them together.

## 6. Example of Identity Source and CRaC Resource

The following example illustrates a single resource coordinating identity refresh. The interfaces `PlatformIdentityProvider`, `IdentityAwareComponents`, and `ReadinessGate` are application abstractions.

```java
import java.time.Instant;
import java.util.UUID;

import org.crac.Context;
import org.crac.Resource;

final class IdentityRefreshResource implements Resource {
    private final String serviceName;
    private final String releaseId;
    private final PlatformIdentityProvider platform;
    private final RuntimeIdentityHolder identityHolder;
    private final IdentityAwareComponents components;
    private final ReadinessGate readiness;

    IdentityRefreshResource(
            String serviceName,
            String releaseId,
            PlatformIdentityProvider platform,
            RuntimeIdentityHolder identityHolder,
            IdentityAwareComponents components,
            ReadinessGate readiness) {
        this.serviceName = serviceName;
        this.releaseId = releaseId;
        this.platform = platform;
        this.identityHolder = identityHolder;
        this.components = components;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        components.stopCreatingWork();
        components.awaitInFlightWork();
        components.releaseEphemeralOwnership();
        identityHolder.clear();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();

        String instanceId = platform.currentInstanceId();
        String incarnationId = UUID.randomUUID().toString();

        RuntimeIdentity next = new RuntimeIdentity(
                serviceName,
                releaseId,
                instanceId,
                incarnationId,
                Instant.now()
        );

        identityHolder.install(next);
        components.recreateClients(next);
        components.registerInstance(next);
        components.acquireRequiredLeases(next);
        components.verifyDependencies(next);
        components.resumeWork(next);
        readiness.acceptTraffic();
    }
}
```

Register the resource during application initialization:

```java
import org.crac.Core;

Core.getGlobalContext().register(identityRefreshResource);
```

`UUID.randomUUID()` in the example is called inside `afterRestore`, not in a static initializer. For identity requirements with strict security or uniqueness, use an identity provider/OS entropy verified for the runtime; do not keep a stateful `Random` or `SecureRandom` instance in the checkpoint and continue using it for all clones. If the identity is used to grant write permissions, a lease/fencing token from a coordination system is needed instead of just a UUID.

In production, `components.*` operations need timeouts, bounded retries, and error handling. If obtaining the instance ID, registering, or acquiring a lease fails, the callback should report an error and readiness should remain closed. Do not catch the exception and continue as if the identity were valid.

### Why Consolidate Ordering into One Coordinator?

An application may have multiple `Resource`s: resources for the database pool, HTTP server, metrics, message consumer, and identity. If they run independently without an ordering contract, a component might open a listener before the new identity is installed, or a consumer might start before the lease is granted.

A coordinator helps define a clear order:

```text
afterRestore
    |
    v
Read current platform identity
    |
    v
Create new process incarnation
    |
    v
Install immutable identity snapshot
    |
    v
Recreate clients and sessions
    |
    v
Register endpoint / acquire lease
    |
    v
Verify dependencies
    |
    v
Start consumers and scheduled work
    |
    v
Open readiness
```

If a framework or library already has its own CRaC resource, the coordinator needs to coordinate with that integration via supported APIs. Do not register another resource to close/open the same client without clear ownership.

## 7. Refreshing Service Registration and Network Endpoint

A service registry typically maps a logical service to instance endpoints. If three restored replicas register with the same `instanceId`, one registration can overwrite another, or one replica's heartbeat can mistakenly update another replica.

After restore, each replica needs to:

1. Determine the current bind address and port.
2. Generate a new incarnation ID.
3. Register the endpoint using the new identity.
4. Associate health/heartbeat with the correct incarnation.
5. Accept traffic only after the listener is bound and the registration is valid.
6. Deregister the old registration if it still exists and if the instance has permission to revoke it.

Do not use the hostname or IP from the checkpoint as an immutable identity. In container environments, pod IP and port can differ after restore. In VMs, NIC addresses or routes can change depending on network attachment. Read current information from the platform and check the actual listener.

### Avoiding Mistakenly Deleting Another Replica's Registration

When cleaning up old registrations, the operation should use compare-and-delete by `instanceId`/`incarnationId` or registration version. If replicas A and B share the same ID, A could delete the new registration just created by B. Unique identity is a prerequisite for safe cleanup.

## 8. Lease, Leader Election, and Fencing Token

A field like `isLeader = true` in a singleton does not prove the instance still holds leadership after restore. The lease may have expired while the process was stopped. If multiple replicas restore together, all of them may carry `isLeader = true` from the snapshot.

After restore:

- Clear/mark stale the old leader state.
- Rejoin leader election or request a new lease.
- Run exclusive tasks only after the lease is granted.
- Renew the lease according to the current clock.
- Use monotonically increasing fencing tokens so target systems reject operations from an old owner.

Fencing tokens are especially important when an old process might stay alive while a newly restored replica has acquired the lease. The lease service issues a new epoch, for example 1088; the database/storage accepts an operation only if the token is not older than the already-accepted token. Thus, the old owner with token 1087 cannot overwrite state managed by the new owner.

A UUID only distinguishes instances. It does not replace a fencing token because a UUID does not indicate which owner is newer.

## 9. Message Consumer, Scheduler, and Worker Identity

If the checkpoint contains a message consumer or scheduled job, multiple replicas can continue with the same client/member ID or scheduler state.

### Message Broker

- Create a new client/session after restore according to the client library's guidance.
- Let the broker assign a new member ID when joining the consumer group if the protocol supports it.
- Do not reuse connection/session or heartbeat state from the checkpoint if the library does not support it.
- Confirm subscription and partition assignment before processing messages.
- Use idempotency keys and appropriate commit/ack mechanisms to handle redelivery.
- If a unique client ID is required, generate the ID from the new instance/incarnation.

### Scheduled Job

- Do not restore `schedulerStarted` or `jobOwner` flags as proof of current ownership.
- Start jobs only after identity and lease are ready.
- Use a distributed lock/lease if the job must run uniquely cluster-wide.
- Store long-running job progress in durable storage.
- Design jobs to be idempotent so retries after restore do not create duplicate side effects.

### Worker Pool

Local thread names or worker numbers can be the same across replicas without issue if they are only used for debugging. However, if a worker ID is sent to an external system, used as an ownership key, or recorded in a registry, append the instance/incarnation identity.

## 10. Counter, Sequence, and Random State

A counter in the heap can be cloned with the same value. If that counter is used to issue global IDs, replicas can generate duplicate numbers:

```java
static final AtomicLong NEXT_ORDER_ID = new AtomicLong(1_000_000);
```

After cloning, multiple instances may all issue `1_000_001`. Use a database sequence, an ID service, an appropriate UUID/ULID, or a structured ID containing a unique instance component and a local counter.

Random generators also have state. If a PRNG object is checkpointed and cloned, replicas can produce the same sequence of subsequent numbers. Do not use a snapshotted `Random` as the sole source for IDs or tokens requiring uniqueness/security.

Options:

- Issue IDs from an external service with a uniqueness guarantee.
- Create a new entropy source after restore from a supported OS/provider.
- Use UUID v4 or another ID scheme based on a reliable entropy source.
- Combine instance/incarnation ID with a local counter if ordered IDs within an instance are needed.
- Use a unique constraint in the database to detect and reject collisions.

For cryptographic keys, nonces, or security tokens, follow the guidance for `SecureRandom`, the provider, and the CRaC runtime in use. Do not copy seeds yourself, and do not concatenate a timestamp with a counter and treat it as secure entropy.

## 11. Metrics, Logging, and Tracing Need New Identity

If multiple replicas share the same metric labels or logger identity from the checkpoint, observability data can become ambiguous.

### Metrics

- Keep `service.name`, environment, and release labels stable.
- Attach the platform-provided instance label or incarnation label according to backend policy.
- Avoid using the same series identity for multiple independent processes.
- Rebind gauges to the new pool/client after restore.
- Do not put a new UUID into every metric label if cardinality will grow uncontrollably.

### Logging

- Add instance/incarnation metadata to the log context/MDC.
- Recreate appenders/sessions if network output needs to reconnect.
- Do not let multiple clones write to the same local file or share the same appender identity when unsupported.
- Preserve the original timestamp of log events created before checkpoint; add a separate restore marker.

### Tracing

- Create a new startup/restore span for each incarnation.
- Do not use a fixed trace ID from the checkpoint for all replicas.
- Recreate the exporter/client if the old connection is no longer valid.
- For resumed work, create a new span or link to a durable trace context instead of continuing an old span in the heap if the semantics do not fit.

## 12. Practical Example: Three Replicas from the Same Checkpoint

Suppose an `inventory-api` application is warmed up and checkpointed with the following metadata:

```text
serviceName       = inventory-api
releaseId         = release-2026.11.13.4
instanceId        = prepare-runner-01
incarnationId     = prepare-incarnation-01
leader            = true
consumerClientId  = inventory-consumer-01
```

The deployment restores the same checkpoint into three instances. Target state after restore:

| Field | Replica A | Replica B | Replica C |
|---|---|---|---|
| serviceName | inventory-api | inventory-api | inventory-api |
| releaseId | release-2026.11.13.4 | release-2026.11.13.4 | release-2026.11.13.4 |
| instanceId | pod-uid-a | pod-uid-b | pod-uid-c |
| incarnationId | inc-a-new | inc-b-new | inc-c-new |
| leader | Re-elected | Re-elected | Re-elected |
| consumer session | New session A | New session B | New session C |
| endpoint | IP/port A | IP/port B | IP/port C |

Practical sequence:

1. Create a checkpoint from a prepare process; do not use that identity as the production identity.
2. Launch three restored replicas in an isolated test environment.
3. Each restored replica reads its identity from the current platform or identity provider.
4. Each process generates a new incarnation ID.
5. Each process installs the identity snapshot into the holder.
6. Each process creates a new client/session with its own ID.
7. Each process registers its own endpoint.
8. If only one replica may run an exclusive job, they participate in election and only the owner with a valid lease/fencing token runs.
9. Confirm that the three registrations, heartbeats, and metric series do not overwrite each other.
10. Send traffic and check logs/tracing to show the right replica handled the request.

The point to verify is that the instance identity is not taken from `prepare-runner-01` already in the checkpoint. If the platform does not provide a new identity through a channel readable after restore, the application must call an identity service or generate an independent incarnation and register it with the control plane.

## 13. Testing Collisions and Behavior When the Identity Service Fails

Do not test only the normal case. It is necessary to test:

- Multiple replicas restoring concurrently from the same checkpoint.
- The identity provider returning the same ID due to misconfiguration.
- The metadata endpoint timing out or returning metadata of another instance.
- The token for accessing platform metadata having expired.
- The service registry rejecting registration because the identity already exists.
- The lease service being unreachable.
- An old process still being alive and holding the old lease.
- One replica restoring twice with the same pod identity but different incarnations.
- Cleanup of an old registration running late after a new replica has already registered.

When the identity cannot be verified, do not fall back to the old ID in the checkpoint. Keep readiness closed, perform bounded retries, and emit an alert. If a fallback is needed, only use an identity source with an equivalent uniqueness guarantee that was designed in advance.

### Checking Uniqueness in Tests

An integration test can collect the identities of all replicas and assert uniqueness:

```java
Set<String> instanceIds = restoredInstances.stream()
        .map(instance -> instance.identity().instanceId())
        .collect(Collectors.toSet());

if (instanceIds.size() != restoredInstances.size()) {
    throw new AssertionError("Restored instances share an instance ID");
}

Set<String> incarnationIds = restoredInstances.stream()
        .map(instance -> instance.identity().incarnationId())
        .collect(Collectors.toSet());

if (incarnationIds.size() != restoredInstances.size()) {
    throw new AssertionError("Restored processes share an incarnation ID");
}
```

This test snippet assumes `restoredInstances` is a list of results collected from each process and has the imports `java.util.Set` and `java.util.stream.Collectors`. In multi-process/container tests, data should be collected via a test endpoint or registry rather than static state of the test runner.

## 14. Observing Identity in Production

To detect clones with duplicate identities, monitor:

| Data | Purpose |
|---|---|
| service name and release ID | Group replicas of the same service/release |
| instance ID | Distinguish instances issued by the platform |
| incarnation ID | Distinguish process restores/restarts |
| checkpoint generation | Trace the snapshot source |
| identity created timestamp | Detect abnormally old identities |
| lease/fencing epoch | Identify the latest owner |
| registration version | Track service registry updates/cleanup |
| restore result/readiness time | Detect errors in the restore sequence |

An `application.restore` log event can be emitted after the new identity is installed. The event should contain service, release, instance, incarnation, and checkpoint generation. Do not put secrets, tokens, or full sensitive metadata into logs.

Some useful metrics:

- Number of active instances per service/release.
- Number of identity collisions or registration conflicts.
- Number of lease acquisition failures.
- Number of stale fencing tokens rejected.
- Time from `afterRestore` start to identity ready.
- Time from identity ready to readiness accepting.

Avoid using the incarnation UUID as a label on every metric if the backend has cardinality limits. The UUID can be kept in log/tracing resource attributes, while metric labels use controlled retention/cardinality.

## 15. Common Mistakes

### Generating a UUID in a Static Initializer

The UUID is generated before checkpoint and copied to every replica. Generate a new incarnation in `afterRestore` or obtain it from an identity provider.

### Thinking `final` Means Each Replica Has Its Own Value

`static final` preserves the checkpointed value. `final` only prevents reassigning the reference within the process; it does not automatically generate a new identity.

### Using the Hostname from the Process Environment

The environment may be the prepare process's values saved in the snapshot. Read current metadata through a channel updated after restore and verify it.

### Using a UUID as a Distributed Lock

A UUID distinguishes instances but does not prove ownership. Use a lease/leader election and fencing tokens from a coordination system.

### Keeping Old Leader Flags and Consumer Sessions

Multiple clones may think they are the leader or use old session state. Create a new session and reacquire ownership after restore.

### Opening the Listener Before the New Identity Is Installed

The first requests may be processed with an old registration or log context. Install the identity, create clients, register the endpoint, and check health before readiness.

### Deleting Old Registrations with a Non-Unique Key

One replica may delete another replica's registration. Use compare-and-delete by incarnation/registration version.

### Using a Cloned Counter/PRNG to Issue IDs

Replicas may continue from the same counter or random state. Use an identity service, fresh OS-backed entropy, or a unique constraint.

## 16. Implementation Checklist

- [ ] Distinguished service identity, release/checkpoint ID, instance ID, and process incarnation ID.
- [ ] Do not use the prepare process's identity as the production identity.
- [ ] Each restore generates a new incarnation ID.
- [ ] Instance ID is read from the current platform or an authoritative identity provider.
- [ ] Do not assume checkpointed environment variables automatically change for a new container.
- [ ] Runtime identity is installed atomically before dependent components start.
- [ ] Clients/sessions are recreated with the new identity.
- [ ] Service registry and heartbeat use unique instance/incarnation IDs.
- [ ] Lease/leader election is re-run after restore.
- [ ] Write systems have fencing tokens to prevent old owners from writing data.
- [ ] Consumers, schedulers, and workers do not reuse old ownership state.
- [ ] Checkpointed counters and PRNGs are not used as global ID sources.
- [ ] Readiness is opened only after identity, endpoint, lease, and required dependencies are ready.
- [ ] Cleanup of old registrations uses safe compare-and-delete.
- [ ] Tested multiple concurrent replica restores and verified uniqueness.
- [ ] Tested identity/lease provider failures and confirmed the instance does not reuse old IDs.

## 17. Conclusion

Restoring multiple replicas from the same checkpoint can clone every identity already in the heap. A `static UUID`, hostname, broker client ID, leader flag, or lease token created before checkpoint does not automatically change upon restore. Therefore, applications must separate stable service identity from instance identity and process incarnation identity.

Refresh identity in `afterRestore`, read metadata from the current instance's source, generate a new incarnation, and install a consistent identity snapshot before starting clients, listeners, consumers, or schedulers. For exclusive resources, acquire a new lease and use fencing tokens; for service registry, heartbeats, and metrics, attach a unique identity per replica. Open readiness only after all identities and required dependencies have been verified. That way, multiple replicas can share one checkpoint generation while still operating as independent instances.
