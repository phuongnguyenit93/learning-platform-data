# Testing Images in the Deployment Environment

## 1. Why Must Runtime Images Be Tested in the Deployment Environment?

When packaging a modular application with `jlink`, the project produces a runtime image containing the JVM and the required set of modules. When deploying via containers or servers, the application usually runs from this image rather than using a full JDK on a development machine.

A successful build does not prove the image can run in production. The deployment environment may differ from the build machine in operating system, CPU architecture, native libraries, process-running user, filesystem permissions, environment variables, TLS certificates, DNS, timezone, and network configuration.

An image can start on a developer machine yet fail inside a container because:

- The runtime image was created for a different operating system or CPU architecture.
- A JDK module is missing because the `jlink` configuration did not include a required dependency.
- A service provider was not linked into the image.
- The application still references a file or executable that only exists on the build machine.
- The production user lacks permission to read configuration files, write to temporary directories, or open ports.
- The base image lacks native libraries or CA certificates needed by the application.
- Runtime flags, environment variables, or the working directory differ from the tested environment.

Therefore, you must test the exact artifact to be released, in an environment as close to production as possible. Do not simply run tests with the build machine's JDK and assume the runtime image will also work.

## 2. Distinguishing Artifact Types to Test

In a modular packaging workflow, there are usually three types of artifacts:

| Artifact | Contents | What to Verify |
| --- | --- | --- |
| Modular JAR | Application bytecode and `module-info.class` | Module descriptor, dependencies, and service declarations are correct. |
| Runtime image | JVM along with modules linked by `jlink` | The image has all needed modules, runs on the target platform, and does not depend on an external JDK. |
| Container image | Runtime image or JRE along with the application, config, and container filesystem | The process runs with the actual base image, user, network, mounts, and resource limits. |

If using `jpackage`, the native application package also includes a launcher, metadata, and OS-specific installation layout. The installed package should be tested and run as a production user, not just by running the JAR file inside.

A meaningful test must use the exact final artifact. For example, if production runs a container built from the runtime image, test that container. If you only run the `build/runtime-image` directory on a developer machine, container differences remain untested.

## 3. Identifying the Target Platform Before Building the Image

The runtime image created by `jlink` depends on the platform of the JDK used to build it. Do not treat the image as a portable Java package that can be copied arbitrarily across Linux, Windows, macOS, or across different CPU architectures.

Before building, record:

- Operating system and version or base distribution.
- CPU architecture, such as x86_64 or AArch64.
- JDK version and vendor used to compile and link.
- Container base image and version/digest if deploying with Docker.
- External native libraries or executables needed by the application.
- User/group, working directory, and filesystem mounts in production.

If production runs Linux containers on a specific distribution, build and test the image in a compatible Linux environment. An image built on Windows cannot be transferred as-is to Linux simply because both use Java 21.

For Linux, differences between distributions can also involve glibc, OpenSSL, fonts, timezone data, and other native libraries. For applications with JNI/JNA, native drivers, or native math libraries, verify both architecture and library ABI.

## 4. Creating a Testable Runtime Image

For example, a modular application has main module `com.acme.app`, with dependent modules in the `mods` directory. Use JDK 21 to create the image:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --launcher app=com.acme.app/com.acme.app.Main \
  --output build/runtime-image
~~~

Explanation:

- `--module-path` supplies JDK modules and application modules to the linker.
- `--add-modules` selects the root module to resolve the dependency graph.
- `--bind-services` instructs the linker to consider service providers that can be linked from observable modules.
- `--launcher` creates a launcher named `app` pointing to the module's main class.
- `--output` is the generated runtime image directory.

If the application uses service providers through JPMS, confirm the consumer declares `uses` and the provider declares `provides` in their descriptors. `--bind-services` cannot fix an incorrect descriptor or add a provider JAR not on the module path.

You can use options such as `--strip-debug`, `--no-header-files`, `--no-man-pages`, or `--compress` to reduce image size. Apply them only after determining the required configuration and having tests prove the application still works. Size optimization should not remove data or runtime components that the application needs.

## 5. Inspecting Runtime Image Contents

After linking succeeds, inspect the image before running the application.

### 5.1. Checking the Java Executable and Version

On Linux/macOS:

~~~bash
build/runtime-image/bin/java -version
build/runtime-image/bin/java --list-modules
~~~

On Windows:

~~~powershell
build/runtime-image/bin/java.exe -version
build/runtime-image/bin/java.exe --list-modules
~~~

Always invoke the executable using its path inside the image. If you only type `java -version`, the shell may invoke the JDK on the build machine or another Java in PATH, causing test results not to reflect the image.

Verify:

- The runtime has the expected Java version.
- Application modules are linked if you chose to package application modules into the image.
- Required JDK modules are present.
- Required service provider modules are linked when using service binding.
- The image does not accidentally rely on a full JDK pre-installed on the test machine.

### 5.2. Checking the Module Graph and Service Binding

You can use:

~~~bash
build/runtime-image/bin/java --list-modules
~~~

to view the modules inside the runtime image.

When diagnosing service providers, cross-check consumer modules with `uses` and provider modules with `provides`. If the image needs a provider that is missing from the runtime image, review the module path and `--bind-services` or the module set specified with `--add-modules`.

If the application is released as separate JARs rather than linked into the image, test module resolution using the runtime image itself:

~~~bash
build/runtime-image/bin/java \
  --show-module-resolution \
  --module-path app/mods \
  --module com.acme.app/com.acme.app.Main
~~~

Do not use an external JDK to run this check. The goal is to confirm the linked runtime can resolve and run the application's module graph properly.

### 5.3. Checking the Application's Module Descriptor

Use appropriate JDK tooling to inspect the descriptor of a modular JAR:

~~~bash
jar --describe-module --file app/mods/com.acme.app.jar
~~~

If you need to check dependencies on JDK modules, you can use:

~~~bash
jdeps --print-module-deps --module-path app/mods app/mods/com.acme.app.jar
~~~

The output helps compare the required module set with the runtime image. Static analysis tools may not fully detect dependencies used through reflection, JNI, resources, or dynamically configured class names. Those paths must be verified by integration tests in a realistic environment.

## 6. Smoke Testing with the Runtime Image Itself

A smoke test should confirm that the image can start the application and execute a minimal functional flow. Do not just check whether the process returns exit code 0; a server can start and immediately stop due to configuration errors, or keep running while failing to serve requests.

Example running the launcher created by `jlink`:

~~~bash
build/runtime-image/bin/app
~~~

Or running the module directly:

~~~bash
build/runtime-image/bin/java \
  --module com.acme.app/com.acme.app.Main
~~~

If application modules are not linked into the image but distributed separately:

~~~bash
build/runtime-image/bin/java \
  --module-path app/mods \
  --module com.acme.app/com.acme.app.Main
~~~

A smoke test should check at least:

1. The process starts using the exact Java executable inside the image.
2. The module graph resolves successfully.
3. The application reads mandatory configuration.
4. Required service providers are discovered and initialized.
5. The application can perform a minimal business operation.
6. The server can bind to the expected address/port if the application is a service.
7. The health endpoint or readiness signal returns a ready status.
8. The process shuts down cleanly when receiving a shutdown signal.

If the application runs in the background, check readiness rather than just waiting for the process to exist. For HTTP services, send an actual request to the health endpoint or a small business endpoint after the server has bound.

## 7. Production-Like Container Testing

If the runtime image is placed into Docker, build and run the container from the exact Dockerfile and base image planned for release.

Minimal Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/runtime-image /opt/app

RUN useradd --system --uid 10001 appuser \
    && chown -R appuser:appuser /opt/app /app

USER 10001:10001

ENTRYPOINT ["/opt/app/bin/app"]
~~~

This is only an example for a Linux image that has the `useradd` utility. Some minimal or distroless base images do not include a shell or user management commands; in that case, create the user in another build stage or use the user already provided by the base image.

Build and run:

~~~bash
docker build -t acme-app:test .
docker run --rm --name acme-app-test -p 8080:8080 acme-app:test
~~~

In the test environment, verify:

- The container uses the right base image and runtime artifact.
- The process runs under an unprivileged user like in production.
- The working directory is correct.
- Ports are published or exposed as configured.
- Environment variables and mounted configurations are complete.
- The process has permission to read application files and write to permitted directories.
- The container does not rely on a host JDK.
- Health checks and shutdown work properly.

Do not run the container as root just to make permission errors disappear. If production uses a non-root user, testing must also use a non-root user to catch misowned files or directories early.

### 7.1. Read-Only Filesystem and Temporary Directories

Many deployment environments mount the filesystem read-only to reduce the chance of mutating runtime artifacts. If the application needs to write files, explicitly identify which directories are allowed for writing, such as a temporary directory or data volume.

You can test with a read-only filesystem:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 \
  acme-app:test
~~~

Adjust mounts according to the application. Not every application can run with a read-only filesystem out of the box; the goal is to pinpoint file write paths and grant minimal necessary permissions.

Check logs, uploads, caches, PID files, temporary files, and data directories. If the application needs to persist durable data, use a managed volume instead of writing into the runtime installation directory.

### 7.2. Resource Limits and Shutdown Signals

Production containers may have CPU, memory, and PID limits. Testing under similar limits helps uncover memory allocation errors, timeouts, thread pool issues, or startup delays.

Example:

~~~bash
docker run --rm \
  --memory=512m \
  --cpus=1 \
  -p 8080:8080 \
  acme-app:test
~~~

When running the JVM inside a container, verify heap sizing and memory headroom within container limits. Heap is not total memory usage: metaspace, code cache, direct buffers, thread stacks, and native libraries also consume memory.

Send the shutdown signal in the same way the production environment does and confirm the application closes connections, flushes needed data, and exits within the grace period.

## 8. Testing OS Configuration and External Services

A runtime image only provides the Java runtime and linked modules. It does not automatically package every operating system component that the application needs.

Items that should be tested in the container or deployment host:

| Item | What to Verify |
| --- | --- |
| DNS and network | Can resolve hostnames and connect to required services. |
| TLS/CA certificates | HTTPS and TLS connections trust the environment's certificates. |
| Timezone | Displayed times, schedules, and timestamps match production configuration. |
| Locale | Number formats, date formats, encodings, and messages match expectations. |
| Native libraries | JNI/JNA and system libraries load with the right version/architecture. |
| Fonts | PDF generation, image creation, or text rendering has required fonts. |
| Proxy | The JVM and application receive proper proxy configuration if required by the environment. |
| File permissions | The runtime user can read secrets/configs and write to granted directories. |

If the application uses `java.time`, `Locale`, or TLS, do not only check that the JVM starts. Execute an actual request or test that exercises those capabilities.

For applications using JDBC, verify the driver is present, connect to the database, authenticate, and run a small query. For messaging or object storage, verify the connection and a minimal observable operation.

## 9. Testing Service Providers and Reflection in the Image

Running on a full JDK can accidentally mask bugs caused by missing provider modules or package opening configurations. A minimal runtime image helps expose these issues.

If using `ServiceLoader`, exercise the real flow to confirm providers are discovered. If providers are declared via JPMS, check `uses`, `provides`, and module linking with `jlink --bind-services`. If the application runs plugins in a separate `ModuleLayer`, test the exact layer and the exact `ServiceLoader.load(layer, service)` overload.

If a framework needs deep reflection, confirm packages are opened via descriptor `opens` or JVM option `--add-opens` in the actual launch command. A flag configured only for the test JVM does not automatically apply to the production container.

If a module needs to access public types in an unexported package, check `exports` or `--add-exports`. Do not use `opens` to replace public API access, and do not add broad flags just to make the image run without identifying which module/package actually needs access.

## 10. Testing the Exact Artifact After Every Change

A change in the module descriptor, dependency graph, service provider, JDK version, or Docker base image can alter the runtime image. Therefore, tests must run against the artifact produced by the exact build being prepared for release.

Recommended workflow:

1. Build the modular JARs and inspect module descriptors.
2. Create the runtime image using the build's exact JDK/toolchain and module path.
3. Check the module list using `bin/java --list-modules` inside the image.
4. Run smoke tests using the Java executable or launcher inside the image.
5. Build the container from that exact runtime image.
6. Run the container with production-like user, environment, volumes, and resource limits.
7. Send health requests and a few representative business requests.
8. Check logs, exit code, readiness, provider discovery, and shutdown.
9. Record the image digest, JDK version, base image digest, and test results tied to the tested artifact.

Do not reuse an old runtime image directory for testing after source code or dependencies have changed. Ensure the build output is regenerated by the CI workflow for the commit being released.

## 11. Testing on Target Platforms

If production deploys across multiple platforms or architectures, build and test the corresponding runtime image for each target. A Linux x86_64 image does not represent Linux ARM64, Windows, or macOS.

You can organize a CI matrix by:

- OS and base image version.
- CPU architecture.
- JDK vendor/version.
- Package type (runtime image, container, or native installer).
- Production configuration profile.

For each target, run at least a smoke test and check critical native dependencies. If no real runner exists for the target architecture, emulators or cross-builds provide only partial evidence; testing on the target environment is required before official release.

In particular, do not test containers only on a Linux host and assume every runtime environment is equivalent. Distributions, libc, certificate stores, and user policies may differ.

## 12. Diagnosing Common Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Image lacks java executable | Runtime image was not created properly or directory copy was incomplete | Check output structure and Docker COPY path. |
| `UnsupportedClassVersionError` | Bytecode was compiled with a newer version than the runtime | Compare `javac --release`, compile JDK, and runtime version. |
| `FindException` or module not found | Missing module in module path or image | Check descriptors, `--list-modules`, `--module-path`, and `jlink --add-modules`. |
| `ServiceConfigurationError` or missing provider | Service descriptor/provider was not resolved or linked | Check `uses`, `provides`, `--bind-services`, and module layer. |
| `InaccessibleObjectException` | Package is not open for deep reflection | Check `opens` or `--add-opens` in the actual JVM. |
| `UnsatisfiedLinkError` | Missing native library, wrong architecture, or wrong ABI | Check native libraries in the base image and target architecture. |
| TLS handshake or certificate error | Missing CA store or TLS configuration | Check trust store, certificate mounts, and JVM configuration. |
| Cannot write files | User or filesystem lacks write permission | Check UID/GID, ownership, mounts, and temporary directories. |
| Container starts and exits | Main process terminated or startup failure | Read logs, exit code, and ENTRYPOINT/CMD configuration. |
| Health check fails though process is running | App not ready, wrong port, or health endpoint | Check readiness, bind address, and container health command. |
| Runs on dev machine but fails in production | Different environment, config variables, or OS dependencies | Run the exact container/base image and production user. |

When an error occurs, keep full logs and the actual launch command. Avoid fixing by adding modules or opening packages wholesale before knowing whether the error belongs to dependencies, module access, the filesystem, or the OS runtime.

## 13. Pre-Release Checklist for Runtime Images

- [ ] Target OS, architecture, JDK, and base image are identified.
- [ ] Runtime image is built from the exact module graph and toolchain.
- [ ] `bin/java --version` and `--list-modules` of the image have been checked.
- [ ] Required service providers are resolved and initialized.
- [ ] Application starts using the executable inside the image.
- [ ] Smoke tests and health/readiness tests pass.
- [ ] Container runs as an unprivileged user.
- [ ] Config/secret read permissions and temp directory write permissions are verified.
- [ ] DNS, network, TLS, timezone, and required native dependencies are tested.
- [ ] Shutdown and resource limits are tested.
- [ ] Tested on the target platform or documented clearly where test environment limitations exist.
- [ ] Image digest and test results are attached to the release candidate artifact.

Runtime image testing must prove that the exact artifact being released can run under expected deployment conditions. Combining module graph checks, smoke tests, container integration tests, and target-platform verification catches packaging bugs early that unit tests on a full JDK often miss.
