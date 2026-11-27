# Identifying a Binary's Operating System, Architecture, and Linked Libraries

## 1. Why Inspect a Binary Before Release?

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed with Spring AOT and GraalVM Native Image to produce a native executable. Unlike a JAR containing Java bytecode that can run on any compatible JVM, a native executable is tied to the **operating system, CPU architecture, ABI, and native libraries** against which it was compiled and linked.

A binary built successfully on a developer's machine is not guaranteed to run in a production container. For example, a Linux x86-64 binary cannot run natively on ARM64; an executable dynamically linked against glibc may fail inside a musl-only image; or the runtime container may lack a shared library version required by the binary.

Therefore, before packaging and releasing, you should be able to answer:

- What executable format is the file, and which operating system is it for?
- Which CPU architecture was the binary built for?
- Which ABI/libc does it use, and which loader does it require?
- Which shared libraries must be present at runtime?
- Does the runtime image have the required dependencies and remain compatible with the binary?

This is an **artifact and execution environment** verification step. It complements Spring AOT/native functional testing: a properly formatted binary can still lack reflection metadata or resources, and an application that functions properly on the build host can still fail to launch on the deployment image.

## 2. Operating System, Architecture, and ABI Are Three Distinct Pieces of Information

| Concept | Example | Meaning |
|---|---|---|
| Operating system / format | Linux ELF, Windows PE, macOS Mach-O | Executable format and operating system conventions |
| CPU architecture | x86-64, AArch64/ARM64 | CPU instruction set contained in the binary |
| ABI | Linux GNU/glibc ABI, Linux musl ABI | Calling conventions, symbols, data types, and system library linkage |
| Dynamic loader | `ld-linux-x86-64.so.2`, musl loader | Component that loads shared libraries at launch |
| Shared libraries | `libc.so.6`, `libz.so.1`, `libstdc++.so.6` | Dynamic libraries required by the executable |

You cannot infer the ABI merely from the word "Linux" or solely from the architecture. Two binaries that are both ELF x86-64 can still depend on different libc implementations and symbol versions. Similarly, a container image may run on an ARM64 host via emulation, yet that does not make an x86-64 binary an ARM64 native binary.

## 3. Executable Formats: ELF, PE, and Mach-O

GraalVM Native Image generates executables matching the supported build/target platform.

- **ELF (Executable and Linkable Format):** standard on Linux, used for executables, object files, and shared libraries.
- **PE/COFF:** standard executable and object format on Windows, such as `.exe` files.
- **Mach-O:** executable and library format on macOS.

Use the `file` command for quick identification:

```bash
file ./application
```

Example Linux output might look similar to:

```text
application: ELF 64-bit LSB pie executable, x86-64, dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2
```

This tells you the file is 64-bit ELF, x86-64 architecture, and uses a dynamic interpreter. Actual output varies by toolchain, link mode, and architecture.

On Windows you can inspect files with appropriate PE inspection tools; on macOS you can use `file` and `otool`. Do not use `ldd` to inspect PE or Mach-O binaries.

## 4. Identifying Binary and Host Architecture

On Linux:

```bash
uname -m
file ./application
readelf -h ./application
```

- `uname -m` shows the running kernel/host architecture.
- `file` identifies the binary's format and architecture.
- `readelf -h` reads the ELF header, including class, data encoding, type, and machine.

Common values:

| Output `Machine` | Architecture | Example Target |
|---|---|---|
| `Advanced Micro Devices X86-64` | x86-64 / AMD64 | Linux amd64 |
| `AArch64` | ARM 64-bit | Linux arm64 |
| `Intel 80386` | x86 32-bit | Linux 386 |
| `ARM` | ARM 32-bit | Some embedded systems |

Docker uses platform names like `linux/amd64` and `linux/arm64`. You can inspect an image's architecture with:

```bash
docker image inspect application:latest --format '{{.Os}}/{{.Architecture}}'
```

This command displays image metadata; it does not inspect individual executables inside. With multi-architecture manifests, an image tag can point to multiple manifests/platforms; the registry/runtime selects the matching variant. Inspect both the image platform and actual binaries if the image contains multiple artifacts.

## 5. Reading the ELF Header, Program Headers, and Dynamic Section

`readelf` is an essential tool for inspecting ELF binaries without executing them.

### ELF Header

```bash
readelf -h ./application
```

Fields to pay attention to:

- **Class:** ELF32 or ELF64.
- **Data:** little endian or big endian.
- **Type:** executable, shared object, or another type.
- **Machine:** CPU architecture.
- **Entry point:** execution start address.

### Program Headers and Interpreter

```bash
readelf -l ./application
```

Look for the `INTERP` entry or a line like:

```text
[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
```

This is the dynamic loader the kernel must locate when launching the executable. If the loader is absent from the runtime filesystem, the process can fail with "No such file or directory" even though the executable file itself is present. This is a common error when copying a glibc binary into an Alpine/musl image lacking the glibc loader.

### Dynamic Section

```bash
readelf -d ./application
```

Look for `NEEDED` entries to see shared library dependencies recorded in ELF. Example:

```text
Shared library: [libz.so.1]
Shared library: [libc.so.6]
```

These dependencies must be found by the loader at runtime. Not every binary has a dynamic section; statically linked executables may list no `NEEDED` entries.

## 6. Identifying Required Shared Libraries

On Linux, `ldd` can display the shared libraries required by a dynamically linked executable:

```bash
ldd ./application
```

Illustrative output:

```text
linux-vdso.so.1
libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1
libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6
/lib64/ld-linux-x86-64.so.2
```

If `not found` appears, the required library is missing in the current environment. Identify the runtime package providing that library and verify matching architecture/ABI.

**Operational warning:** do not run `ldd` directly on untrusted binaries. Depending on the platform and executable type, certain historical `ldd` implementations can trigger code execution. For untrusted artifacts, prefer inspecting metadata statically with `readelf -d` or static ELF analysis tools.

You can use `objdump -p` to inspect dynamic dependencies:

```bash
objdump -p ./application | grep NEEDED
```

`NEEDED` results list library names; they do not prove libraries will resolve successfully inside a container. Verify further in the runtime filesystem.

## 7. glibc vs. musl: Why Both Are Linux Yet Not Compatible by Default

Linux distributions commonly use different libc implementations:

- **glibc:** common across Debian, Ubuntu, Fedora, RHEL, and many other Linux distributions.
- **musl:** used by default in Alpine Linux, designed to be compact and suited for minimal environments.

A native executable dynamically linked against glibc typically requires the glibc loader and symbol versions. Alpine defaults to musl; simply copying a glibc executable into Alpine usually will not run. Conversely, a binary built for musl does not automatically run on every glibc distribution if ABI assumptions differ.

Check which dynamic interpreter a binary requires with:

```bash
readelf -l ./application | grep interpreter
```

Check dynamic dependencies with:

```bash
readelf -d ./application | grep NEEDED
```

Do not conclude a binary is "static" just because `ldd` lists no libraries. An executable may statically link some components while still relying on other dynamic libraries; inspect ELF metadata and run real tests.

With GraalVM Native Image, your choice of build distribution/toolchain and linking mode affects deployability. Choose compatible builders and runtime base images from the start rather than waiting for container startup to discover a mismatch.

## 8. Symbol Versions and glibc Version Requirements

A dynamically linked binary can require specific symbol versions. For example, an executable built in a newer glibc environment may reference `GLIBC_2.xx`; a runtime image with an older glibc will not supply that symbol.

You can inspect required versions in ELF:

```bash
readelf --version-info ./application
```

Or filter symbol version info:

```bash
objdump -T ./application | grep GLIBC_
```

These commands help identify symbol version requirements. Do not rely solely on the glibc version stated in an image's name; inspect the actual binary and libraries inside the image.

Typical resolutions include:

- Building in an environment with a glibc compatible with the runtime base image.
- Selecting a runtime image with a sufficiently recent and supported glibc.
- Using an appropriate toolchain/target if a static or musl build is needed.
- Avoiding ad-hoc libc upgrades inside production containers, as that can affect other packages.

Practical rule: **build on a platform compatible with runtime**, or use a controlled cross-build pipeline and test on the exact target.

## 9. Inspecting the Runtime Container

The binary must be verified inside the actual deployment image, not only on the build host.

```bash
docker run --rm --entrypoint sh application:latest -c '
  uname -m
  cat /etc/os-release
  ls -l /app
'
```

This command assumes the image includes a shell and those utilities; distroless/scratch images may not. For minimal images, use a compatible debug container or inspect with external runtime tools. Do not alter the production entrypoint merely for inspection convenience.

You can run the application and observe exit codes/logs:

```bash
docker run --rm -p 8080:8080 application:latest
```

Then send a request from the host:

```bash
curl -i http://localhost:8080/actuator/health
```

The Actuator endpoint is only present if the application added Actuator and configured appropriate exposure. Otherwise, use a known business endpoint.

If the container exits immediately with a loader/shared library error, check the interpreter and `NEEDED` entries. If the process runs but an endpoint fails on reflection/resources, that is a different class of problem requiring inspection of Spring AOT/GraalVM metadata and functional tests.

## 10. Verifying Multi-Platform Architectures

When publishing multi-architecture images, build separate binaries for each target or use a multi-platform build mechanism supported by your toolchain. An x86-64 executable does not automatically turn into ARM64 when Docker builds a manifest list.

Inspect the image platforms:

```bash
docker buildx imagetools inspect registry.example.com/orders:1.0
```

The output shows the platform manifests referenced by the tag. Verify that each platform genuinely contains a binary of the matching architecture:

- The `linux/amd64` build target must contain an ELF x86-64 binary.
- The `linux/arm64` build target must contain an ELF AArch64 binary.
- The runtime base and shared libraries of each platform must match that architecture and ABI.
- Run smoke tests on an appropriate host/native runner or a verified emulation environment.

Native cross-compilation has limitations depending on GraalVM version, toolchain, and native libraries. Do not assume setting `--platform linux/arm64` in Docker makes every GraalVM step cross-compile accurately on its own.

## 11. Building and Inspecting a Spring Boot Native Image Artifact

With Maven, build native per project configuration:

```bash
./mvnw -Pnative native:compile
```

With Gradle:

```bash
./gradlew nativeCompile
```

Executable name and location depend on artifact name, plugin version, OS, and configuration. After the build, locate the exact file in the Maven/Gradle output and run inspection steps:

```bash
file ./path/to/application
readelf -h ./path/to/application
readelf -l ./path/to/application
readelf -d ./path/to/application
```

On Linux, inspect the host:

```bash
uname -m
cat /etc/os-release
```

Then compare against the runtime container's platform and libc. Do not run the native binary during the build step merely to confirm the file exists; verify functionality, dependencies, and deployment conditions.

## 12. Categorizing Errors by Symptom

| Symptom | Root-Cause Category | Verification Direction |
|---|---|---|
| `Exec format error` | Wrong OS format or architecture | `file`, `readelf -h`, image platform |
| `No such file or directory` even though binary exists | Missing dynamic loader/interpreter | `readelf -l`, inspect runtime base |
| `error while loading shared libraries` | Missing shared library | `readelf -d`, inspect packages in image |
| `GLIBC_x.y not found` | Runtime glibc is too old | `readelf --version-info`, pick compatible base |
| Binary runs on host but fails in container | Different libc, loader, architecture, or runtime files | Inspect inside the actual image |
| Process starts but endpoint fails | Metadata, resources, config, or business logic | Native integration tests and application logs |
| Binary is too large | Link mode, dependencies, and retained code | Analyze build report and Native Image config |

"No such file or directory" when the file clearly exists is often confusing. The kernel may be failing to locate the **interpreter** recorded in the ELF header, not the executable path itself. Thus, checking `readelf -l` is a crucial step.

## 13. Artifact Release Checklist

Before pushing a native image to a registry or production, verify:

- [ ] Artifact has the right format for the target operating system.
- [ ] Binary architecture matches the image platform.
- [ ] ABI/libc and dynamic loader match the runtime.
- [ ] All `NEEDED` shared libraries are provided.
- [ ] Symbol versions do not exceed those of runtime libraries.
- [ ] Runtime image has CA certificates, timezone data, and required runtime files.
- [ ] Container runs under an appropriate user/permissions and can start up.
- [ ] Smoke tests for endpoints and critical business flows pass.
- [ ] Image tag/digest, builder, and toolchain versions are recorded.
- [ ] Each platform in a multi-arch image has been verified independently.

This checklist should be enforced in the release pipeline to avoid "works on developer machine, fails in production" incidents.

## 14. Practice Exercise: Analyzing a Binary and Running It in a Container

**Context:** a Spring Boot Native Image executable has been built on Linux.

**Step 1 — Identify the binary.**

```bash
file ./application
readelf -h ./application
```

Record the ELF class, machine architecture, and file type.

**Step 2 — Inspect the interpreter and libraries.**

```bash
readelf -l ./application
readelf -d ./application
readelf --version-info ./application
```

Record the dynamic loader, `NEEDED` list, and required symbol versions.

**Step 3 — Compare with the runtime environment.** Determine the OS, architecture, and libc in the container base. Check library paths and required library versions.

**Step 4 — Run the container.** Launch the image, observe exit codes/logs, and call an endpoint. If loader errors appear, resolve ABI/dependency issues before investigating Spring.

**Step 5 — Run native functional tests.** Execute requests covering JSON, reflection, resources, validation, and real integrations. Clearly classify errors as system-layer vs. application-layer.

**Step 6 — Record the artifact manifest.** Save binary checksum, image digest, OS/architecture, builder/runtime base, GraalVM version, and key dependencies for release traceability.

## 15. Conclusion

A GraalVM Native Image executable depends on **OS format, CPU architecture, ABI/libc, dynamic loader, and shared libraries**. Tools such as `file`, `readelf`, `objdump`, and container inspection help surface these requirements prior to deployment. A binary that builds successfully is not guaranteed to run on every Linux image; verify inside the exact runtime filesystem and for each release architecture.

By cleanly separating system-level errors (format, architecture, loader, libraries) from application-level errors (Spring AOT hints, reflection, resources, configuration), teams can troubleshoot the right layer, produce reproducible artifacts, and operate Spring Boot Native Image reliably.
