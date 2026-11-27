# CPU Targets and Binary Portability Across Machines with Different Instruction Sets

A Spring Boot native executable does not depend solely on the operating system and CPU architecture such as Linux/AMD64 or Linux/AArch64. It also depends on the **CPU instruction set (ISA)** that GraalVM allowed the compiler to emit when creating the binary.

Two machines both running Linux x86-64 may still fail to run the same native executable if the target CPU lacks an instruction set required by the binary. A common situation is building a binary on a newer machine with AVX2, FMA, or another instruction group, then deploying it to an older machine or a VM/cloud instance with restricted CPU features.

GraalVM Native Image provides the `-march` option to choose the target CPU level. Choosing the right level balances performance with the range of machines able to execute the binary. This lesson focuses on understanding ISA targets, choosing a baseline, configuring Maven/Gradle/Buildpacks, diagnosing incompatibility errors, and testing across target machine groups.

## 1. Two Compatibility Axes to Distinguish

When shipping a native executable, verify two independent compatibility layers:

1. **Platform target:** the operating system and CPU architecture the executable is built for, such as Linux/AMD64 or Linux/AArch64.
2. **CPU instruction-set target:** the specific CPU instructions the compiler is permitted to emit on that architecture, such as x86-64-v2 or x86-64-v3.

Native Image provides two corresponding options:

| Option | Controls | Example | Does Not Mean |
| --- | --- | --- | --- |
| `--target` | Platform consisting of OS and CPU architecture | `linux-amd64`, `linux-aarch64` if supported by the toolchain | Does not select AVX/SSE level or CPU microarchitecture |
| `-march` | CPU instruction-set level for the Graal compiler | `-march=x86-64-v3`, `-march=compatibility` | Does not turn Linux into Windows or AMD64 into AArch64 |

For instance, `linux-amd64` only specifies that the executable targets Linux on AMD64. It does not specify whether the binary requires baseline x86-64-v1, v2, v3, or v4.

A container image tagged `linux/amd64` likewise does not fully describe CPU requirements. Two nodes both reporting AMD64—one with AVX2 and the other without—can behave differently when executing the binary.

### Where CPU Target Fits in the Spring Boot Pipeline

~~~mermaid
flowchart TD
    A["Java source and dependencies"] --> B["Spring AOT"]
    B --> C["Generated source, bytecode, and hints"]
    C --> D["GraalVM Native Image build"]
    D --> E["Select OS/architecture target"]
    E --> F["Select CPU ISA via -march"]
    F --> G["Native executable"]
    G --> H["Check deployment machine CPU and OS"]
    H --> I{"Sufficient platform and CPU features?"}
    I -->|Yes| J["Run application"]
    I -->|No| K["Rebuild for appropriate target"]
~~~

Spring AOT prepares code and metadata for the application. The CPU target is decided during the GraalVM Native Image build step, after AOT inputs are produced.

## 2. What Is an Instruction Set?

An instruction set is the set of instructions a CPU can execute. Common instruction groups include:

- SSE and its extensions on x86.
- AVX, AVX2, and AVX-512 on supporting x86-64 CPUs.
- BMI1, BMI2, FMA, and F16C on certain x86 generations.
- AArch64 extensions such as AES, SHA, CRC32, LSE, or SVE depending on CPU and toolchain.

The compiler can optimize code using newer instructions. If a binary contains instructions unsupported by the destination CPU, the process may refuse to start or hit an illegal instruction error when reaching that code path.

### x86-64 Levels

On AMD64, microarchitecture feature levels are commonly named x86-64-v1, v2, v3, and v4. These levels are cumulative: higher levels include all requirements of lower levels.

| Level | Overview | Deployment Implication |
| --- | --- | --- |
| x86-64-v1 | Original x86-64 baseline, including foundational instructions like SSE2 | Broadest older CPU compatibility among common x86-64 levels |
| x86-64-v2 | Adds extensions such as SSE3, SSSE3, SSE4.1, SSE4.2, and POPCNT | Requires CPUs supporting v2's additional instruction group |
| x86-64-v3 | Adds AVX, AVX2, BMI1, BMI2, FMA, and additional extensions | Will not run on CPUs lacking AVX2 or other mandatory v3 features |
| x86-64-v4 | Adds the corresponding AVX-512 group | Deploy only on CPUs and OS environments supporting all v4 features |

This table is a summary, not a complete CPUID specification. Certain extensions also require the OS to enable and save the corresponding register state. CPU model names or release years are only hints; verify actual feature flags on the destination machine.

### AArch64

AArch64 has architectural levels such as `armv8-a` and subsequent extensions. Do not apply x86-64 level names to ARM. One ARM machine may support AES or LSE while another ARM machine of the same base architecture lacks those extensions.

The list of targets and features supported by GraalVM varies by version and platform. Run `native-image -march=list` and `native-image --list-cpu-features` on the exact toolchain to see available choices.

## 3. GraalVM's `-march` Option

GraalVM Native Image provides `-march` to control the instruction set the Graal compiler is allowed to emit when generating native code.

Common configurations:

| Configuration | Behavior | When to Use |
| --- | --- | --- |
| `-march=compatibility` | Selects a conservative instruction set, lowering CPU requirements for older machines | Distributing binaries to many machines or fleets with heterogeneous CPUs |
| `-march=native` | Lets the compiler use CPU features detected on the build machine | Building and running on the same machine or a fleet with identical feature sets |
| `-march=x86-64-v2` | Explicitly targets x86-64-v2 if listed as supported by the toolchain | When all destination machines are confirmed to meet the v2 baseline |
| `-march=x86-64-v3` | Explicitly targets x86-64-v3 if listed as supported by the toolchain | Fleets with a verified v3 baseline |
| `-march=list` | Prints machine types Native Image can target | Surveying valid targets before configuring |

`-march=native` can leverage AVX2, AES, LSE, or features present on the build machine. In exchange, the binary may fail to run on other machines even of the same CPU architecture.

`-march=compatibility` lowers ISA requirements to widen the range of compatible machines. That may forgo some optimization opportunities, though it does not mean every workload becomes noticeably slower. Benchmark with real workloads.

### Defaults Change Across GraalVM Versions

Do not assume every GraalVM version uses the same default:

- In GraalVM for JDK 17/20, a change in the 23.0 line set the AMD64 default to `x86-64-v3`; previously `compatibility` was the default.
- Current documentation describes the x64 default as `x86-64-v3`.
- The AArch64 default has changed across releases and version docs. Some release notes state `armv8.1-a`, while optimization pages of certain releases list `armv8-a`.

Therefore, **the build output from the exact toolchain you run is the final authority on the selected machine type**. When upgrading GraalVM, re-check the target machine line in build output and re-test on the lowest supported CPU group.

## 4. Inspecting Machine Types and CPU Features Before Building

Run the following commands with the exact GraalVM JDK containing Native Image:

~~~bash
# Active Native Image version.
native-image --version

# Selectable machine types.
native-image -march=list

# CPU features recognized by the toolchain's target platform.
native-image --list-cpu-features
~~~

The last two commands answer two different questions:

- `-march=list` lists the machine-type level names supported by the compiler.
- `--list-cpu-features` lists the target platform's CPU features usable by the toolchain.

To inspect a Linux host's CPU, you can run:

~~~bash
lscpu
grep -m 1 '^flags' /proc/cpuinfo
~~~

Inside a VM or container, the feature list visible to the guest may be masked by the hypervisor or container configuration. Do not rely solely on the physical machine's CPU model underneath.

### Reading Build Output

Native Image build output contains Graal compiler details, typically showing optimization level and target machine. For example:

~~~text
Graal compiler: optimization level: 2, target machine: x86-64-v3
C compiler: gcc (linux, x86_64, ...)
~~~

If build output shows `x86-64-v3`, the binary was built for that level even if the build command omitted `-march`. This is why build logs or machine-readable build reports should be archived alongside artifacts.

## 5. Choosing a Baseline for the Deployment Environment

Choose the CPU target based on the set of machines actually running the binary, not the developer's workstation.

| Environment | Recommended Strategy | Rationale |
| --- | --- | --- |
| Fixed single host, build and deploy on same machine | Consider `-march=native` | Can utilize all known CPU features |
| Homogeneous cloud fleet with verified baseline | Pick explicit ISA level or `native` if build host matches | Uses optimizations while controlling compatibility |
| Fleet spanning multiple AMD64 CPU generations | `-march=compatibility` or lowest baseline supported fleet-wide | Avoids binaries requiring instructions missing on older nodes |
| Software distributed to customers without hardware control | `-march=compatibility` | Maximizes chance of running across diverse CPUs |
| System deployed strictly on ARM | Build for AArch64 target and pick an appropriate baseline | AMD64 binaries cannot run natively on ARM64 |
| Mixed AMD64 and AArch64 | Produce separate artifacts per OS/architecture | A single native executable is not a multi-architecture binary |

### Selection Example

A system has 30 AMD64 nodes, 10 of which are older and fall below the v3 baseline. Building on a new workstation with the v3 default leaves part of the fleet unable to run the binary.

Two design options exist:

- Build one binary targeting the lowest common baseline met by the entire fleet.
- Build multiple binary variants and schedule artifacts onto node pools with matching CPU features.

The second option preserves optimizations for newer nodes at the cost of more artifacts, build pipelines, and test matrices.

## 6. Distinguishing CPU ISA Errors from OS/ABI Errors

A binary can use a compatible ISA yet still fail due to platform differences.

| Issue | Example | Resolution |
| --- | --- | --- |
| Incompatible CPU ISA | Binary requires AVX2, target CPU lacks AVX2 | Rebuild with a lower `-march` |
| Different CPU architecture | AMD64 binary run on AArch64 | Build a dedicated AArch64 executable |
| Different OS | Linux binary run directly on Windows | Build for the target OS |
| Different libc | Binary depends on glibc while runtime image has only musl | Choose matching builder/runtime and verify linkage |
| Incompatible native library | JNI library compiled with higher ISA than main binary | Replace or rebuild the native dependency with a matching baseline |

`-march=compatibility` only governs the instruction set emitted by the Native Image compiler for generated code. It does not convert a Linux binary into a Windows binary, change `libc`, or fix a JNI library already compiled with higher CPU requirements.

## 7. Why Spring AOT Does Not Decide the CPU Target

Spring AOT analyzes the `ApplicationContext` and generates code/hints for Native Image to process. Those AOT files remain inputs that can be packaged inside an executable JAR.

GraalVM Native Image is the step that generates machine code for a specific OS/architecture and CPU target.

Spring Boot supports pipelines that build an executable JAR with AOT assets once, then convert that JAR into a native image in the appropriate CI/CD step. This lets you reuse the intermediate Java artifact across build targets, while each native executable must still be built separately for its target deployment platform.

### Native Image Is Not a General-Purpose Cross-Compiler

The `--target` option can select an OS/architecture target in formats supported by the toolchain, but you should not assume setting `--target` lets you cross-compile from any build host to any OS/CPU.

Spring Boot documentation explicitly notes that Native Image does not support general-purpose cross-compilation. When multiple platforms are needed, use build workers or buildpacks running on the respective platforms. An AOT-asset JAR can be a shared input; the native executable must be built in a matching build environment.

## 8. Configuring Maven Native Build Tools

For a Spring Boot project using `native-maven-plugin`, pass `-march` via `buildArgs`.

Compatible baseline example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-march=compatibility</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

If the project already configures the plugin in a parent POM or `native` profile, add the argument to the existing configuration instead of creating a duplicate plugin declaration.

Build the executable:

~~~bash
./mvnw -Pnative native:compile
~~~

If targeting a v2 baseline verified across the fleet:

~~~xml
<buildArgs>
    <buildArg>-march=x86-64-v2</buildArg>
</buildArgs>
~~~

Use a specific machine type only if `native-image -march=list` on your exact GraalVM toolchain lists it and every target host meets its feature requirements.

Native Build Tools treats each `buildArg` as an individual option expression. Never put an entire shell command string inside one `buildArg` element.

## 9. Configuring Gradle Native Build Tools

With Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

When building strictly for a fleet confirmed on x86-64-v3:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=x86-64-v3")
        }
    }
}
~~~

Build the executable:

~~~bash
./gradlew nativeCompile
~~~

If the project has multiple binaries such as `main` and `test`, decide which options apply to each binary. Share settings across all binaries only when all target the same platform and CPU baseline.

### Kotlin DSL

In `build.gradle.kts`, configure the same Native Build Tools extension:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

Exact API syntax can vary by plugin version. Check the Native Build Tools version managed by the build and use `buildArgs` on the corresponding binary.

## 10. Passing the CPU Target with Cloud Native Buildpacks

Spring Boot can use Paketo Buildpacks to create a container image containing a native executable. The Native Image buildpack provides the environment variable:

`BP_NATIVE_IMAGE_BUILD_ARGUMENTS`

This variable passes arguments directly to the `native-image` command. Example using `pack` with an AOT-processed executable JAR:

~~~bash
pack build orders-api:0.1.0 \
  --path target/orders-api.jar \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-march=compatibility
~~~

The input JAR must contain AOT-generated assets. The buildpack executes the Native Image build inside the builder container and places the executable into the application image.

Points to verify:

- The builder image and buildpack must support the target OS/architecture.
- Which architecture the builder runs on and which CPU features it exposes can affect `-march=native` detection.
- When running a builder under CPU emulation, never assume reported features match real deployment hosts.
- Record the buildpack/builder version, GraalVM version, and build output.
- The runtime image must match the executable's OS, architecture, and `libc`.

With Maven/Gradle Spring Boot plugins, image build environment variables can be configured through the plugin's API. When strict control is needed, verify the buildpack environment reached the build phase and confirm `native-image` logs received the argument.

## 11. Producing Artifacts for Multiple OSes and Architectures

If the service must run on both Linux AMD64 and Linux AArch64, the pipeline should build two separate native artifacts:

~~~mermaid
flowchart TD
    A["Source code"] --> B["Spring AOT"]
    B --> C["Executable JAR with AOT assets"]
    C --> D["Linux AMD64 build worker"]
    C --> E["Linux AArch64 build worker"]
    D --> F["AMD64 native binary"]
    E --> G["AArch64 native binary"]
    F --> H["linux/amd64 container image"]
    G --> I["linux/arm64 container image"]
    H --> J["Multi-platform manifest"]
    I --> J
~~~

You can store the AOT-processed executable JAR as an intermediate artifact. Each build worker uses a matching GraalVM Native Image and native toolchain to compile the executable for its target.

### Container Manifests Do Not Replace CPU Baselines

A multi-platform OCI image can hold manifests for `linux/amd64` and `linux/arm64`. When pulling, the container runtime picks the image matching OS/architecture.

However, the manifest does not check x86-64-v2/v3/v4 compatibility. If the AMD64 binary is built for v3, the image still carries the `linux/amd64` label yet will fail on AMD64 nodes lacking v3 features.

For heterogeneous AMD64 fleets, standardize a single ISA baseline in the build pipeline or schedule deployments according to node capabilities.

## 12. CPU Feature Mismatch Errors and Diagnosis

A common error when running a binary on an older CPU looks like:

~~~text
The current machine does not support all of the following CPU features
that are required by the image: [ ... ]
Please rebuild the executable with an appropriate setting
of the -march option.
~~~

The feature list in the message identifies which instructions the binary requires that the current CPU lacks.

Troubleshooting workflow:

1. Record the GraalVM version and target machine type from the build output.
2. Inspect CPU features on both the build machine and destination machine.
3. Determine whether the binary was built with `-march=native`, the version default, or an explicit ISA level.
4. Select `-march=compatibility` or a lower explicit level supported across all destination machines.
5. Rebuild the binary and test on the machine with the lowest baseline.
6. If `Illegal instruction` persists, inspect JNI/C/C++ native libraries and system libraries as well.

### Distinguishing Feature Errors from Architecture Errors

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| Message listing missing AVX2, BMI2, FMA, or similar features | CPU target too high | Lower `-march` |
| Binary reports wrong executable format | Wrong OS or CPU architecture | Check `file`, platform, and build target |
| `Exec format error` on ARM | Running an AMD64 binary on ARM or vice versa | Build binary for the matching architecture |
| `Illegal instruction`/`SIGILL` | CPU lacks instruction or native dependency targets higher ISA | Inspect binary and JNI/shared libraries |
| Missing `libc.so` or shared library error | Runtime image lacks required ABI/library | Inspect dynamic dependencies and runtime base image |

Do not change only `-march` when the actual failure stems from wrong OS, architecture, or `libc`.

## 13. Native Libraries and JNI Also Need the Same Baseline

Native Image's `-march` governs the instruction set emitted by the Graal compiler for code it generates. A Spring Boot application may also rely on external native code:

- JNI libraries.
- C/C++ libraries packaged inside JARs.
- Database drivers with native components.
- Compression, cryptography, or image-processing libraries.
- Shared libraries loaded via `System.loadLibrary`.

A C/C++ library might be prebuilt with AVX2 or AVX-512. In that case, even if the main binary uses `-march=compatibility`, the process can still hit `SIGILL` when calling that library on an older CPU.

When suspected:

1. List packaged or runtime-loaded shared libraries.
2. Check vendor documentation for CPU requirements.
3. Use OS tools to inspect dependencies, such as `ldd` on Linux.
4. If you build the native library yourself, pick a compatible baseline or use tested runtime dispatch.
5. Run integration tests on the fleet machine with the lowest feature set.

Not every library must be compiled for the lowest baseline. Some libraries select implementations via runtime CPU dispatch. Verify the actual dispatch mechanism rather than assuming.

## 14. Benchmarking Performance Before Picking a Baseline

Selecting `-march=native` can let the compiler emit extra instructions and speed up certain workloads. Gains depend on code paths, CPU-bound share, native libraries, memory access, and real load.

For a meaningful comparison, build two binaries from the same source and same GraalVM version:

- Binary A: `-march=compatibility`.
- Binary B: `-march=native` or the fleet's specific ISA level.

Hold all other conditions constant:

- Same optimization level, GC, heap limit, and dependency versions.
- Same container base image and OS.
- Same CPU/VM for performance measurements if both binaries can run there.
- Same request mix, dataset, concurrency, and warmup duration.
- Measure throughput, p50/p95/p99 latency, CPU, memory, and error rate.

Never benchmark Binary A on an old machine and Binary B on a new machine and attribute the entire gap to `-march`. CPU model, memory, kernel, virtualization, and network all affect results.

### Metrics to Record

| Metric | Purpose |
| --- | --- |
| Build target machine | Confirms the selected ISA |
| Startup/ready time | Checks for startup differences |
| Throughput | Measures requests processed per second |
| p95/p99 latency | Evaluates latency tail |
| CPU utilization | Checks CPU efficiency |
| Peak RSS/container memory | Tracks memory cost |
| Error rate | Confirms binary correctness |
| CPU model and feature flags | Documents the benchmark environment |

`-march` is only one variable in native optimization. Do not change GC, PGO, optimization level, and CPU target together if your goal is understanding each choice's impact.

## 15. Pre-Release Checklist for Native Executables

- [ ] Documented exact target OS and architecture.
- [ ] Identified the lowest CPU baseline in the deployment fleet.
- [ ] Checked the default `-march` of the active GraalVM version.
- [ ] Checked `native-image -march=list`.
- [ ] Checked CPU features on both build machines and deployment hosts.
- [ ] Avoided `-march=native` on CI runners unrepresentative of destination hosts.
- [ ] Configured `-march` via Maven, Gradle, or Buildpacks.
- [ ] Verified builder image and runtime image compatibility.
- [ ] Checked whether JNI/shared libraries impose separate ISA requirements.
- [ ] Tested the binary on the lowest supported CPU.
- [ ] Archived GraalVM version, build output, and machine type with the artifact.
- [ ] If supporting multiple OSes/architectures, built and tested separate binaries per target.

## 16. Hands-On Exercise: Building Two CPU Targets and Testing Portability

Suppose the `orders-api` service deploys onto a Linux AMD64 fleet spanning multiple CPU generations. The goal is building one binary that runs on the common baseline and comparing it with a binary optimized for the build machine.

### Part A — Survey the Toolchain

Run:

~~~bash
native-image --version
native-image -march=list
native-image --list-cpu-features
~~~

Record the GraalVM version, selectable machine types, and CPU features.

### Part B — Build the Compatible Binary

With Maven, configure the plugin to pass:

~~~xml
<buildArgs>
    <buildArg>-march=compatibility</buildArg>
</buildArgs>
~~~

Then build:

~~~bash
./mvnw -Pnative native:compile -DskipTests
~~~

With Gradle, configure:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-march=compatibility")
        }
    }
}
~~~

Then run:

~~~bash
./gradlew nativeCompile
~~~

### Part C — Build the Build-Host Binary

Create a separate build variant passing:

~~~text
-march=native
~~~

Run both binaries on the build machine. Compare build outputs to confirm distinct target machines. Measure throughput and latency under the same workload.

### Part D — Destination Machine Testing

1. Pick a machine/VM with the lowest CPU feature set in the fleet.
2. Run the compatibility binary and send requests to health/business endpoints.
3. Run the native-target binary on the same machine to see whether features are missing.
4. If an error occurs, record the reported features and pick a lower baseline.
5. Run additional tests on newer AMD64 nodes.
6. If the system includes ARM64, run a separate build on an AArch64 worker and validate the `linux/arm64` container image.

### Self-Check Questions

1. Why might two AMD64 machines still fail to run the same native executable?
2. How does `-march` differ from `--target`?
3. Why can `-march=native` fail when built on CI and deployed to older hosts?
4. How does `-march=compatibility` affect optimization opportunities?
5. Why should you check CPU features inside a VM/container rather than relying solely on the physical CPU model?
6. Why does the OCI `linux/amd64` label not fully capture x86-64-v2/v3/v4 requirements?
7. Why can a Spring AOT JAR be reused while native executables still must be built per platform?
8. Why should `--target` not be treated as a general-purpose cross-compilation solution?
9. Can a JNI library trigger `SIGILL` even when the Graal compiler uses `-march=compatibility`?
10. Which conditions must be held constant to benchmark two CPU targets fairly?

**Completion criteria:** can explain the difference between OS/architecture target and CPU instruction-set target; chooses `-march` based on the real fleet; configures it via Maven, Gradle, or Buildpacks; diagnoses missing CPU feature errors; tests binaries on the lowest baseline host; and builds separate artifacts when deploying across multiple OSes/architectures.

## Official Documentation

- GraalVM — Optimizations and Performance: https://www.graalvm.org/jdk25.5/reference-manual/native-image/optimizations-and-performance/
- GraalVM — Command-line Options: https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/Options/
- GraalVM — Native Image Build Output: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/
- GraalVM — Native Image Changelog: https://github.com/oracle/graal/blob/master/substratevm/CHANGELOG.md
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Paketo — Native Image Buildpack: https://github.com/paketo-buildpacks/native-image
