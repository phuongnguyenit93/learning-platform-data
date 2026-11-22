# CRaC API and Managed Snapshot Services Such as AWS Lambda SnapStart

CRaC and AWS Lambda SnapStart both use the idea of capturing the state of an initialized process to reduce repeated work at startup. However, these two options sit at two different layers. CRaC provides an API and integration mechanism for the application to coordinate resource lifecycles around checkpoint/restore; development and operations teams usually control many parts of the runtime, checkpoint, and infrastructure. Lambda SnapStart is an AWS-managed snapshot feature for supported Lambda function versions and runtimes; the service handles creating, storing, and restoring snapshots in the Lambda environment.

Therefore, SnapStart should not be viewed as a general-purpose CRaC checkpoint engine or assumed that a checkpoint created with CRaC can be placed directly into Lambda. The appropriate choice depends on where the application runs, the required level of infrastructure control, the deployment model, cold start requirements, resource management capabilities, and operational cost.

## 1. Two options solving the same problem at two different layers

A Java application typically spends startup time loading classes, creating objects, initializing frameworks, reading configuration, establishing connections, and warming up part of the code. When needing to create multiple instances, these repeated steps can increase startup latency.

Checkpoint/snapshot allows preparing an initialized state and using that state to start new instances faster. The difference lies in who owns the snapshot process and what the application can control.

~~~text
                 Java Application
                      |
       Initialize framework and dependencies
                      |
         Prepare resources before snapshot
                      |
             +--------+--------+
             |                 |
             v                 v
         CRaC API          Lambda SnapStart
             |                 |
   Integrated JDK/runtime   Supported Lambda runtime
             |                 |
   Checkpoint engine and    AWS manages snapshots of
   infrastructure chosen    published function versions
   by deployment team          |
             |                 |
   Operations team          Lambda restores execution
   coordinates              environment when needed
   checkpoint/restore          |
             |                 |
             +--------+--------+
                      |
            Application continues
                after restore
~~~

CRaC describes how an application coordinates with the runtime through the Resource lifecycle. SnapStart describes a managed feature of AWS Lambda, in which the snapshot lifecycle is tied to the process of publishing and running a Lambda function version. SnapStart can use CRaC-compatible hooks in the Java runtime so the application prepares or recovers resources, but ownership of the snapshot remains with the Lambda service.

## 2. What is the CRaC API?

CRaC stands for Coordinated Restore at Checkpoint. The CRaC project provides a Java API for an application to inform the runtime how to prepare resources before checkpoint and recover them after restore.

The common API centers around the **org.crac.Resource** interface:

- **beforeCheckpoint(...)**: called by the runtime before creating a checkpoint so that the Resource closes, flushes, pauses, or saves necessary state.
- **afterRestore(...)**: called by the runtime after the process is restored so that the Resource recreates or verifies resources.
- **Core.getGlobalContext().register(resource)**: registers the Resource with the global context so the runtime coordinates callbacks.

The CRaC API is not a standard Java SE feature that every JDK must provide. One must choose a JDK distribution/runtime with CRaC support and check that version's documentation. The API, runtime integration, checkpoint engine, and platform limitations must be considered together.

### Simple Resource example

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;

    public CacheResource(LocalCache cache) {
        this.cache = cache;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        cache.stopBackgroundRefresh();
        cache.awaitInFlightOperations();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.refreshTimeSensitiveEntries();
        cache.resumeBackgroundRefresh();
    }
}
~~~

LocalCache here is an application-defined abstraction. The example illustrates that callbacks can stop background tasks and refresh time-dependent data. In a real application, timeouts, callback errors, concurrency, and the case where a checkpoint is aborted after resources have been prepared must be handled.

### CRaC does not automatically decide how to handle every resource

The runtime does not fully understand the business semantics of every object on the heap. A Connection may still exist in memory while the server-side database session has timed out. A token may still be in a String but have expired. A file descriptor may be supported by the engine at the native layer while the file or mount has changed.

Resource helps the application coordinate meaningful actions:

- Stop accepting requests and drain in-flight work.
- Complete or rollback transactions according to policy.
- Flush and close files/channels.
- Close or pause connection pools, HTTP clients, and broker clients.
- Save offsets or logical state needed to continue.
- After restore, re-validate dependencies and create new resources.

CRaC does not replace transaction management, distributed coordination, or recovery APIs of external services.

## 3. What is AWS Lambda SnapStart?

AWS Lambda SnapStart is a managed snapshot feature for Lambda function versions and runtimes supported by the service. During version publishing, Lambda initializes the execution environment, runs the Init phase of the function, and creates a snapshot from the prepared state. When a new execution environment is needed, Lambda can restore from the snapshot instead of re-executing the entire initial setup process.

An overview lifecycle:

~~~text
Deploy function code and configuration
              |
              v
Publish a Lambda version
              |
              v
Lambda creates execution environment
              |
              v
Run Init phase
              |
              v
Create Lambda-managed snapshot
              |
              v
Invocation needs execution environment
              |
              v
Lambda restores snapshot
              |
              v
Run restore hooks / complete recovery
              |
              v
Invoke handler
~~~

Detailed steps, supported runtimes, deployment regions, limits, and snapshot caching behavior depend on current Lambda documentation. Check the AWS compatibility matrix for the specific runtime and region before designing a release.

### Published version is an important boundary

SnapStart is tied to a published version of a Lambda function. Changing code or configuration and publishing a new version creates a new immutable version for that release; the snapshot is created and managed according to the version's lifecycle. SnapStart should not be understood as an arbitrary snapshot that an application can create at any time during runtime or move between services.

Lambda manages creating and restoring snapshots within the platform. The application team configures the feature for the function version and prepares the code so that post-restore state remains correct.

### SnapStart does not mean the function no longer has cold starts

SnapStart can reduce the repeated initialization overhead, but restore time, restore hooks, dependency connections, credential loading, and processing the first request still have costs. Actual latency also depends on state size, runtime, deployment region, dependencies, and system load.

Do not measure only the time from when the handler starts running. It is necessary to also measure time to invocation, restore hooks, dependency connections, and p95/p99 of the first request.

## 4. Comparing CRaC and Lambda SnapStart

| Criterion | CRaC API with compatible runtime | AWS Lambda SnapStart |
|---|---|---|
| Nature | API/lifecycle contract and runtime integration for checkpoint/restore | AWS Lambda managed snapshot feature |
| Where it runs | Java environment and platforms supported by runtime/engine | AWS Lambda with supported runtime and region |
| Who creates snapshot | Operations/runtime/engine workflow coordinated by deployment team | Lambda creates snapshot during the publish version lifecycle |
| Who stores and restores | Deployment team or integrated platform manages artifacts and restore | AWS Lambda manages snapshot and execution environment |
| Level of control | Can control runtime, engine, filesystem, host, and release workflow per platform | Less control over snapshot infrastructure; focuses on Lambda function and configuration |
| Portability | Source can use CRaC API, but checkpoint binary depends on runtime/engine/platform | Snapshot is tied to the Lambda version and service; not a portable artifact |
| Lifecycle hook | Resource beforeCheckpoint and afterRestore per runtime | Lambda provides snapshot/restore lifecycle; Java can use compatible CRaC hooks per runtime |
| Scaling | Depends on orchestrator and how checkpoints are distributed | Lambda manages execution environments under the serverless model |
| Networking | Deployment team decides how to close/reopen connections | Must handle potentially stale connections per Lambda restore lifecycle |
| Observability | Runtime, engine, host, and application provide logs/metrics | Combines Lambda logs/metrics/tracing with application logs |
| Operations | Need to manage checkpoint artifacts, compatibility, and rollout | Reduces work managing engine and snapshot storage |
| Best suited for | Java services needing deep runtime control or running outside Lambda | Functions suited to Lambda's event-driven/serverless model |

The important point is that the CRaC API and SnapStart are not two products of the same category. Some of the same lifecycle ideas and the Resource API can be used in both environments, but how snapshots are created, stored, distributed, and restored is different.

## 5. Differences in control and operational responsibility

### When choosing CRaC

The operations team typically bears more responsibility for:

- Selecting the JDK vendor/build and CRaC runtime.
- Selecting the checkpoint engine and supported platform.
- Preparing the filesystem, kernel, CPU, and container.
- Deciding when to create the checkpoint.
- Storing, checksumming, signing, and distributing checkpoint artifacts.
- Checking producer/consumer compatibility.
- Coordinating traffic draining, checkpoint, restore, and readiness.
- Creating a cold-start fallback when the checkpoint cannot be used.

In return, CRaC can be integrated into services running on VMs, containers, or custom platforms if the runtime/engine combination is supported. The deployment team can choose rollout, placement, and observability approaches suited to the system.

### When choosing SnapStart

Lambda manages many platform tasks:

- Creating snapshots according to the published function version lifecycle.
- Storing and distributing snapshots within the service scope.
- Restoring execution environments when needed.
- Integrating with Lambda's invocation and scaling model.

The application team still needs to:

- Choose a supported runtime/region.
- Design a reasonable Init phase.
- Handle state that needs to be unique per execution environment.
- Refresh tokens, connections, and time-dependent data after restore.
- Ensure restore hooks complete before using resources.
- Measure actual cold start and request latency.

A managed service reduces the work of managing the engine, but also limits detailed control over the host, kernel, checkpoint files, and restore schedule. If intervention at that layer is required, Lambda may not be the appropriate model.

## 6. Resource lifecycle: the intersection between the two options

Whether using CRaC directly or SnapStart, one rule remains the same: an object on the heap does not mean the external resource is still valid.

For example:

- A JDBC connection may have been closed by the database during the snapshot's lifetime.
- An HTTP keep-alive socket may expire or be closed by a load balancer.
- DNS results may change.
- Tokens or certificates may expire/rotate.
- Background threads or schedulers may continue with timing assumptions that are no longer valid.
- SecureRandom, nonces, and counters may be duplicated across execution environments.

### Preparing before snapshot

Before snapshot, decide which resources:

- Can be kept intact because they are supported by the runtime/service and are not time-dependent.
- Need to be flushed and closed.
- Need to be stopped so there are no in-flight operations.
- Need to be excluded from the snapshot because they contain instance-specific state.
- Need to be refreshed after restore.

Do not close every resource mechanically. An immutable cache or expensive computed data can be retained if valid across all instances. A connection may be kept if the runtime and service confirm that usage is safe; however, it must be re-checked after restore.

### Recovering after snapshot

After restore:

1. Identify the current execution environment.
2. Recreate unique identity if needed.
3. Refresh short-lived tokens or secrets.
4. Recreate closed connections and clients or those at risk of being stale.
5. Refresh time-dependent data.
6. Confirm required dependencies are ready.
7. Only then allow processing requests.

With Lambda, initialization code in Init does not automatically re-run as on a cold start when a snapshot is restored. Use the appropriate restore hook to handle tasks that must run for each execution environment. With CRaC directly, afterRestore is the callback for the corresponding recovery work.

## 7. Using CRaC Resource in Java applications running on Lambda SnapStart

Lambda's Java runtime may provide hook integration compatible with the CRaC API for SnapStart. As a result, some Resource logic can be used to prepare before snapshot and recover after restore. Confirm the runtime version, dependencies, and current AWS guidance before applying; not every runtime or version has the same behavior.

The example below illustrates a client that needs to be closed before snapshot and recreated after restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApiClientResource implements Resource {
    private final ApiClientFactory factory;
    private volatile ApiClient client;

    public ApiClientResource(ApiClientFactory factory) {
        this.factory = factory;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    public ApiClient client() {
        ApiClient current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "API client is not ready");
        }
        return current;
    }

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
        client = factory.create();
        client.healthCheck();
    }
}
~~~

ApiClient and ApiClientFactory are application-defined illustrative types. In practice, creating a client may require obtaining new credentials, verifying the endpoint, and setting timeouts. If healthCheck() fails, an incomplete client should not be published or allowed to be used by the handler while the dependency is not ready.

With Lambda SnapStart, Resource registration must occur during Init before the snapshot is created. beforeCheckpoint is used for the snapshot preparation step; afterRestore runs when the execution environment is restored according to hooks supported by the runtime. Do not assume the constructor or every startup callback will re-run on each invocation.

If the same application runs both outside Lambda and on a separate CRaC runtime, resource management logic can be reused, but integration, callback order, and error behavior must still be tested in each environment.

## 8. Init phase and Restore phase in Lambda

Lambda divides the execution environment lifecycle into phases. With SnapStart, the Init phase occurs before the snapshot is created for the function version. The Restore phase occurs when Lambda initializes a new execution environment from the snapshot.

Some principles:

- Put shared, stable, and time-consuming work into Init if it is safe to snapshot.
- Do not create a token or identity unique to one execution environment in Init if those values will be copied across multiple restores.
- Put work that needs to be per-execution-environment into the restore hook.
- Ensure connections are recreated or verified before handlers depend on them.
- Do not rely on elapsed time across the snapshot; use the current clock after restore for TTL, expiry, and deadlines.

### Example task classification

| Task | Init before snapshot | Restore hook / after restore |
|---|---|---|
| Parse immutable schemas | Suitable | No need to repeat if unchanged |
| Create object mappers and serializers | Suitable if safe | Check if dependent on runtime configuration |
| Load public, stable reference data | Possible | Refresh if data has TTL/version |
| Obtain short-lived access tokens | Avoid storing shared tokens in snapshot | Obtain token appropriate for execution environment |
| Open JDBC/HTTP connections | Only when supported and verified safe | Usually needs reconnect/validate per client lifecycle |
| Generate instance-specific nonces/counters | Do not create one shared state and clone it | Initialize or request a new range |
| Generate replica-specific private keys | Do not put replica-specific private key into shared snapshot | Obtain distinct key/handle by identity |
| Load classes and create pure objects | Suitable | No need to re-run unless required |

Not every task in the table is mandatory in the restore hook. The final decision depends on data type, dependency lifecycle, and runtime semantics.

## 9. Security when cloning state

A snapshot may contain heap data, static fields, caches, tokens, private keys, sessions, and other sensitive data. When a snapshot is restored into multiple execution environments, those values can appear in multiple replicas.

### Tokens and credentials

Multiple replicas should not use the same rotating refresh token or a token issued specifically to a single instance. Use workload identity or a post-restore credential issuance mechanism so each instance receives an appropriate token.

### Randomness and nonces

Do not assume a SecureRandom created before snapshot will automatically have independent state in every restore. For nonces requiring uniqueness under the same key, use separate keys, a durable range allocator, or a mechanism designed not to repeat. Reseeding must use an entropy source supported by the provider and platform; timestamps or PIDs are not cryptographic entropy.

### Private keys and certificates

Public trust material can be shared intentionally. Instance-identifying private keys should be generated or retrieved from KMS/HSM after restore. If multiple execution environments share an identity, the consequences regarding audit, revocation, and blast radius must be explicitly accepted.

### Protecting snapshots

With self-managed CRaC, the operations team must protect checkpoint artifacts, read/write permissions, checksums, signatures, and the distribution process. With SnapStart, AWS manages snapshot storage and platform lifecycle, but the application must still handle secrets on the heap and comply with IAM permissions, encryption policies, and Lambda security.

A managed snapshot does not make data inside the snapshot automatically safe from a business perspective. Minimize secrets residing on the heap, do not log tokens/private keys, and re-issue unique state after restore.

## 10. Compatibility and portability

The CRaC API helps decouple part of the resource lifecycle logic from how checkpoints are created. However, checkpoint binaries still depend on runtime, engine, OS, kernel, CPU, native libraries, and configuration. A checkpoint created on one JDK/runtime cannot be assumed by default to restore on another runtime.

Lambda SnapStart has its own compatibility boundaries:

- Snapshots belong to the Lambda function version and runtime managed by the service.
- The function must use a runtime/region and SnapStart configuration supported by AWS.
- An internal Lambda snapshot cannot be extracted and used as a standalone CRaC checkpoint on a VM or Kubernetes.
- An arbitrary CRaC checkpoint cannot be taken and Lambda asked to restore it.
- Changing code/runtime and publishing a new version creates a new snapshot lifecycle according to the service's mechanism.

If you want to run the same code across multiple environments, reuse domain logic and resource management abstractions, do not expect to reuse the same binary checkpoint. Keep platform integration in a separate module or adapter.

## 11. Performance and cost

### Factors determining benefit

Snapshots are most useful when initialization can be performed once and that state is safe to reuse:

- Loading classes and creating framework contexts.
- Parsing immutable schemas, templates, or metadata.
- Initializing serializers, mappers, and data structures.
- Computing reference data that does not contain instance-specific state.
- Warming up certain code paths if the runtime and platform preserve that benefit.

Snapshots are less useful if most of the startup time is spent in dependencies that must be recreated after restore, or if each instance needs to do a lot of individual work before becoming ready.

### Comparing operational costs

| Factor | Self-managed CRaC | Lambda SnapStart |
|---|---|---|
| Application runtime infrastructure | VM/container/host chosen and operated by team | Managed Lambda infrastructure |
| Snapshot artifact | Team builds pipeline to create, store, sign, distribute, and delete | Lambda manages snapshot lifecycle |
| Runtime optimization | Deeper control possible if platform permits | Constrained by Lambda runtime and configuration |
| Restore orchestration | Orchestrator or platform configured by team | Lambda orchestrates execution environments itself |
| Compatibility tracking | Requires producer/consumer matrix | Follows AWS runtime/region/service support |
| Operational effort | Higher at checkpoint and host layer | Lower at snapshot infrastructure layer |
| Cost | Compute, storage, network, and operations per custom architecture | Lambda and related service charges per current pricing |

Do not compare using only a single cold-start number. Account for snapshot build cost, storage, memory, idle capacity, invocations, dependencies, and operational effort. AWS pricing structures can change; use the current pricing page to calculate for actual workloads rather than relying on a fixed price in technical documentation.

## 12. When should CRaC be chosen?

CRaC is typically suitable when:

- The application is a Java service running on VMs, containers, or a custom platform.
- The team needs control over runtime, checkpoint engine, and placement.
- There is a clear artifact release and compatibility verification process.
- Lifecycles can be designed for databases, brokers, HTTP clients, files, and native resources.
- Startup optimization is needed for a long-lived or multi-instance service.
- The deployment platform has a supported JDK/CRaC runtime and engine.

CRaC can fit Kubernetes or containerized environments, but it is necessary to verify the kernel, container runtime, permissions, storage, namespace, and how checkpoint/restore is orchestrated. Running Java in a container does not automatically mean checkpointing can be used.

## 13. When should Lambda SnapStart be chosen?

SnapStart is typically suitable when:

- The workload already fits AWS Lambda's event-driven model.
- The Java runtime and target region are on the supported list.
- Cold start is a significant factor for latency.
- The Init phase can be prepared before snapshot and does not contain unique state needing recreation.
- The team wants AWS to manage snapshot infrastructure and execution environments.
- Handlers and dependencies can recover properly within the Lambda lifecycle.

SnapStart does not replace every compute option. If the workload requires continuous processes, long-running background daemons, host control, or long-lived connection protocols in ways unsuitable for Lambda, evaluate containers/VMs or another platform.

## 14. When should snapshots not be used?

Snapshots may provide no benefit or introduce additional risk when:

- Initialization consists mostly of dependency connections that must be redone after restore.
- Init produces business side effects such as sending messages, writing to a database, or creating orders.
- The application holds tokens, nonces, private keys, or unique identities that cannot be shared across replicas.
- Multiple background threads/tasks cannot be brought to a safe state.
- Native libraries or runtime do not support checkpointing on the platform.
- The snapshot is too large, causing storage, transfer, or restore to dominate latency.
- Frequent changes to configuration or secrets quickly make snapshots stale.
- The workload needs artifact portability that the runtime/engine does not provide.

In those cases, cold start can be optimized by reducing Init work, lazy-loading optional dependencies, using appropriate connection pools, improving the classpath, reducing allocations, or choosing a different compute model.

## 15. Migration path from CRaC to SnapStart or vice versa

Do not start by trying to migrate checkpoint binaries. Separate application logic from the snapshot mechanism.

### Step 1: Separate domain logic and resource adapters

Keep business services independent of proprietary APIs of a single platform. Create abstractions for resources that need preparation and recovery, for example:

- Remote client manager.
- Credential provider.
- File/resource manager.
- Work admission gate.
- Security context provider.

### Step 2: Define lifecycle contract

Clearly define pre-snapshot and post-restore actions. For example, prepareForSnapshot() stops background work and closes clients; resumeAfterRestore() obtains new credentials, creates clients, and checks readiness.

Do not put business logic such as creating orders or publishing messages into snapshot callbacks.

### Step 3: Write adapters for each platform

For CRaC, the adapter implements org.crac.Resource and registers with the appropriate context.

For Lambda SnapStart, use the hooks supported by the Lambda runtime, including CRaC-compatible Resource if provided by that runtime version. Do not assume hooks have the same ordering or semantics across runtimes.

### Step 4: Keep platform dependencies in separate modules

A possible structure is:

~~~text
application/
  domain/
    OrderService.java
    ResourceLifecycle.java
  infrastructure/
    RemoteClientManager.java
    CredentialProvider.java
  runtime-crac/
    CracResourceAdapter.java
  runtime-lambda/
    LambdaSnapStartIntegration.java
~~~

There is no need to create two modules if deploying to only one platform. This structure illustrates how to keep platform dependencies separated from the domain when multiple deployment targets are genuinely needed.

### Step 5: Create separate pipelines for each platform

A CRaC pipeline needs to pin JDK/engine/platform, create checkpoints, write a manifest, checksum, sign artifacts, and test restore.

A Lambda pipeline needs to build the function artifact, publish a version, configure SnapStart per service guidelines, and test the execution environment after restore. Do not include CRaC checkpoints in the Lambda package.

### Step 6: Test semantics, not just startup time

Check tokens, certificates, nonces, connections, schedulers, clock, caches, readiness, and side effects. Run multiple instances from the same snapshot to detect duplicated state.

## 16. Testing and measurement before choosing

A fair comparison requires the same workload, data, and correctness requirements.

### Metrics to measure

- Cold start time without snapshots.
- Snapshot/checkpoint creation time if the team owns that step.
- Restore time.
- Restore hook execution time.
- Time to readiness.
- First request latency.
- p50/p95/p99 latency of the first batch of requests.
- CPU and memory during Init/restore.
- Number of reconnections to database, broker, and APIs.
- Timeout, stale connection, or credential errors.
- Compute, storage, and operational costs over the same load cycle.

### Test scenarios

1. Start from cold start and record baseline.
2. Create a snapshot according to each platform's mechanism.
3. Restore multiple execution environments from the same snapshot.
4. Confirm tokens and identities are issued properly per instance.
5. Check that database/HTTP/broker connections remain valid or are recreated.
6. Check SecureRandom, nonces, counters, and replay state.
7. Change secrets/configuration during the snapshot's lifetime.
8. Make a dependency unavailable and confirm readiness has not opened.
9. Check the first request and p99 after restore.
10. Perform a new version rollout and rollback according to the tested procedure.

With Lambda, measure on a published function version with SnapStart enabled and check restore behavior in the target AWS environment. With CRaC, measure on the exact JDK, engine, kernel, container, and storage to be used in production. Results from a development machine do not replace testing on the deployment environment.

## 17. Common misconceptions

**"CRaC and SnapStart are the same product."**

CRaC is an API/lifecycle integration and checkpoint/restore runtime ecosystem. SnapStart is Lambda's managed snapshot feature. They may use similar hooks, but snapshot ownership and infrastructure differ.

**"Using the CRaC API means checkpoints can be moved to Lambda."**

No. The Resource API helps manage resource lifecycles; checkpoint binaries still belong to the runtime/engine/platform that created them. Lambda manages snapshots per Lambda version.

**"SnapStart re-runs all of Init upon restore."**

Do not assume that. The Init state is snapshotted; parts needing refresh per execution environment must reside in a restore hook or corresponding lifecycle mechanism.

**"Snapshots keep database connections so no reconnect is needed."**

Connections can become stale or the server may have closed the session. Clients/connections must be verified according to driver and runtime guidance.

**"All tokens and SecureRandom can be shared after restore."**

No. Snapshots can duplicate state. Credentials, identities, nonces, and random state must be handled per instance requirements.

**"SnapStart completely eliminates cold starts."**

Snapshots reduce part of the initialization work, but restore, hooks, dependencies, and the first request still incur costs.

**"CRaC always provides more control without increasing operational work."**

CRaC allows deeper control on a suitable platform, but the team must manage runtime, engine, artifacts, compatibility, and rollout.

**"Managed snapshots do not require lifecycle testing."**

AWS manages snapshot infrastructure, but the application remains responsible for the correctness of state, credentials, connections, and side effects after restore.

## 18. Decision-making process

The following questions can be used to choose a direction:

1. Must the application run on AWS Lambda? If yes, evaluate SnapStart within the supported runtime/region list.
2. Is control over checkpoint engine, host, filesystem, and restore orchestration required? If yes, evaluate CRaC on a supported runtime/platform.
3. Can time-consuming initialization be put into the snapshot without saving side effects or unique identities?
4. Can dependencies be closed/reopened or re-verified in lifecycle hooks?
5. Can tokens, certificates, nonce ranges, and identities be re-issued for each instance?
6. Are snapshot size and storage I/O aligned with target latency?
7. Does the team have the capability to operate the compatibility matrix and artifact releases if self-managing CRaC?
8. Is there a tested cold-start fallback and rollback procedure?

If the workload suits Lambda and the primary goal is reducing Init time, SnapStart is usually the operationally simpler path. If checkpointing is needed for a Java service outside Lambda or deeper control over the runtime/host is required, CRaC may be more suitable. Measure and verify on the exact environment before deciding.

## 19. Conclusion

The CRaC API and AWS Lambda SnapStart both help reduce repeated initialization overhead by preparing state beforehand and then restoring that state. CRaC provides the Resource contract and integrates with the JDK/runtime and checkpoint engine chosen by the deployment team. SnapStart is a managed Lambda feature tied to a published function version, letting AWS manage the snapshot lifecycle.

Lifecycle thinking and parts of Resource code can be reused across both environments, but one should not expect portable checkpoint binaries or assume all callbacks have identical semantics. Classify shareable state, refresh credentials and connections per execution environment, ensure nonces/identities are not improperly duplicated, measure restore along with request latency, and choose the platform based on control requirements, operations, and deployment model.
