# Dynamic Linking, Static Linking, and Conditions for Using glibc or musl

## 1. Why Choose a Linking Mode?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT analyzes application structure and GraalVM Native Image compiles reachable code into an executable for the target operating system and architecture. This executable can still depend on system native libraries such as the C library, zlib, libgcc, or third-party SDK libraries.

When deploying Linux containers, you must decide whether those native libraries are loaded from the OS at runtime or linked into the binary at build time. This decision affects:

- which libraries and dynamic loader must exist in the runtime image;
- compatibility with Debian/Ubuntu, Red Hat, Alpine, distroless, or `scratch`;
- ABI compatibility between build and runtime environments;
- executable and container image size;
- how system libraries are updated and security vulnerabilities patched;
- the ability to use JNI or third-party native libraries.

GraalVM Native Image supports three common Linux deployment modes:

| Linking Mode | C Library | Other Native Libraries | Suitable Runtime |
| --- | --- | --- | --- |
| Dynamic | Dynamically loaded, typically glibc | Can be dynamically loaded | Linux image providing the matching glibc and shared libraries |
| Mostly static | glibc still loaded dynamically | Statically links libraries supported by the toolchain | Image with glibc, such as Debian-based distroless |
| Fully static | Statically linked against musl | Statically links required libraries | Can run in `scratch` if the app needs no external files/runtime resources |

Key point: **Native Image builds dynamically linked binaries by default**. If you need a fully static binary on Linux, GraalVM supports that with musl. Statically linking glibc via `--static` is not supported by Native Image.

## 2. How Does Dynamic Linking Work in ELF?

On Linux, executables normally use the ELF (Executable and Linkable Format). A dynamically linked binary contains metadata telling the kernel to invoke a dynamic loader, which then locates and loads the required shared objects (`.so`).

General startup flow:

~~~mermaid
flowchart TB
    A["Container starts native executable"] --> B["Kernel reads ELF header"]
    B --> C{"ELF has PT_INTERP?"}
    C -->|Yes| D["Start dynamic loader"]
    D --> E["Resolve DT_NEEDED shared libraries"]
    E --> F["Map libraries and resolve symbols"]
    F --> G["Enter native application"]
    C -->|No| H["Start statically linked executable"]
    H --> G
~~~

Two ELF entries commonly checked:

- `PT_INTERP`: path to the dynamic loader, e.g., `/lib64/ld-linux-x86-64.so.2`.
- `DT_NEEDED`: list of shared libraries the binary must load.

With a dynamically linked binary, copying only the executable into a container without a dynamic loader or missing `.so` dependencies prevents the process from starting. Error messages sometimes report the executable file was not found even though it exists; the cause can be that the interpreter in `PT_INTERP` is missing.

## 3. Distinguishing Java Linking from Native Linking

Before choosing a libc, distinguish two concepts:

| Concept | When It Happens | Components Involved |
| --- | --- | --- |
| Spring AOT | Build time | `ApplicationContext`, bean definitions, generated code, and runtime hints |
| Native Image analysis/compilation | Build time | Java bytecode, reachability, and native code |
| Native dynamic linking | When the executable starts | ELF loader, libc, and shared libraries |
| Native static linking | When the executable is created | Object files and static archives (`.a`) merged into the binary |

Static linking does not mean Java classes are dynamically loaded. Native Image has already processed Java code under closed-world analysis earlier. Choosing glibc/musl determines only the ABI and how the executable links against the C library and native dependencies.

Similarly, adding reflection runtime hints cannot fix a missing `libc.so`, and switching to musl cannot fix Spring AOT reflection/resource errors.

## 4. What Is glibc?

**glibc** (GNU C Library) is the standard C library across many Linux distributions such as Debian, Ubuntu, Fedora, Red Hat Enterprise Linux, Oracle Linux, and Amazon Linux.

glibc provides foundational APIs commonly used by native code:

- process, thread, and synchronization handling;
- memory allocation;
- file, socket, and system-call wrappers;
- DNS/name service integration;
- locales and system runtime utilities.

Native Image on Linux defaults to producing binaries dynamically linked against glibc. This is the right fit when the runtime container already uses glibc and the application's JNI/native dependencies are also built for glibc.

### 4.1. glibc Version Compatibility

A dynamically linked binary can require a specific glibc symbol version. Building on a newer system and running in an older runtime image can trigger:

~~~text
version 'GLIBC_2.xx' not found
~~~

This occurs because the runtime glibc lacks the symbol version required by the binary. A safe deployment practice is building on a glibc baseline equal to or older than the lowest supported runtime environment, then inspecting the executable's symbol requirements.

Do not rely solely on distribution names. Two images from the Debian family can carry different glibc versions across releases.

### 4.2. Benefits and Constraints

| Benefits of glibc | What to Control |
| --- | --- |
| Compatible with most common Linux server images | Minimum glibc version required by the binary |
| Many SDK/JNI vendors ship binaries built for glibc | Vendor ABI and shared-library dependencies |
| Familiar ecosystem of locales, NSS, and system tools | Runtime image must contain loader, libc, and required `.so` files |
| libc can be patched via OS packages | Must re-test the application after updating system libraries |

If a vendor ships a native library only for glibc, choose a glibc runtime. You cannot take a glibc shared library and assume it will load in a musl environment just because both are libc implementations.

## 5. What Is musl?

**musl** is a C standard library implementation for Linux designed to be compact, simple, and standards-focused. Alpine Linux uses musl as its default libc.

musl is typically considered when:

- you want a fully static native executable;
- you want a very small runtime container or `scratch`;
- all native dependencies can be built/linked compatibly with musl;
- you have tested any behavioral differences the application relies on.

### 5.1. musl Is Not Just Renamed glibc

Both libcs share many similar APIs, yet their ABIs and certain behaviors differ. An `.so` built for glibc is not automatically compatible with musl. Native libraries must be rebuilt for musl or replaced with a compatible implementation.

Areas requiring testing:

- JNI/native SDKs and C/C++ dependencies;
- DNS resolver, hostname lookup, and network configuration;
- locales, collation, and locale-dependent data formatting;
- timezones and zoneinfo data;
- thread, signal, and system-call behavior used by native dependencies;
- libraries relying on glibc-specific APIs or `dlopen`.

Do not conclude an application is musl-compatible just because an HTTP smoke test passed. Exercise paths that actually invoke database drivers, compression, crypto, image processing, or JNI if present.

### 5.2. Platform Support Conditions

Static musl builds depend on the GraalVM distribution and the target's native toolchain. Current GraalVM guidance on static executables specifies requirements such as Linux x64, GraalVM JDK 17 or later, a 64-bit musl toolchain, and compatible zlib.

Support also varies by architecture and version. Current GraalVM Compatibility Guides explicitly state that musl is not yet supported for Native Image on Linux AArch64. If targeting ARM64, check the support matrix for your exact GraalVM release before choosing musl.

## 6. Three Linking Modes in GraalVM Native Image

### 6.1. Default Dynamic Linking

Standard build:

~~~bash
native-image -jar target/billing-service.jar billing-service
~~~

Native Image builds a binary dynamically linked against required system libraries. On Linux, the default configuration normally uses glibc.

You can select libc explicitly for clearer build configuration:

~~~bash
native-image --libc=glibc \
  -jar target/billing-service.jar \
  billing-service
~~~

The runtime image needs the dynamic loader, glibc, and every shared library listed in the ELF. `ldd` helps inspect the actual dependency list.

### 6.2. Mostly-Static with --static-nolibc

Mostly-static statically links native libraries that Native Image can link except `libc`. Under the default Linux glibc configuration, glibc remains dynamically loaded at runtime while libraries such as zlib and several JDK native libraries are statically linked.

Build:

~~~bash
native-image --static-nolibc \
  -jar target/billing-service.jar \
  billing-service
~~~

This binary still requires a runtime providing glibc and the dynamic loader. It fits glibc-based images, including some distroless images, when reducing remaining shared-library dependencies.

Depending on code and toolchain, the executable may still require dynamic `libstdc++` or `libgcc`. Therefore, do not infer behavior from the `--static-nolibc` name alone; run `ldd` on the actual binary.

### 6.3. Fully Static with musl

To build an executable statically linked against musl:

~~~bash
native-image --static --libc=musl \
  -jar target/billing-service.jar \
  billing-service
~~~

Prerequisites:

- building on a supported Linux target;
- a GraalVM Native Image version supporting musl on that architecture;
- musl toolchain and compiler wrapper available on `PATH`;
- required static libraries present, including zlib per toolchain instructions;
- all native dependencies used by the application able to statically link compatibly.

Static glibc is not supported by Native Image via `--static`. If your target is a glibc runtime while reducing other shared libraries, use `--static-nolibc`.

## 7. Comparing the Three Modes

| Criterion | Dynamic glibc | Mostly-static glibc | Fully-static musl |
| --- | --- | --- | --- |
| How selected | Default or `--libc=glibc` | `--static-nolibc` | `--static --libc=musl` |
| C library at runtime | Dynamic glibc | Dynamic glibc | Statically linked musl |
| Other native libraries | May need `.so` files | Mostly statically linked if toolchain provides archives | Statically linked if compatible archives exist |
| Runtime image | Contains loader, glibc, and dependent `.so` files | Contains loader and glibc | Can use `scratch` |
| Native dependency shipped only for glibc | Usually fits | Usually fits if dependency links cleanly | Not directly compatible |
| Executable size | Usually smaller than fully static | May be larger than dynamic | Can be larger due to bundled libraries |
| Updating libc | Updated in the runtime image | glibc updated in the runtime image | Must rebuild binary to pick up newer musl |
| Runtime flexibility | Depends on system libraries | Depends on glibc | Minimal dependence on host native libraries |

No single mode is always fastest or smallest. Static linking can enlarge the executable; dynamic linking can share libraries already present in the OS. Measure startup, RSS, image size, and performance under real workloads.

## 8. Choosing glibc vs. musl by Deployment Requirements

### 8.1. Choose Dynamic glibc When

- the runtime image is Debian, Ubuntu, Red Hat, Oracle Linux, or a glibc-based distribution;
- SDK/JNI vendors provide `.so` files for glibc;
- the application needs native dependencies relying on glibc-specific APIs;
- you want OS package updates to patch libc without rebuilding the app;
- the team already standardizes on glibc runtime images and diagnostic tooling.

This is usually the easiest option to integrate for Spring Boot applications with many drivers and external libraries already tested on glibc Linux.

### 8.2. Choose Mostly-Static glibc When

- you want fewer shared libraries beyond libc;
- the runtime is Debian-based distroless or a minimal glibc image;
- you want optional `.so` libraries statically linked away;
- you still need the glibc ABI and glibc-compatible JNI libraries.

Verify with `ldd` what the runtime still requires. `--static-nolibc` does not make the executable runnable in `scratch`, since it still needs glibc and the dynamic loader.

### 8.3. Choose Fully-Static musl When

- you need an executable capable of running in `scratch`;
- you want zero dependency on glibc in the runtime image;
- all JNI/native dependencies can build for musl or link statically;
- DNS, locales, timezones, TLS, and native libraries have been tested on the target environment;
- the target OS/architecture is supported by your GraalVM version.

If the application depends on a vendor `.so` shipped strictly for glibc, do not choose static musl until a compatible vendor build exists.

## 9. Preparing the musl Toolchain

Native Image does not bundle all compilers and static system libraries required for musl. The build machine needs a compatible toolchain.

Per GraalVM guidelines, static builds require:

- Linux x64 in the documented configuration;
- a GraalVM distribution with Native Image;
- a 64-bit musl toolchain;
- `make` and `configure`;
- compatible zlib, including the required static archive.

After installing the toolchain per GraalVM documentation, check the compiler wrapper:

~~~bash
which x86_64-linux-musl-gcc
x86_64-linux-musl-gcc --version
~~~

Exact executable names depend on the toolchain. Some toolchains provide `musl-gcc`; toolchains recommended by GraalVM may provide target-prefixed names like `x86_64-linux-musl-gcc`.

Verify the zlib static archive and headers exist in the toolchain's sysroot. Do not check only `gcc --version`: the host's default compiler may still point to glibc.

Pin the toolchain, GraalVM, and target architecture in CI so builds stay reproducible. Never mix glibc headers with musl static libraries in the same native build.

## 10. Configuring Maven Native Build Tools

Linker options can be passed via `native-maven-plugin`. Mostly-static glibc example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--static-nolibc</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Fully static musl example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--static</buildArg>
            <buildArg>--libc=musl</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Use only one mode matching the runtime target in a build profile. If the POM already configures `buildArgs`, merge options into the existing block instead of creating duplicate plugin executions.

Build using the project's profile/plugin:

~~~bash
./mvnw -Pnative native:compile
~~~

The `native` profile is a common convention, though it must actually exist in your POM. Verify the effective POM and Native Build Tools version; supported options depend on the GraalVM release.

## 11. Configuring Gradle Native Build Tools

Kotlin DSL example for mostly-static glibc:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--static-nolibc")
        }
    }
}
~~~

Kotlin DSL example for fully static musl:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--static")
            buildArgs.add("--libc=musl")
        }
    }
}
~~~

Then run:

~~~bash
./gradlew nativeCompile
~~~

With Groovy DSL or other plugin versions, binary/task access syntax may differ. Check the project's plugin version and task list. A musl build must run in an environment with a matching musl toolchain and static libraries.

## 12. Choosing the Runtime Container

### 12.1. Dynamic glibc

Use a runtime image with compatible glibc and dynamic loader. Debian slim example:

~~~dockerfile
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY billing-service /app/billing-service

USER 65532:65532
ENTRYPOINT ["/app/billing-service"]
~~~

The base image must contain every `.so` reported as needed by `ldd`. If the binary was built against a newer glibc than the one in this Debian release, symbol-version errors can still occur; confirm the baseline.

### 12.2. Mostly-Static glibc

A minimal glibc image or Debian-based distroless works well. Example runtime frame:

~~~dockerfile
FROM gcr.io/distroless/base-debian12:nonroot

COPY billing-service /app/billing-service

ENTRYPOINT ["/app/billing-service"]
~~~

Distroless images omit a shell and package manager. Confirm the binary matches the glibc version and all remaining libraries are statically linked. If the binary still needs `libstdc++`, `libgcc`, or other libraries, the runtime image must provide them or the build must be adjusted.

### 12.3. Fully Static musl

A fully static binary can run in `scratch`:

~~~dockerfile
FROM scratch

COPY billing-service /app/billing-service
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

USER 65532:65532
ENTRYPOINT ["/app/billing-service"]
~~~

The CA bundle path must be copied from a stage with `ca-certificates` installed or from a prepared artifact. `scratch` contains no CA certificates, timezone files, shell, user database, or diagnostic utilities.

A static binary may still require external runtime resources:

- CA bundle for HTTPS/TLS;
- mounted configs and runtime secrets;
- timezone files or locale data if required by the application;
- a writable temporary directory if used by the application;
- config files, templates, or native resources meant to be mounted.

Fully static only eliminates native shared-library dependencies; it does not automatically embed OS files or application data.

Static linking also does not remove compatibility requirements with the target kernel and CPU. The executable still issues Linux system calls and is built for a specific architecture. Verify kernel baseline, architecture, and CPU features on the node/container runtime; a fully static x86-64 binary still cannot run on ARM64.

## 13. Inspecting the Binary After Building

Do not select a runtime image based purely on build flag names. Inspect the actual ELF artifact.

### 13.1. Checking Format and Architecture

~~~bash
file billing-service
~~~

Verify the binary is an ELF executable for the right architecture, such as x86-64 or AArch64. Static linking does not let an x86-64 binary run on ARM64.

### 13.2. Checking the Dynamic Loader

~~~bash
readelf -l billing-service | grep -i interpreter
~~~

If a `Requesting program interpreter` line appears, the executable requires a dynamic loader. If fully static, `PT_INTERP` is normally absent.

### 13.3. Checking Shared-Library Dependencies

~~~bash
readelf -d billing-service | grep NEEDED
ldd billing-service
~~~

Run `ldd` only on executables you built yourself or trusted artifacts. Running `ldd` on an untrusted binary can invoke the dynamic loader unsafely.

Typical results:

- Dynamic glibc: multiple `NEEDED` entries, including libc and other `.so` files.
- Mostly-static glibc: dynamic loader/libc still present; `libstdc++` or `libgcc` may remain depending on code.
- Fully-static musl: `ldd` typically reports `not a dynamic executable`; the ELF has no dynamic interpreter and no dynamic `NEEDED` libraries.

### 13.4. Checking glibc Symbol Versions

For dynamically linked glibc binaries:

~~~bash
readelf --version-info billing-service | grep GLIBC_
~~~

The symbol version list reveals the minimum glibc requirement. Compare against the actual runtime image, not only the build machine.

## 14. Resources Still Needed at Runtime

Choosing static linking does not replace Native Image resource configuration or OS configuration.

For example, an application making HTTPS calls:

- the binary needs no `libc.so` when fully static musl;
- yet it still needs CA certificates to verify servers;
- it still needs the container's DNS resolver and network configuration;
- it still needs valid hostnames and certificate chains.

An application using timezones:

- must verify whether timezone data comes from the JDK image or the OS;
- must test zone IDs and daylight-saving transitions;
- must not assume `scratch` includes `/usr/share/zoneinfo`.

An application using fonts, templates, or config files:

- embeds resources into Native Image if appropriate and registered via metadata;
- or copies/mounts files per the deployment contract;
- checks paths and permissions inside the runtime container.

This is why a fully static binary can start cleanly in a minimal test container yet fail when executing real business logic.

## 15. Testing glibc and musl Compatibility

A helpful test matrix:

| Build Mode | Runtime | What to Verify |
| --- | --- | --- |
| Dynamic glibc | Same glibc baseline | Loader, `.so` files, symbol versions, and TLS |
| Dynamic glibc | Newer glibc | ABI compatibility and native dependencies |
| Dynamic glibc | Older glibc | No missing `GLIBC_x.y` symbols |
| Mostly-static glibc | Debian-based distroless | glibc/loader present; no missing remaining `.so` files |
| Fully-static musl | `scratch` | No dynamic dependencies; CA/config/resources supplied |
| Fully-static musl | Alpine | Runs on matching architecture; verify DNS, locales, and native integrations |

For each runtime, test:

- process startup and readiness;
- health endpoints;
- HTTPS handshake and certificate validation;
- DNS lookup;
- database connection and reconnect;
- message brokers/clients if present;
- compression, crypto, and JNI;
- graceful shutdown;
- running as a non-root user with a read-only root filesystem if required by deployment.

Do not run only `--version` or health checks. Invoke business APIs that exercise native dependencies.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `No such file or directory` even though executable exists | Missing dynamic loader specified in `PT_INTERP` | Inspect `readelf -l`; use a runtime image with the matching loader |
| `error while loading shared libraries` | Missing `.so` dependency | Run `ldd` on a trusted binary and add the matching library version |
| `GLIBC_2.xx not found` | Runtime glibc is older than required symbol version | Build on an older glibc baseline or upgrade the runtime |
| `--static` reports glibc unsupported | Native Image does not support static glibc | Use `--static-nolibc` for mostly-static glibc or `--static --libc=musl` |
| musl compiler not found | Toolchain missing from `PATH` or wrong target prefix | Check musl toolchain and compiler wrapper |
| `libz.a` or static archive not found | Missing zlib/toolchain static libraries | Install the proper archive in the musl sysroot and rebuild |
| glibc JNI `.so` fails to load on Alpine | Native library uses glibc ABI | Use a glibc runtime or build the dependency for musl |
| Static binary fails HTTPS calls | Missing CA bundle or trust config | Copy/mount CA certificates and check hostname/chain |
| DNS differs between glibc and musl | Resolver/configuration behavior differs | Check `/etc/resolv.conf`, DNS, and client behavior |
| Native build runs on x86-64 while runtime is ARM64 | Wrong target architecture | Build a dedicated artifact for the target architecture |
| Binary runs yet lacks timezone/config | Static linking does not embed these files | Supply resources or mount them at the expected paths |

## 17. Selection and Release Workflow

Suppose a billing service must run in Kubernetes with a small image, connect over HTTPS to a payment provider, and use a JNI SDK.

**Step 1 — Inspect native dependencies**

- List all JNI/shared libraries.
- Determine whether vendors ship glibc or musl builds.
- Check whether static archives exist for those libraries.
- Confirm whether the SDK uses `dlopen` or dynamic plugin loading.

**Step 2 — Choose the runtime contract**

If the SDK ships only glibc `.so` files, choose dynamic or mostly-static glibc and use a glibc runtime. If every dependency supports musl, consider fully-static musl for `scratch`.

**Step 3 — Build variants if evaluation is needed**

Dynamic:

~~~bash
native-image --libc=glibc \
  -jar target/billing-service.jar \
  billing-service-glibc
~~~

Mostly-static:

~~~bash
native-image --static-nolibc \
  -jar target/billing-service.jar \
  billing-service-mostly-static
~~~

Fully static musl (only on supported targets):

~~~bash
native-image --static --libc=musl \
  -jar target/billing-service.jar \
  billing-service-musl
~~~

**Step 4 — Inspect the ELF**

Run `file`, `readelf -l`, `readelf -d`, and `ldd` on each artifact. Record dynamic loader, `NEEDED` libraries, and GLIBC symbol versions if present.

**Step 5 — Test in the final runtime image**

Run the test suite covering HTTPS, DNS, database, SDK/JNI, resources, and a non-root user. Ensure CA bundles and configuration are properly provided.

**Step 6 — Compare costs**

Measure executable size, container image size, startup-to-ready, RSS, and throughput. Static linking can enlarge the binary; do not judge solely by base image size.

**Step 7 — Pin toolchain and runtime**

Record GraalVM version, JDK, compiler, musl/glibc baseline, target OS/architecture, and runtime image digest. Rebuild and re-test whenever updating libc or native dependencies.

## 18. Pre-Selection Checklist for Linking Mode

- [ ] Listed all application JNI/shared-library dependencies.
- [ ] Identified whether the runtime image uses glibc or musl.
- [ ] Distinguished dynamic, mostly-static, and fully-static modes.
- [ ] Avoided `--static` with glibc.
- [ ] If using `--static-nolibc`, verified the runtime still provides glibc and loader.
- [ ] If using `--static --libc=musl`, verified target and GraalVM version support musl.
- [ ] Properly installed the musl toolchain and static zlib libraries.
- [ ] Verified native dependencies match the chosen libc's ABI.
- [ ] Checked ELF interpreter and `DT_NEEDED`.
- [ ] Checked GLIBC symbol versions for dynamic glibc binaries.
- [ ] Supplied required CA bundle, timezone/config, and resources.
- [ ] Tested DNS, TLS, database, JNI, and critical business flows.
- [ ] Tested inside the exact final runtime container as a non-root user.
- [ ] Measured image size, startup, RSS, and throughput under identical workloads.
- [ ] Pinned GraalVM, toolchain, architecture, and runtime image digest.

**Key takeaway:** dynamic glibc fits most standard Linux runtimes and common JNI dependencies; `--static-nolibc` cuts down shared-library dependencies while still requiring glibc; `--static --libc=musl` produces a fully static executable runnable in `scratch` on supported targets. Choose based on the ABI of native dependencies, the runtime container, and required resources, then verify via ELF inspection and testing inside the final image.

## References

- [GraalVM Native Image — Build a Statically Linked or Mostly-Statically Linked Native Executable](https://www.graalvm.org/latest/reference-manual/native-image/guides/build-static-executables/): toolchain prerequisites, `--static --libc=musl`, `--static-nolibc`, and container choices.
- [GraalVM Native Image — Compatibility Guide](https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/): feature and architecture support limits, including musl on Linux AArch64.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/): checking options supported in the installed version.
- [musl libc](https://musl.libc.org/): documentation and details on the musl C library.
- [Linux man-pages — ld.so](https://man7.org/linux/man-pages/man8/ld.so.8.html): dynamic linker/loader and shared library resolution.
- [Linux man-pages — elf](https://man7.org/linux/man-pages/man5/elf.5.html): ELF structure, program headers, and dynamic section.
