# Testing the Binary in the Actual Runtime Environment to Detect Missing Libraries

A **GraalVM Native Image** is a native executable built for a specific operating system and architecture. Compiling successfully on a development machine does not prove the binary will run in a container or production server. The runtime environment may lack shared libraries, use an incompatible libc version, omit JNI libraries, or lack CA certificates, the timezone database, or resources the application needs to read.

Therefore, after building a Spring Boot Native Image, you must test **the actual generated executable in an environment as close to production as possible**. This lesson walks through inspecting architecture and ABI, listing dynamic libraries, verifying JNI and serialization, running smoke tests in the real run image, and diagnosing common errors across Linux, macOS, Windows, and containers.

## 1. Why Does a Successful Build Still Fail to Run?

The Native Image compiler checks and links the program within the build environment. Some system dependencies are dynamically linked and are only loaded when the executable launches. The build machine may have libraries pre-installed that the run image lacks.

For example:

- The build machine has `libz.so.1`, but the runtime container does not.
- The binary was built on a system with a newer glibc, while the target host uses an older glibc.
- A JNI library exists on a laptop but was not copied into the image.
- The primary JNI library is present, but one of its dependent libraries is missing.
- The executable is Linux x86-64 but is run on an ARM64 node.
- The container has the binary but lacks CA certificates or timezone data.
- The application requires config files, templates, or native resources not included in the image.
- The container runs under a user lacking permission to read files or write to the temp directory.

The testing flow should proceed in order:

~~~mermaid
flowchart TD
    A["Built native executable"] --> B["Check OS, CPU architecture, and ABI"]
    B --> C["List shared library dependencies"]
    C --> D["Check JNI libraries and metadata"]
    D --> E["Check resources, CA, timezone, permissions"]
    E --> F["Run in target run image / host"]
    F --> G["Smoke tests and integration tests"]
    G --> H{"Do all critical paths work?"}
    H -->|Yes| I["Package and release artifact"]
    H -->|No| J["Analyze loader, logs, syscalls, and configuration"]
    J --> B
~~~

**Key takeaway:** inspecting the binary file on the build machine is only the first step. Results must be confirmed on the runtime image or target machine that will actually run the application.

## 2. Which Platform Aspects Does a Native Binary Depend On?

A native executable is not a cross-platform artifact like a Java JAR file. It is built for a specific target:

| Component | Example | Risk when environment differs |
|---|---|---|
| Operating system | Linux, Windows, macOS | Different executable formats and OS APIs |
| CPU architecture | x86-64, AArch64/ARM64 | Incompatible instruction set and ABI |
| Binary format | ELF, PE, Mach-O | OS loader only understands its corresponding format |
| C library | glibc, musl | Binary requires symbols or ABI not provided by runtime |
| C++ runtime | libstdc++, libc++ | JNI/native dependencies may require a specific runtime |
| Shared libraries | zlib, OpenSSL, libstdc++ | Missing files or wrong major versions fail to load |
| JNI libraries | libpayment.so, libcrypto-adapter.so | File not found, wrong architecture, or missing child dependencies |

Example error:

~~~text
cannot execute binary file: Exec format error
~~~

This message typically appears when the binary format or architecture does not match the runtime environment. Check `file` and the node/container architecture before investigating reflection or Spring.

A Linux x86-64 binary cannot be turned into ARM64 simply by copying files. You must build separately per target or use a multi-architecture build mechanism with matching builders/toolchains.

## 3. Checking Format and Architecture Before Running

On Linux:

~~~bash
# Check binary type and architecture
file ./application

# Machine architecture
uname -m
uname -s
~~~

Example output:

~~~text
application: ELF 64-bit LSB pie executable, x86-64, ...
x86_64
Linux
~~~

If the binary is AArch64, the host running it must support ARM64. In containers, inspect both the host and the image platform:

~~~bash
docker image inspect example/orders:native \
  --format '{{.Os}}/{{.Architecture}}'
~~~

On macOS:

~~~bash
file ./application
uname -m
otool -hv ./application
~~~

`file` identifies Mach-O and architecture. `otool` provides header and dependency information for macOS binaries.

On Windows PowerShell:

~~~powershell
Get-Item .\application.exe | Select-Object Name, Length, LastWriteTime
$env:PROCESSOR_ARCHITECTURE
~~~

You can use Developer Command Prompt with `dumpbin /headers application.exe` to inspect machine type and PE format. The Dependencies tool also helps inspect transitive dependencies and DLL architectures.

**Do not use a binary built for one OS to test on another OS.** If the deployment target is a Linux container, test inside a Linux run image or Linux node with the same architecture as production.

## 4. What Are Shared Libraries and Why Check Them?

A shared library is a native library loaded by the loader when a process starts or when requested by the program. On Linux, files usually have the `.so` suffix; macOS uses `.dylib` or frameworks; Windows uses `.dll`.

A native executable may depend on:

- The C library and dynamic loader.
- System libraries such as zlib, OpenSSL, or the C++ runtime.
- Native libraries supplied by the application or dependencies.
- JNI libraries invoked from Java code.
- Transitive dependencies of JNI libraries.

For example, an application calls an encryption library via JNI. The file `libcrypto-adapter.so` may exist, yet itself require `libssl.so` or `libcrypto.so`. If a transitive dependency is absent from the run image, the loader still cannot load the JNI library.

Illustrative library names do not mean every native image needs them. **Add only the exact libraries required by the binary or JNI dependencies**, avoiding installing entire system packages by guesswork.

## 5. Inspecting Dependencies on Linux with readelf and ldd

For an ELF binary, start with:

~~~bash
# Check binary type and architecture
file ./application

# List dynamic section and NEEDED libraries
readelf -d ./application | grep NEEDED

# Check dynamic loader/interpreter
readelf -l ./application | grep interpreter

# Inspect symbol version requirements, if needed
readelf --version-info ./application
~~~

The dynamic section may reveal dependencies such as:

~~~text
Shared library: [libc.so.6]
Shared library: [libz.so.1]
Shared library: [libstdc++.so.6]
~~~

The actual list depends on toolchain, configuration, and native dependencies. Some binaries statically link parts or all of certain libraries, so a long `NEEDED` list is not always present.

To see whether the loader can locate dependencies in the current environment:

~~~bash
ldd ./application
~~~

If you see:

~~~text
libz.so.1 => not found
~~~

then the current runtime has not found that library in its search paths. Install the package providing the exact SONAME in the runtime image or configure the appropriate path.

**Only run `ldd` on trusted binaries produced by your project.** For files of unknown origin, prefer `readelf -d` or `objdump -p` to read ELF information without invoking the loader on the binary.

If `ldd` reports `not a dynamic executable`, do not rush to conclude the binary is corrupt. The binary might be statically linked, not a matching ELF, or built for a different architecture/ABI. Cross-check with `file` and `readelf`.

## 6. Understanding glibc, musl, and ABI Version Errors

On Linux, binaries may depend on glibc or musl. These two implementations cannot be swapped arbitrarily.

A common error:

~~~text
version 'GLIBC_2.34' not found
~~~

This indicates the binary requires a newer glibc symbol version than the runtime provides. Causes include building on a newer distribution and running on an older one, or using a run image incompatible with the build environment.

Resolution steps:

1. Identify the glibc version required by the binary using `readelf --version-info`.
2. Check the glibc version inside the runtime image.
3. Build on a base image/toolchain compatible with the target runtime.
4. Or select a runtime image with a newer, organization-supported glibc.
5. Rebuild and run tests on that exact run image.

Alpine Linux typically uses musl instead of glibc. A binary built for glibc will not run on Alpine by default. If you want to use Alpine/musl, verify that your GraalVM and toolchain versions support the musl target, build with the proper configuration (such as `--libc=musl` if supported), and test on that actual musl runtime.

Do not simply install an unofficial glibc compatibility package onto Alpine and treat it as a production solution. That increases ABI complexity and operational risk.

## 7. Inspecting Libraries on macOS and Windows

### macOS

Use `otool -L` to view dynamic libraries:

~~~bash
file ./application
otool -L ./application
otool -l ./application
~~~

If a dependency has an install name pointing to a nonexistent path, the loader may report `Library not loaded`. Check paths, `@rpath`, `@loader_path`, and `@executable_path`; do not copy libraries into an arbitrary directory and assume the loader will find them.

### Windows

In Developer Command Prompt:

~~~bat
dumpbin /headers application.exe
dumpbin /dependents application.exe
~~~

`dumpbin /dependents` lists directly imported DLLs. Use the Dependencies tool to inspect transitive dependencies and DLL architectures as well.

Errors such as:

~~~text
The code execution cannot proceed because VCRUNTIME140.dll was not found
~~~

indicate a required runtime DLL is missing on the machine. Install or bundle the proper Microsoft Visual C++ runtime following the application's release policy, for the matching architecture.

**Never mix x86 DLLs with x64 executables**, and never grab DLLs off an arbitrary developer machine and copy them to production without checking source, version, and license.

## 8. JNI: Checking Both Metadata and Native Libraries

JNI allows Java code to call native functions and native code to call back into Java. With Native Image, two separate layers must be verified:

1. **JNI metadata:** classes, methods, fields, or constructors accessed by native code via JNI must be recognized/registered as required by Native Image.
2. **Native libraries:** JNI library files and all transitive dependencies must exist in the runtime environment with the matching OS, architecture, and ABI.

Example of Java declaring a native method:

~~~java
public final class NativeChecksum {

    static {
        System.loadLibrary("checksum");
    }

    public native long calculate(byte[] data);
}
~~~

On Linux, the library is typically named `libchecksum.so`. At runtime, the dynamic loader must also find libraries that `libchecksum.so` depends on.

Common errors:

~~~text
java.lang.UnsatisfiedLinkError: no checksum in java.library.path
~~~

or:

~~~text
java.lang.UnsatisfiedLinkError: /opt/native/libchecksum.so:
libcrypto.so.3: cannot open shared object file: No such file or directory
~~~

The first error typically relates to locating the JNI library. The second indicates the JNI library was found, but one of its dependencies is missing.

### Checking a JNI Library on Linux

~~~bash
file /opt/native/libchecksum.so
readelf -d /opt/native/libchecksum.so | grep NEEDED
ldd /opt/native/libchecksum.so
~~~

If the library sits outside default loader directories, place it in an appropriate directory or configure search paths. `LD_LIBRARY_PATH` can help the loader locate shared libraries, though explicit deployment paths, appropriate RUNPATH/RPATH configuration, or container packaging mechanisms are preferred.

`java.library.path` is the property for locating JNI libraries at the Java runtime layer; it does not replace the dynamic loader's search path for transitive dependencies of an ELF file. Check both layers when using `System.loadLibrary`.

### JNI Metadata

GraalVM has dedicated configuration for JNI, typically represented in `jni-config.json` in toolchains using metadata files. Spring `RuntimeHints` also provides a JNI API to register required types where appropriate for your Spring Framework version.

The Tracing Agent can record JNI access during executed flows. However, the agent only sees paths that actually ran; test callbacks from native code into Java as well, not just Java-to-native calls.

## 9. Serialization: A Runnable Binary Can Still Lack Data Types

Serialization is not an OS shared library. It is another category of dynamic access that must be verified when migrating applications to Native Image.

Java serialization, framework serializers, or data binding may require constructors, fields, record components, methods, or type metadata. Native Image may not fully infer types selected dynamically through object graphs or external data.

DTO example:

~~~java
public record PaymentEvent(
    String paymentId,
    BigDecimal amount
) implements Serializable {
}
~~~

If the application uses Java serialization for dynamically selected types, confirm those types are registered for serialization as required by GraalVM. With Spring, you can use serialization hints in `RuntimeHints` or appropriate annotations for binding/serialization. Do not confuse a constructor reflection hint with serialization registration; these two purposes can require separate metadata.

Errors such as `ClassNotFoundException`, `InvalidClassException`, or missing reflection registration during deserialization should be categorized separately:

- Is the class included in the executable?
- Is the type registered for serialization?
- Are required constructors/fields prepared?
- Are the schema or `serialVersionUID` compatible across versions?
- Is data serialized on the JVM compatible with the running native version?

Tests should use representative data, including data saved from previous versions, rather than only serializing and deserializing within the same new process.

## 10. Testing in the Exact Container Run Image

A common mistake is building inside a builder image and then copying only the executable into a tiny image or `scratch`. The builder may contain compilers, libc, OpenSSL, zlib, and many tools absent from the run image.

With Cloud Native Buildpacks, the builder and run image have distinct roles:

- **Builder image** provides the detect/build environment, compilers, buildpacks, and artifact-building tools.
- **Run image** provides the operating system and libraries needed to run the artifact.
- **Final application image** combines the executable, launch metadata, and required runtime components.

If using Spring Boot `bootBuildImage` or `spring-boot:build-image`, test the exact image produced:

~~~bash
docker image inspect example/orders:native \
  --format '{{.Os}}/{{.Architecture}}'

docker run --rm --publish 8080:8080 example/orders:native
~~~

Do not test only the executable inside the builder and conclude the runtime image will work. Run smoke tests in the final image or an image sharing the exact run image and runtime packages.

If writing a multi-stage Dockerfile yourself, both build and runtime stages must be deliberately chosen. General skeleton example:

~~~dockerfile
FROM build-stage AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew nativeCompile

FROM runtime-base AS runtime
WORKDIR /app
COPY --from=build /workspace/build/native/nativeCompile/application /app/application
USER 10001
ENTRYPOINT ["/app/application"]
~~~

This is a skeleton, not a complete Dockerfile for every project. `runtime-base` must supply libc and required shared libraries; if the application uses JNI, copy JNI libraries and configure loader paths. Do not select `scratch` before confirming the binary truly requires no shared libraries or other system files.

## 11. Why Can Distroless or Scratch Still Fail?

Small images reduce attack surface and deployment size, but that does not mean every native executable can run in a minimal image.

`scratch` provides no shell, package manager, CA bundle, timezone data, or shared libraries. `distroless` also contains only a curated set of files for a specific purpose; not every variant includes libc, CA certificates, or native libraries required by your application.

Before choosing a minimal image, verify:

- The dynamic loader is present at the path required by the ELF interpreter.
- glibc/musl and shared libraries match required versions.
- JNI libraries along with transitive dependencies are in the image.
- A CA certificate bundle is present if making HTTPS calls.
- The timezone database is present if the application needs zones like `Asia/Ho_Chi_Minh`.
- External resources, config files, fonts, locales, or temp directories are available as needed.
- An unprivileged user has read/execute permissions on the executable and write permissions on allowed directories.

If a shell is missing in distroless, use the corresponding debug image or run diagnostic tools in a temporary container sharing the same filesystem/runtime packages. There is no need to install a shell into the production image solely for debugging.

## 12. Checking Resources and Filesystem Items Beyond Shared Libraries

A binary may start successfully yet still fail on a feature due to missing environment files:

| Component | Symptom | How to verify |
|---|---|---|
| CA certificate bundle | HTTPS reports PKIX/certificate path errors | Check CA path and certificate packages |
| Timezone database | Zone ID not found or times render inaccurately | Check `/usr/share/zoneinfo` and runtime timezone |
| Locale data | Date/number formatting or characters differ from expectations | Check locale settings and locale data in the image |
| Fonts | PDFs/images missing text or failing to render | Check font files and fontconfig if used |
| Templates/configs/schemas | Resource not found | Distinguish classpath resources from filesystem mounts |
| `/tmp` directory | Errors creating temporary files | Check existence, write permissions, and capacity |
| DNS resolver | Unable to connect to hostnames | Check DNS inside container/network namespace |
| Socket/device files | Unable to open device or socket | Check mounts, permissions, and container policies |

Classpath resources must be included in the Native Image via resource hints or appropriate AOT mechanisms. External files such as `/etc/orders/rules.json` must be mounted/copied onto the runtime filesystem. Having a file in the repository does not guarantee it exists at the corresponding filesystem path inside the container.

## 13. Running Meaningful Smoke Tests on the Runtime Image

A smoke test should verify critical paths, not merely check that the process is alive.

For example:

~~~bash
# Run container in the background
docker run -d --name orders-native-test \
  -p 18080:8080 \
  example/orders:native

# Wait for the application to be ready; native startup times can still vary.
for attempt in $(seq 1 30); do
  if curl --fail --silent http://localhost:18080/actuator/health >/dev/null; then
    break
  fi
  sleep 1
done

# Check health endpoint
curl --fail http://localhost:18080/actuator/health

# Test a business operation involving serialization
curl --fail \
  -H 'Content-Type: application/json' \
  -d '{"paymentId":"P-100","amount":125.50}' \
  http://localhost:18080/api/payments

# Stop and remove test container
docker rm -f orders-native-test
~~~

These URLs and endpoints are only examples; substitute your application's real APIs. If the application uses a database or broker, smoke tests should confirm connectivity to those dependencies in the test environment. For JNI, invoke at least one real native method. For serialization, send payloads with dynamic data types and verify the returned data.

If Actuator is not present, use a readiness endpoint provided by the application. Never use an open TCP port as the sole proof that the entire application is ready.

## 14. Running as an Unprivileged User with a Restricted Filesystem

Production containers typically run non-root and may use a read-only root filesystem. A binary that runs as root may not run under that configuration.

Verify:

- The user has execute permissions on the binary and JNI libraries.
- Config files, certificates, and resources have read permissions.
- The application only writes to permitted volumes/directories.
- `java.io.tmpdir` or native temp directories used by libraries are writable.
- Selected ports comply with the user and container policy.
- There is no assumption that the process can create files in the installation directory.

Example running a container with a specific user:

~~~bash
docker run --rm \
  --user 10001:10001 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --publish 8080:8080 \
  example/orders:native
~~~

This is a hardening example. If the application must write uploaded files or data, mount a separate volume with appropriate ownership/permissions. Do not enable `--read-only` without knowing where the application needs to write; use it as a test to uncover filesystem assumptions.

## 15. Diagnosing Missing Libraries with strace and Loader Diagnostics

On Linux, `strace` helps observe file opens and failing syscalls:

~~~bash
strace -f -e trace=file -o /tmp/orders-files.log ./application
~~~

Then search for lines containing `ENOENT` or `EACCES`:

~~~bash
grep -E 'ENOENT|EACCES' /tmp/orders-files.log
~~~

`ENOENT` indicates the path did not exist at access time; `EACCES` indicates permission denied. Distinguish optional files probed across multiple paths from an actual dependency causing the application to fail.

With the glibc dynamic loader, you can enable:

~~~bash
LD_DEBUG=libs ./application
~~~

The loader prints library search details. Output can be very verbose and expose environment paths; enable only during debugging sessions.

When errors occur only in a container, run diagnostics **inside that same runtime image** or an equivalent debug image. `ldd` on the build host does not prove a library exists inside the container.

## 16. Common Error Matrix

| Symptom | Likely cause | Resolution |
|---|---|---|
| `Exec format error` | Wrong OS or CPU architecture | Build for the right target and inspect image platform |
| `No such file or directory` even though binary exists | ELF interpreter/dynamic loader missing | Check `readelf -l`, runtime libc, and loader path |
| `libxyz.so: cannot open shared object file` | Shared library missing or not found by loader | Check `readelf -d`, `ldd`, install package, or fix search path |
| `GLIBC_2.xx not found` | Runtime glibc older than binary requires | Build on a compatible base or upgrade run image |
| `Error loading shared library` on Alpine | musl/glibc mismatch or missing dependency | Use matching libc target, rebuild for musl if supported |
| `UnsatisfiedLinkError: no ... in java.library.path` | JNI library not found | Check filename, path, OS/arch, and load configuration |
| JNI library found but reports missing dependent lib | Missing transitive dependency | Run `ldd` on the JNI library itself inside the runtime image |
| `PKIX path building failed` | Missing CA certificates or improper truststore | Install/supply CA bundle and test HTTPS |
| Zone ID not found | Missing timezone database or zone data | Supply tzdata or appropriate configuration |
| `Permission denied` | User lacks execute/read/write permission | Fix owner, mode, and volume mounts |
| Deserialization fails on native | Missing serialization/reflection metadata or schema mismatch | Register required types and test representative data |
| Resource returns null | Wrong resource hint or file path | Check classpath resources and file mounts |

A `No such file or directory` message while the executable file is visibly present often misleads newcomers into checking the binary path. On Linux, an important cause is **the interpreter recorded in the ELF header is absent from the runtime image**. Use `readelf -l` to inspect `Requesting program interpreter`.

## 17. Testing on the Exact Release Architecture and Run Image

CI should have at least one job testing on the same OS/libc/architecture as the deployment environment.

Example matrix:

| Artifact | Runtime test | What to verify |
|---|---|---|
| Linux x86-64, glibc | Production x86-64 run image | Loader, glibc, JNI, certificates, and APIs |
| Linux ARM64, glibc | ARM64 run image/node | Matching binary architecture, native dependencies on same architecture |
| Linux musl/Alpine | Actual musl runtime | Binary built for exact musl target and all libraries present |
| Windows x64 | Matching Windows host/runtime | PE/DLL dependencies and JNI DLLs |
| macOS ARM64 | macOS ARM64 | Mach-O dependencies, frameworks, and native libraries |

You do not necessarily have to support every target. Simply identify the platforms you actually release for and test each of them. For multi-arch images, verify each platform manifest and run smoke tests on the corresponding runner/node; the existence of a manifest does not prove the binary works on every architecture.

## 18. Pre-Release Verification Workflow

A binary verification pipeline can include:

1. **Record build target:** OS, architecture, GraalVM/JDK version, libc/toolchain, builder, and run image.
2. **Inspect binary:** `file`, ELF interpreter, `NEEDED` libraries, symbol versions.
3. **Verify JNI:** confirm library files, architecture, metadata, and transitive dependencies.
4. **Verify serialization:** run tests with dynamically selected types and payloads.
5. **Verify resources:** CA, timezone, locale, fonts, templates, configs, and external files.
6. **Run final image:** do not run only on the builder or build host.
7. **Run non-root/read-only test:** verify file permissions, temp directories, and volumes.
8. **Smoke/integration tests:** call endpoints, access databases/brokers, HTTPS, JNI, and serialization.
9. **Save artifacts and evidence:** image digest, binary checksum, dependency report, test logs, and toolchain versions.

If there are multiple runtime environments, run a matrix across each target. A passing test on Ubuntu glibc does not prove the binary is compatible with Alpine musl or Windows.

## 19. Hands-On Exercise: Detecting a Missing Library in a Container

Suppose a Spring Boot application has an endpoint calling the `checksum` JNI library to compute file checksums. On a dev machine, the app works normally; inside the runtime container, the endpoint fails with `UnsatisfiedLinkError`.

### Step 1 — Inspect the Application Binary

~~~bash
file ./application
readelf -l ./application | grep interpreter
readelf -d ./application | grep NEEDED
~~~

Identify the target and direct dependencies of the executable.

### Step 2 — Inspect the JNI Library

~~~bash
file ./lib/libchecksum.so
readelf -d ./lib/libchecksum.so | grep NEEDED
ldd ./lib/libchecksum.so
~~~

If you see:

~~~text
libcrypto.so.3 => not found
~~~

then you need to supply the package containing `libcrypto.so.3` in the runtime image or rebuild the JNI library with compatible dependencies.

### Step 3 — Check Paths

Ensure `libchecksum.so` actually exists in the image with proper read permissions and architecture. Confirm code using `System.loadLibrary("checksum")` can locate the library via the runtime's mechanism; also check search paths for transitive dependencies of the ELF loader.

### Step 4 — Run in the Final Image

Start the exact image to be released, call the checksum endpoint, and verify the result. If the minimal container lacks `ldd`, use an equivalent debug image or inspect the ELF on the host with `readelf`, then confirm with a smoke test in the final runtime.

### Step 5 — Verify Serialization Too

Send a payload with binary/base64 fields or a DTO deserialized before calling JNI. Verify both the deserialization step and the native method work, distinguishing serialization metadata errors from JNI loader errors.

### Tracking Table

| Item | Result to record |
|---|---|
| OS/architecture | Linux x86-64, ARM64, or actual target |
| libc/runtime | glibc/musl and version |
| Native executable dependencies | `NEEDED` list, interpreter |
| JNI dependencies | JNI file and transitive dependencies |
| Serialization | Tested types/payloads |
| Runtime image | Builder/run image tag or digest |
| Permissions | User, file permissions, temp directory |
| Smoke test | Endpoint and native operation succeeded |

## 20. Key Takeaways

A native executable only runs reliably when **binary, OS, architecture, ABI, shared libraries, JNI libraries, and runtime resources** match the target environment. A successful build on a development machine does not prove system dependencies are present in the final container.

Inspect ELF/PE/Mach-O files, dynamic loaders, and dependencies using platform tools; inspect JNI libraries alongside transitive libraries; register metadata for serialization/JNI where needed; and run smoke tests on the actual run image or a production-equivalent host. CA files, timezones, fonts, templates, access permissions, and temp directories are also part of the runtime contract.

**Release evidence should be the execution result of the final artifact in the target environment**, accompanied by platform, image digest, dependency report, and test logs. This practice detects missing-library errors before a native executable is rolled out widely.

### References

- GraalVM — Native Image Compatibility and Runtime: https://www.graalvm.org/reference-manual/native-image/
- GraalVM — JNI in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/JNI/
- GraalVM — Serialization in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/Serialization/
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- Linux man-pages — ldd(1), readelf(1), ld.so(8).

Tool syntax and metadata may vary by GraalVM version, operating system, and builder. When deploying, verify against the exact toolchain and runtime image pinned in your project.
