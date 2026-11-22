# Restoring Multiple Processes from the Same Image

An important benefit of checkpoint/restore is the ability to prepare an application once and use the prepared state as a starting point for multiple instances. Instead of initializing the JVM, loading frameworks, and warming up the application from scratch for each instance, the system creates a checkpoint after the application has reached an appropriate baseline state. When scaling is needed, multiple processes can be restored from the same checkpoint image set, provided that the CRaC JDK build and the deployment platform support that usage.

Each restore creates an independent process with its own address space and lifecycle. The processes may start from the same memory state, but once running, their states change independently. They are not multiple threads accessing the same Java heap, nor are they multiple users controlling a single process.

The challenge of this model lies in what is copied along with the checkpoint. If the image contains instance identity, network connections, tokens, task schedules, or business state specific to the image-creating process, the restored instances may start with duplicated or stale data. To use an image safely as a template, it is necessary to prepare a shareable baseline state and recreate instance-specific state after restore.

## 1. Concept of Restoring Multiple Processes from the Same Image

A checkpoint is a saved snapshot of a process's state at a point in time. In a Java application using CRaC, that state can include the heap, runtime state, and other information needed for the checkpoint/restore environment to recreate the process.

When restoring multiple processes from the same image, the workflow takes the following form:

1. Start a preparation process.
2. Initialize the application, load baseline configuration, and warm up the necessary processing paths.
3. Put resources into a checkpoint-safe state and create the image.
4. Keep the image set as a baseline artifact.
5. When multiple instances are needed, request the environment to create multiple restored processes from that artifact.
6. Each process recovers resources, establishes its own identity, checks readiness, and begins accepting work.

```text
                 Preparation process
                         |
                         v
       Application initialization and warm-up
                         |
                         v
                 Create checkpoint
                         |
                         v
             Base checkpoint image set
                  /       |       \
                 /        |        \
                v         v         v
           Restore A  Restore B  Restore C
                |         |         |
                v         v         v
           Process A  Process B  Process C
                |         |         |
                v         v         v
           Private     Private     Private
           resources A resources B resources C
```

The diagram illustrates the logical model. How the restore command is invoked, how the image directory is organized, the ability to run multiple restores concurrently, and limits on the number of restores depend on the specific JDK build, checkpoint/restore tool, and platform. Not every JDK build with CRaC support automatically supports every fan-out pattern or parallel restore. You should confirm this capability in the vendor's documentation and test it on the target environment.

## 2. One Image Can Produce Multiple Independent Processes

Imagine a product service application that needs to scale from one instance to three instances when request volume increases. If each instance starts from scratch, all three must repeat part of the initialization and warm-up work. With the checkpoint model, the team can prepare the application once and use the prepared image as the starting point for three restores.

The post-restore processes have several characteristics:

- **Initial state can be identical:** Objects and caches that already exist in the checkpoint can appear in each restored process.
- **Memory is managed separately:** Each process has its own address space and runtime state. Modifying an object in process A does not automatically modify the corresponding object in process B.
- **Operating system resources must be handled separately:** File descriptors, sockets, threads, namespaces, and external resources must satisfy the rules of the restore mechanism and the application.
- **States will diverge:** After receiving different requests, caches, counters, threads, and business state in each process can differ.

"The same image" should not be understood as processes sharing a writable heap. Nor should it be understood as copying a JAR file. A checkpoint image is typically a collection of data and metadata tied to a specific process state, runtime environment, and resource layout.

Some operating systems or storage mechanisms may optimize physical memory using copy-on-write or sharing read-only pages. This is a system-level optimization that depends on the tool and environment. Applications must not rely on it to share mutable Java objects, and should not assume that restored processes always share physical RAM.

## 3. Distinguishing the Base Checkpoint Image from Restored Processes

In a multi-instance system, three types of entities need to be distinguished:

| Component | Role | Lifecycle |
|---|---|---|
| Base checkpoint image | Template artifact containing the prepared baseline state | Stored, versioned, and used for restores according to policy |
| Preparation process | Runs the application to create the baseline state and checkpoint | Usually exists only during the image preparation phase |
| Restored process | Independent instance created from the image | Has its own identity, resources, and lifecycle |

The base image should be managed as an immutable artifact after successful creation. If the restore tool or vendor workflow requires a separate working directory, create a copy or a dedicated workspace for each restore. Do not let multiple processes write to the same image directory or modify the metadata of the same checkpoint set unless the platform documentation confirms that operation is safe.

Treat a checkpoint as a complete artifact set. Do not copy only a single file while omitting accompanying data files, metadata, permissions, or directory structure. Before distribution, you can compute a checksum for the artifact set in a way appropriate to the storage format to verify that copies are not missing or corrupted.

A safe release workflow typically keeps the original read-only, creates a separate restore workspace, and tags each instance with a deployment identifier. Whether an image can be read concurrently by multiple restores or whether the image directory must be cloned beforehand must be confirmed according to the exact tool being used.

## 4. Compatibility Conditions for Multiple Restores

Restoring an image multiple times does not eliminate the inherent compatibility requirements of checkpoint/restore. Each restore must still run in an environment that meets the requirements of the JDK build and the tool that created the image.

Factors to verify include:

- Vendor, version, build number, and configuration of the CRaC JDK.
- Operating system, kernel version, CPU architecture, and required kernel features.
- CRIU version or checkpoint/restore mechanism used by the build.
- Container runtime, PID namespace, network namespace, user namespace, cgroup, and system permissions.
- Native libraries, environment variables, file paths, mounts, and dependent files.
- How operating system resources are allocated for each restore.

Do not assume that an image created on a development machine can be restored on any node in a cluster. Nodes within the same cluster can also differ in kernel, architecture, libraries, security configuration, or mounts. You should pin the image-creation environment and the restore environment using deployment images, node configurations, and the vendor's compatibility documentation.

When multiple restores run concurrently, the platform must also allocate system resources for each process. For example, each process needs an appropriate PID, cgroup limits, memory, file descriptors, and a separate storage location. How namespaces are created or reused directly affects whether those processes can coexist.

## 5. Unique Identity for Each Process

This is the most important requirement when one image is used as a template for multiple instances. The preparation process may have already read some identifying information of its own. If those values are preserved in the checkpoint, every restored instance risks using the same identity.

Values that may need to be re-established per instance include:

- Instance ID, pod name, hostname, or replica identifier.
- IP address, listening port, and network interface information.
- Deployment region, availability zone, or node identity.
- Tokens, credentials, or authentication information tied to the instance.
- Consumer names, client IDs, or worker names that must be unique.
- Temporary file paths, log directories, and local data write locations.

Do not include the preparation process's identity in the baseline state if those values must differ between replicas. Instance-specific information can be read from environment variables, mounted configuration files, metadata services, or the orchestration system after restore. The source and timing of reading must match the deployment environment.

A common configuration pattern is to split configuration into two groups:

| Configuration group | Examples | Processing time |
|---|---|---|
| Shared baseline configuration | Business rules, immutable metadata, serializer configuration | Can be loaded before checkpoint if safe and contains no instance-specific data |
| Per-instance configuration | Instance ID, IP, port, consumer ID, node information | Read or refresh after restore |

If a library caches configuration in a static field, changing environment variables after restore does not automatically update previously read values. The application needs a mechanism to reload or reinitialize that component. Therefore, you must identify which data is read at startup and which data needs to be refreshed in the `afterRestore(...)` callback or an equivalent recovery step.

## 6. Handling Network Connections and Listening Ports

Network connections are one of the most common causes of failure in the multi-process restore model. An open TCP connection in the preparation process may no longer be valid after the checkpoint is saved, and restoring the same socket for multiple processes can produce undesirable behavior.

Before checkpoint, the application typically needs to stop accepting new connections and close environment-dependent sockets or clients according to the library's CRaC guidelines. After restore, each process recreates the necessary connections using its own network information.

Pay special attention to HTTP ports or service ports:

- If processes are in different network namespaces, they can use the same port number within their own namespace, depending on platform configuration.
- If multiple processes are in the same network namespace and bind to the same address/port, the bind operation may fail because the port is already in use.
- Some systems support `SO_REUSEPORT` for cases where multiple sockets bind to the same port, but you must verify the capabilities of the operating system, JVM, and server framework. Do not assume that the Java application in use supports that configuration.
- Another option is to assign a separate port to each instance or place a reverse proxy/load balancer in front to distribute traffic.

For example, three replicas in three containers with separate network namespaces can all listen on port 8080 inside their containers. A load balancer or service discovery routes to each container's address. If all three processes run directly in a single host namespace, a clear port allocation design is required.

Outbound connections also need to be recreated when appropriate. Database connection pools, HTTP clients, TLS sessions, message broker channels, and DNS caches may contain expired state or be tied to the old node. After restore, each instance should create its own connections and verify connectivity before reporting readiness.

## 7. Managing Databases, Message Brokers, and External Services

A checkpoint created from the preparation process may contain the state of external clients. When multiple processes restore, they should not all continue using an old connection or an old client identifier.

### 7.1. Databases and Connection Pools

Each instance should have its own pool or a connection mechanism explicitly supported by the library and platform. Before checkpoint, close or put the pool into a safe state according to the CRaC integration. After restore, create a new pool with the instance's configuration and verify connectivity.

If three processes restore a pool that already has existing connections, errors can occur due to invalid sockets, connection limits, or all three processes simultaneously using an unsuitable identifier. You also need to calculate the total expected number of connections: if each replica creates a pool of up to 30 connections, 20 replicas can generate demand for up to 600 connections.

### 7.2. Message Brokers and Consumers

Consumers often need an appropriate identifier or consumer group. When multiple instances use the same consumer ID in a system that requires unique IDs, they can overwrite state or contend with each other. With Kafka, for example, a consumer group can be shared intentionally to distribute partitions, but each consumer instance still needs to have its client lifecycle created and managed properly. Do not copy an active consumer from a checkpoint and let restored instances continue with the same internal state.

Before checkpoint, stop receiving new messages, finish or roll back in-flight messages, and ensure offsets/acknowledgements are not in an inconsistent state. After restore, each instance reconnects, joins the group, or registers subscriptions according to the system's design.

### 7.3. Secrets and Tokens

Tokens or credentials stored in the heap may expire between the time the checkpoint is created and the time it is restored. If all instances share a short-lived token, they may all fail together once the token expires or is revoked. Fetch secrets according to the system's policy after restore, or verify their expiration and refresh them before use.

## 8. Background Threads, Schedulers, and Periodic Tasks

A preparation process may have background threads, executors, timers, and schedulers. When creating a checkpoint, these threads must be in a supported state and must not hold unfinished work that breaks consistency.

Before checkpoint, the application should have a quiesce procedure:

1. Stop accepting new tasks.
2. Wait for running tasks to complete within a defined timeout.
3. Persist work state if it needs to continue after restore.
4. Stop executors or timers that hold environment-dependent resources.
5. Ensure no locks or transactions are held in an unrecoverable state.

After restore, each process starts workers and schedulers according to its own configuration. Note that a task schedule saved in the checkpoint may be restored by multiple processes at the same time. If all of them run the same periodic task, the system may send emails multiple times, generate duplicate reports, or execute the same business operation multiple times.

Common approaches include:

- Using a distributed lock or leader election when only one instance is allowed to run the task.
- Using partitioning or sharding so each instance processes its own portion of work.
- Using a durable queue and acknowledgements to coordinate work across workers.
- Designing idempotent tasks with deduplication keys and state checks before writing results.
- Recalculating the next execution time after restore instead of replaying all missed schedules.

Do not rely on an in-memory `static` variable to guarantee that "only one instance runs the task." That variable is copied with the checkpoint, so all processes can see the same initial value. Coordination between processes must rely on an external coordination mechanism or a verifiable work-partitioning scheme.

## 9. Caches and In-Memory Data

One reason to create a checkpoint after warm-up is to reuse preloaded caches. However, not every cache is suitable for cloning across multiple processes.

**Logically shareable baseline caches:** immutable metadata, rarely changing lookup tables, parsed structures, or reference data can be prepared before checkpoint. Each process receives a similar initial state and can read it quickly after restore.

**Instance-mutable caches:** request counters, session state, user-specific data, or caches containing identity information should not be treated as shared state. Each process has an independent copy; updates in one process do not automatically synchronize to other processes.

**Expiring caches:** data with TTLs, DNS, certificates, tokens, or configuration may already be stale upon restore. Check expiration, invalidate, or refresh them after restore.

If the application needs a consistent cache across multiple replicas, use an external cache system or data store designed for concurrent access. Each process having a copy of the heap does not replace a distributed cache.

## 10. Randomness, Time, and Unique Data

Because processes start from the same memory state, pseudorandom number generators initialized before checkpoint may carry the same state in each restored instance. If they continue using that state, the processes may generate duplicate or unexpectedly correlated sequences of values.

For values that need to be unique or unpredictable, choose an appropriate mechanism:

- Generate instance IDs from the orchestration system or an identity source that guarantees uniqueness.
- Use `SecureRandom` or an appropriate entropy mechanism and verify the runtime's behavior after restore.
- Re-seed pseudorandom number generators according to the library's guidelines when their state is saved in the checkpoint.
- Do not use an in-heap counter as the sole source for generating system-wide IDs.

Time must also be considered. A cached object with a timestamp created before checkpoint may already be expired upon restore. Schedulers or timeout logic may carry old deadlines. After restore, re-evaluate expirations, leases, tokens, and schedules based on the current clock.

## 11. Preventing Repeated Side Effects

When an image is used to create multiple instances, all state and work performed before checkpoint must be reviewed for side effects.

For example, the preparation process might run an initialization snippet that creates a default record in the database. That record already exists once before checkpoint. Restored instances should not re-execute the record creation as if it were the application's first run.

Conversely, if an `afterRestore(...)` callback sends a welcome email, creates an order, or writes business data without a deduplication key, that operation will be executed in every restored process. When creating 10 instances, the side effect could occur 10 times.

Categorize work into:

| Work type | Examples | How to handle |
|---|---|---|
| One-time baseline preparation | Parsing schemas, loading immutable metadata | Perform before checkpoint if reusable |
| Per-instance initialization | Creating pools, binding ports, fetching instance ID | Perform after restore for each process |
| Business side effects | Sending emails, creating orders, recording transactions | Run only on real business events; use idempotency and durable state |
| Single-owner tasks | System-wide cron, migration coordination | Use leader election, locks, or centralized coordination |

A safe warm-up workflow should use test data and operations that do not cause business side effects. Recovery callbacks should focus on recreating runtime resources. If migrations or system-wide initialization tasks are needed, manage them as a separate, controlled deployment step.

## 12. Orchestrating Multiple Restores

Even when an image can produce multiple processes, restoring all instances at once is not necessarily a good choice. Each restore can place heavy load on CPU, memory, filesystem, database, DNS, and dependent services.

For example, an image is used to scale from 2 to 40 replicas. If all 38 new processes restore simultaneously and open connection pools, the database could receive hundreds of connections in a few seconds. External caches could be reloaded by many instances at once. Logging systems and service discovery could also receive a large surge of registrations.

An orchestrator should control:

- **Concurrency:** the number of concurrent restores per node and across the cluster.
- **Staggering:** splitting restores into batches or adding time offsets between instances.
- **Backoff and retry:** limiting retries, using exponential backoff and jitter when dependent services are not yet ready.
- **Capacity:** pre-checking CPU, RAM, file descriptors, PIDs, cgroups, storage space, and connection limits.
- **Readiness:** adding an instance to the load balancer only after callbacks, connections, and health checks have completed.
- **Scale-in:** stopping new work, draining requests, and closing resources when removing an instance.

Do not treat the moment a process finishes restoring as the moment the application is ready. A process may already exist while still creating pools, fetching secrets, registering consumers, or starting workers. Readiness must reflect the actual serving state.

## 13. Workflow for Preparing an Image Used by Multiple Instances

A workflow can be organized into the following phases.

### Phase 1: Select Baseline Configuration

Choose the right CRaC JDK, application version, dependencies, framework configuration, and deployment image. Configuration loaded before checkpoint should contain only data that can be shared safely. Do not include IDs, IPs, tokens, or information tied to a specific replica in the baseline state.

### Phase 2: Initialize and Warm Up

Start the application, complete baseline initialization steps, and run a representative workload. Verify that critical code paths have been warmed up. Avoid executing real business operations or creating side effects that cannot be safely repeated.

### Phase 3: Put the Process into a Checkpointable State

Stop accepting new work, drain requests, finish transactions, and stop consumers and schedulers as designed. Close or prepare to recreate connections, sockets, pools, and environment-dependent resources. Register the necessary CRaC resources so callbacks are invoked during the checkpoint/restore lifecycle.

### Phase 4: Create and Package the Image

Create the checkpoint according to the instructions of the JDK build and platform tools. Confirm that the checkpoint completes, and record release metadata such as JDK version, application version, image digest, and baseline configuration. Protect the image because it may contain sensitive data in memory.

### Phase 5: Test a Single Restore

Before scaling out, restore one instance from the image. Verify callbacks, connections, identity, ports, readiness, logs, and several representative requests. This is the basic verification step confirming that the image can be restored on the target environment.

### Phase 6: Test Multiple Restores

Create at least two instances from the same image set in the manner supported by the platform. Verify that they have separate PIDs/identities and resources, do not have unintended port bind conflicts, do not repeat side effects, and can serve requests together. Test both sequential and concurrent restores if production plans to use concurrent mode.

### Phase 7: Release and Monitor

Push the image to the artifact repository, apply access permissions, and enforce retention policies. During deployment, orchestrate the number of restores according to system capacity. Monitor restore duration, readiness duration, callback errors, connection success rate, latency, throughput, CPU, memory, and retry counts.

## 14. Example of Per-Instance Callback Design

The code snippet below illustrates a resource that manages connections created separately after each restore. `ConnectionManager` is a hypothetical application class; actual closing and creation of connections must follow the API of the library in use.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class InstanceConnectionResource implements Resource {
    private final ConnectionManager manager;

    public InstanceConnectionResource(ConnectionManager manager) {
        this.manager = manager;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Stop accepting new work and close old connections safely.
        manager.quiesceAndClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Read the current instance's configuration/identity and then create new connections.
        manager.reinitializeForCurrentInstance();
    }

    public interface ConnectionManager {
        void quiesceAndClose() throws Exception;
        void reinitializeForCurrentInstance() throws Exception;
    }
}
```

In the multi-process model, each restore has an `InstanceConnectionResource` instance in its own process. The `afterRestore(...)` callback runs in the context of each individual process and must initialize resources appropriate for that instance.

This is an example illustrating responsibility boundaries. A real-world application must ensure that the resource is registered exactly once per process, callbacks are safe on failure, dependent components do not use the manager while it is closing/opening, and readiness succeeds only after reinitialization is complete. Business operations with side effects should not be placed in this callback.

## 15. Testing Process Independence

A multi-restore test must prove that processes can not only start up, but also operate independently.

Suppose three processes A, B, and C are created from the same image. You can verify them according to the following table:

| Item | Expected result |
|---|---|
| Process ID and instance ID | Each process has a distinct identifier per environment |
| Heap and internal counters | Each process has its own runtime state; updates in A do not automatically change B or C |
| Ports and network addresses | No unintended conflicts; each instance receives an appropriate endpoint |
| Database connections | Each instance creates or owns connections according to the defined policy |
| Message consumers | Each consumer joins the system with a valid group/partition and ID |
| Schedulers | Tasks run only according to the chosen coordination mechanism, without unintended duplication |
| Secrets and tokens | Each instance uses valid credentials with the proper scope |
| Side effects | No duplicate emails, transactions, or records merely due to multiple restores |
| Readiness | Succeeds only after resources recover and dependencies are ready |

Send different requests to each instance and observe logs/metrics tagged with the instance ID. Verify that local memory changes do not leak to other processes, while data that must be shared is still synchronized through external data stores or services as designed.

Failure scenarios should also be tested: a callback failing, the database not being ready, an expired token, an occupied port, or a restore interrupted mid-way. Confirm that the orchestrator does not route traffic to a failed instance and can clean up allocated resources.

## 16. Performance and Limits When Cloning from the Same Image

Checkpoints reduce repeated work, but restoring multiple processes still consumes resources. Each process needs CPU to recover and run callbacks, memory for private state, threads, file descriptors, and connections to external services.

Metrics to measure include:

- Time from restore request until the process exists.
- Time from process existence until readiness succeeds.
- CPU and RAM per instance and across the node during restore.
- Number of new connections to databases, brokers, and other services.
- Time to first request and latency on initial requests.
- Throughput as the number of instances increases.
- Rate of restore failures, callback failures, and retries.

Do not compare only the restore time of a single instance against the cold start of a single instance. Measure multi-replica scaling scenarios as well, because concurrent load can turn the filesystem, CPU, memory bandwidth, or dependent services into bottlenecks.

If the platform supports copy-on-write or memory page sharing, RAM savings can be recorded in measurements. However, as each process modifies data, pages may split into private copies. Actual memory usage also depends on the post-restore workload and cannot be inferred solely from the checkpoint image size.

## 17. Common Mistakes

**Sharing the preparation process's identity.** Multiple replicas register the same instance ID, consumer ID, or hostname. Generate a unique identity after restore.

**Restoring sockets and ports improperly.** Multiple processes try to use the same socket or bind to the same address/port in one namespace. Close and recreate connections, and design namespaces or port allocation clearly.

**Sharing an old connection pool.** Expired or invalid connections are copied into multiple processes. Close the pool before checkpoint and create a new pool in each restored process.

**Running duplicate schedulers or consumers.** Restored instances all resume the same schedule or consumer state. Use appropriate coordination, partitioning, and idempotency mechanisms.

**Reusing random state.** Pseudorandom number generators saved in the checkpoint may start from the same state in every process. Initialize randomness sources and IDs according to security and uniqueness requirements.

**Reading instance-specific configuration too early.** The application stores the preparation process's hostname or token in a static field. Refresh instance-dependent configuration after restore.

**Concurrent restores exceeding service capacity.** A scaling surge creates too many connections and initialization requests. Limit concurrency, batch restores, and use backoff.

**Assuming one image works in every environment.** Differences in JDK, kernel, CPU, namespaces, mounts, or permissions can cause restore to fail. Pin and verify the compatibility matrix.

**Assuming a restored process is already ready.** Callbacks or essential connections have not yet completed. Tie readiness to the actual recovery state.

**Modifying the base image while multiple restores are running.** A write or cleanup operation can corrupt another restore. Manage the base image as immutable and use separate workspaces according to platform rules.

## 18. Checklist Before Using One Image for Multiple Processes

- [ ] Do the CRaC JDK build and platform have documentation confirming support for multiple restores in the intended manner?
- [ ] Was the checkpoint image created from a properly initialized and warmed-up application?
- [ ] Has the complete image set been packaged, checksum-verified, and versioned?
- [ ] Do restores have separate workspaces if required by the tool?
- [ ] Does each process have its own PID, instance ID, and configuration?
- [ ] Are sockets, ports, DNS, HTTP clients, and outbound connections recreated appropriately?
- [ ] Are database pools, message consumers, and credentials initialized separately or coordinated properly?
- [ ] Do background threads, schedulers, timers, and locks have a stop/start procedure?
- [ ] Have shared caches, private caches, and expiring caches been categorized?
- [ ] Are randomness sources, tokens, and unique IDs handled safely after restore?
- [ ] Are side effects controlled with idempotency or coordination mechanisms?
- [ ] Have at least two restores from the same image been tested, both sequentially and concurrently if needed?
- [ ] Does the orchestrator limit concurrent restores and enforce readiness?
- [ ] Have CPU, RAM, latency, throughput, connections, and error rates been measured during scaling?
- [ ] Is the checkpoint image protected as data that may contain secrets and user information?

## Conclusion

Restoring multiple processes from the same image allows a prepared application state to serve as the starting point for multiple instances. Each restore creates an independent process with its own memory and lifecycle, even though the initial state may be identical. This model can reduce repeated initialization work, but it operates safely only when the JDK build and platform support multi-restore workflows.

The most important design principle is separating reusable baseline state from per-instance state. Refresh identities, connections, secrets, workers, and task schedules after restore; control side effects; orchestrate the number of restores; and verify readiness before accepting traffic. When these conditions are met and measured in a real deployment environment, a checkpoint image can become the foundation for creating multiple Java instances consistently and quickly.
