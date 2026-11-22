# Differences That Only Occur in CI or Containers

During **Java Advance Compatibility Migration**, a very common situation is that the same commit runs fine on a laptop yet fails in CI, Docker, or Kubernetes. For example, unit tests pass in the IDE but fail under Maven Surefire; the application starts with `java -jar` on the host, but the container reports a missing class; an HTTPS request works on a personal machine but throws `SSLHandshakeException` in the new image; or the new JDK uses less heap, yet the pod gets `OOMKilled`.

You cannot conclude “the new JDK is buggy” just because an issue appears after upgrading the JDK. A Java environment consists of many components: **JDK launcher, compiler, and test fork; framework/dependencies; OS and CPU architecture; base image and native libraries; CPU/memory/PID limits; filesystem; locale/timezone/charset; DNS/proxy/CA/truststore; secrets/config; and parallel test execution schedule**. A change at any layer can cause local and CI results to differ.

The lesson **Differences That Only Occur in CI or Containers**, part of the **Troubleshooting** chapter, presents a systematic method to identify the cause: categorizing failures by stage, collecting the fingerprint of the actual process, comparing local–CI–container conditions, performing controlled reproduction, fixing at the right layer, and adding regression tests. The goal is not “making CI green at all costs,” but having sufficient evidence that the system is compatible and safe on the new Java runtime.

## 1. Understanding “local pass, CI fail” Correctly

“Local pass” can actually mean one of several very different outcomes:
- The IDE runs tests with JDK 21, while CI runs JDK 17.
- The developer uses dependencies stored in the Maven/Gradle cache.
- Local runs the `dev` profile, while CI uses `test` and Kubernetes uses `prod`.
- The laptop has a local database or proxy; CI does not.
- Local is macOS/Windows with a case-insensitive filesystem; CI is Linux.
- Local runs a single test in isolation; CI runs multiple test forks concurrently.
- Local has abundant CPU/RAM; the container is allocated only 1 vCPU and 768 MiB of RAM.
- Local has an internal CA certificate, whereas the Java truststore in the image does not.
- Local is x86_64; the deployment node is arm64 with a different native binary.

Therefore, replace the question “why is CI wrong?” with:

> Given the same artifact and the same data, **what conditions differ between the succeeding process and the failing process**?

### 1.1. Classify the Failure Point Before Investigating

| Stage | Symptoms | Priority Layer to Check |
|---|---|---|
| Dependency resolve | 401/403, artifact not found, timeout | Repository, proxy, credentials, cache |
| Compilation | Invalid target release, missing API | Compiler JDK, `--release`, plugin, classpath |
| Test discovery | 0 tests executed, test engine missing | JUnit/Surefire/Gradle runner |
| Test execution | Flaky assertion, thread timeout | Concurrency, clock, data, resources |
| Image build | Package install, platform error | Dockerfile, base image, architecture |
| JVM startup | Unsupported option, class version | Java launcher, VM flags, bytecode |
| Application startup | Bean creation, SSL/JDBC errors | Config, secrets, dependency, network |
| Runtime | OOMKilled, 503, DNS/HTTP failures | Cgroups, networking, downstream |
| Performance | CI slow, increased p99 | CPU throttling, GC, load differences |
| Shutdown | Pod killed, duplicate jobs | PID 1, SIGTERM, checkpoint, lifecycle |

You must capture the **root-cause stack trace and failure stage**. The final line “BUILD FAILED” does not provide enough data to choose a solution.

## 2. Building a Local–CI–Container Difference Matrix

An illustrative table:

| Component | Local | CI runner | Container/K8s |
|---|---|---|---|
| Shell JDK | JDK 21 | JDK 17? | May not have a shell |
| Compiler JDK | Toolchain 17 | Toolchain 17? | Pre-compiled artifact |
| Test JVM | IDE JDK 21 | Surefire JDK 17? | Custom test image? |
| OS/architecture | Windows x64 | Linux x64 | Linux arm64? |
| CPU | Many cores | Shared runner | 1 core quota |
| RAM | 16 GiB | 4 GiB | 768 MiB limit |
| Timezone | Local timezone | UTC | UTC or configured |
| Charset | Per JDK/OS | UTF-8? | UTF-8? |
| Filesystem | Case-insensitive | Case-sensitive | Potentially read-only |
| Certificates | Corporate CA | Runner CA | Image's JDK truststore |
| Network | Local proxy/VPN | CI egress | DNS/service mesh/NetworkPolicy |
| Config | IDE or .env | CI variables | ConfigMap/Secret |
| Concurrency | Tests run individually | Parallel forks | Replicas/worker pools |

Question marks mean **need to measure**, do not fill them in from memory. The table also needs the commit SHA, artifact checksum, Docker image digest, and timestamps to avoid comparing two runs with different code.

### 2.1. Three Sources of Divergence to Separate

1. **Different artifact**: different commit, dependency graph, build cache, compiler, or generated code.
2. **Different runtime**: different Java vendor/build, VM arguments, OS/architecture, native libraries.
3. **Different environment**: different quotas, files, network, certificates, secrets, timezone, or traffic.

If you change the JDK, framework, and Docker base image at the same time, the result is a **migration bundle**. There is not yet a basis to attribute every failure solely to the JDK.

## 3. Collecting the Fingerprint of the Exact Process

On the appropriate machine:

~~~bash
java -version
which java
uname -a
uname -m
id
pwd
~~~

These commands are useful but have limitations. `java -version` from the CI shell only reflects the executable that **the shell invokes**, and does not by itself prove that the Maven test fork or the JVM in a Kubernetes pod uses that exact Java.

### 3.1. A Minimal Java Probe

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        show("java.version", System.getProperty("java.version"));
        show("java.runtime.version",
                System.getProperty("java.runtime.version"));
        show("java.vendor", System.getProperty("java.vendor"));
        show("java.home", System.getProperty("java.home"));
        show("os.name", System.getProperty("os.name"));
        show("os.arch", System.getProperty("os.arch"));
        show("user.dir", System.getProperty("user.dir"));
        show("file.encoding", System.getProperty("file.encoding"));
        show("charset", Charset.defaultCharset().name());
        show("timezone", ZoneId.systemDefault().getId());
        show("locale", Locale.getDefault().toLanguageTag());
        show("processors",
                Runtime.getRuntime().availableProcessors());
        show("maxHeapBytes", Runtime.getRuntime().maxMemory());
        show("pid", ProcessHandle.current().pid());
    }

    private static void show(String key, Object value) {
        System.out.println(key + "=" + value);
    }
}
~~~

This snippet uses `ProcessHandle` (Java 9+) and requires no external libraries. When you want to inspect the **test JVM**, run the probe in the same test fork; when you want to inspect the **app container**, run the probe in the runtime image or log an allowlisted set of corresponding information from the application.

Do not dump all of `System.getenv()`, `System.getProperties()`, or JVM input arguments to public CI logs: they can contain tokens, passwords, internal hosts, keys, or sensitive configuration data. Print only **allowlisted non-secret keys**, with redaction if needed.

### 3.2. Reproducible Run Manifest

~~~yaml
runId: "ci-java-migration-001"
commit: "REPLACE_WITH_COMMIT_SHA"
artifactSha256: "REPLACE_WITH_HASH"
imageDigest: "REPLACE_WITH_IMAGE_DIGEST"
jdk:
  vendor: "REPLACE_WITH_VENDOR"
  runtimeVersion: "REPLACE_WITH_BUILD"
buildTool: "REPLACE_WITH_GRADLE_OR_MAVEN_VERSION"
osArchitecture: "linux-amd64"
profile: "test"
resourceLimits:
  cpu: "1"
  memory: "768Mi"
failingStage: "integration-test"
traceReference: "REPLACE_WITH_SAFE_LOG_LINK"
~~~

This is a metadata template, not a file belonging to a specific default tool. Hashes/versions must be taken from real artifacts; do not leave placeholders when drawing conclusions.

## 4. There Can Be Multiple JVMs in One Pipeline

Diagram:

~~~text
CI runner
   |
   +-- Maven or Gradle launcher JVM
   |
   +-- Compiler JDK / toolchain
   |
   +-- Unit test JVM fork
   |
   +-- Integration test JVM fork
   |
   +-- Docker application JVM
~~~

Each process can use a different Java. A single `JAVA_HOME` property on the runner is not sufficient proof when Gradle toolchains, Maven Toolchains, container images, or IDE configs select their own runtimes.

### 4.1. Symptoms of the Wrong Java Version

- `UnsupportedClassVersionError`: the runtime is loading a class file newer than what it supports.
- `invalid target release` or `release version ... not supported`: the compiler does not recognize the target release.
- `Unrecognized VM option`: the VM flag does not exist on the running JVM.
- `ClassNotFoundException`/`NoClassDefFoundError`: missing runtime class or API/module.
- `NoSuchMethodError`: binary linkage mismatch, which may be caused by a dependency version rather than necessarily the JDK.
- Test passes in IDE but fails in CI when mocking/final classes: the test VM or Mockito/Byte Buddy may differ.

### 4.2. Checking Class-File Version

~~~bash
javap -verbose -classpath target/classes com.example.Main
~~~

Some milestones:

| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

`--release 17` limits the source/API/class-file target for code processed by the compiler, but does not automatically guarantee that every runtime dependency is also Java 17-compatible. A transitive library built with class-file 65 can cause errors when running on JVM 17.

### 4.3. Gradle: Daemon, Compiler, and Test Launcher

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew test --info
~~~

Items to cross-check:
- The JDK running the daemon.
- `JavaCompile.javaCompiler`.
- `Test.javaLauncher` and `Test.jvmArgs`.
- Custom `integrationTest` tasks/test suites.
- IDE test runner if it bypasses Gradle.
- Plugin and wrapper versions.

A CI-only failure may occur because CI uses a Java 17 test launcher while the developer runs tests using IDE JDK 21, even though the build script has toolchain compile 17.

### 4.4. Maven: Launcher, Compiler, and Surefire

~~~bash
./mvnw -version
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Inspect the compiler plugin `release`/`source`/`target`, Maven Toolchains, Surefire/Failsafe fork configuration, `argLine`, active profiles, and the effective dependency graph.

`-Dmaven.compiler.release=17` does not automatically change the JDK running Maven or the Surefire fork. When upgrading the JDK, do not just update the compiler target and assume all JVMs in the pipeline have switched.

## 5. Build Image Is Not the Runtime Image

A multi-stage Docker build can use a **full JDK** to build and then a **minimal JRE/jlink/runtime image** to run the app:

~~~dockerfile
# Illustrative example; in production, pin the image digest.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The sample Dockerfile needs adjustments for artifact name, file permissions, dependency caching, and security profile. `-DskipTests` in the build stage **does not prove** tests passed; if used, tests must run in another pipeline step.

Differences that easily cause errors:
- The runtime image lacks `javac`, `jar`, `jcmd`, `bash`, `curl`.
- The runtime image lacks the appropriate CA certificate/truststore.
- Native libraries exist in the build stage but are not copied into runtime.
- Non-root user cannot read/write required files.
- `WORKDIR` differs from local path.
- Multi-platform build produces an image with the wrong architecture.
- The JRE is a different version/vendor from the build JDK.

Use the **actual deployed final image** to reproduce, not just running the application from `target/classes` on the host.

## 6. OS, CPU Architecture, libc, and Native Code

Java bytecode is portable, but many applications use native components: JNI/JNA, Netty native transport, RocksDB, compression, SQLite, crypto providers, media tools, or executables external to the JVM.

### 6.1. x86_64 vs. arm64

For example:
- Laptop uses x86_64.
- CI node runs arm64.
- Dependency only contains the `linux-x86_64` native binary.

You may encounter:

~~~text
java.lang.UnsatisfiedLinkError:
  no some_native_lib in java.library.path
~~~

or:

~~~text
Exec format error
~~~

Compare `os.arch`, `uname -m`, the image manifest architecture, and the native dependency classifier. Adding `java.library.path` will not help the JVM run a binary for the wrong CPU architecture.

### 6.2. Alpine/musl vs. glibc

Alpine Linux typically uses musl libc; many Java native libraries are packaged for glibc. Java source may build successfully, yet fail to load JNI at runtime.

Approaches:
- Choose a native dependency that supports musl.
- Choose a glibc base image when appropriate.
- Check the JNI provider, native classifier, and ABI.
- Run tests on the target image/arch.
- Do not blindly copy system libraries and bypass provenance/security updates.

### 6.3. Jlink Image Missing Modules

A runtime image created with `jlink` can miss modules:
- `java.sql` (JDBC).
- `java.naming` (JNDI).
- `java.management` and monitoring.
- `java.instrument` if an agent needs it.
- Other JDK modules used by libraries/frameworks.

Test startup and integration tests on the final image. `jdeps` assists with static reference analysis, but does not cover all reflective loading, plugin discovery, or service providers at runtime.

## 7. Container CPU Quota and Timeout Effects

A test can run fast on a laptop yet be very slow in CI when CPU is constrained. Causes:
- CPU quota of 1 vCPU while the JVM spawns many threads.
- GC/JIT compiler consumes CPU during warm-up.
- Test forks compete for quota.
- Node has noisy neighbors.
- Kubernetes CPU throttling.
- Different CPU architecture has different instruction throughput.

### 7.1. Host Cores Do Not Equal Container Quota

A host having 32 cores does not mean a pod is allowed to use 32 cores. Newer JVM versions usually detect container limits, though behavior depends on vendor/JDK update and cgroups v1/v2.

In a Linux environment with cgroups v2:

~~~bash
cat /proc/self/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
~~~

If the file does not exist, the container may be using cgroups v1 or a different mount; do not immediately conclude “there is no limit”.

Cross-check:
- `Runtime.availableProcessors()`.
- CPU requests/limits and cpuset.
- CPU usage in core-seconds.
- CPU throttled periods/time.
- Thread count, executor queues, and latency.
- Test concurrency/fork settings.

### 7.2. -XX:ActiveProcessorCount to Test a Hypothesis

On supported HotSpot builds, `-XX:ActiveProcessorCount=N` can limit the number of processors the JVM reports in order to adjust certain ergonomics. This can serve as a **controlled experiment**, not a production measure to apply blindly. If you change this option, document that the JDK configuration changed and re-run benchmarks under real workload/limits.

## 8. Memory: Distinguishing Java OOME from OOMKilled

A pod killed when the heap is not full is not necessarily a GC bug. A Java process uses many types of memory:

~~~text
JVM process memory
   |
   +-- Java heap
   +-- Metaspace / class metadata
   +-- Code cache
   +-- Thread stacks
   +-- Direct buffers / off-heap caches
   +-- JNI/native allocations
   +-- Runtime internal structures
~~~

A container with a 1 GiB memory limit but configured with `-Xmx1g` can exceed the limit because it leaves no headroom for non-heap/native memory.

| Symptom | Possibilities to Check |
|---|---|
| `OutOfMemoryError: Java heap space` | Heap limit, allocation pressure, leaks |
| `OutOfMemoryError: Metaspace` | Classloading/metaspace cap |
| `OutOfMemoryError: Direct buffer memory` | NIO/direct allocations |
| `unable to create native thread` | Native memory, PID/thread limit |
| Exit 137 | SIGKILL; **possibly** OOM kill |
| Pod reason `OOMKilled` | Container memory exceeded policy/limit |
| RSS growing, heap stable | Native/direct/thread allocations or page accounting |

**Exit 137 alone does not prove OOM**: check Pod status, container events, cgroup counters, and logs.

### 8.1. JDK Ergonomics Affect Max Heap

If `-Xmx` is not pinned, the JVM may choose heap size automatically based on memory limits/JDK flags. When upgrading the runtime, max heap can change. Compare:
- JDK vendor/build.
- `-Xms`, `-Xmx`, `-XX:MaxRAMPercentage`, or equivalent flags.
- `Runtime.maxMemory()`.
- Heap used/committed/max.
- RSS/container working set.
- GC logs and thread counts.

Do not claim “the new JDK leaks” solely because RSS increases if heap sizing, allocation rate, or workload also changed.

### 8.2. Native Memory Tracking

On supported HotSpot builds:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

When `jcmd` is present and permissions allow:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT has overhead and does not reflect all native allocations outside the JVM; understand its limitations. If a minimal runtime image lacks `jcmd`, an equivalent debug image may be used when permitted, with the differing conditions clearly noted.

## 9. PID Limits, ulimit, and Thread Starvation

A CI runner may have a lower process/PID limit than a laptop, while parallel JUnit tests, Maven forks, Gradle workers, or server thread pools create many threads.

Symptoms:
- `OutOfMemoryError: unable to create native thread`.
- Tests hang because the executor has no available workers.
- Ports/sockets/file descriptors exhausted.
- Container cannot spawn subprocesses.
- JVM/JIT/GC threads push the process near the PID limit.

Check the PID cgroup, thread count, file descriptor limit, executor queue, fork count, and native memory. Do not just increase `-Xmx`; heap limits do not solve every resource limit.

### 9.1. Virtual Threads Do Not Eliminate All Limits

On a JDK supporting virtual threads, an application can have many virtual threads while still consuming carrier/platform threads, sockets, direct memory, and downstream connection pools. Changing the concurrency model during a JDK upgrade is a behavioral/resource change **in addition to changing the Java runtime**. Test under real container quotas.

## 10. Filesystem: Case Sensitivity, Paths, and Working Directory

### 10.1. Case-Sensitive Paths

A test:

~~~java
getClass().getResourceAsStream("/fixtures/Order.JSON");
~~~

yet the file is named:

~~~text
src/test/resources/fixtures/order.json
~~~

may work on a case-insensitive filesystem and fail on Linux. The fix is to make names consistent rather than assuming the OS will fix casing.

### 10.2. Relative Paths

~~~java
new java.io.File("config/orders.yml");
~~~

depends on `user.dir`. The IDE may set the working directory to the repository root; Docker `WORKDIR` is `/app`. A Maven multi-module test task may even use the module dir.

If the file is a resource inside the JAR, prefer classpath resources. If it is external config, specify an absolute path/mount. Temp files should use APIs that create isolated paths and clean up.

### 10.3. Non-Root, Read-Only Filesystem

When switching an image from running as root to non-root:
- `/app/logs` may not be writable.
- Temp directory does not exist/is not writable.
- Native library extraction fails.
- Keystore file is unreadable.
- Shell entrypoint lacks the executable bit.
- User home/caches are not writable.

In Kubernetes, `readOnlyRootFilesystem: true` can also prevent the application/framework from writing temporary files.

Resolution approaches:
- Mount an appropriate writable temp volume.
- Choose suitable UID/GID and ownership.
- Write logs to stdout/stderr when possible.
- Explicitly set `java.io.tmpdir` if needed.
- Do not revert a production container back to root just to hide permission errors.

### 10.4. Line Endings and Git Checkout

Windows may use CRLF; Linux scripts typically require LF. An entrypoint can fail with:

~~~text
/bin/sh^M: bad interpreter
~~~

Check Git line-ending policy, executable bit, shebang, and how files are packaged. For fixtures used to verify binary compatibility, compare the SHA-256 of the **actual bytes**, not just visible text diffs.

### 10.5. Port Collision

Tests hard-coding port 8080 may pass locally but fail in CI when multiple workers run in parallel. Use port 0/random host port mapping via the web/test framework; avoid the “open a socket to get a port number then close it before the server binds” pattern because of race conditions.

## 11. Charset, Locale, and Timezone

Local runs in one timezone/locale, while CI commonly uses UTC or a different default locale. A test involving dates, currency, or Unicode can fail even though business logic has not changed.

### 11.1. JEP 400: Default Charset

JDK 18 standardized the default charset to UTF-8 in many common situations under JEP 400. Code like:

~~~java
String text = new String(bytes);
~~~

can yield different results when legacy files use another encoding. Choose an explicit charset according to the **format contract**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
        Path.of("fixtures/order.txt"),
        StandardCharsets.UTF_8
);
~~~

If legacy data originally uses Windows-1252, read it with that charset per the contract. Do not blindly use UTF-8 just because the new JDK defaults to it.

### 11.2. Clock and Timezone

Fragile test:

~~~java
assertEquals("2026-11-12",
        java.time.LocalDate.now().toString());
~~~

When running near midnight or on UTC, results can differ. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate date = LocalDate.now(clock);
~~~

The contract may store instants in UTC while computing business days in a specific timezone. Do not default to “everything must be UTC” when the business logic requires a local date.

### 11.3. Locale and Unicode

Changing the default locale can affect:
- Decimal/grouping separators.
- Date formats.
- Upper/lowercase.
- Resource bundles.
- Sorting/collation.
- Unicode normalization.

For language-independent identifiers, `Locale.ROOT` is typically used for case conversion when appropriate. For user text, handle locale/Unicode semantics accurately according to business requirements.

## 12. TLS, Truststore, and CA Certificates

If an HTTPS call works on a laptop but throws in a container:

~~~text
javax.net.ssl.SSLHandshakeException
PKIX path building failed
unable to find valid certification path
~~~

possible causes include:
- The corporate CA is only installed on the host.
- The Java truststore in the image is missing the CA.
- The server sends an incomplete certificate chain.
- Hostname/SAN mismatch.
- Different TLS protocol/cipher defaults.
- Expired certificate or clock skew.
- mTLS client certificate/keystore is not mounted.
- Service mesh/proxy intercepts or replaces the endpoint.

### 12.1. Java Truststore Differs from the OS CA Bundle

Depending on the Java distribution, Java TLS may use a separate truststore or integrate with the OS store. You cannot assume that because `curl` succeeds, `HttpClient`/JDBC TLS will also succeed.

Check:
- `java.home` and the Java truststore path.
- `javax.net.ssl.trustStore`/`trustStoreType` when configured.
- CA chain and hostname.
- Proxy, SNI/ALPN/mTLS.
- JDK security policy and certificate validity.

**Do not use a TrustManager that trusts every certificate, and do not disable hostname verification** to make CI green. Provide the proper CA/keystore according to policy.

## 13. DNS, Proxy, Network Policy, and localhost

In Docker, `localhost` points to the container's own network namespace, not automatically to the host database or a service in another container.

For example, local config:

~~~text
jdbc:postgresql://localhost:5432/orders
~~~

may fail in CI when PostgreSQL runs as a `postgres` service or in another pod. Use the service name address matching the topology.

Other factors:
- Kubernetes DNS search domains.
- IPv4/IPv6 resolution.
- `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`.
- Java `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`.
- NetworkPolicy and egress firewall.
- Sidecar/service mesh and mTLS.
- Load balancer/ingress routing.

### 13.1. Proxy Env Vars Do Not Automatically Apply to All Java HTTP Clients

Some CLIs read `HTTPS_PROXY`; Java clients may rely on JVM properties or ProxySelector. Do not infer that `curl` passing means Java will pass. Check the application's **actual HTTP client implementation**.

### 13.2. Network Error Table

| Symptom | Priority Layer to Check |
|---|---|
| `UnknownHostException` | DNS |
| `ConnectException: Connection refused` | Host/port/listener |
| `SocketTimeoutException` | Network/server latency/timeout |
| `SSLHandshakeException` | TLS CA/hostname/protocol/mTLS |
| HTTP 401/403 | Authentication/authorization |
| HTTP 407 | Proxy authentication |
| HTTP 429/503 | Rate limit/upstream capacity |
| HTTP 502/504 | Gateway/upstream failure |

Read the nested root cause and timestamp of the error before choosing a solution.

## 14. Secrets, Profiles, and Property Precedence

Local often has `.env`, IDE run configurations, or credential helpers; CI uses runner secrets; Kubernetes uses Secret/ConfigMap.

Symptoms:
- API returns 401 because the token is not provided.
- Framework does not activate the right profile.
- Application picks an embedded DB instead of the intended DB.
- mTLS certificate path config is missing its mount.
- Different feature flags lead to different auto-configuration.
- Config placeholder uses an unintended default.

### 14.1. Check Presence, Do Not Print Secret Values

~~~java
String token = System.getenv("PAYMENT_API_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "PAYMENT_API_TOKEN is required"
    );
}
~~~

The error may log **the missing variable name**, not the token. When diagnosing, check source precedence and the effective values of required **non-secret keys**.

### 14.2. Read the Right Framework Version

Spring Boot and other frameworks have multiple property sources. Precedence order can change depending on version and the config-data mechanism. The same `application.yml` does not guarantee the same effective config when environment variables, command-line args, or remote config differ.

A diagnostic report should record:
- Active profiles.
- Which config sources were loaded.
- Non-secret effective values.
- Property names that changed/were deprecated when upgrading the framework.
- Bean/auto-configuration conditions at runtime.
- Whether secrets are present, without revealing values.

## 15. Dependency Cache and Build Reproducibility

Local may use artifacts in `~/.m2` or the Gradle cache, whereas a clean CI runner must resolve from the repository. This exposes:
- Unpublished local `mvn install` dependencies.
- Different SNAPSHOT versions.
- Different dynamic version range resolution.
- Different BOM/plugin/transitive graphs.
- Missing artifact repository credentials.
- Proxy/mirror returning different results.
- Stale cache hiding class-file version errors.

### 15.1. Compare Dependency Graphs

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
~~~

These are instructional commands for a real project, not actions to execute when authoring a lesson. Pin versions and locks/checksums per build policy. Do not compare code dependency declarations while ignoring **resolved dependency versions**.

### 15.2. Disable Cache Only to Isolate Issues

Running a clean build or Gradle `--no-build-cache` can help verify a hypothesis, but clearing the cache every time does not fix the underlying cause. It can increase build times and introduce network variability. Keep cache keys scoped by tool/JDK, dependency verification, version locking, and artifact provenance.

## 16. Test Runner: Passing Locally Because the Same Test Suite Wasn't Run

An application might have:
- The IDE running JUnit 5.
- CI Maven Surefire being too old to discover the engine properly.
- Gradle missing `useJUnitPlatform()`.
- Integration tests belonging to Failsafe while the pipeline only runs Surefire.
- CI reporting only a subset of tests due to includes/tags/excludes.
- Coverage Java agent or Mockito agent not passed into the test fork.

**BUILD SUCCESS with 0 tests is not proof of compatibility.**

### 16.1. Gradle and JUnit Platform

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

This example applies to Gradle Kotlin DSL with a compatible JUnit 5 engine. Check custom test suites/tasks and the resolved test runtime classpath.

### 16.2. Maven Surefire/Failsafe

Check plugin/provider versions, forks, test includes/excludes, and `argLine`. If both JaCoCo and Mockito require `-javaagent`, do not accidentally overwrite `argLine` and drop the other agent.

## 17. Race Conditions and Flaky Tests

CI can run with higher parallelism or experience CPU throttling, exposing timing/ordering bugs.

### 17.1. Do Not Use Fixed Sleeps to Wait for Async Completion

Avoid:

~~~java
Thread.sleep(100);
assertEquals("DONE", task.status());
~~~

On a 1-vCPU CI runner, the task may not have been scheduled yet. Prefer a future, latch, or condition polling with a finite deadline:

~~~java
String result = future.get(
        5, java.util.concurrent.TimeUnit.SECONDS
);
assertEquals("DONE", result);
~~~

The example assumes `future` has already been created. This is not a license to increase timeouts indefinitely: if there is a deadlock or queue starvation, obtain a thread dump and find the real cause.

### 17.2. Global Mutable State

Tests that call `System.setProperty` or mutate a static singleton can fail when run in parallel. Although a try/finally restore reduces leaks in sequential tests, **system properties are still shared global state**; inject configuration or isolate processes if tests must change global state.

### 17.3. File and Port Collisions

If two tests both write `/tmp/output.json` or bind port 8080, one test can delete/steal the other's resource. Use unique temp directories and test server port 0.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportTest {
    @TempDir Path temporaryDirectory;

    @Test
    void writesInIsolatedDirectory() throws Exception {
        Path output = temporaryDirectory.resolve("out.txt");
        Files.writeString(output, "OK");
        assertEquals("OK", Files.readString(output));
    }
}
~~~

Containers still need a writable temp volume if the root filesystem is read-only. Do not pick a random port by binding and then closing a socket before the service actually binds: that introduces a race condition.

### 17.4. Test Order and Randomness

Do not rely on `HashMap` iteration order if the contract does not guarantee ordering. For randomized tests, log the seed to reproduce. When testing date/time, use an injected Clock. When running the full suite, check environment cleanup so state does not leak across test classes.

## 18. Mockito, Byte Buddy, and Java Agents

A test can fail on a new JDK/container when the Mockito inline mock maker or Byte Buddy fails to initialize.

Distinguish:
- Does the Byte Buddy version understand the new JDK's class-file version?
- Does the Mockito version support the JDK/test runtime?
- Does the test need inline mocking (final/static/constructor) or subclass mocking?
- Is the agent configured at startup or using self-attach?
- Does the JVM have a policy restricting dynamic attach?
- Does the agent JAR exist at the path of the **test fork** inside the container?
- Was `-javaagent` accidentally placed on the build JVM instead of the test JVM?

JDK 21 began warning on dynamic agent loading under JEP 451 in applicable environments. **Do not claim that all JDK 21+ releases already block dynamic attach by default**; the policy depends on release/vendor. For supported Mockito versions, configuring `-javaagent` at test JVM startup is clearer than relying on self-attach.

### 18.1. JPMS Is Different from Agent Attachment

`InaccessibleObjectException` can occur due to reflective access to a non-open module/package. `--add-opens` is a scoped measure by package/target; it does not fix a missing Java agent, an outdated bytecode tooling version, or a removed API.

Do not copy broad `--add-opens` flags from IDE configs into production `JAVA_TOOL_OPTIONS` without verifying which library needs them and the security risks.

## 19. Docker Entrypoint and Process Lifecycle

An app running properly with:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

is not guaranteed to run properly in Docker if ENTRYPOINT/CMD quoting is wrong.

### 19.1. Exec Form

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This form provides explicit argv and generally allows the Java process to receive signals directly.

### 19.2. Shell Form

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

A shell can sit in between, changing quoting/variable expansion and signal handling. If using a shell entrypoint, use `exec` with safely handled argv; do not concatenate a shell command string from untrusted values.

### 19.3. SIGTERM and Graceful Shutdown

Kubernetes typically sends SIGTERM, waits for the grace period, and then sends SIGKILL. If Java does not receive the signal or a job does not checkpoint properly, deployments can cause duplicate processing.

Test:
- Entrypoint/PID tree.
- Readiness before receiving traffic and during shutdown.
- Termination grace period.
- Executor/HTTP server stop.
- Message offset/checkpoint/idempotent restart.

`JAVA_TOOL_OPTIONS` can affect multiple Java processes in the container, including tooling; verify the proper scope of flags.

## 20. Clock Skew, Certificate Validity, and Distributed State

Timezone is not the same as clock skew:
- **Timezone** is how local time is represented.
- **Clock skew** is the actual time difference between two hosts.
- **Monotonic clock** is used to measure elapsed durations.
- **Wall clock** is used for token/certificate expiration.

JWT `nbf`/`exp`, signed requests, and TLS certificate validation can fail if the container host clock is skewed. Changing `TZ` does not fix clock skew. When unit tests need to verify expiry, inject a fixed Clock; for integration tests, inspect timestamps from both the issuer and verifier along with host time sync.

## 21. Testcontainers and Docker-in-Docker

Testcontainers can pass on a laptop yet fail in CI because:
- Docker daemon/socket is unavailable.
- Runner lacks permissions.
- Docker-in-Docker is not configured.
- Rootless Docker or different network policy.
- Registry auth/rate limits.
- Wrong image architecture.
- Database container is not ready yet.
- Cleanup sidecar is blocked.
- Nested containers cannot connect to host-mapped ports.

If Testcontainers fails to create the DB container, **application JDBC logic has not been tested**. Do not modify Hibernate just to work around a Docker socket error.

Record:
- Docker provider/host.
- Runner permissions and security policy.
- Testcontainers version.
- Image digest.
- Network/port mapping.
- Health/readiness strategy.
- Cleanup and parallelism.

Do not grant `--privileged` or mount the Docker socket into every CI job by default; Docker privileges are sensitive. Use approved runners.

## 22. CI Timeouts and Retries

Timeouts can result from:
- CPU throttling or insufficient threads.
- JIT warm-up/cold cache.
- Slow image pulls/registry.
- Network/proxy/dependency.
- Deadlock/connection pool starvation.
- CI job time limit set too small.
- Test waiting on an uninitialized external service.

Increasing the timeout slightly can aid observation, but **does not fix the root cause** if there is a deadlock or unbounded retries. Inspect thread dumps, queues, timestamps, CPU/memory, and dependency latency.

Retries should apply only to identified transient errors, with bounded attempts/backoff, idempotency, and without masking flaky assertions. Do not infinitely retry the entire test suite until it turns green.

## 23. Step-by-Step Diagnostic Workflow

~~~text
Step 1: Classify the failure
          |
          v
Step 2: Collect logs + fingerprint
          |
          v
Step 3: Compare artifact/JDK/image/config/resources
          |
          v
Step 4: Form a testable hypothesis
          |
          v
Step 5: Reproduce by changing one variable at a time
          |
          v
Step 6: Confirm root cause
          |
          v
Step 7: Fix at the right layer
          |
          v
Step 8: Run regression test on target CI/container
~~~

### 23.1. Step 1: Collect the Original Failure

Record:
- Stage, command, exit code.
- Full exception chain and test name.
- Pod/container termination reason when relevant.
- Last pass, first fail.
- Reproducible or flaky?
- Affects only one runner/node or all?
- JDK, app, image, dependency versions.

### 23.2. Step 2: Verify the Artifact

- Is the commit SHA the same?
- JAR/build output checksum?
- Resolved dependency graph?
- Docker image digest/architecture?
- Are generated code and resources included in the artifact?
- Does the runtime JDK have sufficient class-file/module support?

If the artifacts differ, establish build reproducibility before comparing JVM behavior.

### 23.3. Step 3: Verify the JVM

- Build launcher vs. compiler toolchain vs. test fork.
- App runtime `java -version` inside the image.
- VM options, heap flags, Java agent.
- OS/arch/libc.
- Class-file major and API compatibility.

### 23.4. Step 4: Verify the Environment

- CPU/RAM/PID limits.
- Non-root/read-only permissions.
- Working directory and path case.
- Locale/timezone/charset.
- DNS/proxy/CA.
- Secret presence/active profiles.
- Network and downstream readiness.

### 23.5. Step 5: Test One Hypothesis

For example:
- Pin the timezone with a test Clock.
- Run the container with the same CPU quota.
- Test the exact ARM64 image on an ARM64 node.
- Add the CA to the Java truststore following policy.
- Run tests sequentially to observe whether the race appears/disappears.
- Pin dependencies to eliminate cache effects.
- Run with/without the agent on the test fork, using the right version.

**An experiment is only valid if the changed condition is explicitly recorded.** Avoid upgrading libraries, changing the image, and increasing RAM at the same time and claiming you found the root cause.

### 23.6. Steps 6–8: Fix and Guard Against Regressions

Fix at the right layer, and create corresponding regression evidence:
- Wrong Java runtime → pin toolchain/runtime.
- Encoding → explicit charset.
- Timezone → injected Clock/business zone.
- Path → classpath resource/unique temp dir.
- CPU quota → sizing/concurrency, test at limits.
- JNI arch → appropriate native variant.
- TLS → CA/truststore and integration test.
- Flaky test → isolation/synchronization.
- Missing dependency → lock/verification.
- Incorrect agent placement → test JVM configuration.

## 24. Reproducing with the Final Container Image

An illustrative command:

~~~bash
docker run --rm \
  --cpus=1 \
  --memory=768m \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=128m \
  --user 10001:10001 \
  -e TZ=UTC \
  registry.example/orders:PINNED_TAG
~~~

This template applies only if the image supports read-only, UID, temp mount, and needs no other networks/volumes. Use dedicated test credentials, **never use production secrets** for local reproduction.

### 24.1. Why Does Local Docker Still Differ from Kubernetes?

Even when the image is identical:
- Node CPU architecture/noisy neighbors may differ.
- Service mesh and NetworkPolicy differ.
- DNS/search domains differ.
- Secret/volume permissions differ.
- Pod probes, resource policies, and HPA differ.
- Storage performance and backend latency differ.

Local Docker helps isolate issues, but does not replace staging/cluster integration verification.

### 24.2. Pin the Image Digest

The `latest` tag can change. The run manifest must store the image digest, JDK build, artifact hash, and deployment flags. If baseline/candidate changed the base image as well, the conclusion must explicitly note that this is a **JDK + image migration**, without having isolated the JVM alone.

## 25. Quick Diagnostic Table

| Symptom Only in CI/Container | Cause to Check |
|---|---|
| `UnsupportedClassVersionError` | Runtime JDK lower than class file |
| `invalid target release` | Wrong compiler JDK/toolchain |
| `Unrecognized VM option` | Unsupported JVM flag/vendor/version |
| `ClassNotFoundException` | Missing runtime classpath/module |
| `NoSuchMethodError` | Binary dependency/API mismatch |
| `UnsatisfiedLinkError` | Native library wrong arch/libc/path |
| `Exec format error` | Wrong OS architecture for binary/image |
| `InaccessibleObjectException` | JPMS opens/reflective access |
| Mockito inline fail | Byte Buddy/agent/test JVM mismatch |
| JUnit runs 0 tests | Engine/provider/excludes |
| CI test timeout | Throttling, network, race, queue |
| `unable to create native thread` | PID/thread/native memory limit |
| Exit 137 / `OOMKilled` | Cgroup memory/SIGKILL |
| `OutOfMemoryError: Java heap space` | Heap pressure/leak |
| FileNotFoundException | Workdir/mount/case/resource |
| Permission denied | Non-root/read-only filesystem |
| `UnknownHostException` | DNS/network |
| `SSLHandshakeException` | CA/truststore/TLS/mTLS |
| HTTP 401/403 | Env/secret/auth policy |
| JSON/text differs | Charset/default mapper |
| Date assertion skew | Timezone/locale/clock |
| Local dependency present, missing in CI | Cache/repository/unpublished artifact |
| Testcontainers fails to start | Docker runner/permissions/network |
| High p99 in container | CPU quota/GC/DB/traffic |
| SIGTERM does not clean up | Entrypoint/PID 1/shutdown hook |

This table helps choose **the first investigation step**, and does not prove causality from a single exception type alone.

## 26. Scenario 1: IDE Passes, CI Runs the Wrong Test JDK

Suppose the IDE runs JUnit 5 on Java 21, but Maven Surefire in CI uses a Java 17 JVM. A test dependency has class-file major 65.

**Symptom:** `UnsupportedClassVersionError`.

**Handling steps:**
1. Record the class causing the error.
2. Verify the JDK of the test fork, not just the shell.
3. Check toolchains and the final dependency graph.
4. Finalize the actual runtime floor that must be supported.
5. Choose a compatible dependency/test JDK.
6. Pin plugin/provider versions and test count.
7. Re-run in CI.

Do not lower `--release` on application source if the issue actually comes from a third-party test dependency or runtime fork.

## 27. Scenario 2: Container Gets OOM Killed Yet Heap Is Not Full

Suppose the app has a 768 MiB memory limit, uses nearly 650 MiB of heap, and uses many direct buffers and native threads.

**Symptom:** pod restarts, with `OOMKilled` or exit 137; Java logs show no heap OOME.

**Handling steps:**
1. Inspect Pod/container status and OOM events.
2. Record max heap, RSS, and cgroup limits.
3. Inspect non-heap/direct/native/thread memory.
4. Check allocation/GC and workload.
5. Adjust heap/native headroom or fix leaks.
6. Compare baseline/candidate under the same limits.
7. Run load/soak tests and observe the memory trend.

Do not increase `-Xmx` in a small container to fix a kernel OOM kill; doing so can make memory pressure worse.

## 28. Scenario 3: HTTPS Fails Only in the New Image

Suppose the laptop trusts the corporate CA, but the Java 21 runtime image does not yet have the proper truststore installed.

**Symptom:** `SSLHandshakeException: PKIX path building failed`.

**Handling steps:**
1. Confirm the actual endpoint and certificate chain inside the container.
2. Check the Java truststore, CA, and proxy.
3. Check hostname, SNI, and client certificate if using mTLS.
4. Check clock and JDK TLS policies.
5. Supply the proper CA/truststore per image policy.
6. Run integration tests on the final image.
7. Do not disable certificate/hostname verification.

## 29. Scenario 4: Two Tests Contend for the Same File in CI

Suppose tests A and B both use `/tmp/export.json`. Locally they run individually; in CI they run in parallel.

**Symptom:** file deleted or randomly written with corrupted data.

**Fix:** use a unique temporary directory per test, do not hard-code global paths, and clean up per lifecycle. If still depending on static singletons/global properties, inject/isolate state rather than merely increasing test retries.

## 30. Checklist Before Concluding Resolution

- [ ] Identified the failing stage and root-cause stack trace.
- [ ] Recorded commit, artifact checksum, and image digest.
- [ ] Verified JDK launcher, compiler, test fork, and app JVM.
- [ ] Checked `--release`, class-file major, and dependency versions.
- [ ] Recorded OS/architecture, base image, libc, and native library support.
- [ ] Checked how the build stage differs from the runtime image.
- [ ] Checked CPU quota, availableProcessors, and throttling.
- [ ] Checked heap, RSS, non-heap/native memory, and OOM reason.
- [ ] Checked PID/thread/file descriptor limits.
- [ ] Checked case-sensitive paths, workdir, and read-only mounts.
- [ ] Checked charset/locale/timezone and clock behavior.
- [ ] Checked DNS, proxy, service names, and NetworkPolicy.
- [ ] Checked Java truststore/CA/TLS and mTLS.
- [ ] Checked presence/config sources of secrets without logging values.
- [ ] Compared resolved Maven/Gradle dependencies and cache behavior.
- [ ] Verified JUnit test discovery and count of executed tests.
- [ ] Checked parallelism, global mutable state, and port/file collisions.
- [ ] Checked Java agent, Mockito/Byte Buddy, and JPMS flags when relevant.
- [ ] Checked Docker/Testcontainers privileges and readiness.
- [ ] Checked entrypoint, argv, PID 1, SIGTERM, and shutdown.
- [ ] Reproduced or explicitly documented reproduction limitations.
- [ ] Changed one variable at a time to confirm the root cause.
- [ ] Fixed the root cause without disabling TLS/security or adding infinite retries.
- [ ] Added regression evidence on the target CI/container.

## 31. References

- [Java Launcher Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM flags, launcher, and GC logging.
- [JDK jcmd Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM flags, GC, and JFR.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset starting in JDK 18.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): module access.
- [JEP 451 — Dynamic Loading of Agents](https://openjdk.org/jeps/451): Java agent behavior.
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test JDK configuration.
- [Gradle Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): test tasks and JUnit Platform.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): release/source/target.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): tests/forks/argLine.
- [Dockerfile Reference](https://docs.docker.com/reference/dockerfile/): USER, WORKDIR, ENTRYPOINT, multi-stage.
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, and cgroups.
- [Kubernetes Debug Running Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/): logs, events, and debugging.
- [Testcontainers Java](https://java.testcontainers.org/): container-based tests.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): mock maker and agent.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, parallel execution, and TempDir.

“current/latest” documentation pages may differ from pinned versions. When implementing, consult documentation for the **exact JDK, OS/image, build plugin, and framework version**, and cross-check with runtime evidence.

## 32. Conclusion

**Failures occurring only in CI or containers usually indicate that execution conditions are not yet equivalent; you should not blame the new JDK by default.** Separately check the artifact and dependency graph, Java compiler/test/runtime, OS and native libs, cgroup resources, filesystem, charset/timezone, DNS/proxy/CA, secrets/config, and how CI runs tests in parallel.

A reliable process is **identify the failing stage → collect fingerprint and logs → build a difference matrix → reproduce with equivalent artifact/image/resources → change one variable deliberately at a time → fix the root cause → add regression tests in the target CI/container**. Rather than making the pipeline green by increasing timeouts indefinitely, skipping tests, disabling TLS verification, or running privileged containers, the team needs to retain sufficient technical evidence so that the next Java upgrade does not repeat the “it works on my machine” incident and turn workarounds into production risks.