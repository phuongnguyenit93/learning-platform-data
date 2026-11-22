# Compatibility by Checkpoint Engine and Vendor Extensions

CRaC enables a Java application to prepare resources before a checkpoint and restore them after a restore. However, the ability to create and restore a checkpoint also depends on the component that captures and restores the process state. This component is commonly called the checkpoint engine or checkpoint/restore implementation. It operates at the runtime and operating system layers, while the CRaC API provides the contract for the application to coordinate resource lifecycles.

Two applications that both implement org.crac.Resource cannot necessarily share the same checkpoint. They may run on different JDK vendors, different engines, different kernels, or rely on vendor-specific extensions. A checkpoint is usually tightly coupled to the runtime and environment combination that created it. Therefore, at release time, it is necessary to clearly specify which engine creates the checkpoint, which versions are supported, which extensions participate, and which conditions must be kept compatible in the restore environment.

## 1. Distinguishing the CRaC API, JDK Runtime, and Checkpoint Engine

A CRaC workflow involves multiple coordinating layers:

~~~text
Java Application
    |
    |  Resource: beforeCheckpoint / afterRestore
    v
CRaC API and framework/library integrations
    |
    v
JDK runtime / CRaC-enabled JVM build
    |
    |  Coordinates checkpoint, threads, and JVM state
    v
Checkpoint engine / native implementation
    |
    |  Captures and restores process state, memory,
    |  file descriptors, and supported OS resources
    v
Kernel, CPU, filesystem, container, and host
~~~

These layers have distinct responsibilities:

- **CRaC API:** provides the contract for applications to register Resources and execute callbacks before checkpoint and after restore.
- **JDK runtime:** integrates CRaC into the JVM, coordinating Java state, the runtime, and required hooks.
- **Checkpoint engine:** performs the native work to save and restore process state according to the platform's capabilities.
- **Vendor extension:** extensions provided by the JDK vendor or platform to add integrations, hooks, Resource adapters, tools, or custom features.
- **Deployment environment:** kernel, CPU, container runtime, filesystem, namespaces, permissions, and external dependencies required by the checkpoint.

For example, an application can use Core.getGlobalContext().register(resource) to register a Resource under the CRaC API. This call does not specify a particular native engine, nor does it prove that a checkpoint created with one engine can be restored on every host.

The checkpoint engine is typically integrated into or invoked by a specific JDK/runtime. Some platforms use CRIU on Linux; some distributions may provide their own integration, tooling, or extensions. Do not infer the engine being used solely from the Java API name. Obtain that information from the documentation of the exact JDK distribution, the checkpoint command, and actual runtime logs.

## 2. What Does the Checkpoint Engine Decide?

The checkpoint engine works with process state below the Java object layer. Depending on the implementation, it may need to save or reconstruct:

- Process memory regions and CPU state required to resume execution.
- Process trees and relationships between supported processes/threads.
- File descriptors, pipes, sockets, and kernel resources supported by the engine.
- Namespaces, cgroups, mounts, and related environment metadata.
- State required to recreate the process inside a container or host.
- Coordination data with external resources or resources requiring special handling.

Support coverage is not identical across all engines and versions. An engine may support a type of socket or namespace in one configuration but not in another. Some resources must be closed before checkpoint, some are supported by the engine, some must be reopened after restore, and some cannot be recovered via checkpoint.

The checkpoint engine does not fully understand the business semantics of Java objects. It may see a file descriptor or memory, but it does not know whether a transaction has committed, whether a message has been acknowledged, or whether a distributed lease still belongs to the application. That is why CRaC Resources and business logic still need to coordinate.

### The Engine Does Not Replace Resource

Suppose an application holds a JDBC Connection object. The engine might handle some native process state, but that does not prove the database session on the server is still valid upon restore. The database is an independent system and continues operating on its own timeline.

Similarly, the engine may restore file descriptor state within its supported scope, but the application must still determine whether the file was modified, whether permissions remain valid, and what logical position had been processed.

Therefore:

- Use CRaC Resources to prepare and restore resources owned by the application.
- Use engine capabilities for resources confirmed as supported by the implementation.
- Use external service APIs to verify or recreate remote state.
- Do not rely on the engine restoring the process to infer that external systems have rolled back to the checkpoint timestamp.

## 3. Not Every Checkpoint Has a Cross-Compatible Format

A checkpoint contains runtime and process state, not an independent Java data file that can be opened on any JVM. The artifact may depend on:

- JDK vendor, version, and build number.
- CRaC runtime/API integration.
- Checkpoint engine version and configuration.
- Kernel version and kernel features used.
- CPU architecture and instruction sets required by machine code/runtime.
- Native libraries, libc, and ABI.
- Container image, filesystem, mount points, and namespaces.
- JVM flags, module path, native agents, and configuration at checkpoint creation time.

Consequently, having the same Java 21 version or both running Linux is not sufficient to prove compatibility. Two images created on two different JDK vendors may have differences in JVM build, native integration, checkpoint engine, and extensions. Even within the same vendor, two different builds or engine versions can still have different compatibility requirements.

Treat a checkpoint as an artifact bound to a verified compatibility profile. That profile must specify the producer (image-creation environment) and consumers (restore environments) allowed to use the artifact.

## 4. Compatibility Axes to Check

| Axis | Information to record | Why it matters |
|---|---|---|
| JDK vendor and build | Vendor, full runtime version, build number | JVM and native integration may differ |
| CRaC API/runtime | API version, implementation, and integration | Callbacks, runtime behavior, or extensions may change |
| Checkpoint engine | Engine name, version, build, and options | Format and recovery capabilities depend on the implementation |
| OS and kernel | Distribution, kernel release, and required configuration | Engine depends on kernel features |
| CPU | Architecture, ABI, and required features | Machine code and CPU state may not transfer across platforms |
| Native dependencies | libc, shared libraries, JNI, and native agents | Process may depend on host ABI and libraries |
| Container | Base image digest, runtime, namespaces, and cgroups | Restore must see a matching filesystem and process environment |
| Filesystem | Mounts, paths, permissions, and filesystem types | File handles and paths may not exist or may have different state |
| JVM options | Relevant flags, agents, module options, and system properties | Options can affect runtime layout or behavior |
| Vendor extensions | Extension name, version, and configuration | Extensions may add custom hooks or formats |
| External resources | Databases, brokers, secret stores, locks, and endpoints | These services do not automatically revert to checkpoint state |

Not every project needs to record every field at the same level of detail. Start from the engine and vendor requirements, then record the factors that can affect restore. Do not enter a placeholder guess to fill a missing field; use unknown or mark it unverified.

## 5. Distinguishing API Compatibility and Checkpoint Compatibility

These are two concepts that are frequently confused:

**API compatibility** refers to the ability to compile and run source code against the API used by the application. For example, a class implementing org.crac.Resource can compile on a JDK that provides the corresponding CRaC API.

**Checkpoint compatibility** refers to the ability of a specific runtime and engine to properly restore a created checkpoint artifact. It involves native state, kernel, CPU, engine version, container, and extensions.

An application can:

- Compile successfully on JDK A.
- Run successfully and create a checkpoint using JDK A with engine X.
- Still fail to restore that checkpoint using JDK B or engine Y.

This is not necessarily a source code bug or a Java API violation. It may be a compatibility limitation of the checkpoint artifact.

Similarly, the fact that two JDKs both provide the org.crac.Resource interface does not prove that callbacks are orchestrated identically in every situation or that their checkpoint images are interchangeable.

## 6. What Can Vendor Extensions Include?

Vendor extensions are additional mechanisms outside the common CRaC API contract. Depending on the vendor, extensions can include:

- Resource adapters for specific frameworks or libraries.
- Pre/post-checkpoint hooks at the runtime or launcher level.
- Automatic Resource registration mechanisms.
- Integrations with connection pools, TLS, native libraries, or client SDKs.
- Custom commands, options, or configurations to invoke checkpoint/restore.
- Environment pre-checks before checkpointing.
- Diagnostic tools to report unready resources or restore failures.
- Native integrations or custom engine patches.

This list describes the kinds of capabilities you may encounter, not a common API that every vendor must provide. Class names, packages, command-line options, callback behavior, and support levels must be verified from official documentation for the exact vendor and exact version.

### Extensions Are Not Automatically Portable Standards

An application may use the standard CRaC API together with a vendor-specific extension. The part using the standard API may be easier to port at the source level, while the extension can bind the application to:

- A specific JDK distribution.
- An extension version.
- A checkpoint engine or engine build.
- A specific framework integration.
- A set of JVM flags or launcher options.

If source code directly calls vendor-specific classes, switching to another JDK may require code or module dependency changes. If the extension is configured only at runtime, the source may compile on multiple JDKs while the checkpoint artifact remains incompatible across engines.

## 7. How to Isolate Vendor-Specific Extensions

When a proprietary extension is needed, isolate it behind an abstraction controlled by the application. Business logic should not depend directly on proprietary class names or callbacks unless necessary.

For example, the application defines a neutral interface:

~~~java
public interface CheckpointIntegration {
    void prepare() throws Exception;

    void restored() throws Exception;

    default void checkpointAborted() throws Exception {
        // Does nothing by default; implementation can restore independently.
    }
}
~~~

An implementation using the standard CRaC API can register a Resource adapter:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceAdapter implements Resource {
    private final CheckpointIntegration integration;

    public CracResourceAdapter(CheckpointIntegration integration) {
        this.integration = integration;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        integration.prepare();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        integration.restored();
    }
}
~~~

The application can have a neutral implementation and separate runtime-specific implementations when genuinely needed. Create a vendor-specific implementation only after identifying the official extension API. Do not invent class names, methods, or JVM flags by guessing.

A possible module structure is:

~~~text
application/
  domain/
    CheckpointIntegration.java
  runtime-crac/
    CracResourceAdapter.java
  runtime-vendor-a/
    VendorACheckpointIntegration.java
  runtime-vendor-b/
    VendorBCheckpointIntegration.java
~~~

The domain module does not depend on the JDK vendor. The runtime-crac module uses the standard CRaC API. Vendor-specific modules are included in the build only when a deployment profile selects the corresponding runtime. If the application deploys on only one vendor, there is no need to create hypothetical adapters; keep the integration small and pin dependencies explicitly.

### Do Not Wrap Extensions to Hide Semantic Differences

An abstraction is useful only if implementations can fulfill the same contract. If vendor A supports restoring one socket type while vendor B does not, you should not create a common method named restoreAllSockets() and pretend the two implementations are equivalent.

Represent capabilities explicitly, for example:

~~~java
public record CheckpointCapabilities(
        boolean supportsUnixSockets,
        boolean supportsTcpConnections,
        boolean supportsFileLocks,
        boolean supportsNativeMappings) {}
~~~

Capability values must be supplied from verified configuration or official runtime metadata. Do not infer them from the vendor name or major version. The application can use the capability profile to reject a configuration that does not meet requirements before creating a checkpoint.

## 8. Compatibility by Checkpoint Engine: Examples With Engine and Native State

CRIU is a checkpoint/restore engine commonly encountered in Linux environments. It operates at the process and kernel layers, while the CRaC runtime coordinates with the JVM and application to prepare Java state. Integration methods, CRIU versions, options, and supported features depend on the JDK distribution and deployment environment.

When a CRaC runtime uses CRIU or a similar engine, verify:

- The engine version is supported by the JDK distribution.
- The kernel has the required features and is configured appropriately.
- Process permissions and capabilities are sufficient for checkpoint/restore operations.
- The container runtime permits the required namespace/cgroup operations.
- Required filesystems and mounts are present in the restore environment.
- Network resources are handled in a manner supported by the engine.
- File descriptors or special native handles are closed, recreated, or handled according to documentation.

Do not install a newer engine version on the host and assume an older JDK will be compatible. A JDK distribution may be built and tested against a specific range of engine versions. Use a vendor-validated combination.

### Example of a Compatibility Profile

An internal release profile may record:

~~~yaml
checkpointProfile:
  id: "linux-x86_64-crac-profile-01"
  java:
    vendor: "recorded-vendor"
    runtimeVersion: "recorded-full-version"
    cracApiVersion: "recorded-version"
  engine:
    name: "criu"
    version: "recorded-version"
    optionsProfile: "production-default"
  host:
    os: "recorded-distribution"
    kernel: "recorded-kernel"
    architecture: "x86_64"
    libc: "recorded-libc"
  container:
    imageDigest: "sha256:..."
    runtime: "recorded-container-runtime"
  extensions:
    - name: "vendor-resource-integration"
      version: "recorded-version"
  restorePolicy:
    allowedProfile: "linux-x86_64-crac-profile-01"
    coldStartFallback: true
~~~

The recorded-* values and digest above are illustrative placeholders. The pipeline must replace them with actual information collected from the checkpoint creation environment. Do not copy this profile into deployment configuration without verifying engine and vendor requirements.

## 9. Controlling Extension and Dependency Versions

Vendor extensions can be packaged in multiple ways:

- Maven/Gradle dependencies included in the application artifact.
- Modules or agents added to the JVM.
- Native libraries installed in the container/base image.
- Scripts or binaries invoked by the checkpoint launcher.
- Runtime configuration stored outside the JAR.

Each packaging method has its own version lifecycle. Recording only the application JAR version is insufficient.

Record:

- Extension name and version.
- Artifact coordinates or package identifier.
- Hash of the JAR, agent, or binary.
- Native library version and hash if applicable.
- Relevant JVM flags or launcher options.
- Framework integration version.
- Range of JDKs and engines supported by the extension according to vendor documentation.

If an extension has transitive dependencies, include them in the lockfile/SBOM. Avoid uncontrolled version ranges for components that affect checkpointing. Builds and checkpoints should pin specific versions so a given release remains traceable.

## 10. Callback Ordering and Extension Limitations

Not every vendor extension shares the same execution order or semantics as a CRaC Resource. An extension may:

- Register its own Resource into the context.
- Provide additional callbacks at the launcher level.
- Run checks before the runtime invokes Resources.
- Manage separate native resources.
- Perform a post-restore verification step.

Before combining an extension with application-registered Resources, know:

1. Whether the extension registers its own Resource.
2. Which Resources own the same client or pool.
3. Whether close and reopen ordering is guaranteed.
4. Whether callbacks can run multiple times or fail midway.
5. If a checkpoint is aborted after resources were closed, how the original process is recovered.
6. Whether the extension supports the exact framework and driver versions in use.

Avoid registering two Resources that both close the same connection pool. Avoid calling extension callbacks directly as if they were standard APIs. Use the documented public entry points.

If dependency ordering is mandatory, group related steps under a coordinator with clear ownership or use lifecycle orchestration supported by the framework/vendor. Do not rely on accidental ordering between independent callbacks.

## 11. Building a Producer and Consumer Compatibility Matrix

The producer is the environment creating the checkpoint; the consumer is the environment restoring the checkpoint. The matrix should define tested combinations, not merely list installed versions.

Example matrix structure:

| Producer | Consumer | Status | Notes |
|---|---|---|---|
| JDK vendor A + engine X vN + Linux profile P | Same pinned combination | Tested | Standard combination for the release |
| Newer JDK vendor A build + engine X vN+1 | Older combination | Unverified | Needs testing per vendor documentation |
| JDK vendor B + engine Y | JDK vendor A + engine X | Not compatible by default | Different runtime/engine, requires official support and separate testing |
| Linux x86_64 | Linux ARM64 | Not compatible by default | Different architecture and machine code state |
| Same JDK but different kernel | Different host kernel | Unverified | Needs cross-checking against engine/kernel requirements |
| Same app version but different native extension | Different extension build | Unverified | Extension hash/version must be controlled |

Statuses should have clear meanings:

- **Supported:** the vendor or platform confirms the combination is supported.
- **Tested:** the combination has run successfully in internal testing.
- **Not tested:** no evidence exists; must not be inferred as compatible.
- **Unsupported:** the vendor or deployment policy does not support that combination.

A single successful restore in a test environment does not automatically create an official support commitment. Conversely, vendor documentation stating a combination is supported does not replace testing the application with its actual resources and extensions.

## 12. Verification Workflow Before Releasing a Checkpoint

A practical workflow can be divided into stages:

### Define the Checkpoint Creation Combination

1. Pin the JDK vendor and full version.
2. Identify the CRaC API/runtime build.
3. Identify the checkpoint engine, version, and option profile.
4. Pin the container base image by digest.
5. Record the OS, kernel, CPU architecture, libc, and native dependencies.
6. List vendor extensions, framework integrations, and artifact hashes.
7. Record relevant JVM flags and launcher configuration.

### Test on the Producer

1. Run the application on the exact target JDK and engine.
2. Confirm Resources and extensions are registered properly.
3. Run pre-checks to detect unsupported resources.
4. Stop requests, consumers, and transactions according to policy.
5. Create the checkpoint using the vendor-supported mechanism.
6. Record actual logs and metadata from the checkpoint run.

### Test on the Consumer

1. Provision the restore environment according to the compatibility profile.
2. Verify the engine, runtime, kernel, CPU, and container digest.
3. Inspect the checkpoint files and manifest.
4. Restore the checkpoint using the exact deployment procedure.
5. Confirm callbacks and vendor extensions complete.
6. Verify databases, brokers, secrets, files, and external dependencies.
7. Open readiness only after mandatory dependencies are ready.

### Test Version Changes

When upgrading the JDK, engine, kernel, base image, or extensions, create a new checkpoint and rerun the test suite. Do not swap a single component in production and reuse an old checkpoint if the new combination is unsupported or unverified.

## 13. Attaching the Compatibility Profile to the Release Manifest

The checkpoint manifest should record components that affect restore. For example:

~~~json
{
  "application": {
    "version": "2.4.1",
    "commit": "full-commit-sha",
    "artifactSha256": "..."
  },
  "checkpoint": {
    "id": "release-checkpoint-001",
    "engine": {
      "name": "recorded-engine",
      "version": "recorded-version",
      "optionsProfile": "recorded-profile"
    }
  },
  "runtime": {
    "jdkVendor": "recorded-vendor",
    "javaVersion": "recorded-full-version",
    "cracRuntime": "recorded-version"
  },
  "platform": {
    "os": "recorded-os",
    "kernel": "recorded-kernel",
    "architecture": "x86_64",
    "libc": "recorded-libc",
    "containerDigest": "sha256:..."
  },
  "extensions": [
    {
      "name": "recorded-extension",
      "version": "recorded-version",
      "sha256": "..."
    }
  ],
  "compatibility": {
    "profileId": "linux-x86_64-crac-profile-01",
    "verification": "tested"
  }
}
~~~

This is an example schema, not a standard manifest prescribed by CRaC. Associate this manifest with checksums and signatures of the release bundle. Version, hash, and verification status values must originate from the verification pipeline. Do not place secrets, tokens, or sensitive data in metadata.

Upon restore, the deployment controller or script can read the manifest to compare against the actual runtime/host before invoking the engine. If the profile does not match, abort restore and fall back to a cold start or an artifact verified to be compatible.

## 14. When Should Vendor Extensions Be Used?

A proprietary extension can be helpful when it handles an integration piece the application should not manage itself, such as:

- CRaC support for a specific connection pool or SDK.
- Automatic Resource registration and lifecycle ordering.
- Handling a specialized native handle.
- Providing diagnostics for non-checkpointable resources.
- Integrating with the JDK distribution's engine or launcher.

Before adding an extension, confirm:

- Whether the extension is maintained and supported by the vendor.
- Which exact JDK builds and engine versions it supports.
- Whether it is compatible with the application's framework, driver, and dependency versions.
- Whether it registers Resources automatically or requires manual registration.
- Whether it changes command lines, JVM flags, native libraries, or the base image.
- How to upgrade and roll back the extension.
- How to handle cases where the extension cannot restore a resource.

If an extension supports only a narrow runtime range, reflect that constraint in the compatibility profile. Do not add an extension merely because its product name contains CRaC; identify which resources it actually supports and what its limitations are.

## 15. Upgrade and Rollback Strategy

Upgrading one component in the stack can affect restore capability. Manage versions as a unit:

~~~text
Release N
  Application build A
  JDK build J1
  CRaC integration C1
  Engine E1
  Extension X1
  Container digest I1
  Checkpoint artifact P1

Release N+1
  Application build B
  JDK build J2
  CRaC integration C2
  Engine E2
  Extension X2
  Container digest I2
  Checkpoint artifact P2
~~~

If only the JDK or engine is upgraded while still using checkpoint P1, explicit vendor compatibility confirmation and specific testing are required. Otherwise, build P2 on the new combination.

Rollback must also account for the checkpoint. Rolling back the application image while using a checkpoint created from a newer JDK/engine still will not work with the older runtime. Keep the complete release bundle of the previous version, including the application artifact, container digest, checkpoint artifact, manifest, extensions, and compatibility profile.

A tested cold-start path is an essential fallback. If a checkpoint is incompatible or restore fails, the system can boot the application from the application artifact on a supported runtime instead of forcing an unsuitable checkpoint.

## 16. Common Mistakes

**Assuming the same CRaC API means checkpoints are interchangeable.**

Source-level API compatibility does not prove checkpoint format, JVM state, or native engine compatibility. Verify producer/consumer profiles.

**Not recording the checkpoint engine version.**

When restore fails, there is insufficient information to cross-reference the native implementation. Record the engine name, version, options, and source.

**Checking only the JDK major version.**

Vendor, build, CRaC patches, native integration, and JVM flags can differ. Record the full runtime version.

**Upgrading the engine independently of the JDK.**

A JDK distribution may support only a specific engine range. Use a validated and tested combination.

**Using a vendor extension without pinning its version.**

Extensions can change hooks, resource support, or dependencies. Record the version and artifact hash.

**Registering a Resource that overlaps with an extension.**

Two components closing the same pool or client can cause errors. Clearly define owners and lifecycle responsibilities.

**Assuming the engine restores databases or brokers.**

External services continue their own lifecycles. Reconnect, verify sessions, and handle transactions/messages according to policy.

**Relying on OS/container tag names to conclude compatibility.**

Tags can change; kernel, digest, CPU, libc, and native libraries also matter. Pin and record concrete metadata.

**Testing only checkpoint creation without testing restore.**

A successful checkpoint does not prove the artifact can be restored on the target host. Producer/consumer integration tests are required.

## 17. Conclusion

Checkpoint compatibility depends on the CRaC API, JDK runtime, checkpoint engine, vendor extensions, and operating system environment alike. CRaC Resources help the application coordinate resource lifecycles, while the engine performs native checkpoint/restore. These two parts complement each other but do not replace each other.

Pin and thoroughly record the JDK vendor/build, CRaC runtime, engine/version/options, extensions, kernel, CPU, native libraries, and container digest. Build a compatibility profile for producers and consumers, use extensions according to vendor documentation, test restore in the target environment, and maintain a cold-start path to handle incompatible checkpoints.
