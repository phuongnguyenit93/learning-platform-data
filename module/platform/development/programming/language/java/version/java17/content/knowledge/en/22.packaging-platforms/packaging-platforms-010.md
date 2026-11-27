# Updating Runtimes Distributed with an Application

## 1. Why Should an Application Distribute Its Own Runtime?

A Java application needs a compatible JVM and platform modules to run. If users are required to install Java themselves, the application depends on whatever runtime happens to exist on their machine:

- Users may not have Java installed.
- The Java version on the machine may be too old or too new for the application.
- Two machines may have different JDK vendors, patch levels, or configurations.
- Operating-system Java updates may alter the runtime the application uses.
- User support becomes harder when bugs occur only on a particular Java setup.

For desktop applications, internal tools, or services deployed as images, distributing a private runtime gives you control over the Java version and platform modules the application relies on.

In Java 17, the primary tools for creating and packaging runtimes are:

- **jlink:** builds a custom runtime image from JDK and application modules.
- **jpackage:** packages the application into an OS-appropriate application image or installer.
- **jdeps:** analyzes dependencies to help determine required JDK modules.
- **java, jcmd, jar:** inspect runtimes, processes, and artifact modules.

A runtime image distributed with an application is a private runtime whose update lifecycle is managed by the application team. When Java 17 security patches arrive, you must rebuild the runtime image from the updated JDK and release a new application version. Installing a newer JDK on a build server does not update runtimes already packaged and installed on user machines.

## 2. JDK, Runtime Image, and Java Applications

### 2.1. How JDK and Runtime Images Differ

The **JDK (Java Development Kit)** is built for development and operations, containing the runtime plus tools such as:

- `java`: runs applications.
- `javac`: compiles source code.
- `jlink`: builds runtime images.
- `jpackage`: packages applications.
- `jdeps`: analyzes dependencies.
- `jcmd`, `jstack`, `jmap`: diagnose running processes.
- Other tools such as `jar` and `keytool`.

A **runtime image** built with `jlink` contains only the modules needed to run the application and related runtime files. Normally, this image omits the compiler and full development toolset.

Example runtime image layout:

~~~text
runtime/
├── bin/
│   └── java
├── conf/
├── legal/
├── lib/
│   ├── modules
│   └── security/
└── release
~~~

File names and exact structure vary by platform. On Windows, the executable is `bin/java.exe`.

A runtime image can include fewer modules than a full JDK, shrinking distribution size and removing unneeded components from the execution environment.

### 2.2. No Need to Ship Compilers to End Users

Once an application is compiled into classes or modules, end users typically need only a runtime to execute it. Do not bundle an entire JDK just because the application needs the `java` command.

Some operational environments may require extra diagnostic tools. Decide intentionally based on support needs instead of defaulting to shipping `javac`, the entire toolchain, and unused modules in every release.

### 2.3. A Bundled Runtime Is a Dependency with a Lifecycle

When bundling a private runtime, the development team is responsible for:

- Choosing a JDK vendor and update stream.
- Identifying required modules.
- Testing on target operating systems and architectures.
- Tracking security patches and runtime bug fixes.
- Rebuilding the runtime image when advancing patch levels.
- Releasing updated installers/application images.
- Recording version metadata to support rollbacks and incident investigation.

Never treat a runtime directory as a static file to copy once and forget.

## 3. Two Approaches to Distributing a Runtime

### 3.1. Using a Pre-Installed Machine Runtime

The application runs via the Java installation available on `PATH` or `JAVA_HOME`:

~~~shell
java -jar application.jar
~~~

Advantages:

- Smaller application artifact.
- Operators can manage JDKs centrally.
- Runtimes are updated via host software management workflows.

Disadvantages:

- A runtime must be installed beforehand.
- Minimum version requirements and version drift must be managed.
- User environments can vary.
- Upgrading Java can impact multiple applications sharing that runtime.

This model fits server fleets or container base images that already have clear JDK management processes.

### 3.2. Bundling a Private Runtime with the Application

The application carries its own runtime image inside an application image or installer:

~~~text
AcmeApp/
├── app/
│   ├── application.jar
│   └── lib/
├── runtime/
│   ├── bin/java
│   └── lib/
└── bin/
    └── acme-launcher
~~~

Advantages:

- Users do not have to install Java themselves.
- The application controls its exact runtime.
- Included JDK modules can be minimized.
- Different application versions can carry separate runtimes.

Disadvantages:

- Installer size increases.
- Maintainers must re-release the runtime when patches arrive.
- Separate artifacts must be built per OS and architecture.
- Native libraries, installers, and runtime images must be tested on target platforms.

This model usually fits desktop applications, customer-facing tools, and products needing standalone installation.

## 4. jlink Creates Custom Runtime Images

### 4.1. How Does jlink Work?

`jlink` links compiled modules into a runtime image. It reads modules from the module path—including JDK modules and compatible application modules—and creates an image runnable via the bundled Java launcher.

Primary inputs:

- Module path: locations holding JDK modules and application modules.
- Root modules: modules selected as starting points.
- Module dependency graph: modules required by the root modules.
- Linker options: flags for optimization or creating launchers.

Simple example building a runtime from JDK modules:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/runtime
~~~

The resulting image contains the requested modules and their dependencies. This example does not bake an application JAR into the runtime; the application can run via a separate classpath alongside this runtime image.

### 4.2. jlink Needs Modules, Not Arbitrary Classpath JARs

`jlink` operates on modules. A JAR containing `module-info.class` is an explicit named module. A JAR without a descriptor can act as an automatic module on the module path, but automatic modules are not valid inputs for linking into a runtime image with `jlink`.

Therefore:

- Modular applications can place their application module and modular dependencies on the module path.
- Classpath applications can still use a minimal runtime image containing needed JDK modules while distributing application and dependency JARs separately on the classpath.
- Do not pass an arbitrary classpath library to `--add-modules` expecting `jlink` to bundle it as a module.

If a dependency is not modular, you can continue running it on the application's classpath. You do not have to modularize every JAR solely to benefit from a slim runtime image.

### 4.3. Selecting Modules with --add-modules

`--add-modules` specifies the root modules `jlink` includes in the image along with their dependencies:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/runtime
~~~

Do not guess modules from library names alone. Inspect which APIs the application uses and their corresponding modules:

| API / Feature | Commonly Related JDK Module |
|---|---|
| Core language, collections, basic I/O | `java.base` |
| Logging API | `java.logging` |
| JDBC API | `java.sql` |
| XML API | `java.xml` |
| HTTP Client | `java.net.http` |
| Management API | `java.management` |
| Desktop AWT/Swing | `java.desktop` |
| Naming/Directory API | `java.naming` |
| Scripting API | `java.scripting` |
| Additional security APIs/providers | May require matching `jdk.*` modules |

These are directional hints; the application's actual dependency graph determines required modules. One API can pull in additional modules via `requires`.

### 4.4. Analyzing Dependencies with jdeps

`jdeps` inspects bytecode dependencies and can output required JDK modules:

~~~shell
jdeps --multi-release 17 --print-module-deps application.jar
~~~

For classpath applications with dependency JARs:

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" application.jar
~~~

Output can feed directly into `jlink --add-modules`. Before using it, check:

- Whether all dependency JARs were present on the analysis classpath.
- Whether artifacts have multi-release entries matching the target version.
- Whether modules are loaded via reflection or `ServiceLoader` that `jdeps` cannot fully infer.
- Whether JNI/native libraries or dynamically loaded providers exist.

Static analysis cannot always detect modules loaded by name from configs or reflection. If an application uses plugins, scripting, JDBC driver discovery, security providers, or `ServiceLoader`, test those code paths and add needed modules.

### 4.5. jlink and ServiceLoader

An application may use service providers:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class);
~~~

If providers reside in separate modules, the module graph must include those providers. Depending on module structure and service declarations, the option:

~~~shell
--bind-services
~~~

helps `jlink` link providers for services used in the graph. Verify service descriptors, `uses`, `provides`, and run real tests; do not assume a provider module is included merely because the service API class appears in bytecode.

## 5. Useful jlink Options

### 5.1. Reducing Runtime Image Size

A commonly used command:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

Options:

| Option | Effect |
|---|---|
| `--strip-debug` | Strips unnecessary debug info from module images |
| `--no-header-files` | Excludes native header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--compress=2` | Compresses resources in the image using supported compression |
| `--bind-services` | Links service providers matching `uses` in the module graph |
| `--limit-modules` | Limits observable modules during resolution |
| `--launcher` | Generates a launcher script/executable for a module and main class |
| `--output` | Target directory for the runtime image |

Compression shrinks disk footprint but can affect resource read/decompression latency. Benchmark on your application and target filesystem before choosing.

### 5.2. Creating a Launcher with --launcher

For modular applications, you can create a launcher:

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher acme=com.acme.app/com.acme.app.Main --strip-debug --no-header-files --no-man-pages --output build/acme-runtime
~~~

In this example:

- `mods` contains the application module and its module dependencies.
- `com.acme.app` is the root module.
- `com.acme.app.Main` is the main class.
- `acme` is the generated launcher name inside the runtime image.

On Windows, the module path separator is `;`; on Linux/macOS it is `:`. Build the image on the target platform and verify the launcher inside `bin`.

### 5.3. Do Not Remove Modules by Guesswork

An overly slim runtime may show the initial screen yet fail on less common paths:

- TLS or cipher providers needing crypto modules.
- Dynamically loaded JDBC drivers.
- Locales outside the default set.
- XML parsers or scripting engines.
- Desktop toolkits.
- Logging handlers or service providers.
- Code invoking reflection on rarely used APIs/modules.

Test representative features and config-toggled paths. When uncertain, start with a broader module set and trim gradually based on analysis and tests rather than deleting modules blindly.

### 5.4. Locale Data

The JDK splits extended locale data into modules such as `jdk.localedata`. If the application needs specific locales, ensure the runtime image includes that data.

The `--include-locales` option can filter locale data when the relevant module is included:

~~~shell
--add-modules jdk.localedata --include-locales=en,vi
~~~

Only restrict locales after testing date, number, currency formatting, collation, and resource bundles across your application. Missing locale data can cause fallback formatting or unexpected behavior in a language.

### 5.5. Viewing Supported jlink Plugins

Available plugins can vary by JDK vendor and build. Run:

~~~shell
jlink --list-plugins
~~~

Do not copy options from newer JDKs into a Java 17 pipeline without verifying them. Run builds with the exact chosen JDK toolchain.

## 6. Building a Runtime for a Modular Application

### 6.1. Sample Module Structure

~~~text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.acme.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Application started");
    }
}
~~~

### 6.2. Compiling the Module

~~~shell
javac --release 17 --module-source-path src -d mods -m com.acme.app
~~~

### 6.3. Testing on the Full JDK

~~~shell
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

This confirms the module works before building a custom runtime. If the application fails on a full JDK, a minimal runtime image will not fix application bugs.

### 6.4. Linking the Runtime Image

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher acme=com.acme.app/com.acme.app.Main --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

### 6.5. Running with the Runtime Image

~~~shell
build/runtime/bin/acme
~~~

Or invoke the Java launcher and module directly:

~~~shell
build/runtime/bin/java -m com.acme.app/com.acme.app.Main
~~~

If it works on a full JDK yet fails on the runtime image, check the module graph, service providers, locales, security providers, and dynamically loaded modules.

## 7. Building a Runtime for a Classpath Application

Not every application is modularized yet. An application may still run via:

~~~shell
java -cp "app.jar:lib/*" com.acme.Main
~~~

You can still bundle a minimal JDK runtime for a classpath application by linking the required JDK modules and distributing the application JAR and dependencies separately.

### 7.1. Analyzing JDK Module Dependencies

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" app.jar
~~~

Suppose the output is:

~~~text
java.base,java.logging,java.sql
~~~

This is an illustrative output. Actual module lists depend on your application's bytecode and classpath.

### 7.2. Building a JDK-Only Runtime

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

### 7.3. Distributing the App and Dependencies Separately

~~~text
distribution/
├── runtime/
├── app/
│   ├── app.jar
│   └── lib/
│       ├── dependency-a.jar
│       └── dependency-b.jar
└── launch.sh
~~~

Launcher on Linux/macOS:

~~~shell
#!/bin/sh
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APP_DIR/runtime/bin/java" -cp "$APP_DIR/app/app.jar:$APP_DIR/app/lib/*" com.acme.Main "$@"
~~~

On Windows, the classpath separator is `;`:

~~~bat
@echo off
set "APP_DIR=%~dp0"
"%APP_DIR%runtime\bin\java.exe" -cp "%APP_DIR%app\app.jar;%APP_DIR%app\lib\*" com.acme.Main %*
~~~

Production launchers must handle arguments, working directories, log paths, and exit codes per product requirements. Never hardcode absolute build-machine paths.

### 7.4. Limitations of jdeps for Classpath Applications

Static analysis can miss modules needed for:

- `Class.forName` with class names from configuration.
- Plugins loaded at runtime.
- JDBC driver/provider discovery.
- Dynamically registered security providers.
- Scripting engines.
- JNI or native libraries.
- Resource bundles and locale data.

After building the image, test all features thoroughly and add missing modules to `--add-modules`. Never treat `jdeps` output as an exhaustive guarantee for dynamic execution paths.

## 8. Packaging Applications with jpackage

### 8.1. What Does jpackage Do?

`jpackage` creates application images or installer packages for Java applications. It bundles the launcher, application files, and runtime image so users do not need to install Java separately.

Common package types in JDK 17:

| Platform | Commonly Supported Package Types |
|---|---|
| Windows | `exe`, `msi`, `app-image` |
| macOS | `dmg`, `pkg`, `app-image` |
| Linux | `deb`, `rpm`, `app-image` |

Supported installer types depend on OS, native tools, and build environment. `app-image` is a self-contained application directory that runs directly without building a native installer.

### 8.2. jpackage for Classpath Applications

Suppose the input directory is:

~~~text
dist/
├── app.jar
└── lib/
    ├── dependency-a.jar
    └── dependency-b.jar
~~~

Create an application image using the `jlink`-built runtime:

~~~shell
jpackage --type app-image --name AcmeApp --input dist --main-jar app.jar --main-class com.acme.Main --class-path "lib/dependency-a.jar:lib/dependency-b.jar" --runtime-image build/runtime --dest build/packages
~~~

In this command:

- `--type app-image`: creates an application image.
- `--name`: application/launcher name.
- `--input`: directory containing application files.
- `--main-jar`: JAR containing the entry point.
- `--main-class`: main class.
- `--class-path`: dependency JARs relative to the input directory.
- `--runtime-image`: prebuilt runtime image from `jlink`.
- `--dest`: destination directory for packaged output.

The classpath separator in the example is `:` for Linux/macOS. On Windows, use `;`. If the app uses manifest `Class-Path` in the main JAR, verify the manifest and dependency paths after installation.

### 8.3. jpackage for Modular Applications

For modular applications, you can let `jpackage` build the runtime image via `jlink`:

~~~shell
jpackage --type app-image --name AcmeApp --module-path "mods:$JAVA_HOME/jmods" --module com.acme.app/com.acme.app.Main --jlink-options "--strip-debug --no-header-files --no-man-pages --compress=2" --dest build/packages
~~~

Here:

- `--module-path` points to application modules and JDK modules usable for building the image.
- `--module` specifies the application's module/main class.
- `--jlink-options` forwards linker flags used to create the runtime image.

Inspect `jpackage --help` for your exact JDK 17 vendor/build because platform options and requirements can differ. Module paths use `:` on Unix-like systems and `;` on Windows.

### 8.4. Building Native Installers

Once the application image works, build an installer on the target platform:

~~~shell
jpackage --type msi --name AcmeApp --input dist --main-jar app.jar --main-class com.acme.Main --runtime-image build/runtime --dest build/installer
~~~

The example above targets Windows and requires the appropriate packaging toolchain. On Linux, choose `deb` or `rpm`; on macOS, choose `dmg` or `pkg`.

Build and test packages on the target OS and architecture. An application image or installer containing platform executables and native libraries is not portable across operating systems.

### 8.5. How Application Images and Installers Differ

| Artifact | Purpose |
|---|---|
| Runtime image | Custom Java runtime, not necessarily containing an app launcher |
| Application image | Application directory containing launcher, app files, and configured runtime |
| Native installer | OS-integrated installer package capable of creating shortcuts/menus and metadata |
| Container image | Image for deploying server/app workloads with runtime and needed filesystem |

Verify the application image first. Once launcher and runtime behave reliably, build the final installer or distribution image.

## 9. Updating Runtimes Distributed with an Application

### 9.1. Why Must the Runtime Be Updated Along with the Product?

A private runtime is embedded inside the released artifact. When an application ships with a Java 17 runtime at a specific patch level, installing a newer JDK on a user's machine does not alter that bundled private runtime.

For example:

~~~text
AcmeApp 4.2
  runtime: JDK 17 build A

JDK 17 build B is released with security patches

Build machine is updated to build B
  |
  +-- Already-released AcmeApp 4.2 installer still contains build A
~~~

To deliver patches to users, rebuild the runtime image from the updated JDK, test, package, and ship a new application/installer release.

### 9.2. Controlled Update Workflow

A runtime update cycle:

1. Monitor security advisories and releases from your chosen JDK vendor.
2. Select the appropriate patch release for Java 17.
3. Update the JDK toolchain in the build environment.
4. Rebuild the runtime image with `jlink` or let `jpackage` produce a fresh runtime.
5. Rebuild the application image, installer, or container image.
6. Run functional, integration, TLS/crypto, locale, and native library tests.
7. Verify the runtime version embedded inside the artifact.
8. Sign and publish the new artifact per product release policy.
9. Maintain rollout, rollback, and user communication plans.

Never patch a runtime image installed on user machines by copying individual files from another JDK. A runtime image is a cohesive bundle of modules, native libraries, security configurations, and metadata that must stay consistent.

### 9.3. Recording Runtime Provenance

Each release should record:

- JDK vendor.
- JDK version and build number.
- OS/architecture used to build the image.
- Linked modules.
- Linker and `jpackage` options.
- Application and dependency versions.
- Checksums of the runtime image and installer.
- Test results on target platforms.

This metadata tells you exactly which runtime is deployed on customer machines and lets you reproduce builds on demand.

### 9.4. Avoid Floating Runtime Versions

Do not pull an unpinned "latest JDK 17" on every build without recording the build number. Within major version 17, patch levels, vendors, and builds can vary.

Pipelines should pin a specific JDK distribution and record its full version. When advancing patches, make an intentional change in source/build configuration and cut a new release.

### 9.5. Updating the Runtime Independently of Application Version

Sometimes application source code has not changed, yet a new release is needed purely to update the runtime. In that case, release notes should clearly state it is a runtime/security update, and the runtime version inside the artifact must reflect the update.

Do not assume users can patch the runtime by replacing the `java` executable alone. Update the entire image/application package through a tested release flow.

## 10. Choosing a JDK Vendor and Runtime Source

### 10.1. Pick a Distribution with Clear Update Policies

OpenJDK distributions can differ in:

- Release cadence and support duration.
- How security patches are delivered.
- Supported platforms and CPU architectures.
- Licensing terms and redistribution rights.
- Native libraries, crypto providers, or build configurations.

Teams should pick a vendor aligned with product policy and operational needs. Do not rely on the generic label "Java 17"; record the exact vendor and build.

### 10.2. Respecting Licenses and Notices

Runtime images may include license, copyright, and legal notice files for JDK modules. Retain the `legal` files distributed with the image. Review terms of both the JDK distribution and dependencies before bundling into commercial installers.

Do not delete the `legal` directory just to save a few megabytes. If using stripping plugins or custom packaging scripts, ensure notice obligations remain satisfied.

### 10.3. Security Patches and Support Lifecycles

Java 17 is a major release, but support status and patch schedules depend on the vendor/distribution. Use your chosen vendor's official update channels to decide which build to ship.

Runtime management needs an owner, cadence, and emergency patching process. When a runtime is embedded across thousands of client machines, plan for product distribution and upgrade time—not just upgrading the JDK on CI.

## 11. Testing the Runtime Image Before Release

### 11.1. Verifying Version and Modules

Run the executable inside the image:

~~~shell
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
~~~

On Windows:

~~~powershell
build\runtime\bin\java.exe --version
build\runtime\bin\java.exe --list-modules
~~~

Confirm:

- Version and vendor match expectations.
- Required application modules are present.
- Required crypto, locale, desktop, or provider modules are included.
- The runtime does not include unintended extra modules.

### 11.2. Running Without Relying on the Build Machine's JDK

A common pitfall is an application image accidentally invoking `java` from `PATH` instead of its bundled runtime. To verify:

- Run the application image's launcher.
- Use a machine/VM/container without an external JDK installed.
- Do not set `JAVA_HOME` to a build JDK.
- Confirm the process command line points to the runtime inside the application image.

If the application works only on machines with a full JDK, the runtime image may lack modules or the launcher may be resolving the wrong Java executable.

### 11.3. Testing Dynamic Features

Run tests for features that `jdeps` may miss:

- JDBC drivers and connection pools.
- TLS/HTTPS, certificates, and crypto providers.
- `ServiceLoader` and plugins.
- Locales, date/number/currency formatting.
- XML or scripting if used.
- Reflection and dynamic class loading.
- JNI and native libraries.
- GUI, fonts, printing, or media for desktop applications.

### 11.4. Testing on Each OS and Architecture

Runtime images contain native components tailored to the build platform. Test separately across:

- Windows x64/ARM64 if supported.
- Linux distributions/libc and CPU architectures.
- macOS Intel/Apple Silicon if supported.
- Native libraries and launcher executables.
- Installer upgrades/uninstalls, shortcuts, file associations, and write permissions.

Never assume a Linux runtime image runs as-is on Windows or macOS.

### 11.5. Checking Data Paths

Never store user files, logs, or mutable configs inside the runtime image directory if installers can update or replace that directory.

Separate:

- Application binaries.
- Runtime image.
- User configuration.
- User data.
- Logs and diagnostic files.

Store mutable data in appropriate user or service-account directories so runtime upgrades never erase application data.

## 12. Runtime Images in Docker and Kubernetes

### 12.1. Packaging a Runtime into a Container Image

A container image can hold a `jlink` runtime image alongside the application JAR:

~~~dockerfile
FROM debian:stable-slim
WORKDIR /opt/acme
COPY runtime/ /opt/acme/runtime/
COPY app/ /opt/acme/app/
ENTRYPOINT ["/opt/acme/runtime/bin/java", "-cp", "/opt/acme/app/app.jar:/opt/acme/app/lib/*", "com.acme.Main"]
~~~

This is a conceptual example. Choose base images, users, certificates, timezone data, CA trust, and native dependencies to fit your application and deployment environment.

### 12.2. Updating the Base Image vs. Updating the Runtime

A container may consist of:

- Base OS image.
- JDK runtime image copied into the container image.
- Application files.

Upgrading the base OS image does not automatically update a Java runtime copied into a layer. Likewise, upgrading the JDK on a build agent does not alter runtimes already inside older container images.

When updating:

1. Rebuild from the patched base image.
2. Rebuild the `jlink` runtime from the patched JDK.
3. Copy the runtime and application into the container image.
4. Scan and test the image.
5. Push the new image and roll out via pinned digest/version.

### 12.3. Using Immutable Images

In container environments, prefer building a new image and rolling out replacements over exec'ing into running containers to edit runtime files in place. Immutable images make it easy to:

- Track the exact running version.
- Roll back safely.
- Audit and verify artifacts.
- Prevent runtime drift across replicas sharing the same tag.

## 13. Optimizing Runtime Size and Performance

### 13.1. Omitting Unused Modules

A smaller runtime image speeds up downloads, trims install footprint, and reduces unused components. However, the goal is not the smallest image at all costs.

Keep modules required for all features and security providers. A slim image missing a TLS provider, locale, or JDBC support causes hard-to-diagnose failures.

### 13.2. Measuring Footprint Before and After

Record:

- Full JDK size.
- Runtime image size.
- Application image size.
- Installer size.
- Startup time.
- Key feature execution times.

Compression and strip options can alter both footprint and startup. Measure on the same OS/filesystem under identical workloads.

### 13.3. Do Not Confuse Runtime Size with Heap Size

`jlink` reduces distributed modules and runtime files. It does not directly configure max heap, thread stacks, metaspace, or container memory limits.

Heap sizing is still controlled via JVM flags such as `-Xms`, `-Xmx`, or percentage flags. A smaller runtime image does not automatically mean the application needs less heap memory.

## 14. Security and Operations for Distributed Runtimes

### 14.1. Keeping Runtimes Aligned with Patches

Follow vendor security advisories and schedule regular updates. When a patch affects the Java 17 runtime, evaluate impact on the application, rebuild images, and ship updated artifacts. Do not wait for users to install a new JDK to patch your app's private runtime.

### 14.2. Controlling Runtime Files

- Do not grant application users write access to runtime executables or module files unnecessarily.
- Set appropriate filesystem permissions.
- Do not run applications as administrator/root merely to read the runtime.
- Preserve legal and security configuration files.
- Never drop unknown native libraries into the runtime directory.

### 14.3. Trust Stores and Security Configuration

A runtime image may carry the JDK's security configuration and trust store. If the application uses TLS, check:

- Which CA certificates come from the runtime, base OS, or application config.
- Which trust store the JVM actually loads.
- Required crypto providers and modules.
- Processes for updating CA certificates.

Do not edit security configuration files manually outside version control. When custom settings are needed, build a new image or supply managed external configuration.

### 14.4. Native Libraries

If the application uses JNI or native libraries:

- Distribute matching binaries per OS and architecture.
- Check system library and `libc` dependencies.
- Verify loader paths.
- Test in clean environments.
- Update native libraries alongside releases when patches arrive.

Java runtime images do not automatically bundle third-party native dependencies.

## 15. Troubleshooting Runtime Images and Installers

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| `Module ... not found` | Module omitted from image or wrong module path | Check `--add-modules`, module path, and module graph |
| `NoClassDefFoundError` | Missing class/JAR dependency or missing module | Inspect classpath/module path and packaged files |
| `ClassNotFoundException` | Dynamically loaded class missing from distribution | Check plugins, config, and class loaders |
| Service provider not found | Provider/module/service descriptor not packaged | Check `uses`, `provides`, and `--bind-services` |
| TLS/crypto errors after slimming runtime | Missing crypto provider/module or security config | Check crypto modules and run TLS tests |
| Locales display wrong/fallback formatting | Missing locale data or resource bundles | Check `jdk.localedata`, locales, and resources |
| Launcher runs with a different Java | Misconfigured `PATH`/`JAVA_HOME` or launcher config | Inspect process command line and runtime paths |
| Native library load failed | Binary has wrong architecture or missing OS dependencies | Check native binary, loader, and OS |
| Installer succeeds yet app won't start | Wrong runtime, modules, permissions, or paths | Run the app-image directly and inspect launcher logs |
| Update still uses old Java | New installer lacks updated runtime or app picks up system Java | Verify runtime version inside the artifact |
| Works on one OS, fails on another | Image/native library/installer is platform-specific | Build and test artifacts separately per OS/architecture |

When troubleshooting, inspect the runtime image first with `runtime/bin/java --version` and `--list-modules`, then run the application launcher with enough logging to confirm the actual executable and class/module paths.

## 16. Example Pipeline for Building Runtime and Application Images

A simple pipeline for a modular application:

~~~text
Source + dependencies
        |
        v
Compile with JDK 17
        |
        v
Resolve module graph
        |
        v
jlink / jpackage
        |
        v
Application image
        |
        v
Test on target OS and architecture
        |
        v
Sign + publish artifact
        |
        v
User installs application with private runtime
~~~

Steps that can be automated:

1. Pin a specific JDK vendor and build in the build environment.
2. Compile with `--release 17`.
3. Inspect modules/dependencies via `jdeps` and module descriptors.
4. Build a runtime image or let `jpackage` invoke `jlink`.
5. Build the application image.
6. Run smoke tests in an environment with no external JDK.
7. Run feature and native integration tests.
8. Verify runtime version, module list, and package contents.
9. Sign artifacts and store checksums/provenance.
10. Publish to your update channel and retain rollback artifacts.

For classpath applications, replace the module graph step with JDK module dependency analysis, build a JDK-only runtime, and bundle the app JAR and dependencies on the classpath.

## 17. Comprehensive Example: Building a Runtime Image for a Modular App

Suppose the application module is `com.acme.desktop`, its main class is `com.acme.desktop.Main`, and compiled modules reside in `mods`.

Create the runtime image:

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.desktop --launcher acme=com.acme.desktop/com.acme.desktop.Main --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

Inspect the runtime:

~~~shell
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
~~~

Run the launcher:

~~~shell
build/runtime/bin/acme
~~~

Creating a separate application image from a linked runtime image and modules is not always mandatory; the runtime image above already contains a launcher. You can distribute that image directory as an application bundle, adding resources and platform install scripts. If you want a native installer and prefer `jpackage` to manage launcher/package layout, configure `jpackage` for modular apps using `--module-path`, `--module`, and `--jlink-options` so it builds the runtime image during packaging.

Example of `jpackage` creating an application image from a module path:

~~~shell
jpackage --type app-image --name AcmeDesktop --module-path "mods:$JAVA_HOME/jmods" --module com.acme.desktop/com.acme.desktop.Main --jlink-options "--strip-debug --no-header-files --no-man-pages --compress=2" --dest build/packages
~~~

On Windows, change the module path separator to `;`. Once built, run the launcher inside `build/packages/AcmeDesktop` on a clean test machine and verify the bundled runtime is used.

## 18. Practice Exercises

### Exercise 1 — Inspecting the JDK and Runtime Images

Run:

~~~shell
java --version
java --list-modules
jlink --version
jpackage --version
~~~

Record the vendor/build and module list of JDK 17. Compare against a runtime image built from a small set of modules.

### Exercise 2 — Analyzing Dependencies with jdeps

Create or pick a Java 17 application with several dependency JARs. Run:

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" app.jar
~~~

Build a runtime image from the printed modules. Verify whether all application features work, and add modules if any dynamic dependencies exist.

### Exercise 3 — Linking a Modular Application

Create a module with `module-info.java`, compile into `mods`, then run `jlink` with `--add-modules` and `--launcher`. Run via the generated launcher without using the full JDK.

### Exercise 4 — Comparing Linker Options

Build two runtime images: one with defaults and one with `--strip-debug`, `--no-header-files`, `--no-man-pages`, and `--compress=2`. Compare disk size and startup time.

### Exercise 5 — Creating an Application Image with jpackage

Use `jpackage` to create an `app-image` for a classpath application with a private runtime. Check the launcher, classpath, runtime directory, and how the app locates config files.

### Exercise 6 — Updating a Runtime Patch

In a test environment, build an artifact using one JDK 17 patch build and record its version in release metadata. Then update the build JDK to a newer patch, rebuild the runtime/app image, and confirm the runtime version inside the artifact changed.

### Exercise 7 — Testing in a Clean Environment

Copy the application image to a VM/container without a JDK installed. Run the app and test TLS, locales, JDBC, plugins, or other dynamic features used. Note any errors caused by missing modules or native dependencies.

### Exercise 8 — Testing Updates and Rollbacks

Create two artifacts carrying different runtime versions. Install the first, upgrade to the second, and confirm user data/configuration remain intact. Test rolling back according to your release process.

## 19. Self-Check Questions

1. How does a JDK differ from a runtime image?
2. Why does an application bundling its own runtime need its own update workflow?
3. Does `jlink` accept only modules or any kind of JAR?
4. Why are automatic modules unsuitable as `jlink` inputs?
5. What does `--add-modules` specify?
6. Which dynamically loaded dependencies can `jdeps` miss?
7. How does `--bind-services` help when an application uses `ServiceLoader`?
8. What do `--strip-debug`, `--no-man-pages`, and `--compress=2` do?
9. Why might an overly slim runtime fail on TLS or JDBC even if the app launches?
10. Can a classpath application use a `jlink` runtime image?
11. How does `jpackage` differ from `jlink`?
12. How does an application image differ from a native installer?
13. Why should you test the application image before building an installer?
14. Why must `jlink` artifacts be built separately per OS and architecture?
15. Does upgrading the JDK on a build server automatically update already-distributed runtimes?
16. What metadata should be recorded to trace runtime provenance?
17. Why shouldn't you patch an installed runtime image by copying a new `java` executable?
18. Does updating a container base image automatically update a runtime copied into that image?
19. Why should user data never live inside the runtime directory?
20. How can you verify an application actually runs on its bundled runtime?

## 20. References

- [Java SE 17 jlink Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): creating runtime images and linker options.
- [Java SE 17 jpackage Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): creating application images and installer packages.
- [Java SE 17 jdeps Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): analyzing dependencies and module dependencies.
- [Java SE 17 java Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): running applications, module paths, and runtime options.
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282): design of the custom runtime image linker tool.
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): Java application packaging tool.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): module path, module graph, and module resolution.

Distributing a runtime alongside your application gives you control over the Java version and reduces reliance on user machine environments. In Java 17, use `jlink` to create runtime images with the required modules, `jpackage` to create application images or installers, and `jdeps` as a starting point for dependency analysis. Every runtime image is an artifact with its own lifecycle: pin the JDK vendor/build, test on target platforms, record provenance, and rebuild and re-release images whenever Java patches arrive. Never assume a packaged runtime updates automatically just because the JDK on a build host or operating system has changed.
