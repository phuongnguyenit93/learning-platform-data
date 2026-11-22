# CRaC and CDS or AppCDS: Differences in State Scope

CRaC and CDS/AppCDS can both help Java applications start faster, but they address two very different parts of startup. **CDS/AppCDS stores data used for class loading and shares eligible data across JVMs; a CRaC checkpoint saves the state of a running process so that process can be restored.** A CDS archive is not a process image, and a CRaC checkpoint is not merely a class archive.

CDS (Class Data Sharing) focuses on class metadata and the mechanism for sharing class data. AppCDS (Application Class-Data Sharing) extends the archive scope to include application and dependency classes. When a new JVM starts, it can map a matching archive and reduce the work of reading, parsing, loading, or creating certain class structures.

CRaC (Coordinated Restore at Checkpoint) goes beyond class loading. The application runs and is prepared beforehand; the JVM checkpoints the process state according to runtime/platform capabilities. Upon restore, the application continues from the saved state, and then CRaC callbacks recover external resources such as sockets, connection pools, credentials, and schedulers per the application's design.

Because the state scope differs, choosing between the two solutions depends on the goal: if you only need to reduce class loading overhead, CDS/AppCDS is usually simpler; if you need to restore both warmed-up runtime state and part of the in-memory application state, CRaC is more suitable, though it requires a more complex checkpoint/restore pipeline and resource management. The two mechanisms can also be combined if the runtime and deployment workflow support it.

## 1. Starting from the Scope of Saved State

The core difference lies not in the names, but in **what is saved and restored**.

| Aspect | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Unit saved | Archive of class data, primarily class metadata and eligible related data | State of a checkpointed JVM process |
| Class scope | Core platform classes and, with AppCDS, archived application/dependency classes | Classes loaded in the process and related runtime state inside the process image |
| Application heap | Does not save the full active heap; only eligible archived heap objects in the CDS mechanism | Can restore the process's heap state per checkpoint runtime capabilities |
| Threads and execution state | Does not save thread stacks or running execution state of an application | Part of the checkpointed process state; resources/threads must be prepared per CRaC lifecycle |
| JIT/runtime warm-up | Class archive reduces class loading; not a snapshot of a full run's execution/JIT state | Can retain warmed-up runtime state in the process image, depending on JVM and platform |
| Sockets/connections | Does not save open connections | May have descriptor state in the checkpoint, but external resources may become invalid and usually must be closed/recreated via callbacks |
| Startup usage | A new JVM starts and uses the archive | JVM/process is restored from the checkpoint image |
| Reuse scope | Archive can be used by many compatible JVMs | Checkpoint is bound to a specific environment/runtime and process state; not a shared archive for independent JVMs |
| Operational requirements | Create archive, ensure classpath/module compatibility, and inspect CDS logs | Warm-up, prepare resources, checkpoint, package, restore in matching environment, and verify readiness |

CDS/AppCDS does not preserve the state of an in-flight request, arbitrary application object graphs, or a connection pool initialized in a previous run. CRaC can restore much more process state, but it does not turn external systems into part of a consistent snapshot.

## 2. What Is CDS?

CDS is a HotSpot JVM mechanism that allows storing certain class data in an archive so JVMs can share and reuse it at startup. Instead of each JVM rebuilding all class structures from scratch, the JVM can map the archive and use pre-prepared structures.

Key benefits:

- Reduces class loading and initialization time in applications with many classes.
- Reduces memory overhead when multiple JVMs share archive data on the same host.
- Reduces parsing/verification/metadata setup work for eligible classes.
- Can improve startup for many application types without modifying business code.

CDS is not a mechanism for saving the state of a run. Each JVM still creates its own heap and executes the program through its own lifecycle. A new JVM does not resume from the threads, requests, connections, or arbitrary object graphs of the JVM that created the archive.

### 2.1 Class Metadata and Archived Data

A CDS archive can contain class metadata and related data supported for sharing by the JVM. Some JDKs also support archived Java heap objects, such as certain strings or objects belonging to the prepared module graph/class metadata. These objects must satisfy the JVM's archiving rules; it does not mean every live object in the application heap is placed into the archive.

Therefore, distinguish among:

- **Class metadata:** information the JVM needs to represent classes, methods, fields, the constant pool, and related runtime structures.
- **Archived heap objects:** a specific set of Java objects the JVM allows storing in the archive, not the entire application heap.
- **Application runtime state:** business object graphs, sessions, threads, connections, dynamic caches, and request state inside a process. CDS is not a snapshot for this group of state.

When the JVM starts from a CDS archive, it still must create required runtime objects, execute static initialization according to proper semantics, and perform unarchived application work.

## 3. AppCDS Extends Archives to Application Classes

AppCDS (Application Class-Data Sharing) allows archiving classes provided by the application and its dependencies, alongside the platform classes CDS can share. This is useful for large framework applications with many classes loaded from the JAR/module path.

For example, a Spring service may load many classes from:

- Application JAR.
- Spring Framework and Spring Boot.
- JSON/serialization libraries.
- Database drivers.
- Validation, logging, and metrics libraries.
- Other internal libraries.

AppCDS can help the JVM reuse class data for eligible classes in the archive. It does not automatically create a Spring `ApplicationContext`, run `@PostConstruct`, open a DataSource, or load business data into caches simply because the corresponding classes are in the archive.

### 3.1 Static Archive and Dynamic Archive

Operationally, AppCDS is typically created in two ways:

| Archive type | General creation method | Characteristics |
| --- | --- | --- |
| Static archive | Collect a class list, then create the archive using CDS dump mode | Archive is explicitly created during build/provision steps; typically suits a relatively stable class set. |
| Dynamic archive | Run the application with `-XX:ArchiveClassesAtExit=<file>` to write loaded classes to an archive upon normal JVM exit | Convenient for collecting classes from a representative run; requires normal JVM termination and compliance with JDK conditions. |

Flag names, creation conditions, and archive capabilities depend on the JDK version. Check the documentation for the exact vendor/build before putting commands into a pipeline.

### 3.2 Example of Creating a Dynamic AppCDS Archive

General example with a classpath application:

```bash
java \
  -XX:ArchiveClassesAtExit=app-cds.jsa \
  -cp app.jar \
  com.example.Application
```

Run the application with a representative workload, then let the JVM exit normally so the runtime has an opportunity to write the dynamic archive. If the process is forcibly killed or the JVM terminates abnormally, the archive may not be completely generated.

Using the archive on a subsequent launch:

```bash
java \
  -Xshare:auto \
  -XX:SharedArchiveFile=app-cds.jsa \
  -cp app.jar \
  com.example.Application
```

This is a minimal example. A dynamic archive may depend on a base archive and the classpath/module path conditions used during creation. Use the exact configuration required by the JDK documentation and check CDS logs to see whether the archive is actually used or ignored.

## 4. Scope of CRaC State

CRaC allows preparing a running JVM and then creating a checkpoint to restore the process state. Compared to CDS/AppCDS, the restored scope is much larger.

A process image can retain states such as:

- Heap objects and application state at the time of checkpoint.
- Loaded classes and existing runtime structures.
- Thread/process execution state per checkpoint implementation capabilities.
- Certain native/process states and file descriptors supported by the platform.
- Caches and objects initialized during the prior run.
- Warmed-up runtime state, which can reduce repeated startup work.

The exact scope depends on the CRaC JDK, CRIU or platform mechanism, and resource types. Do not claim that every socket, native handle, thread, or device can continue operating after restore. The application must use `org.crac.Resource` to close, refresh, or verify resources whose lifecycles live outside the process image.

### 4.1 Checkpoint Does Not Mean a Snapshot of Every Dependency

Suppose an application has a `DataSource` object, a connection pool with 10 connections, and a DNS cache. The checkpoint can hold these objects in the heap, but the database may close sessions while the process is paused; DNS may change IPs; credentials may expire. Restoring objects does not make the database reopen old sessions or automatically update the DNS cache.

Therefore, a CRaC design typically:

1. Stops accepting new requests/messages.
2. Drains in-flight requests and transactions.
3. Closes pools/sockets/clients via supported APIs.
4. Retains logical configuration and required factories.
5. Creates the checkpoint.
6. After restore, refreshes endpoints/secrets/config and creates new resources.
7. Validates dependencies and only then opens readiness.

This differs completely from CDS: CDS does not require a running application to quiesce and close resources to create a class archive.

## 5. Comparing Through an Application Example

Suppose a Spring Boot application has 20,000 loaded classes, an `ApplicationContext`, a DataSource, a product cache, and a scheduler.

### Using CDS/AppCDS

1. Collect/package the class archive from the appropriate class set.
2. A new JVM starts and maps the archive.
3. The JVM still executes the startup flow: creating beans, building `ApplicationContext`, initializing services, connecting to the database, and populating caches per application code.
4. The main benefit comes from class loading/metadata setup assisted by the archive.

### Using CRaC

1. Start the application completely in the checkpoint environment.
2. Run warm-up to load classes, exercise critical code paths, build appropriate caches, and warm up the runtime.
3. Quiesce workers, drain transactions, and close resources requiring recreation.
4. Create the checkpoint process image.
5. Restore the process from the image.
6. Run `afterRestore`, recreate the DataSource/HTTP client/broker consumer, and validate dependencies.
7. The application can skip most startup/warm-up work performed before checkpoint, depending on runtime restore scope.

### State Outcomes

| Component | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Archived class metadata | Can be reused | May already reside in checkpointed runtime state; not a shared class archive. |
| Spring bean graph | Recreated when a new JVM starts up | Can be preserved in the heap and restored along with the process. |
| `ApplicationContext` | Startup flow creates a new context | Existing context can be restored; does not automatically re-run constructors/`@PostConstruct`. |
| Application cache | Reloaded per startup logic; only eligible archived objects are shared | In-heap caches can be preserved, but require freshness/version validation. |
| JIT/runtime warm-up | Does not restore full execution state from a previous run | Can retain warmed-up runtime state depending on implementation capabilities. |
| Database pool | Created fresh per startup logic | Must be checked/closed and typically recreated after restore. |
| In-flight requests | Not restored from archive | Must be drained before checkpoint; do not snapshot mid-incomplete transaction/request. |

## 6. What CDS/AppCDS Does Not Save

CDS/AppCDS is not a tool for saving arbitrary application state. Specifically, do not expect the archive to retain:

- Current values of every field in singleton beans.
- Lists of currently logged-in user sessions.
- Queued or in-flight requests.
- Thread stacks and monitor/lock states of a run.
- Contents of open connection pools and socket peers.
- Uncommitted database transactions.
- In-flight message broker offset/ack state.
- Dynamic caches holding recently queried data from the prior run, except the very limited subset under the JVM-supported archived object mechanism.
- Credentials or tokens refreshed during a run.

Some static/immutable objects can be archived by the JVM if they satisfy CDS conditions, but do not design the application assuming any serializable or static final object is automatically placed in the archive.

## 7. What CRaC Does Not Guarantee

CRaC has a broader process state scope, yet it is also not a system-wide consistent snapshot. Do not assume a checkpoint guarantees:

- An open database transaction can continue after restore.
- TCP sockets remain connected to the same server or endpoint.
- DNS, routes, service discovery, and IPs stay the same.
- Credentials, access tokens, leases, or certificates remain valid.
- Broker consumers retain old assignments, delivery tags, or receipt handles.
- Schedulers ran on schedule while the process was checkpointed.
- Filesystems, mounts, cgroups, PID namespaces, and CPU/kernel on another host are completely compatible.
- In-heap caches remain fresh compared to source data.

CRaC restores process state; the application and external systems still need to coordinate lifecycle, consistency, and readiness.

## 8. State Models: Class Archive vs. Process Image

The two mechanisms can be visualized as follows:

```text
CDS / AppCDS
-------------
JDK class data + application class data
                 |
                 v
          Shared archive (.jsa)
                 |
       +---------+---------+
       |                   |
       v                   v
   JVM instance A      JVM instance B
   new heap            new heap
   new threads         new threads
   startup flow        startup flow


CRaC
----
Running JVM process
  heap + runtime + threads + app state
                 |
                 v
       beforeCheckpoint resources
                 |
                 v
          Process checkpoint
                 |
                 v
       Restore same process state
                 |
                 v
       afterRestore resources
                 |
                 v
          Application resumes
```

A CDS archive is designed to be used by many compatible JVMs. A CRaC checkpoint represents the state of a specific process, not shared class data for many fresh processes to map like an AppCDS archive.

## 9. Startup Performance: The Two Mechanisms Reduce Different Costs

CDS/AppCDS primarily reduces costs related to class data and class loading. The benefit is usually more pronounced in applications with many classes, large frameworks, or multiple JVMs starting on the same host.

CRaC can eliminate much more startup work because the process is restored from a running and warmed-up state. If the application has already built `ApplicationContext`, loaded caches, and executed critical code paths before checkpoint, those states can be restored with the process. However, dependency reconnection, credential refresh, and readiness validation still contribute to startup-to-ready time.

Do not compare the two mechanisms by a single startup number. Measure:

- Cold start without CDS/CRaC.
- Cold start with CDS/AppCDS.
- Restore with CRaC.
- If combined, CRaC restore from a runtime that used CDS/AppCDS when creating the checkpoint.

Use the same application build, CPU/memory limits, dependencies, workload, and readiness criteria. Measure multiple times, record percentiles, and distinguish process launch from the moment the application actually accepts traffic.

## 10. Creating and Using CDS/AppCDS in a Pipeline

A CDS/AppCDS pipeline typically has these steps:

1. Build the application and dependencies.
2. Run the application or a class-loading workload to collect a class list.
3. Create the archive in static or dynamic mode as supported by the JDK.
4. Launch a new JVM with the archive.
5. Check logs to confirm the class archive is used.
6. Measure startup time and memory against the baseline.

Example of collecting a class list for a run:

```bash
java \
  -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp app.jar \
  com.example.Application
```

Once the class list exists, create the archive using the syntax supported by the corresponding JDK, for example:

```bash
java \
  -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-cds.jsa \
  -cp app.jar
```

Options and classpath/module path conditions can vary by JDK version. Some modern AppCDS workflows use simpler dynamic archives. Consult the specific JDK documentation rather than copying commands across vendors/versions without verification.

When running with an archive, you can use `-Xshare:auto` so the JVM uses the archive if available or skips it if incompatible; `-Xshare:on` requires CDS to be used and may cause the JVM to fail if impossible; `-Xshare:off` disables class data sharing. `-Xlog:cds` logging is helpful to see whether the archive was mapped and which classes were skipped.

## 11. Creating a CRaC Checkpoint in a Pipeline

A CRaC pipeline requires additional steps that AppCDS does not:

1. Provision an environment compatible with checkpoint/restore.
2. Start the application with a defined runtime and configuration.
3. Run a representative warm-up profile.
4. Confirm warm-up is complete and the application is in a suitable state.
5. Switch readiness to refuse traffic and drain new work.
6. Close/prepare resources via `beforeCheckpoint`.
7. Trigger checkpoint according to the JDK/CRaC runtime.
8. Confirm checkpoint completion before packaging.
9. Restore in a compatible environment and run smoke tests.
10. Refresh dependencies and open readiness only after validation.

CRaC requires managing resource lifecycles, artifact compatibility, and checkpoint image security. An AppCDS archive is usually simpler operationally because it does not contain the application heap state of a running process.

## 12. Can CDS/AppCDS and CRaC Be Combined?

In terms of goals, the two mechanisms are not mutually exclusive: CDS/AppCDS can assist class loading in the JVM used to create the checkpoint; CRaC can checkpoint the process after the application has warmed up. However, practical benefits and combinability depend on the specific JDK/vendor/build, how the archive is built, how the JVM is launched, and the CRaC runtime.

A workflow that can be tested:

1. Create the AppCDS archive from the pinned application build.
2. Launch the checkpoint builder with the same JDK and archive.
3. Warm up the application.
4. Create the CRaC checkpoint.
5. Restore with the exact runtime image/configuration and verify results.

In this model, AppCDS can speed up launching the builder; CRaC saves the process state after warm-up. During CRaC restore, the JVM restores the process image rather than simply starting a new JVM and loading the AppCDS archive from scratch.

Do not assume combining both mechanisms always yields additive gains. If the CRaC checkpoint is already created after full warm-up, AppCDS startup savings in the builder may have little impact on final restore time. It may still make checkpoint creation faster or benefit a cold-start fallback path. Benchmark all three configurations.

## 13. Compatibility of CDS/AppCDS

A CDS archive has constraints tied to the JDK and how the application is run. The archive may go unused or be rejected if the environment is incompatible.

Factors to check:

- JDK vendor, version, and build.
- Base archive matching the runtime.
- Classpath/module path and JAR locations.
- Class loaders and class-loading mechanism.
- Whether class bytecode/dependencies changed compared to when the archive was created.
- JVM options affecting CDS.
- Operating system, architecture, and archive mapping conditions.

Some classes may not be archived or shared due to class loaders, bytecode transformation, instrumentation, or JVM conditions. This does not necessarily cause the application to fail; the JVM can load classes normally depending on the `-Xshare` mode.

Do not copy an AppCDS archive to a different runtime without checking. If the archive is skipped in auto mode, the application may still run, but the startup benefit disappears. If using a mode that requires sharing, a mismatch can prevent the JVM from starting.

## 14. Compatibility of CRaC Checkpoints

A CRaC checkpoint has broader environmental constraints than a class archive. Restore capability depends on process state, runtime, kernel, and checkpointed resources.

The checkpoint manifest should record:

- Application build and container image digest.
- JDK vendor/version/build and CRaC implementation.
- CRIU version/capabilities if used.
- OS/kernel/CPU architecture and feature baseline.
- Container runtime, namespaces, cgroups, and mount configuration.
- Native libraries, agents, and drivers.
- Checkpoint configuration, resource callback results, and artifact checksums.
- Dependency/configuration assumptions that require refreshing after restore.

Do not use checksums as proof of compatibility. Checksums only confirm content has not changed since hashing; a restore test proves the artifact works on the target environment.

## 15. Security and Saved Data

A CDS/AppCDS archive primarily contains class data, yet still requires managing integrity and artifact provenance. An archive can expose internal class names, package names, dependencies, and application structure.

A CRaC checkpoint carries greater risk because it can contain in-memory data:

- Passwords, tokens, API keys, and private keys.
- Session cookies and user information.
- Request/response payloads and business data.
- Caches, connection configuration, and internal endpoints.
- Other sensitive data residing in heap/native memory.

For both, control read/write permissions, checksums/signatures, and retention. For CRaC, encrypt the checkpoint at rest/in transit, restrict who may restore/read images, and do not attach raw images to regular tickets/chats.

If warm-up loads production data into the heap, the checkpoint may save that data. Prefer fixtures or test data and refresh sensitive caches after restore.

## 16. Selection Table by Need

| Need | CDS/AppCDS | CRaC |
| --- | --- | --- |
| Reduce class loading time | Directly suitable | Indirectly, since loaded classes are inside process state |
| Share class metadata across multiple JVMs | Suitable | Not the goal of a checkpoint |
| Reduce framework/bean initialization overhead | Reduces only the class loading part; framework still initializes | Can restore already-created context/bean state |
| Retain warmed-up caches | Does not keep arbitrary dynamic caches | Can preserve in-heap caches; requires freshness check |
| Retain runtime/JIT warm-up state | Not a runtime snapshot of a run | Can retain portions of runtime state depending on implementation |
| Restore a running process | No | Yes |
| Reduce cold start with minimal operational changes | Usually easier to deploy | Requires checkpoint/restore environment and resource integration |
| Suit many independent JVM instances | Archive can be reused if compatible | Each process needs a compatible checkpoint; do not use one image as a shared class archive |
| Need to close/reopen network resources | No special checkpoint lifecycle | Usually requires Resource callbacks |
| Need to protect snapshots containing heap data | Does not store full application heap | Yes, checkpoint may contain sensitive in-memory data |

## 17. When Should You Choose CDS/AppCDS?

CDS/AppCDS is usually a reasonable choice when:

- Startup is dominated by class loading and class metadata setup.
- The application has many classes/framework dependencies.
- You want to preserve the standard JVM startup model.
- There is no need to restore object graphs or runtime state of a previously running process.
- You want to share the archive across multiple compatible JVMs in the same environment.
- You do not want to introduce a resource checkpoint/restore workflow into the application.

This is typically the less invasive startup optimization step. You can start with the JDK's default CDS, then evaluate AppCDS if application classes still generate significant overhead.

## 18. When Should You Choose CRaC?

CRaC is appropriate when:

- Startup involves heavy steps beyond class loading: framework initialization, object graphs, caches, JIT warm-up, or runtime preparation.
- Instances need to reach readiness quickly in a scale-out environment.
- A compatible and controllable checkpoint/restore environment can be created.
- The application can quiesce/drain work and manage resource lifecycles.
- Dependencies, credentials, DNS, and caches can be refreshed after restore.
- The organization can protect checkpoint images as sensitive artifacts.

CRaC is not a good choice if the application holds many non-recreatable resources, has long-running transactions that cannot be drained, depends on unsupported native libraries, or runs in an uncontrolled restore environment. Test early with real dependencies before taking it to production.

## 19. When Should You Use Both?

Combining them can make sense if:

- AppCDS helps reduce launch time of the checkpoint builder or cold-start fallback.
- CRaC reduces restore-to-readiness time by preserving warmed-up state.
- The specific JDK/runtime supports the combined workflow.
- Benchmarks prove overall benefits outweigh the cost of creating and managing both artifacts.

Do not combine them solely because both are startup features. Adding both an archive and a checkpoint increases artifact count, compatibility metadata, and pipeline stages. If AppCDS does not significantly improve builder time or the fallback path, it may not be worth maintaining.

## 20. Designing a Fair Benchmark

To compare, use the same:

- Application build, dependency versions, and runtime image.
- CPU/memory limits and host class.
- Database/broker/API dependencies and network conditions.
- Warm-up request profile and test data.
- Readiness criteria and smoke workload.
- Iteration count, measurement points, and percentiles.

Configurations to measure:

| Configuration | How to run | What it measures |
| --- | --- | --- |
| Baseline | JVM cold start, no AppCDS/CRaC | Startup baseline. |
| CDS/AppCDS | JVM cold start with archive | Benefit of class sharing. |
| CRaC | Restore process checkpoint | Benefit of restoring a warmed-up process. |
| CDS + CRaC | Create checkpoint from a JVM using the archive, if supported | Overall benefit and additional archive overhead. |

Measure separately:

- Process start/restore time.
- Time until `afterRestore` completes.
- Dependency reconnection time.
- Time to readiness.
- Time to first successful request.
- CPU, RSS, heap, and memory footprint.
- Error rate and p50/p95/p99 latency after traffic opens.
- Archive/checkpoint size and creation/transfer time.

A configuration may restore the process very quickly yet take a long time reconnecting to the database. Therefore, the primary user-experience metric is usually restore-to-ready time and request latency, not just when the JVM process appears.

## 21. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| AppCDS saves the entire application heap | AppCDS stores class data and certain eligible archived objects; it is not a general heap snapshot. |
| CDS preserves initialized Spring beans | A new JVM still runs Spring startup and creates new beans/context. |
| CRaC is just advanced AppCDS | CRaC checkpoints process state, encompassing far more runtime/application state than a class archive. |
| CRaC keeps all sockets alive | External sockets/resources can become stale or invalid; they must be prepared and reconnected. |
| CDS and CRaC use the same file type | CDS uses a class data archive (usually `.jsa`); CRaC uses a runtime/platform-specific process checkpoint image. |
| A CRaC checkpoint can be shared by any JVM | A checkpoint is bound to a specific process and compatible environment. |
| Valid checksums prove restore works | Checksums only verify integrity; a restore test is required. |
| CRaC is always faster than AppCDS | Depends on the startup bottleneck, resource reconnection, and pipeline overhead. |
| Combining both always adds up benefits | Must be benchmarked; AppCDS may primarily benefit the checkpoint builder or cold-start fallback. |

## 22. Testing CDS/AppCDS

AppCDS tests should confirm that the archive is actually used and does not alter behavior:

1. Create the archive from the exact application build and runtime.
2. Run a new JVM with `-Xshare:auto` or the selected mode.
3. Enable `-Xlog:cds` to observe archive mapping/loading.
4. Confirm classpath/module path compatibility.
5. Run startup smoke tests and a representative workload.
6. Measure startup time and memory against the baseline.
7. Test an incompatible archive to confirm fallback/error behavior per `-Xshare` mode.
8. Test when dependencies/JARs change to determine whether the archive is skipped or rejected.

Do not conclude the JVM used the archive merely by seeing a `.jsa` file. Read the CDS logs and check runtime behavior.

## 23. Testing CRaC

CRaC tests must verify process state and resource lifecycles:

1. Start the application using a compatible JDK/CRaC runtime.
2. Run the warm-up workload.
3. Verify cache/JIT/readiness against criteria.
4. Trigger `beforeCheckpoint` via a real checkpoint workflow and drain workers/transactions.
5. Create the checkpoint image.
6. Mutate dependencies across the checkpoint interval: DNS, database, broker, or credentials.
7. Restore the process in a compatible environment.
8. Confirm `afterRestore` refreshes/recreates resources.
9. Check readiness and run business smoke tests.
10. Measure restore-to-ready time and check that data is not stale/duplicated.

Unit tests invoking callbacks directly do not replace real checkpoint/restore tests on the target JDK, kernel, and CRIU/container runtime.

## 24. Testing the Combined Workflow

If using CDS/AppCDS and CRaC together:

1. Build the application artifact and create the AppCDS archive.
2. Confirm the checkpoint builder JVM actually maps the archive.
3. Run the warm-up profile.
4. Create the CRaC checkpoint.
5. Restore using the pinned runtime image and configuration.
6. Confirm CRaC callbacks and dependency recovery.
7. Measure restore-to-ready.
8. Compare against CRaC-without-AppCDS and AppCDS-without-CRaC configurations.
9. Test cold-start fallback if the checkpoint cannot be used.
10. Record a manifest linking the JAR, AppCDS archive, runtime image, and CRaC checkpoint.

If the AppCDS archive is no longer compatible after JARs/dependencies change, recreate both the archive and the checkpoint from the same build. Do not mix a class archive from a new build with a process checkpoint from an old build.

## 25. Security and Artifact Lifecycle

Both CDS/AppCDS archives and CRaC checkpoints require integrity/provenance, though their sensitivity levels differ.

For CDS/AppCDS:

- Control the archive creation source and runtime version.
- Bind the archive to the application build/classpath.
- Verify checksums/signatures if stored in an artifact registry.
- Do not use archives from untrusted sources.

For CRaC:

- Assume the checkpoint may contain secrets and user data in memory.
- Encrypt at rest/in transit and restrict read/restore permissions.
- Do not attach raw images to regular tickets/chats.
- Use retention and cleanup with references/leases to avoid deleting images currently being restored.
- Refresh credentials and sensitive caches after restore.

Do not put secrets into the manifest of either artifact. The manifest should store only versions, checksums, build identity, and required metadata.

## 26. Decision Checklist

- [ ] Identified whether the startup bottleneck is class loading, framework initialization, warm-up, or dependency reconnection.
- [ ] If mainly class loading, benchmarked CDS/AppCDS before deploying CRaC.
- [ ] Understand that AppCDS does not save the entire heap or Spring bean state.
- [ ] Understand that CRaC checkpoints save broader process state but do not guarantee external dependencies remain valid.
- [ ] Pinned JDK vendor/version/build and application dependencies.
- [ ] For AppCDS, archive is generated from the exact classpath/module path and verified via CDS logs.
- [ ] For CRaC, warm-up profile, resource callbacks, and readiness gate are in place.
- [ ] Identified which resources close before checkpoint and recreate after restore.
- [ ] Caches/credentials/endpoints have a post-restore freshness policy.
- [ ] Verified archive/checkpoint compatibility with the target runtime.
- [ ] Performed real CRaC restore testing, not just manual callback invocation.
- [ ] If combined, benchmarked AppCDS-only, CRaC-only, and combined configurations.
- [ ] Manifest properly links the build, archive, runtime image, and checkpoint.
- [ ] Artifacts are protected according to sensitivity; in particular, checkpoints may contain heap data.

## 27. Conclusion

CDS/AppCDS and CRaC optimize startup across two different scopes. CDS/AppCDS stores class data and certain eligible archived objects so a new JVM loads classes more efficiently; it does not restore the application heap, threads, Spring bean graph, or connection pools from a previous run. CRaC checkpoints a running process and can retain heap/runtime state and warm-up, but requires preparing and recovering resources because databases, DNS, brokers, credentials, and other dependencies still change independently.

Choose CDS/AppCDS when the bottleneck is mainly class loading and you want to retain the standard startup flow. Choose CRaC when you need to restore warmed-up runtime state and can manage the checkpoint/restore lifecycle. They can be combined if the JDK supports it and benchmarks prove a benefit, provided the build, archive, and checkpoint are accurately linked. Evaluate using time to readiness and first successful request, not just process launch time.
