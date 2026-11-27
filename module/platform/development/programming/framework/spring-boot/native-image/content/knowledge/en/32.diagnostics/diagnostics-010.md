# Binary Fails to Run Due to Wrong Architecture, libc, or Linked Libraries

A Spring Boot application that runs fine in the builder container yet crashes immediately upon moving to the runtime container often faces an OS-layer error: the executable was built for a different CPU, the dynamic loader is missing, glibc is incompatible, or a shared library is missing. This belongs to the category of **native binary and Linux environment** errors, distinct from Spring AOT errors like missing reflection/resource hints.

Native Image produces an executable bound to an OS, CPU architecture, ABI, and linking mode. Therefore, a successful build does not prove the binary will run in the final image. This lesson guides diagnosing from the ELF header, interpreter, and dynamic dependencies down to glibc/musl and CPU instruction sets, while showing how to select builder/runtime images, inspect the final container, and fix errors systematically.

This lesson belongs to the **Diagnostics** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module. The module guides compiling Spring Boot with Spring AOT into a GraalVM Native Image to evaluate startup and memory, practicing Maven/Gradle builds, configuring reflection/resources, compatibility testing, container packaging, and operating native builds.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish ELF format/architecture errors from missing dynamic loader or shared library errors.
- Identify the architecture of the host, container image, and executable.
- Read the ELF header, program interpreter, `DT_NEEDED`, RPATH/RUNPATH, and symbol versions.
- Analyze `Exec format error`, `No such file or directory`, `GLIBC_2.xx not found`, missing shared library errors, and `Illegal instruction`.
- Distinguish dynamically linked, mostly-static, and fully-static executables.
- Choose a glibc or musl runtime matching how the binary was built.
- Check CPU instruction sets and select an appropriate `-march`.
- Produce separate binaries for `linux/amd64` and `linux/arm64`.

## 2. Four Compatibility Layers of a Native Executable

A Linux native executable must satisfy four conditions simultaneously:

| Layer | What must match | Example errors |
|---|---|---|
| Format and architecture | ELF format, 32/64-bit, CPU architecture | `Exec format error`, `wrong ELF class` |
| Dynamic loader | The interpreter path in ELF must exist | File exists yet reports `No such file or directory` |
| ABI and libc | Binary matches runtime glibc/musl and symbol versions | `GLIBC_2.xx not found`, relocation errors |
| Shared libraries and CPU features | Required `.so` files and instruction sets must exist | `libfoo.so: cannot open`, `Illegal instruction` |

A container image packages a filesystem and declares a platform, but the container still uses the host kernel. Therefore, the binary must match the host's CPU architecture and execution capability or rely on emulation. Docker can select an image variant by platform, yet it cannot automatically fix a wrong-architecture binary copied into an image.

~~~mermaid
flowchart TD
    A["Binary fails to start"] --> B{"ELF matches architecture?"}
    B -- "No" --> C["Build for target CPU/OS"]
    B -- "Yes" --> D{"PT_INTERP exists?"}
    D -- "No" --> E["Pick matching loader/base image"]
    D -- "Yes" --> F{"Libc and symbol versions match?"}
    F -- "No" --> G["Align glibc/musl or rebuild"]
    F -- "Yes" --> H{"All shared libraries present?"}
    H -- "No" --> I["Install right runtime libraries"]
    H -- "Yes" --> J{"CPU supports instructions?"}
    J -- "No" --> K["Rebuild with appropriate -march"]
    J -- "Yes" --> L["Check config and application errors"]
~~~

## 3. Identify Host, Image, and Executable Architecture

On a Linux host:

~~~bash
uname -m
~~~

Common values:

| `uname -m` | Docker platform | ELF machine |
|---|---|---|
| `x86_64` | `linux/amd64` | x86-64 |
| `aarch64` | `linux/arm64` | AArch64 |

Inspect the image and Docker daemon:

~~~bash
docker image inspect --format '{{.Os}}/{{.Architecture}}' orders-service:native
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

Inspect the executable:

~~~bash
file ./orders-service
readelf -h ./orders-service
~~~

In the ELF header, pay attention to `Class` (ELF64/ELF32), `Data`, `Machine`, and `Type`. For example, `ELF 64-bit ... x86-64` cannot run natively on ARM64; `ARM aarch64` cannot run natively on x86-64.

Do not infer architecture from image tags. Multi-architecture images have manifest lists; Docker picks a variant matching the host on pull, yet the binary copied into each variant must still match that variant's architecture.

## 4. Diagnose `Exec format error`

Example:

~~~text
exec /app/orders-service: exec format error
~~~

This error usually indicates the kernel cannot execute the file in its current format or architecture. Common causes:

- Binary built for `linux/amd64` while the runtime host is `linux/arm64`, or vice versa.
- Binary built for another OS such as macOS/Windows.
- Corrupted file, wrong artifact copied, or not an ELF executable.
- Host lacks emulation for foreign architectures.

Check:

~~~bash
uname -m
file /app/orders-service
readelf -h /app/orders-service | grep -E 'Class:|Machine:'
docker image inspect --format '{{.Os}}/{{.Architecture}}' orders-service:native
~~~

Prefer building binaries on a runner whose architecture matches the release platform:

~~~bash
# x86-64 runner
docker buildx build --platform linux/amd64 -t orders-service:native-amd64 .

# ARM64 runner
docker buildx build --platform linux/arm64 -t orders-service:native-arm64 .
~~~

Docker Buildx supports QEMU emulation, native builder nodes, and cross-compilation. Native Image compilation is heavy; running the compiler under QEMU can be slow or toolchain-dependent. For releases, native builder nodes per architecture are usually easier to control.

`--platform` selects the platform of the image/build stage. It does not automatically convert a host-built executable into a binary for another target. Check `file` on the executable after native compilation.

You can run an amd64 image on an ARM64 host if the host has QEMU/binfmt configured:

~~~bash
docker run --rm --platform linux/amd64 orders-service:native-amd64
~~~

Emulation helps for basic compatibility checks. Performance benchmarks must run on native CPUs because QEMU alters execution costs.

## 5. File Exists Yet Reports `No such file or directory`

Example:

~~~text
/app/orders-service: No such file or directory
~~~

even though `ls -l /app/orders-service` confirms the file actually exists. For a dynamically linked ELF, the kernel reads the `PT_INTERP` segment to locate the dynamic loader. If the loader recorded in the binary does not exist in the runtime image, executing it can report that the file does not exist.

Read the program headers:

~~~bash
readelf -l /app/orders-service | grep -A1 INTERP
~~~

Example:

~~~text
[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
~~~

Check the interpreter path inside the **runtime filesystem**:

~~~bash
ls -l /lib64/ld-linux-x86-64.so.2
~~~

This example is for x86-64 glibc; ARM64 uses a different loader path. Never create a fake symlink pointing to a loader from a different libc, architecture, or ABI.

### Inspect the Binary Inside the Final Image

The builder stage may have loaders and libraries absent from the final stage. You can copy the executable out of the final image to analyze it on the host:

~~~bash
docker create --name native-inspect orders-service:native
docker cp native-inspect:/app/orders-service ./orders-service-from-image
docker rm native-inspect
file ./orders-service-from-image
readelf -l ./orders-service-from-image | grep -A1 INTERP
~~~

Distroless and `scratch` typically lack a shell, `ls`, or a package manager. Use a debug image or diagnostic container sharing the same root filesystem; do not mistake `docker exec ... sh` failing for a broken executable.

## 6. Understand glibc, musl, and ABI

`libc` provides foundational primitives such as memory allocation, string handling, threading, and system-call wrappers. Two common libc families:

- **glibc:** used by Debian, Ubuntu, Oracle Linux, Red Hat Enterprise Linux, and many other distros.
- **musl:** used by Alpine Linux.

Binaries dynamically linked against glibc typically need the glibc loader and glibc symbols. Alpine uses musl, so it lacks the glibc loader and ABI expected by default. Similarly, do not assume a musl-built binary will run on glibc without verification.

### 6.1. `GLIBC_2.xx not found` Error

Example:

~~~text
/app/orders-service: /lib64/libc.so.6:
version GLIBC_2.34 not found (required by /app/orders-service)
~~~

The binary requires a newer glibc symbol version than the runtime provides. This commonly happens when the builder uses a newer distro while the runtime uses an older distro.

Check which symbol versions the binary references:

~~~bash
readelf --version-info /app/orders-service | grep GLIBC_
~~~

Check glibc in the runtime:

~~~bash
ldd --version
~~~

On a glibc-based runtime, `ldd --version` shows the glibc version. On a musl-based image, do not interpret the loader output as a glibc version. If a minimal runtime image lacks this tool, use a debug image or check the libc package/version by an appropriate method.

### 6.2. Fix glibc Mismatch

**Build on the lowest glibc baseline you must support.** If production runs multiple distro versions, pick a builder matching the lowest baseline and test on every target runtime. A binary built on newer glibc may require symbols missing from older runtimes; a binary built on an older baseline usually runs on newer glibc if other dependencies are also compatible.

**Align builder and runtime OS family/version.** For example, base both on Oracle Linux 9. This reduces ABI mismatch risks, though you must still verify additional libraries.

**Consider mostly-static or fully-static.** Mostly-static still needs a compatible libc; fully-static with musl can eliminate runtime libc dependencies. Review section 9 before choosing.

Never fix this by arbitrarily copying `libc.so.6` or the dynamic loader from builder to runtime. Mixing glibc and loaders across versions causes unpredictable ABI failures.

## 7. Diagnose Missing Shared Libraries

Common error:

~~~text
error while loading shared libraries: libfoo.so.1:
cannot open shared object file: No such file or directory
~~~

The binary found its dynamic loader, but the loader cannot find a required shared library.

### 7.1. List Dependencies

On a trusted binary produced by your pipeline:

~~~bash
ldd ./orders-service
~~~

Example:

~~~text
linux-vdso.so.1
libz.so.1 => /lib64/libz.so.1
libc.so.6 => /lib64/libc.so.6
/lib64/ld-linux-x86-64.so.2
~~~

If you see `libfoo.so.1 => not found`, the runtime image lacks the library or the loader cannot locate it in configured search paths.

**Security note:** never run `ldd` on untrusted executables. Some implementations may invoke the dynamic loader or execute parts of the binary. For untrusted files, use static analysis:

~~~bash
objdump -p ./unknown-binary | grep NEEDED
readelf -d ./unknown-binary | grep NEEDED
~~~

These commands report direct `DT_NEEDED` entries; they do not necessarily list all transitive dependencies like `ldd`.

### 7.2. RPATH, RUNPATH, and Library Search

Inspect dynamic entries:

~~~bash
readelf -d ./orders-service | grep -E 'RPATH|RUNPATH|NEEDED'
~~~

The glibc dynamic linker searches for libraries using dependency paths, `RPATH`/`RUNPATH`, `LD_LIBRARY_PATH`, the loader cache, and default directories. `RUNPATH` normally applies only to direct dependencies of the object declaring it; transitive dependencies may need separate configuration.

You can enable loader tracing in a glibc environment:

~~~bash
LD_DEBUG=libs ./orders-service
~~~

This shows where the dynamic linker searches for libraries and why it skips paths. Use only during diagnosis because output is verbose.

### 7.3. Fix Missing Libraries

1. Identify the runtime package providing the exact missing `.so` file.
2. Install that package in the final stage, or copy the library under a controlled packaging policy.
3. Ensure the library's architecture and ABI match the executable.
4. If using a custom directory, configure RUNPATH/library paths properly or run `ldconfig` on supported glibc images.
5. Re-run checks against the final image, not just the builder.

Do not copy all of `/usr/lib` from builder to runtime. That can pull in conflicting library versions. Also avoid setting a global `LD_LIBRARY_PATH` to mask errors; add the right package or required path instead.

## 8. Distinguish glibc and musl in Containers

Alpine is compact but uses musl. A Native Image binary built by default on a glibc-based builder generally will not run directly on Alpine merely by copying the file.

Symptoms may include:

- Dynamic loader path `/lib64/ld-linux-...` does not exist.
- `Error loading shared library ...`.
- `Error relocating ...: symbol not found`.
- Binary starts up, but a native dependency fails when invoked.

Remediation workflow:

1. Use `file` and `readelf -l` to determine which loader the binary requires.
2. Check whether the runtime image uses glibc or musl.
3. Identify native dependencies such as JNI, native database drivers, compression, crypto, and C/C++ libraries.
4. Pick a compatible glibc runtime or build the binary using a musl toolchain.
5. Run integration tests on the exact final image.

Do not assume Alpine compatibility packages fully substitute for every glibc version. Compatibility layers can help some applications, yet they do not guarantee every binary, loader path, and native dependency works.

## 9. Dynamic, Mostly-Static, and Fully-Static Native Images

GraalVM Native Image builds dynamically linked binaries by default. Depending on the deployment environment, you can choose:

| Linking mode | How it works | What the runtime needs |
|---|---|---|
| Dynamic (default) | Links against shared libraries at runtime | Dynamic loader, libc, and all required `.so` files |
| Mostly-static | Statically links native libraries except libc | Still needs a compatible libc; may depend on `libstdc++`/`libgcc` |
| Fully-static | Statically links libc too using musl | No dynamic shared-library loader needed for that executable |

### 9.1. Fully-Static with musl

Illustrative command:

~~~bash
native-image --static --libc=musl \
  -jar application.jar \
  -o orders-service
~~~

The builder must contain a musl toolchain and matching static libraries. Check the documentation for your GraalVM version and architecture limits before applying; current documentation notes musl is not yet supported on Linux AArch64.

Inspect the binary:

~~~bash
ldd ./orders-service
~~~

For a fully-static binary, output typically says `not a dynamic executable`. It can be deployed into ultra-minimal images such as `scratch` if the application does not require CA certificates, timezone databases, config files, temp directories, or other runtime assets.

### 9.2. Mostly-Static

~~~bash
native-image --static-nolibc \
  -jar application.jar \
  -o orders-service
~~~

Mostly-static statically links relevant libraries except libc. It still requires libc—specifically glibc when built on glibc. This is useful when reducing the number of shared libraries to install in Debian-based Distroless or other glibc runtimes.

Do not confuse `--static-nolibc` with fully-static: this binary cannot run on `scratch` by default because it still needs a runtime libc.

### 9.3. Choose an Option

- Choose dynamic if using a standard glibc base image with explicit runtime package management.
- Choose mostly-static if reducing extra shared dependencies while still deploying on glibc.
- Choose fully-static/musl if needing a self-contained executable and your project's architecture/toolchain supports it.

Static linking does not fix a wrong CPU architecture, incompatible CPU instruction sets, or missing external runtime files required by the application.

## 10. `Illegal instruction` Errors and CPU Instruction Sets

If the process starts and terminates with:

~~~text
Illegal instruction (core dumped)
~~~

or an exit code caused by `SIGILL`, the binary may contain instructions unsupported by the target CPU. One cause is building with `-march=native` on a newer CPU and running on an older CPU.

Native Image provides `-march` to control which instruction set the compiler may emit. Per current GraalVM documentation, defaults are `x86-64-v3` on x64 and `armv8-a` on AArch64; exact defaults may depend on version.

Inspect CPU and machine types:

~~~bash
lscpu
native-image -march=list
~~~

| Option | When to use |
|---|---|
| `-march=native` | Binary runs only on the build machine's CPU or CPUs with equivalent features |
| `-march=compatibility` | Distributing across heterogeneous machines, including older CPUs; prioritizes compatibility |
| `-march=x86-64-v3` or a specific machine type | Production fleet has standardized on a CPU feature level |

Compatibility-first build example:

~~~bash
native-image -march=compatibility \
  -jar application.jar \
  -o orders-service
~~~

When using Maven/Gradle plugins, pass the option via Native Build Tools configuration for your plugin version. Record `-march` in the build manifest because changing it alters the binary and its performance.

Never use `-march=native` on a runner that does not represent production CPUs if the binary will run across multiple CPU generations. Test on a machine with the lowest instruction set in the supported fleet.

## 11. Repeatable ELF Diagnostic Procedure

On a trusted executable, run in order:

~~~bash
BIN=./orders-service

# 1. File type and architecture
file "$BIN"
readelf -h "$BIN" | grep -E 'Class:|Data:|Machine:|Type:'

# 2. Dynamic loader
readelf -l "$BIN" | grep -A1 INTERP || true

# 3. Direct dependencies and search paths
readelf -d "$BIN" | grep -E 'NEEDED|RPATH|RUNPATH' || true

# 4. Required glibc symbol versions
readelf --version-info "$BIN" | grep GLIBC_ || true

# 5. Full dependency resolution (trusted binary only)
ldd "$BIN"
~~~

Then run the same checks on the file copied out of the **final image**. If the binary in the builder and the binary in the final image have different SHA-256 digests, pinpoint which step altered the file.

### Inspect File and Image with Docker

~~~bash
docker image inspect \
  --format '{{.Os}}/{{.Architecture}} {{.Id}}' \
  orders-service:native

docker create --name inspect-native orders-service:native
docker cp inspect-native:/app/orders-service ./orders-service-from-image
docker rm inspect-native

file ./orders-service-from-image
readelf -h ./orders-service-from-image
~~~

`docker cp` lets you extract the executable from the image to analyze with host tools even when the runtime image has no shell. For Distroless, use a debug image or diagnostic container with the same base filesystem.

## 12. Symptom and Remediation Matrix

| Symptom | Likely error layer | First check | Fix direction |
|---|---|---|---|
| `exec format error` | Wrong ELF format/architecture | `file`, `readelf -h`, `uname -m` | Build for right OS/CPU or configure emulation |
| `cannot execute binary file` | Wrong architecture or invalid executable | `file`, permissions, ELF header | Use right artifact and executable permission |
| File exists yet `No such file or directory` | Missing `PT_INTERP` loader | `readelf -l`, loader path in final rootfs | Use runtime with matching loader or rebuild |
| `wrong ELF class` | 32/64-bit or ABI class mismatch | `readelf -h` on executable and `.so` | Match dependency architecture/bitness |
| `GLIBC_2.xx not found` | Runtime glibc older than required symbol | `readelf --version-info`, `ldd --version` | Build on lower glibc baseline or upgrade runtime |
| `libfoo.so: cannot open shared object file` | Missing shared library or wrong search path | `ldd`, `readelf -d`, `LD_DEBUG=libs` | Install right package or fix RUNPATH/library path |
| `Error relocating ... symbol not found` | ABI/libc mismatch or wrong `.so` version | `file`, `readelf -d` | Align libc and native libraries; rebuild if needed |
| `Illegal instruction` / `SIGILL` | CPU lacks instruction feature | `lscpu`, build flags, and `-march` | Build with `-march=compatibility` or common feature target |
| Runs in builder but fails in final image | Builder has loader/library missing in runtime | Repeat ELF checks on final file and rootfs | Add minimal runtime dependencies or pick right base |
| Runs only with `LD_LIBRARY_PATH` | Library search path not packaged properly | `readelf -d`, `LD_DEBUG=libs` | Place library in explicit runtime path/RUNPATH |

## 13. Build Matrix Design for amd64 and arm64

GraalVM provides Linux distributions for x64 and AArch64; check the compatibility guide for your exact GraalVM release and options. In particular, current documentation notes musl is not yet supported on Linux AArch64, so do not assume an amd64 fully-static workflow applies as-is to arm64.

If the product runs on both x86-64 and ARM64, treat each architecture as a distinct artifact:

| Attribute | amd64 | arm64 |
|---|---|---|
| Runner | Linux x86-64 | Linux AArch64 |
| Build platform | `linux/amd64` | `linux/arm64` |
| ELF machine | x86-64 | AArch64 |
| Native executable | `orders-service-amd64` | `orders-service-arm64` |
| Binary SHA-256 | Separate | Separate |
| Integration tests | Run on amd64 | Run on arm64 |

The pipeline can use two native runners building in parallel, then package image variants and publish a manifest list. Each binary should undergo ELF header, loader, shared-dependency, and smoke tests on its native architecture.

Docker Buildx can combine multiple platforms into one image manifest list:

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/orders-service:1.0.0 \
  --push .
~~~

For this command to produce native executables for the right architecture, the builder strategy must genuinely produce a binary per target. For Native Image, prefer native builder nodes per architecture; do not assume Buildx selecting a platform automatically cross-compiles the binary properly.

Store checksums and test evidence separately per platform. When pulling a multi-arch image, Docker selects the variant matching the host, yet you must still verify the manifest list includes every platform the product commits to support.

## 14. Test the Final Image Before Release

Do not stop after verifying the binary runs in the builder. The final image is the actual environment production will run.

Minimum procedure:

1. Build the native executable for the right target architecture.
2. Package it into the final runtime image.
3. Verify the image platform and ELF machine.
4. Verify `PT_INTERP`, shared libraries, and libc compatibility.
5. Start the container with production-like user, filesystem permissions, and environment.
6. Wait for the readiness endpoint.
7. Send a real request to confirm the server serves traffic.
8. Inspect logs, exit codes, and signal handling when the container stops.

Example:

~~~bash
docker run -d --name orders-native-test \
  -p 18080:8080 \
  orders-service:native

docker logs orders-native-test
curl --fail http://localhost:18080/actuator/health
docker stop orders-native-test
docker rm orders-native-test
~~~

Adjust the health path and port for your application. If Actuator is protected by Spring Security, use an appropriate test configuration or the designed readiness probe endpoint.

For Distroless or `scratch` containers, do not require a shell for verification. Use health probes from the host/orchestrator and run inspection tools against an extracted copy of the executable.

## 15. Fixes That Easily Introduce New Bugs

| Practice | Risk |
|---|---|
| Copying `libc.so.6` from builder to runtime | Mixes glibc and loader across versions, causing unpredictable ABI crashes |
| Installing bulk development packages into runtime | Bloats image, expands attack surface, complicates dependency control |
| Setting broad `LD_LIBRARY_PATH` across directories | May load wrong library versions or untrusted libraries |
| Using `-march=native` on a runner with a newer CPU | Binary may raise SIGILL on older production CPUs |
| Building amd64 and retagging as arm64 | Tags do not change machine code inside the ELF |
| Testing only inside the builder image | Builder may mask missing runtime loaders/shared libraries |
| Running `ldd` on untrusted files | Some implementations can execute code during inspection |
| Assuming Alpine is glibc-compatible | Alpine uses musl; loader and ABI may not match |
| Assuming `--static-nolibc` runs on `scratch` | Mostly-static still requires a runtime libc |

## 16. Pre-Release Diagnostic Checklist

- [ ] Identified host architecture and Docker daemon platform.
- [ ] Verified final image/manifest platform.
- [ ] Used `file` and `readelf -h` to confirm ELF machine and class.
- [ ] Checked `PT_INTERP` and confirmed the loader exists in the runtime filesystem.
- [ ] Checked `DT_NEEDED`, RPATH/RUNPATH, and shared-library resolution.
- [ ] Checked glibc symbol versions and runtime libc.
- [ ] Clearly identified whether the binary was built for glibc or musl.
- [ ] Distinguished dynamic, mostly-static, and fully-static builds.
- [ ] Checked CPU instruction set and `-march`.
- [ ] Built separate binaries for each supported architecture.
- [ ] Ran smoke/integration tests on the exact final image.
- [ ] Archived ELF inspection, dependency list, binary digest, and image digest alongside build evidence.

## 17. Self-Check Exercises

**Q1.** Why can an executable file exist on disk yet the shell report `No such file or directory`?

**Hint:** the kernel may fail to find the dynamic loader declared in the `PT_INTERP` segment.

**Q2.** How does `exec format error` differ from `GLIBC_2.xx not found`?

**Hint:** the first typically occurs when the kernel rejects the binary format/architecture; the second occurs when the loader finds the binary, but runtime libc lacks a required symbol version.

**Q3.** Why should `ldd` be run only on trusted binaries?

**Hint:** some implementations may invoke the dynamic loader or execute parts of the file while querying dependencies.

**Q4.** Can a `--static-nolibc` binary run on `scratch`?

**Hint:** not by default. Mostly-static still requires a runtime libc.

**Q5.** When should you choose `-march=compatibility`?

**Hint:** when the binary must run across multiple CPU generations or CPUs older than the build machine.

**Q6.** Does Docker Buildx automatically convert an amd64 executable into arm64 when building with `--platform linux/arm64`?

**Hint:** no. The build stage must actually produce a native binary for that target; use native runners/builder nodes or a verified cross-build pipeline.

**Q7.** Why is testing the binary inside the builder stage insufficient?

**Hint:** the builder may contain loaders and shared libraries absent from the final runtime image.

## 18. References

- [GraalVM — Installation on Linux Platforms](https://www.graalvm.org/docs/getting-started/linux/): Linux x64/AArch64 and Native Image toolchain prerequisites.
- [GraalVM — Native Image Compatibility Guide](https://www.graalvm.org/reference-manual/native-image/metadata/Compatibility/): Native Image compatibility limits by platform.
- [GraalVM — Optimizations and Performance](https://www.graalvm.org/reference-manual/native-image/optimizations-and-performance/): `-march`, machine types, and CPU-targeted optimization options.
- [GraalVM — Build Static or Mostly-Static Native Executables](https://www.graalvm.org/reference-manual/native-image/StaticImages/): dynamic, mostly-static, fully-static, and musl/glibc.
- [Docker — Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): platform manifests, QEMU, native nodes, and cross-compilation strategies.
- [Docker — Dockerfile reference](https://docs.docker.com/reference/dockerfile/): `--platform`, `BUILDPLATFORM`, and `TARGETPLATFORM`.
- [Linux man-pages — execve(2)](https://man7.org/linux/man-pages/man2/execve.2.html): kernel behavior when executing ELF binaries and dynamic interpreters.
- [Linux man-pages — ldd(1)](https://man7.org/linux/man-pages/man1/ldd.1.html): printing shared-object dependencies and security notes.
- [Linux man-pages — ld.so(8)](https://man7.org/linux/man-pages/man8/ld.so.8.html): dynamic linker/loader and shared library search mechanism.
- [GNU Binutils — readelf(1)](https://www.man7.org/linux/man-pages/man1/readelf.1.html): reading ELF headers, program headers, dynamic sections, and symbol versions.

**Takeaway:** Diagnose Native Image binaries in order: ELF architecture, dynamic loader, libc/ABI, shared libraries, and CPU instruction set. Always test the executable inside the final runtime image. Build separately per architecture, choose the matching libc, and set `-march` according to the lowest CPU the product must support.
