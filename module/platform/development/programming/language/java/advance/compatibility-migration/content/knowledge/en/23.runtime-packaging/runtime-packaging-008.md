# Container base images, system libraries, and target architecture

When upgrading a Java application, recompiling with a newer JDK solves only part of compatibility. A JAR can still run stably on a developer's machine yet fail when moved into a container: the JVM fails to start, JNI throws UnsatisfiedLinkError, TLS connections do not trust certificates, time data drifts, or an x86-64 native library fails to run on an ARM64 node. These issues usually originate from the **container base image**, **system libraries**, **ABI**, and **deployment architecture**, rather than directly from Java source.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Packaging and Environment**. The focus is on understanding what a base image contains, choosing the JDK/JRE and base operating system, distinguishing glibc from musl, identifying native dependencies, packaging multi-architecture images, managing runtime resources, securing the supply chain, and testing migration against the exact image going to production.

Core principle: **container compatibility is compatibility across the Java artifact, JVM, OS userland, native libraries, container runtime, and target CPU platform**. One successful docker build or one passing Java unit test does not prove the entire chain works.

## 1. Layers involved when a Java container runs

~~~text
Application request / message
             |
             v
+-----------------------------------------+
| Application bytecode                    |
| app.jar, classes, third-party JARs      |
+-----------------------------------------+
| Java runtime                            |
| JVM, JRE modules, GC, JSSE, JIT         |
+-----------------------------------------+
| Native libraries and agents             |
| JNI, JNA, JVMTI, libc, libstdc++        |
+-----------------------------------------+
| Container image userland                |
| OS packages, CA, timezone, fonts, user  |
+-----------------------------------------+
| Container runtime + Linux kernel        |
| namespaces, cgroups, seccomp, mounts    |
+-----------------------------------------+
| CPU architecture and instruction set    |
| x86-64, AArch64, CPU extensions         |
+-----------------------------------------+
~~~

A pure-Java program may rely minimally on third-party native code, yet the JVM still requires matching binaries and system interfaces. Systems doing image processing, native database clients, GPUs, JNI compression, or APM profilers can pull in additional C/C++ libraries and agents.

### 1.1. Three questions to answer before changing images

1. **Which Java runtime is required?** Major/update/build, vendor, modules, JVM flags, security policy, and Java APIs.
2. **Which userland is required?** Linux distribution, libc, shared libraries, CA certificates, timezone, locale, fonts, and OS configuration files.
3. **Which target platform is supported?** OS, architecture, bitness, instruction set, cgroups, container runtime, and deployment policy.

Never equate the Java version with the full runtime contract.

## 2. What is a base image?

A base image is the foundation selected in the Dockerfile's FROM instruction, providing the filesystem and runtime components for subsequent layers.

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example assumes a prebuilt executable JAR at target/app.jar. Real projects must use the actual artifact path and confirm tag availability. An image provides more than the java executable; it also includes JVM libraries and OS components chosen by the image publisher.

### 2.1. A base image does not create its own kernel

Linux containers typically share the host or Linux VM kernel, while the image contains userland such as the filesystem, shared libraries, and application binaries. Picking a Debian-based image does not turn the host's kernel into a Debian kernel. On Docker Desktop for macOS/Windows, Linux containers generally run inside a Linux VM.

### 2.2. Tags are not immutable content

A tag such as 21-jre can be updated to deliver security patches. Two builds run on different days can pull different image contents even though the Dockerfile never changed.

To produce traceable artifacts, you can pin an image by digest:

~~~dockerfile
FROM registry.example.org/java/runtime:21@sha256:REPLACE_WITH_REAL_DIGEST
~~~

That digest string is a placeholder, not a valid digest for deployment. Real digests must come from a trusted registry and be verified for the target platform. Pinning digests helps reproducibility yet requires regular update processes; never pin and forget security patches.

### 2.3. Details to record about an image

| Attribute | Example details to record |
|---|---|
| JDK/JRE | Java 21, update/build version, and vendor |
| OS userland | Debian-family, Ubuntu-family, Alpine, UBI… |
| libc | glibc or musl, version |
| Platform | linux/amd64, linux/arm64 |
| Image identity | Registry, repository, tag, immutable digest |
| User | UID/GID, root or non-root |
| Native dependencies | libstdc++, crypto, codec, database libraries |
| Runtime files | Truststore, CA, tzdata, fonts, locales |
| Container settings | CPU/memory limit, writable mounts, entrypoint |
| Patching | Source/vendor, CVE scanning and update policy |

## 3. JDK, JRE, jlink, and distroless: choosing a runtime

| Image type | Advantages | Things to watch |
|---|---|---|
| Full JDK | Includes compiler and diagnostic tools | Many components unnecessary in production |
| JRE | Focused on running Java applications | May omit jcmd, javac, and dev tooling |
| Custom jlink runtime | Picks needed Java modules only | May miss dynamically loaded modules or providers |
| Distroless runtime | Minimal userland, fewer extraneous tools | No shell/package manager, harder direct debugging |
| Linux distro + custom-installed Java | Full control over installing native dependencies | Must manage patching for both OS and JDK |

No single choice is universally best. Services needing font rendering, HSM libraries, JNI, machine-learning runtimes, or native agents may require more OS packages than a pure-Java REST service.

### 3.1. Build with JDK, run with JRE

Builds need javac and Maven/Gradle; production usually only needs the runtime.

~~~text
Build stage:
  JDK + Maven/Gradle + source -> JAR

Runtime stage:
  JRE + JAR + required native libraries -> image
~~~

If the compiler emits Java 17 class files while the runtime image contains Java 21, the app can run provided dependencies and runtime behavior align. Conversely, Java 21 class files will not run on JRE 17 merely by renaming the image tag.

### 3.2. When production needs JDK tools

Some environments run jcmd, jfr, jstack, or keytool directly inside containers. JRE or distroless images may omit them. Diagnostic images or external observability mechanisms can serve instead, yet must be planned before incident investigations arise.

### 3.3. Image size does not determine correctness

Saving 100 MB is worthless if it strips CA certificates, fonts, native codecs, or memory leak diagnostics. Prioritize compatibility, security, patchability, and operability first, then optimize size.

## 4. Java version differs from OS and libc

Two images both labeled Java 21 can differ substantially:

~~~text
Image A:
  JDK vendor A, Java 21
  Debian-family userland
  glibc
  linux/amd64

Image B:
  JDK vendor B, Java 21
  Alpine-family userland
  musl
  linux/arm64
~~~

Both can execute compatible Java bytecode, yet may not run the same native library or agent.

### 4.1. Choose OS distribution by dependencies

| Image family | Characteristics | Migration risks |
|---|---|---|
| Debian/Ubuntu | glibc, apt/dpkg ecosystem | glibc version, packages, CA/tzdata |
| RHEL/UBI | glibc, RPM ecosystem | Vendor support, native packages, FIPS |
| Alpine | musl, apk ecosystem | glibc native binaries do not automatically run on musl |
| Distroless | Minimal userland, sparse tooling | May lack shell, CA/fonts/native libs depending on image |
| Scratch/custom | Supply every needed file manually | Easy to omit dynamic loader or Java modules |

If a native library is vendor-supported solely on glibc, switching to Alpine/musl for smaller image size can cause serious incompatibility.

### 4.2. Avoid bundling multiple changes at once

~~~text
Before:
  JDK 11 + Ubuntu + glibc + amd64

After:
  JDK 21 + Alpine + musl + arm64
~~~

When failures occur, isolating whether the cause is JDK, libc, architecture, or native libraries becomes difficult. Whenever possible, upgrade the JDK first within the same OS family, trim the image next, and expand architectures last.

## 5. glibc and musl: a critical ABI boundary

glibc and musl are distinct C library implementations. C/C++ binaries compiled against glibc are **not guaranteed** to load in a musl-only userland.

~~~text
Java JAR
    |
    v
JNI/JNA wrapper
    |
    v
libimage.so built for glibc
    |
    v
Alpine runtime with musl only
    |
    v
Dynamic loader / symbol error
~~~

Having a .so file present on the filesystem does not guarantee the OS dynamic loader can load it.

### 5.1. Layers that must match

- ELF architecture and bitness.
- C dynamic loader.
- libc family and symbol versions.
- Native dependencies via NEEDED entries.
- libstdc++/C++ ABI when using C++.
- Calling conventions and struct layout.
- CPU instruction set.
- Read/execute permissions and filesystem policy.

### 5.2. Even glibc has version boundaries

Binaries built on a newer distro may require symbol versions absent on an older runtime, triggering errors like:

~~~text
version 'GLIBC_2.xx' not found
~~~

xx is a placeholder. Check actual symbol requirements and pick matching build/runtime baselines. Never copy individual libc files from another image as a quick patch, because the dynamic loader, NSS, and companion libraries must form a coherent set.

### 5.3. Compatibility layers are not a universal fix

Some environments offer compatibility packages or ways to run certain glibc binaries on musl, yet never assume every JNI/JNA/OpenSSL/C++ library will work. When a vendor only supports glibc for native packages, picking a glibc-based base image is typically lower risk.

## 6. Which system libraries might a Java application need?

A Java application that never imports C code directly can still pull native dependencies via JARs.

| Category | Examples | Possible failures |
|---|---|---|
| C/C++ runtime | libc, libstdc++, libgcc | UnsatisfiedLinkError or symbol mismatch |
| Native crypto | OpenSSL, PKCS#11/HSM | Provider fails to load, handshake/crypto errors |
| Networking | Native Netty transport, resolvers | Transport/resolver errors or silent fallback |
| Compression | zlib, zstd, lz4 JNI | Native codec unavailable |
| Database | ODBC/native clients, embedded engines | Shared library load failure |
| Rendering | fontconfig, freetype, image codecs | Corrupt PDFs, images, or glyphs |
| ML/GPU | CUDA, inference engines | Driver/runtime/ABI mismatch |
| Monitoring | JVMTI, profiler/APM agents | Crashes or attach failures |
| File/OS | Native watchers, serial/USB | Cannot access device/syscall |
| Runtime data | CA, timezone, locale, fonts | Trust/time/formatting failures |

Do not install every library in this table. Inventory what the application genuinely uses.

### 6.1. Java TLS rarely requires system OpenSSL

Most HTTP clients use JDK JSSE. Never conclude that HTTPS requires installing OS libssl. Conversely, native TLS engines, PKCS#11 providers, or custom C/C++ libraries may require matching OpenSSL versions.

### 6.2. Transitive native dependencies

~~~text
app.jar
   |
   v
third-party.jar
   |
   v
Extract libwrapper.so
   |
   +--> libstdc++.so
   +--> libcrypto.so
   +--> libc.so
~~~

The Java dependency tree shows only part of the picture. Dynamic linker dependencies do not always appear in Maven or Gradle metadata.

## 7. Inspecting native libraries on Linux

The following commands are diagnostic examples run on systems where the tools exist.

### 7.1. Architecture and binary format

~~~bash
file /opt/app/native/libexample.so
readelf -h /opt/app/native/libexample.so
~~~

Check ELF class, Machine, file type, ABI, and toolchain metadata.

### 7.2. Dynamic dependencies

~~~bash
readelf -d /opt/app/native/libexample.so
~~~

Entries like NEEDED, RPATH, or RUNPATH reveal what the dynamic loader needs.

Some environments permit:

~~~bash
ldd /opt/app/native/libexample.so
~~~

However, **do not run ldd casually on untrusted binaries**. Depending on the environment, the tool may involve dynamic loader execution; prefer static analysis or sandboxing for untrusted files.

### 7.3. Exports and JNI symbols

~~~bash
nm -D /opt/app/native/libexample.so
objdump -T /opt/app/native/libexample.so
~~~

If a Java native method changes package, name, or signature without rebuilding the native library, JNI symbol lookup fails. For JNA, exported C functions and calling conventions must also match.

### 7.4. Distroless images lack these commands

Do not install compilers or linker utilities inside production images just to run ldd. Use a diagnostic image carrying the same binaries, a compatible test image, or CI build pipeline tooling.

## 8. Target architecture: amd64, arm64, and naming conventions

Container platforms are typically specified as:

~~~text
linux/amd64
linux/arm64
~~~

Other tools may use different strings:

| Context | x86-64 | ARM64 |
|---|---|---|
| Docker platform | linux/amd64 | linux/arm64 |
| Common uname -m | x86_64 | aarch64 |
| Common Java os.arch | amd64 | aarch64 |
| Native classifier | linux-x86_64 | linux-aarch64 |

Actual strings vary across vendors, frameworks, and packages. Code choosing native binaries must use explicit mapping rather than brittle string matching.

### 8.1. Java bytecode is not the whole application

A multi-arch base image supplies JVMs for both amd64 and arm64, yet app.jar might embed linux-x86_64/libcompress.so. On ARM64, Java classes can load fine until failing at the very first native call.

Check:

- JNI/JNA artifacts.
- Native agents/JVMTI profilers.
- Native database clients.
- Compression, image, and ML codecs.
- OS utilities copied into the image.
- CPU-specific binaries and kernel interfaces.

### 8.2. ARM 32-bit is not ARM64

If a library carries classifier linux-armv7, never assume compatibility with linux/arm64. Bitness, ABI, and instruction sets differ.

### 8.3. CPU instruction extensions

Even within x86-64, a native binary compiled with newer instruction sets may fail on older CPUs. Pick an appropriate minimum CPU baseline or tested runtime dispatch.

## 9. Multi-architecture images and manifest lists

One image tag can reference multiple platform-specific manifests:

~~~text
my-service:1.0
    |
    +--> linux/amd64 image
    |      +--> amd64 JVM
    |      +--> amd64 native libs
    |
    +--> linux/arm64 image
           +--> arm64 JVM
           +--> arm64 native libs
~~~

Container runtimes usually pick the manifest matching the host node. Still, having both variants under one tag **does not prove** every bundled library matches its architecture.

### 9.1. Inspecting manifests

~~~bash
docker buildx imagetools inspect registry.example.org/team/my-service:1.0
~~~

Illustrative command; substitute your real repository/tag. Check all platforms and digests, not merely the first entry.

### 9.2. Multi-platform builds

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.org/team/my-service:1.0 \
  --push .
~~~

Builders need native workers, cross-compilation, or suitable emulation. Buildx never automatically translates an x86-64 binary into ARM64.

### 9.3. Image index digest differs from per-platform digest

Distinguish the manifest index digest from each platform variant's digest. When debugging ARM64-only failures, confirm which ARM64 manifest/runtime digest the node pulled.

### 9.4. Emulation never replaces real-node testing

QEMU helps for experiments or builds, yet performance, CPU features, and runtime behavior differ from native ARM64 hardware. If production runs ARM64, execute integration tests on real ARM64 nodes.

## 10. BUILDPLATFORM and TARGETPLATFORM

BuildKit distinguishes:

- BUILDPLATFORM: the machine executing the build.
- TARGETPLATFORM: the platform of the output image.

Example:

~~~dockerfile
FROM --platform=$BUILDPLATFORM eclipse-temurin:21-jdk AS build
ARG TARGETPLATFORM
ARG TARGETARCH

WORKDIR /workspace
# Compile Java artifact for the exact Java release.
~~~

This fragment illustrates the concept. Java bytecode can be compiled on BUILDPLATFORM when no host-arch native artifacts are baked in.

However, if Maven automatically picks classifiers from the build JVM's os.arch, building a JAR on amd64 and placing it inside an arm64 image can embed the wrong binary.

### 10.1. Know where native artifacts originate

Three patterns exist:

1. Native libraries are built on native builders per architecture.
2. Native libraries are cross-compiled using matching toolchains/ABIs.
3. Native libraries are published per platform by vendors and packaging picks the matching variant.

Setting ARG TARGETARCH in a Dockerfile does not force C/C++ compilers or Maven classifiers to use it automatically. Wire target variables into build tools and verify outputs.

## 11. Basic multi-stage Dockerfile

Example building with Maven and running on a JRE:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN chmod +x ./mvnw

COPY src src
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar

USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Assumptions:

- Maven Wrapper already exists in the repository.
- Single-module project requiring no extra reactor copies.
- Build produces target/app.jar.
- Artifact includes a launcher/Main-Class.
- Runtime image matches Java version and platform.
- App runs without write access to /app.
- No extra native dependencies require copying.

In production, adapt the Dockerfile to your project, run full pipeline tests/validation, and pin managed base image versions/digests. Using -DskipTests here is **not guidance to skip release testing**.

### 11.1. Benefits of multi-stage builds

- Keeps Maven/compiler out of production images.
- Separates build-time and runtime dependencies.
- Shrinks the production tooling footprint.
- Tightly controls artifacts entering the final image.

### 11.2. Common pitfalls

- Installing native libraries only in the build stage.
- Mismatched release between build JDK and runtime JRE by mistake.
- Copying a non-executable JAR.
- Running non-root without read access to config files.
- Runtime missing fonts/CA/timezone data.
- Native classifiers selected from builder architecture.
- CI testing only the JAR on host without testing the final image.

## 12. Trimming runtimes with jlink

jlink constructs a runtime containing selected Java Platform modules. Example:

~~~bash
jlink \
  --add-modules java.base,java.logging,java.naming,java.sql,java.management,java.xml \
  --strip-debug \
  --no-man-pages \
  --no-header-files \
  --output custom-runtime
~~~

This module list is illustrative, **insufficient for every application**. Frameworks can use ServiceLoader, reflection, or dynamic dependencies that static analysis overlooks.

### 12.1. Identifying modules

~~~bash
jdeps --print-module-deps --multi-release 21 app.jar
~~~

With third-party JARs, supply the full classpath/modulepath and verify dependencies jdeps misses when inspecting app.jar alone.

### 12.2. Common errors after jlink

- ClassNotFoundException or NoClassDefFoundError from missing modules.
- Missing Java services/crypto providers.
- Missing JDBC/JNDI/XML modules.
- Missing logging/management/instrumentation modules.
- Altered charset, timezone, or locale handling.
- Frameworks/agents using reflection into absent packages.
- Incompatible native dependencies or JSSE configuration.

Verify trimmed runtimes with **real integration tests**, never merely `java -version`.

### 12.3. A jlink runtime is architecture-specific

Custom runtimes embed JVM native binaries from the source JDK's platform. You cannot copy a runtime built for Linux amd64 onto Linux arm64 and expect it to execute.

### 12.4. jlink does not handle JNI/JNA

If an app requires libdatabase.so or libimage.so, jlink only handles Java modules; third-party native libraries still must be packaged and ABI-verified separately.

## 13. Distroless and shell-less images

Distroless images keep minimal runtime dependencies while removing unnecessary CLI tools and package managers.

Advantages can include a smaller filesystem surface and fewer extra utilities. However:

- No /bin/sh or /bin/bash as legacy scripts assume.
- No apt, apk, curl, ps, top, or ldd.
- Cannot install packages dynamically in a running container.
- Native libraries must be baked in beforehand.
- External debugging workflows are necessary.
- CA, timezone, fonts, and writable dirs must be verified upfront.

### 13.1. Prefer exec-form ENTRYPOINT

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Shell form:

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

requires a shell and introduces an intermediate shell process. On distroless images, use exec form and supply JVM options via launcher or container configuration mechanisms.

### 13.2. Do not strip images before mapping the dependency closure

If a service relies on Java2D PDF rendering, JNI compression, PKCS#11, or native profilers, inventory and bundle all dependencies before shrinking down to distroless.

## 14. Non-root users and filesystem permissions

Production containers should generally run with least privilege.

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar /app/app.jar

USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Verify:

- UID/GID can read artifacts and configs.
- Secrets/truststores have controlled read permissions.
- Native libraries can be loaded.
- /tmp, /logs, cache, and heap dump paths are writable.
- Mounted volumes avoid ownership mismatches.
- No elevated capabilities are needed to bind ports.
- If the user lacks a home directory, does code depend on user.home?

### 14.1. Read-only root filesystem

A service can run with a read-only root filesystem when writable paths use dedicated mounts/tmpfs. Yet JNA/JNI libraries may extract .so files into java.io.tmpdir, frameworks may write temporary files, and JFR/heap dumps need writable output destinations.

### 14.2. noexec on temporary directories

If a library extracts native code into /tmp and tries to load it, a noexec mount causes the dynamic loader to refuse. Configure library-supported extraction directories with proper permissions and clear security policies rather than disabling all safeguards as a quick fix.

## 15. CA certificates and Java truststore

Changing base images can alter CA trust configuration. Distinguish:

- OS CA store managed by the distro.
- JDK truststore, such as cacerts.
- Custom truststore specified by the application.
- Keystore containing client keys/certificates for mTLS.

Some distros automatically synchronize OS CA updates into the Java truststore; others maintain them separately. Never assume installing the ca-certificates package updates every Java TLS client's trust decisions.

### 15.1. Common symptoms

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

Possible causes:

- Image lacks internal CAs.
- Custom truststore is not mounted.
- Non-root UID lacks permission to read keystore files.
- JDK security policy rejects weak certificates/algorithms.
- Server fails to send the full chain.
- Proxy/load balancer swaps certificates.
- Client uses a different truststore than expected.

### 15.2. Remediation

Confirm active providers/truststores, certificate chains, and hostnames; update CAs through controlled workflows while preserving certificate validation. **Never disable TrustManager/HostnameVerifier** just to "make the new image work".

### 15.3. mTLS

For mutual TLS, verify client keys, certificate chains, filesystem permissions, and secret rotation. Never bake production private keys into image layers or print passwords in build logs.

## 16. Timezone, locale, and charset

A runtime image can shift the default timezone or lack complete timezone/locale datasets. Effects include:

- Scheduled batch jobs firing off-schedule.
- Log timestamps differing from expectations.
- Wrong offsets in date/time serialization.
- Altered Unicode strings or file encodings.
- Changed number/date formatting.
- Historical data replays yielding altered results.

### 16.1. Specify explicit timezones for contracts

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime now = ZonedDateTime.now(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

This merely illustrates an explicit ZoneId; choose the timezone required by business logic. Cross-system event timestamps should generally carry explicit UTC/offset representations rather than trusting container defaults.

### 16.2. ENV TZ vs. JVM timezone

~~~dockerfile
ENV TZ=UTC
~~~

and:

~~~text
-Duser.timezone=UTC
~~~

are distinct mechanisms. Exact behavior depends on the JDK, OS config, and application code. Verify `ZoneId.systemDefault()` and business logic outputs rather than trusting one env variable alone.

### 16.3. Charset

Default charsets can change across JDK upgrades. Starting in Java 18, UTF-8 became the standard default charset under JEP 400 within its specified scope.

Specify encodings explicitly at I/O boundaries:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
    Path.of("/app/data/message.txt"),
    StandardCharsets.UTF_8
);
~~~

Never treat a base image's default locale/charset as an API contract for business data.

## 17. Fonts, Java2D, and headless mode

Even a headless backend uses fonts when generating PDFs, Excel files, images, barcodes, templates, or measuring text bounds. Minimal images often omit fontconfig, freetype, or font families.

Symptoms:

- PDFs drop Vietnamese diacritics.
- Glyph substitution garbles text.
- Layouts/tables misalign.
- Native font subsystem errors.
- Image rendering differs between staging and production.

### 17.1. Headless mode does not supply fonts

~~~text
-Djava.awt.headless=true
~~~

does not install fonts or native text-rendering libraries. Bundle properly licensed fonts/resources into the image and test against Vietnamese text, emoji, currency symbols, and all supported languages.

## 18. DNS, networking, and proxies

Image and native resolver configurations shape DNS behavior. In Kubernetes, CoreDNS, network policies, service discovery, and proxies also factor in.

Symptoms:

- UnknownHostException only inside new containers.
- Slow DNS lookups.
- Changed IPv4/IPv6 preferences.
- TLS routing changes through proxies.
- Missing native DNS resolver libraries.

Isolate failures by layer:

~~~text
Hostname
   |
   v
DNS resolution
   |
   v
TCP connection
   |
   v
TLS handshake
   |
   v
HTTP/JDBC/application protocol
~~~

Never fix network issues by installing random OS packages or disabling TLS verification. Pinpoint the failing layer using logs, traces, and tests along **the same network path** as production.

## 19. Cgroups and JVM container awareness

Container runtimes typically constrain CPU/memory via cgroups. Modern JDKs feature container awareness, yet exact calculation rules depend on JDK vendor/version and cgroup v1/v2.

### 19.1. Heap is not total container memory

~~~text
Container memory limit
    |
    +--> Java heap (-Xmx)
    +--> Metaspace
    +--> Thread stacks
    +--> Code cache
    +--> DirectByteBuffer/off-heap
    +--> JNI/JNA allocations
    +--> Mapped files
    +--> Native agents
    +--> JVM native runtime
~~~

If a memory limit is 1 GiB and -Xmx=1g, process RSS can exceed the limit due to non-heap and native allocations. Containers can suffer OOM kills before the Java heap fills up.

### 19.2. MaxRAMPercentage

For supporting JDKs/HotSpot builds:

~~~text
-XX:MaxRAMPercentage=65.0
~~~

is an example percentage, not a universal optimum. Reserve headroom for threads, metaspace, direct memory, and native allocations.

### 19.3. CPU quota and processor count

The JVM can size GC/JIT thread pools and runtime scheduling using CPU limits visible via cgroups.

~~~java
System.out.println(
    Runtime.getRuntime().availableProcessors()
);
~~~

Check CPU quotas, requests/limits, thread pools, and workloads. Migrating a service from amd64 to arm64 with identical nominal vCPU counts does not guarantee identical throughput.

### 19.4. Distinguish OOMKilled from OutOfMemoryError

When the kernel/cgroup kills a container, no Java heap dump may be written. Exit code 137 often reflects SIGKILL, though runtime/container events must confirm the reason. Java heap OutOfMemoryError and total-memory OOM kills have different causes.

## 20. PID 1, signals, and graceful shutdown

Production containers must handle SIGTERM, grace periods, and clean lifecycle teardown.

### 20.1. Exec-form ENTRYPOINT

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

normally lets the JVM receive signals directly. Shell form can interpose a shell and disrupt signal forwarding; if wrapping with scripts, verify `exec` usage and init processes.

### 20.2. Clean shutdown

Upon receiving termination signals, an application should:

1. Stop accepting new work.
2. Drain in-flight requests/messages within timeouts.
3. Close connections, pools, and thread executors.
4. Release owned JNI/JNA/native callbacks cleanly.
5. Flush logs/traces while time remains.
6. Exit before the container grace period expires.

Shutdown hooks cannot guarantee cleanup completes if SIGKILL arrives. Test shutdown while active work and native resources are running.

### 20.3. Readiness differs from liveness

A Java process may be alive yet unready for traffic while loading models or initializing database connections. Never treat "process alive" alone as proof of readiness.

## 21. Image security and software supply chain

Base images, OS packages, JDK vendors, native binaries, and application code all form part of the supply chain.

Practices to enforce:

- Pick trusted image sources with clear support policies.
- Record tags and digests.
- Pin and verify dependency versions.
- Scan vulnerabilities, including native libraries.
- Generate SBOMs/provenance where policy requires.
- Ensure builds never leak secrets into image layers.
- Never install OS packages dynamically at container startup.
- Run non-root and drop unnecessary capabilities.
- Update and re-test base images continuously; never pin digests forever without updates.
- Track security advisories from both the JDK vendor and OS distribution.

### 21.1. CVE scanners have limits

Scanners may flag unused OS packages or miss a manually copied .so file lacking package metadata. Triage findings against vendor advisories, actual exposure, and runtime reachability.

Images with fewer OS packages are not automatically vulnerability-free. Both the Java runtime and app dependencies still require active management.

### 21.2. Reproducible builds

Record the source commit, Dockerfile version, base digest, JDK version, dependency graph, native compiler versions, target platform, and output image digest. Relying purely on mutable tags makes reproducing an incident weeks later difficult.

## 22. Debugging minimal production images

Distroless images may exclude bash, curl, ldd, ps, or keytool. Adding debugging tools directly into production images is rarely the best fix.

Alternatives:

- Diagnostic images holding identical artifacts/native libraries.
- Ephemeral debug containers.
- JFR/JMX/metrics/logging.
- Build-stage static inspection.
- Access-controlled core dump/heap dump pipelines.
- Tool-equipped staging image variants for analysis.
- CI inspection of image filesystems and digests.

However, **at least one integration test pass must run against the final production image**, not solely the JDK builder image, which may contain packages missing at runtime.

## 23. Diagnostic flow when an app fails only in containers

~~~text
Image platform matches?
       |
       +-- No --> Wrong manifest/native binary
       |
       v
JVM starts?
       |
       +-- No --> JDK/loader/libc/permissions
       |
       v
App loads classes?
       |
       +-- No --> Bytecode release/modules/classpath
       |
       v
Native libraries work?
       |
       +-- No --> ABI/symbol/dependency/path
       |
       v
TLS/DNS/config work?
       |
       +-- No --> Truststore/proxy/network
       |
       v
Business flow and graceful shutdown?
       |
       +-- No --> Application lifecycle/runtime behavior
       |
       v
Performance/observability meet targets?
~~~

### 23.1. Confirm the actual running image

Do not inspect only the Dockerfile in Git. Verify:

- Exact image digest pulled by the node.
- Platform-specific manifest selected.
- Actual Java version/vendor.
- Effective entrypoint and JVM options.
- Mounted secrets/volumes.
- User ID and filesystem permissions.
- Container memory/CPU limits.
- Application artifact version.

A staging container and a production container using the same mutable tag may hold different image contents.

### 23.2. Runtime diagnostics

~~~bash
java -version
java -XshowSettings:properties -version
~~~

On supporting JDKs:

~~~bash
java -XshowSettings:system -version
~~~

can report container/cgroup metrics. Interpret output for your exact JVM version. Compare Java os.arch, uname, and manifest platform carefully since names differ across tools.

## 24. Case: migrating a glibc library onto Alpine

Before migration:

~~~text
JDK 11 + Debian base + libimage.so (glibc)
~~~

After migration:

~~~text
JDK 21 + Alpine base + libimage.so (still glibc)
~~~

The application can fail with UnsatisfiedLinkError or missing loader/symbol errors.

**Resolution:** inspect ABI with readelf, check the native library's support matrix, use an official musl build if staying on Alpine, or return to a glibc-based runtime. Never treat tweaking `java.library.path` as an ABI fix.

## 25. Case: multi-arch base image yet JNI only ships x86-64

Before: application runs on linux/amd64. After: deployment expands to linux/arm64.

The base image provides both manifests, while a dependency packages native/linux-x86_64/libcodec.so only.

Resolution:

1. Inventory all JNI/JNA/classifier packages.
2. Verify ARM64 builds exist for each library.
3. Build/package using matching TARGETARCH.
4. Inspect per-platform images.
5. Run native integration tests on real ARM64 hardware.
6. Compare CPU/GC performance and error rates.
7. Roll out across node architectures with monitoring.

If no ARM64 variant exists, replace the library or do not claim ARM64 support.

## 26. Case: CA or mTLS failures on minimal runtimes

The old JDK image held custom CAs, while the new JRE/distroless image omits that truststore. HTTPS or database TLS throws PKIX path building failed.

Resolution:

- Identify the active truststore.
- Validate certificate chains and hostnames.
- Mount/configure internal CAs via approved procedures.
- Confirm the runtime UID can read the truststore/keystore.
- Review JDK security policies.
- Re-test against the exact target endpoint/network path.

Never disable certificate validation just to "restore compatibility".

## 27. Case: image missing fonts and timezone data

A service generates invoice PDFs and schedules jobs by local time. The minimal image boots cleanly, yet PDFs drop Vietnamese diacritics and jobs fire at wrong hours.

Resolution:

- Identify required font and glyph coverage.
- Check fontconfig/freetype and native rendering dependencies.
- Package properly licensed fonts into the image.
- Use explicit `ZoneId` values in business logic.
- Verify tzdata/runtime timezone configuration.
- Maintain regression fixtures for PDFs and schedules.

Clean JVM startup does not guarantee correct business behavior.

## 28. Case: heap has headroom yet pod gets OOMKilled

GC metrics show low post-GC heap usage, while Kubernetes reports OOMKilled. Direct buffers, JNI allocations, thread stacks, or agent memory may be exhausting container memory headroom.

Investigate cgroup memory, RSS/native memory, JVM heap bounds, and native library consumption. Never raise `-Xmx` up to the container limit, starving non-heap regions further.

## 29. Case: restarts hang on SIGTERM

The container uses shell-form entrypoint while the Java service holds native background threads and connection pools. SIGTERM either never reaches the JVM or cleanup outlasts the grace period.

Resolution:

- Use exec-form entrypoint or wrapper `exec`.
- Implement bounded draining/cancellation timeouts.
- Explicitly close native resources.
- Test shutdown under active in-flight traffic.
- Align with termination grace periods.
- Never assume every shutdown hook always finishes in time.

## 30. Test matrix when changing base images

| Java | OS/libc | Platform | Test scope |
|---|---|---|---|
| Old JDK | Old base/glibc | linux/amd64 | Baseline |
| New JDK | Same OS family | linux/amd64 | Isolate JDK impact |
| New JDK | Minimal runtime | linux/amd64 | Detect missing OS/runtime dependencies |
| New JDK | New glibc image | linux/arm64 | Native architecture compatibility |
| New JDK | musl image if supported | linux/amd64 | libc compatibility |
| New JDK | Final production image | Real target | Integration/end-to-end |
| New JDK | Final image + agents | Real target | JVMTI/JNI/observability |

Not every matrix cell must be supported. Select combinations matching support policies and migration paths, testing every committed target platform.

### 30.1. Artifact verification

- Image index contains expected platforms.
- Correct JDK major/update/vendor.
- App classes match target Java release.
- Native binaries match OS/CPU/libc.
- Dynamic dependencies resolve and symbols exist.
- No build-host native binaries leaked into target images.
- Entrypoint/user/permissions configured properly.
- Base image digest recorded.

### 30.2. Business functionality testing

- Startup, readiness, liveness.
- TLS/mTLS, DNS/proxies.
- Databases/message brokers.
- Charset/timezone/locale handling.
- Fonts/PDF/image rendering where applicable.
- JNI/JNA/JVMTI native calls.
- CPU/heap/off-heap behavior under load.
- Graceful shutdown.
- Crash logs/JFR/metrics.
- Rollback.

### 30.3. Negative tests

Deliberately test cases that must reject or fail safely:

- Wrong-architecture native binary.
- Untrusted certificate.
- Missing secret or truststore.
- Write attempt on read-only filesystem.
- Missing required native dependency.
- Requested platform missing manifest.
- CPU/memory limits below minimum thresholds.

Negative tests uncover silent fallbacks or unsafe error handling.

## 31. Phased migration workflow

### Step 1 — Inventory before changing anything

Document the legacy base image, JDK version, libc/OS, architecture, JARs/dependencies, JNI/JNA/JVMTI artifacts, CAs, fonts, timezone, native clients, logging, and resource limits.

### Step 2 — Choose explicitly supported targets

Define target runtime JDK, distro family, libc, target architectures, and vendor support. Never pick an image solely because it is small or popular.

### Step 3 — Upgrade the JDK within the same OS family when possible

Hold architecture and libc largely steady first to validate Java/framework/agent compatibility.

### Step 4 — Trim build and runtime stages

Separate JDK builds from JRE runtimes; when using jlink/distroless, verify modules, native libraries, CAs, timezones, fonts, temp dirs, and diagnostic tooling.

### Step 5 — Change libc or add architectures deliberately

Treat this as a dedicated native-compatibility phase. Build per platform, pick proper classifiers, and verify exported symbols/ABI.

### Step 6 — Package and record provenance

Pin digests, capture SBOMs, native artifacts/toolchains, and both index and per-platform digests. Keep secrets out of layers.

### Step 7 — Test the final image

Run integration tests against the final image under matching permissions, mounted files, CPU/memory limits, and network dependencies.

### Step 8 — Canary rollout

Monitor startup failures, native crashes, TLS, DNS, latency, RSS/off-heap, CPU, GC, container restarts, and shutdown behavior. Roll out per node/architecture group where appropriate.

### Step 9 — Coordinated rollback readiness

Keep prior image digests, runtime/config/secret policies, and backward readability for any data written by the new release. Rollback is not just swapping JDKs if new images wrote incompatible data formats.

### Step 10 — Retire legacy exceptions

Remove compatibility shims, legacy native binaries, and temporary flags once no longer needed. Update runbooks and patching schedules for the new base image.

## 32. Reference CI/CD pipeline

~~~text
Source commit + dependency lock
          |
          v
Compile JAR + unit tests
          |
          v
Build per-platform image
          |
          v
Inspect image manifests / native symbols
          |
          v
Security scan / SBOM / provenance
          |
          v
Integration tests on target platforms
          |
          v
Publish immutable image digest
          |
          v
Canary deployment
          |
          v
Measure + rollout or rollback
~~~

A green `buildx push` does not prove every architecture variant passed integration tests. Verify test results explicitly per supported platform.

## 33. Common misconceptions

### "Java is write once, run anywhere, so architecture doesn't matter"

Java bytecode can be portable, while the JVM, JNI/JNA libraries, and native agents still must match OS/CPU/ABI.

### "A multi-arch base image makes the application multi-arch"

False if the JAR embeds native artifacts compiled for only one CPU architecture.

### "A JRE always has everything a JDK image has"

Not guaranteed. JREs/custom runtimes may omit tools, modules, and OS dependencies.

### "Alpine is always best because it's small"

No blanket rule holds. Musl may fail to load an app's glibc-built native binaries.

### "Just fixing java.library.path eliminates UnsatisfiedLinkError"

False when the binary targets the wrong architecture, misses transitive libraries, or mismatches ABI.

### "An unchanged Dockerfile means an unchanged image"

False with mutable tags and unpinned dependency resolution.

### "Distroless having no shell means you cannot debug"

You can use diagnostic images, JFR/metrics, ephemeral debug containers, and out-of-image workflows when planned ahead.

### "Non-root only requires adding USER"

Insufficient. Secrets, volumes, temp dirs, and native library extraction permissions also need checking.

### "Container memory limit equals heap limit"

False. Native/off-heap allocations, thread stacks, and JVM overhead also consume container memory.

### "Having OS CA certificates guarantees Java trusts them"

False across several distros/JDKs. Inspect the active Java truststore directly.

### "QEMU tests are enough to commit to ARM64 production"

Not always. Test native behavior and performance on real ARM64 hardware when ARM64 is a target.

### "A successful docker build finishes migration"

False. TLS, DNS, native loaders, timezones, fonts, resource limits, and shutdown can still fail at runtime.

## 34. Container compatibility assessment record template

~~~text
APPLICATION
  Service:
  Owner:
  Java compiler release:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  App artifact hash:
  Main/JVM flags:

IMAGE
  Current tag/digest:
  Target tag/digest:
  Distro/version:
  libc/version:
  JDK/JRE/jlink/distroless:
  Support/patch policy:

PLATFORM
  linux/amd64:
  linux/arm64:
  Other target OS:
  CPU instruction baseline:
  Kernel/cgroup assumptions:

NATIVE DEPENDENCIES
  JNI/JNA:
  JVMTI/APM agent:
  Native codec/database/HSM:
  libstdc++/libgcc:
  OpenSSL/crypto:
  ABI and dynamic dependencies:
  Per-platform artifacts:

RUNTIME DATA
  CA/truststore:
  mTLS keys:
  DNS/proxy:
  Timezone/locale:
  Fonts:
  Temporary directories:
  File permissions:

SECURITY
  Non-root UID/GID:
  Read-only root:
  Secrets mount:
  Capabilities:
  Vulnerability scan:
  SBOM/provenance:

RESOURCES
  Memory limit:
  Heap max:
  Direct/native memory:
  CPU quota:
  Thread settings:
  GC/metrics:

VALIDATION
  Startup:
  Native loading:
  TLS/DNS:
  Database/message broker:
  Data/time/encoding:
  Font/rendering:
  Load/stress tests:
  SIGTERM/shutdown:
  Per-platform tests:
  Canary/rollback:

DECISION
  Approved image digest:
  Owner:
  Risks/exceptions:
  Rollback digest:
  Next patch milestone:
~~~

Store this record alongside image digests and build provenance so production issues can be reproduced accurately.

## 35. Release checklist

- [ ] Verified JDK vendor/version/build and artifact Java release.
- [ ] Verified base image distribution, libc, and immutable digest.
- [ ] Verified manifests for every target architecture.
- [ ] Checked every JNI/JNA/JVMTI library matches the target platform.
- [ ] Checked native loaders, exported symbols, and transitive dependencies.
- [ ] Confirmed no unintended glibc/musl mismatches.
- [ ] Verified CPU instruction baseline.
- [ ] Confirmed runtime modules suffice when using jlink.
- [ ] Verified CA/truststore/mTLS configs and read permissions.
- [ ] Verified timezone, locale, charset, and fonts match business needs.
- [ ] Verified DNS/proxy/TLS/network paths work end-to-end.
- [ ] Verified non-root container user and filesystem permissions.
- [ ] Verified temp/native extraction aligns with noexec/read-only rules.
- [ ] Verified ENTRYPOINT handles termination signals and shuts down within grace limits.
- [ ] Verified heap/off-heap/native memory leaves cgroup headroom.
- [ ] Verified observability/JFR/GC logging configurations.
- [ ] Ran integration tests against the final production image.
- [ ] Tested ARM64 on real ARM64 hardware when arm64 is supported.
- [ ] Completed security scans/SBOM/provenance per policy.
- [ ] Prepared canary rollout and digest-pinned rollback steps.

## 36. Summary

The container base image is an essential part of the compatibility contract when upgrading Java. Switching from a JDK image to JRE/distroless, Debian to Alpine, or amd64 to arm64 can break applications even when Java source never changed and builds passed.

Key principles to remember:

1. **Separate Java compatibility from native/OS compatibility.** Compatible class files do not validate .so/.dll binaries, libc, or JNI ABIs.
2. **Choose images by actual dependencies.** JDK/JRE tooling, CAs, timezones, fonts, OS packages, and native agents all matter.
3. **Verify target architecture down to each native binary.** Multi-arch base manifests do not automatically make an app multi-arch.
4. **Manage artifacts via digests and provenance.** Mutable tags are no substitute for immutable artifact identity.
5. **Respect container resource limits.** Heap is only part of memory; cgroups and CPU quotas govern JVM behavior.
6. **Minimize intentionally.** Non-root users, read-only filesystems, jlink, and distroless require companion testing and diagnostic workflows.
7. **Limit variables changed per migration.** Upgrading JDKs, changing distro/libc, trimming images, and adding ARM64 each carry distinct risks.
8. **Test the final image on target platforms.** Startup, native calls, TLS, data handling, throughput, and graceful shutdown must all be proven.

A reliable migration produces more than an image sporting a newer Java label. It delivers an artifact tailored to the committed OS and CPU architecture, bundling all required system libraries, ready for security patching, operationally stable, and safely rollback-ready when needed.
