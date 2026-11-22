# Building a Matrix of Supported JDKs, Vendors, Operating Systems, and Architectures

## 1. Why Does Regression Testing During a JDK Upgrade Require a Matrix?

A Java application may run fine on JDK 17 on a developer workstation yet fail when deployed on JDK 21 in production. The difference is not just the two numbers 17 and 21. A JDK comes with a **distribution/vendor**, patch updates, operating system, CPU architecture, container configuration, native library set, and accompanying JVM flags.

For example:

- CI runs Eclipse Temurin on Linux `x86_64`, whereas production runs a different JDK distribution on Linux `aarch64`.
- Unit tests run JDK 21 on Windows, whereas the application deploys onto Alpine Linux with `musl` instead of `glibc`.
- A JNI driver supplies native binaries for Linux x64 yet lacks Linux ARM64.
- The application uses TLS encryption and truststores; another JDK distribution/OS image has different root certificates or security configurations.
- A tracing agent works on JDK 17 yet has not been declared supported by the vendor for the target JDK.
- Java classes are compatible, yet a bytecode generation library does not understand the new class-file major version.
- Tests turn green on Apple Silicon macOS because Java runs under Rosetta/x64 emulation; native production ARM64 exhibits different native behavior.

Therefore, the question “has Java 21 been tested yet?” is too vague. You must ask more precisely:

> **Which artifact** ran, on **which JDK vendor/build**, on **which OS/architecture**, with **which runtime image and dependency set**, under **which test suite**, and **do the results fall within the official support scope**?

A **compatibility matrix** answers those questions. It distinguishes **combinations the product commits to support** from **combinations tested only for reference**, while turning the claim “Java compatible” into reproducible evidence.

## 2. The Matrix's Goal Is Not Testing Everything Exhaustively

Taking 3 JDK releases × 3 vendors × 3 OSes × 2 architectures already yields 54 theoretical combinations, before even counting patch versions, libc, JVM flags, application servers, drivers, agents, and databases.

Not every combination even exists as a vendor-supported binary. Nor does every combination require running the full end-to-end suite.

**The right goals** are:

1. Identify the platforms the product genuinely **commits to support**.
2. Explicitly exclude combinations that lack a distribution or sit outside the support policy.
3. Select tests capable of catching major regressions.
4. Ensure every **production or release-blocking combination** is tested deeply enough.
5. Run supplemental tests to detect interactions across JDK, vendor, OS, and architecture.
6. Preserve evidence including versions, binaries, images, test reports, and timestamps.
7. Set explicit release-blocking criteria; never equate “tests ran” with “supported”.

A matrix is a **contract defining support scope and verification processes**, not a decorative spreadsheet filled with green cells.

## 3. Primary Dimensions of the Matrix

| Dimension | Example | Risks This Dimension Helps Detect |
| --- | --- | --- |
| JDK feature release | Java 8, 11, 17, 21 | API removals, class-file version, GC/JIT, module encapsulation |
| JDK update/build | 17.0.x, 21.0.x, exact build | Patches, regressions, changed security defaults |
| JDK distribution/vendor | Temurin, Corretto, Zulu, Oracle JDK, Microsoft, Semeru, Liberica... | Packaging, JVM implementation, truststore/providers, support policy |
| JVM implementation | HotSpot-family, OpenJ9, or another supported runtime | JIT/GC/JVM options, attach, diagnostics, native integration |
| Operating system | Linux, Windows, macOS | Native loader, file paths, encoding, process model |
| OS release/image | Ubuntu/RHEL/Alpine/Windows build/macOS release | libc, certificates, system packages, permissions |
| CPU architecture | x86_64/amd64, aarch64/arm64 | JNI binaries, calling conventions, CPU intrinsics |
| Runtime environment | Bare metal, VM, container, Kubernetes | cgroup limits, PID namespaces, startup flags, native libraries |
| Packaging/loading mode | Classpath, module path, fat JAR, `jlink` image | Class loading, modules, resource/service lookup |
| Dependencies/agents | JDBC, JNI/JNA, HTTP client, APM, coverage | Bytecode/native/runtime compatibility |
| Application workload | Request APIs, batch, messaging, encryption, persistence | Actual functionality and non-functional regressions |

The **JDK feature release** and **JDK update version** dimensions must be kept separate. Writing “Java 21” is insufficient to reproduce a regression tied to a specific patch or vendor build.

## 4. Distinguish Four Types of “Support”

A combination might run yet still not be committed to customers. Label clearly:

| Type | Meaning | Release Consequence |
| --- | --- | --- |
| **Supported** | Inside the product's official policy, with an owner and test plan | Can block release if failing |
| **Validated** | Successfully tested with a specific build and suite | Point-in-time test evidence; does not automatically become a long-term commitment |
| **Experimental** | Tested to uncover risks or prepare future support expansion | Usually non-blocking unless specified |
| **Unsupported** | Out of policy, EOL, lacks supported binaries, or invalid combination | Must not be presented as validated |

You can add **Untested** for combinations inside support scope that lack evidence. That represents a gap to resolve, not a passing state.

### 4.1. Separate Vendor Support from Application Support

A JDK vendor publishing a distribution for a given OS/CPU does not mean **your application** automatically supports that combination. Conversely, your application passing some tests on an unmaintained distribution does not replace a formal support/EOL policy.

Combinations entering production should satisfy **both sides**: a binary/runtime supported under approved policy and verified application test evidence.

## 5. Define Support Scope from the Product Before Designing CI

Do not start from whichever runners GitHub Actions or a CI provider happens to offer. Start from **real users and deployments**:

- Does the application run exclusively inside organization-published containers, or do customers bring their own JDK?
- Is it a server application, desktop application, SDK/library, or CLI tool?
- Do customers still run JDK 11/17, or is Java 21 already the committed minimum?
- Do customers run Windows Server, Linux ARM64, or macOS?
- Are native binaries distributed per OS/CPU?
- Is there a commitment to multiple JDK vendors, or just one approved distribution?
- Are FIPS, custom truststores, proxies, LDAP/Kerberos, or smart cards required?
- Must rolling deployments across different JVM versions be supported?
- Is rollback possible once a new producer writes data or alters a protocol?

A backend running strictly inside team-controlled Linux AMD64 Kubernetes has a different matrix from a commercial SDK shipped across multi-architecture Windows/macOS/Linux.

### 5.1. Three Scope Groups to Declare Explicitly

**Production baseline:** Combinations currently running in production that must stay green throughout migration.

**Target supported:** Combinations promised after cutover; acts as the primary release gate.

**Exploratory/forward-looking:** Combinations used to surface risks early, such as an upcoming JDK feature release or an architecture the market may demand.

Never mix failing exploratory tests into a report claiming “all supported platforms passed”.

## 6. Build a Support Policy with a Clear Lifecycle

Example policy for a Java server:

~~~text
Application: orders-service
Current supported runtime: JDK 17 on approved Linux image
Target supported runtime: JDK 21 on approved Linux images
Allowed vendors: Temurin and Corretto, subject to validated binaries
Architectures: linux/amd64; linux/arm64 after native dependency validation
Unsupported: JDK 8/11, desktop OS and unapproved runtime images
JDK patch policy: approved security update baseline
Test policy: production combinations are release-blocking
Review cadence: each JDK security-update cycle and OS-image change
Owner: runtime-platform and service team
~~~

This is merely an **example**, not a recommendation of vendors or JDK levels for every organization.

### 6.1. Feature Release vs. Update Release

21 is a feature release. Builds like 21.0.x can differ in security fixes, certificate handling, performance, or bug fixes. The matrix should record:

~~~text
jdk_feature: 21
jdk_full_version: 21.0.x+build
vendor_distribution: ...
jvm_implementation: ...
image_digest: sha256:...
~~~

When pinning a baseline patch, maintain a reasonable security patch update policy instead of staying on an outdated build indefinitely. Picking up a new patch must re-trigger appropriate test suites.

### 6.2. Do Not Equate “LTS = Forever Supported”

LTS JDKs carry different update and support policies depending on vendor, license, and timeframe. A feature release labeled LTS does not guarantee unlimited free patches for an artifact. Always inspect the lifecycle/support contract of the exact distribution and release.

## 7. JDK Vendors: Why “Same Java” Still Requires Testing

JDK distributions sharing a feature release generally adhere to Java SE platform compatibility, yet implementation/operational details can still diverge:

- JVM implementation and JIT/GC tuning.
- Default configuration, build flags, or patch sets.
- Certificates/truststores, CA lists, and security provider setup by distribution/image.
- Packaging, filesystem layout, and presence of tools like `jcmd`/`jfr`/`jlink`.
- License, update cadence, and support window.
- OS/CPU architecture coverage.
- Diagnostic flags, JVM crash signatures, and native integration.
- Presence or absence of vendor value-add features.

Examples of commonly encountered distributions:

| Distribution | What to Verify |
| --- | --- |
| Eclipse Temurin | Release/build, supported OS/arch, HotSpot packaging, update policy |
| Amazon Corretto | Specific build, OS/architecture support, update policy |
| Azul Zulu | Version, JVM variant/configuration, supported platforms |
| Oracle JDK | Distribution/build/license/support terms, supported platforms |
| Microsoft Build of OpenJDK | Release/build, supported OS/CPU, support commitments |
| IBM Semeru | Runtime implementation variant, features/flags, OS/CPU support |
| BellSoft Liberica | Distribution variant, package contents, supported platforms |
| GraalVM-based runtime | JDK compatibility, runtime mode, native image vs. JVM execution |

This table does not claim every distribution ships every JDK/OS/architecture. **Include a cell in the matrix only when a matching binary exists and is vendor-supported/organization-approved.**

### 7.1. Do Not Equate Vendor with JVM Implementation

“Different vendor” does not always mean a different JIT/GC implementation; many distributions are built on HotSpot. Conversely, a distribution offering another JVM such as OpenJ9 can alter flags, diagnostics, and operational behavior.

Therefore record **distribution + JVM implementation** instead of a single “vendor” column from which everything is guessed.

### 7.2. Rules for Selecting Representative Vendors

If production strictly runs one approved distribution, test that combination deeply. If a library/SDK claims to be vendor-neutral, select a genuinely distinct set of representative vendors and define the boundaries of your commitment.

Do not run every vendor daily just to feel thorough, yet never claim “runs on every JDK vendor” when evidence comes from only one build.

## 8. Operating Systems: More Than Just Linux, Windows, macOS

Listing `Linux` in a matrix is insufficient, especially when applications use JNI/JNA, native agents, or filesystem interactions.

Important differences:

- OS distribution and release.
- C standard library (`glibc` vs. `musl` on Linux).
- Kernel version and container runtime.
- Filesystem case sensitivity, path separators, and permissions.
- Default charset/locale/timezone when configuration or operations differ.
- Named pipes, sockets, file locks, and process signals.
- TLS certificate stores, native crypto providers, keystores.
- Native dynamic linker rules and shared library dependencies.
- Scheduler, threads, memory allocation, and resource limits.
- Attach/debug/profiling permissions.

### 8.1. Linux `glibc` vs. `musl`

A native library compiled for Linux `glibc` will not automatically run on Alpine Linux `musl`. Changing the Docker base image while upgrading the JDK can simultaneously swap the underlying ABI.

Example error:

~~~text
java.lang.UnsatisfiedLinkError:
  /app/native/libcodec.so: error loading shared library ...
~~~

Do not immediately blame JDK 21 if the upgrade also switched the base image from Debian to Alpine.

### 8.2. Windows

Testing should cover:

- Actual Windows edition/build.
- DLL search behavior and Microsoft runtime dependencies.
- File paths with spaces, drive letters, and separators.
- File locking and deleting/renaming open files.
- Process creation, service account privileges, and charset.
- Native binaries matching `x64` or `arm64`.

Never infer behavior for a Windows-supported SDK solely from Linux results.

### 8.3. macOS

Distinguish Apple Silicon `arm64` from Intel `x86_64`, the actual JVM/CLI architecture, binary slices, code signing, and native dependencies.

An Apple Silicon machine can execute an x64 JDK under Rosetta. Those tests exercise x64 emulation, **not** native arm64 support.

## 9. CPU Architectures: x64 and ARM64 Are Distinct Combinations

Java bytecode is portable, yet an entire application may not be:

- JNI/JNA/native libraries must supply matching CPU binaries.
- APM, profilers, native transports, and compression libraries may ship separate binaries.
- Calling conventions, alignment, word size, and endianness assumptions affect native code.
- CPU instruction sets and vectorization can alter JIT behavior/performance.
- Atomic operations, memory fences, and concurrency timing may differ.
- Docker images must carry the matching manifest/platform.
- Architecture-specific JVM flags may not exist or may carry different semantics.

### 9.1. Examples of Architecture Representation

~~~text
Linux x86_64    ~ linux/amd64
Linux aarch64   ~ linux/arm64
Windows x64     ~ windows/amd64
macOS arm64     ~ darwin/arm64
~~~

These are common toolchain conventions, not identical names used across every API. `os.arch` may report `amd64`, `x86_64`, or `aarch64` depending on the JVM. **Normalize values for comparison** while preserving raw values in test evidence.

### 9.2. Do Not Check Only `uname -m`

A shell may run on an ARM64 host while the container/JVM runs a different binary or emulation layer. Record:

- Host architecture.
- Container platform.
- JVM `os.arch` and JVM build.
- Architecture of the native library actually loaded.

If those values do not align as expected, test reports must flag the discrepancy instead of stamping “native ARM64 pass”.

## 10. Container Images: A Dimension That Often Must Be Separated

For containerized deployments, JDK/vendor/OS/arch matrix testing works best pinned to **image digests**, not mutable tag names:

~~~text
registry.example/orders:java21
registry.example/orders@sha256:<immutable-image-digest>
~~~

Tags can move to point at another manifest, whereas digests pinpoint the exact image artifact tested. A multi-arch image carries a manifest list/index and child manifests; when tracing native failures, store both the image reference/digest and resolved platform.

### 10.1. Container Configuration Affects the JVM

- CPU/memory limits enforced via cgroups.
- User ID, permissions, and read-only filesystems.
- Whether `/tmp` and dump/log directories are writable.
- Container/PID namespaces and attach mechanisms.
- Certificate stores, timezone data, and DNS configuration.
- Native libraries baked into the base image.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and entrypoint scripts.
- Platform-injected JVM agents or instrumentation.

Consequently, “tested JDK 21 Linux AMD64” must state **whether tests ran inside the matching production image or using a JDK installed directly on a CI runner**. One result does not substitute for the other.

### 10.2. Distroless, Slim, and `jlink` Images

Minimal images can lack a shell, CLI diagnostics, or JDK modules/providers available in a full JDK. If the application uses `ServiceLoader`, reflection, TLS, or JNI, test directly inside the final runtime image.

Do not treat `java -version` in a full JDK container as proof that a `jlink` runtime image contains all required modules.

## 11. Frequently Overlooked Dimensions Beyond the Four Main Axes

To make the matrix practical, sometimes secondary dimensions must be captured:

| Secondary Dimension | Example | When to Prioritize |
| --- | --- | --- |
| Compiler JDK and `--release` | JDK 21, `--release 17` | Libraries/SDKs preserving a Java minimum |
| Runtime Java flags | GC, memory, `--add-opens` | JVM migration/agents/tooling |
| Application framework | Spring, Jakarta, Quarkus, custom | Concurrent major framework upgrades |
| Database/driver | DB vendor, JDBC version, TLS | Backend persistence |
| Network/security | TLS protocol, ciphers, FIPS policy | Regulated/secure services |
| Native/agent versions | JNI, Netty native, APM | OS/architecture variants |
| Packaging | JAR, fat JAR, module path, `jlink` | Libraries, modules, and launchers |
| Workload | CPU-bound, I/O-bound, latency-sensitive | Non-functional regressions |
| Cloud/instance type | ARM vs. x86 nodes, VM families | Runtime performance/architecture |

You do not need to turn every dimension into a massive Cartesian product. **Attach secondary dimensions to specific test cases or compatibility groups** wherever they can influence results.

## 12. Rules for Selecting Valid Combinations

A combination should only be scheduled if:

1. A JDK vendor publishes binaries for that release/OS/architecture.
2. The binary falls within support scope or has a documented experimental rationale.
3. The CI runner/container runs natively on that architecture without unintended emulation.
4. The application and its native dependencies can be packaged for that environment.
5. Appropriate test suites exist and evidence can be retained.
6. If production-supported, an owner is assigned to address regressions.

Hypothetical example:

~~~text
JDK 21 × Vendor A × Linux x64   => Supported + mandatory
JDK 21 × Vendor A × Linux arm64 => Supported after JNI validation
JDK 21 × Vendor B × macOS x64   => Experimental CLI
JDK 17 × Vendor A × Windows arm64 => Unsupported by product policy
~~~

Labels here only illustrate the **classification method**; they make no claim about whether vendor A/B supports specific binaries.

### 12.1. “No Runner Available” Differs from “Unsupported”

If the product promises an OS/arch yet CI lacks a runner, that is a **testing coverage gap**. Never mark it “unsupported” merely to turn reports green without changing the product contract. Add a runner, a controlled manual test protocol, or obtain formal approval to revise the support policy.

## 13. Product-Level Matrix Table Template

Suppose a server application is migrating from JDK 17 to JDK 21:

| ID | JDK | Distribution | OS/image | Arch | Support | CI Depth |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | 17 latest-approved patch | Temurin | Linux glibc image A | amd64 | Baseline supported | Full |
| P02 | 21 latest-approved patch | Temurin | Linux glibc image B | amd64 | Target supported | Full |
| P03 | 21 latest-approved patch | Corretto | Linux glibc image B | amd64 | Target supported if approved | Full |
| P04 | 21 latest-approved patch | Temurin | Linux glibc image B | arm64 | Target candidate | Native + integration |
| P05 | 21 latest-approved patch | Temurin | Linux musl image C | amd64 | Experimental | Smoke + native |
| P06 | 21 latest-approved patch | Temurin | Windows image D | x64 | Outside server policy | Optional CLI test |

Image names and support labels are hypothetical illustrative data. **Do not declare P03/P04 supported until both vendor/platform and application verification are complete.**

### 13.1. Required Columns to Include

At a minimum:

~~~text
matrix_id
application_artifact_or_commit
jdk_feature
jdk_full_version_and_build
distribution
jvm_implementation
os_name_and_version
libc_or_base_image
cpu_architecture
deployment_mode
support_status
test_profile
expected_result
owner
evidence_link_or_artifact_id
last_validated_at
~~~

Include JDK flags, native/agent versions, and container digests when associated risks exist.

## 14. Tiering Test Depth to Avoid Multiplicative Cost Explosion

You do not need to run 20 hours of end-to-end tests on every cell. Partition into profiles:

| Profile | Includes | When Applied |
| --- | --- | --- |
| **Compile/API** | Build, bytecode target, API diff, dependency resolution | All artifacts/target releases |
| **Smoke** | Startup, health, critical routes, class loading | Most valid combinations |
| **Core regression** | Unit, core integration, serialization, TLS/DB | All production-supported combinations |
| **Native/agent** | JNI/JNA, drivers, profilers, bytecode instrumentation | OS/CPU/JDK combinations using natives |
| **Full E2E** | Business workflows, migration scenarios, persistence | Production/reference environments |
| **Non-functional** | Startup, memory, GC, p95/p99, throughput | Representative/critical platforms |
| **Exploratory** | New JDK, vendor, OS, architecture | Non-release-blocking by default |

Assign profiles by **risk**, not uniform cosmetic spread. If Linux ARM64 is a production environment using JNI with strict latency targets, it requires core regression + native + appropriate non-functional testing even at higher cost.

### 14.1. Release-Blocking Rules

Example:

~~~text
Release blocked when:
  - any mandatory production matrix row has failed or not-run core tests
  - any mandatory native/agent validation has failed
  - API compatibility contract is broken
  - security-critical TLS/crypto tests fail
  - a mandatory platform has no trustworthy test evidence
  - severe unresolved performance or stability regression exceeds policy
~~~

Never treat “did not run” as a pass. If a mandatory cell is skipped due to a runner outage, its status must remain **blocked/unknown** per policy rather than flipping to green.

## 15. Risk-Based Selection and Pairwise Testing

When combination counts grow large, **pairwise testing** (covering every pair of dimension values) can catch interaction defects while cutting test count compared to a full Cartesian product.

Example dimensions:

~~~text
JDK: 17, 21
Vendor: Temurin, Corretto
OS: Linux, Windows, macOS
Arch: x64, arm64
~~~

Not every OS/arch/vendor yields a valid binary. Before running pairwise generation, **filter by constraints**. A constraint-unaware pairwise generator can emit impossible combinations.

### 15.1. When Pairwise Is Helpful

- Screening interactions such as JDK × vendor, vendor × OS, OS × arch.
- Selecting a representative smoke/integration subset.
- Broadening coverage across non-critical environments.
- Shortening PR feedback while keeping the full matrix for nightly/release runs.

### 15.2. When Pairwise Is Not Enough

- Every committed production combination must carry policy-compliant evidence.
- A native library may fail only on the triple JDK 21 × ARM64 × musl.
- TLS providers/FIPS depend simultaneously on vendor, OS, and policy.
- Multi-agent/bytecode instrumentation involves 3–4-way interactions.
- Security/compliance risks demand specific certification.

Combine them as follows:

1. **Mandatory full coverage** for production-critical combinations.
2. **Constraint-aware pairwise** for broader secondary support.
3. **Targeted high-order tests** for high-risk interactions.
4. **Exploratory tests** when new JDKs/OSes/vendors appear.

Do not use pairwise testing as a substitute for support responsibility.

## 16. Prioritizing by Risk and Impact

A straightforward prioritization model:

| Tier | Condition | Testing Strategy |
| --- | --- | --- |
| P0 | Running in production or regulatory/security mandate | Full release-blocking |
| P1 | Migration target, critical native/agent/TLS usage | Core + targeted deep tests |
| P2 | Supported non-critical consumer footprint | Smoke + contract + representative integration |
| P3 | Experimental/new platform | Exploratory and documentation |

A combination can be promoted to a higher tier based on evidence:

- Past production outages occurred on that architecture.
- Vendor shipped a JVM build with major changes.
- Base image swapped libc or certificate stores.
- A native dependency lacks a vendor support matrix.
- The project uses custom class loaders, JPMS, or `jlink`.
- Many external consumers exist or rollback is complex.

### 16.1. Do Not Prioritize by Popularity Alone

An environment representing just 5% of traffic yet handling high-accuracy payment rails may warrant P0. Conversely, a rarely used OS for an internal utility may only need smoke testing. Priority must reflect **impact × likelihood × detectability**, not user share alone.

## 17. Baseline, Target, and Root-Cause Isolation Tests

A JDK migration often alters multiple variables simultaneously: JDK, frameworks, images, libraries, and agents. Running only before/after states makes isolating the culprit difficult when regressions occur.

Control matrix:

| Case | JDK | Dependency Graph | Runtime Image | Purpose |
| --- | --- | --- | --- | --- |
| A | Old | Old | Old | Baseline |
| B | New | Old | Old-equivalent | Isolate JDK effect, if combination is valid |
| C | Old | New | Old-equivalent | Isolate library effect, if still compatible with old JDK |
| D | New | New | Old-equivalent | Evaluate JDK + dependencies |
| E | New | New | New target image | Verify final deployment |

**Not every cell is runnable.** For example, a newer framework requiring Java 21 makes case C invalid; mark it “unsupported combination” rather than forcing it to run.

If B fails while D passes, upgrading dependencies likely resolved a JDK blocker. If D passes while E fails, inspect OS image, libc, permissions, TLS certs, or native packaging instead of immediately blaming the JDK.

## 18. Build JDK, Compiler JDK, and Runtime JDK Must Be Recorded Separately

In modern Java builds you may have:

- JDK running the Maven/Gradle daemon.
- JDK compiler toolchain.
- `--release`/source/API target.
- Test JVM.
- Application/container JVM.

Example:

~~~text
Gradle daemon:      JDK 21
Compiler toolchain: JDK 21
javac --release:   17
JUnit on Java 17:  mandatory
JUnit on Java 21:  mandatory
Production floor:  Java 17
~~~

This setup is valid for a library continuing to support Java 17. Never conclude that running tests on Java 21 proves Java 17 compatibility merely because the compiler used `--release 17`.

### 18.1. What Does `--release` Control?

`javac --release N` constrains Java language syntax, Java platform APIs, and bytecode to release `N` supported by the compiler. It **does not inspect every third-party dependency** for matching class-file versions/minimum runtimes and does not replace runtime execution tests.

### 18.2. Toolchain Version Differs from Build Daemon Version

Whether a Gradle version can run itself on a new JDK is distinct from whether Gradle can invoke that JDK via toolchains for compilation/testing. In Maven too, toolchains differ from the JVM running Maven. Record both in the matrix to reproduce compiler plugin or processor bugs.

## 19. What Should a JVM Vendor Matrix Verify?

A vendor comparison suite should validate:

1. Startup, classpath/module path, and Java agent initialization.
2. Security providers, truststores, key/trust management, and TLS negotiation.
3. Reflection, strong encapsulation, and JVM flags used by the app.
4. Whether garbage collector/JIT options are supported by the runtime.
5. Thread scheduling and concurrency liveness/correctness.
6. Native JNI/JNA libraries and JVMTI agents if present.
7. Performance baselines on identical workloads/hardware.
8. Diagnostic tooling, crash handling, logs, and supportability.
9. `ServiceLoader` and provider discovery inside the runtime image.
10. Runtime packaging, CA certificates, and system properties.

### 19.1. Inspecting the JVM Implementation

Run:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Outputs typically contain:

~~~text
java.vendor
java.vendor.version
java.version
java.runtime.version
java.vm.name
java.vm.vendor
java.vm.version
os.name
os.arch
os.version
~~~

Store both the output and artifact provenance; a single property cannot fully authenticate the distribution binary/build.

### 19.2. Do Not Force One Implementation's JVM Flags onto Every Vendor

GC options, compiler flags, diagnostic flags, or native profiling support are not always identical across JVM implementations. If a startup flag set targets only HotSpot, you should:

- Restrict your support policy to that JVM implementation, or
- Provide runtime-selected configurations with matching verification.

Do not treat an “unrecognized VM option” warning as an application bug; it may reflect non-portable JVM flags.

## 20. OS and Architecture: Suites That Should Run

### 20.1. Filesystem and Processes

- Path separators, Unicode filenames, symlinks.
- Case sensitivity, file locking, and permission errors.
- Temporary directories and read-only filesystems.
- Child process creation, termination, stdout/stderr encoding.
- File watcher event behavior and quotas.

### 20.2. Networking and Security

- TLS handshakes/certificate validation against test endpoints.
- Proxies/DNS/IPv4/IPv6 if inside deployment scope.
- HTTP/2, keepalive, connection pools, and timeouts.
- Keystore/truststore initialization and algorithm availability.
- Clock/timezone/datetime representation.

### 20.3. Native Integration

- Confirming JNI/JNA binaries actually load.
- Native dependency search paths and `glibc`/`musl`.
- Compression/crypto libraries and epoll/kqueue/native transports.
- Signal handling and native profilers/agents.
- Off-heap buffer allocation/freeing and memory pressure.

### 20.4. Concurrency and Performance

- Long-running workloads on real CPU architectures.
- Thread pools, and virtual threads if used by the app.
- Atomic/volatile correctness under contention.
- Throughput, p95/p99 latency, GC, CPU steal/memory limits.

A “Java app prints Hello World” smoke test only proves the launcher executes; it will not uncover the differences above.

## 21. JDK Patch Updates and Security Regressions

A JDK update can change:

- TLS/protocol/cipher defaults.
- Certificate trust decisions.
- Security algorithm constraints.
- Timezone data or locale data.
- Provider implementations.
- Native/JIT/GC bug fixes.
- JVM warnings/options behavior.

You do not need to run the full matrix on every pull request solely to track patch updates. Yet **when deploying a JDK baseline patch update**, run a risk-appropriate suite—especially TLS, cryptography, serialized data, and agents/tooling.

### 21.1. Periodic Update Workflow

One workflow:

~~~text
New approved JDK update available
            |
            v
Create updated immutable runtime image
            |
            v
Run mandatory compatibility matrix
            |
            v
Compare functional + nonfunctional baseline
            |
            v
Canary / staged rollout
            |
            v
Promote or rollback with documented evidence
~~~

Never rely on the `latest` tag for CI and production without storing digests/builds. Two environments may execute completely different binaries under the same tag.

## 22. API/Binary Compatibility and Runtime Compatibility Are Two Separate Gates

For Java libraries, distinguish:

- **Source compatibility:** do consumers still compile against the public API?
- **Binary compatibility:** do precompiled consumers still link methods/fields/classes?
- **Java platform compatibility:** do class-file major versions and Java SE APIs fit the minimum runtime?
- **Behavioral compatibility:** do identical inputs and state yield valid outputs/behavior?
- **Data/protocol compatibility:** is data/HTTP/serialization across old and new versions handled cleanly?
- **Operational compatibility:** do monitoring, diagnostics, and resource budgets remain satisfied?

A class compiled with `--release 17` can execute on Java 21, yet a native dependency or agent can still fail. Conversely, a Java 17 runtime cannot load class-file major 65 even though the source compiled cleanly on Java 21.

### 22.1. Distinguishing Common Failures

| Error | Investigate First |
| --- | --- |
| `UnsupportedClassVersionError` | Compiler release target and JVM runtime |
| `NoSuchMethodError` | Dependency graph, ABI, and actual JAR |
| `InaccessibleObjectException` | Reflection/module access and tools/libraries |
| `UnsatisfiedLinkError` | Native binary, OS/CPU/ABI, `java.library.path` |
| `Unsupported class file major version` in ASM/agent | Bytecode parser/tool version |
| TLS handshake failure | Certificates, providers, protocols, policy, network |
| `OOMKilled` | Container limits, heap/direct/native memory, GC/agents |

**Do not diagnose a Java language-level failure** when the root cause is Alpine `musl` failing to load a native binary.

## 23. JNI, JNA, and Native Libraries Require Their Own Matrix When Used

If an application uses JNI/JNA, testing ARM64 differs fundamentally from testing pure Java code:

~~~text
JDK distribution
    × OS image
    × CPU architecture
    × libc / native ABI
    × JNI library version
~~~

Maintain a native artifact table:

| Artifact | OS | Arch | libc/ABI | Binary Source | Test |
| --- | --- | --- | --- | --- | --- |
| `libcodec.so` | Linux | amd64 | glibc | Vendor/build approved | Load + encode/decode |
| `libcodec.so` | Linux | arm64 | glibc | Vendor/build approved | Load + encode/decode |
| `nativecodec.dll` | Windows | x64 | Windows ABI | Vendor/build approved | Load + encode/decode |
| `libcodec.dylib` | macOS | arm64 | Mach-O | Vendor/build approved | Load + encode/decode |

Verify every row has an existing, valid binary. Never take an x64 `.so` library and rename it for arm64.

### 23.1. Tests Must Exercise Real Native Functionality

A library may load native code lazily. Unit tests constructing only DTOs/beans will pass without touching `System.loadLibrary`. For JNI, tests must execute actual native code paths, check outputs, handle error paths, and test memory/lifetimes under load.

### 23.2. Verify Java/Native Artifact Version Alignment

The Java wrapper and native library must match versions. A JNI method signature change can trigger `UnsatisfiedLinkError` even after the OS loader succeeds in opening the file. During JDK/image upgrades, ensure a new wrapper never loads a stale native binary due to caching or path precedence.

## 24. Java Agents, JVMTI, and Test Tooling Also Depend on Vendor/Architecture

Commonly overlooked tools:

- APM/tracing Java agents.
- Native JVMTI profilers.
- Coverage/mocking agents using test-time instrumentation.
- Class-file transformers built on ASM/Byte Buddy.
- Debuggers, attach tools, and JFR integration.

On JDK 21+, dynamic agent loading carries warning policies under JEP 451; on other releases check current JVM policy. An agent running at startup via `-javaagent` does not imply dynamic attach is allowed in every container.

### 24.1. Do Not Treat Lost Tracing as a Test Pass

After a JDK/vendor/image migration, an app might return HTTP 200 while:

- Missing JDBC spans.
- Breaking context propagation across async threads.
- Crashing or adding severe overhead while profiling.
- Shipping an agent supporting only x64, not ARM64.
- Changing metric names, breaking dashboards/alerts.

Where observability is an operational requirement, add dedicated checks for these failures.

## 25. TLS, Cryptography, and Compliance Require Mandatory Cells

In payment, identity, or cryptographic systems, each JDK/vendor/OS combination can differ in truststores, providers, HSM/PKCS#11 setups, security policies, or FIPS configurations.

Testing should cover:

1. TLS handshakes using approved certificates/cipher suites.
2. Client/server certificate validation and mTLS.
3. Truststore/keystore formats and password handling.
4. Key generation/signing/verification with real providers.
5. Certificate chains and revocation checks when required.
6. PKCS#11/HSM native providers or FIPS mode if mandatory.
7. Expired/invalid certificates and negative tests.
8. Correctness of signed/encrypted payloads across JDK versions.

Never pass `-Djdk.tls.client.protocols=...` or disable certificate verification just to “make tests pass” without formal security analysis. Weakening security guarantees outweighs the migration goal.

### 25.1. Separate “Algorithm Exists” from “Permitted for Use”

A JDK distribution may bundle an algorithm while application/OS security policy disables or restricts it. Tests must validate the **actual operational contract**, not just whether `Security.getProviders()` lists a provider name.

## 26. Tests for Localization, Timezones, and Data

Impacts invisible at compile time:

- Locale/collation, Unicode normalization, case folding.
- Timezone databases and DST transitions.
- Default charsets when code omits explicit encodings.
- Number, currency, and date/time parsing/formatting.
- Java serialization and JSON/XML/protobuf compatibility.
- Filesystem path encodings.
- Database timestamp/timezone mappings.

### 26.1. Do Not Rely Unintentionally on Environment Defaults

Code like:

~~~java
new String(bytes)
~~~

depends on the default charset. On many modern systems UTF-8 is the default on newer Java platforms, yet compatibility with older JDKs/other OSes still needs attention. When the contract mandates UTF-8, specify it explicitly:

~~~java
new String(bytes, java.nio.charset.StandardCharsets.UTF_8)
~~~

Similarly, when business logic requires UTC, configure or reference timezones explicitly rather than assuming the host OS is always configured accordingly.

### 26.2. Golden Data Fixtures

For serialization and protocols, generate fixtures from released builds:

- Old-JDK writer, new-JDK reader.
- New-JDK writer, old-JDK reader if rolling deployments/rollbacks require it.
- Inputs containing `null`, missing fields, unknown enums, large payloads, Unicode characters, and DST dates.

Do not generate both “v1” and “v2” fixtures using the same new implementation and assume backward compatibility was tested.

## 27. Concurrency and Performance Can Vary by JVM and CPU

Upgrading the JDK or switching architecture can expose rare race conditions:

- Lock contention and thread scheduling.
- Parallel streams and fork-join behavior under load.
- Garbage collection pauses/throughput.
- Memory fences/atomic operations in native integrations.
- Virtual threads if the application runs on a supporting JDK.
- Connection pools, executor saturation, and backpressure.
- CPU vector instructions and cryptographic intrinsics.

### 27.1. Performance Baselines Require Identical Conditions

When comparing JDK 17 against JDK 21:

- Identical application workload and input distribution.
- Identical hardware/instance class where possible.
- Recorded CPU/memory limits, JVM flags, and agent settings.
- Consistent warmup/JIT and cache state methodology.
- Sufficient repetitions and variance analysis for each run.
- Observe latency percentiles, throughput, CPU, memory, GC, and error rate.

Never declare “the new JDK is 20% faster” from an uncontrolled run, especially when switching `x86_64` to ARM64 or altering container images simultaneously.

### 27.2. Regression Thresholds Must Be Based on SLOs

Illustrative policy:

~~~text
P0: business correctness is mandatory
P0: no new crash/OOM under reference workload
P1: p99 latency must stay within approved SLO
P1: native memory overhead monitored against budget
P2: startup time trend reviewed and recorded
~~~

Actual thresholds must be agreed upon by product and SRE/QA, not picked as arbitrary percentages across every service.

## 28. Designing a CI Matrix: Structure First, Syntax Second

Maintain a repository-managed **matrix definition** as the source of truth:

~~~yaml
matrix:
  - id: linux-amd64-jdk17-baseline
    jdk: "17"
    vendor: temurin
    os: linux
    arch: amd64
    profile: full
    support: baseline

  - id: linux-amd64-jdk21-target
    jdk: "21"
    vendor: temurin
    os: linux
    arch: amd64
    profile: full
    support: target

  - id: linux-arm64-jdk21-target
    jdk: "21"
    vendor: temurin
    os: linux
    arch: arm64
    profile: native-integration
    support: candidate
~~~

This data is illustrative, not mandatory syntax for any CI provider. Vendor/image/build values must be validated against approved distributions.

**Governance rule:** changing the support policy requires code-review rigor. Never delete a failing row from the matrix merely to turn the pipeline green.

## 29. GitHub Actions Example for a Representative CI Subset

This example uses runner labels and JDK distributions that the project must confirm are available at implementation time. It illustrates the CI matrix mechanism rather than claiming full architectural coverage:

~~~yaml
name: Java compatibility

on:
  push:
  pull_request:

jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-22.04
            distribution: temurin
            java: "17"
          - os: ubuntu-22.04
            distribution: temurin
            java: "21"
          - os: windows-2022
            distribution: temurin
            java: "21"
          - os: macos-14
            distribution: temurin
            java: "21"

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: ${{ matrix.distribution }}
          java-version: ${{ matrix.java }}
      - name: Record JDK
        run: java -version
      - name: Run regression tests
        run: ./mvnw -B verify
~~~

**Platform note:** `./mvnw` may not run identically on Windows runners depending on wrapper files/shells; a multi-OS workflow requires appropriate per-runner commands, such as `mvnw.cmd` on Windows or a portable script. The example illustrates the matrix concept and does not replace verifying exact syntax and runner support in a real repository.

### 29.1. Genuine Architecture Must Be Proven

The runner list above is **not** ARM64 coverage. Testing Linux ARM64 requires real ARM64 runners/hosts or properly guaranteed platforms, such as managed and clearly labeled self-hosted runners.

Never add `arch: arm64` to a matrix while still executing the job on an x64 host and stamping “ARM64 PASS”. A parameter does not change the underlying CPU architecture.

### 29.2. GitHub Actions Artifact Provenance

Beyond job status, preserve:

- `java -version` and JVM properties.
- Container digest/OS/architecture evidence.
- Maven/Gradle versions and dependency graphs where needed.
- Test reports and logs.
- Artifact checksums and commit SHAs.

Mutable runner labels like `ubuntu-latest` can change OS releases over time; for release-blocking validation, pin runner/image versions or capture complete OS build details.

## 30. Platform-Independent CI Pattern Across Multiple Providers

On other CI providers, the core pattern stays the same:

~~~text
load approved-matrix.yml
for each row:
    verify runner provides real OS + CPU architecture
    provision approved JDK vendor/full build
    verify JDK/runtime image and artifact checksum
    run test profile for this row
    collect logs, reports and environment metadata
    apply gating policy
aggregate mandatory row results
publish compatibility evidence
~~~

In particular, never skip **verify runner provides real OS + architecture**. If CI transparently falls back to QEMU/emulation, that is a distinct testing condition and must be explicitly recorded.

### 30.1. Fail-Fast and Investigation

In matrix runs, disabling fail-fast collects all results in a single pass. Yet that does not mean failures can be ignored. At the end of the pipeline, summarize:

~~~text
P0 required:  PASS / FAIL / NOT_RUN
P1 targeted:  PASS / FAIL / NOT_RUN
P2 exploratory: PASS / FAIL / NOT_RUN
release decision: PASS only if policy requirements satisfied
~~~

Any row skipped due to runner unavailability must retain a transparent status.

## 31. Maven Toolchains and Gradle Java Toolchains in the Matrix

### 31.1. Maven

Maven Toolchains can assign a JDK to the compiler or toolchain-aware plugins while Maven itself runs on another JDK. This helps compile multiple Java release targets, yet does not automatically ensure forked JUnit tests run on the intended JDK.

When building a test matrix, verify:

~~~bash
mvn -version
./mvnw -version
~~~

Use the command matching your repository, and log compiler and test-fork JVM versions explicitly.

### 31.2. Gradle

Example using a Java 21 toolchain with release 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This builds an artifact keeping the Java 17 target. To **execute tests on both Java 17 and 21**, configure `Test.javaLauncher`/test tasks or CI jobs accordingly; a compiler toolchain alone does not create a runtime test matrix.

### 31.3. Never Use the IDE SDK as Evidence

An IDE may use JDK 21 for code insights while terminals/CI run another JVM. Capture build daemon, compiler, and test JVM versions directly from the execution runtime rather than reading the IDE Project SDK screen.

## 32. Testing on Real JVMs and Final Images: Verification Principles

A “Java 21 pass” report should include:

~~~text
Artifact source commit:
Artifact SHA-256:
JDK distribution:
java.version:
java.runtime.version:
java.vm.name:
OS name/version:
Architecture:
Container image digest:
JVM arguments:
Test suite/profile:
Test count/passed/failed/skipped:
CI run ID:
Timestamp:
Owner:
~~~

### 32.1. Skipped Tests Must Never Be Hidden

A test report showing 1,000 cases with 900 passed and 100 skipped is not equivalent to “1,000 tests pass”. If skipped cases cover JNI ARM64 or TLS security checks, that may represent a release-blocking coverage gap.

Record a **reason code** for every skip:

- Feature outside platform scope.
- Approved waiver in place.
- Dependency/vendor binary unavailable.
- Runner or external service unavailable.
- Flaky/quarantined with owner and remediation deadline.

Never count skipped tests as support evidence.

## 33. Small Java Utility to Record Environment Fingerprints

A diagnostic helper can run prior to the suite:

~~~java
import java.util.List;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        List<String> keys = List.of(
                "java.version",
                "java.runtime.version",
                "java.vendor",
                "java.vm.name",
                "java.vm.vendor",
                "java.vm.version",
                "os.name",
                "os.version",
                "os.arch");

        for (String key : keys) {
            System.out.println(
                    key + "=" + System.getProperty(key));
        }
    }
}
~~~

This snippet uses `List.of`, requiring Java 9+; if your baseline floor is Java 8, replace it with `Arrays.asList` or a string array. Diagnostic helpers must not accidentally demand a higher JDK than the runtime under test.

Beyond Java properties, collect the OS distribution, container image digest, and platform architecture using appropriate infrastructure tools. `System.getProperty("os.arch")` alone cannot detect emulation or the architecture of loaded native binaries.

### 33.1. Avoid Printing Secrets

`java -XshowSettings` and JVM arguments/logs can contain sensitive configuration. When collecting CI fingerprints, pick only required fields and redact tokens/passwords. Never upload raw environment variables or core dumps to public artifacts.

## 34. Test Stability: Flakiness vs. Incompatibility

Running a matrix across multiple OSes/CPUs/JVMs shifts timing and scheduling, exposing tests dependent on timing.

Example anti-pattern:

~~~java
Thread.sleep(100);
assertTrue(asyncResult.isCompleted());
~~~

This test might pass on a fast x64 machine yet fail on a heavily loaded ARM64 runner; it does not prove a JDK/architecture bug. Replace fixed sleeps with synchronization/signaling with appropriate timeouts, then verify the business invariant.

### 34.1. Flaky Tests Must Be Managed

- Track failure rates per matrix row.
- Preserve logs and timing metrics.
- Re-run per policy for classification without deleting initial failure records.
- Find the root cause: race condition, environment, resource pressure, or JVM bug.
- Assign an owner and quarantine deadline if permitted.
- Never silently disable high-failure-rate tests without an explicit decision.

A test failing consistently only on ARM64 is an investigation signal, not something to label “flaky ARM” and ignore.

## 35. Managing Test Environments and External Data

CI matrices often require databases, message brokers, HTTP dependencies, and secrets. These components also carry versions that affect outcomes.

Best practices:

- Use pinned versions/images for test infrastructure.
- Isolate database/protocol compatibility issues from JDK defects when possible.
- Reset data between cases and between jobs.
- Avoid pointing multiple concurrent matrix rows at an unisolated shared database.
- Record network/proxy/certificate behavior.
- Set timezone/locale explicitly in tests requiring determinism.
- Record schema versions/migrations and migration state.
- Minimize unstable external dependencies in release gates.

### 35.1. Rolling Deployments Require Cross-Version Tests

When new Java 21 services and old Java 17 services coexist, the JDK itself does not guarantee identical wire formats; frameworks, JSON/XML/protobuf serializers, TLS, and code may change concurrently.

Testing should cover:

~~~text
Old producer -> New consumer
New producer -> Old consumer (if rollback/rolling requires)
Old client   -> New server
New client   -> Old server (if supported)
~~~

Do not assume a JDK upgrade preserves wire contracts if schemas, frameworks, or serialization also changed in the same release.

## 36. Structuring Layer-by-Layer Summary Reports

A minimal report:

| Matrix row | Compile/API | Smoke | Core regression | Native/agent | E2E | Perf | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Linux x64 / JDK17 / vendor A | PASS | PASS | PASS | PASS | PASS | Baseline | Baseline |
| Linux x64 / JDK21 / vendor A | PASS | PASS | PASS | PASS | PASS | Within SLO | Supported |
| Linux arm64 / JDK21 / vendor A | PASS | PASS | PASS | FAIL | NOT_RUN | N/A | BLOCKED |
| Linux musl / JDK21 / vendor A | PASS | PASS | NOT_RUN | FAIL | NOT_RUN | N/A | Experimental |

All statuses above are illustrative. A real report must link to CI runs, JDK builds, image digests, and fail/skip reasons.

### 36.1. Meaning of Result States

- **PASS:** the suite completed per profile with zero policy-violating failures.
- **FAIL:** test failures or gate failures occurred.
- **NOT_RUN:** did not execute or blocked by infrastructure.
- **N/A:** intentionally inapplicable with documented reason.
- **WAIVED:** explicit exception granted with owner and expiration date.

Never collapse NOT_RUN, N/A, and WAIVED into PASS.

## 37. Investigation Example: Java 21 ARM64 Hits `UnsatisfiedLinkError`

Scenario:

~~~text
Java 21 Linux AMD64: PASS
Java 21 Linux ARM64: FAIL
java.lang.UnsatisfiedLinkError: no codecnative in java.library.path
~~~

Investigation path:

1. Verify the runner is genuinely ARM64, not merely mislabeled in CI.
2. Check JDK distribution, container image digest, and `os.arch`.
3. Inspect which native classifier the Java wrapper selects.
4. Confirm the ARM64 `.so` exists inside the artifact/image.
5. Check ELF architecture and `libc` dependencies.
6. Inspect `java.library.path` and OS dynamic linker paths.
7. If a JNI symbol fails to resolve, compare Java/native versions and symbols.
8. Run native integration tests inside the actual image.

If the failure occurs solely on ARM64, do not tweak source compatibility or scatter `--add-opens` flags: they do not conjure an ARM64 binary.

### 37.1. Release Decision

If ARM64 is a P0 supported target, the release is blocked until fixed or scope is formally changed. If ARM64 is only exploratory, still log the failure and remediation plan before claiming support.

## 38. Investigation Example: Switching JDK Vendors Breaks TLS

Scenario:

~~~text
JDK 21 vendor A / Linux x64: PASS
JDK 21 vendor B / Linux x64: TLS handshake FAIL
Application JAR, code, service endpoint identical
~~~

Questions:

- Are security providers and truststores identical?
- Where do Java security properties/cipher/algorithm constraints differ?
- Do CA certificates or OS trust stores differ?
- Are mutual TLS cert chains and alias selection correct?
- Is a FIPS/PKCS#11/native provider involved?
- Do container images share identical base packages?
- Do JVM flags or proxy settings differ?

Matching the JDK feature release does not eliminate distribution packaging or security configuration differences. Never disable certificate validation as a “fix”. Instead, configure truststores/providers per security policy and re-test.

## 39. Investigation Example: CI Green Yet Production Java 21 Fails

Scenario:

~~~text
CI: Ubuntu hosted runner + full JDK 21, tests pass
Production: minimal jlink image + agents, startup fails
~~~

Possible causes:

- The `jlink` image lacks a module or service provider needed by the app.
- Production injects an agent/JVMTI absent from CI.
- Different JDK distribution or update build.
- Different OS/native libraries/certificates.
- Different runtime flags, permissions, or container limits.

Steps:

1. Compare CI and production fingerprints.
2. Check image digest and `java -version`.
3. List modules and service providers inside the `jlink` image.
4. Inspect startup JVM arguments, agent JARs, and permissions.
5. Run smoke/integration tests on the **production-like final image**.
6. Fix image/modules/agents at the root cause and re-run gates.

**Takeaway:** a matrix is only valuable when each row represents an environment genuinely claimed as supported, rather than an approximate runner.

## 40. Investigation Example: ARM64 Is Slower Than x64

Scenario:

~~~text
Java 21 x64:  p99 within SLO
Java 21 ARM:  p99 exceeds SLO
No functional test failures
~~~

Do not conclude one CPU architecture is inferior from this result alone. Check:

- Instance SKUs, CPU quotas, and noisy neighbors.
- JVM flags/GC, vendor build, and CPU features.
- JIT warmup and compilation behavior.
- Whether native crypto/compression libraries are tuned for ARM.
- Network/storage throughput.
- Profiling/telemetry overhead.
- Thread pools and contention.
- Whether workloads and datasets actually matched.

If a regression persists under fair conditions, optimize, constrain deployment, or document a performance support policy for that platform.

## 41. From Matrix to Rollout: Do Not Stop at CI

Once release gates pass, production migration still needs verification:

1. Deploy a canary matching the exact JDK vendor/build/OS/image/arch.
2. Monitor functional errors, latency, memory, CPU, GC, and traces.
3. Compare against baseline under comparable traffic.
4. Increase traffic/replicas in stages per policy.
5. Keep a realistic rollback/roll-forward plan ready.
6. Verify logging, metrics, traces, and alerts.
7. Record every hotfix and JDK patch deployed.

### 41.1. Rollback Is More Than Reverting a Docker Image

If a migration modifies database schemas, serialization, message payloads, authentication, or public APIs, older consumers may fail to read newly written data. Test **cross-version compatibility** and set clear rollback limits.

### 41.2. Keep Maintaining the Matrix After Rollout

Any of the following changes warrants re-running the matrix:

- JDK security updates.
- OS base image or kernel/container runtime upgrades.
- Adding ARM64 nodes.
- Switching JDK vendors.
- JDBC/native library/agent upgrades.
- Major framework or bytecode generator upgrades.
- Security policy or truststore changes.

That is why the matrix belongs inside the repository and release workflow rather than in a one-off spreadsheet that gets forgotten.

## 42. Common Mistakes

**“Testing Java 21 is enough.”** Not if the product supports multiple vendors, OSes, CPUs, or runtime images.

**“Java bytecode is portable, so JNI is portable too.”** False. Native binaries depend on OS/architecture/libc and ABI.

**“Another vendor is just a different logo.”** Do not assume that. Distribution builds, JVM implementations, security providers, and support policies matter.

**“Linux is a single uniform environment.”** False regarding `glibc`/`musl`, OS images, kernels, and native libraries.

**“Setting `arch=arm64` in CI means we tested ARM64.”** False if the real runner stays x64 or runs unacknowledged emulation.

**“`--release 17` proves Java 17 runtime passes.”** False. You must run the artifact on real Java 17 with matching dependencies.

**“CI passed on a full JDK, so the `jlink` image passes too.”** False if the image misses modules/providers or uses different agents.

**“Pairwise covers all production combinations.”** False for mandatory support cases and high-order native/security interactions.

**“No runner available, so mark it N/A.”** False if the product contract still promises that combination.

**“A skipped test counts as a pass.”** False. Every skipped/waived test needs a reason and policy tracking.

**“The app returned HTTP 200, so the entire migration passed.”** False if observability, TLS/crypto, persistence, or performance broke contracts.

**“Changing base images does not affect JDK migration.”** False: `libc`, certificates, native libraries, and filesystem semantics can all change.

**“All LTS releases have identical support.”** False: vendor lifecycles, licenses, and update policies vary.

**“Testing with the `latest` tag is still reproducible.”** Doubtful; pin full JDK builds and immutable image digests.

**“Flaky ARM64 failures do not need investigation.”** False; they may signal real concurrency bugs or resource regressions.

**“A green grid is enough without evidence.”** False: capture test suites, runtime fingerprints, artifact hashes, logs, and test dates.

## 43. Checklist When Approving a JDK Migration Matrix

- [ ] Defined current baseline, target support, and experimental scope.
- [ ] Assigned support policy owners and review cadence.
- [ ] Recorded JDK feature, full update/build, distribution, and JVM implementation for every cell.
- [ ] Recorded OS release/image, libc where relevant, and real CPU architecture for every cell.
- [ ] Verified vendors publish matching binaries for the OS/architecture.
- [ ] Verified product support (not just vendor support) for each combination.
- [ ] Ensured no unsupported combinations are reported as passes.
- [ ] Recorded compiler JDK, `--release`, test JVM, and runtime JVM separately where needed.
- [ ] Pinned application artifact checksums and runtime image digests.
- [ ] Confirmed CI runners actually run on the declared CPU architecture.
- [ ] Defined mandatory vs. optional test profiles per row.
- [ ] Covered all production-supported rows with core regression and smoke tests.
- [ ] Verified JNI/JNA/native library binaries and integration tests per OS/arch.
- [ ] Checked Java agents, JVMTI, bytecode parsers, and coverage tools.
- [ ] Ran policy-compliant TLS/crypto/security-provider tests where relevant.
- [ ] Verified cross-version serialization/data/protocol compatibility if rolling/rollback requires it.
- [ ] Executed performance/GC/memory tests on critical platforms.
- [ ] Distinguished PASS/FAIL/NOT_RUN/SKIPPED/WAIVED/N/A in test reports.
- [ ] Confirmed no mandatory rows lack evidence due to runner outages.
- [ ] Saved runtime fingerprints, test counts, logs, commit SHAs, and timestamps.
- [ ] Secured logs/core dumps/arguments and redacted secrets.
- [ ] Defined processes for JDK patches, vendor changes, and OS image changes.
- [ ] Prepared canary, monitoring, and rollback/roll-forward plans.
- [ ] Accurately documented the support matrix and constraints in release notes.

## 44. Template Record for Supporting a Combination

~~~text
Matrix ID: COMPAT-JDK-021
Application / release: orders-service / candidate-build
Purpose: target production
JDK feature: 21
JDK full version/build: verified at execution
Distribution: approved JDK vendor
JVM implementation: recorded from runtime
OS image/version: immutable image digest
Architecture: linux/arm64, native
libc: recorded
Java artifact SHA256: recorded
JNI/JNA dependencies: approved ARM64 variants
Java agent: approved agent version
Compiler target: --release 17 or approved product floor
Test profile: smoke + core + native + TLS + E2E
Performance criteria: approved product SLO
Support status: candidate until validated
CI run / evidence: link or artifact identifier
Owner: runtime-platform + service team
Decision: PASS / FAIL / BLOCKED / WAIVED
Expiry / next review: next JDK/image update cycle
~~~

Do not leave `verified at execution` standing in for actual versions in a final report: it is only a placeholder in the template. Every release must record the real JDK build, image digest, and artifact for traceability.

## 45. References to Consult When Building the Matrix

Because support matrices, JDK release policies, and runner catalogs change over time, consult official **version-accurate** documentation:

- **OpenJDK/JDK release notes:** API changes, JVM flags, security, and known issues.
- **Per-distribution JDK platform support docs:** supported OSes, CPU architectures, JVM variants, and lifecycles.
- **Java SE Specification / Java Virtual Machine Specification:** language, bytecode, and class-loading compatibility.
- **`javac` Tool Guide:** `--release` and platform API bounds.
- **Gradle Java Compatibility Matrix / Toolchains:** Gradle daemon JVM vs. compiler/test toolchains.
- **Maven Compiler/Toolchains/Surefire/Failsafe documentation:** compiler JDKs, release targets, and test JVM forks.
- **CI runner provider documentation:** runner labels, architectures, images, and lifecycles.
- **Container runtime / multi-platform Docker docs:** architecture selection and immutable image references.
- **OS native loader / JNI / JVMTI documentation:** native architectures/ABIs and agent compatibility.
- **Vendor APM/JDBC/HTTP/framework support matrices:** dependency and instrumentation support on the target JDK.
- **Security/TLS/provider docs:** certificates, algorithm constraints, and FIPS/PKCS#11 where applicable.

Never hardcode a blanket claim such as “vendor X supports every JDK on every OS” in test plans. Verify the **specific distribution release** when drafting and updating the matrix.

## 46. Conclusion

Building a matrix of JDKs, vendors, operating systems, and architectures is an essential pillar of **regression testing in Java Advance Compatibility Migration**. Identical Java release numbers can still behave differently when JDK vendor/build, JVM implementation, OS image, `libc`, CPU architecture, native dependencies, or agents change.

A meaningful matrix begins with the **product support policy**, filters to valid combinations, tiers testing depth by risk, and verifies each cell using **real runtimes and artifacts** rather than source-level compatibility alone. Production environments require clear release gates; pairwise and exploratory testing expand coverage without replacing the obligation to test committed combinations.

Finally, record the full JDK build, distribution, OS/CPU, container digest, artifact hash, test profile, and outcomes. The matrix must not stop at CI reports: it must tie into canary rollouts, observability, rollback plans, and ongoing JDK security update workflows. That turns the claim **“this application supports Java on these platforms”** into a backed, owned, and reproducible engineering contract.
