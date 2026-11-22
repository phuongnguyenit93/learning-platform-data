# Evaluating CRaC Support for Libraries and Versions in Use

A Java application typically depends on many libraries: web frameworks, JDBC drivers, connection pools, HTTP clients, message broker clients, caches, logging, metrics, native libraries, and internal components. When using CRaC, it is not sufficient to merely confirm that the application compiles with a JDK that has the CRaC API and then conclude that the entire stack is compatible.

A checkpoint captures the state of a process. Each library may hold resources with their own lifecycles: sockets, file descriptors, threads, executors, timers, locks, native handles, TLS sessions, connection pools, or connection state to external services. After restore, those resources may have expired or may no longer be appropriate for the current environment.

Therefore, CRaC support must be evaluated for the **exact library version, exact version, exact CRaC JDK version, and exact runtime environment**. A library may support CRaC in a newer version but not in the version the application is currently using. A framework with CRaC integration does not automatically guarantee that every transitive library in the application is safe.

The goal of the evaluation is to determine:

- Which libraries the vendor has officially declared CRaC support for a specific version.
- Which libraries self-manage their lifecycle using a CRaC Resource or an equivalent integration mechanism.
- Which libraries require the application to manually close, recreate, or verify resources.
- Which libraries have no evidence of support or have unresolved limitations.
- Which JDK, CRIU, operating system, and native dependency versions have been verified.
- Which tests must be run before bringing a checkpoint into deployment.

## 1. CRaC support is not just about compile-time compatibility

There are at least four aspects to distinguish:

1. **Compile-time compatibility**: the library can be compiled or run on the Java/JDK version in use.
2. **Checkpoint compatibility**: the library's state can be saved during a checkpoint without encountering unsupported resources or activities.
3. **Restore compatibility**: after the process is restored, the library can continue to operate correctly or re-establish invalidated resources.
4. **Operational support**: the vendor has documentation, supported versions, error-handling procedures, and tests for the specific CRaC environment.

A library may pass compile-time checks but still fail at restore. For example, an HTTP client may create objects normally but hold a connection pool containing stale sockets. The application restores successfully, but the first request receives a connection reset error.

Conversely, a library that does not directly implement `org.crac.Resource` may still work fine if it only holds pure Java data or if the application manages its resources through a suitable wrapper. The presence or absence of a Resource class is merely one indicator to consider, not a final conclusion.

### Four questions when evaluating a dependency

| Question | Evidence to look for |
|---|---|
| Does this version run on the target JDK? | Java baseline, bytecode level, module and compatibility matrix |
| Are there any resources that need preparation before a checkpoint? | Lifecycle documentation, list of socket/thread/file/native resources |
| After restore, does the library self-recover or does the application need to intervene? | CRaC integration, callbacks, close/reopen API, or reconnect instructions |
| Has the vendor confirmed the version combination in use? | Official documentation, release notes, resolved issues, and support matrix |

Do not rely on a generic "library supports CRaC" statement. Record the specific artifact version, JDK, platform, and feature scope that has been confirmed.

## 2. Classifying support levels

For consistent evaluation, each dependency can be classified into the following levels. This is an internal rating scale for the project; it does not replace the official support level declared by the vendor.

| Level | Meaning | Handling |
|---|---|---|
| A — Officially supported | Vendor confirms CRaC for the exact version or version range, JDK, and target platform | Use as directed; still run application integration tests |
| B — CRaC-aware integration | Library has a Resource/callback or official integration module, but support scope is conditional | Verify conditions, callback order, and version-specific limitations |
| C — Application-managed | No full automatic integration, but the public API allows safely closing, recreating, and verifying resources | Write an adapter/resource at the application level and test real restore |
| D — Unverified | May run in some trials but lacks sufficient documentation or evidence | Do not treat as supported; add trials and confirm |
| E — Unsupported/incompatible | Vendor declares no support or a known unfixable error has been identified in the target configuration | Upgrade, replace, or remove the dependency from the checkpoint path |

Add verification status to avoid confusion:

- **Documented**: official documentation describes the support.
- **Tested**: the version combination has passed tests run by the project.
- **Vendor-confirmed**: the vendor has confirmed via documentation or support channels.
- **Limited**: only certain features or environments are supported.
- **Unknown**: insufficient information available.

For example, a library may be classified as "B — CRaC-aware integration, tested on JDK A on Linux x86_64, not confirmed on JDK B". Do not reduce this to "B — supported everywhere".

## 3. Compiling the actual dependency list

Evaluation starts from the dependencies the application actually packages and runs, including transitive dependencies. Looking only at direct declarations in the build script will miss many important components.

### Maven

List dependencies in the runtime scope:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

The dependency tree can be exported to a file to store alongside the evaluation record:

~~~bash
mvn dependency:tree -Dscope=runtime -DoutputFile=target/runtime-dependencies.txt
~~~

If a library appears with multiple versions, examine dependency mediation and the final version selected. A direct dependency declaring version A does not mean the runtime actually uses A if another dependency pulls in version B and Maven selects B by its resolution rules.

### Gradle

List the runtime configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To understand why a particular version was selected:

~~~bash
./gradlew dependencyInsight --dependency <library-name> --configuration runtimeClasspath
~~~

Also check configuration-specific scenarios such as the runtime of integration tests, plugins, or deployment modules if they are packaged into the same process.

### Components not to overlook

- Direct and transitive dependencies.
- Framework and starter/autoconfiguration modules.
- JDBC drivers and connection pools.
- HTTP clients, TLS providers, and DNS resolvers.
- Message broker, Redis, or cache clients.
- Logging backends, async appenders, and exporters.
- Metrics, tracing, and telemetry exporters.
- Schedulers, executors, event loops, and thread pools.
- Native libraries, JNI, Java agents, and profilers.
- Dynamically loaded plugins or libraries via custom class loaders.
- Internal libraries developed by the organization.

Not every dependency carries the same risk. A library that only processes pure Java JSON typically has fewer external resources than a database driver. However, the static state, threads, caches, and lazy initialization of each library must still be examined.

## 4. Identifying library resources and behavior

After obtaining the dependency tree, classify each library according to what it owns or creates at runtime.

| Library type | Resources/behavior to consider | Post-restore question |
|---|---|---|
| JDBC driver | Socket, TLS, native code, connection state | Are old connections closed and can the driver create new ones? |
| Connection pool | Connections, housekeeping threads, timers | Can the pool be recreated or recovered via a supported API? |
| HTTP client | Socket pool, DNS cache, TLS session, selector/event loop | Does the client discard old connections and reconnect? |
| Message client | TCP connection, consumer group, heartbeat, offset | Does the client reconnect/rejoin and safely handle duplicate messages? |
| Cache client | Socket, cluster topology, local cache | Is the cache and topology re-verified? |
| Scheduler | Threads, timers, run schedule | Are tasks duplicated or missed after restore? |
| Executor/event loop | Threads, queue, selector | Are stopped threads properly recreated? |
| Logging | File handles, async queue, background thread | Does the appender still write without losing logs? |
| Metrics/tracing | Exporter socket, batch queue, periodic task | Does the exporter flush/reconnect and avoid duplicate sends? |
| File/storage client | File descriptor, lock, memory mapping | Are files/locks/mounts still valid? |
| Native/JNI library | Native pointer, handle, thread, callback | Is native state supported by CRIU/runtime? |
| Cryptography/TLS | Native provider, entropy, session/cache | Do the provider and key material remain valid? |

A library may fall into multiple categories. For example, a broker client may have a network connection, a heartbeat thread, timers, buffers, and callbacks. The evaluation must consider its entire lifecycle.

### Distinguishing Java state from external resources

A Java object can be restored in the heap while the resource it represents has changed. For example:

- A `Connection` object still exists but the socket has been closed by the peer.
- A `ScheduledExecutorService` object still exists but worker threads are no longer in a continuable state.
- A file wrapper object remains in the heap but the file descriptor or lock is no longer valid.
- A cache object still holds data but the TTL expired during the checkpoint.
- A TLS client object still holds an old session but the certificate or endpoint has changed.

Do not infer the validity of an external resource from a non-null Java object.

## 5. Finding evidence of support in documentation and release notes

For each dependency, look for information specific to the exact artifact and version in use. The highest-value sources are typically official documentation, release notes, and compatibility matrices from the vendor.

### Order of sources to review

1. **Vendor's official CRaC documentation**: describes supported versions, configuration, and required callbacks.
2. **Release notes/changelog**: look for changes related to checkpoint, restore, socket, thread, native state, or CRaC.
3. **Compatibility matrix**: cross-reference JDK, OS, architecture, and runtime.
4. **Framework integration documentation**: see which resources the framework manages and which dependencies still need separate handling.
5. **Issue/bug tracker**: look for known issues, fix versions, limitations, and workarounds.
6. **Official tests or samples**: identify tested combinations and how to reproduce them.
7. **Vendor confirmation**: use when documentation is unclear or the version in use falls outside the published matrix.

When reading release notes, look for terms such as CRaC, checkpoint, restore, snapshot, restart, reconnect, native state, file descriptor, thread, socket, and lifecycle. Do not only search for the keyword "CRaC": a reconnect or thread lifecycle bug fix may be very significant even if the release note does not directly mention CRaC.

### Evidence that must be recorded

A note saying "read the docs" is not sufficient for someone else to verify. Record:

- URL or name of the official documentation.
- Documentation version and access date.
- Artifact name and version referenced.
- Supported JDK/OS/architecture.
- Required configuration conditions or APIs.
- Known limitations.
- Internal tests run and their results.

If documentation only confirms a newer version than the one in use, do not infer that the older version is supported. If an issue says a bug was fixed in version 4.2.1, verify that the application is actually resolving 4.2.1 and not still using 4.1.x.

## 6. Inspecting the artifact and metadata of the running version

After identifying the dependency tree, inspect the actual artifacts in the package to avoid evaluating the wrong version.

You can use:

~~~bash
jar tf path/to/library.jar
~~~

To view dependency or module metadata, use the appropriate tool for the artifact format, such as `jdeps` for bytecode dependency relationships:

~~~bash
jdeps --recursive --summary path/to/library.jar
~~~

If you need to view the manifest:

~~~bash
unzip -p path/to/library.jar META-INF/MANIFEST.MF
~~~

These commands help identify content, packages, modules, and some metadata. They do not prove that a library supports CRaC. Finding a class whose name contains "crac" or a dependency on `org.crac` is merely a clue; you must cross-reference the documentation, actual behavior, and version.

### Looking for signs of CRaC integration

You can inspect the artifact's packages/classes:

~~~bash
jar tf path/to/library.jar | grep -i crac
~~~

Or inspect service provider entries:

~~~bash
jar tf path/to/library.jar | grep META-INF/services
~~~

An empty result does not prove the library has no support. The library may register a resource through other code or rely on a framework adapter. Conversely, finding a class that implements Resource does not prove that every component of the library is safe to restore.

### Verifying resolved dependencies

With Maven/Gradle, check the dependency tree after the build. If the application uses a fat JAR or shaded JAR, verify the actual version packaged and avoid relying solely on the filename in the build tool's cache.

If multiple modules use different versions, record each artifact. For example, the framework core may be on a newer version while a starter or client module remains on an older version due to a dependency override.

## 7. Evaluating JDK and CRaC runtime support

A library is confirmed only within a specific environment. Beyond the library version, record:

- CRaC JDK distributor and version.
- Java language/runtime baseline version.
- CRaC API version compiled against and running on.
- CRIU version.
- Linux kernel and distribution.
- CPU architecture.
- Container runtime, namespace, cgroup, and capabilities.
- Native libraries and system libraries.

Do not assume that all JDKs with the same Java version name package or behave identically for CRaC. One distribution may carry different patches, options, or packaging procedures.

### API dependency and JDK runtime

The application may need a dependency that provides the `org.crac` API to compile resources. The declaration method and API version must match the CRaC JDK and the distributor's instructions.

Do not add an arbitrary CRaC API version just to make the build succeed. The compile-time API does not replace the JDK, CRIU, or kernel feature implementation required at runtime. Avoid mistakenly packaging duplicate API classes into a fat JAR if the runtime instructions require using the API from the JDK.

### Native dependencies

If a library uses JNI, native executables, or FFM/native access, additional evaluation is required:

- Can native handles be checkpointed/restored?
- Are there native threads or callbacks running?
- Are file descriptors, shared memory, or device handles supported?
- Is the binary compatible with the architecture, libc, and kernel in the restore environment?
- Does the library have an official API to release and recreate native state?

A Java wrapper may be restored in the heap while the native pointer inside it is no longer valid. Do not copy or reuse native pointers if the vendor has not confirmed the approach.

## 8. Evaluating framework CRaC integration

A framework may help manage some resources, but the exact scope of integration must be identified.

### Things to check

- Which version does the framework support for CRaC JDK?
- Is there a dedicated adapter or module for CRaC?
- Which resources does the framework register on its own?
- Are beans/clients created by the application automatically managed?
- Can resources be registered twice on restore?
- How is the callback order between the server, pool, broker, and application resources defined?
- Can resource order or grouping be configured according to dependencies?
- Is readiness/liveness maintained correctly during restore?

Do not infer that the entire stack is supported simply because the framework has an integration module. For example, a framework may stop the embedded web server but have no knowledge that the application independently created a native client or a scheduler outside the container.

### Framework and sub-libraries

Create an ownership table:

| Component | Who owns the lifecycle? | Needs verification |
|---|---|---|
| Embedded web server | Framework or application | Listener, accept thread, active requests |
| JDBC DataSource | Framework/pool/library | Pool close/recreate and validation |
| HTTP client | Application/library | Connection pool, DNS, and TLS |
| Message consumer | Application/library | Pause, ack, rejoin, and offset |
| Scheduler | Framework/application | Running jobs, duplicate schedules |
| Custom native client | Application/vendor | Native state and API recreate |

Each resource should have one clearly responsible owner. If both the framework and the application register a resource to close a pool or server, double-closing, double-opening, or an unsafe order may occur.

## 9. When a library has no built-in CRaC support

The absence of official integration does not mean the library must be replaced immediately. First determine whether the library has a public API that allows lifecycle management.

An application-level adapter may be appropriate when:

- Resources can be fully closed before the checkpoint.
- A factory is available to create new instances after restore.
- A health check or real verification operation is available.
- Services use a stable provider/proxy rather than holding direct references to old instances.
- The vendor does not prohibit or warn against this approach.

An adapter is not appropriate when the library holds native state that cannot be released, has internal threads that cannot be stopped, or has state that cannot be recreated from the public API.

### Resource pattern for managing a client

The example below uses an interface defined by the application. `LibraryClient` represents a client of a library; `ClientFactory` creates new clients; `ClientProvider` holds the current reference so services can obtain the client after restore.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.concurrent.atomic.AtomicReference;

public final class LibraryClientResource implements Resource {

    public interface LibraryClient extends AutoCloseable {
        void verify() throws Exception;

        @Override
        void close() throws Exception;
    }

    @FunctionalInterface
    public interface ClientFactory {
        LibraryClient create() throws Exception;
    }

    public static final class ClientProvider {
        private final AtomicReference<LibraryClient> current =
                new AtomicReference<>();

        public LibraryClient get() {
            LibraryClient client = current.get();
            if (client == null) {
                throw new IllegalStateException("Client is not ready");
            }
            return client;
        }

        LibraryClient detach() {
            return current.getAndSet(null);
        }

        void install(LibraryClient client) {
            if (!current.compareAndSet(null, client)) {
                throw new IllegalStateException("A client is already installed");
            }
        }
    }

    private final ClientFactory factory;
    private final ClientProvider provider;

    public LibraryClientResource(
            ClientFactory factory,
            ClientProvider provider) {
        this.factory = factory;
        this.provider = provider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        LibraryClient oldClient = provider.detach();
        if (oldClient != null) {
            oldClient.close();
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        LibraryClient candidate = factory.create();
        try {
            candidate.verify();
            provider.install(candidate);
        } catch (Exception failure) {
            try {
                candidate.close();
            } catch (Exception closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }
}
~~~

This is a lifecycle pattern, not an adapter that can be applied as-is to every library. In a real application:

- Admission must be closed and requests using the client must drain before detaching.
- The provider must be injected into every consumer; services must not directly hold a reference to the old client.
- The factory must use current configuration and credentials.
- `verify()` must check real operability, not just that the object is non-null.
- If client creation fails, readiness must remain false.
- A rollback policy must be defined for when a checkpoint is cancelled after the client has already been closed.
- Do not recreate threads or schedulers if the library already has an integration that manages them.

If the library has an official CRaC API, prefer that integration. A manual adapter should only be used when the resource lifecycle is well understood and the vendor does not recommend a different approach.

## 10. Evaluating common library categories

### JDBC drivers and connection pools

Verify that the driver supports the target JDK/runtime, the pool has CRaC documentation, and connections are closed before the checkpoint.

Things to test:

- Database restart or failover between checkpoint and restore.
- Credential rotation.
- DNS/endpoint change.
- Old pool closed and new pool created.
- Connection validation executes a lightweight query.
- Multiple instances restoring simultaneously do not cause a connection storm.

Do not evaluate based solely on whether the `DataSource` still exists after restore. The pool object may remain in the heap while all connections inside it are stale.

### HTTP clients and networking

Check the socket pool, selector/event loop, DNS cache, TLS session, proxy configuration, and timeouts.

Things to test:

- Closing connections before the checkpoint.
- Restoring when the remote server has restarted.
- Creating new connections and performing real requests.
- Verifying TLS/certificates and credentials.
- Verifying the event loop/threads are not stopped or duplicated.

### Message brokers

Check whether the client has a lifecycle to pause/close and reconnect/rejoin after restore. Verify the consumer group, partition assignment, offset, heartbeat, and acknowledgment.

Test checkpointing while the consumer is processing a message, then restore and verify that no messages are lost or processed beyond the policy's allowance for duplicates. The application still needs idempotency/deduplication; CRaC does not create a distributed transaction with the broker.

### Cache clients and local caches

Check the connection to the cache server, cluster topology, subscriptions/invalidations, and TTL. Local data in the heap may expire while the process is paused. Determine which caches can be retained, which must be refreshed, and whether cache misses will cause a sudden load spike on the database.

### Logging, metrics, and tracing

Check file appenders, async queues, background exporters, batch buffers, sockets, and periodic tasks. After restore, verify that logs continue to be written, exporters reconnect, and telemetry is not lost or excessively duplicated.

Do not use the fact that console logs still appear as evidence that all appenders or exporters have recovered.

### Schedulers and executors

Check thread lifecycle, running tasks, queues, timers, and periodic schedules. An executor object remaining in the heap does not guarantee that worker threads are ready. Do not call `start()` a second time on a finished Thread; create new workers using the library's API.

Test restoring near the time a job is due to start to verify no jobs are missed or run twice. For business-critical jobs, a lease, idempotency, or persistent state mechanism is needed.

### Native/JNI and system libraries

Require clear documentation on native state and checkpoint/restore capability. If the vendor does not confirm, classify as unverified or unsupported until evidence is available.

Do not assume that a native pointer, file descriptor, or callback stored in the heap will remain valid after restore. If the library has a close/reinitialize API, verify that this is an officially supported procedure.

## 11. Building a compatibility matrix

A matrix lets the development and operations team know exactly which combinations have been verified.

Example structure:

| Component | Artifact/version | CRaC support | JDK/OS tested | Resource owner | Result |
|---|---|---|---|---|---|
| Web framework | Record actual version | Official / partial / unknown | Record specific combination | Framework | Pending / Pass / Fail |
| JDBC driver | Record actual version | Vendor-confirmed / unknown | Record specific combination | App/pool | Pending / Pass / Fail |
| Connection pool | Record actual version | CRaC-aware / manual | Record specific combination | Pool adapter | Pending / Pass / Fail |
| HTTP client | Record actual version | Manual / unknown | Record specific combination | App/client | Pending / Pass / Fail |
| Broker client | Record actual version | Official / limited | Record specific combination | Client adapter | Pending / Pass / Fail |
| Native library | Record actual version | Supported / unsupported | Specific OS/arch | Vendor/app | Pending / Pass / Fail |

For each row, also record:

- Link to documentation or release notes.
- Minimum confirmed version.
- Known limitations.
- Required configuration.
- Test cases and test dates.
- Person/team responsible for updates.

Do not leave "Pass" labels without a version combination. "Pass on Java 21" is insufficient if the project uses multiple JDK distributions or CPU architectures.

## 12. The evaluation process from dependency tree to decision

The process can be performed in the following steps:

### Step 1 — Finalize the target environment

Record the CRaC JDK distribution/version, CRIU, kernel, Linux distribution, architecture, container runtime, and permission configuration. This is the baseline against which compatibility is cross-referenced.

### Step 2 — Export the runtime dependency tree

Obtain all runtime dependencies from Maven/Gradle, including transitive dependencies. Identify the final resolved version and the artifact actually packaged.

### Step 3 — Classify resources

For each library, record the sockets, threads, timers, files, native state, caches, or external connections it owns. Identify who is the owner of the lifecycle.

### Step 4 — Find vendor evidence

Read the CRaC documentation, compatibility matrix, release notes, and known issues. Record the exact version and conditions. If information is unclear, ask the vendor or keep the status as unverified.

### Step 5 — Choose a management approach

Choose one of the following directions:

- Use the library's official CRaC integration.
- Use the framework's integration if it covers the correct resources.
- Write an adapter using the public API when close/recreate is supported.
- Upgrade to a confirmed version.
- Replace or remove an incompatible dependency from the checkpoint process.

### Step 6 — Test each dependency individually

Create a minimal test to prove that the resource can be closed before a checkpoint and recovered after restore. Test the error when the dependency is unavailable and confirm readiness does not open prematurely.

### Step 7 — Test the full application

Run a real checkpoint/restore with the full dependency tree and a production-like configuration. Test request flows, background jobs, telemetry, and business data.

### Step 8 — Record decisions and release conditions

Save the compatibility matrix, limitations, tested versions, result logs, and responsible parties. Only bring a combination into release when mandatory dependencies have appropriate evidence.

## 13. Checkpoint/restore testing for libraries

A compile test or a regular unit test is not sufficient. Testing must be performed on a real CRaC JVM and in the target operating system environment.

### Phases that must be confirmed

1. The application starts with the correct dependency versions.
2. The library creates resources and operates normally.
3. The pre-checkpoint callback is invoked and resources are closed/paused as instructed.
4. The checkpoint completes.
5. The image is restored in the target environment.
6. The post-restore callback recreates or verifies resources.
7. A real operation through the library succeeds.
8. Readiness opens only after mandatory dependencies are ready.

### Scenario matrix

| Scenario | What to verify |
|---|---|
| Normal restore | Resource recovers and real operation succeeds |
| External dependency restart | Client reconnects or reports a controlled error |
| Credential rotation | Client uses current credentials |
| DNS/endpoint change | Client does not use old cached addresses |
| Resource close fails | Checkpoint is not treated as safe |
| Restore callback fails | Instance does not open readiness |
| Multiple restores from the same image | No duplicate Resource, thread, or scheduler registrations |
| Increased concurrent load | No connection storm or unlimited worker growth |
| Normal shutdown | Lifecycle is not confused with a checkpoint pause |
| Multiple interdependent resources | Close/open order is defined and verified |

### Unit tests and integration tests

Unit tests are suitable for testing the adapter:

- `beforeCheckpoint` closes the client.
- `afterRestore` creates a new client.
- If the candidate client fails, it is closed.
- The provider does not expose an unverified client.
- Exceptions propagate and readiness remains false.

Integration tests must demonstrate real behavior:

- CRaC invokes callbacks in the actual lifecycle.
- Socket/file/native state works correctly.
- The database, broker, or external server can restart.
- The application continues to serve after restore.

Do not use mocks to conclude that a native library or socket is supported by CRIU. Mocks only validate adapter logic.

## 14. Version management and dependency upgrades

CRaC support may be added or changed between library versions. Therefore, every dependency upgrade requires updating the compatibility matrix.

When upgrading:

- Determine whether the new version has official CRaC support.
- Read the migration guide and breaking changes.
- Check whether the callback API or resource registration has changed.
- Check whether transitive dependencies have been upgraded or downgraded.
- Re-run checkpoint/restore tests for affected resources.
- Re-measure latency, memory, and recovery time if the lifecycle changes.

Do not upgrade a single dependency if the framework manages versions via a BOM or platform without checking the entire dependency resolution. Forcing a new version may create binary or API conflicts.

### Pinning versions in the production environment

Record the verified versions and avoid using dynamic versions or uncontrolled ranges for critical dependencies. If a build can resolve a different version between two runs, a checkpoint image created from one dependency set may fail when restored against different artifacts, causing difficult-to-investigate errors.

For checkpoint artifacts, store external metadata alongside the image including:

- Application build/version.
- Dependency lockfile or dependency tree.
- JDK distribution/version.
- JVM flags.
- CRIU/kernel/OS/architecture.
- Checkpoint creation timestamp and ID.

This metadata helps identify which combination the image was created from and whether it is compatible with the current restore runtime.

## 15. Signs that require further investigation

| Sign | Possibility to consider |
|---|---|
| Checkpoint reports errors related to threads or file descriptors | Library still has active resources or no CRaC integration |
| Restore succeeds but first request fails | Stale connection, DNS/TLS, or resource not yet recreated |
| Thread count increases after each restore | Worker/executor is initialized twice |
| Abnormal CPU spike after restore | Warm-up, JIT, retries, or duplicate background tasks |
| Logging/exporter stops working | Appender or telemetry client not recovered |
| Native crash after restore | Native state or library does not support the checkpoint/restore environment |
| Error only appears on a specific JDK patch | Version difference in JDK/library/runtime combination |
| Error only appears in a container | Namespace, cgroup, capability, mount, or network difference |
| Error only occurs with a transitive dependency | Actual version differs from the direct dependency being examined |

When investigating, record the stack trace, artifact versions, JDK, CRIU, kernel, and reproduction conditions. Avoid attributing errors to "CRaC in general" before identifying the specific component or version causing the problem.

## 16. CRaC support evaluation checklist

### Inventory and versions

- [ ] The full runtime dependency tree has been exported, including transitive dependencies.
- [ ] The artifact version actually resolved and packaged has been identified.
- [ ] The CRaC JDK distribution/version, CRIU, kernel, OS, and architecture have been recorded.
- [ ] Framework, driver, pool, network client, broker, scheduler, logging, and native libraries have been reviewed.

### Evidence of support

- [ ] The CRaC documentation and release notes for the exact version have been read.
- [ ] The compatibility matrix and known limitations have been checked.
- [ ] Official support has been distinguished from internal trial results.
- [ ] Conclusions are not based solely on finding or not finding a Resource class.
- [ ] Evidence sources and the specific environment combination have been recorded.

### Lifecycle and ownership

- [ ] Resources that need to be closed or paused before a checkpoint have been identified.
- [ ] Resources that need to be recreated or verified after restore have been identified.
- [ ] Each resource has a single owner managing its lifecycle clearly.
- [ ] Providers/proxies do not allow consumers to hold references to old, closed objects.
- [ ] Threads, schedulers, sockets, files, and native state have a supported handling approach.

### Testing and release

- [ ] A real checkpoint/restore has been run on the target JDK and OS.
- [ ] Dependency restart, credential/DNS changes, and recovery failures have been tested.
- [ ] Requests, background jobs, and telemetry after restore have been verified.
- [ ] Readiness opens only after mandatory dependencies are ready.
- [ ] The compatibility matrix has results, limitations, and test dates.
- [ ] Dependency versions and checkpoint metadata have been recorded.

Evaluating CRaC support means confirming a specific combination of library, version, JDK, and environment. The dependency tree reveals which artifacts the application actually runs; vendor documentation defines the scope of support; lifecycle analysis identifies resources that need management; and checkpoint/restore integration tests prove behavior in a real system. By preserving evidence and a compatibility matrix, the development team can clearly decide which libraries to use directly, which need adapters, and which must be upgraded or replaced before bringing CRaC into production.
