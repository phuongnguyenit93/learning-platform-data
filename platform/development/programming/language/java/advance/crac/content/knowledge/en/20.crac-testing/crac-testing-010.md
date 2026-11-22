# Testing the JDK, Kernel, CPU, and Container Matrix in CI

A CRaC (Coordinated Restore at Checkpoint) checkpoint image saves the state of a running Java process. Restorability depends on the runtime that created the image, the checkpoint engine, operating system, kernel, CPU, native libraries, and how the container is launched. Therefore, testing on a single CI machine is not sufficient to conclude that the image can restore on every production node.

A CRaC pipeline needs to verify meaningful environment combinations, record the exact checkpoint source configuration and restore target configuration, and use those results as a release condition. The matrix must reflect the real environments where workloads will run: which JDK build, which kernel, which CPU architecture/features, which container image/runtime, and which engine.

This article presents how to build a scalable CI matrix, distinguish what containers control from what depends on the host, organize tests by source/target profiles, collect evidence, and set release gates based on real restore results.

## 1. Why Is Matrix Testing Necessary?

A successful CRaC test on a development machine only proves that one specific combination worked. It does not prove that other combinations are compatible as well.

For example, the same application and container image may run on:

- CRaC JDK build A and CRaC JDK build B.
- Kernel 6.x on node pool A and kernel 6.y on node pool B.
- amd64 CPUs with AVX2 and amd64 CPUs without AVX2.
- amd64 and arm64 CPUs.
- Different container runtime versions.
- ext4, XFS, or overlay filesystems.
- CRIU or another checkpoint engine provided by a vendor.

These differences can affect how the JVM saves state, how the engine restores the process, native code, memory mappings, file descriptors, namespaces, and permissions. An image may be created successfully yet fail to restore on the target. The process may also restore successfully while the afterRestore callback fails to reconnect to the database or the application fails to reach readiness.

Matrix testing helps answer three separate questions:

1. **Can the build/runtime create a checkpoint?** Do the source JDK and engine support the workload and source host?
2. **Can the checkpoint restore on the target?** Can the engine restore the process under the exact JDK, kernel, CPU, and container combination?
3. **Does the application work properly after restore?** Do resource callbacks, external reconciliation, and functional smoke tests succeed?

A test that checks only callbacks does not fully answer these three questions. Fast tests in pull requests must be combined with restore integration tests on real runners.

## 2. The Matrix Must Describe Source and Target

A checkpoint is created in a source environment and later restored in a target environment. Compatibility is a **source → target** relationship, not just a property of a single host.

For example:

| Source profile | Target profile | What to verify |
|---|---|---|
| JDK A, kernel K1, CPU amd64, engine E1 | Same profile | Baseline restore |
| JDK A, kernel K1 | JDK A, kernel K2 | Different kernel |
| JDK A, CPU amd64 | JDK A, CPU arm64 | Different architecture; usually requires separate support verification |
| JDK A, engine E1 | JDK B, engine E1 | Different JDK build/vendor |
| Container digest X on node pool A | Same digest X on node pool B | Different host kernel/CPU/runtime |
| Container digest X | Container digest Y | Different userland, JDK, or native libraries |

A passing result for A → B does not automatically prove B → A. Some vendors only support one direction or require the source and target to use the exact same build. Record each pair in the direction tested and cross-check against the vendor's support matrix.

~~~mermaid
flowchart LR
    S["Source profile<br/>JDK / kernel / CPU / container"] --> C["Create checkpoint<br/>artifact + manifest"]
    C --> T1["Target profile A"]
    C --> T2["Target profile B"]
    C --> T3["Target profile C"]
    T1 --> R1["Restore + app tests"]
    T2 --> R2["Restore + app tests"]
    T3 --> R3["Restore + app tests"]
    R1 --> E["Evidence and status"]
    R2 --> E
    R3 --> E
~~~

If production only creates checkpoints on one node type yet restores across multiple node pools, test that source against all required target classes. If each architecture or runtime class builds its own image, test each source image against the targets permitted to use it.

### 2.1 Do Not Conflate Vendor Support with Tested Status

Keep three statuses distinct:

- Vendor declares support for that combination.
- Checkpoint engine restored successfully in CI.
- Application passed post-restore checks.

A combination may appear in vendor documentation without having been tested with the application's native libraries. Conversely, a single successful test run does not expand the vendor's official support scope.

The matrix should have separate columns for vendor support, process restore, application readiness, and evidence.

## 3. Four Primary Dimensions of the Matrix

### 3.1 JDK Vendor, Version, and Build

Do not record only the major version such as Java 21. Store the full details:

- Vendor and distribution.
- Full Java version.
- Update/build identifier.
- CRaC runtime/API build.
- JDK architecture.
- JVM implementation and GC if required.
- JVM flags related to heap, GC, memory layout, or checkpoint.
- Loaded agents and native modules.

Two JDKs with the same major version can have different CRaC integrations, patches, native libraries, or implementations. Therefore, the test matrix needs to use the exact JDK build that will run in production.

In CI, the JDK may be pre-installed on the runner or provisioned from an internal artifact repository. With CRaC, do not assume a generic JDK setup action provides a real checkpoint engine. Verify that the specific runtime has CRaC support according to vendor documentation.

Save metadata using:

~~~bash
java -version
~~~

You can additionally collect input arguments and non-sensitive system properties from RuntimeMXBean. Do not write environment variables containing secrets into reports.

### 3.2 Kernel and OS

Containers share the kernel with the host under the standard container model. Using the same container image on two nodes does not make the two nodes' kernels identical.

Fields to record:

- OS distribution and release.
- Kernel release/build.
- Critical kernel configuration or sysctl values.
- cgroup version.
- Namespace mode.
- VMA and process limits.
- File descriptor limits.
- Capabilities and security policy.
- SELinux/AppArmor or seccomp profile.
- Privileges/permissions required by the checkpoint engine.

Example of collecting metadata on Linux:

~~~bash
uname -a
cat /etc/os-release
cat /proc/sys/kernel/osrelease
cat /proc/sys/vm/max_map_count
ulimit -n
~~~

The exact values to compare depend on the engine and workload. Do not compile an arbitrary sysctl list and treat every item as a compatibility requirement. Take requirements from the vendor, engine, and observed failures.

Kernel tests need to run on a host or VM with the actual corresponding kernel. Running a container with a different base image does not change the host kernel.

### 3.3 CPU Architecture and Features

Record:

- Architecture such as amd64/x86_64 or arm64/aarch64.
- CPU model or CPU family when relevant.
- Instruction set extensions and feature flags.
- Virtualization or CPU feature masking if using VMs.
- Native library ABI.
- Node pool runtime CPU constraints.

On Linux, you can collect:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Do not record only the architecture. Two amd64 hosts may expose different sets of CPU features. Native libraries or JIT-generated code may depend on specific features.

If production uses node pools with different CPU generations, test across representative profiles. If the checkpoint image depends on CPU features or the vendor mandates equivalent features on the target, CI needs to enforce that condition before restore.

QEMU or emulation can be useful for certain build and application logic tests, but an emulated test run should not be treated as sufficient proof for process checkpoint/restore on physical CPUs or target VMs. Critical restore tests need to run on the actual supported architecture and CPU profile.

### 3.4 Container Image and Container Runtime

Two layers must be distinguished.

**Container image / userland**

- Base image and distribution.
- JDK build.
- Native libraries.
- CA certificates and timezone data.
- Application JAR and dependencies.
- User, entrypoint, and filesystem layout.
- Container image digest.

**Container runtime / host integration**

- Docker/containerd/CRI-O version.
- OCI runtime such as runc or another runtime class.
- Namespace, mount, and cgroup behavior.
- Seccomp profile and capabilities.
- Volume/mount options.
- Host kernel and CPU.
- Kubernetes version, node pool, and RuntimeClass if applicable.

The same container image digest can run on hosts with different kernels or CPUs. Conversely, the same kernel can still fail if userland or native libraries differ.

Use an immutable digest instead of a mutable tag to bind the checkpoint to the container image that produced it.

## 4. Do Not Mechanically Generate a Full Cartesian Product

If there are 3 JDK builds, 4 kernel profiles, 3 CPU profiles, 2 engines, and 3 container profiles, a full Cartesian product can yield hundreds of combinations. Many combinations may be unsupported by the vendor or never used in production.

You do not need to test every theoretical combination. Build the matrix from real target profiles and choose meaningful source-target pairs.

### 4.1 Start from Deployment Environments

List node pools and runtime classes currently used or planned:

- Production amd64 node pool.
- Production arm64 node pool if applicable.
- Disaster recovery node pool.
- Staging.
- CI integration runner.
- Node pools with distinct kernels or container runtimes.

Each profile needs a stable ID and detailed metadata. Do not create profiles merely to cover a combination that is never deployed.

### 4.2 Use Include/Exclude Instead of All Combinations

Permitted pairs can be defined explicitly:

| Source | Target | Reason |
|---|---|---|
| src-amd64-jdkA-E1 | prod-amd64-poolA | Mandatory deployment |
| src-amd64-jdkA-E1 | prod-amd64-poolB | Different kernel, same architecture |
| src-arm64-jdkA-E1 | prod-arm64-poolA | Separate architecture |
| src-amd64-jdkB-E1 | prod-amd64-poolA | JDK upgrade evaluation |
| src-amd64-jdkA-E1 | staging-amd64 | Pre-release validation |

Unsupported pairs should be excluded from the matrix with an explicit reason. Do not use exclude to hide a failing test; exclude only combinations identified as not applicable or unsupported by policy.

### 4.3 Pairwise and Risk-Based Selection

Pairwise testing can reduce combinations across weakly interacting dimensions. However, it does not guarantee that every multi-dimensional interaction is caught.

For example, a bug that only surfaces when JDK build B combines with kernel K2 and native library N3 will not necessarily appear in individual pairs.

Prioritize exact end-to-end testing for:

- JDK/CRaC build changes.
- Engine changes.
- CPU architecture or feature baseline changes.
- Kernel changes outside the verified range.
- Native library or JNI changes.
- Container runtime/security profile changes.
- Filesystem or mount changes affecting mappings.
- New production target node pools.

Pairwise is suitable for expanding coverage across lower-risk dimensions, not replacing tests for mandatory production profiles.

## 5. Testing Tiers in CI

A good pipeline does not need to run the full restore matrix on every commit. It can be split into tiers with different runtimes and confidence levels.

| Tier | When it runs | Contents | What it proves |
|---|---|---|---|
| Unit tests | Every pull request | Deadlines, state machines, config, and Resource logic | Application logic |
| Callback/simulation tests | Every pull request | beforeCheckpoint/afterRestore with simulation or test harness | Callback behavior |
| JDK build tests | Pull request or nightly | Compile and run smoke tests on supported JDKs | Basic Java/runtime compatibility |
| Real checkpoint/restore | Nightly or release | Create image and restore using the real engine | Process checkpoint/restore on a specific profile |
| Source-target matrix | Nightly/release | Restore the same artifact across target profiles | Compatibility in the source → target direction |
| Application integration | Release gate | DB, TLS, broker, filesystem, readiness, and workload | Application works after restore |
| Performance/capacity | Nightly/release | Restore time, RSS/PSS, first-request latency | Operational targets |

Simulation engines can run callbacks inside the same process and are useful for verifying cleanup/reopen logic. They do not prove that the kernel properly saved and restored process state, native memory, VMAs, or file descriptors.

Real checkpoint tests must use the exact JDK/engine and host class intended for deployment.

### 5.1 Pull Request Tier

On each pull request, run quickly:

- Compile and run unit tests on the primary JDK.
- Unit tests on supported JDK major versions.
- Callback logic tests.
- Resource registration checks.
- Timeout and failure handling checks.
- Manifest/profile schema checks.
- Container image build checks.

If the runner lacks a real checkpoint engine or sufficient privileges, do not label that result a checkpoint restore pass. Explicitly mark it as a simulation or compile test.

### 5.2 Nightly Tier

Nightly can create a checkpoint from a canonical source profile, then restore it on representative target profiles. Also run repeated restore and multi-instance scenarios if production uses the same image to scale.

Nightly is suited to catching runner drift, kernel updates, container runtime updates, or external dependency changes that pull requests do not cover.

### 5.3 Release Tier

Before publishing a checkpoint artifact:

- Run all mandatory source-target pairs for production.
- Run callback and application integration tests.
- Verify external state after restore.
- Check readiness.
- Collect performance metrics.
- Save artifact checksums and environment metadata.
- Release only if mandatory profiles satisfy the release policy.

Do not mark a release VERIFIED merely because the restore command returned exit code 0. The application must pass all defined checks.

## 6. CI Runners Must Represent Real Environments

The JDK can be installed within a job, but the kernel and CPU belong to the runner host. Therefore, a JDK/kernel/CPU/container matrix often requires multiple runner classes.

### 6.1 Hosted Runners vs. Self-Hosted Runners

Hosted runners are convenient for compilation, unit tests, and container builds. However, kernel versions, CPU models, virtualization, and system privileges may be managed by the CI provider and change over time.

Self-hosted runners are appropriate when you need:

- A specific kernel.
- A specific CPU architecture or feature baseline.
- Privileges/capabilities required by the checkpoint engine.
- A specific container runtime.
- A specific filesystem/mount profile.
- A stable, auditable host configuration.

Runner labels should reflect the standardized profile, for example:

~~~text
self-hosted
linux
amd64
kernel-6-8
cpu-avx2
crac-engine-e1
~~~

Label names are examples. Keep labels synchronized with the runner's actual metadata. A kernel-6-8 label loses its meaning if the host kernel is upgraded without updating the label.

### 6.2 Runners Must Be Managed as Part of the Matrix

For self-hosted runners:

- Use a dedicated runner pool for checkpoint tests.
- Do not run untrusted jobs on runners with checkpoint privileges.
- Clean workspaces and checkpoint files after jobs.
- Restrict access to the daemon/container runtime.
- Record runner images and host fingerprints.
- Update labels when kernel, CPU, or runtime changes.
- Maintain a maintenance schedule and drift checks.
- Avoid using a single host concurrently for multiple tests that may conflict on process state.

Checkpoint tests may require special privileges. Do not grant privileged access to every CI job if only one job needs it.

### 6.3 Job Isolation

Use ephemeral VMs or per-job recreated runners when possible. If using long-lived runners, ensure one test does not leave behind:

- Stale processes.
- Mounts or namespaces.
- Checkpoint files.
- Network listeners.
- File descriptors or shared resources.
- Old containers.
- Secrets or credentials.
- Modified temporary sysctls.

A failed restore test must not pollute the environment for the next test.

## 7. Containers Do Not Replace the Host Matrix

A container image can pin the JDK and native libraries, but cannot pin the entire host kernel and CPU.

### 7.1 Same Image, Multiple Hosts

This is a useful test: create a checkpoint from a fixed container image digest and then restore it across different node pools.

This tests the impact of:

- Kernel release.
- CPU features.
- Container runtime.
- cgroup mode.
- Seccomp/capabilities.
- Filesystem and mounts.

Running multiple containers on the same host does not cover kernel/CPU differences across nodes.

### 7.2 Different Container Images

If changing the base image or native libraries, treat this as a separate dimension. A checkpoint created in container image A should not automatically restore in image B merely because the JAR is the same.

Record:

- OCI image digest.
- Base distribution.
- JDK build.
- Native library versions.
- Runtime user and permissions.
- Entrypoint and JVM arguments.
- Mount layout.

If the vendor allows certain userland differences, document that exact scope and test restoring on the corresponding target.

### 7.3 Container Runtime and OCI Runtime

Docker, containerd, CRI-O, or OCI runtimes may have different versions and configurations. Namespaces, mounts, cgroups, and security profiles can affect process checkpointing.

Do not record only a Dockerfile or image digest and treat the container environment as fully described. Host runtime details need to be collected separately.

## 8. Reference CI Workflow Structure

The example below is CI-provider-neutral pseudocode. It illustrates how source jobs and target jobs are separated; runner label names, JDK provisioning, checkpoint/restore commands, and artifact transfers must be replaced with your organization's and vendor's actual tooling.

### 8.1 Defining Source Profiles

A source profile describes the runner that will launch the application and create the checkpoint.

~~~yaml
sourceProfiles:
  - id: linux-amd64-jdkA-engineE1
    runner: crac-linux-amd64-kernel-k1-cpu-avx2
    jdkProfile: jdkA
    containerDigest: sha256:source-image-digest

  - id: linux-arm64-jdkA-engineE1
    runner: crac-linux-arm64-kernel-k2
    jdkProfile: jdkA-arm64
    containerDigest: sha256:arm64-image-digest
~~~

The pipeline reads each profile, selects the corresponding runner, installs or verifies the JDK, starts the container with the exact digest, warms up the application, and creates the checkpoint. Each source job saves its own artifact together with the source fingerprint.

### 8.2 Defining Restore Pairs

Do not generate all combinations automatically if only certain pairs are allowed.

~~~yaml
restorePairs:
  - source: linux-amd64-jdkA-engineE1
    target: prod-amd64-poolA
    required: true

  - source: linux-amd64-jdkA-engineE1
    target: prod-amd64-poolB
    required: true

  - source: linux-arm64-jdkA-engineE1
    target: prod-arm64-poolA
    required: true
~~~

Each target profile points to a real runner pool. The target job downloads the exact artifact by source ID, verifies checksums and metadata, and then runs restore on the target runner.

### 8.3 Example Job Steps

~~~yaml
steps:
  - name: Provision CRaC JDK
    run: ./ci/install-crac-jdk.sh PROFILE_ID

  - name: Record source or target profile
    run: ./ci/collect-environment.sh > environment-profile.json

  - name: Verify runner fingerprint
    run: ./ci/verify-runner-profile.sh environment-profile.json PROFILE_ID

  - name: Start and warm up application
    run: ./ci/start-and-warmup.sh

  - name: Create checkpoint
    run: ./ci/create-checkpoint.sh

  - name: Verify artifact
    run: ./ci/verify-checkpoint-artifact.sh

  - name: Restore checkpoint
    run: ./ci/restore-checkpoint.sh

  - name: Run application smoke tests
    run: ./ci/post-restore-smoke.sh

  - name: Publish evidence
    run: ./ci/write-matrix-result.sh
~~~

The scripts are repository-provided components, not standard CRaC commands. Actual commands depend on the JDK vendor and checkpoint engine. The evidence-publishing step should run even when the job fails to preserve logs, without turning a failed test into a passing result.

### 8.4 Limiting Concurrency

If the checkpoint engine or runner does not support multiple concurrent restores on the same host, limit concurrency per runner or per profile.

Do not share a single checkpoint directory across multiple jobs. Each job needs its own workspace, process ID, output directory, and checkpoint ID.

## 9. Separating Test Commands from the Matrix Policy

Do not hard-code all logic inside the workflow YAML. Extract it into small scripts or tools with a stable interface:

~~~text
ci/
  collect-environment.sh
  install-crac-jdk.sh
  start-and-warmup.sh
  create-checkpoint.sh
  package-checkpoint.sh
  verify-checkpoint-manifest.sh
  restore-checkpoint.sh
  post-restore-smoke.sh
  write-matrix-result.sh
  profiles/
    source-profiles.yml
    restore-pairs.yml
~~~

The workflow orchestrates profiles. Scripts perform actions. Manifests record evidence.

Benefits:

- Can run locally or on dedicated runners.
- Easy to swap engine commands without rewriting the entire matrix.
- Parsers and policy can be tested independently.
- Results are easy to standardize.
- Profiles are reviewed through Git.
- The same scripts can be used in nightly and release pipelines.

Do not let scripts guess targets from incomplete information or infer profiles automatically. If metadata does not match the runner label, fail fast and record BLOCKED.

## 10. Collecting Source and Target Fingerprints

Each creation and restore must collect metadata from the actual host/process rather than reading metadata from a static config file and assuming the host matches.

A profile should include these groups:

~~~json
{
  "profileId": "linux-amd64-jdkA-kernelK1-engineE1",
  "os": {
    "name": "linux",
    "distribution": "example-linux",
    "kernel": "6.x.y"
  },
  "cpu": {
    "architecture": "amd64",
    "model": "example-cpu",
    "features": ["sse4_2", "avx2"]
  },
  "jdk": {
    "vendor": "example-vendor",
    "version": "21.x",
    "build": "example-crac-build"
  },
  "engine": {
    "name": "example-engine",
    "version": "example-engine-version"
  },
  "container": {
    "imageDigest": "sha256:example-image-digest",
    "runtime": "example-runtime",
    "runtimeVersion": "example-runtime-version"
  }
}
~~~

Values only illustrate the structure. Real manifests need data collected from the runner and runtime.

### 10.1 Fingerprints Do Not Replace Full Metadata

A hash can be generated from normalized fields for quick profile comparison. However, the raw metadata must also be retained to investigate when fingerprints differ.

Do not put secrets, tokens, private keys, or sensitive environment contents into fingerprint reports. Collect only allowlisted environment variables.

### 10.2 Policy-Driven Source–Target Comparison

Not every field must match identically. There may be differences supported by the vendor, such as certain kernel patches or host CPUs within the same range. Policy needs to specify clearly:

- Which fields must match identically.
- Which fields may differ within a range.
- Which fields only need to be recorded.
- Which fields require retesting when changed.
- Which fields render the target unsupported.

Do not use a simple string comparison to decide compatibility if the vendor has more complex rules.

## 11. Managing Test Status and Release Gates

Each source-target pair should have an independent result.

| Status | Meaning | Action |
|---|---|---|
| VERIFIED | Both process restore and application checks passed on the exact pair | Permit according to policy |
| PROCESS_RESTORED | Engine restore succeeded, but application checks have not completed | Do not publish if app readiness is required |
| VENDOR_SUPPORTED | Listed in vendor matrix, but no internal test yet | Do not treat as verified |
| UNTESTED | No test executed yet | Do not infer pass |
| UNSUPPORTED | Outside support scope | Do not use checkpoint |
| FAILED | Tested and encountered errors | Block pair until resolved |
| BLOCKED | Could not run due to runner/permissions/dependency | Do not treat as pass |
| FLAKY | Unstable results across runs | Investigate; do not release as VERIFIED |

Release gates should check mandatory target profiles. If an optional target fails, policy may permit a scoped release. If a mandatory production node pool has not been tested, do not publish the checkpoint for that node pool.

### 11.1 Do Not Rely on a Generic Green Build

A workflow can turn green even when a matrix row was skipped or excluded. Check the list of required pairs and verify that each pair has valid evidence.

If a test is skipped because a runner is unavailable, the status must be BLOCKED or UNTESTED, not PASS.

### 11.2 Fresh Startup Fallback

If a target has not been verified or checkpoint restore fails, deployment can use fresh JVM startup from the same container image/JAR according to fallback policy.

Fallback needs to control side effects. Migrations, seeds, and initialization must have an idempotent policy; application readiness opens only after dependencies are ready.

## 12. The Test Matrix Must Verify Application State After Restore

A successful process restore does not guarantee the application can serve traffic. Each target pair needs to run checks appropriate for the application.

### 12.1 Resource Callbacks

Verify:

- beforeCheckpoint stopped accepting work and released resources.
- afterRestore reopened files, sockets, and connection pools.
- Callback errors are propagated outward.
- Dependent resources are recovered in the proper order.
- Multiple checkpoint/restore cycles do not cause leaks.
- No background thread continues using old handles.

### 12.2 Database and External Services

Check:

- New database connections work.
- Schema is within the compatibility range.
- TLS handshakes succeed.
- Secrets and certificates are fetched at the correct version.
- Service discovery returns current endpoints.
- Message broker grants appropriate assignments.
- Leases are re-acquired or verified.
- Cache revisions and external state are reconciled.

### 12.3 Filesystem and Native Memory

If the application uses file mappings or native code:

- Backing files exist with proper permissions.
- Mount layout matches.
- Mappings can be read/written as required.
- Native libraries load with the correct ABI.
- Direct/mapped memory is managed properly.
- No native crashes or invalid handle errors occur.

### 12.4 Functional Smoke Tests

Send representative requests after restore:

- Read data.
- Write test data with an idempotency key.
- Call an internal dependency.
- Exercise a processing path using TLS.
- Verify authentication using the runtime identity.
- Verify readiness opens only after reconciliation.

Use sandbox data and test dependencies in CI. Do not let matrix tests trigger production payments, emails, or side effects.

## 13. Measuring Timing and Performance

In addition to pass/fail, record measurements to tell whether environment changes degrade performance.

Useful metrics:

- Checkpoint creation time.
- Checkpoint artifact size.
- Time from restore command to process alive.
- afterRestore callback duration.
- External reconciliation duration.
- Time to readiness.
- First-request latency.
- Post-restore throughput.
- Post-restore error rate.
- RSS/PSS and native memory.
- File descriptor count and memory mappings.
- Artifact download time.

Compare using the same workload and measurement method. Do not conclude one kernel is faster from a single run; multiple iterations and percentile analysis may be necessary.

### 13.1 Distinguishing Process Restore Time from Time-to-Ready

An engine may restore a process quickly while the application takes a long time to reconnect to the database or fetch credentials. Measure separately:

~~~text
T0: restore command started
T1: process restored
T2: afterRestore callbacks completed
T3: external state reconciled
T4: readiness true
~~~

- Restore duration = T1 - T0.
- Callback duration = T2 - T1.
- Reconcile duration = T3 - T2.
- Time-to-ready = T4 - T0.

Time-to-ready is the metric closest to deployment experience. Measuring only engine restore time can cause the pipeline to miss real bottlenecks.

## 14. When Should the Matrix Be Re-Run?

The matrix needs updating when the environment changes. You do not need to re-run the entire suite on every commit, but you need clear trigger policies.

| Change | Tests that should be triggered |
|---|---|
| JDK vendor/build | Compile, callbacks, and JDK-related real restore matrix |
| CRaC runtime/API | Real checkpoint/restore across all mandatory targets |
| Checkpoint engine/version | Real restore matrix |
| Kernel/node image | Restore on the updated node pool |
| CPU architecture | Separate checkpoint and restore on the corresponding architecture |
| CPU feature baseline | Restore/native smoke tests on the new feature profile |
| Container image/base image | Create new checkpoint and restore using the new digest |
| Container runtime/OCI runtime | Restore on runners using the new runtime |
| Native library/JNI | Native smoke and real restore |
| Filesystem/mount | File mapping and restore tests |
| JVM flags | Create new image and restore under the new configuration |
| External dependency/config | Reconciliation, readiness, and integration tests |

Dependency fingerprints can be used to determine which profiles are affected. If only one node pool changes its kernel, re-run pairs using that node pool and relevant source images. However, if a shared JDK or engine changes, the retest scope may be broader.

### 14.1 Nightly Drift Detection

Nightly jobs can collect runner metadata and compare it against verified profiles. If the kernel or runtime has changed, the job marks NEEDS_RETEST and runs restore tests.

This is especially useful with hosted runners or auto-updating node pools. If CI cannot guarantee fixed hosts, actual metadata must be saved for every run.

## 15. Handling Failures in the Matrix

A failing matrix job needs to pinpoint the failing layer rather than simply returning “restore failed”.

| Layer | Example | Investigation direction |
|---|---|---|
| Provisioning | Failed to fetch JDK or image | Registry, artifact source, and runner setup |
| Source startup | Application failed to warm up or readiness false | App logs, dependencies, and fixtures |
| Checkpoint | beforeCheckpoint or engine failed | Callback exception tree, engine logs, host privileges |
| Artifact handoff | Missing file or checksum mismatch | Upload/download, storage, and paths |
| Target provisioning | Runner has wrong kernel/CPU/runtime | Host fingerprint and runner labels |
| Process restore | Engine could not recreate the process | JDK/engine/kernel/CPU compatibility |
| Callback recovery | afterRestore threw an exception | Resource lifecycle and dependencies |
| External reconciliation | Secret/DB/DNS/lease invalid | External services and identity |
| Functional test | Request failed after restore | App state, stale caches, and business flows |

Save exit codes, stdout/stderr, engine logs, and JVM logs by source-target pair. Avoid logging secrets or tokens.

### 15.1 Controlled Retries

Transient infrastructure errors such as runner disconnects or artifact download timeouts can be retried. However, do not infinitely retry deterministic failures such as:

- Incompatible JDK build.
- Wrong CPU architecture.
- Missing capability.
- Native library fails to load.
- Backing file does not exist.
- Callback consistently throws an exception.

A flaky test needs its own status and root-cause investigation. Do not flip FLAKY to VERIFIED merely because the last retry passed.

### 15.2 Preserving Evidence Even When Jobs Fail

Use an always step or equivalent mechanism to collect reports, without letting the evidence-publishing step turn a failed test into a success.

Each report needs:

- Workflow run ID.
- Commit/release ID.
- Checkpoint ID.
- Source and target profiles.
- Artifact checksum.
- JDK/engine/kernel/CPU/container metadata.
- Restore result.
- Callback result.
- Application test result.
- Failure reason.
- Timestamp and duration.

## 16. Securing CI Runners and Artifacts

Checkpoint images can contain heap data, tokens, sessions, or decrypted secrets. Therefore, checkpoint artifacts and runners must be protected like an environment holding sensitive data.

Apply these principles:

- Use sandbox data and scoped credentials.
- Do not put production secrets onto CI runners.
- Restrict permissions to create, download, and restore checkpoints.
- Encrypt artifacts at rest and in transit.
- Use short artifact retention suited to test purposes.
- Delete checkpoint files and workspaces after jobs.
- Do not run untrusted pull requests on runners with privileged access.
- Do not record tokens or environment secrets in metadata.
- Audit artifact downloads and restores.
- Do not upload checkpoints to public artifact storage.

If runners are self-hosted, segment the runner pool. Ordinary build jobs should not have access to checkpoint storage or the host capabilities that restore tests require.

## 17. Example Policy for Release Gates

A policy can define required target profiles in YAML:

~~~yaml
matrixPolicyVersion: 1

requiredTargets:
  - prod-amd64-poolA
  - prod-amd64-poolB
  - prod-arm64-poolA

requiredChecks:
  artifactIntegrity: true
  processRestore: true
  resourceCallbacks: true
  externalReconciliation: true
  functionalSmoke: true
  readiness: true

allowedStatuses:
  - VERIFIED

fallback:
  enabled: true
  mode: fresh-jvm-startup

evidence:
  requireCheckpointId: true
  requireSourceProfile: true
  requireTargetProfile: true
  requireArtifactChecksum: true
  requirePipelineRun: true
~~~

This is an illustrative policy schema defined by the pipeline. The release gate needs to verify each required target has a VERIFIED result for the exact checkpoint ID and source-target pair. Do not accept a passing result from an old checkpoint or a profile with a different fingerprint.

If production only uses amd64, there is no need to make arm64 a required target. If a disaster recovery region uses a different kernel/runtime, that profile needs to be included in the required list.

## 18. Managing Artifacts and Metadata Between Jobs

Source jobs and target jobs need to exchange immutable checkpoint artifacts.

Store:

- Checkpoint files in the structure required by the engine.
- Checkpoint ID.
- Artifact checksum.
- Source environment profile.
- JAR checksum.
- Container image digest.
- JDK vendor/version/build.
- Engine name/version.
- Required JVM flags.
- Checkpoint creation timestamp.
- Application build and config compatibility metadata.

Target jobs need to verify checksums before restore. Do not modify or merge files from multiple checkpoints. Do not use artifact names that can be overwritten without a version.

If CI artifact storage has short retention, ensure the artifact persists for all target jobs. For large matrices, object storage or a dedicated artifact store with restricted access can be used.

## 19. Example Matrix for a Release

A release can define profiles as follows:

| Profile | JDK | Kernel | CPU | Container | Role |
|---|---|---|---|---|---|
| SRC-A | Vendor A CRaC build 21.x | K1 | amd64 + AVX2 | Digest X / runtime R1 | Create amd64 checkpoint |
| DST-A | Vendor A CRaC build 21.x | K1 | amd64 + AVX2 | Digest X / runtime R1 | Production pool A |
| DST-B | Vendor A CRaC build 21.x | K2 | amd64 + AVX2 | Digest X / runtime R2 | Production pool B |
| SRC-C | Vendor A CRaC build 21.x arm64 | K3 | arm64 profile | Digest Y / runtime R1 | Create arm64 checkpoint |
| DST-C | Vendor A CRaC build 21.x arm64 | K3 | arm64 profile | Digest Y / runtime R1 | Production arm64 |

The profiles above are only examples. Replace them with the exact builds and configurations supported by the vendor.

Matrix pairs can be:

| Source | Target | Required | Expected result |
|---|---|---:|---|
| SRC-A | DST-A | Yes | VERIFIED |
| SRC-A | DST-B | Yes | VERIFIED |
| SRC-C | DST-C | Yes | VERIFIED |
| SRC-A | DST-C | No | UNSUPPORTED or NOT_APPLICABLE per vendor policy |

Do not restore an amd64 image on arm64 just to add a test row if the vendor specifies that combination is unsupported. Document the exclusion reason clearly.

## 20. Implementation Workflow in CI

The following workflow can be applied for every runtime-affecting change or before a release:

**Step 1 — Identify target profiles.** Obtain the list of actually deployed node pools and runtime classes. Record JDK, kernel, CPU, container runtime, and architecture.

**Step 2 — Cross-check vendor support.** Exclude unsupported source-target pairs. Specify which fields must match and which may differ.

**Step 3 — Provision source runner.** Select a runner with the matching kernel, CPU, and engine. Install the exact JDK build and pull the container digest.

**Step 4 — Collect source fingerprint.** Record OS, kernel, CPU features, JDK, engine, container runtime, image digest, and JVM flags.

**Step 5 — Create real checkpoint.** Start the application, warm up, check readiness, run beforeCheckpoint, and save the artifact along with its manifest.

**Step 6 — Fan out target jobs.** Each job receives the exact checkpoint artifact and runs on the designated target runner.

**Step 7 — Collect target fingerprint.** Verify the actual runner matches the required profile before restore.

**Step 8 — Restore and verify application.** Run engine restore, check callbacks, external reconciliation, functional smoke tests, and readiness.

**Step 9 — Store evidence.** Record results per source-target pair, including logs, checksums, and durations.

**Step 10 — Enforce release gate.** Publish checkpoints only if mandatory targets meet policy. Keep fresh startup fallback for unverified targets.

**Step 11 — Monitor drift.** When JDK, kernel, CPU, engine, or container runtime changes, trigger retests for affected profiles.

**Step 12 — Clean up runners and temporary artifacts.** Stop processes, unmount volumes, revoke test credentials, and delete workspaces per retention.

## 21. Completion Criteria for a Matrix Run

A matrix run can be considered complete when:

- All mandatory source profiles created a checkpoint or reported a clear error.
- Each artifact has an ID and checksum.
- Target jobs use the exact artifact from the declared source.
- Target metadata is collected from real runners.
- Runners match the required profiles.
- Restore tests use the real checkpoint engine.
- Post-restore callbacks completed.
- External dependencies and readiness are verified.
- Functional smoke tests passed.
- Every required pair has a status and evidence.
- Skipped or blocked jobs are not counted as passes.
- Artifacts and temporary workspaces are handled per retention policy.

If a target cannot run because the runner is offline, the outcome is BLOCKED. If the target profile does not exist yet, it is UNTESTED. If process restore succeeds but app tests have not run, it is PROCESS_RESTORED or PARTIALLY_VERIFIED per policy. Use VERIFIED only when all mandatory checks have passed.

## 22. Common Mistakes

### Testing Only One JDK Major Version

Major version does not fully identify the vendor, patch, build, and CRaC integration. Record the exact JDK build.

### Running Multiple Containers on the Same Kernel and Calling It a Kernel Matrix

Containers share the host kernel. You need runners or VMs with genuinely different kernels.

### Using a Container Image to Emulate a CPU

Containers do not emulate the host's architecture or CPU features. Run targets on hosts/VMs with the corresponding CPU profile.

### Checking Only java -version

That command does not reveal the engine, kernel, CPU features, container runtime, or mount profile. Collect metadata from both the host and the process.

### Using Simulation Tests Instead of Real Restore Tests

Simulation is useful for callback logic, but does not prove the process image can be restored by the real engine.

### Building an Oversized Cartesian Product

Many combinations are not applicable or unsupported. Build the matrix from production profiles and required source-target pairs.

### Not Recording the source → target Direction

One A → B run does not prove B → A. Record each pair in the actual direction.

### Relying on Runner Labels Without Checking Metadata

The host may have had its kernel upgraded or CPU changed. Read the actual fingerprint and fail fast on profile mismatch.

### Treating Restore Exit Code as Complete Success

The process may be alive while the database, TLS, secrets, or broker have not recovered. Run application checks and readiness checks.

### Ignoring Skipped Matrix Rows

A green workflow can hide untested targets. The release gate needs to verify the list of required pairs and evidence.

### Infinitely Retrying Deterministic Failures

Compatibility errors must be investigated and blocked. Retrying will not fix a wrong architecture, JDK build, or native ABI.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): the checkpoint/restore model and application coordination.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): preparing the JDK/runtime and running a CRaC application.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): checkpoint engines and differences across builds.
- [CRaC — Debugging](https://crac.org/reference/debugging/): diagnosing checkpoint and restore failures.
- [GitHub Actions — Using a matrix for your jobs](https://docs.github.com/actions/using-jobs/using-a-matrix-for-your-jobs): organizing job matrices and include/exclude.
- [GitHub Actions — Choosing the runner for a job](https://docs.github.com/actions/using-jobs/choosing-the-runner-for-a-job): runner labels and self-hosted runners.
- [GitHub Actions — Workflow artifacts](https://docs.github.com/actions/using-workflows/storing-workflow-data-as-artifacts): passing checkpoint artifacts and test evidence between jobs.
- [Kubernetes — Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/): container runtimes on nodes.
- [Kubernetes — Nodes](https://kubernetes.io/docs/concepts/architecture/nodes/): nodes and host resources in a cluster.
- [Linux man-pages — uname](https://man7.org/linux/man-pages/man2/uname.2.html): querying kernel/system identity.
- [Linux man-pages — proc](https://man7.org/linux/man-pages/man5/proc.5.html): process and CPU/system information via procfs.
- [CRIU Documentation](https://criu.org/): checkpoint/restore of processes on Linux and system requirements.
