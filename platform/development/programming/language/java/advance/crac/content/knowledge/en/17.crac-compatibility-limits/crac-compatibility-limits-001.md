# Compatibility Between Checkpoint and Restore by JDK Version and Vendor

A CRaC checkpoint image is the state of a Java process that has already run, including the JVM state and the operating system resources supported by the checkpoint mechanism. Therefore, the image depends on the runtime that created it. An image created with a specific CRaC JDK build cannot by default be restored with just any other JDK, even when the two JDKs have the same Java version number.

When designing a release process, you need to clearly define the pair of **checkpoint runtime** and **restore runtime** environments supported by the vendor. Information such as vendor, distribution, full version, build number, CPU architecture, operating system, kernel, CRIU, and native libraries can all affect compatibility. The safe approach is to create a compatibility matrix with test evidence, store runtime information alongside the image, and only deploy confirmed checkpoint–restore pairs.

## 1. Why Does a Checkpoint Image Depend on the JDK?

The JVM does more than just execute bytecode. While the application operates, the runtime creates many internal structures such as heap objects, class metadata, thread stacks, runtime data, code cache, memory management structures, and native state. A checkpoint image can store part or all of the process state within the scope supported by the CRaC build and the platform.

These structures depend on how a JVM build is constructed and implemented. Two JDK builds with the same Java language level can differ in:

- Layout and representation of internal structures of HotSpot or another JVM implementation.
- How heap, garbage collector, threads, monitors, and code cache are managed.
- Security patches, native libraries, and packaged runtime components.
- CRaC integration mechanisms, metadata formats, and restore procedures.
- JVM flags, agents, modules, and bundled libraries.

Therefore, the fact that an application compiles with Java 21 does not prove that an image created with one JDK 21 can be restored with every other JDK 21. The major version is only one part of the runtime identity.

### 1.1. Distinguishing Three Types of Versions

When recording the environment, you need to distinguish:

| Concept | Illustrative Example | Meaning |
|---|---|---|
| Java feature version | 17, 21, 25 | Java platform release line |
| Update/patch version | 21.0.x | Update release within the same feature release |
| Vendor build/distribution | Vendor name, build number, revision | Specific JDK build with its own patches and integrations |

Two runtimes with the same feature version but different updates or builds can still be incompatible with the same checkpoint image. Conversely, a vendor may explicitly publish a compatible set of builds or support restore across a number of updates. You may rely on that scope only when confirmed by the documentation for that exact vendor and exact CRaC release line.

### 1.2. A Checkpoint Image Is Not Portable Bytecode

Java JARs and bytecode are designed to run on compatible JVMs. A checkpoint image, on the other hand, contains the state of a specific process that has already run. You can think of it as:

- A JAR is the input for the JVM to create a new process.
- A checkpoint image is a snapshot of the process after the JVM has loaded and initialized the application.
- Restore recovers the process from the snapshot according to the rules of the runtime and the operating system.

Therefore, bytecode compatibility rules cannot be used to infer checkpoint image compatibility rules. A JAR may run on many JDKs while the image created from that JAR can still only be restored on a narrower set of supported runtimes.

## 2. Role of the JDK Vendor

CRaC requires coordination between the JVM and the checkpoint/restore platform. JDK vendors may package, configure, or support CRaC differently. Not every JDK distribution includes CRaC; adding the Java library `org.crac` does not by itself add checkpoint/restore capabilities to a standard JVM.

When choosing a vendor, you need to read the documentation for the exact product and version:

- Whether that JDK line supports CRaC.
- Which operating systems and CPU architectures are supported.
- Which CRIU version, kernel, and system configurations are required.
- Whether an image can be restored with the same build or if a range of other builds is supported.
- Whether there are limitations across patch updates, CPU releases, vendor revisions, or container images.
- Which JVM options, agents, and native libraries are supported.
- Troubleshooting procedures and how to collect restore logs.

You should not conclude that two JDKs are compatible just because both are based on OpenJDK, both use HotSpot, or both implement the `org.crac` API. Sharing the same source base does not equate to having the same binary build, CRaC configuration, or restore conditions.

### 2.1. Same Vendor Still Requires Build Verification

Choosing the same vendor is a useful condition to reduce differences, but it is not an absolute guarantee. A vendor may change CRaC packaging, JVM patches, or platform requirements between releases.

If the documentation does not state a clear compatibility range, treat **same vendor, same distribution, same full version, and same build** as the standard configuration for creating and restoring images. When upgrading a patch or build, create a new image with the new runtime and rerun tests. Do not use an old image with a new runtime just because they share the same vendor.

### 2.2. Different Vendors Must Be Treated as Different Runtimes

An image created by vendor A's CRaC JDK must not be assumed restorable with vendor B's CRaC JDK by default. Two vendors may use different patches, build options, native integrations, and checkpoint management approaches.

Only attempt cross-vendor restore when both vendors have documentation explicitly confirming that the version pair is supported. Without confirmation, create a new image using the target vendor's runtime. The fact that both runtimes run the same application does not prove they can read and restore the same snapshot.

## 3. Distinguishing the JDK Runtime from the `org.crac` Library

A Java application can use APIs in the `org.crac` package, such as:

- `org.crac.Resource` to describe the lifecycle of a resource.
- `org.crac.Context` to represent the resource management context.
- `org.crac.Core` to access the global context.

The Maven dependency `org.crac:crac` provides the Java API for application code. It is not a JVM and does not replace a CRaC-enabled JDK. You need to distinguish:

| Component | Role | Does It Provide Image Restore Capability by Itself? |
|---|---|---|
| CRaC-enabled JDK | JVM and runtime checkpoint/restore integration | Yes, within the scope supported by the JDK/platform |
| `org.crac:crac` | Java API for applications to register Resources and callbacks | No |
| CRIU or equivalent OS mechanism | Supports process checkpoint/restore at the system layer | Does not replace a CRaC JVM |
| Application JAR | Application bytecode and resources | No |

The API version can affect compilation compatibility, available methods, and how the application registers a Resource. However, source/binary-level API compatibility does not mean checkpoint image compatibility between two JVMs. Manage two separate questions:

1. Does the application code use the exact `org.crac` API supported by the chosen JDK/framework?
2. Is the runtime used for restore within the supported version set for reading the created image?

If the JDK already provides the API in its own way, follow the vendor's documentation to avoid packaging duplicate or incompatible classes. If a Maven dependency is needed, explicitly pin the version and inspect the dependency tree.

## 4. Compatibility Layers to Verify

Restore capability does not depend solely on the JDK version. An image can be created successfully yet fail when moved to another host due to conditions outside the JVM.

| Compatibility Layer | Information to Record | Risk When Different |
|---|---|---|
| JDK vendor/distribution | Vendor and distribution name | Different CRaC integration or runtime binary |
| JDK version/build | Full version, build number, revision | Changes in runtime structures or image support |
| JVM options | GC, heap, modules, agents, and CRaC flags | Different runtime initialization or incompatible options |
| CPU architecture | `amd64`/`x86_64`, `arm64`/`aarch64` | Different instruction set and native binaries |
| OS distribution | Linux name and version | Different libc, system libraries, and filesystem layout |
| Kernel | Version and enabled features | Missing capabilities required for checkpoint/restore |
| CRIU | Version and configuration | Unable to read/restore system state |
| Native dependencies | JNI, `.so`, agent, driver | Incompatible binary or ABI |
| Container/runtime | Image digest, container runtime, namespace, cgroup | Different filesystem, permissions, and process configuration |
| Filesystem/mount | Path, volume, permissions, and file contents | FD or path does not exist after restore |
| Network | Interface, address, route, DNS, and port | Socket or external connection is no longer valid |

Some components can be changed if the vendor supports it and the application handles resources properly. For example, a database endpoint can be re-read after restore; however, that does not mean every old socket can remain intact. You need to classify which resources are restored by the engine, which resources must be closed/reopened via a Resource, and which resources are mandatory host requirements.

## 5. Version-Based Checkpoint–Restore Matrix

Instead of writing only a single line “JDK 21”, build a matrix of image-creating runtime and restore runtime pairs. The example below illustrates the structure, not a compatibility confirmation table for any specific vendor.

| Checkpoint Runtime | Restore Runtime | Initial Status to Apply |
|---|---|---|
| Vendor A, build X | Vendor A, build X | Standard configuration; still must be tested on the target OS/arch |
| Vendor A, build X | Vendor A, build Y | Supported only if vendor documentation confirms; do not accept without evidence |
| Vendor A, build X | Vendor A, different feature release | Do not assume compatibility; requires specific support documentation |
| Vendor A, build X | Vendor B, build Z | Do not assume cross-vendor compatibility; requires official confirmation |
| Vendor A, build X | Same JDK but different OS/kernel | Check the platform matrix and run a restore test |
| Vendor A, build X on amd64 | Same build on arm64 | Do not assume the image is portable across architectures |

You can use the following management statuses:

- `SUPPORTED`: announced as supported by the vendor and has passed project testing.
- `TESTED`: tested successfully by the project, but without an official support commitment; requires risk assessment before production use.
- `UNTESTED`: no evidence yet; do not use as a standard runtime pair.
- `UNSUPPORTED`: documentation or testing confirms it is not supported.

Do not mark as `SUPPORTED` based solely on a single successful attempt. A single passing restore may not cover load conditions, native dependencies, architectures, or failures occurring at another time.

### 5.1. Default Policy When No Vendor Matrix Exists

If the vendor documentation does not clearly state cross-version restore capability, apply a conservative rule:

1. Create the image with a specific CRaC JDK.
2. Restore with that exact vendor, distribution, version, and build.
3. Keep the verified architecture, OS/runtime image, and system conditions unchanged.
4. When upgrading the JDK, create a new image using the new JDK.
5. Only expand to another patch/build after reading the documentation and running tests for that specific pair.

This is a reproducible operational baseline. If the vendor publishes a broader compatibility range, you can expand the matrix according to the exact conditions they state.

## 6. Recording Runtime Identity When Creating an Image

Each image needs sufficient metadata to identify which application and runtime created it. You should not name the directory solely after the application version, because multiple builds can share the same version while differing in commit, JDK, or dependencies.

Runtime information can be retrieved using:

```bash
java -version
java -XshowSettings:properties -version
```

Useful properties include `java.vendor`, `java.version`, `java.runtime.version`, `java.vm.name`, `java.vm.version`, `java.home`, and `os.arch`. On Linux, also record:

```bash
cat /etc/os-release
uname -a
uname -m
ldd --version
criu --version
```

The commands above help identify the running environment. Not all information is provided by JVM properties; you need to save results from the host or container runtime where appropriate.

### 6.1. Example Manifest for a Checkpoint Image

```yaml
checkpointImage:
  imageId: "orders-api-2.4.0-build-318-amd64"
  application:
    version: "2.4.0"
    gitCommit: "<commit-sha>"
    artifactSha256: "<jar-sha256>"
    dependencyLockSha256: "<lockfile-sha256>"
  jdk:
    vendor: "<vendor-name>"
    distribution: "<crac-enabled-distribution>"
    version: "<full-version>"
    build: "<build-number-or-revision>"
    vmName: "<vm-name>"
    vmVersion: "<vm-version>"
    architecture: "amd64"
  platform:
    os: "<distribution-and-release>"
    kernel: "<kernel-version>"
    libc: "<libc-version>"
    criu: "<criu-version>"
    containerDigest: "sha256:<digest>"
  runtime:
    jvmOptionsHash: "<options-hash>"
    nativeDependencies: "<native-dependency-manifest>"
  checkpoint:
    createdAt: "<timestamp>"
    restoreTestedWith: "<exact-runtime-identity>"
    restoreStatus: "PASS"
```

The values in angle brackets are placeholders and must be replaced with actual data. The manifest should be generated automatically in the pipeline to avoid manual entry errors. If a field has not been collected yet, record an unknown status instead of guessing.

### 6.2. A Manifest Does Not Replace Compatibility Verification

A manifest indicates which environment the image was created from. It does not by itself prove that the target runtime is compatible. Before restoring, the deployment system should compare the image metadata with the current environment against the confirmed policy.

For example, if the image requires JDK build X but the node is running build Y that is not yet in the matrix, the deployment should stop and require creating a new image or approving the runtime pair after testing. Do not ignore the warning just because both runtimes have the same Java feature version.

## 7. Container Image and Host Are Two Different Layers

A container image can pin the JDK, system libraries in the filesystem, the application JAR, and certain tools such as CRIU. However, a container uses the host's kernel. A container image digest does not package the entire kernel or every condition required for restore.

When creating and restoring inside a container, you need to check:

- Digest of the image containing the JDK and application.
- Container runtime and version.
- Host kernel and features required by CRIU.
- PID, mount, network namespaces, and cgroups.
- Capabilities, seccomp, AppArmor, or SELinux policies.
- Volumes, mount points, file paths, and access permissions.
- How the orchestration platform assigns network identity and ports after restore.

If the image is created on one Linux host and then restored in Kubernetes, test using a configuration close to the target pod/node. A privileged container may checkpoint successfully in a lab but lack the same permissions in production. Lab results in that case do not prove that the real deployment will work.

## 8. Native Library and JNI Compatibility

An application may use native libraries via JNI, JNA, agents, or drivers. These components depend on CPU architecture, ABI, libc, binary version, and native state at checkpoint time.

For example, a Java JAR may be identical on `amd64` and `arm64`, but the `.so` file loaded into the JVM is an architecture-specific binary. A checkpoint image from a process that has loaded that library cannot be treated as a portable artifact across architectures.

When native dependencies exist, record:

- Name, version, and checksum of each native binary.
- CPU architecture and ABI.
- Required libc and system library versions.
- How the library releases/recreates native handles.
- Whether native threads or native callbacks are active during checkpoint.
- Whether the vendor supports checkpoint/restore for that library.

If a native component cannot be safely checkpointed, use a wrapper/Resource to release it before checkpoint and recreate it after restore, or exclude that component from the process to be checkpointed. The fact that a Java object is restored does not guarantee that native pointers or handles remain valid.

## 9. JDK Upgrades and Strategy for Creating New Images

Upgrading the JDK can change the runtime build, native libraries, CRaC integration, and platform requirements. Therefore, a JDK upgrade should be treated as a change to the image creation chain.

The upgrade process should include:

1. Read the vendor's release notes and CRaC documentation for the new JDK version.
2. Identify new requirements for OS, kernel, CRIU, architecture, and containers.
3. Update the JDK build in the build/runtime image and pin related dependencies.
4. Rebuild the application using the chosen toolchain.
5. Start the application with the new JDK, run warm-up, and prepare Resources.
6. Create a new checkpoint image in a separate staging directory.
7. Restore using that exact new runtime and run smoke tests.
8. If cross-version restore support is needed, test each checkpoint–restore pair against the matrix and confirm vendor support.
9. Publish the new image only after restore, readiness, and business tests succeed.
10. Keep the old image together with the old runtime for as long as rollback remains necessary.

Do not replace the JDK in a container and continue using an old checkpoint image without compatibility confirmation. The new image should be created from a process running the exact application build and the new runtime.

### 9.1. Rollback Also Requires the Exact Runtime

Keeping an old checkpoint image without keeping the corresponding runtime can make rollback impossible. Rollback artifacts need to accompany the JDK/container/host configuration that created and successfully restored that image.

A release can store the pair:

```text
release-2.3/
  application.jar
  runtime-manifest.yml
  container-image-digest.txt
  checkpoint-image/

release-2.4/
  application.jar
  runtime-manifest.yml
  container-image-digest.txt
  checkpoint-image/
```

The paths only illustrate the organization structure. The goal is to keep the artifact and runtime identity linked together. When rolling back, deploy the image together with the verified compatible environment.

## 10. Matrix-Based Compatibility Testing

A single checkpoint and restore using the same runtime only confirms that this baseline works. If the project wants to support patch upgrades, host changes, or vendor changes, each combination must be intentionally tested.

### 10.1. Pairs to Test

| Scenario | Objective |
|---|---|
| Create and restore with the same JDK build | Verify runtime baseline |
| Create with build X, restore with build Y from the same vendor | Verify patch/build range according to vendor documentation |
| Create and restore with two different feature releases | Determine whether it is supported; do not assume success by default |
| Create with vendor A, restore with vendor B | Test only if cross-vendor support is declared |
| Same JDK, change Linux distribution/kernel | Check system dependencies and CRIU |
| Same JDK/OS, change CPU architecture | Confirm architecture limits; do not assume portability |
| Same runtime, change container digest | Check native dependencies, filesystem, and configuration |
| Restore after the image has been stored for a long time | Check secrets, certificates, DNS, leases, and external dependencies |

You do not need to test every conceivable combination. Select the pairs that need support in production, the pairs in the upgrade plan, and a few negative pairs to verify that the system rejects invalid environments.

### 10.2. Smoke Test Steps

1. Print and save the JDK identity, vendor, version, build, and VM.
2. Save OS, kernel, architecture, CRIU, and container digest.
3. Start the designated application build.
4. Perform warm-up and register Resources.
5. Request checkpoint and verify the image is completely created.
6. Restore using the target runtime in the matrix.
7. Verify that the `afterRestore` callback has executed.
8. Check the database, HTTP client, message consumer, and mandatory resources.
9. Run health/readiness checks and a few representative business requests.
10. Record restore time, time to readiness, logs, and results.

If restore fails, save the full JVM and CRIU logs along with the metadata of both environments. Do not save only the final error message, because the root cause may appear during image validation, memory restoration, FD reopening, or application callbacks.

### 10.3. Testing Rejection of Unsupported Pairs

The pipeline should also prove that the system does not deploy the wrong image. For example, if the manifest specifies JDK build X but the node only has an unapproved build Y, the pre-restore check must reject the deployment and clearly indicate the discrepancy.

Early rejection helps avoid attempting a restore on an unsupported environment and surfaces configuration errors before the instance joins the rollout.

## 11. Diagnosing Compatibility Errors

Restore errors can occur at multiple layers. You need to correlate the error against the image creation metadata and the target runtime.

| Symptom | Cause Group to Check |
|---|---|
| Runtime rejects image or reports version mismatch | JDK vendor, build, format, or CRaC version |
| CRIU- or kernel-related error | CRIU version, kernel features, capabilities, namespaces, cgroups |
| Native library load error | Architecture, ABI, libc, `.so` path, binary version |
| File or descriptor open error | Path, mount, permissions, modified file, or FD policy |
| Socket/network error | Network namespace, interface, address, route, peer, or un-recreated resource |
| `afterRestore` callback failure | External dependency, credentials, factory, Resource order, or recovery logic |
| Restore succeeds but readiness fails | Application state, database, cache, message broker, or runtime configuration |

Some investigation principles:

- Compare the image's manifest with the actual runtime; do not rely on container labels or abbreviated JDK names.
- Confirm the exact `java` executable used for restore via `java -version` and `java.home`.
- Inspect JVM and CRIU logs from the same run.
- Check permissions, namespaces, and mounts on the actual host.
- Distinguish errors caused by the runtime rejecting the image from errors caused by application callbacks after restore.
- Do not work around errors by bypassing version checks or altering binaries inside the image directory.

## 12. Managing Images by Runtime Identity

A checkpoint image needs to be managed as a versioned artifact. Naming the image solely by the application build is not enough; you should also associate the runtime identity and architecture.

Example structure:

```text
artifacts/
  orders-api/
    2.4.0/
      commit-a81f2d1/
        linux-amd64/
          vendor-a-jdk-21.0.x-build-123/
            checkpoint-image/...
            manifest.yml
            restore-test.log
      2.4.1/
        commit-b42c9e0/
          linux-amd64/
            vendor-a-jdk-21.0.y-build-127/
              checkpoint-image/...
              manifest.yml
              restore-test.log
```

These are illustrative identifiers, not actual JDK version names. Each checkpoint directory should be created separately for a single image creation run. Do not overwrite an image currently used by production; create a new image, test restoring it, and publish it with an immutable identifier.

The retention policy should keep images still referenced by deployments and builds needed for rollback. When deleting old images, also delete related metadata according to policy, but do not delete runtime artifacts still needed to recover retained releases.

## 13. Common Mistakes

**Comparing only the Java major version.** Sharing Java 21 does not prove two JDKs have the same build or support the same image. Record vendor, distribution, full version, and build.

**Assuming the same vendor is always compatible.** Vendors can change the runtime and CRaC rules between releases. Check the official matrix and test the specific build.

**Assuming all OpenJDK-based JDKs can restore each other's images.** CRaC integration and runtime binaries can differ. Do not assume cross-vendor compatibility without confirmation.

**Confusing the `org.crac` API with a CRaC-enabled JVM.** The API dependency helps application code compile and register Resources; it does not add checkpoint/restore capabilities to a regular JDK.

**Pinning only the container digest.** The digest does not pin the host kernel, namespaces, capabilities, or all CRIU conditions. You must check the host as well.

**Ignoring CPU architecture.** Images and native libraries may depend on `amd64` or `arm64`. Build and test separately for each architecture.

**Upgrading the JDK while reusing an old image.** The old image still contains the previous runtime state. Create a new image with the new JDK unless the vendor confirms the version pair is supported.

**Checking only that checkpoint succeeds.** Creating an image successfully does not prove restore succeeds. Always run restore and check readiness.

**Marking a pair as supported after one attempt.** Test results do not replace a vendor support statement. Clearly record `TESTED` or `SUPPORTED` along with corresponding evidence.

**Keeping rollback images while deleting the corresponding runtime.** Rollback may no longer be possible. Store the image–runtime pair together.

## 14. Self-Check Questions

1. **Why is having the same Java feature version not enough to conclude checkpoint image compatibility?** Because vendor, distribution, update, build, and CRaC integration may differ.
2. **Can an image from vendor A be restored by default using vendor B?** No. Only do so when both parties confirm that the runtime pair is supported and the project has tested it.
3. **Does `org.crac:crac` provide checkpoint capability for a regular JDK?** No. It provides the Java API; checkpoint/restore requires a supporting runtime and platform.
4. **Why should the JDK build number be recorded in the manifest?** To accurately identify the runtime that created the image and compare it against the target runtime.
5. **Does a container digest pin the kernel?** No. A container uses the host kernel, so the kernel and CRIU conditions must be recorded and checked.
6. **What should be done with the checkpoint image when upgrading the JDK?** Create a new image from the application running on the new JDK and test restoring it with the target runtime.
7. **How does `SUPPORTED` differ from `TESTED`?** `SUPPORTED` has official support documentation along with project testing; `TESTED` only indicates the project has tested it successfully without a corresponding support commitment.
8. **Why does rollback require keeping the old runtime?** Because the old image may only be restorable on the JDK and environment that created it, or on a pair confirmed by the vendor.

## Conclusion

A checkpoint image is tied to the state of a process and the runtime that created it. Restore capability depends on the vendor, distribution, full version, JDK build, CPU architecture, operating system, kernel, CRIU, container/runtime, and native dependencies. Sharing the same Java feature version or the same `org.crac` API is not enough to prove two environments are compatible.

Choose a standard runtime set, save a detailed manifest alongside the image, and build a matrix for each checkpoint–restore pair. When there is no documentation confirming cross-version compatibility, use the exact JDK build that created the image as the baseline. Any JDK upgrade or platform change requires creating a new image and running a restore test on the target environment. Keep the rollback image together with its corresponding runtime so that the release and recovery processes remain reproducible.