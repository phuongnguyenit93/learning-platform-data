# Building a Verified Environment Matrix Instead of Assuming Images Run Everywhere

A CRaC (Coordinated Restore at Checkpoint) checkpoint image stores the state of a Java process at a point in time. The image can contain the heap, thread state, native memory, and runtime structures that the checkpoint engine needs to restore the process. Because this state is tied to the JVM, operating system, and process resources, a checkpoint image does not have the same portability as an application JAR.

A JAR can usually run on multiple compatible JDKs. A container image can run on multiple hosts that meet the container runtime's requirements. However, a checkpoint image should only be restored on environments that the vendor/runtime supports and the deployment team has verified.

You cannot conclude that two machines are compatible merely because both run Linux, share the same CPU architecture, or use the same major Java version. Compatibility depends on a specific combination of JDK build, CRaC integration, checkpoint engine, kernel, CPU features, native libraries, filesystem, container runtime, JVM configuration, and external state.

The reliable way to manage this is to build a **verified environment matrix**. The matrix clearly records which environment created the image, which environments have successfully restored it, what the test evidence is, and which scope has not yet been tested. Every conclusion must be tied to a specific combination of versions and configurations.

## 1. Why Can You Not Assume a Checkpoint Runs Everywhere?

A checkpoint image does not contain only bytecode. It stores the state of a running process. Upon restore, the runtime must recover memory regions, threads, and system state on which the process depends.

The following components can alter restore capability:

- **JDK vendor and build:** each build may contain different JVM implementations, CRaC APIs, and internal changes.
- **Checkpoint engine:** the engine determines how process state, memory pages, file descriptors, and supported resources are captured and restored.
- **Operating system and kernel:** system calls, VMAs, namespaces, cgroups, signals, and process structures depend on the operating system.
- **CPU architecture and features:** register state, instruction sets, native code, and CPU extensions may differ.
- **Native libraries:** JNI, C/C++ libraries, allocators, TLS libraries, or drivers may depend on ABI and version.
- **Container runtime:** how namespaces, mounts, capabilities, and cgroups are created can affect checkpoint/restore.
- **Filesystem and volumes:** backing files, mount points, permissions, overlay filesystems, and shared volumes can change.
- **JVM flags and runtime configuration:** heap, GC, memory layout, system properties, and environment variables can affect saved state.
- **External dependencies:** databases, DNS, secrets, certificates, service endpoints, and leases can change while the image is stored.

An image may be created successfully yet fail to restore on another host. Restore may also succeed while the afterRestore callback cannot reopen the database pool or the current configuration is no longer compatible. Therefore, verifying that checkpoint files can be read or seeing the process get created is not sufficient to mark an environment as compatible.

## 2. Compatibility Is a Relationship Between Image Source and Restore Target

A common matrix design mistake is recording only a list of "supported" environments. However, a checkpoint is created in a source environment and restored in a target environment. Compatibility is a relationship between the two sides.

For example:

- Image A is created on Linux distribution X, kernel build K1, JDK build J1, and engine E1.
- Host B has the same CPU architecture but kernel K2, JDK build J1, and engine E1.
- Host C has kernel K1 but JDK build J2.
- Host D uses the same container image digest but different CPU features.

You cannot conclude from a single dimension alone that B, C, or D can restore A. You must test the actual combination in the source → target direction and cross-check against the vendor's official support matrix.

~~~mermaid
flowchart LR
    S["Source environment<br/>Create checkpoint"] --> I["Checkpoint artifact<br/>+ metadata"]
    I --> T1["Target A<br/>Restore test"]
    I --> T2["Target B<br/>Restore test"]
    I --> T3["Target C<br/>Restore test"]
    T1 --> R1["Verified / Failed"]
    T2 --> R2["Verified / Failed"]
    T3 --> R3["Verified / Failed"]
~~~

A result for A → B does not automatically prove B → A. Some differences can have directional impact: an image created from a newer build might not restore on an older runtime, whereas the reverse direction might be supported by the vendor. Explicitly record the direction tested.

### 2.1 Distinguishing Three Questions

When evaluating a target, answer separately:

1. **Vendor-supported:** is this combination within the support scope published by the vendor/runtime?
2. **Technically-restored:** did the checkpoint engine successfully restore the process in the test?
3. **Application-ready:** did the application recover resources, reconcile dependencies, and pass business health checks?

A successful restore result in a single test run does not automatically expand the official support scope. Conversely, a combination listed in the vendor's support matrix still requires testing the actual application because the application's native libraries and external dependencies may impose their own requirements.

## 3. Dimensions Needed in an Environment Matrix

The matrix does not need to record every detail of the machine, but it must capture enough factors that can affect checkpoint and restore. Group them into runtime, host, container, application, and external state.

### 3.1 JDK and CRaC Runtime

Specify:

- JDK vendor and distribution name.
- Full Java version, including update/build number.
- JDK architecture.
- CRaC API/runtime version or build identifier.
- JVM implementation and GC if required by the vendor.
- JVM flags that affect memory layout or checkpointing.
- Relevant system properties and environment variables.
- Loaded native modules or agents.

Do not record only "Java 21". Two JDKs with the same major version can differ in vendor, patch level, CRaC integration, or engine packaging.

The following command is useful for recording basic runtime information:

~~~bash
java -version
~~~

You can also record the process's actual system properties and command line. Do not include secret values in environment reports.

### 3.2 Checkpoint Engine

Specify:

- Engine name.
- Version and build.
- Engine configuration.
- Image creation method and restore method.
- Options related to memory loading or compression.
- Required permissions and capabilities.
- Known limitations per vendor documentation.

CRIU and Warp are examples of engines with different implementations. Do not extrapolate results from one engine to another. A simulation engine can be useful for running callbacks and checking lifecycle behavior, but it does not prove a real process image can restore on a production kernel.

### 3.3 Operating System and Kernel

Record:

- OS distribution and release.
- Kernel release and build.
- CPU architecture.
- Relevant CPU model or CPU feature flags.
- Important kernel configurations or sysctls.
- Namespace and cgroup mode.
- Process, memory map, and file descriptor limits.
- SELinux/AppArmor or equivalent security policy.
- Capabilities or permissions required by the engine.

Example commands on Linux:

~~~bash
uname -a
cat /etc/os-release
lscpu
~~~

These commands provide baseline information. Not every field in the output needs to be compared; select the fields identified by the vendor or engine as compatibility conditions.

### 3.4 Container and Orchestration

If running in a container, specify:

- Container image digest, not just tag.
- Container runtime and version.
- OCI runtime if applicable.
- Base image and userland libraries.
- Mount namespace, volumes, and mount options.
- UID/GID, user, and group.
- Linux capabilities and seccomp profile.
- cgroup version and resource limits.
- Kubernetes version, node pool, and runtime class if deployed on Kubernetes.

An image with the same digest running on a host with a different kernel or CPU still needs verification. A container image does not abstract away the host's kernel and CPU entirely.

### 3.5 Filesystem and External Resources

Record files and mounts that the checkpoint or application needs after restore:

- Filesystem type.
- Mount points and mount options.
- Backing files for memory mappings.
- Access permissions and ownership.
- Whether volumes are mounted on the target.
- Network filesystem or volume driver.
- DNS, routes, and endpoints.
- Database schema compatibility.
- Secret/certificate source and revision.
- Message broker, partition assignment, or lease service.

Do not store raw secrets in the matrix. Record only secret names, version identifiers, or non-sensitive fingerprints if cross-checking is needed.

### 3.6 Application and Dependencies

Each checkpoint should be linked to:

- Source commit or release ID.
- Application JAR hash.
- Dependency lockfile or SBOM.
- Native library versions.
- Agents and instrumentation.
- JVM arguments.
- Configuration revision.
- Schema compatibility range.
- Checkpoint ID and checksum.
- Image creation timestamp.

If the application uses JNI or native libraries, explicitly record versions and ABI. Changing a native library can alter restore compatibility even when the JAR is unchanged.

## 4. Designing the Matrix Around Meaningful Combinations

Do not build a massive table listing every possible OS × JDK × engine × CPU × filesystem value and assume every combination must be tested. The number of combinations explodes quickly.

Instead, start from the actual environments the organization plans to use, then select dimensions likely to have impact and representative targets.

Example compact matrix:

| Source checkpoint | Target restore | Vendor support | Restore test | App readiness | Conclusion |
|---|---|---|---|---|---|
| Linux x86_64, JDK build A, engine E1 | Same host class and build | Yes | Pass | Pass | Verified |
| Linux x86_64, JDK build A, engine E1 | Newer kernel, same JDK/engine | Needs confirmation | Not run | Not run | Untested |
| Linux x86_64, JDK build A, engine E1 | Different JDK vendor | Unknown | Fail | N/A | Not approved |
| Linux x86_64, engine E1 | Linux ARM64, engine E1 | Unsupported per current matrix | Not run | N/A | Unsupported |
| Container digest X, checkpoint C1 | Same digest, host node pool B | Conditional | Pass | Dependency test pending | Partially verified |

The rows above only illustrate table structure, not support conclusions for any specific vendor.

### 4.1 Naming Environment Profiles

Each test environment should have a stable ID, for example:

- linux-amd64-jdkA-engineE1-kernelK1.
- linux-amd64-jdkA-engineE1-kernelK2.
- linux-arm64-jdkA-engineE1-kernelK3.
- linux-amd64-jdkB-engineE2-kernelK4.

An ID does not replace detailed metadata. It helps make the matrix readable and links logs to saved configurations.

### 4.2 Directed Source → Target Matrix

Each test can be represented by a pair:

| Checkpoint source | Restore target | Result |
|---|---|---|
| profile-A | profile-A | Pass |
| profile-A | profile-B | Pass/Fail |
| profile-A | profile-C | Pass/Fail |
| profile-B | profile-A | Pass/Fail |
| profile-B | profile-B | Pass |

If there is only one source image in the pipeline, at minimum restore must be tested on all planned target classes. If images are created on multiple source classes, specify which source class was tested against which target.

Do not collapse two directions into a single cell "A and B are compatible" if only A → B was tested.

## 5. Classifying Verification Results

Use statuses with clear meanings. Do not leave blank cells that could be misinterpreted as compatible.

| Status | Meaning | Permitted to deploy? |
|---|---|---|
| VERIFIED | Tested the exact source/target combination and the application passed required checks | Yes, within the tested scope |
| VENDOR_SUPPORTED | Vendor declares support, but internal application testing is not yet complete | Only per organization policy; do not label as verified |
| PARTIALLY_VERIFIED | Process restore succeeded, but app/dependency steps or workload remain unconfirmed | Do not expand beyond the checked scope |
| UNTESTED | No test evidence exists | Do not assume compatible |
| UNSUPPORTED | Vendor or platform does not support that combination | Do not deploy checkpoint |
| FAILED | Tested and failed | Do not deploy until the cause is resolved |
| BLOCKED | Unable to run the test due to missing permissions, infrastructure, or dependencies | Do not treat as pass |

You can separate vendor support and internal verification into two columns instead of merging them into a single status. For example, vendor-supported but not yet verified is useful information and should be preserved separately.

### 5.1 Evidence Must Accompany Status

A VERIFIED row needs:

- Checkpoint ID.
- Source profile ID.
- Target profile ID.
- JAR hash and container digest.
- JDK/engine/kernel/architecture.
- Test date and time.
- Pipeline run or test report ID.
- Process restore result.
- Callback result.
- External reconciliation result.
- Functional smoke test result.
- Confirming person or system.

If evidence is missing, the status should be UNTESTED or PARTIALLY_VERIFIED.

## 6. Testing Workflow for an Environment Pair

A compatibility test must confirm both process recovery capability and the application's ability to continue operating.

### 6.1 Preparing the Source Environment

1. Select the exact JAR and container image digest.
2. Record JDK, CRaC runtime, engine, kernel, CPU, and container configuration.
3. Launch the application in the source profile.
4. Wait for startup and warm-up to complete.
5. Verify readiness and dependencies.
6. Request the checkpoint.
7. Collect checkpoint files, checksums, and metadata.
8. Record logs of beforeCheckpoint and the engine result.

The checkpoint must be created by the real runtime/engine that will be used in deployment. Running callbacks with a simulation engine does not replace this step.

### 6.2 Preparing the Target Environment

1. Provision a target host or node belonging to the profile to be tested.
2. Install or pull the exact container image digest.
3. Provide mounts, volumes, permissions, and runtime configuration.
4. Check that the target satisfies vendor/engine requirements.
5. Provision suitable test external dependencies.
6. Transfer the checkpoint artifact to the target in a byte-preserving manner.

Do not modify checkpoint files or combine partial images from multiple runs. If the engine produces a set of files, preserve the exact structure and relationships between files.

### 6.3 Performing the Restore

Restore the process according to the instructions for the exact runtime/engine. Record:

- Whether the engine can open and read the checkpoint artifact.
- Whether the process is created successfully.
- Whether the JVM can resume.
- Whether afterRestore callbacks execute completely.
- Whether any suppressed exceptions or native errors occur.
- How long the restore takes.
- Which resources are reconnected or recreated.

A successful exit code from the restore command is not enough to confirm application readiness.

### 6.4 Testing the Application After Restore

Run appropriate functional checks:

- Readiness and liveness.
- Database queries or transaction tests.
- Network clients and TLS handshakes.
- File reads/writes and memory mappings if applicable.
- Message consumer reconnect and offset correctness.
- Secret/certificate refresh.
- Lease/lock reacquisition.
- Cache revisions and external state reconciliation.
- A representative business request.
- Checking for no duplicated side effects or unintended migrations.

If process restore succeeds but the database pool fails to connect, the result is PARTIALLY_VERIFIED or FAILED depending on criteria, not VERIFIED.

### 6.5 Repetition and Load Testing

A single successful restore proves only a single run. For critical environments, test multiple iterations:

- Create a new checkpoint and restore repeatedly.
- Restore multiple instances concurrently if production does so.
- Restore after the image has been stored for a longer period.
- Change external dependencies during the checkpoint/restore interval.
- Run representative workloads after restore.
- Check for resource leaks and readiness latency.

## 7. Avoiding Test Combination Explosion

If there are 4 JDK builds, 3 kernels, 2 architectures, 2 engines, 3 filesystem classes, and 2 container runtimes, the full number of combinations is huge. It is not necessary to test every combination if many configurations are never deployed or are unsupported by the vendor.

Scope can be narrowed with these steps:

1. Exclude combinations explicitly unsupported by the vendor.
2. Select profiles currently in use or planned for deployment.
3. Prioritize changes that can affect process state: JDK, engine, kernel, architecture.
4. Create dedicated tests for native libraries, file mappings, filesystems, and container policies used by the application.
5. Use pairwise or representative combinations for low-interaction dimensions, while keeping end-to-end tests for real production combinations.
6. Add tests when a component changes or an incident occurs.

Pairwise testing helps reduce the number of combinations, but it does not prove every three-way or four-way interaction. For instance, a native library might fail only when a specific architecture is combined with a specific JDK build. For high-risk dimensions, test the exact real combination.

### 7.1 Selecting Tests by Risk

| Change | Testing priority |
|---|---|
| JDK vendor/build changed | Very high |
| Checkpoint engine/version changed | Very high |
| CPU architecture changed | Very high |
| Kernel or OS family changed | High |
| Native library or JNI changed | High |
| Container runtime/security policy changed | High |
| Filesystem/mount changed | High if file mapping is used or engine depends on it |
| Only application config changed | Check reconciliation and compatibility |
| Only external data changed | Check external state and readiness |

Priority levels are suggestions for planning, not a substitute for the vendor support matrix.

## 8. Example Data Structure for the Matrix

The matrix can be stored in YAML for review via Git. The example below illustrates one source profile and two target profiles:

~~~yaml
matrixVersion: 1

application:
  name: orders-service
  version: 2.8.1
  sourceCommit: abcdef123
  jarSha256: sha256:example-jar-digest

checkpoint:
  id: orders-2.8.1-amd64-001
  artifactSha256: sha256:example-checkpoint-digest
  createdAt: "2026-11-13T06:00:00Z"
  sourceProfile: linux-amd64-jdkA-engineE1

profiles:
  linux-amd64-jdkA-engineE1:
    os: linux
    distribution: example-linux
    kernel: "6.x.y"
    architecture: amd64
    cpuFeatures:
      - sse4_2
      - avx2
    jdkVendor: example-vendor
    jdkBuild: example-crac-build
    cracRuntime: example-crac-version
    engine:
      name: example-engine
      version: example-engine-version
    containerRuntime: example-runtime
    containerDigest: sha256:example-container-digest
    filesystem: ext4

  linux-amd64-jdkA-engineE1-target:
    os: linux
    distribution: example-linux
    kernel: "6.x.z"
    architecture: amd64
    cpuFeatures:
      - sse4_2
      - avx2
    jdkVendor: example-vendor
    jdkBuild: example-crac-build
    cracRuntime: example-crac-version
    engine:
      name: example-engine
      version: example-engine-version
    containerRuntime: example-runtime
    containerDigest: sha256:example-container-digest
    filesystem: ext4

tests:
  - source: linux-amd64-jdkA-engineE1
    target: linux-amd64-jdkA-engineE1
    vendorSupport: supported
    restoreResult: passed
    applicationResult: passed
    status: VERIFIED
    evidence:
      pipelineRun: "run-12345"
      report: "artifacts/restore-report.json"
      testedAt: "2026-11-13T07:00:00Z"

  - source: linux-amd64-jdkA-engineE1
    target: linux-amd64-jdkA-engineE1-target
    vendorSupport: pending
    restoreResult: not_run
    applicationResult: not_run
    status: UNTESTED
~~~

The example values are not real CRaC configurations. This schema is defined by the deployment team itself. More detailed fields can be stored, such as kernel config, cgroup mode, seccomp profile, mount options, CPU model, native library hashes, and JVM flags.

### 8.1 Keeping Test Evidence Separate

It is not necessary to embed all logs into YAML. The manifest can point to:

- Test reports.
- Engine logs.
- JVM logs.
- Runtime metadata.
- Checkpoint checksums.
- Restore timings.
- Functional test results.

Evidence should be stored immutably by pipeline run or release ID. If a report is overwritten, the matrix loses traceability.

## 9. Automatically Collecting Environment Metadata

To avoid manual version entry errors, the pipeline should collect metadata directly from the host/process that created the checkpoint and the target performing the restore.

Example Linux commands:

~~~bash
java -version
uname -a
cat /etc/os-release
lscpu
cat /proc/self/status
~~~

If running in a container, supplement with metadata from the container runtime and orchestration platform. Some information may require special read permissions; if it cannot be collected, record UNKNOWN instead of guessing.

### 9.1 Do Not Store Secrets in the Manifest

The manifest may be retained for a long time and shared widely across pipelines. Record only versions or references:

- Secret name and version ID.
- Certificate fingerprint.
- Configuration revision.
- Workload identity provider.
- Environment name.

Do not record passwords, tokens, private keys, or secret contents.

### 9.2 Normalizing Metadata

Use a consistent format:

- Full version rather than major version only.
- Architecture using standard names such as amd64 or arm64.
- Full kernel release.
- Image digest instead of mutable tags.
- UTC timestamps.
- Unique checkpoint ID.
- Source and target profile IDs.
- Fixed enum values for test results.

Normalization enables automated profile comparison and detection of unexpected changes.

## 10. Integrating the Compatibility Matrix With the Release Pipeline

A matrix is only valuable if the pipeline uses it to make release decisions. If it is only stored in a spreadsheet without a release gate, deployers can still select the wrong image.

A pipeline can include these stages:

~~~mermaid
flowchart TD
    A["Build JAR and container image"] --> B["Collect source environment metadata"]
    B --> C["Start and warm up application"]
    C --> D["Create checkpoint"]
    D --> E["Store immutable checkpoint + manifest"]
    E --> F["Select target profiles"]
    F --> G["Run restore matrix"]
    G --> H{"Required profiles verified?"}
    H -->|Yes| I["Publish checkpoint release"]
    H -->|No| J["Block release or use fresh startup"]
    I --> K["Deploy by approved profile"]
    J --> L["Record failure and investigate"]
~~~

### 10.1 Defining Required Profiles

Not every environment in the inventory needs to support every release. Define required profiles by deployment target:

- Production node pool A.
- Production node pool B.
- Disaster recovery region.
- Staging.
- Development or CI runner.

A release is marked eligible only if mandatory profiles have been verified or have a policy-approved exception.

### 10.2 Checking Drift Before Deploy

Even if a profile was once VERIFIED, hosts may have received kernel upgrades, CPU generation changes, or container runtime updates.

Before deploying:

1. Collect current target metadata.
2. Compare against the verified profile.
3. Identify changed fields.
4. Check whether changes fall within vendor support and test evidence scope.
5. If significant changes exist, require a new restore test.
6. If no evidence exists, select fresh startup or an already confirmed target.

Do not automatically treat a new profile as compatible merely because the difference appears minor.

### 10.3 Fresh Startup as an Explicit Fallback

If the target is not in the VERIFIED matrix or no longer meets the profile, the pipeline can:

- Block checkpoint deployment.
- Select a verified node pool.
- Create a new checkpoint on the matching target class.
- Start a fresh JVM from the JAR in the container image.

Fresh startup does not require checkpoint compatibility, though it still requires normal application/runtime compatibility. It must also follow the application's migration, initialization, and readiness policies.

## 11. Application-Level Compatibility Checks

Process restore is only the first layer. A good matrix must include checks for features the application actually uses.

### 11.1 Resource Lifecycle

Confirm:

- beforeCheckpoint completes.
- Resources requiring closure have been released.
- afterRestore successfully reopens files, sockets, and pools.
- Callback errors are reported accurately.
- Callback ordering does not introduce invalid dependencies.
- Multiple checkpoint/restore cycles do not leak resources.

### 11.2 Native Code and Memory

If the application includes native code:

- Verify libraries have the same ABI and version.
- Check native threads and TLS state.
- Check direct buffers and mapped memory.
- Check backing files and mounts.
- Run a representative native operation after restore.
- Check memory usage and segmentation/native crash errors.

### 11.3 External State

Check:

- Database connections and schema compatibility.
- DNS and service discovery.
- Secret/certificate rotation.
- Session and token expiration.
- Leases and fencing tokens.
- Message broker assignments and cursors.
- Feature flag/config revisions.
- Cache invalidation or event replay.

These checks help detect cases where process restore succeeds yet the application retains stale state.

### 11.4 Post-Restore Performance

Measure:

- Time from restore command to process availability.
- Duration of afterRestore callbacks.
- Duration of external reconciliation.
- Time to readiness.
- First-request latency.
- Throughput and error rate after restore.
- Memory RSS/PSS and file descriptor count.
- Checkpoint artifact size.

An image may restore successfully yet miss latency targets or consume excessive memory. Performance results should be recorded separately from functional compatibility results.

## 12. Change Management and Re-Verification

The matrix is not a write-once document kept static forever. Every runtime or platform change can invalidate a previous conclusion.

### 12.1 Changes Requiring Re-Evaluation

| Change | What needs re-verification |
|---|---|
| JDK vendor/build | Checkpoint/restore and application tests |
| CRaC runtime/API | Callback behavior, image format, and restore |
| Checkpoint engine | Full process restore across target profiles |
| Kernel | Process state, VMAs, syscalls, and engine requirements |
| CPU architecture/model/features | Native code and process compatibility |
| Container runtime/OCI runtime | Namespaces, mounts, cgroups, and permissions |
| Native library | ABI, memory, threads, and callbacks |
| Filesystem/volume | File mappings, permissions, and backing data |
| JVM flags | Runtime layout, heap, and restore configuration |
| Application JAR | Functional tests and checkpoint recreation |
| External dependency version | Reconciliation and application readiness |

### 12.2 Do Not Blindly Reuse VERIFIED Status

If the source profile changes JDK build or the target profile changes kernel, the old status may no longer apply.

You can store a testedProfileFingerprint or hash of normalized metadata. When the current fingerprint differs from the tested fingerprint in critical fields, the pipeline marks it NEEDS_RETEST.

Not every change necessarily forces creating a new checkpoint. The decision depends on vendor documentation and actual impact. However, there must be clear rules so a VERIFIED status does not persist indefinitely after the environment has changed.

## 13. Controlling Support Scope

A product may claim support for many host types, but checkpoint compatibility requires a narrower, concrete scope.

For example, instead of claiming:

> Checkpoints run on Linux.

Describe the scope:

- Tested Linux distributions and kernel ranges.
- Supported JDK vendors/builds.
- Checkpoint engine and version.
- CPU architectures/features.
- Container runtime and configuration.
- Filesystem and mount profiles.
- Verified native libraries.
- Target profiles where restore succeeded.

This scope can be updated per release. If a host lies outside the matrix, treat it as UNTESTED until evidence exists.

### 13.1 Distinguishing Vendor Matrix and Application Matrix

A vendor may publish an engine/runtime/platform support matrix. That is the foundation for selecting valid combinations.

The application needs its own matrix because it adds:

- Frameworks.
- JNI/native libraries.
- Database drivers.
- HTTP/TLS stacks.
- Filesystem mappings.
- External dependencies.
- Callbacks and readiness logic.

A vendor-supported combination may still be unsuitable for an application if the application holds native state or resources that are not properly handled.

## 14. Example Test Report

A restore report should describe the concrete source and target:

~~~text
Checkpoint compatibility test

Checkpoint ID: orders-2.8.1-amd64-001
Source profile: linux-amd64-jdkA-engineE1
Target profile: linux-amd64-jdkA-engineE1-nodepoolB

Source:
  JDK build: <exact-build>
  Engine: <name-and-version>
  Kernel: <release>
  Architecture: amd64
  Container digest: sha256:<digest>

Target:
  JDK build: <exact-build>
  Engine: <name-and-version>
  Kernel: <release>
  Architecture: amd64
  Container digest: sha256:<digest>

Results:
  Artifact integrity: PASS
  Process restore: PASS
  afterRestore callbacks: PASS
  Database reconnect: PASS
  Secret validation: PASS
  Service discovery: PASS
  Functional smoke test: PASS
  Readiness: PASS

Restore duration: <measured-duration>
Evidence: <pipeline-run-or-report-id>
Status: VERIFIED
~~~

Values inside angle brackets are placeholders. Reports must be generated from real pipeline data, not by copying an old report and replacing the profile name.

## 15. Handling Target Failures

When a restore fails, do not immediately conclude the entire source image is unusable. Identify the failing layer.

| Layer | Example symptoms | Remediation approach |
|---|---|---|
| Artifact integrity | Mismatched checksum, missing files | Re-download artifact, verify publishing process |
| JDK/CRaC | Runtime rejects image or callbacks/API differ | Compare exact build and vendor support |
| Engine | Unable to reconstruct process state | Check engine version, logs, and permissions |
| Kernel/platform | System call, namespace, or VMA failure | Check kernel, sysctl, capabilities, and host profile |
| CPU | Native instruction or architecture mismatch | Check architecture/features and create separate image |
| Container | Different mounts, seccomp, or cgroups | Compare container runtime and security policy |
| Native library | Linker error, crash, or invalid native handle | Check ABI, library version, and native lifecycle |
| Application | Callbacks or readiness fail | Read the exception tree and external dependency state |

Record failures by source-target pair. One target failure should not invalidate passing results on other targets, but it must transition the failing target to FAILED or BLOCKED.

If a target falls outside vendor support scope, do not continue attempting ad-hoc tweaks in production. Use an isolated test environment or choose fresh startup.

## 16. Managing Images by Architecture and Environment

If a cluster has multiple CPU architectures or multiple environments, multiple checkpoint artifacts may be needed.

~~~text
checkpoint-artifacts/
  orders-service/
    2.8.1/
      linux-amd64/
        checkpoint-001/
        manifest.json
      linux-arm64/
        checkpoint-001/
        manifest.json
    2.8.2/
      linux-amd64/
        checkpoint-001/
        manifest.json
~~~

If staging and production have different credentials, endpoints, or configs, do not share images if the heap already contains environment-specific state.

A checkpoint can be created per application build, but must be separated by:

- Architecture.
- JDK/engine build.
- Runtime profile.
- Environment/config revision.
- External dependency compatibility.

Each combination does not necessarily require a separate artifact if the vendor and tests confirm that a single image can restore across multiple targets. However, that conclusion must be documented via tested source-target pairs.

## 17. Security and Access Control for Evidence

The matrix contains potentially sensitive infrastructure details: kernel builds, CPU models, runtime versions, network profiles, and container digests. Checkpoint artifacts can also contain secrets in the heap.

Apply these principles:

- Do not store raw secrets in profiles or reports.
- Separate access permissions for checkpoint artifacts from container images.
- Encrypt checkpoints at rest and in transit.
- Audit who downloads or restores images.
- Do not include internal hostnames or sensitive IPs in publicly shared reports.
- Retain test reports according to retention policy.
- Revoke artifacts when a release or credential has been revoked.
- Use immutable digests to detect artifact tampering.

The matrix can be split into a shared section for development teams and detailed infrastructure metadata restricted to operations.

## 18. Workflow for Building and Maintaining the Matrix

The following workflow can be applied for each release:

**Step 1 — Select source profile.** Identify the environment that will start the application, warm up, and create the checkpoint. Record the full JDK, engine, kernel, architecture, and container digest.

**Step 2 — Collect metadata.** Automatically record OS, kernel, CPU features, container runtime, filesystem, JVM flags, and native libraries.

**Step 3 — Identify target profiles.** List the node pools, regions, architectures, and runtime classes that actually need to restore.

**Step 4 — Cross-check vendor support.** Exclude unsupported combinations and clearly mark unknowns.

**Step 5 — Create immutable checkpoint artifact.** Store checksums and metadata linked to the JAR, container image digest, and source profile.

**Step 6 — Run restore matrix.** Test each required source-target pair using the real checkpoint on the corresponding environment.

**Step 7 — Verify application.** Confirm callbacks, external reconciliation, functional smoke tests, readiness, and performance.

**Step 8 — Record results and evidence.** Classify as VERIFIED, PARTIALLY_VERIFIED, UNTESTED, UNSUPPORTED, FAILED, or BLOCKED.

**Step 9 — Enforce release gate.** Publish checkpoints only for target profiles meeting policy. If a target is unverified, use fresh startup or block deployment.

**Step 10 — Monitor drift.** When the JDK, engine, kernel, CPU, container runtime, or native libraries change, compare fingerprints and schedule retests.

**Step 11 — Manage retention.** Keep checkpoints, container images, and corresponding reports for the required rollback window; delete old artifacts per policy.

## 19. Criteria for Completing a VERIFIED Environment

An environment pair should be marked VERIFIED only when all mandatory conditions have evidence:

- Vendor support is not violated.
- Checkpoint artifact integrity is intact.
- Source and target profiles are fully recorded.
- Process restore succeeds on the target.
- Resource callbacks complete.
- External dependencies are reconnected and reconciled.
- Functional smoke tests pass.
- Readiness opens only after validation completes.
- No duplicate side effects or unhandled state drift are detected.
- Restore duration and resource usage remain within operational limits.
- Test report is stored with checkpoint ID and pipeline run.

If process restore succeeds while a business check has not yet run, keep the status PARTIALLY_VERIFIED. If no test has been run on the target, keep UNTESTED. Accurate status tells the deployment team the actual risk level instead of creating the misconception that the image "will definitely run".

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and environment-dependency limitations.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): preparing the runtime and running CRaC applications.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): engines and differences across builds.
- [CRaC — Debugging](https://crac.org/reference/debugging/): investigating checkpoint/restore failures.
- [CRIU Documentation](https://criu.org/): Linux process checkpoint/restore requirements and limitations.
- [Open Container Initiative — Image Format Specification](https://github.com/opencontainers/image-spec): container image metadata and format.
- [Kubernetes — Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/): runtimes and container integration on nodes.
- [Linux man-pages — proc](https://man7.org/linux/man-pages/man5/proc.5.html): process information and procfs interfaces.
- [Linux man-pages — uname](https://man7.org/linux/man-pages/man2/uname.2.html): querying kernel information.
- [Java API — RuntimeMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/RuntimeMXBean.html): JVM runtime information and input arguments.
