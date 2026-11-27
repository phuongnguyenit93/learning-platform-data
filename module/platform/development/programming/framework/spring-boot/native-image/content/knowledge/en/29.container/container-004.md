# Limits of Using scratch or distroless When System Resources Are Still Needed

## 1. Why the Smallest Image Is Not Always the Right Image

Native Image produces an executable independent of the traditional JVM runtime, making it possible to package a Spring Boot application in a very small container. This makes base images like `scratch` or distroless appealing: fewer packages, a smaller attack surface, and lower transfer size.

However, a native executable may still depend on OS libraries, CA certificates, a timezone database, DNS/NSS, temporary directories, and other runtime resources. Removing the shell and package manager also changes how debugging, health checks, and operations work. A tiny image missing a library or system data can prevent the application from starting, break HTTPS connections, misresolve DNS, or handle time incorrectly.

In the **SPRING_BOOT_NATIVE_IMAGE** module, you should choose a base image based on the executable's actual dependencies and operational requirements. This lesson explains the limits of `scratch` and distroless, how to inspect ELF/shared libraries, which system resources are commonly overlooked, and a verification workflow for production-like images.

## 2. Distinguishing scratch, distroless, and Minimal OS Images

| Image Type | Characteristics | Operational Impact |
|---|---|---|
| `scratch` | Empty image; no shell, package manager, libc, or CA bundle | Can only run copied binaries and files; every dependency must be explicitly provided |
| Distroless | Contains only a minimal set of runtime files, typically no shell/package manager | Fewer debugging tools; must pick the right variant and verify shared libraries |
| Minimal OS image | Includes baseline userspace/packages, fewer packages than a full OS | Easier to add CA certs, timezone data, libc, and needed tools |
| Full OS image | Many system utilities | Easy to debug, but larger image with a broader package surface |

Distroless is not a single image. Different variants may provide different libc, CA certificates, or runtime components. Read the contents and purpose of the exact image tag you use.

`scratch` provides no system dependencies on its own. If a binary is dynamically linked, copying only the binary into scratch will usually fail. Even if a binary is statically linked, the application may still need CA certificates, timezone data, configuration files, or other system data.

## 3. Native Executable Does Not Equal Static Executable

GraalVM Native Image builds a native executable, but that does not mean the binary always embeds all OS libraries. Depending on the toolchain and build configuration, the executable may dynamically link against libc and shared libraries.

Inspect the binary on Linux:

```bash
file orders-service
ldd orders-service
readelf -l orders-service
readelf -d orders-service
```

- `file` shows the format, architecture, and basic ELF info.
- `ldd` lists shared library dependencies in a suitable environment.
- `readelf -l` inspects ELF program headers, including the interpreter if present.
- `readelf -d` displays the dynamic section and dependency entries.

Run `ldd` only on trusted binaries in a safe environment; for untrusted artifacts, prefer static ELF inspection tools like `readelf`. Results depend on the inspection environment: a library may be found on the host yet be absent inside the container runtime.

## 4. libc and ABI Must Be Compatible

Linux executables typically depend on a specific ABI environment. For example, a binary built for glibc requires a runtime with a compatible glibc. An image providing only musl will not automatically run a glibc binary just because both are Linux.

Items to verify:

- Does the binary's target architecture match the host node/container?
- Does the executable use glibc or musl?
- Does the dynamic loader recorded in the ELF exist in the image?
- Are the symbol versions of shared libraries compatible?
- Are additional libraries such as `libstdc++`, `libgcc_s`, or SDK native libraries provided?

If you want a very small image, decide on the toolchain and linking strategy upfront. Switching to musl or static linking may require a different builder, native toolchain, and configuration; you cannot simply swap the base image in a Dockerfile and expect the binary to become compatible.

## 5. Scratch and the Static Binary Case

A statically linked executable can reduce the number of shared libraries needed in the runtime image. However, “static” only describes how certain components are linked; it does not mean all runtime needs disappear.

The application may still need:

- CA certificates to verify TLS servers.
- A timezone database for timezone processing.
- Mounted configuration files or secrets.
- A temporary write directory or upload directory.
- Dynamically loaded native libraries.
- Proper DNS/NSS configuration.
- User/group identity or system files expected by libraries.

In addition, static linking with libc can affect DNS, name services, and security updates. Test actual behavior against the resolver and network of your deployment environment rather than relying solely on a successful build command.

## 6. CA Certificates and HTTPS Connections

Spring Boot applications frequently make HTTPS calls to partner APIs, database proxies, identity providers, or telemetry collectors. TLS requires a trust store containing the appropriate CAs.

If the base image lacks a CA bundle, HTTPS connections can fail with certificate verification errors even when DNS and TCP work normally.

Some systems store bundles at paths such as:

- `/etc/ssl/certs/ca-certificates.crt`
- `/etc/pki/tls/certs/ca-bundle.crt`

Paths vary by distribution. Do not hardcode a single path if the application must run across multiple base images. You can configure the trust store explicitly or copy a properly formatted CA bundle from an appropriate stage.

Never disable certificate verification to “fix” a missing CA error. Add valid trust roots and test HTTPS from the final container image itself.

## 7. Timezone Database and Locale Data

Java APIs handle `ZoneId`, `ZonedDateTime`, date/time formatting, and locales. A native executable still requires timezone/locale data consistent with how the runtime was built and configured.

If the OS timezone database or required locale data is missing, the application may:

- Fail to recognize an expected zone name.
- Fall back to an unintended default.
- Format dates, times, or numbers differently than expected.
- Behave differently locally versus in a container.

Not every Java API depends directly on the `tzdata` package; GraalVM/JDK may bundle or consume data via its own mechanisms. Check the exact APIs used, how Native Image is built, and the runtime base image.

For timezone-sensitive business logic, use explicit zone IDs such as `Asia/Ho_Chi_Minh` and test them in the executable inside the final image. Do not rely solely on the build machine's default timezone.

## 8. DNS, NSS, and Resolver Configuration

Containerized applications commonly reach services via DNS names such as `orders-db`, `payment-api`, or internal Kubernetes service names. Name resolution can depend on:

- `/etc/resolv.conf`.
- `/etc/hosts`.
- `/etc/nsswitch.conf`.
- libc/resolver implementation.
- DNS search domains and network policies.

A scratch image does not ship with these files, though the container runtime or orchestrator may mount certain system files into the container. Mounting behavior and resolver capabilities depend on the runtime, libc, and how the binary is linked.

Do not assume DNS works simply because the container can open a TCP connection to a fixed IP. Test using real service hostnames in the intended network namespace and runtime platform.

## 9. /tmp, Filesystem, and Write Permissions

Some libraries create temporary files, caches, locks, or spool files. Common locations include `/tmp`, `/var/tmp`, or custom-configured directories.

Scratch does not include these directories by default. If the application must write temporary files, create the directory in the image or mount a runtime volume, and set permissions matching the user running the process.

Example Dockerfile:

```dockerfile
FROM scratch
WORKDIR /app
COPY --chown=10001:10001 orders-service /app/orders-service
COPY --chown=10001:10001 --from=certs /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

This is an illustration only and requires a `certs` stage defined in the actual Dockerfile. Scratch has no `/tmp` by default; if needed, create the directory in a build stage and copy it with the right owner/mode, or mount a writable volume.

Prefer a read-only root filesystem for the application where possible, granting only the necessary writable paths. Test uploads, exports, temporary files, and cleanup using the exact runtime UID/GID.

## 10. Users, Groups, and Identity in Minimal Images

Scratch does not contain `/etc/passwd` or `/etc/group` by default. Some runtimes or libraries look up a username, group, or home directory via the OS. Distroless variants may provide a default user or varying metadata.

You can specify a numeric UID/GID in the Dockerfile:

```dockerfile
USER 10001:10001
```

A numeric identity avoids depending on usernames in the passwd database, but it does not automatically create a home directory or grant write permissions. Verify that:

- The executable has execute permission for the UID.
- The working directory has read permission.
- Writable directories exist and are properly owned.
- Kubernetes volume mounts match the UID/GID.
- Libraries do not depend on resolving a username to construct paths.

Never run as root just to avoid permission errors. Identify the exact files/paths requiring permissions and grant least privilege.

## 11. Shell and Package Manager Are Unavailable

Distroless and scratch typically omit `sh`, `bash`, `apt`, `apk`, and `yum`. Consequently, the following operations usually do not work inside the container:

- `docker exec -it ... sh`
- Installing packages after the container starts.
- Running a shell script as the entrypoint.
- Using shell form to chain startup commands.
- Installing debugging tools in a production container.

Use an exec-form entrypoint:

```dockerfile
ENTRYPOINT ["/app/orders-service"]
```

Avoid:

```dockerfile
ENTRYPOINT /app/orders-service
```

Shell form requires a shell to execute and can interfere with process termination signals. For images without a shell, exec form is the proper choice.

For debugging, use ephemeral debug containers, a sidecar/tooling image, or run the binary in a staging environment with the needed tools. Do not add a shell to a production image solely for manual troubleshooting convenience.

## 12. Shell-Independent Health Checks and Readiness

Some Dockerfiles use:

```dockerfile
HEALTHCHECK CMD curl -f http://localhost:8080/actuator/health
```

This does not work if the image lacks `curl` or a shell. Shell-command Docker `HEALTHCHECK` instructions also depend on a shell existing in the image.

Options:

- Use Kubernetes startup/readiness/liveness probes that call HTTP directly from the kubelet.
- Use a small, intentionally packaged healthcheck binary.
- Use container-platform health check mechanisms that do not require a shell.
- Omit Docker `HEALTHCHECK` when the orchestrator already manages health probes appropriately.

With Spring Boot, configure Actuator health probes and expose only the required endpoints. Readiness should reflect the ability to accept traffic; liveness should avoid restarting the process solely because of a transient dependency outage.

## 13. Logging and stdout/stderr

Container applications should log to stdout/stderr for collection by the runtime platform. There is no need to install a syslog daemon inside the image solely for application logs.

Verify that:

- The logging backend does not require a default file path that does not exist.
- Log rotation is managed by the container platform/agent.
- Logs are not written to a read-only filesystem without a volume.
- Stack traces contain enough diagnostic detail without leaking secrets.
- Encoding/locale matches what the log collector expects.

If audit or output files are needed, declare volumes and retention explicitly. Distroless/scratch do not ship log rotation tools; that is the responsibility of the runtime platform or a sidecar/agent.

## 14. Native Libraries and Runtime File Dependencies

Some Java dependencies call native libraries via JNI/JNA or platform libraries. A native executable may depend on additional `.so` files or libraries beyond the main binary.

Inspect dependencies:

```bash
ldd orders-service
readelf -d orders-service
```

If a library is loaded via `System.loadLibrary`, its filename and loader path must be valid inside the runtime image. Ensure the library matches the architecture, ABI, and version; copy the exact file along with its dependencies.

Do not rely solely on `ldd` if the application dynamically loads libraries by name at runtime. Test the JNI/JNA APIs directly from the executable and check for loader errors in the final container.

## 15. Distroless Can Be a Balanced Choice

Distroless is often a good fit when you want fewer packages while keeping selected userspace components. Still, you must choose the right variant:

- A variant with glibc/shared libraries matching the executable.
- A variant with CA certificates if HTTPS is needed.
- A variant with timezone data if the use case requires it.
- A variant matching the architecture and native dependencies.
- A clear default user or non-root configuration.

Distroless tag names and contents vary by publishing project. Read the official documentation and inspect the image filesystem/manifest; do not infer contents solely from names like `base`, `static`, or `cc`.

Distroless reduces debugging utilities in the final image. You can use the corresponding debug image in troubleshooting environments, while ensuring the binary and runtime dependencies match production.

## 16. Multi-Stage Builds Do Not Automatically Solve Runtime Dependencies

Multi-stage builds keep compilers, Maven/Gradle caches, and source code out of the runtime image:

```dockerfile
FROM build-image AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -Pnative -DskipTests package

FROM runtime-image
WORKDIR /app
COPY --from=build /workspace/target/orders-service /app/orders-service
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

This example may not be sufficient for every application. If the runtime needs a CA bundle, timezone data, native libraries, configs, or a temporary write directory, add them explicitly to the final stage or mount them at runtime.

Builder and runtime must be compatible in OS, libc, architecture, and ABI. Copying a binary from an Ubuntu/glibc builder into scratch or a musl-only runtime can fail even when the multi-stage Docker build succeeds.

## 17. Test the Final Image Instead of Only the Build Stage

A successful Docker image build only proves the layers were created. Run the final image itself against these scenarios:

1. Start with the production UID/GID.
2. Confirm the readiness endpoint responds properly.
3. Call an HTTPS endpoint to verify CA trust.
4. Call a service via internal DNS name.
5. Verify critical timezone/locale behavior.
6. Exercise features that write temporary files.
7. Invoke JNI/native libraries if the application uses them.
8. Send SIGTERM and confirm graceful shutdown.
9. Inspect stdout/stderr logs and exit code.
10. Run with a read-only root filesystem if required by the architecture.

Do not run tests on the builder stage and assume the final image works. The runtime image may lack files that the builder happened to supply.

## 18. Diagnosing Common Errors

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `exec format error` | Wrong architecture or binary format | `file`, target platform, and image manifest |
| `No such file or directory` even though binary exists | ELF interpreter/loader missing from image | `readelf -l`, libc, and dynamic loader |
| `error while loading shared libraries` | Missing shared library or ABI mismatch | `ldd`, `readelf -d`, runtime image |
| HTTPS certificate failure | Missing CA bundle or wrong trust store | CA path and TLS test inside the container |
| Cannot resolve service name | Resolver/NSS/DNS config or network issue | `resolv.conf`, runtime network, hostname test |
| Timezone error | Missing/different timezone data or default zone | Test explicit ZoneId and tzdata |
| Permission denied | UID/GID lacks access to file/path | Owner/mode and volume security context |
| Cannot create temporary files | Missing `/tmp` or read-only filesystem | Writable path and temp directory config |
| Docker exec has no shell | Minimal image by design | Debug container or staging tooling |
| Health check always fails | Healthcheck invokes missing curl/shell | Use orchestrator probe or binary healthcheck |

## 19. Hands-On Exercise: Choosing Between scratch and distroless

**Scenario:** A native Order API must make HTTPS calls to a payment provider, resolve internal DNS service names, handle Vietnam timezones, and write temporary files when exporting invoices.

**Step 1 — Inspect the executable.** Run `file`, `readelf`, and `ldd` in a compatible builder to identify architecture, interpreter, and shared library dependencies.

**Step 2 — Create a runtime dependency inventory.** List libc, CA certificates, DNS/NSS, timezone data, temp directories, native libraries, and writable paths.

**Step 3 — Create a distroless variant.** Pick the right runtime variant containing required dependencies, run with a non-root UID, and use an exec-form entrypoint.

**Step 4 — Create a scratch variant if appropriate.** Copy only the binary and explicitly identified files; create writable directories if needed, and add CA/timezone data as required. Do not assume a static binary carries all system data on its own.

**Step 5 — Run the same test suite.** Verify startup/readiness, HTTPS, DNS, timezone, file export, logs, and graceful shutdown on each image.

**Step 6 — Verify security.** Confirm non-root execution, filesystem permissions, package inventory, exposed ports, and secret mounts.

**Step 7 — Measure the artifacts.** Compare image size, pull time, and operational cost; document how compressed/unpacked layers were measured.

**Step 8 — Choose the image.** Select the smallest image that satisfies the full runtime contract, debugging workflow, and security requirements; keep the dependency inventory to re-verify on future upgrades.

Completion criteria: OS dependencies are inventoried; the final image starts and runs real functionality; HTTPS/DNS/timezone/filesystem behavior is verified; the process runs non-root; and the base image choice is backed by metrics and evidence.

## 20. Conclusion

Scratch and distroless can shrink image size and package count, but a native executable still needs the right system components. libc/loader, shared libraries, CA certificates, DNS/NSS, timezone data, user identity, temporary directories, native libraries, and health/debug tooling must all be evaluated against the real application.

Inspect the binary's ELF metadata and dependencies, choose the right runtime variant, use non-root execution and an exec-form entrypoint, and run tests on the final image itself. A minimal image is only valuable when it still satisfies the full runtime contract: starting up, connecting, processing data, writing needed files, emitting logs, and shutting down safely.
